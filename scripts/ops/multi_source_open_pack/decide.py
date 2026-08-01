"""Decisão GO | REVIEW | NO_GO com score explicável e hard gates."""

from __future__ import annotations

from typing import Any

from scripts.ops.multi_source_open_pack.classify_aec import AecClassification, classify_aec
from scripts.ops.multi_source_open_pack.models import CanonicalProcess, DecisionEvaluation
from scripts.ops.multi_source_open_pack.textutil import br_date

SCORING_VERSION = "extra-decision/1.0.0"

# Profile fields that block GO when PENDING (Extra capacity elicitation)
CRITICAL_PENDING_DEFAULT = (
    "capital_giro",
    "cats_atestados",
    "equipe_tecnica",
    "equipamentos",
    "garantias",
    "capacidade_simultanea",
    "margem",
)


def _profile_pending_fields(profile: dict[str, Any] | None) -> list[str]:
    if not profile:
        return list(CRITICAL_PENDING_DEFAULT)
    pending: list[str] = []
    # common patterns in extra.yaml
    for key in ("capabilities", "capacity", "elicitation", "pending_fields"):
        block = profile.get(key)
        if isinstance(block, dict):
            for k, v in block.items():
                if str(v).upper() in {"PENDING", "NULL", "NONE", ""} or v is None:
                    pending.append(str(k))
        elif isinstance(block, list):
            pending.extend(str(x) for x in block)
    # capabilities listed as status
    caps = profile.get("capabilities") or profile.get("operational_capacity") or {}
    if isinstance(caps, dict):
        for k, v in caps.items():
            if isinstance(v, dict) and str(v.get("status", "")).upper() == "PENDING":
                pending.append(str(k))
            elif str(v).upper() == "PENDING":
                pending.append(str(k))
    if not pending:
        # Extra profile always has human-gated GO per policy
        pending = list(CRITICAL_PENDING_DEFAULT)
    return sorted(set(pending))


def evaluate_process(
    proc: CanonicalProcess,
    *,
    profile: dict[str, Any] | None = None,
    shortlist_max_distance_km: float = 200.0,
) -> DecisionEvaluation:
    aec: AecClassification = classify_aec(
        proc.objeto,
        is_active_dispute=proc.is_active_dispute and proc.status_processo == "open",
        modalidade=proc.modalidade,
        profile=profile,
    )

    reasons: list[str] = []
    blockers: list[str] = []
    risks: list[str] = []
    pending = _profile_pending_fields(profile)
    score = 0

    # --- Hard gates → NO_GO ---
    if proc.layer != "decision" or not proc.in_universe:
        blockers.append("fora_do_universo_200km")
    if proc.status_processo == "expired":
        blockers.append("prazo_encerrado")
    if proc.status_processo in {"terminal", "suspended"}:
        blockers.append(f"status_{proc.status_processo}")
    if not proc.is_active_dispute:
        blockers.append("sem_disputa_ativa")
        if proc.exclusion_reason:
            blockers.append(proc.exclusion_reason)
    if not aec.is_aec:
        blockers.append(f"objeto_nao_aec:{aec.category}")
    if proc.distance_km is not None and proc.distance_km > shortlist_max_distance_km:
        blockers.append(f"distancia_proibitiva:{proc.distance_km:.1f}km")
    if proc.in_universe and proc.distance_km is None and proc.match_universo == "municipio":
        risks.append("distancia_nao_resolvida_match_apenas_municipio")
    if proc.in_universe and proc.distance_km is None and proc.match_universo != "municipio":
        blockers.append("distancia_ausente_no_universo")

    # Soft scoring (not win probability)
    if aec.is_aec:
        score += 30
        reasons.append(f"AEC:{aec.category_label}")
    if aec.is_profile_adherent:
        score += 20
        reasons.append("aderente_perfil_Extra")
    if aec.confidence >= 0.7:
        score += 10
    if proc.fontes:
        score += min(15, 5 * len(proc.fontes))
        reasons.append(f"fontes:{','.join(proc.fontes)}")
    if proc.official_page_validated:
        score += 10
        reasons.append("url_oficial_especifica")
    else:
        risks.append("url_oficial_generica_ou_ausente")
        pending.append("validar_pagina_oficial")
    if proc.valor_estimado is not None and proc.valor_estimado >= 100_000:
        score += 5
        reasons.append("valor_estimado_material")
    if proc.calendar_days_remaining is not None:
        if proc.calendar_days_remaining >= 5:
            score += 10
            reasons.append(f"prazo_{proc.calendar_days_remaining}d")
        elif proc.calendar_days_remaining >= 1:
            score += 3
            risks.append("prazo_curto")
        else:
            risks.append("prazo_mesmo_dia_verificar_hora")
    if proc.distance_km is not None:
        if proc.distance_km <= 50:
            score += 10
            reasons.append(f"distancia_{proc.distance_km:.0f}km")
        elif proc.distance_km <= 120:
            score += 5
            reasons.append(f"distancia_{proc.distance_km:.0f}km")
        else:
            risks.append(f"logistica_{proc.distance_km:.0f}km")

    # Docs inventory updated after evaluate by inventariar; only flag if still empty
    if proc.docs_inventory_status in {"pending", "urls_linked_only", ""}:
        risks.append("documentos_ainda_nao_inventariados")

    pending = sorted(set(pending))
    conf = min(0.95, 0.35 + aec.confidence * 0.4 + (0.1 if proc.official_page_validated else 0))

    # Decision rules
    hard = [
        b
        for b in blockers
        if b.startswith(
            (
                "prazo_",
                "status_",
                "sem_disputa",
                "objeto_nao_aec",
                "fora_do_universo",
                "distancia_proibitiva",
                "distancia_ausente",
            )
        )
        or "ato_sem_disputa" in b
        or "evento_terminal" in b
        or "texto_indica_ato_terminal" in b
        or "publicacao_dom_sem" in b
    ]

    if hard:
        recommendation = "NO_GO"
        exclusion = ";".join(hard)
        inclusion = ""
        next_action = "Descartar — blocker comprovado; registrar motivo no CRM."
        owner = "Operações Extra"
        score = min(score, 25)
    else:
        # GO only if no critical pending AND high adherence AND docs ok — Extra always has pending
        critical_pending = [p for p in pending if p in CRITICAL_PENDING_DEFAULT or p.startswith("capital")]
        docs_ok = str(proc.docs_inventory_status).startswith("complete")
        if (
            not critical_pending
            and aec.is_profile_adherent
            and docs_ok
            and proc.official_page_validated
            and score >= 70
        ):
            recommendation = "GO"
            inclusion = "perfil_completo_e_aderente_com_docs"
            exclusion = ""
            next_action = "Montar proposta e validar com Tiago."
            owner = "Tiago / Orçamentos"
        else:
            recommendation = "REVIEW"
            inclusion = "candidata_aec_universo_aberta"
            exclusion = ""
            if not proc.official_page_validated:
                next_action = "Validar página oficial e baixar edital/anexos antes de orçar."
            elif critical_pending:
                next_action = (
                    "Deep dive documental; preencher campos PENDING do perfil Extra "
                    f"({', '.join(critical_pending[:4])}) antes de GO."
                )
            else:
                next_action = "Revisar edital, requisitos e concorrência; decidir GO/NO_GO."
            owner = "Equipe Extra / Tiago"

    action_deadline = ""
    if proc.deadline_dt:
        action_deadline = br_date(proc.deadline_dt)

    return DecisionEvaluation(
        recommendation=recommendation,
        score=int(max(0, min(100, score))),
        confidence=round(conf, 3),
        reasons_for=reasons,
        blockers=sorted(set(blockers)),
        risks=sorted(set(risks)),
        pending=sorted(set(pending)),
        next_action=next_action,
        owner_suggested=owner,
        action_deadline=action_deadline,
        scoring_version=SCORING_VERSION,
        category=aec.category,
        category_label=aec.category_label,
        sector_label=aec.sector_label,
        sector_confidence=aec.confidence,
        inclusion_reason=inclusion,
        exclusion_reason=exclusion if recommendation == "NO_GO" else "",
    )


