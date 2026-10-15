"""Labels in place of names, so what reaches a model carries figures rather than people."""

from __future__ import annotations

import re


class Masker:
    """Gives each counterparty a label, and puts the name back for your eyes only."""

    def __init__(self, word: str = "counterparty"):
        self.word = word
        self.labels: dict[str, str] = {}
        self.names: dict[str, str] = {}

    def label(self, place: str) -> str:
        if place not in self.labels:
            given = f"{self.word} {len(self.labels) + 1}"
            self.labels[place] = given
            self.names[given] = place
        return self.labels[place]

    def hide(self, value):
        """Replace every counterparty a probe returned with its label."""
        if isinstance(value, dict):
            return {
                key: self.label(str(item)) if key == "place" else self.hide(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self.hide(item) for item in value]
        return value

    def reveal(self, text: str) -> str:
        """Each label ends at a word boundary, so label 5 leaves label 55 alone."""
        for given, place in self.names.items():
            text = re.sub(rf"{re.escape(given)}\b", lambda _, name=place: name, text)
        return text
