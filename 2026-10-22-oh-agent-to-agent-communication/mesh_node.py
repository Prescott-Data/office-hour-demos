"""One agent, one terminal, one peer in the mesh.

    python mesh_node.py analyst 7946                    # first node (the seed)
    python mesh_node.py writer  7947 127.0.0.1:7946     # every other node points at the seed
    python mesh_node.py scout   7948 127.0.0.1:7946

No LLM key. No Redis. No broker. Ctrl+C a terminal and watch the others notice.
"""
import asyncio
import logging
import signal
import sys
import time

from jarviscore import Mesh
from jarviscore.core.agent import Agent

logging.disable(logging.WARNING)

ROLE = sys.argv[1]
PORT = int(sys.argv[2])
SEED = sys.argv[3] if len(sys.argv) > 3 else ""


def say(text):
    print(time.strftime("%H:%M:%S"), text, flush=True)


class Peer(Agent):
    role = ROLE
    capabilities = [ROLE]
    description = f"the {ROLE}"

    async def execute_task(self, task):
        return {"status": "completed", "by": ROLE}


async def answer_requests(me):
    """Reply to anyone who asks. Nobody routes these messages but the peers themselves."""
    while True:
        msg = await me.peers.receive(timeout=5)
        if msg is not None:
            await me.peers.respond(msg, {"reply": f"hello from the {ROLE}"})


async def watch_roster(me):
    """Print who joins and who leaves. Nobody maintains this list by hand."""
    seen = set()
    while True:
        now = {p["role"] for p in me.peers.list_peers()}
        for role in sorted(now - seen):
            say(f"  + {role} joined")
        for role in sorted(seen - now):
            say(f"  - {role} left")
        seen = now
        await asyncio.sleep(1)


async def say_hello(me):
    """Every few seconds, ask one peer something directly."""
    while True:
        await asyncio.sleep(4)
        peer = me.peers.discover_one(strategy="round_robin")
        if peer is None:
            continue
        reply = await me.peers.request(peer.role, {"ping": ROLE}, timeout=3)
        if not reply:
            outcome = "no answer"
        else:
            outcome = reply.get("reply") or "not ready yet"  # it joined a moment ago
        say(f"  {ROLE} -> {peer.role}: {outcome}")


async def main():
    mesh = Mesh(config={"p2p_enabled": True, "bind_host": "127.0.0.1",
                        "bind_port": PORT, "seed_nodes": SEED})
    me = mesh.add(Peer)
    await mesh.start()
    loop, task = asyncio.get_running_loop(), asyncio.current_task()
    for sig in (signal.SIGINT, signal.SIGTERM):  # Ctrl+C or a kill: leave politely
        loop.add_signal_handler(sig, task.cancel)
    say(f"[{ROLE}] up on port {PORT}" + (f", seed {SEED}" if SEED else " (I am the seed)"))
    try:
        await asyncio.gather(answer_requests(me), watch_roster(me), say_hello(me))
    finally:
        await mesh.stop()  # says goodbye, so the others see "- role left"


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    say(f"[{ROLE}] left the mesh")
