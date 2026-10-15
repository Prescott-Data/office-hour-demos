"""Your corrections: exact, durable, and yours to edit."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from personal_finance.state import STATE_DIR, JsonState

DEFAULT_PATH = STATE_DIR / "corrections.json"


class Corrections(JsonState):
    """A ledger keyed by counterparty, read back exactly rather than approximately."""

    def __init__(self, path: Path | str = DEFAULT_PATH):
        super().__init__(path)

    def record(self, key: str, category: str) -> None:
        self.data[key] = {"category": category, "at": datetime.now(timezone.utc).isoformat()}
        self.save()

    def forget(self, key: str) -> bool:
        if key not in self.data:
            return False
        del self.data[key]
        self.save()
        return True

    def as_dict(self) -> dict[str, str]:
        return {key: entry["category"] for key, entry in self.data.items()}
