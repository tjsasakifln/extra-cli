"""Anti-fragmentation controls for direct-contracting intelligence.

Legal ceiling is never a pricing target or package-splitting device.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from scripts.public_agency import SUM_UNKNOWN


@dataclass
class FragmentationAssessment:
    fragmentation_suspected: bool
    severity: str  # NONE | LOW | MEDIUM | HIGH
    indicators: list[str] = field(default_factory=list)
    annual_sum_same_nature: float | None = None
    annual_sum_known: bool = False
    annual_sum_state: str = SUM_UNKNOWN
    packages: list[dict[str, Any]] = field(default_factory=list)
    blocks_eligibility_claim: bool = False
    pricing_near_ceiling: bool = False
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _same_nature(a: str, b: str) -> bool:
    """Coarse same-nature heuristic by shared engineering tokens."""
    tokens = {
        "OBRA",
        "PAVIMENT",
        "REFORMA",
        "SANEAMENTO",
        "DRENAGEM",
        "EDIFIC",
        "PROJETO",
        "ORCAMENT",
        "FISCALIZ",
        "ENGENHAR",
    }
    au = (a or "").upper()
    bu = (b or "").upper()
    sa = {t for t in tokens if t in au}
    sb = {t for t in tokens if t in bu}
    return bool(sa & sb)


def assess_fragmentation(
    *,
    proposed_amount: float | None,
    ceiling: float | None,
    same_nature_contracts: list[dict[str, Any]] | None = None,
    proposed_packages: list[dict[str, Any]] | None = None,
    near_ceiling_ratio: float = 0.97,
) -> FragmentationAssessment:
    """Evaluate fragmentation indicators for a unit gestor / same-nature objects.

    same_nature_contracts items: {amount, object, year, id}
    proposed_packages items: {amount, object, label}
    """
    indicators: list[str] = []
    contracts = list(same_nature_contracts or [])
    packages = list(proposed_packages or [])

    annual_sum = None
    annual_known = False
    if contracts:
        try:
            annual_sum = float(sum(float(c.get("amount") or 0) for c in contracts))
            annual_known = True
        except (TypeError, ValueError):
            annual_sum = None
            annual_known = False

    annual_state = SUM_UNKNOWN
    if annual_known and annual_sum is not None and ceiling is not None:
        if annual_sum >= ceiling:
            annual_state = "SAME_NATURE_ANNUAL_SUM_ABOVE_THRESHOLD"
            indicators.append("same_nature_annual_sum_above_threshold")
        else:
            annual_state = "SAME_NATURE_ANNUAL_SUM_BELOW_THRESHOLD"

    if len(packages) >= 2:
        # Multiple packages that look like one need
        objs = [str(p.get("object") or "") for p in packages]
        related = 0
        for i in range(len(objs)):
            for j in range(i + 1, len(objs)):
                if _same_nature(objs[i], objs[j]):
                    related += 1
        if related:
            indicators.append("multiple_packages_same_nature")
        # Artificial split: each package under ceiling but sum over
        if ceiling is not None:
            try:
                psum = sum(float(p.get("amount") or 0) for p in packages)
                each_below = all(
                    float(p.get("amount") or 0) < ceiling for p in packages if p.get("amount") is not None
                )
                if each_below and psum >= ceiling:
                    indicators.append("packages_sum_above_ceiling_each_below")
            except (TypeError, ValueError):
                pass

    # Repeated same-nature hiring
    if len(contracts) >= 3:
        indicators.append("recurring_same_nature_contracting")

    pricing_near = False
    if proposed_amount is not None and ceiling is not None and ceiling > 0:
        if float(proposed_amount) >= float(ceiling) * near_ceiling_ratio and float(proposed_amount) < float(
            ceiling
        ):
            pricing_near = True
            indicators.append("value_deliberately_near_ceiling")

    severity = "NONE"
    if indicators:
        if any(
            x in indicators
            for x in (
                "packages_sum_above_ceiling_each_below",
                "same_nature_annual_sum_above_threshold",
            )
        ):
            severity = "HIGH"
        elif "multiple_packages_same_nature" in indicators or "recurring_same_nature_contracting" in indicators:
            severity = "MEDIUM"
        else:
            severity = "LOW"

    suspected = severity in {"MEDIUM", "HIGH"} or pricing_near
    blocks = severity == "HIGH" or "packages_sum_above_ceiling_each_below" in indicators

    notes = (
        "Teto legal é filtro de elegibilidade potencial, não âncora de preço. "
        "Preço deve decorrer de escopo, esforço, responsabilidade técnica e riscos."
    )
    if not annual_known:
        notes += f" Somatório anual: {SUM_UNKNOWN}."

    return FragmentationAssessment(
        fragmentation_suspected=suspected,
        severity=severity,
        indicators=indicators,
        annual_sum_same_nature=annual_sum,
        annual_sum_known=annual_known,
        annual_sum_state=annual_state,
        packages=packages,
        blocks_eligibility_claim=blocks,
        pricing_near_ceiling=pricing_near,
        notes=notes,
    )


def price_from_scope(
    *,
    effort_hours: float,
    hourly_rate: float,
    travel_cost: float = 0.0,
    inspections: int = 0,
    inspection_cost: float = 0.0,
    complexity_factor: float = 1.0,
    margin: float = 0.0,
    taxes: float = 0.0,
    ceiling: float | None = None,
) -> dict[str, Any]:
    """Scope-based pricing — never uses legal ceiling as price target."""
    base = float(effort_hours) * float(hourly_rate) * float(complexity_factor)
    base += float(travel_cost) + float(inspections) * float(inspection_cost)
    subtotal = base * (1.0 + float(margin)) + float(taxes)
    result = {
        "currency": "BRL",
        "effort_hours": effort_hours,
        "hourly_rate": hourly_rate,
        "travel_cost": travel_cost,
        "inspections": inspections,
        "inspection_cost": inspection_cost,
        "complexity_factor": complexity_factor,
        "margin": margin,
        "taxes": taxes,
        "proposed_price": round(subtotal, 2),
        "ceiling_used_as_price_anchor": False,
        "pricing_method": "SCOPE_EFFORT_RESPONSIBILITY",
    }
    if ceiling is not None:
        result["ceiling_reference_only"] = ceiling
        result["strictly_below_ceiling"] = subtotal < float(ceiling)
        if subtotal >= float(ceiling) * 0.97 and subtotal < float(ceiling):
            result["warning"] = "PRICE_NEAR_CEILING_REVIEW_REQUIRED"
    return result
