# Agent to Agent Communication

**Office Hours · 22 October 2026 · Ruth Mutua · Prescott Data Developers**

Most multi-agent systems route every message through one orchestrator. This session asked
what happens when that orchestrator dies, and answered it live in the terminal: a small
team of agents that find each other by gossip and message each other directly, with
nothing in the middle. One agent is killed mid-conversation and the rest keep talking. A
new one joins and the others find it, with no redeploy.

**Slides:** [`slides/agent-to-agent-communication.pdf`](slides/agent-to-agent-communication.pdf)

| Part | Covers |
|---|---|
| The question | Everyone talks through the boss. So what happens when the boss dies? |
| The landscape | Four ways agents talk today: orchestrator, message broker, protocols (MCP, A2A), peer mesh |
| Side by side | What breaks when one node dies, and why A2A and a peer mesh aren't rivals |
| How a mesh works | Seeds, gossip (SWIM), suspect then dead, direct messages over ZeroMQ |
| The build | Three checkpoints, below |
| Taking it further | From one laptop to a fleet |

---

## What you need

- Python 3.10 or newer
- **No LLM key, no Redis, no broker.** Everything runs on one machine

```bash
git clone https://github.com/Prescott-Data/office-hour-demos.git
cd office-hour-demos/2026-10-22-oh-agent-to-agent-communication

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # pins jarviscore-framework[p2p] 2.1.1, as on the day
unset REDIS_URL                          # if it's set, the Mesh uses Redis instead of staying local
```

On zsh, keep the quotes if you install by hand: `pip install "jarviscore-framework[p2p]"`.

---

## Checkpoint 1: two agents talking

One file, two agents, a direct request and a reply. No network.

```bash
./scripts/show agent      # the whole Analyst: a role, capabilities and a description. No address
./scripts/show listen     # how it answers: wait for a message, respond to whoever sent it
./scripts/show ask        # the researcher finds the analyst by role and asks it directly
python two_agents.py
```

```
researcher can see: ['analyst']
analyst replied:    {'verdict': 'signal, not noise'}
```

Nobody told the researcher the analyst existed, and nothing routed the message.

---

## Checkpoint 2: a mesh across terminals

Each agent is now its own process, like separate machines. Open three terminals in this
folder (venv on, `REDIS_URL` unset) and a fourth for reading code.

```bash
./scripts/show config                               # the only networking you write
```

```bash
python mesh_node.py analyst 7946                    # terminal 1: the seed
python mesh_node.py writer  7947 127.0.0.1:7946     # terminal 2: join through the seed
python mesh_node.py scout   7948 127.0.0.1:7946     # terminal 3
```

Each pane prints `+ <role> joined` as the others arrive, then every four seconds one agent
pings a neighbour directly:

```
11:24:08   scout -> writer: hello from the writer
11:24:12   scout -> analyst: hello from the analyst
```

```bash
./scripts/show roster     # every second: who's around now? Nobody maintains this list
./scripts/show hello      # pick a neighbour, round robin, ask, print the reply
```

**Now kill the writer.** Press Ctrl+C in terminal 2. Within a second every other pane
prints `- writer left`, and the scout's next ping goes to the analyst. Nobody restarted
anything, because there was no boss to fail over. A hard crash (`kill -9`) drops off the
roster too, once the gossip marks it dead, about twenty seconds later.

---

## Checkpoint 3: a new agent, found live

```bash
python mesh_node.py translator 7950 127.0.0.1:7946  # in the writer's old terminal
./scripts/show join                                 # everything it took to join
```

The analyst and the scout print `+ translator joined` and start pinging it. No agent was
edited or redeployed. Every agent is the same command with its own port and the seed's
address. Pick any role name you like.

---

## Gotchas from the day

| What you see | Why |
|---|---|
| A new node takes 15 to 20 seconds to print `up` | Normal. It announces itself to the mesh first. The others often print `joined` before it does |
| A ping says `not ready yet` | The peer joined a moment ago and its listener hasn't started. The next ping answers |
| A restarted node says `up` but nobody sees it, with `Port ... is not available` above | Your OS holds the old port for up to a minute. Restart on a new port |
| The second node never prints `joined` | The seed isn't running, or the seed port is wrong. Start the seed first |
| A stopped peer never prints `left` | You're on a version before 2.1.1. `pip show jarviscore-framework` should say 2.1.1 |
| Long `Task was destroyed but it is pending` lines on Ctrl+C | Harmless shutdown noise |

---

## Taking it further

Across machines it's the same code: set `bind_host` to `0.0.0.0`, use the seed's real IP,
and open the ports, TCP and UDP. Each node uses its port for gossip and that port plus 1000
for messages.

For real-world scenarios, where agents on the mesh share real work through Redis and the
workflow survives a restart, see the JarvisCore
[`examples`](https://github.com/Prescott-Data/jarviscore-framework/tree/main/examples) folder.
A good start is the distributed research network: start
[`research_synthesizer.py`](https://github.com/Prescott-Data/jarviscore-framework/blob/main/examples/research_synthesizer.py)
(the seed), then
[`research_node_1.py`](https://github.com/Prescott-Data/jarviscore-framework/blob/main/examples/research_node_1.py),
`_2` and `_3`. Each node claims its step of a shared workflow from Redis, and the synthesizer
combines their outputs. It needs Redis and an LLM key.

- P2P concepts: https://jarviscore.developers.prescottdata.io/concepts/p2p/
- Retrying safely after a lost reply: [`p2p_lost_reply_retry.py`](https://github.com/Prescott-Data/jarviscore-framework/blob/main/examples/p2p_lost_reply_retry.py)

---

## Files

| File | What it is |
|---|---|
| `two_agents.py` | Checkpoint 1: two agents in one process, a direct request and reply |
| `mesh_node.py` | Checkpoints 2 and 3: one agent per terminal, joining the mesh through a seed |
| `scripts/show` | Prints the piece of code being discussed, straight from the two files |
| `slides/` | The deck as a PDF |
