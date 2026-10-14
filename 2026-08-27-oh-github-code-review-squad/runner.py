"""
Plumbing: the mesh, the Nexus calls, and the handoff between steps.

The split here is the framework's own rule. The three agents in agents.py do
the judgement — write the module, review it, draft the report. The mechanics of
talking to GitHub and Gmail are ordinary Python, right here, because they are
deterministic and we want every one of them visible on screen.

Nothing in this file ever holds a credential. Every call goes through
NexusCallProxy.call(connection_id, ...), which resolves the token internally and
hands back only the HTTP response. The connection_id is an opaque handle — it is
safe to print, and we do.
"""
import asyncio
import base64
import json
import re
import tempfile
from pathlib import Path

from jarviscore import Mesh
from jarviscore.memory import UnifiedMemory

import config

GITHUB = "https://api.github.com"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"

RUN_DIR = Path(__file__).parent / ".run"
RULE = "─" * 74

DIM, CYAN, GREEN, YELLOW, RED, BOLD, OFF = (
    "\033[2m", "\033[36m", "\033[32m", "\033[33m", "\033[31m", "\033[1m", "\033[0m"
)


# ── screen ───────────────────────────────────────────────────────────────────

def banner(step: str, subtitle: str = "") -> None:
    print(f"\n{BOLD}{RULE}{OFF}")
    print(f"{BOLD}  {step}{OFF}")
    if subtitle:
        print(f"  {DIM}{subtitle}{OFF}")
    print(f"{BOLD}{RULE}{OFF}")


def stage(n: int, text: str) -> None:
    print(f"\n{CYAN}[{n}]{OFF} {BOLD}{text}{OFF}")


def ok(text: str) -> None:
    print(f"  {GREEN}✓{OFF} {text}")


def warn(text: str) -> None:
    print(f"  {YELLOW}!{OFF} {text}")


def link(label: str, url: str) -> None:
    print(f"  {label:<14} {CYAN}{url}{OFF}")


# ── mesh ─────────────────────────────────────────────────────────────────────

def _coerce_nexus_credentials() -> None:
    """
    Work around a real bug in the framework's own token parsing.

    NexusClient.resolve_strategy() builds a DynamicStrategy where
    `credentials: Dict[str, str]` — every value must be a string. GitHub's
    token payload happens to be string-only, so this has never surfaced. The
    gateway's google-workspace payload nests `expired` (bool) and
    `expires_in` (int) inside `credentials`, and pydantic rejects the whole
    thing before a single Gmail call can be made.

    Neither field is read again anywhere downstream — only the top-level
    `expires_at` ISO string drives expiry — so stringifying them here is a
    complete fix, not a patch over a symptom.
    """
    from jarviscore.nexus import client as nexus_client

    if getattr(nexus_client.NexusClient, "_credentials_coerced", False):
        return
    original_get_token = nexus_client.NexusClient.get_token

    async def get_token(self, connection_id: str):
        data = await original_get_token(self, connection_id)
        creds = data.get("credentials")
        if isinstance(creds, dict):
            data["credentials"] = {
                k: v if isinstance(v, str) else json.dumps(v) for k, v in creds.items()
            }
        return data

    nexus_client.NexusClient.get_token = get_token
    nexus_client.NexusClient._credentials_coerced = True


def _isolate_agent_workspace() -> None:
    """
    Stop the coder sandbox running inside this checkout.

    CoderSandbox defaults its workspace to Path.cwd() and `git` is the first
    entry in its bash allow-list. Left alone, an agent asked to put code on
    GitHub will happily `git checkout -b` and `git commit` in whatever repo you
    launched it from — which is how this repo ended up on an agent's branch
    with a day of work orphaned on it. Give it an empty scratch directory
    instead.
    """
    from jarviscore.execution import coder_sandbox as cs

    if getattr(cs.CoderSandbox, "_workspace_isolated", False):
        return
    scratch = Path(tempfile.mkdtemp(prefix="jc-agent-workspace-"))
    original_init = cs.CoderSandbox.__init__

    def __init__(self, *args, **kwargs):
        if not args and kwargs.get("workspace_dir") is None:
            kwargs["workspace_dir"] = scratch
        original_init(self, *args, **kwargs)

    cs.CoderSandbox.__init__ = __init__
    cs.CoderSandbox._workspace_isolated = True


