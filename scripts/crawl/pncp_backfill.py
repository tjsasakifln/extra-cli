"""Operational PNCP backfill with page-atomic persistence and reconciliation.

This command is intentionally scoped to one official source (PNCP), one UF
(Santa Catarina), and one closed seven-day publication window.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import os
import signal
import sys
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
import requests

from scripts.crawl import pncp_crawler_adapter as adapter
from scripts.crawl.ingestion._base.crawler import CrawlRequest
from scripts.crawl.pncp_contract import DEFAULT_MODALIDADES, PNCP_CONSULTA_BASE

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE_SCHEMA_MIGRATION = PROJECT_ROOT / "db" / "migrations" / "001_pncp_raw_bids.sql"
BACKFILL_MIGRATION = PROJECT_ROOT / "db" / "migrations" / "049_pncp_resumable_backfill.sql"
SAFE_DATABASE_PREFIXES = ("pncp_mission_", "pncp_acceptance_")

_STOP_SIGNAL: int | None = None


class BackfillError(RuntimeError):
    """Controlled operational failure."""


@dataclass
class SourceSnapshot:
    total_records: int
    unique_records: int
    duplicate_records: int
    duplicate_keys: int
    data_pages: int
    requests: int
    ids: list[str]
    modalities: dict[int, dict[str, int]]


def _signal_handler(signum: int, _frame: Any) -> None:
    global _STOP_SIGNAL
    _STOP_SIGNAL = signum
    print(f"SIGNAL received={signum}; stopping after current atomic page", flush=True)


def _connect(dsn: str, *, autocommit: bool = False):
    conn = psycopg2.connect(dsn)
    conn.autocommit = autocommit
    return conn


def _database_name(conn: Any) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database()")
        return str(cur.fetchone()[0])


def prepare_clean_database(dsn: str) -> None:
    """Recreate the public schema in a dedicated acceptance database."""
    conn = _connect(dsn, autocommit=True)
    try:
        db_name = _database_name(conn)
        if not db_name.startswith(SAFE_DATABASE_PREFIXES):
            raise BackfillError(
                f"--prepare-clean refused for database {db_name!r}; "
                f"use a dedicated database prefixed by {SAFE_DATABASE_PREFIXES}"
            )
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA IF EXISTS public CASCADE")
            cur.execute("CREATE SCHEMA public AUTHORIZATION CURRENT_USER")
            cur.execute(BASE_SCHEMA_MIGRATION.read_text())
            cur.execute(BACKFILL_MIGRATION.read_text())
        print(f"PREPARE database={db_name} schema=clean migrations=001,049", flush=True)
    finally:
        conn.close()


def ensure_backfill_schema(dsn: str) -> None:
    conn = _connect(dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.pncp_raw_bids')")
            if cur.fetchone()[0] is None:
                cur.execute(BASE_SCHEMA_MIGRATION.read_text())
            cur.execute(BACKFILL_MIGRATION.read_text())
    finally:
        conn.close()


def _validate_window(window_start: date, window_end: date) -> None:
    if (window_end - window_start).days != 6:
        raise BackfillError("a janela deve ter exatamente 7 dias inclusivos")
    if window_end >= date.today():
        raise BackfillError("a janela deve estar fechada: data final anterior a hoje")


def _new_run(conn: Any, window_start: date, window_end: date) -> str:
    run_id = f"pncp-{window_start:%Y%m%d}-{window_end:%Y%m%d}-{uuid.uuid4().hex[:12]}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pncp_backfill_runs (run_id, window_start, window_end, status)
            VALUES (%s, %s, %s, 'running')
            """,
            (run_id, window_start, window_end),
        )
    conn.commit()
    return run_id


def _resume_run(conn: Any, window_start: date, window_end: date) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT run_id
            FROM pncp_backfill_runs
            WHERE window_start = %s
              AND window_end = %s
              AND status IN ('running', 'interrupted', 'failed')
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (window_start, window_end),
        )
        row = cur.fetchone()
        if row is None:
            raise BackfillError("nenhuma execucao incompleta encontrada para retomar")
        run_id = str(row[0])
        cur.execute(
            """
            UPDATE pncp_backfill_runs
            SET status = 'running', error_message = NULL, completed_at = NULL
            WHERE run_id = %s
            """,
            (run_id,),
        )
    conn.commit()
    return run_id


