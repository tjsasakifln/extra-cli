#!/usr/bin/env python3
"""Backfill municipio for SC Dados Abertos contracts (COVERAGE-1.9).

Enriches 75.523 contracts in ``pncp_supplier_contracts`` where
``source = 'sc_dados_abertos'`` and ``municipio IS NULL``.

Inference cascade:
    1. sc_public_entities  — match by LEFT(orgao_cnpj, 8) (fast, local)
    2. Brasil API           — consult https://brasilapi.com.br/api/cnpj/v1/{cnpj}
    3. Local cache          — ``data/cnpj_cache.json``

Usage:
    python scripts/fix/sc_dados_abertos_backfill.py --dry-run
    python scripts/fix/sc_dados_abertos_backfill.py --commit
    python scripts/fix/sc_dados_abertos_backfill.py --report-only
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg2
import requests

# Ensure project root is on sys.path so that config.settings is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.settings import DATA_DIR, DEFAULT_DSN  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CACHE_FILE = DATA_DIR / "cnpj_cache.json"
BRASIL_API_URL = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"
BRASIL_API_RATE_LIMIT = 2.0  # 2 requests per second
SAVE_CACHE_EVERY = 50  # persist cache every N external API calls

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

log = logging.getLogger("sc_dados_abertos_backfill")


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, stream=sys.stderr)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def load_cnpj_cache() -> dict[str, Any]:
    """Load CNPJ cache from ``data/cnpj_cache.json``.

    Returns:
        Empty dict if file missing or malformed.
    """
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE) as f:
                data: dict = json.load(f)
            log.info("Cache loaded: %d CNPJs", len(data))
            return data
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Cache file corrupt (%s), starting fresh", exc)
    return {}


def save_cnpj_cache(cache: dict[str, Any]) -> None:
    """Persist CNPJ cache to disk."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    log.info("Cache saved: %d CNPJs", len(cache))


# ---------------------------------------------------------------------------
# CNPJ helpers
# ---------------------------------------------------------------------------


def _clean_cnpj(raw: str) -> str:
    """Strip non-digit characters from a CNPJ string."""
    return re.sub(r"\D", "", raw)


# ---------------------------------------------------------------------------
# Brasil API
# ---------------------------------------------------------------------------


def consultar_brasil_api(
    cnpj: str,
    cache: dict[str, Any],
    last_request_time: list[float],
) -> dict[str, Any] | None:
    """Consult Brasil API for CNPJ data with rate-limiting and caching.

    Args:
        cnpj: Full CNPJ (14 digits, with or without mask).
        cache: Shared cache dictionary (mutated in-place).
        last_request_time: One-element list ``[timestamp]`` tracking last API call.

    Returns:
        Dict with ``municipio``, ``codigo_ibge``, ``uf``, ``cached_at``,
        or ``None`` on failure.
    """
    cnpj_clean = _clean_cnpj(cnpj)

    # --- Level 3: cache check (before network) ---
    cached = cache.get(cnpj_clean)
    if cached is not None:
        log.debug("Cache hit: %s -> %s", cnpj_clean, cached.get("municipio"))
        return cached

    # --- Rate limit ---
    elapsed = time.time() - last_request_time[0]
    min_interval = 1.0 / BRASIL_API_RATE_LIMIT
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)

    # --- HTTP call ---
    url = BRASIL_API_URL.format(cnpj=cnpj_clean)
    try:
        resp = requests.get(url, timeout=10)
    except requests.exceptions.ConnectionError:
        log.error("Brasil API connection error — skipping %s", cnpj_clean)
        return None
    except requests.exceptions.Timeout:
        log.error("Brasil API timeout — skipping %s", cnpj_clean)
        return None
    except Exception as exc:
        log.error("Unexpected error consulting %s: %s", cnpj_clean, exc)
        return None
    finally:
        last_request_time[0] = time.time()

    # --- Response handling ---
    if resp.status_code == 200:
        data = resp.json()
        result = {
            "municipio": data.get("municipio"),
            "codigo_ibge": str(data.get("codigo_municipio_ibge", "") or ""),
            "uf": data.get("uf"),
            "cached_at": datetime.now().isoformat(),
        }
        cache[cnpj_clean] = result
        return result

    if resp.status_code == 429:
        log.warning("Rate limit (429) for %s, backing off 5s…", cnpj_clean)
        time.sleep(5)
        return consultar_brasil_api(cnpj, cache, last_request_time)  # retry

    if resp.status_code == 404:
        log.debug("CNPJ not found at Brasil API: %s", cnpj_clean)
        cache[cnpj_clean] = None  # negative cache
        return None

    log.warning("Brasil API HTTP %d for %s", resp.status_code, cnpj_clean)
    return None


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------


