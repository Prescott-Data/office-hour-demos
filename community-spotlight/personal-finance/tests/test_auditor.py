import json

import pytest

from personal_finance import layouts
from personal_finance.agents.auditor import Auditor
from personal_finance.desk import Desk
from personal_finance.notes import Notes
from tests.fixtures import paid
from tests.test_probes import charge

LAYOUT = layouts.load("mpesa-statement")


class StubLLM:
    """Answers the two prompts in turn: what to run, then what it means."""

    def __init__(self, *answers):
        self.answers, self.seen = list(answers), []

    async def generate(self, *, messages, temperature=0.2, response_format=None):
        self.seen.append(messages[-1]["content"])
        payload = self.answers.pop(0) if self.answers else {}
        return {"content": json.dumps(payload), "cost_usd": 0.0002}


def rows():
    return [paid("SHOP", 100, 1), charge(23, 1), charge(7, 2, "CHG2")]


def build(tmp_path, *answers):
    agent = Auditor(LAYOUT, desk=Desk("audit-test", tmp_path))
    agent.llm = StubLLM(*answers)
    return agent


@pytest.mark.asyncio
async def test_the_agent_chooses_what_to_measure(tmp_path):
    agent = build(tmp_path,
        {"run": [{"probe": "total_of_kind", "takes": {"kind": "charge"}}]},
        {"run": []},
        {"lines": []},
    )
    audit = await agent.audit(rows(), notes=Notes("/dev/null"))
    assert audit.probes_run == ["spending()", "total_of_kind(kind=charge)"]
    assert "probes_you_can_run" in agent.llm.seen[0]


@pytest.mark.asyncio
async def test_a_line_is_kept_when_its_figure_came_from_a_probe(tmp_path):
    agent = build(tmp_path,
        {"run": [{"probe": "total_of_kind", "takes": {"kind": "charge"}}]},
        {"run": []},  # the agent is asked a second time and wants nothing more
        {"lines": [{"what": "transaction charges", "amount": "30", "avoidable": True,
                    "says": "30 went on charges."}], "caveat": "Some charges are unavoidable."},
    )
    audit = await agent.audit(rows(), notes=Notes("/dev/null"))
    assert audit.avoidable_total == 30
    assert audit.caveat.startswith("Some charges")
    assert audit.headline() == "30 of what left need not have"


@pytest.mark.asyncio
async def test_an_invented_figure_is_dropped(tmp_path):
    agent = build(tmp_path,
        {"run": [{"probe": "total_of_kind", "takes": {"kind": "charge"}}]},
        {"run": []},
        {"lines": [{"what": "charges", "amount": "999999", "avoidable": True, "says": "no"}]},
    )
    assert (await agent.audit(rows(), notes=Notes("/dev/null"))).lines == []


@pytest.mark.asyncio
async def test_what_was_spent_rather_than_wasted_stays_out_of_the_total(tmp_path):
    agent = build(tmp_path,
        {"run": [{"probe": "biggest", "takes": {"how_many": "2"}}]},
        {"run": []},
        {"lines": [
            {"what": "charges", "amount": "30", "avoidable": True, "says": "fees"},
            {"what": "the shop", "amount": "100", "avoidable": False, "says": "you bought things"},
        ]},
    )
    audit = await agent.audit(rows(), notes=Notes("/dev/null"))
    assert len(audit.lines) == 2 and audit.avoidable_total == 30


@pytest.mark.asyncio
async def test_asking_for_nothing_ends_the_audit(tmp_path):
    agent = build(tmp_path, {"run": []})
    audit = await agent.audit(rows(), notes=Notes("/dev/null"))
    assert audit.lines == []
    assert audit.probes_run == ["spending()"]  # the orienting figure, and nothing asked for


@pytest.mark.asyncio
async def test_a_probe_the_agent_invents_returns_an_error_rather_than_crashing(tmp_path):
    agent = build(
        tmp_path,
        {"run": [{"probe": "guess_everything", "takes": {}}]},
        {"run": []},
        {"lines": []},
    )
    audit = await agent.audit(rows(), notes=Notes("/dev/null"))
    assert audit.probes_run == ["guess_everything()", "spending()"]
    assert audit.lines == []


@pytest.mark.asyncio
async def test_the_same_statement_is_only_worked_out_once(tmp_path):
    answers = (
        {"run": [{"probe": "total_of_kind", "takes": {"kind": "charge"}}]},
        {"run": []},
        {"lines": [{"what": "charges", "amount": "30", "avoidable": True, "says": "fees"}]},
    )
    first = build(tmp_path, *answers)
    await first.audit(rows(), notes=Notes("/dev/null"))
    asked_first = len(first.llm.seen)

    again = build(tmp_path, *answers)  # a fresh desk session, same ledger
    audit = await again.audit(rows(), notes=Notes("/dev/null"))
    assert again.llm.seen == []  # nothing was asked the second time
    assert audit.avoidable_total == 30 and asked_first == 3


