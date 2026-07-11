"""Crawler sync adapter for Portal de Compras SC (compras.sc.gov.br).

Adapted from legacy async/httpx/class-based crawler to the simple sync interface
expected by monitor.py: crawl(mode) -> list[dict], transform(records) -> list[dict].

Sources:
  - compras.sc.gov.br — Main unified portal (primary)
  - e-lic.sc.gov.br — Electronic bidding system (Paradigma platform, secondary)

Stdlib only: urllib, re, json, hashlib, logging, os, time, datetime, unicodedata.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.crawl.security import sanitize_url_param

# Add project root to path for standalone usage
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (env vars with SC_COMPRAS_ prefix)
# ---------------------------------------------------------------------------

BASE_URL = os.getenv("SC_COMPRAS_BASE_URL", "https://compras.sc.gov.br")
E_LIC_URL = os.getenv("SC_COMPRAS_E_LIC_URL", "https://e-lic.sc.gov.br")

HTTP_TIMEOUT = int(os.getenv("SC_COMPRAS_TIMEOUT", "45"))
MAX_RETRIES = int(os.getenv("SC_COMPRAS_MAX_RETRIES", "3"))
PAGE_DELAY_S = float(os.getenv("SC_COMPRAS_PAGE_DELAY_S", "1.0"))
MAX_PAGES = int(os.getenv("SC_COMPRAS_MAX_PAGES", "100"))

SC_COMPRAS_FULL_DAYS = int(os.getenv("SC_COMPRAS_FULL_DAYS", "30"))
SC_COMPRAS_INCREMENTAL_DAYS = int(os.getenv("SC_COMPRAS_INCREMENTAL_DAYS", "3"))

# ---------------------------------------------------------------------------
# Modalidade mapping
# ---------------------------------------------------------------------------

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


def _normalize_modalidade(raw: str) -> str:
    """Normalize modalidade string for lookup — strip accents, lowercase, clean."""
    s = raw.strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"^\d+[\.\)]\s*", "", s)
    s = re.sub(r"[\(\)]", "", s)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    return s


def _map_modalidade(raw: str) -> tuple[int | None, str]:
    """Map SC portal modalidade string to (modalidade_id, modalidade_nome).

    Returns (None, raw) if not found.
    """
    normalized = _normalize_modalidade(raw)
    mid = _MODALIDADE_MAP.get(normalized)
    if mid is not None:
        return mid, raw.strip()
    # Fuzzy fallback
    for key, mid in _MODALIDADE_MAP.items():
        if key in normalized or normalized in key:
            return mid, raw.strip()
    _logger.debug("[ScCompras] Unknown modalidade: '%s' (normalized: '%s')", raw, normalized)
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
    """Infer sphere from orgao name: 'E' (Estadual), 'M' (Municipal), or ''."""
    lower = orgao_nome.lower().strip()
    for kw in _ESFERA_ESTADUAL_KEYWORDS:
        if kw in lower:
            return "E"
    if lower.startswith("pm ") or lower.startswith("prefeitura"):
        return "M"
    return "E"


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------


def _digits_only(s: str | None) -> str:
    """Strip non-digits from a string."""
    if not s:
        return ""
    return re.sub(r"\D", "", s)


def _parse_br_date(s: str | None) -> str | None:
    """Parse DD/MM/YYYY to YYYY-MM-DD. Returns None if unparseable."""
    if not s or not s.strip():
        return None
    s = s.strip()
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    if re.match(r"\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    return None


def _parse_br_number(s: str | None) -> float | None:
    """Parse Brazilian-formatted number (e.g. '1.500,00' or '150000')."""
    if not s or not s.strip():
        return None
    s = s.strip().replace("R$", "").replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
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


def _content_hash(*parts: str) -> str:
    """Deterministic MD5 hash of joined parts for dedup."""
    raw = "|".join(parts)
    return hashlib.md5(raw.encode("utf-8"), usedforsecurity=False).hexdigest()


# ---------------------------------------------------------------------------
# HTML parsing (stdlib — regex-based, no BeautifulSoup)
# ---------------------------------------------------------------------------


def _extract_table_rows(html: str) -> list[dict]:
    """Extract rows from the portal's bootstrap table using regex.

    Returns list of dicts with keys:
        numero_processo, modalidade, objeto, orgao, data_publicacao,
        situacao, valor, url_detalhe
    """
    items: list[dict] = []

    # Locate <table class="table"> blocks
    table_pattern = re.compile(
        r'<table[^>]*class\s*=\s*["\'][^"\']*\btable\b[^"\']*["\'][^>]*>',
        re.IGNORECASE,
    )
    for table_match in table_pattern.finditer(html):
        # Find matching </table> (handle nesting naively)
        table_start = table_match.end()
        depth = 1
        i = table_start
        while i < len(html) and depth > 0:
            next_open = html.find("<table", i, i + 20)
            next_close = html.find("</table>", i)
            if next_close == -1:
                break
            if next_open != -1 and next_open < next_close:
                depth += 1
                i = next_open + 7
            else:
                depth -= 1
                i = next_close + 8
        if depth > 0:
            continue
        table_html = html[table_match.start():i]

        # Find tbody
        tbody_m = re.search(r'<tbody[^>]*>(.*?)</tbody>', table_html, re.DOTALL)
        if not tbody_m:
            continue
        tbody = tbody_m.group(1)

        # Extract rows
        for tr_m in re.finditer(r'<tr[^>]*>(.*?)</tr>', tbody, re.DOTALL):
            cells = re.findall(r'<td[^>]*>(.*?)</td>', tr_m.group(1), re.DOTALL)
            if len(cells) < 5:
                continue

            link_cell = cells[0]
            link_m = re.search(
                r'<a\s+[^>]*href\s*=\s*["\']([^"\']+)["\']', link_cell
            )
            url_detalhe = None
            if link_m:
                href = link_m.group(1).strip()
                url_detalhe = href if href.startswith("http") else f"{BASE_URL}{href}"

            def _strip_html(t: str) -> str:
                return re.sub(r'<[^>]+>', '', t).strip()

            items.append({
                "numero_processo": _strip_html(link_cell),
                "modalidade": _strip_html(cells[1]),
                "objeto": _strip_html(cells[2]),
                "orgao": _strip_html(cells[3]),
                "data_publicacao": _strip_html(cells[4]),
                "situacao": _strip_html(cells[5]) if len(cells) > 5 else "",
                "valor": _strip_html(cells[6]) if len(cells) > 6 else "",
                "url_detalhe": url_detalhe,
            })

    return items


# Label-to-key mapping for detail pages
_LABEL_MAP: dict[str, str] = {
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


def _normalize_label(text: str) -> str | None:
    """Map a Portuguese detail-page label to canonical key."""
    normalized = text.lower().strip().rstrip(":")
    normalized = unicodedata.normalize("NFKD", normalized)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    return _LABEL_MAP.get(normalized)


def _extract_detail_fields(html: str) -> dict:
    """Parse detail page HTML for additional fields using regex.

    Returns dict with canonical keys (numero_processo, orgao_cnpj, etc.).
    """
    detail_data: dict = {}

    # Try to find the detail container div
    container_pat = re.compile(
        r'<div[^>]*(?:class\s*=\s*["\'][^"\']*\b(?:detalhe-licitacao|panel-body|content-wrapper)\b[^"\']*["\'])',
        re.IGNORECASE,
    )
    container_m = container_pat.search(html)
    container_html = html[container_m.end():] if container_m else html

    # Extract <dl> definitions: <dt>label</dt><dd>value</dd>
    for dl_m in re.finditer(r'<dl[^>]*>(.*?)</dl>', container_html, re.DOTALL):
        inner = dl_m.group(1)
        dts = re.findall(r'<dt[^>]*>(.*?)</dt>', inner, re.DOTALL)
        dds = re.findall(r'<dd[^>]*>(.*?)</dd>', inner, re.DOTALL)
        for dt_text, dd_text in zip(dts, dds):
            key = _normalize_label(re.sub(r'<[^>]+>', '', dt_text).strip())
            val = re.sub(r'<[^>]+>', '', dd_text).strip()
            if key and val:
                detail_data[key] = val

    # Extract label-value pairs from Bootstrap form-group patterns
    field_patterns = [
        # <label>...</label> <span>...</span>
        r'<label[^>]*>(.*?)</label>[^<]*(?:<span[^>]*>(.*?)</span>|<p[^>]*>(.*?)</p>)',
        # <strong>...</strong> <span>...</span>
        r'<strong[^>]*>(.*?)</strong>[^<]*(?:<span[^>]*>(.*?)</span>|<p[^>]*>(.*?)</p>)',
    ]
    for pat in field_patterns:
        for m in re.finditer(pat, container_html, re.DOTALL | re.IGNORECASE):
            label = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            val = re.sub(r'<[^>]+>', '', (m.group(2) or m.group(3) or "")).strip()
            key = _normalize_label(label)
            if key and val and key not in detail_data:
                detail_data[key] = val

    return detail_data


# ---------------------------------------------------------------------------
# HTTP helpers (sync, urllib only)
# ---------------------------------------------------------------------------


def _fetch(url: str, params: dict[str, str] | None = None) -> str | None:
    """Fetch a URL via GET with retries. Returns body text or None on failure."""
    if params:
        query = "&".join(f"{k}={sanitize_url_param(v)}" for k, v in params.items())
        full_url = f"{url}?{query}"
    else:
        full_url = url

    last_error: str | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(full_url)
            req.add_header(
                "User-Agent",
                "Mozilla/5.0 (compatible; SmartLic-Bot/1.0; +https://smartlic.tech/bot)",
            )
            req.add_header("Accept", "text/html,application/xhtml+xml")

            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                if resp.status == 200:
                    return resp.read().decode("utf-8", errors="replace")
                _logger.warning(
                    "[ScCompras] HTTP %s for %s (attempt %d/%d)",
                    resp.status, full_url, attempt, MAX_RETRIES,
                )
                last_error = f"HTTP {resp.status}"

        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                _logger.debug("[ScCompras] %s returned %d — no data", full_url, e.code)
                return None
            _logger.warning(
                "[ScCompras] HTTP %d for %s (attempt %d/%d): %s",
                e.code, full_url, attempt, MAX_RETRIES, e,
            )
            last_error = f"HTTP {e.code}"
        except Exception as e:
            _logger.warning(
                "[ScCompras] Network error for %s (attempt %d/%d): %s",
                full_url, attempt, MAX_RETRIES, e,
            )
            last_error = str(e)

        if attempt < MAX_RETRIES:
            time.sleep(2.0 * attempt)

    _logger.error(
        "[ScCompras] Failed to fetch %s after %d attempts: %s",
        full_url, MAX_RETRIES, last_error,
    )
    return None


def _fetch_list_page(date_from: str, date_to: str, page: int) -> list[dict]:
    """Fetch one page of the SC portal listing. Returns parsed items."""
    # Primary URL
    html = _fetch(
        f"{BASE_URL}/licitacoes",
        {"pagina": str(page), "data_publicacao_inicio": date_from, "data_publicacao_fim": date_to},
    )
    if not html:
        # Fallback to e-lic URL
        html = _fetch(
            f"{E_LIC_URL}/licitacao",
            {"pagina": str(page), "data_inicio": date_from, "data_fim": date_to},
        )
        if not html:
            return []

    return _extract_table_rows(html)


def _fetch_detail_page(url: str) -> dict:
    """Fetch and parse a detail page. Returns dict or {} on failure."""
    if not url:
        return {}
    html = _fetch(url)
    if not html:
        return {}
    return _extract_detail_fields(html)


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def _normalize_item(raw: dict, detail: dict | None = None) -> dict | None:
    """Normalize a raw SC portal item to pncp_raw_bids schema.

    Merges optional detail data over raw list data before normalization.
    Returns None if item is skippable (empty numero_processo).

    Does NOT include 'source' — monitor.py adds it.
    Content hash uses MD5.
    """
    merged = dict(raw)
    if detail:
        merged.update(detail)

    numero = (merged.get("numero_processo") or "").strip()
    if not numero:
        return None

    pncp_id = f"sc-{numero}"
    objeto = (merged.get("objeto") or "").strip()
    if len(objeto) > 1000:
        objeto = objeto[:997] + "..."

    data_publicacao = (
        _parse_br_date(merged.get("data_publicacao"))
        or datetime.now().date().isoformat()
    )
    data_abertura = _parse_br_date(merged.get("data_abertura"))
    data_encerramento = _parse_br_date(merged.get("data_encerramento"))

    orgao = (merged.get("orgao") or "").strip()
    orgao_cnpj = _digits_only(merged.get("orgao_cnpj"))
    valor = _parse_br_number(merged.get("valor"))

    modalidade_raw = (merged.get("modalidade") or "").strip()
    modalidade_id, modalidade_nome = _map_modalidade(modalidade_raw)

    municipio = (merged.get("municipio") or "").strip()
    url_detalhe = (merged.get("url_detalhe") or "").strip()
    esfera = _infer_esfera(orgao)

    content_hash = _content_hash(pncp_id, data_publicacao, objeto)

    return {
        "pncp_id": pncp_id,
        "objeto_compra": objeto or None,
        "valor_total_estimado": round(valor, 2) if valor is not None else None,
        "modalidade_id": modalidade_id,
        "modalidade_nome": modalidade_nome or None,
        "esfera_id": esfera,
        "uf": "SC",
        "municipio": municipio or None,
        "codigo_municipio_ibge": None,  # Not available from SC portal
        "orgao_razao_social": orgao or None,
        "orgao_cnpj": orgao_cnpj or None,
        "data_publicacao": data_publicacao,
        "data_abertura": data_abertura or None,
        "data_encerramento": data_encerramento or None,
        "link_pncp": url_detalhe or None,
        "content_hash": content_hash,
        "source_id": pncp_id,
    }


# ---------------------------------------------------------------------------
# Public API (called by monitor.py)
# ---------------------------------------------------------------------------


def crawl(mode: str = "full") -> list[dict]:
    """Crawl SC Compras portal.

    Fetches list pages and their detail pages, merging all available fields
    into each raw record.

    Args:
        mode: 'full' (last 30 days) or 'incremental' (last 3 days)

    Returns:
        List of raw item dicts with fields from both list and detail pages.
        Empty list on failure (graceful degradation).
    """
    days = SC_COMPRAS_FULL_DAYS if mode == "full" else SC_COMPRAS_INCREMENTAL_DAYS
    today_d = date.today()
    date_from_d = today_d - timedelta(days=days)
    date_from = date_from_d.isoformat()
    date_to = today_d.isoformat()

    _logger.info("[ScCompras] Crawling %s mode: %s -> %s", mode, date_from, date_to)

    all_items: list[dict] = []
    pages_fetched = 0

    try:
        for page in range(1, MAX_PAGES + 1):
            items = _fetch_list_page(date_from, date_to, page)
            if not items:
                if page == 1:
                    _logger.warning(
                        "[ScCompras] Page 1 returned empty — portal may be unavailable"
                    )
                else:
                    _logger.info("[ScCompras] Page %d: empty — end of data", page)
                break

            pages_fetched += 1

            # Enrich with detail page data
            enriched: list[dict] = []
            for item in items:
                url = item.get("url_detalhe")
                detail = _fetch_detail_page(url) if url else {}
                enriched.append(dict(item, **detail))

            all_items.extend(enriched)
            _logger.debug(
                "[ScCompras] Page %d: %d items (total: %d)",
                page, len(enriched), len(all_items),
            )

            time.sleep(PAGE_DELAY_S)

    except Exception as e:
        _logger.warning("[ScCompras] Crawl error after %d pages: %s", pages_fetched, e)
        # Return what we have so far, don't raise

    _logger.info(
        "[ScCompras] Crawl complete: %d items from %d pages",
        len(all_items), pages_fetched,
    )
    return all_items


def transform(records: list[dict]) -> list[dict]:
    """Transform raw SC portal records to pncp_raw_bids schema.

    Pure normalization — does NOT fetch additional data.
    Does NOT include 'source' field (monitor.py adds it).

    Args:
        records: Raw records from crawl() (enriched with detail data)

    Returns:
        List of normalized dicts matching pncp_raw_bids schema.
    """
    normalized: list[dict] = []
    errors = 0

    for raw in records:
        try:
            rec = _normalize_item(raw)
            if rec:
                normalized.append(rec)
            else:
                errors += 1
        except Exception as e:
            _logger.warning("[ScCompras] Transform error: %s", e)
            errors += 1

    if errors:
        _logger.warning(
            "[ScCompras] Transform: %d/%d records skipped due to errors",
            errors, len(records),
        )

    _logger.info(
        "[ScCompras] Transform complete: %d -> %d normalized records",
        len(records), len(normalized),
    )
    return normalized
