"""The shapes every part of the desk agrees on."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class Column(BaseModel):
    """One column of a statement table, found by its heading."""

    name: str
    heading: str
    kind: str = "text"  # text | timestamp | amount


class LayoutProfile(BaseModel):
    """How to read one issuer's statement, learned once and stored as data."""

    name: str
    columns: list[Column]
    row_start: str  # regex the first cell of a new row matches
    timestamp_format: str
    owner_label: str = ""  # the header field naming whose statement this is
    paid_in: str
    withdrawn: str
    balance: str
    skip_lines: list[str] = Field(default_factory=list)  # regexes for page furniture
    end_lines: list[str] = Field(default_factory=list)  # where the table stops on a page
    status_values: list[str] = Field(default_factory=list)  # anything else is description text
    kinds: dict[str, str] = Field(default_factory=dict)  # this issuer's phrase -> shared kind

    def column(self, name: str) -> Column:
        return next(c for c in self.columns if c.name == name)


class CategoryPolicy(BaseModel):
    """The categories you keep, what each one means, and the kinds that place themselves."""

    categories: dict[str, str]
    by_kind: dict[str, str] = Field(default_factory=dict)
    confidence_threshold: float = 0.6

    def allows(self, category: str) -> bool:
        return category in self.categories


class Verdict(BaseModel):
    """One category, and an account of where it came from."""

    key: str
    category: str
    decided_by: str
    confidence: float | None = None
    needs_review: bool = False


class Transaction(BaseModel):
    """One line of money moving, from any issuer."""

    reference: str
    timestamp: datetime
    description: str
    status: str
    paid_in: Decimal = Decimal(0)
    withdrawn: Decimal = Decimal(0)
    balance: Decimal
    source: str  # which statement it came from

    @property
    def signed_amount(self) -> Decimal:
        return self.paid_in - self.withdrawn


class Finding(BaseModel):
    """Something in the statement worth your attention, with what it is based on."""

    kind: str
    headline: str
    amount: Decimal = Decimal(0)
    occurrences: int = 1
    evidence: list[str] = Field(default_factory=list)


class Statement(BaseModel):
    """Every transaction read out of one document."""

    source: str
    layout: str
    transactions: list[Transaction]
