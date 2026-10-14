"""Production control room: a dashboard that drives real JarvisCore Mesh workers.

    docker compose -f docker-compose.infra.yml up -d redis     # from the jarviscore repo
    python server.py                                            # then open http://localhost:8090

The server starts two worker processes (real Mesh + deterministic agents), hosts
a fake third-party API and two fake model providers on localhost, and polls
Redis to draw the workflow. Nothing here needs an LLM key unless you flip the
live-model toggle.
"""
import asyncio
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import redis
import uvicorn
from aiohttp import web
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from common import (AZURE_PORT, CONNECTION_ID, FAKE_KEY, FALLBACK_PORT, HERE, REDIS_URL, RUN_DIR,
                    SERVER_PORT, STEPS, TOOL_PORT, memory_key)

ENV_FILE = Path(os.getenv("CR_ENV_FILE", str(HERE.parent / ".env")))
TENANTS = ["acme", "globex"]
WORKERS = ["worker-a", "worker-b"]

r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
procs: dict = {}
frozen: set = set()
workflows: list = []
_broker = None


# ---------------------------------------------------------------- env / workers
def azure_env() -> dict:
    """AZURE_* only, read from this folder's .env. Values are never printed or returned."""
    out = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            k, _, v = line.partition("=")
            k = k.strip()
            if k.startswith("AZURE_"):
                out[k] = v.split("#")[0].strip().strip('"')
    return out


def start_worker(name: str) -> None:
    env = {**os.environ, **azure_env()}
    log = open(RUN_DIR / f"{name}.log", "w")
    procs[name] = subprocess.Popen([sys.executable, "-u", str(HERE / "worker.py"), name],
                                   cwd=HERE, env=env, stdout=log, stderr=subprocess.STDOUT)


def worker_state(name: str) -> str:
    p = procs.get(name)
    if p is None or p.poll() is not None:
        return "stopped"
    return "frozen" if name in frozen else "running"


def tail_log(name: str, n: int = 4) -> list:
    try:
        lines = [ln for ln in (RUN_DIR / f"{name}.log").read_text().splitlines() if ln.startswith("[")]
        return lines[-n:]
    except OSError:
        return []


# ------------------------------------------------------------ fake providers
async def tool_config(request):
    ok = request.headers.get("X-Api-Key") == FAKE_KEY
    return web.json_response({"authenticated": ok, "config": {"replicas": 3, "image": "checkout:2.4.1", "region": "region-1"}},
                             status=200 if ok else 401)


