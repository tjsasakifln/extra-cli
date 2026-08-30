"""Resumable national publishing-org census built on the existing PNCP spine.

The PNCP catalog is fetched once. Existing source-wide date-window checkpoints
describe the aggregate corpus window; this module never fans out one HTTP
request per catalog organization. Aggregate completion is not entity-scoped
negative evidence, so a missing organization remains ``BLOCKED``.

Raw catalogs, corpus snapshots, and reconciliation checkpoints are operational
artifacts and must remain outside git. Compact hashes/summaries may be checked
in according to ADR-020.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, BinaryIO

from scripts.crawl.resilience.circuit_breaker import PersistentCircuitBreaker
from scripts.crawl.resilience.http_policy import HttpResiliencePolicy
from scripts.national_contract_truth.live_universe import PNCP_ORGAOS, USER_AGENT
from scripts.national_coverage.evaluate import evaluate_from_dict
from scripts.national_coverage.hashing import digest
from scripts.national_coverage.models import CORE_METHOD_VERSION, NationalCoverageError, PublishingOrg
from scripts.national_coverage.policy import normalize_org_id
from scripts.national_coverage.universe import build_official_universe

CENSUS_SCHEMA = "national-census-operation/1.0"
CATALOG_SCHEMA = "national-census-catalog/1.1"
CORPUS_SCHEMA = "national-census-corpus/1.0"
WINDOW_SCHEMA = "national-census-window-evidence/1.0"
CHECKPOINT_SCHEMA = "national-census-checkpoint/1.1"
MAX_CATALOG_BYTES = 128 * 1024 * 1024
DEFAULT_BATCH_SIZE = 5_000
TERMINAL_STATUSES = ("FOUND", "ZERO_CONFIRMED", "BLOCKED", "FAILED")
_WINDOW_KEY = re.compile(r"^(\d{8})_(\d{8})$")


class CensusOperationError(NationalCoverageError):
    """An input or checkpoint cannot safely support census reconciliation."""


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary_path.unlink(missing_ok=True)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    raw = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _atomic_write(path, raw)


def _load_object(path: Path) -> dict[str, Any]:
    payload, _ = _load_object_with_raw(path)
    return payload


def _load_object_with_raw(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CensusOperationError(f"invalid_json:{path.name}:{type(exc).__name__}") from exc
    if not isinstance(payload, dict):
        raise CensusOperationError(f"json_object_required:{path.name}")
    return payload, raw


def _parse_day(value: str) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise CensusOperationError(f"invalid_date:{value}") from exc


def _window_days(key: str) -> set[date]:
    matched = _WINDOW_KEY.fullmatch(str(key))
    if not matched:
        raise CensusOperationError(f"invalid_window_key:{key}")
    start = datetime.strptime(matched.group(1), "%Y%m%d").date()
    end = datetime.strptime(matched.group(2), "%Y%m%d").date()
    if end < start:
        raise CensusOperationError(f"inverted_window_key:{key}")
    return {start + timedelta(days=offset) for offset in range((end - start).days + 1)}


def _current_failed_windows(checkpoint: dict[str, Any]) -> set[str]:
    completed = {str(item) for item in checkpoint.get("completed_windows") or []}
    failed = {str(item) for item in checkpoint.get("failed_windows") or []}
    for item in checkpoint.get("windows") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("window_key") or item.get("key") or "")
        if key and str(item.get("status") or "").lower() == "failed":
            failed.add(key)
    results = checkpoint.get("window_results") or {}
    if isinstance(results, dict):
        for key, item in results.items():
            if isinstance(item, dict) and str(item.get("terminal") or "").upper() == "FAILED":
                failed.add(str(key))
    return failed - completed


def _current_blocked_windows(checkpoint: dict[str, Any]) -> set[str]:
    completed = {str(item) for item in checkpoint.get("completed_windows") or []}
    blocked = {str(item) for item in checkpoint.get("blocked_windows") or []}
    return blocked - completed


def build_window_evidence(
    checkpoint_paths: Iterable[Path],
    *,
    period_start: str,
    period_end_exclusive: str,
) -> dict[str, Any]:
    """Union existing crawler checkpoints into a day-exact source proof."""
    start = _parse_day(period_start)
    end = _parse_day(period_end_exclusive)
    if end <= start:
        raise CensusOperationError("period_end_exclusive_must_follow_start")
    expected_days = {start + timedelta(days=offset) for offset in range((end - start).days)}
    completed_days: set[date] = set()
    failed_days: set[date] = set()
    blocked_days: set[date] = set()
    artifacts: list[dict[str, Any]] = []
    for path in checkpoint_paths:
        payload, raw = _load_object_with_raw(path)
        source = str(payload.get("source") or "")
        if source != "pncp_contracts":
            raise CensusOperationError(f"unexpected_checkpoint_source:{path.name}:{source or 'missing'}")
        meta = payload.get("meta") or {}
        if not isinstance(meta, dict):
            raise CensusOperationError(f"checkpoint_meta_invalid:{path.name}")
        capability = str(meta.get("capability") or "historical_contracts")
        if capability != "historical_contracts":
            raise CensusOperationError(f"checkpoint_capability_mismatch:{path.name}:{capability}")
        query_kind = str(meta.get("query_kind") or "")
        logical_job_id = str(meta.get("logical_job_id") or "")
        mode = str(payload.get("mode") or "")
        if query_kind != "publication":
            raise CensusOperationError(f"checkpoint_query_kind_mismatch:{path.name}:{query_kind or 'missing'}")
        completed = sorted({str(item) for item in payload.get("completed_windows") or []})
        failed = sorted(_current_failed_windows(payload))
        blocked = sorted(_current_blocked_windows(payload))
        completed_in_scope: list[str] = []
        failed_in_scope: list[str] = []
        blocked_in_scope: list[str] = []
        for key in completed:
            overlap = _window_days(key) & expected_days
            if overlap:
                completed_days.update(overlap)
                completed_in_scope.append(key)
        for key in failed:
            overlap = _window_days(key) & expected_days
            if overlap:
                failed_days.update(overlap)
                failed_in_scope.append(key)
        for key in blocked:
            overlap = _window_days(key) & expected_days
            if overlap:
                blocked_days.update(overlap)
                blocked_in_scope.append(key)
        artifacts.append(
            {
                "sha256": sha256_bytes(raw),
                "source": source,
                "mode": mode,
                "capability": capability,
                "query_kind": query_kind,
                "logical_job_id": logical_job_id or None,
                "updated_at": payload.get("updated_at"),
                "completed_windows_in_scope": completed_in_scope,
                "failed_windows_in_scope": failed_in_scope,
                "blocked_windows_in_scope": blocked_in_scope,
            }
        )
    uncovered = expected_days - completed_days
    current_failed = uncovered & failed_days
    current_blocked = (uncovered & blocked_days) - current_failed
    never_ran = uncovered - current_failed - current_blocked
    reason_codes: list[str] = []
    if current_failed:
        reason_codes.append("source_windows_failed")
    if current_blocked:
        reason_codes.append("source_windows_blocked")
    if never_ran:
        reason_codes.append("source_windows_not_consulted")
    if uncovered:
        reason_codes.append("source_window_coverage_incomplete")
    seed: dict[str, Any] = {
        "schema_version": WINDOW_SCHEMA,
        "source": "pncp_contracts",
        "period_start": start.isoformat(),
        "period_end_exclusive": end.isoformat(),
        "expected_days": len(expected_days),
        "covered_days": len(expected_days & completed_days),
        "failed_dates": sorted(item.isoformat() for item in current_failed),
        "blocked_dates": sorted(item.isoformat() for item in current_blocked),
        "not_consulted_dates": sorted(item.isoformat() for item in never_ran),
        "artifacts": sorted(artifacts, key=lambda item: item["sha256"]),
        "reason_codes": reason_codes,
    }
    seed["complete"] = not uncovered
    seed["window_evidence_hash"] = digest(seed)
    return seed


def _validate_window_evidence(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != WINDOW_SCHEMA or payload.get("source") != "pncp_contracts":
        raise CensusOperationError("window_evidence_contract_mismatch")
    supplied_hash = str(payload.get("window_evidence_hash") or "")
    seed = {key: value for key, value in payload.items() if key != "window_evidence_hash"}
    if len(supplied_hash) != 64 or supplied_hash != digest(seed):
        raise CensusOperationError("window_evidence_hash_mismatch")
    start = _parse_day(str(payload.get("period_start") or ""))
    end = _parse_day(str(payload.get("period_end_exclusive") or ""))
    expected = (end - start).days
    if expected < 1 or int(payload.get("expected_days") or -1) != expected:
        raise CensusOperationError("window_evidence_expected_days_mismatch")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise CensusOperationError("window_evidence_artifacts_required")
    if any(
        not isinstance(item, dict)
        or item.get("source") != "pncp_contracts"
        or item.get("capability") != "historical_contracts"
        or item.get("query_kind") != "publication"
        or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256") or ""))
        for item in artifacts
    ):
        raise CensusOperationError("window_evidence_artifact_invalid")
    uncovered_values = [
        *list(payload.get("failed_dates") or []),
        *list(payload.get("blocked_dates") or []),
        *list(payload.get("not_consulted_dates") or []),
    ]
    uncovered = {_parse_day(str(value)) for value in uncovered_values}
    if len(uncovered) != len(uncovered_values):
        raise CensusOperationError("window_evidence_date_overlap")
    target = {start + timedelta(days=offset) for offset in range(expected)}
    if not uncovered <= target:
        raise CensusOperationError("window_evidence_date_outside_period")
    covered = int(payload.get("covered_days") or 0)
    if covered + len(uncovered) != expected:
        raise CensusOperationError("window_evidence_reconciliation_mismatch")
    complete = bool(payload.get("complete"))
    if complete != (covered == expected and not uncovered):
        raise CensusOperationError("window_evidence_complete_mismatch")


def build_catalog_inventory(
    raw: bytes,
    *,
    competence: str,
    cutoff: str,
    retrieved_at: str,
    source_url: str = PNCP_ORGAOS,
    response_metadata: dict[str, Any] | None = None,
    raw_artifact: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Validate and canonically order one bounded catalog response body."""
    if len(raw) > MAX_CATALOG_BYTES:
        raise CensusOperationError("catalog_response_too_large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CensusOperationError(f"catalog_invalid_or_truncated:{type(exc).__name__}") from exc
    if not isinstance(payload, list):
        raise CensusOperationError("catalog_unwrapped_array_required")
    orgs: list[dict[str, Any]] = []
    seen: set[str] = set()
    active = 0
    inactive = 0
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise CensusOperationError(f"catalog_record_not_object:{index}")
        org_id = normalize_org_id(str(item.get("cnpj") or ""))
        if len(org_id) != 14:
            raise CensusOperationError(f"catalog_invalid_cnpj:{index}")
        if org_id in seen:
            raise CensusOperationError(f"catalog_duplicate_cnpj:{org_id}")
        seen.add(org_id)
        is_active = item.get("statusAtivo") is True
        active += int(is_active)
        inactive += int(not is_active)
        orgs.append(
            {
                "org_id": org_id,
                "name": str(item.get("razaoSocial") or org_id).strip() or org_id,
                "unit_count": 1,
                "catalog_active": is_active,
            }
        )
    if not orgs:
        raise CensusOperationError("catalog_empty")
    orgs.sort(key=lambda item: item["org_id"])
    # The existing national-coverage builder remains the sole identity/hash authority.
    universe = build_official_universe(
        source="pncp",
        source_url=source_url,
        competence=competence,
        cutoff=cutoff,
        as_of=retrieved_at,
        retrieved_at=retrieved_at,
        raw_hash=sha256_bytes(raw),
        method_version=CORE_METHOD_VERSION,
        units_enumerated=False,
        orgs=tuple(PublishingOrg(org_id=item["org_id"], name=item["name"], unit_count=1) for item in orgs),
    )
    inventory: dict[str, Any] = {
        "schema_version": CATALOG_SCHEMA,
        "source": "pncp",
        "source_url": source_url,
        "response_shape": "unwrapped_array",
        "retrieved_at": retrieved_at,
        "competence": competence,
        "cutoff": cutoff,
        "raw_bytes": len(raw),
        "raw_sha256": sha256_bytes(raw),
        "catalog_hash": universe.catalog_hash,
        "national_universe_id": universe.national_universe_id,
        "org_count": len(orgs),
        "active_org_count": active,
        "inactive_org_count": inactive,
        "unique_org_count": len(seen),
        "grain": "publishing_org",
        "unit_count": None,
        "transport_body_complete": True,
        "catalog_completeness_proven": False,
        "declared_total": None,
        "limitations": [
            "official_response_does_not_declare_total",
            "publishing_unit_denominator_not_enumerated",
        ],
        "response_metadata": response_metadata or {},
    }
    inventory["inventory_hash"] = digest(inventory)
    if raw_artifact is not None:
        if Path(raw_artifact).name != raw_artifact:
            raise CensusOperationError("catalog_raw_artifact_must_be_basename")
        inventory["raw_artifact"] = raw_artifact
    return inventory, orgs


def load_catalog_bundle(manifest_path: Path) -> tuple[bytes, dict[str, Any]]:
    """Load a content-addressed raw catalog through its immutable manifest."""
    payload = _load_object(manifest_path)
    if payload.get("schema_version") != CATALOG_SCHEMA or payload.get("source") != "pncp":
        raise CensusOperationError("catalog_manifest_contract_mismatch")
    artifact = str(payload.get("raw_artifact") or "")
    if not artifact or Path(artifact).name != artifact:
        raise CensusOperationError("catalog_manifest_raw_artifact_invalid")
    raw_path = manifest_path.parent / artifact
    try:
        raw = raw_path.read_bytes()
    except OSError as exc:
        raise CensusOperationError("catalog_manifest_raw_artifact_unavailable") from exc
    rebuilt, _ = build_catalog_inventory(
        raw,
        competence=str(payload.get("competence") or ""),
        cutoff=str(payload.get("cutoff") or ""),
        retrieved_at=str(payload.get("retrieved_at") or ""),
        source_url=str(payload.get("source_url") or ""),
        response_metadata=payload.get("response_metadata") or {},
        raw_artifact=artifact,
    )
    if payload != rebuilt:
        raise CensusOperationError("catalog_manifest_reconciliation_mismatch")
    return raw, rebuilt


def publish_catalog_bundle(
    *,
    out_raw: Path,
    out_manifest: Path,
    raw: bytes,
    inventory: dict[str, Any],
) -> Path:
    """Publish raw first under its hash, then atomically advance the LKG manifest."""
    if out_raw.parent.resolve() != out_manifest.parent.resolve():
        raise CensusOperationError("catalog_bundle_paths_must_share_directory")
    raw_hash = sha256_bytes(raw)
    versioned = out_raw.with_name(f"{out_raw.stem}.{raw_hash[:16]}{out_raw.suffix}")
    manifest = {**inventory, "raw_artifact": versioned.name}
    rebuilt, _ = build_catalog_inventory(
        raw,
        competence=str(manifest.get("competence") or ""),
        cutoff=str(manifest.get("cutoff") or ""),
        retrieved_at=str(manifest.get("retrieved_at") or ""),
        source_url=str(manifest.get("source_url") or ""),
        response_metadata=manifest.get("response_metadata") or {},
        raw_artifact=versioned.name,
    )
    if manifest != rebuilt:
        raise CensusOperationError("catalog_bundle_inventory_mismatch")
    existing = versioned.read_bytes() if versioned.exists() else None
    if existing is not None and sha256_bytes(existing) != raw_hash:
        raise CensusOperationError("catalog_content_address_collision")
    if existing is None:
        _atomic_write(versioned, raw)
    _atomic_json(out_manifest, manifest)
    return versioned


def build_corpus_snapshot(
    publishers: Iterable[dict[str, Any]],
    *,
    period_start: str,
    period_end_exclusive: str,
    retrieved_at: str,
    source: str = "pncp_supplier_contracts",
) -> dict[str, Any]:
    start = _parse_day(period_start)
    end = _parse_day(period_end_exclusive)
    if end <= start:
        raise CensusOperationError("period_end_exclusive_must_follow_start")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_contracts = 0
    for item in publishers:
        org_id = normalize_org_id(str(item.get("org_id") or item.get("raw_org_id") or ""))
        if len(org_id) != 14:
            raise CensusOperationError(f"corpus_invalid_cnpj:{org_id or 'missing'}")
        if org_id in seen:
            raise CensusOperationError(f"corpus_duplicate_cnpj:{org_id}")
        seen.add(org_id)
        count = int(item.get("contract_count") or 0)
        if count < 1:
            raise CensusOperationError(f"corpus_nonpositive_contract_count:{org_id}")
        total_contracts += count
        rows.append(
            {
                "org_id": org_id,
                "contract_count": count,
                "first_seen": item.get("first_seen"),
                "last_seen": item.get("last_seen"),
            }
        )
    rows.sort(key=lambda item: item["org_id"])
    content: dict[str, Any] = {
        "schema_version": CORPUS_SCHEMA,
        "source": source,
        "period_start": start.isoformat(),
        "period_end_exclusive": end.isoformat(),
        "retrieved_at": retrieved_at,
        "publisher_count": len(rows),
        "contract_count": total_contracts,
        "publishers": rows,
    }
    snapshot_hash = digest(content)
    return {
        **content,
        "snapshot_id": f"ncc-{end.isoformat()}-{snapshot_hash[:16]}",
        "snapshot_hash": snapshot_hash,
    }


def load_corpus_snapshot(path: Path) -> dict[str, Any]:
    payload = _load_object(path)
    required = ("period_start", "period_end_exclusive", "retrieved_at", "publishers")
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise CensusOperationError(f"corpus_missing_fields:{','.join(missing)}")
    rebuilt = build_corpus_snapshot(
        payload["publishers"],
        period_start=str(payload["period_start"]),
        period_end_exclusive=str(payload["period_end_exclusive"]),
        retrieved_at=str(payload["retrieved_at"]),
        source=str(payload.get("source") or "pncp_supplier_contracts"),
    )
    supplied = payload.get("snapshot_hash")
    if supplied and supplied != rebuilt["snapshot_hash"]:
        raise CensusOperationError("corpus_snapshot_hash_mismatch")
    return rebuilt


def _validate_corpus_snapshot(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != CORPUS_SCHEMA:
        raise CensusOperationError("corpus_schema_mismatch")
    if payload.get("source") != "pncp_supplier_contracts":
        raise CensusOperationError("corpus_source_not_canonical")
    rebuilt = build_corpus_snapshot(
        payload.get("publishers") or [],
        period_start=str(payload.get("period_start") or ""),
        period_end_exclusive=str(payload.get("period_end_exclusive") or ""),
        retrieved_at=str(payload.get("retrieved_at") or ""),
        source=str(payload.get("source") or ""),
    )
    fields = ("snapshot_hash", "snapshot_id", "publisher_count", "contract_count")
    if any(payload.get(field) != rebuilt[field] for field in fields):
        raise CensusOperationError("corpus_snapshot_reconciliation_mismatch")


def snapshot_corpus_from_dsn(
    dsn: str,
    *,
    period_start: str,
    period_end_exclusive: str,
    retrieved_at: str,
) -> dict[str, Any]:
    """Read a bounded aggregate; identifiers/counts only, no contract bodies."""
    try:
        import psycopg2
    except ImportError as exc:  # pragma: no cover - production dependency
        raise CensusOperationError("psycopg2_required") from exc
    start = _parse_day(period_start)
    end = _parse_day(period_end_exclusive)
    if end <= start:
        raise CensusOperationError("period_end_exclusive_must_follow_start")
    conn = psycopg2.connect(dsn)
    try:
        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    regexp_replace(coalesce(orgao_cnpj, ''), '[^0-9]', '', 'g') AS org_id,
                    count(*)::bigint AS contract_count,
                    min(coalesce(first_seen_at, ingested_at)) AS first_seen,
                    max(coalesce(last_seen_at, ingested_at)) AS last_seen
                FROM public.pncp_supplier_contracts
                WHERE data_publicacao >= %s
                  AND data_publicacao < %s
                GROUP BY 1
                ORDER BY 1
                """,
                (start, end),
            )
            rows = cursor.fetchall()
        conn.rollback()
    finally:
        conn.close()
    publishers = _corpus_publishers_from_rows(rows)
    return build_corpus_snapshot(
        publishers,
        period_start=start.isoformat(),
        period_end_exclusive=end.isoformat(),
        retrieved_at=retrieved_at,
    )


def _corpus_publishers_from_rows(rows: Iterable[Any]) -> list[dict[str, Any]]:
    publishers: list[dict[str, Any]] = []
    rejected_groups = 0
    rejected_contracts = 0
    for row in rows:
        org_id = normalize_org_id(str(row[0] or ""))
        count = int(row[1] or 0)
        if len(org_id) != 14:
            rejected_groups += 1
            rejected_contracts += count
            continue
        publishers.append(
            {
                "org_id": org_id,
                "contract_count": count,
                "first_seen": row[2].isoformat() if row[2] else None,
                "last_seen": row[3].isoformat() if row[3] else None,
            }
        )
    if rejected_groups:
        raise CensusOperationError(
            f"corpus_unmappable_identity_rows:groups={rejected_groups}:contracts={rejected_contracts}"
        )
    return publishers


def _read_response_limited(response: BinaryIO, *, maximum: int = MAX_CATALOG_BYTES) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = response.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > maximum:
            raise CensusOperationError("catalog_response_too_large")
        chunks.append(chunk)
    return b"".join(chunks)


def _retry_after(error: urllib.error.HTTPError) -> float | None:
    raw = error.headers.get("Retry-After") if error.headers else None
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def fetch_catalog_bytes(
    *,
    policy: HttpResiliencePolicy,
    breaker: PersistentCircuitBreaker,
    opener: Callable[..., Any] = urllib.request.urlopen,
    sleeper: Callable[[float], None] = time.sleep,
    url: str = PNCP_ORGAOS,
) -> tuple[bytes, dict[str, Any]]:
    """One bounded catalog request with shared retry and breaker policy."""
    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.scheme != "https" or parsed_url.hostname != "pncp.gov.br":
        raise CensusOperationError("official_catalog_url_not_allowed")
    request = urllib.request.Request(  # noqa: S310 - HTTPS host allowlisted above
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    attempts: list[dict[str, Any]] = []
    for attempt in range(policy.max_retries + 1):
        if not breaker.allow_request():
            raise CensusOperationError("official_catalog_circuit_open")
        started = time.monotonic()
        try:
            with opener(request, timeout=policy.read_timeout) as response:  # noqa: S310 - fixed official HTTPS URL
                raw = _read_response_limited(response)
                headers = getattr(response, "headers", {})
                status = int(getattr(response, "status", 200))
            if status != 200:
                raise CensusOperationError(f"official_catalog_http_{status}")
            # Parse before closing the breaker; a truncated 200 is a source failure.
            decoded = json.loads(raw.decode("utf-8"))
            if not isinstance(decoded, list) or not decoded:
                raise CensusOperationError("catalog_response_array_required")
            breaker.record_success()
            attempts.append({"attempt": attempt + 1, "classification": "success", "http_status": status})
            return raw, {
                "http_status": status,
                "date": headers.get("Date") if hasattr(headers, "get") else None,
                "etag": headers.get("ETag") if hasattr(headers, "get") else None,
                "last_modified": headers.get("Last-Modified") if hasattr(headers, "get") else None,
                "attempts": attempts,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "request_count": len(attempts),
                "concurrency": 1,
                "policy_version": policy.policy_version,
                "policy_fingerprint": policy.policy_fingerprint,
            }
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            retryable = status in policy.transient_statuses
            classification = "rate_limited" if status == 429 else ("server_error" if status >= 500 else "client_error")
            attempts.append({"attempt": attempt + 1, "classification": classification, "http_status": status})
            breaker.record_failure(http_status=status, error=classification)
            if not retryable or attempt >= policy.max_retries:
                raise CensusOperationError(f"official_catalog_http_{status}:{classification}") from exc
            sleeper(policy.retry_delay(attempt, _retry_after(exc)))
        except (TimeoutError, urllib.error.URLError) as exc:
            classification = "timeout" if isinstance(exc, TimeoutError) else "transport_error"
            attempts.append({"attempt": attempt + 1, "classification": classification, "http_status": None})
            breaker.record_failure(error=classification)
            if attempt >= policy.max_retries:
                raise CensusOperationError(f"official_catalog_{classification}") from exc
            sleeper(policy.retry_delay(attempt))
        except (UnicodeDecodeError, json.JSONDecodeError, CensusOperationError) as exc:
            breaker.record_failure(error="invalid_response")
            raise CensusOperationError(f"official_catalog_invalid_response:{type(exc).__name__}") from exc
    raise CensusOperationError("official_catalog_retry_budget_exhausted")


class _CheckpointLock:
    def __init__(self, path: Path):
        self.path = path.with_suffix(path.suffix + ".lock")
        self.handle: Any | None = None

    def __enter__(self) -> _CheckpointLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+", encoding="utf-8")
        try:
            import fcntl

            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.handle.close()
            raise CensusOperationError("census_checkpoint_already_claimed") from exc
        return self

    def __exit__(self, *_args: object) -> None:
        if self.handle is None:
            return
        try:
            import fcntl

            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()


def _input_hash(
    catalog: dict[str, Any], corpus: dict[str, Any], window_evidence: dict[str, Any], *, competence: str
) -> str:
    return digest(
        {
            "schema_version": CENSUS_SCHEMA,
            "competence": competence,
            "catalog_hash": catalog["catalog_hash"],
            "catalog_raw_sha256": catalog["raw_sha256"],
            "corpus_snapshot_hash": corpus["snapshot_hash"],
            "window_evidence_hash": window_evidence["window_evidence_hash"],
        }
    )


def _new_checkpoint(input_hash: str, total: int) -> dict[str, Any]:
    return {
        "schema_version": CHECKPOINT_SCHEMA,
        "input_hash": input_hash,
        "queue_order": "normalized_cnpj_ascending",
        "http_concurrency": 1,
        "partition_concurrency": 1,
        "expected_partitions": total,
        "next_index": 0,
        "terminal_by_status": {status: [] for status in TERMINAL_STATUSES},
        "complete": False,
        "updated_at": None,
    }


def _load_or_create_checkpoint(
    path: Path,
    *,
    input_hash: str,
    ordered_org_ids: list[str],
    expected_status_by_org: dict[str, str],
) -> dict[str, Any]:
    total = len(ordered_org_ids)
    if not path.exists():
        return _new_checkpoint(input_hash, total)
    payload = _load_object(path)
    if payload.get("schema_version") != CHECKPOINT_SCHEMA:
        raise CensusOperationError("checkpoint_schema_mismatch")
    if payload.get("input_hash") != input_hash:
        raise CensusOperationError("checkpoint_input_hash_mismatch")
    if int(payload.get("expected_partitions") or -1) != total:
        raise CensusOperationError("checkpoint_expected_partitions_mismatch")
    if payload.get("queue_order") != "normalized_cnpj_ascending":
        raise CensusOperationError("checkpoint_queue_order_mismatch")
    if payload.get("http_concurrency") != 1 or payload.get("partition_concurrency") != 1:
        raise CensusOperationError("checkpoint_concurrency_mismatch")
    terminal = payload.get("terminal_by_status")
    if not isinstance(terminal, dict) or set(terminal) != set(TERMINAL_STATUSES):
        raise CensusOperationError("checkpoint_terminal_states_corrupt")
    cursor = int(payload.get("next_index") or 0)
    if cursor < 0 or cursor > total:
        raise CensusOperationError("checkpoint_cursor_corrupt")
    complete = payload.get("complete")
    if not isinstance(complete, bool) or complete != (cursor == total):
        raise CensusOperationError("checkpoint_complete_mismatch")
    if any(not isinstance(terminal.get(status), list) for status in TERMINAL_STATUSES):
        raise CensusOperationError("checkpoint_terminal_states_corrupt")
    if any(not isinstance(org_id, str) for status in TERMINAL_STATUSES for org_id in terminal[status]):
        raise CensusOperationError("checkpoint_terminal_states_corrupt")
    terminal_ids = [org_id for status in TERMINAL_STATUSES for org_id in terminal[status]]
    if len(terminal_ids) != len(set(terminal_ids)):
        raise CensusOperationError("checkpoint_duplicate_terminal_partition")
    if set(terminal_ids) != set(ordered_org_ids[:cursor]):
        raise CensusOperationError("checkpoint_queue_prefix_corrupt")
    if any(
        expected_status_by_org.get(org_id) != status
        for status in TERMINAL_STATUSES
        for org_id in terminal[status]
    ):
        raise CensusOperationError("checkpoint_partition_status_mismatch")
    return payload


def run_census(
    *,
    catalog_raw: bytes,
    catalog_retrieved_at: str,
    corpus: dict[str, Any],
    window_evidence: dict[str, Any],
    competence: str,
    checkpoint_path: Path,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_partitions: int | None = None,
) -> dict[str, Any]:
    """Reconcile a deterministic local queue, resuming terminal partitions."""
    if batch_size < 1:
        raise CensusOperationError("batch_size_must_be_positive")
    _validate_corpus_snapshot(corpus)
    _validate_window_evidence(window_evidence)
    period_start = str(corpus["period_start"])
    period_end = str(corpus["period_end_exclusive"])
    if period_start != window_evidence.get("period_start") or period_end != window_evidence.get("period_end_exclusive"):
        raise CensusOperationError("corpus_window_period_mismatch")
    cutoff = (_parse_day(period_end) - timedelta(days=1)).isoformat()
    catalog, orgs = build_catalog_inventory(
        catalog_raw,
        competence=competence,
        cutoff=cutoff,
        retrieved_at=catalog_retrieved_at,
    )
    fingerprint = _input_hash(catalog, corpus, window_evidence, competence=competence)
    observed = {str(item["org_id"]): item for item in corpus["publishers"]}
    budget = len(orgs) if max_partitions is None else max(0, int(max_partitions))
    processed_this_run = 0
    with _CheckpointLock(checkpoint_path):
        ordered_org_ids = [str(item["org_id"]) for item in orgs]
        expected_status_by_org = {
            org_id: "FOUND" if org_id in observed else "BLOCKED" for org_id in ordered_org_ids
        }
        checkpoint = _load_or_create_checkpoint(
            checkpoint_path,
            input_hash=fingerprint,
            ordered_org_ids=ordered_org_ids,
            expected_status_by_org=expected_status_by_org,
        )
        terminal_by_status: dict[str, list[str]] = checkpoint["terminal_by_status"]
        states = {str(org_id): status for status in TERMINAL_STATUSES for org_id in terminal_by_status[status]}
        cursor = int(checkpoint.get("next_index") or 0)
        if not checkpoint_path.exists():
            checkpoint["updated_at"] = utc_now()
            _atomic_json(checkpoint_path, checkpoint)
        while cursor < len(orgs) and processed_this_run < budget:
            stop = min(cursor + batch_size, len(orgs), cursor + (budget - processed_this_run))
            for item in orgs[cursor:stop]:
                org_id = item["org_id"]
                if org_id in states:
                    continue
                # Source-wide completion is not entity-scoped negative evidence.
                # It may support the corpus snapshot, but cannot turn absence into
                # ZERO_CONFIRMED or make an organization look queried.
                status = expected_status_by_org[org_id]
                states[org_id] = status
                terminal_by_status[status].append(org_id)
                processed_this_run += 1
            cursor = stop
            checkpoint["next_index"] = cursor
            checkpoint["updated_at"] = utc_now()
            checkpoint["complete"] = cursor == len(orgs)
            _atomic_json(checkpoint_path, checkpoint)

        found = [org_id for org_id, status in states.items() if status == "FOUND"]
        zero = {
            org_id: f"source_window_manifest:{window_evidence['window_evidence_hash']}#org:{org_id}"
            for org_id, status in states.items()
            if status == "ZERO_CONFIRMED"
        }
        failed = {
            org_id: f"source_window_manifest:{window_evidence['window_evidence_hash']}"
            for org_id, status in states.items()
            if status == "FAILED"
        }
        blocked = {
            org_id: f"source_window_manifest:{window_evidence['window_evidence_hash']}"
            for org_id, status in states.items()
            if status == "BLOCKED"
        }
        # Unscheduled queue items deliberately remain implicit BLOCKED/unconsulted.
        input_payload = {
            "official": {
                "status": "AVAILABLE",
                "source": "pncp",
                "source_url": PNCP_ORGAOS,
                "competence": competence,
                "cutoff": cutoff,
                "as_of": catalog_retrieved_at,
                "retrieved_at": catalog_retrieved_at,
                "raw_hash": catalog["raw_sha256"],
                "method_version": CORE_METHOD_VERSION,
                "units_enumerated": False,
                "orgs": orgs,
            },
            "corpus": {
                "as_of": corpus["retrieved_at"],
                "source": corpus["source"],
                "publishers": [
                    {
                        "raw_org_id": item["org_id"],
                        "contract_count": item["contract_count"],
                        "first_seen": item.get("first_seen"),
                        "last_seen": item.get("last_seen"),
                    }
                    for item in corpus["publishers"]
                ],
            },
            "consulted": {
                "use_observed_as_found": False,
                "found": found,
                "zero_confirmed": zero,
                "failed": failed,
                "blocked": blocked,
                "queried": [*found, *zero, *failed],
            },
            "authorization_blockers": [
                "source_wide_aggregate_without_identity",
                "official_catalog_total_not_declared",
                *list(window_evidence.get("reason_codes") or []),
            ],
            "freshness": {"as_of": corpus["retrieved_at"]},
            "request": {
                "geography": "BR",
                "period": f"{period_start}/{period_end}",
                "source": "pncp",
                "grain": "publishing_org",
            },
        }
        coverage = evaluate_from_dict(input_payload)
        counts = coverage["partitions"]["by_status"]
        census_meta: dict[str, Any] = {
            "schema_version": CENSUS_SCHEMA,
            "input_hash": fingerprint,
            "catalog": catalog,
            "corpus": {key: value for key, value in corpus.items() if key != "publishers"},
            "window_evidence": window_evidence,
            "queue": {
                "order": "normalized_cnpj_ascending",
                "expected": len(orgs),
                "terminal": len(states),
                "remaining": len(orgs) - len(states),
                "complete": bool(checkpoint["complete"]),
                "checkpoint_schema": CHECKPOINT_SCHEMA,
                "checkpoint_hash": sha256_file(checkpoint_path),
                "http_concurrency": 1,
                "partition_concurrency": 1,
                "parallel_leasing_required": False,
                "claim_lock": "exclusive_flock",
            },
            "states": counts,
            "processed_this_run": processed_this_run,
            "nacional_completo": bool(coverage["national_claim_authorized"]),
            "national_claim_allowed": bool(coverage["consumer"]["national_claim_allowed"]),
            "reason_codes": list(coverage["reason_codes"]),
            "limitations": sorted(
                set(
                    [
                        *coverage["consumer"]["limitations"],
                        *catalog["limitations"],
                    ]
                )
            ),
        }
        return {**coverage, "census_operation": census_meta}


def _cmd_fetch_catalog(args: argparse.Namespace) -> int:
    policy = HttpResiliencePolicy.from_env(url=PNCP_ORGAOS)
    breaker = PersistentCircuitBreaker(
        Path(args.breaker_dir),
        environment=args.environment,
        source="pncp",
        route="orgaos-catalog",
        threshold=policy.circuit_breaker_threshold,
        cooldown_seconds=policy.circuit_breaker_cooldown,
    )
    raw, response = fetch_catalog_bytes(policy=policy, breaker=breaker)
    retrieved_at = utc_now()
    out_raw = Path(args.out_raw)
    raw_artifact = out_raw.with_name(f"{out_raw.stem}.{sha256_bytes(raw)[:16]}{out_raw.suffix}").name
    inventory, _ = build_catalog_inventory(
        raw,
        competence=args.competence,
        cutoff=args.cutoff,
        retrieved_at=retrieved_at,
        response_metadata=response,
        raw_artifact=raw_artifact,
    )
    versioned_raw = publish_catalog_bundle(
        out_raw=out_raw,
        out_manifest=Path(args.out_manifest),
        raw=raw,
        inventory=inventory,
    )
    sys.stdout.write(
        json.dumps(
            {
                "ok": True,
                "raw_path": str(versioned_raw),
                "manifest_path": args.out_manifest,
                "org_count": inventory["org_count"],
                "raw_sha256": inventory["raw_sha256"],
                "catalog_hash": inventory["catalog_hash"],
                "request_count": response["request_count"],
            },
            sort_keys=True,
        )
        + "\n"
    )
    return 0


def _cmd_snapshot_corpus(args: argparse.Namespace) -> int:
    snapshot = snapshot_corpus_from_dsn(
        args.dsn,
        period_start=args.period_start,
        period_end_exclusive=args.period_end_exclusive,
        retrieved_at=utc_now(),
    )
    _atomic_json(Path(args.out), snapshot)
    sys.stdout.write(
        json.dumps(
            {
                "ok": True,
                "path": args.out,
                "publisher_count": snapshot["publisher_count"],
                "contract_count": snapshot["contract_count"],
                "snapshot_hash": snapshot["snapshot_hash"],
            },
            sort_keys=True,
        )
        + "\n"
    )
    return 0


def _cmd_census(args: argparse.Namespace) -> int:
    corpus = load_corpus_snapshot(Path(args.corpus_json))
    catalog_raw, catalog_manifest = load_catalog_bundle(Path(args.catalog_manifest))
    expected_cutoff = (_parse_day(str(corpus["period_end_exclusive"])) - timedelta(days=1)).isoformat()
    if catalog_manifest.get("cutoff") != expected_cutoff:
        raise CensusOperationError("catalog_manifest_corpus_cutoff_mismatch")
    windows = build_window_evidence(
        [Path(item) for item in args.window_checkpoint],
        period_start=corpus["period_start"],
        period_end_exclusive=corpus["period_end_exclusive"],
    )
    report = run_census(
        catalog_raw=catalog_raw,
        catalog_retrieved_at=str(catalog_manifest["retrieved_at"]),
        corpus=corpus,
        window_evidence=windows,
        competence=str(catalog_manifest["competence"]),
        checkpoint_path=Path(args.checkpoint),
        batch_size=args.batch_size,
        max_partitions=args.max_partitions,
    )
    _atomic_json(Path(args.out), report)
    summary = {
        "ok": True,
        "path": args.out,
        "checkpoint": args.checkpoint,
        "national_universe_id": report["national_universe_id"],
        "catalog_hash": report["catalog_hash"],
        "reconciliation_hash": report["reconciliation_hash"],
        "states": report["partitions"]["by_status"],
        "nacional_completo": report["census_operation"]["nacional_completo"],
        "national_claim_allowed": report["census_operation"]["national_claim_allowed"],
        "remaining": report["census_operation"]["queue"]["remaining"],
        "reason_codes": report["reason_codes"],
    }
    sys.stdout.write(json.dumps(summary, ensure_ascii=False, sort_keys=True) + "\n")
    return 0


def add_census_subcommands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    fetch = sub.add_parser("fetch-catalog", help="Fetch one official PNCP catalog response safely")
    fetch.add_argument("--out-raw", required=True)
    fetch.add_argument("--out-manifest", required=True)
    fetch.add_argument("--competence", required=True)
    fetch.add_argument("--cutoff", required=True)
    fetch.add_argument("--breaker-dir", default="data/circuit-breakers")
    fetch.add_argument("--environment", default="production")
    fetch.set_defaults(func=_cmd_fetch_catalog)

    snapshot = sub.add_parser("snapshot-corpus", help="Export a read-only aggregate corpus snapshot")
    snapshot.add_argument("--dsn", required=True)
    snapshot.add_argument("--period-start", required=True)
    snapshot.add_argument("--period-end-exclusive", required=True)
    snapshot.add_argument("--out", required=True)
    snapshot.set_defaults(func=_cmd_snapshot_corpus)

    census = sub.add_parser("census", help="Resume deterministic national partition reconciliation")
    census.add_argument("--catalog-manifest", required=True)
    census.add_argument("--corpus-json", required=True)
    census.add_argument("--window-checkpoint", action="append", required=True)
    census.add_argument("--checkpoint", required=True)
    census.add_argument("--out", required=True)
    census.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    census.add_argument("--max-partitions", type=int, default=None)
    census.set_defaults(func=_cmd_census)


if __name__ == "__main__":
    raise SystemExit("use python3 -m scripts.national_coverage census ...")