async def build_mesh(*agent_classes) -> Mesh:
    """Start a mesh with Nexus auth and Redis available."""
    _isolate_agent_workspace()          # before Mesh() — sandboxes are built in start()
    _coerce_nexus_credentials()
    mesh = Mesh(config=config.mesh_config())
    for cls in agent_classes:
        mesh.add(cls)
    await mesh.start()

    if getattr(mesh, "_auth_manager", None) is None:
        raise RuntimeError(
            "Mesh started without a Nexus auth manager — config.mesh_config() "
            "must set auth_mode, or NEXUS_GATEWAY_URL is missing."
        )
    return mesh


async def think(mesh, role: str, task: str, context: dict | None = None,
                attempts: int = 3) -> dict:
    """
    Ask an agent for a judgement and return its payload.

    Two things make this more than a one-liner. The kernel reports success even
    when the generated code set no result, so an empty payload has to be treated
    as the failure it is rather than passed down the chain. And its loop is not
    deterministic — the same task can converge on one run and stall on the next
    — so we give it a couple of goes before giving up.
    """
    last = ""
    for attempt in range(1, attempts + 1):
        results = await mesh.workflow(f"{role}-{config.RUN_STAMP}-{attempt}", [{
            "id": role,
            "agent": role,
            "task": task,
            "context": {"_agent_default_kernel_role": "coder", **(context or {})},
        }])
        r = results[0]
        payload = r.get("output") or {}
        data = payload.get("data") if isinstance(payload, dict) else None

        if r.get("status") == "success" and data:
            if attempt > 1:
                ok(f"{role} came back on attempt {attempt}")
            return data

        last = (r.get("error") or
                f"reported success with an empty payload "
                f"({json.dumps(payload, default=str)[:120]})")
        if attempt < attempts:
            warn(f"{role} attempt {attempt}: {str(last)[:90]} — retrying")

    raise RuntimeError(f"{role} failed after {attempts} attempts. Last: {last}")


# ── nexus ────────────────────────────────────────────────────────────────────

async def connect(mesh, provider: str, scopes: list | None = None):
    """
    Get (proxy, connection_id) for a provider, running OAuth consent if needed.

    Scopes are passed explicitly for providers JarvisCore's local catalog does
    not know — google-workspace is on the gateway but not in PROVIDER_CATALOG,
    so left alone it would request consent for nothing at all and every call
    afterwards would 403.
    """
    from jarviscore.nexus.call_proxy import NexusCallProxy

    auth = mesh._auth_manager

    # Each step is its own process and connections live in process memory, so
    # without this the audience sits through a consent screen per step. The
    # connection_id is an opaque handle — it grants nothing on its own — so
    # parking it in .run/ between steps is safe and keeps the demo moving.
    parked = RUN_DIR / f"connection-{provider}.txt"
    if provider not in getattr(auth, "_connections", {}) and parked.exists():
        auth._connections[provider] = parked.read_text().strip()

    cached = getattr(auth, "_connections", {}).get(provider)
    if cached:
        ok(f"{provider}: reusing connection {DIM}{cached[:8]}…{OFF}")
        conn = cached
    else:
        print(f"  {CYAN}→{OFF} {provider}: no connection — opening consent in your browser")
        conn = await (auth.authenticate(provider, scopes=scopes) if scopes
                      else auth.get_connection_id(provider))
        ok(f"{provider}: connected {DIM}{conn[:8]}…{OFF}")
        # The gateway reports ACTIVE the moment consent lands, but the broker
        # takes a beat to store the token. Calling straight away gets
        # "no credentials found" and falls through to the local store, which
        # has nothing. Wait for the token to actually resolve before going on.
        for attempt in range(10):
            try:
                await auth.resolve_strategy(conn)
                break
            except Exception:
                if attempt == 9:
                    raise RuntimeError(
                        f"{provider} consent completed but the gateway never produced "
                        f"a token for {conn[:8]}…. Check the provider's client secret "
                        f"on the gateway."
                    )
                await asyncio.sleep(1.5)
        RUN_DIR.mkdir(exist_ok=True)
        parked.write_text(conn)
    return NexusCallProxy(auth), conn


