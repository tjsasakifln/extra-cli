"""Análise de edital, órgão e concorrentes (com texto de documentos + market intel)."""

from __future__ import annotations

import re
from typing import Any

from scripts.ops.multi_source_open_pack.market_intel import apply_market_intel
from scripts.ops.multi_source_open_pack.models import CanonicalProcess
from scripts.ops.multi_source_open_pack.textutil import br_currency


def _find_patterns(text: str) -> dict[str, str]:
    t = text or ""
    out: dict[str, str] = {}
    patterns = {
        "objeto_escopo": r"(?:objeto|do objeto)[:\s]+(.{20,200})",
        "garantia_proposta": r"garantia\s+da\s+proposta[^.\n]{0,160}",
        "garantia_contratual": r"garantia\s+contratual[^.\n]{0,160}",
        "habilitacao": r"habilita[cç][aã]o[^.\n]{0,200}",
        "habilitacao_juridica": r"habilita[cç][aã]o\s+jur[ií]dica[^.\n]{0,160}",
        "regularidade_fiscal": r"regularidade\s+fiscal[^.\n]{0,140}",
        "capacidade_tecnica": r"(?:capacidade|qualifica[cç][aã]o)\s+t[eé]cnica[^.\n]{0,180}",
        "capacidade_economica": r"(?:capacidade|qualifica[cç][aã]o)\s+econ[oô]mico[^.\n]{0,180}",
        "patrimonio_liquido": r"patrim[oô]nio\s+l[ií]quido[^.\n]{0,120}",
        "indices_financeiros": r"(?:[ií]ndices?\s+(?:cont[aá]beis|econ[oô]micos)|liquidez\s+geral|liquidez\s+corrente)[^.\n]{0,140}",
        "prazo_execucao": r"prazo\s+de\s+execu[cç][aã]o[^.\n]{0,140}",
        "vigencia": r"vig[eê]ncia[^.\n]{0,120}",
        "regime_execucao": r"regime\s+de\s+execu[cç][aã]o[^.\n]{0,120}",
        "criterio_julgamento": r"crit[eé]rio\s+de\s+julgamento[^.\n]{0,140}",
        "forma_disputa": r"forma\s+de\s+disputa[^.\n]{0,120}",
        "visita_tecnica": r"visita\s+t[eé]cnica[^.\n]{0,140}",
        "consorcio": r"cons[oó]rcio[^.\n]{0,120}",
        "subcontratacao": r"subcontrata[cç][aã]o[^.\n]{0,120}",
        "pagamento": r"(?:condi[cç][oõ]es\s+de\s+pagamento|medi[cç][oõ]es|cronograma\s+de\s+desembolso)[^.\n]{0,160}",
        "reajuste": r"reajust[^.\n]{0,100}",
        "multas": r"(?:multas?|san[cç][oõ]es)[^.\n]{0,140}",
        "matriz_risco": r"matriz\s+de\s+riscos?[^.\n]{0,120}",
        "local_execucao": r"local\s+de\s+execu[cç][aã]o[^.\n]{0,140}",
        "orcamento_sigiloso": r"or[cç]amento\s+sigiloso[^.\n]{0,100}",
        "bdi": r"\bBDI\b[^.\n]{0,80}",
        "cat_atestado": r"(?:CAT|atestado\s+de\s+capacidade)[^.\n]{0,140}",
        "esclarecimentos": r"esclarecimentos?[^.\n]{0,120}",
        "impugnacao": r"impugna[cç][aã]o[^.\n]{0,120}",
    }
    for key, pat in patterns.items():
        m = re.search(pat, t, re.I | re.S)
        if m:
            snippet = m.group(0) if m.lastindex is None else (m.group(0))
            out[key] = re.sub(r"\s+", " ", snippet).strip()[:220]
    return out


