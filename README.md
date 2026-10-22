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
| **OH** | [**Building a GitHub Code Review Squad**](2026-08-27-oh-github-code-review-squad/) · 27 August 2026 | Three agents that write code, push it, review it, remember what they found, and email the report. Every call goes through Nexus; no agent holds a token | [JarvisCore](https://jarviscore.developers.prescottdata.io/), Nexus, GitHub, Gmail |
| **EP 02** | [**Agents That Learn From Their Mistakes**](ep02-garage-service-desk/) · 3 September 2026 | A garage service desk. The agent briefs a mechanic on a vehicle's history, gets corrected once, and every brief after that is shaped differently | [JarvisCore](https://jarviscore.developers.prescottdata.io/), [Athena](https://athena.developers.prescottdata.io/), FastAPI |
| **EP 03** | [**Give Your AI Agent a Compass**](ep03-odin-evidence-compass/) · 17 September 2026 | A claims investigator chooses what to inspect while Odin navigates and ranks the connected evidence | [Odin](https://github.com/Prescott-Data/odin), FastAPI, React |
| **OH** | [**AI Agents in Production**](2026-09-22-oh-ai-agents-in-production/) · 22 September 2026 | A technical session on running agents on Kubernetes, with slides and a live control room: leases, a credential broker, a human gate, and failover | [JarvisCore](https://jarviscore.developers.prescottdata.io/), Redis, FastAPI |
| **SPOTLIGHT** | [**JarvisCore for Personal Finance**](community-spotlight/personal-finance/) · 8 October 2026 | A private money desk. A locked statement goes in, five agents propose categories, flag what departs from a place's own pattern, and separate cost from waste. Counterparty names are replaced with labels before anything leaves the machine | [JarvisCore](https://jarviscore.developers.prescottdata.io/), Jev, FastAPI |
| **OH** | [**Agent to Agent Communication**](2026-10-22-oh-agent-to-agent-communication/) · 22 October 2026 | A team of agents that find each other by gossip and talk directly, with no orchestrator. One is killed mid-conversation and the rest keep talking; a new one joins and the others find it | [JarvisCore](https://jarviscore.developers.prescottdata.io/), SWIM, ZeroMQ |

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

One folder per session, named `epNN-short-description`, or `YYYY-MM-DD-oh-short-description`
when the session has no episode number, with the code as it stood when the session ended.
Tidying for readability is fine. Rewriting it into something that was not shown live is not,
because the value of this repo is that it matches the recording.

**Community spotlights are the exception**, and they live under `community-spotlight/`. A
spotlight is something one of us built and demoed rather than a session taught from a script, so
its folder keeps growing after the demo instead of being frozen at it. The table marks these
**SPOTLIGHT**. Everything below still applies in full.

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
| **Odin**, the graph navigation engine | https://odin.developers.prescottdata.io/ | https://github.com/Prescott-Data/Odin-1 |

**Join Office Hours on Discord:** https://discord.gg/QxzpRZ6VaD

---

## Licence

Apache 2.0, the same licence as JarvisCore and Athena. See [LICENSE](LICENSE). Use this code,
change it, ship it, including commercially. Keep the notice and say what you changed.
