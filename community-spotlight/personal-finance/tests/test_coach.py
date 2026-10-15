import json

import pytest

from personal_finance import layouts
from personal_finance.agents.coach import Coach
from personal_finance.notes import Notes
from tests.fixtures import paid

LAYOUT = layouts.load("mpesa-statement")


class StubLLM:
    def __init__(self, payload):
        self.payload, self.seen = payload, []

    async def generate(self, *, messages, temperature=0.3, response_format=None):
        self.seen.append(messages[-1]["content"])
        return {"content": json.dumps(self.payload), "cost_usd": 0.0003}


def rows():
    return [paid("SHOP", 100, 1), paid("SHOP", 300, 2), paid("BANK", 5000, 3)]


def build(payload):
    agent = Coach(LAYOUT)
    agent.llm = StubLLM(payload)
    return agent


def test_the_figures_add_up_before_any_model_sees_them():
    figures = Coach(LAYOUT).figures(rows(), notes=Notes("/dev/null"))
    assert figures["spent"] == 5400
    assert figures["places_paid"] == 2
    assert figures["by_category"][0]["share"] == 100  # all uncategorised here


def test_your_own_accounts_are_left_out_of_what_you_spent(tmp_path):
    notes = Notes(tmp_path / "notes.json")
    notes.claim("BANK")
    assert Coach(LAYOUT).figures(rows(), notes=notes)["spent"] == 400


@pytest.mark.asyncio
async def test_a_summary_is_kept_when_its_figures_were_given():
    agent = build({"headline": "You spent 5400 across 2 places.",
                   "paragraphs": ["All of it, 5400, sat in one category."],
                   "worth_knowing": ["3 transactions in total."]})
    summary = await agent.summarise(rows(), notes=Notes("/dev/null"))
    assert summary.headline.startswith("You spent 5400")
    assert summary.paragraphs and summary.worth_knowing
    assert summary.spent == 5400


@pytest.mark.asyncio
async def test_a_sentence_quoting_an_invented_figure_is_dropped():
    agent = build({"headline": "You spent 999999 this month.",
                   "paragraphs": ["You spent 5400 across 2 places."],
                   "worth_knowing": []})
    summary = await agent.summarise(rows(), notes=Notes("/dev/null"))
    assert summary.headline == ""
    assert summary.paragraphs == ["You spent 5400 across 2 places."]


@pytest.mark.asyncio
async def test_an_unreadable_answer_leaves_the_totals_intact():
    agent = Coach(LAYOUT)

    class Broken:
        async def generate(self, *, messages, temperature=0.3, response_format=None):
            return {"content": "not json", "cost_usd": 0.0}

    agent.llm = Broken()
    summary = await agent.summarise(rows(), notes=Notes("/dev/null"))
    assert summary.paragraphs == [] and summary.spent == 5400


@pytest.mark.asyncio
async def test_what_the_watchdog_already_said_is_passed_along():
    from personal_finance.contracts import Finding

    agent = build({"headline": "", "paragraphs": [], "worth_knowing": []})
    await agent.summarise(rows(), notes=Notes("/dev/null"),
                          findings=[Finding(kind="repeat", headline="SHOP paid twice")])
    assert "already_flagged" in agent.llm.seen[0]


class StubPeers:
    """Answers a peer request the way the auditor would, recording what was asked."""

    def __init__(self, reply):
        self.reply, self.asked = reply, []

    async def request(self, target, message, timeout=30, context=None):
        self.asked.append((target, message))
        return self.reply


@pytest.mark.asyncio
async def test_the_coach_asks_the_auditor_rather_than_working_it_out():
    agent = build({"headline": "", "paragraphs": [], "worth_knowing": []})
    agent.peers = StubPeers({
        "status": "success",
        "avoidable_total": "4901.64",
        "audit": {"lines": [
            {"what": "charges", "amount": "1628.00", "avoidable": True, "says": "fees"}
        ]},
    })
    await agent.summarise(rows(), notes=Notes("/dev/null"))
    target, message = agent.peers.asked[0]
    assert target == "auditor" and message["capability"] == "avoidable_cost"
    assert "4901.64" in agent.llm.seen[0]  # the agreed figure reached the summary


@pytest.mark.asyncio
async def test_the_coach_may_quote_the_agreed_figure():
    agent = build({"headline": "4901.64 of what left need not have.", "paragraphs": [],
                   "worth_knowing": []})
    agent.peers = StubPeers({
        "status": "success", "avoidable_total": "4901.64", "audit": {"lines": []},
    })
    summary = await agent.summarise(rows(), notes=Notes("/dev/null"))
    assert summary.headline.startswith("4901.64")


@pytest.mark.asyncio
async def test_a_coach_with_no_peers_still_writes_a_summary():
    agent = build({"headline": "You spent 5400 across 2 places.", "paragraphs": [],
                   "worth_knowing": []})
    summary = await agent.summarise(rows(), notes=Notes("/dev/null"))
    assert summary.headline.startswith("You spent 5400")


@pytest.mark.asyncio
async def test_an_auditor_that_has_nothing_is_not_quoted():
    agent = build({"headline": "", "paragraphs": [], "worth_knowing": []})
    agent.peers = StubPeers({"status": "failure", "error": "that statement has not been audited"})
    await agent.summarise(rows(), notes=Notes("/dev/null"))
    assert "avoidable" not in agent.llm.seen[0]
