"""Edital requirement matching against acervo (no auto-sum by default)."""

from __future__ import annotations

from typing import Any

from scripts.technical_acervo.normalize import normalize_text, normalize_unit
from scripts.technical_acervo.search import rank_item_hits, search_items, service_relevant_hits
from scripts.technical_acervo.store import AcervoStore

ADHERENCE_LEVELS = (
    "full_individual",
    "partial_individual",
    "only_with_sum",
    "evidence_limited",
    "no_match",
    "human_review_required",
)


def match_requirement(
    store: AcervoStore,
    *,
    service: str,
    quantity: float | None = None,
    unit: str | None = "m2",
    activity: str | None = None,
    allow_sum: bool = False,
    require_cat_attestation: bool = False,
) -> dict[str, Any]:
    """Compare a tender quantity requirement to the acervo.

    Default: never sum distinct works. When allow_sum=True, sum is reported
    separately and which records were summed is explicit.
    """
    unit_n = normalize_unit(unit) if unit else None
    hits = search_items(
        store,
        service,
        min_quantity=None,
        unit=unit_n,
        activity=activity,
        limit=100,
        service_only=True,
    )
    # Prefer CAT with attestation when scoring candidates
    if require_cat_attestation:
        hits = [
            h
            for h in hits
            if h.get("evidence_level") == "cat_with_registered_attestation"
            or h.get("document_type") == "CAT"
        ]

    # Only service-relevant items — never invent quantitativos from tag-polluted rows
    candidates = service_relevant_hits(hits)
    if not candidates and hits:
        # Fallback only if search returned non-relevant noise; treat as no match
        candidates = []
    # Rank for display: exact → score → qty (already in service_relevant_hits)
    candidates = rank_item_hits(candidates)
    best_individual = candidates[0] if candidates else None
    if candidates:
        max_individual = max(float(c.get("quantity") or 0) for c in candidates)
        # best for adherence is the highest quantity service-relevant row
        # (may differ from top score when exact match has lower qty)
        best_by_qty = max(candidates, key=lambda c: float(c.get("quantity") or 0))
        best_individual = best_by_qty
    else:
        max_individual = None

    summed_records: list[dict[str, Any]] = []
    sum_total: float | None = None
    if allow_sum and candidates:
        # Distinct experiences only (one item per experience — take max per exp for service)
        by_exp: dict[str, dict[str, Any]] = {}
        for h in candidates:
            eid = h.get("experience_id") or ""
            prev = by_exp.get(eid)
            if prev is None or (h.get("quantity") or 0) > (prev.get("quantity") or 0):
                by_exp[eid] = h
        summed_records = list(by_exp.values())
        sum_total = sum(float(r.get("quantity") or 0) for r in summed_records)

    adherence = "no_match"
    human_review = True
    limitations: list[str] = [
        "Resultado é evidência documental, não parecer jurídico de habilitação.",
        "Análise do edital (parcela de maior relevância, somatório permitido, vínculos RT/PJ) permanece necessária.",
    ]

    if not candidates:
        adherence = "no_match"
        limitations.append("Nenhum item do acervo corresponde semanticamente ao serviço informado.")
    elif quantity is None:
        adherence = "human_review_required"
        limitations.append("Quantidade exigida não informada — listando candidatos apenas.")
    else:
        qty = float(quantity)
        if max_individual is not None and float(max_individual) >= qty:
            adherence = "full_individual"
            human_review = True  # still need edital analysis
            if best_individual and best_individual.get("individual_cat_not_provided"):
                adherence = "evidence_limited"
                limitations.append(
                    "Maior quantitativo individual atende numericamente, mas evidência é somente CAO "
                    "(sem CAT individual fornecida)."
                )
            elif best_individual and best_individual.get("document_status") == "expired":
                adherence = "evidence_limited"
                limitations.append("Documento do maior quantitativo está vencido ou com status limitado.")
        elif allow_sum and sum_total is not None and sum_total >= qty:
            adherence = "only_with_sum"
            limitations.append(
                "Atendimento numérico só com somatório de obras distintas; use apenas se o edital permitir."
            )
            limitations.append(
                "Registros somados: "
                + ", ".join(
                    f"{r.get('certificate_number') or r.get('experience_id')}={r.get('quantity')} {r.get('unit')}"
                    for r in summed_records
                )
            )
        elif max_individual is not None and float(max_individual) > 0:
            adherence = "partial_individual"
            limitations.append(
                f"Maior quantitativo individual ({max_individual} {unit_n}) inferior ao exigido ({qty} {unit_n})."
            )
        else:
            adherence = "no_match"

    if not allow_sum:
        limitations.append(
            "Somatório automático entre obras distintas desabilitado (allow_sum=false)."
        )

    # CAO / professional vs PJ caveats
    for c in candidates[:5]:
        if c.get("document_type") == "CAO":
            limitations.append(
                "CAO não substitui CAT/atestado registrado e não deve ser usada como prova "
                "atual de habilitação se vencida."
            )
            break
    limitations.append(
        "CAT profissional não é prova irrestrita de capacidade operacional da pessoa jurídica."
    )

    return {
        "requirement": {
            "service": service,
            "activity": activity,
            "quantity": quantity,
            "unit": unit_n,
            "modality": activity or "nao_especificada",
        },
        "allow_sum": allow_sum,
        "candidates": candidates[:15],
        "max_individual_quantity": max_individual,
        "best_individual": best_individual,
        "sum_total": sum_total if allow_sum else None,
        "summed_records": summed_records if allow_sum else [],
        "adherence_level": adherence,
        "limitations": _unique(limitations),
        "human_review_required": human_review,
        "disclaimer": (
            "Evidência documental do acervo EXTRA. Não afirma atendimento jurídico absoluto "
            "a exigência de edital. Distingue evidência, inferência e necessidade de análise humana."
        ),
        "sources": [
            {
                "document": c.get("document_type"),
                "number": c.get("certificate_number"),
                "art": c.get("art_number"),
                "quantity": c.get("quantity"),
                "unit": c.get("unit"),
                "source_file": c.get("source_file"),
                "source_page": c.get("source_page"),
                "experience_id": c.get("experience_id"),
                "evidence_level": c.get("evidence_level"),
            }
            for c in candidates[:15]
        ],
    }


