"""Built-in rules. Each one cites the policy clause it enforces and the evidence it used."""

from __future__ import annotations

from difflib import SequenceMatcher

from claimlens.domain.models import (
    DocumentType,
    Evidence,
    ItemCategory,
    RuleResult,
    RuleStatus,
    Severity,
)
from claimlens.extraction.parsing import normalize_name
from claimlens.rules.base import Rule, RuleContext

PASS, FAIL, UNKNOWN = RuleStatus.PASS, RuleStatus.FAIL, RuleStatus.UNKNOWN


def _res(
    rule: Rule,
    status: RuleStatus,
    message: str,
    severity: Severity = Severity.INFO,
    clause: str | None = None,
    evidence: list[Evidence] | None = None,
) -> RuleResult:
    return RuleResult(
        rule_id=rule.rule_id,
        title=rule.title,
        status=status,
        severity=severity if status != PASS else Severity.INFO,
        message=message,
        clause=clause,
        evidence=evidence or [],
    )


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _fmt(x: float) -> str:
    return f"Rs {x:,.0f}"


def _name_similarity(a: str | None, b: str | None) -> float | None:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return None
    ta, tb = set(na.split()), set(nb.split())
    if ta <= tb or tb <= ta:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _same_hospital(a: str, b: str) -> bool:
    na, nb = normalize_name(a), normalize_name(b)
    return bool(
        na and nb and (na in nb or nb in na or SequenceMatcher(None, na, nb).ratio() >= 0.85)
    )


class PolicyPeriod:
    rule_id, title = "R001", "Admission falls within the policy period"

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        adm = ctx.admission_date
        if adm is None:
            return _res(self, UNKNOWN, "Admission date could not be read.", Severity.WARN, "1.2")
        p = ctx.policy
        ev = [Evidence(field="admission_date", text=adm.isoformat())]
        if adm < p.start_date or adm > p.end_date:
            return _res(
                self,
                FAIL,
                f"Admission on {adm} is outside the policy period {p.start_date} to {p.end_date}.",
                Severity.BLOCKER,
                "1.2",
                ev,
            )
        return _res(self, PASS, "Admission is within the policy period.", clause="1.2", evidence=ev)


class InitialWaiting:
    rule_id, title = "R002", "Initial waiting period"

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        adm, p = ctx.admission_date, ctx.policy
        if adm is None:
            return _res(self, UNKNOWN, "Admission date could not be read.", Severity.WARN, "2.1")
        days = (adm - p.start_date).days
        if days >= p.initial_waiting_days:
            return _res(
                self,
                PASS,
                f"Admission is {days} days after inception (waiting period {p.initial_waiting_days} days).",
                clause="2.1",
            )
        accident = ctx.data.discharge.is_accident if ctx.data.discharge else None
        if accident is True:
            return _res(
                self,
                PASS,
                "Within the initial waiting period, but the discharge summary states an accident, which is exempt.",
                clause="2.1",
            )
        if accident is None:
            return _res(
                self,
                UNKNOWN,
                f"Admission is only {days} days after inception and the cause (accident or illness) is not stated.",
                Severity.BLOCKER,
                "2.1",
            )
        return _res(
            self,
            FAIL,
            f"Admission is {days} days after inception, inside the {p.initial_waiting_days}-day initial waiting period, and the cause is not an accident.",
            Severity.BLOCKER,
            "2.1",
        )


class SpecificWaiting:
    rule_id, title = "R003", "Condition-specific waiting period"

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        adm, p = ctx.admission_date, ctx.policy
        text = ctx.diagnosis_text
        if not text:
            return _res(self, UNKNOWN, "Diagnosis could not be read.", Severity.WARN, "2.2")
        hits = [w for w in p.waiting_periods if any(k in text for k in w.keywords)]
        if not hits:
            return _res(
                self,
                PASS,
                "No condition-specific waiting period applies to the stated diagnosis or procedure.",
                clause="2.2",
            )
        if adm is None:
            return _res(
                self,
                UNKNOWN,
                "A waiting period may apply but the admission date could not be read.",
                Severity.WARN,
                "2.2",
            )
        elapsed = (adm - p.start_date).days
        accident = ctx.data.discharge.is_accident if ctx.data.discharge else None
        for w in hits:
            if elapsed < w.days and accident is not True:
                return _res(
                    self,
                    FAIL,
                    f"{w.condition} has a {w.days}-day waiting period; admission is {elapsed} days after inception.",
                    Severity.BLOCKER,
                    w.clause,
                    [Evidence(field="diagnosis", text=text[:160])],
                )
        names = ", ".join(w.condition for w in hits)
        return _res(self, PASS, f"Waiting period for {names} has been served.", clause="2.2")


