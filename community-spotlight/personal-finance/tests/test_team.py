import pytest

from personal_finance import team
from personal_finance.agents.categoriser import Categoriser
from personal_finance.agents.coach import Coach
from personal_finance.agents.watchdog import Watchdog


def test_a_desk_is_a_mesh_of_five_agents():
    mesh = team.build_mesh("tester")
    roles = sorted(agent.role for agent in mesh.agents)
    assert roles == ["auditor", "categoriser", "coach", "proposer", "watchdog"]


def test_agents_are_found_by_what_they_do_not_by_name():
    mesh = team.build_mesh("tester")
    assert isinstance(team.member(mesh, "transaction_categorisation"), Categoriser)
    assert isinstance(team.member(mesh, "spending_oversight"), Watchdog)
    assert isinstance(team.member(mesh, "spending_summary"), Coach)
    assert team.member(mesh, "avoidable_cost").role == "auditor"
    assert team.member(mesh, "category_proposal").role == "proposer"


def test_a_capability_nobody_offers_is_an_error():
    with pytest.raises(LookupError):
        team.member(team.build_mesh("tester"), "making_tea")


def test_each_person_gets_their_own_desk():
    mine = {a.agent_id for a in team.build_mesh("marrie").agents}
    theirs = {a.agent_id for a in team.build_mesh("someone").agents}
    assert not mine & theirs


def test_building_a_desk_contacts_nothing():
    mesh = team.build_mesh("tester")
    categoriser = team.member(mesh, "transaction_categorisation")
    assert categoriser.questions_asked == 0
    assert categoriser.spend_usd == 0.0


@pytest.mark.asyncio
async def test_a_request_without_a_statement_says_so():
    with pytest.raises(ValueError, match="statement"):
        await team.submit_task(team.build_mesh("tester"), "  ")
