"""Transparencia Crawler — Extra Consultoria.

Crawler base para portais de transparencia municipais.
Detecta a plataforma de cada municipio e prepara dados para scraping futuro.

Fase 1 (implementada): Platform Detection
  - Betha: {slug}.atende.net/transparencia
  - Ipam: {slug}.ipm.org.br/transparencia
  - E-gov: {slug}.e-gov.betha.com.br
  - Dominio proprio: heuristica generica via {municipio}.gov.br

Fase 2 (futura): Scraping por plataforma
  - Parse de HTML especifico de cada template

Fase 3 (futura): Transform para schema pncp_raw_bids

Interface obrigatoria:
    crawl(mode: str = "full") -> list[dict]
    transform(records: list[dict]) -> list[dict]

Dependencias: apenas stdlib (urllib, json, hashlib, logging, os, sys, time,
              datetime, pathlib, re, unicodedata).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
import unicodedata

# Add project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (env vars with TRANSPARENCIA_ prefix)
# ---------------------------------------------------------------------------

TRANSPARENCIA_TIMEOUT = int(os.getenv("TRANSPARENCIA_TIMEOUT", "5"))
"""Timeout em segundos para requisicoes HTTP de deteccao (default: 5s)."""

TRANSPARENCIA_REQUEST_DELAY = float(os.getenv("TRANSPARENCIA_REQUEST_DELAY", "0.5"))
"""Delay entre requisicoes para o mesmo dominio (default: 500ms)."""

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
"""Diretorio para salvar resultados de deteccao."""


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


# ---------------------------------------------------------------------------
# Platform detection
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

    # --- Fallback: try dominio proprio via {municipio}.gov.br ---
    if municipio:
        gov_slug = _slugify(municipio)
        gov_url = f"https://{gov_slug}.gov.br"
        try:
            status, body = _fetch_url(gov_url)
        except Exception as e:
            _logger.debug(f"Error fetching {gov_url}: {e}")
            status = 0
            body = ""

        if status == 200 or status == 302:
            found = [kw for kw in _GENERIC_KEYWORDS if kw in body.lower()]
            if found or status == 302:
                result["platform"] = "proprio"
                result["url"] = gov_url
                result["status"] = "detected"
                if found:
                    result["keywords_found"] = found
                _logger.info(
                    f"Detected 'proprio' for '{municipio}': {gov_url}"
                    + (f" (keywords: {found})" if found else "")
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
            with open(path, "r", encoding="utf-8") as f:
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
            with open(path, "r", encoding="utf-8") as f:
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


# ---------------------------------------------------------------------------
# Crawler interface (called by monitor.py)
# ---------------------------------------------------------------------------

def crawl(mode: str = "full") -> list[dict]:
    """Detect transparency platforms for SC municipalities.

    Iterates over entities (from TRANSPARENCIA_ENTITIES_FILE or stub list),
    detects which transparency portal platform each one uses, and saves
    results to ``data/transparencia_platforms.json``.

    Args:
        mode:
            ``"full"`` (default) — detect all entities, overwriting previous
            results for re-detected slugs.
            ``"incremental"`` — only detect entities not yet present in the
            saved results file.

    Returns:
        List of detection result dicts (see ``detect_platform`` for schema).
        Each dict has at least: municipio, slug, platform, url, status.
    """
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
            results.append({
                "municipio": nome,
                "slug": slug,
                "platform": None,
                "url": None,
                "status": "error",
                "error": str(e),
                "detected_at": date.today().isoformat(),
            })
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
        f"Crawl complete: {new_count} new, {skipped_count} skipped, "
        f"{error_count} errors ({len(results)} total in file)"
    )

    return results


def transform(records: list[dict]) -> list[dict]:
    """Normalize raw records to pncp_raw_bids schema.

    **Phase 2 stub.** Actual scraping logic (parsing HTML per platform)
    will be implemented in a future iteration. For now, returns an empty
    list.

    Schema (when implemented):
        pncp_id, objeto_compra, valor_total_estimado, modalidade_id,
        modalidade_nome, esfera_id, uf, municipio, codigo_municipio_ibge,
        orgao_razao_social, orgao_cnpj, data_publicacao, data_abertura,
        data_encerramento, link_pncp, content_hash (MD5), source_id

    Args:
        records: Raw records from ``crawl()`` (platform detection results).

    Returns:
        Empty list — no scraping data available yet.
    """
    _logger.info(
        "transform() called but scraping not yet implemented (Phase 2). "
        f"Received {len(records)} raw records, returning empty list."
    )
    return []


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
        description="Transparencia Crawler — detecta plataformas de portais municipais"
    )
    parser.add_argument(
        "--mode",
        choices=["full", "incremental"],
        default="full",
        help="Modo de execucao (default: full)",
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
        "--verbose", "-v",
        action="store_true",
        help="Log em nivel DEBUG",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.slug:
        # Fast single-slug detection (for testing)
        result = detect_platform(args.slug, municipio=args.slug)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if args.entities:
            os.environ["TRANSPARENCIA_ENTITIES_FILE"] = args.entities
        if args.output:
            os.environ["TRANSPARENCIA_OUTPUT_DIR"] = args.output

        results = crawl(mode=args.mode)
        print(f"\nDetection complete: {len(results)} total records")
        print(f"  Detected:   {sum(1 for r in results if r.get('status') == 'detected')}")
        print(f"  Not found:  {sum(1 for r in results if r.get('status') == 'not_found')}")
        print(f"  Errors:     {sum(1 for r in results if r.get('status') == 'error')}")