class PreExisting:
    rule_id, title = "R004", "Pre-existing condition"

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        d, adm, p = ctx.data.discharge, ctx.admission_date, ctx.policy
        if d is None:
            return _res(
                self,
                UNKNOWN,
                "No discharge summary, so condition history cannot be checked.",
                Severity.WARN,
                "2.3",
            )
        if d.history_of_condition_years is None:
            return _res(
                self,
                UNKNOWN,
                "The discharge summary does not state how long the condition has existed.",
                Severity.WARN,
                "2.3",
            )
        if adm is None:
            return _res(self, UNKNOWN, "Admission date could not be read.", Severity.WARN, "2.3")
        policy_age_days = (adm - p.start_date).days
        history_days = d.history_of_condition_years * 365
        ev = [
            Evidence(
                document_id=d.document_id,
                field="history",
                text=f"{d.history_of_condition_years:g} years",
            )
        ]
        if history_days > policy_age_days and policy_age_days < p.pre_existing_waiting_days:
            return _res(
                self,
                FAIL,
                f"The condition is stated to be {d.history_of_condition_years:g} years old, older than the policy ({policy_age_days} days), and the pre-existing waiting period is {p.pre_existing_waiting_days} days.",
                Severity.BLOCKER,
                "2.3",
                ev,
            )
        return _res(
            self,
            PASS,
            "Condition history does not conflict with the pre-existing waiting period.",
            clause="2.3",
            evidence=ev,
        )


class Exclusions:
    rule_id, title = "R005", "Permanent exclusions"

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        text = ctx.diagnosis_text
        if not text:
            return _res(
                self, UNKNOWN, "Diagnosis and procedure could not be read.", Severity.WARN, "3.1"
            )
        for ex in ctx.policy.exclusions:
            if any(k in text for k in ex.keywords):
                return _res(
                    self,
                    FAIL,
                    f"Matches exclusion '{ex.title}'.",
                    Severity.BLOCKER,
                    ex.clause,
                    [Evidence(field="diagnosis", text=text[:160])],
                )
        return _res(
            self, PASS, "No exclusion keywords matched the diagnosis or procedure.", clause="3.1"
        )


class RoomRent:
    rule_id, title = "R006", "Room rent limit"

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        cap, bill = ctx.policy.room_rent_cap_per_day, ctx.data.bill
        if cap is None:
            return _res(self, PASS, "The policy has no room rent limit.", clause="4.1")
        if bill is None:
            return _res(self, UNKNOWN, "No bill available.", Severity.WARN, "4.1")
        rooms = [i for i in bill.line_items if i.category == ItemCategory.ROOM]
        if not rooms:
            if bill.admission_date and bill.admission_date == bill.discharge_date:
                return _res(self, PASS, "Day-care stay: no room rent charged.", clause="4.1")
            return _res(
                self, UNKNOWN, "No room charge line was found on the bill.", Severity.WARN, "4.1"
            )
        worst = max(rooms, key=lambda i: i.unit_price or i.amount)
        rate = worst.unit_price or worst.amount
        if rate > cap:
            ratio = cap / rate
            return _res(
                self,
                FAIL,
                f"Room rent {_fmt(rate)}/day exceeds the limit {_fmt(cap)}/day. Proportionate deduction of about {100 * (1 - ratio):.0f}% may apply to related charges.",
                Severity.WARN,
                "4.1",
                [Evidence(document_id=bill.document_id, field="line_item", text=worst.description)],
            )
        return _res(
            self,
            PASS,
            f"Room rent {_fmt(rate)}/day is within the limit {_fmt(cap)}/day.",
            clause="4.1",
        )


class SumInsured:
    rule_id, title = "R007", "Claim within sum insured"

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        bill = ctx.data.bill
        if bill is None or bill.total_claimed is None:
            return _res(self, UNKNOWN, "Claimed total could not be read.", Severity.WARN, "1.1")
        si = ctx.policy.sum_insured
        if bill.total_claimed > si:
            return _res(
                self,
                FAIL,
                f"Claimed {_fmt(bill.total_claimed)} exceeds the sum insured {_fmt(si)}.",
                Severity.WARN,
                "1.1",
            )
        return _res(
            self,
            PASS,
            f"Claimed {_fmt(bill.total_claimed)} is within the sum insured {_fmt(si)}.",
            clause="1.1",
        )


