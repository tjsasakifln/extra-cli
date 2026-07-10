"""Crawler for Portal de Compras SC (compras.sc.gov.br + e-lic.sc.gov.br).

Portal de Compras SC is the unified procurement portal for the state of Santa
Catarina, operated by CIASC using the Paradigma platform. It publishes all
state-level bids from 27 secretarias, 15+ autarquias, 5+ fundacoes, 8+ empresas
publicas, and ~236 municipios catarinenses.

The portal is server-side rendered HTML (no JS required for data extraction).
httpx + BeautifulSoup are sufficient for scraping.

Sources:
  - compras.sc.gov.br — Main unified portal (primary)
  - e-lic.sc.gov.br — Electronic bidding system (Paradigma platform, secondary)

Modes:
  - full:        Last 30 days
  - incremental: Last 24 hours (+1h overlap for safety)

Schedule:
  - Full:  02:00 BRT daily (05:00 UTC)
  - Incremental: 08:00, 14:00, 20:00 BRT (11:00, 17:00, 23:00 UTC)

Volume: +2.000-3.000 editais/month SC
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from ingestion.config import INGESTION_UPSERT_BATCH_SIZE
from redis_pool import get_redis_pool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = os.getenv("SC_COMPRAS_BASE_URL", "https://compras.sc.gov.br")
E_LIC_URL = os.getenv("SC_COMPRAS_E_LIC_URL", "https://e-lic.sc.gov.br")
SOURCE = "compras_sc_gov"

HTTP_TIMEOUT = 45
MAX_RETRIES = 3
RETRY_BACKOFF_S = 2.0

# Page navigation
MAX_PAGES = int(os.getenv("INGESTION_SC_COMPRAS_MAX_PAGES", "100"))

# Concurrency
CONCURRENT_DETAILS = int(os.getenv("INGESTION_SC_COMPRAS_CONCURRENT_REQUESTS", "3"))
PAGE_DELAY_S = float(os.getenv("INGESTION_SC_COMPRAS_PAGE_DELAY_S", "1.0"))

# Feature flag
SC_COMPRAS_ENABLED = os.getenv(
    "INGESTION_SC_COMPRAS_ENABLED", "true"
).lower() in ("true", "1")

# Date ranges
SC_COMPRAS_FULL_DAYS = int(os.getenv("INGESTION_SC_COMPRAS_FULL_DAYS", "30"))
SC_COMPRAS_INCREMENTAL_DAYS = int(
    os.getenv("INGESTION_SC_COMPRAS_INCREMENTAL_DAYS", "1")
)

# ARQ timeouts
SC_COMPRAS_FULL_TIMEOUT = 7200     # 2h for full crawl
SC_COMPRAS_INCREMENTAL_TIMEOUT = 1800  # 30min for incremental

# Checkpoint
_CHECKPOINT_TTL = 7 * 24 * 3600

# ---------------------------------------------------------------------------
# Modalidade mapping
# ---------------------------------------------------------------------------

# SC portal modalidade names as returned by the portal
_MODALIDADE_MAP: dict[str, int] = {
    "pregao": 5,
    "pregao eletronico": 5,
    "pregao presencial": 6,
    "concorrencia": 4,
    "concorrencia antiga": 1,
    "tomada de precos": 2,
    "convite": 3,
    "concurso": 9,
    "leilao": 10,
    "dialogo competitivo": 13,
    "dispena de licitacao": 7,
    "dispensa de licitacao": 7,
    "contratacao direta": 7,
    "inexigibilidade": 8,
    "credenciamento": 12,
}

# SC-specific modalidade IDs not covered by standard PNCP
_SC_MODALIDADE_IDS: dict[str, int] = {
    "concorrencia antiga": 1,
    "tomada de precos": 2,
    "convite": 3,
    "concurso": 9,
    "leilao": 10,
    "dialogo competitivo": 13,
}


def _normalize_modalidade(raw: str) -> str:
    """Normalize a raw modalidade string for lookup.

    Strips accents, lowercases, and removes numbering prefixes.
    """
    s = raw.strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("–", "-").replace("—", "-")
    # Remove leading number+period (e.g. "1. Concorrência" -> "concorrência")
    s = re.sub(r"^\d+[\.\)]\s*", "", s)
    # Remove parenthetical qualifiers
    # e.g. "Concorrência (antiga)" -> "Concorrência antiga"
    s = re.sub(r"[\(\)]", "", s)
    # Strip Unicode accents (NFKD decomposition)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    return s


def _map_modalidade(raw: str) -> tuple[int | None, str]:
    """Map SC portal modalidade to (modalidade_id, modalidade_nome).

    Returns (None, raw) if modalidade is unknown.
    """
    normalized = _normalize_modalidade(raw)
    modalidade_id = _MODALIDADE_MAP.get(normalized)
    if modalidade_id is not None:
        return modalidade_id, raw.strip()
    # Fuzzy match: try partial matching
    for key, mid in _MODALIDADE_MAP.items():
        if key in normalized or normalized in key:
            return mid, raw.strip()
    logger.debug(
        "[ScCompras] Unknown modalidade: '%s' (normalized: '%s')",
        raw, normalized,
    )
    return None, raw.strip()


# ---------------------------------------------------------------------------
# Esfera inference
# ---------------------------------------------------------------------------

_ESFERA_ESTADUAL_KEYWORDS = [
    "secretaria de estado", "secretaria da", "governo do estado",
    "fundo estadual", "companhia", "santa catarina",
    "deinfra", "udesc", "jucesc", "detran", "ima", "imetro",
    "aresc", "iprev", "fapesc", "fcc", "fcee", "fesporte",
    "ciasc", "badesc", "scpar", "scgas", "ceasa", "cidasc",
    "santur", "sudes", "pcisc", "ena",
]


def _infer_esfera(orgao_nome: str) -> str:
    """Infer the administrative sphere from the orgao name.

    Returns 'E' (Estadual), 'M' (Municipal), or '' (unknown).
    """
    lower = orgao_nome.lower().strip()
    # Check estadual keywords
    for kw in _ESFERA_ESTADUAL_KEYWORDS:
        if kw in lower:
            return "E"
    # Prefeitura/PM prefix typically means municipal
    if lower.startswith("pm ") or lower.startswith("prefeitura"):
        return "M"
    # Default to estadual for SC portal (most entities are state-level)
    return "E"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _digits_only(s: str | None) -> str:
    """Strip non-digit characters from a string."""
    if not s:
        return ""
    return re.sub(r"\D", "", s)


def _parse_br_date(s: str | None) -> str | None:
    """Parse a Brazilian date (DD/MM/YYYY) to YYYY-MM-DD ISO format.

    Returns None if unparseable.
    """
    if not s or not s.strip():
        return None
    s = s.strip()
    match = re.match(r"(\d{2})/(\d{2})/(\d{4})", s)
    if match:
        return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"
    # Try ISO format directly
    if re.match(r"\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    return None


def _parse_br_number(s: str | None) -> float | None:
    """Parse a Brazilian-formatted number string (e.g. '1.500,00' or '150000').

    Returns None if unparseable.
    """
    if not s or not s.strip():
        return None
    s = s.strip().replace("R$", "").replace(" ", "")
    if not s:
        return None
    # Handle mixed formats
    if "," in s and "." in s:
        # BR format: dots as thousands, comma as decimal
        # e.g. "1.500,00" or "2.500.000,00"
        if s.rindex(",") > s.rindex("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _compute_content_hash(
    pncp_id: str, data_publicacao: str | None, objeto: str | None
) -> str:
    """Compute deterministic content_hash from (pncp_id, data_publicacao, objeto)."""
    raw = f"{pncp_id}|{data_publicacao or ''}|{objeto or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore


def _parse_list_html(html: str) -> list[dict]:
    """Extract process list from the portal's HTML table.

    Parses the table rows, extracting visible fields and detail URL.

    Returns list of raw item dicts with keys:
        numero_processo, modalidade, objeto, orgao, data_publicacao,
        situacao, valor, url_detalhe
    """
    if BeautifulSoup is None:
        raise ImportError("BeautifulSoup4 is required for HTML parsing")

    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []

    # Try to find the table — the portal uses bootstrap table
    tables = soup.select("table.table")
    if not tables:
        logger.debug("[ScCompras] No table.table found in HTML")
        return items

    for table in tables:
        rows = table.select("tbody tr")
        if not rows:
            continue

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 5:
                continue

            # Extract detail URL from the first cell's anchor
            link_cell = cells[0]
            link = link_cell.find("a")
            url_detalhe = None
            if link and link.get("href"):
                href = link["href"].strip()
                if href.startswith("http"):
                    url_detalhe = href
                else:
                    url_detalhe = f"{BASE_URL}{href}"

            item = {
                "numero_processo": link_cell.get_text(strip=True) or "",
                "modalidade": cells[1].get_text(strip=True) if len(cells) > 1 else "",
                "objeto": cells[2].get_text(strip=True) if len(cells) > 2 else "",
                "orgao": cells[3].get_text(strip=True) if len(cells) > 3 else "",
                "data_publicacao": (
                    cells[4].get_text(strip=True) if len(cells) > 4 else ""
                ),
                "situacao": cells[5].get_text(strip=True) if len(cells) > 5 else "",
                "valor": cells[6].get_text(strip=True) if len(cells) > 6 else "",
                "url_detalhe": url_detalhe,
            }
            items.append(item)

    return items


def _parse_detail_html(html: str) -> dict:
    """Parse a detail page for additional structured fields.

    Returns a dict with additional fields parsed from the detail page.
    """
    if BeautifulSoup is None:
        raise ImportError("BeautifulSoup4 is required for HTML parsing")

    detail_data: dict = {}
    soup = BeautifulSoup(html, "html.parser")

    # Try different selectors for detail pages
    detail_container = (
        soup.select_one("div.detalhe-licitacao")
        or soup.select_one("div.panel-body")
        or soup.select_one("div.content-wrapper")
    )

    if detail_container is None:
        # Fallback: just scan all definition lists
        detail_container = soup

    # Find all definition lists (<dl>) or row-based layouts
    dls = detail_container.find_all("dl")
    if dls:
        for dl in dls:
            terms = dl.find_all("dt")
            definitions = dl.find_all("dd")
            for dt, dd in zip(terms, definitions):
                key = _normalize_detail_key(dt.get_text(strip=True))
                value = dd.get_text(strip=True)
                if key and value:
                    detail_data[key] = value

    # Also handle label-value div layouts (common in Bootstrap)
    # e.g., <div class="col-md-6"><label>CNPJ</label><span>...</span></div>
    labeled_items = detail_container.select(
        ".form-group, .detalhe-item, [class*='field']"
    )
    for item in labeled_items:
        label_el = item.select_one("label, dt, .control-label, strong")
        value_el = item.select_one("span, dd, .form-control-static, p")
        if label_el and value_el:
            key = _normalize_detail_key(label_el.get_text(strip=True))
            value = value_el.get_text(strip=True)
            if key and value and key not in detail_data:
                detail_data[key] = value

    return detail_data


def _normalize_detail_key(text: str) -> str | None:
    """Normalize a detail page label to a predefined key.

    Maps Portuguese labels to canonical field names.
    """
    mapping = {
        "numero do processo": "numero_processo",
        "numero": "numero_processo",
        "processo": "numero_processo",
        "modalidade": "modalidade",
        "objeto": "objeto",
        "objeto da licitacao": "objeto",
        "objeto da compra": "objeto",
        "valor total estimado": "valor",
        "valor estimado": "valor",
        "valor": "valor",
        "situacao": "situacao",
        "situacao da compra": "situacao",
        "orgao": "orgao",
        "orgao entidade": "orgao",
        "orgao/entidade": "orgao",
        "cnpj do orgao": "orgao_cnpj",
        "cnpj": "orgao_cnpj",
        "municipio": "municipio",
        "uf": "uf",
        "data de publicacao": "data_publicacao",
        "data publicacao": "data_publicacao",
        "publicacao": "data_publicacao",
        "data de abertura": "data_abertura",
        "data abertura": "data_abertura",
        "abertura": "data_abertura",
        "data de encerramento": "data_encerramento",
        "data encerramento": "data_encerramento",
        "encerramento": "data_encerramento",
        "esfera": "esfera",
        "esfera id": "esfera",
    }
    normalized = text.lower().strip().rstrip(":")
    # Strip Unicode accents (NFKD decomposition)
    normalized = unicodedata.normalize("NFKD", normalized)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    return mapping.get(normalized, None)


# ---------------------------------------------------------------------------
# Checkpoint helpers (Redis)
# ---------------------------------------------------------------------------


def _ckpt_key(days_offset: str) -> str:
    return f"sc_compras:ckpt:{days_offset}"


async def _get_checkpoint(source_date: str) -> dict | None:
    """Return saved checkpoint dict or None."""
    try:
        redis = await get_redis_pool()
        if redis is None:
            return None
        raw = await redis.get(_ckpt_key(source_date))
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.debug("[ScCompras] Checkpoint read error: %s", exc)
        return None


async def _save_checkpoint(
    source_date: str,
    status: str,
    last_page: int = 0,
    records_fetched: int = 0,
) -> None:
    """Persist crawl progress to Redis."""
    try:
        redis = await get_redis_pool()
        if redis is None:
            return
        payload = json.dumps({
            "status": status,
            "last_page": last_page,
            "records_fetched": records_fetched,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        })
        await redis.set(_ckpt_key(source_date), payload, ex=_CHECKPOINT_TTL)
    except Exception as exc:
        logger.debug("[ScCompras] Checkpoint write error: %s", exc)


async def clear_checkpoints() -> int:
    """Delete all sc_compras:ckpt:* keys from Redis."""
    try:
        redis = await get_redis_pool()
        if redis is None:
            return 0
        keys: list[str] = []
        async for key in redis.scan_iter("sc_compras:ckpt:*"):
            keys.append(key)
        if keys:
            await redis.delete(*keys)
        logger.info("[ScCompras] Cleared %d checkpoint keys", len(keys))
        return len(keys)
    except Exception as exc:
        logger.error("[ScCompras] Failed to clear checkpoints: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# ScComprasCrawler
# ---------------------------------------------------------------------------


class ScComprasCrawler:
    """Crawler for Portal de Compras SC.

    Crawls compras.sc.gov.br and e-lic.sc.gov.br to extract structured bid data
    from HTML pages. Uses a two-pass approach: first parse the list table to get
    basic info, then fetch detail pages for complete data.

    Normalized records are upserted into pncp_raw_bids via bulk_upsert.
    """

    def __init__(
        self,
        date_from: date,
        date_to: date,
        *,
        crawl_batch_id: str | None = None,
        start_page: int = 1,
    ) -> None:
        self.date_from = date_from
        self.date_to = date_to
        self.crawl_batch_id = crawl_batch_id or datetime.now(timezone.utc).strftime(
            "sc_compras_%Y%m%d_%H%M%S"
        )
        self.start_page = start_page
        self._stats: dict[str, Any] = {
            "pages_fetched": 0,
            "items_in_list": 0,
            "details_fetched": 0,
            "normalized": 0,
            "inserted": 0,
            "updated": 0,
            "unchanged": 0,
            "errors": 0,
            "start_page": start_page,
        }

        # Build checkpoint key from date range
        self._source_date = f"{date_from.isoformat()}_{date_to.isoformat()}"

    @property
    def _date_from_str(self) -> str:
        return self.date_from.isoformat()

    @property
    def _date_to_str(self) -> str:
        return self.date_to.isoformat()

    # ------------------------------------------------------------------
    # Page fetching
    # ------------------------------------------------------------------

    async def fetch_process_list(
        self,
        client: httpx.AsyncClient,
        page: int,
    ) -> list[dict]:
        """Fetch one page of the process listing from the SC portal.

        Returns a list of raw item dicts parsed from HTML.
        Returns empty list if the page has no data or page is beyond available.
        """
        # First try the new unified portal
        url = f"{BASE_URL}/licitacoes"
        params: dict[str, Any] = {
            "pagina": page,
            "data_publicacao_inicio": self._date_from_str,
            "data_publicacao_fim": self._date_to_str,
        }
        html = await self._fetch_html(client, url, params)
        if not html:
            # Fallback: try e-lic URL
            url = f"{E_LIC_URL}/licitacao"
            params = {
                "pagina": page,
                "data_inicio": self._date_from_str,
                "data_fim": self._date_to_str,
            }
            html = await self._fetch_html(client, url, params)
            if not html:
                return []

        items = _parse_list_html(html)
        logger.debug(
            "[ScCompras] Page %d: fetched %d items", page, len(items)
        )
        return items

    async def fetch_process_detail(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> dict:
        """Fetch the detail page for a single process.

        Returns a dict of additional fields parsed from the detail HTML.
        Returns empty dict on failure.
        """
        if not url:
            return {}
        try:
            resp = await client.get(url, timeout=HTTP_TIMEOUT, follow_redirects=True)
            resp.raise_for_status()
            return _parse_detail_html(resp.text)
        except Exception as exc:
            logger.debug(
                "[ScCompras] Detail fetch failed for %s: %s", url, exc
            )
            return {}

    async def _fetch_html(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> str | None:
        """Fetch HTML with retries. Returns None on failure."""
        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = await client.get(
                    url,
                    params=params,
                    timeout=HTTP_TIMEOUT,
                    follow_redirects=True,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (compatible; SmartLic-Bot/1.0; "
                            "+https://smartlic.tech/bot)"
                        ),
                        "Accept": "text/html,application/xhtml+xml",
                    },
                )
                if resp.status_code == 200:
                    return resp.text
                if resp.status_code in (404, 410):
                    logger.warning(
                        "[ScCompras] %s returned %d — no data for this range",
                        url, resp.status_code,
                    )
                    return None
                logger.warning(
                    "[ScCompras] HTTP %d for %s (attempt %d/%d)",
                    resp.status_code, url, attempt, MAX_RETRIES,
                )
                last_error = httpx.HTTPStatusError(
                    f"HTTP {resp.status_code}", request=resp.request, response=resp
                )
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                logger.warning(
                    "[ScCompras] Network error for %s (attempt %d/%d): %s",
                    url, attempt, MAX_RETRIES, exc,
                )
                last_error = exc

            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_BACKOFF_S * attempt)

        logger.error(
            "[ScCompras] Failed to fetch %s after %d attempts: %s",
            url, MAX_RETRIES, last_error,
        )
        return None

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def normalize_item(
        self,
        raw: dict,
        detail: dict | None = None,
    ) -> dict | None:
        """Normalize a raw SC portal item to pncp_raw_bids schema.

        Args:
            raw: Dict from list page parsing.
            detail: Optional dict from detail page (overrides list fields).

        Returns:
            Normalized dict ready for upsert, or None if the item is skippable.
        """
        merged = dict(raw)
        if detail:
            merged.update(detail)

        numero_processo = (merged.get("numero_processo") or "").strip()
        if not numero_processo:
            return None

        pncp_id = f"sc-{numero_processo}"
        objeto_compra = (merged.get("objeto") or "").strip()
        if len(objeto_compra) > 1000:
            objeto_compra = objeto_compra[:997] + "..."

        data_publicacao = (
            _parse_br_date(merged.get("data_publicacao"))
            or datetime.now(timezone.utc).date().isoformat()
        )
        data_abertura = _parse_br_date(merged.get("data_abertura"))
        data_encerramento = _parse_br_date(merged.get("data_encerramento"))

        orgao = (merged.get("orgao") or "").strip()
        orgao_cnpj_digits = _digits_only(merged.get("orgao_cnpj"))

        valor_str = merged.get("valor")
        valor = _parse_br_number(valor_str)

        modalidade_raw = (merged.get("modalidade") or "").strip()
        modalidade_id, modalidade_nome = _map_modalidade(modalidade_raw)

        municipio = (merged.get("municipio") or "").strip()
        situacao = (merged.get("situacao") or "").strip()

        url_detalhe = (merged.get("url_detalhe") or "").strip()
        esfera = _infer_esfera(orgao)

        # Compute content_hash for dedup
        content_hash = _compute_content_hash(pncp_id, data_publicacao, objeto_compra)

        return {
            "pncp_id": pncp_id,
            "uf": "SC",
            "municipio": municipio,
            "orgao_razao_social": orgao,
            "orgao_cnpj": orgao_cnpj_digits or None,
            "objeto_compra": objeto_compra or None,
            "valor_total_estimado": round(valor, 2) if valor is not None else None,
            "modalidade_id": modalidade_id,
            "modalidade_nome": modalidade_nome,
            "situacao_compra": situacao or None,
            "data_publicacao": data_publicacao,
            "data_abertura": data_abertura,
            "data_encerramento": data_encerramento,
            "link_pncp": url_detalhe or None,
            "esfera_id": esfera,
            "source": SOURCE,
            "content_hash": content_hash,
        }

    # ------------------------------------------------------------------
    # Upsert
    # ------------------------------------------------------------------

    async def upsert_batch(self, records: list[dict]) -> dict[str, int]:
        """Upsert normalized records via bulk_upsert.

        Returns aggregated counts.
        """
        if not records:
            return {
                "inserted": 0, "updated": 0,
                "unchanged": 0, "total": 0, "batches": 0,
            }

        from ingestion.loader import bulk_upsert
        return await bulk_upsert(records, batch_size=INGESTION_UPSERT_BATCH_SIZE)

    # ------------------------------------------------------------------
    # Main crawl
    # ------------------------------------------------------------------

    async def run(self) -> dict[str, Any]:
        """Run the full crawl: iterate pages, fetch details, normalize, upsert.

        Returns aggregated stats dict.
        """
        t0 = time.monotonic()
        logger.info(
            "[ScCompras] Starting crawl %s -> %s (batch=%s, start_page=%d)",
            self._date_from_str, self._date_to_str,
            self.crawl_batch_id, self.start_page,
        )

        # Create ingestion run record
        from ingestion.checkpoint import create_ingestion_run
        await create_ingestion_run(self.crawl_batch_id, "full")

        async with httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; SmartLic-Bot/1.0; "
                    "+https://smartlic.tech/bot)"
                ),
                "Accept": "text/html,application/xhtml+xml",
            },
        ) as client:

            for page in range(self.start_page, MAX_PAGES + 1):
                # Fetch list page
                items = await self.fetch_process_list(client, page)
                if not items:
                    logger.info(
                        "[ScCompras] Page %d: empty — end of data", page
                    )
                    break

                self._stats["pages_fetched"] += 1
                self._stats["items_in_list"] += len(items)

                # Fetch detail pages concurrently for all items with URLs
                detail_futures: dict[int, dict] = {}
                for idx, item in enumerate(items):
                    url = item.get("url_detalhe")
                    if url:
                        detail_futures[idx] = url

                if detail_futures:
                    sem = asyncio.Semaphore(CONCURRENT_DETAILS)

                    async def _fetch_with_sem(url: str) -> dict:
                        async with sem:
                            return await self.fetch_process_detail(client, url)

                    detail_tasks = {
                        idx: asyncio.create_task(_fetch_with_sem(url))
                        for idx, url in detail_futures.items()
                    }

                    details: dict[int, dict] = {}
                    for idx, task in detail_tasks.items():
                        try:
                            details[idx] = await task
                        except Exception as exc:
                            logger.debug(
                                "[ScCompras] Detail fetch failed for item %d: %s",
                                idx, exc,
                            )
                            details[idx] = {}
                else:
                    details = {}

                self._stats["details_fetched"] += len(details)

                # Normalize items
                normalized: list[dict] = []
                for idx, item in enumerate(items):
                    try:
                        rec = self.normalize_item(item, details.get(idx))
                        if rec:
                            normalized.append(rec)
                        else:
                            self._stats["errors"] += 1
                    except Exception as exc:
                        logger.warning(
                            "[ScCompras] Normalize error item %d: %s", idx, exc,
                        )
                        self._stats["errors"] += 1

                self._stats["normalized"] += len(normalized)

                # Upsert batch
                if normalized:
                    try:
                        counts = await self.upsert_batch(normalized)
                        self._stats["inserted"] += counts.get("inserted", 0)
                        self._stats["updated"] += counts.get("updated", 0)
                        self._stats["unchanged"] += counts.get("unchanged", 0)
                    except Exception as exc:
                        logger.error(
                            "[ScCompras] Upsert error on page %d: %s", page, exc
                        )
                        self._stats["errors"] += len(normalized)

                # Save page-level checkpoint
                await _save_checkpoint(
                    self._source_date,
                    "in_progress",
                    last_page=page,
                    records_fetched=self._stats["items_in_list"],
                )

                # Respectful delay between pages
                await asyncio.sleep(PAGE_DELAY_S)

                # Log progress every 10 pages
                if page % 10 == 0:
                    elapsed = time.monotonic() - t0
                    logger.info(
                        "[ScCompras] Progress: page %d, %.1fs elapsed, "
                        "%d items, %d normalized, %d inserted",
                        page, elapsed,
                        self._stats["items_in_list"],
                        self._stats["normalized"],
                        self._stats["inserted"],
                    )

        # Final checkpoint: completed
        await _save_checkpoint(
            self._source_date,
            "completed",
            last_page=self._stats["pages_fetched"],
            records_fetched=self._stats["items_in_list"],
        )

        # Complete the ingestion run
        from ingestion.checkpoint import complete_ingestion_run
        await complete_ingestion_run(
            self.crawl_batch_id,
            status="completed",
            total_fetched=self._stats["items_in_list"],
            inserted=self._stats["inserted"],
            updated=self._stats["updated"],
            unchanged=self._stats["unchanged"],
        )

        elapsed = round(time.monotonic() - t0, 1)
        self._stats["duration_s"] = elapsed
        self._stats["date_from"] = self._date_from_str
        self._stats["date_to"] = self._date_to_str
        self._stats["status"] = "completed"

        logger.info(
            "[ScCompras] Crawl complete in %.1fs — pages=%d items=%d "
            "norm=%d ins=%d upd=%d unch=%d err=%d",
            elapsed,
            self._stats["pages_fetched"],
            self._stats["items_in_list"],
            self._stats["normalized"],
            self._stats["inserted"],
            self._stats["updated"],
            self._stats["unchanged"],
            self._stats["errors"],
        )

        return dict(self._stats)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_full_crawl() -> dict[str, Any]:
    """Run a full crawl of the SC Compras portal (last 30 days).

    Returns aggregated stats dict.
    """
    if not SC_COMPRAS_ENABLED:
        logger.info(
            "[ScCompras] Full crawl skipped — INGESTION_SC_COMPRAS_ENABLED=false"
        )
        return {"status": "skipped", "reason": "feature_disabled"}

    today = datetime.now(timezone.utc).date()
    date_from = today - timedelta(days=SC_COMPRAS_FULL_DAYS)
    date_to = today
    source_date = f"{date_from.isoformat()}_{date_to.isoformat()}"

    # Check checkpoint for resume
    ckpt = await _get_checkpoint(source_date)
    start_page = 1
    if ckpt and ckpt.get("status") == "completed":
        logger.info(
            "[ScCompras] Full crawl already completed for %s — skipping",
            source_date,
        )
        return {"status": "skipped", "reason": "already_completed"}
    if ckpt and ckpt.get("status") == "in_progress":
        start_page = max(1, ckpt.get("last_page", 1) + 1)
        logger.info("[ScCompras] Resuming full crawl from page %d", start_page)

    crawl_batch_id = (
        f"sc_compras_full_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    )
    crawler = ScComprasCrawler(
        date_from=date_from,
        date_to=date_to,
        crawl_batch_id=crawl_batch_id,
        start_page=start_page,
    )

    # Track metrics
    try:
        from ingestion.metrics import SC_COMPRAS_RUNS_TOTAL
        SC_COMPRAS_RUNS_TOTAL.labels(run_type="full", status="running").inc()
    except Exception:
        pass

    result = await crawler.run()

    try:
        from ingestion.metrics import (
            SC_COMPRAS_RUNS_TOTAL,
            SC_COMPRAS_RUN_DURATION,
            SC_COMPRAS_RECORDS_FETCHED,
        )
        status = result.get("status", "completed")
        SC_COMPRAS_RUNS_TOTAL.labels(run_type="full", status=status).inc()
        SC_COMPRAS_RUN_DURATION.labels(run_type="full").observe(
            result.get("duration_s", 0)
        )
        SC_COMPRAS_RECORDS_FETCHED.labels(source=SOURCE).inc(
            result.get("items_in_list", 0)
        )
    except Exception:
        pass

    return result


async def run_incremental_crawl() -> dict[str, Any]:
    """Run an incremental crawl (last 24h + 1h overlap).

    Returns aggregated stats dict.
    """
    if not SC_COMPRAS_ENABLED:
        logger.info(
            "[ScCompras] Incremental crawl skipped — "
            "INGESTION_SC_COMPRAS_ENABLED=false"
        )
        return {"status": "skipped", "reason": "feature_disabled"}

    today = datetime.now(timezone.utc).date()
    incremental_days = SC_COMPRAS_INCREMENTAL_DAYS + 1  # +1 overlap
    date_from = today - timedelta(days=incremental_days)
    date_to = today
    source_date = f"{date_from.isoformat()}_{date_to.isoformat()}"

    # Check checkpoint
    ckpt = await _get_checkpoint(source_date)
    start_page = 1
    if ckpt and ckpt.get("status") == "completed":
        logger.info(
            "[ScCompras] Incremental crawl already completed for %s — skipping",
            source_date,
        )
        return {"status": "skipped", "reason": "already_completed"}
    if ckpt and ckpt.get("status") == "in_progress":
        start_page = max(1, ckpt.get("last_page", 1) + 1)

    crawl_batch_id = (
        f"sc_compras_incr_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    )
    crawler = ScComprasCrawler(
        date_from=date_from,
        date_to=date_to,
        crawl_batch_id=crawl_batch_id,
        start_page=start_page,
    )

    try:
        from ingestion.metrics import SC_COMPRAS_RUNS_TOTAL
        SC_COMPRAS_RUNS_TOTAL.labels(run_type="incremental", status="running").inc()
    except Exception:
        pass

    result = await crawler.run()

    try:
        from ingestion.metrics import (
            SC_COMPRAS_RUNS_TOTAL,
            SC_COMPRAS_RUN_DURATION,
            SC_COMPRAS_RECORDS_FETCHED,
        )
        status = result.get("status", "completed")
        SC_COMPRAS_RUNS_TOTAL.labels(run_type="incremental", status=status).inc()
        SC_COMPRAS_RUN_DURATION.labels(run_type="incremental").observe(
            result.get("duration_s", 0)
        )
        SC_COMPRAS_RECORDS_FETCHED.labels(source=SOURCE).inc(
            result.get("items_in_list", 0)
        )
    except Exception:
        pass

    return result
