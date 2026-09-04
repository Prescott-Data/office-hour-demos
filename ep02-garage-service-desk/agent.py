import json
import asyncio
import os
import time
import textwrap

# without this, .env is only read if you happened to source it in this terminal
from dotenv import load_dotenv
load_dotenv()

from jarviscore import Mesh, AutoAgent
from jarviscore.memory.athena_client import AthenaClient
from jarviscore.memory.athena_memory import AthenaMemory




AGENT_ID = os.getenv("AGENT_ID", "garage-advisor")
_agent_id = AGENT_ID


def current_agent_id():
    return _agent_id

# the only route back to an empty memory is a new identity, there is no delete
# one rotation clears all three sessions, they are all named off this
def new_memory():
    global _agent_id
    _agent_id = f"{AGENT_ID}-{int(time.time())}"
    return _agent_id


class GarageAgent(AutoAgent):
    name = "Garage"
    role = "garage"
    capabilities = ["service_intake"]
    description = "Briefs the mechanic on a vehicle before they start work."
    system_prompt = (
            "You are the service advisor at an independent garage. A mechanic asks you about a "
            "vehicle before starting work, and you tell them what they would otherwise have to "
            "go and look for in the job cards.\n"
            "A brief is a selection, not a summary. This garage may have worked on the vehicle "
            "many times. Lead with what bears on what the mechanic is dealing with today, say "
            "what was done and what was left, and leave the rest out. Short enough to read on "
            "the walk to the ramp, specific enough to change where they look first.\n"
            "The diagnosis belongs to the mechanic. Where the workshop has given you standing "
            "guidance about what to lead with, that guidance decides what bears on today."
        )

CONTRACT = (
    "\n\nAnswer with a JSON object holding exactly three fields:\n"
    "  brief — two or three sentences the mechanic reads before starting work\n"
    "  related_visits — the job references your brief draws on, empty when there are none\n"
    "  guidance_applied — the workshop guidance you followed, empty when none applied"
)

CARDS, GUIDANCE, CHAT = "cards", "guidance", "chat"
RECENT_TURNS = 6

def _step(step, detail, state, lines=None):
    return {"step": step, "detail": detail, "state": state, "lines": lines or []}

# Parse
def _parse(output):
    """Read the three fields. The advisor's own wording is kept, never rewritten."""
    if isinstance(output, dict):
        data = output
    else:
        text = str(output or "").strip().strip("`")
        start, end = text.find("{"), text.rfind("}")
        try:
            data = json.loads(text[start:end + 1]) if start >= 0 < end else {}
        except (ValueError, TypeError):
            data = {}
        if not data:
            return (text.strip()[:400] or "NO OUTPUT"), [], ""

    brief = data.get("brief") or data.get("summary") or ""
    if isinstance(brief, (list, dict)):
        brief = json.dumps(brief)
    related = data.get("related_visits") or data.get("related_jobs") or []
    if isinstance(related, str):
        related = [related] if related.strip() else []
    applied = data.get("guidance_applied") or data.get("guidance") or ""
    if isinstance(applied, list):
        applied = "; ".join(str(a) for a in applied)
    return str(brief).strip(), [str(r) for r in related], str(applied).strip()

# memory
async def _open_memory(kind):
    """Open one of the agent's memories, returning None if unavailable."""
    client = AthenaClient.from_env()
    if client is None:
        return None
    try:
        return await AthenaMemory.create(f"{_agent_id}-{kind}", client)
    except Exception as exc:
        print(f"[memory] could not open: {type(exc).__name__}: {exc}")
        return None

async def _observations(memory):
    try:
        ctx = await memory.get_memory_context(limit=50)
    except Exception:
        return None
    return [e.get("content", "") for e in ctx.get("stm_events", [])
            if e.get("type") == "observation" and e.get("content")]

async def _recall(kind):
    """Everything on file of one kind, oldest first."""
    memory = await _open_memory(kind)
    return (await _observations(memory) or []) if memory else []

