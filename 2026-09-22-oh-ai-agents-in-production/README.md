# AI Agents in Production

**Office Hours · 22 September 2026 · Ruth Mutua · Prescott Data Developers**

From architecture to a production-grade deployment. This session was a technical
discussion, not a build-along: what agents ask of a platform, the reference architecture
we run them on, the setup order and configuration that matter, and what went wrong on the
way. It closed with a live demo of one request travelling through a production control room.

**Slides:** [`ai-agents-in-production.pdf`](ai-agents-in-production.pdf). The deck is the main
artifact of this session; the code below is the demo and three short scripts that each prove
one claim from it.

| Part | Covers |
|---|---|
| Anatomy | The four planes, the peer mesh (seeds, gossip, trade-offs), security layers, memory tiers, tool access, leases and fencing |
| Platform | What the workload asks for, the options, why Kubernetes, the resulting topology |
| Setup | The order that works, and the StatefulSet, autoscaler and network-policy settings that matter |
| Running it | Observability and cost, resilience patterns, and the challenges we hit |
| Close | A ten-point production-readiness checklist |

Product and tenant names in the talk are generalized.

---

## What you need

- Python 3.10+
- Docker, for Redis
- **No LLM key.** The models are local fakes. A key is optional, for the live-model toggle

---

## Set it up

```bash
git clone https://github.com/Prescott-Data/office-hour-demos.git
cd office-hour-demos/2026-09-22-oh-ai-agents-in-production

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # pins jarviscore-framework 1.13.0, as on the day

cp .env.example .env                     # optional: everything runs without it
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

---

## The production control room

Real JarvisCore Mesh workers in two separate processes, Redis, a dashboard, and local fake
providers. The workflow (intake, plan, fetch config, approve, execute, summarize) runs
through the framework's own distributed worker loop.

```bash
cd control_room && python server.py      # then open http://localhost:8090
```

Each panel on the dashboard names the slide it demonstrates. Click through:

| Click | What you see | Slide |
|---|---|---|
| **Run request** (either tenant) | Two workers claim steps with leases; the ledger records every claim and completion | 12 |
| *(watch `fetch_config`)* | The call goes through the real `NexusCallProxy`; the agent's output holds a connection handle, never a token | 11 |
| *(watch tenant memory)* | The plan step writes under `cr:memory:<tenant>`, so the two tenants never share keys | 10 |
| **Approve** | The `approve_release` step waits in the framework's HITL queue until you resolve it | 9 |
| **Simulate: worker lost** | The worker holding a step stalls; its lease expires, the other worker finishes, and the stale result is rejected on resume | 12 |
| **Simulate: provider at capacity** | The primary model answers 429 "retry after 3600 seconds"; the fallback loop fails over in about a second | 22 |
| **Try a disallowed host** | Nexus refuses to attach the credential: `HostNotAllowed` | 11 |
| **Live model** *(optional)* | The summary becomes a real Azure OpenAI call, using `AZURE_*` from `.env` | |

`expected-output/control-room.txt` is a known-good run to compare against.

### Known limits (we said these on the day)

- Tenant memory scoping in Redis is a key-shape convention written for this demo, not
  framework enforcement.
- Execution is at-least-once, so the `execute` step is idempotent.
- Steps are slowed to about 2 seconds each so you can watch them; leases are 5 seconds.
- Everything is local. Nothing external is contacted unless the live-model toggle is on.

---

## Three claims, one script each

Each runs on its own, with no keys.

```bash
python beat1_lease_recovery.py    # needs Redis on localhost:6379
python beat2_nexus_contract.py    # no Redis; makes one request to httpbin.org
python beat3_fake_provider.py     # no Redis, no network
```

| Script | Claim | Proof it prints |
|---|---|---|
| `beat1_lease_recovery.py` | A frozen worker can't lose or duplicate work | The ledger: `step_claim_expired`, then worker-b finishes the step |
| `beat2_nexus_contract.py` | The agent never holds the credential | `grep` over everything the "agent" wrote finds nothing token-shaped |
| `beat3_fake_provider.py` | A provider that's up but out of capacity doesn't stall you | `answered by: vllm`, in about 1.6s rather than 3600s |

`beat3_failover.py` is the same idea against real providers: Azure as primary and a local
model through [Ollama](https://ollama.com) as the fallback. It needs `AZURE_*` in `.env`
and Ollama running; setup is in its docstring.

Known-good outputs for beats 1 and 3 are in `expected-output/`.

---

## Files

| File | What it is |
|---|---|
| `control_room/server.py` | The dashboard API: starts the workers and fake providers, drives the scenarios |
| `control_room/worker.py` | One Mesh worker process; the server starts two |
| `control_room/common.py` | Shared settings: ports, lease length, the six steps |
| `control_room/ui.html` | The dashboard |
| `beat1_lease_recovery.py`, `beat2_nexus_contract.py`, `beat3_fake_provider.py`, `beat3_failover.py` | The standalone proofs |
| `expected-output/` | Known-good output from the day |
| `ai-agents-in-production.pdf` | The slides |
