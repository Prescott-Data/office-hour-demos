"""Who decides a category: you first, then the document, and only then the agent."""

from __future__ import annotations

from enum import Enum

from personal_finance import counterparty
from personal_finance.contracts import CategoryPolicy, LayoutProfile

UNCATEGORISED = "uncategorised"


class Decided(str, Enum):
    """Where a category came from, so any answer can be traced back."""

    CORRECTION = "correction"
    DOCUMENT = "document"
    AGENT = "agent"


def settle(
    description: str,
    layout: LayoutProfile,
    policy: CategoryPolicy,
    corrections: dict[str, str] | None = None,
) -> tuple[str, Decided] | None:
    """A category and where it came from, or None when only judgement will do."""
    key = counterparty.key(description, layout.kinds)
    corrected = (corrections or {}).get(key)
    if corrected and policy.allows(corrected):
        return corrected, Decided.CORRECTION
    stated = policy.by_kind.get(counterparty.kind(description, layout.kinds))
    if stated and policy.allows(stated):
        return stated, Decided.DOCUMENT
    return None


def needs_judgement(
    descriptions: list[str],
    layout: LayoutProfile,
    policy: CategoryPolicy,
    corrections: dict[str, str] | None = None,
) -> list[str]:
    """The distinct counterparties the agent has to think about, each asked about once."""
    pending = {
        counterparty.key(d, layout.kinds)
        for d in descriptions
        if settle(d, layout, policy, corrections) is None
    }
    return sorted(p for p in pending if p)
