"""Transparencia Crawler — Extra Consultoria.

Crawler base para portais de transparencia municipais.
Duas fases:

Fase 1 (existente): Platform Detection
  - Betha: {slug}.atende.net/transparencia
  - Ipam: {slug}.ipm.org.br/transparencia
  - E-gov: {slug}.e-gov.betha.com.br
  - Dominio proprio: heuristica generica via {municipio}.gov.br

Fase 2 (adicionada): Template-driven Scraping
  - Le configuracoes de config/transparencia_config.yaml
  - Aplica template de seletor CSS por municipio
  - Extrai licitacoes do HTML usando BeautifulSoup

Interface obrigatoria (compativel com monitor.py):
    crawl(mode: str = "full") -> list[dict]
    transform(records: list[dict]) -> list[dict]

Dependencias adicionais (ja em requirements.txt):
    - PyYAML (config parse)
    - beautifulsoup4 (HTML parsing)
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
from datetime import date, datetime
from pathlib import Path
from typing import Any

# Add project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (env vars with TRANSPARENCIA_ prefix)
# ---------------------------------------------------------------------------

TRANSPARENCIA_TIMEOUT = int(os.getenv("TRANSPARENCIA_TIMEOUT", "5"))
"""Timeout em segundos para requisicoes HTTP (default: 5s)."""

TRANSPARENCIA_REQUEST_DELAY = float(os.getenv("TRANSPARENCIA_REQUEST_DELAY", "0.5"))
"""Delay entre requisicoes para o mesmo dominio (default: 500ms)."""

TRANSPARENCIA_DELAY = float(os.getenv("TRANSPARENCIA_DELAY", "5.0"))
"""Delay entre portais diferentes no modo template-scraping (default: 5s)."""

TRANSPARENCIA_MAX_RETRIES = int(os.getenv("TRANSPARENCIA_MAX_RETRIES", "1"))
"""Maximo de retentativas por URL (default: 1)."""

TRANSPARENCIA_ENTITIES_FILE = os.getenv(
    "TRANSPARENCIA_ENTITIES_FILE",
    str(_PROJECT_ROOT / "data" / "municipios_sc.json"),
)
"""Caminho para arquivo JSON com lista de entidades/municipios."""

TRANSPARENCIA_OUTPUT_DIR = os.getenv(
    "TRANSPARENCIA_OUTPUT_DIR",
    str(_PROJECT_ROOT / "data"),
)
"""Diretorio para salvar resultados."""

TRANSPARENCIA_CONFIG = os.getenv(
    "TRANSPARENCIA_CONFIG",
    str(_PROJECT_ROOT / "config" / "transparencia_config.yaml"),
)
"""Caminho para o arquivo YAML de configuracao de templates."""

TRANSPARENCIA_SELENIUM_ENABLED = os.getenv(
    "TRANSPARENCIA_SELENIUM_ENABLED", "false"
).lower() in ("true", "1", "yes")
"""Habilita modo selenium para portais JS (FEAT-2.4)."""

SELENIUM_HEADLESS = os.getenv("SELENIUM_HEADLESS", "true").lower() in ("true", "1", "yes")
"""Modo headless do Selenium (default: true)."""

SELENIUM_TIMEOUT = int(os.getenv("SELENIUM_TIMEOUT", "30"))
"""Timeout em segundos para renderizacao JS (default: 30)."""

SELENIUM_REQUEST_DELAY = float(os.getenv("SELENIUM_REQUEST_DELAY", "5.0"))
"""Delay entre requisicoes Selenium (default: 5s)."""


# ---------------------------------------------------------------------------
# Slug utilities
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    """Convert municipality name to URL slug.

    Lowercase, remove accents, replace spaces with hyphens.
    Examples:
        "São José" -> "sao-jose"
        "Chapecó" -> "chapeco"
        "Blumenau" -> "blumenau"
        "Balneário Camboriú" -> "balneario-camboriu"
    """
    name = name.lower().strip()
    # Decompose unicode to separate base chars from combining marks
    name = unicodedata.normalize("NFKD", name)
    # Remove combining diacritical marks (accents, cedilha, etc.)
    name = name.encode("ascii", "ignore").decode("ascii")
    # Replace any non-alphanumeric sequence with a single hyphen
    name = re.sub(r"[^a-z0-9]+", "-", name)
    # Strip leading/trailing hyphens
    name = name.strip("-")
    return name


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------


def _fetch_url(url: str, timeout: int | None = None) -> tuple[int, str]:
    """Fetch a URL synchronously with timeout.

    Args:
        url: Full URL to fetch.
        timeout: Override timeout in seconds (default: TRANSPARENCIA_TIMEOUT).

    Returns:
        (status_code, body_or_error_message).
        0 status code indicates a connection/network error.
    """
    import urllib.error
    import urllib.request

    t = timeout or TRANSPARENCIA_TIMEOUT
    req = urllib.request.Request(url)
    req.add_header(
        "User-Agent",
        "Extra-Consultoria/1.0 (transparencia-crawler; +https://extraconsultoria.com.br)",
    )
    req.add_header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")

    try:
        with urllib.request.urlopen(req, timeout=t) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as e:
        # 4xx/5xx — return code as-is, empty body
        return e.code, ""
    except urllib.error.URLError as e:
        # DNS / connection refused / unreachable
        return 0, str(e.reason)
    except TimeoutError:
        return 0, "timeout"
    except OSError as e:
        # Socket-level errors (connection reset, name resolution failure)
        return 0, str(e)


def _head_url(url: str, timeout: int | None = None) -> int:
    """Perform a HEAD request to check URL availability.

    Args:
        url: Full URL to check.
        timeout: Override timeout (default: TRANSPARENCIA_TIMEOUT).

    Returns:
        HTTP status code, or 0 on connection error / timeout.
    """
    import urllib.error
    import urllib.request

    t = timeout or TRANSPARENCIA_TIMEOUT
    req = urllib.request.Request(url, method="HEAD")
    req.add_header(
        "User-Agent",
        "Extra-Consultoria/1.0 (transparencia-crawler; +https://extraconsultoria.com.br)",
    )
    req.add_header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")

    try:
        with urllib.request.urlopen(req, timeout=t) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except urllib.error.URLError:
        return 0
    except TimeoutError:
        return 0
    except OSError:
        return 0


# ---------------------------------------------------------------------------
# Platform detection (Fase 1 — existente, mantida)
# ---------------------------------------------------------------------------

# Platform templates: each has a URL pattern and a body check heuristic.
# Ordered by specificity (Betha before E-gov since E-gov is a Betha product).
_PLATFORM_TEMPLATES = [
    {
        "platform": "betha",
        "url": "https://{slug}.atende.net/transparencia",
        "check": lambda body: "atende.net" in body or "betha" in body.lower()[:2000],
    },
    {
        "platform": "ipam",
        "url": "https://{slug}.ipm.org.br/transparencia",
        "check": lambda body: "ipm" in body.lower()[:2000],
    },
    {
        "platform": "egov",
        "url": "https://{slug}.e-gov.betha.com.br",
        "check": lambda body: "e-gov" in body.lower()[:2000] or "betha" in body.lower()[:2000],
    },
    {
        "platform": "sc_gov_portal",
        "url": "https://{slug}.sc.gov.br",
        "check": lambda body: "transpar" in body.lower()[:5000] or "licita" in body.lower()[:5000],
    },
    {
        "platform": "fiorilli",
        "url": "https://{slug}.fiorilli.com.br/transparencia",
        "check": lambda body: "fiorilli" in body.lower()[:2000],
    },
    {
        "platform": "iplan",
        "url": "https://{slug}.iplan.gov.br/transparencia",
        "check": lambda body: "iplan" in body.lower()[:2000],
    },
    {
        "platform": "iri",
        "url": "https://{slug}.iri.com.br/transparencia",
        "check": lambda body: "iri" in body.lower()[:2000],
    },
    {
        "platform": "prima",
        "url": "https://{slug}.prima.com.br/transparencia",
        "check": lambda body: "prima" in body.lower()[:2000],
    },
    {
        "platform": "tecnospeed",
        "url": "https://{slug}.tecnospeed.com.br/transparencia",
        "check": lambda body: "tecnospeed" in body.lower()[:2000],
    },
]

# Keywords for generic portal detection on dominio proprio
_GENERIC_KEYWORDS = [
    "transparência",
    "transparencia",
    "licitação",
    "licitacao",
    "edital",
    "pregão",
    "pregao",
    "portal da transparência",
    "portal da transparencia",
]


def _detect_platform_from_url(url: str) -> str | None:
    """Detect platform from portal URL using substring matching.

    Extracted from the URL pattern matching logic originally inline in
    _PLATFORM_TEMPLATES iteration. Restored for backward compatibility
    with external test suites.

    Args:
        url: Full portal URL (e.g., ``https://chapeco.atende.net/transparencia``).

    Returns:
        Platform name string (``betha``, ``ipam``, ``egov``) or ``None``
        if the URL does not match any known platform pattern.
    """
    url_lower = url.lower()

    # Betha (Portal Transparencia .NET) — product of Betha Sistemas
    if "atende.net" in url_lower:
        return "betha"

    # Ipam (IpM) — product of IpM Sistemas
    if "ipm.org.br" in url_lower:
        return "ipam"

    # E-gov — also Betha, but a different portal product line
    if "e-gov.betha" in url_lower or "betha" in url_lower:
        return "egov"

    # Fiorilli
    if "fiorilli" in url_lower:
        return "fiorilli"

    # Iplan
    if "iplan" in url_lower:
        return "iplan"

    # IRI
    if "iri.com.br" in url_lower or "iri.sp.gov.br" in url_lower:
        return "iri"

    # Prima
    if "prima" in url_lower:
        return "prima"

    # Tecnospeed
    if "tecnospeed" in url_lower:
        return "tecnospeed"

    return None


def detect_platform(slug: str, municipio: str = "") -> dict:
    """Detect transparency portal platform for a municipality.

    Tries known platform URL patterns in order. If none match,
    attempts a generic heuristic via {municipio}.gov.br.

    Args:
        slug: URL-safe slug of the municipality name (from _slugify).
        municipio: Original municipality name (for fallback gov.br search).

    Returns:
        dict with keys:
            municipio   - Original municipality name
            slug        - URL-safe slug
            platform    - Detected platform name or None
            url         - Detected portal URL or None
            status      - "detected", "not_found", or "error"
            error       - Error message if status is "error"
            detected_at - ISO date string
    """
    result: dict[str, Any] = {
        "municipio": municipio or slug,
        "slug": slug,
        "platform": None,
        "url": None,
        "status": "unknown",
        "error": None,
        "detected_at": date.today().isoformat(),
    }

    # --- Try known platform templates ---
    for tmpl in _PLATFORM_TEMPLATES:
        url = tmpl["url"].format(slug=slug)
        try:
            status, body = _fetch_url(url)
        except Exception as e:
            _logger.debug(f"Error fetching {url}: {e}")
            continue

        if status == 200:
            # Optional body check to confirm platform identity
            try:
                is_match = tmpl["check"](body)
            except Exception:
                is_match = True  # If check fails, trust the URL match

            result["platform"] = tmpl["platform"]
            result["url"] = url
            result["status"] = "detected"
            result["body_hint"] = tmpl["platform"] if is_match else tmpl["platform"] + "_generic"
            _logger.info(f"Detected {tmpl['platform']} for '{municipio or slug}': {url}")
            return result

        # Rate limiting: 500ms between requests to different domains
        time.sleep(TRANSPARENCIA_REQUEST_DELAY)

    # --- Fallback: try dominio proprio via {municipio}.sc.gov.br then {municipio}.gov.br ---
    if municipio:
        gov_slug = _slugify(municipio)
        # SC-specific pattern first (most common for SC municipalities)
        for gov_url in (
            f"https://{gov_slug}.sc.gov.br",
            f"https://www.{gov_slug}.sc.gov.br",
            f"https://{gov_slug}.gov.br",
        ):
            try:
                status, body = _fetch_url(gov_url)
            except Exception as e:
                _logger.debug(f"Error fetching {gov_url}: {e}")
                continue

            if status == 200 or status == 302:
                found = [kw for kw in _GENERIC_KEYWORDS if kw in body.lower()]
                if found or status == 302:
                    result["platform"] = "proprio"
                    result["url"] = gov_url
                    result["status"] = "detected"
                    if found:
                        result["keywords_found"] = found
                    _logger.info(
                        f"Detected 'proprio' for '{municipio}': {gov_url}" + (f" (keywords: {found})" if found else "")
                    )
                    return result

        # TODO: Google fallback search
        # spec mentions: site:{municipio}.gov.br transparencia licitacoes
        # Requires external search API — deferred to Phase 2.

    # --- No platform found ---
    result["status"] = "not_found"
    _logger.info(f"No platform detected for '{municipio or slug}'")
    return result


# ---------------------------------------------------------------------------
# Config loading (Fase 2 — template-driven scraping)
# ---------------------------------------------------------------------------


def load_config(config_path: str | None = None) -> dict:
    """Load template config from YAML file.

    Args:
        config_path: Path to YAML config file (default: TRANSPARENCIA_CONFIG).

    Returns:
        Dict with keys "templates" and "municipios".
        Returns empty structure if config not found or parse fails.
    """
    path = Path(config_path or TRANSPARENCIA_CONFIG)
    empty = {"templates": {}, "municipios": {}}

    if not path.exists():
        _logger.warning(f"Config file not found: {path}")
        return empty

    try:
        import yaml

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            _logger.warning(f"Config file {path} is not a valid YAML mapping")
            return empty
        return data
    except ImportError:
        _logger.warning("PyYAML not installed, config file not loaded")
        return empty
    except Exception as e:
        _logger.warning(f"Failed to parse config {path}: {e}")
        return empty


def _get_template_selectors(template_name: str, config: dict) -> dict | None:
    """Resolve selectors for a template name from config.

    Args:
        template_name: Name of template (e.g. "portal_transparencia_net").
        config: Loaded config dict.

    Returns:
        Dict of selectors, or None if template not found.
    """
    templates = config.get("templates", {})
    tmpl = templates.get(template_name)
    if not tmpl:
        return None
    return tmpl.get("selectors")


def _resolve_selectors(municipio_config: dict, config: dict) -> dict | None:
    """Resolve selectors for a municipio entry.

    Priority:
        1. municipio_config.selectors (for custom templates)
        2. Template selectors from config.templates[municipio_config.template]

    Args:
        municipio_config: Dict with municipio config (ibge, portal_url, template, etc.)
        config: Full loaded config dict.

    Returns:
        Dict of CSS selectors, or None if cannot resolve.
    """
    # Custom selectors defined inline take priority
    custom_sel = municipio_config.get("selectors")
    if custom_sel and isinstance(custom_sel, dict) and custom_sel.get("lista_licitacoes"):
        return custom_sel

    # Resolve from template
    template_name = municipio_config.get("template", "")
    if template_name and template_name != "custom":
        tmpl_sel = _get_template_selectors(template_name, config)
        if tmpl_sel and tmpl_sel.get("lista_licitacoes"):
            return tmpl_sel

    return None


# ---------------------------------------------------------------------------
# Template-based scraping (Fase 2)
# ---------------------------------------------------------------------------


def health_check(portal_url: str) -> int:
    """Check if a portal is reachable via HEAD request.

    Args:
        portal_url: URL to check.

    Returns:
        HTTP status code, or 0 if unreachable.
    """
    _logger.debug(f"Health check: HEAD {portal_url}")
    status = _head_url(portal_url)
    if status == 200:
        _logger.info(f"Health check PASSED for {portal_url} (HTTP {status})")
    else:
        _logger.warning(f"Health check FAILED for {portal_url} (HTTP {status})")
    return status


def scrape_municipio(
    slug: str,
    portal_url: str,
    selectors: dict,
    municipio_nome: str = "",
    ibge: str = "",
) -> dict:
    """Scrape licitacoes from a single municipio portal using template selectors.

    Args:
        slug: URL-safe slug of the municipality.
        portal_url: Full URL of the transparency portal.
        selectors: Dict of CSS selectors:
            lista_licitacoes: Selector for the licitacoes table/list container.
            modalidade: Selector for modalidade column.
            data: Selector for data column.
            objeto: Selector for objeto column.
            orgao: Selector for orgao column (optional).
            valor: Selector for valor column (optional).
            link: Selector for detail link (optional).
        municipio_nome: Original municipality name.
        ibge: IBGE code.

    Returns:
        dict with:
            municipio: Nome do municipio.
            slug: Slug do municipio.
            ibge: Codigo IBGE.
            portal_url: URL do portal.
            status: "ok", "unreachable", "no_content", or "parse_error".
            records: List of scraped records (each as dict).
            count: Number of records extracted.
            error: Error message if status is not "ok".
            scraped_at: ISO timestamp.
    """
    result: dict[str, Any] = {
        "municipio": municipio_nome or slug,
        "slug": slug,
        "ibge": ibge,
        "portal_url": portal_url,
        "status": "unknown",
        "records": [],
        "count": 0,
        "error": None,
        "scraped_at": datetime.now().isoformat(),
    }

    # Health check first
    http_status = health_check(portal_url)
    if http_status != 200:
        result["status"] = "unreachable"
        result["error"] = f"HTTP {http_status}"
        _logger.warning(f"Portal unreachable for {municipio_nome or slug}: HTTP {http_status}")
        return result

    # Fetch page content
    try:
        http_status, body = _fetch_url(portal_url)
    except Exception as e:
        result["status"] = "unreachable"
        result["error"] = str(e)
        return result

    if http_status != 200 or not body:
        result["status"] = "unreachable"
        result["error"] = f"HTTP {http_status} or empty body"
        return result

    # Parse HTML
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(body, "html.parser")
    except ImportError:
        result["status"] = "parse_error"
        result["error"] = "BeautifulSoup not installed"
        _logger.error("BeautifulSoup not installed — cannot parse HTML")
        return result
    except Exception as e:
        result["status"] = "parse_error"
        result["error"] = f"HTML parse error: {e}"
        return result

    # Find licitacoes container
    container_sel = selectors.get("lista_licitacoes", "")
    if not container_sel:
        result["status"] = "parse_error"
        result["error"] = "No lista_licitacoes selector defined"
        return result

    try:
        container = soup.select_one(container_sel)
    except Exception as e:
        result["status"] = "parse_error"
        result["error"] = f"CSS selector error ({container_sel}): {e}"
        return result

    if container is None:
        _logger.info(f"No container found for {municipio_nome or slug} using '{container_sel}'")
        result["status"] = "no_content"
        result["records"] = []
        result["count"] = 0
        return result

    # Extract rows
    rows = []
    try:
        # Try <tr> elements inside container
        trs = container.find_all("tr")
        if not trs:
            # Fallback: direct children
            trs = container.children

        for tr in trs:
            if tr.name != "tr":
                continue
            row = _extract_row(tr, selectors, slug, ibge, portal_url)
            if row:
                rows.append(row)
    except Exception as e:
        _logger.warning(f"Row extraction error for {municipio_nome or slug}: {e}")

    result["status"] = "ok"
    result["records"] = rows
    result["count"] = len(rows)

    _logger.info(f"Scraped {len(rows)} licitacoes from {municipio_nome or slug} ({portal_url})")

    return result


def _extract_row(
    tr: Any,
    selectors: dict,
    slug: str,
    ibge: str,
    portal_url: str,
) -> dict | None:
    """Extract a single row from a <tr> element using CSS selectors.

    Args:
        tr: BeautifulSoup Tag for the table row.
        selectors: Dict of CSS selectors for columns.
        slug: Municipality slug.
        ibge: IBGE code.
        portal_url: Portal URL.

    Returns:
        Dict with extracted fields, or None if row is empty/invalid.
    """

    row: dict[str, Any] = {
        "slug": slug,
        "codigo_municipio_ibge": ibge,
        "portal_url": portal_url,
        "modalidade": "",
        "data_publicacao": "",
        "objeto": "",
        "orgao": "",
        "valor": "",
        "link": "",
    }

    def _text(sel: str) -> str:
        try:
            el = tr.select_one(sel) if sel else None
            return el.get_text(strip=True) if el else ""
        except Exception:
            return ""

    modalidade_sel = selectors.get("modalidade", "")
    data_sel = selectors.get("data", "")
    objeto_sel = selectors.get("objeto", "")
    orgao_sel = selectors.get("orgao", "")
    valor_sel = selectors.get("valor", "")
    link_sel = selectors.get("link", "")

    row["modalidade"] = _text(modalidade_sel)
    row["data_publicacao"] = _text(data_sel)
    row["objeto"] = _text(objeto_sel)
    row["orgao"] = _text(orgao_sel)
    row["valor"] = _text(valor_sel)

    # Extract link
    if link_sel:
        try:
            link_el = tr.select_one(link_sel)
            if link_el and link_el.name == "a" and link_el.get("href"):
                href = link_el["href"]
                # Handle relative URLs
                if href.startswith("/"):
                    from urllib.parse import urlparse

                    parsed = urlparse(portal_url)
                    row["link"] = f"{parsed.scheme}://{parsed.netloc}{href}"
                else:
                    row["link"] = href
        except Exception:
            pass

    # Skip empty rows (no data extracted at all)
    if not any([row["modalidade"], row["objeto"], row["data_publicacao"]]):
        return None

    # Generate content hash
    content_key = f"{row['modalidade']}|{row['objeto']}|{row['data_publicacao']}|{row['valor']}"
    row["content_hash"] = hashlib.md5(content_key.encode(), usedforsecurity=False).hexdigest()

    return row


# ---------------------------------------------------------------------------
# Entity loading
# ---------------------------------------------------------------------------


def _load_entities(filepath: str | None = None) -> list[dict]:
    """Load municipality/entity list from JSON file.

    Expected JSON formats (both accepted):
        - List of dicts: [{"nome": "...", "ibge": "..."}, ...]
        - Dict with key "municipios": [...]

    Falls back to a built-in stub list of major SC municipalities
    if the file does not exist (useful for testing).

    Args:
        filepath: Path to JSON file (default: TRANSPARENCIA_ENTITIES_FILE).

    Returns:
        List of entity dicts, each with at least a "nome" key.
    """
    path = Path(filepath or TRANSPARENCIA_ENTITIES_FILE)

    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("municipios", data.get("entities", data.get("orgaos", [])))
        except Exception as e:
            _logger.warning(f"Failed to load entities from {path}: {e}")
    else:
        _logger.info(f"Entities file not found at {path}, using stub list")

    # Fallback stub — major SC municipalities for testing
    return [
        {"nome": "Florianopolis", "ibge": "4205407"},
        {"nome": "Joinville", "ibge": "4209102"},
        {"nome": "Blumenau", "ibge": "4202404"},
        {"nome": "Sao Jose", "ibge": "4216602"},
        {"nome": "Chapeco", "ibge": "4204202"},
        {"nome": "Criciuma", "ibge": "4204608"},
        {"nome": "Lages", "ibge": "4209300"},
        {"nome": "Itajai", "ibge": "4208203"},
        {"nome": "Balneario Camboriu", "ibge": "4202008"},
        {"nome": "Tubarao", "ibge": "4218707"},
        {"nome": "Palhoca", "ibge": "4211900"},
        {"nome": "Brusque", "ibge": "4202909"},
        {"nome": "Rio do Sul", "ibge": "4214805"},
        {"nome": "Indaial", "ibge": "4207502"},
        {"nome": "Biguacu", "ibge": "4202305"},
    ]


# ---------------------------------------------------------------------------
# Results persistence
# ---------------------------------------------------------------------------


def _results_path(output_dir: str | None = None) -> Path:
    """Get path to the platforms detection results file."""
    base = Path(output_dir or TRANSPARENCIA_OUTPUT_DIR)
    base.mkdir(parents=True, exist_ok=True)
    return base / "transparencia_platforms.json"


def _scrape_results_path(output_dir: str | None = None) -> Path:
    """Get path to the scraping results file."""
    base = Path(output_dir or TRANSPARENCIA_OUTPUT_DIR)
    base.mkdir(parents=True, exist_ok=True)
    return base / "transparencia_scrape_results.json"


def _load_existing_results(output_dir: str | None = None) -> dict:
    """Load previously detected platforms from JSON file.

    Returns a dict with:
        - "detected": list of detection result dicts
        - "metadata": dict with version, counts, and timestamp

    Returns an empty skeleton if file does not exist or is corrupt.
    """
    path = _results_path(output_dir)
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "detected" in data:
                return data
        except Exception as e:
            _logger.warning(f"Failed to load existing results from {path}: {e}")
    return {"detected": [], "metadata": {"version": 1}}


def _save_results(data: dict, output_dir: str | None = None) -> str:
    """Save platform detection results to JSON file.

    Args:
        data: Dict with "detected" list and "metadata" dict.
        output_dir: Override output directory.

    Returns:
        Absolute path to saved file.
    """
    path = _results_path(output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    _logger.info(f"Saved detection results to {path}")
    return str(path)


def _save_scrape_results(data: dict) -> str:
    """Save scraping results to JSON file.

    Args:
        data: Dict with "municipios" list and "metadata".

    Returns:
        Absolute path to saved file.
    """
    base = Path(TRANSPARENCIA_OUTPUT_DIR)
    base.mkdir(parents=True, exist_ok=True)
    path = _scrape_results_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    _logger.info(f"Saved scrape results to {path}")
    return str(path)


# ---------------------------------------------------------------------------
# Template-driven crawl (Fase 2)
# ---------------------------------------------------------------------------


def crawl_template(
    municipio_slug: str | None = None,
    config_path: str | None = None,
) -> list[dict]:
    """Run template-driven scraping for configured municipios.

    Carrega a configuracao YAML, faz health check de cada portal,
    aplica scraping com template, e salva resultados com log de efetividade.

    Args:
        municipio_slug: If set, scrape apenas este municipio.
        config_path: Caminho alternativo para config YAML.

    Returns:
        List of scraping result dicts (see scrape_municipio for schema).
    """
    config = load_config(config_path)
    municipios = config.get("municipios", {})

    if not municipios:
        _logger.warning("No municipios configured in transparencia_config.yaml")
        return []

    results: list[dict] = []
    success_count = 0
    error_count = 0
    total_licitacoes = 0

    for slug, cfg in municipios.items():
        # Filter by municipio slug if specified
        if municipio_slug and slug != municipio_slug:
            continue

        # Skip inactive municipios
        if not cfg.get("ativo", True):
            _logger.info(f"Skipping {slug} (inactive)")
            continue

        portal_url = cfg.get("portal_url", "")
        ibge = cfg.get("ibge", "")
        nome = cfg.get("nome", slug)

        if not portal_url:
            _logger.warning(f"No portal_url for {slug}, skipping")
            continue

        # Resolve selectors
        selectors = _resolve_selectors(cfg, config)
        if not selectors:
            _logger.warning(f"No selectors resolved for {slug} (template={cfg.get('template')}), skipping")
            continue

        # Scrape
        try:
            result = scrape_municipio(
                slug=slug,
                portal_url=portal_url,
                selectors=selectors,
                municipio_nome=nome,
                ibge=ibge,
            )
            results.append(result)

            if result["status"] == "ok":
                success_count += 1
                total_licitacoes += result["count"]
                _logger.info(f"  [{success_count}] {nome}: {result['count']} licitacoes extraidas")
            else:
                error_count += 1
                _logger.warning(
                    f"  [{success_count + error_count}] {nome}: {result['status']} ({result.get('error', '')})"
                )

        except Exception as e:
            _logger.error(f"Scraping failed for {slug}: {e}")
            results.append(
                {
                    "municipio": nome,
                    "slug": slug,
                    "ibge": ibge,
                    "portal_url": portal_url,
                    "status": "error",
                    "records": [],
                    "count": 0,
                    "error": str(e),
                    "scraped_at": datetime.now().isoformat(),
                }
            )
            error_count += 1

        # Delay between portals
        time.sleep(TRANSPARENCIA_DELAY)

    # Log de efetividade
    _logger.info("=" * 60)
    _logger.info("EFETIVIDADE — Template Scraping")
    _logger.info("=" * 60)
    for r in results:
        status_icon = "OK" if r["status"] == "ok" else "XX"
        _logger.info(f"  [{status_icon}] {r['municipio']:30s} | {r['count']:4d} licitacoes | {r.get('status', '?')}")
    _logger.info("-" * 60)
    _logger.info(
        f"  Total: {len(results)} municipios | {success_count} ok | {error_count} erros | {total_licitacoes} licitacoes"
    )
    _logger.info("=" * 60)

    # Save results
    metadata = {
        "version": 1,
        "total_municipios": len(results),
        "success": success_count,
        "errors": error_count,
        "total_licitacoes": total_licitacoes,
        "scraped_at": datetime.now().isoformat(),
    }
    _save_scrape_results({"municipios": results, "metadata": metadata})

    return results


# ---------------------------------------------------------------------------
# Selenium crawl (FEAT-2.4)
# ---------------------------------------------------------------------------


def crawl_selenium(
    municipio_slug: str | None = None,
    config_path: str | None = None,
) -> list[dict]:
    """Run Selenium-based crawling for JS-rendered transparency portals.

    Processes only municipios with ``requires_js: true`` in the config.
    For municipios with ``requires_js: false`` (or unset), falls back to
    HTTP-based scraping via ``crawl_template()``.

    Args:
        municipio_slug: If set, process apenas este municipio.
        config_path: Caminho alternativo para config YAML.

    Returns:
        List of scraping result dicts (see ``scrape_municipio`` for schema,
        plus ``method`` field indicating selenium or http_fallback).
    """
    config = load_config(config_path)
    municipios = config.get("municipios", {})
    if not municipios:
        _logger.warning("No municipios configured in transparencia_config.yaml")
        return []

    # Validate selenium availability
    selenium_available = True
    try:
        from scripts.crawl.selenium_crawler import SeleniumCrawler
    except ImportError:
        selenium_available = False
        _logger.warning("Selenium not available — falling back to HTTP for all municipios")

    if not TRANSPARENCIA_SELENIUM_ENABLED:
        _logger.info("TRANSPARENCIA_SELENIUM_ENABLED=false — using HTTP for all municipios")
        selenium_available = False

    results: list[dict] = []
    success_count = 0
    error_count = 0
    total_licitacoes = 0
    selenium_count = 0
    http_count = 0

    for slug, cfg in municipios.items():
        if municipio_slug and slug != municipio_slug:
            continue
        if not cfg.get("ativo", True):
            _logger.info(f"Skipping {slug} (inactive)")
            continue

        portal_url = cfg.get("portal_url", "")
        ibge = cfg.get("ibge", "")
        nome = cfg.get("nome", slug)
        requires_js = cfg.get("requires_js", False)

        if not portal_url:
            _logger.warning(f"No portal_url for {slug}, skipping")
            continue

        # Resolve selectors
        selectors = _resolve_selectors(cfg, config)
        if not selectors:
            _logger.warning(f"No selectors resolved for {slug}, skipping")
            continue

        # Determine template module
        template_name = cfg.get("template", "")
        template_module = None
        if template_name and template_name != "custom":
            try:
                from importlib import import_module

                module_map = {
                    "portal_transparencia_net": "scripts.crawl.transparencia_templates.betha",
                    "e_gov_net": "scripts.crawl.transparencia_templates.egov",
                }
                mod_path = module_map.get(template_name)
                if mod_path:
                    template_module = import_module(mod_path)
            except Exception as e:
                _logger.debug(f"Could not load template {template_name}: {e}")

        wait_for = cfg.get("wait_for", "")

        if requires_js and selenium_available:
            # Selenium path
            selenium_count += 1
            try:
                from scripts.crawl.selenium_crawler import SeleniumCrawler

                with SeleniumCrawler() as crawler:
                    result = crawler.scrape(
                        slug=slug,
                        portal_url=portal_url,
                        selectors=selectors if not template_module else None,
                        template_module=template_module,
                        municipio_nome=nome,
                        ibge=ibge,
                        wait_for=wait_for or None,
                        fallback_to_http=True,
                    )
                results.append(result)
            except Exception as e:
                _logger.error(f"Selenium scraping failed for {slug}: {e}")
                # HTTP fallback on unexpected error
                try:
                    http_result = scrape_municipio(
                        slug=slug,
                        portal_url=portal_url,
                        selectors=selectors,
                        municipio_nome=nome,
                        ibge=ibge,
                    )
                    http_result["method"] = "http_fallback"
                    results.append(http_result)
                except Exception as e2:
                    results.append({
                        "municipio": nome,
                        "slug": slug,
                        "ibge": ibge,
                        "portal_url": portal_url,
                        "status": "error",
                        "records": [],
                        "count": 0,
                        "error": f"Selenium: {e}; HTTP fallback: {e2}",
                        "scraped_at": datetime.now().isoformat(),
                        "method": "fallback_error",
                    })
        else:
            # HTTP path (requires_js false or selenium unavailable)
            http_count += 1
            try:
                result = scrape_municipio(
                    slug=slug,
                    portal_url=portal_url,
                    selectors=selectors,
                    municipio_nome=nome,
                    ibge=ibge,
                )
                result["method"] = "http" if not requires_js else "http_forced"
                results.append(result)
            except Exception as e:
                _logger.error(f"HTTP scraping failed for {slug}: {e}")
                results.append({
                    "municipio": nome,
                    "slug": slug,
                    "ibge": ibge,
                    "portal_url": portal_url,
                    "status": "error",
                    "records": [],
                    "count": 0,
                    "error": str(e),
                    "scraped_at": datetime.now().isoformat(),
                    "method": "http_error",
                })

        # Count results
        if results and results[-1]["status"] == "ok":
            success_count += 1
            total_licitacoes += results[-1]["count"]
        else:
            error_count += 1

        # Delay between portals
        time.sleep(TRANSPARENCIA_DELAY)

    # Efetividade log
    _logger.info("=" * 60)
    _logger.info("EFETIVIDADE — Selenium Crawl")
    _logger.info("=" * 60)
    for r in results:
        method_tag = r.get("method", "?")
        status_icon = "OK" if r["status"] == "ok" else "XX"
        _logger.info("  [%s][%s] %-30s | %4d licitacoes | %s",
                     status_icon, method_tag, r['municipio'], r['count'], r.get('status', '?'))
    _logger.info("-" * 60)
    _logger.info("  Total: %d | Selenium: %d | HTTP: %d | OK: %d | Erros: %d | Licitacoes: %d",
                 len(results), selenium_count, http_count,
                 success_count, error_count, total_licitacoes)
    _logger.info("=" * 60)

    return results


# ---------------------------------------------------------------------------
# Crawler interface (called by monitor.py)
# ---------------------------------------------------------------------------


def crawl(mode: str = "full") -> list[dict]:
    """Crawl transparency portals for SC municipalities.

    Supports multiple modes with explicit semantics:

    ``"detect"``
        Platform detection only — identify which portal platform each
        municipality uses.  Saves results to
        ``data/transparencia_platforms.json``.  Returns detection records
        (municipio, slug, platform, url, status).

    ``"template"``
        Template-driven scraping via BeautifulSoup using CSS selectors
        from ``config/transparencia_config.yaml``.  Returns scraping
        result dicts with embedded ``records`` lists.

    ``"selenium"``
        Selenium-based scraping for JS-rendered portals.  Falls back to
        HTTP for portals with ``requires_js: false``.  Returns scraping
        result dicts.

    ``"full"`` (default)
        **Detection + template scraping.**  First runs platform detection,
        then scrapes detected platforms via template config.  Returns
        scraping results when config is available; falls back to detection
        records otherwise (so coverage-only runs still work).

    ``"incremental"``
        Detection only for entities not yet present in saved results.

    Returns:
        List of dicts.  Detection records have at least: municipio, slug,
        platform, url, status.  Scraping records have: municipio, slug,
        portal_url, status, records, count.
    """
    # ── Explicit mode routing ──────────────────────────────────────────
    if mode in ("template",):
        return crawl_template()

    if mode in ("selenium",):
        return crawl_selenium()

    if mode in ("detect",):
        return _crawl_detect(mode)

    if mode in ("incremental",):
        return _crawl_detect(mode)

    # ── Full mode: detect + template scrape ────────────────────────────
    if mode == "full":
        _logger.info("Full mode: running platform detection first...")
        _crawl_detect("full")  # updates transparencia_platforms.json

        _logger.info("Full mode: running template-driven scraping...")
        try:
            scraping_results = crawl_template()
            if scraping_results:
                total_bids = sum(r.get("count", 0) for r in scraping_results)
                _logger.info(
                    "Full mode: template scraping returned %d portal(s) with %d bid(s)",
                    len(scraping_results),
                    total_bids,
                )
                return scraping_results
            _logger.warning(
                "Full mode: template scraping returned 0 results — "
                "returning detection records as fallback"
            )
        except Exception as exc:
            _logger.error(
                "Full mode: template scraping failed: %s — "
                "returning detection records as fallback",
                exc,
            )

        # Fallback: return detection records so platform tracking still works
        return _load_existing_results().get("detected", [])

    # ── Unknown mode ───────────────────────────────────────────────────
    _logger.warning("Unknown mode %r — defaulting to detection", mode)
    return _crawl_detect("full")


def _crawl_detect(mode: str) -> list[dict]:
    """Run platform detection (internal — extracted from old crawl())."""
    entities = _load_entities()
    existing = _load_existing_results()

    # Build set of already-detected slugs (from previous runs)
    detected_map: dict[str, dict] = {}
    for d in existing.get("detected", []):
        slug = d.get("slug")
        if slug:
            detected_map[slug] = d

    results: list[dict] = []
    new_count = 0
    skipped_count = 0
    error_count = 0

    for entity in entities:
        nome: str = entity.get("nome", "")
        slug: str = entity.get("slug", "") or _slugify(nome)
        if not nome and not slug:
            continue

        # In incremental mode, skip already-detected slugs
        if mode == "incremental" and slug in detected_map:
            skipped_count += 1
            continue

        try:
            detection = detect_platform(slug, municipio=nome)
            results.append(detection)

            if detection.get("status") == "detected":
                new_count += 1
            elif detection.get("status") == "not_found":
                error_count += 1

            _logger.info(
                f"[{new_count + error_count + skipped_count}/{len(entities)}] "
                f"{nome}: {detection.get('platform') or 'not_found'}"
            )

        except Exception as e:
            _logger.error(f"Detection failed for {nome} ({slug}): {e}")
            results.append(
                {
                    "municipio": nome,
                    "slug": slug,
                    "platform": None,
                    "url": None,
                    "status": "error",
                    "error": str(e),
                    "detected_at": date.today().isoformat(),
                }
            )
            error_count += 1

    # Merge with existing results (preserving previously detected slugs
    # that were not re-checked in this run)
    all_detected = list(detected_map.values())
    # New results overwrite old entries for the same slug
    seen_slugs: set[str] = set()
    for r in results:
        slug = r.get("slug")
        if slug:
            seen_slugs.add(slug)

    for old_entry in all_detected:
        old_slug = old_entry.get("slug")
        if old_slug and old_slug not in seen_slugs:
            results.append(old_entry)

    # Build metadata
    total_detected = sum(1 for r in results if r.get("status") == "detected")
    total_not_found = sum(1 for r in results if r.get("status") == "not_found")
    total_errors = sum(1 for r in results if r.get("status") == "error")

    output = {
        "detected": results,
        "metadata": {
            "version": 1,
            "total_entities": len(entities),
            "total_detected": total_detected,
            "total_not_found": total_not_found,
            "total_errors": total_errors,
            "mode": mode,
            "updated_at": date.today().isoformat(),
        },
    }
    _save_results(output)

    _logger.info(
        f"Crawl complete: {new_count} new, {skipped_count} skipped, {error_count} errors ({len(results)} total in file)"
    )

    return results


def transform(records: list[dict]) -> list[dict]:
    """Normalize raw records to pncp_raw_bids schema.

    Handles both platform detection records and template-scraped records.

    Schema:
        pncp_id, objeto_compra, valor_total_estimado, modalidade_id,
        modalidade_nome, esfera_id, uf, municipio, codigo_municipio_ibge,
        orgao_razao_social, orgao_cnpj, data_publicacao, data_abertura,
        data_encerramento, link_pncp, content_hash (MD5), source_id

    Args:
        records: Raw records from ``crawl()``.

    Returns:
        List of normalized dicts ready for upsert.
    """
    normalized: list[dict] = []

    for record in records:
        # Detect record type: template-scraped or platform detection
        if "portal_url" in record and "records" in record:
            # Template-scraped record (from crawl_template / scrape_municipio / crawl_selenium)
            sub_records = record.get("records", [])
            method = record.get("method", "http")
            for r in sub_records:
                normalized.append(
                    {
                        "pncp_id": r.get("content_hash", ""),
                        "objeto_compra": r.get("objeto", ""),
                        "valor_total_estimado": _parse_valor(r.get("valor", "")),
                        "modalidade_nome": r.get("modalidade", ""),
                        "uf": "SC",
                        "municipio": record.get("municipio", ""),
                        "codigo_municipio_ibge": r.get("codigo_municipio_ibge", ""),
                        "orgao_razao_social": r.get("orgao", ""),
                        "data_publicacao": _parse_date(r.get("data_publicacao", "")),
                        "link_pncp": r.get("link", ""),
                        "content_hash": r.get("content_hash", ""),
                        "source": "transparencia",
                        "source_subtype": (
                            r.get("_source_subtype")
                            or record.get("source_subtype")
                            or record.get("template_module")
                            or "generico"
                        ),
                        "source_id": f"transparencia_{record.get('slug', '')}",
                        "method": method,
                    }
                )
        elif "platform" in record:
            # Platform detection record (Fase 1) — skip, no bid data
            pass

    if not normalized:
        _logger.info(f"transform() called with {len(records)} raw records, returning {len(normalized)} normalized")

    return normalized


def _parse_valor(valor_str: str) -> float | None:
    """Parse a Brazilian currency string to float.

    Examples:
        "R$ 1.234,56" -> 1234.56
        "1.234,56" -> 1234.56
        "" -> None
    """
    if not valor_str:
        return None
    # Remove "R$", spaces, and dots (thousands separator)
    cleaned = re.sub(r"[R$\s]", "", valor_str)
    # Replace comma with dot (decimal separator)
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_date(date_str: str) -> str | None:
    """Parse various date formats to ISO date string (YYYY-MM-DD)."""
    if not date_str:
        return None

    # Common Brazilian formats
    patterns = [
        r"(\d{2})/(\d{2})/(\d{4})",  # DD/MM/YYYY
        r"(\d{2})-(\d{2})-(\d{4})",  # DD-MM-YYYY
        r"(\d{4})-(\d{2})-(\d{2})",  # YYYY-MM-DD
    ]

    for pattern in patterns:
        m = re.search(pattern, date_str)
        if m:
            groups = m.groups()
            if pattern.startswith(r"(\d{4})"):
                return f"{groups[0]}-{groups[1]}-{groups[2]}"
            else:
                return f"{groups[2]}-{groups[1]}-{groups[0]}"

    return date_str


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    import argparse

    parser = argparse.ArgumentParser(
        description="Transparencia Crawler — detecta plataformas e extrai licitacoes de portais municipais"
    )
    parser.add_argument(
        "--mode",
        choices=["full", "incremental", "template", "selenium"],
        default="full",
        help="Modo de execucao: full/incremental (deteccao), template (scraping via config) ou selenium (JS portals) (default: full)",
    )
    parser.add_argument(
        "--entities",
        default=None,
        help="Caminho para arquivo JSON de entidades (default: TRANSPARENCIA_ENTITIES_FILE)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Diretorio de saida (default: TRANSPARENCIA_OUTPUT_DIR)",
    )
    parser.add_argument(
        "--slug",
        default=None,
        help="Detectar plataforma para um unico slug (teste rapido)",
    )
    parser.add_argument(
        "--municipio",
        default=None,
        help="Scraping template-driven para um municipio especifico (slug do config)",
    )
    parser.add_argument(
        "--todos",
        action="store_true",
        default=False,
        help="Scraping template-driven para TODOS os municipios configurados",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Caminho para config YAML (default: TRANSPARENCIA_CONFIG)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Log em nivel DEBUG",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Template-driven scraping mode
    if args.municipio or args.todos or args.mode == "template":
        config_path = args.config
        slug = args.municipio if args.municipio else None
        results = crawl_template(municipio_slug=slug, config_path=config_path)

        if results:
            total_licitacoes = sum(r.get("count", 0) for r in results)
            ok_count = sum(1 for r in results if r.get("status") == "ok")
            fail_count = sum(1 for r in results if r.get("status") != "ok")

            print(f"\nTemplate scraping complete: {len(results)} municipios")
            print(f"  OK:   {ok_count}")
            print(f"  Fail: {fail_count}")
            print(f"  Total licitacoes: {total_licitacoes}")

            # Log de efetividade (terminal)
            print(f"\n{'=' * 72}")
            print("  EFETIVIDADE — Template Scraping")
            print(f"{'=' * 72}")
            print(f"  {'Municipio':30s} | {'Licitacoes':>10s} | {'Status':>12s}")
            print(f"  {'-' * 30} | {'-' * 10} | {'-' * 12}")
            for r in results:
                status_icon = "OK" if r["status"] == "ok" else r.get("status", "?")
                print(f"  {r['municipio']:30s} | {r['count']:10d} | {status_icon:>12s}")
            print(f"  {'-' * 30} | {'-' * 10} | {'-' * 12}")
            print(f"  {'TOTAL':30s} | {total_licitacoes:10d} | {ok_count}/{len(results)}")
            print(f"{'=' * 72}")
        else:
            print("No results from template scraping")
            print("  Check config/transparencia_config.yaml for configured municipios")
        sys.exit(0)

    # Selenium mode (FEAT-2.4)
    if args.mode == "selenium":
        config_path = args.config
        results = crawl_selenium(config_path=config_path)

        if results:
            total_licitacoes = sum(r.get("count", 0) for r in results)
            ok_count = sum(1 for r in results if r.get("status") == "ok")
            fail_count = sum(1 for r in results if r.get("status") != "ok")

            print(f"\nSelenium crawl complete: {len(results)} municipios")
            print(f"  OK:   {ok_count}")
            print(f"  Fail: {fail_count}")
            print(f"  Total licitacoes: {total_licitacoes}")

            print(f"\n{'=' * 72}")
            print("  EFETIVIDADE — Selenium Crawl")
            print(f"{'=' * 72}")
            print(f"  {'Municipio':30s} | {'Metodo':>10s} | {'Licitacoes':>10s} | {'Status':>12s}")
            print(f"  {'-' * 30} | {'-' * 10} | {'-' * 10} | {'-' * 12}")
            for r in results:
                method = r.get("method", "?")
                status_icon = "OK" if r["status"] == "ok" else r.get("status", "?")
                print(f"  {r['municipio']:30s} | {method:>10s} | {r['count']:10d} | {status_icon:>12s}")
            print(f"  {'-' * 30} | {'-' * 10} | {'-' * 10} | {'-' * 12}")
            print(f"  {'TOTAL':30s} | {'':>10s} | {total_licitacoes:10d} | {ok_count}/{len(results)}")
            print(f"{'=' * 72}")
        else:
            print("No results from selenium crawl")
            print("  Check config/transparencia_config.yaml for municipios with requires_js: true")
        sys.exit(0)

    # Legacy: single slug detection
    if args.slug:
        result = detect_platform(args.slug, municipio=args.slug)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0)

    # Legacy: full/incremental mode
    if args.entities:
        os.environ["TRANSPARENCIA_ENTITIES_FILE"] = args.entities
    if args.output:
        os.environ["TRANSPARENCIA_OUTPUT_DIR"] = args.output

    results = crawl(mode=args.mode)
    print(f"\nDetection complete: {len(results)} total records")
    print(f"  Detected:   {sum(1 for r in results if r.get('status') == 'detected')}")
    print(f"  Not found:  {sum(1 for r in results if r.get('status') == 'not_found')}")
    print(f"  Errors:     {sum(1 for r in results if r.get('status') == 'error')}")
