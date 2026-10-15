"""Whose desk this is: every stored thing is kept per person."""

from __future__ import annotations

import re
from pathlib import Path

from personal_finance.state import STATE_DIR

DEFAULT_USER = "me"
SAFE = re.compile(r"[^a-z0-9_-]+")


class Desk:
    """One person's corrections, judgements and categories, kept apart from anyone else's."""

    def __init__(self, user: str = DEFAULT_USER, root: Path | str = STATE_DIR):
        self.user = SAFE.sub("-", user.strip().lower()) or DEFAULT_USER
        self.root = Path(root) / self.user

    def path(self, name: str) -> Path:
        return self.root / f"{name}.json"

    def corrections(self):
        from personal_finance.corrections import Corrections

        return Corrections(self.path("corrections"))

    def judgements(self):
        from personal_finance.judgements import Judgements

        return Judgements(self.path("judgements"))

    def notes(self):
        from personal_finance.notes import Notes

        return Notes(self.path("notes"))

    def rulings(self):
        from personal_finance.rulings import Rulings

        return Rulings(self.path("rulings"))

    def watched(self):
        from personal_finance.state import JsonState

        return JsonState(self.path("watched"))

    def audits(self):
        from personal_finance.state import JsonState

        return JsonState(self.path("audits"))

    def categories(self):
        from personal_finance.catalogue import Catalogue

        return Catalogue(self.path("categories"))
