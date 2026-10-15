"""Everything known about a counterparty, stated as figures. Nothing here decides what is odd."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from statistics import median

from pydantic import BaseModel, Field

from personal_finance import counterparty
from personal_finance.contracts import LayoutProfile, Transaction, Verdict
from personal_finance.notes import Notes

CLOSE_ENOUGH_HOURS = 24
MOST_PAIRS = 6


class SamePair(BaseModel):
    """Two payments to the same place close together, with how close and whether they match."""

    hours_apart: float
    amounts: list[Decimal]
    same_amount: bool
    references: list[str]


class FactSheet(BaseModel):
    """One counterparty, described only in figures and dates."""

    key: str
    accounts: list[str] = Field(default_factory=list)
    category: str = "uncategorised"
    kinds: list[str] = Field(default_factory=list)
    mine: bool = False
    you_called_normal: list[str] = Field(default_factory=list)

    payments: int = 0
    receipts: int = 0
    paid_out: Decimal = Decimal(0)
    paid_in: Decimal = Decimal(0)
    smallest: Decimal = Decimal(0)
    usual: Decimal = Decimal(0)
    largest: Decimal = Decimal(0)

    first_seen: str = ""
    last_seen: str = ""
    days_since_last: int = 0
    every_days: float | None = None  # the middle gap between payments
    gap_spread_days: float | None = None  # how much the gaps vary
    usual_day_of_month: int | None = None
    months_landing_on_that_day: int = 0

    same_day_pairs: list[SamePair] = Field(default_factory=list)  # only genuine repeats
    most_in_one_day: int = 0
    by_month: dict[str, Decimal] = Field(default_factory=dict)
    share_of_category: Decimal = Decimal(0)


def _pairs(rows: list[Transaction]) -> list[SamePair]:
    pairs = []
    for index, first in enumerate(rows):
        for other in rows[index + 1 :]:
            hours = (other.timestamp - first.timestamp).total_seconds() / 3600
            if hours > CLOSE_ENOUGH_HOURS:
                break
            pairs.append(
                SamePair(
                    hours_apart=round(hours, 2),
                    amounts=[first.withdrawn, other.withdrawn],
                    same_amount=first.withdrawn == other.withdrawn,
                    references=[first.reference, other.reference],
                )
            )
    # only the same amount twice is a repeat; different amounts an hour apart is just a busy day
    pairs = [pair for pair in pairs if pair.same_amount]
    pairs.sort(key=lambda p: p.hours_apart)
    return pairs[:MOST_PAIRS]


def sheets(
    transactions: list[Transaction],
    layout: LayoutProfile,
    verdicts: dict[str, Verdict] | None = None,
    notes: Notes | None = None,
    as_of: datetime | None = None,
) -> list[FactSheet]:
    """A sheet per counterparty, ordered by how much money passed through it."""
    verdicts, notes = verdicts or {}, notes or Notes()
    grouped: dict[str, list[Transaction]] = defaultdict(list)
    for transaction in transactions:
        grouped[counterparty.key(transaction.description, layout.kinds)].append(transaction)

    latest = as_of or max((t.timestamp for t in transactions), default=datetime.now())
    built = []
    for key, rows in grouped.items():
        rows.sort(key=lambda r: r.timestamp)
        out = [r for r in rows if r.withdrawn]
        amounts = [r.withdrawn for r in out]
        gaps = [
            (b.timestamp - a.timestamp).total_seconds() / 86400
            for a, b in zip(out, out[1:], strict=False)
        ]
        days = Counter(r.timestamp.day for r in out)
        favourite = days.most_common(1)[0] if days else None
        months: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
        for row in rows:
            months[f"{row.timestamp:%Y-%m}"] += row.withdrawn

        verdict = verdicts.get(key)
        built.append(
            FactSheet(
                key=key,
                accounts=sorted({counterparty.account(r.description) for r in rows} - {""}),
                category=verdict.category if verdict else "uncategorised",
                kinds=sorted({counterparty.kind(r.description, layout.kinds) for r in rows}),
                mine=notes.mine(key),
                you_called_normal=notes.normal(key),
                payments=len(out),
                receipts=len(rows) - len(out),
                paid_out=sum(amounts, Decimal(0)),
                paid_in=sum((r.paid_in for r in rows), Decimal(0)),
                smallest=min(amounts, default=Decimal(0)),
                usual=Decimal(str(median(float(a) for a in amounts))) if amounts else Decimal(0),
                largest=max(amounts, default=Decimal(0)),
                first_seen=f"{rows[0].timestamp:%Y-%m-%d}",
                last_seen=f"{rows[-1].timestamp:%Y-%m-%d}",
                days_since_last=(latest - rows[-1].timestamp).days,
                every_days=round(median(gaps), 1) if gaps else None,
                gap_spread_days=round(max(gaps) - min(gaps), 1) if gaps else None,
                usual_day_of_month=favourite[0] if favourite else None,
                months_landing_on_that_day=favourite[1] if favourite else 0,
                same_day_pairs=_pairs(out),
                most_in_one_day=max(Counter(r.timestamp.date() for r in out).values(), default=0),
                by_month={month: total for month, total in sorted(months.items())},
            )
        )

    spent_by_category: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    for sheet in built:
        spent_by_category[sheet.category] += sheet.paid_out
    for sheet in built:
        whole = spent_by_category[sheet.category]
        if whole:
            sheet.share_of_category = (sheet.paid_out / whole * 100).quantize(Decimal("0.1"))

    return sorted(built, key=lambda s: s.paid_out, reverse=True)


def spending(sheets_: list[FactSheet]) -> Decimal:
    """What actually left, with movements between your own accounts left out."""
    return sum((s.paid_out for s in sheets_ if not s.mine), Decimal(0))
