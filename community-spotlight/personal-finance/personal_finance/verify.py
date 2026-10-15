"""Prove a statement was read correctly, using the arithmetic it carries."""

from __future__ import annotations

from decimal import Decimal
from itertools import permutations

from pydantic import BaseModel

from personal_finance.contracts import Transaction

TOLERANCE = Decimal("0.01")


class BalanceBreak(BaseModel):
    """One place where the running balance does not follow from the previous row."""

    reference: str
    expected: Decimal
    found: Decimal

    @property
    def difference(self) -> Decimal:
        return self.found - self.expected


class Verdict(BaseModel):
    """Whether a reading of a statement can be trusted."""

    checked: int
    breaks: list[BalanceBreak]
    oldest_first: bool

    @property
    def ok(self) -> bool:
        return not self.breaks

    def summary(self) -> str:
        order = "oldest first" if self.oldest_first else "newest first"
        if self.ok:
            return f"{self.checked} rows reconcile ({order})"
        return f"{len(self.breaks)} of {self.checked} rows do not reconcile ({order})"


MAX_TIE_GROUP = 6


def in_time_order(transactions: list[Transaction]) -> tuple[list[Transaction], bool]:
    if len(transactions) < 2:
        return list(transactions), True
    oldest_first = transactions[0].timestamp <= transactions[-1].timestamp
    ordered = list(transactions) if oldest_first else list(reversed(transactions))
    return resolve_ties(ordered), oldest_first


def _chains(rows: list[Transaction], opening: Decimal) -> bool:
    balance = opening
    for row in rows:
        balance = balance + row.paid_in - row.withdrawn
        if abs(balance - row.balance) > TOLERANCE:
            return False
        balance = row.balance
    return True


def resolve_ties(ordered: list[Transaction]) -> list[Transaction]:
    """Rows sharing a timestamp carry no order of their own, so use the one that reconciles."""
    groups: list[list[Transaction]] = []
    for row in ordered:
        if groups and groups[-1][0].timestamp == row.timestamp:
            groups[-1].append(row)
        else:
            groups.append([row])

    settled: list[Transaction] = []
    for index, group in enumerate(groups):
        if 1 < len(group) <= MAX_TIE_GROUP:
            following = groups[index + 1][0] if index + 1 < len(groups) else None
            group = list(_best_order(group, settled, following))
        settled += group
    return settled


def _best_order(
    group: list[Transaction],
    settled: list[Transaction],
    following: Transaction | None,
) -> tuple[Transaction, ...] | list[Transaction]:
    if settled:
        opening = settled[-1].balance
        candidates = (p for p in permutations(group) if _chains(list(p), opening))
    else:
        # the opening group has nothing before it, so judge it by itself and by what follows
        candidates = (
            p
            for p in permutations(group)
            if _chains(list(p[1:]), p[0].balance)
            and (following is None or _chains([following], p[-1].balance))
        )
    return next(candidates, group)


def check_balances(transactions: list[Transaction]) -> Verdict:
    ordered, oldest_first = in_time_order(transactions)
    breaks = []
    for previous, current in zip(ordered, ordered[1:], strict=False):
        expected = previous.balance + current.paid_in - current.withdrawn
        if abs(expected - current.balance) > TOLERANCE:
            breaks.append(
                BalanceBreak(reference=current.reference, expected=expected, found=current.balance)
            )
    return Verdict(checked=max(len(ordered) - 1, 0), breaks=breaks, oldest_first=oldest_first)
