import pytest

from personal_finance import counterparty, layouts, profiles
from personal_finance.agents.categoriser import Categoriser
from personal_finance.corrections import Corrections
from personal_finance.judgements import Judgements

LAYOUT = layouts.load("mpesa-statement")
POLICY = profiles.categories()

STATED = "Customer Transfer of Funds Charge"
SHOP = "Merchant Payment Online to 1234567 - CORNER GROCERS"


class StubDecisions:
    """Answers like Jev without a network, so the paths can be tested for nothing."""

    def __init__(self, choice="groceries", confidence=0.9):
        self.choice, self.confidence, self.calls = choice, confidence, []

    async def evaluate(self, *, state, questions, model=None):
        self.calls.append(questions)
        answers = {
            label: {"type": "choice", "choice": self.choice, "confidence": self.confidence}
            for label in questions
        }
        return type("Result", (), {"answers": answers})()


def build(stub=None, tmp_path=None):
    agent = Categoriser(
        LAYOUT,
        POLICY,
        corrections=Corrections(tmp_path / "corrections.json"),
        judgements=Judgements(tmp_path / "judgements.json"),
    )
    agent.decisions = stub
    return agent


def test_what_the_statement_states_needs_no_model(tmp_path):
    agent = build(StubDecisions(), tmp_path)
    verdicts = agent.settled([STATED])
    key = next(iter(verdicts))
    assert verdicts[key].category == "fees_and_charges"
    assert verdicts[key].decided_by == "document"
    assert agent.decisions.calls == []


@pytest.mark.asyncio
async def test_a_shop_is_judged_and_only_asked_about_once(tmp_path):
    agent = build(StubDecisions(), tmp_path)
    verdicts = await agent.categorise([SHOP, SHOP, SHOP])
    assert verdicts["CORNER GROCERS"].category == "groceries"
    assert verdicts["CORNER GROCERS"].decided_by == "agent"
    assert len(agent.decisions.calls) == 1
    assert len(agent.decisions.calls[0]) == 1


@pytest.mark.asyncio
async def test_your_correction_beats_both(tmp_path):
    agent = build(StubDecisions(), tmp_path)
    key = counterparty.key(STATED, LAYOUT.kinds)
    verdicts = await agent.categorise([STATED], corrections={key: "transport"})
    assert verdicts[key].category == "transport"
    assert verdicts[key].decided_by == "correction"
    assert agent.decisions.calls == []


@pytest.mark.asyncio
async def test_a_low_confidence_answer_is_held_for_review(tmp_path):
    agent = build(StubDecisions(confidence=0.2), tmp_path)
    verdicts = await agent.categorise([SHOP])
    verdict = verdicts["CORNER GROCERS"]
    assert verdict.category == "uncategorised"
    assert verdict.needs_review


@pytest.mark.asyncio
async def test_an_answer_outside_your_categories_is_refused(tmp_path):
    agent = build(StubDecisions(choice="Groceries & Food"), tmp_path)
    assert (await agent.categorise([SHOP]))["CORNER GROCERS"].needs_review
