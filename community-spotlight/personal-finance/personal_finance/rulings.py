"""Your word on what counts as avoidable, which outranks whatever the agent decided."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from personal_finance.state import STATE_DIR, JsonState

DEFAULT_PATH = STATE_DIR / "rulings.json"
TIDY = re.compile(r"[^a-z0-9]+")


def label(what: str) -> str:
    """The same line, however it was worded, reduces to the same key."""
    return TIDY.sub("_", what.strip().lower()).strip("_")


class Rulings(JsonState):
    """A ledger of the calls you have made on what was waste and what was simply spending."""

    def __init__(self, path: Path | str = DEFAULT_PATH):
        super().__init__(path)

    def record(self, what: str, avoidable: bool) -> str:
        key = label(what)
        self.data[key] = {
            "avoidable": bool(avoidable),
            "at": datetime.now(timezone.utc).isoformat(),
        }
        self.save()
        return key

    def forget(self, what: str) -> bool:
        key = label(what)
        if key not in self.data:
            return False
        del self.data[key]
        self.save()
        return True

    def says(self, what: str) -> bool | None:
        entry = self.data.get(label(what))
        return None if entry is None else bool(entry["avoidable"])
