"""Reconciliação dimensional de contagens."""

from __future__ import annotations

from collections import Counter

from scripts.ops.multi_source_open_pack.models import (
    BuyerEntity,
    CanonicalProcess,
    ReconciliationStats,
    SourceObservation,
)


def build_reconciliation(
    *,
    entities: list[BuyerEntity],
    observations: list[SourceObservation],
    processes: list[CanonicalProcess],
    shortlist: list[CanonicalProcess],
    merges: int,
    coverage_rows: list[dict[str, str]] | None = None,
) -> ReconciliationStats:
    by_src = Counter(o.fonte for o in observations)
    excl = Counter()
    for p in processes:
        if p.decision and p.decision.recommendation == "NO_GO":
            reason = p.decision.exclusion_reason or p.exclusion_reason or "no_go"
            excl[reason.split(";")[0][:80]] += 1
        elif p.exclusion_reason and not p.is_active_dispute:
            excl[p.exclusion_reason[:80]] += 1

    aec = [
        p
        for p in processes
        if p.decision
        and p.decision.sector_label
        in {"ENGINEERING_HIGH_CONFIDENCE", "ENGINEERING_REVIEW"}
    ]
    adherent = [p for p in aec if p.decision and p.decision.category and "nao_relacion" not in p.decision.category]
    open_procs = [p for p in processes if p.status_processo == "open" and p.is_active_dispute]
    in_uni = [p for p in processes if p.in_universe]
    acionaveis = [
        p
        for p in open_procs
        if p.in_universe
        and p.decision
        and p.decision.recommendation in {"GO", "REVIEW"}
        and p.decision.sector_label
        in {"ENGINEERING_HIGH_CONFIDENCE", "ENGINEERING_REVIEW"}
    ]
    with_docs = [p for p in processes if p.docs_inventory_status == "complete"]
    go = sum(1 for p in processes if p.decision and p.decision.recommendation == "GO")
    review = sum(1 for p in processes if p.decision and p.decision.recommendation == "REVIEW")
    nogo = sum(1 for p in processes if p.decision and p.decision.recommendation == "NO_GO")
    pend = sum(1 for p in processes if p.decision and p.decision.pending)

    # Coverage from evidence rows if available
    entes_n = len(entities)
    covered_ids: set[str] = set()
    if coverage_rows:
        for r in coverage_rows:
            st = (r.get("state") or "").strip()
            if st in {"success_with_data", "success_zero", "partial"}:
                eid = (r.get("entity_id") or r.get("cnpj") or r.get("cnpj8") or "").strip()
                if eid:
                    covered_ids.add(eid[:8] if eid.isdigit() and len(eid) >= 8 else eid)
    # Also count entities that matched observations
    matched_entities = {p.entity_key for p in processes if p.in_universe and p.entity_key}
    # entes_cobertos = min of evidence covered or matched, never > universe
    if covered_ids:
        entes_cobertos = min(entes_n, len(covered_ids))
    else:
        entes_cobertos = min(entes_n, len(matched_entities))

    # applicable sources: all municipal entities have pncp+ciga applicable
    entes_aplicavel = entes_n

    return ReconciliationStats(
        entes_universo=entes_n,
        entes_com_fonte_aplicavel=entes_aplicavel,
        entes_cobertos=entes_cobertos,
        entes_nao_consultados=max(0, entes_aplicavel - entes_cobertos),
        observacoes_brutas=len(observations),
        observacoes_por_fonte=dict(by_src),
        publicacoes_dom=by_src.get("ciga_ckan", 0),
        processos_canonicos=len(processes),
        processos_abertos=len(open_procs),
        processos_no_universo=len(in_uni),
        processos_aec=len(aec),
        processos_aderentes=len(adherent),
        processos_com_docs=len(with_docs),
        oportunidades_acionaveis=len(acionaveis),
        shortlist=len(shortlist),
        no_go=nogo,
        review=review,
        go=go,
        pendencias_confirmacao=pend,
        exclusoes_por_motivo=dict(excl.most_common(40)),
        merges_realizados=merges,
        observacoes_fora_universo=sum(1 for o in observations if not o.in_universe),
        observacoes_no_universo=sum(1 for o in observations if o.in_universe),
    )


def format_reconciliation_labels(stats: ReconciliationStats) -> list[tuple[str, int | str]]:
    """Human-readable dimensional labels for PDF/XLSX/LEIA-ME."""
    src = stats.observacoes_por_fonte
    return [
        ("Entes no universo canônico (200 km)", stats.entes_universo),
        ("Entes com fonte aplicável", stats.entes_com_fonte_aplicavel),
        ("Entes cobertos (evidência de consulta)", stats.entes_cobertos),
        ("Entes não consultados / sem evidência", stats.entes_nao_consultados),
        ("Observações brutas coletadas (não são entes)", stats.observacoes_brutas),
        ("  · observações PNCP", src.get("pncp", 0)),
        ("  · publicações DOM (CIGA)", src.get("ciga_ckan", 0)),
        ("  · observações SC Compras", src.get("sc_compras", 0)),
        ("  · observações no universo", stats.observacoes_no_universo),
        ("  · observações fora do universo", stats.observacoes_fora_universo),
        ("Processos canônicos únicos (deduplicados)", stats.processos_canonicos),
        ("Processos realmente abertos (disputa ativa)", stats.processos_abertos),
        ("Processos dentro do universo", stats.processos_no_universo),
        ("Processos classificados AEC", stats.processos_aec),
        ("Processos aderentes ao perfil Extra", stats.processos_aderentes),
        ("Processos com inventário documental completo", stats.processos_com_docs),
        ("Oportunidades acionáveis", stats.oportunidades_acionaveis),
        ("Shortlist prioritária", stats.shortlist),
        ("Decisões NO_GO", stats.no_go),
        ("Decisões REVIEW", stats.review),
        ("Decisões GO", stats.go),
        ("Com pendências de confirmação humana", stats.pendencias_confirmacao),
        ("Merges de duplicidade realizados", stats.merges_realizados),
    ]
