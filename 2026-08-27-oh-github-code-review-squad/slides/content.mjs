// The deck as presented on 27 August 2026. Rebuild with: node build.mjs
// The agenda and section dividers are generated from each slide's `part`.
// Text fields accept **bold** and `code`; `pre` fields are pre-highlighted HTML.

export const TITLE = "Building a GitHub Code Review Squad";
export const SUBTITLE = "Three agents that write code, review it, remember what they found, and report it, built live";

export const SECTIONS = [
  { part: "THE PROBLEM", name: "The problem", blurb: "Where agents break on the way to production, and what we build to fix it" },
  { part: "THE BASICS", name: "JarvisCore basics", blurb: "Two profiles, one mesh, and the choice between a prompt and code" },
  { part: "THE BUILD", name: "The build", blurb: "What you need, how the credentials stay out of reach, and the four steps" },
  { part: "CLOSE", name: "Close", blurb: "Where the code lives, and where to keep asking" },
];

export const slides = [
  {
    id: "title", kind: "title", part: "DEVELOPER OFFICE HOURS",
    title: TITLE,
    lede: "Three agents that write code, push it, review it, remember what they found, and email the report. Built live in one hour, from an empty file.",
    footer: ["Ruth Mutua & Abdullahi · Prescott Data", "JarvisCore 1.3.0 · 27 August 2026"],
  },

  // ------------------------------------------------------------ THE PROBLEM
  {
    id: "why", kind: "twocards", part: "THE PROBLEM",
    title: "Everyone's agent works in the notebook and dies on the way out.",
    left: { tag: "Where they break", ticks: [
      ["01", "bad", "**Credentials.** The token ends up in the prompt, the log, or the repo."],
      ["02", "bad", "**Memory.** Every run is the first run. Nothing carries over."],
      ["03", "bad", "**Reaching the real world.** The demo reads a file; production needs GitHub, Gmail, Slack, Jira."],
    ] },
    right: { tag: "What we'll show", brand: true, ps: [
      "All three, fixed in front of you, in four steps you can run yourself afterwards, and every call the agents make printed as it happens, so you can see exactly where the work is going.",
      "**If your agent is broken in one of those three ways, that's the session. Bring it to the chat.**",
    ] },
  },
  {
    id: "build", kind: "figure", part: "THE PROBLEM", title: "Three agents, one repo, two services.",
    caption: "Every external call goes through the Nexus gateway. Nothing above the red line holds a token.",
    svg: `
<svg viewBox="0 0 720 300" class="fig" role="img" aria-label="CodeSmith, Inspector and Reporter route every external call through the Nexus Gateway, which holds the credentials and reaches GitHub and Gmail.">
  <defs><marker id="a1" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" class="s-a"/></marker></defs>
  <rect x="16" y="10" width="688" height="104" rx="10" class="s-panel" stroke-width="1" stroke-dasharray="4 4"/>
  <text x="32" y="31" class="s-s">JARVISCORE MESH</text>
  <rect x="48" y="44" width="168" height="52" rx="8" class="s-agent" stroke-width="1.4"/>
  <text x="132" y="67" class="s-t" text-anchor="middle">CodeSmith</text>
  <text x="132" y="84" class="s-s" text-anchor="middle">WRITES · PUSHES · OPENS PR</text>
  <rect x="276" y="44" width="168" height="52" rx="8" class="s-agent" stroke-width="1.4"/>
  <text x="360" y="67" class="s-t" text-anchor="middle">Inspector</text>
  <text x="360" y="84" class="s-s" text-anchor="middle">REVIEWS · REMEMBERS</text>
  <rect x="504" y="44" width="168" height="52" rx="8" class="s-agent" stroke-width="1.4"/>
  <text x="588" y="67" class="s-t" text-anchor="middle">Reporter</text>
  <text x="588" y="84" class="s-s" text-anchor="middle">RECALLS · SENDS</text>
  <path d="M216 70 L270 70" class="s-flow" stroke-width="1.4" marker-end="url(#a1)"/>
  <path d="M444 70 L498 70" class="s-flow" stroke-width="1.4" marker-end="url(#a1)"/>
  <path d="M360 96 L360 110 L588 110 L588 96" class="s-line" stroke-width="1.2" stroke-dasharray="3 3"/>
  <text x="474" y="107" class="s-s" text-anchor="middle">MEMORY</text>
  <path d="M132 114 L132 154" class="s-flow" stroke-width="1.4" marker-end="url(#a1)"/>
  <path d="M360 114 L360 154" class="s-flow" stroke-width="1.4" marker-end="url(#a1)"/>
  <path d="M588 114 L588 154" class="s-flow" stroke-width="1.4" marker-end="url(#a1)"/>
  <text x="142" y="128" class="s-s">nexus_call()</text>
  <text x="370" y="128" class="s-s">nexus_call()</text>
  <text x="598" y="128" class="s-s">nexus_call()</text>
  <path d="M16 148 L704 148" class="s-bound" stroke-width="1.2" stroke-dasharray="6 4"/>
  <text x="246" y="143" class="s-b" text-anchor="middle">CREDENTIAL BOUNDARY</text>
  <text x="474" y="143" class="s-b" text-anchor="middle">NO TOKENS ABOVE THIS LINE</text>
  <rect x="48" y="160" width="624" height="54" rx="9" class="s-nexus" stroke-width="1.6"/>
  <text x="360" y="183" class="s-t" text-anchor="middle">Nexus Gateway</text>
  <text x="360" y="201" class="s-s" text-anchor="middle">PROVIDER REGISTRY · OAUTH CONSENT · TOKEN VAULT</text>
  <path d="M216 214 L216 252" class="s-flow" stroke-width="1.4" marker-end="url(#a1)"/>
  <path d="M504 214 L504 252" class="s-flow" stroke-width="1.4" marker-end="url(#a1)"/>
  <rect x="112" y="258" width="208" height="36" rx="8" class="s-ext" stroke-width="1.2"/>
  <text x="216" y="274" class="s-t" text-anchor="middle">GitHub</text>
  <text x="216" y="288" class="s-s" text-anchor="middle">COMMIT · PR · COMMENT</text>
  <rect x="400" y="258" width="208" height="36" rx="8" class="s-ext" stroke-width="1.2"/>
  <text x="504" y="274" class="s-t" text-anchor="middle">Gmail</text>
  <text x="504" y="288" class="s-s" text-anchor="middle">SEND REPORT</text>
</svg>`,
  },

  // ------------------------------------------------------------- THE BASICS
  {
    id: "jarviscore", kind: "statement", part: "THE BASICS",
    title: "Most frameworks hand the model a menu. JarvisCore lets it write the tool.",
    pre: `<span class="c">Most frameworks:</span>   you define tools    →  model picks one     →  the tool runs
<span class="c">JarvisCore:</span>        you describe a goal →  model writes Python →  a sandbox runs it`,
    lede: "And when you'd rather not leave something to a model, you write that part yourself. That choice is the whole API surface.",
    stats: [["150", "service bundles"], ["1,227", "integration atoms"], ["4", "memory tiers"], ["2", "profiles to learn"]],
  },
  {
    id: "profiles", kind: "table", part: "THE BASICS", title: "Two profiles. One mesh.",
    cols: ["Profile", "You write", "The framework writes", "Reach for it when"],
    rows: [
      ["**CustomAgent**", "`execute_task()`: the logic", "Mesh routing, discovery, lifecycle, infrastructure injection", "The answer is deterministic. Don't pay a model to do arithmetic."],
      ["**AutoAgent**", "`role`, `capabilities`, `system_prompt`", "Look-decide-act loop, planning, tool generation, sandboxed execution, self-repair", "The work needs judgement: reviewing, writing, deciding."],
    ],
    lede: "Our squad uses both. That's not a demo contrivance, it's the actual rule: **deterministic work goes in code, judgement goes in a prompt.**",
  },
  {
    id: "autoagent", kind: "code", part: "THE BASICS", title: "An AutoAgent is three attributes.",
    pre: `<span class="k">class</span> <span class="n">Inspector</span>(AutoAgent):
    <span class="hl">role</span>          = <span class="s">"inspector"</span>
    <span class="hl">capabilities</span>  = [<span class="s">"code_analysis"</span>, <span class="s">"security_analysis"</span>]
    <span class="hl">system_prompt</span> = <span class="s">"""You review code that is already on GitHub..."""</span>`,
    lede: "No tool definitions. No JSON schema. No executor wiring. The kernel plans the steps, writes the Python, runs it in a sandbox, and repairs it when it fails.",
    card: { tag: "What those three do", ticks: [
      ["role", "", "The name other agents route to."],
      ["caps", "", "What it advertises to the mesh, so work finds it."],
      ["prompt", "", "The job description. This is where your thinking goes."],
    ] },
  },
  {
    id: "customagent", kind: "code", part: "THE BASICS", title: "A CustomAgent is one method.",
    pre: `<span class="k">class</span> <span class="n">WarehouseAgent</span>(CustomAgent):
    role         = <span class="s">"warehouse"</span>
    capabilities = [<span class="s">"data_access"</span>]

    <span class="k">async def</span> <span class="hl">execute_task</span>(self, task):
        <span class="c"># you write this. no model involved, no tokens spent.</span>
        <span class="k">return</span> {<span class="s">"status"</span>: <span class="s">"success"</span>, <span class="s">"output"</span>: {...}}`,
    lede: "Same mesh, same routing, same infrastructure injection: you just supply the body. **Use it wherever a model would only add latency and risk.**",
  },
  {
    id: "mesh", kind: "code", part: "THE BASICS", title: "The mesh is four lines.",
    pre: `mesh = Mesh(config={<span class="s">"nexus_gateway_url"</span>: ..., <span class="s">"redis_url"</span>: ...})
mesh.add(CodeSmith)
mesh.add(Inspector)
mesh.add(Reporter)
<span class="k">await</span> mesh.start()

results = <span class="k">await</span> mesh.workflow(<span class="s">"review"</span>, [
    {<span class="s">"agent"</span>: <span class="s">"codesmith"</span>, <span class="s">"task"</span>: <span class="s">"Write it and push it"</span>},
    {<span class="s">"agent"</span>: <span class="s">"inspector"</span>, <span class="s">"task"</span>: <span class="s">"Review it"</span>, <span class="s">"depends_on"</span>: [<span class="n">0</span>]},
    {<span class="s">"agent"</span>: <span class="s">"reporter"</span>,  <span class="s">"task"</span>: <span class="s">"Email it"</span>,  <span class="s">"depends_on"</span>: [<span class="n">1</span>]},
])`,
    lede: "`depends_on` is the whole orchestration language. Steps with no dependency between them run in parallel; the engine handles claiming, retries and crash recovery.",
  },
  {
    id: "split", kind: "twocards", part: "THE BASICS", title: "Judgement in a prompt. Mechanics in code.",
    left: { tag: "The three agents decide things", brand: true, ticks: [
      ["1", "", "**CodeSmith**: what does plausible-but-flawed payments code look like?"],
      ["2", "", "**Inspector**: which of these are real defects, and how bad?"],
      ["3", "", "**Reporter**: what does someone actually need to read?"],
    ] },
    right: { tag: "Six calls stay ordinary Python",
      pre: "create_branch()\ncommit_file()\nread_file()\nopen_pr()\ncomment_on_pr()\nsend_email()",
      ps: ["Deterministic, so a model adds nothing but risk, and printing every one of them is what makes the run followable."] },
    lede: "Same credential guarantee either way: every call goes through `proxy.call(connection_id, …)`. **Ask which half a job belongs in before you write it.** That one question is most of the design.",
  },

  // -------------------------------------------------------------- THE BUILD
  {
    id: "requirements", kind: "twocards", part: "THE BUILD", title: "What you need, and what you don't.",
    left: { tag: "Need", ticks: [
      ["✓", "good", "Python 3.10+"],
      ["✓", "good", "`pip install jarviscore-framework[redis]`"],
      ["✓", "good", "Docker, for Redis: one compose command"],
      ["✓", "good", "**One** LLM credential, from whoever you like. JarvisCore is model-agnostic: Azure OpenAI, Anthropic, Gemini, or any OpenAI-compatible endpoint"],
      ["✓", "good", "A GitHub account"],
    ] },
    right: { tag: "Don't need", ticks: [
      ["–", "", "A **second** model provider: one credential covers the whole demo"],
      ["–", "", "A Google Cloud project: the gateway already has a client on `google-workspace`"],
      ["–", "", "Any vector database"],
      ["–", "", "A Nexus deployment: we used ours on the day"],
      ["–", "", "To have written an agent before"],
    ] },
    pre: `git clone https://github.com/Prescott-Data/office-hour-demos
<span class="k">cd</span> office-hour-demos/2026-08-27-oh-github-code-review-squad &amp;&amp; pip install -r requirements.txt`,
  },
  {
    id: "nexus", kind: "twocards", part: "THE BUILD", title: "Your agent never holds the token.",
    left: { tag: "What the agent writes",
      pre: `<span class="k">async def</span> main():
    r = <span class="k">await</span> nexus_call(<span class="s">"PUT"</span>, url,
            json={<span class="s">"content"</span>: b64})
    <span class="k">return</span> {<span class="s">"success"</span>: r[<span class="s">"ok"</span>]}`,
      ps: ["One door. No headers, no secrets, nothing to leak."] },
    right: { tag: "What Nexus does", brand: true, ps: [
      "Resolves an opaque `connection_id` to a live credential, applies it to the request, and returns only the response.",
      "**Nexus is also where the provider gets registered in the first place:** catalog, OAuth consent, token refresh, revocation.",
    ] },
    lede: "Proof, live: after a run we grep the generated code for `token|secret|bearer` and get nothing back.",
  },
  {
    id: "steps", kind: "table", part: "THE BUILD", title: "Four steps. Each runs on its own.",
    cols: ["Run", "What happens", "The moment"],
    rows: [
      ["`write_code.py`", "Writes the module, prints it, checks the defects", "Three attributes, zero infrastructure"],
      ["`push_and_open_pr.py`", "Consent → branch → commit → pull request", "Every call on screen, no token anywhere"],
      ["`review_pr.py`", "Reads it **back from GitHub**, reviews, comments", "Run twice; the second run remembers"],
      ["`email_report.py`", "Drafts the report, then **asks before sending**", "The inbox opens on screen"],
    ],
  },

  // ------------------------------------------------------------------ CLOSE
  {
    id: "close", kind: "close", part: "CLOSE", title: "Everything we typed is in the repo.",
    quote: "So, what's broken in yours?",
    links: [
      ["Code", "github.com/Prescott-Data/office-hour-demos"],
      ["Docs", "jarviscore.developers.prescottdata.io"],
      ["Keep asking", "#jarviscore on Discord"],
    ],
  },
];
