from datetime import timedelta
from decimal import Decimal

from personal_finance import layouts
from personal_finance.contracts import Transaction
from personal_finance.notes import Notes
from personal_finance.probes import PROBES, Toolbox
from tests.fixtures import START, paid

LAYOUT = layouts.load("mpesa-statement")


def charge(amount, day, reference="CHG"):
    return Transaction(
        reference=reference, timestamp=START + timedelta(days=day),
        description="Customer Transfer of Funds Charge", status="Completed",
        withdrawn=Decimal(str(amount)), balance=Decimal("100"), source="fixture")


def box(rows, notes=None):
    return Toolbox(rows, LAYOUT, notes or Notes("/dev/null"))


def test_every_probe_says_what_it_asks():
    assert {p.name for p in PROBES} >= {"spending", "total_of_kind", "repeats", "borrowing"}
    assert all(probe.asks for probe in PROBES)


def test_a_probe_that_does_not_exist_says_so():
    assert "error" in box([paid("SHOP", 100, 1)]).run("read_my_mind")


def test_total_of_kind_sums_what_the_statement_labels():
    rows = [paid("SHOP", 100, 1), charge(23, 1), charge(7, 2, "CHG2")]
    answer = box(rows).run("total_of_kind", kind="charge")
    assert answer["payments"] == 2 and answer["paid_out"] == Decimal("30")


def test_repeats_only_counts_the_same_amount_close_together():
    rows = [paid("SHOP", 250, 1, hour=9), paid("SHOP", 250, 1, hour=9, reference="AGAIN")]
    found = box(rows).run("repeats", within_hours=0.25)
    assert len(found["found"]) == 1 and found["repeated_value"] == Decimal("250")


def test_repeats_leaves_out_what_you_called_normal(tmp_path):
    notes = Notes(tmp_path / "notes.json")
    notes.dismiss("SHOP", "same_day_pairs")
    rows = [paid("SHOP", 250, 1, hour=9), paid("SHOP", 250, 1, hour=9, reference="AGAIN")]
    assert box(rows, notes).run("repeats", within_hours=0.25)["found"] == []


def test_borrowing_reports_the_difference():
    rows = [
        Transaction(reference="OD1", timestamp=START, description="OverDraft of Credit Party",
                    status="Completed", paid_in=Decimal("500"), balance=Decimal("500"),
                    source="fixture"),
        Transaction(reference="OD2", timestamp=START + timedelta(days=1),
                    description="OD Loan Repayment to 232323 - M-PESA", status="Completed",
                    withdrawn=Decimal("535"), balance=Decimal("0"), source="fixture"),
    ]
    answer = box(rows).run("borrowing")
    assert answer["borrowed"] == Decimal("500") and answer["difference"] == Decimal("35")


def test_spending_leaves_out_your_own_accounts(tmp_path):
    notes = Notes(tmp_path / "notes.json")
    notes.claim("MY BANK")
    rows = [paid("SHOP", 100, 1), paid("MY BANK", 5000, 2)]
    assert box(rows, notes).run("spending")["spent"] == Decimal("100")


def test_biggest_ranks_by_what_left():
    rows = [paid("BIG", 900, 1), paid("SMALL", 100, 2)]
    found = box(rows).run("biggest", how_many=1)["found"]
    assert [f["place"] for f in found] == ["BIG"]


def test_recurring_says_how_late_a_rhythm_is():
    from datetime import datetime
    rows = [paid("RENT", 1000, day, hour=9) for day in (0, 31)]
    found = box(rows).run("recurring", least_payments=2)["found"][0]
    assert found["every_days"] == 31.0
    # the probe states lateness, so judging it takes no arithmetic
    assert found["days_overdue"] == round(found["days_since_last"] - 31.0, 1)
    assert isinstance(datetime.now(), datetime)


def test_several_payments_in_one_day_are_not_a_rhythm():
    rows = [paid("SHOP", 100, 1, hour=hour) for hour in (8, 10, 12, 14)]
    assert box(rows).run("recurring", least_payments=3)["found"] == []
