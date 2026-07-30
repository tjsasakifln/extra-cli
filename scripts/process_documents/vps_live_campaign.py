#!/usr/bin/env python3
"""VPS live campaign: independent benchmark + PNCP arquivos by known process keys + CIGA scale.

Uses independent DB tables (opportunity_intel / engineering_opportunities / pncp_raw_bids /
pncp_supplier_contracts) as process denominators — NOT the document crawler under evaluation.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from scripts.process_documents.activity import classify_all_activity
from scripts.process_documents.adapters.ciga_ckan import CigaCkanDocumentAdapter
from scripts.process_documents.classify_docs import classify_document_title
from scripts.process_documents.corpus import build_corpus_from_runs
from scripts.process_documents.coverage import (
    compute_completeness,
    compute_financial_coverage,
    compute_gaps,
    compute_operational_coverage,
    compute_process_recall,
    full_coverage_bundle,
)
from scripts.process_documents.discovery import discover_all
from scripts.process_documents.models import DocumentRecord, DocumentRunResult
from scripts.process_documents.statuses import ActivityStatus, DocumentRunStatus
from scripts.process_documents.storage import detect_mime, ensure_roots, store_blob, write_json

PNCP_API = "https://pncp.gov.br/api/pncp/v1"
USER_AGENT = "extra-cli-process-documents-vps/1.0"
ENGINEERING_RE = re.compile(
    r"obra|engenharia|paviment|reforma|constru|infraestrutura|edifica|saneamento|drenagem|ponte|viaduto|urbaniz",
    re.I,
)


def digits(v: str | None) -> str:
    return "".join(ch for ch in (v or "") if ch.isdigit())


def ordered_hash(ids: list[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(ids)) + "\n").encode()).hexdigest()


def parse_pncp_id(pid: str) -> tuple[str, int, int] | None:
    # format: CNPJ-1-SEQ/ANO  or CNPJ-2-SEQ/ANO
    m = re.match(r"^(\d{14})-\d+-(\d+)/(\d{4})$", pid or "")
    if not m:
        return None
    return m.group(1), int(m.group(3)), int(m.group(2))


def load_independent_processes(dsn: str, *, limit: int = 400) -> list[dict[str, Any]]:
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(dsn)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    rows: list[dict[str, Any]] = []
    # 1) engineering opportunities (highest value for Extra)
    try:
        cur.execute(
            """
            SELECT pncp_id AS process_id, objeto_compra AS title, valor_total_estimado AS estimated_value,
                   NULL::float AS homologated_value, NULL::float AS awarded_value, NULL::float AS contracted_value,
                   uf, municipio, modalidade_nome AS modality, data_publicacao::text AS published_at,
                   orgao_cnpj, TRUE AS is_engineering, 'engineering_opportunities' AS independent_source,
                   link_pncp AS url
            FROM engineering_opportunities
            WHERE coalesce(within_200km, true) IS NOT FALSE
            ORDER BY data_publicacao DESC NULLS LAST
            LIMIT %s
            """,
            (limit,),
        )
        rows.extend([dict(r) for r in (cur.fetchall() or [])])
    except Exception as exc:
        conn.rollback()
        rows.append({"_error": f"engineering_opportunities:{exc}"})  # type: ignore[dict-item]

    # 2) opportunity_intel SC/recent
    try:
        cur.execute(
            """
            SELECT coalesce(numero_controle_pncp, source_id) AS process_id,
                   objeto AS title,
                   valor_estimado AS estimated_value,
                   valor_homologado AS homologated_value,
                   NULL::float AS awarded_value,
                   NULL::float AS contracted_value,
                   uf, municipio, modalidade AS modality,
                   data_publicacao::text AS published_at,
                   orgao_cnpj,
                   (objeto ~* 'obra|engenharia|paviment|reforma|constru|infraestrutura') AS is_engineering,
                   'opportunity_intel' AS independent_source,
                   coalesce(link_edital, source_url) AS url
            FROM opportunity_intel
            WHERE uf = 'SC' OR codigo_ibge LIKE '42%%'
            ORDER BY data_publicacao DESC NULLS LAST
            LIMIT %s
            """,
            (limit,),
        )
        rows.extend([dict(r) for r in (cur.fetchall() or [])])
    except Exception as exc:
        conn.rollback()

    # 3) pncp_raw_bids
    try:
        cur.execute(
            """
            SELECT coalesce(numero_controle_pncp, pncp_id) AS process_id,
                   objeto_compra AS title,
                   valor_total_estimado AS estimated_value,
                   NULL::float AS homologated_value,
                   NULL::float AS awarded_value,
                   NULL::float AS contracted_value,
                   uf, municipio, modalidade_nome AS modality,
                   data_publicacao::text AS published_at,
                   orgao_cnpj,
                   (objeto_compra ~* 'obra|engenharia|paviment|reforma|constru|infraestrutura') AS is_engineering,
                   'pncp_raw_bids' AS independent_source,
                   link_pncp AS url
            FROM pncp_raw_bids
            WHERE uf = 'SC'
            ORDER BY data_publicacao DESC NULLS LAST
            LIMIT %s
            """,
            (limit,),
        )
        rows.extend([dict(r) for r in (cur.fetchall() or [])])
    except Exception as exc:
        conn.rollback()

    # 4) contracts sample SC engineering-ish for financial coverage
    try:
        cur.execute(
            """
            SELECT coalesce(contrato_id, source_id) AS process_id,
                   objeto_contrato AS title,
                   NULL::float AS estimated_value,
                   NULL::float AS homologated_value,
                   NULL::float AS awarded_value,
                   valor_total AS contracted_value,
                   uf, municipio, NULL AS modality,
                   data_publicacao::text AS published_at,
                   orgao_cnpj,
                   (objeto_contrato ~* 'obra|engenharia|paviment|reforma|constru|infraestrutura') AS is_engineering,
                   'pncp_supplier_contracts' AS independent_source,
                   NULL AS url
            FROM pncp_supplier_contracts
            WHERE uf = 'SC' AND valor_total IS NOT NULL AND valor_total > 0
              AND data_publicacao >= (CURRENT_DATE - INTERVAL '36 months')
            ORDER BY valor_total DESC NULLS LAST
            LIMIT %s
            """,
            (limit,),
        )
        rows.extend([dict(r) for r in (cur.fetchall() or [])])
    except Exception as exc:
        conn.rollback()

    cur.close()
    conn.close()

    by_id: dict[str, dict[str, Any]] = {}
    for r in rows:
        if not isinstance(r, dict) or r.get("_error") or not r.get("process_id"):
            continue
        pid = str(r["process_id"])
        title = r.get("title") or ""
        is_eng = bool(r.get("is_engineering")) or bool(ENGINEERING_RE.search(str(title)))
        prev = by_id.get(pid)
        # Prefer engineering flag / richer values
        if prev is None or (is_eng and not prev.get("is_engineering")):
            by_id[pid] = {
                "process_id": pid,
                "title": title,
                "estimated_value": _f(r.get("estimated_value")),
                "homologated_value": _f(r.get("homologated_value")),
                "awarded_value": _f(r.get("awarded_value")),
                "contracted_value": _f(r.get("contracted_value")),
                "uf": r.get("uf"),
                "municipio": r.get("municipio"),
                "modality": r.get("modality"),
                "published_at": r.get("published_at"),
                "orgao_cnpj": r.get("orgao_cnpj"),
                "is_engineering": is_eng,
                "independent_source": r.get("independent_source"),
                "url": r.get("url"),
                "relevant": True,
            }
    return list(by_id.values())


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def download_pncp_arquivos_for_process(
    session: requests.Session,
    process: dict[str, Any],
    *,
    raw_root: Path,
    meta_root: Path,
    entity_id: str,
) -> DocumentRunResult:
    started = datetime.now(UTC)
    run_id = f"pd-pncp-db-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    parsed = parse_pncp_id(str(process["process_id"]))
    docs: list[DocumentRecord] = []
    errors: list[str] = []
    downloaded = 0
    unchanged = 0
    failed = 0
    discovered = 0

    if not parsed:
        finished = datetime.now(UTC)
        return DocumentRunResult(
            run_id=run_id,
            canonical_entity_id=entity_id,
            source_id="pncp",
            portal_family="pncp",
            capabilities_requested=["notice_documents"],
            capabilities_proven=[],
            status=DocumentRunStatus.SCHEMA_FAILED,
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            errors=["cannot parse pncp process id"],
            blockers=["schema_failed"],
            latency_ms=(finished - started).total_seconds() * 1000,
        )
    cnpj, ano, seq = parsed
    url = f"{PNCP_API}/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos"
    try:
        time.sleep(0.25)
        resp = session.get(url, timeout=(8, 90))
    except requests.Timeout:
        finished = datetime.now(UTC)
        return DocumentRunResult(
            run_id=run_id,
            canonical_entity_id=entity_id,
            source_id="pncp",
            portal_family="pncp",
            capabilities_requested=["notice_documents"],
            capabilities_proven=[],
            status=DocumentRunStatus.TIMEOUT,
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            errors=["timeout arquivos"],
            blockers=["timeout"],
            latency_ms=(finished - started).total_seconds() * 1000,
        )
    except requests.RequestException as exc:
        finished = datetime.now(UTC)
        return DocumentRunResult(
            run_id=run_id,
            canonical_entity_id=entity_id,
            source_id="pncp",
            portal_family="pncp",
            capabilities_requested=["notice_documents"],
            capabilities_proven=[],
            status=DocumentRunStatus.CONNECTION_FAILED,
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            errors=[str(exc)],
            blockers=["connection_failed"],
            latency_ms=(finished - started).total_seconds() * 1000,
        )

    if resp.status_code in (401, 403):
        st = DocumentRunStatus.AUTH_REQUIRED
    elif resp.status_code == 404:
        st = None  # empty
    elif resp.status_code == 429:
        st = DocumentRunStatus.HTTP_RATE_LIMIT
    elif resp.status_code >= 500:
        st = DocumentRunStatus.HTTP_SERVER_ERROR
    elif resp.status_code not in (200, 204):
        st = DocumentRunStatus.HTTP_CLIENT_ERROR
    else:
        st = None

    if st is not None:
        finished = datetime.now(UTC)
        return DocumentRunResult(
            run_id=run_id,
            canonical_entity_id=entity_id,
            source_id="pncp",
            portal_family="pncp",
            capabilities_requested=["notice_documents"],
            capabilities_proven=[],
            status=st,
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            errors=[f"HTTP {resp.status_code}"],
            blockers=[st.value],
            pages_attempted=1,
            pages_completed=1,
            latency_ms=(finished - started).total_seconds() * 1000,
        )

    arquivos: list[dict[str, Any]] = []
    if resp.status_code == 200:
        try:
            payload = resp.json()
            if isinstance(payload, list):
                arquivos = [a for a in payload if isinstance(a, dict)]
            elif isinstance(payload, dict):
                arquivos = [a for a in (payload.get("data") or []) if isinstance(a, dict)]
        except json.JSONDecodeError as exc:
            finished = datetime.now(UTC)
            return DocumentRunResult(
                run_id=run_id,
                canonical_entity_id=entity_id,
                source_id="pncp",
                portal_family="pncp",
                capabilities_requested=["notice_documents"],
                capabilities_proven=[],
                status=DocumentRunStatus.PARSE_FAILED,
                started_at=started.isoformat(),
                finished_at=finished.isoformat(),
                errors=[str(exc)],
                blockers=["parse_failed"],
                pages_attempted=1,
                pages_completed=1,
                latency_ms=(finished - started).total_seconds() * 1000,
            )

    for arq in arquivos:
        discovered += 1
        title = str(arq.get("titulo") or "documento")
        aurl = arq.get("url") or arq.get("uri")
        if isinstance(aurl, str) and aurl.startswith("/"):
            aurl = urljoin("https://pncp.gov.br", aurl)
        if not aurl:
            seq_doc = arq.get("sequencialDocumento") or arq.get("sequencial")
            if seq_doc is not None:
                aurl = f"{PNCP_API}/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos/{seq_doc}"
            else:
                failed += 1
                continue
        try:
            time.sleep(0.2)
            dresp = session.get(str(aurl), timeout=(8, 90), allow_redirects=True)
        except requests.RequestException as exc:
            failed += 1
            errors.append(str(exc))
            finished = datetime.now(UTC)
            return DocumentRunResult(
                run_id=run_id,
                canonical_entity_id=entity_id,
                source_id="pncp",
                portal_family="pncp",
                capabilities_requested=["notice_documents"],
                capabilities_proven=[],
                status=DocumentRunStatus.DOWNLOAD_INCOMPLETE,
                started_at=started.isoformat(),
                finished_at=finished.isoformat(),
                documents_discovered=discovered,
                documents_downloaded=downloaded,
                documents_unchanged=unchanged,
                documents_failed=failed,
                errors=errors,
                blockers=["download_incomplete"],
                pages_attempted=1,
                pages_completed=1,
                documents=docs,
                latency_ms=(finished - started).total_seconds() * 1000,
            )
        if dresp.status_code != 200 or not dresp.content:
            failed += 1
            errors.append(f"HTTP {dresp.status_code}")
            finished = datetime.now(UTC)
            return DocumentRunResult(
                run_id=run_id,
                canonical_entity_id=entity_id,
                source_id="pncp",
                portal_family="pncp",
                capabilities_requested=["notice_documents"],
                capabilities_proven=[],
                status=DocumentRunStatus.DOWNLOAD_INCOMPLETE,
                started_at=started.isoformat(),
                finished_at=finished.isoformat(),
                documents_discovered=discovered,
                documents_downloaded=downloaded,
                documents_unchanged=unchanged,
                documents_failed=failed,
                errors=errors,
                blockers=["download_incomplete"],
                pages_attempted=1,
                pages_completed=1,
                documents=docs,
                latency_ms=(finished - started).total_seconds() * 1000,
            )
        blob = dresp.content
        detected = detect_mime(blob, dresp.headers.get("Content-Type"))
        ext = "pdf" if detected == "application/pdf" else ("zip" if detected == "application/zip" else None)
        stored = store_blob(blob, raw_root=raw_root, extension=ext, declared_filename=title)
        if stored.unchanged:
            unchanged += 1
        else:
            downloaded += 1
        docs.append(
            DocumentRecord(
                internal_id=stored.sha256[:20],
                sha256=stored.sha256,
                size_bytes=stored.size_bytes,
                download_url=str(aurl),
                source_id="pncp",
                canonical_entity_id=entity_id,
                portal_family="pncp",
                document_category=classify_document_title(title),
                original_title=title,
                procurement_id=str(process["process_id"]),
                notice_id=str(seq),
                published_at=str(process.get("published_at") or ""),
                declared_mime=dresp.headers.get("Content-Type"),
                detected_mime=detected,
                extension=ext,
                run_id=run_id,
                raw_uri=stored.raw_uri,
                unchanged=stored.unchanged,
            )
        )

    finished = datetime.now(UTC)
    if downloaded + unchanged > 0:
        status = DocumentRunStatus.SUCCESS_NONZERO
        justification = None
    else:
        status = DocumentRunStatus.SUCCESS_ZERO
        justification = f"PNCP arquivos enumerated for {process['process_id']}; zero documents"
    result = DocumentRunResult(
        run_id=run_id,
        canonical_entity_id=entity_id,
        source_id="pncp",
        portal_family="pncp",
        capabilities_requested=["notice_documents", "planning_documents"],
        capabilities_proven=["notice_documents"] if status == DocumentRunStatus.SUCCESS_NONZERO else [],
        status=status,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        query_parameters={"process_id": process["process_id"], "source": "db_independent"},
        pages_attempted=1,
        pages_completed=1,
        records_seen=1,
        processes_seen=1,
        documents_discovered=discovered,
        documents_downloaded=downloaded,
        documents_unchanged=unchanged,
        documents_failed=failed,
        errors=errors,
        documents=docs,
        success_zero_justification=justification,
        latency_ms=(finished - started).total_seconds() * 1000,
    )
    run_dir = meta_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "result.json", result.to_dict())
    result.evidence_uri = str(run_dir / "result.json")
    with (meta_root / "run-index.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "run_id": run_id,
                    "canonical_entity_id": entity_id,
                    "status": result.status.value,
                    "documents_downloaded": downloaded,
                    "documents_unchanged": unchanged,
                    "finished_at": finished.isoformat(),
                    "evidence_uri": result.evidence_uri,
                    "process_id": process["process_id"],
                    "portal_family": "pncp",
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    return result


def map_entity(discoveries: list[Any], cnpj: str | None) -> str:
    root = digits(cnpj)[:8]
    if len(root) < 8:
        return f"pncp-org:{digits(cnpj) or 'unknown'}"
    for d in discoveries:
        if digits(d.cnpj)[:8] == root:
            return d.canonical_id
    return f"pncp-org:{digits(cnpj)}"


def main() -> int:
    raw_root, meta_root = ensure_roots()
    dsn = os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        print(json.dumps({"error": "no DSN"}))
        return 2

    discoveries, disc_report = discover_all(persist=True)
    discoveries, act_report = classify_all_activity(discoveries, persist=True, dsn=dsn)

    processes = load_independent_processes(dsn, limit=500)
    eng = [p for p in processes if p.get("is_engineering")]
    # Prefer engineering first for corpus targets
    target_processes = eng[:40] + [p for p in processes if not p.get("is_engineering")][:80]

    bench = {
        "version": "process_recall_benchmark_v1_vps_db_2026-07-30",
        "criteria": {
            "engineering_compatible": "engineering_opportunities + regex",
            "geography": "SC / Extra 200km when flagged",
            "window": "36 months for contracts; recent for opportunities",
            "modalities": "as in independent tables",
            "profile_adherence": "Extra Construtora engineering preferred",
        },
        "cutoff_date": datetime.now(UTC).date().isoformat(),
        "independent_sources": [
            "engineering_opportunities",
            "opportunity_intel",
            "pncp_raw_bids",
            "pncp_supplier_contracts",
        ],
        "expected_processes": target_processes,
        "expected_count": len(target_processes),
        "engineering_count": sum(1 for p in target_processes if p.get("is_engineering")),
        "expected_ids_sha256": ordered_hash([p["process_id"] for p in target_processes]),
        "financial_value_hierarchy": [
            "contracted_value",
            "homologated_value",
            "awarded_value",
            "estimated_value",
        ],
        "generated_at": datetime.now(UTC).isoformat(),
        "note": "Independent of document crawler under evaluation.",
    }
    write_json(meta_root / "process-recall-benchmark.json", bench)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

    # PNCP live for engineering-first processes (arquivos API)
    pncp_stats: dict[str, int] = {}
    found_ids: set[str] = set()
    for i, proc in enumerate(target_processes[:50], 1):
        entity_id = map_entity(discoveries, proc.get("orgao_cnpj"))
        # Only try parseable PNCP process ids for arquivos
        if not parse_pncp_id(str(proc["process_id"])):
            continue
        result = download_pncp_arquivos_for_process(
            session, proc, raw_root=raw_root, meta_root=meta_root, entity_id=entity_id
        )
        pncp_stats[result.status.value] = pncp_stats.get(result.status.value, 0) + 1
        if result.status in (DocumentRunStatus.SUCCESS_NONZERO, DocumentRunStatus.SUCCESS_ZERO):
            found_ids.add(str(proc["process_id"]))
        if i % 10 == 0:
            print(json.dumps({"pncp_progress": i, "stats": pncp_stats}), flush=True)

    # CIGA scale for remaining active entities without operational run
    from scripts.process_documents.storage import load_jsonl

    covered = {
        r.get("canonical_entity_id")
        for r in load_jsonl(meta_root / "run-index.jsonl")
        if r.get("status") in ("SUCCESS_NONZERO", "SUCCESS_ZERO")
    }
    ciga = CigaCkanDocumentAdapter(request_delay=0.02, raw_root=raw_root, meta_root=meta_root)
    ciga_stats: dict[str, int] = {}
    targets = [
        d
        for d in discoveries
        if d.activity_status == ActivityStatus.ACTIVE.value
        and d.canonical_id not in covered
        and any(p in {x.lower() for x in d.platforms} for p in ("ciga_ckan", "ciga_dom", "dom_sc"))
    ]
    for i, d in enumerate(targets, 1):
        run = ciga.collect(d, max_processes=1, download=True)
        ciga_stats[run.status.value] = ciga_stats.get(run.status.value, 0) + 1
        if i % 50 == 0 or i == len(targets):
            print(json.dumps({"ciga_progress": i, "of": len(targets), "stats": ciga_stats}), flush=True)

    op = compute_operational_coverage(discoveries, meta_root=meta_root, persist=True)
    rec = compute_process_recall(meta_root=meta_root, found_process_ids=found_ids, persist=True)
    fin = compute_financial_coverage(meta_root=meta_root, covered_process_ids=found_ids, persist=True)
    comp = compute_completeness(meta_root=meta_root, persist=True)
    gaps = compute_gaps(discoveries, meta_root=meta_root, persist=True)
    corpus = build_corpus_from_runs(meta_root=meta_root)
    bundle, code = full_coverage_bundle(persist=True)

    summary = {
        "discovery_percent": disc_report.get("entity_source_discovery_coverage_percent"),
        "active_count": act_report.get("active_count"),
        "operational": {"percent": op.get("percent"), "num": op.get("numerator"), "den": op.get("denominator")},
        "recall": {"percent": rec.get("percent"), "num": rec.get("numerator"), "den": rec.get("denominator")},
        "financial": {"percent": fin.get("percent"), "total": fin.get("total_value"), "covered": fin.get("covered_value")},
        "completeness": {k: v.get("percent") for k, v in (comp.get("metrics") or {}).items()},
        "pncp_stats": pncp_stats,
        "ciga_stats": ciga_stats,
        "corpus": {
            "processes": corpus.get("process_count"),
            "engineering": corpus.get("engineering_process_count"),
            "envelopes": corpus.get("complete_envelope_count"),
            "families": corpus.get("portal_family_count"),
            "annotations": corpus.get("annotated_requirements_count"),
        },
        "gate_exit": code,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    write_json(meta_root / "vps-live-campaign-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
