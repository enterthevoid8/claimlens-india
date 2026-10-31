"""Policy products live in YAML so a domain expert can review and change them without touching code."""

from __future__ import annotations

from datetime import date
from importlib import resources
from typing import Any

import yaml
from pydantic import BaseModel, Field

from claimlens.domain.models import Exclusion, Policy, Sublimit, WaitingPeriod


class ProductTemplate(BaseModel):
    product_name: str
    copay_pct: float = 0.0
    room_rent_cap_pct_of_sum_insured: float | None = None
    room_rent_cap_fixed: float | None = None
    initial_waiting_days: int = 30
    pre_existing_waiting_days: int = 1095
    preauth_required_above: float = 100_000
    waiting_periods: list[dict[str, Any]] = Field(default_factory=list)
    exclusions: list[dict[str, Any]] = Field(default_factory=list)
    sublimits: list[dict[str, Any]] = Field(default_factory=list)


def available_products() -> list[str]:
    root = resources.files("claimlens.rules") / "policies"
    return sorted(p.name.removesuffix(".yaml") for p in root.iterdir() if p.name.endswith(".yaml"))


def load_product(name: str) -> ProductTemplate:
    if name not in available_products():
        raise KeyError(f"unknown product '{name}'")
    text = (resources.files("claimlens.rules") / "policies" / f"{name}.yaml").read_text(
        encoding="utf-8"
    )
    return ProductTemplate.model_validate(yaml.safe_load(text))


def instantiate_policy(
    product: str,
    *,
    policy_id: str,
    tenant_id: str,
    holder_name: str,
    start_date: date,
    sum_insured: float,
    network_hospitals: list[str] | None = None,
    term_years: int = 1,
    insurer: str = "Example Insurer",
) -> Policy:
    t = load_product(product)
    cap: float | None = t.room_rent_cap_fixed
    if cap is None and t.room_rent_cap_pct_of_sum_insured is not None:
        cap = round(sum_insured * t.room_rent_cap_pct_of_sum_insured / 100, 2)
    try:
        end = start_date.replace(year=start_date.year + term_years)
    except ValueError:  # 29 Feb
        end = start_date.replace(year=start_date.year + term_years, day=28)
    return Policy(
        policy_id=policy_id,
        tenant_id=tenant_id,
        insurer=insurer,
        product_name=t.product_name,
        holder_name=holder_name,
        start_date=start_date,
        end_date=end,
        sum_insured=sum_insured,
        copay_pct=t.copay_pct,
        room_rent_cap_per_day=cap,
        initial_waiting_days=t.initial_waiting_days,
        pre_existing_waiting_days=t.pre_existing_waiting_days,
        preauth_required_above=t.preauth_required_above,
        waiting_periods=[WaitingPeriod(**w) for w in t.waiting_periods],
        exclusions=[Exclusion(**e) for e in t.exclusions],
        sublimits=[Sublimit(**s) for s in t.sublimits],
        network_hospitals=network_hospitals or [],
    )
