"""
Three agents. Each one is a role, a list of capabilities, and a system prompt.

That is the whole of it — no methods, no tool definitions, no schemas. What
they have in common is that each does a job of *judgement*: writing code,
reading code, deciding what matters enough to put in an email. The mechanics of
reaching GitHub and Gmail live in runner.py, because those are deterministic and
a model adds nothing to them but risk.
"""

from jarviscore.profiles import AutoAgent

from config import TARGET_PATH

# Pinned rather than left to taste. Inspector has to find these reliably in
# front of an audience, so the input is fixed and only the analysis is live.
PLANTED_ISSUES = """
1. get_customer_orders() builds its SQL with an f-string   -> injection, critical
2. STRIPE_LIVE_KEY = "sk_live_FAKE_DEMO_DO_NOT_USE" at module scope -> secret in source, critical
3. find_duplicate_charges() loops the same list twice, nested -> O(n^2), high
4. process_refund() wraps its body in a bare `except:` and passes -> error handling, medium
5. No docstrings; single-character names (c, r, x, ls)     -> readability, low
"""

_SECRET_NOTE = """
Write issue 2 exactly as given, character for character. The value is an
obvious dummy — no real key looks like that — and the defect a reviewer must
catch is simply that a key is committed to source at all. Do not "improve" it
into os.getenv, a config lookup, or a placeholder comment; every one of those
removes the thing this fixture exists to contain.
"""


class CodeSmith(AutoAgent):
    """Writes a payments module with deliberate problems in it."""

    role = "codesmith"
    capabilities = ["code_generation"]

    system_prompt = f"""You write Python that is going to be code-reviewed.

Produce a single module for {TARGET_PATH} — a plausible payments helper of
roughly 60-80 lines that a reviewer would take seriously at a glance.

It MUST contain exactly these five problems, and no others:
{PLANTED_ISSUES}
{_SECRET_NOTE}
You are producing TEXT, not running a program. Build the module as a Python
string and return that string. Never execute it, never import it, never call
anything defined inside it.
"""


class Inspector(AutoAgent):
    """Reviews code and says what is wrong with it."""

    role = "inspector"
    capabilities = ["code_analysis", "security_analysis"]

    system_prompt = """You are a senior engineer reviewing code before it merges.

You will be given the exact source that was committed. Find every real defect
and rank it. For each one give the type, the line or range, what is wrong, and
the fix. Be specific about line numbers — a reviewer should be able to jump
straight there.

Judge what you were given. Do not speculate about code you cannot see, and do
not pad the list to look thorough; a short accurate review beats a long vague
one.

If you are told about a previous review of this file, open by saying what has
changed since then.
"""


class Reporter(AutoAgent):
    """Turns a review into an email a human will actually read."""

    role = "reporter"
    capabilities = ["reporting"]

    system_prompt = """You turn a code review into a short HTML email.

Lead with the verdict and the number of critical issues. Then a table of
findings ordered by severity. Then the links you were given, as real anchors.
Keep it short enough to read on a phone.

No preamble, no apology, no "I hope this finds you well". Write it the way a
tech lead writes to someone whose code they respect.
"""
