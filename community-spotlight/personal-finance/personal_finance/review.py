"""What you need in front of you to settle a counterparty the desk could not."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from personal_finance import counterparty
from personal_finance.contracts import LayoutProfile, Transaction, Verdict

EXAMPLES = 3


class ReviewItem(BaseModel):
    """One counterparty, with enough of its transactions to judge it by."""

    key: str
    suggested: str
    confidence: float | None
    occurrences: int
    total_out: Decimal
    total_in: Decimal
    examples: list[str]

    def headline(self) -> str:
        seen = f"{self.occurrences} transaction" + ("s" if self.occurrences != 1 else "")
        moved = f"out {self.total_out}, in {self.total_in}"
        return f"{self.key}  ({seen}, {moved})"


def pending(
    transactions: list[Transaction],
    verdicts: dict[str, Verdict],
    layout: LayoutProfile,
) -> list[ReviewItem]:
    """Counterparties held for review, heaviest first, so the biggest gaps close soonest."""
    grouped: dict[str, list[Transaction]] = {}
    for transaction in transactions:
        key = counterparty.key(transaction.description, layout.kinds)
        verdict = verdicts.get(key)
        if verdict and verdict.needs_review:
            grouped.setdefault(key, []).append(transaction)

    items = []
    for key, rows in grouped.items():
        verdict = verdicts[key]
        items.append(
            ReviewItem(
                key=key,
                suggested=verdict.category,
                confidence=verdict.confidence,
                occurrences=len(rows),
                total_out=sum((r.withdrawn for r in rows), Decimal(0)),
                total_in=sum((r.paid_in for r in rows), Decimal(0)),
                examples=[
                    f"{r.timestamp:%Y-%m-%d}  {r.signed_amount:>12}  {r.description[:70]}"
                    for r in rows[:EXAMPLES]
                ],
            )
        )
    return sorted(items, key=lambda i: i.total_out + i.total_in, reverse=True)
