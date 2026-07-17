#!/usr/bin/env python3
"""MiDES BigQuery Crawler — Extra Consultoria.

Source: Google BigQuery public dataset ``basedosdados.world_wb_mides``
(mantido pelo Ministerio da Defesa / World Bank).

Dataset contem dados de execucao orcamentaria (empenhos) de todos os estados
brasileiros. Para Santa Catarina, cobre **276 municipios** (93% dos 295) com
dados de 2021-2024.

Estrategia:
    A tabela ``licitacao`` nao possui registros de SC (dados de licitacao).
    A tabela ``empenho`` possui ~7.6M registros de SC com ``id_municipio``
    (codigo IBGE de 7 digitos), ``descricao`` do objeto, ``valor_final`` e
    metadados de execucao orcamentaria.

    O mapeamento para ``pncp_raw_bids`` usa:
        - ``id_municipio`` → ``codigo_municipio_ibge`` (entity matching via IBGE)
        - ``descricao`` → ``objeto_compra``
        - ``valor_final`` → ``valor_total_estimado``
        - Nomes de municipio resolvidos via tabela ``br_bd_diretorios_brasil.municipio``

Integration with monitor.py::
    crawl(mode) -> list[dict]
    transform(records) -> list[dict]

Usage:
    python -m scripts.crawl.mides_bigquery_crawler --dry-run
    python -m scripts.crawl.mides_bigquery_crawler --mode full
    python -m scripts.crawl.mides_bigquery_crawler --mode incremental
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
from pathlib import Path
from typing import Any

# Project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ID = "basedosdados"
DATASET_ID = "world_wb_mides"
TABLE_EMPENHO = "empenho"
TABLE_MUNICIPIO_REF = "br_bd_diretorios_brasil.municipio"

# SC coverage window
COVERAGE_YEARS = [2021, 2022, 2023, 2024]
SOURCE_TAG = "mides-bigquery"

# Chunking: rows per query (BQ limits: 16MB response per row set, 1GB max)
ROWS_PER_CHUNK = 250_000

# Cost control: maximum bytes processed per query (100 GB = ~10% free tier/month)
MAX_BYTES_PER_QUERY = 100 * 1024 * 1024 * 1024  # 100 GB


# ---------------------------------------------------------------------------
# BigQuery client
# ---------------------------------------------------------------------------


def _get_bq_client() -> Any:
    """Get a BigQuery client using GOOGLE_APPLICATION_CREDENTIALS."""
    from google.cloud import bigquery

    return bigquery.Client(project="pncp-monitor")


# ---------------------------------------------------------------------------
# Municipality name cache
# ---------------------------------------------------------------------------

_MUNICIPIO_CACHE: dict[str, str] | None = None


def _load_municipio_cache(client: Any = None) -> dict[str, str]:
    """Load IBGE code -> municipality name mapping for SC.

    Uses the `br_bd_diretorios_brasil.municipio` reference table.
    Returns dict of {id_municipio_7digits: nome_municipio}.
    """
    global _MUNICIPIO_CACHE
    if _MUNICIPIO_CACHE is not None:
        return _MUNICIPIO_CACHE

    if client is None:
        client = _get_bq_client()

    query = f"""
    SELECT id_municipio, nome
    FROM `{PROJECT_ID}.{TABLE_MUNICIPIO_REF}`
    WHERE sigla_uf = 'SC'
    """  # noqa: S608 -- internal constants only, no user input
    cache: dict[str, str] = {}
    try:
        rows = client.query(query).result()
        for row in rows:
            cache[str(row.id_municipio)] = row.nome
        _logger.info("Loaded %d SC municipality names", len(cache))
    except Exception as e:
        _logger.warning("Failed to load municipio cache: %s", e)

    _MUNICIPIO_CACHE = cache
    return cache


# ---------------------------------------------------------------------------
# Query building
# ---------------------------------------------------------------------------


def build_sc_query(
    year: int,
    limit: int | None = None,
    offset: int | None = None,
) -> str:
    """Build a query to fetch SC empenho records for a given year.

    Args:
        year: Year to filter (2021-2024).
        limit: Optional LIMIT clause.
        offset: Optional OFFSET clause.

    Returns:
        SQL query string.
    """
    sql = f"""
    SELECT
        ano,
        mes,
        data,
        sigla_uf,
        id_municipio,
        orgao,
        id_unidade_gestora,
        id_licitacao_bd,
        id_licitacao,
        modalidade_licitacao,
        id_empenho_bd,
        id_empenho,
        numero,
        descricao,
        modalidade,
        funcao,
        subfuncao,
        programa,
        acao,
        elemento_despesa,
        valor_inicial,
        valor_reforco,
        valor_anulacao,
        valor_ajuste,
        valor_final
    FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_EMPENHO}`
    WHERE sigla_uf = 'SC'
      AND ano = {year}
      AND id_municipio IS NOT NULL
    ORDER BY ano, mes, id_municipio, numero
    """  # noqa: S608 -- internal constants only, no user input
    if limit is not None:
        sql += f"\n    LIMIT {limit}"
    if offset is not None:
        sql += f"\n    OFFSET {offset}"
    return sql


def build_incremental_query(days_back: int = 90) -> str:
    """Build a query for incremental (recent) data.

    Args:
        days_back: How many days of history to fetch.

    Returns:
        SQL query string.
    """
    return f"""
    SELECT
        ano,
        mes,
        data,
        sigla_uf,
        id_municipio,
        orgao,
        id_unidade_gestora,
        id_licitacao_bd,
        id_licitacao,
        modalidade_licitacao,
        id_empenho_bd,
        id_empenho,
        numero,
        descricao,
        modalidade,
        funcao,
        subfuncao,
        programa,
        acao,
        elemento_despesa,
        valor_inicial,
        valor_reforco,
        valor_anulacao,
        valor_ajuste,
        valor_final
    FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_EMPENHO}`
    WHERE sigla_uf = 'SC'
      AND data >= DATE_SUB(CURRENT_DATE(), INTERVAL {days_back} DAY)
      AND id_municipio IS NOT NULL
    ORDER BY data, id_municipio, numero
    """  # noqa: S608 -- internal constants only, no user input


# ---------------------------------------------------------------------------
# Cost estimation (dry run)
# ---------------------------------------------------------------------------


def estimate_bytes_processed(query: str, client: Any = None) -> int:
    """Estimate bytes that would be processed by a query (dry run).

    Args:
        query: SQL query string.
        client: Optional BigQuery client.

    Returns:
        Total bytes processed (0 on error).

    Reference:
        1 TB = 1_099_511_627_776 bytes = ~1e12 bytes
        Free tier: 1 TB/month
    """
    from google.cloud import bigquery

    if client is None:
        client = _get_bq_client()
    try:
        job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        job = client.query(query, job_config=job_config)
        result: int = job.total_bytes_processed or 0
        return result
    except Exception as e:
        _logger.warning("Dry run failed: %s", e)
        return 0


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert a BigQuery row to a plain dict."""
    return {k: v for k, v in row.items()}


