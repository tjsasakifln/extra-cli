"""DOM-SC Crawler adapter — Extra Consultoria.

Extrai metadados estruturados de contratos (categoria 6), convenios (7) e
empenhos (28) do Diario Oficial dos Municipios de Santa Catarina via API REST.

API documentada em: diariomunicipal.sc.gov.br/?r=site/page&view=integracao
Autenticacao: HTTP Basic Auth (CPF:CNPJ) + header X-API-Key

Adaptado para a interface sync esperada pelo monitor.py:
    crawl(mode) -> list[dict]       # busca dados brutos da API
    transform(records) -> list[dict] # normaliza para schema pncp_raw_bids
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.crawl.common import (
    digits_only as _digits_only,
    parse_date as _parse_date,
    safe_float as _safe_float,
)
from scripts.crawl.security import USER_AGENT, sanitize_url_param

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

HTTP_TIMEOUT = 60           # Timeout per API call (seconds)
DELAY_BETWEEN_CATEGORIAS = 0.5  # Seconds between categoria calls (rate limit)

# Configuracoes de janela temporal
DOM_SC_FULL_DAYS = int(os.getenv("DOM_SC_FULL_DAYS", "90"))
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

    req = urllib.request.Request(full_url)
    req.add_header("Authorization", f"Basic {encoded_creds}")
    req.add_header("X-API-Key", DOM_SC_API_KEY)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            _logger.error(
                "[DOM-SC] Auth failure (401) — check DOM_SC_CPF, DOM_SC_CNPJ, "
                "DOM_SC_API_KEY env vars"
            )
        elif exc.code == 429:
            _logger.warning("[DOM-SC] Rate limited (429) — waiting before retry")
        else:
            _logger.error(
                "[DOM-SC] HTTP %d on %s: %s", exc.code, full_url, exc,
            )
        return None
    except Exception as exc:
        _logger.error(
            "[DOM-SC] Request failed: %s: %s", type(exc).__name__, exc,
        )
        return None


# ---------------------------------------------------------------------------
# API data fetching
# ---------------------------------------------------------------------------


def _fetch_publications(date_from: date, date_to: date) -> list[dict]:
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

        data = _api_request(url, params)
        if data is None:
            _logger.warning(
                "[DOM-SC] Skipping categoria %d after request failure", categoria,
            )
            continue

        items = data.get("publicacoes", [])
        if not isinstance(items, list):
            items = []

        all_items.extend(items)
        total_fetched += len(items)
        _logger.info(
            "[DOM-SC] Categoria %d (%s): %d publications for %s - %s",
            categoria, CATEGORIA_NOMES.get(categoria, "?"),
            len(items), date_from, date_to,
        )

        # Rate limiting between categoria calls
        if categoria != CATEGORIAS[-1]:
            time.sleep(DELAY_BETWEEN_CATEGORIAS)

    _logger.info(
        "[DOM-SC] Total: %d publications across %d categories",
        total_fetched, len(CATEGORIAS),
    )
    return all_items


# ---------------------------------------------------------------------------
# Crawler interface (called by monitor.py)
# ---------------------------------------------------------------------------


def crawl(mode: str = "full") -> list[dict]:
    """Crawl DOM-SC API for all categories.

    Args:
        mode: 'full' (90 days) or 'incremental' (3 days)

    Returns:
        List of raw publication dicts from the API.
    """
    # Feature flag check
    if not DOM_SC_ENABLED:
        _logger.info("[DOM-SC] Disabled (DOM_SC_ENABLED=false)")
        return []

    # Credential check
    if not DOM_SC_CPF or not DOM_SC_CNPJ or not DOM_SC_API_KEY:
        _logger.warning(
            "[DOM-SC] Missing credentials — set DOM_SC_CPF, DOM_SC_CNPJ, "
            "DOM_SC_API_KEY env vars"
        )
        return []

    days = DOM_SC_FULL_DAYS if mode == "full" else DOM_SC_INCREMENTAL_DAYS
    data_final = date.today()
    data_inicial = data_final - timedelta(days=days)

    _logger.info(
        "[DOM-SC] Crawling %s mode: %s to %s (%d days)",
        mode, data_inicial, data_final, days,
    )

    raw_records = _fetch_publications(data_inicial, data_final)
    _logger.info("[DOM-SC] Fetched %d raw records", len(raw_records))

    return raw_records


# ---------------------------------------------------------------------------
# Transform helpers
# ---------------------------------------------------------------------------


def _generate_content_hash(record: dict) -> str:
    """Deterministic MD5 hash for dedup.

    Uses key fields: orgao_cnpj, numero (from metadados), data_publicacao.
    """
    metadados = record.get("metadados", {}) or {}
    numero = (metadados.get("numero") or "").strip()
    orgao_cnpj = _digits_only(record.get("orgao_cnpj") or "")
    data_pub = _parse_date(record.get("data_publicacao")) or ""

    key_fields = [orgao_cnpj, numero, data_pub]
    key_str = "|".join(key_fields)
    return hashlib.md5(key_str.encode("utf-8"), usedforsecurity=False).hexdigest()


def _transform_record(raw: dict) -> dict | None:
    """Transform a single DOM-SC publication into pncp_raw_bids schema.

    Returns None if the record lacks required fields (numero or orgao_cnpj).
    """
    try:
        metadados = raw.get("metadados", {}) or {}
        numero = (metadados.get("numero") or "").strip()
        orgao_cnpj_raw = (raw.get("orgao_cnpj") or "").strip()
        orgao_cnpj = _digits_only(orgao_cnpj_raw)
        data_pub_raw = raw.get("data_publicacao", "")

        if not numero or not orgao_cnpj:
            _logger.debug("[DOM-SC] Skipping record — missing numero or orgao_cnpj")
            return None

        # Parse valor
        valor = _safe_float(metadados.get("valor"))

        # Build synthetic pncp_id
        pncp_id_input = f"{orgao_cnpj}|{numero}|{_parse_date(data_pub_raw) or ''}"
        pncp_id = hashlib.md5(pncp_id_input.encode("utf-8"), usedforsecurity=False).hexdigest()

        # Build objeto_compra from available data
        categoria_raw = raw.get("categoria")
        categoria = int(categoria_raw) if categoria_raw is not None else 0
        cat_name = CATEGORIA_NOMES.get(categoria, f"Categoria {categoria}")
        municipio = (raw.get("municipio") or "").strip()

        desc_parts = [f"{cat_name} - {municipio} - SC"]
        numero_processo = metadados.get("numero_processo", "")
        if numero_processo:
            desc_parts.append(f"Processo: {numero_processo}")
        objeto_compra = " | ".join(desc_parts)
        if len(objeto_compra) > 500:
            objeto_compra = objeto_compra[:497] + "..."

        # Build link
        url_processo = (metadados.get("url_processo") or "").strip()
        link_pncp = url_processo if url_processo else (
            f"{BASE_URL}/?r=remote/search&categoria={categoria}"
        )

        data_publicacao = _parse_date(data_pub_raw) or ""

        orgao_nome = (raw.get("orgao_nome") or "").strip()

        return {
            "pncp_id": pncp_id,
            "objeto_compra": objeto_compra,
            "valor_total_estimado": valor,
            "modalidade_id": categoria,
            "modalidade_nome": cat_name,
            "esfera_id": ESFERA_ID_MUNICIPAL,
            "uf": "SC",
            "municipio": municipio,
            "codigo_municipio_ibge": "",
            "orgao_razao_social": orgao_nome or None,
            "orgao_cnpj": orgao_cnpj or None,
            "data_publicacao": data_publicacao,
            "data_abertura": None,
            "data_encerramento": None,
            "link_pncp": link_pncp,
            "content_hash": _generate_content_hash(raw),
            "source_id": pncp_id,
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
        _logger.info("[DOM-SC] Transform complete: %d records, %d skipped",
                      len(transformed), skipped)
    else:
        _logger.info("[DOM-SC] Transform complete: %d records", len(transformed))

    return transformed
