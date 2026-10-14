"""
GitHub Code Review Squad — Dashboard

The browsable front end for the backend on :8004. Five actions, shown as a
pipeline: connect to Nexus, write, push, review, draft, send — each one its
own card that fills in with what actually happened, not a single "done" at
the end.

Run: python app.py
Open: http://localhost:8080

The backend must already be running (python main.py, from the repo root, in
another terminal) — this page has no agents of its own, it only drives them.
"""
import logging

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

BACKEND = "http://localhost:8004"

app = FastAPI(title="GitHub Code Review Squad — Dashboard")


async def _proxy_post(path: str, timeout: float = 60.0):
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(f"{BACKEND}{path}")
    except httpx.ConnectError:
        raise HTTPException(502, "Cannot reach the backend on :8004 — is `python main.py` running?")
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        raise HTTPException(r.status_code, detail)
    return r.json()


@app.get("/api/health")
async def health():
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            r = await client.get(f"{BACKEND}/health")
            return {"running": r.status_code == 200}
        except Exception:
            return {"running": False}


@app.get("/api/nexus")
async def nexus_status():
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(f"{BACKEND}/nexus")
            return r.json()
        except Exception as exc:
            return {"gateway": None, "providers": [], "error": f"Backend not running on :8004 ({exc})"}


@app.post("/api/nexus/connect/{provider}")
async def nexus_connect(provider: str):
    """Blocks until consent completes — up to five minutes. That's expected."""
    return await _proxy_post(f"/nexus/connect/{provider}", timeout=310.0)


@app.post("/api/step/write")
async def step_write():
    return await _proxy_post("/step/write", timeout=180.0)


@app.post("/api/step/push")
async def step_push():
    return await _proxy_post("/step/push", timeout=60.0)


@app.post("/api/step/review")
async def step_review():
    return await _proxy_post("/step/review", timeout=180.0)


@app.post("/api/step/draft")
async def step_draft():
    return await _proxy_post("/step/draft", timeout=180.0)