def _completed_pages(conn: Any, run_id: str, modalidade_id: int) -> dict[int, dict[str, int]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT page_number, source_total_records, source_total_pages
            FROM pncp_backfill_pages
            WHERE run_id = %s AND modalidade_id = %s
            ORDER BY page_number
            """,
            (run_id, modalidade_id),
        )
        return {
            int(page): {
                "source_total_records": int(total_records),
                "source_total_pages": int(total_pages),
            }
            for page, total_records, total_pages in cur.fetchall()
        }


def _deduplicate_page(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    by_id: dict[str, dict[str, Any]] = {}
    hashes: dict[str, str] = {}
    for record in records:
        pncp_id = str(record["pncp_id"])
        content_hash = str(record["content_hash"])
        previous_hash = hashes.get(pncp_id)
        if previous_hash is not None and previous_hash != content_hash:
            raise BackfillError(f"pagina contem versões conflitantes para pncp_id={pncp_id}")
        hashes[pncp_id] = content_hash
        by_id[pncp_id] = record
    return list(by_id.values()), len(records) - len(by_id)


def _refresh_run_totals(conn: Any, run_id: str) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH modality_totals AS (
                SELECT
                    modalidade_id,
                    MAX(source_total_pages) AS source_total_pages
                FROM pncp_backfill_pages
                WHERE run_id = %s
                GROUP BY modalidade_id
            ),
            page_totals AS (
                SELECT
                    COUNT(*)::INTEGER AS pages_completed,
                    COALESCE(SUM(records_fetched), 0)::INTEGER AS records_fetched,
                    COALESCE(SUM(inserted), 0)::INTEGER AS inserted,
                    COALESCE(SUM(updated), 0)::INTEGER AS updated,
                    COALESCE(SUM(unchanged), 0)::INTEGER AS unchanged
                FROM pncp_backfill_pages
                WHERE run_id = %s
            ),
            membership AS (
                SELECT COUNT(DISTINCT pncp_id)::INTEGER AS unique_records
                FROM pncp_backfill_records
                WHERE run_id = %s
            )
            SELECT
                COALESCE((SELECT SUM(GREATEST(1, source_total_pages)) FROM modality_totals), 0)::INTEGER,
                COALESCE((SELECT SUM(source_total_pages) FROM modality_totals), 0)::INTEGER,
                p.pages_completed,
                p.records_fetched,
                m.unique_records,
                GREATEST(0, p.records_fetched - m.unique_records)::INTEGER,
                p.inserted,
                p.updated,
                p.unchanged
            FROM page_totals p CROSS JOIN membership m
            """,
            (run_id, run_id, run_id),
        )
        row = cur.fetchone()
        totals = {
            "pages_expected": int(row[0]),
            "data_pages_expected": int(row[1]),
            "pages_completed": int(row[2]),
            "records_fetched": int(row[3]),
            "unique_records": int(row[4]),
            "duplicate_records": int(row[5]),
            "inserted": int(row[6]),
            "updated": int(row[7]),
            "unchanged": int(row[8]),
        }
        cur.execute(
            """
            UPDATE pncp_backfill_runs
            SET pages_expected = %(pages_expected)s,
                data_pages_expected = %(data_pages_expected)s,
                pages_completed = %(pages_completed)s,
                records_fetched = %(records_fetched)s,
                unique_records = %(unique_records)s,
                duplicate_records = %(duplicate_records)s,
                inserted = %(inserted)s,
                updated = %(updated)s,
                unchanged = %(unchanged)s
            WHERE run_id = %(run_id)s
            """,
            {**totals, "run_id": run_id},
        )
    return totals


