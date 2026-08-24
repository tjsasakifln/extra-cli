"""Public CIGA/DOM-SC discovery that survives slug drift.

package_list 404 is a drift alert, never a silent municipal zero.
429/5xx are retryable. ZIP members are extracted with zip-slip protection.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

CKAN_BASE = "https://dados.ciga.sc.gov.br"
CKAN_API = f"{CKAN_BASE}/api/3/action"
MUNICIPAL_UNIVERSE = 295
PERIOD_START = "2025-01-01"
SLA_HOURS = 24
NOMINAL_STATES = frozenset({"FOUND", "ZERO_CONFIRMED", "BLOCKED"})
ACCESS_BLOCK_STATUSES = frozenset({401, 403})
IBGE_SC_ID_RE = re.compile(r"^42\d{5}$")
BINDING_SOURCE = "data/ibge_cache.json"
CAPTCHA_MARKERS = ("captcha", "recaptcha", "hcaptcha", "cf-turnstile", "cf-challenge")
LOGIN_FORM_MARKERS = ('type="password"', "type='password'", 'name="password"', "name='password'")

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


@dataclass(frozen=True)
class UniverseBinding:
    source: str
    version: str
    sha256: str
    count: int
    ibge_ids: tuple[str, ...]
    name_by_id: dict[str, str]
    id_by_name: dict[str, str]


@dataclass(frozen=True)
class FetchClass:
    retryable: bool
    drift_alert: bool
    access_block: str | None


@dataclass(frozen=True)
class IbgeMunicipalityVerdict:
    ibge_id: str
    name: str
    status: str
    evidence: str
    sha256: str | None = None
    url: str | None = None
    freshness_hours: float | None = None
    freshness: str | None = None
    next_recheck: str | None = None
    blocker: str | None = None
    prerequisite: str | None = None
    next_command: str | None = None


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


def _muni_key(name: str) -> str:
    import unicodedata

    folded = unicodedata.normalize("NFKD", (name or "").strip().lower())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", folded).strip()


def _compact_key(name: str) -> str:
    """Return an accent-folded key without spaces or punctuation."""
    return re.sub(r"[^a-z0-9]", "", _muni_key(name))


def pin_municipal_universe(
    mapping: Mapping[str, Any],
    *,
    source_bytes: bytes,
    source: str = BINDING_SOURCE,
) -> UniverseBinding:
    """Bind reconciliation to exactly 295 unique Santa Catarina IBGE ids."""
    name_by_id: dict[str, str] = {}
    id_by_name: dict[str, str] = {}
    ibge_ids: list[str] = []
    for raw_name, raw_id in mapping.items():
        name = _muni_key(str(raw_name))
        ibge_id = str(raw_id).strip()
        if not name:
            raise ValueError("empty_municipality_name")
        if not IBGE_SC_ID_RE.fullmatch(ibge_id):
            raise ValueError(f"invalid_ibge_id:{ibge_id}")
        if ibge_id in name_by_id:
            raise ValueError(f"duplicate_ibge_id:{ibge_id}")
        if name in id_by_name:
            raise ValueError(f"duplicate_municipality_name:{name}")
        name_by_id[ibge_id] = name
        id_by_name[name] = ibge_id
        compact = _compact_key(name)
        if compact and compact != name:
            existing = id_by_name.get(compact)
            if existing and existing != ibge_id:
                raise ValueError(f"duplicate_compact_name:{compact}")
            id_by_name[compact] = ibge_id
        ibge_ids.append(ibge_id)
    if len(ibge_ids) != MUNICIPAL_UNIVERSE:
        raise ValueError(f"universe_size:{len(ibge_ids)}!={MUNICIPAL_UNIVERSE}")
    digest = sha256_bytes(source_bytes)
    return UniverseBinding(
        source=source,
        version=f"ibge_cache:{digest[:16]}",
        sha256=digest,
        count=len(ibge_ids),
        ibge_ids=tuple(sorted(ibge_ids)),
        name_by_id=name_by_id,
        id_by_name=id_by_name,
    )


def load_pinned_universe(path: Path | None = None) -> UniverseBinding:
    target = path or Path(BINDING_SOURCE)
    payload = target.read_bytes()
    mapping = json.loads(payload.decode("utf-8"))
    if not isinstance(mapping, dict):
        raise ValueError(f"universe_not_object:{target}")
    try:
        source = str(target.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        source = BINDING_SOURCE if target.name == Path(BINDING_SOURCE).name else target.name
    return pin_municipal_universe(mapping, source_bytes=payload, source=source)


def classify_access_barrier(status: int, body: bytes = b"") -> str | None:
    """Map an access barrier to a nominal BLOCKED reason."""
    if status in ACCESS_BLOCK_STATUSES:
        return f"http_{status}"
    sample = body[:12_000].decode("utf-8", errors="replace").lower()
    if any(marker in sample for marker in CAPTCHA_MARKERS):
        return "captcha"
    looks_html = "<html" in sample or "<form" in sample
    if looks_html and any(marker in sample for marker in LOGIN_FORM_MARKERS):
        return "login"
    return None


def classify_fetch(status: int, body: bytes = b"") -> FetchClass:
    access = classify_access_barrier(status, body)
    if access:
        return FetchClass(retryable=False, drift_alert=False, access_block=access)
    retryable, drift = classify_http(status)
    return FetchClass(retryable=retryable, drift_alert=drift, access_block=None)


def parse_measured_at(value: str) -> datetime:
    text = (value or "").strip()
    if not text:
        raise ValueError("empty_timestamp")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def freshness_age_hours(*, measured_at: str, now: str) -> float:
    """Measure age from an observed fetch/resource timestamp."""
    delta = parse_measured_at(now) - parse_measured_at(measured_at)
    return delta.total_seconds() / 3600.0


def freshness_status(age_hours: float, sla_hours: float = SLA_HOURS) -> str:
    if age_hours < 0:
        return "stale"
    return "fresh" if age_hours <= sla_hours else "stale"


def next_recheck_at(*, measured_at: str, sla_hours: int = SLA_HOURS) -> str:
    when = parse_measured_at(measured_at) + timedelta(hours=sla_hours)
    return when.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def lookup_ibge_id(name: str, binding: UniverseBinding) -> str | None:
    found = binding.id_by_name.get(_muni_key(name))
    if found:
        return found
    compact = _compact_key(name)
    return binding.id_by_name.get(compact) if compact else None


def refuse_zero_without_exhaustion(*, scope_exhausted: bool, access_block: str | None) -> bool:
    """Allow ZERO_CONFIRMED only after full exhaustion without a barrier."""
    return bool(scope_exhausted) and not access_block


def set_equality(universe_ids: set[str], emitted_ids: set[str]) -> dict[str, Any]:
    missing = sorted(universe_ids - emitted_ids)
    extra = sorted(emitted_ids - universe_ids)
    return {
        "ok": not missing and not extra,
        "universe_count": len(universe_ids),
        "emitted_count": len(emitted_ids),
        "missing": missing,
        "extra": extra,
    }


def _blocked_fields(reason: str) -> tuple[str, str, str]:
    runner = "python3 -m scripts.crawl.ciga_dom_sc_reconcile --out /tmp/ciga-dom-sc-reconcile.json"
    if reason.startswith("http_"):
        return reason, f"public_read_after_{reason}", runner
    if reason == "captcha":
        return reason, "human_solve_or_alternate_public_path", runner
    if reason == "login":
        return reason, "public_unauthenticated_path", runner
    if reason == "drift":
        return (
            reason,
            "resolve_current_domsc_slug",
            "python3 -m scripts.crawl.discover_ciga_packages --list-domsc-months",
        )
    if reason == "scope_incomplete":
        return reason, "exhaust_all_ingestible_resources_of_pinned_package", runner
    return reason, f"clear_{reason}", runner


def reconcile_ibge_universe(
    binding: UniverseBinding,
    *,
    found_ids: set[str],
    scope_exhausted: bool,
    access_block: str | None = None,
    evidence_by_id: Mapping[str, Mapping[str, Any]] | None = None,
    measured_at: str,
    now: str,
    resolved_ok: bool,
) -> list[IbgeMunicipalityVerdict]:
    """Emit exactly one nominal verdict for every pinned IBGE id."""
    extras = found_ids - set(binding.ibge_ids)
    if extras:
        raise ValueError(f"extra_ibge_ids:{sorted(extras)}")
    allow_zero = (
        refuse_zero_without_exhaustion(scope_exhausted=scope_exhausted, access_block=access_block) and resolved_ok
    )
    age = freshness_age_hours(measured_at=measured_at, now=now)
    freshness = freshness_status(age)
    recheck = next_recheck_at(measured_at=measured_at)
    by_evidence = evidence_by_id or {}
    verdicts: list[IbgeMunicipalityVerdict] = []
    for ibge_id in binding.ibge_ids:
        evidence = by_evidence.get(ibge_id, {})
        url = evidence.get("url")
        digest = evidence.get("sha256")
        common = {
            "ibge_id": ibge_id,
            "name": binding.name_by_id[ibge_id],
            "sha256": digest if isinstance(digest, str) else None,
            "url": url if isinstance(url, str) else None,
            "freshness_hours": age,
            "freshness": freshness,
            "next_recheck": recheck,
        }
        if ibge_id in found_ids:
            verdicts.append(
                IbgeMunicipalityVerdict(
                    **common,
                    status="FOUND",
                    evidence="publicacao observada no pacote CIGA/DOM-SC",
                )
            )
        elif access_block:
            reason, prerequisite, next_command = _blocked_fields(access_block)
            verdicts.append(
                IbgeMunicipalityVerdict(
                    **common,
                    status="BLOCKED",
                    evidence=f"access_barrier:{reason}",
                    blocker=reason,
                    prerequisite=prerequisite,
                    next_command=next_command,
                )
            )
        elif allow_zero:
            verdicts.append(
                IbgeMunicipalityVerdict(
                    **common,
                    status="ZERO_CONFIRMED",
                    evidence="escopo exaurido sem publicacao no periodo",
                )
            )
        else:
            reason, prerequisite, next_command = _blocked_fields("scope_incomplete" if resolved_ok else "unresolved")
            verdicts.append(
                IbgeMunicipalityVerdict(
                    **common,
                    status="BLOCKED",
                    evidence="ausencia nao e zero sem exaustao ou resolucao",
                    blocker=reason,
                    prerequisite=prerequisite,
                    next_command=next_command,
                )
            )
    return verdicts


def ibge_reconcile_report(
    *,
    binding: UniverseBinding,
    resolved: dict[str, Any],
    verdicts: list[IbgeMunicipalityVerdict],
    pages: list[PageEvidence],
    previous_snapshot_hash: str | None = None,
    current_snapshot_hash: str | None = None,
    unmatched_names: list[str] | None = None,
    scope_exhausted: bool,
    measured_at: str,
    now: str,
) -> dict[str, Any]:
    equality = set_equality(set(binding.ibge_ids), {verdict.ibge_id for verdict in verdicts})
    statuses = {verdict.status for verdict in verdicts}
    illegal = sorted(statuses - NOMINAL_STATES)
    silent_zero = any(verdict.status == "ZERO_CONFIRMED" for verdict in verdicts) and not resolved.get("ok")
    by_status = {state: 0 for state in sorted(NOMINAL_STATES)}
    for verdict in verdicts:
        by_status[verdict.status] = by_status.get(verdict.status, 0) + 1
    age = freshness_age_hours(measured_at=measured_at, now=now)
    return {
        "binding": {
            "source": binding.source,
            "version": binding.version,
            "sha256": binding.sha256,
            "count": binding.count,
        },
        "resolved": resolved,
        "municipalities": [asdict(verdict) for verdict in verdicts],
        "pages": [asdict(page) for page in pages],
        "set_equality": equality,
        "by_status": by_status,
        "universe": binding.count,
        "sla_hours": SLA_HOURS,
        "scope_exhausted": scope_exhausted,
        "measured_at": measured_at,
        "freshness_hours": age,
        "freshness": freshness_status(age),
        "silent_zero": silent_zero,
        "silent_zero_forbidden": silent_zero,
        "illegal_states": illegal,
        "unmatched_names": sorted(set(unmatched_names or [])),
        "checkpoint": invalidate_checkpoint(previous_snapshot_hash or "", current_snapshot_hash or ""),
        "snapshot_sha256": current_snapshot_hash,
        "generated_at": now,
    }
