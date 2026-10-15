"""The desk roster. Building it starts nothing and contacts no provider."""

from __future__ import annotations

from pathlib import Path

from jarviscore import Mesh

from personal_finance import layouts
from personal_finance.agents.auditor import Auditor
from personal_finance.agents.categoriser import Categoriser
from personal_finance.agents.coach import Coach
from personal_finance.agents.proposer import Proposer
from personal_finance.agents.watchdog import Watchdog
from personal_finance.desk import DEFAULT_USER, Desk
from personal_finance.sources.pdf import read_words
from personal_finance.sources.table import extract

LAYOUT_NAME = "mpesa-statement"


def build_mesh(user: str = DEFAULT_USER) -> Mesh:
    """One person's desk as a mesh, so the agents can reach each other by what they do."""
    layout = layouts.load(LAYOUT_NAME)
    desk = Desk(user)
    mesh = Mesh(config={"mesh_response_capability": "spending_summary"})
    mesh.add(
        Categoriser,
        agent_id=f"pf-categoriser-{desk.user}",
        layout=layout,
        policy=desk.categories().policy(),
        corrections=desk.corrections(),
        judgements=desk.judgements(),
    )
    mesh.add(Proposer, agent_id=f"pf-proposer-{desk.user}", layout=layout, user=desk.user)
    mesh.add(Watchdog, agent_id=f"pf-watchdog-{desk.user}", layout=layout)
    mesh.add(Coach, agent_id=f"pf-coach-{desk.user}", layout=layout)
    mesh.add(Auditor, agent_id=f"pf-auditor-{desk.user}", layout=layout)
    return mesh


def member(mesh: Mesh, capability: str):
    """The agent that does a thing, found by the thing it does rather than by name."""
    for agent in mesh.agents:
        if capability in (getattr(agent, "capabilities", None) or []):
            return agent
    raise LookupError(f"no agent in this mesh offers {capability!r}")


async def read_statement(path: str, user: str = DEFAULT_USER):
    layout = layouts.load(LAYOUT_NAME)
    return extract(read_words(path), layout, source=Path(path).stem)


async def submit_task(mesh: Mesh, message: str, context: dict | None = None) -> dict:
    """One request for the whole desk: read a statement, then say what it means."""
    context = dict(context or {})
    statement = context.get("statement") or message.strip()
    if not statement:
        raise ValueError("this desk needs a statement to read")

    user = context.get("user", DEFAULT_USER)
    desk = Desk(user)
    transactions = await read_statement(statement, user)

    # starting the mesh is what hands each agent its decision client
    ours = not getattr(mesh, "_started", False)
    if ours:
        await mesh.start()
    try:
        categoriser = member(mesh, "transaction_categorisation")
        verdicts = await categoriser.categorise([t.description for t in transactions])

        watchdog = member(mesh, "spending_oversight")
        findings = await watchdog.review(transactions, verdicts, desk.notes())

        coach = member(mesh, "spending_summary")
        summary = await coach.summarise(transactions, verdicts, desk.notes(), findings)
    finally:
        if ours:
            await mesh.stop()

    return {
        "output": {
            "summary": summary.text(),
            "findings": [f.model_dump(mode="json") for f in findings],
            "transactions": len(transactions),
        },
        "cost_usd": round(
            categoriser.spend_usd + watchdog.spend_usd + coach.spend_usd, 6
        ),
    }
