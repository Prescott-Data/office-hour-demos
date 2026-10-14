// Builds index.html from content.mjs.  Usage: node build.mjs
// Open index.html in a browser: arrow keys or Space to move, O for the outline, F for fullscreen.
import { writeFileSync } from "node:fs";
import { slides as authored, TITLE, SUBTITLE } from "./content.mjs";

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

// ---------------------------------------------------------------- structure
// Every content slide belongs to a section through its `part`. The agenda and
// the dividers are derived from this table, so the deck stays as presented.
const SECTIONS = [
  { key: "anatomy", parts: ["PART 1 · ANATOMY"], name: "Anatomy", blurb: "The four planes, the peer mesh, and the controls around every agent" },
  { key: "platform", parts: ["PART 2 · PLATFORM"], name: "Platform", blurb: "What the workload asks for, the options, and where we run" },
  { key: "setup", parts: ["PART 3 · SETUP"], name: "Setup", blurb: "The order that works, and the configuration that matters" },
  { key: "running", parts: ["PART 4 · RUNNING IT"], name: "Running it", blurb: "Watching it, keeping it up, and what went wrong" },
  { key: "demo", parts: ["DEMO", "LIVE DEMO"], name: "Live demo", blurb: "One request through a production control room" },
  { key: "close", parts: ["CLOSE"], name: "Close", blurb: "A checklist to take back to your own platform" },
];
const sectionOf = (part) => SECTIONS.find((s) => s.parts.includes(part));

const deck = [];
const agenda = { id: "agenda", kind: "agenda", title: "Agenda" };
let current = null;
for (const s of authored) {
  const sec = sectionOf(s.part);
  if (sec && sec !== current) {
    current = sec;
    if (!deck.includes(agenda)) deck.push(agenda);
    deck.push({ id: sec.key, kind: "divider", section: sec, title: sec.name });
  }
  deck.push({ ...s, section: sec });
}
const numberOf = Object.fromEntries(deck.map((s, i) => [s.id, i + 1]));
for (const sec of SECTIONS) {
  const own = deck.filter((s) => s.section === sec);
  sec.first = numberOf[own[0].id];
  sec.last = numberOf[own[own.length - 1].id];
}

// ------------------------------------------------------------------ diagrams
const AH = `<defs><marker id="ah" markerUnits="userSpaceOnUse" markerWidth="16" markerHeight="16" refX="14" refY="8" orient="auto"><path d="M0,1 L14,8 L0,15z" class="ahf"/></marker></defs>`;
const box = (x, y, w, h, title, sub, cls = "n") =>
  `<rect class="${cls}" x="${x}" y="${y}" width="${w}" height="${h}" rx="12"/>` +
  `<text class="t b" x="${x + w / 2}" y="${y + (sub ? h / 2 - 4 : h / 2 + 8)}" text-anchor="middle">${esc(title)}</text>` +
  (sub ? `<text class="d s" x="${x + w / 2}" y="${y + h / 2 + 26}" text-anchor="middle">${esc(sub)}</text>` : "");
const arrow = (x1, y1, x2, y2, cls = "ln") =>
  `<line class="${cls}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" marker-end="url(#ah)"/>`;

