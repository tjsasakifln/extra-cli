"""Selenium Crawler Adapter — Interface padronizada para monitor.py.

Fornece as funcoes ``crawl(mode)`` e ``transform(records)`` exigidas
pelo ``monitor.py`` para o source ``selenium``.

Este modulo e um wrapper thin sobre ``SeleniumBatchCrawler`` que
implementa a mesma interface dos demais crawlers (PNCP, DOM-SC, etc.),
permitindo que o orquestrador ``monitor.py`` trate o Selenium como
mais uma fonte de dados.

Usage via monitor.py::

    python scripts/crawl/monitor.py --source selenium --mode full
    python scripts/crawl/monitor.py --source selenium --mode dry-run
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SELENIUM_PORTALS_FILE = os.getenv(
    "SELENIUM_PORTALS_FILE",
    str(_PROJECT_ROOT / "data" / "js_portals_list.json"),
)
"""Path to JSON file listing JS-rendered portals to crawl."""

SELENIUM_HEADLESS = os.getenv("SELENIUM_HEADLESS", "true").lower() in ("true", "1", "yes")
SELENIUM_TIMEOUT = int(os.getenv("SELENIUM_TIMEOUT", "300"))
SELENIUM_DEBUG_DIR = os.getenv("SELENIUM_DEBUG_DIR", "data/selenium_debug/")

# ---------------------------------------------------------------------------
# Portal list loader
# ---------------------------------------------------------------------------


def load_portals(portals_file: str = "") -> list[dict]:
    """Load the list of JS-rendered portals from the JSON file.

    Args:
        portals_file: Path to the JSON portals file.
            Defaults to ``SELENIUM_PORTALS_FILE`` env var.

    Returns:
        List of portal dicts with keys: ``slug``, ``nome``, ``ibge``,
        ``url``, ``platform``, ``requires_js``.
    """
    filepath = Path(portals_file or os.getenv("SELENIUM_PORTALS_FILE", SELENIUM_PORTALS_FILE))
    if not filepath.exists():
        _logger.warning("Portals file not found: %s", filepath)
        return []

    try:
        with open(filepath) as f:
            data = json.load(f)
        # Top-level list format
        if isinstance(data, list):
            portals = data
        else:
            portals = data.get("portals", data.get("detected_list", []))
        _logger.info("Loaded %d portals from %s", len(portals), filepath)
        return portals
    except (json.JSONDecodeError, OSError) as e:
        _logger.error("Failed to load portals file %s: %s", filepath, e)
        return []


# ---------------------------------------------------------------------------
# Crawl interface (called by monitor.py)
# ---------------------------------------------------------------------------


def crawl(mode: str = "full") -> list[dict]:
    """Execute Selenium batch crawl for JS-rendered transparency portals.

    Args:
        mode:
            ``"full"`` (default) — crawl all JS-rendered portals in batch.
            ``"incremental"`` — same as ``"full"`` (Selenium always does full
            render).
            ``"dry-run"`` — list portals without executing crawl.

    Returns:
        List of scraping result dicts per portal, with keys:
        ``slug``, ``municipio``, ``ibge``, ``url``, ``status``,
        ``bids``, ``bid_count``, ``framework``, ``error``, ``method``.
    """
    portals = load_portals()

    if not portals:
        _logger.warning("No JS-rendered portals to crawl")
        return []

    if mode == "dry-run":
        _logger.info("DRY RUN: %d portals to crawl:", len(portals))
        for p in portals:
            _logger.info("  - %s (%s): %s", p.get("nome"), p.get("slug"), p.get("url"))
        return [
            {
                "slug": p.get("slug", ""),
                "municipio": p.get("nome", ""),
                "ibge": p.get("ibge", ""),
                "url": p.get("url", ""),
                "status": "dry-run",
                "bids": [],
                "bid_count": 0,
                "method": "dry_run",
            }
            for p in portals
        ]

    try:
        from scripts.crawl.selenium_crawler import SeleniumBatchCrawler

        batch = SeleniumBatchCrawler(
            headless=SELENIUM_HEADLESS,
            timeout=SELENIUM_TIMEOUT,
            debug_dir=SELENIUM_DEBUG_DIR,
        )
        summary = batch.run_batch(portals)
        _logger.info(
            "Selenium batch complete: %d portals, %d bids, %d failed",
            summary["portal_count"],
            summary["extracted"],
            summary["failed"],
        )
        return summary.get("results", [])

    except ImportError as e:
        _logger.error("Selenium not available: %s", e)
        return []
    except Exception as e:
        _logger.error("Selenium batch crawl failed: %s", e)
        return []


def transform(records: list[dict]) -> list[dict]:
    """Transform Selenium scraping results to canonical pncp_raw_bids schema.

    Cada record e um resultado de portal (com lista de bids internos).
    Esta funcao achata (flatten) os bids para o schema aceito por
    ``upsert_pncp_raw_bids``:

        pncp_id, objeto_compra, valor_total_estimado,
        modalidade_id, modalidade_nome, esfera_id,
        uf, municipio, codigo_municipio_ibge,
        orgao_razao_social, orgao_cnpj,
        data_publicacao, data_abertura, data_encerramento,
        link_pncp, content_hash, source_id

    Args:
        records: Lista de resultados de ``crawl()``, cada um com
            ``bids`` (lista de dicts) e metadados do portal.

    Returns:
        Lista de bids normalizados para upsert em ``pncp_raw_bids``.
    """
    transformed: list[dict] = []

    for record in records:
        if record.get("status") != "ok":
            continue

        bids = record.get("bids", [])
        if not bids:
            continue

        for bid in bids:
            m_id, m_nome = _map_modalidade(bid.get("modalidade", ""))
            pncp_id = _generate_pncp_id(bid, record)
            content_hash = _make_hash(bid, record)

            transformed.append(
                {
                    "pncp_id": pncp_id,
                    "objeto_compra": bid.get("objeto", ""),
                    "valor_total_estimado": _parse_valor(bid.get("valor", "")),
                    "modalidade_id": m_id,
                    "modalidade_nome": m_nome,
                    "esfera_id": 3,  # Municipal (portais de municipios)
                    "uf": "SC",
                    "municipio": record.get("municipio", ""),
                    "codigo_municipio_ibge": record.get("ibge", ""),
                    "orgao_razao_social": bid.get("orgao_nome", record.get("municipio", "")),
                    "orgao_cnpj": bid.get("orgao_cnpj", ""),
                    "data_publicacao": bid.get("data_publicacao", ""),
                    "data_abertura": None,
                    "data_encerramento": None,
                    "link_pncp": bid.get("portal_url", record.get("url", "")),
                    "content_hash": content_hash,
                    "source_id": f"selenium_{record.get('slug', '')}_{pncp_id[-12:]}",
                }
            )

    _logger.info("Selenium transform: %d records -> %d flat bids", len(records), len(transformed))
    return transformed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_valor(valor_str: Any) -> float | None:
    """Parse a Brazilian currency value string to float.

    Examples:
        "R$ 1.234,56" -> 1234.56
        "1.234,56" -> 1234.56
        "1234" -> 1234.0
    """
    if not valor_str:
        return None

    if isinstance(valor_str, (int, float)):
        return float(valor_str)

    cleaned = str(valor_str).strip()
    # Remove "R$", "RS", "R $" prefix
    cleaned = cleaned.replace("R$", "").replace("RS", "").replace("R $", "").strip()
    # Remove dots (thousand separators)
    cleaned = cleaned.replace(".", "")
    # Replace comma with dot (decimal separator)
    cleaned = cleaned.replace(",", ".")

    try:
        return round(float(cleaned), 2)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Modalidade mapping (extracted text → canonical id + name)
# ---------------------------------------------------------------------------

_MODALIDADE_MAP: dict[str, tuple[int, str]] = {
    "pregao": (5, "Pregao Eletronico"),
    "pregao eletronico": (5, "Pregao Eletronico"),
    "pregão eletrônico": (5, "Pregao Eletronico"),
    "pregao presencial": (6, "Pregao Presencial"),
    "pregão presencial": (6, "Pregao Presencial"),
    "concorrencia": (4, "Concorrencia"),
    "concorrência": (4, "Concorrencia"),
    "dispensa": (7, "Dispensa de Licitacao"),
    "dispensa de licitacao": (7, "Dispensa de Licitacao"),
    "dispensa de licitação": (7, "Dispensa de Licitacao"),
    "inexigibilidade": (8, "Inexigibilidade"),
    "concurso": (9, "Concurso"),
    "leilao": (10, "Leilao"),
    "leilão": (10, "Leilao"),
    "tomada de precos": (3, "Tomada de Precos"),
    "tomada de preços": (3, "Tomada de Precos"),
    "convite": (2, "Convite"),
    "chamada publica": (11, "Chamada Publica"),
    "chamada pública": (11, "Chamada Publica"),
    "credenciamento": (12, "Credenciamento"),
}


def _map_modalidade(raw: str) -> tuple[int, str]:
    """Map a raw modalidade string to (modalidade_id, modalidade_nome).

    Returns (0, raw) for unrecognized values.
    """
    if not raw:
        return (0, "")
    normalized = raw.strip().lower()
    result = _MODALIDADE_MAP.get(normalized)
    if result:
        return result
    return (0, raw.strip())


def _generate_pncp_id(bid: dict, record: dict) -> str:
    """Generate a deterministic pncp_id for Selenium bids.

    Uses slug + orgao_nome + objeto + data_publicacao for uniqueness.
    """
    import hashlib

    raw = (
        f"selenium_{record.get('slug', '')}_"
        f"{bid.get('orgao_nome', '')}_"
        f"{bid.get('objeto', '')}_"
        f"{bid.get('data_publicacao', '')}"
    )
    return "sel_" + hashlib.sha256(raw.encode()).hexdigest()[:32]


def _make_hash(bid: dict, record: dict | None = None) -> str:
    """Generate a deterministic content hash for deduplication.

    Uses canonical field names matching the pncp_raw_bids schema
    for consistency with other crawlers.
    """
    import hashlib

    content = (
        f"{bid.get('orgao_nome', '')}|"
        f"{bid.get('modalidade', '')}|"
        f"{bid.get('objeto', '')}|"
        f"{bid.get('data_publicacao', '')}"
    )
    return hashlib.sha256(content.encode()).hexdigest()
