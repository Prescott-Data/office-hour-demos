# Office Hour Demos

**The code from Prescott Data Developers Office Hours, one folder per episode.**

Office Hours is where the engineers who built the runtime build something real with it, live,
in front of whoever turns up. Every session produces working code. This repository is where
that code lives afterwards, exactly as it was written on the day, so you can run it, break it,
and take it further.

Each episode is self contained. It has its own README that walks the build from an empty
folder, its own dependencies, and its own `.env.example`. Nothing is shared between folders,
so you can clone the repo and open any one of them without reading the others.

---

## Episodes

| | Episode | What gets built | Stack |
|---|---|---|---|
| **EP 02** | [**Agents That Learn From Their Mistakes**](ep02-garage-service-desk/) · 3 September 2026 | A garage service desk. The agent briefs a mechanic on a vehicle's history, gets corrected once, and every brief after that is shaped differently | [JarvisCore](https://jarviscore.developers.prescottdata.io/), [Athena](https://athena.developers.prescottdata.io/), FastAPI |
| **EP 03** | [**Give Your AI Agent a Compass**](ep03-odin-evidence-compass/) · 17 September 2026 | A claims investigator chooses what to inspect while Odin navigates and ranks the connected evidence | [Odin](https://github.com/Prescott-Data/odin), FastAPI, React |

---

## Running an episode

```bash
git clone https://github.com/Prescott-Data/office-hour-demos.git
cd office-hour-demos/<episode-folder>
```

Then follow that folder's README from the top. The READMEs are written as build-alongs, so
they explain why each step is there, including the steps that failed silently on the day.

Most episodes need:

- Python 3.10 or newer
- Docker, for any episode that runs Athena or another backing service
- One LLM provider key. Each `.env.example` lists which providers that episode supports

---

## Adding an episode

One folder per session, named `epNN-short-description`, with the code as it stood when the
session ended. Tidying for readability is fine. Rewriting it into something that was not
shown live is not, because the value of this repo is that it matches the recording.

Every episode folder carries:

| File | Why |
|---|---|
| `README.md` | The build from an empty folder, plus the gotchas hit on the day |
| `.env.example` | Every variable the code reads, with placeholders. Never a real key |
| `.gitignore` | Anything the demo writes at runtime: logs, traces, local stores |

Two rules that come from things that went wrong:

- **Load the environment at the top of every entrypoint** with `load_dotenv()`. Code that only
  works because your shell happened to have `.env` sourced will fail for the first person who
  opens a fresh terminal, and it usually fails silently.
- **Never commit `.env`.** The root `.gitignore` excludes it everywhere, but check
  `git status` before your first commit anyway.

Add a row to the table above in the same commit.

---

## Links

| | Docs | Source |
|---|---|---|
| **Athena**, the memory OS for agents | https://athena.developers.prescottdata.io/ | https://github.com/Prescott-Data/athena |
| **JarvisCore**, the agent framework | https://jarviscore.developers.prescottdata.io/ | https://github.com/Prescott-Data/jarviscore-framework |

**Join Office Hours on Discord:** https://discord.gg/CUb2FbasA
