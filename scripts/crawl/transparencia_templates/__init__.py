"""Transparencia Template Modules — Extra Consultoria.

Template modules for platform-specific transparency portal scraping.
Each module exports a consistent interface:

Attributes:
    PLATFORM (str): Platform key (betha, ipam, egov, generico).
    NAME (str): Human-readable platform name.
    DESCRIPTION (str): Brief description.
    URL_PATTERNS (list[str]): URL patterns for platform detection (with {slug} placeholder).
    SELECTORS (dict): Default CSS selectors for scraping.

Functions:
    parse_page(soup: BeautifulSoup, url: str) -> list[dict]:
        Parse HTML page and return list of extracted record dicts.
"""

from importlib import import_module
from typing import Any

_LOGGER: Any = None


def _logger():
    global _LOGGER
    if _LOGGER is None:
        import logging

        _LOGGER = logging.getLogger(__name__)
    return _LOGGER


def get_template(platform: str) -> Any | None:
    """Import and return a template module by platform key.

    Args:
        platform: One of ``betha``, ``ipam``, ``egov``, ``generico``.

    Returns:
        Template module object, or ``None`` if platform not found.
    """
    module_map = {
        "betha": "scripts.crawl.transparencia_templates.betha",
        "ipam": "scripts.crawl.transparencia_templates.ipam",
        "egov": "scripts.crawl.transparencia_templates.egov",
        "generico": "scripts.crawl.transparencia_templates.generico",
    }
    mod_name = module_map.get(platform)
    if not mod_name:
        return None
    try:
        return import_module(mod_name)
    except ImportError as e:
        _logger().warning("Template module not available for '%s': %s", platform, e)
        return None


def get_all_templates() -> dict[str, Any]:
    """Return dict of all available template modules keyed by platform."""
    result: dict[str, Any] = {}
    for platform in ("betha", "ipam", "egov", "generico"):
        mod = get_template(platform)
        if mod:
            result[platform] = mod
    return result
