from decimal import Decimal

import pytest

from personal_finance.sources.table import LayoutMismatch, extract, to_amount
from tests.fixtures import PROFILE, statement_words


def rows():
    return extract(statement_words(), PROFILE, source="fixture")


def test_finds_every_row_and_no_page_furniture():
    assert [t.reference for t in rows()] == ["AAA1111111", "BBB2222222", "CCC3333333"]


def test_wrapped_line_joins_the_row_above_it():
    assert rows()[0].description == "Merchant Payment to 1234567 - CORNER SHOP"


def test_money_out_is_positive_in_its_own_column():
    first = rows()[0]
    assert (first.withdrawn, first.paid_in, first.balance) == (
        Decimal("250.00"), Decimal(0), Decimal("1250.00"))


def test_money_in_lands_in_paid_in():
    last = rows()[2]
    assert (last.paid_in, last.withdrawn) == (Decimal("20000.00"), Decimal(0))


def test_signed_amount_reads_as_direction():
    assert [t.signed_amount for t in rows()] == [
        Decimal("-250.00"), Decimal("-23.00"), Decimal("20000.00")]


def test_amounts_keep_their_precision():
    assert to_amount("1,234.56") == Decimal("1234.56")


def test_a_document_that_does_not_match_is_rejected():
    with pytest.raises(LayoutMismatch):
        extract([{"text": "nothing", "x0": 1.0, "x1": 5.0, "top": 1.0}], PROFILE, source="x")


def test_the_footer_does_not_become_part_of_the_row_above_it():
    from tests.fixtures import CHAR_WIDTH, header, row, word

    words = header(50)
    words += row(70, "AAA1111111", "2026-08-05 09:10:00", "Merchant Payment", "Completed",
                 withdrawn="-250.00", balance="1,250.00")
    disclaimer = "Disclaimer: Any personal information shared should be handled with care"
    offset = 0.0
    for token in disclaimer.split():
        words.append(word(token, 38 + offset, 90))
        offset += CHAR_WIDTH * len(token) + 2
    rows = extract(words, PROFILE, source="fixture")
    assert len(rows) == 1
    assert "Disclaimer" not in rows[0].description
    assert rows[0].description == "Merchant Payment"
