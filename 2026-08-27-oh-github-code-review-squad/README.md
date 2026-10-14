# Building a GitHub Code Review Squad

**Office Hours · 27 August 2026 · Ruth Mutua & Abdullahi · Prescott Data Developers**

Three agents, one repo, two external services, built live from an empty file:

- **CodeSmith** writes a Python module with deliberate quality problems, pushes it to a
  branch, and opens a pull request
- **Inspector** reads that file back *from GitHub*, reviews it, comments on the PR, and
  remembers what it found
- **Reporter** recalls the review, drafts a report, and emails it through Gmail, after
  asking first

GitHub and Gmail are both reached through **Nexus**. The agents never see a token: after a
run you can grep everything they wrote for `token|secret|bearer` and get nothing back.

**Slides:** [`building-a-github-code-review-squad.pdf`](building-a-github-code-review-squad.pdf)

> The `src/payments.py` the agents push is generated, deliberately bad, and exists to be
> reviewed. Don't copy it anywhere.

---

## What you need

- Python 3.10+
- Docker, for Redis
- One LLM provider key: Azure OpenAI, Anthropic, Gemini, or any OpenAI-compatible endpoint
- A GitHub account and a **public** repo you own for the agents to push to
- A **Nexus gateway** with the `github` and `google-workspace` providers registered.
  On the day we used Prescott's hosted gateway, which is not open to the public. See the
  [JarvisCore docs](https://jarviscore.developers.prescottdata.io/) for Nexus.

`write_code.py` needs only the LLM key. Everything after it needs the gateway.

---

## Set it up

```bash
git clone https://github.com/Prescott-Data/office-hour-demos.git
cd office-hour-demos/2026-08-27-oh-github-code-review-squad

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # pins jarviscore-framework 1.3.1, as on the day

cp .env.example .env                     # fill in the gateway, your repo, your LLM key
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

### Install the three GitHub write atoms

The framework ships 150 integration bundles and 1,227 atoms. Eight of them are GitHub:
all reads, plus issues and comments. **None of them writes a file.** `atoms/github/` holds
the three that close that gap:

| Atom | Notes |
|---|---|
| `github_create_branch` | Branches from the repo's real `default_branch`, not an assumed `main` |
| `github_create_or_update_file` | Looks up the blob sha, so update works and not just create |
| `github_create_pull_request` | Returns the already-open PR instead of failing on 422 |

All three are idempotent, which matters when a step retries. Three things make a file an
atom:

1. `auth_info: dict` is the first parameter. Nexus fills it; the atom never fetches it
2. The filename matches the function name. That's how the registry finds it
3. Nothing else

Discovery is a directory glob, so dropping them into the installed package registers them:

```bash
cp atoms/github/*.py "$(python -c 'import jarviscore, os; print(os.path.dirname(jarviscore.__file__))')/integrations/atoms/github/"
jarviscore atom list | grep -c github    # 11, was 8
```

---

## Run it: four steps, each on its own

| Run | What happens | What to look for |
|---|---|---|
| `python write_code.py` | CodeSmith writes the module, prints it, checks the defects | Three attributes, zero infrastructure |
| `python push_and_open_pr.py` | GitHub consent → branch → commit → pull request | Every call on screen, no token anywhere |
| `python review_pr.py` | Inspector reads it **back from GitHub**, reviews, comments | Run it **twice**: the second run recalls the first |
| `python email_report.py` | Google consent, then Reporter drafts the report and **asks before sending** | The email in the recipient's inbox |

`push_and_open_pr.py` and `email_report.py` print the Nexus connection ids. Put them in `.env`
(`NEXUS_GITHUB_CONNECTION_ID`, `NEXUS_GOOGLE_CONNECTION_ID`) and later runs skip the
consent screen.

`providers.py` lists what the gateway can connect to:

```bash
python providers.py git      # github, gitlab
python providers.py google   # google-workspace and friends
```

### The dashboard version

Same three agents, as a pipeline you click through:

```bash
python main.py               # backend on :8004
python dashboard/app.py      # in a second terminal, then open http://localhost:8080
```

---

## What caught us on the day

**`auth_mode` is what actually turns Nexus on.** `Mesh` only builds an
`AuthenticationManager` when `config["auth_mode"]` is truthy. Set `NEXUS_GATEWAY_URL`
without it and the gateway URL is silently ignored: no agent gets an auth manager, and every
`nexus_call()` is a stub that raises the moment it is touched. Nothing warns you at startup.
`config.mesh_config()` sets it.

**If an agent calls `nexus_call()` itself, the routing keys go inside `context`.** In this
code the agents only make judgements, and the six GitHub and Gmail calls go through
`proxy.call()` in `runner.py`. If you move a call into the agent, `nexus_call()` is only
wired in when the step looks like this:

```python
{"agent": "codesmith", "task": "...",
 "context": {"system": "github",
             "_agent_default_kernel_role": "coder"}}
```

The workflow engine copies the whole step, but AutoAgent hands the kernel only
`task["context"]`. A top-level `system` reaches the code registry, never reaches the kernel,
and `nexus_call` stays a stub.

**Google goes through `google-workspace`, not `gmail`, and its scopes must be explicit.**
`google-workspace` is in the gateway's catalog but not in JarvisCore's local provider
catalog, so `get_scopes()` returns `[]`. Left alone, Google is asked for no scopes at all:
consent "succeeds", the connection reports ACTIVE, and the first send fails with a 403 that
looks nothing like a scope problem. `email_report.py` passes the two Gmail scopes to
`runner.connect()` by hand.

| Symptom | Cause | Fix |
|---|---|---|
| `nexus_call is not available: no Nexus connection_id` | `system` or `_agent_default_kernel_role` is missing, or at the top level of the step | Both go **inside** the step's `context`, not at the top level |
| `403` on the first push | The repo is private | The gateway's GitHub app carries `public_repo`, not `repo`. Use a public repo |
| Consent re-opens on every run | Connections live in process memory | Put the printed connection ids in `.env` |
| Consent hangs, never goes ACTIVE | Return URL mismatch | `NEXUS_RETURN_URL=http://localhost:9090/callback`. The CLI listener is on 9090 |
| `memory:` always says first look | Redis isn't up | Long-term memory needs Redis and blob storage. Start Redis |

---

## Files

| File | What it is |
|---|---|
| `write_code.py`, `push_and_open_pr.py`, `review_pr.py`, `email_report.py` | The four steps, in run order, each standalone |
| `agents.py` | CodeSmith, Inspector and Reporter |
| `runner.py` | Mesh setup, Nexus consent, and the six deterministic GitHub and Gmail calls |
| `config.py` | Every setting, read from `.env` |
| `tracer.py` | Prints each call as it happens |
| `providers.py` | Lists the gateway's providers directly |
| `main.py`, `dashboard/app.py` | The dashboard backend and front end |
| `atoms/github/` | The three GitHub write atoms |
| `building-a-github-code-review-squad.pdf` | The slides |