@app.post("/api/send")
async def send():
    return await _proxy_post("/send", timeout=310.0)


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    return HTML_TEMPLATE


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GitHub Code Review Squad</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;700&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
  :root {
    --bg:#0a0e1a; --surface:#121a2c; --surface-2:#1a2338; --border:#233052; --border-firm:#2e3d63;
    --ink:#e7edf9; --ink-2:#a9b8d6; --muted:#5f7099;
    --brand:#3b7cff; --brand-lift:rgba(59,124,255,.14);
    --good:#22c55e; --good-lift:rgba(34,197,94,.12);
    --warn:#eab308; --warn-lift:rgba(234,179,8,.12);
    --bad:#ef4444; --bad-lift:rgba(239,68,68,.12);
  }
  * { box-sizing:border-box; }
  body {
    margin:0; background:var(--bg); color:var(--ink);
    font-family:"IBM Plex Sans",-apple-system,sans-serif;
    min-height:100vh; line-height:1.5;
  }
  h1,h2,h3 { font-family:Archivo,"IBM Plex Sans",sans-serif; margin:0; }
  code, pre, .mono { font-family:"IBM Plex Mono",ui-monospace,monospace; }

  .wrap { max-width:1180px; margin:0 auto; padding:30px 24px 70px; }
  header { display:flex; align-items:baseline; gap:14px; margin-bottom:24px; flex-wrap:wrap; }
  header h1 { font-size:1.5rem; font-weight:700; }
  header .sub { color:var(--muted); font-size:.9rem; }

  .top-row { display:grid; grid-template-columns:2fr 1fr; gap:16px; margin-bottom:28px; }
  @media (max-width:880px) { .top-row { grid-template-columns:1fr; } }

  .panel { background:var(--surface); border:1px solid var(--border); border-radius:14px; padding:18px 20px; }
  .panel h2 { font-size:.75rem; text-transform:uppercase; letter-spacing:.09em;
              color:var(--muted); margin-bottom:12px; font-weight:600; }

  .nexus-row { display:flex; align-items:center; gap:10px; padding:8px 0; }
  .nexus-row + .nexus-row { border-top:1px solid var(--border); }
  .dot { width:9px; height:9px; border-radius:50%; background:var(--muted); flex:none; }
  .dot.active { background:var(--good); box-shadow:0 0 8px rgba(34,197,94,.55); }
  .dot.connecting { background:var(--warn); animation:pulse 1.3s infinite; }
  .dot.unknown { background:var(--warn); }
  .nexus-row .name { font-weight:600; font-size:.92rem; }
  .nexus-row .conn { color:var(--muted); font-size:.76rem; margin-left:2px; }
  .nexus-row .state { color:var(--muted); font-size:.8rem; margin-left:auto; margin-right:10px; }
  @keyframes pulse { 50% { opacity:.4; } }

  .connect-btn {
    font:inherit; font-size:.78rem; font-weight:600; border:none; border-radius:7px;
    padding:6px 12px; cursor:pointer; background:var(--brand); color:#fff;
  }
  .connect-btn:disabled { opacity:.5; cursor:default; }
  .connect-btn.done { background:var(--surface-2); color:var(--good); border:1px solid var(--good); }

  .backend-row { display:flex; align-items:center; gap:9px; font-size:.9rem; }

  .pipeline { display:flex; flex-direction:column; gap:14px; }
  .step {
    background:var(--surface); border:1px solid var(--border); border-radius:14px;
    padding:18px 22px; opacity:.5; transition:opacity .25s;
  }
  .step.ready { opacity:1; }
  .step.done { border-color:var(--good); }
  .step-head { display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
  .step-num {
    width:26px; height:26px; border-radius:50%; background:var(--surface-2);
    border:1px solid var(--border-firm); display:flex; align-items:center; justify-content:center;
    font-size:.8rem; font-weight:700; color:var(--muted); flex:none;
  }
  .step.done .step-num { background:var(--good-lift); border-color:var(--good); color:var(--good); }
  .step-head h3 { font-size:1rem; font-weight:600; }
  .step-head .who { font-size:.78rem; color:var(--muted); }
  .step-head .runbtn {
    margin-left:auto; font:inherit; font-weight:600; font-size:.85rem; border:none;
    border-radius:8px; padding:9px 20px; cursor:pointer; background:var(--brand); color:#fff;
  }
  .step-head .runbtn:disabled { opacity:.4; cursor:default; }
  .step-body { margin-top:14px; display:none; }
  .step.done .step-body, .step.showing .step-body { display:block; }

  pre.code-block {
    background:#060a14; border:1px solid var(--border-firm); border-radius:10px;
    padding:14px 16px; overflow-x:auto; font-size:.78rem; color:#cfe0ff; max-height:280px;
  }
  .checks { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
  .check { font-size:.78rem; padding:4px 10px; border-radius:999px; }
  .check.yes { background:var(--good-lift); color:var(--good); }
  .check.no { background:var(--bad-lift); color:var(--bad); }

  .chips { display:flex; flex-wrap:wrap; gap:8px; margin-top:4px; }
  .chip {
    display:inline-flex; align-items:center; gap:6px; font-size:.82rem;
    background:var(--surface-2); border:1px solid var(--border-firm); border-radius:8px;
    padding:6px 12px; color:var(--ink-2); text-decoration:none;
  }
  .chip:hover { border-color:var(--brand); color:var(--ink); }

  table.findings { width:100%; border-collapse:collapse; font-size:.84rem; margin-top:6px; }
  table.findings th, table.findings td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--border); }
  table.findings th { color:var(--muted); font-size:.7rem; text-transform:uppercase; letter-spacing:.06em; }
  .sev { font-weight:700; font-size:.78rem; }
  .sev.critical { color:var(--bad); } .sev.high { color:#f97316; }
  .sev.medium { color:var(--warn); } .sev.low { color:var(--muted); }
  .badge { display:inline-block; font-size:.76rem; padding:3px 10px; border-radius:999px;
           background:var(--brand-lift); color:var(--brand); margin-bottom:8px; }

  .draft-preview { background:var(--surface-2); border:1px solid var(--border-firm);
    border-radius:10px; padding:14px 16px; margin-top:8px; font-size:.86rem; max-height:260px; overflow-y:auto; }
  .draft-preview .subject { font-weight:600; margin-bottom:8px; }

  .toast { margin-top:10px; font-size:.85rem; padding:9px 13px; border-radius:8px; }
  .toast.err { background:var(--bad-lift); color:#ff9b9b; }
  .toast.ok  { background:var(--good-lift); color:#8ff0b0; }

  .footnote { color:var(--muted); font-size:.78rem; margin-top:26px; text-align:center; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>GitHub Code Review Squad</h1>
    <span class="sub">CodeSmith → Inspector → Reporter, all through Nexus</span>
  </header>

  <div class="top-row">
    <div class="panel">
      <h2>Nexus connections</h2>
      <div id="nexusPanel"><div class="nexus-row"><span class="dot"></span><span class="state">checking…</span></div></div>
    </div>
    <div class="panel">
      <h2>Backend</h2>
      <div class="backend-row"><span class="dot" id="backendDot"></span>
        <span id="backendState">checking…</span></div>
    </div>
  </div>

  <div class="pipeline">

    <div class="step ready" id="step-write">
      <div class="step-head">
        <span class="step-num">1</span>
        <h3>CodeSmith writes the module</h3>
        <span class="who">judgement — no Nexus involved</span>
        <button class="runbtn" onclick="runWrite()">Run</button>
      </div>
      <div class="step-body" id="body-write"></div>
    </div>

    <div class="step" id="step-push">
      <div class="step-head">
        <span class="step-num">2</span>
        <h3>Push to GitHub</h3>
        <span class="who">needs github connected</span>
        <button class="runbtn" onclick="runPush()" disabled>Run</button>
      </div>
      <div class="step-body" id="body-push"></div>
    </div>

    <div class="step" id="step-review">
      <div class="step-head">
        <span class="step-num">3</span>
        <h3>Inspector reviews it</h3>
        <span class="who">reads back from GitHub, not from step 1</span>
        <button class="runbtn" onclick="runReview()" disabled>Run</button>
      </div>
      <div class="step-body" id="body-review"></div>
    </div>

    <div class="step" id="step-draft">
      <div class="step-head">
        <span class="step-num">4</span>
        <h3>Reporter drafts the report</h3>
        <span class="who">does not send anything yet</span>
        <button class="runbtn" onclick="runDraft()" disabled>Run</button>
      </div>
      <div class="step-body" id="body-draft"></div>
    </div>

  </div>

  <p class="footnote">Every HTTP call each step makes is also printed live in the backend terminal.</p>
</div>

<script>
let state = { write:null, push:null, review:null, draft:null };

function el(id) { return document.getElementById(id); }
function esc(s) { return String(s).replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c])); }

async function post(path) {
  const r = await fetch(path, { method: "POST" });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `${r.status} ${r.statusText}`);
  return data;
}