@pytest.mark.asyncio
async def test_a_different_statement_is_worked_out_again(tmp_path):
    answers = ({"run": []},)
    agent = build(tmp_path, *answers)
    await agent.audit(rows(), notes=Notes("/dev/null"))
    other = build(tmp_path, {"run": []})
    await other.audit(rows()[:1], notes=Notes("/dev/null"))
    assert other.llm.seen  # a statement it has not seen is worked out


@pytest.mark.asyncio
async def test_asking_for_it_fresh_works_it_out_again(tmp_path):
    answers = ({"run": []},)
    agent = build(tmp_path, *answers)
    await agent.audit(rows(), notes=Notes("/dev/null"))
    again = build(tmp_path, {"run": []})
    await again.audit(rows(), notes=Notes("/dev/null"), fresh=True)
    assert again.llm.seen


@pytest.mark.asyncio
async def test_your_ruling_outranks_the_agent(tmp_path):
    from personal_finance.rulings import Rulings

    agent = build(
        tmp_path,
        {"run": [{"probe": "total_of_kind", "takes": {"kind": "charge"}}]},
        {"run": []},
        {"lines": [{"what": "transaction charges", "amount": "30", "avoidable": True,
                    "says": "fees"}]},
    )
    rulings = Rulings(tmp_path / "rulings.json")
    rulings.record("Transaction Charges", False)  # wording differs, the line is the same
    audit = await agent.audit(rows(), notes=Notes("/dev/null"), rulings=rulings)
    assert audit.avoidable_total == 0
    assert audit.lines[0].your_call is True
    assert audit.unruled() == []


@pytest.mark.asyncio
async def test_no_counterparty_name_reaches_the_model(tmp_path):
    agent = build(
        tmp_path,
        {"run": [{"probe": "biggest", "takes": {"how_many": "5"}}]},
        {"run": []},
        {"lines": []},
    )
    await agent.audit(rows(), notes=Notes("/dev/null"))
    shown = " ".join(agent.llm.seen)
    assert "SHOP" not in shown
    assert "counterparty 1" in shown


@pytest.mark.asyncio
async def test_the_name_comes_back_for_your_eyes(tmp_path):
    agent = build(
        tmp_path,
        {"run": [{"probe": "biggest", "takes": {"how_many": "5"}}]},
        {"run": []},
        {"lines": [{"what": "counterparty 1 payments", "amount": "100", "avoidable": False,
                    "says": "counterparty 1 took 100."}]},
    )
    audit = await agent.audit(rows(), notes=Notes("/dev/null"))
    assert audit.lines[0].what == "SHOP payments"
    assert "SHOP took 100" in audit.lines[0].says


@pytest.mark.asyncio
async def test_masking_can_be_turned_off_for_a_comparison(tmp_path):
    agent = build(
        tmp_path,
        {"run": [{"probe": "biggest", "takes": {"how_many": "5"}}]},
        {"run": []},
        {"lines": []},
    )
    await agent.audit(rows(), notes=Notes("/dev/null"), mask=False)
    assert "SHOP" in " ".join(agent.llm.seen)


@pytest.mark.asyncio
async def test_a_peer_is_handed_the_audit_already_worked_out(tmp_path):
    from personal_finance.agents.auditor import Audit, Line

    agent = build(tmp_path, {"run": []})
    rows_now = rows()
    kept = agent.desk.audits()
    audit = Audit(lines=[Line(what="charges", amount="30", avoidable=True, says="fees")],
                  spent="130")
    kept.data[Auditor.fingerprint(rows_now)] = json.loads(audit.model_dump_json())
    kept.save()

    message = type("Message", (), {"data": {
        "capability": "avoidable_cost", "statement": Auditor.fingerprint(rows_now)}})()
    reply = await agent.on_peer_request(message)
    assert reply["status"] == "success" and reply["avoidable_total"] == "30"
    assert agent.llm.seen == []  # answering a peer costs nothing


@pytest.mark.asyncio
async def test_a_peer_asking_about_an_unaudited_statement_is_told_so(tmp_path):
    agent = build(tmp_path, {"run": []})
    message = type("Message", (), {"data": {"capability": "avoidable_cost", "statement": "nope"}})()
    assert (await agent.on_peer_request(message))["status"] == "failure"


@pytest.mark.asyncio
async def test_a_peer_asking_about_something_else_is_left_to_others(tmp_path):
    agent = build(tmp_path, {"run": []})
    message = type("Message", (), {"data": {"capability": "making_tea"}})()
    assert await agent.on_peer_request(message) is None
