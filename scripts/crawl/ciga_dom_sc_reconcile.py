"""Reconcile the live CIGA/DOM-SC package against the pinned 295 IBGE ids.

This is a thin consumer of the existing public CKAN discovery and DOM-SC
publication parser.  It emits one FOUND, ZERO_CONFIRMED, or BLOCKED verdict
per municipality and never promotes an incomplete fetch to success.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import logging
import re
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.crawl.ciga_ckan_crawler import REQUEST_DELAY  # noqa: E402
from scripts.crawl.ciga_dom_publications import (  # noqa: E402
    IBGE_CACHE_PATH,
    discover_latest_package,
    iter_zip_json_members,
    list_ingestible_resources,
    parse_json_publications,
)
from scripts.crawl.ciga_public_discovery import (  # noqa: E402
    CKAN_API,
    CKAN_BASE,
    FetchClass,
    HttpFn,
    HttpOutcome,
    PageEvidence,
    UniverseBinding,
    classify_fetch,
    fetch_public,
    ibge_reconcile_report,
    load_pinned_universe,
    lookup_ibge_id,
    page_evidence,
    parse_measured_at,
    reconcile_ibge_universe,
    resolve_package,
    sha256_bytes,
)
from scripts.crawl.security import USER_AGENT, public_get, validate_public_url  # noqa: E402

_logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 90
MAX_RETRIES = 3
RETRY_SLEEP_S = 1.5
CAMPAIGN = "BACKLOG-TRUTH-239"
ALLOWED_CIGA_HOSTS = frozenset({"dados.ciga.sc.gov.br"})
MOP_PARTICIPANT_RE = re.compile(r"^MOP[^-]*-([^-]+)-", re.IGNORECASE)
MOP_MAPPING_METHOD = "mop_participant_single_lexical_match.v1"


def _lexical_key(value: str) -> str:
    """Accent-fold text into explicit lexical tokens (never substring soup)."""
    unescaped = html.unescape(value or "").lower()
    folded = unicodedata.normalize("NFKD", unescaped)
    ascii_text = "".join(char for char in folded if not unicodedata.combining(char))
    ascii_text = re.sub(r"['\u2018\u2019]", "", ascii_text)
    return re.sub(r"[^a-z0-9]+", " ", ascii_text).strip()


def _compact_key(value: str) -> str:
    return _lexical_key(value).replace(" ", "")


class MopParticipantMatcher:
    """Resolve only defensible, non-overlapping names inside one MOP segment."""

    def __init__(self, binding: UniverseBinding) -> None:
        self._names = tuple(
            sorted(
                ((ibge_id, _lexical_key(name), _compact_key(name)) for ibge_id, name in binding.name_by_id.items()),
                key=lambda row: (-len(row[1]), row[1], row[0]),
            )
        )

    def match(self, participant: str) -> tuple[str, set[str], str | None]:
        normalized = _lexical_key(participant)
        compact = normalized.replace(" ", "")
        word_hits: list[tuple[str, int, int]] = []
        for ibge_id, name, _name_compact in self._names:
            for observed in re.finditer(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", normalized):
                word_hits.append((ibge_id, observed.start(), observed.end()))

        # A shorter name occupying the same span is not a second municipality:
        # "Ponte Alta" inside "Ponte Alta do Norte" is discarded. Disjoint
        # names remain separate, so a multi-municipality participant is ambiguous.
        longest_word_ids = {
            ibge_id
            for ibge_id, start, end in word_hits
            if not any(
                other_start <= start and end <= other_end and (other_start < start or end < other_end)
                for _other_id, other_start, other_end in word_hits
            )
        }
        suffix_hits = [
            (ibge_id, len(name_compact))
            for ibge_id, _name, name_compact in self._names
            if name_compact and compact.endswith(name_compact)
        ]
        if suffix_hits:
            suffix_length = max(length for _ibge_id, length in suffix_hits)
            suffix_ids = {ibge_id for ibge_id, length in suffix_hits if length == suffix_length}
        else:
            suffix_ids = set()
        candidates = longest_word_ids | suffix_ids
        if longest_word_ids and suffix_ids:
            method = "word_and_compact_suffix"
        elif longest_word_ids:
            method = "word_only"
        elif suffix_ids:
            method = "compact_suffix_only"
        else:
            method = None
        return normalized, candidates, method


class CoverageAccumulator:
    """Aggregate row-level mapping evidence without retaining source bodies."""

    _BUCKETS = (
        "structured",
        "mop_single_match",
        "structured_unmatched",
        "unmapped_participant",
        "ambiguous_participant",
        "null_non_mop_unclassified",
    )

    def __init__(self, binding: UniverseBinding) -> None:
        self.binding = binding
        self.matcher = MopParticipantMatcher(binding)
        self.found_by_id: dict[str, dict[str, str]] = {}
        self.structured_counts: Counter[str] = Counter()
        self.mop_counts: Counter[str] = Counter()
        self.mop_methods: Counter[str] = Counter()
        self.structured_unmatched: Counter[str] = Counter()
        self.unmapped_participants: Counter[str] = Counter()
        self.ambiguous_participants: Counter[str] = Counter()
        self.ambiguous_candidates: dict[str, set[str]] = {}
        self.null_non_mop_entities: Counter[str] = Counter()
        self.total_rows = 0
        self.null_municipio_rows = 0
        self._hashers = {name: hashlib.sha256() for name in self._BUCKETS}

    def _fingerprint(
        self,
        publication: dict[str, Any],
        *,
        resource_sha256: str,
        member_name: str,
        participant: str | None = None,
        candidates: set[str] | None = None,
    ) -> bytes:
        record = {
            "resource_sha256": resource_sha256,
            "member": member_name,
            "codigo": str(publication.get("codigo") or ""),
            "titulo": str(publication.get("titulo") or ""),
            "data": str(publication.get("data") or ""),
            "entidade": str(publication.get("entidade") or ""),
            "municipio": str(publication.get("municipio") or ""),
            "link": str(publication.get("link") or publication.get("url") or ""),
            "participant": participant,
            "candidates": sorted(candidates or set()),
        }
        return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"

    def _observe(
        self,
        bucket: str,
        publication: dict[str, Any],
        *,
        resource_sha256: str,
        member_name: str,
        participant: str | None = None,
        candidates: set[str] | None = None,
    ) -> None:
        self._hashers[bucket].update(
            self._fingerprint(
                publication,
                resource_sha256=resource_sha256,
                member_name=member_name,
                participant=participant,
                candidates=candidates,
            )
        )

    def collect(
        self,
        publication: dict[str, Any],
        *,
        resource_url: str,
        resource_sha256: str,
        member_name: str,
    ) -> None:
        self.total_rows += 1
        name = str(publication.get("municipio") or "").strip()
        if name:
            ibge_id = lookup_ibge_id(name, self.binding)
            if ibge_id is None:
                normalized_name = _lexical_key(name)
                self.structured_unmatched[normalized_name] += 1
                self._observe(
                    "structured_unmatched",
                    publication,
                    resource_sha256=resource_sha256,
                    member_name=member_name,
                )
                return
            self.structured_counts[ibge_id] += 1
            self.found_by_id[ibge_id] = {"url": resource_url, "sha256": resource_sha256}
            self._observe(
                "structured",
                publication,
                resource_sha256=resource_sha256,
                member_name=member_name,
            )
            return

        self.null_municipio_rows += 1
        title = str(publication.get("titulo") or "")
        observed = MOP_PARTICIPANT_RE.match(title)
        if observed is None:
            entity = _lexical_key(str(publication.get("entidade") or "")) or "<empty>"
            self.null_non_mop_entities[entity] += 1
            self._observe(
                "null_non_mop_unclassified",
                publication,
                resource_sha256=resource_sha256,
                member_name=member_name,
            )
            return

        participant, candidates, method = self.matcher.match(observed.group(1))
        if len(candidates) == 1:
            ibge_id = next(iter(candidates))
            self.mop_counts[ibge_id] += 1
            if method:
                self.mop_methods[method] += 1
            self.found_by_id[ibge_id] = {"url": resource_url, "sha256": resource_sha256}
            self._observe(
                "mop_single_match",
                publication,
                resource_sha256=resource_sha256,
                member_name=member_name,
                participant=participant,
                candidates=candidates,
            )
        elif candidates:
            self.ambiguous_participants[participant] += 1
            self.ambiguous_candidates.setdefault(participant, set()).update(candidates)
            self._observe(
                "ambiguous_participant",
                publication,
                resource_sha256=resource_sha256,
                member_name=member_name,
                participant=participant,
                candidates=candidates,
            )
        else:
            self.unmapped_participants[participant] += 1
            self._observe(
                "unmapped_participant",
                publication,
                resource_sha256=resource_sha256,
                member_name=member_name,
                participant=participant,
            )

    def _bucket(self, rows: int, **extra: Any) -> dict[str, Any]:
        return {"rows": rows, **extra}

    def report(self) -> dict[str, Any]:
        found_ids = set(self.found_by_id)
        missing = sorted(set(self.binding.ibge_ids) - found_ids)
        unresolved_rows = (
            sum(self.structured_unmatched.values())
            + sum(self.unmapped_participants.values())
            + sum(self.ambiguous_participants.values())
            + sum(self.null_non_mop_entities.values())
        )
        evidence = []
        for ibge_id in sorted(found_ids):
            methods = []
            if self.structured_counts[ibge_id]:
                methods.append("structured_municipio")
            if self.mop_counts[ibge_id]:
                methods.append(MOP_MAPPING_METHOD)
            evidence.append(
                {
                    "ibge_id": ibge_id,
                    "name": self.binding.name_by_id[ibge_id],
                    "structured_rows": self.structured_counts[ibge_id],
                    "mop_single_match_rows": self.mop_counts[ibge_id],
                    "methods": methods,
                }
            )
        buckets = {
            "structured": self._bucket(
                sum(self.structured_counts.values()),
                unique_municipalities=len(self.structured_counts),
                sha256=self._hashers["structured"].hexdigest(),
            ),
            "mop_single_match": self._bucket(
                sum(self.mop_counts.values()),
                unique_municipalities=len(self.mop_counts),
                match_methods=dict(sorted(self.mop_methods.items())),
                sha256=self._hashers["mop_single_match"].hexdigest(),
            ),
            "structured_unmatched": self._bucket(
                sum(self.structured_unmatched.values()),
                distinct_names=len(self.structured_unmatched),
                names=[{"name": name, "rows": rows} for name, rows in sorted(self.structured_unmatched.items())],
                sha256=self._hashers["structured_unmatched"].hexdigest(),
            ),
            "unmapped_participant": self._bucket(
                sum(self.unmapped_participants.values()),
                distinct_segments=len(self.unmapped_participants),
                segments=[
                    {"participant": segment, "rows": rows}
                    for segment, rows in sorted(self.unmapped_participants.items())
                ],
                sha256=self._hashers["unmapped_participant"].hexdigest(),
            ),
            "ambiguous_participant": self._bucket(
                sum(self.ambiguous_participants.values()),
                distinct_segments=len(self.ambiguous_participants),
                segments=[
                    {
                        "participant": segment,
                        "rows": rows,
                        "candidates": [
                            {"ibge_id": ibge_id, "name": self.binding.name_by_id[ibge_id]}
                            for ibge_id in sorted(self.ambiguous_candidates[segment])
                        ],
                    }
                    for segment, rows in sorted(self.ambiguous_participants.items())
                ],
                sha256=self._hashers["ambiguous_participant"].hexdigest(),
            ),
            "null_non_mop_unclassified": self._bucket(
                sum(self.null_non_mop_entities.values()),
                distinct_entities=len(self.null_non_mop_entities),
                entities=[
                    {"entity": entity, "rows": rows} for entity, rows in sorted(self.null_non_mop_entities.items())
                ],
                sha256=self._hashers["null_non_mop_unclassified"].hexdigest(),
            ),
        }
        bucket_hash = sha256_bytes(
            json.dumps(buckets, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        return {
            "method": MOP_MAPPING_METHOD,
            "total_rows": self.total_rows,
            "null_municipio_rows": self.null_municipio_rows,
            "mapping_complete": unresolved_rows == 0,
            "unresolved_rows": unresolved_rows,
            "municipal_coverage_complete": not missing,
            "municipalities_covered": len(found_ids),
            "municipalities_missing": [
                {"ibge_id": ibge_id, "name": self.binding.name_by_id[ibge_id]} for ibge_id in missing
            ],
            "buckets_sha256": bucket_hash,
            "buckets": buckets,
            "municipality_evidence": evidence,
        }


def _iso_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def live_http(url: str, timeout: int = HTTP_TIMEOUT) -> tuple[int, bytes, str]:
    """Read an official CIGA HTTPS endpoint and preserve the observed time."""
    fetched_at = _iso_now()
    try:
        validate_public_url(url, resolve_dns=False)
        hostname = (urlsplit(url).hostname or "").lower().rstrip(".")
        if hostname not in ALLOWED_CIGA_HOSTS:
            raise ValueError(f"CIGA host not allowlisted: {hostname or 'missing'}")
        with requests.Session() as session:
            response = public_get(
                session,
                url,
                timeout=timeout,
                max_redirects=0,
                headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            )
        return int(response.status_code), bytes(response.content), fetched_at
    except (requests.RequestException, ValueError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"network_blocked:{type(exc).__name__}:{exc}") from exc


def _fetch_with_retry(url: str, http: HttpFn) -> tuple[HttpOutcome, FetchClass]:
    last: tuple[HttpOutcome, FetchClass] | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        outcome = fetch_public(url, http)
        classified = classify_fetch(outcome.status, outcome.body)
        last = (outcome, classified)
        if classified.access_block or classified.drift_alert or not classified.retryable:
            return last
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_SLEEP_S * attempt)
    if last is None:  # pragma: no cover - MAX_RETRIES is a positive constant
        raise RuntimeError("retry_loop_did_not_run")
    return last


def _parse_package(body: bytes) -> dict[str, Any] | None:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    result = payload.get("result") if payload.get("success") else payload
    return result if isinstance(result, dict) else None


def _collect_publications(
    raw: bytes,
    *,
    kind: str,
    coverage: CoverageAccumulator,
    resource_url: str,
    resource_sha256: str,
) -> None:
    if kind == "zip" or raw.startswith(b"PK"):
        members = list(iter_zip_json_members(raw))
        if not members:
            raise ValueError("archive_without_publication_members")
        payloads = members
    elif kind == "json":
        payloads = [("<resource.json>", raw)]
    else:
        raise ValueError(f"unsupported_membership_resource:{kind}")

    for member_name, payload in payloads:
        try:
            decoded = json.loads(payload.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid_publication_json:{exc}") from exc
        if isinstance(decoded, list):
            valid_shape = all(isinstance(item, dict) for item in decoded)
        elif isinstance(decoded, dict) and decoded.get("autopublicacoes") is None:
            # CIGA emits this exact empty-period shape in otherwise valid
            # resources (for example {"autopublicacoes": null, ...}).
            valid_shape = "autopublicacoes" in decoded
        elif isinstance(decoded, dict) and "autopublicacoes" in decoded:
            publications = decoded["autopublicacoes"]
            valid_shape = isinstance(publications, list) and all(isinstance(item, dict) for item in publications)
        else:
            valid_shape = isinstance(decoded, dict) and any(
                key in decoded for key in ("codigo", "titulo", "municipio", "entidade")
            )
        if not valid_shape:
            raise ValueError("unrecognized_publication_schema")
        for publication in parse_json_publications(payload):
            coverage.collect(
                publication,
                resource_url=resource_url,
                resource_sha256=resource_sha256,
                member_name=member_name,
            )


def _blocked_report(
    *,
    binding: UniverseBinding,
    reason: str,
    resolved: dict[str, Any],
    pages: list[PageEvidence],
    measured_at: str,
    now: str,
) -> dict[str, Any]:
    verdicts = reconcile_ibge_universe(
        binding,
        found_ids=set(),
        scope_exhausted=False,
        access_block=reason,
        measured_at=measured_at,
        now=now,
        resolved_ok=False,
    )
    report = ibge_reconcile_report(
        binding=binding,
        resolved={**resolved, "ok": False, "blocker": reason},
        verdicts=verdicts,
        pages=pages,
        scope_exhausted=False,
        measured_at=measured_at,
        now=now,
    )
    report["campaign"] = CAMPAIGN
    return report


def run_reconcile(
    *,
    universe_path: Path = IBGE_CACHE_PATH,
    http: HttpFn | None = None,
    package_id: str | None = None,
    package_ids: list[str] | None = None,
    max_resources: int | None = None,
    previous_snapshot_hash: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Fetch and reconcile a monthly DOM-SC package without persistence."""
    clock = now or _iso_now()
    http = http or live_http
    binding = load_pinned_universe(universe_path)
    pages: list[PageEvidence] = []

    try:
        latest = package_id or discover_latest_package(package_ids=package_ids)
    except RuntimeError as exc:
        return _blocked_report(
            binding=binding,
            reason=f"network:{exc}",
            resolved={"via": "discover"},
            pages=pages,
            measured_at=clock,
            now=clock,
        )
    if not latest:
        return _blocked_report(
            binding=binding,
            reason="no_domsc_package",
            resolved={"via": "discover"},
            pages=pages,
            measured_at=clock,
            now=clock,
        )

    try:
        resolved = resolve_package(latest, http=http)
    except RuntimeError as exc:
        resolved = {"ok": False, "via": "show", "blocker": f"network:{exc}"}
    slug = str(resolved.get("slug") or latest)
    package_url = f"{CKAN_API}/package_show?id={slug}"
    try:
        package_outcome, package_class = _fetch_with_retry(package_url, http)
    except RuntimeError as exc:
        return _blocked_report(
            binding=binding,
            reason=f"network:{exc}",
            resolved=resolved,
            pages=pages,
            measured_at=clock,
            now=clock,
        )

    pages.append(page_evidence(package_outcome, raw_uri=f"ckan://package_show/{slug}"))
    fetched_at = package_outcome.fetched_at or clock
    if package_class.access_block:
        return _blocked_report(
            binding=binding,
            reason=package_class.access_block,
            resolved=resolved,
            pages=pages,
            measured_at=fetched_at,
            now=clock,
        )
    if not resolved.get("ok") or package_outcome.status != 200:
        reason = (
            "drift" if package_class.drift_alert or resolved.get("drift_alert") else f"http_{package_outcome.status}"
        )
        return _blocked_report(
            binding=binding,
            reason=reason,
            resolved=resolved,
            pages=pages,
            measured_at=fetched_at,
            now=clock,
        )

    package = _parse_package(package_outcome.body)
    if package is None:
        return _blocked_report(
            binding=binding,
            reason="package_parse",
            resolved=resolved,
            pages=pages,
            measured_at=fetched_at,
            now=clock,
        )

    resources = list_ingestible_resources(package)
    selected = resources if max_resources is None else resources[: max(max_resources, 0)]
    truncated = len(selected) != len(resources)
    coverage = CoverageAccumulator(binding)
    resource_hashes: list[str] = []
    resource_records: list[dict[str, Any]] = []
    resource_measured_at: str | None = None
    blocker: str | None = None

    if not resources:
        blocker = "no_ingestible_resources"
    for index, resource in enumerate(selected):
        if index:
            time.sleep(REQUEST_DELAY)
        url = str(resource.get("url") or "")
        resource_id = str(resource.get("id") or "")
        kind = str(resource.get("kind") or "other")
        last_modified = str(resource.get("last_modified") or "") or None
        if last_modified:
            if resource_measured_at is None or parse_measured_at(last_modified) > parse_measured_at(
                resource_measured_at
            ):
                resource_measured_at = last_modified
        try:
            outcome, classified = _fetch_with_retry(url, http)
        except RuntimeError as exc:
            blocker = f"network:{exc}"
            resource_records.append({"id": resource_id, "url": url, "status": "FAILED", "error": str(exc)})
            break

        digest = sha256_bytes(outcome.body)
        pages.append(page_evidence(outcome, raw_uri=url))
        resource_records.append(
            {
                "id": resource_id,
                "url": url,
                "status": outcome.status,
                "sha256": digest,
                "fetched_at": outcome.fetched_at,
                "last_modified": last_modified,
                "kind": kind,
            }
        )
        if classified.access_block:
            blocker = classified.access_block
            break
        if classified.drift_alert or outcome.status != 200:
            blocker = "drift" if classified.drift_alert else f"http_{outcome.status}"
            break
        resource_hashes.append(digest)
        try:
            _collect_publications(
                outcome.body,
                kind=kind,
                coverage=coverage,
                resource_url=url,
                resource_sha256=digest,
            )
        except ValueError as exc:
            blocker = f"archive_or_parse:{exc}"
            resource_records[-1]["status"] = "FAILED"
            resource_records[-1]["error"] = str(exc)
            break

    if truncated:
        blocker = blocker or "scope_incomplete"
    source_scope_exhausted = bool(resources) and not truncated and blocker is None and len(selected) == len(resources)
    coverage_report = coverage.report()
    unmatched_names = sorted(coverage.structured_unmatched)
    if unmatched_names:
        # An observed publication that cannot be bound to the pinned IBGE
        # universe makes absence unknowable for every municipality.  Keeping
        # FOUND while manufacturing ZERO_CONFIRMED for the rest would turn an
        # identity-resolution defect into a factual negative.
        blocker = blocker or "unmatched_municipality_binding"
    if (
        source_scope_exhausted
        and not coverage_report["mapping_complete"]
        and not coverage_report["municipal_coverage_complete"]
    ):
        # Unresolved null-municipality rows do not erase positive evidence,
        # but they make any remaining absence unknowable.
        blocker = blocker or "publication_mapping_incomplete"
    completed_at = now or _iso_now()
    measured_at = resource_measured_at or fetched_at
    snapshot_hash = sha256_bytes("".join(resource_hashes).encode("utf-8")) if resource_hashes else None
    verdicts = reconcile_ibge_universe(
        binding,
        found_ids=set(coverage.found_by_id),
        scope_exhausted=source_scope_exhausted,
        access_block=blocker,
        evidence_by_id=coverage.found_by_id,
        measured_at=measured_at,
        now=completed_at,
        resolved_ok=True,
    )
    report = ibge_reconcile_report(
        binding=binding,
        resolved={
            **resolved,
            "slug": slug,
            "package_url": package_url,
            "ckan_base": CKAN_BASE,
            "resources_available": len(resources),
            "resources_selected": len(selected),
            "truncated": truncated,
        },
        verdicts=verdicts,
        pages=pages,
        previous_snapshot_hash=previous_snapshot_hash,
        current_snapshot_hash=snapshot_hash,
        unmatched_names=unmatched_names,
        scope_exhausted=source_scope_exhausted,
        measured_at=measured_at,
        now=completed_at,
    )
    report.update(
        {
            "campaign": CAMPAIGN,
            "resources": resource_records,
            "fetched_at": fetched_at,
            "completed_at": completed_at,
            "resource_last_modified": resource_measured_at,
            "coverage": coverage_report,
            "blocker": blocker,
        }
    )
    return report


