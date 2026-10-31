"""Deterministic, offline extractor.

This is the CI/laptop baseline and the fallback when the LLM extractor is disabled. It understands the
layouts our synthetic generator produces (pipe tables, whitespace columns, "qty x rate" narrative
lines) and a reasonable range of key spellings. It is *not* a general OCR/extraction engine: real
scans go through Azure Document Intelligence + the LLM extractor, and both are scored by the same
evaluation harness (``claimlens eval``).
"""

from __future__ import annotations

import re

from claimlens.domain.models import DischargeSummary, HospitalBill, LineItem
from claimlens.extraction.categorize import categorize
from claimlens.extraction.parsing import clean, parse_amount, parse_date

_KEYS: dict[str, tuple[str, ...]] = {
    "bill_number": ("bill no", "bill number", "invoice no", "invoice number", "bill #"),
    "patient_name": ("patient name", "name of patient", "patient", "name of the patient"),
    "admission_date": ("date of admission", "admission date", "doa", "admitted on", "d.o.a"),
    "discharge_date": ("date of discharge", "discharge date", "dod", "discharged on", "d.o.d"),
    "room_type": ("room type", "room category", "ward type", "ward", "room"),
    "diagnosis": ("final diagnosis", "diagnosis", "provisional diagnosis"),
    "procedure": ("procedure performed", "procedure", "surgery", "operation performed"),
    "city": ("city", "location"),
    "hospital": ("hospital", "hospital name"),
    "doctor": ("treating doctor", "consultant", "doctor"),
    "mode": ("mode of admission", "type of admission", "admission type"),
    "cause": ("cause", "nature of illness", "mode of injury"),
    "history": (
        "history",
        "past history",
        "duration of illness",
        "history of present illness",
        "known case of",
    ),
}

_KV = re.compile(r"^\s*([A-Za-z][A-Za-z .#/()]{1,40}?)\s*[:\-–]\s*(.+?)\s*$")
_SKIP_DESC = re.compile(
    r"^(sr|s\.?no|sl|description|particulars|item|total|sub\s*total|grand|net|gst|cgst|sgst|tax|amount|discount|advance|balance|paid)\b",
    re.I,
)
_NUM = r"[0-9][0-9,]*(?:\.[0-9]{1,2})?"
_PIPE_NUM = re.compile(rf"^(?:rs\.?|inr|₹)?\s*({_NUM})\s*(?:/-)?$", re.I)
_COLUMNS = re.compile(
    rf"^\s*(?:\d{{1,3}}[.)]?\s+)?(?P<desc>[A-Za-z(].*?)\s{{2,}}(?P<qty>\d+(?:\.\d+)?)\s+(?P<rate>{_NUM})\s+(?P<amt>{_NUM})\s*$"
)
_NARRATIVE = re.compile(
    rf"^\s*(?:\d{{1,3}}[.)]\s+)?(?P<desc>[A-Za-z].*?)\s*\(\s*(?P<qty>\d+(?:\.\d+)?)\s*[x×*]\s*(?:rs\.?|inr|₹)?\s*(?P<rate>{_NUM})\s*\)\s*[.\s:\-]*\s*(?:rs\.?|inr|₹)?\s*(?P<amt>{_NUM})\s*(?:/-)?\s*$",
    re.I,
)
_SIMPLE = re.compile(
    rf"^\s*(?:\d{{1,3}}[.)]\s+)?(?P<desc>[A-Za-z][A-Za-z0-9 ,\-/.&()]+?)\s*[.\s:]{{3,}}\s*(?:rs\.?|inr|₹)?\s*(?P<amt>{_NUM})\s*(?:/-)?\s*$",
    re.I,
)
_TOTAL = re.compile(
    rf"^\s*(grand\s+total|net\s+payable|total\s+claimed|total\s+amount(?:\s+claimed)?|total\s+bill(?:\s+amount)?|bill\s+total|total)\b[^0-9\n]{{0,25}}(?:rs\.?|inr|₹)?\s*({_NUM})",
    re.I,
)
_TOTAL_PRIORITY = (
    "grand",
    "net",
    "total claimed",
    "total amount",
    "total bill",
    "bill total",
    "total",
)


def _key_of(label: str) -> str | None:
    lab = re.sub(r"\s+", " ", label.strip().lower().rstrip(":"))
    for key, variants in _KEYS.items():
        if lab in variants:
            return key
    return None