def infer_municipio_from_cnpj(
    orgao_cnpj: str,
    conn: psycopg2.extensions.connection,
    cache: dict[str, Any],
    last_request_time: list[float],
) -> dict[str, Any] | None:
    """Infer municipality for a contracting authority CNPJ.

    Levels:
        1. ``sc_public_entities`` match by 8-digit CNPJ root.
        2. Brasil API query.
        3. Local cache (checked inside ``consultar_brasil_api``).

    Returns:
        Dict with ``municipio``, ``codigo_ibge``, ``match_method``,
        or ``None`` if inference failed.
    """
    cnpj_clean = _clean_cnpj(orgao_cnpj)
    if len(cnpj_clean) < 8:
        log.warning("Invalid CNPJ (fewer than 8 digits): %s", orgao_cnpj)
        return None

    cnpj_8 = cnpj_clean[:8]

    # --- Level 1: sc_public_entities (local, fast) ---
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT municipio, codigo_ibge
                FROM sc_public_entities
                WHERE cnpj_8 = %s AND is_active = TRUE
                LIMIT 1
                """,
                (cnpj_8,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "municipio": row[0],
                    "codigo_ibge": row[1],
                    "match_method": "sc_public_entities",
                }
    except Exception as exc:
        log.error("DB error querying sc_public_entities for %s: %s", cnpj_8, exc)

    # --- Level 2: Brasil API ---
    try:
        api_result = consultar_brasil_api(cnpj_clean, cache, last_request_time)
        if api_result and api_result.get("municipio"):
            return {
                "municipio": api_result["municipio"],
                "codigo_ibge": api_result.get("codigo_ibge", ""),
                "match_method": "brasil_api",
            }
    except Exception as exc:
        log.error("Brasil API exception for %s: %s", cnpj_clean, exc)

    return None  # could not infer


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


def _log_attempt(
    conn: psycopg2.extensions.connection,
    orgao_cnpj: str,
    match_method: str | None,
    municipio: str | None,
    codigo_ibge: str | None,
    motivo: str,
) -> None:
    """Insert a row into the audit log table."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sc_dados_abertos_backfill_log
                    (orgao_cnpj, match_method, municipio, codigo_ibge, motivo)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (orgao_cnpj, match_method, municipio, codigo_ibge, motivo),
            )
    except Exception as exc:
        log.warning("Failed to write audit log for %s: %s", orgao_cnpj, exc)


# ---------------------------------------------------------------------------
# Backfill engine
# ---------------------------------------------------------------------------

BACKFILL_COLUMNS = ("municipio", "codigo_municipio_ibge")


