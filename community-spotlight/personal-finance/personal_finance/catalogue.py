"""One person's categories: seeded from a default set, then theirs to shape."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from personal_finance import profiles
from personal_finance.contracts import CategoryPolicy
from personal_finance.state import JsonState

RESERVED = "uncategorised"


class Catalogue(JsonState):
    """The categories this person keeps, and whether they have approved the set."""

    def __init__(self, path: Path | str):
        super().__init__(path)
        seeded = bool(self.data)
        if not self.data:
            seed = profiles.categories()
            self.data = {
                "categories": dict(seed.categories),
                "by_kind": dict(seed.by_kind),
                "confidence_threshold": seed.confidence_threshold,
                "approved_at": None,
            }
            self.save()
        if seeded:
            self._keep_stated_kinds()

    def _keep_stated_kinds(self) -> None:
        """Rows the statement explains always need somewhere to land, whatever else you keep."""
        seed = profiles.categories()
        wanted = {k: v for k, v in seed.by_kind.items() if v in seed.categories}
        missing = {
            category: seed.categories[category]
            for category in set(wanted.values())
            if category not in self.data["categories"]
        }
        if not missing and self.data["by_kind"] == wanted:
            return
        self.data["categories"] = {**missing, **self.data["categories"]}
        self.data["by_kind"] = wanted
        self.save()

    def policy(self) -> CategoryPolicy:
        return CategoryPolicy(
            categories=self.data["categories"],
            by_kind=self.data["by_kind"],
            confidence_threshold=self.data["confidence_threshold"],
        )

    @property
    def approved(self) -> bool:
        return bool(self.data.get("approved_at"))

    def approve(self) -> None:
        # once approved the set stops moving, so month-to-month totals stay comparable
        self.data["approved_at"] = datetime.now(timezone.utc).isoformat()
        self.save()

    def add(self, name: str, meaning: str) -> None:
        self.data["categories"][name] = meaning
        self.save()

    def rename(self, old: str, new: str) -> bool:
        if old not in self.data["categories"] or old == RESERVED:
            return False
        self.data["categories"][new] = self.data["categories"].pop(old)
        for kind, category in self.data["by_kind"].items():
            if category == old:
                self.data["by_kind"][kind] = new
        self.save()
        return True

    def remove(self, name: str) -> bool:
        if name not in self.data["categories"] or name == RESERVED:
            return False
        del self.data["categories"][name]
        self.data["by_kind"] = {
            kind: category
            for kind, category in self.data["by_kind"].items()
            if category != name
        }
        self.save()
        return True

    def merge(self, source: str, target: str) -> bool:
        """Fold one category into another, leaving nothing stranded in the one that goes."""
        if source == target or source == RESERVED:
            return False
        if source not in self.data["categories"] or target not in self.data["categories"]:
            return False
        del self.data["categories"][source]
        self.data["by_kind"] = {
            kind: (target if category == source else category)
            for kind, category in self.data["by_kind"].items()
        }
        self.save()
        return True

    def replace(self, categories: dict[str, str]) -> None:
        """Take a proposed set wholesale, keeping what must always exist."""
        seed = profiles.categories()
        self.data["categories"] = {**categories, RESERVED: seed.categories[RESERVED]}
        self.data["approved_at"] = None
        self._keep_stated_kinds()
        self.save()
