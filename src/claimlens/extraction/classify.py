"""Document type classification. Keyword scoring offline; Azure custom classifier is an adapter."""

from __future__ import annotations

from claimlens.domain.models import DocumentType

_SIGNALS: dict[DocumentType, tuple[str, ...]] = {
    DocumentType.HOSPITAL_BILL: (
        "final bill",
        "tax invoice",
        "bill no",
        "invoice no",
        "grand total",
        "amount",
        "rate",
        "qty",
    ),
    DocumentType.DISCHARGE_SUMMARY: (
        "discharge summary",
        "condition at discharge",
        "treating doctor",
        "diagnosis",
        "mode of admission",
        "advice on discharge",
    ),
    DocumentType.PREAUTH_APPROVAL: (
        "pre-authorization",
        "pre-authorisation",
        "preauth",
        "cashless approval",
        "authorization letter",
        "authorisation letter",
    ),
    DocumentType.ID_PROOF: (
        "aadhaar",
        "passport",
        "voter id",
        "driving licence",
        "pan card",
        "identity proof",
    ),
    DocumentType.CLAIM_FORM: ("claim form", "claimant", "declaration by the insured"),
    DocumentType.PRESCRIPTION: ("prescription", "rx", "dosage"),
    DocumentType.LAB_REPORT: (
        "lab report",
        "reference range",
        "specimen",
        "haemoglobin",
        "hemoglobin",
    ),
}

# Header phrases are worth more than incidental words.
_STRONG = {
    "final bill",
    "tax invoice",
    "discharge summary",
    "pre-authorization",
    "pre-authorisation",
    "claim form",
    "lab report",
}


def classify_document(text: str, filename: str = "") -> DocumentType:
    haystack = (filename + "\n" + text[:4000]).lower()
    best, best_score = DocumentType.OTHER, 0
    for doc_type, needles in _SIGNALS.items():
        score = sum(3 if n in _STRONG else 1 for n in needles if n in haystack)
        if score > best_score:
            best, best_score = doc_type, score
    return best if best_score >= 3 else DocumentType.OTHER
