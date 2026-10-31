from datetime import date

import pytest

from claimlens.extraction.parsing import normalize_name, parse_amount, parse_date


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("12/03/2025", date(2025, 3, 12)),
        ("12-03-2025", date(2025, 3, 12)),
        ("12 Mar 2025", date(2025, 3, 12)),
        ("2025-03-12", date(2025, 3, 12)),
        ("12/03/25", date(2025, 3, 12)),
        ("5th March 2024", date(2024, 3, 5)),
        ("DOA: 01/02/2024 10:30", date(2024, 2, 1)),
        ("31/02/2025", None),
        ("not a date", None),
        (None, None),
    ],
)
def test_parse_date_is_day_first(text: str | None, expected: date | None) -> None:
    assert parse_date(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Rs. 12,000.00", 12000.0),
        ("₹2,24,003.00", 224003.0),
        ("Rs 1,500/-", 1500.0),
        ("INR 99", 99.0),
        ("4000", 4000.0),
        ("abc", None),
        (None, None),
    ],
)
def test_parse_amount_handles_indian_grouping(text: str | None, expected: float | None) -> None:
    assert parse_amount(text) == expected


def test_normalize_name_strips_titles() -> None:
    assert normalize_name("Mr. Rahul Sharma") == "rahul sharma"
    assert normalize_name("DR. A. Banerjee") == "a banerjee"
    assert normalize_name(None) == ""