const DIAGRAMS = {
  architecture: () => `
<svg viewBox="0 0 1200 452" class="dg">${AH}
  ${[
    ["CONTROL", 6, [["Gateway / API", "front door, auth"], ["Orchestrator", "workflow engine, DAG scheduling"]]],
    ["EXECUTION", 116, [["Agent services", "stateful, peer mesh"], ["Code runner", "sandboxed, separate process"], ["Stateless services", "APIs, rewards, comms"]]],
    ["DATA", 226, [["Redis", "state, leases, ledger"], ["Document store", "records, audit"], ["Event bus", "tasks, status"], ["Vector store", "retrieval"]]],
    ["MODEL", 336, [["Model gateway", "routing, circuit breaker"], ["Provider tiers", "cloud, then fallback, then local"]]],
  ].map(([label, y, items]) => {
    const n = items.length, gap = 16, x0 = 190, w = (810 - gap * (n - 1)) / n;
    return `<rect class="band" x="10" y="${y}" width="1000" height="104" rx="14"/>
      <text class="lbl" x="34" y="${y + 58}">${label}</text>` +
      items.map(([t, s], i) => box(x0 + i * (w + gap), y + 10, w, 84, t, s)).join("");
  }).join("")}
  <rect class="band ob" x="1030" y="6" width="160" height="434" rx="14"/>
  <text class="lbl" x="1110" y="170" text-anchor="middle" style="font-size:15px;letter-spacing:.06em">OBSERVABILITY</text>
  ${["metrics", "logs", "traces", "cost"].map((w, i) => `<text class="d s" x="1110" y="${210 + i * 32}" text-anchor="middle">${w}</text>`).join("")}
  ${arrow(600, 108, 600, 126)}${arrow(600, 218, 600, 236)}${arrow(400, 328, 400, 346)}
</svg>`,

  tools: () => `
<svg viewBox="0 0 1200 300" class="dg">${AH}
  ${box(10, 60, 250, 120, "Agent", "holds a connection handle")}
  ${arrow(260, 120, 320, 120)}
  ${box(330, 60, 250, 120, "Nexus broker", "resolves the credential")}
  ${arrow(580, 120, 640, 120)}
  <rect class="n gate" x="650" y="60" width="250" height="120" rx="12"/>
  <text class="t b" x="775" y="112" text-anchor="middle">Host allowlist</text>
  <text class="d s" x="775" y="146" text-anchor="middle">checked before attach</text>
  ${arrow(900, 120, 960, 120)}
  ${box(970, 60, 220, 120, "Provider API", "credential injected here")}
  ${box(330, 220, 250, 70, "Credential vault", "", "n vault")}
  <line class="ln" x1="455" y1="180" x2="455" y2="218" marker-end="url(#ah)"/>
  <line class="ln bad" x1="775" y1="180" x2="775" y2="250" marker-end="url(#ah)"/>
  <text class="bad s" x="790" y="252">blocked if the host isn't the provider's</text>
</svg>`,

  lease: () => `
<svg viewBox="0 0 1200 330" class="dg">${AH}
  ${box(20, 110, 240, 100, "pending", "")}
  ${box(480, 110, 260, 100, "in progress", "lease held, renewed")}
  ${box(940, 110, 240, 100, "completed", "")}
  ${arrow(260, 145, 480, 145)}
  <text class="d s" x="370" y="128" text-anchor="middle">claim (leased lock)</text>
  ${arrow(740, 145, 940, 145)}
  <text class="d s" x="840" y="128" text-anchor="middle">commit (holder only)</text>
  <path class="ln warn" d="M 560 210 C 500 300, 300 300, 200 212" fill="none" marker-end="url(#ah)"/>
  <text class="warn s" x="380" y="300" text-anchor="middle">lease expires: recovered, re-queued</text>
  <path class="ln" d="M 640 110 C 640 40, 700 40, 700 108" fill="none" marker-end="url(#ah)"/>
  <text class="d s" x="670" y="30" text-anchor="middle">heartbeat renews</text>
  <rect class="n stale" x="940" y="240" width="240" height="60" rx="12"/>
  <text class="bad s b" x="1060" y="277" text-anchor="middle">stale worker: refused</text>
  <line class="ln bad" x1="1060" y1="240" x2="1060" y2="214" marker-end="url(#ah)"/>
</svg>`,

  topology: () => `
<svg viewBox="0 0 1200 480" class="dg">${AH}
  <rect class="band" x="10" y="6" width="800" height="468" rx="16"/>
  <text class="lbl" x="34" y="38">KUBERNETES CLUSTER</text>
  <rect class="pool" x="30" y="52" width="760" height="92" rx="12"/>
  <text class="t b" x="50" y="84">system pool</text>
  <text class="d s" x="50" y="118">ingress, cert manager, monitoring, logging</text>
  <rect class="pool taint" x="30" y="156" width="760" height="140" rx="12"/>
  <text class="t b" x="50" y="188">agents pool <tspan class="d s">(tainted)</tspan></text>
  ${box(50, 204, 340, 80, "Stateful agent services", "StatefulSets + HPA")}
  ${box(408, 204, 364, 80, "Stateless services", "Deployments")}
  <rect class="pool taint" x="30" y="308" width="760" height="154" rx="12"/>
  <text class="t b" x="50" y="340">data pool <tspan class="d s">(tainted)</tspan></text>
  ${box(50, 358, 172, 84, "Redis", "")}
  ${box(236, 358, 172, 84, "Document store", "")}
  ${box(422, 358, 172, 84, "Event bus", "")}
  ${box(608, 358, 166, 84, "Vector store", "")}
  ${box(850, 20, 330, 92, "Model gateway", "own namespace, fallback tiers")}
  ${box(850, 128, 330, 92, "Sandbox sessions", "managed, outside the nodes")}
  ${box(850, 236, 330, 92, "Secrets store", "via workload identity")}
  ${box(850, 356, 330, 100, "Warm standby cluster", "another region", "n standby")}
  ${arrow(810, 226, 850, 66)}${arrow(810, 226, 850, 174)}${arrow(810, 226, 850, 282)}
</svg>`,

  mesh: () => {
    const X = [55, 245, 435, 625, 815, 1005], W = 140, Y = 88, H = 84;
    const names = [["New peer", "joining"], ["Seed node", "known address"], ["Peer", "analyst"], ["Peer", "writer"], ["Peer", "reviewer"], ["Peer", "silent"]];
    const cls = ["n standby", "n gate", "n", "n", "n", "n stale"];
    const cx = (i) => X[i] + W / 2;
    const arc = (a, b, h) => `<path class="gl" d="M ${cx(a)} ${Y} C ${cx(a)} ${Y - h}, ${cx(b)} ${Y - h}, ${cx(b)} ${Y}" fill="none"/>`;
    return `<svg viewBox="0 0 1200 262" class="dg">${AH}
  ${[[1, 2], [2, 3], [3, 4], [4, 5]].map(([a, b]) => `<line class="gl" x1="${X[a] + W}" y1="${Y + H / 2}" x2="${X[b]}" y2="${Y + H / 2}"/>`).join("")}
  ${arc(1, 3, 60)}${arc(2, 4, 60)}${arc(3, 5, 60)}
  ${names.map(([t, sub], i) => `<rect class="${cls[i]}" x="${X[i]}" y="${Y}" width="${W}" height="${H}" rx="12"/>
  <text class="t b" x="${cx(i)}" y="${Y + 36}" text-anchor="middle">${esc(t)}</text>
  <text class="${i === 5 ? "bad" : "d"} s" x="${cx(i)}" y="${Y + 64}" text-anchor="middle">${esc(sub)}</text>`).join("")}
  <line class="ln warn" x1="${X[0] + W}" y1="${Y + H / 2}" x2="${X[1] - 2}" y2="${Y + H / 2}" stroke-dasharray="7 6" marker-end="url(#ah)"/>
  <text class="warn s" x="${cx(0)}" y="${Y + H + 34}" text-anchor="middle">1. asks the seed to join</text>
  <text class="d s" x="${cx(2) + 60}" y="${Y + H + 34}" text-anchor="middle">2. gossip spreads the news: membership, health, capabilities</text>
  <text class="bad s" x="${cx(5)}" y="${Y + H + 34}" text-anchor="middle">3. peers mark it suspect</text>
  <text class="d s" x="600" y="246" text-anchor="middle">thin lines: gossip between peers. No central registry, no permanent coordinator.</text>
</svg>`;
  },

  demoflow: () => {
    // Each stage points at the slide that explained it, numbered in this deck.
    const ref = (id) => (id ? `slide ${numberOf[id]}` : "");
    const st = [["Request|", "architecture", "Redis DAG"], ["Orchestrate|", "orchestration", "worker loop"], ["Tool via|broker", "tools", "Nexus"],
      ["Tenant|memory", "memory", "tenant-keyed"], ["Human|approval", "security", "HITL queue"], ["Execute|", "", "idempotent step"], ["Model +|ledger", "resilience", "LLM fallback"]];
    const gap = 168, x0 = 70;
    return `<svg viewBox="0 0 1200 400" class="dg">${AH}
  ${st.map(([t, id, comp], i) => {
      const cx = x0 + i * gap, [a, b] = t.split("|");
      return (i < st.length - 1 ? `<line class="ln" x1="${cx + 34}" y1="60" x2="${cx + gap - 36}" y2="60" marker-end="url(#ah)"/>` : "") +
        `<circle class="node" cx="${cx}" cy="60" r="32"/><text class="nodenum" x="${cx}" y="71" text-anchor="middle">${i + 1}</text>` +
        `<text class="t b" x="${cx}" y="125" text-anchor="middle">${esc(a)}</text>` +
        (b ? `<text class="t b" x="${cx}" y="155" text-anchor="middle">${esc(b)}</text>` : "") +
        (id ? `<text class="d s" x="${cx}" y="185" text-anchor="middle">${ref(id)}</text>` : "") +
        `<text class="warn s b" x="${cx}" y="215" text-anchor="middle">${esc(comp)}</text>`;
    }).join("")}
  <rect class="n gate" x="70" y="245" width="1060" height="74" rx="12"/>
  <text class="t b" x="600" y="277" text-anchor="middle">Real JarvisCore: Mesh workers, Nexus, HITL queue, LLM client with fallback</text>
  <text class="d" x="600" y="306" text-anchor="middle" style="font-size:21px">Stubbed: only the third-party API and the model providers</text>
  <rect class="n warnbox" x="70" y="336" width="1060" height="52" rx="12"/>
  <text class="t" x="600" y="370" text-anchor="middle" style="font-size:22px">Then, simulated: a worker is lost, and the model provider hits capacity</text>
</svg>`;
  },
};

