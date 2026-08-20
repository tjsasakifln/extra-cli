"""Claim matrix builders. Absence is UNKNOWN, never a negative FACT."""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from scripts.bofu_evidence.models import (
    COMPARABLE_METRIC,
    COMPARABLE_PERTINENT_FAMILIES,
    COMPARABLE_UNIT,
    FAMILY_DOCUMENT_KINDS,
)

EVIDENCE_PREFIX = "fixture:scripts/bofu_evidence/fixtures"


def make_claim(
    claim_id: str,
    klass: str,
    statement: str,
    *,
    value: Any = None,
    unit: str | None = None,
    refs: tuple[str, ...] = (),
    reason_code: str | None = None,
) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "epistemic_class": klass,
        "statement": statement,
        "value": value,
        "unit": unit,
        "evidence_refs": list(refs),
        "reason_code": reason_code,
    }


def _items_for_family(snapshot: dict[str, Any], family: str) -> list[dict[str, Any]]:
    kinds = FAMILY_DOCUMENT_KINDS[family]
    found: list[dict[str, Any]] = []
    for document in snapshot.get("documents") or []:
        if document.get("kind") in kinds:
            found.append({"role": "document", **document})
    for event in snapshot.get("events") or []:
        if event.get("kind") in kinds:
            found.append({"role": "event", **event})
    return found


def observed_items_unknown(family: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    """UNKNOWN when the recorte has no matching document/event. Not a negative FACT."""
    return make_claim(
        f"{family}-not-observed",
        "UNKNOWN",
        (
            f"Nenhum documento ou evento da familia {family} foi observado "
            "no recorte congelado. Isso nao afirma ausencia no mundo real."
        ),
        refs=(f"{EVIDENCE_PREFIX}/snapshot.json",),
        reason_code="document_not_observed",
    )


def build_observed_claims(family: str, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    items = _items_for_family(snapshot, family)
    if not items:
        return [observed_items_unknown(family, snapshot)]
    claims: list[dict[str, Any]] = []
    for item in items:
        item_id = item.get("doc_id") or item.get("event_id")
        locator = item.get("locator")
        claims.append(
            make_claim(
                f"{family}-{item_id}",
                "FACT",
                f"O recorte contem o {item['role']} {item_id} do tipo {item['kind']}.",
                value={"id": item_id, "role": item.get("role"), "type": item.get("kind")},
                refs=(locator, f"{EVIDENCE_PREFIX}/snapshot.json"),
                reason_code="document_observed" if item.get("doc_id") else "event_observed",
            )
        )
    return claims


def _decimal(value: str) -> Decimal:
    return Decimal(value)


def build_comparable_claims(comparable: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ref = f"{EVIDENCE_PREFIX}/pr435_comparable.json"
    hash_ref = f"pr435:{comparable.get('content_hash')}"
    refs = (ref, hash_ref)
    claims = [
        make_claim(
            "orcamento-comparable-state",
            "FACT",
            "O fixture #435 declara estado COMPARABLE para o grupo de pares de paralelepipedo.",
            value=comparable.get("state"),
            refs=refs,
            reason_code="comparable_state",
        ),
        make_claim(
            "orcamento-comparable-n-used",
            "FACT",
            "O fixture #435 declara n_used=12 pares no grupo COMPARABLE.",
            value=comparable.get("n_used"),
            refs=refs,
            reason_code="comparable_n_used",
        ),
        make_claim(
            "orcamento-comparable-unit",
            "FACT",
            "A metrica observada permanece valor_integral_nominal com unidade BRL_TOTAL.",
            value=comparable.get("unit"),
            unit=COMPARABLE_UNIT,
            refs=refs,
            reason_code="comparable_unit",
        ),
        make_claim(
            "orcamento-comparable-median",
            "FACT",
            "O fixture #435 declara mediana de valor_integral_nominal no grupo COMPARABLE.",
            value=comparable.get("median"),
            unit=COMPARABLE_UNIT,
            refs=refs,
            reason_code="comparable_median",
        ),
        make_claim(
            "orcamento-comparable-scope",
            "OBSERVATION",
            (
                "O comparavel #435 e um recorte de paralelepipedo com unidade BRL_TOTAL. "
                "Nao e custo por unidade e nao autoriza claim nacional."
            ),
            value={
                "paving_family": comparable.get("paving_family"),
                "metric": comparable.get("metric"),
                "unit": comparable.get("unit"),
            },
            unit=COMPARABLE_UNIT,
            refs=refs,
            reason_code="comparable_scope",
        ),
    ]
    p75 = _decimal(str(comparable["p75"]))
    p25 = _decimal(str(comparable["p25"]))
    iqr = (p75 - p25).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    calculations = [
        make_claim(
            "orcamento-comparable-iqr",
            "CALCULATION",
            "Amplitude interquartil (p75 - p25) do fixture #435 em BRL_TOTAL.",
            value=format(iqr, "f"),
            unit=COMPARABLE_UNIT,
            refs=refs,
            reason_code="comparable_iqr",
        )
    ]
    return claims, calculations


def comparable_is_pertinent(family: str) -> bool:
    return family in COMPARABLE_PERTINENT_FAMILIES


def build_family_claims(
    family: str,
    snapshot: dict[str, Any],
    comparable: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    if family == "orcamento_bdi" and comparable_is_pertinent(family) and comparable:
        if comparable.get("unit") != COMPARABLE_UNIT:
            return (
                [
                    make_claim(
                        "orcamento-unit-unknown",
                        "UNKNOWN",
                        "Unidade do comparavel nao e BRL_TOTAL; o pack nao promove a unidade.",
                        value=comparable.get("unit"),
                        refs=(f"{EVIDENCE_PREFIX}/pr435_comparable.json",),
                        reason_code="comparable_unit_not_brl_total",
                    )
                ],
                [],
                False,
            )
        if comparable.get("metric") != COMPARABLE_METRIC:
            return (
                [
                    make_claim(
                        "orcamento-metric-unknown",
                        "UNKNOWN",
                        "Metrica do comparavel nao e valor_integral_nominal.",
                        value=comparable.get("metric"),
                        refs=(f"{EVIDENCE_PREFIX}/pr435_comparable.json",),
                        reason_code="comparable_metric_mismatch",
                    )
                ],
                [],
                False,
            )
        claims, calculations = build_comparable_claims(comparable)
        return claims, calculations, True
    return build_observed_claims(family, snapshot), [], False
