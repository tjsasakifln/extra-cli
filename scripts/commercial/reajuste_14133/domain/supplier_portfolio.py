"""Consolidate contract-level leads into supplier-level commercial portfolios.

One CNPJ → one outreach lead with N linked contractual opportunities.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from scripts.commercial.reajuste_14133 import (
    DOCUMENT_REQUEST_CANDIDATE,
    NOT_READY_FOR_OUTREACH,
    OUTREACH_READY,
    OUTREACH_READY_WITHOUT_VALUE_ESTIMATE,
    PRIOR_ADJUSTMENT_CONFIRMED,
    STATUS_ALREADY_ADJUSTED,
    STATUS_NOT_ELIGIBLE,
    SUL_UFS,
    VALUE_OUTLIER_REQUIRES_REVIEW,
    VALUE_UNUSABLE,
)
from scripts.commercial.reajuste_14133.domain.outreach import exploratory_message


def _cnpj(lead: dict[str, Any]) -> str:
    return str(lead.get("cnpj") or "").strip()


def _safe_float(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def economic_dedupe_key(lead: dict[str, Any]) -> str:
    """Key for same economic work published under different admin unit CNPJs."""
    # Prefer contract id base (org+seq/year without unit branch) + object fingerprint
    cid = str(lead.get("contrato_id") or "")
    # PNCP: cnpj-seq/year — strip org CNPJ so sibling units collide less; use object+value
    obj = (lead.get("objeto") or "")[:120].lower().strip()
    val = round(_safe_float(lead.get("valor_original") or lead.get("valor_atualizado")), -3)
    supplier = _cnpj(lead)
    # Same supplier + similar value + similar object → same economic opportunity
    import hashlib
    import re

    obj_norm = re.sub(r"\s+", " ", obj)
    raw = f"{supplier}|{val}|{obj_norm}|{cid[-12:] if cid else ''}"
    return "eco:" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def same_obra_cross_org_key(lead: dict[str, Any]) -> str:
    """Detect same work republished by different administrative unit CNPJs."""
    import hashlib
    import re

    obj = re.sub(r"\s+", " ", (lead.get("objeto") or "")[:160].lower().strip())
    val = round(_safe_float(lead.get("valor_original") or lead.get("valor_atualizado")), -4)
    # Do NOT include orgao_cnpj — different units of same work should collide
    supplier = _cnpj(lead)
    year = ""
    for field in ("data_assinatura", "data_inicio", "data_publicacao"):
        if lead.get(field):
            year = str(lead.get(field))[:4]
            break
    raw = f"{supplier}|{val}|{obj}|{year}"
    return "obra:" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def dedupe_economic_opportunities(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one row per economic opportunity (contrato_id + same-obra multi-org)."""
    by_cid: dict[str, dict[str, Any]] = {}
    by_obra: dict[str, dict[str, Any]] = {}
    out: list[dict[str, Any]] = []
    for lead in leads:
        cid = str(lead.get("contrato_id") or lead.get("dedupe_key") or "")
        if cid and cid in by_cid:
            lead = dict(lead)
            lead["economic_dedupe"] = "duplicate_contrato_id"
            continue
        ok = same_obra_cross_org_key(lead)
        if ok in by_obra:
            # Prefer higher score / confirmed value
            prev = by_obra[ok]
            if _safe_float(lead.get("score_total")) <= _safe_float(prev.get("score_total")):
                lead = dict(lead)
                lead["economic_dedupe"] = "same_obra_multi_org_cnpj"
                continue
            # replace
            if prev in out:
                out.remove(prev)
        if cid:
            by_cid[cid] = lead
        by_obra[ok] = lead
        lead = dict(lead)
        lead["economic_key"] = ok
        out.append(lead)
    return out


