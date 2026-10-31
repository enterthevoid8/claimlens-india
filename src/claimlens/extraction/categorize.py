"""Map free-text bill descriptions to coarse categories. Shared by every extractor."""

from __future__ import annotations

from claimlens.domain.models import ItemCategory

_RULES: list[tuple[ItemCategory, tuple[str, ...]]] = [
    (ItemCategory.PACKAGE, ("package", "all inclusive", "all-inclusive")),
    (ItemCategory.ICU, ("icu", "iccu", "nicu", "intensive care")),
    (
        ItemCategory.ROOM,
        (
            "room rent",
            "room charge",
            "bed charge",
            "ward charge",
            "room -",
            "private room",
            "semi private",
            "semi-private",
            "twin sharing",
            "general ward",
        ),
    ),
    (ItemCategory.NURSING, ("nursing",)),
    (ItemCategory.SURGEON, ("surgeon",)),
    (ItemCategory.ANAESTHESIA, ("anaesthesia", "anesthesia", "anaesthetist", "anesthetist")),
    (
        ItemCategory.OT,
        ("operation theatre", "operation theater", "ot charge", "theatre charge", "ot -"),
    ),
    (
        ItemCategory.DOCTOR_FEE,
        ("consultation", "visit charge", "doctor", "physician", "specialist"),
    ),
    (
        ItemCategory.DIAGNOSTIC,
        (
            "x-ray",
            "xray",
            "ct scan",
            "mri",
            "ultrasound",
            "usg",
            "blood test",
            "cbc",
            "lab",
            "pathology",
            "ecg",
            "2d echo",
            "biopsy",
            "culture",
            "diagnostic",
            "test",
        ),
    ),
    (
        ItemCategory.PROCEDURE,
        (
            "procedure",
            "endoscopy",
            "dialysis",
            "angioplasty",
            "biopsy procedure",
            "phaco",
            "implant",
            "stent",
        ),
    ),
    (
        ItemCategory.MEDICINE,
        (
            "medicine",
            "tablet",
            "injection",
            "inj.",
            "inj ",
            "iv fluid",
            "drug",
            "pharmacy",
            "antibiotic",
            "syrup",
        ),
    ),
    (
        ItemCategory.CONSUMABLE,
        (
            "consumable",
            "gloves",
            "mask",
            "syringe",
            "catheter",
            "dressing",
            "disposable",
            "surgical kit",
            "suture",
            "kit",
        ),
    ),
    (
        ItemCategory.ADMIN,
        (
            "registration",
            "admission fee",
            "admin",
            "documentation",
            "file charge",
            "service charge",
            "gst",
            "tax",
        ),
    ),
]


def categorize(description: str) -> ItemCategory:
    d = description.lower()
    for category, needles in _RULES:
        if any(n in d for n in needles):
            return category
    return ItemCategory.OTHER
