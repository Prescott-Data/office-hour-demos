"""A real JarvisCore Mesh worker for the control-room demo.

Deterministic CustomAgent (no LLM needed for the workflow itself). Each worker
process runs the framework's distributed worker loop: it claims steps from the
shared Redis workflow with a leased lock, heartbeats the lease, and commits.

    python worker.py worker-a
"""
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

import redis

from common import (CONNECTION_ID, FAKE_KEY, LEASE_SECONDS, POLL_SECONDS, PROVIDER,
                    REDIS_URL, RUN_DIR, TOOL_PORT, AZURE_PORT, FALLBACK_PORT, memory_key)


def say(name, msg):
    print(f"[{name}] {msg}", flush=True)


async def build_broker():
    """Real NexusCallProxy over an isolated throwaway vault (never the presenter's real one)."""
    from jarviscore.nexus import store as nexus_store_module
    from jarviscore.nexus.call_proxy import NexusCallProxy
    from jarviscore.nexus.store import NexusLocalStore

    vault = Path(tempfile.mkdtemp()) / "control-room-nexus.enc"
    store = NexusLocalStore(path=vault)
    store.register(PROVIDER, {
        "auth_type": "api_key",
        "api_key": FAKE_KEY,
        "auth_config": {"header_name": "X-Api-Key"},
        "base_url": "127.0.0.1",   # the host this provider is allowed to reach
    })
    nexus_store_module.get_store = lambda: store

    class NoGateway:
        _connections: dict = {}
        nexus_client = None

    return NexusCallProxy(auth_manager=NoGateway())


def llm_config(mode):
    base = {
        "promo_token": None, "claude_api_key": None, "anthropic_api_key": None,
        "gemini_api_key": None, "vertex_ai_enabled": False,
    }
    if mode == "live":
        return {**base,
                "azure_api_key": os.environ["AZURE_API_KEY"],
                "azure_endpoint": os.environ["AZURE_ENDPOINT"],
                "azure_deployment": os.environ.get("AZURE_DEPLOYMENT", "gpt-4o"),
                "azure_api_version": os.environ.get("AZURE_API_VERSION", "2025-01-01-preview")}
    return {**base,
            "azure_api_key": "fake-key", "azure_endpoint": f"http://127.0.0.1:{AZURE_PORT}",
            "azure_deployment": "gpt-4o",
            "llm_endpoint": f"http://127.0.0.1:{FALLBACK_PORT}", "llm_model": "local"}


async def run(name):
    from jarviscore import Mesh
    from jarviscore.execution.llm import UnifiedLLMClient
    from jarviscore.profiles import CustomAgent

    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    broker = await build_broker()

    class OpsWorker(CustomAgent):
        role = "worker"
        capabilities = ["worker"]

        async def execute_task(self, task):
            ctx = task["context"]
            step, wf, tenant = ctx["step_id"], ctx["workflow_id"], ctx.get("tenant", "acme")
            say(name, f"running {step} (tenant={tenant})")
            await asyncio.sleep(2.0)
            out = await getattr(self, f"step_{step}")(wf, tenant, ctx)
            return {"status": "success", "output": out}

        async def step_intake(self, wf, tenant, ctx):
            return {"request": "release checkout-service", "tenant": tenant}

        async def step_plan(self, wf, tenant, ctx):
            plan = "1) fetch config 2) approval 3) apply 4) summarize"
            r.hset(memory_key(tenant), mapping={"plan": plan, "workflow": wf})
            return {"remembered_under": memory_key(tenant)}

        async def step_fetch_config(self, wf, tenant, ctx):
            resp = await broker.call(CONNECTION_ID, "GET", f"http://127.0.0.1:{TOOL_PORT}/config")
            body = resp.get("json") or {}
            # the agent's output holds a handle and a result, never the credential
            return {"connection_id": CONNECTION_ID, "http": resp["status_code"],
                    "authenticated": body.get("authenticated"), "config": body.get("config")}

        async def step_approve_release(self, wf, tenant, ctx):
            rid = self.hitl.request(
                title="Approve production release: checkout-service",
                content="Irreversible: applies the new config to production.",
                urgency="high", category="critical_action",
                context={"workflow_id": wf, "step_id": "approve_release", "tenant": tenant},
            )
            say(name, f"waiting for human approval ({rid})")
            res = await self.hitl.wait(rid, timeout=600, poll_interval=0.5)
            return {"approved": str(getattr(res, "decision", res)), "request_id": rid}

        async def step_execute(self, wf, tenant, ctx):
            first = r.set(f"cr:released:{wf}", name, nx=True)   # idempotent: safe to run twice
            owner = r.get(f"cr:released:{wf}")
            return {"applied": bool(first), "released_by": owner}

        async def step_summarize(self, wf, tenant, ctx):
            mode = r.get("cr:llm_mode") or "fake"
            client = UnifiedLLMClient(config=llm_config(mode))
            t0 = time.time()
            res = await client.generate(
                "In one sentence, summarize this production release for the on-call channel.",
                max_tokens=80)
            return {"provider": res["provider"], "mode": mode,
                    "elapsed_s": round(time.time() - t0, 1),
                    "answer": (res.get("content") or "")[:200]}

    cfg = {
        "redis_url": REDIS_URL,
        "p2p_enabled": False,
        "distributed_claim_lease_seconds": LEASE_SECONDS,
        "distributed_poll_interval": POLL_SECONDS,
        "hitl_inbox_dir": str(RUN_DIR / "hitl_inbox"),
    }
    mesh = Mesh(config=cfg)
    mesh.add(OpsWorker, agent_id=name)
    await mesh.start()
    say(name, "up")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1]))