def parse_natural_requirement(text: str) -> dict[str, Any]:
    """Lightweight NL parse for queries like 'estrutura metálica acima de 500 m²'."""
    import re

    q = text.strip()
    nq = normalize_text(q)
    allow_sum = bool(re.search(r"\bsoma(r|torio)?\b|\bpermit(e|ido)\s+som", nq))
    qty = None
    unit = None
    m = re.search(
        r"(?:acima\s+de|maior\s+que|minimo\s+de|>=|no\s+minimo|pelo\s+menos)?\s*"
        r"(\d+[.,]?\d*)\s*(m2|m²|m\s*2|metros?\s*quadrados?)",
        nq,
        re.I,
    )
    if not m:
        m = re.search(r"(\d+[.,]?\d*)\s*(m2|m²)", nq, re.I)
    if m:
        qty = float(m.group(1).replace(",", "."))
        unit = "m2"
    # strip quantity phrase for service
    service = re.sub(
        r"(acima\s+de|maior\s+que|minimo\s+de|no\s+minimo|pelo\s+menos)?\s*"
        r"\d+[.,]?\d*\s*(m2|m²|m\s*2|metros?\s*quadrados?)",
        " ",
        nq,
        flags=re.I,
    )
    service = re.sub(r"\b(a extra possui acervo de|existe|ha|quais?|acervo de|comprovad\w*)\b", " ", service)
    service = re.sub(r"\s+", " ", service).strip(" ?")
    activity = None
    for act in ("restauracao", "reforma", "montagem", "instalacao", "execucao", "projeto"):
        if act in service:
            activity = act
            break
    return {
        "service": service or nq,
        "quantity": qty,
        "unit": unit or "m2",
        "activity": activity,
        "allow_sum": allow_sum,
        "original": text,
    }


def match_natural(store: AcervoStore, text: str) -> dict[str, Any]:
    parsed = parse_natural_requirement(text)
    result = match_requirement(
        store,
        service=parsed["service"],
        quantity=parsed["quantity"],
        unit=parsed["unit"],
        activity=parsed["activity"],
        allow_sum=bool(parsed["allow_sum"]),
    )
    result["parsed"] = parsed
    return result


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out