function markDone(stepId) {
  el(stepId).classList.remove("showing");
  el(stepId).classList.add("done");
}

function toast(bodyId, msg, ok) {
  el(bodyId).innerHTML += `<div class="toast ${ok ? "ok" : "err"}">${esc(msg)}</div>`;
}

// ── Nexus panel ──────────────────────────────────────────────────────────
async function pollNexus() {
  try {
    const r = await fetch("/api/nexus");
    const d = await r.json();
    const panel = el("nexusPanel");
    if (d.error) { panel.innerHTML = `<div class="nexus-row"><span class="state">${esc(d.error)}</span></div>`; return; }
    panel.innerHTML = (d.providers || []).map(p => {
      const active = p.state === "active";
      const label = p.provider === "google-workspace" ? "Google (Gmail)" : "GitHub";
      const btn = active
        ? `<button class="connect-btn done" disabled>Connected</button>`
        : `<button class="connect-btn" onclick="doConnect('${p.provider}', this)">Connect</button>`;
      return `<div class="nexus-row">
        <span class="dot ${p.state}"></span>
        <span class="name">${label}</span>
        <span class="conn">${p.connection_id || ""}</span>
        <span class="state">${p.state.replace("_"," ")}</span>
        ${btn}
      </div>`;
    }).join("");
  } catch (e) {}
}

async function doConnect(provider, btn) {
  btn.disabled = true;
  btn.textContent = "Waiting for browser…";
  try {
    await post(`/api/nexus/connect/${provider}`);
  } catch (e) {
    btn.disabled = false;
    btn.textContent = "Connect";
    alert(`Consent failed: ${e.message}`);
    return;
  }
  await pollNexus();
}

async function pollHealth() {
  try {
    const r = await fetch("/api/health");
    const d = await r.json();
    el("backendDot").className = "dot " + (d.running ? "active" : "");
    el("backendState").textContent = d.running ? "running on :8004" : "not running — start `python main.py`";
  } catch (e) {}
}

