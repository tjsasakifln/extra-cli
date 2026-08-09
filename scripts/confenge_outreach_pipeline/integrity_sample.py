"""Organic integrity sample builder (no per-service quota).

Runs: select_services → MessageSpine → draft body → copy gates → near_dup
on TARGET_CONFIRMED bags. Labels sampling as organic_top_n.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from scripts.confenge_account_intelligence.pipeline import build_dossier
from scripts.confenge_account_intelligence.message_spine import is_hollow_fact
from scripts.confenge_outreach_pipeline.near_duplicate import (
    audit_near_duplicates,
    subject_is_generic_contrato,
)
from scripts.confenge_service_contract.mapping import map_to_canonical, map_to_warmbly


def bag_from_feed_lead(lead: dict[str, Any]) -> dict[str, Any]:
    """Convert a confenge.outreach.v1 lead into an intelligence bag."""
    company = lead.get("company") if isinstance(lead.get("company"), dict) else {}
    contracts_in = lead.get("contracts") or []
    contracts: list[dict[str, Any]] = []
    for c in contracts_in:
        if not isinstance(c, dict):
            continue
        contracts.append(
            {
                "id": c.get("id") or c.get("contrato_id"),
                "object": c.get("object") or c.get("objeto"),
                "objeto": c.get("object") or c.get("objeto"),
                "value_brl": c.get("value_brl") or c.get("valor_total"),
                "valor_total": c.get("value_brl") or c.get("valor_total"),
                "orgao": c.get("agency") or c.get("orgao") or c.get("orgao_nome"),
                "agency": c.get("agency") or c.get("orgao"),
                "uf": c.get("uf"),
                "start_date": c.get("start_date"),
                "end_date": c.get("end_date"),
                "publication_date": c.get("publication_date") or c.get("data_publicacao"),
            }
        )
    return {
        "cnpj14": company.get("cnpj14") or lead.get("cnpj14"),
        "cnpj_root": (company.get("cnpj14") or lead.get("cnpj14") or "")[:8],
        "razao_social": company.get("legal_name") or company.get("razao_social") or lead.get("razao_social"),
        "nome_fantasia": company.get("trade_name") or company.get("nome_fantasia"),
        "municipio": company.get("municipio") or company.get("city"),
        "uf": company.get("uf") or company.get("state"),
        "activity_class": company.get("activity_class") or lead.get("activity_class"),
        "target_fit_class": lead.get("target_fit_class") or company.get("target_fit_class"),
        "contracts": contracts,
        "evidence": lead.get("evidence") or [],
        "commercial_state": lead.get("commercial_state") or "NEW",
    }


def compose_body(dossier: dict[str, Any]) -> str:
    company = str(
        (dossier.get("account_snapshot") or {}).get("razao_social")
        or dossier.get("razao_social")
        or "a empresa"
    )
    fact = str(dossier.get("body_seed_fact") or dossier.get("observed_fact") or "").strip()
    # Prefer MessageSpine why_now (never hollow portfolio_review template)
    why_now = ""
    spine = dossier.get("message_spine") if isinstance(dossier.get("message_spine"), dict) else {}
    if spine.get("why_now"):
        why_now = str(spine.get("why_now") or "").strip()
    if not why_now or is_hollow_fact(why_now):
        wn = dossier.get("why_now")
        if isinstance(wn, dict):
            why_now = str(wn.get("temporal_fact") or wn.get("summary") or "").strip()
        if is_hollow_fact(why_now):
            why_now = ""
    cta = str(dossier.get("cta") or "").strip()
    parts = [
        "Olá,",
        "",
        f"Pelo que está público sobre {company}, {fact}." if fact else f"Pelo que está público sobre {company}.",
        "",
    ]
    if why_now and not is_hollow_fact(why_now):
        parts.append(why_now)
        parts.append("")
    if cta:
        parts.append(cta)
    return "\n".join(parts).strip() + "\n"


def compose_subject(dossier: dict[str, Any]) -> str:
    fact = str(dossier.get("observed_fact") or "")
    sid = str((dossier.get("primary_service") or {}).get("service_id") or "")
    # Theme from service / fact snippet
    theme_map = {
        "reequilibrio_economico_financeiro": "Reequilíbrio contratual",
        "aditivos_extracontratuais": "Aditivos e extracontratuais",
        "medicoes_glosas_memoria": "Medições e memória",
        "auditoria_orcamento_bdi": "Planilha / BDI",
        "gestao_monitoramento_contratual": "Gestão contratual",
        "apoio_licitacoes_propostas": "Licitações / propostas",
        "estruturacao_pleito_reajuste": "Checagem de reajuste",
        "diagnostico_contratual_b2g": "Diagnóstico contratual B2G",
        "reforco_temporario_backoffice": "Backoffice contratual",
        "inteligencia_pncp_mercado": "Inteligência PNCP",
    }
    base = theme_map.get(sid, "Contratos públicos")
    # Add short object hook if present
    if "objeto:" in fact.lower():
        obj = fact.split("objeto:", 1)[-1].split(";")[0].strip()[:48]
        if obj:
            return f"{base}: {obj}"
    return base


def build_integrity_sample(
    bags: list[dict[str, Any]],
    *,
    n: int = 30,
    require_target_confirmed: bool = True,
) -> dict[str, Any]:
    """Organic top-n sample. No per-service caps.

    Returns audit payload with drafts, service distribution, gates, near_dup.
    """
    dossiers: list[dict[str, Any]] = []
    for bag in bags:
        if require_target_confirmed:
            tfc = str(bag.get("target_fit_class") or "")
            if tfc and tfc not in {"TARGET_CONFIRMED", "TARGET_CONFIRMED".lower()}:
                # allow empty and re-compute later via bag only if marked confirmed
                if tfc not in {"TARGET_CONFIRMED"}:
                    continue
        try:
            d = build_dossier(bag)
        except Exception:
            continue
        d["_source_bag"] = bag
        dossiers.append(d)

    # Prefer complete spines, then multi-contract portfolios
    def _rank(d: dict[str, Any]) -> tuple:
        spine_ok = 1 if d.get("message_spine_complete") else 0
        fact_ok = 0 if is_hollow_fact(str(d.get("observed_fact") or "")) else 1
        n_contracts = len(d.get("_pipeline_contracts") or [])
        return (spine_ok, fact_ok, n_contracts)

    dossiers.sort(key=_rank, reverse=True)
    # Organic top-n: no rebalancing by service family
    selected = dossiers[:n]

    drafts: list[dict[str, Any]] = []
    for d in selected:
        snap = d.get("account_snapshot") or {}
        sid = str((d.get("primary_service") or {}).get("service_id") or "")
        try:
            warmbly = map_to_warmbly(sid)
            canonical = map_to_canonical(sid)
        except Exception:
            warmbly, canonical = sid, sid
        body = compose_body(d)
        subject = compose_subject(d)
        drafts.append(
            {
                "cnpj": snap.get("cnpj14"),
                "razao_social": snap.get("razao_social"),
                "uf": snap.get("uf"),
                "target_fit_class": d.get("target_fit_class") or "TARGET_CONFIRMED",
                "service_id": sid,
                "canonical_service_code": canonical,
                "warmbly_service_code": warmbly,
                "why_you": d.get("why_this_account") or "",
                "why_now": (
                    (d.get("why_now") or {}).get("temporal_fact")
                    if isinstance(d.get("why_now"), dict)
                    else d.get("why_now")
                )
                or "",
                "observed_fact": d.get("observed_fact") or "",
                "body_seed_fact": d.get("body_seed_fact") or d.get("observed_fact") or "",
                "micro_offer": d.get("micro_offer_code") or "",
                "evidence_ids": list(d.get("fact_evidence_ids") or [])
                or [e.get("id") for e in (d.get("confirmed_facts") or []) if isinstance(e, dict)],
                "rationale": d.get("service_fit_rationale") or "",
                "subject": subject,
                "body": body,
                "message_spine_complete": bool(d.get("message_spine_complete")),
                "supporting_signal_ids": list(
                    ((d.get("primary_service") or {}).get("supporting_signal_ids") or [])
                ),
                "generic_contrato_subject": subject_is_generic_contrato(
                    subject, str(snap.get("razao_social") or "")
                ),
            }
        )

    # Prefer spine why_now (already de-hollowed) over raw dossier why_now temporal_fact
    for x, d in zip(drafts, selected):
        spine = d.get("message_spine") if isinstance(d.get("message_spine"), dict) else {}
        spine_why_now = str(spine.get("why_now") or "").strip()
        if spine_why_now and not is_hollow_fact(spine_why_now):
            x["why_now"] = spine_why_now
        # Prefer spine completeness flag after hollow alignment
        x["message_spine_complete"] = bool(
            d.get("message_spine_complete")
            and not is_hollow_fact(x.get("why_now"))
            and not is_hollow_fact(x.get("observed_fact"))
            and not is_hollow_fact(x.get("why_you"))
        )

    # Gate metrics — same hollow detector as COPY_CONTEXT_READY
    empty_why = sum(1 for x in drafts if not str(x["why_you"]).strip() or is_hollow_fact(x["why_you"]))
    empty_why_now = sum(
        1 for x in drafts if not str(x.get("why_now") or "").strip() or is_hollow_fact(x.get("why_now"))
    )
    empty_micro = sum(1 for x in drafts if not str(x["micro_offer"]).strip())
    empty_fact = sum(1 for x in drafts if is_hollow_fact(x["observed_fact"]))
    empty_ev = sum(1 for x in drafts if not x.get("evidence_ids"))
    generic_subj = sum(1 for x in drafts if x.get("generic_contrato_subject"))
    hollow_body = sum(
        1
        for x in drafts
        if "portfólio público observado com" in (x.get("body") or "").lower()
        or "portfólio público observável" in (x.get("body") or "").lower()
    )
    spine_incomplete = sum(1 for x in drafts if not x.get("message_spine_complete"))
    nd = audit_near_duplicates(drafts)
    svc_dist = Counter(x["service_id"] for x in drafts)
    warmbly_dist = Counter(x["warmbly_service_code"] for x in drafts)
    top = max(svc_dist.values()) / len(drafts) if drafts else 0.0
    concentration = None
    if top > 0.8:
        concentration = "ROUTING_CONCENTRATION_BLOCK"
    elif top > 0.6:
        concentration = "ROUTING_CONCENTRATION_REVIEW_REQUIRED"

    struct_ok = (
        empty_why == 0
        and empty_why_now == 0
        and empty_micro == 0
        and empty_fact == 0
        and empty_ev == 0
        and hollow_body == 0
        and spine_incomplete == 0
        and not nd.blocked
        and len(drafts) >= min(n, 1)
    )

    return {
        "sampling": "organic_top_n",
        "n_requested": n,
        "n_pool": len(dossiers),
        "n_selected": len(drafts),
        "service_distribution_extra_cli": dict(svc_dist),
        "service_distribution_warmbly": dict(warmbly_dist),
        "gates": {
            "empty_why_you": empty_why,
            "hollow_why_now": empty_why_now,
            "empty_micro_offer": empty_micro,
            "hollow_observed_fact": empty_fact,
            "empty_evidence_ids": empty_ev,
            "generic_contrato_subject": generic_subj,
            "hollow_portfolio_body": hollow_body,
            "spine_incomplete": spine_incomplete,
            "near_duplicate": nd.as_dict(),
            "struct_ok": struct_ok,
        },
        "concentration_flag": concentration,
        "top_service_fraction": round(top, 4),
        "drafts": drafts,
        "verdict_hint": "PASS_STRUCTURAL" if struct_ok else "FAIL_STRUCTURAL",
    }
