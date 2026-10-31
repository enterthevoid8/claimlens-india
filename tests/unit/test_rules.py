from datetime import date

import pytest

from claimlens.domain.models import (
    DischargeSummary,
    DocumentRef,
    DocumentType,
    ExtractedClaimData,
    HospitalBill,
    ItemCategory,
    LineItem,
    RuleStatus,
    Severity,
)
from claimlens.rules.base import RuleContext, RuleEngine
from claimlens.rules.builtin import (
    Arithmetic,
    Dates,
    DocumentIntegrity,
    DocumentsComplete,
    Exclusions,
    InitialWaiting,
    NetworkHospital,
    PatientIdentity,
    PolicyPeriod,
    PreAuth,
    PreExisting,
    RoomRent,
    SpecificWaiting,
    SumInsured,
    default_rules,
)
from claimlens.rules.policy_loader import instantiate_policy

TODAY = date(2026, 6, 30)


def policy(**kw):  # type: ignore[no-untyped-def]
    p = instantiate_policy(
        "shield_plus",
        policy_id="P1",
        tenant_id="t1",
        holder_name="Asha Rao",
        start_date=date(2023, 1, 1),
        sum_insured=500_000,
        term_years=5,
    )
    return p.model_copy(update=kw)


def bill(**kw):  # type: ignore[no-untyped-def]
    base = dict(
        bill_number="B1",
        hospital_name="Sunrise Care Hospital",
        patient_name="Asha Rao",
        admission_date=date(2025, 3, 1),
        discharge_date=date(2025, 3, 4),
        diagnosis="Acute appendicitis",
        procedure="Laparoscopic appendectomy",
        total_claimed=11_000.0,
        line_items=[
            LineItem(
                description="Room rent - Semi private",
                category=ItemCategory.ROOM,
                quantity=3,
                unit_price=3000,
                amount=9000,
            ),
            LineItem(
                description="CBC",
                category=ItemCategory.DIAGNOSTIC,
                quantity=1,
                unit_price=2000,
                amount=2000,
            ),
        ],
    )
    return HospitalBill(**{**base, **kw})


def discharge(**kw):  # type: ignore[no-untyped-def]
    base = dict(
        patient_name="Asha Rao",
        diagnosis="Acute appendicitis",
        admission_date=date(2025, 3, 1),
        discharge_date=date(2025, 3, 4),
        history_of_condition_years=0.0,
        is_emergency=True,
        is_accident=False,
    )
    return DischargeSummary(**{**base, **kw})


def ctx(
    p=None,
    b="default",
    d="default",
    docs=(DocumentType.HOSPITAL_BILL, DocumentType.DISCHARGE_SUMMARY),
    **data_kw,
):  # type: ignore[no-untyped-def]
    data = ExtractedClaimData(
        bill=bill() if b == "default" else b,
        discharge=discharge() if d == "default" else d,
        **data_kw,
    )
    refs = [
        DocumentRef(
            filename=str(t),
            content_type="text/plain",
            blob_path="x",
            sha256="0",
            size_bytes=1,
            doc_type=t,
        )
        for t in docs
    ]
    return RuleContext(policy=p or policy(), data=data, documents=refs, today=TODAY)


def test_happy_path_has_no_failures() -> None:
    results = RuleEngine(default_rules()).run(
        ctx(network=None) if False else ctx(p=policy(network_hospitals=["Sunrise Care Hospital"]))
    )
    assert [r.rule_id for r in results if r.status == RuleStatus.FAIL] == []


def test_policy_period() -> None:
    assert PolicyPeriod().evaluate(ctx()).status == RuleStatus.PASS
    assert (
        PolicyPeriod().evaluate(ctx(b=bill(admission_date=date(2022, 1, 1)), d=None)).status
        == RuleStatus.FAIL
    )
    assert (
        PolicyPeriod().evaluate(ctx(b=bill(admission_date=None), d=None)).status
        == RuleStatus.UNKNOWN
    )


