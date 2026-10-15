from decimal import Decimal

from personal_finance import layouts, review
from personal_finance.contracts import Verdict
from personal_finance.sources.table import extract
from tests.fixtures import PROFILE, statement_words

LAYOUT = layouts.load("mpesa-statement")


def rows():
    return extract(statement_words(), PROFILE, source="fixture")


def verdicts_for(key, needs_review=True, confidence=0.3):
    return {key: Verdict(key=key, category="uncategorised", decided_by="agent",
                         confidence=confidence, needs_review=needs_review)}


def test_only_counterparties_held_for_review_appear():
    transactions = rows()
    from personal_finance import counterparty
    key = counterparty.key(transactions[0].description, LAYOUT.kinds)
    items = review.pending(transactions, verdicts_for(key), LAYOUT)
    assert [i.key for i in items] == [key]
    assert items[0].occurrences == 1


def test_settled_counterparties_are_left_alone():
    transactions = rows()
    from personal_finance import counterparty
    key = counterparty.key(transactions[0].description, LAYOUT.kinds)
    assert review.pending(transactions, verdicts_for(key, needs_review=False), LAYOUT) == []


def test_an_item_carries_what_you_need_to_judge_it():
    transactions = rows()
    from personal_finance import counterparty
    key = counterparty.key(transactions[0].description, LAYOUT.kinds)
    item = review.pending(transactions, verdicts_for(key), LAYOUT)[0]
    assert item.total_out == Decimal("250.00")
    assert item.examples and "2026-08-05" in item.examples[0]
    assert "250" in item.headline()


def test_the_heaviest_counterparty_comes_first():
    transactions = rows()
    from personal_finance import counterparty
    keys = {counterparty.key(t.description, LAYOUT.kinds): t for t in transactions}
    verdicts = {}
    for key in keys:
        verdicts.update(verdicts_for(key))
    items = review.pending(transactions, verdicts, LAYOUT)
    totals = [i.total_out + i.total_in for i in items]
    assert totals == sorted(totals, reverse=True)