class Arithmetic:
    rule_id, title = "R008", "Bill arithmetic is consistent"

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        bill = ctx.data.bill
        if (
            bill is None
            or bill.total_claimed is None
            or not (bill.line_items or bill.unparsed_rows)
        ):
            return _res(
                self,
                UNKNOWN,
                "Line items or the total could not be read, so the arithmetic cannot be verified.",
                Severity.WARN,
            )
        if bill.unparsed_rows:
            return _res(
                self,
                UNKNOWN,
                f"{len(bill.unparsed_rows)} bill line(s) could not be read (e.g. '{bill.unparsed_rows[0][:60]}'), so the total cannot be verified. Please check the original.",
                Severity.WARN,
                evidence=[
                    Evidence(document_id=bill.document_id, field="line_item", text=r)
                    for r in bill.unparsed_rows[:3]
                ],
            )
        problems: list[str] = []
        s = round(sum(i.amount for i in bill.line_items), 2)
        tol = max(1.0, 0.005 * bill.total_claimed)
        if abs(s - bill.total_claimed) > tol:
            problems.append(
                f"line items add up to {_fmt(s)} but the bill total is {_fmt(bill.total_claimed)}"
            )
        bad = [
            i
            for i in bill.line_items
            if i.unit_price is not None
            and abs(i.quantity * i.unit_price - i.amount) > max(1.0, 0.005 * i.amount)
        ]
        if bad:
            problems.append(
                f"{len(bad)} line(s) where quantity x rate does not equal the amount (e.g. '{bad[0].description}')"
            )
        if problems:
            return _res(
                self,
                FAIL,
                _cap("; ".join(problems)) + ".",
                Severity.WARN,
                evidence=[
                    Evidence(
                        document_id=bill.document_id,
                        field="total_claimed",
                        text=str(bill.total_claimed),
                    )
                ],
            )
        return _res(self, PASS, "Line items add up to the bill total.")


class Dates:
    rule_id, title = "R009", "Dates are consistent"

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        b, d = ctx.data.bill, ctx.data.discharge
        adm, dis = ctx.admission_date, ctx.discharge_date
        if adm is None or dis is None:
            return _res(
                self, UNKNOWN, "Admission or discharge date could not be read.", Severity.WARN
            )
        if dis < adm:
            return _res(
                self, FAIL, f"Discharge ({dis}) is before admission ({adm}).", Severity.BLOCKER
            )
        if dis > ctx.today:
            return _res(self, FAIL, f"Discharge date {dis} is in the future.", Severity.BLOCKER)
        if (
            b
            and d
            and b.admission_date
            and d.admission_date
            and b.admission_date != d.admission_date
        ):
            return _res(
                self,
                FAIL,
                f"Bill admission date {b.admission_date} differs from the discharge summary {d.admission_date}.",
                Severity.WARN,
            )
        if (
            b
            and d
            and b.discharge_date
            and d.discharge_date
            and b.discharge_date != d.discharge_date
        ):
            return _res(
                self,
                FAIL,
                f"Bill discharge date {b.discharge_date} differs from the discharge summary {d.discharge_date}.",
                Severity.WARN,
            )
        return _res(
            self, PASS, f"Stay of {(dis - adm).days} day(s); dates are consistent across documents."
        )


class DocumentsComplete:
    rule_id, title = "R010", "Required documents present"

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        missing = [t for t in ctx.policy.required_documents if t not in ctx.present_types]
        if missing:
            names = ", ".join(t.value.replace("_", " ") for t in missing)
            return _res(self, FAIL, f"Missing: {names}.", Severity.BLOCKER, "5.2")
        return _res(self, PASS, "All required documents are present.", clause="5.2")


class PreAuth:
    rule_id, title = "R011", "Pre-authorisation for planned high-value claims"

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        bill, d, p = ctx.data.bill, ctx.data.discharge, ctx.policy
        if bill is None or bill.total_claimed is None:
            return _res(self, UNKNOWN, "Claimed total could not be read.", Severity.WARN, "5.1")
        if bill.total_claimed <= p.preauth_required_above:
            return _res(
                self,
                PASS,
                f"Claim is below the {_fmt(p.preauth_required_above)} pre-authorisation threshold.",
                clause="5.1",
            )
        if ctx.data.has_preauth_approval:
            return _res(self, PASS, "A pre-authorisation approval was provided.", clause="5.1")
        emergency = d.is_emergency if d else None
        if emergency is True:
            return _res(
                self, PASS, "Emergency admission: pre-authorisation is not required.", clause="5.1"
            )
        if emergency is None:
            return _res(
                self,
                UNKNOWN,
                "High-value claim; admission type (planned or emergency) is not stated and no approval was provided.",
                Severity.WARN,
                "5.1",
            )
        return _res(
            self,
            FAIL,
            "Planned admission above the threshold with no pre-authorisation approval attached.",
            Severity.WARN,
            "5.1",
        )


