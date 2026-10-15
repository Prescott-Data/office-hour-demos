"""A small JSON file the desk keeps between runs, written so a crash cannot truncate it."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def state_dir() -> Path:
    """One desk per person, found the same way whichever door they come in by."""
    told = os.environ.get("PF_STATE_DIR")
    if told:
        return Path(told).expanduser()
    # the shared Desk runs each task from its own working directory, so anchor to the project
    project = Path(__file__).resolve().parents[1]
    if (project / "pyproject.toml").is_file():
        return project / ".pf-state"
    return Path.home() / ".pf-state"


STATE_DIR = state_dir()


class JsonState:
    """Plain JSON on disk: readable, editable, and exact when read back."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.data: dict[str, Any] = self._read()

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text() or "{}")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, indent=2, sort_keys=True))
        os.replace(temporary, self.path)

    def __len__(self) -> int:
        return len(self.data)

    def __contains__(self, key: str) -> bool:
        return key in self.data
