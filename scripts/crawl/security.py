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

import ipaddress
import socket
import urllib.parse
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3 import HTTPSConnectionPool

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


# ---------------------------------------------------------------------------
# URL scheme validation
# ---------------------------------------------------------------------------

# Scheme allowlist — only https:// is permitted by default for all crawlers.
# http:// is ONLY allowed for specific sources that require it (e.g., some
# municipio-level portals that lack HTTPS).
ALLOWED_SCHEMES: tuple[str, ...] = ("https",)
ALLOWED_SCHEMES_WITH_HTTP: tuple[str, ...] = ("https", "http")


def validate_url_scheme(url: str, *, allow_http: bool = False) -> str:
    """Validate that a URL uses an allowed scheme (https by default).

    This is the primary SSRF defense for all crawler HTTP clients.  It
    rejects ``file://``, ``ftp://``, ``data://``, ``javascript://`` and any
    other unexpected scheme before the URL reaches ``urlopen()``.

    Args:
        url: URL to validate.
        allow_http: If ``True`` also allow ``http://``.  Use ONLY when the
            official source does not support HTTPS and this is documented.

    Returns:
        The validated URL (enables inline use like
        ``urlopen(validate_url_scheme(url))``).

    Raises:
        ValueError: If the URL's scheme is not in the allowlist.
    """
    parsed = urllib.parse.urlparse(url)
    allowed = ALLOWED_SCHEMES_WITH_HTTP if allow_http else ALLOWED_SCHEMES
    if parsed.scheme not in allowed:
        raise ValueError(
            f"Disallowed URL scheme '{parsed.scheme}' in {url[:100]!r}. "
            f"Only {' or '.join('://' + s for s in allowed)} are permitted."
        )
    return url


def validate_public_url(
    url: str,
    *,
    allow_http: bool = False,
    resolve_dns: bool = True,
) -> str:
    """Reject local/private targets and traversal before any crawler request."""
    validate_url_scheme(url, allow_http=allow_http)
    parsed = urllib.parse.urlsplit(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if not hostname or hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("crawler URL requires a non-local hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("crawler URL must not contain userinfo credentials")
    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None
    if literal_ip is not None and not literal_ip.is_global:
        raise ValueError(f"crawler URL resolves to non-public address: {literal_ip}")
    decoded_path = urllib.parse.unquote(parsed.path).replace("\\", "/")
    if any(part == ".." for part in decoded_path.split("/")):
        raise ValueError("crawler URL path traversal rejected")

    if resolve_dns:
        _resolve_public_addresses(hostname, parsed.port or 443)
    return url


def _resolve_public_addresses(hostname: str, port: int) -> tuple[str, ...]:
    """Resolve a host once and return only globally routable addresses."""
    addresses: set[str] = set()
    try:
        addresses.add(str(ipaddress.ip_address(hostname)))
    except ValueError:
        try:
            addresses.update(
                info[4][0]
                for info in socket.getaddrinfo(
                    hostname,
                    port,
                    type=socket.SOCK_STREAM,
                )
            )
        except socket.gaierror as exc:
            raise ValueError(f"crawler hostname could not be resolved: {hostname}") from exc
    if not addresses:
        raise ValueError(f"crawler hostname resolved without addresses: {hostname}")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError(f"crawler URL resolves to non-public address: {address}")
    return tuple(sorted(addresses, key=lambda value: (ipaddress.ip_address(value).version, value)))


class _PinnedHTTPSAdapter(HTTPAdapter):
    """Connect to a validated IP while retaining hostname TLS verification."""

    def __init__(self, *, address: str, hostname: str, port: int):
        self.address = address
        self.hostname = hostname
        self.port = port
        super().__init__()

    def get_connection(self, url: str, proxies: Any = None) -> HTTPSConnectionPool:
        if proxies and any(proxies.values()):
            raise ValueError("crawler pinned transport does not permit ambient proxies")
        return HTTPSConnectionPool(
            self.address,
            self.port,
            assert_hostname=self.hostname,
            server_hostname=self.hostname,
        )


def _pinned_get(session: requests.Session, url: str, addresses: tuple[str, ...], **kwargs: Any) -> Any:
    parsed = urllib.parse.urlsplit(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    port = parsed.port or 443
    origin = f"https://{parsed.netloc}/"
    original_adapter = session.get_adapter(origin)
    pinned_adapter = _PinnedHTTPSAdapter(address=addresses[0], hostname=hostname, port=port)
    if kwargs.get("stream"):
        raise ValueError("crawler pinned transport does not support streamed responses")
    headers = dict(kwargs.pop("headers", {}) or {})
    host_header = hostname if ":" not in hostname else f"[{hostname}]"
    if parsed.port is not None and parsed.port != 443:
        host_header = f"{host_header}:{parsed.port}"
    headers["Host"] = host_header
    session.mount(origin, pinned_adapter)
    try:
        return session.get(url, allow_redirects=False, headers=headers, **kwargs)
    finally:
        session.mount(origin, original_adapter)
        pinned_adapter.close()


def validate_redirect_chain(response: Any, *, allow_http: bool = False) -> None:
    """Validate every effective URL after redirects, including DNS resolution."""
    chain = [*(getattr(response, "history", None) or []), response]
    for item in chain:
        effective = getattr(item, "url", None)
        if isinstance(effective, str) and effective:
            validate_public_url(effective, allow_http=allow_http, resolve_dns=True)


def public_get(
    session: Any,
    url: str,
    *,
    allow_http: bool = False,
    resolve_initial_dns: bool = True,
    max_redirects: int = 10,
    **kwargs: Any,
) -> Any:
    """Issue a GET while validating every redirect target before it is fetched."""
    current = url
    for redirect_count in range(max_redirects + 1):
        resolve_current = resolve_initial_dns if redirect_count == 0 else True
        validate_public_url(
            current,
            allow_http=allow_http,
            resolve_dns=False,
        )
        if resolve_current:
            if allow_http or urllib.parse.urlsplit(current).scheme != "https":
                raise ValueError("crawler pinned transport requires HTTPS")
            if not isinstance(session, requests.Session):
                raise ValueError("crawler DNS pinning requires requests.Session transport")
            parsed = urllib.parse.urlsplit(current)
            hostname = (parsed.hostname or "").lower().rstrip(".")
            addresses = _resolve_public_addresses(hostname, parsed.port or 443)
            response = _pinned_get(session, current, addresses, **kwargs)
        else:
            if isinstance(session, requests.Session):
                raise ValueError("real crawler transport cannot disable DNS pinning")
            response = session.get(current, allow_redirects=False, **kwargs)
        status = int(getattr(response, "status_code", 0) or 0)
        if status not in {301, 302, 303, 307, 308}:
            validate_redirect_chain(response, allow_http=allow_http)
            return response
        location = (getattr(response, "headers", None) or {}).get("Location")
        if not location:
            return response
        if redirect_count >= max_redirects:
            close = getattr(response, "close", None)
            if callable(close):
                close()
            raise ValueError(f"crawler redirect limit exceeded ({max_redirects})")
        next_url = urllib.parse.urljoin(current, str(location))
        validate_public_url(next_url, allow_http=allow_http, resolve_dns=True)
        close = getattr(response, "close", None)
        if callable(close):
            close()
        current = next_url
    raise AssertionError("unreachable redirect loop guard")


def validate_url_scheme_optional(url: str | None, *, allow_http: bool = False) -> str | None:
    """Like :func:`validate_url_scheme` but accepts ``None`` (pass-through).

    Convenience for call sites where the URL may be ``None``.
    """
    if url is None:
        return None
    return validate_url_scheme(url, allow_http=allow_http)


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
