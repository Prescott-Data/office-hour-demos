# JarvisCore for Personal Finance

A private money desk. You give it an M-Pesa or bank statement — the locked PDF exactly as it
arrives — and it reads every transaction, checks its own arithmetic against the running
balance, works out the spending categories that fit your life, and tells you where the money
went, what changed, and what deserves a second look.

Correct a category once and it never gets that counterparty wrong again.

Statements are among the most sensitive documents a person owns. The design goal is that they
are read by a model running inside your own boundary; until then, counterparty names are
replaced with labels before anything leaves the machine.

## Quick start

No statement of your own and no API keys needed:

```bash
cd community-spotlight/personal-finance
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e . --no-deps
pytest        # 144 tests, no network, no model spend
pf-demo
```

`pf-demo` builds a statement that never existed, reads it through the same extractor a real
PDF goes through, proves the reading against the balances the statement carries, and runs the
probes. Everything it prints is arithmetic, so it is identical every run.

## With your own statement

Put the PDF in `private/` (git-ignored) and set the keys:

| variable | what it is for |
|---|---|
| `AZURE_API_KEY`, `AZURE_ENDPOINT`, `AZURE_DEPLOYMENT`, `AZURE_API_VERSION` | the generative steps: proposer, watchdog, coach, auditor |
| `TYPESAFE_API_KEY` | Jev, the decision model the categoriser uses |
| `PF_STATEMENT_PASSWORDS` | comma-separated passwords tried when opening a locked PDF |
| `PF_STATE_DIR` | optional; moves where your desk is kept |

Then, in the order you would actually use them:

```bash
pf read      private/statement.pdf   # extract, and prove it reconciles
pf propose   private/statement.pdf   # categories that fit you; you approve each one
pf categorise private/statement.pdf  # the breakdown, with what it cost
pf review    private/statement.pdf   # settle anything it could not place
pf watch     private/statement.pdf   # what deserves your attention
pf audit     private/statement.pdf   # what the period cost that need not have

pf mine "SOME PAYBILL"               # that account is mine, not spending
pf dismiss "A PLACE" same_day_pairs  # this pattern is normal for me
pf set "A PLACE" groceries           # record a category yourself
pf forget "A PLACE"                  # undo a placement
pf categories list|rename|remove     # repair the category set
```

Or the same desk in a browser, which adds the two-stage flow — categorise, confirm, then see
what deserves attention:

```bash
pf-desk      # http://127.0.0.1:8000
```

The first run after starting takes about two minutes while the mesh starts, then it is quick.

## The agents

Five, each addressed by what it does rather than by its name:

| agent | capability | what it does |
|---|---|---|
| Proposer | `category_proposal` | reads the whole statement and proposes a category set that fits this person |
| Categoriser | `transaction_categorisation` | places each counterparty, using Jev — a decision model that returns a choice and a confidence |
| Watchdog | `spending_oversight` | chooses which probes to run, and reports what departs from a place's own pattern |
| Coach | `spending_summary` | writes the plain account of where the money went |
| Auditor | `avoidable_cost` | separates cost from waste, and says what need not have been spent |

`team.py` builds them into a mesh. Constructing the mesh starts nothing and contacts no
provider, which is why the tests are fast.

```python
def member(mesh, capability):
    """The agent that does a thing, found by the thing it does rather than by name."""
```

Nothing asks for "the Coach"; it asks for whatever offers `spending_summary`. The coach reaches
the auditor through `peers.request`, which lands in the auditor's `on_peer_request` and returns
the audit it already worked out — no second model call.

## In the shared Desk

`pf.desk.yaml` describes this blueprint to the shared Desk: which factory builds the mesh, which
function takes a task, and how each agent appears on the canvas. The Desk itself ships with the
JarvisCore agents repository rather than this folder, so here the way in is `pf-desk` above. The
file travels with the build so that it drops straight into that Desk when it lands there.

`tests/test_desk_config.py` keeps the file honest without the Desk present — every appearance
names a real role, and every shape is one the Desk can draw.

## How it is put together

```
personal_finance/
├── sources/pdf.py, sources/table.py   opening the PDF; one generic column extractor
├── verify.py                          checks the statement's own arithmetic
├── layouts/mpesa-statement.yaml       every issuer word, as data rather than code
├── agents/                            the five above
├── probes.py, facts.py                the questions an agent may ask the numbers
├── masking.py                         names become "counterparty 7" before leaving
├── profiles/categories.yaml           your categories, editable, with their meanings
├── corrections.py, judgements.py,     what is yours: your fixes, decisions already made,
│   rulings.py, notes.py               your word on a line, patterns you call normal
├── team.py                            build_mesh()
├── cli.py, web.py, static/index.html  the two doors in
└── demo/                              a statement that never existed
```

Four ideas carry the rest:

- **Verification beats trust.** A statement carries its own proof: previous balance plus paid
  in minus withdrawn must equal the balance on every row. A misread row is catchable, so the
  reading does not have to be believed.
- **No merchant knowledge in code.** Issuer vocabulary lives in a layout profile, categories in
  a user profile. Encoding "this shop is groceries" in Python would be taking the agent's job.
- **Decide once, store it.** Each judgement is kept against a fingerprint of the category set
  it chose from. This is not only about cost: a model asked twice can answer differently, and
  storing the decision is what makes the figures stable. Change the categories and it asks
  again.
- **Precedence.** Your correction outranks what the document states, which outranks the agent.

## What is yours

Real statements go in `private/`, which is git-ignored. Everything under
`personal_finance/demo/` and in `tests/` is invented — no real person, company or transaction
appears anywhere in this repository.

Your corrections, confirmed categories, rulings and audits live in `.pf-state/<you>/`, beside
this README and also git-ignored. That path is anchored to the project rather than to the
working directory, because the shared Desk runs each task from its own directory — so the CLI,
the browser desk and the shared Desk all reach the same desk.

## Known limits

- Only M-Pesa statements are proven. The extractor is generic and the issuer's vocabulary is a
  YAML profile, so another format is a new profile rather than new code — but that is untested.
- The auditor's judgement is not stable across fresh runs on the same statement. Caching is
  what makes the figure stable, and your ruling on a line outranks it permanently; neither is a
  cure for the underlying variance.
- `mesh.start()` takes about two minutes because each agent re-seeds a shipped atom catalogue.
- Side effects: none. It reads a statement and writes local files. It moves no money.
