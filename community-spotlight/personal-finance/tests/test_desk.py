import pytest

from personal_finance import layouts
from personal_finance.agents.categoriser import Categoriser
from personal_finance.desk import Desk
from tests.test_categoriser import SHOP, StubDecisions

LAYOUT = layouts.load("mpesa-statement")


def agent_for(desk, stub=None):
    agent = Categoriser(
        LAYOUT,
        desk.categories().policy(),
        corrections=desk.corrections(),
        judgements=desk.judgements(),
    )
    agent.decisions = stub
    return agent


def test_each_person_keeps_their_own_categories_and_corrections(tmp_path):
    mine, theirs = Desk("marrie", tmp_path), Desk("someone-else", tmp_path)
    agent_for(mine).correct(SHOP, "groceries")
    assert "CORNER GROCERS" in mine.corrections()
    assert "CORNER GROCERS" not in theirs.corrections()


def test_a_new_desk_is_seeded_with_the_default_categories(tmp_path):
    catalogue = Desk("fresh", tmp_path).categories()
    assert "friends_and_family" in catalogue.policy().categories
    assert not catalogue.approved


def test_approving_a_set_is_recorded(tmp_path):
    catalogue = Desk("fresh", tmp_path).categories()
    catalogue.approve()
    assert Desk("fresh", tmp_path).categories().approved


@pytest.mark.asyncio
async def test_changing_the_categories_invalidates_earlier_judgements(tmp_path):
    desk = Desk("marrie", tmp_path)
    first = agent_for(desk, StubDecisions())
    await first.categorise([SHOP])
    assert first.questions_asked == 1

    again = agent_for(desk, StubDecisions())
    await again.categorise([SHOP])
    assert again.questions_asked == 0  # the cache answers

    desk.categories().add("friends_and_family_extra", "A category that did not exist before.")
    after = agent_for(desk, StubDecisions())
    await after.categorise([SHOP])
    assert after.questions_asked == 1  # the option list changed, so it asks again


def test_a_renamed_category_carries_its_stated_kinds(tmp_path):
    catalogue = Desk("fresh", tmp_path).categories()
    assert catalogue.rename("fees_and_charges", "bank_fees")
    policy = catalogue.policy()
    assert policy.by_kind["charge"] == "bank_fees"
    assert "fees_and_charges" not in policy.categories


def test_uncategorised_cannot_be_removed(tmp_path):
    catalogue = Desk("fresh", tmp_path).categories()
    assert not catalogue.remove("uncategorised")


def test_a_category_can_be_renamed_and_removed(tmp_path):
    catalogue = Desk("fresh", tmp_path).categories()
    catalogue.add("online_services", "Things paid for online.")
    assert catalogue.rename("online_services", "subscriptions")
    assert "subscriptions" in catalogue.policy().categories
    assert catalogue.remove("subscriptions")
    assert "subscriptions" not in catalogue.policy().categories


def test_a_placement_you_set_can_be_undone(tmp_path):
    desk = Desk("fresh", tmp_path)
    corrections = desk.corrections()
    corrections.record("HARBOUR CAPITAL LTD", "shopping")
    assert corrections.forget("HARBOUR CAPITAL LTD")
    assert "HARBOUR CAPITAL LTD" not in desk.corrections()


def test_replacing_your_categories_keeps_a_home_for_stated_rows(tmp_path):
    catalogue = Desk("fresh", tmp_path).categories()
    catalogue.replace({"family_and_friends": "People I help out."})
    policy = catalogue.policy()
    assert policy.by_kind["charge"] == "fees_and_charges"
    assert "fees_and_charges" in policy.categories
    assert "family_and_friends" in policy.categories


def test_a_set_that_already_lost_its_mappings_heals_on_load(tmp_path):
    catalogue = Desk("fresh", tmp_path).categories()
    catalogue.data["by_kind"] = {}
    catalogue.data["categories"] = {"only_mine": "Just this.", "uncategorised": "Nothing fits."}
    catalogue.save()
    healed = Desk("fresh", tmp_path).categories().policy()
    assert healed.by_kind and "only_mine" in healed.categories


def test_merging_folds_one_category_into_another(tmp_path):
    catalogue = Desk("fresh", tmp_path).categories()
    catalogue.add("loan_repayments", "Money I send to repay loans.")
    assert catalogue.merge("loan_and_overdraft", "loan_repayments")
    policy = catalogue.policy()
    assert "loan_and_overdraft" not in policy.categories
    assert policy.by_kind["overdraft"] == "loan_repayments"  # stated rows follow the merge


def test_a_category_cannot_be_merged_into_itself_or_lose_uncategorised(tmp_path):
    catalogue = Desk("fresh", tmp_path).categories()
    assert not catalogue.merge("groceries", "groceries")
    assert not catalogue.merge("uncategorised", "groceries")
    assert not catalogue.merge("groceries", "nothing_like_this")
