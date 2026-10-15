"""The desk in a browser. Statements stay on this machine; only the desk's own calls leave."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pdfplumber.utils.exceptions import PdfminerException
from pydantic import BaseModel

from personal_finance import counterparty, facts, layouts, team
from personal_finance.agents.auditor import Audit, Auditor
from personal_finance.desk import DEFAULT_USER, Desk
from personal_finance.sources.pdf import StatementLocked, read_words
from personal_finance.sources.table import LayoutMismatch, extract
from personal_finance.verify import check_balances

load_dotenv(".env")

# starting the mesh takes about two minutes, almost all of it each agent re-seeding the shipped
# atom catalogue, and that work is synchronous, so it happens on first use and is kept afterwards
AGENTS: dict = {"mesh": None, "starting": False, "failed": ""}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    if AGENTS["mesh"]:
        await AGENTS["mesh"].stop()


async def _agents():
    """The running mesh, started once and shared by every press after that."""
    if AGENTS["mesh"] is None:
        AGENTS["starting"] = True
        try:
            mesh = team.build_mesh(DEFAULT_USER)
            await mesh.start()
            AGENTS["mesh"], AGENTS["failed"] = mesh, ""
        except Exception as exc:  # noqa: BLE001 - say what happened rather than hang
            AGENTS["failed"] = str(exc)
            raise
        finally:
            AGENTS["starting"] = False
    return AGENTS["mesh"]


app = FastAPI(title="Personal Finance Desk", lifespan=lifespan)
PAGE = Path(__file__).parent / "static" / "index.html"
UPLOADS = Path(".pf-state") / "uploads"
LAYOUT = "mpesa-statement"

# one statement at a time, held in memory so nothing is written where it need not be
STATE: dict = {
    "transactions": [], "verdicts": {}, "findings": [], "summary": None, "name": "", "stale": False
}


class Move(BaseModel):
    keys: list[str]
    category: str


class NewCategory(BaseModel):
    name: str
    meaning: str


class Merge(BaseModel):
    source: str
    target: str


class Ruling(BaseModel):
    what: str
    avoidable: bool


def _desk(user: str = DEFAULT_USER) -> Desk:
    return Desk(user)


@app.get("/")
def index():
    return FileResponse(PAGE)


@app.post("/api/statement")
async def upload(statement: UploadFile, password: str = Form(default="")):
    """Read a statement and prove it reconciles. The file is deleted once it is read."""
    UPLOADS.mkdir(parents=True, exist_ok=True)
    saved = UPLOADS / (statement.filename or "statement.pdf")
    saved.write_bytes(await statement.read())
    if password:
        import os

        existing = os.getenv("PF_STATEMENT_PASSWORDS", "")
        os.environ["PF_STATEMENT_PASSWORDS"] = f"{existing},{password}" if existing else password

    layout = layouts.load(LAYOUT)
    try:
        rows = extract(read_words(saved), layout, source=saved.stem)
    except StatementLocked:
        return JSONResponse({"error": "No password opens that statement."}, status_code=400)
    except LayoutMismatch as exc:
        return JSONResponse({"error": f"That layout is not one we know: {exc}"}, status_code=400)
    except PdfminerException:
        return JSONResponse({"error": "That file is not a PDF we can open."}, status_code=400)
    finally:
        saved.unlink(missing_ok=True)

    verdict = check_balances(rows)
    STATE.update(
        transactions=rows, verdicts={}, findings=[], summary=None, name=saved.name, stale=False
    )
    return {
        "transactions": len(rows),
        "reconciles": verdict.ok,
        "checked": verdict.checked,
        "breaks": len(verdict.breaks),
        "verdict": verdict.summary(),
    }


@app.get("/api/categories")
def categories(user: str = DEFAULT_USER):
    """Your categories with the transactions under each, and what is still unplaced."""
    desk, layout = _desk(user), layouts.load(LAYOUT)
    policy = desk.categories().policy()
    rows = STATE["transactions"]
    verdicts, corrections = STATE["verdicts"], desk.corrections().as_dict()

    placed: dict[str, list] = {name: [] for name in policy.categories}
    for row in rows:
        key = counterparty.key(row.description, layout.kinds)
        found = verdicts.get(key)
        category = corrections.get(key) or (found.category if found else "uncategorised")
        placed.setdefault(category, []).append(
            {
                "key": key,
                "reference": row.reference,
                "when": f"{row.timestamp:%Y-%m-%d}",
                "description": row.description,
                "amount": str(row.signed_amount),
                "corrected": key in corrections,
            }
        )

    return {
        "statement": STATE["name"],
        "categories": [
            {
                "name": name,
                "meaning": policy.categories.get(name, ""),
                "spent": str(
                    sum((Decimal(t["amount"]) for t in items if Decimal(t["amount"]) < 0),
                        Decimal(0))
                ),
                "transactions": sorted(items, key=lambda t: t["when"], reverse=True),
            }
            for name, items in sorted(placed.items(), key=lambda kv: -len(kv[1]))
            if items or name != "uncategorised"
        ],
        "names": list(policy.categories),
    }


@app.post("/api/move")
def move(request: Move, user: str = DEFAULT_USER):
    """Put counterparties in a category and keep them there, for every past and future payment."""
    desk, layout = _desk(user), layouts.load(LAYOUT)
    if not desk.categories().policy().allows(request.category):
        return JSONResponse({"error": "That is not one of your categories."}, status_code=400)
    corrections = desk.corrections()
    moved = [counterparty.key(key, layout.kinds) for key in request.keys]
    for key in moved:
        corrections.record(key, request.category)
    STATE["stale"] = bool(STATE["findings"] or STATE["summary"])
    return {"moved": moved, "to": request.category}


@app.post("/api/categories/add")
def add_category(request: NewCategory, user: str = DEFAULT_USER):
    """A category of your own, with the meaning the categoriser will judge against."""
    name = request.name.strip().lower().replace(" ", "_")
    if not name or not request.meaning.strip():
        return JSONResponse({"error": "A category needs a name and a meaning."}, status_code=400)
    catalogue = _desk(user).categories()
    if name in catalogue.policy().categories:
        return JSONResponse({"error": f"{name} is already one of yours."}, status_code=400)
    catalogue.add(name, request.meaning.strip())
    return {"added": name}


@app.post("/api/categories/merge")
def merge_categories(request: Merge, user: str = DEFAULT_USER):
    """Fold one category into another, moving everything that sat in it."""
    desk = _desk(user)
    corrections = desk.corrections()
    for key, category in list(corrections.as_dict().items()):
        if category == request.source:
            corrections.record(key, request.target)
    if not desk.categories().merge(request.source, request.target):
        return JSONResponse({"error": "Those cannot be merged."}, status_code=400)
    STATE["stale"] = bool(STATE["findings"] or STATE["summary"])
    return {"merged": request.source, "into": request.target}


def _stream(work):
    """Run a stage, reporting each step as it finishes."""

    async def events():
        queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(work(queue))
        try:
            while True:
                kind, payload = await queue.get()
                yield f"event: {kind}\ndata: {json.dumps(payload)}\n\n"
                if kind in {"done", "error"}:
                    break
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


@app.post("/api/categorise")
async def categorise(user: str = DEFAULT_USER):
    """Place every counterparty. Nothing here writes findings, so you can tidy first."""
    if not STATE["transactions"]:
        return JSONResponse({"error": "Upload a statement first."}, status_code=400)

    async def work(queue: asyncio.Queue):
        rows = STATE["transactions"]
        if AGENTS["mesh"] is None:
            await queue.put(("step", {
                "say": "starting the agents",
                "detail": "about two minutes, once per server",
            }))
        agent = team.member(await _agents(), "transaction_categorisation")
        await queue.put(("step", {"say": f"{len(rows)} transactions, reading who they went to"}))
        before = agent.spend_usd
        STATE["verdicts"] = await agent.categorise([t.description for t in rows])
        await queue.put(("step", {
            "say": f"placed {len(STATE['verdicts'])} counterparties",
            "detail": f"asked {agent.questions_asked}, cost ${agent.spend_usd - before:.6f}",
        }))
        await queue.put(("done", {"placed": len(STATE["verdicts"])}))

    return _stream(work)


@app.post("/api/analyse")
async def analyse(user: str = DEFAULT_USER, fresh: bool = False):
    """Once you are happy with the categories: what deserves attention, and the summary."""
    if not STATE["verdicts"]:
        return JSONResponse({"error": "Categorise the statement first."}, status_code=400)

    async def work(queue: asyncio.Queue):
        desk = _desk(user)
        rows, verdicts = STATE["transactions"], STATE["verdicts"]
        mesh = await _agents()

        watchdog = team.member(mesh, "spending_oversight")
        spent = watchdog.spend_usd
        findings = await watchdog.review(rows, verdicts, desk.notes(), fresh=fresh)
        STATE["findings"] = [f.model_dump(mode="json") for f in findings]
        await queue.put(("step", {"say": f"{len(findings)} things worth your attention"}))

        coach = team.member(mesh, "spending_summary")
        spent += coach.spend_usd
        summary = await coach.summarise(rows, verdicts, desk.notes(), findings)
        STATE["summary"] = summary.model_dump(mode="json")
        cost = watchdog.spend_usd + coach.spend_usd - spent
        await queue.put(("step", {"say": "summary written", "detail": f"${cost:.6f}"}))
        STATE["stale"] = False
        await queue.put(("done", {
            "findings": STATE["findings"], "summary": STATE["summary"]
        }))

    return _stream(work)


@app.get("/api/findings")
def findings():
    return {
        "findings": STATE["findings"], "summary": STATE["summary"], "stale": STATE["stale"]
    }


def _audit_body(audit, agent=None) -> dict:
    return {
        "worked_out": True,
        "headline": audit.headline(),
        "avoidable": str(audit.avoidable_total),
        "spent": str(audit.spent),
        "caveat": audit.caveat,
        "unruled": len(audit.unruled()),
        "lines": [
            {
                "what": line.what,
                "amount": str(line.amount),
                "avoidable": line.avoidable,
                "says": line.says,
                "your_call": line.your_call,
            }
            for line in audit.lines
        ],
        "cost": f"{agent.spend_usd:.6f}" if agent else "0.000000",
    }


@app.get("/api/audit")
async def audit_seen(user: str = DEFAULT_USER):
    """The audit already worked out for this statement, without asking a model."""
    if not STATE["transactions"]:
        return {"worked_out": False, "reason": "Upload a statement first."}
    desk = _desk(user)
    kept = desk.audits()
    statement = Auditor.fingerprint(STATE["transactions"])
    if statement not in kept.data:
        return {"worked_out": False}
    agent = Auditor(layouts.load(LAYOUT), desk=desk)
    return _audit_body(agent.apply_rulings(Audit(**kept.data[statement]), desk.rulings()))


@app.post("/api/audit")
async def audit_run(user: str = DEFAULT_USER, fresh: bool = False):
    """Work out what the period cost that need not have."""
    if not STATE["transactions"]:
        return JSONResponse({"error": "Upload a statement first."}, status_code=400)
    desk = _desk(user)
    agent = team.member(await _agents(), "avoidable_cost")
    before = agent.spend_usd
    found = await agent.audit(STATE["transactions"], notes=desk.notes(),
                              rulings=desk.rulings(), fresh=fresh)
    body = _audit_body(found)
    body["cost"] = f"{agent.spend_usd - before:.6f}"
    return body


@app.post("/api/audit/rule")
async def audit_rule(request: Ruling, user: str = DEFAULT_USER):
    """Your word on one line, which outranks the desk from now on."""
    desk = _desk(user)
    desk.rulings().record(request.what, request.avoidable)
    return await audit_seen(user)


@app.get("/api/ready")
def ready():
    """Whether the agents have finished starting, so the page can say so rather than hang."""
    return {
        "ready": AGENTS["mesh"] is not None,
        "starting": AGENTS["starting"],
        "failed": AGENTS["failed"],
    }


@app.get("/api/sheets")
def sheets(user: str = DEFAULT_USER):
    """What is known about each counterparty, which is what the watchdog reads."""
    desk, layout = _desk(user), layouts.load(LAYOUT)
    built = facts.sheets(STATE["transactions"], layout, STATE["verdicts"], desk.notes())
    return {"sheets": [json.loads(s.model_dump_json()) for s in built[:40]]}


def serve() -> None:
    """Run the desk on localhost, where the statements are."""
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