def _is_complete(report: dict[str, Any]) -> bool:
    by_status = report.get("by_status") or {}
    return bool(
        report.get("scope_exhausted")
        and report.get("set_equality", {}).get("ok")
        and not report.get("illegal_states")
        and not report.get("silent_zero")
        and int(by_status.get("BLOCKED", 0)) == 0
        and int(by_status.get("FOUND", 0)) + int(by_status.get("ZERO_CONFIRMED", 0)) == int(report.get("universe", 0))
    )


def write_report(report: dict[str, Any], path: Path) -> tuple[Path, str]:
    payload = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path, sha256_bytes(payload)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="python3 -m scripts.crawl.ciga_dom_sc_reconcile")
    parser.add_argument("--out", required=True, help="Reconciliation JSON path")
    parser.add_argument("--package-id", default=None, help="Override auto-discovered monthly package")
    parser.add_argument("--max-resources", type=int, default=None, help="Smoke only; forces BLOCKED remainder")
    parser.add_argument("--universe", default=str(IBGE_CACHE_PATH))
    parser.add_argument("--previous-snapshot-hash", default=None)
    args = parser.parse_args(argv)

    try:
        report = run_reconcile(
            universe_path=Path(args.universe),
            package_id=args.package_id,
            max_resources=args.max_resources,
            previous_snapshot_hash=args.previous_snapshot_hash,
        )
    except Exception as exc:  # noqa: BLE001 - CLI emits a reproducible fatal proof
        _logger.exception("reconciliation failed")
        report = {
            "campaign": CAMPAIGN,
            "decision": "FAILED",
            "blocker": str(exc),
            "prerequisite": "reachable_ciga_host_and_valid_pinned_universe",
        }

    path, report_sha256 = write_report(report, Path(args.out))
    coverage = report.get("coverage") or {}
    buckets = coverage.get("buckets") or {}
    summary = {
        "ok": _is_complete(report),
        "campaign": CAMPAIGN,
        "binding": report.get("binding"),
        "package": (report.get("resolved") or {}).get("slug"),
        "universe": report.get("universe"),
        "by_status": report.get("by_status"),
        "set_equality": report.get("set_equality"),
        "scope_exhausted": report.get("scope_exhausted"),
        "freshness_hours": report.get("freshness_hours"),
        "freshness": report.get("freshness"),
        "measured_at": report.get("measured_at"),
        "completed_at": report.get("completed_at"),
        "checkpoint": report.get("checkpoint"),
        "snapshot_sha256": report.get("snapshot_sha256"),
        "coverage": {
            "method": coverage.get("method"),
            "mapping_complete": coverage.get("mapping_complete"),
            "municipal_coverage_complete": coverage.get("municipal_coverage_complete"),
            "municipalities_covered": coverage.get("municipalities_covered"),
            "structured": (buckets.get("structured") or {}).get("rows"),
            "mop_single_match": (buckets.get("mop_single_match") or {}).get("rows"),
            "unmapped_participant": (buckets.get("unmapped_participant") or {}).get("rows"),
            "ambiguous_participant": (buckets.get("ambiguous_participant") or {}).get("rows"),
            "null_non_mop_unclassified": (buckets.get("null_non_mop_unclassified") or {}).get("rows"),
            "buckets_sha256": coverage.get("buckets_sha256"),
        },
        "report_sha256": report_sha256,
        "path": str(path),
    }
    sys.stdout.write(json.dumps(summary, ensure_ascii=False) + "\n")
    return 0 if summary["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
