import pytest

from personal_finance import layouts, profiles
from personal_finance.agents.categoriser import Categoriser
from personal_finance.corrections import Corrections
from personal_finance.judgements import Judgements
from tests.test_categoriser import SHOP, StubDecisions

LAYOUT = layouts.load("mpesa-statement")
POLICY = profiles.categories()


def agent_with(tmp_path, stub=None):
    agent = Categoriser(
        LAYOUT,
        POLICY,
        corrections=Corrections(tmp_path / "corrections.json"),
        judgements=Judgements(tmp_path / "judgements.json"),
    )
    agent.decisions = stub
    return agent


@pytest.mark.asyncio
async def test_a_correction_survives_a_restart_and_stops_the_asking(tmp_path):
    first = agent_with(tmp_path, StubDecisions())
    key = first.correct(SHOP, "eating_out")

    second = agent_with(tmp_path, StubDecisions())  # a fresh desk, same ledger
    verdicts = await second.categorise([SHOP])
    assert verdicts[key].category == "eating_out"
    assert verdicts[key].decided_by == "correction"
    assert second.decisions.calls == []


def test_a_category_you_do_not_keep_is_refused(tmp_path):
    agent = agent_with(tmp_path)
    with pytest.raises(ValueError):
        agent.correct(SHOP, "holidays")
    assert len(agent.corrections) == 0


def test_the_ledger_is_plain_json_you_can_read(tmp_path):
    agent = agent_with(tmp_path)
    agent.correct(SHOP, "groceries")
    written = (tmp_path / "corrections.json").read_text()
    assert "CORNER GROCERS" in written and "groceries" in written


def test_forgetting_a_correction_puts_it_back_to_judgement(tmp_path):
    agent = agent_with(tmp_path, StubDecisions())
    key = agent.correct(SHOP, "groceries")
    assert agent.corrections.forget(key)
    assert key not in agent.corrections
