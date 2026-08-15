"""Generic public transparency-portal adapter.

Never invents success on login, CAPTCHA or 403. An empty or error page is
never published as "no tender".

Refs #256
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

from scripts.crawl.resilience.diagnostics import sanitize_url

PORTAL_STRATEGY_SCHEMA = "generic-public-portal/v1"
_CAPTCHA_MARKERS = ("captcha", "recaptcha", "hcaptcha", "cf-challenge")
_LOGIN_MARKERS = (
    'type="password"',
    'name="password"',
    'name="senha"',
    'id="login"',
    "acesso restrito",
    "autenticar",
)
_LIST_HINTS = ("licita", "edital", "pregão", "pregao", "concorrenc")


@dataclass(frozen=True)
class PortalStrategy:
    version: str
    list_selector: str = "table.licitacoes tr, article.edital, li.edital"
    document_href_contains: str = ".pdf"
    pagination_rel: str = "next"


@dataclass(frozen=True)
class PortalRecord:
    title: str
    detail_url: str | None
    document_url: str | None


@dataclass(frozen=True)
class PortalPageResult:
    terminal: str
    reason: str
    strategy_version: str
    sanitized_url: str | None
    http_status: int | None
    records: tuple[PortalRecord, ...]
    pages_fetched: int
    raw_sha256: str
    freshness_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "terminal": self.terminal,
            "reason": self.reason,
            "strategy_version": self.strategy_version,
            "sanitized_url": self.sanitized_url,
            "http_status": self.http_status,
            "record_count": len(self.records),
            "records": [
                {
                    "title": record.title,
                    "detail_url": record.detail_url,
                    "document_url": record.document_url,
                }
                for record in self.records
            ],
            "pages_fetched": self.pages_fetched,
            "raw_sha256": self.raw_sha256,
            "freshness_at": self.freshness_at,
        }


def default_strategy(version: str = "v1") -> PortalStrategy:
    return PortalStrategy(version=f"{PORTAL_STRATEGY_SCHEMA}:{version}")


def interpret_portal_fetch(
    *,
    url: str,
    http_status: int | None,
    body: str | bytes,
    strategy: PortalStrategy | None = None,
    fetched_at: datetime | None = None,
) -> PortalPageResult:
    """Classify one public portal page without inventing a zero-tender success."""
    resolved = strategy or default_strategy()
    raw = body.encode("utf-8") if isinstance(body, str) else bytes(body)
    digest = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8", errors="replace")
    lowered = text.lower()
    safe_url = sanitize_url(url)
    observed = (fetched_at or datetime.now(UTC)).astimezone(UTC).isoformat()
    if http_status in {401, 403} or any(marker in lowered for marker in _CAPTCHA_MARKERS) or _looks_like_login(lowered):
        return PortalPageResult(
            terminal="BLOCKED",
            reason="login_captcha_or_forbidden",
            strategy_version=resolved.version,
            sanitized_url=safe_url,
            http_status=http_status,
            records=(),
            pages_fetched=1,
            raw_sha256=digest,
            freshness_at=observed,
        )
    if http_status is None or http_status >= 500 or http_status == 404:
        return PortalPageResult(
            terminal="FAILED",
            reason="transport_or_source_error",
            strategy_version=resolved.version,
            sanitized_url=safe_url,
            http_status=http_status,
            records=(),
            pages_fetched=1,
            raw_sha256=digest,
            freshness_at=observed,
        )
    records = _extract_records(text, url=url)
    if records:
        return PortalPageResult(
            terminal="FOUND",
            reason="listing_or_document_extracted",
            strategy_version=resolved.version,
            sanitized_url=safe_url,
            http_status=http_status,
            records=tuple(records),
            pages_fetched=1,
            raw_sha256=digest,
            freshness_at=observed,
        )
    return PortalPageResult(
        terminal="FAILED",
        reason="empty_or_layout_unrecognized",
        strategy_version=resolved.version,
        sanitized_url=safe_url,
        http_status=http_status,
        records=(),
        pages_fetched=1,
        raw_sha256=digest,
        freshness_at=observed,
    )


def _looks_like_login(lowered: str) -> bool:
    return any(marker in lowered for marker in _LOGIN_MARKERS)


def _extract_records(html: str, *, url: str) -> list[PortalRecord]:
    records: list[PortalRecord] = []
    row_pattern = re.compile(
        r"<tr[^>]*>(.*?)</tr>|<article[^>]*>(.*?)</article>|<li[^>]*class=\"[^\"]*edital[^\"]*\"[^>]*>(.*?)</li>",
        re.IGNORECASE | re.DOTALL,
    )
    href_pattern = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
    text_pattern = re.compile(r">([^<>]{3,200})<")
    for match in row_pattern.finditer(html):
        chunk = next(group for group in match.groups() if group)
        lowered = chunk.lower()
        hrefs = href_pattern.findall(chunk)
        if not hrefs and not any(hint in lowered for hint in _LIST_HINTS):
            continue
        texts = [item.strip() for item in text_pattern.findall(chunk) if item.strip()]
        title = next(
            (item for item in texts if any(hint in item.lower() for hint in _LIST_HINTS)),
            texts[0] if texts else "documento",
        )
        document_url = next((urljoin(url, href) for href in hrefs if ".pdf" in href.lower()), None)
        detail_url = urljoin(url, hrefs[0]) if hrefs else None
        if document_url or any(hint in lowered for hint in _LIST_HINTS):
            records.append(
                PortalRecord(
                    title=title,
                    detail_url=sanitize_url(detail_url) if detail_url else None,
                    document_url=sanitize_url(document_url) if document_url else None,
                )
            )
    if records:
        return records
    pdf_only = href_pattern.findall(html)
    for href in pdf_only:
        if ".pdf" not in href.lower():
            continue
        records.append(
            PortalRecord(
                title="documento",
                detail_url=None,
                document_url=sanitize_url(urljoin(url, href)),
            )
        )
    return records
