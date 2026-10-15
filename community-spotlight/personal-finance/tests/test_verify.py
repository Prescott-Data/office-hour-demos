from decimal import Decimal

from personal_finance.sources.table import extract
from personal_finance.verify import check_balances
from tests.fixtures import PROFILE, statement_words


def test_a_correct_reading_reconciles():
    verdict = check_balances(extract(statement_words(), PROFILE, source="fixture"))
    assert verdict.ok
    assert verdict.checked == 2
    assert verdict.oldest_first is False


def test_a_misread_amount_is_caught():
    transactions = extract(statement_words(), PROFILE, source="fixture")
    transactions[0].withdrawn = Decimal("2500.00")  # a digit read wrong
    verdict = check_balances(transactions)
    assert not verdict.ok
    assert verdict.breaks[0].difference == Decimal("2250.00")


def test_summary_says_which_way_the_statement_runs():
    verdict = check_balances(extract(statement_words(), PROFILE, source="fixture"))
    assert verdict.summary() == "2 rows reconcile (newest first)"


def test_rows_sharing_a_second_are_ordered_by_what_reconciles():
    from tests.fixtures import tied_statement_words
    verdict = check_balances(extract(tied_statement_words(), PROFILE, source="fixture"))
    assert verdict.ok, verdict.summary()


def test_the_opening_group_is_resolved_against_the_row_after_it():
    from personal_finance.verify import in_time_order, resolve_ties
    from tests.fixtures import tied_statement_words
    ordered, _ = in_time_order(extract(tied_statement_words(), PROFILE, source="fixture"))
    assert [t.reference for t in ordered] == ["CCC3333333", "BBB2222222", "AAA1111111"]
    assert resolve_ties(ordered) == ordered