# write to Athena 
def card_text(job):
    """Actual job card"""
    bits = [f"Job {job['job_ref']}. Vehicle {job['reg']}."]
    if job.get("date"):
        bits.append(f"{job['date']}.")
    if job.get("complaint"):
        bits.append(f"Customer reported: {job['complaint'].rstrip('.')}.")
    if job.get("work_done"):
        bits.append(f"Work done: {job['work_done'].rstrip('.')}.")
    if job.get("technician"):
        bits.append(f"Technician: {job['technician'].rstrip('.')}.")
    if job.get("left_undone"):
        bits.append(f"Left undone: {job['left_undone'].rstrip('.')}.")
    return " ".join(bits)

async def file_job(job):
    """Normal writes no model is involved"""
    memory = await _open_memory(CARDS)
    if memory is None:
        return False
    try:
        await memory.record_observation(
            card_text(job),
            metadata={
                "job_ref": job["job_ref"], "reg": job["reg"], "kind": "visit"
                      })
        return True
    except Exception as exc:
        print(f"[file_job] {type(exc).__name__}: {exc}")
        return False

# Mechanic's correction 
async def record_correction(text):
    memory = await _open_memory(GUIDANCE)
    if memory is None:
        return False
    try:
        # no prefix needed any more, the session it lands in is what makes it guidance
        await memory.record_observation(text.strip(), metadata={"kind": "guidance"})
        return True
    except Exception as exc:
        print(f"[record_correction] {type(exc).__name__}: {exc}")
        return False

async def ask(question, emit=None):
    trace = []
    task = (
        "A mechanic is asking about a vehicle before starting work.\n\n"
                f"What they asked:\n{question}"
        + CONTRACT
    )

    async def push(entry):
            trace.append(entry)
            if emit:
                await emit(entry)
    # memory
    guidance, history, turns = [], [], []
    client_up = AthenaClient.from_env() is not None
    await push(_step(
        "Memory opened",
        f"on · {os.getenv('ATHENA_URL')}" if client_up else "off · no client, nothing to read",
        "on" if client_up else "off",
    ))

    if client_up:
        # three sessions, read at the same time. no prefix sniffing, the session is the kind
        history, guidance, turns = await asyncio.gather(
            _recall(CARDS), _recall(GUIDANCE), _recall(CHAT))
        turns = turns[-RECENT_TURNS:]

        n = len(history)
        await push(_step(f"Job cards recalled from Athena",
                            f"{n} on file, read back verbatim" if n else "nothing on file",
                            "hit" if n else "miss", history))
        if guidance:
            await push(_step("Guidance recalled from Athena",
                                f"{len(guidance)} correction{'s' if len(guidance) != 1 else ''} on file, read back verbatim",
                                "hit", guidance))
        if turns:
            await push(_step("This conversation, recalled from Athena",
                                f"{len(turns)} earlier turn{'s' if len(turns) != 1 else ''}",
                                "hit", turns))
    else:
        await push(_step("Recall", "skipped — Athena is not reachable", "off"))

    if turns:
        task += ("\n\nWhat has already been said in this conversation, oldest first:\n"
                 + "\n".join(f"- {t}" for t in turns))
    if guidance:
        task += (
            "\n\nStanding guidance from the workshop. This is how they have asked you to "
            "brief, and it applies here as much as anywhere:\n"
            + "\n".join(f"- {g}" for g in guidance)
            + "\n\nThe guidance you follow goes in `guidance_applied`."
        )
    if history:
        task += (
            "\n\nEvery job card this garage holds, across all vehicles:\n"
            + "\n".join(f"- {h}" for h in history)
            + "\n\nWork out which of these the mechanic means, and lead with whatever bears "
                "on what they are asking. Where nothing on file matches, say so rather than "
                "reaching for the nearest card. The job references you use go in "
                "`related_visits`."
        )
    else:
        task += ("\n\nThis garage holds no job cards at all yet. Say so plainly so the "
                    "mechanic knows they are starting cold.")
    task += CONTRACT

    await push(_step("Writing the brief",
                    f"{len(task):,} characters · {len(guidance)} guidance, {len(history)} cards",
                    "info"))

    mesh = Mesh()
    mesh.add(GarageAgent, agent_id=_agent_id)
    await mesh.start()

    started = time.time()
    result = await mesh.run_task(agent="garage", task=task)
    elapsed = time.time() - started

    brief, related, applied = _parse(result.get("output"))
    await push(_step(
        "The advisor's own account" if applied else "Brief written",
        ("it says it followed the correction" if applied
            else "no guidance was on file to follow"),
        "hit" if applied else "info",
        ([f"draws on {', '.join(related)}"] if related else [])
        + ([applied] if applied else [])))

    # the conversation is memory too, and it goes to its own session so its rolling
    # window cannot push the job cards out
    chat = await _open_memory(CHAT)
    if chat is not None:
        try:
            await chat.record_observation(f"Mechanic asked: {question}",
                                          metadata={"kind": "turn"})
            await chat.record_observation(f"You answered: {brief}", metadata={"kind": "turn"})
        except Exception as exc:
            print(f"[turn] {type(exc).__name__}: {exc}")

    tokens = result.get("tokens") or {}
    
    return {
        "question": question,
        "brief": brief,
        "related_visits": related,
        "guidance_applied": applied,    
        "cards_seen": len(history),
        "guidance_count": len(guidance),
        "turns_seen": len(turns),
        "trace": trace,
        "tokens": tokens.get("total", 0) if isinstance(tokens, dict) else (tokens or 0),
        "cost_usd": round(result.get("cost_usd") or 0.0, 4),
        "seconds": round(elapsed, 1),
        "at": time.strftime("%H:%M:%S"),
    }


