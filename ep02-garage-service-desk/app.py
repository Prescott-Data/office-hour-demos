from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
import asyncio
import json
import os
from pathlib import Path
from agent import current_agent_id, file_job, record_correction, ask, new_memory

HERE = Path(__file__).parent
CARDS = HERE / "cards.json"
CHAT = HERE / "chat.json"
MECHANIC = os.getenv("MECHANIC", "Onyach Pala")

app = FastAPI(title="Modern Garage")

# Define the schemas for our various inputs (fast api will do the type checking)
# 3 classes cause they are genuinely  3 different payloads
class JobRequest(BaseModel):
    job_ref: str
    reg: str
    date: str = ""
    complaint: str = ""
    work_done: str = ""
    technician: str = ""
    left_undone: str = ""

class AskRequest(BaseModel):
    text: str


class CorrectionRequest(BaseModel):
    text: str


def _read(path, default):
    if path.exists():
        return json.loads(path.read_text())
    return default

def _write(path, data):
    path.write_text(json.dumps(data, indent=2))

@app.get("/")
def index():
    return FileResponse(HERE / "index.html")


@app.get("/api/state")
def get_state():
    return {
        "examples": _read(HERE / "jobs.json", []),
        "cards": _read(CARDS, []),
        "chat": _read(CHAT, []),
        "mechanic": MECHANIC,
        "agent_id": current_agent_id()
    }

# Insert a new job 
@app.post("/api/job")
async def insert_job(req: JobRequest):
    card = req.model_dump() # generate dict representation of the model so it can be mutated
    card["job_ref"] = card["job_ref"].strip()
    card["reg"] = card["reg"].strip().upper()
    if not card["job_ref"] or not card["reg"]:
        return JSONResponse({"error": "a job reference and a registration"}, status_code=400)
    if not await file_job(card):
        return JSONResponse({"error": "Athena is not reachable, so the card cannot be kept"},
                            status_code=409)
    cards = _read(CARDS, [])
    cards.append(card)
    _write(CARDS, cards)
    return {"ok": True, "card": card}

@app.post("/api/correct")
async def correct(req: CorrectionRequest):
    text = req.text.strip()
    if not text:
        return JSONResponse({"error": "nothing to correct"}, status_code=400)
    if not await record_correction(text):
        return JSONResponse({"error": "Athena is not reachable, so the correction cannot be recorded"},
                            status_code=409)

    chat = _read(CHAT, [])
    chat.append({"role": "mechanic", "kind": "correction", "text": text})
    chat.append({"role": "advisor", "kind": "ack",
                    "text": "Noted. I will lead with that from now on."})
    _write(CHAT, chat)
    return {"ok": True, "correction": text}

@app.post("/api/ask")
async def ask_endpoint(req: AskRequest):
    """Server-sent events: each step goes out as the advisor takes it, then the brief."""
    question = req.text.strip()
    if not question:
        return JSONResponse({"error": "pose a question"}, status_code=400)

    # nothing is read out of the question here, working out which vehicle is the agent's job
    async def events():
        queue: asyncio.Queue = asyncio.Queue()

        # emit puts a step on the queue, this is what we hand to ask()
        async def emit(entry):
            await queue.put(("step", entry))

        async def work():
            try:
                result = await ask(question, emit=emit)
                chat = _read(CHAT, [])
                chat.append({"role": "mechanic", "kind": "question", "text": question})
                chat.append({"role": "advisor", "kind": "brief", **result})
                _write(CHAT, chat)
                await queue.put(("done", result))
            except Exception as exc:
                # the status line is already sent, so an error has to travel as an event
                await queue.put(("failed", {"error": f"{type(exc).__name__}: {exc}"}))

        # create_task not await, otherwise we block and there is nothing to stream
        task = asyncio.create_task(work())
        while True:
            kind, payload = await queue.get()
            yield f"event: {kind}\ndata: {json.dumps(payload)}\n\n"
            if kind in ("done", "failed"):
                break
        await task

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.post("/api/reset")
def reset():
    """Clears the desk AND the memory — a half-reset is how a demo quietly breaks."""
    _write(CARDS, [])
    _write(CHAT, [])
    return {"ok": True, "agent_id": new_memory()}