def analyze_edital_minimo(proc: CanonicalProcess, page_text: str = "") -> dict[str, Any]:
    """Análise de edital a partir de texto de página + PDFs extraídos."""
    text = (
        page_text
        or getattr(proc, "_combined_doc_text", "")
        or getattr(proc, "_page_text_sample", "")
        or ""
    )
    extracted = _find_patterns(text)
    critical = (
        "habilitacao",
        "garantia_proposta",
        "prazo_execucao",
        "criterio_julgamento",
        "regime_execucao",
        "capacidade_tecnica",
    )
    found_critical = [k for k in critical if k in extracted]
    missing = [k for k in critical if k not in extracted]

    summary_parts = [
        f"Objeto: {(proc.objeto or '')[:280]}",
        f"Modalidade: {proc.modalidade or 'n/d'}",
        f"Valor estimado (semântica=estimado): "
        f"{br_currency(proc.valor_estimado) if proc.valor_estimado is not None else 'n/d'}",
        f"Prazo encerramento: {proc.data_encerramento or 'n/d'} "
        f"(dúteis: {proc.business_days_remaining if proc.business_days_remaining is not None else 'n/d'})",
        f"Status: {proc.status_processo}; disputa ativa: {proc.is_active_dispute}",
        f"Documentos: {len(proc.documents)} ({proc.docs_inventory_status}); "
        f"texto extraído: {len(text)} chars",
    ]
    if extracted:
        summary_parts.append("Cláusulas/trechos localizados nos documentos oficiais:")
        for k, v in list(extracted.items())[:14]:
            summary_parts.append(f"  - {k}: {v[:140]}")
    if missing:
        summary_parts.append(
            "Campos críticos ainda não localizados no texto extraído: " + ", ".join(missing)
        )

    risks = list(proc.decision.risks if proc.decision else [])
    if "visita_tecnica" in extracted and re.search(
        r"obrigat", extracted["visita_tecnica"], re.I
    ):
        risks.append("visita_tecnica_possivelmente_obrigatoria")
    if proc.calendar_days_remaining is not None and proc.calendar_days_remaining < 5:
        risks.append("prazo_curto_para_montagem_proposta")
    if "orcamento_sigiloso" in extracted:
        risks.append("orcamento_sigiloso_dificulta_precificacao")
    if missing:
        risks.append("lacunas_na_extracao_documental")

    requirements: list[str] = []
    for k in (
        "habilitacao",
        "habilitacao_juridica",
        "capacidade_tecnica",
        "capacidade_economica",
        "garantia_proposta",
        "garantia_contratual",
        "cat_atestado",
        "consorcio",
        "indices_financeiros",
    ):
        if k in extracted:
            requirements.append(f"{k}: {extracted[k][:100]}")
        else:
            requirements.append(f"{k}: não localizado no texto extraído — validar no PDF completo")

    conf = 0.35
    if len(text) > 1500:
        conf += 0.15
    if found_critical:
        conf += min(0.35, 0.08 * len(found_critical))
    if proc.docs_inventory_status.startswith("complete"):
        conf += 0.1
    conf = min(0.92, conf)

    proc.requirements_summary = " | ".join(requirements)[:1800]
    proc.risks_summary = "; ".join(sorted(set(risks)))[:1200] or "riscos a detalhar no deep dive"

    # drop obsolete risk if we actually parsed docs
    if len(text) > 800 and proc.decision:
        proc.decision.risks = [
            r
            for r in proc.decision.risks
            if "documentos_nao_baixados_nem_parseados" not in r
        ]
        if found_critical:
            proc.decision.pending = [
                p
                for p in proc.decision.pending
                if p not in {"analise_documental_completa", "analise_edital_profunda"}
            ]
            proc.decision.pending = sorted(
                set(proc.decision.pending + ["validacao_humana_clausulas_criticas"])
            )
        if missing:
            proc.decision.pending = sorted(
                set(proc.decision.pending + [f"confirmar_{m}" for m in missing[:4]])
            )

    analysis = {
        "process_id": proc.process_id,
        "extracted_fields": extracted,
        "missing_fields": missing,
        "found_critical": found_critical,
        "summary": "\n".join(summary_parts),
        "confidence": round(conf, 3),
        "source": "documentos_oficiais_extraidos"
        if len(text) > 400
        else "metadados_processo",
        "text_chars": len(text),
        "note": (
            "Análise vinculada a trechos extraídos dos documentos oficiais baixados. "
            "Não substitui parecer jurídico/técnico humano."
        ),
    }
    proc._edital_analysis = analysis  # type: ignore[attr-defined]
    return analysis


def apply_minimum_analysis(
    processes: list[CanonicalProcess],
    *,
    all_processes: list[CanonicalProcess] | None = None,
    fetch_contracts: bool = True,
) -> dict[str, Any]:
    results: dict[str, Any] = {
        "edital": [],
        "orgao": [],
        "concorrentes": [],
        "market_intel": {},
    }
    universe = all_processes if all_processes is not None else processes
    # Market intel first so buyer/competitor fields exist before summarizing
    results["market_intel"] = apply_market_intel(
        processes,
        universe,
        fetch_contracts=fetch_contracts,
    )
    for p in processes:
        page_text = (
            getattr(p, "_combined_doc_text", "")
            or getattr(p, "_page_text_sample", "")
            or ""
        )
        ed = analyze_edital_minimo(p, page_text)
        results["edital"].append(ed)
        org = getattr(p, "_org_history", None) or {
            "process_id": p.process_id,
            "analise": p.buyer_analysis,
        }
        results["orgao"].append(org)
        comps = getattr(p, "_competitors", None) or []
        results["concorrentes"].append(
            {
                "process_id": p.process_id,
                "concorrentes": comps,
                "texto": p.competitors_probable,
            }
        )
        if p.decision:
            # Remove analysis placeholders already satisfied
            drop = {
                "analise_documental_completa",
                "analise_edital_profunda",
                "analise_orgao_12_24_36m",
                "concorrentes_provaveis_historicos",
            }
            found = set(ed.get("found_critical") or [])
            for f in found:
                drop.add(f"confirmar_{f}")
            p.decision.pending = sorted(
                (set(p.decision.pending) - drop) | {"validacao_humana_tiago"}
            )
            if p.docs_inventory_status.startswith("complete") and ed.get(
                "found_critical"
            ):
                if "review_bloqueado" not in (p.decision.inclusion_reason or ""):
                    p.decision.inclusion_reason = (
                        p.decision.inclusion_reason
                        or "candidata_aec_com_documentos_e_analise_parcial"
                    )
            # Drop obsolete doc risk when complete
            if str(p.docs_inventory_status).startswith("complete"):
                p.decision.risks = [
                    r
                    for r in p.decision.risks
                    if "documentos_nao_baixados" not in r
                    and "documentos_ainda_nao_inventariados" not in r
                ]
    return results