// ── Step 1 — write ───────────────────────────────────────────────────────
async function runWrite() {
  const body = el("body-write");
  el("step-write").classList.add("showing");
  body.innerHTML = "<p>Writing…</p>";
  try {
    const d = await post("/api/step/write");
    state.write = d;
    const checks = d.checks.map(c =>
      `<span class="check ${c.found ? "yes" : "no"}">${c.found ? "✓" : "✗"} ${esc(c.label)}</span>`).join("");
    body.innerHTML = `<pre class="code-block">${esc(d.source)}</pre><div class="checks">${checks}</div>`;
    if (!d.complete) { toast("body-write", "Not all five defects landed — you can re-run this step.", false); return; }
    markDone("step-write");
    el("step-push").classList.add("ready");
    el("step-push").querySelector(".runbtn").disabled = false;
  } catch (e) { toast("body-write", e.message, false); }
}

// ── Step 2 — push ────────────────────────────────────────────────────────
async function runPush() {
  const body = el("body-push");
  el("step-push").classList.add("showing");
  body.innerHTML = "<p>Connecting to GitHub and pushing…</p>";
  try {
    const d = await post("/api/step/push");
    state.push = d;
    body.innerHTML = `<div class="chips">
      <a class="chip" href="${d.file_url}" target="_blank">📄 file</a>
      <a class="chip" href="${d.commit_url}" target="_blank">⎇ commit</a>
      <a class="chip" href="${d.pr_url}" target="_blank">↗ pull request #${d.pr_number}</a>
      <span class="chip mono">${esc(d.branch)}</span>
    </div>`;
    markDone("step-push");
    el("step-review").classList.add("ready");
    el("step-review").querySelector(".runbtn").disabled = false;
    pollNexus();
  } catch (e) { toast("body-push", e.message, false); }
}

// ── Step 3 — review ──────────────────────────────────────────────────────
async function runReview() {
  const body = el("body-review");
  el("step-review").classList.add("showing");
  body.innerHTML = "<p>Reading it back from GitHub and reviewing…</p>";
  try {
    const d = await post("/api/step/review");
    state.review = d;
    const badge = d.recalled_previous_review
      ? `<span class="badge">recalled a previous review</span>`
      : `<span class="badge">first look at this repository</span>`;
    const rows = (d.findings || []).map(f => `
      <tr><td class="sev ${f.severity}">${esc(f.severity)}</td><td>${esc(f.type)}</td>
          <td>${esc(String(f.line))}</td><td>${esc(f.description)}</td></tr>`).join("");
    body.innerHTML = `${badge}
      <table class="findings"><thead><tr><th>Severity</th><th>Type</th><th>Line</th><th>Issue</th></tr></thead>
        <tbody>${rows}</tbody></table>
      <div class="chips"><a class="chip" href="${d.comment_url}" target="_blank">💬 review comment</a></div>`;
    markDone("step-review");
    el("step-draft").classList.add("ready");
    el("step-draft").querySelector(".runbtn").disabled = false;
  } catch (e) { toast("body-review", e.message, false); }
}

// ── Step 4 — draft + send ────────────────────────────────────────────────
async function runDraft() {
  const body = el("body-draft");
  el("step-draft").classList.add("showing");
  body.innerHTML = "<p>Drafting…</p>";
  try {
    const d = await post("/api/step/draft");
    state.draft = d;
    body.innerHTML = `<div class="draft-preview">
        <div class="subject">${esc(d.subject)}</div>${d.html}
      </div>
      <button class="runbtn" style="margin-top:10px" onclick="doSend(this)">Send report</button>`;
    markDone("step-draft");
  } catch (e) { toast("body-draft", e.message, false); }
}

async function doSend(btn) {
  btn.disabled = true;
  btn.textContent = "Sending…";
  try {
    const d = await post("/api/send");
    btn.textContent = "Sent";
    toast("body-draft", `Delivered — message ${d.message_id}`, true);
  } catch (e) {
    btn.disabled = false;
    btn.textContent = "Send report";
    toast("body-draft", e.message, false);
  }
}

pollNexus(); pollHealth();
setInterval(pollNexus, 5000);
setInterval(pollHealth, 5000);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  GitHub Code Review Squad — Dashboard")
    print("  Open http://localhost:8080 in your browser")
    print()
    print("  Needs the backend running in another terminal:")
    print("    python ../main.py")
    print("=" * 60 + "\n")

    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=False, log_level="info")