def test_initial_waiting_accident_exemption_and_unknown_cause() -> None:
    p = policy(start_date=date(2025, 2, 20))
    r = InitialWaiting().evaluate(ctx(p=p, d=discharge(is_accident=False)))
    assert r.status == RuleStatus.FAIL and r.severity == Severity.BLOCKER
    assert (
        InitialWaiting().evaluate(ctx(p=p, d=discharge(is_accident=True))).status == RuleStatus.PASS
    )
    assert (
        InitialWaiting().evaluate(ctx(p=p, d=discharge(is_accident=None))).status
        == RuleStatus.UNKNOWN
    )
    assert InitialWaiting().evaluate(ctx(p=p, d=None)).status == RuleStatus.UNKNOWN


def test_specific_waiting() -> None:
    cat = bill(diagnosis="Senile cataract", procedure="Phacoemulsification with IOL")
    young = policy(start_date=date(2024, 6, 1))  # ~9 months, cataract needs 730 days
    assert SpecificWaiting().evaluate(ctx(p=young, b=cat)).status == RuleStatus.FAIL
    assert (
        SpecificWaiting().evaluate(ctx(p=policy(start_date=date(2021, 1, 1)), b=cat)).status
        == RuleStatus.PASS
    )
    assert (
        SpecificWaiting().evaluate(ctx(b=bill(diagnosis=None, procedure=None), d=None)).status
        == RuleStatus.UNKNOWN
    )


def test_pre_existing() -> None:
    p = policy(start_date=date(2024, 9, 1))  # 181 days in force at admission
    assert (
        PreExisting().evaluate(ctx(p=p, d=discharge(history_of_condition_years=5))).status
        == RuleStatus.FAIL
    )
    assert (
        PreExisting().evaluate(ctx(p=p, d=discharge(history_of_condition_years=0))).status
        == RuleStatus.PASS
    )
    assert (
        PreExisting().evaluate(ctx(p=p, d=discharge(history_of_condition_years=None))).status
        == RuleStatus.UNKNOWN
    )  # not stated != none
    assert PreExisting().evaluate(ctx(p=p, d=None)).status == RuleStatus.UNKNOWN


def test_exclusions() -> None:
    assert (
        Exclusions().evaluate(ctx(b=bill(procedure="Cosmetic rhinoplasty"))).status
        == RuleStatus.FAIL
    )
    assert Exclusions().evaluate(ctx()).status == RuleStatus.PASS
    assert (
        Exclusions().evaluate(ctx(b=bill(diagnosis=None, procedure=None), d=None)).status
        == RuleStatus.UNKNOWN
    )


def test_room_rent_cap_proportional_deduction() -> None:
    p = policy(room_rent_cap_per_day=2000.0)
    r = RoomRent().evaluate(ctx(p=p))
    assert r.status == RuleStatus.FAIL and "33%" in r.message  # 2000/3000 -> one third reduction
    assert RoomRent().evaluate(ctx(p=policy(room_rent_cap_per_day=None))).status == RuleStatus.PASS
    no_room = bill(
        line_items=[LineItem(description="CBC", category=ItemCategory.DIAGNOSTIC, amount=350)]
    )
    assert RoomRent().evaluate(ctx(p=p, b=no_room)).status == RuleStatus.UNKNOWN
    daycare = bill(
        admission_date=date(2025, 3, 1),
        discharge_date=date(2025, 3, 1),
        line_items=no_room.line_items,
    )
    assert RoomRent().evaluate(ctx(p=p, b=daycare)).status == RuleStatus.PASS


def test_sum_insured() -> None:
    assert SumInsured().evaluate(ctx(b=bill(total_claimed=600_000))).status == RuleStatus.FAIL
    assert SumInsured().evaluate(ctx()).status == RuleStatus.PASS
    assert SumInsured().evaluate(ctx(b=bill(total_claimed=None))).status == RuleStatus.UNKNOWN


def test_arithmetic() -> None:
    assert Arithmetic().evaluate(ctx()).status == RuleStatus.PASS
    assert Arithmetic().evaluate(ctx(b=bill(total_claimed=12_500))).status == RuleStatus.FAIL
    bad_line = bill(
        line_items=[LineItem(description="X", quantity=3, unit_price=100, amount=500)],
        total_claimed=500,
    )
    assert Arithmetic().evaluate(ctx(b=bad_line)).status == RuleStatus.FAIL
    assert Arithmetic().evaluate(ctx(b=bill(line_items=[]))).status == RuleStatus.UNKNOWN
    assert (
        Arithmetic().evaluate(ctx(b=bill(unparsed_rows=["3 | Surgeon | 1 | 5,0O0.00"]))).status
        == RuleStatus.UNKNOWN
    )  # unreadable row: cannot verify