class NetworkHospital:
    rule_id, title = "R012", "Network hospital"

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        bill, nets = ctx.data.bill, ctx.policy.network_hospitals
        if not nets:
            return _res(
                self,
                UNKNOWN,
                "No network list is configured for this policy.",
                Severity.INFO,
                "5.3",
            )
        if bill is None or not bill.hospital_name:
            return _res(self, UNKNOWN, "Hospital name could not be read.", Severity.WARN, "5.3")
        if any(_same_hospital(bill.hospital_name, n) for n in nets):
            return _res(self, PASS, "Hospital is in the insurer's network.", clause="5.3")
        return _res(
            self,
            FAIL,
            f"'{bill.hospital_name}' is not in the network list; the claim follows the reimbursement path.",
            Severity.INFO,
            "5.3",
        )


class Sublimits:
    rule_id, title = "R013", "Procedure sub-limits"

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        bill, text = ctx.data.bill, ctx.diagnosis_text
        if bill is None or bill.total_claimed is None or not text:
            return _res(
                self, UNKNOWN, "Procedure or total could not be read.", Severity.WARN, "6.1"
            )
        for s in ctx.policy.sublimits:
            if any(k in text for k in s.keywords):
                if bill.total_claimed > s.max_amount:
                    return _res(
                        self,
                        FAIL,
                        f"{s.procedure} is capped at {_fmt(s.max_amount)}; claimed {_fmt(bill.total_claimed)}.",
                        Severity.WARN,
                        s.clause,
                    )
                return _res(
                    self,
                    PASS,
                    f"{s.procedure} is within its sub-limit of {_fmt(s.max_amount)}.",
                    clause=s.clause,
                )
        return _res(self, PASS, "No sub-limit applies to this procedure.", clause="6.1")


class PatientIdentity:
    rule_id, title = "R014", "Patient name matches across documents"

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        b, d = ctx.data.bill, ctx.data.discharge
        if b is None or d is None:
            return _res(
                self, UNKNOWN, "Needs both the bill and the discharge summary.", Severity.WARN
            )
        sim = _name_similarity(b.patient_name, d.patient_name)
        if sim is None:
            return _res(self, UNKNOWN, "Patient name missing on one document.", Severity.WARN)
        if sim >= 0.85:
            return _res(self, PASS, "Patient name matches on the bill and the discharge summary.")
        if sim < 0.6:
            return _res(
                self,
                FAIL,
                f"Patient name differs: '{b.patient_name}' on the bill vs '{d.patient_name}' on the discharge summary.",
                Severity.BLOCKER,
            )
        return _res(
            self,
            UNKNOWN,
            "Patient names are similar but not identical; please verify.",
            Severity.WARN,
        )


class DocumentIntegrity:
    rule_id, title = "R015", "Documents contain no embedded instructions"

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        flags = ctx.data.injection_flags
        if flags:
            return _res(
                self,
                FAIL,
                f"{len(flags)} suspicious passage(s) found in the uploaded documents. They were treated as plain text and ignored; a reviewer should inspect them.",
                Severity.WARN,
                evidence=[Evidence(text=f[:200]) for f in flags[:5]],
            )
        return _res(self, PASS, "No embedded instructions or hidden text found.")


class ExtractionQuality:
    rule_id, title = "R016", "Extraction confidence"

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        c = ctx.data.extraction_confidence
        if c < 0.6:
            return _res(
                self,
                UNKNOWN,
                f"Only {c:.0%} of expected fields were read. Verify the source documents manually.",
                Severity.WARN,
            )
        return _res(self, PASS, f"{c:.0%} of expected fields were read.")


class Readable:
    rule_id, title = "R017", "All uploaded files could be read"

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        bad = ctx.data.unreadable_documents
        if bad:
            return _res(
                self,
                FAIL,
                f"{len(bad)} file(s) could not be read: "
                + "; ".join(bad[:3])
                + ". Please upload a clearer copy.",
                Severity.WARN,
                "5.2",
            )
        return _res(self, PASS, "All uploaded files could be read.")


def default_rules() -> list[Rule]:
    return [
        PolicyPeriod(),
        InitialWaiting(),
        SpecificWaiting(),
        PreExisting(),
        Exclusions(),
        RoomRent(),
        SumInsured(),
        Arithmetic(),
        Dates(),
        DocumentsComplete(),
        PreAuth(),
        NetworkHospital(),
        Sublimits(),
        PatientIdentity(),
        DocumentIntegrity(),
        ExtractionQuality(),
        Readable(),
    ]


def missing_documents(ctx: RuleContext) -> list[DocumentType]:
    return [t for t in ctx.policy.required_documents if t not in ctx.present_types]