def _persist_page(
    conn: Any,
    *,
    run_id: str,
    window_start: date,
    window_end: date,
    modalidade_id: int,
    page_number: int,
    raw_records: list[dict[str, Any]],
    pagination: dict[str, Any],
    collected_at: datetime,
    force_upsert_failure: bool = False,
) -> dict[str, int]:
    transformed = adapter.transform(raw_records)
    if len(transformed) != len(raw_records):
        raise BackfillError(
            f"transform incompleto modalidade={modalidade_id} pagina={page_number}: "
            f"fetch={len(raw_records)} transform={len(transformed)}"
        )
    for record in transformed:
        record["crawl_batch_id"] = run_id

    unique_records, duplicate_records = _deduplicate_page(transformed)
    payload = json.dumps(unique_records, ensure_ascii=False, default=str)

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM upsert_pncp_raw_bids(%s::jsonb)", (payload,))
            inserted, updated, unchanged = (int(value) for value in cur.fetchone()[:3])
            if inserted + updated + unchanged != len(unique_records):
                raise BackfillError(
                    f"upsert nao reconciliou a pagina: unique={len(unique_records)} "
                    f"inserted={inserted} updated={updated} unchanged={unchanged}"
                )
            if force_upsert_failure:
                cur.execute("SELECT 1 / 0")

            membership_rows = [
                (
                    run_id,
                    record["pncp_id"],
                    window_start,
                    window_end,
                    modalidade_id,
                    page_number,
                    record["content_hash"],
                    json.dumps(record["raw_payload"], ensure_ascii=False, default=str),
                    collected_at,
                )
                for record in unique_records
            ]
            if membership_rows:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO pncp_backfill_records (
                        run_id, pncp_id, window_start, window_end,
                        modalidade_id, page_number, content_hash, raw_payload, collected_at
                    ) VALUES %s
                    ON CONFLICT (run_id, modalidade_id, page_number, pncp_id) DO NOTHING
                    """,
                    membership_rows,
                )

            cur.execute(
                """
                INSERT INTO pncp_backfill_pages (
                    run_id, modalidade_id, page_number,
                    source_total_records, source_total_pages,
                    records_fetched, unique_records, duplicate_records,
                    inserted, updated, unchanged, collected_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id, modalidade_id, page_number) DO NOTHING
                """,
                (
                    run_id,
                    modalidade_id,
                    page_number,
                    int(pagination["totalRegistros"]),
                    int(pagination["totalPaginas"]),
                    len(raw_records),
                    len(unique_records),
                    duplicate_records,
                    inserted,
                    updated,
                    unchanged,
                    collected_at,
                ),
            )
            if cur.rowcount != 1:
                raise BackfillError(
                    f"checkpoint duplicado modalidade={modalidade_id} pagina={page_number}"
                )
            totals = _refresh_run_totals(conn, run_id)
        conn.commit()
        return {
            **totals,
            "page_inserted": inserted,
            "page_updated": updated,
            "page_unchanged": unchanged,
            "page_duplicates": duplicate_records,
        }
    except Exception:
        conn.rollback()
        raise


def _mark_run(conn: Any, run_id: str, status: str, error_message: str | None = None) -> dict[str, Any]:
    with conn.cursor() as cur:
        totals = _refresh_run_totals(conn, run_id)
        cur.execute(
            """
            UPDATE pncp_backfill_runs
            SET status = %s,
                completed_at = CASE WHEN %s IN ('completed', 'interrupted', 'failed') THEN NOW() ELSE NULL END,
                error_message = %s
            WHERE run_id = %s
            """,
            (status, status, error_message, run_id),
        )
    conn.commit()
    return {"run_id": run_id, "status": status, "error_message": error_message, **totals}


def execute_backfill(
    *,
    dsn: str,
    window_start: date,
    window_end: date,
    resume: bool = False,
    request_delay: float = 1.1,
    stop_after_pages: int | None = None,
    fail_after_upsert_page: int | None = None,
) -> dict[str, Any]:
    """Execute or resume one official PNCP run."""
    global _STOP_SIGNAL
    _STOP_SIGNAL = None
    _validate_window(window_start, window_end)
    ensure_backfill_schema(dsn)

    conn = _connect(dsn)
    session = requests.Session()
    request = CrawlRequest(
        mode="backfill",
        date_from=window_start,
        date_to=window_end,
        target="sc",
    )
    previous_term = signal.signal(signal.SIGTERM, _signal_handler)
    previous_int = signal.signal(signal.SIGINT, _signal_handler)

    run_id = ""
    page_sequence = 0
    try:
        run_id = _resume_run(conn, window_start, window_end) if resume else _new_run(
            conn, window_start, window_end
        )
        print(
            f"RUN run_id={run_id} resume={str(resume).lower()} "
            f"window={window_start.isoformat()}..{window_end.isoformat()} "
            f"endpoint={PNCP_CONSULTA_BASE}/contratacoes/publicacao",
            flush=True,
        )

        for modalidade_id in DEFAULT_MODALIDADES:
            completed = _completed_pages(conn, run_id, modalidade_id)
            known_total_pages = next(
                (data["source_total_pages"] for data in completed.values()),
                None,
            )
            page_limit = max(1, known_total_pages or 1)
            page_number = 1

            while page_number <= page_limit:
                if _STOP_SIGNAL is not None:
                    return _mark_run(
                        conn,
                        run_id,
                        "interrupted",
                        f"signal={_STOP_SIGNAL}; antes da proxima pagina",
                    )
                if page_number in completed:
                    print(
                        f"SKIP modalidade={modalidade_id:02d} page={page_number} checkpoint=completed",
                        flush=True,
                    )
                    page_number += 1
                    continue

                result = adapter._fetch_publication_page(  # noqa: SLF001 - same crawler runtime
                    request,
                    modalidade_id,
                    page_number,
                    session=session,
                )
                if result.errors or not result.request_completed:
                    raise BackfillError(
                        f"fetch incompleto modalidade={modalidade_id} pagina={page_number}: "
                        f"{'; '.join(result.errors) or 'request_completed=false'}"
                    )
                pagination = result.metadata.get("pagination")
                if not isinstance(pagination, dict):
                    raise BackfillError(
                        f"paginacao ausente modalidade={modalidade_id} pagina={page_number}"
                    )
                if int(pagination["numeroPagina"]) != page_number:
                    raise BackfillError(
                        f"pagina divergente modalidade={modalidade_id}: "
                        f"solicitada={page_number} recebida={pagination['numeroPagina']}"
                    )
                source_total_pages = int(pagination["totalPaginas"])
                if source_total_pages > adapter.PNCP_MAX_PAGES:
                    raise BackfillError(
                        f"limite PNCP_MAX_PAGES={adapter.PNCP_MAX_PAGES} menor que "
                        f"totalPaginas={source_total_pages} modalidade={modalidade_id}"
                    )
                if known_total_pages is not None and source_total_pages != known_total_pages:
                    raise BackfillError(
                        f"totalPaginas mudou modalidade={modalidade_id}: "
                        f"checkpoint={known_total_pages} fonte={source_total_pages}"
                    )
                known_total_pages = source_total_pages
                page_limit = max(1, source_total_pages)

                page_sequence += 1
                stats = _persist_page(
                    conn,
                    run_id=run_id,
                    window_start=window_start,
                    window_end=window_end,
                    modalidade_id=modalidade_id,
                    page_number=page_number,
                    raw_records=result.records,
                    pagination=pagination,
                    collected_at=datetime.now(UTC),
                    force_upsert_failure=(
                        fail_after_upsert_page is not None
                        and page_sequence == fail_after_upsert_page
                    ),
                )
                print(
                    f"PAGE modalidade={modalidade_id:02d} page={page_number}/{page_limit} "
                    f"records={len(result.records)} inserted={stats['page_inserted']} "
                    f"updated={stats['page_updated']} unchanged={stats['page_unchanged']} "
                    f"checkpoint=committed",
                    flush=True,
                )

                if stop_after_pages is not None and stats["pages_completed"] >= stop_after_pages:
                    _STOP_SIGNAL = signal.SIGTERM
                if _STOP_SIGNAL is not None:
                    return _mark_run(
                        conn,
                        run_id,
                        "interrupted",
                        f"signal={_STOP_SIGNAL}; checkpoint apos pagina atomica",
                    )

                page_number += 1
                if request_delay > 0:
                    time.sleep(request_delay)

        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(DISTINCT modalidade_id) FROM pncp_backfill_pages WHERE run_id = %s",
                (run_id,),
            )
            modalities_completed = int(cur.fetchone()[0])
        totals = _refresh_run_totals(conn, run_id)
        conn.commit()
        if modalities_completed != len(DEFAULT_MODALIDADES):
            raise BackfillError(
                f"modalidades incompletas: {modalities_completed}/{len(DEFAULT_MODALIDADES)}"
            )
        if totals["pages_completed"] != totals["pages_expected"]:
            raise BackfillError(
                f"paginas incompletas: {totals['pages_completed']}/{totals['pages_expected']}"
            )
        result = _mark_run(conn, run_id, "completed")
        print("COMPLETE " + json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
        return result
    except Exception as exc:
        conn.rollback()
        if run_id:
            result = _mark_run(conn, run_id, "failed", f"{type(exc).__name__}: {exc}")
        else:
            result = {"run_id": None, "status": "failed", "error_message": str(exc)}
        print("FAILED " + json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
        return result
    finally:
        signal.signal(signal.SIGTERM, previous_term)
        signal.signal(signal.SIGINT, previous_int)
        session.close()
        conn.close()


def _independent_response(
    session: requests.Session,
    *,
    params: dict[str, Any],
    request_delay: float,
    max_retries: int = 8,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Independent requests-based reference implementation."""
    url = f"{PNCP_CONSULTA_BASE}/contratacoes/publicacao"
    for attempt in range(max_retries + 1):
        response = session.get(url, params=params, timeout=(10, 120))
        if response.status_code in {408, 425, 429, 500, 502, 503, 504}:
            if attempt >= max_retries:
                raise BackfillError(
                    f"reconciliacao independente esgotou retries HTTP {response.status_code}"
                )
            retry_after = adapter._retry_after_seconds(response.headers.get("Retry-After"))  # noqa: SLF001
            wait = retry_after if retry_after is not None else min(60.0, 5.0 * (2**attempt))
            time.sleep(wait)
            continue
        if response.status_code == 204:
            return [], {
                "totalRegistros": 0,
                "totalPaginas": 0,
                "numeroPagina": int(params["pagina"]),
                "paginasRestantes": 0,
            }
        if response.status_code != 200:
            raise BackfillError(
                f"reconciliacao independente HTTP {response.status_code}: {response.text[:200]}"
            )
        if "json" not in response.headers.get("content-type", "").lower():
            raise BackfillError("reconciliacao independente recebeu Content-Type nao JSON")
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise BackfillError("reconciliacao independente recebeu schema invalido")
        pagination: dict[str, int] = {}
        for field in ("totalRegistros", "totalPaginas", "numeroPagina", "paginasRestantes"):
            value = payload.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise BackfillError(f"reconciliacao independente: {field} invalido")
            pagination[field] = value
        records = payload["data"]
        if any(not isinstance(row, dict) or not row.get("numeroControlePNCP") for row in records):
            raise BackfillError("reconciliacao independente encontrou chave natural ausente")
        if request_delay > 0:
            time.sleep(request_delay)
        return records, pagination
    raise BackfillError("reconciliacao independente falhou sem resposta")


