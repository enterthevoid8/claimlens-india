"""Tolerant parsers for dates, money and names found in Indian hospital paperwork."""

from __future__ import annotations

import re
from datetime import date, datetime

_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"],
        start=1,
    )
}

_NUM_DATE = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b")
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_TEXT_DATE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?[\s\-]+([A-Za-z]{3,9})[\s,\-]+(\d{2,4})\b")


def _year(y: int) -> int:
    return y + 2000 if y < 100 else y


def parse_date(text: str | None) -> date | None:
    """Parse the first date in ``text``. Day-first, as is the Indian convention."""
    if not text:
        return None
    m = _ISO_DATE.search(text)
    try:
        if m:
            return date(int(m[1]), int(m[2]), int(m[3]))
        m = _NUM_DATE.search(text)
        if m:
            return date(_year(int(m[3])), int(m[2]), int(m[1]))
        m = _TEXT_DATE.search(text)
        if m and m[2][:3].lower() in _MONTHS:
            return date(_year(int(m[3])), _MONTHS[m[2][:3].lower()], int(m[1]))
    except ValueError:
        return None
    return None


_AMOUNT = re.compile(r"(?:rs\.?|inr|₹)?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(?:/-)?", re.IGNORECASE)


def parse_amount(text: str | None) -> float | None:
    if not text:
        return None
    m = _AMOUNT.search(text.replace(" ", " "))
    if not m:
        return None
    try:
        return round(float(m[1].replace(",", "")), 2)
    except ValueError:
        return None


def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    name = re.sub(r"\b(mr|mrs|ms|miss|shri|smt|dr|master|baby)\b\.?", "", name, flags=re.IGNORECASE)
    return re.sub(r"[^a-z ]", "", name.lower()).strip()


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", value).strip(" \t:-|")
    return value or None


def iso(d: date | datetime | None) -> str | None:
    return d.isoformat() if d else None
