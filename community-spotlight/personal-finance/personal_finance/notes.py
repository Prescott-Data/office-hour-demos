"""What you have told the desk about a counterparty, beyond its category."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from personal_finance.state import STATE_DIR, JsonState

DEFAULT_PATH = STATE_DIR / "notes.json"


class Notes(JsonState):
    """Which counterparties are you, and which of their patterns you consider normal."""

    def __init__(self, path: Path | str = DEFAULT_PATH):
        super().__init__(path)

    def _entry(self, key: str) -> dict:
        return self.data.setdefault(key, {"mine": False, "normal": [], "at": None})

    def claim(self, key: str, mine: bool = True) -> None:
        """Mark a counterparty as an account of your own, so moving money there is not spending."""
        entry = self._entry(key)
        entry["mine"] = mine
        entry["at"] = datetime.now(timezone.utc).isoformat()
        self.save()

    def dismiss(self, key: str, topic: str) -> None:
        """Record that a pattern is unremarkable for this counterparty."""
        entry = self._entry(key)
        if topic not in entry["normal"]:
            entry["normal"].append(topic)
        entry["at"] = datetime.now(timezone.utc).isoformat()
        self.save()

    def mine(self, key: str) -> bool:
        return bool(self.data.get(key, {}).get("mine"))

    def normal(self, key: str) -> list[str]:
        return list(self.data.get(key, {}).get("normal", []))

    def mine_keys(self) -> list[str]:
        return sorted(key for key, entry in self.data.items() if entry.get("mine"))
