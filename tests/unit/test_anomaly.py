from datetime import date

from claimlens.domain.models import HospitalBill, ItemCategory, LineItem
from claimlens.extraction.categorize import categorize
from claimlens.ml.anomaly import analyse_lines
from claimlens.ml.price_book import default_price_book


def item(desc: str, qty: float, unit: float) -> LineItem:
    return LineItem(
        description=desc,
        category=categorize(desc),
        quantity=qty,
        unit_price=unit,
        amount=qty * unit,
    )


def bill(items: list[LineItem], **kw) -> HospitalBill:  # type: ignore[no-untyped-def]
    return HospitalBill(
        city="Pune",
        procedure="Laparoscopic appendectomy",
        admission_date=date(2025, 3, 1),
        discharge_date=date(2025, 3, 4),
        line_items=items,
        **kw,
    )


def codes(b: HospitalBill) -> set[str]:
    return {f.code for f in analyse_lines(b).flags}


def test_price_book_matches_items() -> None:
    book = default_price_book()
    assert book.match("Room rent - Semi private") == "room_semi"
    assert book.match("Room rent - Private") == "room_private"
    assert (
        book.match("Surgeon fee - Laparoscopic appendectomy", "Laparoscopic appendectomy")
        == "surgeon|appendectomy"
    )
    assert book.match("Mystery item") is None


def test_normal_prices_are_not_flagged() -> None:
    assert (
        codes(
            bill(
                [
                    item("Room rent - Semi private", 3, 3000),
                    item("CBC (complete blood count)", 1, 350),
                ]
            )
        )
        == set()
    )


def test_inflated_price_is_flagged_with_evidence() -> None:
    a = analyse_lines(bill([item("CBC (complete blood count)", 1, 1200)]))
    flag = next(f for f in a.flags if f.code == "price_outlier")
    assert "3.4x" in flag.description and flag.evidence and a.price_z_max > 3


def test_city_multiplier_is_applied() -> None:
    b = bill([item("Room rent - Semi private", 3, 3600)])
    b.city = "Mumbai"  # 3000 * 1.25 = 3750 expected
    assert "price_outlier" not in codes(b)
    b.city = "Patna"  # 3000 * 0.7 = 2100 expected: 3600 is 1.7x
    assert analyse_lines(b).price_z_max > 2


def test_duplicate_lines_flagged_but_repeat_medicines_are_not() -> None:
    assert "duplicate_line" in codes(bill([item("ECG", 2, 400), item("ECG", 2, 400)]))
    assert "duplicate_line" not in codes(
        bill([item("Injection Ceftriaxone 1g", 4, 85), item("Injection Ceftriaxone 1g", 4, 85)])
    )


def test_unbundling() -> None:
    items = [
        item("Surgical package (all inclusive) - Laparoscopic appendectomy", 1, 54000),
        item("Surgeon fee - Laparoscopic appendectomy", 1, 14400),
    ]
    assert "unbundled_package" in codes(bill(items))
    assert "unbundled_package" not in codes(
        bill([item("Surgeon fee - Laparoscopic appendectomy", 1, 14400)])
    )


def test_days_billed_beyond_stay() -> None:
    assert "days_exceed_stay" in codes(bill([item("Room rent - Semi private", 7, 3000)]))
    assert "days_exceed_stay" not in codes(bill([item("Room rent - Semi private", 3, 3000)]))


def test_unmatched_items_are_not_price_checked_and_reported() -> None:
    a = analyse_lines(bill([item("Mystery item", 1, 99999), item("ECG", 1, 400)]))
    assert a.price_checked_share == 0.5 and not a.flags
    assert categorize("Mystery item") == ItemCategory.OTHER
