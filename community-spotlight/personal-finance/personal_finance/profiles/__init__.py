"""Profiles: the surfaces you are meant to edit."""

from pathlib import Path

import yaml

from personal_finance.contracts import CategoryPolicy

PROFILE_DIR = Path(__file__).parent


def categories() -> CategoryPolicy:
    return CategoryPolicy(**yaml.safe_load((PROFILE_DIR / "categories.yaml").read_text()))
