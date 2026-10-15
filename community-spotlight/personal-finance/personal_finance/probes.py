"""Probes an agent can run over a statement. Each returns figures; none decides what they mean."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from pydantic import BaseModel, Field

from personal_finance import counterparty, facts
from personal_finance.contracts import LayoutProfile, Transaction
from personal_finance.notes import Notes


class Probe(BaseModel):
    """One question the agent can ask of the numbers, and what it needs to ask it."""

    name: str
    asks: str
    takes: dict[str, str] = Field(default_factory=dict)


PROBES = [
    Probe(
        name="spending",
        asks="What left in total, leaving out movements between their own accounts.",
    ),
    Probe(
        name="total_of_kind",
        asks="What the statement itself labels as this kind of row, summed.",
        takes={"kind": "one of: charge, airtime, data, overdraft, overdraft_repayment, "
                       "withdrawal, deposit, send_money, merchant, paybill, received"},
    ),
    Probe(
        name="repeats",
        asks="Payments of the same amount to the same place within a window.",
        takes={"within_hours": "a number, for example 0.25 for a quarter of an hour"},
    ),
    Probe(
        name="borrowing",
        asks="What was borrowed against what was repaid, and the difference.",
    ),
    Probe(
        name="recurring",
        asks="Places paid on a rhythm of a day or more, with the gap, the total and how late "
             "the next one is.",
        takes={"least_payments": "a number, for example 3"},
    ),
    Probe(
        name="month_changes",
        asks="How much each place took in each month, so a rise or a stop is visible.",
        takes={"how_many": "a number, for example 10"},
    ),
    Probe(
        name="biggest",
        asks="The places that took the most, with counts and their usual amount.",
        takes={"how_many": "a number, for example 10"},
    ),
]


class Toolbox:
    """The probes, bound to one statement."""

    def __init__(
        self,
        transactions: list[Transaction],
        layout: LayoutProfile,
        notes: Notes | None = None,
    ):
        self.transactions = transactions
        self.layout = layout
        self.notes = notes
        self.sheets = [s for s in facts.sheets(transactions, layout, notes=notes) if not s.mine]

    def run(self, name: str, **takes: Any) -> dict:
        probe: Callable | None = getattr(self, f"_{name}", None)
        if probe is None:
            return {"error": f"there is no probe called {name!r}"}
        try:
            return probe(**takes)
        except (TypeError, ValueError) as exc:
            return {"error": f"{name} could not run: {exc}"}

    def _spending(self) -> dict:
        return {"spent": facts.spending(self.sheets), "places": len(self.sheets)}

    def _total_of_kind(self, kind: str) -> dict:
        rows = [
            t
            for t in self.transactions
            if counterparty.kind(t.description, self.layout.kinds) == kind
        ]
        return {
            "kind": kind,
            "payments": len(rows),
            "paid_out": sum((t.withdrawn for t in rows), Decimal(0)),
            "paid_in": sum((t.paid_in for t in rows), Decimal(0)),
        }

    def _repeats(self, within_hours: float = 0.25) -> dict:
        found = []
        for sheet in self.sheets:
            if "same_day_pairs" in sheet.you_called_normal:
                continue
            for pair in sheet.same_day_pairs:
                if pair.same_amount and pair.hours_apart <= float(within_hours):
                    found.append({
                        "place": sheet.key,
                        "amount": pair.amounts[0],
                        "hours_apart": pair.hours_apart,
                    })
        return {
            "within_hours": float(within_hours),
            "found": found,
            "repeated_value": sum((Decimal(str(f["amount"])) for f in found), Decimal(0)),
        }

    def _borrowing(self) -> dict:
        borrowed = self._total_of_kind("overdraft")
        repaid = self._total_of_kind("overdraft_repayment")
        return {
            "times_borrowed": borrowed["payments"],
            "borrowed": borrowed["paid_in"],
            "repaid": repaid["paid_out"],
            "difference": repaid["paid_out"] - borrowed["paid_in"],
        }

    def _recurring(self, least_payments: int = 3) -> dict:
        rhythms = [
            {
                "place": sheet.key,
                "payments": sheet.payments,
                "every_days": sheet.every_days,
                "usual": sheet.usual,
                "paid_out": sheet.paid_out,
                "days_since_last": sheet.days_since_last,
                # positive means it is late against its own rhythm
                "days_overdue": round(sheet.days_since_last - sheet.every_days, 1),
            }
            for sheet in self.sheets
            if sheet.payments >= int(least_payments) and (sheet.every_days or 0) >= 1
        ]
        return {"found": sorted(rhythms, key=lambda r: r["paid_out"], reverse=True)[:15]}

    def _month_changes(self, how_many: int = 10) -> dict:
        moved = []
        for sheet in self.sheets:
            months = sorted(sheet.by_month.items())
            if len(months) < 2:
                continue
            (_, before), (_, after) = months[-2], months[-1]
            # a month change answers what moved; a rhythm comes from recurring, which guards it
            moved.append({
                "place": sheet.key,
                "by_month": {month: total for month, total in months},
                "change": after - before,
            })
        moved.sort(key=lambda m: abs(m["change"]), reverse=True)
        return {"found": moved[: int(how_many)]}

    def _biggest(self, how_many: int = 10) -> dict:
        return {
            "found": [
                {
                    "place": sheet.key,
                    "paid_out": sheet.paid_out,
                    "payments": sheet.payments,
                    "usual": sheet.usual,
                    "category": sheet.category,
                }
                for sheet in self.sheets[: int(how_many)]
            ]
        }
