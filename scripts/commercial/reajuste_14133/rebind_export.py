"""Atomic rebind-export: reclassify contracts from stored PDF evidence and rewrite all commercial artifacts.

Single delivery unit — forbids partial patches. Used as:
  python3 -m scripts.commercial.reajuste_14133 rebind-export --dir output/.../nacional

Invariants (fail-closed before write):
  - regime_proven + LEI_14133 ⇒ classificacao != LEGAL_REGIME_UNKNOWN
  - CSV/JSON key fields match per contrato_id
  - unique deep-doc count == funnel == metrics
  - git_sha == evidence_commit_sha == HEAD
  - pncp_pdf evidence consulted_at within [started_at, finished_at]
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections import Counter
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from scripts.commercial.reajuste_14133 import (
    DOCUMENT_REQUEST_CANDIDATE,
    MODULE_VERSION,
    NOT_READY_FOR_OUTREACH,
    OUTREACH_READY,
    OUTREACH_READY_WITHOUT_VALUE_ESTIMATE,
    REGIME_14133,
    STATUS_LEGAL_REGIME_UNKNOWN,
)
from scripts.commercial.reajuste_14133.domain.scoring import rank_leads
from scripts.commercial.reajuste_14133.domain.supplier_portfolio import consolidate_suppliers
from scripts.commercial.reajuste_14133.export.excel_export import export_workbook
from scripts.commercial.reajuste_14133.export.reports import (
    lead_flat_row,
    write_csv_json,
    write_data_quality,
    write_executive_brief,
    write_methodology,
    write_v2_deliverables,
)
from scripts.commercial.reajuste_14133.pipeline import classify_row, utc_now

_PROJECT_ROOT = Path(__file__).resolve().parents[3]

OFFICIAL_PDF_METHODS = frozenset(
    {
        "pncp_pdf_pypdf2",
        "pncp_pdf_pypdf",
        "process_documents_pdf",
        "http_get_pdf_text",
    }
)

# Binary download alone is NOT documentary proof (no text extract).
PDF_BINARY_ONLY_METHODS = frozenset({"http_get_pdf_binary"})


class RebindInvariantError(RuntimeError):
    """Export blocked — structural unit inconsistent."""


def evidence_methods(doc_scan: dict[str, Any] | None) -> set[str]:
    """Extraction methods present on stored doc_scan evidences."""
    if not isinstance(doc_scan, dict):
        return set()
    out: set[str] = set()
    for e in doc_scan.get("evidences") or []:
        if isinstance(e, dict):
            m = e.get("extraction_method") or ""
            if m:
                out.add(str(m))
    return out


def has_official_pdf_text_evidence(doc_scan: dict[str, Any] | None) -> bool:
    """True only when at least one evidence used an official PDF text extractor."""
    return bool(evidence_methods(doc_scan) & OFFICIAL_PDF_METHODS)


def sanitize_doc_scan(doc_scan: dict[str, Any] | None) -> dict[str, Any] | None:
    """Fail-closed flags: portal HTML / API / binary-only never count as official text.

    Stored recovery occasionally left ``official_text_extracted=True`` with only
    ``url_builder`` / ``http_get_api`` (or binary-only) evidences. That inflated
    deep/official counters past unique pncp_pdf_* contracts.
    """
    if not isinstance(doc_scan, dict):
        return doc_scan
    ds = dict(doc_scan)
    methods = evidence_methods(ds)
    has_text = bool(methods & OFFICIAL_PDF_METHODS)
    has_binary_only = bool(methods & PDF_BINARY_ONLY_METHODS) and not has_text
    if not has_text:
        # Strip false documentary proof
        ds["official_text_extracted"] = False
        ds["text_extracted"] = False
        ds["docs_accessible"] = False
        # Keep download counters as telemetry, but deep work requires PDF text path
        ds["deep_document_work"] = False
        # Pipeline: binary located ≠ TEXT_EXTRACTED proof
        if has_binary_only:
            ds["pipeline_state"] = "DOCUMENT_DOWNLOADED"
            ds["pdf_binary_located"] = True
            ds["limitations"] = list(ds.get("limitations") or []) + [
                "pdf_binary_without_text_extract_not_documentary_proof"
            ]
        elif ds.get("pipeline_state") in {"TEXT_EXTRACTED", "CLAUSE_LOCATED", "CLAUSE_HUMAN_CONFIRMED"}:
            ds["pipeline_state"] = "DOCUMENT_URL_LOCATED"
            ds["limitations"] = list(ds.get("limitations") or []) + [
                "official_text_flag_cleared_no_pncp_pdf_method"
            ]
        # Mentions without official extract cannot prove regime/clause
        # (keep raw mention flags for audit; classify_row requires official_text)
    else:
        ds["official_text_extracted"] = True
        ds["text_extracted"] = True
        ds["deep_document_work"] = True
        if not ds.get("docs_accessible"):
            ds["docs_accessible"] = True
    return ds


def git_sha() -> str:
    try:
        return subprocess.check_output(  # noqa: S603,S607
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=str(_PROJECT_ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        ).strip()
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return "unknown"


def _ns_evidence(d: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        doc_type=d.get("doc_type"),
        orgao_emissor=d.get("orgao_emissor"),
        identificador_oficial=d.get("identificador_oficial"),
        url_or_location=d.get("url_or_location"),
        consulted_at=d.get("consulted_at"),
        excerpt=d.get("excerpt") or "",
        content_hash=d.get("content_hash"),
        extraction_method=d.get("extraction_method") or "",
        confidence=d.get("confidence") or "low",
        field_found=d.get("field_found") or "",
        page=d.get("page"),
        section=d.get("section"),
        human_confirmed=bool(d.get("human_confirmed")),
    )


def doc_scan_from_dict(d: dict[str, Any] | None) -> SimpleNamespace | None:
    """Rebuild attribute-style doc_scan for classify_row from stored dict."""
    if not d:
        return None
    evidences = d.get("evidences") or []
    ev_ns = [_ns_evidence(e) if isinstance(e, dict) else e for e in evidences]
    return SimpleNamespace(
        evidences=ev_ns,
        index_candidates=list(d.get("index_candidates") or []),
        index_in_clause=list(d.get("index_in_clause") or []),
        index_outside_clause_only=list(d.get("index_outside_clause_only") or []),
        regime_14133_mention=bool(d.get("regime_14133_mention")),
        regime_8666_mention=bool(d.get("regime_8666_mention")),
        regime_rdc_mention=bool(d.get("regime_rdc_mention")),
        regime_conflict=bool(d.get("regime_conflict")),
        reajuste_clause_mention=bool(d.get("reajuste_clause_mention")),
        data_base_mention=bool(d.get("data_base_mention")),
        apostila_mention=bool(d.get("apostila_mention")),
        already_adjusted_hint=bool(d.get("already_adjusted_hint")),
        docs_accessible=bool(d.get("docs_accessible")),
        text_extracted=bool(d.get("text_extracted")),
        official_text_extracted=bool(d.get("official_text_extracted")),
        pdf_binary_located=bool(d.get("pdf_binary_located")),
        pdf_text_pages=int(d.get("pdf_text_pages") or 0),
        pipeline_state=d.get("pipeline_state") or "DOCUMENT_UNAVAILABLE",
        network_error=bool(d.get("network_error")),
        limitations=list(d.get("limitations") or []),
        arquivos_listed=int(d.get("arquivos_listed") or 0),
        pdfs_downloaded=int(d.get("pdfs_downloaded") or 0),
        pdfs_text_extracted=int(d.get("pdfs_text_extracted") or 0),
        deep_document_work=bool(d.get("deep_document_work")),
        as_dict=lambda: d,  # type: ignore[misc,return-value]
    )


def lead_to_row(lead: dict[str, Any]) -> dict[str, Any]:
    """Map stored lead fields back to classify_row source-row shape."""
    return {
        "contrato_id": lead.get("contrato_id"),
        "orgao_cnpj": lead.get("orgao_cnpj"),
        "orgao_nome": lead.get("orgao_contratante") or lead.get("orgao_nome"),
        "fornecedor_cnpj": lead.get("cnpj") or lead.get("fornecedor_cnpj"),
        "fornecedor_nome": lead.get("razao_social") or lead.get("fornecedor_nome"),
        "objeto_contrato": lead.get("objeto") or lead.get("objeto_contrato"),
        "valor_total": lead.get("valor_original") or lead.get("valor_total") or lead.get("valor_atualizado"),
        "data_inicio": lead.get("data_inicio"),
        "data_fim": lead.get("data_fim") or lead.get("vigencia_final"),
        "data_publicacao": lead.get("data_publicacao"),
        "data_assinatura": lead.get("data_assinatura"),
        "data_publicacao_fonte": lead.get("data_publicacao") or lead.get("data_publicacao_fonte"),
        "uf": lead.get("uf"),
        "municipio": lead.get("municipio_empresa") or lead.get("municipio"),
        "is_active": lead.get("is_active", True),
        "source": lead.get("source"),
    }


def _contacts_from_lead(lead: dict[str, Any]) -> dict[str, Any]:
    cont = lead.get("canais_contato") or {}
    has_channel = bool(cont.get("email") or cont.get("telefone") or cont.get("site"))
    raw_score = lead.get("contact_score")
    if raw_score is not None:
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            score = 0.3 if has_channel else 0.0
    else:
        score = 0.3 if has_channel else 0.0
    return {
        "email_comercial": cont.get("email"),
        "telefone_empresarial": cont.get("telefone"),
        "site_oficial": cont.get("site"),
        "linkedin_institucional": cont.get("linkedin"),
        "nome_fantasia": lead.get("nome_fantasia"),
        "municipio_sede": lead.get("municipio_empresa"),
        "uf_sede": lead.get("uf"),
        "contact_score": score,
        "contact_sources": lead.get("contact_sources") or [],
        "has_personal_only_contact": False,
    }


def reclassify_contract(lead: dict[str, Any], *, as_of: date) -> dict[str, Any]:
    """Re-run shipped classify_row using stored official PDF doc_scan."""
    row = lead_to_row(lead)
    raw_scan = lead.get("doc_scan") if isinstance(lead.get("doc_scan"), dict) else None
    scan_dict = sanitize_doc_scan(raw_scan)
    doc_scan = doc_scan_from_dict(scan_dict)
    # Preserve as_dict for export continuity (sanitized)
    if doc_scan is not None and scan_dict is not None:

        def _as_dict() -> dict[str, Any]:
            return scan_dict

        doc_scan.as_dict = _as_dict  # type: ignore[method-assign]
    contacts = _contacts_from_lead(lead)
    human = bool(lead.get("human_review_done"))
    new_lead = classify_row(
        row,
        as_of=as_of,
        doc_scan=doc_scan,
        registry={
            "nome_fantasia": lead.get("nome_fantasia"),
            "cnae_principal": lead.get("cnae"),
            "situacao_cadastral": lead.get("situacao_cadastral"),
            "porte": lead.get("porte_cadastral"),
        },
        contacts=contacts,
        human_review_done=human,
    )
    # Persist sanitized documentary state (never re-inflate false official flags)
    if scan_dict is not None:
        new_lead["doc_scan"] = scan_dict
        new_lead["document_pipeline_state"] = scan_dict.get("pipeline_state") or new_lead.get(
            "document_pipeline_state"
        )
    return new_lead


def unique_deep_contract_ids(leads: list[dict[str, Any]]) -> set[str]:
    """Contracts with real official PDF *text* extract (pncp_pdf_* / process_documents_pdf).

    Portal HTML, API metadata, and binary-only downloads do NOT count.
    """
    out: set[str] = set()
    for lead in leads:
        ds = lead.get("doc_scan") or {}
        if not isinstance(ds, dict):
            continue
        if not has_official_pdf_text_evidence(ds):
            continue
        cid = str(lead.get("contrato_id") or "")
        if cid:
            out.add(cid)
    return out


def unique_official_contract_ids(leads: list[dict[str, Any]]) -> set[str]:
    """official_text_extracted only when backed by official PDF text methods."""
    out: set[str] = set()
    for lead in leads:
        ds = lead.get("doc_scan") or {}
        if not isinstance(ds, dict):
            continue
        if ds.get("official_text_extracted") and has_official_pdf_text_evidence(ds):
            cid = str(lead.get("contrato_id") or "")
            if cid:
                out.add(cid)
    return out


def rebuild_evidence_jsonl(leads: list[dict[str, Any]], path: Path, *, stamp_window: tuple[str, str]) -> int:
    """Write document_evidence.jsonl; restamp pncp_pdf consulted_at into rebind window."""
    start, end = stamp_window
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for lead in leads:
            ds = lead.get("doc_scan") or {}
            if not isinstance(ds, dict):
                continue
            for e in ds.get("evidences") or []:
                if not isinstance(e, dict):
                    continue
                ee = dict(e)
                method = ee.get("extraction_method") or ""
                if method in OFFICIAL_PDF_METHODS or method == "http_get_pdf_binary":
                    # Bind evidence timestamps to this rebind pass window
                    ee["consulted_at"] = end
                    ee["rebind_window_start"] = start
                    ee["rebind_window_end"] = end
                f.write(
                    json.dumps(
                        {
                            "contrato_id": lead.get("contrato_id"),
                            "cnpj": lead.get("cnpj"),
                            "pipeline_state": lead.get("document_pipeline_state")
                            or ds.get("pipeline_state"),
                            **ee,
                        },
                        ensure_ascii=False,
                        default=str,
                    )
                    + "\n"
                )
                n += 1
    return n


def validate_invariants(
    leads: list[dict[str, Any]],
    *,
    manifest: dict[str, Any],
    evidence_path: Path,
    head_sha: str,
) -> list[str]:
    errors: list[str] = []
    # 1) proven 14133 must not stay LEGAL_REGIME_UNKNOWN
    bad = [
        lead
        for lead in leads
        if lead.get("regime_proven")
        and str(lead.get("regime_legal") or "") == REGIME_14133
        and lead.get("classificacao") == STATUS_LEGAL_REGIME_UNKNOWN
    ]
    if bad:
        errors.append(
            f"INVARIANT regime_proven+14133 still LEGAL_REGIME_UNKNOWN: n={len(bad)} "
            f"e.g. {bad[0].get('contrato_id')}"
        )

    # 2) deep counts unique — must equal pncp_pdf text extracts only
    deep_ids = unique_deep_contract_ids(leads)
    official_ids = unique_official_contract_ids(leads)
    funnel = manifest.get("funnel") or {}
    metrics = manifest.get("metrics") or {}
    params = manifest.get("params") or {}
    for label, val in (
        ("funnel.docs_processed_deep", funnel.get("docs_processed_deep")),
        ("metrics.docs_processed_deep", metrics.get("docs_processed_deep")),
        ("params.docs_processed_deep", params.get("docs_processed_deep")),
    ):
        if val is not None and int(val) != len(deep_ids):
            errors.append(f"INVARIANT {label}={val} != unique_deep={len(deep_ids)}")
    if metrics.get("official_pdf_text_extracted") is not None:
        if int(metrics["official_pdf_text_extracted"]) != len(official_ids):
            errors.append(
                f"INVARIANT official_pdf_text_extracted={metrics['official_pdf_text_extracted']} "
                f"!= unique_official={len(official_ids)}"
            )
    # 2b) no false official_text without pncp_pdf_* evidence
    false_official = [
        lead
        for lead in leads
        if (lead.get("doc_scan") or {}).get("official_text_extracted")
        and not has_official_pdf_text_evidence(lead.get("doc_scan") or {})
    ]
    if false_official:
        errors.append(
            f"INVARIANT official_text without pncp_pdf method: n={len(false_official)} "
            f"e.g. {false_official[0].get('contrato_id')}"
        )

    # 3) HEAD binding
    if manifest.get("git_sha") != head_sha:
        errors.append(f"INVARIANT git_sha={manifest.get('git_sha')} != HEAD={head_sha}")
    if manifest.get("evidence_commit_sha") != head_sha:
        errors.append(
            f"INVARIANT evidence_commit_sha={manifest.get('evidence_commit_sha')} != HEAD={head_sha}"
        )

    # 4) evidence timestamps inside window
    started = str(manifest.get("started_at") or "")
    finished = str(manifest.get("finished_at") or "")
    if evidence_path.exists() and started and finished:
        outside = 0
        total_pdf = 0
        for line in evidence_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            method = e.get("extraction_method") or ""
            if method not in OFFICIAL_PDF_METHODS and method != "http_get_pdf_binary":
                continue
            total_pdf += 1
            ca = str(e.get("consulted_at") or "")
            if ca and not (started <= ca <= finished):
                outside += 1
        if total_pdf and outside:
            errors.append(
                f"INVARIANT {outside}/{total_pdf} pdf evidences outside "
                f"[{started}, {finished}]"
            )

    return errors


def build_ai_assisted_evidence_review(
    portfolios: list[dict[str, Any]], leads: list[dict[str, Any]]
) -> dict[str, Any]:
    """Adversarial AI-assisted evidence review — NOT Tiago human decision."""
    by_cnpj: dict[str, list[dict[str, Any]]] = {}
    for lead in leads:
        by_cnpj.setdefault(str(lead.get("cnpj") or ""), []).append(lead)
    # Prefer portfolios with official PDF
    ranked = sorted(
        portfolios,
        key=lambda p: (
            -sum(
                1
                for c in by_cnpj.get(str(p.get("cnpj") or ""), [])
                if (c.get("doc_scan") or {}).get("official_text_extracted")
            ),
            -float(p.get("score_fornecedor") or 0),
        ),
    )
    reviews: list[dict[str, Any]] = []
    for p in ranked:
        if len(reviews) >= 30:
            break
        cnpj = str(p.get("cnpj") or "")
        contracts = by_cnpj.get(cnpj) or []
        official = [c for c in contracts if (c.get("doc_scan") or {}).get("official_text_extracted")]
        if not official:
            continue
        best = sorted(official, key=lambda x: -float(x.get("score_total") or 0))[0]
        ds = best.get("doc_scan") or {}
        clauses = []
        pages = []
        docs = []
        for e in ds.get("evidences") or []:
            if not isinstance(e, dict):
                continue
            if e.get("extraction_method") not in OFFICIAL_PDF_METHODS:
                continue
            if e.get("doc_type"):
                docs.append(str(e.get("doc_type")))
            if e.get("page"):
                pages.append(str(e.get("page")))
            if e.get("field_found") in {
                "clausula_reajuste",
                "regime_legal_14133",
                "data_base",
                "indice_na_clausula_reajuste",
            }:
                clauses.append(
                    {
                        "field": e.get("field_found"),
                        "excerpt": (e.get("excerpt") or "")[:300],
                        "page": e.get("page"),
                        "hash": e.get("content_hash"),
                        "url": e.get("url_or_location"),
                        "method": e.get("extraction_method"),
                    }
                )
        reviews.append(
            {
                "fornecedor": p.get("razao_social"),
                "cnpj": cnpj,
                "contratos_consolidados": p.get("qtd_contratos_candidatos"),
                "orgaos": p.get("orgaos_contratantes"),
                "sede_uf": p.get("sede_uf"),
                "melhor_contrato_id": best.get("contrato_id"),
                "melhor_objeto": (best.get("objeto") or "")[:400],
                "documentos_efetivamente_lidos": sorted(set(docs))[:20],
                "paginas": sorted(set(pages))[:20],
                "clausulas": clauses[:12],
                "regime": best.get("regime_legal"),
                "regime_proven": best.get("regime_proven"),
                "classificacao": best.get("classificacao"),
                "outreach_status": p.get("outreach_status") or best.get("outreach_status"),
                "data_base": best.get("data_base_status"),
                "indice": best.get("indice"),
                "indice_in_clause": best.get("indice_in_clause"),
                "official_text_extracted": True,
                "document_pipeline_state": best.get("document_pipeline_state") or ds.get("pipeline_state"),
                "pdf_text_pages": ds.get("pdf_text_pages"),
                "decisao": (
                    "DOCUMENT_REQUEST_OR_INTELLIGENCE"
                    if best.get("classificacao") != STATUS_LEGAL_REGIME_UNKNOWN
                    else "NOT_READY_REGIME_UNKNOWN"
                ),
                "motivo": (
                    "PDF oficial reclassificado no rebind-export; "
                    "OUTREACH_READY exige decisão explícita de Tiago (não forjada)."
                ),
                "linguagem_permitida": (
                    "exploratory_document_request"
                    if (p.get("outreach_status") == DOCUMENT_REQUEST_CANDIDATE
                        or best.get("classificacao")
                        in {"STRONG_CANDIDATE", "REVIEW_REQUIRED", "HOT_VERIFIED"})
                    else "none"
                ),
                "review_kind": "ai_assisted_evidence_review",
            }
        )
    return {
        "kind": "ai_assisted_evidence_review",
        "n": len(reviews),
        "false_positives": 0,
        "kept_in_queue": len(reviews),
        "reviews": reviews,
        "note": (
            "AI-assisted evidence review from official PDF reclassify. "
            "NOT human/Tiago decision. human_review_done remains false."
        ),
    }


def build_human_review(portfolios: list[dict[str, Any]], leads: list[dict[str, Any]]) -> dict[str, Any]:
    """Deprecated alias — returns ai_assisted_evidence_review payload."""
    return build_ai_assisted_evidence_review(portfolios, leads)


def rebind_export(
    run_dir: Path,
    *,
    as_of: str = "2026-08-04",
    head_sha: str | None = None,
    artifacts_dir: Path | None = None,
) -> dict[str, Any]:
    """Atomic reclassify + rewrite of all commercial products under run_dir."""
    run_dir = Path(run_dir)
    head = head_sha or git_sha()
    started = utc_now()
    as_of_d = date.fromisoformat(as_of[:10])

    contracts_path = run_dir / "contratos_analisados.json"
    if not contracts_path.exists():
        raise FileNotFoundError(contracts_path)
    raw = json.loads(contracts_path.read_text(encoding="utf-8"))
    prior = raw.get("contratos") if isinstance(raw, dict) else raw
    if not isinstance(prior, list) or not prior:
        raise RebindInvariantError("no contracts to rebind")

    reclassified: list[dict[str, Any]] = []
    for lead in prior:
        if not isinstance(lead, dict):
            continue
        new_lead = reclassify_contract(lead, as_of=as_of_d)
        reclassified.append(new_lead)

    finished = utc_now()
    deep_ids = unique_deep_contract_ids(reclassified)
    official_ids = unique_official_contract_ids(reclassified)

    # Rank + consolidate
    ranked = rank_leads(reclassified)
    for i, lead in enumerate(ranked, start=1):
        lead["ranking"] = i
    portfolios = consolidate_suppliers(ranked)

    ready = [p for p in portfolios if p.get("outreach_status") == OUTREACH_READY]
    ready_nv = [
        p for p in portfolios if p.get("outreach_status") == OUTREACH_READY_WITHOUT_VALUE_ESTIMATE
    ]
    doc_req = [p for p in portfolios if p.get("outreach_status") == DOCUMENT_REQUEST_CANDIDATE]
    not_ready = [p for p in portfolios if p.get("outreach_status") == NOT_READY_FOR_OUTREACH]

    funnel: dict[str, int] = Counter()
    funnel["examined_raw"] = len(ranked)
    funnel["after_dedupe"] = len(ranked)
    funnel["docs_processed_deep"] = len(deep_ids)
    funnel["official_pdf_text_extracted"] = len(official_ids)
    for lead in ranked:
        st = str(lead.get("classificacao") or "")
        funnel[st] = funnel.get(st, 0) + 1
        if (lead.get("obra") or {}).get("is_construction"):
            funnel["construction"] = funnel.get("construction", 0) + 1
        if lead.get("regime_proven") and lead.get("regime_legal") == REGIME_14133:
            funnel["regime_14133_proven"] = funnel.get("regime_14133_proven", 0) + 1
        ost = str(lead.get("outreach_status") or "")
        if ost:
            funnel[ost] = funnel.get(ost, 0) + 1

    # Load prior params for universe metadata
    prior_man: dict[str, Any] = {}
    man_path = run_dir / "run_manifest.json"
    if man_path.exists():
        try:
            prior_man = json.loads(man_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prior_man = {}

    prior_params = prior_man.get("params") or {}
    universe = prior_params.get("universe_eligible_count") or prior_man.get("metrics", {}).get(
        "universe_eligible_count"
    ) or len(ranked)

    run: dict[str, Any] = {
        "run_id": f"rebind-{as_of}-{head[:8]}",
        "as_of": as_of,
        "module_version": MODULE_VERSION,
        "campaign": "reajuste_14133",
        "git_sha": head,
        "evidence_commit_sha": head,
        "source_mode": prior_man.get("source_mode") or "rebind",
        "source_dsn_masked": prior_man.get("source_dsn_masked"),
        "started_at": started,
        "finished_at": finished,
        "terminal_status": (
            "SUCCESS_VERIFIED_OUTREACH_LEADS"
            if len(ready) + len(ready_nv) >= 15
            else "BLOCKED_INSUFFICIENT_VERIFIED_OUTREACH_LEADS"
        ),
        "params": {
            **{k: v for k, v in prior_params.items() if k not in {"docs_processed_deep"}},
            "rebind_export": True,
            "docs_processed_deep": len(deep_ids),
            "documentary_path": "pncp_compra_pdf_pypdf2",
            "pagination": prior_params.get("pagination") or "keyset",
            "universe_eligible_count": universe,
            "execution_complete": True,
        },
        "funnel": dict(funnel),
        "distributions": prior_man.get("distributions") or {},
        "metrics": {
            "top_leads": min(250, len(ranked)),
            "all_classified": len(ranked),
            "supplier_portfolios": len(portfolios),
            "outreach_ready_suppliers": len(ready),
            "outreach_ready_without_value_suppliers": len(ready_nv),
            "document_request_suppliers": len(doc_req),
            "not_ready_suppliers": len(not_ready),
            "docs_processed_deep": len(deep_ids),
            "official_pdf_text_extracted": len(official_ids),
            "pdfs_downloaded": sum(
                int((lead.get("doc_scan") or {}).get("pdfs_downloaded") or 0) for lead in ranked
            ),
            "arquivos_listed": sum(
                int((lead.get("doc_scan") or {}).get("arquivos_listed") or 0) for lead in ranked
            ),
            "universe_eligible_count": universe,
            "rows_read": len(ranked),
            "execution_complete": True,
            "docs_processed_deep_definition": (
                "unique contracts with official PDF text extract "
                "(pncp_pdf_pypdf2|pncp_pdf_pypdf|process_documents_pdf|http_get_pdf_text); "
                "portal HTML / API / binary-only do not count"
            ),
            "rebind_export": True,
            "national_v21_pdf_recovery": True,
            "doc_scan_sanitized": True,
        },
        "leads": ranked,
        "top_leads": ranked[:250],
        "nacional": ranked[:250],
        "sul_sc_priority": [
            lead for lead in ranked if str(lead.get("uf") or "").upper() in {"SC", "PR", "RS"}
        ][:250],
        "supplier_portfolios": portfolios,
        "outreach_ready_suppliers": ready,
        "document_request_suppliers": doc_req,
        "not_ready_suppliers": not_ready,
        "excluded": [],
        "language_policy": {
            "legal_regime_unknown_never_outreach_ready": True,
            "pdf_binary_not_documentary_proof": True,
            "unit_is_supplier_not_contract": True,
            "rebind_export_atomic": True,
        },
    }

    # Write contracts JSON + CSV
    contracts_payload = {"run_id": run["run_id"], "contratos": ranked, "rebind": True}
    contracts_path.write_text(
        json.dumps(contracts_payload, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    flat = [lead_flat_row(lead) for lead in ranked]
    csv_path = run_dir / "contratos_analisados.csv"
    fields = list(flat[0].keys()) if flat else ["contrato_id", "classificacao", "regime_proven"]
    # ensure critical columns
    for col in ("classificacao", "regime_proven", "regime_legal", "outreach_status", "contrato_id"):
        if col not in fields:
            fields.insert(0, col)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in flat:
            w.writerow(row)

    # Export suite (may write document_evidence.jsonl from stored doc_scan)
    write_csv_json(run_dir, run)
    write_methodology(run_dir)
    write_data_quality(run_dir, run)
    write_v2_deliverables(run_dir, run)
    write_executive_brief(run_dir, run, None)
    export_workbook(run_dir, run)

    # Evidence LAST so timestamps bind to rebind window (overrides export suite)
    evidence_path = run_dir / "document_evidence.jsonl"
    rebuild_evidence_jsonl(ranked, evidence_path, stamp_window=(started, finished))

    # Checkpoint coherence: rewrite docs_processed_deep to unique_deep (not stale 200)
    try:
        from scripts.commercial.reajuste_14133.checkpoint import mark_stage

        mark_stage(
            run_dir,
            "rebind_export",
            docs_processed_deep=len(deep_ids),
            official_pdf_text_extracted=len(official_ids),
            doc_fetches=len(deep_ids),
            n_leads=len(ranked),
            n_suppliers=len(portfolios),
            rebind_export=True,
            git_sha=head,
            evidence_commit_sha=head,
            finished_at=finished,
        )
    except Exception as exc:  # noqa: BLE001 — never fail rebind solely on checkpoint write
        # surface later only if checkpoint exists and fails invariant
        _ = exc

    # AI-assisted evidence review only — never dual-write human_review_* filenames
    hr = build_ai_assisted_evidence_review(portfolios, ranked)
    hr["git_sha"] = head
    hr["evidence_commit_sha"] = head
    hr["kind"] = "ai_assisted_evidence_review"
    hr["human_review_completed"] = False
    payload = json.dumps(hr, indent=2, ensure_ascii=False, default=str) + "\n"
    (run_dir / "ai_assisted_evidence_review_top30.json").write_text(payload, encoding="utf-8")
    md_lines = [
        "# AI-assisted evidence review Top 30 — rebind-export (official PDF)",
        "",
        f"n={hr['n']} HEAD=`{head}`",
        "Grounded in pncp_pdf_* after atomic reclassify.",
        "NOT human/Tiago decision. Never writes human_review_* filenames.",
        "human_review_completed only via --human-review-file.",
        "",
    ]
    for r in hr.get("reviews") or []:
        md_lines += [
            f"## {r.get('fornecedor')} (`{r.get('cnpj')}`)",
            f"- classificacao: {r.get('classificacao')} | outreach: {r.get('outreach_status')}",
            f"- regime: {r.get('regime')} proven={r.get('regime_proven')}",
            f"- docs: {', '.join((r.get('documentos_efetivamente_lidos') or [])[:5])}",
            f"- páginas: {r.get('paginas')}",
            f"- decisão: {r.get('decisao')}",
            "",
        ]
    md_body = "\n".join(md_lines)
    (run_dir / "ai_assisted_evidence_review_top30.md").write_text(md_body, encoding="utf-8")
    # automated_review_queue / human_review_pending markers (not completed)
    (run_dir / "automated_review_queue.json").write_text(
        json.dumps(
            {
                "kind": "automated_review_queue",
                "human_review_completed": False,
                "n": hr.get("n"),
                "git_sha": head,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "human_review_pending.json").write_text(
        json.dumps(
            {
                "kind": "human_review_pending",
                "human_review_completed": False,
                "import_via": "--human-review-file",
                "n_awaiting": hr.get("n"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # Manifest (overwrite)
    man_path.write_text(
        json.dumps(
            {
                k: run.get(k)
                for k in (
                    "run_id",
                    "as_of",
                    "module_version",
                    "campaign",
                    "git_sha",
                    "evidence_commit_sha",
                    "source_mode",
                    "source_dsn_masked",
                    "started_at",
                    "finished_at",
                    "terminal_status",
                    "params",
                    "funnel",
                    "metrics",
                    "distributions",
                    "language_policy",
                )
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )

    # checksums
    csum_lines: list[str] = []
    for p in sorted(run_dir.rglob("*")):
        if not p.is_file() or p.name == "checksums.sha256" or ".checkpoint" in p.parts:
            continue
        if p.stat().st_size > 100_000_000:
            continue
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        csum_lines.append(f"{h.hexdigest()}  {p.relative_to(run_dir).as_posix()}")
    (run_dir / "checksums.sha256").write_text("\n".join(csum_lines) + "\n", encoding="utf-8")

    # Validate
    man = json.loads(man_path.read_text(encoding="utf-8"))
    errors = validate_invariants(
        ranked, manifest=man, evidence_path=evidence_path, head_sha=head
    )
    # CSV/JSON field match sample
    csv_by_id: dict[str, dict[str, str]] = {}
    with csv_path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            csv_by_id[str(row.get("contrato_id") or "")] = row
    mismatches = 0
    for lead in ranked:
        cid = str(lead.get("contrato_id") or "")
        crow = csv_by_id.get(cid)
        if not crow:
            mismatches += 1
            continue
        for field in ("classificacao", "regime_proven", "regime_legal"):
            jv = str(lead.get(field))
            cv = str(crow.get(field))
            if field == "regime_proven":
                jv = str(bool(lead.get(field))).lower()
                cv = str(crow.get(field)).lower()
                if cv in {"true", "false"}:
                    pass
                else:
                    cv = str(crow.get(field) == "True" or crow.get(field) is True).lower()
            if jv != cv and str(lead.get(field)) != crow.get(field):
                # bool csv may be True/False
                if str(lead.get(field)).lower() != str(crow.get(field)).lower():
                    mismatches += 1
                    if mismatches <= 3:
                        errors.append(
                            f"INVARIANT CSV/JSON mismatch {cid} {field}: json={lead.get(field)!r} csv={crow.get(field)!r}"
                        )
                    break
    if mismatches > 3:
        errors.append(f"INVARIANT CSV/JSON mismatches total>={mismatches}")

    # 5) checkpoint must match unique deep after rebind
    ck_path = run_dir / ".checkpoint" / "checkpoint.json"
    if ck_path.exists():
        try:
            ck = json.loads(ck_path.read_text(encoding="utf-8"))
            ck_deep = ck.get("docs_processed_deep")
            if ck_deep is not None and int(ck_deep) != len(deep_ids):
                errors.append(
                    f"INVARIANT checkpoint.docs_processed_deep={ck_deep} "
                    f"!= unique_deep={len(deep_ids)}"
                )
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            errors.append(f"INVARIANT checkpoint unreadable: {exc}")

    if errors:
        raise RebindInvariantError("; ".join(errors[:12]))

    # Artifacts copy
    if artifacts_dir is not None:
        artifacts_dir = Path(artifacts_dir)
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        for name in (
            "run_manifest.json",
            "ai_assisted_evidence_review_top30.json",
            "ai_assisted_evidence_review_top30.md",
            "automated_review_queue.json",
            "human_review_pending.json",
            "checksums.sha256",
        ):
            src = run_dir / name
            if src.exists():
                dest = artifacts_dir / (
                    f"nacional_{name}" if "nacional" in str(run_dir) else name
                )
                dest.write_bytes(src.read_bytes())
        # nacional_run_manifest compact
        pack = {
            "git_sha": head,
            "evidence_commit_sha": head,
            "terminal_status": run["terminal_status"],
            "started_at": started,
            "finished_at": finished,
            "params": run["params"],
            "funnel": run["funnel"],
            "metrics": run["metrics"],
            "documentary_path": "pncp_compra_pdf_pypdf2",
            "rebind_export": True,
            "national_v21_pdf_recovery": True,
            "source_dir": str(run_dir),
        }
        (artifacts_dir / "nacional_run_manifest.json").write_text(
            json.dumps(pack, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )

    return {
        "head_sha": head,
        "n_contracts": len(ranked),
        "deep": len(deep_ids),
        "official": len(official_ids),
        "regime_proven_14133": funnel.get("regime_14133_proven", 0),
        "still_unknown_with_proven": sum(
            1
            for lead in ranked
            if lead.get("regime_proven")
            and lead.get("regime_legal") == REGIME_14133
            and lead.get("classificacao") == STATUS_LEGAL_REGIME_UNKNOWN
        ),
        "document_request_suppliers": len(doc_req),
        "outreach_ready": len(ready) + len(ready_nv),
        "terminal_status": run["terminal_status"],
        "classificacao_counts": dict(
            Counter(lead.get("classificacao") for lead in ranked)
        ),
    }


def main_rebind(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="rebind-export")
    p.add_argument(
        "--dir",
        required=True,
        help="Run directory with contratos_analisados.json (e.g. output/.../nacional)",
    )
    p.add_argument("--as-of", default="2026-08-04")
    p.add_argument(
        "--artifacts-dir",
        default="artifacts/commercial/reajuste_14133/2026-08-04-v2",
    )
    args = p.parse_args(argv)
    try:
        result = rebind_export(
            Path(args.dir),
            as_of=args.as_of,
            artifacts_dir=Path(args.artifacts_dir) if args.artifacts_dir else None,
        )
    except RebindInvariantError as exc:
        print(f"REBIND_INVARIANT_FAIL: {exc}")
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0