def fetch_year(
    year: int,
    client: Any = None,
    chunk_size: int = ROWS_PER_CHUNK,
    max_records: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch SC empenho records for a given year, with pagination.

    Args:
        year: Year to fetch (2021-2024).
        client: Optional BigQuery client.
        chunk_size: Rows per page.
        max_records: Maximum total records to fetch (None = no limit).
                     Applied at the query level for efficiency.

    Returns:
        List of raw record dicts.
    """
    if client is None:
        client = _get_bq_client()

    # Cap chunk_size to max_records when applicable
    effective_chunk = chunk_size
    if max_records is not None and max_records < effective_chunk:
        effective_chunk = max_records

    all_rows: list[dict[str, Any]] = []
    offset = 0

    while True:
        remaining: int | None = None
        if max_records is not None:
            remaining = max_records - len(all_rows)
            if remaining <= 0:
                break
            if remaining < effective_chunk:
                effective_chunk = remaining

        query = build_sc_query(year=year, limit=effective_chunk, offset=offset)
        rows = client.query(query).result()
        batch = [_row_to_dict(r) for r in rows]
        all_rows.extend(batch)
        if len(batch) < effective_chunk:
            break
        offset += effective_chunk
        _logger.debug("Fetched %d rows for SC %d (offset=%d)", len(all_rows), year, offset)
        effective_chunk = chunk_size  # Reset after first limited chunk

    _logger.info("Fetched %d SC empenho records for %d", len(all_rows), year)
    return all_rows


def fetch_incremental(
    days_back: int = 90,
    client: Any = None,
) -> list[dict[str, Any]]:
    """Fetch recent SC empenho records.

    Args:
        days_back: How many days of history.
        client: Optional BigQuery client.

    Returns:
        List of raw record dicts.
    """
    if client is None:
        client = _get_bq_client()

    query = build_incremental_query(days_back=days_back)
    rows = client.query(query).result()
    records = [_row_to_dict(r) for r in rows]
    _logger.info("Fetched %d SC empenho records (incremental, %d days)", len(records), days_back)
    return records


# ---------------------------------------------------------------------------
# Esfera inference from CNPJ
# ---------------------------------------------------------------------------


def _infer_esfera_from_cnpj(cnpj: str | None) -> int:
    """Infer administrative sphere from CNPJ root (first digit).

    CNPJ first-digit classification (raiz):
        1 = Federal (Uniao)
        2 = Estadual
        3 = Municipal
        4-9 = Private/other (default to Municipal for SC municipio-filtered data)

    Returns:
        1=Federal, 2=Estadual, 3=Municipal (fallback).

    Reference:
        db/migrations/018-td-5.3_esfera_id_check.sql
        CHECK (esfera_id IS NULL OR esfera_id IN (1, 2, 3, 4))
    """
    if not cnpj:
        return 3  # Default to Municipal (data is filtered by SC municipios)
    digits = "".join(c for c in cnpj if c.isdigit())
    if not digits:
        return 3
    first = digits[0]
    if first == "1":
        return 1  # Federal
    if first == "2":
        return 2  # Estadual
    if first == "3":
        return 3  # Municipal
    return 3  # Private/unknown — default to Municipal


# ---------------------------------------------------------------------------
# Schema mapping
# ---------------------------------------------------------------------------


def _make_pncp_id(record: dict) -> str:
    """Generate a unique pncp_id for a MiDES empenho record.

    Uses ``id_empenho_bd`` when available, otherwise constructs a composite key
    from id_municipio + orgao + ano + numero.
    """
    emp_bd = record.get("id_empenho_bd")
    if emp_bd:
        # Sanitize: replace spaces with hyphens
        clean = str(emp_bd).replace(" ", "-")
        return f"mides-empenho-{clean}"
    # Composite key fallback
    muni = record.get("id_municipio") or "0000000"
    orgao = record.get("orgao") or "0"
    ano = record.get("ano") or "0"
    numero = record.get("numero") or "0"
    return f"mides-empenho-{muni}-{orgao}-{ano}-{numero}"


def _make_content_hash(record: dict) -> str:
    """Generate a content hash for deduplication.

    Hashes the key data fields of a raw record.
    """
    raw = "|".join(
        str(record.get(k, ""))
        for k in [
            "id_municipio",
            "orgao",
            "ano",
            "mes",
            "descricao",
            "valor_final",
            "numero",
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _extract_cnpj_from_id_licitacao(id_licitacao: str | None) -> str | None:
    """Try to extract a CNPJ from ``id_licitacao`` field.

    Some SC records have ``id_licitacao`` in format ``CNPJ#process_number``.
    Extracts the CNPJ (14 digits) when present.
    """
    if not id_licitacao:
        return None
    # Check for CNPJ#processo format
    if "#" in id_licitacao:
        parts = id_licitacao.split("#")
        candidate = parts[0].strip()
        digits = "".join(c for c in candidate if c.isdigit())
        if len(digits) == 14:
            return digits
    # Also try raw 14-digit pattern
    digits_only = "".join(c for c in id_licitacao if c.isdigit())
    # Look for 14 consecutive digits
    for i in range(len(digits_only) - 13):
        chunk = digits_only[i : i + 14]
        if len(chunk) == 14:
            return chunk
    return None


def transform(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Transform MiDES BigQuery empenho records to pncp_raw_bids schema.

    Args:
        records: Raw BigQuery row dicts from ``crawl()``.

    Returns:
        List of dicts ready for upsert_pncp_raw_bids.
    """
    # Empty transformations are pure and must not open a database connection.
    # This keeps health checks and offline QA deterministic.
    if not records:
        return []

    municipio_cache = _load_municipio_cache()

    # Track seen pncp_ids to handle duplicates (some records share
    # the same composite key when id_empenho_bd is NULL)
    _seen_pncp_ids: dict[str, int] = {}

    transformed: list[dict[str, Any]] = []
    for rec in records:
        id_municipio = str(rec.get("id_municipio") or "")
        municipio_nome = municipio_cache.get(id_municipio, "")

        # Extract CNPJ from id_licitacao if available
        orgao_cnpj = _extract_cnpj_from_id_licitacao(rec.get("id_licitacao"))

        # Timestamp from the date field
        data_val = rec.get("data")
        if data_val is not None:
            data_iso = str(data_val)[:10]
        else:
            data_iso = ""

        # Map modalidade_licitacao to modalidade_id/modalidade_nome
        # SC records have NULL modalidade_licitacao, so default to 0
        modalidade_id = 0
        modalidade_nome = None

        valor = rec.get("valor_final", 0) or 0

        # Generate pncp_id with dedup counter for records that share a key
        base_id = _make_pncp_id(rec)
        count = _seen_pncp_ids.get(base_id, 0)
        if count > 0:
            doc_id = f"{base_id}#{count}"
        else:
            doc_id = base_id
        _seen_pncp_ids[base_id] = count + 1

        transformed.append(
            {
                "pncp_id": doc_id,
                "objeto_compra": (rec.get("descricao") or "").strip(),
                "valor_total_estimado": float(valor),
                "modalidade_id": modalidade_id,
                "modalidade_nome": modalidade_nome,
                "situacao_compra": None,
                "esfera_id": _infer_esfera_from_cnpj(orgao_cnpj),
                "uf": "SC",
                "municipio": municipio_nome,
                "codigo_municipio_ibge": id_municipio,
                "orgao_razao_social": None,
                "orgao_cnpj": orgao_cnpj,
                "unidade_nome": None,
                "data_publicacao": data_iso,
                "data_abertura": None,
                "data_encerramento": None,
                "link_sistema_origem": None,
                "link_pncp": None,
                "content_hash": _make_content_hash(rec),
                "source": SOURCE_TAG,
                "is_active": True,
            }
        )

    _logger.info("Transformed %d records to pncp_raw_bids schema", len(transformed))
    return transformed


# ---------------------------------------------------------------------------
# Monitor.py interface
# ---------------------------------------------------------------------------


def crawl(mode: str = "full", max_records: int | None = None) -> list[dict[str, Any]]:
    """Monitor.py-compatible crawl entry point.

    Args:
        mode: ``"full"`` (all 2021-2024), ``"incremental"`` (last 90d),
               or ``"dry-run"`` (cost estimate only).
        max_records: Maximum total records to fetch (None = no limit).
                     Falls back to ``MIDES_CRAWL_LIMIT`` env var if not provided.

    Returns:
        List of raw BigQuery record dicts.
    """
    from google.api_core import exceptions as google_exceptions

    # Env var fallback for monitor.py integration
    if max_records is None:
        env_limit = os.environ.get("MIDES_CRAWL_LIMIT")
        if env_limit:
            try:
                max_records = int(env_limit)
            except (ValueError, TypeError):
                pass

    client = _get_bq_client()

    if mode == "dry-run":
        _logger.info("Dry run mode — estimating cost only")
        return []

    if mode == "incremental":
        return fetch_incremental(client=client)

    # Full mode: fetch all years 2021-2024
    all_records: list[dict[str, Any]] = []
    for year in COVERAGE_YEARS:
        if max_records is not None and len(all_records) >= max_records:
            break
        try:
            remaining = None
            if max_records is not None:
                remaining = max_records - len(all_records)
                if remaining <= 0:
                    break
            records = fetch_year(year, client=client, max_records=remaining)
            all_records.extend(records)
        except google_exceptions.Forbidden as e:
            _logger.error("Permission denied for year %d: %s", year, e)
            raise
        except google_exceptions.BadRequest as e:
            _logger.error("Query failed for year %d: %s", year, e)
            raise

    _logger.info("Total SC empenho records fetched: %d", len(all_records))
    return all_records


# ---------------------------------------------------------------------------
# Cost estimation utility
# ---------------------------------------------------------------------------


def print_cost_estimate() -> None:
    """Print estimated bytes processed for a full crawl."""
    client = _get_bq_client()
    print("\n  Cost Estimate (Dry Run):")
    print("  " + "-" * 50)

    total_bytes = 0
    for year in COVERAGE_YEARS:
        query = build_sc_query(year=year, limit=1000)
        bytes_proc = estimate_bytes_processed(query, client)
        gb = bytes_proc / (1024**3)
        print(f"    {year}: {bytes_proc:>12d} bytes ({gb:.2f} GB)")
        total_bytes += bytes_proc

    total_gb = total_bytes / (1024**3)
    total_tb = total_bytes / (1024**4)
    pct_free_tier = total_bytes / (1_099_511_627_776) * 100  # 1 TB

    print(f"    {'TOTAL':>4s}: {total_bytes:>12d} bytes ({total_gb:.2f} GB, {total_tb:.4f} TB)")
    print(f"    Free tier usage: {pct_free_tier:.2f}% of 1 TB/month")
    print(f"    {'OK' if pct_free_tier < 100 else 'EXCEEDED'}")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="MiDES BigQuery Coverage Crawler — Extra Consultoria")
    p.add_argument(
        "--mode",
        default="full",
        choices=["full", "incremental", "dry-run"],
        help="Crawl mode (default: full)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Alias for --mode dry-run (cost estimate only)",
    )
    p.add_argument(
        "--year",
        type=int,
        choices=COVERAGE_YEARS,
        help="Specific year to fetch (default: all 2021-2024)",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max rows per year (default: all)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    mode = "dry-run" if args.dry_run else args.mode

    print("=" * 72)
    print("  MiDES BigQuery Crawler")
    print(f"  Source: {PROJECT_ID}.{DATASET_ID}.{TABLE_EMPENHO}")
    print(f"  Mode: {mode}")
    print("=" * 72)

    if mode == "dry-run":
        print_cost_estimate()
        return 0

    # Connect and verify
    print("\n  Connecting to BigQuery...")
    client = _get_bq_client()
    try:
        client.query("SELECT 1").result()
        print("  Connection OK")
    except Exception as e:
        print(f"  Connection FAILED: {e}")
        return 1

    # Load municipio cache
    print("\n  Loading municipality names...")
    muni_cache = _load_municipio_cache(client)
    print(f"  Cached {len(muni_cache)} municipalities (SC)")

    # Fetch data
    print(f"\n  Fetching SC empenho data ({mode})...")
    if args.limit:
        print(f"  (limited to {args.limit} records)")
    raw_records = crawl(mode, max_records=args.limit)
    print(f"  Fetched: {len(raw_records)} records")

    if not raw_records:
        print("  No data fetched.")
        return 0

    # Transform
    print("\n  Transforming to pncp_raw_bids schema...")
    transformed = transform(raw_records)
    print(f"  Transformed: {len(transformed)} records")

    # Stats
    muni_set = set()
    cnpj_count = 0
    for t in transformed:
        if t["codigo_municipio_ibge"]:
            muni_set.add(t["codigo_municipio_ibge"])
        if t["orgao_cnpj"]:
            cnpj_count += 1

    print("\n  Stats:")
    print(f"    Municipalities covered: {len(muni_set)}")
    print(f"    Records with CNPJ: {cnpj_count}")
    print(f"    Total value: R$ {sum(t['valor_total_estimado'] or 0 for t in transformed):,.2f}")
    print(f"    Date range: {transformed[0]['data_publicacao']} to {transformed[-1]['data_publicacao']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
