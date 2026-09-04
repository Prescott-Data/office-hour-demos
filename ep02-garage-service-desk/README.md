# Agents That Learn From Their Mistakes

**Office Hours · EP 02 · Prescott Data Developers**

A service desk for a garage. A mechanic walks up to a car; before he touches it, the agent
tells him what this garage has done to that vehicle before — and what got left undone.

Then he reads a brief that is **shaped wrong**. It opens by telling him the make and the
registration of the car he is standing next to, and buries the thing that matters. He
corrects it once, in one sentence. Every brief after that is different.

That correction is the whole point. It is stored in [Athena](https://athena.developers.prescottdata.io/),
it survives the process, and the agent applies it to questions it has never seen.

```
BEFORE THE CORRECTION
  "The vehicle is a Toyota Vitz (2016), reg KDA 421X."

  ── the mechanic corrects it, once ──
  "Lead with what we left undone. I already know the make and the plate,
   I am standing next to the car."

AFTER THE CORRECTION — same question, same job cards
  "The rear brake pads were left undone on 4 March 2026, roughly 20%
   remaining, advised within six months."
```

It always knew about the pads — they were in sentence two of the first brief. It did not
learn a fact. It learned **what mattered**. That is the part a bigger context window does
not give you.

---

## What you need

- Python 3.10+
- Docker running — Athena brings up seven containers
- One LLM provider key (Azure OpenAI, Anthropic, Gemini, or a `JARVISCORE_PROMO_TOKEN`)
- ~5 GB free disk for the Athena images

---

## Build it from an empty folder

### 1. Folder and virtualenv

```bash
mkdir garage-desk && cd garage-desk
python3 -m venv venv && source venv/bin/activate
```

### 2. Install — the `[redis]` extra is not optional

```bash
pip install "jarviscore-framework[redis]" fastapi uvicorn python-dotenv
```

> Without `[redis]` the memory subsystem is dead and **fails silently**. You get
> `BlobStorage init failed: No module named 'redis'`, and nothing is ever written to
> Athena — even with `ATHENA_URL` set and the whole stack healthy.

### 3. Scaffold and configure

```bash
jarviscore init
cp .env.example .env
```

Edit `.env`. For Azure OpenAI all four lines matter — `AZURE_ENDPOINT` is the **resource
root only**, no path, and `AZURE_API_VERSION` is missing from the generated file:

```
AZURE_API_KEY=<your key>
AZURE_ENDPOINT=https://<your-resource>.openai.azure.com
AZURE_DEPLOYMENT=gpt-4o
AZURE_API_VERSION=2025-01-01-preview
```

### 4. Verify before writing a line of code

```bash
jarviscore check --validate-llm
```

### 5. Write the agent — `agent.py`

The agent is a class with five attributes and a prompt:

```python
class GarageAgent(AutoAgent):
    name = "Garage"
    role = "garage"                     # how mesh.run_task finds it
    capabilities = ["service_intake"]   # required — the quickstart omits it
    description = "Briefs the mechanic on a vehicle before they start work."
    system_prompt = "..."
```

Two things in `agent.py` are worth reading closely:

**The prompt describes a principle, not a checklist.** *"A brief is a selection, not a
summary."* If the prompt instead said *include the history, the technician, the dates*,
then a correction saying *lead with what we left undone* would be fighting the prompt's own
instruction to include everything. Describe what makes a brief good, and a correction has
room to steer it.

**The output contract lives in the task, not `system_prompt`.** Measured on the same
question: **0/3** clean responses with the contract in `system_prompt`, **3/3** with the
identical words in the task. `kernel/kernel.py:737` tucks `system_prompt` into a context
payload where the shape does not survive.

Run it:

```bash
python agent.py
```

It works, it is articulate, and it knows nothing. Ask twice and you get the same nothing —
every question starts from zero.

### 6. Start Athena

```bash
set -a && . ./.env && set +a      # memory init reads os.environ, not .env
jarviscore memory init
```

Seven containers: Athena, Redis, MongoDB, Milvus, etcd, MinIO, ArangoDB. First run pulls
images, so give it a few minutes.

### 7. Give the agent memory

Three questions: where memories go, how you read them, how you write them.

**Where they go — one session per kind:**

```python
CARDS, GUIDANCE, CHAT = "cards", "guidance", "chat"

async def _open_memory(kind):
    client = AthenaClient.from_env()
    return await AthenaMemory.create(f"{_agent_id}-{kind}", client) if client else None
```

> **Athena's short-term memory holds the last 10 events per session.** Measured: 15
> observations written, `limit=500` requested, events 6–15 returned. The five oldest were
> gone, with no error. On top of that, every `run_task` writes a `thought` and an `action`
> whether you asked for them or not — so with everything in one session, the conversation
> quietly evicts the job cards and the briefs get thinner with no way to tell why.
>
> Separate sessions, separate windows. Nothing crowds anything else out, and the session
> name *is* the category, so nothing has to prefix its writes and sniff the string back out.

**How you read** — `_recall(kind)` returns everything on file of one kind, and `ask()`
pulls all three at once with `asyncio.gather`.

**How you write** — `file_job()` into CARDS, `record_correction()` into GUIDANCE, and the
conversation into CHAT at the end of every `ask()`.

> **You have to call `record_observation` yourself.** `memory/unified.py:145` writes only
> `record_thought` and `record_action` — the framework stores the agent's own reasoning
> and never the work. Nothing in JarvisCore calls `record_observation` for you.

Run the whole arc — two cards filed, a question, a correction, the same question again,
then a follow-up that names no vehicle at all:

```bash
python agent.py
```

### 8. Wrap it in an API — `app.py`

```bash
uvicorn app:app --reload --port 8000
```

`GET /` serves the page, `POST /api/job` files a card, `POST /api/correct` records a
correction, `POST /api/ask` streams the brief, `POST /api/reset` starts a fresh identity.

`/api/ask` is server-sent events, so each step of the agent's work appears the moment it
happens rather than all at once at the end:

```bash
curl -sN -X POST localhost:8000/api/ask \
  -H 'content-type: application/json' \
  -d '{"text":"and the rear pads?"}'
```

`-N` is not optional — without it curl buffers and you see nothing until the end. Recall
lands at about 0.12s; the model then thinks for around five seconds. That gap is why the
trace streams.

FastAPI also generates interactive docs from the Pydantic request classes, free:
**http://localhost:8000/docs**

### 9. The interface

Open **http://localhost:8000**.

Three panels — book a vehicle in on the left, talk to the desk in the middle, and on the
right **what the agent actually looked up**, read back verbatim rather than summarised.

Try this order:
1. File the three example cards (the chips fill the form for you)
2. Ask *"What do you know about KDA 421X?"*
3. Correct it: *"Lead with what we left undone, that belongs in the first sentence."*
4. Ask the identical question again
5. Ask *"and the rear pads?"* — no plate, no vehicle named

---

## Files

| | |
|---|---|
| `agent.py` | the agent, its memory, and the whole arc under `__main__` |
| `app.py` | FastAPI wrapper, SSE streaming on `/api/ask` |
| `index.html` | the three-panel desk |
| `jobs.json` | three example cards — the KDA 421X story |
| `jobs-extra.json` | ten more across six vehicles, for your own testing |
| `.env.example` | copy to `.env` and fill in one provider |

**Reset between runs.** There is no delete in Athena — rotating the agent's identity is how
you start clean, and it clears all three sessions at once:

```bash
AGENT_ID="run-$(date +%s)" uvicorn app:app --reload --port 8000
```

---

## Gotchas worth knowing

| | |
|---|---|
| Missing `capabilities` | `ValueError` on startup; the documented quickstart omits it |
| Installed without `[redis]` | memory subsystem dead, silently, even with a healthy stack |
| Output contract in `system_prompt` | 0/3 vs 3/3 — put it in the task |
| Framework memory writes | `thought` and `action` only; call `record_observation` yourself |
| STM window | last 10 events **per session** — split your memories or they evict each other |
| `search()` returns nothing | it queries MTM chains, which need volume; a short session has zero |
| `memory status` shows Redis ❌ | it checks 6379, Athena maps 6380. Cosmetic |
| `AZURE_ENDPOINT` with a path | resource root only |

---

## Links

| | Docs | Source |
|---|---|---|
| **Athena** — the memory OS | https://athena.developers.prescottdata.io/ | https://github.com/Prescott-Data/athena |
| **JarvisCore** — the agent framework | https://jarviscore.developers.prescottdata.io/ | https://github.com/Prescott-Data/jarviscore-framework |

**Office Hours — join us on Discord:** https://discord.gg/CUb2FbasA

Built live on 3 September 2026. Questions and experiments welcome in the Athena channel.
