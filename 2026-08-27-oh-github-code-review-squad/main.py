"""
GitHub Code Review Squad — backend API.

Five actions, matching the four CLI steps plus explicit Nexus consent:

    POST /nexus/connect/{provider}   run OAuth consent for github or google-workspace
    POST /step/write                 CodeSmith writes the module
    POST /step/push                  push it, open the PR                (needs github)
    POST /step/review                read it back, review it, comment    (needs github)
    POST /step/draft                 Reporter drafts the report
    POST /send                       send the draft                      (needs google-workspace)

Each is its own call so the dashboard can show what that step actually
produced — the code, the PR link, the findings, the draft — rather than one
opaque "done" at the end. State lives in memory between calls, one run at a
time, which matches the demo: nobody is running this twice at once.

    python main.py
"""
import json
import logging
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import config
from agents import CodeSmith, Inspector, Reporter
from runner import (build_mesh, comment_on_pr, commit_file, connect,
                    create_branch, memory_for, open_pr, read_file, send_email,
                    think, write_module)
from tracer import get_tracer

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

tracer = get_tracer()

app = FastAPI(
    title="GitHub Code Review Squad",
    description="Write → push → review → draft → send, one step at a time, all through Nexus",
    version="2.0.0",
)

mesh = None
_state: dict = {}   # one active run's worth of output, held between step calls


class ProviderRequest(BaseModel):
    pass


class WriteResponse(BaseModel):
    source: str
    checks: list   # [{"label": str, "found": bool}]
    complete: bool


class PushResponse(BaseModel):
    branch: str
    file_url: str
    commit_url: str
    pr_number: int
    pr_url: str


class ReviewResponse(BaseModel):
    severity: str
    summary: str
    findings: list
    comment_url: str
    recalled_previous_review: bool


class DraftResponse(BaseModel):
    subject: str
    html: str


class SendResponse(BaseModel):
    message_id: str


class ConnectResponse(BaseModel):
    provider: str
    connection_id: str


def _require(key: str, message: str):
    if key not in _state:
        raise HTTPException(400, message)
    return _state[key]


@app.on_event("startup")
async def startup():
    global mesh
    mesh = await build_mesh(CodeSmith, Inspector, Reporter)
    logger.info("Mesh started — agents: codesmith, inspector, reporter")


@app.on_event("shutdown")
async def shutdown():
    if mesh:
        await mesh.stop()
    await tracer.close()


@app.get("/health")
async def health():
    return {"status": "ok", "agents": ["codesmith", "inspector", "reporter"]}


@app.get("/nexus")
async def nexus_status():
    """
    Connection state per provider.

    Reports what this process actually holds rather than what is registered
    — a registered provider with no consent still cannot make a call.
    """
    auth = getattr(mesh, "_auth_manager", None)
    held = dict(getattr(auth, "_connections", {}) or {})

    out = []
    for provider in ("github", config.GOOGLE_PROVIDER):
        conn_id = held.get(provider)
        state = "not_connected"
        if conn_id and auth and auth.nexus_client:
            try:
                state = (await auth.nexus_client.check_connection_status(conn_id)).lower()
            except Exception as exc:
                logger.warning("status check failed for %s: %s", provider, exc)
                state = "unknown"
        out.append({
            "provider": provider,
            "state": state,
            "connection_id": (conn_id[:8] + "…") if conn_id else None,
        })
    return {"gateway": config.NEXUS_GATEWAY_URL, "providers": out}


@app.post("/nexus/connect/{provider}", response_model=ConnectResponse)
async def nexus_connect(provider: str):
    """
    Run consent for one provider, on demand.

    Opens the OAuth screen in whatever browser is on this machine and blocks
    until it completes — the same thing push_and_open_pr.py/email_report.py do, just reachable
    as a button instead of a terminal prompt.
    """
    if provider not in ("github", config.GOOGLE_PROVIDER):
        raise HTTPException(404, f"Unknown provider: {provider}")
    scopes = config.GOOGLE_SCOPES if provider == config.GOOGLE_PROVIDER else None
    try:
        _, conn_id = await connect(mesh, provider, scopes=scopes)
    except Exception as exc:
        raise HTTPException(502, f"Consent for {provider} failed: {exc}")
    return ConnectResponse(provider=provider, connection_id=conn_id[:8] + "…")


@app.post("/step/write", response_model=WriteResponse)
async def step_write():
    """CodeSmith writes the module. No Nexus involved."""
    await tracer.step_start("write", "CodeSmith", f"Write {config.TARGET_PATH}")
    source, results = await write_module(mesh)
    complete = all(found for _, found in results)
    _state.clear()   # a fresh write starts a fresh run
    _state["source"] = source
    await tracer.step_complete("write", "CodeSmith", "success" if complete else "partial",
                               f"{len(source)} chars, {sum(f for _, f in results)}/5 defects")
    return WriteResponse(
        source=source,
        checks=[{"label": label, "found": found} for label, found in results],
        complete=complete,
    )