async def api(proxy, conn, method: str, url: str, allow=(), **kw):
    """
    One authenticated call, printed. Raises unless 2xx or an allowed status.

    The proxy is the only object that ever sees a credential; we get back a
    response and nothing else.
    """
    short = url.replace(GITHUB, "").replace(GMAIL, "gmail")
    print(f"  {DIM}→ {method:5} {short}{OFF}")
    r = await proxy.call(conn, method, url, **kw)
    code = r["status_code"]
    if r["ok"] or code in allow:
        print(f"  {DIM}←{OFF} {GREEN}{code}{OFF}")
        return r
    print(f"  {DIM}←{OFF} {RED}{code}{OFF}")
    raise RuntimeError(f"{method} {short} → {code}: {r['body'][:300]}")


# ── github ───────────────────────────────────────────────────────────────────

async def create_branch(proxy, conn, branch: str) -> str:
    o, r_, base = config.GITHUB_OWNER, config.GITHUB_REPO, config.BASE_BRANCH
    ref = await api(proxy, conn, "GET", f"{GITHUB}/repos/{o}/{r_}/git/ref/heads/{base}")
    sha = ref["json"]["object"]["sha"]
    made = await api(proxy, conn, "POST", f"{GITHUB}/repos/{o}/{r_}/git/refs",
                     allow=(422,), json={"ref": f"refs/heads/{branch}", "sha": sha})
    if made["status_code"] == 422:
        warn(f"branch {branch} already exists — reusing it")
    return sha


async def commit_file(proxy, conn, branch: str, path: str, content: str, message: str) -> dict:
    o, r_ = config.GITHUB_OWNER, config.GITHUB_REPO
    probe = await proxy.call(conn, "GET", f"{GITHUB}/repos/{o}/{r_}/contents/{path}",
                             params={"ref": branch})
    body = {"message": message, "branch": branch,
            "content": base64.b64encode(content.encode()).decode()}
    if probe["ok"]:
        body["sha"] = probe["json"]["sha"]
    res = await api(proxy, conn, "PUT", f"{GITHUB}/repos/{o}/{r_}/contents/{path}", json=body)
    return {"file_url": res["json"]["content"]["html_url"],
            "commit_url": res["json"]["commit"]["html_url"]}


async def read_file(proxy, conn, branch: str, path: str) -> str:
    """Read the file back out of GitHub. This is the round-trip proof."""
    o, r_ = config.GITHUB_OWNER, config.GITHUB_REPO
    res = await api(proxy, conn, "GET", f"{GITHUB}/repos/{o}/{r_}/contents/{path}",
                    params={"ref": branch})
    return base64.b64decode(res["json"]["content"]).decode()


async def open_pr(proxy, conn, branch: str, title: str, body: str) -> dict:
    o, r_, base = config.GITHUB_OWNER, config.GITHUB_REPO, config.BASE_BRANCH
    res = await api(proxy, conn, "POST", f"{GITHUB}/repos/{o}/{r_}/pulls", allow=(422,),
                    json={"title": title, "head": branch, "base": base, "body": body})
    if res["status_code"] == 422:
        opens = await api(proxy, conn, "GET", f"{GITHUB}/repos/{o}/{r_}/pulls",
                          params={"head": f"{o}:{branch}", "state": "open"})
        j = opens["json"][0]
        return {"number": j["number"], "url": j["html_url"]}
    return {"number": res["json"]["number"], "url": res["json"]["html_url"]}


async def comment_on_pr(proxy, conn, number: int, body: str) -> str:
    o, r_ = config.GITHUB_OWNER, config.GITHUB_REPO
    res = await api(proxy, conn, "POST",
                    f"{GITHUB}/repos/{o}/{r_}/issues/{number}/comments", json={"body": body})
    return res["json"]["html_url"]


# ── gmail ────────────────────────────────────────────────────────────────────

