// Builds index.html from content.mjs.  Usage: node build.mjs
// Open index.html in a browser: arrow keys or Space to move, O for the outline, F for fullscreen.
import { writeFileSync } from "node:fs";
import { slides as authored, TITLE, SUBTITLE, SECTIONS } from "./content.mjs";

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
// **bold** and `code` inside slide text.
const md = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<code>$1</code>");

// ---------------------------------------------------------------- structure
// Every content slide belongs to a section through its `part`. The agenda and
// the dividers are derived from SECTIONS, so the deck stays as presented.
for (const sec of SECTIONS) sec.key = sec.part.toLowerCase().replace(/[^a-z]+/g, "-");
const sectionOf = (part) => SECTIONS.find((s) => s.part === part);

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

// ------------------------------------------------------------------ renderers
const ticks = (list) => `<ul class="ticks">${list.map(([m, cls, text]) => `<li><span class="m ${cls}">${esc(m)}</span><span>${md(text)}</span></li>`).join("")}</ul>`;
const card = (c) => `<div class="card${c.brand ? " brand" : ""}">
    ${c.tag ? `<span class="tag">${esc(c.tag)}</span>` : ""}
    ${c.ticks ? ticks(c.ticks) : ""}
    ${c.pre ? `<pre class="code">${c.pre}</pre>` : ""}
    ${(c.ps || []).map((p) => `<p>${md(p)}</p>`).join("")}
  </div>`;
const lede = (t) => (t ? `<p class="note">${md(t)}</p>` : "");

