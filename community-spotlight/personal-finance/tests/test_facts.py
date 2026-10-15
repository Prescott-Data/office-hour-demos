from datetime import datetime
from decimal import Decimal

from personal_finance import facts, layouts
from personal_finance.notes import Notes
from tests.fixtures import paid

LAYOUT = layouts.load("mpesa-statement")
AS_OF = datetime(2026, 9, 30, 12, 0, 0)


def sheet_for(key, rows, notes=None, verdicts=None):
    built = facts.sheets(rows, LAYOUT, verdicts=verdicts, notes=notes or Notes("/dev/null"),
                         as_of=AS_OF)
    return next(s for s in built if s.key == key)


def test_a_sheet_states_the_spread_of_amounts():
    rows = [paid("SHOP", 100, 1), paid("SHOP", 300, 2), paid("SHOP", 200, 3)]
    sheet = sheet_for("SHOP", rows)
    assert (sheet.smallest, sheet.usual, sheet.largest) == (
        Decimal("100"), Decimal("200"), Decimal("300"))
    assert sheet.payments == 3


def test_same_day_pairs_carry_the_hours_between_them():
    rows = [paid("ZACH", 200, 1, hour=9), paid("ZACH", 200, 1, hour=17, reference="LATER")]
    pair = sheet_for("ZACH", rows).same_day_pairs[0]
    assert pair.hours_apart == 8.0
    assert pair.amounts == [Decimal("200"), Decimal("200")]


def test_payments_far_apart_are_not_paired():
    rows = [paid("ZACH", 200, 1), paid("ZACH", 200, 5)]
    assert sheet_for("ZACH", rows).same_day_pairs == []


def test_a_regular_payment_states_its_rhythm_and_silence():
    rows = [paid("RENT", 1000, day, hour=9) for day in (0, 31)]  # 1 August, 1 September
    sheet = sheet_for("RENT", rows)
    assert sheet.every_days == 31.0
    assert sheet.usual_day_of_month == 1 and sheet.months_landing_on_that_day == 2
    # the sheet states the silence; whether it is a missed payment is the agent's call
    assert sheet.days_since_last == 29


def test_the_account_paid_is_kept_so_two_paybills_are_distinguishable():
    assert sheet_for("SHOP", [paid("SHOP", 100, 1)]).accounts == ["1234567"]


def test_monthly_totals_are_broken_out():
    rows = [paid("SHOP", 100, 1), paid("SHOP", 400, 40)]
    assert sheet_for("SHOP", rows).by_month == {
        "2026-08": Decimal("100"), "2026-09": Decimal("400")}


def test_what_you_said_about_a_counterparty_appears_on_its_sheet(tmp_path):
    notes = Notes(tmp_path / "notes.json")
    notes.claim("SHOP")
    notes.dismiss("SHOP", "same_day_pairs")
    sheet = sheet_for("SHOP", [paid("SHOP", 100, 1)], notes=notes)
    assert sheet.mine and sheet.you_called_normal == ["same_day_pairs"]


def test_your_own_accounts_are_left_out_of_spending(tmp_path):
    notes = Notes(tmp_path / "notes.json")
    notes.claim("MY BANK")
    rows = [paid("SHOP", 100, 1), paid("MY BANK", 5000, 2)]
    built = facts.sheets(rows, LAYOUT, notes=notes, as_of=AS_OF)
    assert facts.spending(built) == Decimal("100")