@app.post("/step/push", response_model=PushResponse)
async def step_push():
    """Push what /step/write produced, and open the pull request."""
    source = _require("source", "Nothing written yet — call /step/write first.")

    branch = config.BRANCH
    await tracer.step_start("push", "CodeSmith", f"Commit to {branch}")

    proxy, conn = await connect(mesh, "github")
    await create_branch(proxy, conn, branch)
    commit = await commit_file(proxy, conn, branch, config.TARGET_PATH, source,
                               "Add payments module for review")
    pr = await open_pr(proxy, conn, branch, "Payments module for review",
                       "Generated by CodeSmith during the JarvisCore build-along.")

    _state.update(branch=branch, pr=pr, github_proxy=proxy, github_conn=conn)
    await tracer.step_complete("push", "CodeSmith", "success", pr["url"])
    return PushResponse(branch=branch, file_url=commit["file_url"],
                        commit_url=commit["commit_url"], pr_number=pr["number"], pr_url=pr["url"])


@app.post("/step/review", response_model=ReviewResponse)
async def step_review():
    """Read the file back from GitHub, review it, comment, remember."""
    pr = _require("pr", "Nothing pushed yet — call /step/push first.")
    branch = _state["branch"]
    proxy, conn = _state["github_proxy"], _state["github_conn"]

    await tracer.step_start("review", "Inspector", "Read the file back and review it")

    memory = memory_for(mesh, step_id="review", agent_id="inspector")
    prior = await memory.ltm.load_summary() if memory.ltm else None
    if prior:
        await tracer.observation("Inspector", "Recalled a previous review of this repository")

    read_back = await read_file(proxy, conn, branch, config.TARGET_PATH)
    review = await think(mesh, "inspector", (
        f"Review this file. It is {config.TARGET_PATH} exactly as committed to "
        f"{config.repo_slug()} on branch {branch}.\n\n```python\n{read_back}\n```\n\n"
        + (f"For reference, here is your review of an EARLIER VERSION of this file:\n{prior}\n\n"
           f"Review the code above from scratch — line numbers and contents may have "
           f"changed. Open your summary by saying what is different.\n\n" if prior else "")
        + "Every severity value must be exactly one of: critical, high, medium, low.\n"
          "Set result = {'success': True, 'data': {'severity': ..., 'summary': ..., "
          "'findings': [{'type':..., 'severity':..., 'line':..., 'description':..., 'fix':...}]}}"
    ))
    findings = review.get("findings", [])
    comment_body = "## Automated review\n\n| Severity | Type | Line | Issue |\n|---|---|---|---|\n" + "\n".join(
        f"| **{f.get('severity','?')}** | {f.get('type','?')} | {f.get('line','?')} | {f.get('description','')} |"
        for f in findings
    )
    comment_url = await comment_on_pr(proxy, conn, pr["number"], comment_body)

    if memory.ltm:
        await memory.ltm.save_summary(json.dumps(
            {"severity": review.get("severity"), "summary": review.get("summary"),
             "findings": findings}, indent=2))

    _state["review"] = review
    await tracer.step_complete("review", "Inspector", "success", review.get("summary", ""))
    return ReviewResponse(
        severity=review.get("severity", "?"), summary=review.get("summary", ""),
        findings=findings, comment_url=comment_url, recalled_previous_review=bool(prior),
    )


@app.post("/step/draft", response_model=DraftResponse)
async def step_draft():
    """Reporter drafts the email from the review. Does not send it."""
    review = _require("review", "Nothing reviewed yet — call /step/review first.")
    pr = _state["pr"]

    await tracer.step_start("draft", "Reporter", "Draft the email")
    findings = review.get("findings", [])
    criticals = sum(1 for f in findings if str(f.get("severity", "")).lower() == "critical")
    draft = await think(mesh, "reporter", (
        f"Write the review email.\n\nRepository: {config.repo_slug()}   Branch: {_state['branch']}\n"
        f"Pull request: {pr['url']}\nOverall severity: {review.get('severity')}   "
        f"Critical issues: {criticals}\nSummary: {review.get('summary')}\nFindings: {findings}\n\n"
        f"It is going to {config.RECIPIENT} and it is from {config.SENDER_NAME}.\n"
        f"Set result = {{'success': True, 'data': {{'subject': <subject line>, 'html': <full HTML body>}}}}"
    ))
    _state["draft"] = draft
    await tracer.step_complete("draft", "Reporter", "success", draft.get("subject", ""))
    return DraftResponse(subject=draft.get("subject", ""), html=draft.get("html", ""))


@app.post("/send", response_model=SendResponse)
async def send():
    """Send the draft. Nothing reaches an inbox before this is called."""
    draft = _require("draft", "Nothing drafted yet — call /step/draft first.")
    proxy, conn = await connect(mesh, config.GOOGLE_PROVIDER, scopes=config.GOOGLE_SCOPES)
    message_id = await send_email(proxy, conn, config.RECIPIENT, draft["subject"], draft["html"])
    await tracer.observation("Reporter", f"Sent to {config.RECIPIENT} — message {message_id}")
    del _state["draft"]
    return SendResponse(message_id=message_id)


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  GitHub Code Review Squad — backend API")
    print("  Listening at   http://localhost:8004")
    print("  Endpoints      /health  /nexus  /nexus/connect/{provider}")
    print("                 /step/write  /step/push  /step/review  /step/draft  /send")
    print()
    print("  This process has no page of its own. The UI is the dashboard —")
    print("  run it separately, in another terminal:")
    print("    cd dashboard && python app.py")
    print("  then open  http://localhost:8080")
    print("=" * 60 + "\n")

    uvicorn.run(app, host="0.0.0.0", port=8004)