def independent_source_snapshot(
    *,
    window_start: date,
    window_end: date,
    request_delay: float = 1.1,
) -> SourceSnapshot:
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/json",
            "User-Agent": "pncp-independent-reconciliation/1.0",
        }
    )
    ids: list[str] = []
    modalities: dict[int, dict[str, int]] = {}
    data_pages = 0
    requests_made = 0
    try:
        for modalidade_id in DEFAULT_MODALIDADES:
            page_number = 1
            seen = 0
            expected_records: int | None = None
            expected_pages: int | None = None
            while True:
                records, pagination = _independent_response(
                    session,
                    params={
                        "dataInicial": window_start.strftime("%Y%m%d"),
                        "dataFinal": window_end.strftime("%Y%m%d"),
                        "codigoModalidadeContratacao": modalidade_id,
                        "uf": "SC",
                        "pagina": page_number,
                        "tamanhoPagina": 50,
                    },
                    request_delay=request_delay,
                )
                requests_made += 1
                if expected_records is None:
                    expected_records = pagination["totalRegistros"]
                    expected_pages = pagination["totalPaginas"]
                if pagination["totalRegistros"] != expected_records:
                    raise BackfillError(
                        f"totalRegistros mudou modalidade={modalidade_id}"
                    )
                if pagination["totalPaginas"] != expected_pages:
                    raise BackfillError(f"totalPaginas mudou modalidade={modalidade_id}")
                seen += len(records)
                ids.extend(str(row["numeroControlePNCP"]) for row in records)
                if page_number >= max(1, expected_pages):
                    break
                page_number += 1
            if seen != expected_records:
                raise BackfillError(
                    f"contagem independente divergente modalidade={modalidade_id}: "
                    f"fonte={expected_records} percorrido={seen}"
                )
            data_pages += expected_pages or 0
            modalities[modalidade_id] = {
                "records": seen,
                "data_pages": expected_pages or 0,
                "requests": max(1, expected_pages or 0),
            }
            print(
                f"INDEPENDENT modalidade={modalidade_id:02d} records={seen} "
                f"data_pages={expected_pages or 0}",
                flush=True,
            )
    finally:
        session.close()

    counts = Counter(ids)
    duplicate_records = sum(count - 1 for count in counts.values() if count > 1)
    return SourceSnapshot(
        total_records=len(ids),
        unique_records=len(counts),
        duplicate_records=duplicate_records,
        duplicate_keys=sum(1 for count in counts.values() if count > 1),
        data_pages=data_pages,
        requests=requests_made,
        ids=ids,
        modalities=modalities,
    )


