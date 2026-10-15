"""Reduce a description to who it was with, so the same shop is only ever asked about once."""

from __future__ import annotations

import re

ACCOUNT = re.compile(r"\b[\d*]{5,}\b")
ACC_REF = re.compile(r"\bAcc\.?\s*\S+", re.IGNORECASE)
PUNCT = re.compile(r"[^A-Z0-9&' ]+")
SPACES = re.compile(r"\s+")
MARKERS = (" to ", " from ", " by ")
IDENTIFIER = re.compile(r"\b(?:to|from|by)\s+([0-9*]{5,})", re.IGNORECASE)


def kind(description: str, kinds: dict[str, str]) -> str:
    """What the document says this row is, in shared words. Its phrases come from the layout."""
    text = SPACES.sub(" ", description.strip().lower())
    for phrase in sorted(kinds, key=len, reverse=True):
        if text.startswith(phrase.lower()):
            return kinds[phrase]
    return "unstated"


def name(description: str) -> str:
    """The other party, as a stable key: the same shop always reduces to the same string."""
    text = SPACES.sub(" ", description.strip())
    text = ACC_REF.sub("", text)
    if " - " in text:
        text = text.rsplit(" - ", 1)[1]
    else:
        lowered = text.lower()
        positions = [lowered.rindex(m) + len(m) for m in MARKERS if m in lowered]
        if positions:
            text = text[max(positions) :]
    text = PUNCT.sub(" ", ACCOUNT.sub("", text.upper()))
    return SPACES.sub(" ", text).strip()


def account(description: str) -> str:
    """The paybill, till or masked number paid, which two shops can share a name without."""
    found = IDENTIFIER.search(description)
    return found.group(1) if found else ""


def key(description: str, kinds: dict[str, str]) -> str:
    """What the categoriser is asked about: the counterparty, or the kind when there is none."""
    return name(description) or kind(description, kinds)