def test_dates() -> None:
    assert Dates().evaluate(ctx()).status == RuleStatus.PASS
    assert (
        Dates().evaluate(ctx(b=bill(discharge_date=date(2025, 2, 1)), d=None)).severity
        == Severity.BLOCKER
    )
    assert (
        Dates().evaluate(ctx(b=bill(discharge_date=date(2030, 1, 1)), d=None)).status
        == RuleStatus.FAIL
    )
    assert (
        Dates().evaluate(ctx(d=discharge(discharge_date=date(2025, 3, 5)))).status
        == RuleStatus.FAIL
    )
    assert (
        Dates().evaluate(ctx(b=bill(admission_date=None, discharge_date=None), d=None)).status
        == RuleStatus.UNKNOWN
    )


def test_documents_complete() -> None:
    assert DocumentsComplete().evaluate(ctx()).status == RuleStatus.PASS
    r = DocumentsComplete().evaluate(ctx(docs=(DocumentType.HOSPITAL_BILL,)))
    assert r.status == RuleStatus.FAIL and "discharge summary" in r.message


def test_preauth() -> None:
    big = bill(total_claimed=250_000)
    assert PreAuth().evaluate(ctx(b=big, d=discharge(is_emergency=False))).status == RuleStatus.FAIL
    assert (
        PreAuth()
        .evaluate(ctx(b=big, d=discharge(is_emergency=False), has_preauth_approval=True))
        .status
        == RuleStatus.PASS
    )
    assert PreAuth().evaluate(ctx(b=big, d=discharge(is_emergency=True))).status == RuleStatus.PASS
    assert (
        PreAuth().evaluate(ctx(b=big, d=discharge(is_emergency=None))).status == RuleStatus.UNKNOWN
    )
    assert PreAuth().evaluate(ctx()).status == RuleStatus.PASS


def test_network() -> None:
    assert (
        NetworkHospital().evaluate(ctx(p=policy(network_hospitals=[]))).status == RuleStatus.UNKNOWN
    )
    assert (
        NetworkHospital()
        .evaluate(ctx(p=policy(network_hospitals=["Sunrise Care Hospital"])))
        .status
        == RuleStatus.PASS
    )
    assert (
        NetworkHospital().evaluate(ctx(p=policy(network_hospitals=["Other Hospital"]))).status
        == RuleStatus.FAIL
    )


def test_patient_identity() -> None:
    assert PatientIdentity().evaluate(ctx()).status == RuleStatus.PASS
    assert (
        PatientIdentity().evaluate(ctx(d=discharge(patient_name="Asha K Rao"))).status
        == RuleStatus.PASS
    )  # subset of tokens
    assert (
        PatientIdentity().evaluate(ctx(d=discharge(patient_name="Vikram Joshi"))).status
        == RuleStatus.FAIL
    )
    assert PatientIdentity().evaluate(ctx(d=None)).status == RuleStatus.UNKNOWN


def test_document_integrity() -> None:
    assert DocumentIntegrity().evaluate(ctx()).status == RuleStatus.PASS
    assert (
        DocumentIntegrity()
        .evaluate(ctx(injection_flags=["instruction_override: line 4: ignore ..."]))
        .status
        == RuleStatus.FAIL
    )


class Boom:
    rule_id, title = "RX", "always crashes"

    def evaluate(self, c):  # type: ignore[no-untyped-def]
        raise RuntimeError("bug")


def test_crashing_rule_becomes_unknown_never_pass() -> None:
    results = RuleEngine([Boom()]).run(ctx())
    assert results[0].status == RuleStatus.UNKNOWN and results[0].severity == Severity.WARN


@pytest.mark.parametrize("missing", ["bill", "discharge", "both"])
def test_missing_documents_never_produce_a_clean_pass(missing: str) -> None:
    b = None if missing in ("bill", "both") else "default"
    d = None if missing in ("discharge", "both") else "default"
    results = RuleEngine(default_rules()).run(ctx(b=b, d=d))
    assert any(r.status != RuleStatus.PASS for r in results)
    assert all(
        r.status != RuleStatus.PASS
        for r in results
        if r.rule_id in {"R007", "R008", "R013"} and b is None
    )