def reconcile_run(dsn: str, run_id: str, source: SourceSnapshot) -> dict[str, Any]:
    conn = _connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    r.pages_expected,
                    r.data_pages_expected,
                    r.pages_completed,
                    r.records_fetched,
                    r.unique_records,
                    COUNT(DISTINCT m.pncp_id),
                    COUNT(DISTINCT b.pncp_id)
                FROM pncp_backfill_runs r
                LEFT JOIN pncp_backfill_records m ON m.run_id = r.run_id
                LEFT JOIN pncp_raw_bids b ON b.pncp_id = m.pncp_id
                WHERE r.run_id = %s
                GROUP BY r.run_id
                """,
                (run_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise BackfillError(f"run inexistente: {run_id}")
            cur.execute(
                "SELECT DISTINCT pncp_id FROM pncp_backfill_records WHERE run_id = %s",
                (run_id,),
            )
            database_ids = {str(item[0]) for item in cur.fetchall()}
    finally:
        conn.close()

    source_ids = set(source.ids)
    missing = sorted(source_ids - database_ids)
    unexpected = sorted(database_ids - source_ids)
    result = {
        "run_id": run_id,
        "official_records": source.total_records,
        "official_unique": source.unique_records,
        "official_duplicate_records": source.duplicate_records,
        "official_duplicate_keys": source.duplicate_keys,
        "official_data_pages": source.data_pages,
        "official_requests": source.requests,
        "database_pages_expected": int(row[0]),
        "database_data_pages_expected": int(row[1]),
        "database_pages_completed": int(row[2]),
        "database_records_fetched": int(row[3]),
        "database_unique_records": int(row[4]),
        "membership_unique_records": int(row[5]),
        "database_joined_records": int(row[6]),
        "missing_count": len(missing),
        "unexpected_count": len(unexpected),
        "missing_sample": missing[:10],
        "unexpected_sample": unexpected[:10],
    }
    result["difference_unexplained"] = len(missing) + len(unexpected)
    result["reconciled"] = (
        result["database_pages_expected"] == source.requests
        and result["database_data_pages_expected"] == source.data_pages
        and result["database_pages_completed"] == source.requests
        and result["database_records_fetched"] == source.total_records
        and result["database_unique_records"] == source.unique_records
        and result["membership_unique_records"] == source.unique_records
        and result["database_joined_records"] == source.unique_records
        and result["difference_unexplained"] == 0
    )
    print("RECONCILIATION " + json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return result


def database_fingerprint(dsn: str) -> str:
    conn = _connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT pncp_id, content_hash, updated_at
                FROM pncp_raw_bids
                WHERE source = 'pncp'
                ORDER BY pncp_id
                """
            )
            digest = hashlib.sha256()
            for pncp_id, content_hash, updated_at in cur.fetchall():
                digest.update(f"{pncp_id}|{content_hash}|{updated_at.isoformat()}\n".encode())
            return digest.hexdigest()
    finally:
        conn.close()