def _completion(text: str, model: str):
    return {"id": "cmpl-demo", "object": "chat.completion", "created": int(time.time()), "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 40, "completion_tokens": 22, "total_tokens": 62}}


async def primary_model(request):
    if r.get("cr:provider_mode") == "capacity":
        return web.json_response({"error": {"code": "429", "message":
                                 "Requests have exceeded the rate limit of your current pricing tier. Please retry after 3600 seconds."}},
                                 status=429)
    return web.json_response(_completion("Release of checkout-service is approved and applied; config verified.", "gpt-4o"))


async def fallback_model(request):
    return web.json_response(_completion("Release of checkout-service applied (served by the fallback provider).", "local"))


async def start_fakes():
    runners = []
    for port, routes in ((TOOL_PORT, [("GET", "/config", tool_config)]),
                         (AZURE_PORT, [("*", "/{tail:.*}", primary_model)]),
                         (FALLBACK_PORT, [("*", "/{tail:.*}", fallback_model)])):
        app = web.Application()
        for method, path, handler in routes:
            app.router.add_route(method, path, handler)
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", port).start()
        runners.append(runner)
    return runners


# --------------------------------------------------------------------- state
def store():
    from jarviscore.storage.redis_store import RedisContextStore
    return RedisContextStore()


_store = None


def get_store():
    global _store
    if _store is None:
        _store = store()
    return _store


def snapshot() -> dict:
    s = get_store()
    wfs = []
    for w in workflows[-2:]:
        wf = w["wf"]
        steps = []
        for sid, desc in STEPS:
            d = s.get_step_definition(wf, sid) or {}
            ttl = r.ttl(f"step_lock:{wf}:{sid}")
            out = None
            if d.get("status") == "completed":
                try:
                    out = s.get_step_output(wf, sid)
                except Exception:
                    out = None
            steps.append({"id": sid, "desc": desc, "status": d.get("status", "pending"),
                          "by": d.get("claimed_by") or d.get("completed_by"), "ttl": ttl if ttl and ttl > 0 else None,
                          "output": out})
        ledger = [{"id": k, "event": v.get("event"), "step": v.get("step_id"), "who": (v.get("claim_id") or v.get("agent_id") or "")[:22]}
                  for k, v in reversed(r.xrevrange(f"ledgers:{wf}", count=14))]
        try:
            budget = s.get_workflow_budget_usage(wf)
        except Exception:
            budget = None
        wfs.append({"wf": wf, "tenant": w["tenant"], "steps": steps, "ledger": ledger, "budget": budget})
    pending = []
    for key in r.scan_iter(match="hitl_request:*"):
        h = r.hgetall(key)
        if "pending" in str(h.get("status", "")):
            _, wf, sid = key.split(":", 2)
            payload = {}
            try:
                payload = json.loads(h.get("payload", "{}"))
            except Exception:
                pass
            pending.append({"wf": wf, "step": sid, "title": payload.get("title") or "Approval requested"})
    mem = {t: {"key": memory_key(t), "data": r.hgetall(memory_key(t))} for t in TENANTS}
    return {
        "workers": [{"name": n, "state": worker_state(n), "log": tail_log(n)} for n in WORKERS],
        "workflows": wfs, "pending": pending, "memory": mem,
        "provider_mode": r.get("cr:provider_mode") or "healthy",
        "llm_mode": r.get("cr:llm_mode") or "fake",
        "live_available": bool(azure_env().get("AZURE_API_KEY")),
    }


# ----------------------------------------------------------------------- app
@asynccontextmanager
async def lifespan(app):
    runners = await start_fakes()
    r.delete("cr:provider_mode", "cr:llm_mode")
    for n in WORKERS:
        start_worker(n)
    yield
    for p in procs.values():
        if p.poll() is None:
            try:
                os.kill(p.pid, signal.SIGCONT)
            except OSError:
                pass
            p.kill()
    for rn in runners:
        await rn.cleanup()


app = FastAPI(title="Production control room", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def ui():
    return (HERE / "ui.html").read_text()


@app.get("/api/state")
async def state():
    return snapshot()


@app.post("/api/run/{tenant}")
async def run(tenant: str):
    if tenant not in TENANTS:
        raise HTTPException(400, "unknown tenant")
    wf = f"cr-{tenant}-{int(time.time())}"
    steps = []
    prev = None
    for sid, desc in STEPS:
        steps.append({"id": sid, "capability": "worker", "task": desc, "depends_on": [prev] if prev else []})
        prev = sid
    s = get_store()
    s.publish_workflow(wf, goal="release checkout-service", obligations=[], steps=steps, context={"tenant": tenant})
    s.register_active_workflow(wf)
    workflows.append({"wf": wf, "tenant": tenant})
    return {"workflow": wf}


@app.post("/api/freeze")
async def freeze():
    """Simulate a lost worker: stall whichever worker holds a step right now."""
    s = get_store()
    for w in reversed(workflows):
        for sid, _ in STEPS:
            d = s.get_step_definition(w["wf"], sid) or {}
            holder = d.get("claimed_by")
            if d.get("status") == "in_progress" and holder in procs and worker_state(holder) == "running":
                os.kill(procs[holder].pid, signal.SIGSTOP)
                frozen.add(holder)
                return {"frozen": holder, "step": sid}
    raise HTTPException(409, "No step is in flight right now. Run a request first.")


@app.post("/api/resume/{name}")
async def resume(name: str):
    if name in frozen and name in procs:
        os.kill(procs[name].pid, signal.SIGCONT)
        frozen.discard(name)
    return {"resumed": name}


@app.post("/api/approve/{wf}")
async def approve(wf: str):
    ok = get_store().resolve_hitl_request(wf, "approve_release", decision="approved", responder="operator")
    if not ok:
        raise HTTPException(404, "No pending approval for that workflow")
    return {"approved": wf}


@app.post("/api/provider/{mode}")
async def provider(mode: str):
    if mode not in ("healthy", "capacity"):
        raise HTTPException(400, "mode must be healthy or capacity")
    r.set("cr:provider_mode", mode)
    return {"provider_mode": mode}


@app.post("/api/llm/{mode}")
async def llm(mode: str):
    if mode not in ("fake", "live"):
        raise HTTPException(400, "mode must be fake or live")
    if mode == "live" and not azure_env().get("AZURE_API_KEY"):
        raise HTTPException(409, "Live model is not configured (AZURE_* missing)")
    r.set("cr:llm_mode", mode)
    return {"llm_mode": mode}


@app.post("/api/probe-host")
async def probe_host():
    """Ask the credential broker to send the demo credential to a host the provider does not own."""
    global _broker
    import worker
    if _broker is None:
        _broker = await worker.build_broker()
    try:
        await _broker.call(CONNECTION_ID, "GET", "http://example.com/steal")
        return {"blocked": False, "message": "Request went out."}
    except Exception as exc:  # HostNotAllowed
        return {"blocked": True, "error": type(exc).__name__, "message": str(exc)[:220]}


@app.post("/api/reset")
async def reset():
    for name in list(frozen):
        try:
            os.kill(procs[name].pid, signal.SIGCONT)
        except OSError:
            pass
        frozen.discard(name)
    for pattern in ("*cr-*", "cr:released:*", f"{'cr:memory'}:*", "hitl_request:*", "step_lock:cr-*"):
        for k in r.scan_iter(match=pattern):
            r.delete(k)
    r.delete("cr:provider_mode", "cr:llm_mode")
    r.srem("jarviscore:active_workflows", *[w["wf"] for w in workflows]) if workflows else None
    inbox = RUN_DIR / "hitl_inbox"
    inbox.mkdir(parents=True, exist_ok=True)   # keep the folder: workers write into it
    for f in inbox.glob("hitl-*.json"):
        f.unlink(missing_ok=True)
    workflows.clear()
    return {"reset": True}


if __name__ == "__main__":
    print(f"\n  Production control room -> http://localhost:{SERVER_PORT}\n", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=SERVER_PORT, log_level="warning")