def _kv_pairs(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if line.count("|") >= 2:
            continue
        m = _KV.match(line)
        if not m:
            continue
        key = _key_of(m[1])
        if key and key not in out:
            out[key] = m[2]
    return out


def _to_float(s: str) -> float:
    return round(float(s.replace(",", "")), 2)


_ROW_START = re.compile(r"^\s*\|?\s*\d{1,3}\s*[.)|]?\s+[A-Za-z]")
_MONEYISH = re.compile(r"[0-9OIl][0-9,OIl]*\.\d{2}")


def _looks_like_row(line: str) -> bool:
    return bool(_ROW_START.match(line) and (line.count("|") >= 4 or _MONEYISH.search(line)))


def parse_line_items(text: str) -> list[LineItem]:
    return parse_line_items_ex(text)[0]


def parse_line_items_ex(text: str) -> tuple[list[LineItem], list[str]]:
    """Items plus the rows that look like items but could not be read (reported, never silently dropped)."""
    items: list[LineItem] = []
    unparsed: list[str] = []
    for line in text.splitlines():
        item = _parse_line(line)
        if item is not None:
            items.append(item)
        elif _looks_like_row(line):
            unparsed.append((clean(line) or line)[:120])
    return items, unparsed


def _parse_line(line: str) -> LineItem | None:
    if "|" in line:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        nums: list[float] = []
        i = len(cells)
        while i > 0 and _PIPE_NUM.match(cells[i - 1] or "x"):
            i -= 1
            cell = _PIPE_NUM.match(cells[i])
            if cell is None:  # pragma: no cover - guarded by the loop condition
                break
            nums.insert(0, _to_float(cell[1]))
        desc_cells = [c for c in cells[:i] if c and not c.isdigit()]
        if len(nums) >= 3 and desc_cells:
            qty, rate, amt = nums[-3], nums[-2], nums[-1]
            desc = clean(desc_cells[-1])
            if desc and not _SKIP_DESC.match(desc):
                return LineItem(
                    description=desc,
                    category=categorize(desc),
                    quantity=qty,
                    unit_price=rate,
                    amount=amt,
                )
        if len(nums) == 1 and desc_cells:
            desc = clean(desc_cells[-1])
            if desc and not _SKIP_DESC.match(desc):
                return LineItem(
                    description=desc,
                    category=categorize(desc),
                    quantity=1.0,
                    unit_price=nums[0],
                    amount=nums[0],
                )
        return None
    for pattern in (_NARRATIVE, _COLUMNS):
        m = pattern.match(line)
        if m:
            desc = clean(m["desc"])
            if desc and not _SKIP_DESC.match(desc):
                return LineItem(
                    description=desc,
                    category=categorize(desc),
                    quantity=float(m["qty"]),
                    unit_price=_to_float(m["rate"]),
                    amount=_to_float(m["amt"]),
                )
            return None
    m = _SIMPLE.match(line)
    if m:
        desc = clean(m["desc"])
        if desc and not _SKIP_DESC.match(desc):
            amt = _to_float(m["amt"])
            return LineItem(
                description=desc,
                category=categorize(desc),
                quantity=1.0,
                unit_price=amt,
                amount=amt,
            )
    return None


def parse_total(text: str) -> float | None:
    found: dict[str, float] = {}
    for line in text.splitlines():
        if "sub" in line.lower()[:12]:
            continue
        m = _TOTAL.match(line)
        if m:
            label = re.sub(r"\s+", " ", m[1].lower())
            for p in _TOTAL_PRIORITY:
                if label.startswith(p):
                    found[p] = _to_float(m[2])
                    break
    for p in _TOTAL_PRIORITY:
        if p in found:
            return found[p]
    return None


def parse_history_years(value: str | None) -> float | None:
    """Years the condition is stated to pre-date admission. ``None`` means 'not stated'."""
    if not value:
        return None
    v = value.lower()
    if re.search(r"\b(no|nil|none|not applicable|n/?a|no significant|no known)\b", v):
        return 0.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*(year|yr|y)\w*", v)
    if m:
        return float(m[1])
    m = re.search(r"(\d+(?:\.\d+)?)\s*(month|mo)\w*", v)
    if m:
        return round(float(m[1]) / 12, 2)
    return None


class RuleBasedExtractor:
    name = "rule_based"

    def extract_bill(self, text: str) -> HospitalBill:
        kv = _kv_pairs(text)
        first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
        hospital = clean(kv.get("hospital")) or (
            first_line
            if first_line and not re.search(r"bill|invoice|\d", first_line, re.I)
            else None
        )
        items, unparsed = parse_line_items_ex(text)
        return HospitalBill(
            bill_number=clean(kv.get("bill_number")),
            hospital_name=hospital,
            city=clean(kv.get("city")),
            patient_name=clean(kv.get("patient_name")),
            admission_date=parse_date(kv.get("admission_date")),
            discharge_date=parse_date(kv.get("discharge_date")),
            diagnosis=clean(kv.get("diagnosis")),
            procedure=clean(kv.get("procedure")),
            room_type=clean(kv.get("room_type")),
            line_items=items,
            unparsed_rows=unparsed,
            total_claimed=parse_total(text),
        )

    def extract_discharge(self, text: str) -> DischargeSummary:
        kv = _kv_pairs(text)
        mode = (kv.get("mode") or "").lower()
        cause = (kv.get("cause") or "").lower()
        return DischargeSummary(
            patient_name=clean(kv.get("patient_name")),
            diagnosis=clean(kv.get("diagnosis")),
            procedure=clean(kv.get("procedure")),
            admission_date=parse_date(kv.get("admission_date")),
            discharge_date=parse_date(kv.get("discharge_date")),
            history_of_condition_years=parse_history_years(kv.get("history")),
            is_emergency=("emergency" in mode) if mode else None,
            is_accident=("accident" in cause or "injury" in cause or "trauma" in cause)
            if cause
            else None,
            treating_doctor=clean(kv.get("doctor")),
        )


def parse_amount_text(text: str) -> float | None:  # re-exported for tests
    return parse_amount(text)