def consolidate_suppliers(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group contract leads by supplier CNPJ into commercial portfolios."""
    deduped = dedupe_economic_opportunities(leads)
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for lead in deduped:
        c = _cnpj(lead)
        if len(c) != 14:
            continue
        buckets[c].append(lead)

    portfolios: list[dict[str, Any]] = []
    for cnpj, contracts in buckets.items():
        contracts_sorted = sorted(
            contracts,
            key=lambda x: (
                -_safe_float(x.get("score_total")),
                str(x.get("contrato_id") or ""),
            ),
        )
        best = contracts_sorted[0]
        orgaos = sorted(
            {
                str(c.get("orgao_contratante") or "").strip()
                for c in contracts_sorted
                if c.get("orgao_contratante")
            }
        )
        ufs = sorted({str(c.get("uf") or "").upper() for c in contracts_sorted if c.get("uf")})
        portfolio_value = 0.0
        for c in contracts_sorted:
            vq = (c.get("value_quality") or {}).get("status") or c.get("value_quality_status")
            if vq in {VALUE_OUTLIER_REQUIRES_REVIEW, VALUE_UNUSABLE, "VALUE_CONFLICT"}:
                continue
            portfolio_value += _safe_float(c.get("valor_original") or c.get("valor_atualizado"))

        mature = [
            c
            for c in contracts_sorted
            if c.get("outreach_status")
            in {OUTREACH_READY, OUTREACH_READY_WITHOUT_VALUE_ESTIMATE}
            or (
                c.get("dates", {}).get("interregno_completo")
                and c.get("regime_proven")
                and c.get("data_base_status") == "CONFIRMED"
            )
        ]
        doc_dep = [
            c
            for c in contracts_sorted
            if c.get("outreach_status") == DOCUMENT_REQUEST_CANDIDATE
            or c.get("classificacao")
            in {"STRONG_CANDIDATE", "REVIEW_REQUIRED", "RESEARCH_REQUIRED", "LEGAL_REGIME_UNKNOWN"}
        ]
        already = [
            c
            for c in contracts_sorted
            if c.get("classificacao") == STATUS_ALREADY_ADJUSTED
            or c.get("adjustment_history") == PRIOR_ADJUSTMENT_CONFIRMED
        ]
        discarded = [
            c for c in contracts_sorted if c.get("classificacao") == STATUS_NOT_ELIGIBLE
        ]

        # Supplier-level outreach = best among contracts (never UNKNOWN as ready)
        outreach_priority = {
            OUTREACH_READY: 4,
            OUTREACH_READY_WITHOUT_VALUE_ESTIMATE: 3,
            DOCUMENT_REQUEST_CANDIDATE: 2,
            NOT_READY_FOR_OUTREACH: 1,
        }
        best_outreach = NOT_READY_FOR_OUTREACH
        for c in contracts_sorted:
            st = c.get("outreach_status") or NOT_READY_FOR_OUTREACH
            if outreach_priority.get(st, 0) > outreach_priority.get(best_outreach, 0):
                best_outreach = st

        sul = bool(SUL_UFS.intersection(ufs)) or str(best.get("uf") or "").upper() in SUL_UFS
        contact = best.get("canais_contato") or {}
        has_contact = bool(contact.get("email") or contact.get("telefone") or contact.get("site"))

        if best_outreach == DOCUMENT_REQUEST_CANDIDATE:
            arg = exploratory_message()
        else:
            arg = best.get("argumento_comercial") or exploratory_message()

        risks: list[str] = []
        for c in contracts_sorted[:5]:
            risks.extend(list(c.get("riscos") or [])[:2])
        risks = list(dict.fromkeys(risks))[:12]

        portfolio = {
            "cnpj": cnpj,
            "razao_social": best.get("razao_social"),
            "nome_fantasia": best.get("nome_fantasia"),
            "sede_municipio": best.get("municipio_empresa"),
            "sede_uf": best.get("uf") or (ufs[0] if ufs else None),
            "ufs_execucao": ufs,
            "sul_priority": sul,
            "porte_cadastral": best.get("porte_cadastral"),
            "cnae": best.get("cnae") or (best.get("registry") or {}).get("cnae_principal"),
            "situacao_cadastral": best.get("situacao_cadastral")
            or (best.get("registry") or {}).get("situacao_cadastral"),
            "contatos": contact,
            "contato_verificavel": has_contact,
            "qtd_contratos_candidatos": len(contracts_sorted),
            "orgaos_contratantes": orgaos,
            "valor_total_portfolio_analisado": portfolio_value,
            "contratos_reajuste_maduro": [
                c.get("contrato_id") for c in mature if c.get("contrato_id")
            ],
            "contratos_dependentes_documentos": [
                c.get("contrato_id") for c in doc_dep if c.get("contrato_id")
            ],
            "contratos_ja_reajustados": [
                c.get("contrato_id") for c in already if c.get("contrato_id")
            ],
            "contratos_descartados": [
                c.get("contrato_id") for c in discarded if c.get("contrato_id")
            ],
            "melhor_oportunidade": {
                "contrato_id": best.get("contrato_id"),
                "orgao": best.get("orgao_contratante"),
                "score": best.get("score_total"),
                "classificacao": best.get("classificacao"),
                "outreach_status": best.get("outreach_status"),
                "valor_original": best.get("valor_original"),
                "data_base_status": best.get("data_base_status"),
                "regime_legal": best.get("regime_legal"),
                "objeto": (best.get("objeto") or "")[:400],
            },
            "argumento_comercial": arg,
            "outreach_status": best_outreach,
            "prioridade_abordagem": (
                "SUL_SC_PRIORITY"
                if sul and best_outreach != NOT_READY_FOR_OUTREACH
                else ("NACIONAL" if best_outreach != NOT_READY_FOR_OUTREACH else "INTELIGENCIA")
            ),
            "proxima_acao": best.get("proxima_acao_investigativa")
            or best.get("outreach_next_action")
            or "Revisar dossiê documental do melhor contrato.",
            "riscos": risks,
            "evidencias": best.get("evidencias_favoraveis") or [],
            "score_fornecedor": max(_safe_float(c.get("score_total")) for c in contracts_sorted),
            "contratos": [
                {
                    "contrato_id": c.get("contrato_id"),
                    "orgao_contratante": c.get("orgao_contratante"),
                    "orgao_cnpj": c.get("orgao_cnpj"),
                    "uf": c.get("uf"),
                    "valor_original": c.get("valor_original"),
                    "classificacao": c.get("classificacao"),
                    "outreach_status": c.get("outreach_status"),
                    "score_total": c.get("score_total"),
                    "data_base_status": c.get("data_base_status"),
                    "regime_legal": c.get("regime_legal"),
                    "regime_proven": c.get("regime_proven"),
                    "indice": c.get("indice"),
                    "valor_potencial": c.get("valor_potencial"),
                    "value_quality_status": c.get("value_quality_status")
                    or (c.get("value_quality") or {}).get("status"),
                    "objeto": (c.get("objeto") or "")[:300],
                }
                for c in contracts_sorted
            ],
            "mensagem_abordagem": arg,
            "module_version": best.get("module_version"),
        }
        portfolios.append(portfolio)

    portfolios.sort(
        key=lambda p: (
            -{"OUTREACH_READY": 4, "OUTREACH_READY_WITHOUT_VALUE_ESTIMATE": 3,
              "DOCUMENT_REQUEST_CANDIDATE": 2}.get(p.get("outreach_status") or "", 0),
            -_safe_float(p.get("score_fornecedor")),
            p.get("cnpj") or "",
        )
    )
    for i, p in enumerate(portfolios, start=1):
        p["ranking"] = i
    return portfolios
