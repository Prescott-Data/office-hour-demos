# Give Your AI Agent a Compass, Not a Bigger Prompt

This repository contains a full-screen presentation and evidence-map demo for
showing a small, explicit claims agent using Odin as its graph-navigation compass.

The agent chooses what to investigate, interprets returned evidence, and chooses
the next seed. Odin navigates and ranks recorded graph paths. Neither the demo
nor Odin declares fraud or intent.

## Presentation

- `http://127.0.0.1:5173/present/title` opens the presentation.
- `http://127.0.0.1:5173/present/agent` jumps to the live agent chapter.
- `http://127.0.0.1:5173/demo` opens the standalone Odin evidence map.

Use the arrow keys, Page Up, Page Down, or Space to navigate. Press `F` or use
the fullscreen control to enter fullscreen mode. Chapter URLs and local progress
support refresh and rehearsal recovery.

The Lisa-only transcript and operational material live under `docs/session/`.

## Claims Agent

The live chapter calls Azure OpenAI directly. Create a private local environment
file from the committed template and fill in its values before rehearsal:

```bash
cp .env.example .env
```

The committed template is safe to share. The populated `.env` is ignored and
must be distributed only through an approved secret-sharing channel.

The claims investigator in `agent.py` owns one visible reason/act/observe loop.
On each turn the model gives a concise rationale, optionally updates its durable
scratchpad, and chooses one action: resolve an entity, call Odin, or finish. The
application does not prescribe a retrieval sequence, entity route, or verdict.

Every model call, Odin result, event, and conclusion is preserved under
`artifacts/agent-runs/` with a stable mission ID. Required evidence is never
silently reduced to a top-N view. Complete reasoning-bearing Odin evidence is
provided to every subsequent agent turn; an oversized payload stops the mission
explicitly instead of being truncated.

# Odin Evidence Map

This demo visualizes a real Odin retrieval over a deterministic graph stored in
ArangoDB. Cytoscape.js renders the graph in the browser; it does not replace the
database or retrieval engine.

## Data flow

```text
ArangoDB -> OdinEngine -> FastAPI -> Cytoscape.js
```

The frozen dataset contains 775 entities and 2,619 relationships. Every API
retrieval writes the complete canonical Odin response to `artifacts/` before
returning it to the browser.

## Prerequisites

- ArangoDB available at `http://localhost:8529`
- a Python environment with Odin and `requirements-demo.txt` installed
- Node.js and npm

The loader reads these optional environment variables:

```bash
export ARANGO_URL=http://localhost:8529
export ARANGO_USERNAME=root
export ARANGO_PASSWORD=odin-demo
export ODIN_DEMO_DATABASE=odin_demo_validation
```

## Load and verify the graph

From this directory:

```bash
python load_graph.py
python verify_odin.py
```

## Run the application

Terminal one:

```bash
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Terminal two:

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173/`.

## Validate

```bash
python -m unittest test_api.py
cd frontend
npm run lint
npm run build
```

The UI displays both requested and effective retrieval controls. Odin 0.2.0
may adapt a `12 / 10 / 32` request to an effective `24 / 4 / 64` pass when its
initial result has low support.

The navigation view exposes only evidence available from released Odin and the
loaded ArangoDB records:

- PPR node ranks and values;
- public NPLL edge plausibility scores;
- effective beam controls, timings, and budget counts;
- retained ranked paths; and
- the exact source document attached to every returned edge.

After a retrieval completes, the UI replays retained paths in rank order so the
viewer can see the evidence set accumulate. This is explicitly a result replay,
not a live beam-frontier trace: Odin 0.2.0 does not expose rejected candidate
identities or per-hop frontier snapshots through its public API.
