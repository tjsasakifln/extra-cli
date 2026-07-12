"""DOE-SC Crawler adapter — Extra Consultoria.

Extrai licitacoes, contratos e editais publicados no Diario Oficial do
Estado de Santa Catarina (DOE-SC) via REST API com autenticacao Bearer.

Portal: https://portal.doe.sea.sc.gov.br
API base: https://portal.doe.sea.sc.gov.br/apis/doe-api/
Autenticacao: POST /login com login(CPF) + password -> Bearer token

Cobre 513 entidades estaduais de SC que publicam no diario oficial.

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
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from scripts.crawl.common import (
    digits_only,
    extract_cnpj,
    parse_date,
    safe_float,
)

# Add project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DOE_SC_API_HOST = os.getenv(
    "DOE_SC_API_HOST",
    "https://portal.doe.sea.sc.gov.br/apis",
)
DOE_SC_API_BASE = f"{DOE_SC_API_HOST}/doe-api"
DOE_SC_PORTAL = "https://portal.doe.sea.sc.gov.br"

# Credentials para autenticacao
DOE_SC_LOGIN = os.getenv("DOE_SC_LOGIN", "")
DOE_SC_PASSWORD = os.getenv("DOE_SC_PASSWORD", "")

# Feature flag
DOE_SC_ENABLED = os.getenv("DOE_SC_ENABLED", "true").lower() in ("true", "1")

# Janela temporal
DOE_SC_FULL_DAYS = int(os.getenv("DOE_SC_FULL_DAYS", "90"))
DOE_SC_INCREMENTAL_DAYS = int(os.getenv("DOE_SC_INCREMENTAL_DAYS", "1"))

# HTTP config
HTTP_TIMEOUT = int(os.getenv("DOE_SC_HTTP_TIMEOUT", "30"))
HTTP_DELAY = float(os.getenv("DOE_SC_HTTP_DELAY", "1.0"))
MAX_RETRIES = int(os.getenv("DOE_SC_MAX_RETRIES", "2"))

# Paginacao
PAGE_SIZE = int(os.getenv("DOE_SC_PAGE_SIZE", "50"))
MAX_PAGES = int(os.getenv("DOE_SC_MAX_PAGES", "100"))

# Esfera estadual (2 = Estadual no padrao PNCP)
ESFERA_ID_ESTADUAL = 2

# Categorias relevantes para procurement (mapeamento sera feito via API)
# Valores serao preenchidos dinamicamente pelo _load_categories()
CATEGORIAS_RELEVANTES: set[int] = set()

# Cache de autenticacao
_auth_token: str | None = None
_auth_expires: float = 0.0

# Cache de categorias
_categories_cache: list[dict] | None = None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _digits_only(s: str | None) -> str:
    """Strip non-digit characters from a string (delegates to common)."""
    return digits_only(s)


def _parse_date(value: Any) -> str | None:
    """Parse a date from various formats to YYYY-MM-DD (delegates to common)."""
    return parse_date(value)


def _safe_float(value: Any) -> float | None:
    """Safely parse a numeric value to float (delegates to common)."""
    return safe_float(value)


def _extract_cnpj(text: str | None) -> str:
    """Extract CNPJ from text (delegates to common)."""
    return extract_cnpj(text)


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------


def _get_token() -> str | None:
    """Get a valid auth token, logging in if necessary.

    Returns:
        Bearer token string, or None if authentication fails.
    """
    global _auth_token, _auth_expires

    # Reuse cached token if not expired (conservative 30min cache)
    if _auth_token and time.time() < _auth_expires:
        return _auth_token

    if not DOE_SC_LOGIN or not DOE_SC_PASSWORD:
        _logger.warning("[DOE-SC] Missing credentials — set DOE_SC_LOGIN and DOE_SC_PASSWORD env vars")
        return None

    _logger.info("[DOE-SC] Authenticating with DOE_SC_LOGIN=%s...", DOE_SC_LOGIN[:3] + "***")

    import urllib.error
    import urllib.request

    # Login endpoint is at {DOE_SC_API_HOST}/login (/apis/login),
    # NOT {DOE_SC_API_BASE}/login (/apis/doe-api/login)
    url = f"{DOE_SC_API_HOST}/login"
    payload = json.dumps({"login": DOE_SC_LOGIN, "password": DOE_SC_PASSWORD}).encode("utf-8")

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header(
        "User-Agent",
        "Extra-Consultoria/1.0 (consultoria-licitacoes)",
    )

    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body)

        # Response structure varies; try common patterns
        token = (
            data.get("token")
            or data.get("access_token")
            or data.get("data", {}).get("token")
            or data.get("data", {}).get("access_token")
        )
        if token:
            _auth_token = str(token)
            _auth_expires = time.time() + 1800  # 30 min cache
            _logger.info("[DOE-SC] Authentication successful")
            return _auth_token

        _logger.error("[DOE-SC] Login response has no token field: %s", str(data)[:200])
        return None

    except urllib.error.HTTPError as exc:
        body = b""
        try:
            body = exc.read()
        except (AttributeError, OSError):
            pass
        if exc.code == 401:
            _logger.error("[DOE-SC] Auth failure (401) on login — check DOE_SC_LOGIN and DOE_SC_PASSWORD")
        else:
            _logger.error("[DOE-SC] HTTP %d on login %s: %s", exc.code, url, body[:200])
        return None

    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        _logger.error(
            "[DOE-SC] Connection error on login %s: %s: %s",
            url,
            type(exc).__name__,
            exc,
        )
        return None

    except json.JSONDecodeError as exc:
        _logger.error("[DOE-SC] Invalid JSON in login response from %s: %s", url, exc)
        return None

    except Exception as exc:
        _logger.error("[DOE-SC] Login failed unexpectedly: %s: %s", type(exc).__name__, exc)
        return None


# ---------------------------------------------------------------------------
# HTTP client (sync, stdlib only)
# ---------------------------------------------------------------------------


def _api_request(
    path: str,
    params: dict[str, Any] | None = None,
    method: str = "GET",
    data: dict | None = None,
) -> dict | list | None:
    """Make an authenticated sync HTTP request to the DOE-SC API.

    Args:
        path: API path relative to base (e.g., "/materia").
        params: Optional query parameters.
        method: HTTP method.
        data: Optional JSON body for POST/PUT.

    Returns:
        Parsed JSON response (dict or list), or None on failure.
    """
    import urllib.error
    import urllib.request

    token = _get_token()
    if not token:
        return None

    # Build URL
    url = f"{DOE_SC_API_BASE}{path}"
    if params:
        query = "&".join(f"{k}={urllib.request.quote(str(v), safe='')}" for k, v in params.items() if v is not None)
        url = f"{url}?{query}"

    # Build request
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")
    req.add_header("Content-Type", "application/json")
    req.add_header(
        "User-Agent",
        "Extra-Consultoria/1.0 (consultoria-licitacoes)",
    )
    req.add_header("Origin", "https://portal.doe.sea.sc.gov.br")
    req.add_header("Referer", "https://portal.doe.sea.sc.gov.br/")

    if data is not None and method in ("POST", "PUT", "PATCH"):
        body = json.dumps(data).encode("utf-8")
        req.data = body

    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body)

        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                # Token might have expired — force re-login
                global _auth_token
                _auth_token = None
                if attempt < MAX_RETRIES:
                    _logger.info("[DOE-SC] Token expired, re-authenticating...")
                    # Clear cached pages on token expiry
                    continue
                _logger.error("[DOE-SC] Auth failure after re-auth on %s", path)
                return None

            if exc.code == 429:
                retry_after = int(exc.headers.get("Retry-After", "60"))
                _logger.warning("[DOE-SC] Rate limited. Waiting %ds", retry_after)
                time.sleep(retry_after)
                continue

            if exc.code in (404, 400):
                _logger.debug("[DOE-SC] HTTP %d on %s", exc.code, path)
                return None

            if attempt < MAX_RETRIES:
                delay = 2**attempt
                _logger.debug("[DOE-SC] HTTP %d, retrying in %ds", exc.code, delay)
                time.sleep(delay)
                continue

            _logger.warning(
                "[DOE-SC] HTTP %d after %d retries on %s",
                exc.code,
                MAX_RETRIES,
                path,
            )
            return None

        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt < MAX_RETRIES:
                delay = 1 + attempt
                _logger.debug(
                    "[DOE-SC] Connection error, retrying in %ds: %s",
                    delay,
                    exc,
                )
                time.sleep(delay)
                continue
            _logger.warning(
                "[DOE-SC] Fetch error after %d retries: %s",
                MAX_RETRIES,
                exc,
            )
            return None

    return None


# ---------------------------------------------------------------------------
# Category loading
# ---------------------------------------------------------------------------


def _load_categories() -> list[dict]:
    """Load all publication categories from the DOE-SC API.

    Caches the result globally to avoid repeated calls.

    Returns:
        List of category dicts with keys like id, descricao, etc.
    """
    global _categories_cache

    if _categories_cache is not None:
        return _categories_cache

    result = _api_request("/categoria")
    if result is None:
        _logger.warning("[DOE-SC] Could not load categories")
        _categories_cache = []
        return []

    # Response might be wrapped
    if isinstance(result, dict):
        data = result.get("data", result.get("records", result.get("result", [])))
        if isinstance(data, list):
            _categories_cache = data
        else:
            items = result.get("categorias", result.get("categoria", []))
            _categories_cache = items if isinstance(items, list) else []
    elif isinstance(result, list):
        _categories_cache = result
    else:
        _categories_cache = []

    _logger.info("[DOE-SC] Loaded %d categories", len(_categories_cache))

    # Identify procurement-relevant categories by name
    global CATEGORIAS_RELEVANTES
    procurement_keywords = [
        "licita",
        "contrat",
        "edital",
        "pregao",
        "concorrencia",
        "dispensa",
        "inexigibilidade",
        "convenio",
        "ata",
        "adjudicacao",
        "homologacao",
        "rescisao",
    ]
    for cat in _categories_cache:
        name = (cat.get("descricao") or cat.get("nome") or cat.get("dsCategoria") or "").lower()
        cat_id = cat.get("id") or cat.get("cdCategoria") or cat.get("codigo")
        if cat_id and any(kw in name for kw in procurement_keywords):
            try:
                CATEGORIAS_RELEVANTES.add(int(cat_id))
            except (ValueError, TypeError):
                pass

    _logger.info(
        "[DOE-SC] Identified %d procurement-relevant categories: %s",
        len(CATEGORIAS_RELEVANTES),
        sorted(CATEGORIAS_RELEVANTES),
    )

    return _categories_cache


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------


def _fetch_materias(
    date_from: date,
    date_to: date,
    categorias: set[int] | None = None,
) -> list[dict]:
    """Fetch published matters (materias) for the given date range.

    Iterates through paginated results from the API.

    Args:
        date_from: Start date (inclusive).
        date_to: End date (inclusive).
        categorias: Optional set of category IDs to filter by.
            If None, fetches all categories and filters procurement-relevant ones.

    Returns:
        List of raw materia dicts from the API.
    """
    all_items: list[dict] = []
    page = 1
    total_pages = 1

    # If no category filter specified, use procurement-relevant ones
    if categorias is None:
        _load_categories()
        categorias = CATEGORIAS_RELEVANTES if CATEGORIAS_RELEVANTES else None

    date_from_str = date_from.strftime("%Y-%m-%d")
    date_to_str = date_to.strftime("%Y-%m-%d")

    while page <= MAX_PAGES:
        params: dict[str, Any] = {
            "page": page,
            "perPage": PAGE_SIZE,
            "dtPublicacaoInicial": date_from_str,
            "dtPublicacaoFinal": date_to_str,
            "sort": "dtPublicacao",
            "sortOrder": "desc",
        }

        _logger.debug(
            "[DOE-SC] Fetching page %d/%d: %s to %s",
            page,
            total_pages,
            date_from_str,
            date_to_str,
        )

        result = _api_request("/materia", params)
        if result is None:
            _logger.warning("[DOE-SC] Stopping at page %d (API error)", page)
            break

        # Parse response — various possible wrappers
        records: list[dict] = []
        if isinstance(result, dict):
            records = (
                result.get("data") or result.get("records") or result.get("result") or result.get("materias") or []
            )
            # Try pagination info
            total_pages = result.get("totalPages") or result.get("pageCount") or result.get("lastPage") or total_pages
            if total_pages == 0:
                total_pages = 1
        elif isinstance(result, list):
            records = result
        else:
            records = []

        if not isinstance(records, list):
            records = []

        # If we have category filter, apply client-side
        if categorias:
            filtered = [
                r
                for r in records
                if r.get("cdCategoria") in categorias
                or r.get("categoria", {}).get("id") in categorias
                or r.get("idCategoria") in categorias
            ]
            all_items.extend(filtered)
            _logger.debug(
                "[DOE-SC] Page %d: %d records, %d after category filter",
                page,
                len(records),
                len(filtered),
            )
        else:
            all_items.extend(records)
            _logger.debug(
                "[DOE-SC] Page %d: %d records",
                page,
                len(records),
            )

        # Check if more pages
        if page >= total_pages:
            break
        page += 1
        time.sleep(HTTP_DELAY)

    _logger.info(
        "[DOE-SC] Fetched %d materias total",
        len(all_items),
    )
    return all_items


# ---------------------------------------------------------------------------
# Crawler interface (called by monitor.py)
# ---------------------------------------------------------------------------


def crawl(mode: str = "full") -> list[dict]:
    """Crawl DOE-SC API for procurement-related publications.

    Args:
        mode: 'full' (90 days) or 'incremental' (3 days)

    Returns:
        List of raw materia dicts from the API.
    """
    if not DOE_SC_ENABLED:
        _logger.info("[DOE-SC] Disabled (DOE_SC_ENABLED=false)")
        return []

    days = DOE_SC_FULL_DAYS if mode == "full" else DOE_SC_INCREMENTAL_DAYS
    data_final = date.today()
    data_inicial = data_final - timedelta(days=days)

    _logger.info(
        "[DOE-SC] Crawling %s mode: %s to %s (%d days)",
        mode,
        data_inicial,
        data_final,
        days,
    )

    # Ensure categories are loaded for filtering
    _load_categories()

    raw_records = _fetch_materias(data_inicial, data_final)
    _logger.info("[DOE-SC] Fetched %d raw records", len(raw_records))

    return raw_records


# ---------------------------------------------------------------------------
# Transform helpers
# ---------------------------------------------------------------------------


def _generate_content_hash(record: dict) -> str:
    """Deterministic MD5 hash for dedup.

    Uses key fields: id, titulo, cdCategoria, dtPublicacao.
    """
    materia_id = str(record.get("id") or record.get("cdMateria") or "")
    titulo = (record.get("titulo") or record.get("dsTitulo") or "").strip()
    categoria = str(record.get("cdCategoria") or record.get("idCategoria") or "")
    data_pub = _parse_date(record.get("dtPublicacao") or record.get("dataPublicacao") or "") or ""

    key_fields = [materia_id, titulo, categoria, data_pub]
    key_str = "|".join(key_fields)
    return hashlib.md5(key_str.encode("utf-8"), usedforsecurity=False).hexdigest()


def _extract_entity_info(text: str) -> tuple[str, str, str, str]:
    """Extract entity info (nome, cnpj, municipio, uf) from materia text.

    Uses regex patterns for CNPJ, municipality references, and orgão names.

    Returns:
        (orgao_nome, orgao_cnpj, municipio, uf)
    """
    if not text:
        return ("", "", "", "SC")

    cnpj = _extract_cnpj(text)
    uf = "SC"

    orgao_nome = ""

    # Look for standard header patterns in the text
    header_match = re.search(
        r"(GOVERNO\s+DO\s+ESTADO\s+DE\s+SANTA\s+CATARINA.*?)(?:\n|$)",
        text,
        re.IGNORECASE,
    )
    if header_match:
        orgao_nome = header_match.group(1).strip()

    # Look for municipality in text
    municipio = ""
    muni_match = re.search(
        r"(?:MUNICIPIO\s+DE|MUNICIPIO\s+-\s+)([A-Z\s]+?)(?:\s*[-,]|\n|$)",
        text,
    )
    if muni_match:
        municipio = muni_match.group(1).strip().title()

    return (orgao_nome, cnpj, municipio, uf)


def _transform_record(raw: dict) -> dict | None:
    """Transform a single DOE-SC materia into pncp_raw_bids schema.

    Returns None if the record lacks essential fields.
    """
    try:
        materia_id = raw.get("id") or raw.get("cdMateria")
        if not materia_id:
            return None

        titulo = (raw.get("titulo") or raw.get("dsTitulo") or "").strip()
        texto = (raw.get("texto") or raw.get("dsTexto") or raw.get("descricao") or "").strip()
        data_pub_raw = raw.get("dtPublicacao") or raw.get("dataPublicacao") or ""
        data_publicacao = _parse_date(data_pub_raw) or ""

        if not titulo and not texto:
            _logger.debug("[DOE-SC] Skipping record — empty title and text")
            return None

        # Extract entity info from title + text
        combined_text = f"{titulo} {texto}"
        orgao_nome, orgao_cnpj, municipio, uf = _extract_entity_info(combined_text)

        # Category info
        categoria_id = raw.get("cdCategoria") or raw.get("idCategoria") or 0
        categoria_nome = (
            raw.get("categoria", {}).get("descricao")
            or raw.get("dsCategoria")
            or raw.get("categoria", {}).get("nome")
            or f"Categoria {categoria_id}"
        )

        # Extract value if present
        valor = None
        valor_match = re.search(
            r"(?:R\$|valor[:\s]+|total[:\s]+)\s*([\d\.,]+)",
            combined_text,
            re.IGNORECASE,
        )
        if valor_match:
            valor = _safe_float(valor_match.group(1))

        # Build synthetic pncp_id
        pncp_id_input = f"doe_sc_{materia_id}"
        pncp_id = hashlib.md5(pncp_id_input.encode("utf-8"), usedforsecurity=False).hexdigest()

        # Build objeto_compra
        desc_parts = [titulo] if titulo else []
        if not desc_parts:
            desc_parts = [categoria_nome]
        if orgao_nome:
            desc_parts.append(orgao_nome)
        objeto_compra = " | ".join(desc_parts)
        if len(objeto_compra) > 500:
            objeto_compra = objeto_compra[:497] + "..."

        # Build link
        link = ""
        pdf_url = raw.get("dsArquivo") or raw.get("url") or raw.get("link")
        if pdf_url:
            if pdf_url.startswith("http"):
                link = pdf_url
            else:
                link = f"https://portal.doe.sea.sc.gov.br/repositorio/{pdf_url}"

        return {
            "pncp_id": pncp_id,
            "objeto_compra": objeto_compra,
            "valor_total_estimado": valor,
            "modalidade_id": int(categoria_id) if categoria_id else 0,
            "modalidade_nome": str(categoria_nome),
            "esfera_id": ESFERA_ID_ESTADUAL,
            "uf": uf or "SC",
            "municipio": municipio or "",
            "codigo_municipio_ibge": "",
            "orgao_razao_social": orgao_nome or None,
            "orgao_cnpj": orgao_cnpj or None,
            "data_publicacao": data_publicacao,
            "data_abertura": None,
            "data_encerramento": None,
            "link_pncp": link,
            "content_hash": _generate_content_hash(raw),
            "source_id": str(materia_id),
        }

    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        _logger.warning(
            "[DOE-SC] Transform error on materia_id=%s: %s: %s",
            raw.get("id", raw.get("cdMateria", "?")),
            type(exc).__name__,
            exc,
        )
        return None
    except Exception as exc:
        _logger.warning(
            "[DOE-SC] Unexpected transform error: %s: %s",
            type(exc).__name__,
            exc,
        )
        return None


# ---------------------------------------------------------------------------
# Transform interface (called by monitor.py)
# ---------------------------------------------------------------------------


def transform(raw_records: list[dict]) -> list[dict]:
    """Transform raw DOE-SC records to unified pncp_raw_bids schema.

    Args:
        raw_records: List of raw materia dicts from crawl().

    Returns:
        List of dicts normalized to pncp_raw_bids schema.
    """
    transformed = []
    skipped = 0

    for rec in raw_records:
        t = _transform_record(rec)
        if t and t.get("pncp_id"):
            transformed.append(t)
        else:
            skipped += 1

    if skipped:
        _logger.info(
            "[DOE-SC] Transform complete: %d records, %d skipped",
            len(transformed),
            skipped,
        )
    else:
        _logger.info(
            "[DOE-SC] Transform complete: %d records",
            len(transformed),
        )

    return transformed


# ---------------------------------------------------------------------------
# Diagnostic interface (called by monitor.py in dry-run mode)
# ---------------------------------------------------------------------------


def diagnostic() -> dict:
    """Run comprehensive diagnostics of the DOE-SC API connectivity.

    Tests:
        1. Portal homepage accessibility
        2. Login endpoint existence
        3. API resource endpoint (unauthenticated)
        4. Credentials availability
        5. DNS resolution

    Returns:
        Dict with diagnostic results matching monitor.py dry-run expectations.
    """
    import time
    import urllib.error
    import urllib.request

    result: dict = {
        "summary": "",
        "total_time_s": 0.0,
        "main_portal": {},
        "e_lic": {},
        "list_page_test": {},
        "auth_status": {},
    }
    start = time.time()

    # Test 1: Portal homepage
    try:
        t0 = time.time()
        req = urllib.request.Request(DOE_SC_PORTAL)
        with urllib.request.urlopen(req, timeout=15) as resp:
            portal_time = round(time.time() - t0, 3)
            result["main_portal"] = {
                "status_code": resp.status,
                "response_time_s": portal_time,
                "reachable": True,
                "cloudflare_detected": False,
            }
    except Exception as e:
        result["main_portal"] = {
            "status_code": 0,
            "response_time_s": 0.0,
            "reachable": False,
            "error": str(e),
        }

    # Test 2: Login endpoint
    try:
        t0 = time.time()
        url = f"{DOE_SC_API_HOST}/login"
        payload = json.dumps({"login": "test", "password": "test"}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "Extra-Consultoria/1.0")
        with urllib.request.urlopen(req, timeout=15) as resp:
            login_time = round(time.time() - t0, 3)
            result["e_lic"] = {
                "status_code": resp.status,
                "response_time_s": login_time,
                "reachable": True,
            }
    except urllib.error.HTTPError as e:
        login_time = round(time.time() - t0, 3)
        result["e_lic"] = {
            "status_code": e.code,
            "response_time_s": login_time,
            "reachable": True,
            "note": "Login endpoint exists (returns 400=bad_credentials, not 404)",
        }
    except Exception as e:
        result["e_lic"] = {
            "status_code": 0,
            "response_time_s": 0.0,
            "reachable": False,
            "error": str(e),
        }

    # Test 3: Materia endpoint (unauthenticated)
    try:
        t0 = time.time()
        url = f"{DOE_SC_API_BASE}/materia?page=1&perPage=5"
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=15) as resp:
            list_time = round(time.time() - t0, 3)
            result["list_page_test"] = {
                "status_code": resp.status,
                "response_time_s": list_time,
                "reachable": True,
            }
    except urllib.error.HTTPError as e:
        list_time = round(time.time() - t0, 3)
        result["list_page_test"] = {
            "status_code": e.code,
            "response_time_s": list_time,
            "reachable": True,
            "note": "API endpoint requires auth (401 expected without token)",
        }
    except Exception as e:
        result["list_page_test"] = {
            "status_code": 0,
            "response_time_s": 0.0,
            "reachable": False,
            "error": str(e),
        }

    # Test 4: Auth status
    credentials_available = bool(DOE_SC_LOGIN and DOE_SC_PASSWORD)
    result["auth_status"] = {
        "credentials_available": credentials_available,
        "can_authenticate": credentials_available,
        "login_endpoint": f"{DOE_SC_API_HOST}/login",
        "note": "Credentials required" if not credentials_available else "Credentials available",
    }

    result["total_time_s"] = round(time.time() - start, 3)

    # Build summary
    portal_ok = result["main_portal"].get("reachable", False)
    login_ok = result["e_lic"].get("reachable", False)
    can_auth = result["auth_status"]["can_authenticate"]

    summary_parts = []
    if portal_ok:
        summary_parts.append("portal=OK")
    else:
        summary_parts.append("portal=FAIL")

    if login_ok:
        summary_parts.append("login_endpoint=OK")
    else:
        summary_parts.append("login_endpoint=FAIL")

    if can_auth:
        summary_parts.append("auth=READY")
    else:
        summary_parts.append("auth=BLOCKED")

    result["summary"] = f"DOE-SC: {', '.join(summary_parts)}"
    return result
