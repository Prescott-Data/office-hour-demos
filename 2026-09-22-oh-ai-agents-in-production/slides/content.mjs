// The deck as presented on 22 September 2026. Rebuild with: node build.mjs
// The agenda and section dividers are generated from each slide's `part`.
// Code lines: "!" prefix = accent, "#" prefix = comment (dim), plain = normal.

export const TITLE = "AI Agents in Production";
export const SUBTITLE = "From architecture to a production-grade deployment";

export const slides = [
  // ---------------------------------------------------------------- OPEN
  {
    id: "title", kind: "title", part: "DEVELOPER OFFICE HOURS",
    title: TITLE, subtitle: SUBTITLE,
    footer: ["Ruth Mutua · Prescott Data", "Developer Office Hours · 22 September 2026"],
  },
  {
    id: "leave-with", kind: "takeaways", part: "OPEN", title: "What you'll leave with",
    items: [
      { h: "A reference architecture", p: "Four planes, and the peer mesh that ties the agents together." },
      { h: "What agents ask of a platform", p: "The requirements, and how they decided where we run." },
      { h: "A setup order that works", p: "The sequence, and the handful of settings that matter." },
      { h: "A readiness checklist", p: "Ten questions to ask before agents go live." },
    ],
    note: "Everything I show comes from running JarvisCore, our open-source agent framework, in production. Product and tenant names are generalized.",
  },
  {
    id: "why-different", kind: "table", part: "OPEN", title: "Why agents aren't just another service",
    cols: ["Trait", "What it means for operations"],
    rows: [
      ["Long-running", "No request timeouts in front; graceful drain on deploy"],
      ["Stateful", "Stable identity and durable state, or a restart loses work"],
      ["Non-deterministic", "You can't assert outputs, so you bound behaviour instead"],
      ["Holds credentials to other systems", "Blast radius is every system it can reach"],
      ["Multi-tenant", "Isolation has to be designed in, not added later"],
      ["Expensive per call", "Budgets, quotas and fallbacks are reliability features"],
    ],
  },

  // ------------------------------------------------------- PART 1 ANATOMY
  {
    id: "architecture", kind: "diagram", diagram: "architecture", part: "PART 1 · ANATOMY",
    title: "Reference architecture: four planes",
    caption: "What we run: two stateful agent services on a gossip mesh, a stateless service, a model gateway, and a managed data layer.",
  },
  {
    id: "mesh", kind: "diagram", diagram: "mesh", part: "PART 1 · ANATOMY", title: "Agents as peers: mesh, seeds and gossip",
    defs: [
      { h: "Peer", p: "A running agent service that advertises what it can do." },
      { h: "Mesh", p: "All the peers that know about each other. No central list." },
      { h: "Seed node", p: "A known address a new peer contacts to join. An entry point, not a leader." },
      { h: "Gossip (SWIM)", p: "Peers ping each other and share news, so everyone converges on who's alive." },
    ],
    caption: "Membership, failure detection and capability announcements ride on gossip. Agent-to-agent messages go peer to peer.",
  },
  {
    id: "gossip-tradeoff", kind: "twocol", part: "PART 1 · ANATOMY", title: "Why gossip, and what it costs",
    left: {
      h: "What you get",
      items: [
        "No registry or broker to run, scale or fail",
        "Failure detection built in: silent peers go suspect, then dead",
        "Capabilities announced: the roster writes itself, no redeploy",
        "No permanent coordinator: any eligible peer can claim work",
        "The same code from one process to a fleet",
      ],
    },
    right: {
      h: "What it asks of your platform",
      items: [
        "Stable identity per node: a seed needs a stable name",
        "TCP and UDP open on the mesh ports",
        "Membership is eventually consistent, not instant",
        "Work and state still live in Redis: gossip is not the source of truth",
      ],
    },
    note: "If you've run Consul or Cassandra, you've relied on the same idea. The right-hand column is why the platform choice comes next.",
  },
  {
    id: "security", kind: "table", part: "PART 1 · ANATOMY", title: "Security: layers, not a single gate",
    cols: ["Layer", "Control"],
    rows: [
      ["Identity", "Workload identity to a managed secrets store"],
      ["Credentials", "Nexus, a broker at the call boundary; agents hold opaque handles, never tokens"],
      ["Code execution", "Generated code runs in a separate process with a scrubbed environment"],
      ["Network", "Policies scoped per service, opened per port and protocol"],
      ["Tenants", "Tenant id carried in every memory and workflow key"],
      ["Actions", "Irreversible tools require human approval"],
    ],
    note: "Direction we're hardening toward: authenticate at the endpoint, not only at the network boundary.",
  },
  {
    id: "memory", kind: "cards", part: "PART 1 · ANATOMY", title: "Memory: four tiers, one interface",
    cols: 4,
    items: [
      { h: "Working", p: "Scratchpad for the current step, discarded when it finishes.", meta: ["Lives in: blob storage", "Lifetime: the step"] },
      { h: "Episodic", p: "An append-only ledger of what happened, in order. The audit trail.", meta: ["Lives in: a Redis stream", "Lifetime: 7 days by default"] },
      { h: "Long-term", p: "The model compresses a long ledger into a summary, backed up to blob storage.", meta: ["Lives in: Redis + blob", "Lifetime: the workflow"] },
      { h: "Cross-session", p: "Semantically searchable memory that spans workflows and restarts, not just the current one. A restarted agent recovers what it learned, not just its last checkpoint.", meta: ["Lives in: an external memory service", "Lifetime: across sessions"], hl: true },
    ],
    note: "One object, UnifiedMemory, fronts all four tiers. For this tier, we use Athena, our open-source memory framework — it ships with three tiers of its own (short-term, mid-term, long-term graph). Set ATHENA_URL and every agent upgrades, with no code changes.",
  },
  {
    id: "tools", kind: "diagram", diagram: "tools", part: "PART 1 · ANATOMY", title: "Tool access: one door, built in",
    caption: "In JarvisCore, agents never hold a token. Nexus checks the host allowlist before a credential is attached.",
    bullets: [
      "Nexus: one call for OAuth2, API keys and Basic auth, with automatic token refresh",
      "About 150 integrations ship as atoms: typed single-file functions the agent finds in a registry",
      "Destructive tools declare an approval policy; execution is at-least-once, so keep tools idempotent",
    ],
  },
  {
    id: "orchestration", kind: "diagram", diagram: "lease", part: "PART 1 · ANATOMY", title: "Orchestration: leases and fencing",
    caption: "Think of a job queue with a visibility timeout, plus a fencing token. No permanent coordinator: any eligible peer can claim a ready step.",
    bullets: [
      "A workflow is a DAG in Redis; workers claim a step with a leased lock",
      "A heartbeat renews the lease; an expired lease is recovered and re-queued",
      "Only the current claim holder can commit a result",
    ],
  },

  // ------------------------------------------------------ PART 2 PLATFORM
  {
    id: "requirements", kind: "table", part: "PART 2 · PLATFORM", title: "What the workload asks of the platform",
    cols: ["Workload trait", "Platform requirement"],
    rows: [
      ["Stateful gossip mesh", "Stable pod identity and per-pod DNS"],
      ["Long-running steps", "Graceful termination; no idle timeout in front"],
      ["Bursty load", "Autoscaling that scales down slowly"],
      ["Slow startup", "Generous rollout timeouts and ordered start"],
      ["Untrusted generated code", "Isolation outside the cluster nodes"],
      ["Multi-tenant", "Namespace and network boundaries"],
      ["Model capacity limits", "A gateway with fallback tiers"],
    ],
  },
  {
    id: "decision", kind: "matrix", part: "PART 2 · PLATFORM", title: "The options and the decision",
    cols: ["Option", "Where it fits", "Where it struggles"],
    rows: [
      ["Serverless functions", "Stateless, short, bursty work", "Long-running, stateful, identity-bound agents"],
      ["Container-app platforms", "Simple long-running containers", "Less control over pod identity, placement and policy"],
      ["Kubernetes", "StatefulSets, node pools, network policy, tuned autoscaling", "You operate it"],
      ["VMs + compose", "Where we started: fast to stand up", "Rolling updates, autoscaling, isolation at scale"],
    ],
    decision: "We chose Kubernetes: StatefulSets for the mesh, node pools for isolation, and a managed sandbox-session service for untrusted code. It also sat next to the platform we already ran.",
  },
  {
    id: "topology", kind: "diagram", diagram: "topology", part: "PART 2 · PLATFORM", title: "The resulting topology",
    caption: "Separate clusters per product shape, with a warm standby in another region.",
  },

  // --------------------------------------------------------- PART 3 SETUP
  {
    id: "setup-order", kind: "steps", part: "PART 3 · SETUP", title: "Setup order, and why the order matters",
    steps: [
      ["Infrastructure as code", "Cluster, workload identity, secrets store, registry"],
      ["Platform layer", "Cert manager, ingress, monitoring, logging"],
      ["Data layer", "Redis, document store, event bus, vector store"],
      ["Agent services", "Seed pod first, then the rest in order"],
      ["Policies and autoscaling", "Network policies and HPA, once the workload is healthy"],
      ["CI/CD", "Build, then roll out with a long timeout: agent startup is slow"],
    ],
    note: "Agents assume the data layer and their seed peer already exist.",
  },
  {
    id: "config", kind: "code3", part: "PART 3 · SETUP", title: "The configuration that matters",
    panels: [
      {
        label: "Stable identity",
        why: "Peers find each other by name, and the seed pod starts first.",
        code: [
          "kind: StatefulSet",
          "spec:",
          "!  serviceName: agents-headless",
          "!  podManagementPolicy: OrderedReady",
          "#  # ordinal 0 is the seed",
          "  containers:",
          "  - env:",
          "    - name: SWIM_BIND_HOST",
          "!      valueFrom: {fieldRef:",
          "!        {fieldPath: status.podIP}}",
          "#      # not 0.0.0.0",
        ],
      },
      {
        label: "Slow to shrink",
        why: "Every pod that leaves costs the mesh time to reconverge.",
        code: [
          "kind: HorizontalPodAutoscaler",
          "spec:",
          "  minReplicas: 3",
          "  maxReplicas: 10",
          "  behavior:",
          "    scaleDown:",
          "!      stabilizationWindowSeconds: 300",
          "!      policies: [{type: Pods,",
          "!        value: 1, periodSeconds: 120}]",
          "#  # VPA: InPlaceOrRecreate",
        ],
      },
      {
        label: "Both protocols",
        why: "Joins use TCP; steady-state gossip uses UDP. Allow both.",
        code: [
          "kind: NetworkPolicy",
          "#  # mesh ports, ingress + egress",
          "  - ports:",
          "    - {protocol: UDP, port: 8001}",
          "#      # steady-state gossip",
          "!    - {protocol: TCP, port: 8001}",
          "#      # joins and full sync",
        ],
      },
    ],
  },

  // ---------------------------------------------------- PART 4 OPERATIONS
  {
    id: "observability", kind: "twocol", part: "PART 4 · RUNNING IT", title: "Observability and cost control",
    left: {
      h: "What we watch",
      items: [
        "Workflow and step state, from the ledger",
        "Lease expiries and reclaimed steps",
        "Pod memory near its limit; OOMKilled",
        "Mesh membership, not just readiness",
        "Tokens and cost per workflow",
        "Provider errors and rate limits",
      ],
    },
    right: {
      h: "Who provides it",
      items: [
        "JarvisCore: ledger stream, scrubbed traces, per-workflow budgets, optional metrics endpoint",
        "Operator: alert rules, dashboards, membership checks",
        "Stack: Prometheus and Grafana for metrics, Loki for logs",
      ],
      note: "JarvisCore gives you the events. You build the alerts.",
    },
  },
  {
    id: "resilience", kind: "table", part: "PART 4 · RUNNING IT", title: "Staying up: resilience patterns",
    cols: ["Pattern", "What it protects against"],
    rows: [
      ["Leases and fencing", "A stalled or partitioned worker holding a step"],
      ["Provider fallback, capped backoff", "A model provider that is rate-limited or out of quota"],
      ["Gateway circuit breaker and model tiers", "Capacity exhausted in one tier"],
      ["Human approval", "An irreversible action taken on a bad plan"],
      ["Idempotent tools", "At-least-once execution repeating a side effect"],
    ],
  },
  {
    id: "lessons", kind: "table3", part: "PART 4 · RUNNING IT", title: "Challenges and what we learned",
    cols: ["Challenge", "What it taught us", "What we do now"],
    rows: [
      ["Mesh nodes advertised an unroutable address", "Bind to what peers can reach", "Pod IP injected at start"],
      ["A blocking call froze the API while gossip looked healthy", "A healthy process isn't a working service", "Blocking init runs off the event loop"],
      ["Seed hostname cached through rolling restarts", "Stable identity is not stable addresses", "Check membership on every replica after a restart"],
      ["Network policy allowed UDP but not TCP", "Policies fail silently until a cold start", "Test a full-restart join"],
      ["Admission cap of 16 over a call limit of 1", "Set concurrency limits explicitly, in one place", "Explicit defaults in config"],
    ],
  },

  // ------------------------------------------------------- DEMO AND CLOSE
  {
    id: "demo-setup", kind: "diagram", diagram: "demoflow", part: "DEMO", title: "One request, end to end",
    caption: "The path you're about to watch. Each stage maps to a slide you've just seen.",
  },
  {
    id: "demo-live", kind: "demo", part: "LIVE DEMO", title: "The production control room",
    watch: [
      "Steps claimed by two workers, with lease timers",
      "A tool call: the agent holds a handle, never a token",
      "Two tenants with separate memory",
      "An approval gate on an irreversible step",
      "Simulate: worker lost",
      "Simulate: model provider at capacity",
    ],
    run: "Run it yourself: control_room/ in this folder. No LLM key needed.",
  },
  {
    id: "checklist", kind: "checklist", part: "CLOSE", title: "The production-readiness checklist",
    items: [
      ["Identity", "Workload identity; no shared secrets baked into images"],
      ["Credentials", "Brokered, never in agent context"],
      ["Tenants", "Isolation in every key and policy"],
      ["Bounded behaviour", "Iteration, time and token budgets"],
      ["Idempotent tools", "Safe to run twice"],
      ["Leases and fencing", "Work survives a lost worker"],
      ["Budgets", "Cost per workflow, alerts on drift"],
      ["Fallbacks", "Provider, model tier, degraded mode"],
      ["Observability", "State, membership and cost, not just readiness"],
      ["Human gates", "Approval for irreversible actions"],
    ],
  },
  {
    id: "resources", kind: "resources", part: "CLOSE", title: "Take it further",
    groups: [
      { h: "Run this session's code", items: [
        ["control_room/", "The live demo: two Mesh workers, Nexus, a human gate, failover"],
        ["beat1_lease_recovery.py", "A lost worker's step is reclaimed and finished"],
        ["beat2_nexus_contract.py", "The agent holds a handle; an off-allowlist host is refused"],
        ["beat3_failover.py", "A provider at capacity, and the fallback that takes over"],
      ] },
      { h: "The projects behind it", items: [
        ["pip install jarviscore-framework", "The agent framework used throughout"],
        ["github.com/Prescott-Data/jarviscore-framework", "Source, docs and examples"],
        ["github.com/Prescott-Data/athena", "Cross-session memory for agents"],
      ] },
    ],
  },
];