if __name__ == "__main__":
    MARCH = {
        "job_ref": "JOB-1042", "reg": "KDA 421X", "date": "4 March 2026",
        "complaint": "Judders when braking, grinding sound from the front. Toyota Vitz 2016",
        "work_done": "Front discs and pads replaced, both sides",
        "technician": "Kamau",
        "left_undone": "Customer declined the rear pads. Roughly 20% left, advised within six months",
    }
    APRIL = {
        "job_ref": "JOB-1198", "reg": "KDA 421X", "date": "19 April 2026",
        "complaint": "Booked in for the 60,000 km major service",
        "work_done": "Engine oil and filter, air filter, cabin filter, spark plugs, brake fluid flushed",
        "technician": "Njeri",
        "left_undone": "Nothing outstanding. Next service due at 70,000 km",
    }
    QUESTION = "What do you know about KDA 421X?"
    # names no vehicle at all — only the chat session can resolve it
    FOLLOW_UP = "And the rear pads, were they ever done?"
    CORRECTION = (
        "Lead with what we left undone, "
        "that belongs in the first sentence. I already know the make and the plate, "
        "I am standing next to the car."
    )

    def show(title, result):
        print(f"\n── {title} ──")
        print(f"  Kimemia asked   {result['question']}")
        print(f"  on file        {result['cards_seen']} job card(s) · "
              f"{result['guidance_count']} correction(s) · {result['turns_seen']} turn(s)")
        print("  advisor        " + textwrap.fill(result["brief"], 86,
                                                  subsequent_indent=" " * 17))
        if result["guidance_applied"]:
            print("  it followed    " + textwrap.fill(result["guidance_applied"], 86,
                                                      subsequent_indent=" " * 17))

    async def main():
        print(f"agent identity: {_agent_id}\n")

        for card in (MARCH, APRIL):
            ok = await file_job(card)
            print(f"filed {card['job_ref']}: {'ok' if ok else 'FAILED'}")

        show("BEFORE THE CORRECTION", await ask(QUESTION))

        print("\n── THE CORRECTION ──")
        print("  Kimemia         " + textwrap.fill(CORRECTION, 86, subsequent_indent=" " * 17))
        print(f"  kept           {'yes' if await record_correction(CORRECTION) else 'FAILED'}")

        show("AFTER THE CORRECTION — same question", await ask(QUESTION))
        show("A FOLLOW-UP THAT NAMES NO VEHICLE", await ask(FOLLOW_UP))

    asyncio.run(main())