def changed_records_between_runs(dsn: str, previous_run_id: str, current_run_id: str) -> list[dict[str, Any]]:
    conn = _connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH previous AS (
                    SELECT DISTINCT ON (pncp_id) pncp_id, content_hash, raw_payload
                    FROM pncp_backfill_records
                    WHERE run_id = %s
                    ORDER BY pncp_id, modalidade_id, page_number
                ),
                current AS (
                    SELECT DISTINCT ON (pncp_id) pncp_id, content_hash, raw_payload
                    FROM pncp_backfill_records
                    WHERE run_id = %s
                    ORDER BY pncp_id, modalidade_id, page_number
                )
                SELECT
                    current.pncp_id,
                    previous.content_hash,
                    current.content_hash,
                    previous.raw_payload,
                    current.raw_payload
                FROM current
                JOIN previous USING (pncp_id)
                WHERE current.content_hash IS DISTINCT FROM previous.content_hash
                ORDER BY current.pncp_id
                """,
                (previous_run_id, current_run_id),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    changed: list[dict[str, Any]] = []
    for pncp_id, previous_hash, current_hash, previous_payload, current_payload in rows:
        previous_payload = previous_payload or {}
        current_payload = current_payload or {}
        fields = sorted(
            key
            for key in set(previous_payload) | set(current_payload)
            if previous_payload.get(key) != current_payload.get(key)
        )
        changed.append(
            {
                "pncp_id": str(pncp_id),
                "previous_hash": str(previous_hash),
                "current_hash": str(current_hash),
                "changed_fields": fields,
            }
        )
    return changed


class _FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: Any = None,
        *,
        headers: dict[str, str] | None = None,
        json_error: Exception | None = None,
    ):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self._json_error = json_error
        self.text = ""

    def json(self) -> Any:
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse]):
        self.responses = list(responses)
        self.calls = 0

    def get(self, *_args: Any, **_kwargs: Any) -> _FakeResponse:
        self.calls += 1
        return self.responses.pop(0)

    def close(self) -> None:
        return None


def run_fault_checks() -> dict[str, Any]:
    valid_empty = {
        "data": [],
        "totalRegistros": 0,
        "totalPaginas": 0,
        "numeroPagina": 1,
        "paginasRestantes": 0,
        "empty": True,
    }

    sleeps_500: list[float] = []
    session_500 = _FakeSession(
        [
            _FakeResponse(500, headers={"content-type": "application/json"}),
            _FakeResponse(200, valid_empty, headers={"content-type": "application/json"}),
        ]
    )
    result_500 = adapter._http_get_json(  # noqa: SLF001
        "https://pncp.test/500",
        session=session_500,  # type: ignore[arg-type]
        sleeper=sleeps_500.append,
    )
    if result_500.errors or session_500.calls != 2 or len(sleeps_500) != 1:
        raise BackfillError("falha no cenário 500 -> retry -> sucesso")

    sleeps_429: list[float] = []
    session_429 = _FakeSession(
        [
            _FakeResponse(
                429,
                headers={"content-type": "text/html", "Retry-After": "7"},
            ),
            _FakeResponse(200, valid_empty, headers={"content-type": "application/json"}),
        ]
    )
    result_429 = adapter._http_get_json(  # noqa: SLF001
        "https://pncp.test/429",
        session=session_429,  # type: ignore[arg-type]
        sleeper=sleeps_429.append,
    )
    if result_429.errors or sleeps_429 != [7.0]:
        raise BackfillError("falha no cenário 429 Retry-After")

    invalid_json = requests.exceptions.JSONDecodeError("invalid", "{", 1)
    session_json = _FakeSession(
        [
            _FakeResponse(
                200,
                headers={"content-type": "application/json"},
                json_error=invalid_json,
            )
        ]
    )
    result_json = adapter._http_get_json(  # noqa: SLF001
        "https://pncp.test/json",
        session=session_json,  # type: ignore[arg-type]
        sleeper=lambda _seconds: None,
    )
    if not result_json.errors or session_json.calls != 1:
        raise BackfillError("JSON invalido foi repetido ou aceito")

    session_schema = _FakeSession(
        [_FakeResponse(200, {"unexpected": []}, headers={"content-type": "application/json"})]
    )
    result_schema = adapter._http_get_json(  # noqa: SLF001
        "https://pncp.test/schema",
        session=session_schema,  # type: ignore[arg-type]
        sleeper=lambda _seconds: None,
    )
    if not result_schema.errors or session_schema.calls != 1:
        raise BackfillError("schema invalido foi repetido ou aceito")

    result = {
        "http_500": {"calls": session_500.calls, "retry_delays": sleeps_500, "success": True},
        "http_429": {"calls": session_429.calls, "retry_delays": sleeps_429, "success": True},
        "invalid_json": {"calls": session_json.calls, "page_completed": False, "success": True},
        "invalid_schema": {
            "calls": session_schema.calls,
            "page_completed": False,
            "success": True,
        },
    }
    print("FAULT_CHECKS " + json.dumps(result, sort_keys=True), flush=True)
    return result


def run_upsert_failure_check(
    *,
    dsn: str,
    window_start: date,
    window_end: date,
) -> dict[str, Any]:
    """Force a PostgreSQL error after upsert and resume from the prior page."""
    conn = _connect(dsn)
    run_id = _new_run(conn, window_start, window_end)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT raw_payload
                FROM pncp_raw_bids
                WHERE source = 'pncp'
                  AND modalidade_id = 8
                  AND raw_payload IS NOT NULL
                ORDER BY pncp_id
                LIMIT 120
                """
            )
            raw_records = [row[0] for row in cur.fetchall()]
        if len(raw_records) != 120:
            raise BackfillError(
                f"cenário G requer 120 registros reais da modalidade 8; encontrou {len(raw_records)}"
            )

        pages = [raw_records[index : index + 50] for index in range(0, len(raw_records), 50)]
        fingerprint_before = database_fingerprint(dsn)
        _persist_page(
            conn,
            run_id=run_id,
            window_start=window_start,
            window_end=window_end,
            modalidade_id=8,
            page_number=1,
            raw_records=pages[0],
            pagination={
                "totalRegistros": len(raw_records),
                "totalPaginas": len(pages),
                "numeroPagina": 1,
                "paginasRestantes": len(pages) - 1,
            },
            collected_at=datetime.now(UTC),
        )
        try:
            _persist_page(
                conn,
                run_id=run_id,
                window_start=window_start,
                window_end=window_end,
                modalidade_id=8,
                page_number=2,
                raw_records=pages[1],
                pagination={
                    "totalRegistros": len(raw_records),
                    "totalPaginas": len(pages),
                    "numeroPagina": 2,
                    "paginasRestantes": len(pages) - 2,
                },
                collected_at=datetime.now(UTC),
                force_upsert_failure=True,
            )
        except psycopg2.Error as exc:
            failed = _mark_run(conn, run_id, "failed", f"{type(exc).__name__}: {exc}")
        else:
            raise BackfillError("cenário G não produziu falha PostgreSQL")

        if failed["pages_completed"] != 1 or failed["records_fetched"] != 50:
            raise BackfillError("cenário G perdeu ou avançou além da página anterior")

        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE pncp_backfill_runs
                SET status = 'running', completed_at = NULL, error_message = NULL
                WHERE run_id = %s
                """,
                (run_id,),
            )
        conn.commit()

        completed = _completed_pages(conn, run_id, 8)
        for page_number, records in enumerate(pages, start=1):
            if page_number in completed:
                continue
            _persist_page(
                conn,
                run_id=run_id,
                window_start=window_start,
                window_end=window_end,
                modalidade_id=8,
                page_number=page_number,
                raw_records=records,
                pagination={
                    "totalRegistros": len(raw_records),
                    "totalPaginas": len(pages),
                    "numeroPagina": page_number,
                    "paginasRestantes": len(pages) - page_number,
                },
                collected_at=datetime.now(UTC),
            )
        resumed = _mark_run(conn, run_id, "completed")
        fingerprint_after = database_fingerprint(dsn)
        if (
            resumed["pages_completed"] != len(pages)
            or resumed["records_fetched"] != len(raw_records)
            or fingerprint_before != fingerprint_after
        ):
            raise BackfillError("cenário G não retomou de forma idempotente")

        result = {
            "run_id": run_id,
            "failed_pages_completed": failed["pages_completed"],
            "failed_records_persisted": failed["records_fetched"],
            "resumed_pages_completed": resumed["pages_completed"],
            "resumed_records_fetched": resumed["records_fetched"],
            "fingerprint_unchanged": True,
            "status": "completed",
        }
        print("UPSERT_FAILURE_CHECK " + json.dumps(result, sort_keys=True), flush=True)
        return result
    finally:
        conn.close()


def _acceptance_child(
    dsn: str,
    window_start: date,
    window_end: date,
    request_delay: float,
) -> None:
    result = execute_backfill(
        dsn=dsn,
        window_start=window_start,
        window_end=window_end,
        request_delay=request_delay,
    )
    raise SystemExit(0 if result["status"] == "completed" else 130 if result["status"] == "interrupted" else 1)


def _latest_run_progress(dsn: str, window_start: date, window_end: date) -> tuple[str | None, int]:
    conn = _connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT run_id, pages_completed
                FROM pncp_backfill_runs
                WHERE window_start = %s AND window_end = %s
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (window_start, window_end),
            )
            row = cur.fetchone()
            return (str(row[0]), int(row[1])) if row else (None, 0)
    finally:
        conn.close()


def run_acceptance(
    *,
    dsn: str,
    window_start: date,
    window_end: date,
    request_delay: float,
) -> dict[str, Any]:
    """Execute scenarios A-G with real PNCP/PostgreSQL and simulated HTTP faults."""
    results: dict[str, Any] = {}

    prepare_clean_database(dsn)
    scenario_a = execute_backfill(
        dsn=dsn,
        window_start=window_start,
        window_end=window_end,
        request_delay=request_delay,
    )
    if scenario_a["status"] != "completed":
        raise BackfillError("cenário A falhou")
    results["A_empty_database"] = scenario_a

    prepare_clean_database(dsn)
    kill_target = max(2, scenario_a["pages_expected"] // 2)
    child = multiprocessing.Process(
        target=_acceptance_child,
        args=(dsn, window_start, window_end, request_delay),
    )
    child.start()
    child_run_id: str | None = None
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        child_run_id, pages_completed = _latest_run_progress(dsn, window_start, window_end)
        if pages_completed >= kill_target:
            os.kill(child.pid, signal.SIGTERM)
            break
        if not child.is_alive():
            break
        time.sleep(0.25)
    child.join(timeout=180)
    if child.is_alive():
        child.terminate()
        child.join(timeout=30)
        raise BackfillError("processo de kill/resume nao encerrou")
    if child_run_id is None or child.exitcode != 130:
        raise BackfillError(
            f"interrupcao esperada exit=130, obtido exit={child.exitcode} run={child_run_id}"
        )
    interrupted_run, interrupted_pages = _latest_run_progress(dsn, window_start, window_end)
    resumed = execute_backfill(
        dsn=dsn,
        window_start=window_start,
        window_end=window_end,
        resume=True,
        request_delay=request_delay,
    )
    if resumed["status"] != "completed" or resumed["run_id"] != interrupted_run:
        raise BackfillError("cenário B nao retomou a mesma execucao")
    results["B_kill_resume"] = {
        "run_id": interrupted_run,
        "exit_code": child.exitcode,
        "pages_before_resume": interrupted_pages,
        "resumed": resumed,
    }

    fingerprint_before = database_fingerprint(dsn)
    scenario_c = execute_backfill(
        dsn=dsn,
        window_start=window_start,
        window_end=window_end,
        request_delay=request_delay,
    )
    for _attempt in range(2):
        if scenario_c["status"] != "failed":
            break
        scenario_c = execute_backfill(
            dsn=dsn,
            window_start=window_start,
            window_end=window_end,
            resume=True,
            request_delay=request_delay,
        )
    fingerprint_after = database_fingerprint(dsn)
    changed_records = changed_records_between_runs(
        dsn,
        resumed["run_id"],
        scenario_c["run_id"],
    )
    if (
        scenario_c["status"] != "completed"
        or scenario_c["inserted"] != 0
        or scenario_c["updated"] != len(changed_records)
        or (not changed_records and fingerprint_before != fingerprint_after)
    ):
        raise BackfillError("cenário C violou idempotencia")
    results["C_second_run"] = {
        **scenario_c,
        "changed_records": changed_records,
        "unexplained_updates": scenario_c["updated"] - len(changed_records),
        "fingerprint_unchanged": fingerprint_before == fingerprint_after,
    }

    fault_results = run_fault_checks()
    results["D_500"] = fault_results["http_500"]
    results["E_429"] = fault_results["http_429"]
    results["F_invalid_payload"] = {
        "invalid_json": fault_results["invalid_json"],
        "invalid_schema": fault_results["invalid_schema"],
    }

    results["G_upsert_resume"] = run_upsert_failure_check(
        dsn=dsn,
        window_start=window_start,
        window_end=window_end,
    )

    source = independent_source_snapshot(
        window_start=window_start,
        window_end=window_end,
        request_delay=request_delay,
    )
    reconciliation = reconcile_run(dsn, scenario_c["run_id"], source)
    if not reconciliation["reconciled"]:
        raise BackfillError("reconciliacao final divergiu")
    results["reconciliation"] = reconciliation
    results["status"] = "completed"
    print("ACCEPTANCE " + json.dumps(results, ensure_ascii=False, sort_keys=True), flush=True)
    return results


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use YYYY-MM-DD") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PNCP SC resumable seven-day backfill")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(target: argparse.ArgumentParser) -> None:
        target.add_argument("--dsn", required=True)
        target.add_argument("--date-from", required=True, type=_parse_date)
        target.add_argument("--date-to", required=True, type=_parse_date)
        target.add_argument("--request-delay", type=float, default=1.1)

    run_parser = subparsers.add_parser("run", help="execute or resume one backfill")
    add_common(run_parser)
    run_parser.add_argument("--prepare-clean", action="store_true")
    run_parser.add_argument("--resume", action="store_true")
    run_parser.add_argument("--reconcile", action="store_true")
    run_parser.add_argument("--stop-after-pages", type=int, default=None, help=argparse.SUPPRESS)
    run_parser.add_argument("--fail-after-upsert-page", type=int, default=None, help=argparse.SUPPRESS)

    acceptance_parser = subparsers.add_parser("acceptance", help="execute scenarios A-G")
    add_common(acceptance_parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _validate_window(args.date_from, args.date_to)
        if args.command == "acceptance":
            run_acceptance(
                dsn=args.dsn,
                window_start=args.date_from,
                window_end=args.date_to,
                request_delay=args.request_delay,
            )
            return 0

        if args.prepare_clean:
            prepare_clean_database(args.dsn)
        result = execute_backfill(
            dsn=args.dsn,
            window_start=args.date_from,
            window_end=args.date_to,
            resume=args.resume,
            request_delay=args.request_delay,
            stop_after_pages=args.stop_after_pages,
            fail_after_upsert_page=args.fail_after_upsert_page,
        )
        if result["status"] != "completed":
            return 130 if result["status"] == "interrupted" else 1
        if args.reconcile:
            source = independent_source_snapshot(
                window_start=args.date_from,
                window_end=args.date_to,
                request_delay=args.request_delay,
            )
            reconciliation = reconcile_run(args.dsn, result["run_id"], source)
            if not reconciliation["reconciled"]:
                return 2
        return 0
    except BackfillError as exc:
        print(f"ERROR {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
