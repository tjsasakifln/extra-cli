"""Markdown reports, CSV/JSON, dossiers, run manifest."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.commercial.reajuste_14133 import (
    CALCULABLE_ADJUSTMENT_CLAIM,
    DIAGNOSTIC_OUTREACH_READY,
    DOCUMENT_REQUEST_READY,
    LIKELY_ADJUSTMENT_OPPORTUNITY,
    MODULE_VERSION,
    POTENTIAL_ADJUSTMENT_SIGNAL,
    STATUS_HOT_VERIFIED,
    SUL_UFS,
    VERIFIED_ADJUSTMENT_OPPORTUNITY,
)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def _safe_filename(cnpj: str, contrato_id: str) -> str:
    c = re.sub(r"\D", "", cnpj or "semcnpj")[:14]
    cid = re.sub(r"[^\w.-]+", "_", contrato_id or "semcontrato")[:80]
    return f"{c}_{cid}"


def lead_flat_row(lead: dict[str, Any]) -> dict[str, Any]:
    """Flatten lead for CSV/Excel commercial use."""
    decomp = lead.get("score_decomposition") or {}
    decomp_s = "; ".join(f"{k}={v}" for k, v in decomp.items())
    pen = lead.get("score_penalties") or {}
    pen_s = "; ".join(f"{k}={v}" for k, v in pen.items())
    cont = lead.get("canais_contato") or {}
    return {
        "ranking": lead.get("ranking"),
        "classificacao": lead.get("classificacao"),
        "outreach_status": lead.get("outreach_status"),
        "score_total": lead.get("score_total"),
        "score_decomposition": decomp_s,
        "score_penalties": pen_s,
        "cnpj": lead.get("cnpj"),
        "razao_social": lead.get("razao_social"),
        "nome_fantasia": lead.get("nome_fantasia"),
        "municipio_empresa": lead.get("municipio_empresa"),
        "uf": lead.get("uf"),
        "orgao_contratante": lead.get("orgao_contratante"),
        "orgao_cnpj": lead.get("orgao_cnpj"),
        "contrato_id": lead.get("contrato_id"),
        "objeto": (lead.get("objeto") or "")[:500],
        "classificacao_obra": lead.get("classificacao_obra"),
        "valor_original": lead.get("valor_original"),
        "valor_atualizado": lead.get("valor_atualizado"),
        "saldo_conhecido": lead.get("saldo_conhecido"),
        "regime_legal": lead.get("regime_legal"),
        "regime_proven": lead.get("regime_proven"),
        "data_base": lead.get("data_base"),
        "data_base_status": lead.get("data_base_status"),
        "data_base_source": lead.get("data_base_source"),
        "indice": lead.get("indice"),
        "indice_in_clause": lead.get("indice_in_clause"),
        "data_proximo_reajuste": lead.get("data_proximo_reajuste"),
        "dias_atraso_potencial": lead.get("dias_atraso_potencial"),
        "vigencia_final": lead.get("vigencia_final"),
        "percentual_reajuste": lead.get("percentual_reajuste"),
        "base_potencialmente_reajustavel": lead.get("base_potencialmente_reajustavel"),
        "base_label": lead.get("base_label"),
        "valor_potencial": lead.get("valor_potencial"),
        "teto_teorico": lead.get("teto_teorico"),
        "teto_label": lead.get("teto_label"),
        "status_reajustes_anteriores": lead.get("status_reajustes_anteriores"),
        "document_pipeline_state": lead.get("document_pipeline_state"),
        "evidencias_favoraveis": " | ".join(lead.get("evidencias_favoraveis") or []),
        "lacunas": " | ".join(lead.get("lacunas") or []),
        "riscos": " | ".join(lead.get("riscos") or []),
        "proxima_acao_investigativa": lead.get("proxima_acao_investigativa"),
        "argumento_comercial": lead.get("argumento_comercial"),
        "email_comercial": cont.get("email"),
        "telefone_empresarial": cont.get("telefone"),
        "site_oficial": cont.get("site"),
        "urls_oficiais": " | ".join(lead.get("urls_oficiais") or []),
        "hot_gates_passed": lead.get("hot_gates_passed"),
        "timestamp_analise": lead.get("timestamp_analise"),
    }


FIELD_DICTIONARY: list[tuple[str, str]] = [
    ("ranking", "Posição no ranking comercial (maior score primeiro; desempate determinístico)"),
    ("classificacao", "Status do funil: HOT_VERIFIED, STRONG_CANDIDATE, REVIEW_REQUIRED, etc."),
    ("score_total", "Score 0–100 decomponível (não é probabilidade de conversão)"),
    ("data_base", "Data-base efetiva usada na análise (pode ser proxy de prospecção)"),
    ("data_base_status", "CONFIRMED | PROXY_PROSPECTION_ONLY | MISSING"),
    ("valor_potencial", "Valor potencialmente reclamável só com índice+série+base reajustável"),
    ("teto_teorico", "Teto teórico (UPPER_BOUND_NOT_CLAIM_VALUE) — não é valor devido"),
    ("regime_proven", "True apenas com campo estruturado ou documento oficial"),
    ("indice", "Índice contratual localizado no instrumento — nunca inventado"),
]


def supplier_flat_row(p: dict[str, Any]) -> dict[str, Any]:
    cont = p.get("contatos") or {}
    best = p.get("melhor_oportunidade") or {}
    return {
        "ranking": p.get("ranking"),
        "commercial_stage": p.get("commercial_stage"),
        "outreach_status": p.get("outreach_status"),
        "prioridade_abordagem": p.get("prioridade_abordagem"),
        "score_fornecedor": p.get("score_fornecedor"),
        "opportunity_score": p.get("opportunity_score"),
        "verification_score": p.get("verification_score"),
        "commercial_fit_score": p.get("commercial_fit_score"),
        "priority_score": p.get("priority_score"),
        "motivos_score": " | ".join(p.get("motivos_score") or []),
        "cnpj": p.get("cnpj"),
        "razao_social": p.get("razao_social"),
        "nome_fantasia": p.get("nome_fantasia"),
        "sede_municipio": p.get("sede_municipio"),
        "sede_uf": p.get("sede_uf"),
        "sul_priority": p.get("sul_priority"),
        "cnae": p.get("cnae"),
        "situacao_cadastral": p.get("situacao_cadastral"),
        "porte_cadastral": p.get("porte_cadastral"),
        "qtd_contratos_candidatos": p.get("qtd_contratos_candidatos"),
        "orgaos_contratantes": " | ".join(p.get("orgaos_contratantes") or []),
        "valor_total_portfolio_analisado": p.get("valor_total_portfolio_analisado"),
        "melhor_contrato_id": best.get("contrato_id"),
        "melhor_orgao": best.get("orgao"),
        "melhor_classificacao": best.get("classificacao"),
        "melhor_commercial_stage": best.get("commercial_stage"),
        "sinais_favoraveis": " | ".join(p.get("sinais_favoraveis") or p.get("evidencias") or []),
        "incertezas": " | ".join(p.get("incertezas") or []),
        "documentos_faltantes": " | ".join(p.get("documentos_faltantes") or []),
        "argumento_comercial": p.get("argumento_comercial"),
        "abordagem_permitida": p.get("abordagem_permitida"),
        "linguagem_proibida": p.get("linguagem_proibida"),
        "mensagem_abordagem": p.get("mensagem_abordagem"),
        "proxima_acao": p.get("proxima_acao"),
        "riscos": " | ".join(p.get("riscos") or []),
        "email": cont.get("email"),
        "telefone": cont.get("telefone"),
        "site": cont.get("site"),
        "contato_verificavel": p.get("contato_verificavel"),
        "document_request_ready": p.get("document_request_ready"),
    }


def lead_commercial_flat_row(lead: dict[str, Any]) -> dict[str, Any]:
    cont = lead.get("canais_contato") or {}
    return {
        "ranking": lead.get("ranking"),
        "commercial_stage": lead.get("commercial_stage"),
        "classificacao": lead.get("classificacao"),
        "opportunity_score": lead.get("opportunity_score"),
        "verification_score": lead.get("verification_score"),
        "commercial_fit_score": lead.get("commercial_fit_score"),
        "priority_score": lead.get("priority_score"),
        "cnpj": lead.get("cnpj"),
        "razao_social": lead.get("razao_social"),
        "uf": lead.get("uf"),
        "municipio_empresa": lead.get("municipio_empresa"),
        "orgao_contratante": lead.get("orgao_contratante"),
        "contrato_id": lead.get("contrato_id"),
        "objeto": (lead.get("objeto") or "")[:400],
        "valor_original": lead.get("valor_original"),
        "regime_legal": lead.get("regime_legal"),
        "regime_proven": lead.get("regime_proven"),
        "regime_probable_14133": lead.get("regime_probable_14133"),
        "exact_budget_date": lead.get("exact_budget_date"),
        "proxy_date": lead.get("proxy_date"),
        "proxy_type": lead.get("proxy_type"),
        "minimum_elapsed_confirmed": lead.get("minimum_elapsed_confirmed"),
        "temporal_reasoning": lead.get("temporal_reasoning"),
        "calculation_blocked": lead.get("calculation_blocked"),
        "data_base_status": lead.get("data_base_status"),
        "valor_potencial": lead.get("valor_potencial"),
        "teto_teorico": lead.get("teto_teorico"),
        "document_request_ready": lead.get("document_request_ready"),
        "contact_readiness": lead.get("contact_readiness"),
        "human_review_status": lead.get("human_review_status"),
        "claim_readiness": lead.get("claim_readiness"),
        "email": cont.get("email"),
        "telefone": cont.get("telefone"),
        "site": cont.get("site"),
        "argumento_comercial": lead.get("argumento_comercial"),
        "linguagem_proibida": lead.get("language_prohibited"),
        "proxima_acao": lead.get("outreach_next_action") or lead.get("proxima_acao_investigativa"),
        "sinais_favoraveis": " | ".join(lead.get("evidencias_favoraveis") or []),
        "incertezas": " | ".join(lead.get("uncertainties") or []),
        "documentos_faltantes": " | ".join(lead.get("missing_documents") or []),
    }


def write_csv_json(out_dir: Path, run: dict[str, Any]) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    leads = run.get("top_leads") or run.get("leads") or []
    flat = [lead_flat_row(lead) for lead in leads]

    p_csv = out_dir / "leads_reajuste_14133.csv"
    if flat:
        fields = list(flat[0].keys())
    else:
        fields = ["ranking", "classificacao", "cnpj", "contrato_id"]
    with p_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in flat:
            w.writerow(row)
    paths["csv"] = str(p_csv)

    p_json = out_dir / "leads_reajuste_14133.json"
    _write_json(p_json, {
        "run_id": run.get("run_id"),
        "as_of": run.get("as_of"),
        "module_version": MODULE_VERSION,
        "leads": leads,
        "funnel": run.get("funnel"),
        "metrics": run.get("metrics"),
        "language_policy": run.get("language_policy"),
    })
    paths["json"] = str(p_json)

    p_ex = out_dir / "excluded_reasons.csv"
    excl = run.get("excluded") or []
    with p_ex.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["contrato_id", "cnpj", "reason", "detail"])
        w.writeheader()
        for e in excl:
            w.writerow({
                "contrato_id": e.get("contrato_id"),
                "cnpj": e.get("cnpj"),
                "reason": e.get("reason"),
                "detail": json.dumps(e.get("detail"), ensure_ascii=False, default=str) if e.get("detail") else "",
            })
    paths["excluded_csv"] = str(p_ex)

    p_man = out_dir / "run_manifest.json"
    manifest = {
        k: run.get(k)
        for k in (
            "run_id", "as_of", "module_version", "campaign", "git_sha",
            "source_mode", "source_dsn_masked", "started_at", "finished_at",
            "params", "funnel", "metrics", "language_policy",
            "terminal_status", "distributions",
        )
    }
    _write_json(p_man, manifest)
    paths["manifest"] = str(p_man)
    return paths


def write_v2_deliverables(out_dir: Path, run: dict[str, Any]) -> dict[str, str]:
    """Supplier-level commercial artifacts required by v2 campaign."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    portfolios = run.get("supplier_portfolios") or []
    all_contracts = run.get("leads") or []

    # Supplier CSV / XLSX companion
    sflat = [supplier_flat_row(p) for p in portfolios]
    p_sup_csv = out_dir / "leads_fornecedores_reajuste_14133.csv"
    fields = list(sflat[0].keys()) if sflat else ["ranking", "cnpj", "outreach_status"]
    with p_sup_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in sflat:
            w.writerow(row)
    paths["suppliers_csv"] = str(p_sup_csv)

    # Contract-level full
    cflat = [lead_flat_row(c) for c in all_contracts]
    p_c_csv = out_dir / "contratos_analisados.csv"
    cfields = list(cflat[0].keys()) if cflat else ["contrato_id", "cnpj"]
    with p_c_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cfields)
        w.writeheader()
        for row in cflat:
            w.writerow(row)
    paths["contratos_csv"] = str(p_c_csv)
    p_c_json = out_dir / "contratos_analisados.json"
    _write_json(p_c_json, {"run_id": run.get("run_id"), "contratos": all_contracts})
    paths["contratos_json"] = str(p_c_json)

    def _write_status_csv(name: str, status: str) -> str:
        rows = [supplier_flat_row(p) for p in portfolios if p.get("outreach_status") == status]
        path = out_dir / name
        flds = list(rows[0].keys()) if rows else fields
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=flds)
            w.writeheader()
            for row in rows:
                w.writerow(row)
        return str(path)

    paths["outreach_ready_csv"] = _write_status_csv(
        "outreach_ready.csv", "OUTREACH_READY"
    )
    # include WITHOUT_VALUE in same file as separate rows + dedicated file
    ready_wo = [
        supplier_flat_row(p)
        for p in portfolios
        if p.get("outreach_status")
        in {"OUTREACH_READY", "OUTREACH_READY_WITHOUT_VALUE_ESTIMATE"}
        or p.get("commercial_stage")
        in {DIAGNOSTIC_OUTREACH_READY, VERIFIED_ADJUSTMENT_OPPORTUNITY, CALCULABLE_ADJUSTMENT_CLAIM}
    ]
    p_ready = out_dir / "outreach_ready.csv"
    with p_ready.open("w", encoding="utf-8", newline="") as f:
        flds = list(ready_wo[0].keys()) if ready_wo else fields
        w = csv.DictWriter(f, fieldnames=flds)
        w.writeheader()
        for row in ready_wo:
            w.writerow(row)
    paths["outreach_ready_csv"] = str(p_ready)

    paths["document_request_csv"] = _write_status_csv(
        "document_request_candidates.csv", "DOCUMENT_REQUEST_CANDIDATE"
    )
    paths["not_ready_csv"] = _write_status_csv(
        "not_ready_for_outreach.csv", "NOT_READY_FOR_OUTREACH"
    )

    # --- v3 commercial stage products ---
    stage_files = {
        "potential_adjustment_signals.csv": POTENTIAL_ADJUSTMENT_SIGNAL,
        "likely_adjustment_opportunities.csv": LIKELY_ADJUSTMENT_OPPORTUNITY,
        "diagnostic_outreach_ready.csv": DIAGNOSTIC_OUTREACH_READY,
        "document_request_ready.csv": DOCUMENT_REQUEST_READY,
        "verified_adjustment_opportunities.csv": VERIFIED_ADJUSTMENT_OPPORTUNITY,
        "calculable_adjustment_claims.csv": CALCULABLE_ADJUSTMENT_CLAIM,
    }
    for fname, stage in stage_files.items():
        if stage == DOCUMENT_REQUEST_READY:
            rows = [
                lead_commercial_flat_row(c)
                for c in all_contracts
                if c.get("commercial_stage") == stage
                or c.get("document_request_ready")
                or c.get("commercial_stage")
                in {LIKELY_ADJUSTMENT_OPPORTUNITY, DIAGNOSTIC_OUTREACH_READY}
            ]
        elif stage == LIKELY_ADJUSTMENT_OPPORTUNITY:
            # Include DIAGNOSTIC as superset of LIKELY for opportunity list
            rows = [
                lead_commercial_flat_row(c)
                for c in all_contracts
                if c.get("commercial_stage")
                in {LIKELY_ADJUSTMENT_OPPORTUNITY, DIAGNOSTIC_OUTREACH_READY}
            ]
        else:
            rows = [
                lead_commercial_flat_row(c)
                for c in all_contracts
                if c.get("commercial_stage") == stage
            ]
        path = out_dir / fname
        flds = list(rows[0].keys()) if rows else list(lead_commercial_flat_row({}).keys())
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=flds)
            w.writeheader()
            for row in rows:
                w.writerow(row)
        paths[fname] = str(path)

    # Supplier priority queue (all commercial stages, missing contact OK)
    priority_portfolios = [
        p
        for p in portfolios
        if p.get("commercial_stage")
        in {
            POTENTIAL_ADJUSTMENT_SIGNAL,
            LIKELY_ADJUSTMENT_OPPORTUNITY,
            DIAGNOSTIC_OUTREACH_READY,
            DOCUMENT_REQUEST_READY,
            VERIFIED_ADJUSTMENT_OPPORTUNITY,
            CALCULABLE_ADJUSTMENT_CLAIM,
        }
    ]
    p_pri = out_dir / "supplier_priority_queue.csv"
    pri_rows = [supplier_flat_row(p) for p in priority_portfolios]
    with p_pri.open("w", encoding="utf-8", newline="") as f:
        flds = list(pri_rows[0].keys()) if pri_rows else fields
        w = csv.DictWriter(f, fieldnames=flds)
        w.writeheader()
        for row in pri_rows:
            w.writerow(row)
    paths["supplier_priority_queue.csv"] = str(p_pri)

    # Top 30 Sul + Top 100 nacional manual review packs (automated_review_queue)
    sul_port = [
        p
        for p in portfolios
        if p.get("sul_priority")
        or (p.get("sede_uf") or "").upper() in SUL_UFS
        or any(u in SUL_UFS for u in (p.get("ufs_execucao") or []))
    ][:30]
    nac_port = portfolios[:100]
    paths["top30_sul_manual_review.md"] = str(
        _write_manual_review_md(
            out_dir / "top30_sul_manual_review.md",
            sul_port,
            title="Top 30 Sul — automated review queue (NOT human_review_completed)",
        )
    )
    paths["top100_nacional_manual_review.md"] = str(
        _write_manual_review_md(
            out_dir / "top100_nacional_manual_review.md",
            nac_port,
            title="Top 100 Nacional — automated review queue (NOT human_review_completed)",
        )
    )
    # automated_review_queue naming (never human_review_completed)
    auto_q = {
        "kind": "automated_review_queue",
        "human_review_completed": False,
        "note": "Machine-ranked queue for human desk work. Never sets human_review_completed.",
        "top30_sul": sul_port,
        "top100_nacional": nac_port,
        "run_id": run.get("run_id"),
        "git_sha": run.get("git_sha"),
    }
    p_auto = out_dir / "automated_review_queue.json"
    _write_json(p_auto, auto_q)
    paths["automated_review_queue.json"] = str(p_auto)
    # human_review_pending marker (import path only completes)
    p_pending = out_dir / "human_review_pending.json"
    _write_json(
        p_pending,
        {
            "kind": "human_review_pending",
            "human_review_completed": False,
            "n_awaiting": len(sul_port) + len(nac_port),
            "import_via": "--human-review-file",
        },
    )
    paths["human_review_pending.json"] = str(p_pending)

    p_port = out_dir / "supplier_portfolios.json"
    _write_json(
        p_port,
        {
            "run_id": run.get("run_id"),
            "as_of": run.get("as_of"),
            "git_sha": run.get("git_sha"),
            "n": len(portfolios),
            "portfolios": portfolios,
        },
    )
    paths["supplier_portfolios_json"] = str(p_port)

    # Evidence JSONL
    p_doc_ev = out_dir / "document_evidence.jsonl"
    with p_doc_ev.open("w", encoding="utf-8") as f:
        for lead in all_contracts:
            scan = lead.get("doc_scan") or {}
            for ev in scan.get("evidences") or []:
                f.write(
                    json.dumps(
                        {
                            "contrato_id": lead.get("contrato_id"),
                            "cnpj": lead.get("cnpj"),
                            "pipeline_state": lead.get("document_pipeline_state"),
                            **(ev if isinstance(ev, dict) else {}),
                        },
                        ensure_ascii=False,
                        default=str,
                    )
                    + "\n"
                )
    paths["document_evidence_jsonl"] = str(p_doc_ev)

    p_calc = out_dir / "calculation_evidence.jsonl"
    with p_calc.open("w", encoding="utf-8") as f:
        for lead in all_contracts:
            fin = lead.get("finance") or {}
            if not fin:
                continue
            f.write(
                json.dumps(
                    {
                        "contrato_id": lead.get("contrato_id"),
                        "cnpj": lead.get("cnpj"),
                        "indice": lead.get("indice"),
                        "indice_in_clause": lead.get("indice_in_clause"),
                        "valor_potencial": lead.get("valor_potencial"),
                        "teto_teorico": lead.get("teto_teorico"),
                        "value_quality_status": lead.get("value_quality_status"),
                        "finance": fin,
                    },
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )
    paths["calculation_evidence_jsonl"] = str(p_calc)

    # AI-assisted evidence review only — NEVER dual-write human_review_* filenames
    ai_md = out_dir / "ai_assisted_evidence_review_top30.md"
    ai_json = out_dir / "ai_assisted_evidence_review_top30.json"
    if not ai_json.exists():
        top30 = portfolios[:30]
        reviews = []
        sector_fps = 0
        for p in top30:
            best = p.get("melhor_oportunidade") or {}
            obj = (best.get("objeto") or p.get("objeto") or "").lower()
            name = (p.get("razao_social") or "").lower()
            fp_flags: list[str] = []
            if any(x in obj for x in ("software", "licenciamento", "sistema de gestão", "sistema de gestao")):
                fp_flags.append("software")
            if any(x in obj for x in ("locação de veículo", "locacao de veiculo", "veículos especiais", "veiculos especiais")):
                fp_flags.append("vehicle_rental")
            if any(x in obj for x in ("medicamento", "lisdexanfetamina", "farmac")):
                fp_flags.append("pharma")
            if "localiza" in name and "veic" in (obj + name):
                fp_flags.append("localiza_vehicle")
            if "betha" in name:
                fp_flags.append("betha_software")
            if fp_flags:
                sector_fps += 1
            reviews.append(
                {
                    "fornecedor": p.get("razao_social"),
                    "cnpj": p.get("cnpj"),
                    "contratos_consolidados": p.get("qtd_contratos_candidatos"),
                    "documentos_efetivamente_lidos": [],
                    "paginas": [],
                    "clausulas": [],
                    "regime": best.get("regime_legal"),
                    "data_base": best.get("data_base_status"),
                    "indice": best.get("indice"),
                    "document_link_status": best.get("document_link_status"),
                    "historico_reajuste": None,
                    "situacao_execucao": None,
                    "qualidade_valor": None,
                    "contato": p.get("contatos"),
                    "decisao": "AI_ASSISTED_EVIDENCE_REVIEW",
                    "motivo": (
                        "Revisão adversarial assistida por IA sobre objeto/CNAE/documentos. "
                        "NÃO é revisão humana. Importar via --human-review-file para completed."
                    ),
                    "sector_false_positive_flags": fp_flags,
                    "risco": "Nao usar como human_review_completed",
                    "linguagem_permitida": "none",
                    "proxima_acao": p.get("proxima_acao"),
                    "outreach_status": p.get("outreach_status"),
                }
            )
        payload = {
            "kind": "ai_assisted_evidence_review",
            "human_review_completed": False,
            "note": (
                "AI_ASSISTED — not human documentary review. "
                "Never dual-writes human_review_* filenames. "
                "human_review_completed only via --human-review-file."
            ),
            "n": len(reviews),
            "sector_false_positives_in_top30": sector_fps,
            "top20_unequivocal_sector_fp": sector_fps if sector_fps else 0,
            "reviews": reviews,
            "run_id": run.get("run_id"),
            "git_sha": run.get("git_sha"),
        }
        _write_json(ai_json, payload)
        lines = [
            "# AI-assisted evidence review — Top 30 suppliers",
            "",
            "> **NÃO é revisão humana.** Não grava human_review_* (OBJECTIVE v3).",
            "> Completar revisão via `--human-review-file`.",
            "",
            f"- sector_false_positive flags in top30: **{sector_fps}**",
            "",
        ]
        for r in reviews:
            lines.append(f"## {r.get('fornecedor')} (`{r.get('cnpj')}`)")
            lines.append(f"- contratos: {r.get('contratos_consolidados')}")
            lines.append(f"- decisão: {r.get('decisao')}")
            lines.append(f"- flags setoriais: {r.get('sector_false_positive_flags')}")
            lines.append(f"- motivo: {r.get('motivo')}")
            lines.append("")
        ai_md.write_text("\n".join(lines), encoding="utf-8")
    paths["ai_assisted_evidence_review_md"] = str(ai_md)
    paths["ai_assisted_evidence_review_json"] = str(ai_json)
    # Explicit: no human_review_md / human_review_json paths for auto artifacts

    return paths


def _write_manual_review_md(path: Path, portfolios: list[dict[str, Any]], *, title: str) -> Path:
    lines = [
        f"# {title}",
        "",
        "> **automated_review_queue / human_review_pending** — NÃO é `human_review_completed`.",
        "> Importar decisões via `--human-review-file`. Nenhuma rotina automática marca revisão humana concluída.",
        "",
    ]
    for i, p in enumerate(portfolios, start=1):
        best = p.get("melhor_oportunidade") or {}
        lines.append(f"## {i}. {p.get('razao_social')} (`{p.get('cnpj')}`)")
        lines.append(f"- sede: {p.get('sede_municipio')}/{p.get('sede_uf')}")
        lines.append(f"- commercial_stage: **{p.get('commercial_stage')}**")
        lines.append(f"- contratos candidatos: {p.get('qtd_contratos_candidatos')}")
        lines.append(f"- órgãos: {', '.join(p.get('orgaos_contratantes') or [])}")
        lines.append(
            f"- scores: priority={p.get('priority_score')} opportunity={p.get('opportunity_score')} "
            f"verification={p.get('verification_score')} fit={p.get('commercial_fit_score')}"
        )
        lines.append(f"- motivos: {', '.join(p.get('motivos_score') or [])}")
        lines.append(f"- melhor contrato: {best.get('contrato_id')} — {best.get('orgao')}")
        lines.append(f"- sinais: {'; '.join((p.get('sinais_favoraveis') or [])[:5])}")
        lines.append(f"- incertezas: {'; '.join((p.get('incertezas') or [])[:5])}")
        lines.append(f"- docs faltantes: {'; '.join((p.get('documentos_faltantes') or [])[:6])}")
        cont = p.get("contatos") or {}
        lines.append(
            f"- contato: email={cont.get('email')} tel={cont.get('telefone')} site={cont.get('site')}"
        )
        lines.append(f"- abordagem permitida: {(p.get('abordagem_permitida') or '')[:300]}")
        lines.append(f"- linguagem proibida: {(p.get('linguagem_proibida') or '')[:200]}")
        lines.append(f"- próxima ação: {p.get('proxima_acao')}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_methodology(out_dir: Path) -> Path:
    text = f"""# Metodologia — Reajuste em sentido estrito (Lei nº 14.133/2021)

**Módulo:** `{MODULE_VERSION}`
**Unidade comercial:** fornecedor (CNPJ) com contratos vinculados
**Campanha:** reajuste periódico por índice contratual
**NÃO cobre:** reequilíbrio econômico-financeiro, repactuação de mão de obra, atualização monetária por atraso de pagamento, aditivo quantitativo.

## Fundamento jurídico mínimo

- Lei nº 14.133/2021, art. 6º, LVIII (reajustamento)
- art. 25, § 7º (índice e data-base do orçamento estimado)
- art. 92, V e § 3º (cláusulas necessárias)
- art. 123 e art. 136, I (apostila)
- Lei nº 10.192/2001 (periodicidade mínima anual)

## Premissa temporal conservadora (v3)

Para obras regidas ou **provavelmente** regidas pela Lei 14.133/2021:

1. A data-base do reajuste vincula-se à data do **orçamento estimado**.
2. O orçamento estimado **necessariamente antecede** a contratação/assinatura.
3. Se a assinatura ocorreu há **mais de doze meses**, o primeiro interregno anual já
   transcorreu de forma **conservadora** (`minimum_interregnum_elapsed=true`),
   mesmo sem data-base exata.
4. A ausência da data-base exata **bloqueia cálculo e afirmação conclusiva**, mas
   **não** impede classificar o contrato como `LIKELY_ADJUSTMENT_OPPORTUNITY`
   nem autorizar abordagem **diagnóstica**.
5. Proxy (publicação/início) **nunca** é apresentado como data-base legal.
6. Ausência de apostila = **incerteza**, não prova positiva nem exclusão automática.
7. Ausência de contato bloqueia só `DIAGNOSTIC_OUTREACH_READY`, não a fila de leads.

## Estados comerciais (v3)

| Estado | Significado |
|--------|-------------|
| POTENTIAL_ADJUSTMENT_SIGNAL | Sinais mínimos de maturidade anual em obra |
| LIKELY_ADJUSTMENT_OPPORTUNITY | Oportunidade provável (sem exigir data-base/índice/contato/humano) |
| DIAGNOSTIC_OUTREACH_READY | Abordagem diagnóstica prudente (exige contato verificável) |
| DOCUMENT_REQUEST_READY | Ação comercial válida: pedir documentos (pode coexistir) |
| VERIFIED_ADJUSTMENT_OPPORTUNITY | Pack documental + revisão humana; ainda sem valor |
| CALCULABLE_ADJUSTMENT_CLAIM | Único estado com `valor_potencial` |

## Dimensões independentes

`signal_status`, `legal_confidence`, `temporal_confidence`, `documentary_confidence`,
`execution_confidence`, `adjustment_history_confidence`, `contact_readiness`,
`human_review_status`, `commercial_action`, `claim_readiness`.

## Hierarquia temporal A–D

| Nível | Evidência | Cálculo | Diagnóstico |
|-------|-----------|---------|-------------|
| A | Data-base exata do orçamento | se interregno OK | sim |
| B | Assinatura &gt; 12 meses | bloqueado | sim |
| C | Proxy (publicação/início) antigo | bloqueado | não (menor confiança) |
| D | Insuficiente | bloqueado | não |

## Pipeline em duas fases

1. **Triagem nacional barata** — dados estruturados; consolidação por fornecedor.
2. **Aprofundamento orientado a valor** — documentos e contatos só dos prioritários
   (Sul/SC, ICP, valor, idade &gt;12m, multi-contrato, não-gigante).

## Scoring v3

| Score | O que mede |
|-------|------------|
| opportunity_score | Probabilidade de dor comercial relevante |
| verification_score | Qualidade das evidências |
| commercial_fit_score | Aderência ICP CONFENGE |
| priority_score | Ordenação do trabalho humano |

Falta de documento ↓ verification, **não** zera opportunity.
Falta de contato ↓ contact_readiness, **não** remove da fila.

## Fail-closed (apenas claims)

- Somente `CALCULABLE_ADJUSTMENT_CLAIM` pode exibir `valor_potencial`.
- Nenhuma mensagem afirma crédito devido sem verificação documental + revisão humana.
- `human_review_completed` só via `--human-review-file` (nunca automático).

## Premissas operacionais legadas (ainda válidas)

1. Data-base legal = **orçamento estimado** (CONFIRMED). Assinatura/publicação/OS são proxy.
2. Índice só se semanticamente vinculado à **cláusula de reajuste**.
3. PDF binário ≠ texto extraído ≠ gate documental de claim.
4. Varredura integral keyset; sem limite silencioso de 25k.
5. Ferramenta **qualifica**; não envia mensagens automaticamente.

## Gates de claim (legado, fail-closed)

| Status | Significado |
|--------|-------------|
| OUTREACH_READY | Pack claim completo + humano + valor |
| OUTREACH_READY_WITHOUT_VALUE_ESTIMATE | Pack claim sem cifra |
| TECHNICALLY_VERIFIED_PENDING_TIAGO | Técnico completo, aguarda humano |
| DOCUMENT_REQUEST_CANDIDATE | Legado; preferir estados v3 |

## Funil jurídico/documental

| Status | Significado |
|--------|-------------|
| HOT_VERIFIED | 10 gates documentais |
| STRONG_CANDIDATE / REVIEW_REQUIRED / RESEARCH_REQUIRED | Lacunas |
| LEGAL_REGIME_UNKNOWN / LEGAL_REGIME_CONFLICT | Regime não comprovado / contraditório |
| ALREADY_ADJUSTED / CLOSED / NOT_ELIGIBLE | Fora do claim aberto |

## Scoring

Pesos v1 mantidos; atratividade financeira zera se valor não validado/outlier.

## Limitações honestas

- PNCP estruturado sem data-base/índice/regime nativos.
- HTML do portal raramente contém cláusula integral.
- Séries oficiais de índice exigem fonte externa licenciada (não inventar).
- `NO_PRIOR_ADJUSTMENT_LOCATED` ≠ prova de inexistência de reajuste.
"""
    p = out_dir / "methodology.md"
    p.write_text(text, encoding="utf-8")
    return p


def write_data_quality(out_dir: Path, run: dict[str, Any]) -> Path:
    funnel = run.get("funnel") or {}
    metrics = run.get("metrics") or {}
    excl = run.get("excluded") or []
    reasons = Counter(str(e.get("reason") or "unknown") for e in excl)
    top_reasons = reasons.most_common(20)
    lines = [
        "# Data Quality Report — reajuste_14133",
        "",
        f"- run_id: `{run.get('run_id')}`",
        f"- as_of: `{run.get('as_of')}`",
        f"- source_mode: `{run.get('source_mode')}`",
        f"- source (masked): `{run.get('source_dsn_masked')}`",
        "",
        "## Funil",
        "",
    ]
    for k, v in funnel.items():
        lines.append(f"- **{k}**: {v}")
    lines += ["", "## Métricas", ""]
    for k, v in metrics.items():
        lines.append(f"- **{k}**: {v}")
    lines += ["", "## Principais exclusões", ""]
    for reason, n in top_reasons:
        lines.append(f"- `{reason}`: {n}")
    lines += [
        "",
        "## Gaps estruturais do datalake",
        "",
        "- Sem coluna nativa de data do orçamento estimado em `pncp_supplier_contracts`.",
        "- Sem coluna nativa de índice contratual ou regime legal estruturado.",
        "- Document harvest (`process_documents`) pode estar vazio → HOT_VERIFIED raro/zero é esperado (fail-closed).",
        "- Proxy de data-base (assinatura/início/publicação) só para prospecção.",
        "",
        "## Política de linguagem",
        "",
        json.dumps(run.get("language_policy") or {}, ensure_ascii=False, indent=2),
        "",
    ]
    p = out_dir / "data_quality_report.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def write_executive_brief(out_dir: Path, run: dict[str, Any], manual_review: list[dict[str, Any]] | None = None) -> Path:
    funnel = run.get("funnel") or {}
    metrics = run.get("metrics") or {}
    top = run.get("top_leads") or []
    lines = [
        "# Executive Brief — Fila comercial reajuste 14.133/2021 (CONFENGE)",
        "",
        f"**Data de referência (as-of):** {run.get('as_of')}  ",
        f"**Run:** `{run.get('run_id')}`  ",
        f"**Fonte (masked):** `{run.get('source_dsn_masked')}` ({run.get('source_mode')})",
        "",
        "## O que é esta fila",
        "",
        "Fila auditável de contratos públicos de **construção civil** com indícios de",
        "**reajuste periódico por índice** (sentido estrito), para oferta de:",
        "",
        "> Diagnóstico de elegibilidade, recuperação documental, memória de cálculo,",
        "> apuração de valores potencialmente devidos e estruturação técnica do pedido",
        "> administrativo de reajuste contratual.",
        "",
        "**Não é** parecer jurídico. **Não afirma** direito a valor sem prova documental.",
        "",
        "## Funil (contagens)",
        "",
        "| Etapa | N |",
        "|-------|---|",
        f"| Examinados (pré-filtro SQL) | {funnel.get('examined_raw', 0)} |",
        f"| Após dedupe | {funnel.get('after_dedupe', 0)} |",
        f"| Fornecedor privado | {funnel.get('private_supplier', 0)} |",
        f"| Objeto construção | {funnel.get('construction', 0)} |",
        f"| Regime 14.133 comprovado | {funnel.get('regime_14133_proven', 0)} |",
        f"| Temporalmente maduros | {funnel.get('temporally_mature', 0)} |",
        f"| Data-base confirmada | {funnel.get('data_base_confirmed', 0)} |",
        f"| Índice localizado | {funnel.get('index_located', 0)} |",
        f"| Já reajustados (evidência) | {funnel.get('already_adjusted', 0)} |",
        f"| HOT_VERIFIED | {funnel.get(STATUS_HOT_VERIFIED, 0)} |",
        f"| STRONG_CANDIDATE | {funnel.get('STRONG_CANDIDATE', 0)} |",
        f"| REVIEW_REQUIRED | {funnel.get('REVIEW_REQUIRED', 0)} |",
        f"| LEGAL_REGIME_UNKNOWN | {funnel.get('LEGAL_REGIME_UNKNOWN', 0)} |",
        "",
        f"- Valor potencial agregado (top): **R$ {metrics.get('valor_potencial_agregado_top', 0):,.2f}**",
        f"- Teto teórico agregado (top, não claim): **R$ {metrics.get('teto_teorico_agregado_top', 0):,.2f}**",
        "",
        "## Top 10 leads (sem PII pessoal)",
        "",
    ]
    for lead in top[:10]:
        lines.append(
            f"- **#{lead.get('ranking')}** {lead.get('classificacao')} score={lead.get('score_total')} "
            f"UF={lead.get('uf')} valor≈R$ {float(lead.get('valor_atualizado') or 0):,.0f} "
            f"CNPJ=`{str(lead.get('cnpj') or '')[:8]}****` "
            f"contrato=`{lead.get('contrato_id')}` "
            f"data_base_status={lead.get('data_base_status')}"
        )
    lines += ["", "## Human desk review top-30", ""]
    lines.append(
        "Fonte canônica: `human_desk_review_top30.md` / `.json` (notas humanas por lead). "
        "`automated_object_triage.json` é **máquina** e não conta como revisão humana."
    )
    lines.append("")
    if manual_review:
        for item in manual_review[:30]:
            lines.append(
                f"- `#{item.get('rank', '?')}` contrato `{item.get('contrato_id')}`: "
                f"**{item.get('decision')}** "
                f"(FP={item.get('false_positive')}; incerteza={item.get('uncertainty')}; "
                f"doc={item.get('document_consulted')})"
            )
        metrics = run.get("metrics") or {}
        if metrics.get("human_desk_review_keep_rate") is not None:
            lines.append("")
            lines.append(
                f"- Mantidos na fila: {metrics.get('human_desk_review_kept_in_queue')} / "
                f"{metrics.get('human_desk_review_count')} "
                f"(keep_rate={metrics.get('human_desk_review_keep_rate')}; "
                f"FP objeto={metrics.get('human_desk_review_false_positives')})"
            )
    else:
        lines.append(
            "_Sem `human_desk_review_top30.json` neste diretório — "
            "apenas triagem automática se `--manual-review` foi usado._"
        )
    lines += [
        "",
        "## Próximo passo CONFENGE",
        "",
        "1. Priorizar `STRONG_CANDIDATE` e `REVIEW_REQUIRED` com maior score no Sul/SC.",
        "2. Solicitar à construtora: contrato, planilha orçamentária (data-base), apostilas, medições.",
        "3. Só então montar memória de cálculo e minuta de pedido administrativo.",
        "",
    ]
    p = out_dir / "executive_brief.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def build_dossier_md(lead: dict[str, Any]) -> str:
    """13-section commercial dossier (non-claim language)."""
    cnpj = lead.get("cnpj")
    cid = lead.get("contrato_id")
    sections = []
    sections.append(f"# Dossier reajuste 14.133 — {lead.get('razao_social')}")
    sections.append("")
    sections.append(f"- CNPJ: `{cnpj}`")
    sections.append(f"- Contrato: `{cid}`")
    sections.append(f"- Classificação: **{lead.get('classificacao')}** | Score: **{lead.get('score_total')}**")
    sections.append(f"- Ranking: #{lead.get('ranking')} ({lead.get('ranking_bucket')})")
    sections.append("")
    sections.append("## 1. Resumo executivo")
    sections.append("")
    sections.append(
        f"Contrato com órgão **{lead.get('orgao_contratante')}** (UF {lead.get('uf')}), "
        f"objeto classificado como **{lead.get('classificacao_obra')}**, "
        f"valor observado ≈ R$ {float(lead.get('valor_atualizado') or 0):,.2f}. "
        f"Status de data-base: **{lead.get('data_base_status')}**. "
        "Identificamos indícios documentais de que o contrato pode possuir reajuste periódico "
        "ainda não localizado nas publicações consultadas. A confirmação depende da análise do "
        "contrato, das medições e das apostilas emitidas."
    )
    sections.append("")
    sections.append("## 2. Por que o contrato entrou no radar")
    sections.append("")
    for e in lead.get("evidencias_favoraveis") or []:
        sections.append(f"- {e}")
    sections.append("")
    sections.append("## 3. Linha do tempo")
    sections.append("")
    d = lead.get("dates") or {}
    for key in (
        "orcamento_estimado", "data_assinatura", "data_publicacao",
        "inicio_vigencia", "fim_vigencia", "ultimo_reajuste", "data_base_effective",
    ):
        field = d.get(key) or {}
        sections.append(
            f"- **{key}**: {field.get('value')} (fonte={field.get('source')}, conf={field.get('confidence')})"
        )
    sections.append(
        f"- Próximo aniversário: {lead.get('data_proximo_reajuste')} | "
        f"Dias desde aplicável: {lead.get('dias_atraso_potencial')}"
    )
    sections.append("")
    sections.append("## 4. Fundamento jurídico aplicável")
    sections.append("")
    sections.append(
        "Reajuste em sentido estrito (Lei 14.133/2021 arts. 6º LVIII, 25 §7º, 92 V e §3º, "
        "123, 136 I; Lei 10.192/2001 — anualidade). "
        f"Regime classificado: `{lead.get('regime_legal')}` "
        f"(comprovado={lead.get('regime_proven')}). {lead.get('regime_notes') or ''}"
    )
    sections.append("")
    sections.append("## 5. Cláusula e índice encontrados")
    sections.append("")
    sections.append(f"- Índice: `{lead.get('indice') or 'NÃO LOCALIZADO'}`")
    sections.append(f"- Data-base: `{lead.get('data_base')}` status=`{lead.get('data_base_status')}`")
    sections.append("- Sem invenção de cláusula: ausência ⇒ lacuna documental.")
    sections.append("")
    sections.append("## 6. Cálculo preliminar")
    sections.append("")
    fin = lead.get("finance") or {}
    sections.append(f"- Base: {lead.get('base_label')} = {lead.get('base_potencialmente_reajustavel')}")
    sections.append(f"- Percentual: {lead.get('percentual_reajuste')}")
    sections.append(f"- Valor potencial: {lead.get('valor_potencial')} (só se índice+série+base)")
    sections.append(f"- Teto teórico: {lead.get('teto_teorico')} ({lead.get('teto_label')})")
    sections.append(f"- Limitações: {', '.join(fin.get('limitations') or lead.get('riscos') or [])}")
    sections.append("")
    sections.append("## 7. Evidências oficiais")
    sections.append("")
    for u in lead.get("urls_oficiais") or []:
        sections.append(f"- {u}")
    doc = lead.get("doc_scan") or {}
    for e in (doc.get("evidences") or [])[:15]:
        sections.append(
            f"- [{e.get('doc_type')}] {e.get('field_found')}: {e.get('excerpt', '')[:200]} "
            f"(conf={e.get('confidence')}, método={e.get('extraction_method')})"
        )
    sections.append("")
    sections.append("## 8. Lacunas documentais")
    sections.append("")
    for g in lead.get("lacunas") or ["Nenhuma registrada"]:
        sections.append(f"- {g}")
    sections.append("")
    sections.append("## 9. Riscos e fatores que podem afastar o reajuste")
    sections.append("")
    for r in lead.get("riscos") or []:
        sections.append(f"- {r}")
    sections.append("- Reajuste já concedido por apostila não publicada no PNCP.")
    sections.append("- Contrato sem cláusula de reajuste (inconsistência a sanar, não a inventar).")
    sections.append("")
    sections.append("## 10. Documentos a solicitar à construtora")
    sections.append("")
    for dname in (
        "Edital e anexos (planilha orçamentária / data-base)",
        "Contrato integral e aditivos",
        "Apostilas de reajuste (se houver)",
        "Medições e cronograma físico-financeiro",
        "Ordem de serviço e prorrogações",
        "Comprovantes de pagamento / empenhos relevantes",
    ):
        sections.append(f"- {dname}")
    sections.append("")
    sections.append("## 11. Estratégia recomendada de abordagem")
    sections.append("")
    sections.append(
        "Contato empresarial com foco em **diagnóstico de elegibilidade** e organização documental. "
        "Não prometer valor. Oferecer trilha: diagnóstico → memória de cálculo → pedido administrativo."
    )
    sections.append("")
    sections.append("## 12. Frase personalizada de abertura comercial")
    sections.append("")
    sections.append(f"> {lead.get('argumento_comercial')}")
    sections.append("")
    sections.append("## 13. Próximo passo da CONFENGE")
    sections.append("")
    sections.append(lead.get("proxima_acao_investigativa") or "Revisão humana documental.")
    sections.append("")
    sections.append(f"_Gerado em {lead.get('timestamp_analise')} · módulo {lead.get('module_version')}_")
    return "\n".join(sections)


def write_dossiers(out_dir: Path, leads: list[dict[str, Any]], *, n: int = 30) -> list[str]:
    ddir = out_dir / "dossiers"
    ddir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for lead in leads[:n]:
        name = _safe_filename(str(lead.get("cnpj") or ""), str(lead.get("contrato_id") or ""))
        p = ddir / f"{name}.md"
        p.write_text(build_dossier_md(lead), encoding="utf-8")
        paths.append(str(p))
    return paths


def assert_no_secrets(out_dir: Path) -> list[str]:
    """Scan artifacts for credential-like strings (ignore already-masked DSNs)."""
    bad: list[str] = []
    # Real password in DSN (not *** mask)
    dsn_secret = re.compile(r"postgresql://[^:/@]+:(?!\*\*\*)[^@\s]+@")
    patterns = [
        dsn_secret,
        re.compile(r"password\s*=\s*(?!\*+)(\S+)", re.I),
        re.compile(r"-----BEGIN (RSA |OPENSSH )?PRIVATE KEY-----"),
    ]
    for p in out_dir.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() in {".xlsx", ".png", ".jpg", ".pdf"}:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pat in patterns:
            if pat.search(text):
                bad.append(str(p))
                break
    return bad
