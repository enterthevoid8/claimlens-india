"""Domain models.

Everything here is plain Pydantic: no Azure types, no I/O. Extraction output is deliberately
permissive (optional fields, no cross-field validators) so that bad or missing data surfaces as a
rule result of ``unknown``/``fail`` instead of an exception that hides the problem.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


# --------------------------------------------------------------------------- enums


class DocumentType(StrEnum):
    HOSPITAL_BILL = "hospital_bill"
    DISCHARGE_SUMMARY = "discharge_summary"
    PREAUTH_APPROVAL = "preauth_approval"
    ID_PROOF = "id_proof"
    CLAIM_FORM = "claim_form"
    PRESCRIPTION = "prescription"
    LAB_REPORT = "lab_report"
    OTHER = "other"


class ItemCategory(StrEnum):
    ROOM = "room"
    ICU = "icu"
    NURSING = "nursing"
    DOCTOR_FEE = "doctor_fee"
    SURGEON = "surgeon"
    ANAESTHESIA = "anaesthesia"
    OT = "ot"
    PROCEDURE = "procedure"
    MEDICINE = "medicine"
    CONSUMABLE = "consumable"
    DIAGNOSTIC = "diagnostic"
    PACKAGE = "package"
    ADMIN = "admin"
    OTHER = "other"


class ClaimStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    READY = "ready"  # analysed, waiting for a human
    NEEDS_INFO = "needs_info"  # analysed, documents or answers missing
    FAILED = "failed"
    DECIDED = "decided"


class RuleStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"  # not enough information: never treated as a pass


class Severity(StrEnum):
    INFO = "info"
    WARN = "warn"
    BLOCKER = "blocker"


class RiskBand(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DecisionType(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_INFO = "request_info"


class Role(StrEnum):
    PATIENT = "patient"
    HOSPITAL = "hospital"
    REVIEWER = "reviewer"


# --------------------------------------------------------------------------- evidence & extraction


class Evidence(BaseModel):
    """Pointer back to the source text for a fact or a rule outcome."""

    document_id: str | None = None
    page: int | None = None
    field: str | None = None
    text: str = ""


class LineItem(BaseModel):
    description: str
    category: ItemCategory = ItemCategory.OTHER
    quantity: float = 1.0
    unit_price: float | None = None
    amount: float
    code: str | None = None
    service_date: date | None = None
    page: int | None = None


class HospitalBill(BaseModel):
    bill_number: str | None = None
    hospital_name: str | None = None
    city: str | None = None
    patient_name: str | None = None
    admission_date: date | None = None
    discharge_date: date | None = None
    diagnosis: str | None = None
    procedure: str | None = None
    room_type: str | None = None
    line_items: list[LineItem] = Field(default_factory=list)
    total_claimed: float | None = None
    unparsed_rows: list[str] = Field(
        default_factory=list
    )  # table rows that looked like items but could not be read
    document_id: str | None = None


class DischargeSummary(BaseModel):
    patient_name: str | None = None
    diagnosis: str | None = None
    procedure: str | None = None
    admission_date: date | None = None
    discharge_date: date | None = None
    history_of_condition_years: float | None = None  # None means "not stated"
    is_emergency: bool | None = None
    is_accident: bool | None = None
    treating_doctor: str | None = None
    document_id: str | None = None


class ExtractedClaimData(BaseModel):
    bill: HospitalBill | None = None
    discharge: DischargeSummary | None = None
    has_preauth_approval: bool = False
    injection_flags: list[str] = Field(default_factory=list)
    unreadable_documents: list[str] = Field(default_factory=list)  # "filename: reason"
    extraction_confidence: float = 1.0  # 0..1, share of expected fields found
    extractor: str = "unknown"


# --------------------------------------------------------------------------- policy


class Exclusion(BaseModel):
    code: str
    title: str
    keywords: list[str]
    clause: str


class WaitingPeriod(BaseModel):
    condition: str
    keywords: list[str]
    days: int
    clause: str = "2.2"


class Sublimit(BaseModel):
    procedure: str
    keywords: list[str]
    max_amount: float
    clause: str = "6.1"


class Policy(BaseModel):
    policy_id: str
    tenant_id: str
    insurer: str = "Example Insurer"
    product_name: str
    holder_name: str
    start_date: date
    end_date: date
    sum_insured: float
    copay_pct: float = 0.0
    room_rent_cap_per_day: float | None = None
    initial_waiting_days: int = 30
    pre_existing_waiting_days: int = 1095
    preauth_required_above: float = 100_000.0
    waiting_periods: list[WaitingPeriod] = Field(default_factory=list)
    exclusions: list[Exclusion] = Field(default_factory=list)
    sublimits: list[Sublimit] = Field(default_factory=list)
    network_hospitals: list[str] = Field(default_factory=list)
    required_documents: list[DocumentType] = Field(
        default_factory=lambda: [DocumentType.HOSPITAL_BILL, DocumentType.DISCHARGE_SUMMARY]
    )


# --------------------------------------------------------------------------- analysis


class RuleResult(BaseModel):
    rule_id: str
    title: str
    status: RuleStatus
    severity: Severity = Severity.INFO
    message: str
    clause: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class RiskReason(BaseModel):
    feature: str
    contribution: float  # log-odds contribution from the tree model (TreeSHAP)
    direction: str  # "increases" | "decreases"
    text: str


class RiskScore(BaseModel):
    probability: float  # calibrated P(claim is queried or reduced by the insurer)
    band: RiskBand
    reasons: list[RiskReason] = Field(default_factory=list)
    model_version: str


class AnomalyFlag(BaseModel):
    code: str
    description: str
    score: float = 0.0
    evidence: list[Evidence] = Field(default_factory=list)


class ClaimAnalysis(BaseModel):
    claim_id: str
    extracted: ExtractedClaimData
    rules: list[RuleResult] = Field(default_factory=list)
    anomalies: list[AnomalyFlag] = Field(default_factory=list)
    risk: RiskScore | None = None
    missing_documents: list[DocumentType] = Field(default_factory=list)
    features: dict[str, float | None] = Field(default_factory=dict)  # model inputs, kept for audit
    summary: str = ""
    suggested_route: str = "review"  # "review" | "request_info"; never an approval or rejection
    pipeline_version: str = "0.1.0"
    created_at: datetime = Field(default_factory=utcnow)


# --------------------------------------------------------------------------- claim


class DocumentRef(BaseModel):
    document_id: str = Field(default_factory=lambda: new_id("doc"))
    filename: str
    content_type: str
    blob_path: str
    sha256: str
    size_bytes: int
    doc_type: DocumentType | None = None
    uploaded_at: datetime = Field(default_factory=utcnow)


class ReviewerDecision(BaseModel):
    decision: DecisionType
    reviewer_id: str
    note: str = ""
    decided_at: datetime = Field(default_factory=utcnow)
    model_config = ConfigDict(use_enum_values=False)


class Claim(BaseModel):
    claim_id: str = Field(default_factory=lambda: new_id("clm"))
    tenant_id: str
    policy_id: str
    submitted_by: str
    consent_given: bool
    status: ClaimStatus = ClaimStatus.RECEIVED
    documents: list[DocumentRef] = Field(default_factory=list)
    analysis: ClaimAnalysis | None = None
    decision: ReviewerDecision | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class AuditEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: new_id("evt"))
    tenant_id: str
    actor: str
    action: str
    resource: str
    at: datetime = Field(default_factory=utcnow)
    details: dict[str, Any] = Field(default_factory=dict)


class ClaimJob(BaseModel):
    """Queue message. Carries ids only: never document content or personal data."""

    tenant_id: str
    claim_id: str
    attempt: int = 0
