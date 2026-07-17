"""DOM-SC Crawler adapter — Extra Consultoria.

Extrai metadados estruturados de contratos, convenios e empenhos do
Diario Oficial dos Municipios de Santa Catarina via API REST v2.

API documentada em: diariomunicipal.sc.gov.br/?r=site/page&view=integracao
Autenticacao: HTTP Basic Auth (CPF:CNPJ) + header X-API-Key

Endpoint migrado:
  - ANTIGO: ?r=remote/search (removed — returns 404)
  - NOVO:   ?r=remote/list  (native pagination via page + count)

Adaptado para a interface sync esperada pelo monitor.py:
    crawl(mode) -> list[dict]       # busca dados brutos da API
    transform(records) -> list[dict] # normaliza para schema pncp_raw_bids

Version: 2.0.0 (API migration)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from scripts.crawl.common import (
    digits_only as _digits_only,
)
from scripts.crawl.common import (
    parse_date as _parse_date,
)
from scripts.crawl.common import (
    safe_float as _safe_float,
)
from scripts.crawl.dlq_sync import dlq_write
from scripts.crawl.provenance_sync import provenance_complete, provenance_fail, provenance_start
from scripts.crawl.security import USER_AGENT, sanitize_url_param, validate_url_scheme
from scripts.crawl.watermark_sync import watermark_commit

# Add project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://diariomunicipal.sc.gov.br"

# Categorias de atos com metadados estruturados obrigatorios:
#   6 = Contratos
#   7 = Convenios
#   28 = Empenhos
CATEGORIAS = [6, 7, 28]

CATEGORIA_NOMES: dict[int, str] = {
    6: "Contrato",
    7: "Convenio",
    28: "Empenho",
}

# Mapeamento reverso: nome da categoria (string da nova API) -> ID numerico
CATEGORIA_NOME_PARA_ID: dict[str, int] = {
    "Contrato": 6,
    "Convenio": 7,
    "Empenho": 28,
}

# Configuracoes do endpoint /list
API_LIST_ENDPOINT = f"{BASE_URL}/?r=remote/list"
API_PAGE_SIZE = 100  # Items per page (count parameter)
API_MAX_PAGES = 20  # Max pages per categoria

HTTP_TIMEOUT = 60  # Timeout per API call (seconds)
DELAY_BETWEEN_PAGES = 0.3  # Seconds between page calls (rate limit)
DELAY_BETWEEN_CATEGORIAS = 0.5  # Seconds between categoria calls (rate limit)

# Configuracoes de janela temporal
DOM_SC_FULL_DAYS = int(os.getenv("DOM_SC_FULL_DAYS", "180"))
DOM_SC_INCREMENTAL_DAYS = int(os.getenv("DOM_SC_INCREMENTAL_DAYS", "3"))

# Feature flag
DOM_SC_ENABLED = os.getenv("DOM_SC_ENABLED", "true").lower() in ("true", "1")

# Auth env vars
DOM_SC_CPF = os.getenv("DOM_SC_CPF", "")
DOM_SC_CNPJ = os.getenv("DOM_SC_CNPJ", "")
DOM_SC_API_KEY = os.getenv("DOM_SC_API_KEY", "")

# Esfera municipal (3 = Municipal no padrao PNCP)
ESFERA_ID_MUNICIPAL = 3

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Helpers _digits_only, _parse_date, _safe_float imported from common.py (TD-3.2)


# ---------------------------------------------------------------------------
# HTTP Client (sync, stdlib only)
# ---------------------------------------------------------------------------


def _api_request(url: str, params: dict[str, Any]) -> dict | None:
    """Make a sync HTTP GET request to the DOM-SC API.

    Uses HTTP Basic Auth (CPF:CNPJ) + header X-API-Key.

    Returns:
        Parsed JSON dict, or None on failure.
    """
    import urllib.error
    import urllib.request

    query = "&".join(f"{k}={sanitize_url_param(v)}" for k, v in params.items())
    full_url = f"{url}?{query}"

    # Build Basic Auth header manually (urllib BasicAuth can be tricky)
    import base64

    credentials = f"{DOM_SC_CPF}:{DOM_SC_CNPJ}"
    encoded_creds = base64.b64encode(credentials.encode("utf-8")).decode("ascii")

    req = urllib.request.Request(full_url)  # noqa: S310 — validated at caller (hardcoded HTTPS BASE_URL)
    req.add_header("Authorization", f"Basic {encoded_creds}")
    req.add_header("X-API-Key", DOM_SC_API_KEY)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:  # noqa: S310 — validated at caller (hardcoded HTTPS BASE_URL)
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            _logger.error("[DOM-SC] Auth failure (401) — check DOM_SC_CPF, DOM_SC_CNPJ, DOM_SC_API_KEY env vars")
        elif exc.code == 429:
            _logger.warning("[DOM-SC] Rate limited (429) — waiting before retry")
        else:
            _logger.error(
                "[DOM-SC] HTTP %d on %s: %s",
                exc.code,
                full_url,
                exc,
            )
        return None
    except Exception as exc:
        _logger.error(
            "[DOM-SC] Request failed: %s: %s",
            type(exc).__name__,
            exc,
        )
        return None


# ---------------------------------------------------------------------------
# Municipality coverage logging (adaptado para nova API)
# ---------------------------------------------------------------------------


def _log_municipio_coverage(records: list[dict]) -> None:
    """Log municipality-level coverage stats from crawled records.

    Uses ``municipio`` field when available, otherwise logs per-entity stats
    based on ``orgao_nome`` and ``orgao_cnpj``.
    """
    municipios: Counter[str] = Counter()
    orgaos: Counter[str] = Counter()

    for r in records:
        muni = (r.get("municipio") or "").strip()
        if muni:
            municipios[muni] += 1
        orgao = (r.get("orgao_nome") or r.get("orgao_razao_social") or "").strip()
        if orgao:
            orgaos[orgao] += 1

    if municipios:
        _logger.info(
            "[DOM-SC] Coverage by municipio: %d municipios, %d records",
            len(municipios),
            sum(municipios.values()),
        )
        for muni, count in municipios.most_common(5):
            _logger.info("[DOM-SC]   %s: %d records", muni, count)
        low_coverage = [m for m, c in municipios.items() if c < 3]
        if low_coverage:
            _logger.warning("[DOM-SC] %d municipios with < 3 records", len(low_coverage))
    else:
        _logger.info("[DOM-SC] No municipio data — %d records, %d orgaos", len(records), len(orgaos))


# ---------------------------------------------------------------------------
# Individual publication detail fetcher
# ---------------------------------------------------------------------------


def _fetch_publication_detail(url_origem: str) -> dict | None:
    """Fetch an individual publication page to extract entity data.

    The ``url_origem_api`` from the list endpoint points to an HTML page
    containing full publication details including entity CNPJ/name.

    Args:
        url_origem: URL to the individual publication page.

    Returns:
        Dict with extracted entity data, or None on failure.
    """
    import urllib.error
    import urllib.request

    if not url_origem:
        return None
    validate_url_scheme(url_origem)

    import base64

    credentials = f"{DOM_SC_CPF}:{DOM_SC_CNPJ}"
    encoded_creds = base64.b64encode(credentials.encode("utf-8")).decode("ascii")

    req = urllib.request.Request(url_origem)  # noqa: S310 — validated above
    req.add_header("Authorization", f"Basic {encoded_creds}")
    req.add_header("X-API-Key", DOM_SC_API_KEY)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "application/json, text/html")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 — validated above
            body = resp.read().decode("utf-8", errors="replace")

        # Try JSON first (API response)
        content_type = resp.headers.get("Content-Type", "")
        if "json" in content_type:
            try:
                return json.loads(body)
            except (json.JSONDecodeError, ValueError):
                pass

        # Fallback: parse HTML for entity info
        entity_info: dict[str, Any] = {}

        # Extract CNPJ from HTML (pattern: XX.XXX.XXX/XXXX-XX or XXXXXXXXXXXXXX)
        cnpj_match = re.search(r"(\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2})", body)
        if cnpj_match:
            entity_info["orgao_cnpj"] = "".join(c for c in cnpj_match.group(1) if c.isdigit())

        # Extract entity name from title/headers
        title_match = re.search(r"<title>(.*?)</title>", body, re.IGNORECASE)
        if title_match:
            entity_info["orgao_nome"] = title_match.group(1).strip()

        h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.IGNORECASE)
        if h1_match:
            h1_text = re.sub(r"<[^>]+>", "", h1_match.group(1)).strip()
            if h1_text:
                entity_info["orgao_nome"] = h1_text

        # Extract municipio from page text
        muni_match = re.search(r"(?:Munic[ií]pio|Cidade)[:\s]+([A-Z][A-Za-z\s]+?)(?:<|$)", body)
        if muni_match:
            entity_info["municipio"] = muni_match.group(1).strip()

        if entity_info.get("orgao_cnpj") or entity_info.get("orgao_nome"):
            return entity_info

        return None
    except Exception as exc:
        _logger.debug("[DOM-SC] Detail fetch failed for %s: %s", url_origem[:80], exc)
        return None


# ---------------------------------------------------------------------------
# Pagination-aware fetching (nova API /list)
# ---------------------------------------------------------------------------


def _fetch_all_pages(categoria_nome: str, date_from: date, date_to: date) -> tuple[list[dict], int]:
    """Fetch all publication pages for a category via ``?r=remote/list``.

    Uses native pagination with ``page`` and ``count`` parameters.
    Attempts to enrich each record with entity data by fetching individual
    publication details via ``url_origem_api``.

    Args:
        categoria_nome: Category name string (e.g. "Contrato", "Convenio").
        date_from: Start date.
        date_to: End date.

    Returns:
        Tuple of (list of enriched publication dicts, total_fetched count).
    """
    all_items: list[dict] = []
    total = 0

    for page in range(1, API_MAX_PAGES + 1):
        params: dict[str, Any] = {
            "categoria": categoria_nome,
            "data_inicio": date_from.strftime("%d/%m/%Y"),
            "data_fim": date_to.strftime("%d/%m/%Y"),
            "page": page,
            "count": API_PAGE_SIZE,
        }

        data = _api_request(API_LIST_ENDPOINT, params)
        if data is None:
            _logger.info("[DOM-SC] Stopped at page %d (request failed)", page)
            break

        if not data.get("ok", False):
            _logger.warning("[DOM-SC] Page %d returned ok=false", page)
            break

        items = data.get("result", [])
        if not isinstance(items, list) or not items:
            _logger.info("[DOM-SC] Stopped at page %d (empty result)", page)
            break

        # Enrich each record with entity data from individual detail page
        enriched = []
        for item in items:
            url_origem = (item.get("url_origem_api") or "").strip()
            entity_data = _fetch_publication_detail(url_origem) if url_origem else None
            if entity_data:
                item.update(entity_data)
            enriched.append(item)

        all_items.extend(enriched)
        total += len(items)
        _logger.debug("[DOM-SC] Page %d: %d publications", page, len(items))

        # Last page: fewer items than page size
        if len(items) < API_PAGE_SIZE:
            break

        time.sleep(DELAY_BETWEEN_PAGES)

    _logger.info("[DOM-SC] %s: %d publications across %d pages", categoria_nome, total, (total // API_PAGE_SIZE) + 1)
    return all_items, total


# ---------------------------------------------------------------------------
# API data fetching (nova API /list)
# ---------------------------------------------------------------------------


def _fetch_publications(date_from: date, date_to: date) -> list[dict]:
    """Fetch all publications with entity data for the given date range.

    Uses the new ``?r=remote/list`` endpoint with native pagination
    (``page`` + ``count``). For each publication, tries to enrich with
    entity data by fetching the individual detail page via ``url_origem_api``.

    Each categoria response includes publications from ALL 295+ municipios
    within the date range.

    Returns:
        List of raw publication dicts from the API, enriched with entity data.
    """
    all_items: list[dict] = []
    total_fetched = 0

    for categoria_id in CATEGORIAS:
        categoria_nome = CATEGORIA_NOMES[categoria_id]

        # Fetch via new API endpoint with pagination
        items, count = _fetch_all_pages(categoria_nome, date_from, date_to)
        all_items.extend(items)
        total_fetched += count

        _logger.info(
            "[DOM-SC] Categoria %d (%s): %d publications for %s - %s",
            categoria_id,
            categoria_nome,
            count,
            date_from,
            date_to,
        )

        # Municipality-level logging per categoria
        _log_municipio_coverage(items)

        # Rate limiting between categoria calls
        if categoria_id != CATEGORIAS[-1]:
            time.sleep(DELAY_BETWEEN_CATEGORIAS)

    if not all_items and total_fetched == 0:
        _logger.warning("[DOM-SC] No publications returned — check credentials and API availability")

    _logger.info(
        "[DOM-SC] Total: %d publications across %d categories",
        total_fetched,
        len(CATEGORIAS),
    )
    return all_items


# ---------------------------------------------------------------------------
# Crawler interface (called by monitor.py)
# ---------------------------------------------------------------------------


def crawl(mode: str = "full", resume: bool = False) -> list[dict]:
    """Crawl DOM-SC API for all categories.

    Args:
        mode: 'full' (180 days) or 'incremental' (3 days)
        resume: If True, resume from last committed watermark.

    Returns:
        List of raw publication dicts from the API.
    """
    # Feature flag check
    if not DOM_SC_ENABLED:
        _logger.info("[DOM-SC] Disabled (DOM_SC_ENABLED=false)")
        return []

    # Credential check
    if not DOM_SC_CPF or not DOM_SC_CNPJ or not DOM_SC_API_KEY:
        _logger.warning("[DOM-SC] Missing credentials — set DOM_SC_CPF, DOM_SC_CNPJ, DOM_SC_API_KEY env vars")
        return []

    days = DOM_SC_FULL_DAYS if mode == "full" else DOM_SC_INCREMENTAL_DAYS
    data_final = date.today()
    data_inicial = data_final - timedelta(days=days)
    run_id = f"dom_sc-{int(time.time())}"

    _logger.info(
        "[DOM-SC] Crawling %s mode: %s to %s (%d days)",
        mode,
        data_inicial,
        data_final,
        days,
    )

    # Provenance: start run
    provenance_start(source="dom_sc", mode=mode, params={"data_inicial": str(data_inicial), "data_final": str(data_final)})

    try:
        raw_records = _fetch_publications(data_inicial, data_final)
        _logger.info("[DOM-SC] Fetched %d raw records", len(raw_records))

        # Provenance: complete run
        provenance_complete(run_id, "dom_sc", records_fetched=len(raw_records))

        # Watermark: commit date range
        if resume:
            watermark_commit(source="dom_sc", scope_key="date", value=str(data_final), run_id=run_id)
    except Exception as e:
        _logger.error("[DOM-SC] Crawl failed: %s", e)
        dlq_write(
            source="dom_sc",
            run_id=run_id,
            stage="fetch",
            error_code="crawl_failed",
            error_message=str(e)[:2000],
            payload={"mode": mode, "data_inicial": str(data_inicial), "data_final": str(data_final)},
        )
        provenance_fail(run_id, "dom_sc", error_message=str(e))
        return []

    return raw_records


# ---------------------------------------------------------------------------
# Transform helpers (adaptado para nova API /list)
# ---------------------------------------------------------------------------


def _generate_content_hash(record: dict) -> str:
    """Deterministic MD5 hash for dedup.

    Uses key fields from the new API: orgao_cnpj (if available),
    codigo (publication code from API), data_publicacao.
    Falls back to titulo if codigo/orgao_cnpj not available.
    """
    codigo = str(record.get("codigo") or "")
    orgao_cnpj = _digits_only(record.get("orgao_cnpj") or "")
    data_pub = _parse_date(record.get("data_publicacao")) or ""

    # Use codigo as primary key (unique per API)
    key_fields = [orgao_cnpj, codigo, data_pub]
    if not orgao_cnpj:
        # Fallback: use titulo
        titulo = (record.get("titulo") or "").strip()
        key_fields[0] = titulo

    key_str = "|".join(key_fields)
    return hashlib.md5(key_str.encode("utf-8"), usedforsecurity=False).hexdigest()


def _transform_record(raw: dict) -> dict | None:
    """Transform a single DOM-SC publication into pncp_raw_bids schema.

    Handles both the new API format (``?r=remote/list``) and the old
    format (``?r=remote/search``) for backward compatibility.

    New format fields: codigo, titulo, categoria (string), data_publicacao,
    url_origem_api, status (may be enriched with orgao_cnpj, orgao_nome,
    municipio from individual detail page fetch).

    Old format fields: categoria (int), orgao_cnpj, orgao_nome, municipio,
    metadados (dict), data_publicacao.

    Returns None if the record lacks a unique identifier (codigo or numero).
    """
    try:
        # Detect API format: new API uses codigo (int), old uses metadados.numero
        codigo = raw.get("codigo")
        metadados = raw.get("metadados", {}) or {}
        numero = (metadados.get("numero") or "").strip()

        # Unique identifier: prefer codigo (new API), fallback to numero (old API)
        unique_id = str(codigo) if codigo is not None else numero
        if not unique_id:
            _logger.debug("[DOM-SC] Skipping record — missing codigo or numero")
            return None

        # Entity data: may be enriched from detail page, or from old API format
        orgao_cnpj_raw = (raw.get("orgao_cnpj") or "").strip()
        orgao_cnpj = _digits_only(orgao_cnpj_raw)
        orgao_nome = (raw.get("orgao_nome") or raw.get("titulo") or "").strip()

        # Parse categoria: new API returns string name, old API returns int
        categoria_raw = raw.get("categoria")
        if isinstance(categoria_raw, str):
            # New API: string category name -> map to ID
            categoria_id = CATEGORIA_NOME_PARA_ID.get(categoria_raw, 0)
            cat_name = categoria_raw
        else:
            # Old API: integer category ID
            categoria_id = int(categoria_raw) if categoria_raw is not None else 0
            cat_name = CATEGORIA_NOMES.get(categoria_id, f"Categoria {categoria_id}")

        # Municipio: may come from detail enrichment or old API
        municipio = (raw.get("municipio") or "").strip()

        # Valor: from old API metadados, or new API (not available in list)
        valor = _safe_float(metadados.get("valor"))

        # Date
        data_pub_raw = raw.get("data_publicacao", "")
        data_publicacao = _parse_date(data_pub_raw) or ""

        # Build objeto_compra from available data
        desc_parts: list[str] = [f"{cat_name} - {municipio or orgao_nome or 'SC'} - SC"]
        if metadados.get("numero_processo"):
            desc_parts.append(f"Processo: {metadados['numero_processo']}")
        if raw.get("titulo"):
            titulo = (raw.get("titulo") or "").strip()
            if titulo and titulo not in desc_parts[0]:
                desc_parts.append(titulo)
        objeto_compra = " | ".join(desc_parts)
        if len(objeto_compra) > 500:
            objeto_compra = objeto_compra[:497] + "..."

        # Build link: prefer url_origem_api (new API), fallback to url_processo (old API)
        url_origem = (raw.get("url_origem_api") or "").strip()
        url_processo = (metadados.get("url_processo") or "").strip()
        link_pncp = url_origem or url_processo or f"{BASE_URL}/?r=remote/list&categoria={cat_name}"

        # Build pncp_id from available fields
        pncp_id_input = f"{orgao_cnpj or 'unknown'}|{unique_id}|{data_publicacao}"
        pncp_id = hashlib.md5(pncp_id_input.encode("utf-8"), usedforsecurity=False).hexdigest()

        return {
            "pncp_id": pncp_id,
            "objeto_compra": objeto_compra,
            "valor_total_estimado": valor,
            "modalidade_id": categoria_id,
            "modalidade_nome": cat_name,
            "esfera_id": ESFERA_ID_MUNICIPAL,
            "uf": "SC",
            "municipio": municipio or None,
            "codigo_municipio_ibge": "",
            "orgao_razao_social": orgao_nome or None,
            "orgao_cnpj": orgao_cnpj or None,
            "data_publicacao": data_publicacao,
            "data_abertura": None,
            "data_encerramento": None,
            "link_pncp": link_pncp,
            "content_hash": _generate_content_hash(raw),
            "source_id": unique_id,
        }
    except Exception as exc:
        _logger.warning("[DOM-SC] Transform error: %s: %s", type(exc).__name__, exc)
        return None


# ---------------------------------------------------------------------------
# Transform interface (called by monitor.py)
# ---------------------------------------------------------------------------


def transform(raw_records: list[dict]) -> list[dict]:
    """Transform raw DOM-SC records to unified pncp_raw_bids schema.

    Args:
        raw_records: List of raw publication dicts from crawl().

    Returns:
        List of dicts normalized to pncp_raw_bids schema.
    """
    transformed = []
    skipped = 0

    for rec in raw_records:
        t = _transform_record(rec)
        if t and t.get("orgao_cnpj"):
            transformed.append(t)
        else:
            skipped += 1

    if skipped:
        _logger.info("[DOM-SC] Transform complete: %d records, %d skipped", len(transformed), skipped)
    else:
        _logger.info("[DOM-SC] Transform complete: %d records", len(transformed))

    return transformed
