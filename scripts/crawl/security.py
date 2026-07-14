"""Security hardening utilities for crawler modules — Extra Consultoria.

Provides shared security constants and helpers used across all crawlers
to enforce consistent security practices:

- **Standardized User-Agent** — single constant imported by all crawlers
- **Safe URL construction** — prevents injection via unencoded param values
- **SSL verification** — centralized verification policy

Consolidated per TD-5.4 (Hardening de Seguranca).

Usage::

    from scripts.crawl.security import USER_AGENT, make_url

    url = make_url("https://api.example.com", {"key": "value"})
    headers = {"User-Agent": USER_AGENT}
"""

from __future__ import annotations

import urllib.parse
from typing import Any

# ---------------------------------------------------------------------------
# Standardized User-Agent
# ---------------------------------------------------------------------------

# Single consistent User-Agent string for all API-based crawlers.
# HTML scrapers (e.g., sc_compras_crawler) MAY use a browser-like UA
# for compatibility with server-side request inspection.
USER_AGENT = "Extra-Consultoria/1.0 (consultoria-licitacoes; +https://extraconsultoria.com.br)"

# Alternative UA for PNCP-specific clients that need to identify differently
# to API providers who expect the SmartLic application identity.
PNCP_USER_AGENT = USER_AGENT

# ---------------------------------------------------------------------------
# SSL verification
# ---------------------------------------------------------------------------

# All HTTP clients validate SSL certificates by default (urllib, requests,
# httpx). This constant documents the policy — we explicitly DO NOT disable
# SSL verification in any environment, including development.
#
# Rationale (TD-SEC-02):
# - Disabling SSL verification (verify=False) exposes all traffic to
#   man-in-the-middle attacks
# - Brazilian government APIs (PNCP, ComprasGov, DOM-SC, TCE-SC) all
#   support HTTPS with valid certificates
# - Self-signed certificates in dev environments MUST use certifi or
#   custom CA bundles instead of disabling verification
SSL_VERIFY_ENABLED = True

# ---------------------------------------------------------------------------
# Safe URL construction
# ---------------------------------------------------------------------------

# Sentinel for parameters that should be omitted (not sent as empty string)
_OMIT = object()


def sanitize_url_param(value: Any) -> str:
    """URL-encode a parameter value safely.

    This is the core defense against injection attacks in URL query strings.
    Always use this when constructing URLs with user-supplied or API-supplied
    parameter values.

    Args:
        value: Parameter value (converted to str before encoding).

    Returns:
        URL-encoded string safe for inclusion in query strings.
    """
    return urllib.parse.quote(str(value), safe="")


def make_url(base: str, params: dict[str, Any]) -> str:
    """Build a URL with query parameters, encoding all values safely.

    Replaces the unsafe ``f"{k}={v}"`` pattern found in several crawlers.

    Args:
        base: Base URL (e.g. ``"https://api.example.com/endpoint"``).
        params: Query parameters dict. Values set to ``None`` are omitted.

    Returns:
        Full URL with properly encoded query string.

    Example:
        >>> make_url("https://api.gov.br/search", {"q": "licitação 2024", "page": 1})
        'https://api.gov.br/search?q=licita%C3%A7%C3%A3o+2024&page=1'
    """
    parts: list[str] = []
    for k, v in params.items():
        if v is None:
            continue
        parts.append(f"{k}={sanitize_url_param(v)}")
    query = "&".join(parts)
    return f"{base}?{query}" if query else base