const R = {
  title: (s) => `
    <div class="ttl">
      <div class="kicker">${esc(s.part)}</div>
      <h1 class="mega">${esc(s.title)}</h1>
      <p class="sub">${md(s.lede)}</p>
    </div>
    <div class="ttl-foot">${s.footer.map((f) => `<span>${esc(f)}</span>`).join("")}</div>`,

  agenda: () => `
    <ol class="agenda">${SECTIONS.map((sec, i) => `
      <li><a href="#${sec.key}" data-go="${numberOf[sec.key]}">
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

  twocards: (s) => `
    <div class="grid g2">${card(s.left)}${card(s.right)}</div>
    ${s.pre ? `<pre class="code wide">${s.pre}</pre>` : ""}
    ${lede(s.lede)}`,

  figure: (s) => `<div class="figbox">${s.svg}</div>${lede(s.caption)}`,

  statement: (s) => `
    <pre class="code wide">${s.pre}</pre>
    <p class="lead-p">${md(s.lede)}</p>
    <div class="stats">${s.stats.map(([v, l]) => `<div class="stat"><span class="v">${esc(v)}</span><span class="l">${esc(l)}</span></div>`).join("")}</div>`,

  table: (s) => `
    <table class="tbl"><thead><tr>${s.cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>
    <tbody>${s.rows.map((r) => `<tr>${r.map((c, i) => `<td class="${i === 0 ? "k" : ""}">${md(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>
    ${lede(s.lede)}`,

  code: (s) => `
    <pre class="code wide">${s.pre}</pre>
    <p class="lead-p">${md(s.lede)}</p>
    ${s.card ? `<div class="grid g1">${card(s.card)}</div>` : ""}`,

  close: (s) => `
    <p class="quote">${esc(s.quote)}</p>
    <div class="stats links">${s.links.map(([l, v]) => `<div class="stat"><span class="l">${esc(l)}</span><span class="v mono-v">${esc(v)}</span></div>`).join("")}</div>`,
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
  --paper:#f3f5f9; --card:#ffffff; --ink:#0b1322; --ink2:#2f3d57; --mute:#5f6f8a; --rule:#dae3f2;
  --accent:#1758f5; --accent-2:#6e9bff; --accent-soft:#e6eefe; --red:#c4272c; --red-soft:#fbe3e3; --night:#0b1322; --good:#0a8f54;
  --sans:'IBM Plex Sans',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
  --mono:'IBM Plex Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  color-scheme:light;
}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:#141c2b;color:var(--ink);font-family:var(--sans);-webkit-font-smoothing:antialiased;}
button{font:inherit;color:inherit}

/* viewer */
.viewer{height:100%;display:flex;flex-direction:column;}
.bar{display:flex;align-items:center;gap:8px;padding:10px 16px;padding-top:max(10px,env(safe-area-inset-top,0px));color:#dfe6f2;font-family:var(--mono);font-size:12px;flex-wrap:wrap;}
.bar .ttl-b{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;letter-spacing:.04em;color:#9fb0cc}
.bar .ttl-b b{color:#eef3fb;font-weight:600}
.bar button{background:#1f2a3d;border:1px solid #33425c;border-radius:6px;padding:6px 10px;cursor:pointer;color:#eef3fb}
.bar button:hover{background:#2a3850}
.bar .count{min-width:64px;text-align:center;color:#eef3fb}
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
.k-title{padding:0;background:var(--night);color:#eef3fb}
.k-title .body{padding:0 80px;justify-content:center;position:relative}
.k-title .body::before{content:"";position:absolute;right:-120px;top:-160px;width:620px;height:620px;border-radius:50%;border:2px solid #24324a;box-shadow:0 0 0 60px #101a2b,0 0 0 61px #24324a}
.ttl{position:relative;max-width:900px}
.kicker{font-family:var(--mono);font-size:15px;letter-spacing:.2em;color:var(--accent-2);margin-bottom:26px}
.mega{font-size:86px;line-height:1;font-weight:600;letter-spacing:-.03em;margin:0 0 24px;text-wrap:balance}
.sub{font-size:30px;line-height:1.3;color:#c3cfe3;font-weight:300;max-width:760px}
.ttl-foot{position:absolute;left:80px;right:80px;bottom:56px;display:flex;justify-content:space-between;font-family:var(--mono);font-size:15px;letter-spacing:.06em;color:#9fb0cc;border-top:1px solid #24324a;padding-top:20px}
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
.k-divider{background:var(--night);color:#eef3fb;padding-top:0}
.k-divider .body{flex-direction:row;align-items:center;gap:64px;padding:0 16px}
.k-divider .sf{border-top-color:#24324a;color:#8496b4}.k-divider .mono{fill:#eef3fb}
.dv-num{font-family:var(--mono);font-size:200px;line-height:1;font-weight:600;color:var(--accent-2);letter-spacing:-.04em}
.dv-title{font-size:64px;font-weight:600;letter-spacing:-.025em;margin:0 0 14px}
.dv-blurb{font-size:24px;color:#c3cfe3;font-weight:300;margin-bottom:28px;max-width:640px}
.dv-list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:9px;font-size:19px;color:#dbe4f3}
.dv-list span{display:inline-block;width:44px;font-family:var(--mono);font-size:14px;color:#8496b4}

/* tables */
.tbl{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--rule);border-radius:10px;overflow:hidden}
.tbl th{text-align:left;font-family:var(--mono);font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--mute);padding:calc(12px * var(--k)) 20px;border-bottom:1px solid var(--rule);background:#eaf0f9;font-weight:500}
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
.code{background:#0d1729;border-radius:10px;padding:18px 20px;font-family:var(--mono);font-size:calc(15px * var(--k));line-height:1.55;margin:0;white-space:pre;overflow:hidden;color:#dbe4f3}
.code .c-a{color:#5fd8ff;font-weight:600}.code .c-d{color:#7f93b5}
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
.runit{margin-top:auto;margin-bottom:18px;align-self:flex-start;font-family:var(--mono);font-size:16px;background:var(--night);color:#eef3fb;border-radius:8px;padding:12px 18px}
.ck{gap:4px 40px}
.ckrow{display:flex;gap:16px;align-items:flex-start;border-bottom:1px solid var(--rule);padding:12px 0}
.ckrow .box{flex:none;width:22px;height:22px;border:2px solid var(--accent);border-radius:5px;margin-top:3px}
.ckrow b{display:block;font-size:19px;color:var(--ink);font-weight:600}
.ckrow span:not(.box){display:block;font-size:17px;color:var(--ink2);line-height:1.4}
.res dl{margin:14px 0 0;display:grid;grid-template-columns:1fr;gap:4px}
.res dt{font-family:var(--mono);font-size:16px;color:var(--accent);font-weight:600;margin-top:12px;word-break:break-all}
.res dd{margin:0;font-size:18px;color:var(--ink2);line-height:1.4}

/* this deck's blocks */
code{font-family:var(--mono);font-size:.9em;background:var(--accent-soft);color:var(--ink);padding:1px 6px;border-radius:4px}
pre code,.code code{background:none;padding:0}
.code.wide{font-size:calc(17px * var(--k));padding:20px 24px;white-space:pre}
.code .c{color:#7f93b5}.code .k{color:#5fd8ff}.code .s{color:#9fe0a8}.code .n{color:#ffc98b}
.code .hl{background:rgba(90,144,255,.22);border-radius:3px;padding:0 3px}
.card .code{margin:12px 0;font-size:calc(16px * var(--k))}
.card.brand{border-color:var(--accent);background:var(--accent-soft)}
.card p+p{margin-top:12px}
.card strong,.note strong,.lead-p strong,.tbl strong{color:var(--ink);font-weight:600}
.tag{display:block;font-family:var(--mono);font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--mute);margin-bottom:12px;font-weight:500}
ul.ticks{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:calc(12px * var(--k))}
ul.ticks li{display:grid;grid-template-columns:52px 1fr;gap:10px;font-size:calc(19px * var(--k));line-height:1.45;color:var(--ink2)}
ul.ticks .m{font-family:var(--mono);font-size:.85em;color:var(--accent);font-weight:600;padding-top:.12em}
ul.ticks .m.bad{color:var(--red)}ul.ticks .m.good{color:var(--good)}
.g1{grid-template-columns:1fr;margin-top:16px}
.lead-p{margin-top:18px;font-size:calc(21px * var(--k));line-height:1.5;color:var(--ink2);max-width:1040px}
.stats{display:flex;gap:22px;margin-top:auto;margin-bottom:22px}
.stat{flex:1;border-left:3px solid var(--accent);padding-left:16px;display:flex;flex-direction:column;gap:4px}
.stat .v{font-size:44px;font-weight:600;letter-spacing:-.03em;color:var(--ink);font-variant-numeric:tabular-nums}
.stat .l{font-family:var(--mono);font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--mute)}
.stat .v.mono-v{font-family:var(--mono);font-size:19px;font-weight:500;letter-spacing:0;word-break:break-all}
.stats.links{flex-direction:column;gap:0;border-top:1px solid var(--rule)}
.links .stat{flex-direction:row;align-items:baseline;gap:24px;border-left:0;padding:16px 0;border-bottom:1px solid var(--rule)}
.links .stat .l{width:160px;flex:none}
.stat .v.mono-v{word-break:normal}
.quote{font-size:56px;font-weight:600;letter-spacing:-.025em;line-height:1.1;color:var(--accent);margin:24px 0 0;max-width:900px}
.figbox{flex:1;min-height:0;display:flex;align-items:center;justify-content:center}
svg.fig{width:100%;height:100%;max-height:440px}
.fig .s-panel{fill:var(--card);stroke:#bccde8}.fig .s-agent{fill:var(--accent-soft);stroke:var(--accent)}
.fig .s-nexus{fill:#e8eefa;stroke:var(--accent)}.fig .s-ext{fill:var(--paper);stroke:#bccde8}
.fig .s-flow{stroke:var(--accent);fill:none}.fig .s-line{stroke:#bccde8;fill:none}.fig .s-bound{stroke:var(--red);fill:none}
.fig .s-t{fill:var(--ink);font-family:var(--sans);font-size:13px;font-weight:600}
.fig .s-s{fill:var(--mute);font-family:var(--mono);font-size:9px;letter-spacing:.03em}
.fig .s-b{fill:var(--red);font-family:var(--mono);font-size:9.5px;letter-spacing:.07em}.fig .s-a{fill:var(--accent)}
.k-title .mega{font-size:72px}

/* outline */
.outline[hidden]{display:none}
.outline{position:fixed;inset:0;background:rgba(8,14,26,.72);display:flex;justify-content:center;align-items:flex-start;padding:48px 16px;overflow:auto;z-index:5}
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
