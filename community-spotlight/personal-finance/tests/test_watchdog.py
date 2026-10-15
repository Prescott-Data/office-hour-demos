import json

import pytest

from personal_finance import layouts
from personal_finance.agents.watchdog import Watchdog
from personal_finance.desk import Desk
from personal_finance.notes import Notes
from tests.fixtures import paid
from tests.test_probes import charge

LAYOUT = layouts.load("mpesa-statement")


class StubLLM:
    def __init__(self, *answers):
        self.answers, self.seen = list(answers), []

    async def generate(self, *, messages, temperature=0.0, response_format=None):
        self.seen.append(messages[-1]["content"])
        return {"content": json.dumps(self.answers.pop(0) if self.answers else {}),
                "cost_usd": 0.0002}


def rows():
    return [paid("SHOP", 100, 1), paid("SHOP", 100, 2), charge(23, 1)]


def build(tmp_path, *answers, user="watch-test"):
    agent = Watchdog(LAYOUT, desk=Desk(user, tmp_path))
    agent.llm = StubLLM(*answers)
    return agent


@pytest.mark.asyncio
async def test_the_watchdog_chooses_what_to_measure(tmp_path):
    agent = build(tmp_path, {"run": [{"probe": "biggest", "takes": {"how_many": "5"}}]},
                  {"run": []}, {"findings": []})
    await agent.review(rows(), notes=Notes("/dev/null"))
    assert "probes_you_can_run" in agent.llm.seen[0]


@pytest.mark.asyncio
async def test_no_name_reaches_the_model_and_comes_back_for_you(tmp_path):
    agent = build(
        tmp_path,
        {"run": [{"probe": "biggest", "takes": {"how_many": "5"}}]},
        {"run": []},
        {"findings": [{"about": "counterparty 1", "topic": "rising",
                       "say": "counterparty 1 took 200.", "why_it_matters": "watch it"}]},
    )
    findings = await agent.review(rows(), notes=Notes("/dev/null"))
    assert "SHOP" not in " ".join(agent.llm.seen)
    assert findings[0].headline.startswith("SHOP:")


@pytest.mark.asyncio
async def test_a_finding_quoting_an_invented_figure_is_dropped(tmp_path):
    agent = build(
        tmp_path,
        {"run": [{"probe": "biggest", "takes": {"how_many": "5"}}]},
        {"run": []},
        {"findings": [{"about": "counterparty 1", "topic": "rising", "say": "it took 999999."}]},
    )
    assert await agent.review(rows(), notes=Notes("/dev/null")) == []


@pytest.mark.asyncio
async def test_the_same_statement_is_only_judged_once(tmp_path):
    answers = (
        {"run": [{"probe": "biggest", "takes": {"how_many": "5"}}]},
        {"run": []},
        {"findings": [{"about": "counterparty 1", "topic": "rising", "say": "it took 200."}]},
    )
    first = build(tmp_path, *answers)
    await first.review(rows(), notes=Notes("/dev/null"))
    again = build(tmp_path, *answers)
    findings = await again.review(rows(), notes=Notes("/dev/null"))
    assert again.llm.seen == [] and len(findings) == 1


@pytest.mark.asyncio
async def test_what_you_called_normal_never_comes_back(tmp_path):
    answers = (
        {"run": [{"probe": "biggest", "takes": {"how_many": "5"}}]},
        {"run": []},
        {"findings": [{"about": "counterparty 1", "topic": "repeat", "say": "paid 100 twice."}]},
    )
    agent = build(tmp_path, *answers)
    notes = Notes(tmp_path / "notes.json")
    assert len(await agent.review(rows(), notes=notes)) == 1

    notes.dismiss("SHOP", "repeat")
    again = build(tmp_path, *answers)
    assert await again.review(rows(), notes=notes) == []
