"""PNCP ARP crawler — Atas de Registro de Precos.

EXT-010: Crawls ARP data from PNCP ``/api/consulta/v1/atas`` and upserts
into ``pncp_raw_atas`` via the ``upsert_pncp_raw_atas`` RPC.

ARP (Atas de Registro de Preco) permits any public agency to "piggyback"
on an already-completed procurement by contracting the winning supplier
without a new bidding process.

Volume estimate:
  - Nacional: ~1.500-2.500/month
  - SC: ~80-120/month

Crawl strategy:
  - Incremental 2x/day (8am, 8pm BRT) for configurable UF scope
  - Last 90 days window by default
  - Content_hash dedup via (ata_id, data_publicacao)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from ingestion._base.crawler import accumulate_stats, chunk_list, empty_run_stats
from ingestion.config import (
    INGESTION_ARP_ENABLED,
    INGESTION_ARP_MAX_PAGES,
    INGESTION_ARP_DAYS,
    INGESTION_BATCH_DELAY_S,
    INGESTION_BATCH_SIZE_UFS,
    INGESTION_CONCURRENT_UFS,
    INGESTION_UPSERT_BATCH_SIZE,
    INGESTION_UFS,
)
from ingestion.metrics import (
    ARP_RECORDS_FETCHED,
    ARP_RECORDS_UPSERTED,
    ARP_RUNS_TOTAL,
    ARP_RUN_DURATION,
    ARP_PAGES_FETCHED,
)

logger = logging.getLogger(__name__)

PNCP_BASE_URL = "https://pncp.gov.br/api/consulta/v1"
PNCP_ARP_ENDPOINT = "/atas"

# Timeouts
_HTTP_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


# ---------------------------------------------------------------------------
# Content hash helper
# ---------------------------------------------------------------------------


def _make_content_hash(ata_id: str, data_publicacao: str | None) -> str:
    """Generate a deterministic content hash for dedup.

    ARP content_hash is computed from (ata_id, data_publicacao) per AC4.
    """
    raw = f"{ata_id}|{data_publicacao or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# API response normaliser
# ---------------------------------------------------------------------------


def _normalise_arp_item(raw: dict, uf: str) -> dict | None:
    """Normalise a raw PNCP ARP API response into a pncp_raw_atas row.

    Args:
        raw: A single item from the PNCP /atas API response array.
        uf: The UF being crawled (used as fallback).

    Returns:
        A dict ready for upsert, or None if the item is malformed.
    """
    try:
        ata_id = str(raw.get("identificadorAta") or raw.get("id") or "")
        if not ata_id:
            return None

        # Extract orgao info (may be nested object or flat)
        orgao = raw.get("orgaoEntidade") or raw.get("orgao") or {}
        orgao_razao = (
            orgao.get("razaoSocial")
            or orgao.get("nome")
            or raw.get("orgaoRazaoSocial")
            or ""
        )
        orgao_cnpj = (
            orgao.get("cnpj")
            or orgao.get("cpfCnpj")
            or raw.get("orgaoCnpj")
            or ""
        )

        # Clean CNPJ (digits only)
        orgao_cnpj_clean = "".join(c for c in orgao_cnpj if c.isdigit())

        # Extract fornecedores (suppliers who can use this ARP)
        fornecedores_raw = raw.get("fornecedores") or raw.get("participantes") or []
        if isinstance(fornecedores_raw, list):
            fornecedores = [
                "".join(c for c in (f.get("cnpj") or f.get("cpfCnpj") or "") if c.isdigit())
                for f in fornecedores_raw
            ]
        else:
            fornecedores = []

        # Dates
        data_publicacao = raw.get("dataPublicacao") or raw.get("dataInclusao") or ""
        data_validade = raw.get("dataValidade") or raw.get("dataVigencia") or ""

        # Extract UF with fallback
        uf_value = (
            (orgao.get("uf") if isinstance(orgao, dict) else None)
            or raw.get("uf")
            or uf
        )

        row = {
            "ata_id": ata_id,
            "pncp_id_origem": str(raw.get("numeroControlePNCP") or raw.get("pncpIdOrigem") or ""),
            "orgao_razao_social": orgao_razao,
            "orgao_cnpj": orgao_cnpj_clean,
            "objeto": str(raw.get("objeto") or raw.get("descricaoObjeto") or ""),
            "valor_total": float(raw.get("valorTotal") or raw.get("valorGlobal") or 0),
            "data_publicacao": str(data_publicacao)[:10] if data_publicacao else None,
            "data_validade": str(data_validade)[:10] if data_validade else None,
            "uf": uf_value.upper() if uf_value else uf,
            "municipio": str(
                raw.get("municipio")
                or (orgao.get("municipio") if isinstance(orgao, dict) else None)
                or ""
            ),
            "fornecedores": json.dumps(fornecedores, ensure_ascii=False),
            "modalidade_nome": str(
                raw.get("modalidadeNome")
                or raw.get("modalidade")
                or raw.get("modalidadeContratacao")
                or ""
            ),
            "content_hash": _make_content_hash(ata_id, str(data_publicacao)[:10] if data_publicacao else None),
            "source": "pncp_arp",
        }
        return row
    except (ValueError, TypeError, AttributeError) as exc:
        logger.debug("ARP normalise error (skipped): %s — raw=%s", exc, str(raw)[:200])
        return None


# ---------------------------------------------------------------------------
# Crawler class
# ---------------------------------------------------------------------------


@dataclass
class ArpCrawlResult:
    """Result from an ARP crawl run per UF."""

    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    pages: int = 0
    errors: int = 0
    uf: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class PncpArpCrawler:
    """Crawler for Atas de Registro de Precos (ARP) from PNCP.

    API: GET /api/consulta/v1/atas
    Parameters: uf, dataPublicacaoInicio, dataPublicacaoFim, pagina, tamanhoPagina
    """

    SOURCE = "pncp_arp"
    ENDPOINT = PNCP_ARP_ENDPOINT

    def __init__(self, ufs: list[str] | None = None) -> None:
        self.ufs = ufs or INGESTION_UFS
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "PncpArpCrawler":
        self._client = httpx.AsyncClient(
            base_url=PNCP_BASE_URL,
            timeout=_HTTP_TIMEOUT,
            headers={
                "User-Agent": "SmartLic/1.0 (procurement-search; contato@smartlic.tech)",
                "Accept": "application/json",
            },
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()

    async def fetch_page(
        self,
        uf: str,
        date_start: date,
        date_end: date,
        page: int = 1,
    ) -> list[dict]:
        """Fetch a single page of ARP records for a given UF and date range.

        Returns:
            List of raw API item dicts. Empty list signals no more data.
        """
        if self._client is None:
            raise RuntimeError("Client not initialised. Use async context manager.")

        params = {
            "uf": uf,
            "dataPublicacaoInicio": date_start.isoformat(),
            "dataPublicacaoFim": date_end.isoformat(),
            "pagina": page,
            "tamanhoPagina": 50,
        }

        response = await self._client.get(self.ENDPOINT, params=params)

        if response.status_code == 204:
            return []

        if response.status_code != 200:
            logger.warning(
                "ARP: uf=%s page=%d HTTP %d — %s",
                uf, page, response.status_code, response.text[:200],
            )
            response.raise_for_status()

        data = response.json()
        items: list[dict] = data.get("data") or []
        return items

    def _has_more(self, response_data: dict) -> bool:
        """Check if more pages are available."""
        return bool(
            response_data.get("temProximaPagina")
            or int(response_data.get("paginasRestantes", 0)) > 0
        )

    async def crawl_uf(
        self,
        uf: str,
        date_start: date,
        date_end: date,
        max_pages: int = INGESTION_ARP_MAX_PAGES,
    ) -> ArpCrawlResult:
        """Crawl ARP for a single UF over a date range.

        Iterates pages, normalises items, returns collected rows without
        upserting (upsert happens at the batch level).
        """
        result = ArpCrawlResult(uf=uf)
        all_rows: list[dict] = []
        page = 1
        has_more = True

        while page <= max_pages and has_more:
            if self._client is None:
                raise RuntimeError("Client not initialised.")

            try:
                # Make the raw request so we can check pagination
                params = {
                    "uf": uf,
                    "dataPublicacaoInicio": date_start.isoformat(),
                    "dataPublicacaoFim": date_end.isoformat(),
                    "pagina": page,
                    "tamanhoPagina": 50,
                }
                resp = await self._client.get(self.ENDPOINT, params=params)

                if resp.status_code == 204:
                    break

                if resp.status_code != 200:
                    logger.warning(
                        "ARP: uf=%s page=%d HTTP %d",
                        uf, page, resp.status_code,
                    )
                    result.errors += 1
                    break

                resp_data = resp.json()
                items = resp_data.get("data") or []

                if not items:
                    break

                ARP_PAGES_FETCHED.labels(uf=uf).inc()
                result.pages += 1

                # Normalise items
                for item in items:
                    row = _normalise_arp_item(item, uf)
                    if row is not None:
                        all_rows.append(row)

                ARP_RECORDS_FETCHED.labels(uf=uf).inc(len(items))

                # Pagination check
                has_more = self._has_more(resp_data)
                page += 1

            except (httpx.HTTPError, asyncio.TimeoutError) as exc:
                logger.warning(
                    "ARP: uf=%s page=%d error — %s: %s",
                    uf, page, type(exc).__name__, exc,
                )
                result.errors += 1
                break

        result.fetched = len(all_rows)
        result.extra["rows"] = all_rows
        return result

    async def crawl_all_ufs(
        self,
        date_start: date,
        date_end: date,
    ) -> dict[str, Any]:
        """Crawl ARP for all configured UFs in parallel batches.

        Returns:
            dict with aggregated stats (fetched, inserted, updated, etc.).
        """
        totals = empty_run_stats()
        semaphore = asyncio.Semaphore(INGESTION_CONCURRENT_UFS)

        async def _crawl_single_uf(uf: str) -> dict[str, Any]:
            async with semaphore:
                result = await self.crawl_uf(uf, date_start, date_end)

            # Upsert rows for this UF immediately
            rows = result.extra.get("rows", [])
            if rows:
                counts = await _upsert_arp_batch(rows)
                result.inserted = counts.get("inserted", 0)
                result.updated = counts.get("updated", 0)
                result.unchanged = counts.get("unchanged", 0)

                ARP_RECORDS_UPSERTED.labels(
                    uf=uf, action="inserted",
                ).inc(result.inserted)
                ARP_RECORDS_UPSERTED.labels(
                    uf=uf, action="updated",
                ).inc(result.updated)

            uf_stats = {
                "fetched": result.fetched,
                "inserted": result.inserted,
                "updated": result.updated,
                "unchanged": result.unchanged,
                "ufs_crawled": result.pages,
                "ufs_failed": result.errors,
            }
            accumulate_stats(totals, uf_stats)
            return uf_stats

        uf_batches = chunk_list(self.ufs, INGESTION_BATCH_SIZE_UFS)

        for batch_idx, uf_batch in enumerate(uf_batches):
            if batch_idx > 0:
                await asyncio.sleep(INGESTION_BATCH_DELAY_S)

            tasks = [_crawl_single_uf(uf) for uf in uf_batch]
            await asyncio.gather(*tasks, return_exceptions=False)

        return {
            "fetched": totals["fetched"],
            "inserted": totals["inserted"],
            "updated": totals["updated"],
            "unchanged": totals["unchanged"],
            "pages": totals["ufs_crawled"],
            "errors": totals["ufs_failed"],
        }


# ---------------------------------------------------------------------------
# Upsert helper
# ---------------------------------------------------------------------------


async def _upsert_arp_batch(rows: list[dict]) -> dict[str, int]:
    """Upsert ARP rows into pncp_raw_atas via Supabase RPC.

    Args:
        rows: List of normalised row dicts.

    Returns:
        Dict with inserted, updated, unchanged counts.
    """
    if not rows:
        return {"inserted": 0, "updated": 0, "unchanged": 0}

    from supabase_client import get_supabase, sb_execute

    totals = {"inserted": 0, "updated": 0, "unchanged": 0}
    batches = [rows[i:i + INGESTION_UPSERT_BATCH_SIZE] for i in range(0, len(rows), INGESTION_UPSERT_BATCH_SIZE)]
    supabase = get_supabase()

    for batch_idx, batch in enumerate(batches):
        try:
            # Serialise — ensure dates etc. are strings
            payload = json.loads(json.dumps(batch, default=str, ensure_ascii=False))

            result = await sb_execute(
                supabase.rpc("upsert_pncp_raw_atas", {"p_records": payload}),
                category="rpc",
            )

            counts = _extract_rpc_counts(result)
            totals["inserted"] += counts.get("inserted", 0)
            totals["updated"] += counts.get("updated", 0)
            totals["unchanged"] += counts.get("unchanged", 0)

            logger.debug(
                "ARP upsert batch %d: inserted=%d updated=%d unchanged=%d",
                batch_idx + 1,
                counts.get("inserted", 0),
                counts.get("updated", 0),
                counts.get("unchanged", 0),
            )

        except Exception as exc:
            logger.error(
                "ARP upsert batch %d failed: %s: %s — continuing",
                batch_idx + 1, type(exc).__name__, exc,
            )
            continue

    return totals


def _extract_rpc_counts(result: Any) -> dict[str, int]:
    """Extract inserted/updated/unchanged from RPC result."""
    try:
        data = result.data
        if isinstance(data, list) and data:
            row = data[0]
            return {
                "inserted": int(row.get("inserted", 0)),
                "updated": int(row.get("updated", 0)),
                "unchanged": int(row.get("unchanged", 0)),
            }
        return {"inserted": 0, "updated": 0, "unchanged": 0}
    except Exception:
        return {"inserted": 0, "updated": 0, "unchanged": 0}


# ---------------------------------------------------------------------------
# Module-level entry points (for ARQ scheduler)
# ---------------------------------------------------------------------------


async def crawl_arp_incremental(
    *,
    days_back: int = INGESTION_ARP_DAYS,
) -> dict[str, Any]:
    """Incremental ARP crawl across all configured UFs.

    Crawls the last ``days_back`` days of ARP data.

    Returns:
        Aggregated statistics dict.
    """
    if not INGESTION_ARP_ENABLED:
        logger.info("[ARP] Skipped — INGESTION_ARP_ENABLED=false")
        ARP_RUNS_TOTAL.labels(status="skipped").inc()
        return {"status": "skipped", "reason": "INGESTION_ARP_ENABLED=false"}

    start = datetime.utcnow()
    logger.info("[ARP] Starting incremental crawl — days_back=%d ufs=%d", days_back, len(INGESTION_UFS))

    today = date.today()
    date_start = today - timedelta(days=days_back)
    date_end = today

    try:
        async with PncpArpCrawler() as crawler:
            result = await crawler.crawl_all_ufs(date_start, date_end)
    except Exception as exc:
        duration = (datetime.utcnow() - start).total_seconds()
        logger.error("[ARP] Crawl failed: %s: %s", type(exc).__name__, exc, exc_info=True)
        ARP_RUNS_TOTAL.labels(status="failed").inc()
        return {"status": "failed", "error": str(exc), "duration_s": round(duration, 1)}

    duration = (datetime.utcnow() - start).total_seconds()
    ARP_RUNS_TOTAL.labels(status="completed").inc()
    ARP_RUN_DURATION.observe(duration)

    logger.info(
        "[ARP] Completed in %.1fs — fetched=%d inserted=%d updated=%d unchanged=%d errors=%d",
        duration,
        result.get("fetched", 0),
        result.get("inserted", 0),
        result.get("updated", 0),
        result.get("unchanged", 0),
        result.get("errors", 0),
    )

    return {
        "status": "completed",
        **result,
        "duration_s": round(duration, 1),
    }
