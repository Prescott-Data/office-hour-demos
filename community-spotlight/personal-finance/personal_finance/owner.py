"""Whose statement this is, read from the document rather than asked for."""

from __future__ import annotations

import re

from personal_finance import counterparty

SHARED_NAMES = 2


def named_in(pages: list[str], label: str) -> str:
    """The account holder, as the statement itself writes it."""
    if not label:
        return ""
    pattern = re.compile(rf"{re.escape(label)}\s*:?\s*(.+)")
    for page in pages:
        for line in page.splitlines():
            found = pattern.search(line)
            if found:
                return counterparty.name(found.group(1).strip())
    return ""


def is_the_owner(key: str, owner: str) -> bool:
    """A counterparty is you when it shares enough of your name to be no one else."""
    if not owner or not key:
        return False
    mine, theirs = set(owner.split()), set(key.split())
    return len(mine & theirs) >= min(SHARED_NAMES, len(mine))