def apply_decisions(
    processes: list[CanonicalProcess],
    *,
    profile: dict[str, Any] | None = None,
) -> list[CanonicalProcess]:
    for p in processes:
        p.decision = evaluate_process(p, profile=profile)
        # enrich honest analysis fields
        if p.decision.recommendation == "NO_GO":
            p.buyer_analysis = "não aplicável — NO_GO"
            p.competitors_probable = "não aplicável — NO_GO"
            p.risks_summary = "; ".join(p.decision.blockers[:5])
            p.requirements_summary = "não avaliado (blocker)"
        else:
            p.buyer_analysis = (
                "histórico do órgão não consolidado neste pack — pendente consulta PNCP/contratos 12–36m"
            )
            p.competitors_probable = (
                "concorrentes prováveis não enumerados sem base histórica validada no recorte"
            )
            p.risks_summary = "; ".join(p.decision.risks[:6]) or "riscos a detalhar no deep dive"
            p.requirements_summary = (
                "habilitação/CAT/índices não extraídos de edital (docs não parseados) — PENDING humano"
            )
            if not p.official_page_validated:
                p.docs_inventory_status = "blocked_missing_official_page"
            else:
                p.docs_inventory_status = "urls_linked_only"
    return processes


def select_shortlist(
    processes: list[CanonicalProcess],
    *,
    limit: int = 25,
) -> list[CanonicalProcess]:
    """Shortlist principal: só camada decision, universo, abertos, AEC, sem NO_GO por terminal/fora."""
    candidates = [
        p
        for p in processes
        if p.layer == "decision"
        and p.in_universe
        and p.decision is not None
        and p.decision.recommendation in {"GO", "REVIEW"}
        and p.is_active_dispute
        and p.status_processo == "open"
        and p.decision.sector_label
        in {"ENGINEERING_HIGH_CONFIDENCE", "ENGINEERING_REVIEW"}
        and p.official_page_validated  # gate: shortlist needs specific official page
    ]
    # If too few with validated URL, allow REVIEW blocked with explicit note (still AEC open)
    if len(candidates) < 5:
        cand_ids = {p.process_id for p in candidates}
        extra = [
            p
            for p in processes
            if p.layer == "decision"
            and p.in_universe
            and p.decision is not None
            and p.decision.recommendation == "REVIEW"
            and p.is_active_dispute
            and p.status_processo == "open"
            and p.decision.sector_label
            in {"ENGINEERING_HIGH_CONFIDENCE", "ENGINEERING_REVIEW"}
            and p.process_id not in cand_ids
        ]
        for p in extra:
            if p.decision and not p.official_page_validated:
                p.decision.inclusion_reason = "review_bloqueado_sem_pagina_oficial_validada"
                p.decision.next_action = (
                    "Bloqueado para shortlist plena: obter URL oficial específica "
                    "e inventário documental."
                )
        candidates = candidates + extra

    candidates.sort(
        key=lambda p: (
            0 if p.decision and p.decision.recommendation == "GO" else 1,
            -(p.decision.score if p.decision else 0),
            p.calendar_days_remaining if p.calendar_days_remaining is not None else 999,
            p.distance_km if p.distance_km is not None else 9999,
        )
    )
    return candidates[:limit]
