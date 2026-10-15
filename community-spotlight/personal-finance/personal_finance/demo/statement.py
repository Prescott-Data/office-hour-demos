"""A statement that never existed, shaped exactly like a real one."""

from __future__ import annotations

CHAR_WIDTH = 3.5
COLUMN_X = {
    "reference": 50.0, "timestamp": 110.0, "description": 215.0,
    "status": 282.0, "paid_in": 372.0, "withdrawn": 435.0, "balance": 510.0,
}
HEADINGS = [
    ("Receipt", 50.0), ("No.", 79.0), ("Completion", 110.0), ("Time", 153.0), ("Details", 215.0),
    ("Transaction", 282.0), ("Status", 325.0), ("Paid", 372.0), ("In", 390.0),
    ("Withdrawn", 435.0), ("Balance", 510.0),
]

# who the money went to, and what the issuer calls each movement
STORY = [
    ("2026-09-28 18:40:12", "Merchant Payment Online to 1234567 - MAMA NGINA GROCERS", -1250.00),
    ("2026-09-28 18:44:31", "Merchant Payment Online to 1234567 - MAMA NGINA GROCERS", -1250.00),
    ("2026-09-28 18:45:02", "Customer Transfer of Funds Charge", -23.00),
    ("2026-09-25 07:15:03", "Customer Transfer to 2547***111 - JOHN THE RIDER", -200.00),
    ("2026-09-25 13:02:41", "Customer Transfer to 2547***111 - JOHN THE RIDER", -200.00),
    ("2026-09-20 09:00:00", "Pay Bill Online to 888880 - CITY POWER PREPAID", -1500.00),
    ("2026-09-18 11:11:11", "Airtime Purchase", -100.00),
    ("2026-09-15 08:30:00", "OverDraft of Credit Party", 500.00),
    ("2026-09-15 08:30:05", "Customer Transfer Fuliza MPesa to 2547***222 - AUNTIE W", -500.00),
    ("2026-09-16 19:45:00", "OD Loan Repayment to 232323 - M-PESA Overdraw", -540.00),
    ("2026-09-10 10:05:00", "Business Payment from 7654321 - FAIRVIEW LIMITED via API", 48000.00),
    ("2026-08-28 18:12:00", "Merchant Payment Online to 1234567 - MAMA NGINA GROCERS", -980.00),
    ("2026-08-25 07:20:00", "Customer Transfer to 2547***111 - JOHN THE RIDER", -200.00),
    ("2026-08-20 09:00:00", "Pay Bill Online to 888880 - CITY POWER PREPAID", -1200.00),
    ("2026-08-18 12:00:00", "Airtime Purchase", -100.00),
    ("2026-08-12 16:30:00", "Customer Transfer to 2547***333 - DAUDI THE LANDLORD", -18000.00),
    ("2026-08-10 10:05:00", "Business Payment from 7654321 - FAIRVIEW LIMITED via API", 48000.00),
]
OPENING = 2000.00


def _word(text: str, x0: float, top: float) -> dict:
    return {"text": text, "x0": x0, "x1": x0 + CHAR_WIDTH * len(text), "top": top}


def _amount(value: float) -> str:
    return f"{value:,.2f}"


DESCRIPTION_WIDTH = COLUMN_X["status"] - COLUMN_X["description"] - 4


def _description(details: str, top: float) -> list[dict]:
    """Laid out the way the issuer does it: wrapped inside its column, not run past it."""
    made, offset, line = [], 0.0, top
    for token in details.split():
        span = CHAR_WIDTH * len(token) + 2
        if offset and offset + span > DESCRIPTION_WIDTH:
            offset, line = 0.0, line + 12.0
        made.append(_word(token, COLUMN_X["description"] + offset, line))
        offset += span
    return made


def words() -> list[dict]:
    """The statement as a page of positioned words, the way a reader sees a PDF."""
    made = [_word(text, x0, 50.0) for text, x0 in HEADINGS]
    balance = OPENING + sum(value for _, _, value in STORY)
    top = 70.0
    for when, details, value in STORY:
        reference = f"D{abs(hash((when, details))) % 10**9:09d}"[:10].upper()
        date, clock = when.split(" ")
        made.append(_word(reference, COLUMN_X["reference"], top))
        made.append(_word(date, COLUMN_X["timestamp"], top))
        made.append(_word(clock, COLUMN_X["timestamp"] + 34, top))
        wrapped = _description(details, top)
        made += wrapped
        made.append(_word("Completed", COLUMN_X["status"], top))
        column = "paid_in" if value > 0 else "withdrawn"
        made.append(_word(_amount(value), COLUMN_X[column], top))
        made.append(_word(_amount(balance), COLUMN_X["balance"], top))
        balance -= value  # the statement runs newest first, so walk the balance backwards
        top = max(word["top"] for word in wrapped) + 14.0
    return made
