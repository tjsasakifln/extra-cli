"""Commercial dossiers for Top-N companies — factual, no purchase claims."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_FORBIDDEN = re.compile(
    r"propens[aã]o|probabilidade de compra|inten[cç][aã]o de compra|"
    r"lead quente|dor comprovada|empresa interessada|chance de convers",
    re.I,
)


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def build_dossier(lead: dict[str, Any], *, run_id: str | None = None) -> dict[str, Any]:
    """Structured dossier payload (JSON-serializable)."""
    signals_fired = lead.get("signals_fired") or []
    signals_nc = lead.get("signals_not_computable") or []
    evidence = lead.get("evidence") or []
    contracts = lead.get("contracts_sample") or lead.get("evidence") or []
    reg = lead.get("registry") or {}
    sector = lead.get("supplier_sector_evidence") or lead.get("supplier_sector_fit")
    limitations = list(lead.get("limitations") or [])
    dossier = {
        "schema_version": "commercial-dossier-v1",
        "identification": {
            "cnpj14": lead.get("cnpj14"),
            "razao_social": lead.get("razao_social"),
            "nome_fantasia": lead.get("nome_fantasia") or reg.get("nome_fantasia") or "NOT_AVAILABLE",
            "municipio": lead.get("municipio") or reg.get("municipio") or "NOT_AVAILABLE",
            "uf": lead.get("uf") or reg.get("uf") or "NOT_AVAILABLE",
            "situacao_cadastral": reg.get("situacao_cadastral") or lead.get("situacao_cadastral") or "NOT_AVAILABLE",
            "cnae_principal": lead.get("cnae_principal") or reg.get("cnae_principal") or "NOT_AVAILABLE",
        },
        "factual_summary": {
            "rank_position": lead.get("rank_position"),
            "score_total": lead.get("score_total"),
            "priority": lead.get("priority"),
            "supplier_sector_fit": lead.get("supplier_sector_fit"),
            "activity_class": lead.get("activity_class"),
            "contract_count": lead.get("contract_count"),
            "total_value_brl": lead.get("total_value"),
            "total_value_semantics": "sum_of_observed_public_contracts_in_loaded_history",
            "last_publication": lead.get("last_publication"),
            "commercial_state": lead.get("commercial_state", "NEW"),
        },
        "contracts_observed": contracts[:50] if isinstance(contracts, list) else [],
        "related_organs": lead.get("organs") or lead.get("related_organs") or [],
        "temporal_evolution": lead.get("history_metrics") or lead.get("data_quality") or {},
        "concentration": {
            k: lead.get(k)
            for k in ("agency_concentration", "contract_concentration")
            if lead.get(k) is not None
        },
        "near_expiry_contracts": lead.get("near_expiry") or [],
        "relevant_events": lead.get("relevant_events") or [],
        "signals_fired": signals_fired,
        "signals_not_computable": signals_nc,
        "suggested_offer": {
            "offer_id": lead.get("suggested_offer"),
            "hypothesis": lead.get("offer_hypothesis")
            or "Oferta sugerida a partir dos sinais observáveis; não implica interesse da empresa.",
            "evidence_refs": evidence[:10] if isinstance(evidence, list) else [],
        },
        "value_hypothesis": lead.get("value_hypothesis")
        or "Hipótese de aderência CONFENGE baseada em sinais B2G observáveis no histórico público.",
        "limitations": limitations,
        "sources": {
            "run_id": run_id or lead.get("source_run_id"),
            "profile_version": lead.get("profile_version"),
            "catalog_version": lead.get("catalog_version"),
            "snapshot_id": lead.get("dataset_snapshot_id") or lead.get("snapshot_hash"),
            "registry_source": reg.get("source") or lead.get("registry_source"),
            "registry_source_date": reg.get("source_date") or lead.get("registry_source_date"),
        },
        "recommended_next_step": lead.get("next_human_step")
        or "Revisão humana: validar aderência setorial e decidir abordagem manual.",
        "human_decision_field": {
            "decision": None,
            "sector_ok": None,
            "priority_ok": None,
            "notes": None,
            "author": None,
            "decided_at": None,
        },
        "outcome_field": {
            "status": lead.get("commercial_state", "NEW"),
            "outcome": None,
            "recorded_at": None,
            "author": None,
        },
        "language_policy": {
            "forbidden_claims_present": False,
            "note": "Documento factual para revisão humana; não afirma demanda ou fechamento.",
        },
    }
    # Scan only commercial prose fields — not the meta note about the policy itself.
    scan_blob = json.dumps(
        {
            "summary": dossier.get("factual_summary"),
            "signals": dossier.get("signals_fired"),
            "offer": dossier.get("suggested_offer"),
            "value_hypothesis": dossier.get("value_hypothesis"),
            "next": dossier.get("recommended_next_step"),
            "limitations": dossier.get("limitations"),
        },
        ensure_ascii=False,
        default=str,
    )
    if _FORBIDDEN.search(scan_blob):
        dossier["language_policy"]["forbidden_claims_present"] = True
        dossier["limitations"].append("language_scan_flagged_forbidden_terms")
    return dossier


def dossier_to_markdown(dossier: dict[str, Any]) -> str:
    ident = dossier.get("identification") or {}
    fact = dossier.get("factual_summary") or {}
    offer = dossier.get("suggested_offer") or {}
    src = dossier.get("sources") or {}
    lines = [
        f"# Dossier comercial — {ident.get('razao_social') or 'N/A'}",
        "",
        f"- **CNPJ:** `{ident.get('cnpj14')}`",
        f"- **Nome fantasia:** {ident.get('nome_fantasia')}",
        f"- **Local:** {ident.get('municipio')}/{ident.get('uf')}",
        f"- **Situação cadastral:** {ident.get('situacao_cadastral')}",
        f"- **CNAE principal:** {ident.get('cnae_principal')}",
        "",
        "## Resumo factual",
        f"- Rank: {fact.get('rank_position')} | Score: {fact.get('score_total')} | Prioridade: {fact.get('priority')}",
        f"- Setor: {fact.get('supplier_sector_fit')} | Atividade: {fact.get('activity_class')}",
        f"- Contratos observados: {fact.get('contract_count')} | Valor total (soma histórica carregada): {fact.get('total_value_brl')}",
        f"- Semântica do valor: `{fact.get('total_value_semantics')}`",
        f"- Última publicação observada: {fact.get('last_publication')}",
        f"- Estado comercial: {fact.get('commercial_state')}",
        "",
        "## Sinais acionados",
    ]
    for s in dossier.get("signals_fired") or []:
        if isinstance(s, dict):
            lines.append(f"- `{s.get('signal_id')}` — {s.get('hypothesis') or s.get('status')}")
        else:
            lines.append(f"- `{s}`")
    lines.append("")
    lines.append("## Sinais não computáveis")
    for s in dossier.get("signals_not_computable") or []:
        if isinstance(s, dict):
            lines.append(f"- `{s.get('signal_id')}` — {s.get('not_computable_reason') or 'NOT_COMPUTABLE'}")
        else:
            lines.append(f"- `{s}`")
    lines += [
        "",
        "## Oferta CONFENGE sugerida",
        f"- **Oferta:** {offer.get('offer_id')}",
        f"- **Hipótese:** {offer.get('hypothesis')}",
        "",
        "## Hipótese de valor",
        _safe_text(dossier.get("value_hypothesis")),
        "",
        "## Limitações",
    ]
    for lim in dossier.get("limitations") or []:
        lines.append(f"- {lim}")
    lines += [
        "",
        "## Fontes",
        f"- run_id: `{src.get('run_id')}`",
        f"- snapshot: `{src.get('snapshot_id')}`",
        f"- registry: `{src.get('registry_source')}` @ `{src.get('registry_source_date')}`",
        "",
        "## Próximo passo recomendado",
        _safe_text(dossier.get("recommended_next_step")),
        "",
        "## Decisão humana (preencher)",
        "- decision: ",
        "- sector_ok: ",
        "- notes: ",
        "- author: ",
        "",
        "## Outcome posterior (preencher)",
        "- status: ",
        "- outcome: ",
        "",
        "---",
        "_Documento gerado para revisão humana. Não envia mensagens. Não afirma intenção de compra._",
        "",
    ]
    return "\n".join(lines)


def export_dossiers(
    out_dir: Path,
    leads: list[dict[str, Any]],
    *,
    run_id: str | None = None,
    limit: int = 20,
) -> dict[str, str]:
    """Write JSON + Markdown dossiers for top N leads."""
    root = Path(out_dir) / "top20-dossiers"
    root.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    index: list[dict[str, Any]] = []
    for lead in leads[:limit]:
        cnpj = str(lead.get("cnpj14") or "unknown")
        dossier = build_dossier(lead, run_id=run_id)
        jp = root / f"{cnpj}.json"
        mp = root / f"{cnpj}.md"
        jp.write_text(json.dumps(dossier, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
        mp.write_text(dossier_to_markdown(dossier), encoding="utf-8")
        paths[f"dossier:{cnpj}:json"] = str(jp)
        paths[f"dossier:{cnpj}:md"] = str(mp)
        index.append(
            {
                "cnpj14": cnpj,
                "rank": lead.get("rank_position"),
                "json": str(jp),
                "md": str(mp),
                "score": lead.get("score_total"),
            }
        )
    idx_path = root / "index.json"
    idx_path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    paths["dossiers_index"] = str(idx_path)
    return paths
