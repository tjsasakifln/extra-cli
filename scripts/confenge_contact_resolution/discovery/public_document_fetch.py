"""Bounded validation of public search leads against an exact CNPJ."""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import re
import socket
import ssl
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request

from scripts.confenge_contact_resolution.discovery.extract import (
    extract_contacts_from_html,
    extract_contacts_from_text,
)
from scripts.confenge_process_enrichment.text_extract import extract_from_pdf_bytes

_USER_AGENT = "Mozilla/5.0 (compatible; extra-cli-confenge-contact/1.0)"
_PUBLISHED_META_RE = re.compile(
    r"""(?is)<meta[^>]+(?:property|name)=["'](?:article:published_time|datePublished|date)["'][^>]+content=["']([^"']+)["']"""
)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _contains_exact_cnpj(value: str, target: str) -> bool:
    digits = re.sub(r"\D", "", target or "")
    if len(digits) != 14:
        return False
    pattern = r"(?<!\d)" + r"[.\-/\s]*".join(re.escape(digit) for digit in digits) + r"(?!\d)"
    return re.search(pattern, value or "") is not None


@dataclass
class PublicDocumentResult:
    url: str
    status: int = 0
    content_type: str = ""
    content_sha256: str | None = None
    source_published_at: str | None = None
    observed_at: str = field(default_factory=_now)
    cnpj_linked: bool = False
    evidence_strength: str = "document_contact"
    contacts: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def as_public_docs(self) -> list[dict[str, Any]]:
        if not self.cnpj_linked:
            return []
        return [
            {
                **contact,
                "url": self.url,
                "source_url": self.url,
                "source_published_at": self.source_published_at,
                "observed_at": self.observed_at,
                "document_id": self.content_sha256,
                "doc_type": "public_source_ladder_document",
                "evidence_strength": self.evidence_strength,
            }
            for contact in self.contacts
        ]


def _public_http_url(url: str) -> tuple[bool, str | None]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return False, "invalid_public_url"
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(
                parsed.hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        }
    except (OSError, UnicodeError, ValueError):
        return False, "public_host_resolution_failed"
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        return False, "non_public_address"
    return True, None


def _validated_addresses(url: str) -> tuple[list[str], str | None]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return [], "invalid_public_url"
    try:
        addresses = sorted(
            {
                item[4][0]
                for item in socket.getaddrinfo(
                    parsed.hostname,
                    parsed.port or (443 if parsed.scheme == "https" else 80),
                    type=socket.SOCK_STREAM,
                )
            }
        )
    except (OSError, UnicodeError, ValueError):
        return [], "public_host_resolution_failed"
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        return [], "non_public_address"
    return addresses, None


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, address: str, *args: Any, **kwargs: Any) -> None:
        self._validated_address = address
        super().__init__(host, *args, **kwargs)

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self._validated_address, self.port),
            self.timeout,
            self.source_address,
        )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str, *args: Any, **kwargs: Any) -> None:
        self._validated_address = address
        super().__init__(host, *args, **kwargs)

    def connect(self) -> None:
        sock = socket.create_connection(
            (self._validated_address, self.port),
            self.timeout,
            self.source_address,
        )
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _PinnedResponse:
    def __init__(self, response: http.client.HTTPResponse, *, connection: Any, url: str) -> None:
        self._response = response
        self._connection = connection
        self.status = response.status
        self.headers = response.headers
        self._url = url

    def __enter__(self):
        return self

    def __exit__(self, *args: Any) -> None:
        self._connection.close()

    def read(self, amount: int) -> bytes:
        return self._response.read(amount)

    def geturl(self) -> str:
        return self._url


def _open_public_url(req: Request, *, timeout: float, max_redirects: int = 5):
    current = req.full_url
    headers = dict(req.header_items())
    for _ in range(max_redirects + 1):
        parsed = urlparse(current)
        addresses, error = _validated_addresses(current)
        if not addresses:
            raise URLError(error or "no_public_address")
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        conn_cls = _PinnedHTTPSConnection if parsed.scheme == "https" else _PinnedHTTPConnection
        conn = (
            conn_cls(
                host,
                addresses[0],
                port=port,
                timeout=timeout,
                context=ssl.create_default_context() if parsed.scheme == "https" else None,
            )
            if parsed.scheme == "https"
            else conn_cls(host, addresses[0], port=port, timeout=timeout)
        )
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        conn.request("GET", path, headers={**headers, "Host": parsed.netloc})
        response = conn.getresponse()
        if response.status not in {301, 302, 303, 307, 308}:
            return _PinnedResponse(response, connection=conn, url=current)
        location = response.headers.get("Location")
        conn.close()
        if not location:
            raise URLError("redirect_without_location")
        current = urljoin(current, location)
    raise URLError("too_many_redirects")


def fetch_cnpj_linked_public_document(
    url: str,
    *,
    cnpj14: str,
    timeout: float = 12.0,
    max_bytes: int = 2_000_000,
    official_company_domain: str | None = None,
) -> PublicDocumentResult:
    """Fetch a public lead and accept its contacts only if exact CNPJ is present."""
    result = PublicDocumentResult(url=url)
    valid, error = _public_http_url(url)
    if not valid:
        result.error = error
        return result
    req = Request(  # noqa: S310
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.1",
        },
    )
    try:
        with _open_public_url(req, timeout=timeout) as response:
            result.status = int(getattr(response, "status", 200) or 200)
            result.url = str(response.geturl() or url)
            if result.status >= 400:
                result.error = f"http_{result.status}"
                return result
            final_valid, final_error = _public_http_url(result.url)
            if not final_valid:
                result.error = final_error or "unsafe_final_url"
                return result
            result.content_type = str(response.headers.get("Content-Type") or "").lower()
            raw = response.read(max_bytes + 1)
    except HTTPError as exc:
        result.status = int(exc.code)
        result.error = f"http_{exc.code}"
        return result
    except (URLError, TimeoutError, OSError) as exc:
        result.error = type(exc).__name__
        return result
    if len(raw) > max_bytes:
        result.error = "document_too_large"
        return result

    result.content_sha256 = hashlib.sha256(raw).hexdigest()
    is_pdf = "application/pdf" in result.content_type or raw.startswith(b"%PDF")
    html = ""
    if is_pdf:
        extracted = extract_from_pdf_bytes(raw, allow_ocr=False)
        text = extracted.text
        contacts = extract_contacts_from_text(text, source_url=result.url)
    else:
        html = raw.decode("utf-8", errors="replace")
        text = re.sub(r"(?s)<[^>]+>", " ", html)
        contacts = extract_contacts_from_html(html, source_url=result.url)
        published = _PUBLISHED_META_RE.search(html)
        if published:
            result.source_published_at = published.group(1).strip()

    target = re.sub(r"\D", "", cnpj14 or "")
    result.cnpj_linked = _contains_exact_cnpj(result.url, target) or _contains_exact_cnpj(text, target)
    if not result.cnpj_linked:
        result.error = "exact_cnpj_not_present"
        return result
    source_host = (urlparse(result.url).hostname or "").lower().removeprefix("www.")
    company_host = (official_company_domain or "").lower().removeprefix("www.")
    if company_host and (source_host == company_host or source_host.endswith(f".{company_host}")):
        result.evidence_strength = "company_authored_document"
    elif source_host.endswith(".gov.br") or source_host == "gov.br":
        result.evidence_strength = "official_cnpj_linked_document"
    result.contacts = contacts
    return result
