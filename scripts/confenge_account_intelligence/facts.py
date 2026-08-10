"""Derive confirmed facts vs strong/weak inferences from a normalized bag.

Rules:
- Portfolio items present in input with identifiers are confirmed (public record).
- Structural interpretations without explicit source are inferences.
- Absence of information is never proof of absence of structure.
"""

from __future__ import annotations

from typing import Any

from scripts.confenge_account_intelligence.models import epistemic_item

# Mature contract threshold (days) for reajuste consideration.
MATURE_DAYS = 365
RECENT_DAYS = 180


def _contract_evidence_id(contract_id: str) -> str:
    return f"ev-contract-{contract_id}"


def build_epistemic_layers(bag: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Split knowledge into confirmed / strong / weak. Never promote inference to fact."""
    confirmed: list[dict[str, Any]] = []
    strong: list[dict[str, Any]] = []
    weak: list[dict[str, Any]] = []
    as_of = bag.get("as_of")

    # Pass through explicit facts from input with class discipline.
    for f in bag.get("facts") or []:
        cls = str(f.get("epistemic_class") or "weak_inference")
        if cls not in {"confirmed", "strong_inference", "weak_inference"}:
            cls = "weak_inference"
        item = epistemic_item(
            item_id=str(f.get("id")),
            text=str(f.get("text") or ""),
            epistemic_class=cls,
            confidence=float(f.get("confidence") if f.get("confidence") is not None else 0.5),
            evidence_ids=list(f.get("evidence_ids") or []),
            provenance=str(f.get("provenance") or "input.facts"),
            as_of=f.get("as_of") or as_of,
        )
        if not item["text"]:
            continue
        if cls == "confirmed":
            confirmed.append(item)
        elif cls == "strong_inference":
            strong.append(item)
        else:
            weak.append(item)

    contracts = bag.get("contracts") or []
    if contracts:
        confirmed.append(
            epistemic_item(
                item_id="cf-portfolio-count",
                text=f"Portfólio público observado com {len(contracts)} contrato(s) no input.",
                epistemic_class="confirmed",
                confidence=1.0,
                evidence_ids=[_contract_evidence_id(c["id"]) for c in contracts[:20]],
                provenance="input.contracts",
                as_of=as_of,
            )
        )

    ufs = sorted({str(c.get("uf")).upper() for c in contracts if c.get("uf")})
    if ufs:
        confirmed.append(
            epistemic_item(
                item_id="cf-ufs",
                text=f"UFs observadas nos contratos do input: {', '.join(ufs)}.",
                epistemic_class="confirmed",
                confidence=1.0,
                evidence_ids=[_contract_evidence_id(c["id"]) for c in contracts if c.get("uf")][:20],
                provenance="input.contracts.uf",
                as_of=as_of,
            )
        )

    addendum_contracts = [c for c in contracts if c.get("has_addendum") or (c.get("addendum_count") or 0) > 0]
    if addendum_contracts:
        n = len(addendum_contracts)
        confirmed.append(
            epistemic_item(
                item_id="cf-addenda",
                text=f"{n} contrato(s) com sinal de aditivo/alteração no registro público ingerido.",
                epistemic_class="confirmed",
                confidence=0.95,
                evidence_ids=[_contract_evidence_id(c["id"]) for c in addendum_contracts][:20],
                provenance="input.contracts.has_addendum",
                as_of=as_of,
            )
        )

    mature_no_reaj = []
    for c in contracts:
        age = c.get("age_days")
        if age is None or age < MATURE_DAYS:
            continue
        if c.get("has_reajuste") or c.get("reajuste_evidence"):
            continue
        mature_no_reaj.append(c)
    if mature_no_reaj:
        confirmed.append(
            epistemic_item(
                item_id="cf-mature-no-reajuste",
                text=(
                    f"{len(mature_no_reaj)} contrato(s) com vigência ≥ {MATURE_DAYS} dias "
                    "sem prova de reajuste no input (ausência de prova ≠ prova de ausência de reajuste)."
                ),
                epistemic_class="confirmed",
                confidence=0.9,
                evidence_ids=[_contract_evidence_id(c["id"]) for c in mature_no_reaj][:20],
                provenance="input.contracts.age+reajuste_evidence",
                as_of=as_of,
            )
        )
        strong.append(
            epistemic_item(
                item_id="si-reajuste-angle",
                text=(
                    "Hipótese: pode haver janela para estruturação de pleito de reajuste; "
                    "requer validação documental da cláusula e índices aplicáveis."
                ),
                epistemic_class="strong_inference",
                confidence=0.7,
                evidence_ids=[_contract_evidence_id(c["id"]) for c in mature_no_reaj][:10],
                provenance="derived.mature_without_reajuste_proof",
                as_of=as_of,
            )
        )

    glosa_or_med = [c for c in contracts if c.get("glosa_signals") or c.get("measurement_issues")]
    if glosa_or_med:
        confirmed.append(
            epistemic_item(
                item_id="cf-glosa-medicao",
                text=f"{len(glosa_or_med)} contrato(s) com sinal de glosa ou medição contestada no input.",
                epistemic_class="confirmed",
                confidence=0.9,
                evidence_ids=[_contract_evidence_id(c["id"]) for c in glosa_or_med][:20],
                provenance="input.contracts.glosa|measurement",
                as_of=as_of,
            )
        )

    reeq = [c for c in contracts if c.get("reequilibrio_mention")]
    if reeq:
        confirmed.append(
            epistemic_item(
                item_id="cf-reequilibrio",
                text=f"{len(reeq)} contrato(s) com menção a reequilíbrio no material ingerido.",
                epistemic_class="confirmed",
                confidence=0.9,
                evidence_ids=[_contract_evidence_id(c["id"]) for c in reeq][:20],
                provenance="input.contracts.reequilibrio_mention",
                as_of=as_of,
            )
        )

    signals = bag.get("signals") or {}
    # Explicit public signals provided by caller → strong inference (not fact of internal org).
    if signals.get("national_operation") or len(ufs) >= 3:
        strong.append(
            epistemic_item(
                item_id="si-national-footprint",
                text=(
                    "Sinais públicos de operação multi-UF/nacional observados; "
                    "não se afirma estrutura interna completa sem fonte organizacional."
                ),
                epistemic_class="strong_inference",
                confidence=0.75 if signals.get("national_operation") else 0.65,
                evidence_ids=[_contract_evidence_id(c["id"]) for c in contracts if c.get("uf")][:10],
                provenance="signals.national_operation|contracts.ufs",
                as_of=as_of,
            )
        )

    if signals.get("consortium_participation"):
        strong.append(
            epistemic_item(
                item_id="si-consortium",
                text="Sinal de participação em consórcios no input (estrutura possivelmente mais formal).",
                epistemic_class="strong_inference",
                confidence=0.7,
                evidence_ids=[],
                provenance="signals.consortium_participation",
                as_of=as_of,
            )
        )

    if signals.get("legal_claims_compliance_unit") or signals.get("large_team_public_signal"):
        strong.append(
            epistemic_item(
                item_id="si-robust-public-org-signals",
                text=(
                    "Sinais públicos de unidade jurídica/claims/compliance ou equipe grande; "
                    "hipótese de estrutura robusta — não é fato de organograma."
                ),
                epistemic_class="strong_inference",
                confidence=0.65,
                evidence_ids=[],
                provenance="signals.legal_claims|large_team",
                as_of=as_of,
            )
        )

    if signals.get("high_recurrence") or len(contracts) >= 8:
        strong.append(
            epistemic_item(
                item_id="si-high-recurrence",
                text="Alta recorrência contratual pública observada ou sinalizada.",
                epistemic_class="strong_inference",
                confidence=0.7 if signals.get("high_recurrence") else 0.6,
                evidence_ids=[_contract_evidence_id(c["id"]) for c in contracts][:10],
                provenance="signals.high_recurrence|contract_count",
                as_of=as_of,
            )
        )

    # Lean signals are weak unless multiple corroborate; never conclude "no structure".
    lean_bits = []
    if signals.get("regional_only") or (len(ufs) == 1 and len(contracts) <= 3):
        lean_bits.append("regionalidade/poucos UFs no material observado")
    if signals.get("rapid_growth"):
        lean_bits.append("crescimento rápido sinalizado")
    if signals.get("concentrated_functions"):
        lean_bits.append("funções concentradas sinalizadas")
    if signals.get("low_public_formalization"):
        lean_bits.append("baixa formalização pública")
    if lean_bits and len(contracts) <= 5:
        weak.append(
            epistemic_item(
                item_id="wi-lean-hypothesis",
                text=(
                    "Hipótese fraca de estrutura enxuta com base em: "
                    + "; ".join(lean_bits)
                    + ". Ausência de sinais robustos ≠ prova de ausência de estrutura interna."
                ),
                epistemic_class="weak_inference",
                confidence=0.4,
                evidence_ids=[],
                provenance="signals.lean_cluster",
                as_of=as_of,
            )
        )

    if not contracts and not any(f.get("text") for f in (bag.get("facts") or [])):
        weak.append(
            epistemic_item(
                item_id="wi-insufficient",
                text=(
                    "Fatos públicos insuficientes no input para especializar serviço; "
                    "ângulo preferencial é diagnóstico/descoberta."
                ),
                epistemic_class="weak_inference",
                confidence=0.55,
                evidence_ids=[],
                provenance="derived.insufficient_facts",
                as_of=as_of,
            )
        )

    return {
        "confirmed_facts": confirmed,
        "strong_inferences": strong,
        "weak_inferences": weak,
    }


def portfolio_summary(bag: dict[str, Any]) -> dict[str, Any]:
    contracts = bag.get("contracts") or []
    values = [c.get("value_brl") for c in contracts if c.get("value_brl") is not None]
    total = float(sum(values)) if values else None
    ufs = sorted({str(c.get("uf")).upper() for c in contracts if c.get("uf")})
    organs = {str(c.get("orgao")) for c in contracts if c.get("orgao")}
    addendum = sum(1 for c in contracts if c.get("has_addendum") or (c.get("addendum_count") or 0) > 0)
    mature_no = 0
    for c in contracts:
        age = c.get("age_days")
        if age is not None and age >= MATURE_DAYS and not c.get("has_reajuste") and not c.get("reajuste_evidence"):
            mature_no += 1
    return {
        "contract_count": len(contracts),
        "total_value_brl_observed": total,
        "ufs": ufs,
        "organs_count": len(organs),
        "addendum_contracts": addendum,
        "mature_without_reajuste": mature_no,
        "semantics": "sum_of_observed_public_contracts_in_input_only",
    }


def why_now(bag: dict[str, Any], layers: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Temporal generator of approach — prefer recent confirmed pain."""
    contracts = bag.get("contracts") or []
    as_of = bag.get("as_of")

    # Priority: concrete pain with recency
    pain_checks = [
        (
            "addendum",
            lambda c: c.get("has_addendum") or (c.get("addendum_count") or 0) > 0,
            "Aditivos/alterações observados em contrato público recente ou ativo.",
        ),
        (
            "glosa_medicao",
            lambda c: c.get("glosa_signals") or c.get("measurement_issues"),
            "Sinais de glosa ou medição contestada no material ingerido.",
        ),
        (
            "reequilibrio",
            lambda c: c.get("reequilibrio_mention"),
            "Menção a reequilíbrio em material contratual ingerido.",
        ),
        (
            "mature_no_reajuste",
            lambda c: (
                bool(c.get("start_date"))
                and (c.get("age_days") or 0) >= MATURE_DAYS
                and not c.get("has_reajuste")
                and not c.get("reajuste_evidence")
            ),
            "Contrato maduro (com data de início observada) sem prova de reajuste no input — janela potencial de reajuste.",
        ),
    ]
    best: dict[str, Any] | None = None
    for trigger, pred, text in pain_checks:
        matches = [c for c in contracts if pred(c)]
        if not matches:
            continue

        # Prefer most recent by age_days ascending (younger among mature still recent activity)
        def recency_key(c: dict[str, Any]) -> int:
            age = c.get("age_days")
            return int(age) if age is not None else 10_000

        matches_sorted = sorted(matches, key=recency_key)
        top = matches_sorted[0]
        age = top.get("age_days")
        candidate = {
            "trigger": trigger,
            "temporal_fact": text,
            "recency_days": age,
            "epistemic_class": "confirmed",
        }
        if best is None:
            best = candidate
            continue
        # Recent beats remote: lower recency_days wins when both confirmed
        br = best.get("recency_days")
        cr = candidate.get("recency_days")
        if cr is not None and (br is None or cr < br):
            # concrete pain of addendum/glosa still beats mature_no_reajuste if similar recency
            if trigger in {"addendum", "glosa_medicao", "reequilibrio"}:
                best = candidate
            elif best.get("trigger") == "mature_no_reajuste":
                best = candidate
        elif best.get("trigger") == "mature_no_reajuste" and trigger in {
            "addendum",
            "glosa_medicao",
            "reequilibrio",
        }:
            best = candidate

    if best is not None:
        return best

    if not contracts:
        return {
            "trigger": "insufficient_facts",
            "temporal_fact": (
                f"Em {as_of}, o input não traz portfólio contratual suficiente; o momento é de diagnóstico/descoberta."
            ),
            "recency_days": None,
            "epistemic_class": "weak_inference",
        }

    # Prefer a concrete contract hook so why_now is not generic portfolio boilerplate
    # (COPY_CONTEXT / MessageSpine reject "portfólio público observável…").
    hook_bits: list[str] = []
    for c in contracts:
        if not isinstance(c, dict):
            continue
        obj = str(c.get("object") or c.get("objeto") or c.get("objeto_contrato") or "").strip()
        if len(obj) < 24:
            continue
        org = str(c.get("orgao") or c.get("agency") or c.get("orgao_nome") or "").strip()
        uf = str(c.get("uf") or "").strip()
        hook_bits = [f"objeto: {obj[:140]}"]
        if org:
            hook_bits.append(f"órgão: {org}")
        if uf:
            hook_bits.append(f"UF {uf}")
        break
    if hook_bits:
        temporal = (
            f"Em {as_of}, fato contratual público utilizável sem dor especializada dominante — "
            + "; ".join(hook_bits)
            + "."
        )
    else:
        temporal = (
            f"Em {as_of}, portfólio contratual no input sem objeto material suficiente "
            "para especialidade — revisão/diagnóstico focal honesto."
        )
    return {
        "trigger": "portfolio_review",
        "temporal_fact": temporal,
        "recency_days": min((c.get("age_days") for c in contracts if c.get("age_days") is not None), default=None),
        "epistemic_class": "strong_inference",
    }
