"""Synthetic positioned words shaped like a statement, with invented transactions."""

from datetime import datetime, timedelta
from decimal import Decimal

from personal_finance import layouts
from personal_finance.contracts import Transaction

COLUMN_X = {
    "reference": 50.0,
    "timestamp": 110.0,
    "description": 215.0,
    "status": 282.0,
    "paid_in": 372.0,
    "withdrawn": 435.0,
    "balance": 510.0,
}

HEADINGS = [
    ("Receipt", 50.0), ("No.", 79.0),
    ("Completion", 110.0), ("Time", 153.0),
    ("Details", 215.0),
    ("Transaction", 282.0), ("Status", 325.0),
    ("Paid", 372.0), ("In", 390.0),
    ("Withdrawn", 435.0),
    ("Balance", 510.0),
]


CHAR_WIDTH = 3.5  # matches the real statement, where "Receipt" spans about 26 points


def word(text: str, x0: float, top: float) -> dict:
    return {"text": text, "x0": x0, "x1": x0 + CHAR_WIDTH * len(text), "top": top}


def header(top: float) -> list[dict]:
    return [word(text, x0, top) for text, x0 in HEADINGS]


def row(top: float, reference: str, when: str, details: str, status: str,
        paid_in: str = "", withdrawn: str = "", balance: str = "") -> list[dict]:
    words = [word(reference, COLUMN_X["reference"], top)]
    date, clock = when.split(" ")
    words += [word(date, COLUMN_X["timestamp"], top), word(clock, COLUMN_X["timestamp"] + 34, top)]
    offset = 0.0
    for token in details.split():
        words.append(word(token, COLUMN_X["description"] + offset, top))
        offset += CHAR_WIDTH * len(token) + 2
    words.append(word(status, COLUMN_X["status"], top))
    for name, value in (("paid_in", paid_in), ("withdrawn", withdrawn), ("balance", balance)):
        if value:
            words.append(word(value, COLUMN_X[name], top))
    return words


def wrapped(top: float, details: str) -> list[dict]:
    offset = 0.0
    words = []
    for token in details.split():
        words.append(word(token, COLUMN_X["description"] + offset, top))
        offset += CHAR_WIDTH * len(token) + 2
    return words


def statement_words() -> list[dict]:
    """Newest first, one wrapped row, one page break, and a fee row."""
    words = header(50)
    words += row(70, "AAA1111111", "2026-08-05 09:10:00", "Merchant Payment to", "Completed",
                 withdrawn="-250.00", balance="1,250.00")
    words += wrapped(82, "1234567 - CORNER SHOP")
    words += row(94, "BBB2222222", "2026-08-04 18:00:00", "Customer Transfer of Funds Charge",
                 "Completed", withdrawn="-23.00", balance="1,500.00")
    footer = [("Page", 250), ("1", 275), ("of", 285), ("2", 295)]
    words += [word(t, x, 106) for t, x in footer]
    words += header(120)
    words += row(140, "CCC3333333", "2026-08-03 12:00:00", "Salary", "Completed",
                 paid_in="20,000.00", balance="1,523.00")
    return words


PROFILE = layouts.load("mpesa-statement")


def tied_statement_words() -> list[dict]:
    """Two rows share a second, and file order alone puts them the wrong way round."""
    words = header(50)
    words += row(70, "BBB2222222", "2026-08-05 09:10:00", "Send money", "Completed",
                 withdrawn="-100.00", balance="1,500.00")
    words += row(82, "AAA1111111", "2026-08-05 09:10:00", "Buy goods", "Completed",
                 withdrawn="-250.00", balance="1,250.00")
    words += row(94, "CCC3333333", "2026-08-05 09:00:00", "Salary", "Completed",
                 paid_in="1,600.00", balance="1,600.00")
    return words


START = datetime(2026, 8, 1, 9, 0, 0)


def paid(key, amount, day, hour=9, reference=None):
    return Transaction(
        reference=reference or f"R{day:02d}{hour:02d}{int(amount)}",
        timestamp=START + timedelta(days=day, hours=hour - 9),
        description=f"Merchant Payment Online to 1234567 - {key}",
        status="Completed",
        withdrawn=Decimal(str(amount)),
        balance=Decimal("1000.00"),
        source="fixture",
    )
