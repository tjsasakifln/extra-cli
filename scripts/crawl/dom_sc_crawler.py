"""DOM-SC API crawler — Contratos de Todos os 295 Municipios de SC.

Extrai metadados estruturados de contratos (categoria 6), convenios (7) e
empenhos (28) do Diario Oficial dos Municipios de Santa Catarina via API REST.

API documentada em: diariomunicipal.sc.gov.br/?r=site/page&view=integracao
Autenticacao: HTTP Basic Auth (CPF:CNPJ) + header X-API-Key

Volume: ~5.000 contratos/mes dos 295 municipios catarinenses.

Mapeia para pncp_supplier_contracts com source='dom_sc'.
Dedup via content_hash = SHA-256 de (numero, orgao_cnpj, data_publicacao).
Checkpoint por (source='dom_sc', municipio, data).
"""

import hashlib
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from supabase_client import get_supabase, sb_execute

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://diariomunicipal.sc.gov.br"
SOURCE = "dom_sc"

# Categorias de atos com metadados estruturados obrigatorios:
#   6 = Contratos
#   7 = Convenios
#   28 = Empenhos
CATEGORIAS = [6, 7, 28]

HTTP_TIMEOUT = 60          # Timeout per API call (seconds)
BATCH_SIZE = 500           # Rows per upsert batch (matches INGESTION_UPSERT_BATCH_SIZE)
DELAY_BETWEEN_MUNICIPIOS = 1.0  # Seconds between municipio groups (rate limit)

# Feature flag
DOM_SC_ENABLED = os.getenv("INGESTION_DOM_SC_ENABLED", "true").lower() in ("true", "1")

# Auth env vars
DOM_SC_CPF = os.getenv("DOM_SC_CPF", "")
DOM_SC_CNPJ = os.getenv("DOM_SC_CNPJ", "")
DOM_SC_API_KEY = os.getenv("DOM_SC_API_KEY", "")

# Timeout for ARQ job
DOM_SC_DAILY_CRAWL_TIMEOUT = 3600  # 1h safety (expected: < 15 min)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _digits_only(s: str | None) -> str:
    """Strip non-digit characters from a string."""
    if not s:
        return ""
    import re
    return re.sub(r"\D", "", s)


def _parse_date(value: Any) -> str | None:
    """Parse a date from various formats to YYYY-MM-DD string.

    Handles ISO 8601 (2026-07-09), Brazilian (09/07/2026), and
    datetime strings like '2026-07-09T00:00:00'.
    """
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, str):
        s = value.strip()
        # ISO format
        if len(s) >= 10 and s[4] == "-":
            return s[:10]
        # Brazilian format DD/MM/YYYY
        if len(s) >= 10 and s[2] == "/":
            try:
                from datetime import datetime as dt
                return dt.strptime(s[:10], "%d/%m/%Y").date().isoformat()
            except ValueError:
                pass
        # Try partial ISO (YYYY-MM-DD anywhere in string)
        for i in range(len(s) - 9):
            if s[i + 4] == "-" and s[i + 7] == "-":
                return s[i:i + 10]
    return None


# ---------------------------------------------------------------------------
# Main crawler class
# ---------------------------------------------------------------------------

