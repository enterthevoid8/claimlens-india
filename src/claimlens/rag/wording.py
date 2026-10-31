"""Render a ``Policy`` into clause-structured policy wording.

The same ``Policy`` object drives both the rules and this text, so the answers the explainer cites can
never drift from what the rules enforce. Real deployments would index the insurer's own PDF wording
instead (chunked by clause with the same ``chunk_policy_wording`` function).
"""

from __future__ import annotations

from claimlens.domain.models import Policy


def _rs(x: float) -> str:
    return f"Rs {x:,.0f}"


def render_policy_wording(p: Policy) -> str:
    lines: list[str] = [
        f"# {p.product_name}: Policy Wording",
        f"Policy number {p.policy_id}. Policy holder {p.holder_name}. Insurer {p.insurer}.",
        "",
        "## Clause 1.1 Sum Insured",
        f"The maximum amount payable in a policy year is the sum insured of {_rs(p.sum_insured)}. "
        "Claims above the sum insured are not payable.",
        "",
        "## Clause 1.2 Policy Period",
        f"Cover starts on {p.start_date:%d %B %Y} and ends on {p.end_date:%d %B %Y}. "
        "Only hospital admissions within this period are covered.",
        "",
        "## Clause 2.1 Initial Waiting Period",
        f"No claim is payable for any illness during the first {p.initial_waiting_days} days from the start of the policy. "
        "This waiting period does not apply to hospitalisation caused by an accident.",
        "",
        "## Clause 2.2 Specific Waiting Periods",
        "The following conditions are covered only after the waiting period from the start of the policy:",
    ]
    for w in p.waiting_periods:
        lines.append(
            f"- {w.condition}: {w.days} days ({w.days / 365:.0f} years). Related terms: {', '.join(w.keywords)}."
        )
    lines += [
        "Accidental hospitalisation is exempt from specific waiting periods.",
        "",
        "## Clause 2.3 Pre-existing Diseases",
        f"A condition that existed before the start of the policy is not covered until {p.pre_existing_waiting_days} days "
        f"({p.pre_existing_waiting_days / 365:.0f} years) of continuous cover have been completed. "
        "The duration of the condition is taken from the discharge summary and treatment records.",
        "",
        "## Clause 3.1 Exclusions",
        "The policy does not cover the following. Each exclusion below is permanent.",
    ]
    for e in p.exclusions:
        lines.append(f"- Clause {e.clause}: {e.title}. Related terms: {', '.join(e.keywords)}.")
    lines += ["", "## Clause 4.1 Room Rent Limit"]
    if p.room_rent_cap_per_day is not None:
        lines.append(
            f"Room rent is covered up to {_rs(p.room_rent_cap_per_day)} per day. If a higher room category is chosen, "
            "related charges such as nursing and doctor visits are reduced in the same proportion."
        )
    else:
        lines.append("There is no limit on room rent under this policy.")
    lines += [
        "",
        "## Clause 4.2 Co-payment",
        f"The insured bears {p.copay_pct:g}% of every admissible claim amount."
        if p.copay_pct
        else "There is no co-payment under this policy.",
        "",
        "## Clause 5.1 Pre-authorisation",
        f"For planned hospitalisation where the expected cost is above {_rs(p.preauth_required_above)}, written pre-authorisation from "
        "the insurer is required before admission. Emergency admissions do not need pre-authorisation but must be intimated within 24 hours.",
        "",
        "## Clause 5.2 Documents Required",
        "Submit these documents with every claim: "
        + ", ".join(d.value.replace("_", " ") for d in p.required_documents)
        + ". "
        "The insurer may ask for more documents, such as lab reports or a pre-authorisation letter.",
        "",
        "## Clause 5.3 Network Hospitals",
        "Cashless treatment is available at network hospitals. At other hospitals you pay first and claim reimbursement.",
        "",
        "## Clause 6.1 Sub-limits",
    ]
    if p.sublimits:
        lines.append("Some procedures have a maximum payable amount:")
        for s in p.sublimits:
            lines.append(
                f"- {s.procedure}: up to {_rs(s.max_amount)} per claim. Related terms: {', '.join(s.keywords)}."
            )
    else:
        lines.append("No procedure-specific sub-limits apply.")
    lines += [
        "",
        "## Clause 7.1 How Claims Are Assessed",
        "Every claim is assessed by a human claims reviewer. Automated checks only highlight missing documents and possible issues. "
        "You can ask the insurer to explain any decision or reduction.",
        "",
    ]
    return "\n".join(lines)
