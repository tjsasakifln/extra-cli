"""Local PostgreSQL datalake access — zero Supabase dependency.

Drop-in replacement for datalake_query.py. Uses asyncpg to connect
directly to a local PostgreSQL instance instead of going through the
Supabase API (PostgREST).

Usage:
    from local_datalake import query_datalake

    results = await query_datalake(
        ufs=["SC", "PR"],
        data_inicial="2026-01-01",
        data_final="2026-06-30",
        query_term="licitacao",
        modo_busca="publicacao",
    )

Env vars:
    LOCAL_DATALAKE_DSN — PostgreSQL connection string (obrigatorio).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from datetime import datetime, timedelta
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_LOCAL_DSN = os.getenv("LOCAL_DATALAKE_DSN", "")

# Connection pool (lazy init)
_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()

# ---------------------------------------------------------------------------
# Cache (same logic as datalake_query.py)
# ---------------------------------------------------------------------------

_CACHE_TTL = 600
_CACHE_MAX_ENTRIES = 20
_query_cache: dict[str, tuple[float, list[dict]]] = {}

_EMBEDDING_CACHE_TTL = 1800
_EMBEDDING_CACHE_MAX_ENTRIES = 50
_embedding_cache: dict[str, tuple[float, list[float]]] = {}

_ROW_CAP = 1000
_MAX_PAGINATION_DEPTH = 10


def _cache_key(
    ufs: list[str],
    data_inicial: str,
    data_final: str,
    tsquery: str | None,
    websearch_text: str | None,
    modo_busca: str,
) -> str:
    ufs_sorted = ",".join(sorted(ufs))
    q = f"{tsquery or ''}|{websearch_text or ''}"
    if modo_busca == "abertas":
        return f"{ufs_sorted}|abertas|{q}"
    return f"{ufs_sorted}|{data_inicial}|{data_final}|{q}|{modo_busca}"


def _cache_get(key: str) -> list[dict] | None:
    if key in _query_cache:
        expiry, results = _query_cache[key]
        if time.monotonic() < expiry:
            return results
        del _query_cache[key]
    return None


def _cache_set(key: str, results: list[dict]) -> None:
    if len(_query_cache) >= _CACHE_MAX_ENTRIES:
        oldest = min(_query_cache, key=lambda k: _query_cache[k][0])
        del _query_cache[oldest]
    _query_cache[key] = (time.monotonic() + _CACHE_TTL, results)


async def get_pool() -> asyncpg.Pool:
    """Get or create the asyncpg connection pool."""
    global _pool
    if _pool is not None:
        return _pool

    async with _pool_lock:
        if _pool is not None:
            return _pool
        _pool = await asyncpg.create_pool(
            _LOCAL_DSN,
            min_size=1,
            max_size=5,
            command_timeout=30,
        )
        logger.info("Local datalake pool initialized: %s", _LOCAL_DSN)
    return _pool


async def close_pool() -> None:
    """Close the connection pool (call during shutdown)."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Local datalake pool closed")


async def _execute_search_datalake(
    ufs: list[str],
    data_inicial: str | None,
    data_final: str | None,
    tsquery: str | None,
    websearch_text: str | None,
    modalidades: list[int] | None,
    valor_min: float | None,
    valor_max: float | None,
    esferas: list[str] | None,
    modo_busca: str,
    limit: int = 2000,
    offset: int = 0,
    embedding: list[float] | None = None,
) -> list[dict]:
    """Execute the search_datalake RPC function directly via SQL.

    This replaces: supabase.rpc('search_datalake', {...}).execute()
    """
    pool = await get_pool()

    query = """
        SELECT * FROM public.search_datalake(
            p_ufs => $1::text[],
            p_date_start => $2::date,
            p_date_end => $3::date,
            p_tsquery => $4::text,
            p_websearch_text => $5::text,
            p_modalidades => $6::int[],
            p_valor_min => $7::numeric,
            p_valor_max => $8::numeric,
            p_esferas => $9::text[],
            p_modo => $10::text,
            p_limit => $11::int,
            p_offset => $12::int,
            p_embedding => $13::vector
        )
    """

    # Convert empty strings to None (PostgreSQL treats them differently)
    _tsquery = tsquery if tsquery else None
    _websearch = websearch_text if websearch_text else None

    # asyncpg requires datetime.date objects, not strings
    _data_start = None
    _data_end = None
    if data_inicial:
        try:
            _data_start = datetime.strptime(data_inicial, "%Y-%m-%d").date()
        except ValueError:
            pass
    if data_final:
        try:
            _data_end = datetime.strptime(data_final, "%Y-%m-%d").date()
        except ValueError:
            pass

    # embedding as string for pgvector compatibility
    _embedding_str = f"[{','.join(str(x) for x in embedding)}]" if embedding else None

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            query,
            ufs,  # $1
            _data_start,  # $2
            _data_end,  # $3
            _tsquery,  # $4
            _websearch,  # $5
            modalidades,  # $6
            valor_min,  # $7
            valor_max,  # $8
            esferas,  # $9
            modo_busca,  # $10
            limit,  # $11
            offset,  # $12
            _embedding_str,  # $13
        )
        return [dict(r) for r in rows]