class DomScCrawler:
    """Crawler para API de metadados do Diario Oficial dos Municipios de SC.

    Autenticacao via HTTP Basic Auth (CPF:CNPJ) + header X-API-Key.
    Consulta as categorias 6 (contratos), 7 (convenios) e 28 (empenhos)
    com filtro por data de publicacao.

    Usage:
        crawler = DomScCrawler()
        async with httpx.AsyncClient() as client:
            pubs = await crawler.fetch_publications(client, date_from, date_to)
    """

    def __init__(self) -> None:
        if not DOM_SC_CPF or not DOM_SC_CNPJ or not DOM_SC_API_KEY:
            logger.warning(
                "[DomScCrawler] Missing auth credentials — set DOM_SC_CPF, "
                "DOM_SC_CNPJ, and DOM_SC_API_KEY env vars"
            )
        self.cpf = DOM_SC_CPF
        self.cnpj = DOM_SC_CNPJ
        self.api_key = DOM_SC_API_KEY
        self.auth = httpx.BasicAuth(self.cpf, self.cnpj)

    # -----------------------------------------------------------------------
    # API calls
    # -----------------------------------------------------------------------

    async def fetch_publications(
        self,
        client: httpx.AsyncClient,
        date_from: date,
        date_to: date,
    ) -> list[dict]:
        """Fetch all publications with metadata for the given date range.

        Makes one API call per categoria (6, 7, 28) and aggregates results.
        Each categoria response includes publications from ALL 295 municipios
        within the date range.

        Returns:
            List of raw publication dicts from the API.
        """
        all_items: list[dict] = []
        total_fetched = 0

        for categoria in CATEGORIAS:
            url = f"{BASE_URL}/?r=remote/search"
            params: dict[str, Any] = {
                "categoria": categoria,
                "data_inicio": date_from.strftime("%d/%m/%Y"),
                "data_fim": date_to.strftime("%d/%m/%Y"),
                "com_metadados": 1,
            }

            try:
                response = await client.get(
                    url,
                    params=params,
                    auth=self.auth,
                    headers={"X-API-Key": self.api_key},
                    timeout=HTTP_TIMEOUT,
                )
                response.raise_for_status()
                data = response.json()
                items = data.get("publicacoes", [])
                all_items.extend(items)
                total_fetched += len(items)
                logger.info(
                    "[DomScCrawler] Categoria %d: %d publications for %s - %s",
                    categoria, len(items), date_from, date_to,
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 401:
                    logger.error(
                        "[DomScCrawler] Auth failure (401) for categoria %d — "
                        "check DOM_SC_CPF, DOM_SC_CNPJ, DOM_SC_API_KEY",
                        categoria,
                    )
                elif exc.response.status_code == 429:
                    logger.warning(
                        "[DomScCrawler] Rate limited (429) on categoria %d", categoria,
                    )
                else:
                    logger.error(
                        "[DomScCrawler] HTTP %d on categoria %d: %s",
                        exc.response.status_code, categoria, exc,
                    )
                raise
            except Exception as exc:
                logger.error(
                    "[DomScCrawler] Failed to fetch categoria %d: %s: %s",
                    categoria, type(exc).__name__, exc,
                )
                raise

        logger.info(
            "[DomScCrawler] Total: %d publications across %d categories",
            total_fetched, len(CATEGORIAS),
        )
        return all_items

    # -----------------------------------------------------------------------
    # Normalization
    # -----------------------------------------------------------------------

    def normalize_to_contract(self, raw: dict) -> dict | None:
        """Map a single DOM-SC publication to pncp_supplier_contracts schema.

        Returns None if the record lacks required fields (numero or orgao_cnpj).
        """
        metadados = raw.get("metadados", {})
        numero = (metadados.get("numero") or "").strip()
        orgao_cnpj_raw = (raw.get("orgao_cnpj") or "").strip()
        orgao_cnpj = _digits_only(orgao_cnpj_raw)
        data_pub_raw = raw.get("data_publicacao", "")

        if not numero or not orgao_cnpj:
            logger.debug(
                "[DomScCrawler] Skipping record — missing numero or orgao_cnpj"
            )
            return None

        # Parse valor if available — handle both numeric and string formats
        valor_raw = metadados.get("valor")
        valor = None
        if valor_raw is not None:
            try:
                if isinstance(valor_raw, (int, float)):
                    valor = round(float(valor_raw), 2)
                else:
                    val_str = str(valor_raw).strip()
                    # Brazilian format: "150.000,00" or "150000.00"
                    if "," in val_str and "." in val_str:
                        val_str = val_str.replace(".", "").replace(",", ".")
                    elif "," in val_str:
                        val_str = val_str.replace(",", ".")
                    valor = round(float(val_str), 2)
            except (ValueError, TypeError):
                pass

        # Build unique control number with DOMSC- prefix (source encoding)
        numero_controle = f"DOMSC-{orgao_cnpj}-{numero}"

        # Build content_hash per AC6: SHA-256 de (numero, orgao_cnpj, data_publicacao)
        data_pub = _parse_date(data_pub_raw) or ""
        hash_input = f"{numero}|{orgao_cnpj}|{data_pub}"
        content_hash = hashlib.sha256(hash_input.encode()).hexdigest()

        municipio = (raw.get("municipio") or "").strip()
        orgao_nome = (raw.get("orgao_nome") or "").strip()
        categoria_raw = raw.get("categoria")
        categoria = int(categoria_raw) if categoria_raw is not None else 0

        # Build informative object description from available data
        cat_names: dict[int, str] = {6: "Contrato", 7: "Convenio", 28: "Empenho"}
        cat_name = cat_names.get(categoria, f"Categoria {categoria}")

        # Build description from raw fields
        desc_parts = [f"{cat_name} - {municipio} - SC"]
        numero_processo = metadados.get("numero_processo", "")
        if numero_processo:
            desc_parts.append(f"Processo: {numero_processo}")
        desc = " | ".join(desc_parts)
        if len(desc) > 500:
            desc = desc[:497] + "..."

        return {
            "numero_controle_pncp": numero_controle,
            "ni_fornecedor": orgao_cnpj,
            "nome_fornecedor": orgao_nome or None,
            "orgao_cnpj": orgao_cnpj or None,
            "orgao_nome": orgao_nome or None,
            "uf": "SC",
            "municipio": municipio or None,
            "esfera": "M",  # Municipal
            "valor_global": valor,
            "data_assinatura": data_pub or None,
            "objeto_contrato": desc or None,
            "content_hash": content_hash,
            "source": SOURCE,
            # Extra metadata not in pncp_supplier_contracts schema
            # (stripped before upsert RPC)
            "_info_extra": {
                "numero_processo": metadados.get("numero_processo", ""),
                "url_processo": metadados.get("url_processo", ""),
                "legislacao": metadados.get("legislacao", ""),
                "categoria": categoria,
            },
        }

    def normalize_batch(
        self, raw_items: list[dict],
    ) -> tuple[list[dict], int]:
        """Normalize a list of raw API items into contracts.

        Returns:
            (normalized_records, skipped_count)
        """
        normalized: list[dict] = []
        skipped = 0
        for item in raw_items:
            rec = self.normalize_to_contract(item)
            if rec:
                normalized.append(rec)
            else:
                skipped += 1
        return normalized, skipped

    # -----------------------------------------------------------------------
    # Checkpoint helpers
    # -----------------------------------------------------------------------

    async def _checkpoint_exists(
        self, supabase, municipio: str, data: date,
    ) -> bool:
        """Check if a checkpoint exists for (dom_sc, municipio, data)."""
        try:
            result = await sb_execute(
                supabase
                .table("ingestion_checkpoints")
                .select("id")
                .eq("source", SOURCE)
                .eq("uf", municipio)
                .eq("modalidade_id", 0)
                .eq("status", "completed")
                .eq("last_date", data.isoformat())
            )
            rows = result.data or []
            return len(rows) > 0
        except Exception as exc:
            logger.warning(
                "[DomScCrawler] Checkpoint check failed for %s/%s: %s",
                municipio, data, exc,
            )
            return False  # False means "not found" — safe to process

    async def _save_checkpoint(
        self, supabase, municipio: str, data: date,
        records_fetched: int, crawl_batch_id: str,
    ) -> None:
        """Save a checkpoint for (dom_sc, municipio, data)."""
        try:
            payload: dict[str, Any] = {
                "uf": municipio,
                "modalidade_id": 0,
                "source": SOURCE,
                "last_date": data.isoformat(),
                "records_fetched": records_fetched,
                "crawl_batch_id": crawl_batch_id,
                "status": "completed",
                "error_message": None,
            }
            await sb_execute(
                supabase
                .table("ingestion_checkpoints")
                .upsert(payload, on_conflict="source,uf,modalidade_id,crawl_batch_id"),
                category="write",
            )
            logger.debug(
                "[DomScCrawler] Checkpoint saved: %s/%s (%d records)",
                municipio, data, records_fetched,
            )
        except Exception as exc:
            logger.error(
                "[DomScCrawler] Failed to save checkpoint for %s/%s: %s",
                municipio, data, exc,
            )

    # -----------------------------------------------------------------------
    # Upsert
    # -----------------------------------------------------------------------

    async def _upsert_batch(self, records: list[dict]) -> dict[str, int]:
        """Upsert normalized records into pncp_supplier_contracts via RPC.

        Returns counts: {inserted: N, updated: N, unchanged: N}.
        Strips internal fields (prefixed with '_') before sending.
        """
        if not records:
            return {"inserted": 0, "updated": 0, "unchanged": 0}

        payload = []
        for rec in records:
            clean = {k: v for k, v in rec.items() if not k.startswith("_")}
            payload.append(clean)

        try:
            supabase = get_supabase()
            safe = json.loads(json.dumps(payload, default=str, ensure_ascii=False))
            result = await sb_execute(
                supabase.rpc("upsert_supplier_contracts", {"contracts": safe}),
                category="rpc",
            )
            if result.data:
                return {
                    "inserted": len(result.data),
                    "updated": 0,
                    "unchanged": 0,
                }
        except Exception as exc:
            logger.error("[DomScCrawler] Upsert batch failed: %s", exc)
            raise

        return {"inserted": 0, "updated": 0, "unchanged": 0}

    # -----------------------------------------------------------------------
    # Daily crawl
    # -----------------------------------------------------------------------

    async def run_daily_crawl(
        self,
        crawl_batch_id: str | None = None,
        target_date: date | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        """Run a daily incremental crawl for the target date.

        Process:
        1. Fetch all publications from the target date
        2. Group by municipio
        3. For each municipio without a checkpoint, normalize and upsert
        4. Save checkpoint for each processed municipio

        Args:
            crawl_batch_id: Unique identifier for this run (auto-generated if None).
            target_date: The date to crawl (default: yesterday).
            client: Optional shared httpx.AsyncClient (creates one if None).

        Returns:
            Summary dict with status, inserted, skipped, municipios_processed, etc.
        """
        if not DOM_SC_ENABLED:
            logger.info("[DomScCrawler] Disabled (INGESTION_DOM_SC_ENABLED=false)")
            return {"status": "disabled"}

        if not self.cpf or not self.cnpj or not self.api_key:
            logger.warning(
                "[DomScCrawler] Missing credentials — DOM_SC_CPF, DOM_SC_CNPJ, "
                "DOM_SC_API_KEY must be set"
            )
            return {"status": "skipped", "reason": "missing_credentials"}

        t0 = datetime.now(timezone.utc)
        target = target_date or (date.today() - timedelta(days=1))
        batch_id = crawl_batch_id or f"dom_sc_{target.strftime('%Y%m%d_%H%M%S')}"
        owned_client = client is None

        if owned_client:
            client = httpx.AsyncClient(timeout=HTTP_TIMEOUT)

        try:
            # 1. Fetch all publications for the target date
            assert client is not None  # Guaranteed: created above if None
            raw_items = await self.fetch_publications(client, target, target)
            logger.info(
                "[DomScCrawler] Fetched %d total publications for %s",
                len(raw_items), target,
            )

            # 2. Group by municipio
            by_municipio: dict[str, list[dict]] = {}
            for item in raw_items:
                mun = (item.get("municipio") or "desconhecido").strip()
                by_municipio.setdefault(mun, []).append(item)

            # 3. Process each municipio
            total_inserted = 0
            total_skipped = 0
            municipios_processed = 0
            municipios_skipped_checkpoint = 0
            municipios_with_data = 0

            supabase = get_supabase()

            for idx, (municipio, items) in enumerate(sorted(by_municipio.items())):
                # Check if already processed
                if await self._checkpoint_exists(supabase, municipio, target):
                    municipios_skipped_checkpoint += 1
                    continue

                municipios_with_data += 1

                # Normalize
                normalized, skipped = self.normalize_batch(items)
                total_skipped += skipped

                if not normalized:
                    # Save checkpoint even if no valid records (edge case)
                    await self._save_checkpoint(
                        supabase, municipio, target, len(items), batch_id,
                    )
                    municipios_processed += 1
                    continue

                # Upsert in batches
                for i in range(0, len(normalized), BATCH_SIZE):
                    batch = normalized[i:i + BATCH_SIZE]
                    try:
                        result = await self._upsert_batch(batch)
                        total_inserted += result.get("inserted", 0)
                    except Exception as exc:
                        logger.error(
                            "[DomScCrawler] Municipio %s batch %d-%d failed: %s",
                            municipio, i, i + len(batch), exc,
                        )

                # Save checkpoint
                await self._save_checkpoint(
                    supabase, municipio, target, len(items), batch_id,
                )
                municipios_processed += 1

                # Rate limit between municipios
                if idx < len(by_municipio) - 1:
                    import asyncio
                    await asyncio.sleep(DELAY_BETWEEN_MUNICIPIOS)

            elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
            summary = {
                "status": "completed",
                "source": SOURCE,
                "target_date": target.isoformat(),
                "crawl_batch_id": batch_id,
                "total_fetched": len(raw_items),
                "total_inserted": total_inserted,
                "total_skipped": total_skipped,
                "municipios_with_data": municipios_with_data,
                "municipios_processed": municipios_processed,
                "municipios_skipped_checkpoint": municipios_skipped_checkpoint,
                "elapsed_s": round(elapsed, 1),
            }
            logger.info(
                "[DomScCrawler] Daily crawl complete: %d inserted from %d municipios "
                "(%.1fs)", total_inserted, municipios_processed, elapsed,
            )

            # Update Prometheus metrics
            try:
                from ingestion.dom_sc_metrics import DOM_SC_CONTRACTS_FETCHED, DOM_SC_MUNICIPIOS_PROCESSED
                DOM_SC_CONTRACTS_FETCHED.inc(total_inserted)
                DOM_SC_MUNICIPIOS_PROCESSED.inc(municipios_processed)
            except Exception:
                pass

            return summary

        except Exception as exc:
            elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
            logger.error(
                "[DomScCrawler] Daily crawl failed after %.1fs: %s: %s",
                elapsed, type(exc).__name__, exc,
            )
            return {
                "status": "failed",
                "error": str(exc),
                "elapsed_s": round(elapsed, 1),
            }
        finally:
            if owned_client and client:
                await client.aclose()


# ---------------------------------------------------------------------------
# ARQ job entry point
# ---------------------------------------------------------------------------

async def dom_sc_daily_job(ctx: dict | None = None) -> dict[str, Any]:
    """ARQ job: Execute daily DOM-SC crawl.

    Crawls yesterday's publications across all 295 municipios.
    Scheduled at 9:00 UTC (6:00 BRT) daily.

    Feature flag: INGESTION_DOM_SC_ENABLED (default: true).
    Timeout: DOM_SC_DAILY_CRAWL_TIMEOUT (1h safety).

    Returns:
        Summary dict from run_daily_crawl().
    """
    logger.info("[DomScCrawler] ARQ job started")
    crawler = DomScCrawler()
    result = await crawler.run_daily_crawl()
    logger.info("[DomScCrawler] ARQ job finished: %s", result.get("status"))
    return result
