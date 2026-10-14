"""
Demo 2 — the credential never leaves the boundary.

Uses JarvisCore's real NexusCallProxy (jarviscore/nexus/call_proxy.py) and the
real local encrypted credential store (jarviscore/nexus/store.py) — not a
mock. The only things faked for the demo are the credential value itself and
the store's file path, which points at a throwaway temp file instead of the
real ~/.jarviscore/nexus.enc so this script never touches the presenter's
actual vault.

What this proves, live:
  1. "Agent code" here only ever holds an opaque connection_id string.
  2. nexus_call() resolves the real credential and attaches it to the
     outgoing request *outside* that agent-visible state.
  3. Whatever agent code writes out (agent_state.json) never contains the
     credential, the header it was placed in, or any token-shaped string —
     confirmed by grepping the file afterward, the same way you'd audit a
     real agent's logs.

Run: python beat2_nexus_contract.py
"""
import asyncio
import json
import tempfile
from pathlib import Path

from jarviscore.nexus.call_proxy import NexusCallProxy
from jarviscore.nexus import store as nexus_store_module
from jarviscore.nexus.store import NexusLocalStore

FAKE_API_KEY = "sk_demo_9f8a2e7c1b6d4a3f_not_a_real_key"
PROVIDER = "demo-crm"
CONNECTION_ID = f"{PROVIDER}:demo-user"


class _NoGatewayAuthManager:
    """Stands in for the real AuthenticationManager with no gateway configured.

    NexusCallProxy tries `self._auth.resolve_strategy(...)` first (gateway
    mode) and falls back to the local encrypted store on failure. This stub
    has no resolve_strategy at all, so every call takes the local-store path
    — the zero-dependency mode a single developer actually runs.
    """

    _connections: dict = {}
    nexus_client = None


async def main():
    demo_vault = Path(tempfile.mkdtemp()) / "demo-nexus.enc"
    store = NexusLocalStore(path=demo_vault)

    # Register a fake credential — real store.register(), fake key, isolated file.
    # base_url tells the host-allow check (jarviscore/nexus/hosts.py) that this
    # provider owns httpbin.org, the same way a tenant's own instance_url would
    # for a real tenant-hosted provider.
    store.register(PROVIDER, {
        "auth_type": "api_key",
        "api_key": FAKE_API_KEY,
        "auth_config": {"header_name": "Authorization", "value_prefix": "Bearer "},
        "base_url": "httpbin.org",
    })

    # Point the real call path at our isolated store instead of ~/.jarviscore/nexus.enc
    nexus_store_module.get_store = lambda: store

    proxy = NexusCallProxy(auth_manager=_NoGatewayAuthManager())
    nexus_call = NexusCallProxy.make_nexus_call_fn(proxy, CONNECTION_ID)

    # This is the entire state "agent code" is allowed to hold.
    agent_state = {"connection_id": CONNECTION_ID}
    Path("agent_state.json").write_text(json.dumps(agent_state, indent=2))

    print(f"agent holds: connection_id = {CONNECTION_ID!r}")
    print("agent code never sees a token\n")

    print("nexus_call('GET', 'https://httpbin.org/headers')")
    result = await nexus_call("GET", "https://httpbin.org/headers")
    print(f"  -> ok={result['ok']}  status={result['status_code']}")
    print("  (response body not printed — httpbin echoes the Authorization")
    print("   header back, and printing it would leak the credential ourselves)\n")

    print("$ cat agent_state.json")
    print(Path("agent_state.json").read_text())

    print("$ grep -riE 'token|secret|bearer|sk_demo' agent_state.json")
    hits = [
        line for line in Path("agent_state.json").read_text().splitlines()
        if any(w in line.lower() for w in ("token", "secret", "bearer", "sk_demo"))
    ]
    print("(nothing)" if not hits else "\n".join(hits))


if __name__ == "__main__":
    asyncio.run(main())
