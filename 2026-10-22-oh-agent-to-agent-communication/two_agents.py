"""Checkpoint 1: two agents, one file, a direct request and a reply.

    python two_agents.py

No network, no Redis, no LLM key. The agents never name each other in config.
"""
import asyncio
import logging

from jarviscore import Mesh
from jarviscore.core.agent import Agent

logging.disable(logging.WARNING)


class Analyst(Agent):
    role = "analyst"
    capabilities = ["analysis"]
    description = "reads findings and gives a verdict"

    async def execute_task(self, task):
        return {"status": "completed"}

    async def listen(self):
        """Answer whoever asks. No orchestrator hands these messages over."""
        while True:
            msg = await self.peers.receive(timeout=5)
            if msg is not None:
                await self.peers.respond(msg, {"verdict": "signal, not noise"})


class Researcher(Agent):
    role = "researcher"
    capabilities = ["research"]
    description = "finds things worth checking"

    async def execute_task(self, task):
        return {"status": "completed"}


async def main():
    mesh = Mesh(config={"p2p_enabled": False})
    analyst = mesh.add(Analyst)
    researcher = mesh.add(Researcher)
    await mesh.start()
    listening = asyncio.create_task(analyst.listen())

    print("researcher can see:", [p["role"] for p in researcher.peers.list_peers()])
    reply = await researcher.peers.request(
        "analyst", {"finding": "traffic doubled overnight"}, timeout=5
    )
    print("analyst replied:   ", reply)

    listening.cancel()
    await mesh.stop()


if __name__ == "__main__":
    asyncio.run(main())
