"""Open statement PDFs, locked or not, and return their text page by page."""

import os
from pathlib import Path

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfplumber.utils.exceptions import PdfminerException


class StatementLocked(Exception):
    """None of the configured passwords opens this statement."""


def candidate_passwords() -> list[str]:
    # an empty string first, so unlocked statements open without trying secrets
    raw = os.getenv("PF_STATEMENT_PASSWORDS", "")
    return [""] + [p.strip() for p in raw.split(",") if p.strip()]


def _is_password_error(exc: Exception) -> bool:
    cause = exc.args[0] if exc.args else None
    return isinstance(exc, PDFPasswordIncorrect) or isinstance(cause, PDFPasswordIncorrect)


def _open(path: str | Path):
    for password in candidate_passwords():
        try:
            return pdfplumber.open(path, password=password)
        except (PDFPasswordIncorrect, PdfminerException) as exc:
            if not _is_password_error(exc):
                raise
    raise StatementLocked(f"no configured password opens {Path(path).name}")


def read_pages(path: str | Path) -> list[str]:
    with _open(path) as pdf:
        return [page.extract_text(layout=True) or "" for page in pdf.pages]


def read_words(path: str | Path) -> list[dict]:
    # page number keeps words from different pages on separate lines
    with _open(path) as pdf:
        words = []
        for number, page in enumerate(pdf.pages):
            for word in page.extract_words():
                words.append({**word, "top": word["top"] + number * 10_000})
        return words