// ------------------------------------------------------------------ renderers
const codeLine = (l) => {
  const cls = l.startsWith("!") ? "c-a" : l.startsWith("#") ? "c-d" : "c-t";
  return `<span class="${cls}">${esc(/^[!#]/.test(l) ? l.slice(1) : l)}</span>`;
};
const note = (n) => (n ? `<p class="note">${esc(n)}</p>` : "");
const table = (s, pick) => `
  <table class="tbl"><thead><tr>${s.cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>
  <tbody>${s.rows.map((r) => `<tr class="${pick && r[0] === pick ? "pick" : ""}">${r.map((c, i) => `<td class="${i === 0 ? "k" : ""}">${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;

const R = {
  title: (s) => `
    <div class="ttl">
      <div class="kicker">${esc(s.part)}</div>
      <h1 class="mega">${esc(s.title)}</h1>
      <p class="sub">${esc(s.subtitle)}</p>
    </div>
    <div class="ttl-foot">${s.footer.map((f) => `<span>${esc(f)}</span>`).join("")}</div>`,

  agenda: () => `
    <ol class="agenda">${SECTIONS.map((sec, i) => `
      <li><a href="#${sec.key}" data-go="${sec.first}">
        <span class="anum">${String(i + 1).padStart(2, "0")}</span>
        <span class="aname">${esc(sec.name)}</span>
        <span class="ablurb">${esc(sec.blurb)}</span>
      </a></li>`).join("")}
    </ol>`,

  divider: (s) => {
    const i = SECTIONS.indexOf(s.section);
    const own = deck.filter((d) => d.section === s.section && d.kind !== "divider");
    return `
    <div class="dv-num">${String(i + 1).padStart(2, "0")}</div>
    <div class="dv-body">
      <h1 class="dv-title">${esc(s.section.name)}</h1>
      <p class="dv-blurb">${esc(s.section.blurb)}</p>
      <ul class="dv-list">${own.map((d) => `<li><span>${numberOf[d.id]}</span>${esc(d.title)}</li>`).join("")}</ul>
    </div>`;
  },

  takeaways: (s) => `
    <div class="grid g2">${s.items.map((it, i) => `<div class="card"><div class="num">${i + 1}</div><h3>${esc(it.h)}</h3><p>${esc(it.p)}</p></div>`).join("")}</div>
    ${note(s.note)}`,

  table: (s) => table(s) + note(s.note),
  table3: (s) => table(s) + note(s.note),

  matrix: (s) => table(s, "Kubernetes") + `<div class="decision"><b>Decision</b>${esc(s.decision)}</div>`,

  cards: (s) => `
    <div class="grid g${s.cols} ${s.items.length > s.cols ? "fill" : ""}">${s.items.map((it) => `<div class="card${it.hl ? " hl" : ""}"><h3>${esc(it.h)}</h3><p>${esc(it.p)}</p>${it.meta ? `<div class="meta">${it.meta.map((m) => `<span>${esc(m)}</span>`).join("")}</div>` : ""}</div>`).join("")}</div>
    ${note(s.note)}`,

  diagram: (s) => `
    <div class="dgwrap ${s.bullets ? "withside" : ""}">
      <div class="dgbox">${DIAGRAMS[s.diagram]()}</div>
      ${s.bullets ? `<div class="grid g3 bl">${s.bullets.map((b) => `<div class="card"><p>${esc(b)}</p></div>`).join("")}</div>` : ""}
    </div>
    ${s.defs ? `<div class="grid g4 defs">${s.defs.map((d) => `<div class="card"><h3>${esc(d.h)}</h3><p>${esc(d.p)}</p></div>`).join("")}</div>` : ""}
    ${note(s.caption)}`,

  steps: (s) => `
    <ol class="steps">${s.steps.map(([h, p], i) => `<li><span class="num">${i + 1}</span><div><h3>${esc(h)}</h3><p>${esc(p)}</p></div></li>`).join("")}</ol>
    ${note(s.note)}`,

  code3: (s) => `
    <div class="grid g3">${s.panels.map((p) => `<div class="pnl"><div class="plabel">${esc(p.label)}</div><pre class="code">${p.code.map(codeLine).join("\n")}</pre><p class="why">${esc(p.why)}</p></div>`).join("")}</div>`,

  twocol: (s) => `
    <div class="grid g2 tc">
      <div class="card"><h3>${esc(s.left.h)}</h3><ul class="bul">${s.left.items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul></div>
      <div class="card"><h3>${esc(s.right.h)}</h3><ul class="bul">${s.right.items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>${s.right.note ? `<p class="note in">${esc(s.right.note)}</p>` : ""}</div>
    </div>${note(s.note)}`,

  demo: (s) => `
    <p class="lead">What to watch for</p>
    <div class="grid g2 watch">${s.watch.map((w, i) => `<div class="card w"><div class="num">${i + 1}</div><p>${esc(w)}</p></div>`).join("")}</div>
    ${s.run ? `<div class="runit">${esc(s.run)}</div>` : ""}`,

  checklist: (s) => `
    <div class="grid g2 ck">${s.items.map(([h, p], i) => `<div class="ckrow"><span class="box" aria-hidden="true"></span><div><b>${i + 1}. ${esc(h)}</b><span>${esc(p)}</span></div></div>`).join("")}</div>`,

  resources: (s) => `
    <div class="grid g2 res">${s.groups.map((g) => `
      <div class="card"><h3>${esc(g.h)}</h3>
        <dl>${g.items.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>
      </div>`).join("")}
    </div>`,
};

const MONO = `<svg class="mono" viewBox="0 0 904.95 1024.47" aria-hidden="true"><rect x="187.82" y="819.58" width="204.89" height="204.89"/><path d="M580.21,27H85.05V846.58H272.87V231.89H580.21c113.16,0,204.9,91.74,204.9,204.9h0c0,113.16-91.74,204.89-204.9,204.89H477.76v204.9H580.21C806.53,846.58,990,663.11,990,436.79h0C990,210.47,806.53,27,580.21,27Z" transform="translate(-85.05 -27)"/></svg>`;

const slideHtml = (s, i) => {
  const n = i + 1, total = deck.length;
  const head = ["title", "divider"].includes(s.kind) ? "" : `
    <header class="sh"><span class="sec">${esc(s.section ? s.section.name : "Overview")}</span><span class="pg">${String(n).padStart(2, "0")} / ${total}</span></header>
    <h2 class="st">${esc(s.title)}</h2>`;
  const foot = s.kind === "title" ? "" : `
    <footer class="sf"><span>${esc(TITLE)}</span>${MONO}</footer>`;
  return `<section class="slide k-${s.kind}" id="${s.id}" data-n="${n}" aria-label="Slide ${n}: ${esc(s.title)}">
    ${head}<div class="body">${R[s.kind](s)}</div>${foot}
    <div class="prog" style="--p:${(n / total).toFixed(4)}"></div>
  </section>`;
};

const outline = SECTIONS.map((sec) => `
  <div class="og"><div class="ogh">${esc(sec.name)}</div>
  ${deck.filter((s) => s.section === sec).map((s) => `<button data-go="${numberOf[s.id]}"><span>${numberOf[s.id]}</span>${esc(s.title)}</button>`).join("")}</div>`).join("");

// --------------------------------------------------------------------- style
const CSS = `
:root{
  --paper:#f6f2ea; --card:#fffdf9; --ink:#1d1a16; --ink2:#4b453c; --mute:#857d70; --rule:#e2dacc;
  --accent:#a95d14; --accent-2:#d48a3a; --accent-soft:#f5e6d2; --red:#b2412c; --red-soft:#f6ddd5; --night:#1d1a16;
  --sans:'IBM Plex Sans',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
  --mono:'IBM Plex Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  color-scheme:light;
}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:#2a2622;color:var(--ink);font-family:var(--sans);-webkit-font-smoothing:antialiased;}
button{font:inherit;color:inherit}

/* viewer */
.viewer{height:100%;display:flex;flex-direction:column;}
.bar{display:flex;align-items:center;gap:8px;padding:10px 16px;padding-top:max(10px,env(safe-area-inset-top,0px));color:#e9e1d4;font-family:var(--mono);font-size:12px;flex-wrap:wrap;}
.bar .ttl-b{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;letter-spacing:.04em;color:#b9ad9b}
.bar .ttl-b b{color:#f3ebdf;font-weight:600}
.bar button{background:#3a342e;border:1px solid #4d453c;border-radius:6px;padding:6px 10px;cursor:pointer;color:#f3ebdf}
.bar button:hover{background:#4a4239}
.bar .count{min-width:64px;text-align:center;color:#f3ebdf}
.stagebox{flex:1;min-height:0;min-width:0;overflow:hidden;display:flex;align-items:center;justify-content:center;padding:0 16px 16px;padding-bottom:max(16px,env(safe-area-inset-bottom,0px));}
.sizer{position:relative;flex:none;overflow:hidden;border-radius:6px;box-shadow:0 24px 60px rgba(0,0,0,.45)}
.stage{position:absolute;top:0;left:0;width:1280px;height:720px;transform-origin:0 0;overflow:hidden;background:var(--paper);}

/* slide frame: a fixed 1280x720 canvas */
.slide{position:absolute;inset:0;display:none;flex-direction:column;padding:34px 64px 0;background:var(--paper);--k:1;}
.slide.active{display:flex}
.sh{display:flex;justify-content:space-between;align-items:center;font-family:var(--mono);font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:var(--mute);padding-bottom:14px;border-bottom:1px solid var(--rule);}
.sh .sec{color:var(--accent);font-weight:600}
.st{font-size:calc(38px * var(--k));line-height:1.12;font-weight:600;letter-spacing:-.015em;margin:22px 0 22px;text-wrap:balance;max-width:1080px}
.body{flex:1;min-height:0;display:flex;flex-direction:column;}
.sf{height:52px;flex:none;display:flex;align-items:center;justify-content:space-between;border-top:1px solid var(--rule);font-family:var(--mono);font-size:12px;letter-spacing:.08em;color:var(--mute);text-transform:uppercase}
.mono{height:20px;width:auto;fill:var(--ink)}
.prog{position:absolute;left:0;bottom:0;height:4px;width:calc(var(--p) * 100%);background:var(--accent)}

h3{margin:0 0 6px;font-size:calc(21px * var(--k));font-weight:600;color:var(--ink);letter-spacing:-.005em}
p{margin:0}
.grid{display:grid;gap:calc(18px * var(--k))}
.grid>*{min-width:0}
.g2{grid-template-columns:1fr 1fr}.g3{grid-template-columns:repeat(3,1fr)}.g4{grid-template-columns:repeat(4,1fr)}
.card{background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:calc(20px * var(--k)) calc(22px * var(--k))}
.card p,.card li{font-size:calc(19px * var(--k));line-height:1.45;color:var(--ink2)}
.card.hl{border-color:var(--accent);box-shadow:inset 4px 0 0 var(--accent)}
.num{display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:50%;background:var(--accent);color:#fff;font-weight:600;font-size:16px;margin-bottom:10px;font-family:var(--mono)}
.note{margin-top:auto;padding:14px 0 18px;font-size:calc(18px * var(--k));line-height:1.45;color:var(--ink2);max-width:1080px}
.note::before{content:"";display:inline-block;width:22px;height:2px;background:var(--accent);vertical-align:middle;margin-right:12px}
.note.in{margin-top:14px;padding:0}
.lead{font-family:var(--mono);font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:var(--mute);margin-bottom:14px}

/* title */
.k-title{padding:0;background:var(--night);color:#f5ede1}
.k-title .body{padding:0 80px;justify-content:center;position:relative}
.k-title .body::before{content:"";position:absolute;right:-120px;top:-160px;width:620px;height:620px;border-radius:50%;border:2px solid #3b342c;box-shadow:0 0 0 60px #221e1a,0 0 0 61px #3b342c}
.ttl{position:relative;max-width:900px}
.kicker{font-family:var(--mono);font-size:15px;letter-spacing:.2em;color:var(--accent-2);margin-bottom:26px}
.mega{font-size:86px;line-height:1;font-weight:600;letter-spacing:-.03em;margin:0 0 24px;text-wrap:balance}
.sub{font-size:30px;line-height:1.3;color:#d9cdbb;font-weight:300;max-width:760px}
.ttl-foot{position:absolute;left:80px;right:80px;bottom:56px;display:flex;justify-content:space-between;font-family:var(--mono);font-size:15px;letter-spacing:.06em;color:#b9ad9b;border-top:1px solid #3b342c;padding-top:20px}
.k-title .prog{background:var(--accent-2)}

/* agenda */
.agenda{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;border-top:1px solid var(--rule)}
.agenda a{display:grid;grid-template-columns:72px 240px 1fr;align-items:baseline;gap:20px;padding:17px 6px;border-bottom:1px solid var(--rule);text-decoration:none;color:inherit}
.agenda a:hover{background:var(--card)}
.anum{font-family:var(--mono);font-size:18px;color:var(--accent);font-weight:600}
.aname{font-size:27px;font-weight:600;letter-spacing:-.01em}
.ablurb{font-size:19px;color:var(--ink2)}
.arange{font-family:var(--mono);font-size:14px;color:var(--mute);text-align:right}

/* section divider */
.k-divider{background:var(--night);color:#f5ede1;padding-top:0}
.k-divider .body{flex-direction:row;align-items:center;gap:64px;padding:0 16px}
.k-divider .sf{border-top-color:#3b342c;color:#9c907f}.k-divider .mono{fill:#f5ede1}
.dv-num{font-family:var(--mono);font-size:200px;line-height:1;font-weight:600;color:var(--accent-2);letter-spacing:-.04em}
.dv-title{font-size:64px;font-weight:600;letter-spacing:-.025em;margin:0 0 14px}
.dv-blurb{font-size:24px;color:#d9cdbb;font-weight:300;margin-bottom:28px;max-width:640px}
.dv-list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:9px;font-size:19px;color:#e9dfd0}
.dv-list span{display:inline-block;width:44px;font-family:var(--mono);font-size:14px;color:#9c907f}

/* tables */
.tbl{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--rule);border-radius:10px;overflow:hidden}
.tbl th{text-align:left;font-family:var(--mono);font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--mute);padding:calc(12px * var(--k)) 20px;border-bottom:1px solid var(--rule);background:#f0ebe1;font-weight:500}
.tbl td{padding:calc(13px * var(--k)) 20px;border-bottom:1px solid var(--rule);font-size:calc(19px * var(--k));line-height:1.4;vertical-align:top;color:var(--ink2)}
.tbl tr:last-child td{border-bottom:0}
.tbl td.k{color:var(--ink);font-weight:600;width:32%}
.tbl tr.pick td{background:var(--accent-soft)}
.tbl tr.pick td.k{box-shadow:inset 4px 0 0 var(--accent)}
.decision{margin-top:18px;display:flex;gap:16px;align-items:baseline;background:var(--card);border:1px solid var(--accent);border-radius:10px;padding:16px 22px;font-size:calc(19px * var(--k));line-height:1.45;color:var(--ink2)}
.decision b{font-family:var(--mono);font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);flex:none}

/* lists, steps, code */
ul.bul{margin:12px 0 0;padding:0;list-style:none;display:flex;flex-direction:column;gap:calc(12px * var(--k))}
ul.bul li{position:relative;padding-left:22px}
ul.bul li::before{content:"";position:absolute;left:2px;top:.62em;width:8px;height:8px;border-radius:2px;background:var(--accent)}
.steps{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:1fr 1fr;gap:16px 22px}
.steps li{display:flex;gap:16px;align-items:flex-start;background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:18px 20px}
.steps .num{margin:0;flex:none}
.steps p{font-size:calc(18px * var(--k));color:var(--ink2);line-height:1.4}
.plabel{font-family:var(--mono);font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);margin-bottom:10px;font-weight:600}
.code{background:#211d19;border-radius:10px;padding:18px 20px;font-family:var(--mono);font-size:calc(15px * var(--k));line-height:1.55;margin:0;white-space:pre;overflow:hidden;color:#e9dfd0}
.code .c-a{color:#f0a95a;font-weight:600}.code .c-d{color:#8f8474}
.why{margin-top:12px;font-size:calc(17px * var(--k));line-height:1.45;color:var(--ink2)}
.meta{margin-top:14px;display:flex;flex-direction:column;gap:4px;font-family:var(--mono);font-size:13px;color:var(--mute)}
.meta span:first-child{color:var(--accent)}

/* diagrams */
.dgwrap{display:flex;flex:1;min-height:0;gap:20px}
.dgbox{flex:1;min-width:0;min-height:0}
.dgwrap.withside{flex-direction:column;justify-content:center}.withside .dgbox{flex:none}
svg.dg{width:100%;height:100%;display:block}.withside svg.dg{height:auto;max-height:260px}
.bl .card p{font-size:calc(18px * var(--k))}
.defs{margin-top:14px}.defs .card{padding:16px 18px}.defs h3{font-size:19px}.defs .card p{font-size:16px;line-height:1.4}
.grid.fill{flex:1;grid-auto-rows:1fr;margin-bottom:12px}.fill .card{display:flex;flex-direction:column;justify-content:center}
.dg .band{fill:none;stroke:var(--rule);stroke-width:2}.dg .band.ob{fill:#efe9de}
.dg .lbl{fill:var(--mute);font-family:var(--mono);font-size:20px;letter-spacing:.12em;font-weight:600}
.dg .gl{stroke:#cbbfac;stroke-width:2;fill:none}
.dg .n{fill:var(--card);stroke:#d6cdbd;stroke-width:2}
.dg .gate{stroke:var(--accent);stroke-width:3;fill:#fbf1e4}
.dg .vault,.dg .standby{stroke-dasharray:8 6}
.dg .warnbox{stroke:var(--accent);stroke-dasharray:8 6;fill:var(--card)}
.dg .stale{stroke:var(--red);stroke-dasharray:6 5;fill:#fdf3f0}
.dg .pool{fill:#f1ece2;stroke:var(--rule);stroke-width:2}.dg .pool.taint{stroke:#d9c3a3}
.dg text{font-family:var(--sans)}
.dg .t{fill:var(--ink);font-size:24px}.dg .b{font-weight:600}.dg .d{fill:var(--ink2)}.dg .s{font-size:18px}
.dg .ln{stroke:#8f8577;stroke-width:3;fill:none}.dg .ln.bad{stroke:var(--red);stroke-dasharray:7 6}.dg .ln.warn{stroke:var(--accent)}
.dg .ahf{fill:#8f8577}.dg .bad{fill:var(--red)}.dg text.warn{fill:var(--accent)}
.dg .node{fill:var(--accent)}.dg .nodenum{fill:#fff;font-family:var(--mono);font-size:24px;font-weight:600}

/* demo, checklist, resources */
.watch .w{display:flex;align-items:center;gap:16px;padding:16px 20px}.watch .num{margin:0;flex:none}.watch p{font-size:20px;color:var(--ink)}
.runit{margin-top:auto;margin-bottom:18px;align-self:flex-start;font-family:var(--mono);font-size:16px;background:var(--night);color:#f3ebdf;border-radius:8px;padding:12px 18px}
.ck{gap:4px 40px}
.ckrow{display:flex;gap:16px;align-items:flex-start;border-bottom:1px solid var(--rule);padding:12px 0}
.ckrow .box{flex:none;width:22px;height:22px;border:2px solid var(--accent);border-radius:5px;margin-top:3px}
.ckrow b{display:block;font-size:19px;color:var(--ink);font-weight:600}
.ckrow span:not(.box){display:block;font-size:17px;color:var(--ink2);line-height:1.4}
.res dl{margin:14px 0 0;display:grid;grid-template-columns:1fr;gap:4px}
.res dt{font-family:var(--mono);font-size:16px;color:var(--accent);font-weight:600;margin-top:12px;word-break:break-all}
.res dd{margin:0;font-size:18px;color:var(--ink2);line-height:1.4}

/* outline */
.outline[hidden]{display:none}
.outline{position:fixed;inset:0;background:rgba(20,17,14,.72);display:flex;justify-content:center;align-items:flex-start;padding:48px 16px;overflow:auto;z-index:5}
.outline .panel{background:var(--paper);border-radius:10px;max-width:980px;width:100%;padding:28px 32px;display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:22px 28px}
.og{display:flex;flex-direction:column;gap:2px;min-width:0}
.ogh{font-family:var(--mono);font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:600;padding-bottom:6px;border-bottom:1px solid var(--rule);margin-bottom:4px}
.og button{display:flex;gap:10px;text-align:left;background:none;border:0;padding:6px 4px;border-radius:5px;cursor:pointer;font-size:15px;color:var(--ink2)}
.og button span{font-family:var(--mono);font-size:12px;color:var(--mute);width:22px;flex:none;padding-top:2px}
.og button:hover,.og button.on{background:var(--accent-soft);color:var(--ink)}

/* print and PDF: one slide per page */
@page{size:1280px 720px;margin:0}
@media print{
  html,body{height:auto;background:var(--paper)}
  .bar,.outline{display:none!important}
  .stagebox{display:block;padding:0}
  .sizer{width:auto!important;height:auto!important;overflow:visible;box-shadow:none;border-radius:0}
  .stage{position:static;transform:none!important;width:auto;height:auto;overflow:visible;background:none}
  .slide{position:relative;display:flex!important;width:1280px;height:720px;break-after:page;page-break-after:always;overflow:hidden}
  *{-webkit-print-color-adjust:exact;print-color-adjust:exact}
}
`;

const JS = `
const slides=[...document.querySelectorAll('.slide')], N=slides.length, stage=document.getElementById('stage');
let idx=0;
function fitText(sl){
  // Shrink a dense slide's type rather than clip it.
  const body=sl.querySelector('.body'); let k=1; sl.style.setProperty('--k',1);
  const over=()=>body.scrollHeight>body.clientHeight+1||[...sl.querySelectorAll('.code')].some(c=>c.scrollHeight>c.clientHeight+1||c.scrollWidth>c.clientWidth+1);
  while(over()&&k>0.6){k-=0.03;sl.style.setProperty('--k',k.toFixed(2));}
}
function fitAll(){slides.forEach(s=>{const was=s.classList.contains('active');s.classList.add('active');fitText(s);if(!was)s.classList.remove('active');});}
function scale(){
  const box=document.querySelector('.stagebox'), r=box.getBoundingClientRect();
  const s=Math.min((r.width-32)/1280,(r.height-16)/720);
  const k=Math.max(0.1,s), sizer=stage.parentElement;
  stage.style.transform='scale('+k+')';
  sizer.style.width=(1280*k)+'px'; sizer.style.height=(720*k)+'px';
}
function show(i,push){
  idx=Math.max(0,Math.min(N-1,i));
  slides.forEach((s,j)=>s.classList.toggle('active',j===idx));
  document.getElementById('count').textContent=(idx+1)+' / '+N;
  document.querySelectorAll('.og button').forEach(b=>b.classList.toggle('on',+b.dataset.go===idx+1));
  if(push!==false){try{history.replaceState(null,'','#'+slides[idx].id);}catch(e){}}
}
function outline(open){document.getElementById('outline').hidden=!open;}
document.addEventListener('click',e=>{
  const g=e.target.closest('[data-go]'); if(g){e.preventDefault();show(+g.dataset.go-1);outline(false);return;}
  if(e.target.id==='outline')outline(false);
});
document.getElementById('prev').onclick=()=>show(idx-1);
document.getElementById('next').onclick=()=>show(idx+1);
document.getElementById('olbtn').onclick=()=>outline(document.getElementById('outline').hidden);
document.getElementById('fsbtn').onclick=()=>{const d=document.documentElement;try{document.fullscreenElement?document.exitFullscreen():d.requestFullscreen().catch(()=>{});}catch(e){}};
window.addEventListener('keydown',e=>{
  if(e.target.closest&&e.target.closest('input,textarea'))return;
  const k=e.key;
  if(k==='ArrowRight'||k==='PageDown'||k===' '){e.preventDefault();show(idx+1);}
  else if(k==='ArrowLeft'||k==='PageUp'){e.preventDefault();show(idx-1);}
  else if(k==='Home')show(0); else if(k==='End')show(N-1);
  else if(k==='o'||k==='O')outline(document.getElementById('outline').hidden);
  else if(k==='Escape')outline(false);
  else if(k==='f'||k==='F')document.getElementById('fsbtn').click();
});
let t; window.addEventListener('resize',()=>{clearTimeout(t);t=setTimeout(scale,80);});
const start=slides.findIndex(s=>'#'+s.id===location.hash);
const ready=()=>{fitAll();scale();show(start>0?start:0,false);};
(document.fonts&&document.fonts.ready?document.fonts.ready:Promise.resolve()).then(ready);
ready();
`;

const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>${esc(TITLE)}</title>
<meta name="description" content="${esc(SUBTITLE)}. Developer Office Hours slides.">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap">
<style>${CSS}</style></head>
<body>
<div class="viewer">
  <div class="bar">
    <div class="ttl-b"><b>${esc(TITLE)}</b> · Developer Office Hours</div>
    <button id="olbtn" title="Outline (O)">Outline</button>
    <button id="prev" aria-label="Previous slide">←</button><span class="count" id="count">1 / ${deck.length}</span><button id="next" aria-label="Next slide">→</button>
    <button id="fsbtn" title="Fullscreen (F)">⛶</button>
  </div>
  <div class="stagebox"><div class="sizer"><div class="stage" id="stage">
${deck.map(slideHtml).join("\n")}
  </div></div></div>
</div>
<div class="outline" id="outline" hidden><div class="panel">${outline}</div></div>
<script>${JS}</script>
</body></html>
`;
writeFileSync(new URL("./index.html", import.meta.url), html);
console.log(`wrote index.html: ${deck.length} slides (${authored.length} as presented, plus agenda and ${SECTIONS.length} section dividers)`);
