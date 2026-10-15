"""What the decision model has already judged, so the same shop is never paid for twice."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from personal_finance.contracts import CategoryPolicy, Verdict
from personal_finance.state import STATE_DIR, JsonState

DEFAULT_PATH = STATE_DIR / "judgements.json"


def fingerprint(policy: CategoryPolicy) -> str:
    """Identifies the option list an answer was chosen from."""
    names = "\n".join(sorted(policy.categories))
    return hashlib.sha256(names.encode("utf-8")).hexdigest()[:16]


class Judgements(JsonState):
    """A cache of the agent's own answers, keyed by counterparty."""

    def __init__(self, path: Path | str = DEFAULT_PATH):
        super().__init__(path)

    def get(self, key: str, against: str | None = None) -> Verdict | None:
        entry = self.data.get(key)
        if not entry:
            return None
        # an answer chosen from a different set of categories is not an answer to this question
        if against is not None and entry.get("categories") != against:
            return None
        return Verdict(
            key=key,
            category=entry["category"],
            decided_by="agent",
            confidence=entry.get("confidence"),
            needs_review=entry.get("needs_review", False),
        )

    def put(self, verdict: Verdict, against: str | None = None) -> None:
        self.data[verdict.key] = {
            "category": verdict.category,
            "confidence": verdict.confidence,
            "needs_review": verdict.needs_review,
            "categories": against,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        self.save()
