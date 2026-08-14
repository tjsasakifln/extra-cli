"""Public CIGA/DOM-SC discovery that survives slug drift.

package_list 404 is a drift alert, never a silent municipal zero.
429/5xx are retryable. ZIP members are extracted with zip-slip protection.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

CKAN_BASE = "https://dados.ciga.sc.gov.br"
CKAN_API = f"{CKAN_BASE}/api/3/action"
MUNICIPAL_UNIVERSE = 295
PERIOD_START = "2025-01-01"
SLA_HOURS = 24

HttpFn = Callable[[str], tuple[int, bytes, str]]


@dataclass(frozen=True)
class HttpOutcome:
    url: str
    status: int
    retryable: bool
    drift_alert: bool
    body: bytes
    fetched_at: str


@dataclass(frozen=True)
class PageEvidence:
    url: str
    status: int
    fetched_at: str
    raw_uri: str
    sha256: str


@dataclass(frozen=True)
class ZipMember:
    name: str
    sha256: str
    size: int


@dataclass(frozen=True)
class MunicipalityVerdict:
    municipio: str
    status: str
    evidence: str


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def classify_http(status: int) -> tuple[bool, bool]:
    """Return (retryable, drift_alert)."""
    if status == 404:
        return False, True
    if status == 429 or status >= 500:
        return True, False
    if 200 <= status < 300:
        return False, False
    if status == 408:
        return True, False
    return False, False


def fetch_public(url: str, http: HttpFn) -> HttpOutcome:
    status, body, fetched_at = http(url)
    retryable, drift = classify_http(status)
    return HttpOutcome(
        url=url,
        status=status,
        retryable=retryable,
        drift_alert=drift,
        body=body,
        fetched_at=fetched_at,
    )


def page_evidence(outcome: HttpOutcome, *, raw_uri: str) -> PageEvidence:
    return PageEvidence(
        url=outcome.url,
        status=outcome.status,
        fetched_at=outcome.fetched_at,
        raw_uri=raw_uri,
        sha256=sha256_bytes(outcome.body),
    )


def resolve_package(
    slug_or_query: str,
    *,
    http: HttpFn,
    api_base: str = CKAN_API,
) -> dict[str, Any]:
    """Show the slug; on 404, search publicly and retry show on the first hit."""
    show_url = f"{api_base}/package_show?id={slug_or_query}"
    shown = fetch_public(show_url, http)
    if shown.status == 200:
        return {"ok": True, "via": "show", "slug": slug_or_query, "drift_alert": False}
    if shown.drift_alert:
        search_url = f"{api_base}/package_search?q={slug_or_query}&rows=5"
        searched = fetch_public(search_url, http)
        if searched.retryable:
            return {"ok": False, "via": "search", "retryable": True, "drift_alert": False}
        if searched.status != 200:
            return {
                "ok": False,
                "via": "search",
                "drift_alert": searched.drift_alert or shown.drift_alert,
                "status": searched.status,
            }
        # Callers supply a parsed name via http side-channel? Keep slug search contract:
        # if search succeeded, try common DOM-SC prefixes.
        candidates = (
            slug_or_query,
            slug_or_query.replace("dom-sc", "domsc"),
            slug_or_query.replace("domsc", "dom-sc"),
            f"domsc-publicacoes-de-{slug_or_query}",
        )
        for candidate in candidates:
            retry = fetch_public(f"{api_base}/package_show?id={candidate}", http)
            if retry.status == 200:
                return {"ok": True, "via": "search+show", "slug": candidate, "drift_alert": True}
        return {"ok": False, "via": "search+show", "drift_alert": True, "status": 404}
    if shown.retryable:
        return {"ok": False, "via": "show", "retryable": True, "drift_alert": False}
    return {"ok": False, "via": "show", "status": shown.status, "drift_alert": shown.drift_alert}


def period_covers(start: str, snapshot: str) -> bool:
    return start <= PERIOD_START and snapshot >= PERIOD_START


def detect_mime(data: bytes, declared: str | None = None) -> str:
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data.startswith(b"PK"):
        return "application/zip"
    return (declared or "application/octet-stream").lower()


def assert_zip_mime(data: bytes, declared: str | None = None) -> None:
    mime = detect_mime(data, declared)
    if mime != "application/zip":
        raise ValueError(f"mime_mismatch:{declared or 'unknown'}->{mime}")


def checkpoint_compatible(previous_snapshot_hash: str, current_snapshot_hash: str) -> bool:
    if not previous_snapshot_hash or not current_snapshot_hash:
        return False
    return previous_snapshot_hash == current_snapshot_hash


def invalidate_checkpoint(previous_snapshot_hash: str, current_snapshot_hash: str) -> str:
    return "keep" if checkpoint_compatible(previous_snapshot_hash, current_snapshot_hash) else "invalidate"


def safe_extract_zip(
    data: bytes,
    *,
    max_members: int = 200,
    max_uncompressed: int = 50_000_000,
    declared_mime: str | None = None,
) -> list[ZipMember]:
    """Extract ZIP members. Zip-slip, bombs, MIME mismatch and traversal fail closed."""
    assert_zip_mime(data, declared_mime)
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"invalid_zip:{exc}") from exc
    names = archive.namelist()
    if len(names) > max_members:
        raise ValueError("zip_bomb_too_many_members")
    total = 0
    members: list[ZipMember] = []
    for info in archive.infolist():
        name = info.filename
        if name.startswith("/") or ".." in name.replace("\\", "/").split("/"):
            raise ValueError(f"zip_slip:{name}")
        total += info.file_size
        if total > max_uncompressed:
            raise ValueError("zip_bomb_uncompressed")
        payload = archive.read(info)
        members.append(ZipMember(name=name, sha256=sha256_bytes(payload), size=len(payload)))
    return members


def reconcile_municipalities(
    found: set[str],
    universe: set[str],
    *,
    scope_complete: bool,
) -> list[MunicipalityVerdict]:
    """Absence is never ZERO without a complete scoped crawl."""
    verdicts: list[MunicipalityVerdict] = []
    for name in sorted(universe):
        if name in found:
            verdicts.append(MunicipalityVerdict(name, "FOUND", "publicacao observada no DOM-SC"))
        elif scope_complete:
            verdicts.append(MunicipalityVerdict(name, "ZERO_CONFIRMED", "escopo completo sem publicação"))
        else:
            verdicts.append(MunicipalityVerdict(name, "SCOPE_INCOMPLETE", "ausência não é zero sem escopo completo"))
    return verdicts


def resource_url(package_name: str, resource_id: str) -> str:
    return urljoin(f"{CKAN_BASE}/dataset/{package_name}/resource/", resource_id)


def discovery_report(
    *,
    resolved: dict[str, Any],
    verdicts: list[MunicipalityVerdict],
    pages: list[PageEvidence],
    previous_snapshot_hash: str | None = None,
    current_snapshot_hash: str | None = None,
) -> dict[str, Any]:
    statuses = {v.status for v in verdicts}
    silent_zero = "ZERO_CONFIRMED" in statuses and not any(v.status == "FOUND" for v in verdicts)
    snapshot = current_snapshot_hash or ""
    return {
        "resolved": resolved,
        "municipalities": [asdict(v) for v in verdicts],
        "pages": [asdict(p) for p in pages],
        "universe": MUNICIPAL_UNIVERSE,
        "sla_hours": SLA_HOURS,
        "silent_zero_forbidden": silent_zero and not resolved.get("ok"),
        "checkpoint": invalidate_checkpoint(previous_snapshot_hash or "", snapshot),
        "generated_at": _utc_now(),
    }