async def _execute_trigram_fallback(
    query_term: str,
    ufs: list[str],
    limit: int = 200,
) -> list[dict]:
    """Execute the trigram fallback RPC."""
    pool = await get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT * FROM public.search_datalake_trigram_fallback(
                p_query_term => $1::text,
                p_ufs => $2::text[],
                p_limit => $3::int
            )""",
            query_term,
            ufs,
            limit,
        )
        return [dict(r) for r in rows]


def _row_to_normalized(row: dict) -> dict:
    """Map RPC columns to flat dict format expected by filter.py/llm.py/excel.py.

    This mirrors the normalization done by PNCPClient._normalize_item()
    so all downstream stages work unchanged.
    """
    return {
        "pncp_id": row.get("pncp_id", ""),
        "objeto_compra": row.get("objeto_compra", ""),
        "valor_total_estimado": float(row.get("valor_total_estimado") or 0),
        "modalidade_id": int(row.get("modalidade_id") or 0),
        "modalidade_nome": row.get("modalidade_nome", ""),
        "situacao_compra": row.get("situacao_compra", ""),
        "esfera_id": row.get("esfera_id", ""),
        "uf": row.get("uf", ""),
        "municipio": row.get("municipio", ""),
        "codigo_municipio_ibge": row.get("codigo_municipio_ibge", ""),
        "orgao_razao_social": row.get("orgao_razao_social", ""),
        "orgao_cnpj": row.get("orgao_cnpj", ""),
        "unidade_nome": row.get("unidade_nome", ""),
        "data_publicacao": str(row.get("data_publicacao") or ""),
        "data_abertura": str(row.get("data_abertura") or ""),
        "data_encerramento": str(row.get("data_encerramento") or ""),
        "link_sistema_origem": row.get("link_sistema_origem", ""),
        "link_pncp": row.get("link_pncp", ""),
        "content_hash": row.get("content_hash", ""),
        "source": row.get("source", "pncp"),
        "ingested_at": str(row.get("ingested_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
        "ts_rank": float(row.get("ts_rank") or 0.0),
    }


async def query_datalake(
    ufs: list[str],
    data_inicial: str = "",
    data_final: str = "",
    query_term: str = "",
    complemento_termos: str = "",
    modalidades: list[int] | None = None,
    valor_min: float | None = None,
    valor_max: float | None = None,
    esferas: list[str] | None = None,
    modo_busca: str = "publicacao",
    is_seo_request: bool = True,
    termo_customizado: str = "",
) -> list[dict]:
    """Query the local datalake — drop-in replacement for datalake_query.query_datalake().

    Args:
        ufs: List of UF codes (e.g. ["SC", "PR"])
        data_inicial: Start date (YYYY-MM-DD)
        data_final: End date (YYYY-MM-DD)
        query_term: Search term (used for tsquery generation)
        complemento_termos: Additional search terms
        modalidades: Modality codes to filter by
        valor_min: Minimum estimated value
        valor_max: Maximum estimated value
        esferas: Government sphere codes (F/E/M/D)
        modo_busca: "publicacao" (by publication date) or "abertas" (open bids)
        is_seo_request: Whether this is an SEO programmatic request
        termo_customizado: Custom search term (websearch_to_tsquery)

    Returns:
        List of normalized bid dicts (same format as PNCPClient output)
    """
    # Build tsquery from query_term + complemento_termos
    tsquery = None
    websearch_text = None

    if query_term:
        # Clean and normalize for tsquery
        cleaned = re.sub(r'[^\w\s]', ' ', query_term.lower()).strip()
        if cleaned:
            tsquery = ' & '.join(cleaned.split())

    if termo_customizado:
        websearch_text = termo_customizado

    # Check cache
    cache_key = _cache_key(ufs, data_inicial, data_final, tsquery, websearch_text, modo_busca)
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.debug("Local datalake cache hit: %s", cache_key)
        return cached

    sem = asyncio.Semaphore(5)  # Concurrency limiter per query

    async def _fetch_uf(uf: str) -> list[dict]:
        """Fetch results for a single UF with pagination handling."""
        async with sem:
            rows: list[dict] = []
            date_start = data_inicial
            date_end = data_final
            page_offset = 0
            depth = 0

            while depth <= _MAX_PAGINATION_DEPTH:
                try:
                    batch = await _execute_search_datalake(
                        ufs=[uf],
                        data_inicial=date_start if date_start else None,
                        data_final=date_end if date_end else None,
                        tsquery=tsquery,
                        websearch_text=websearch_text,
                        modalidades=modalidades,
                        valor_min=valor_min,
                        valor_max=valor_max,
                        esferas=esferas,
                        modo_busca=modo_busca,
                        offset=page_offset,
                    )
                except Exception as e:
                    logger.warning("Local datalake query failed for UF=%s: %s", uf, e)
                    return rows

                if not batch:
                    break

                rows.extend(batch)

                if len(batch) < _ROW_CAP:
                    # No more data for this UF
                    break

                # Pagination: try intra-day offset first
                if page_offset == 0:
                    page_offset = _ROW_CAP
                elif date_start and date_end:
                    # Binary date-range split
                    try:
                        d1 = datetime.strptime(date_start, "%Y-%m-%d")
                        d2 = datetime.strptime(date_end, "%Y-%m-%d")
                        if d1 == d2:
                            # Single day overflow — keep offset pagination
                            page_offset += _ROW_CAP
                            depth += 1
                            continue
                        mid = d1 + (d2 - d1) / 2
                        date_end = mid.strftime("%Y-%m-%d")
                        page_offset = 0
                    except ValueError:
                        break
                else:
                    page_offset += _ROW_CAP

                depth += 1

            return rows

    # Fetch all UFs in parallel (limited by semaphore to 5 concurrent)
    tasks = [_fetch_uf(uf) for uf in ufs]
    all_rows: list[list[dict]] = []
    for task in asyncio.as_completed(tasks):
        try:
            uf_rows = await task
            all_rows.append(uf_rows)
        except Exception as e:
            logger.warning("Local datalake UF query failed: %s", e)

    # Flatten
    results: list[dict] = []
    for batch in all_rows:
        results.extend(batch)

    # Normalize rows to match PNCPClient format
    normalized = [_row_to_normalized(r) for r in results]

    # Trigram fallback: if FTS returned 0 results and we have a query term
    if not normalized and query_term:
        try:
            trigram_rows = await _execute_trigram_fallback(query_term, ufs)
            normalized = [_row_to_normalized(r) for r in trigram_rows]
        except Exception as e:
            logger.warning("Trigram fallback failed: %s", e)

    # Cache results
    _cache_set(cache_key, normalized)

    return normalized


async def get_row_count(uf: str | None = None) -> int:
    """Get total row count for pncp_raw_bids (optionally filtered by UF)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if uf:
            return await conn.fetchval(
                "SELECT count(*) FROM pncp_raw_bids WHERE is_active = true AND uf = $1",
                uf,
            )
        return await conn.fetchval(
            "SELECT count(*) FROM pncp_raw_bids WHERE is_active = true"
        )


async def get_supplier_contracts(cnpj: str, limit: int = 100) -> list[dict]:
    """Get contracts for a specific supplier CNPJ."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM pncp_supplier_contracts
            WHERE is_active = true AND ni_fornecedor = $1
            ORDER BY data_assinatura DESC
            LIMIT $2
            """,
            cnpj,
            limit,
        )
        return [dict(r) for r in rows]


async def get_contracts_by_orgao(cnpj: str, limit: int = 100) -> list[dict]:
    """Get contracts for a specific buyer (orgao) CNPJ."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM pncp_supplier_contracts
            WHERE is_active = true AND orgao_cnpj = $1
            ORDER BY data_assinatura DESC
            LIMIT $2
            """,
            cnpj,
            limit,
        )
        return [dict(r) for r in rows]


async def get_contracts_by_setor_uf(
    setor: str, uf: str, limit: int = 500
) -> list[dict]:
    """Get contracts filtered by sector and UF.

    Uses the rpc_count_contracts_setor_uf RPC for sector classification.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(
                "SELECT * FROM rpc_count_contracts_setor_uf($1, $2, $3)",
                setor,
                uf,
                limit,
            )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning("get_contracts_by_setor_uf failed: %s", e)
            return []
