"""Layout profiles: how each issuer's statement is arranged."""

from pathlib import Path

import yaml

from personal_finance.contracts import LayoutProfile

LAYOUT_DIR = Path(__file__).parent


def load(name: str) -> LayoutProfile:
    return LayoutProfile(**yaml.safe_load((LAYOUT_DIR / f"{name}.yaml").read_text()))


def known() -> list[str]:
    return sorted(p.stem for p in LAYOUT_DIR.glob("*.yaml"))