def run_backfill(dry_run: bool = True) -> dict[str, Any]:
    """Execute the municipio backfill for SC Dados Abertos contracts.

    Args:
        dry_run: If ``True``, roll back all changes at the end (safe mode).

    Returns:
        Dict with execution statistics.
    """
    stats: dict[str, Any] = {
        "total_contratos": 0,
        "orgaos_distintos": 0,
        "level1_match": 0,
        "level2_api": 0,
        "failed": 0,
        "updated_contratos": 0,
        "errors": 0,
        "api_calls": 0,
        "cache_hits": 0,
    }

    conn = psycopg2.connect(DEFAULT_DSN)
    cache = load_cnpj_cache()
    last_request_time = [0.0]
    api_call_count = [0]

    try:
        # --- Fetch contracts missing municipio ---
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, orgao_cnpj, orgao_nome
                FROM pncp_supplier_contracts
                WHERE source = 'sc_dados_abertos'
                  AND municipio IS NULL
                ORDER BY id
                """
            )
            rows = cur.fetchall()

        stats["total_contratos"] = len(rows)
        log.info("Processing %d contracts without municipio…", len(rows))

        # --- Group by unique CNPJ ---
        orgaos_unicos: dict[str, list[int]] = {}
        for row in rows:
            cnpj = row[1]
            orgaos_unicos.setdefault(cnpj, []).append(row[0])

        stats["orgaos_distintos"] = len(orgaos_unicos)
        log.info("Unique CNPJs to resolve: %d", len(orgaos_unicos))

        # --- Resolve each CNPJ ---
        municipio_por_cnpj: dict[str, dict[str, Any]] = {}
        for idx, (cnpj, ids) in enumerate(orgaos_unicos.items(), start=1):
            log.info(
                "[%d/%d] CNPJ %s (%d contracts)",
                idx,
                len(orgaos_unicos),
                cnpj,
                len(ids),
            )

            result = infer_municipio_from_cnpj(
                cnpj,
                conn,
                cache,
                last_request_time,
            )

            if result:
                method = result["match_method"]
                municipio_por_cnpj[cnpj] = result

                if method == "sc_public_entities":
                    stats["level1_match"] += 1
                else:
                    stats["level2_api"] += 1
                    api_call_count[0] += 1

                _log_attempt(
                    conn,
                    cnpj,
                    method,
                    result["municipio"],
                    result["codigo_ibge"],
                    "success",
                )

                # Save cache periodically
                if api_call_count[0] > 0 and api_call_count[0] % SAVE_CACHE_EVERY == 0:
                    save_cnpj_cache(cache)
            else:
                stats["failed"] += 1
                log.warning("Failed to infer municipio for CNPJ %s", cnpj)
                _log_attempt(conn, cnpj, None, None, None, "inference_failed")

        # --- Execute UPDATE ---
        if municipio_por_cnpj:
            updated_count = 0
            with conn.cursor() as cur:
                for cnpj, info in municipio_por_cnpj.items():
                    ids = orgaos_unicos[cnpj]
                    cur.execute(
                        """
                        UPDATE pncp_supplier_contracts
                        SET municipio = %s,
                            codigo_municipio_ibge = %s,
                            municipio_inferido = TRUE
                        WHERE id = ANY(%s::bigint[])
                          AND source = 'sc_dados_abertos'
                          AND municipio IS NULL
                        """,
                        (info["municipio"], info["codigo_ibge"], ids),
                    )
                    updated_count += len(ids)

            stats["updated_contratos"] = updated_count
            log.info(
                "Contracts updated: %d (%s)",
                updated_count,
                "DRY-RUN (will rollback)" if dry_run else "COMMITTED",
            )

        # --- Commit or rollback ---
        if dry_run:
            conn.rollback()
            log.info("DRY-RUN: rolled back — no changes persisted")
        else:
            conn.commit()
            log.info("COMMIT: changes persisted")
            stats["api_calls"] = api_call_count[0]

        # Always save cache (even on dry-run — we still did API calls)
        if api_call_count[0] > 0:
            save_cnpj_cache(cache)

    except Exception:
        log.exception("Fatal error in backfill")
        conn.rollback()
        stats["errors"] += 1
    finally:
        conn.close()

    return stats


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def generate_report() -> dict[str, Any]:
    """Query the current state of contracts and backfill log.

    Returns:
        Dict with summary stats.
    """
    conn = psycopg2.connect(DEFAULT_DSN)
    try:
        with conn.cursor() as cur:
            # Contract-level summary
            cur.execute(
                """
                SELECT
                    COUNT(*)                                           AS total,
                    COUNT(municipio)                                   AS com_municipio,
                    COUNT(CASE WHEN municipio IS NULL THEN 1 END)      AS sem_municipio,
                    ROUND(100.0 * COUNT(municipio) / GREATEST(COUNT(*), 1), 1)
                                                                       AS pct_com_municipio,
                    COUNT(DISTINCT CASE WHEN municipio IS NOT NULL
                                           THEN orgao_cnpj END)        AS orgaos_fixed,
                    COUNT(DISTINCT CASE WHEN municipio IS NULL
                                           THEN orgao_cnpj END)        AS orgaos_failed
                FROM pncp_supplier_contracts
                WHERE source = 'sc_dados_abertos'
                """
            )
            row = cur.fetchone()
            summary = {
                "total": row[0],
                "com_municipio": row[1],
                "sem_municipio": row[2],
                "pct_com_municipio": row[3],
                "orgaos_fixed": row[4],
                "orgaos_failed": row[5],
            }

            # Audit log breakdown
            cur.execute(
                """
                SELECT motivo, COUNT(*) AS qtd
                FROM sc_dados_abertos_backfill_log
                GROUP BY motivo
                ORDER BY qtd DESC
                """
            )
            log_breakdown = {row[0]: row[1] for row in cur.fetchall()}

            # Diagnosis: match rate vs sc_public_entities
            cur.execute(
                """
                WITH orgaos AS (
                    SELECT DISTINCT orgao_cnpj
                    FROM pncp_supplier_contracts
                    WHERE source = 'sc_dados_abertos' AND municipio IS NULL
                ),
                matches AS (
                    SELECT o.orgao_cnpj,
                           CASE WHEN e.id IS NOT NULL THEN 1 ELSE 0 END AS matched
                    FROM orgaos o
                    LEFT JOIN sc_public_entities e
                        ON LEFT(o.orgao_cnpj, 8) = e.cnpj_8
                )
                SELECT COUNT(*)          AS total_orgaos,
                       SUM(matched)      AS matched,
                       ROUND(100.0 * SUM(matched) / GREATEST(COUNT(*), 1), 1) AS match_pct
                FROM matches
                """
            )
            diag_row = cur.fetchone()
            summary["diagnosis"] = {
                "total_orgaos": diag_row[0],
                "matched_orgaos": diag_row[1],
                "match_pct": diag_row[2],
            }

            summary["log_breakdown"] = log_breakdown
            return summary
    finally:
        conn.close()


def print_report(summary: dict[str, Any]) -> None:
    """Pretty-print the report to stdout."""
    sep = "=" * 62
    print()
    print(sep)
    print("  COVERAGE-1.9 — SC Dados Abertos Municipio Backfill Report")
    print(sep)
    print()
    print(f"  Total contracts (sc_dados_abertos):  {summary['total']}")
    print(f"  With municipio:                      {summary['com_municipio']}")
    print(f"  Without municipio:                   {summary['sem_municipio']}")
    print(f"  Coverage:                            {summary['pct_com_municipio']}%")
    print()

    if "diagnosis" in summary:
        d = summary["diagnosis"]
        print("  Diagnosis (remaining null contracts):")
        print(f"    Distinct CNPJs:         {d['total_orgaos']}")
        print(f"    Matchable (sc_entities): {d['matched_orgaos']} ({d['match_pct']}%)")
        print()

    if "log_breakdown" in summary and summary["log_breakdown"]:
        print("  Backfill Log Breakdown:")
        for motivo, qtd in summary["log_breakdown"].items():
            print(f"    {motivo}: {qtd}")
        print()

    print(sep)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="COVERAGE-1.9: Backfill municipio for SC Dados Abertos contracts",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Dry-run mode (default): no changes persisted",
    )
    mode.add_argument(
        "--commit",
        action="store_true",
        help="Persist changes to database",
    )
    mode.add_argument(
        "--report-only",
        action="store_true",
        help="Query current state and print report, no backfill",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _setup_logging(args.verbose)

    log.info("COVERAGE-1.9 — SC Dados Abertos Municipio Backfill")
    log.info("Mode: %s", "commit" if args.commit else "report-only" if args.report_only else "dry-run")

    if args.report_only:
        report = generate_report()
        print_report(report)
        return 0

    dry_run = not args.commit
    stats = run_backfill(dry_run=dry_run)

    # Print summary
    print()
    print("=" * 55)
    print("  Backfill Execution Summary")
    print("=" * 55)
    print(f"  Total contracts processed:  {stats['total_contratos']}")
    print(f"  Unique CNPJs resolved:      {stats['orgaos_distintos']}")
    print(f"  Level 1 (sc_entities):      {stats['level1_match']}")
    print(f"  Level 2 (Brasil API):       {stats['level2_api']}")
    print(f"  Failed:                     {stats['failed']}")
    print(f"  Contracts updated:          {stats['updated_contratos']}")
    print(f"  Errors:                     {stats['errors']}")
    print()

    if dry_run:
        print("  ** DRY-RUN ** — no changes persisted.")
    else:
        print("  Changes COMMITTED to database.")

    final_report = generate_report()
    print_report(final_report)

    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
