"""Turn positioned words into transactions, using a layout profile and nothing issuer-specific."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from personal_finance.contracts import LayoutProfile, Transaction

Word = dict[str, Any]
LINE_TOLERANCE = 3.0


class LayoutMismatch(Exception):
    """The document does not match this layout profile."""


def group_lines(words: Iterable[Word]) -> list[list[Word]]:
    lines: list[list[Word]] = []
    for word in sorted(words, key=lambda w: (round(w["top"], 1), w["x0"])):
        if lines and abs(lines[-1][0]["top"] - word["top"]) <= LINE_TOLERANCE:
            lines[-1].append(word)
        else:
            lines.append([word])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def _heading_centre(line: list[Word], heading: str) -> float | None:
    tokens = heading.split()
    for i in range(len(line) - len(tokens) + 1):
        span = line[i : i + len(tokens)]
        if [w["text"] for w in span] == tokens:
            return (span[0]["x0"] + span[-1]["x1"]) / 2
    return None


def column_bounds(
    line: list[Word], profile: LayoutProfile
) -> dict[str, tuple[float, float]] | None:
    centres = {c.name: _heading_centre(line, c.heading) for c in profile.columns}
    if any(x is None for x in centres.values()):
        return None
    # headings are centred and amounts right-aligned, so a cell belongs to the nearest heading
    ordered = sorted(centres.items(), key=lambda kv: kv[1])
    bounds = {}
    for i, (name, centre) in enumerate(ordered):
        left = 0.0 if i == 0 else (ordered[i - 1][1] + centre) / 2
        right = float("inf") if i + 1 == len(ordered) else (centre + ordered[i + 1][1]) / 2
        bounds[name] = (left, right)
    return bounds


def _cells(line: list[Word], bounds: dict[str, tuple[float, float]]) -> dict[str, str]:
    cells: dict[str, list[str]] = {name: [] for name in bounds}
    for word in line:
        centre = (word["x0"] + word["x1"]) / 2
        for name, (left, right) in bounds.items():
            if left <= centre < right:
                cells[name].append(word["text"])
                break
    return {name: " ".join(parts).strip() for name, parts in cells.items()}


AMOUNT = re.compile(r"^-?[\d,]+(\.\d+)?$")


def _longest_timestamp(tokens: list[str], fmt: str) -> int:
    for count in range(len(tokens), 0, -1):
        try:
            datetime.strptime(" ".join(tokens[:count]), fmt)
            return count
        except ValueError:
            continue
    return 0


def _reclaim(cells: dict[str, str], profile: LayoutProfile) -> dict[str, str]:
    """Each column keeps only what its kind allows; the rest is description text."""
    before: list[str] = []
    after: list[str] = []
    for column in profile.columns:
        tokens = cells.get(column.name, "").split()
        if not tokens or column.kind == "text":
            continue
        if column.kind == "timestamp":
            kept = _longest_timestamp(tokens, profile.timestamp_format)
            cells[column.name] = " ".join(tokens[:kept])
            before += tokens[kept:]
        elif column.kind == "amount":
            keep = [t for t in tokens if AMOUNT.match(t)]
            cells[column.name] = " ".join(keep[-1:])
            after += [t for t in tokens if t not in keep]
    if profile.status_values and cells.get("status"):
        keep = [t for t in cells["status"].split() if t in profile.status_values]
        after += [t for t in cells["status"].split() if t not in keep]
        cells["status"] = " ".join(keep)
    cells["description"] = " ".join(filter(None, [*before, cells.get("description", ""), *after]))
    return cells


def to_amount(text: str) -> Decimal:
    if not text:
        return Decimal(0)
    try:
        return Decimal(text.replace(",", "").replace(" ", ""))
    except InvalidOperation as exc:
        raise LayoutMismatch(f"cell is not an amount: {text!r}") from exc


def extract(words: Iterable[Word], profile: LayoutProfile, source: str) -> list[Transaction]:
    row_start = re.compile(profile.row_start)
    skip = [re.compile(p, re.IGNORECASE) for p in profile.skip_lines]
    ends = [re.compile(p, re.IGNORECASE) for p in profile.end_lines]
    bounds: dict[str, tuple[float, float]] | None = None
    rows: list[dict[str, str]] = []

    for line in group_lines(words):
        found = column_bounds(line, profile)
        if found:
            bounds = found
            continue
        if bounds is None:
            continue
        text = " ".join(w["text"] for w in line)
        # the table ends here, and nothing below belongs to the row above it
        if any(p.search(text) for p in ends):
            bounds = None
            continue
        if any(p.search(text) for p in skip):
            continue
        cells = _reclaim(_cells(line, bounds), profile)
        if row_start.match(cells.get("reference", "")):
            rows.append(cells)
        elif rows:
            # a wrapped row: its remaining words belong to the description
            extra = " ".join(v for k, v in cells.items() if v and k != "reference")
            rows[-1]["description"] = f"{rows[-1]['description']} {extra}".strip()

    if not rows:
        raise LayoutMismatch(f"no rows matched layout {profile.name!r}")
    return [_transaction(row, profile, source) for row in rows]


def _transaction(row: dict[str, str], profile: LayoutProfile, source: str) -> Transaction:
    paid_in = to_amount(row.get(profile.paid_in, ""))
    withdrawn = to_amount(row.get(profile.withdrawn, ""))
    # issuers mark money out with a minus rather than a separate column
    if paid_in < 0:
        paid_in, withdrawn = Decimal(0), withdrawn + abs(paid_in)
    return Transaction(
        reference=row["reference"],
        timestamp=datetime.strptime(row["timestamp"], profile.timestamp_format),
        description=row.get("description", ""),
        status=row.get("status", ""),
        paid_in=paid_in,
        withdrawn=abs(withdrawn),
        balance=to_amount(row.get(profile.balance, "")),
        source=source,
    )
