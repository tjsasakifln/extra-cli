"""E-Lic SC (e-lic.sc.gov.br) — HTML/ASMX limitation stub.

Discovery (2026-07-17) found no anonymous open JSON API for bulk crawl.
This module documents known public surfaces and a selector map so structure
regressions fail loudly when a fixture is present.

Rules:
  - No captcha bypass
  - No session/ASMX bulk scraping in production path
  - Prefer Compras SC JSON + PNCP for SC coverage

Usage::

    from scripts.crawl.elic_sc_stub import SELECTOR_MAP, assert_structure
"""

from __future__ import annotations

import re
from typing import Any

# Public entry points observed during discovery (GET only).
PUBLIC_URLS: dict[str, str] = {
    "home": "https://e-lic.sc.gov.br/",
    "default": "https://e-lic.sc.gov.br/Default.aspx",
    "mural": "https://e-lic.sc.gov.br/portal/Mural.aspx",
    "asmx_base": "https://e-lic.sc.gov.br/Portal/WebService/Servicos.asmx",
}

# ASMX method names referenced in homepage HTML/JS (not open data).
ASMX_METHODS_REFERENCED: tuple[str, ...] = (
    "PesquisarProcessos",
    "PesquisaPainelEletronico",
    "PesquisaPainelEletronicoModuloModalidade",
    "PesquisarAlertaPublico",
    "AdicionarCookieAlerta",
)

# Selector / structural markers for public HTML shell (Default.aspx / portal).
# Used by contract tests against fixtures — NOT for production scraping.
SELECTOR_MAP: dict[str, dict[str, Any]] = {
    "form#aspnetForm": {
        "kind": "css_or_id",
        "patterns": [r'id=["\']aspnetForm["\']', r"<form[^>]+id=[\"']aspnetForm[\"']"],
        "required": True,
        "notes": "Main ASP.NET postback form",
    },
    "#areaConteudo": {
        "kind": "id",
        "patterns": [r'id=["\']areaConteudo["\']'],
        "required": True,
        "notes": "Primary content container",
    },
    "#gridPainelEletronico": {
        "kind": "id",
        "patterns": [r'id=["\']gridPainelEletronico["\']'],
        "required": True,
        "notes": "Kendo/grid target for painel eletrônico",
    },
    "Servicos.asmx/PesquisarProcessos": {
        "kind": "script_ref",
        "patterns": [r"Servicos\.asmx/PesquisarProcessos"],
        "required": True,
        "notes": "Process search ASMX reference in page scripts",
    },
    "viewstate": {
        "kind": "hidden_field",
        "patterns": [r'id=["\']__VIEWSTATE["\']', r'name=["\']__VIEWSTATE["\']'],
        "required": True,
        "notes": "ASP.NET ViewState present on server-rendered pages",
    },
}

LIMITATION = (
    "E-Lic SC does not expose an anonymous open JSON API suitable for bulk crawl. "
    "Public surfaces are ASP.NET HTML (Mural) and session-oriented ASMX endpoints. "
    "Use Portal Compras SC /api/editais and PNCP /contratos instead."
)


def assert_structure(html: str, *, selector_map: dict[str, dict[str, Any]] | None = None) -> list[str]:
    """Validate HTML against selector map.

    Returns list of missing required markers. Empty list means structure OK.
    Raises AssertionError if any required marker is missing (fail loudly).
    """
    smap = selector_map or SELECTOR_MAP
    missing: list[str] = []
    for name, spec in smap.items():
        if not spec.get("required", False):
            continue
        patterns = spec.get("patterns") or []
        found = any(re.search(p, html, flags=re.I) for p in patterns)
        if not found:
            missing.append(name)
    if missing:
        raise AssertionError(
            "E-Lic HTML structure changed — missing required markers: "
            + ", ".join(missing)
            + f". {LIMITATION}"
        )
    return missing


def structure_report(html: str) -> dict[str, Any]:
    """Non-raising report of which markers matched."""
    results: dict[str, bool] = {}
    for name, spec in SELECTOR_MAP.items():
        patterns = spec.get("patterns") or []
        results[name] = any(re.search(p, html, flags=re.I) for p in patterns)
    return {
        "public_json": False,
        "limitation": LIMITATION,
        "markers": results,
        "all_required_ok": all(
            results[n] for n, s in SELECTOR_MAP.items() if s.get("required")
        ),
    }


def crawl(mode: str = "full") -> list[dict]:
    """Stub crawl — always empty; documents limitation.

    monitor.py-compatible signature. Does not hit the network.
    """
    _ = mode
    return []


def transform(records: list[dict]) -> list[dict]:
    """Stub transform — identity empty."""
    return list(records or [])