async def send_email(proxy, conn, to: str, subject: str, html: str) -> str:
    raw = (f"To: {to}\r\nSubject: {subject}\r\n"
           f"Content-Type: text/html; charset=utf-8\r\nMIME-Version: 1.0\r\n\r\n{html}")
    res = await api(proxy, conn, "POST", f"{GMAIL}/messages/send",
                    json={"raw": base64.urlsafe_b64encode(raw.encode()).decode()})
    return res["json"]["id"]


# ── handoff between steps ────────────────────────────────────────────────────

def save(name: str, value) -> Path:
    """Persist a step's output so the next step can pick it up."""
    RUN_DIR.mkdir(exist_ok=True)
    p = RUN_DIR / name
    p.write_text(value if isinstance(value, str) else json.dumps(value, indent=2))
    return p


def load(name: str, as_json: bool = False):
    p = RUN_DIR / name
    if not p.exists():
        raise SystemExit(
            f"\n  {RED}✗{OFF} {name} is missing — run the previous step first.\n"
        )
    return json.loads(p.read_text()) if as_json else p.read_text()


async def confirm(question: str) -> bool:
    """Ask before doing something the audience can see leave the building."""
    answer = await asyncio.get_running_loop().run_in_executor(
        None, input, f"\n  {BOLD}{question} [y/N]{OFF} "
    )
    return answer.strip().lower() in ("y", "yes")


# What Inspector has to find later. Checked here so a run never hands GitHub
# a fixture that is missing one of the five defects. The model reshapes
# things — the framework's ValidationLayer flags a bare `API_KEY = "sk_..."`
# and the model rewrites it as an os.getenv default, still a secret sitting
# in source — so these match the defect, not one spelling of it.
PLANTED_CHECKS = [
    ("SQL built by f-string",         r'f["\'][^"\']*(SELECT|INSERT|UPDATE|DELETE)'),
    ("credential literal in source",  r'["\']sk_live_'),
    ("nested loop over one list",     r'for [^\n]+:\s*\n\s+for [^\n]+:'),
    ("bare except",                   r'except\s*:'),
    ("single-character names",        r'\bfor [a-z]\b|\([a-z]\)|\b[a-z] = |\bdef [a-z]\('),
]


def check_defects(source: str) -> list[tuple[str, bool]]:
    """Which of the five planted defects actually made it into the module."""
    return [(label, bool(re.search(pattern, source))) for label, pattern in PLANTED_CHECKS]


async def write_module(mesh, nudge: str = "") -> tuple[str, list]:
    """
    Ask CodeSmith for the module, retrying up to 3 times against a named gap.

    The model drops a defect now and then — usually widening a bare `except:`
    to `except Exception:`. Rather than accept a fixture Inspector can't fully
    review, ask again naming exactly what's missing.
    """
    from agents import PLANTED_ISSUES
    import config

    base = (
        f"Write the module for {config.TARGET_PATH}.\n\n"
        f"It must contain exactly these five problems:\n{PLANTED_ISSUES}\n"
        f"Assign the module source to a Python string, then set\n"
        f"    result = {{'success': True, 'data': {{'source': <that string>}}}}\n"
        f"Do not write a file. Do not execute or import the module."
    )
    source, results = "", []
    for attempt in range(1, 4):
        ask = base
        if results:
            gone = ", ".join(label for label, found in results if not found)
            ask += (f"\n\nYour last attempt was missing: {gone}. Include those "
                    f"exactly as described — a bare `except:` means `except:`, "
                    f"not `except Exception:`.")
            warn(f"attempt {attempt - 1} missing: {gone} — asking again")
        data = await think(mesh, "codesmith", ask)
        source = data.get("source", "")
        results = check_defects(source)
        if all(found for _, found in results):
            break
    return source, results


def memory_for(mesh, step_id: str, agent_id: str) -> UnifiedMemory:
    """Memory on a workflow id that is stable across runs — that is what makes recall work."""
    return UnifiedMemory(
        workflow_id=config.MEMORY_WORKFLOW_ID,
        step_id=step_id,
        agent_id=agent_id,
        redis_store=getattr(mesh, "_redis_store", None),
        blob_storage=getattr(mesh, "_blob_storage", None),
    )
