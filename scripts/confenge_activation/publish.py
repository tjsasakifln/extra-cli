"""Atomic feed publication: build temp → validate → hash → promote.

Never leave Warmbly observing partial chunks with a new manifest.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA = "confenge.outreach.manifest.v1"
FEED_SCHEMA = "confenge.outreach.v1"
DEFAULT_MAX_AGE_HOURS = 24.0
DEFAULT_STATE_PATH = Path("/var/lib/extra-consultoria/confenge-feed/publication-state.json")
DEFAULT_ALERT_LEDGER = Path("/var/lib/extra-consultoria/alerts/confenge-feed.jsonl")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _fsync_dir(path: Path) -> None:
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _make_public_feed_tree_readable(root: Path) -> None:
    """Make an immutable feed release traversable by the serving process.

    The publication service and nginx intentionally run as different users in
    production. ``mkdtemp`` starts at 0700 and ``copy2`` preserves restrictive
    build modes, so relying on the service umask makes an otherwise valid
    release return 404 from nginx. Feed artifacts are public by contract;
    normalize directories to 0755 and regular files to 0644 before promotion.
    """
    root.chmod(0o755)
    for directory, names, files in os.walk(root):
        base = Path(directory)
        base.chmod(0o755)
        for name in names:
            path = base / name
            if not path.is_symlink():
                path.chmod(0o755)
        for name in files:
            path = base / name
            if not path.is_symlink():
                path.chmod(0o644)


def _parse_timestamp(value: Any, *, field: str) -> datetime:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} is missing or invalid: {text!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    finally:
        tmp.unlink(missing_ok=True)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _read_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return _read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _append_alert(path: Path, *, reason: str, detail: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "event": "confenge_feed_publication_alert",
        "reason": reason,
        "project": "extra-cli",
        **detail,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def record_feed_cycle_state(
    state_path: Path,
    *,
    alert_ledger: Path,
    status: str,
    detail: dict[str, Any],
    at: datetime | None = None,
    alert_reason: str | None = None,
) -> None:
    """Persist end-to-end cycle state without erasing publication history."""
    clock = (at or datetime.now(UTC)).astimezone(UTC)
    cycle = {
        "at": clock.isoformat().replace("+00:00", "Z"),
        "status": status,
        **detail,
    }
    state = _read_state(state_path)
    _atomic_json(
        state_path,
        {
            **state,
            "schema_id": "confenge.feed_publication_state.v1",
            "last_cycle_at": cycle["at"],
            "last_cycle_status": status,
            "cycle": cycle,
        },
    )
    if alert_reason:
        _append_alert(alert_ledger, reason=alert_reason, detail=cycle)


def _provenance_source(contact: dict[str, Any]) -> str:
    direct = str(contact.get("source") or contact.get("source_type") or "").strip()
    if direct:
        return direct
    provenance = contact.get("provenance")
    if isinstance(provenance, dict):
        return str(
            provenance.get("source")
            or provenance.get("source_type")
            or provenance.get("provider")
            or "UNKNOWN"
        )
    return "UNKNOWN"


def _validate_authoritative_manifest(
    build_dir: Path,
    manifest: dict[str, Any],
    *,
    max_age_hours: float,
    now: datetime,
) -> dict[str, Any]:
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise ValueError("unsupported or missing manifest schema_version")
    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
    run_id = str(source.get("run_id") or "").strip()
    snapshot_hash = str(source.get("snapshot_hash") or "").strip()
    if not run_id or not snapshot_hash:
        raise ValueError("manifest source.run_id and source.snapshot_hash are required")

    authority = manifest.get("authoritative_target_fit")
    authority = authority if isinstance(authority, dict) else {}
    if authority.get("coverage_complete") is not True:
        raise ValueError("authoritative target-fit coverage_complete=true is required")
    if authority.get("omission_preserves_authorization") is not False:
        raise ValueError("authoritative target-fit omission must revoke prior authorization")
    ordering = authority.get("ordering") if isinstance(authority.get("ordering"), dict) else {}
    if ordering.get("watermarks_monotonic") is not True:
        raise ValueError("authoritative target-fit watermarks must be monotonic")

    generated_at = _parse_timestamp(manifest.get("generated_at"), field="manifest.generated_at")
    watermark = _parse_timestamp(source.get("datalake_watermark"), field="source.datalake_watermark")
    if generated_at > now + timedelta(minutes=5):
        raise ValueError("manifest.generated_at is in the future")
    generated_age = max(0.0, (now - generated_at).total_seconds() / 3600)
    watermark_age = max(0.0, (now - watermark).total_seconds() / 3600)
    if generated_age > max_age_hours:
        raise ValueError(f"manifest stale: generated_at age {generated_age:.3f}h > {max_age_hours:.3f}h")
    if watermark_age > max_age_hours:
        raise ValueError(f"datalake watermark stale: age {watermark_age:.3f}h > {max_age_hours:.3f}h")

    freshness = manifest.get("authoritative_source_freshness")
    freshness = freshness if isinstance(freshness, dict) else {}
    if freshness.get("contract_version") != "PNCP_CONTRACT_FRESHNESS/1.0":
        raise ValueError("authoritative PNCP freshness contract is required")
    if freshness.get("status") != "FRESH":
        raise ValueError(f"authoritative PNCP freshness is not FRESH: {freshness.get('status') or 'MISSING'}")
    if _parse_timestamp(freshness.get("expires_at"), field="authoritative_source_freshness.expires_at") <= now:
        raise ValueError("authoritative PNCP freshness expired before publication")

    chunks = manifest.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("manifest must list at least one chunk")
    if int(manifest.get("chunk_count") or -1) != len(chunks):
        raise ValueError("manifest chunk_count does not match chunks")
    total_leads = 0
    accounts_with_contacts = 0
    accounts_with_preferred_route = 0
    contacts_total = 0
    route_classes: dict[str, int] = {}
    provenance_sources: dict[str, int] = {}
    for expected_index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            raise ValueError(f"manifest chunk {expected_index} is not an object")
        if int(chunk.get("chunk_index") or 0) != expected_index:
            raise ValueError("manifest chunk indexes must be contiguous")
        filename = str(chunk.get("file") or "").strip()
        if not filename or Path(filename).name != filename:
            raise ValueError(f"unsafe chunk file name: {filename!r}")
        chunk_path = build_dir / filename
        if not chunk_path.is_file():
            raise FileNotFoundError(f"manifest references missing chunk {filename}")
        actual_hash = _sha256_file(chunk_path)
        expected_hash = str(chunk.get("content_hash") or "").strip()
        if not expected_hash or actual_hash != expected_hash:
            raise ValueError(f"chunk hash mismatch for {filename}: {actual_hash} != {expected_hash or 'MISSING'}")
        payload = _read_json(chunk_path)
        payload_source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
        if payload.get("schema_version") != FEED_SCHEMA:
            raise ValueError(f"unsupported chunk schema for {filename}")
        if payload.get("generated_at") != manifest.get("generated_at"):
            raise ValueError(f"chunk generated_at mismatch for {filename}")
        if payload_source.get("run_id") != run_id or payload_source.get("snapshot_hash") != snapshot_hash:
            raise ValueError(f"chunk source mismatch for {filename}")
        leads = payload.get("leads")
        if not isinstance(leads, list) or len(leads) != int(chunk.get("lead_count") or 0):
            raise ValueError(f"chunk lead_count mismatch for {filename}")
        total_leads += len(leads)
        for lead in leads:
            if not isinstance(lead, dict):
                continue
            contacts = [item for item in (lead.get("contacts") or []) if isinstance(item, dict)]
            contacts_total += len(contacts)
            if contacts:
                accounts_with_contacts += 1
            if any(item.get("preferred_initial") is True for item in contacts) or lead.get("preferred_email_route"):
                accounts_with_preferred_route += 1
            for contact in contacts:
                route = str(contact.get("route_class") or "UNKNOWN")
                source_name = _provenance_source(contact)
                route_classes[route] = route_classes.get(route, 0) + 1
                provenance_sources[source_name] = provenance_sources.get(source_name, 0) + 1
    if total_leads != int(manifest.get("lead_count", -1)):
        raise ValueError("manifest lead_count does not match chunk payloads")
    if int(authority.get("full_decision_count", -1)) != total_leads:
        raise ValueError("authoritative target-fit decision count does not match feed")
    return {
        "run_id": run_id,
        "snapshot_hash": snapshot_hash,
        "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
        "datalake_watermark": watermark.isoformat().replace("+00:00", "Z"),
        "generated_age_hours": round(generated_age, 6),
        "watermark_age_hours": round(watermark_age, 6),
        "lead_count": total_leads,
        "chunk_count": len(chunks),
        "accounts_with_contacts": accounts_with_contacts,
        "accounts_with_preferred_route": accounts_with_preferred_route,
        "contacts_total": contacts_total,
        "route_class_distribution": dict(sorted(route_classes.items())),
        "provenance_source_distribution": dict(sorted(provenance_sources.items())),
    }


def atomic_publish_directory(
    build_dir: Path,
    publish_dir: Path,
    *,
    current_name: str = "current",
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    state_path: Path = DEFAULT_STATE_PATH,
    alert_ledger: Path = DEFAULT_ALERT_LEDGER,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Atomically promote build_dir contents to publish_dir/current via rename.

    Layout:
      publish_dir/
        current -> releases/<run_id>   (symlink, atomic replace)
        releases/<run_id>/...
    If build_dir already contains a complete feed (manifest + chunks), we copy
    into a new release directory then swap the symlink.
    """
    started = time.monotonic()
    clock = (now or datetime.now(UTC)).astimezone(UTC)
    build_dir = Path(build_dir)
    publish_dir = Path(publish_dir)
    publish_dir.mkdir(parents=True, exist_ok=True)
    releases = publish_dir / "releases"
    releases.mkdir(parents=True, exist_ok=True)

    manifest_path = build_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"no manifest.json in {build_dir}")

    manifest = _read_json(manifest_path)
    try:
        metrics = _validate_authoritative_manifest(
            build_dir,
            manifest,
            max_age_hours=max_age_hours,
            now=clock,
        )
    except Exception as exc:
        detail = {"build_dir": str(build_dir), "error": str(exc)}
        _append_alert(alert_ledger, reason="PUBLICATION_REFUSED", detail=detail)
        state = _read_state(state_path)
        _atomic_json(
            state_path,
            {
                **state,
                "schema_id": "confenge.feed_publication_state.v1",
                "last_attempt_at": clock.isoformat().replace("+00:00", "Z"),
                "last_status": "REFUSED",
                **detail,
            },
        )
        raise
    run_id = str(metrics["run_id"])

    current = publish_dir / current_name
    if current.is_dir():
        try:
            prior = _read_json(current / "manifest.json")
        except (OSError, ValueError, json.JSONDecodeError):
            prior = {}
        prior_source = prior.get("source") if isinstance(prior.get("source"), dict) else {}
        if str(prior_source.get("snapshot_hash") or "") == metrics["snapshot_hash"]:
            result = {
                "ok": False,
                "skipped_same": True,
                "reason": "SAME_SNAPSHOT_NOT_FRESHNESS",
                "publish_dir": str(publish_dir.resolve()),
                "current": str(current.resolve()),
                **metrics,
                "duration_seconds": round(time.monotonic() - started, 6),
            }
            _append_alert(alert_ledger, reason="SAME_SNAPSHOT_NOT_FRESHNESS", detail=result)
            state = _read_state(state_path)
            _atomic_json(
                state_path,
                {
                    **state,
                    "schema_id": "confenge.feed_publication_state.v1",
                    "last_attempt_at": clock.isoformat().replace("+00:00", "Z"),
                    "last_status": "SKIPPED_SAME_SNAPSHOT",
                    **result,
                },
            )
            return result

    release_dir = releases / f"{run_id}-{str(metrics['snapshot_hash'])[:12]}"
    if release_dir.exists():
        raise FileExistsError(f"immutable feed release already exists: {release_dir}")
    # Copy into temp under releases then rename
    tmp = Path(tempfile.mkdtemp(prefix=".pub-", dir=str(releases)))
    try:
        for item in build_dir.iterdir():
            dest = tmp / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
                # fsync file
                with dest.open("rb") as f:
                    os.fsync(f.fileno())
        _make_public_feed_tree_readable(tmp)
        _fsync_dir(tmp)
        os.replace(str(tmp), str(release_dir))
        _fsync_dir(releases)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise

    # Atomic symlink swap: current -> releases/<run_id>
    link_tmp = publish_dir / f".{current_name}.tmp-{run_id}"
    if link_tmp.exists() or link_tmp.is_symlink():
        link_tmp.unlink()
    # Relative symlink for portability
    rel_target = Path("releases") / release_dir.name
    link_tmp.symlink_to(rel_target, target_is_directory=True)
    os.replace(str(link_tmp), str(current))
    _fsync_dir(publish_dir)

    state = _read_state(state_path)
    previous_contacts = state.get("contacts_total")
    previous_accounts = state.get("accounts_with_contacts")
    result = {
        "ok": True,
        "skipped_same": False,
        "publish_dir": str(publish_dir.resolve()),
        "current": str(current.resolve()),
        "release_dir": str(release_dir.resolve()),
        **metrics,
        "snapshot_changed": str(state.get("snapshot_hash") or "") != str(metrics["snapshot_hash"]),
        "contact_count_delta": (
            int(metrics["contacts_total"]) - int(previous_contacts)
            if previous_contacts is not None
            else None
        ),
        "accounts_with_contacts_delta": (
            int(metrics["accounts_with_contacts"]) - int(previous_accounts)
            if previous_accounts is not None
            else None
        ),
        "duration_seconds": round(time.monotonic() - started, 6),
    }
    _atomic_json(
        state_path,
        {
            **state,
            "schema_id": "confenge.feed_publication_state.v1",
            "last_attempt_at": clock.isoformat().replace("+00:00", "Z"),
            "last_success_at": clock.isoformat().replace("+00:00", "Z"),
            "last_status": "PUBLISHED",
            **result,
            "status": "PUBLISHED",
            "error": None,
        },
    )
    return result


def check_current_publication(
    publish_dir: Path,
    *,
    current_name: str = "current",
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    state_path: Path = DEFAULT_STATE_PATH,
    alert_ledger: Path = DEFAULT_ALERT_LEDGER,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Fail closed when the publicly served current release is stale or corrupt."""
    clock = (now or datetime.now(UTC)).astimezone(UTC)
    current = Path(publish_dir) / current_name
    try:
        manifest = _read_json(current / "manifest.json")
        metrics = _validate_authoritative_manifest(
            current,
            manifest,
            max_age_hours=max_age_hours,
            now=clock,
        )
    except Exception as exc:
        result = {"ok": False, "status": "UNHEALTHY", "current": str(current), "error": str(exc)}
        _append_alert(alert_ledger, reason="PUBLIC_FEED_UNHEALTHY", detail=result)
        state = _read_state(state_path)
        _atomic_json(
            state_path,
            {
                **state,
                "schema_id": "confenge.feed_publication_state.v1",
                "last_monitor_at": clock.isoformat().replace("+00:00", "Z"),
                "last_monitor_status": "UNHEALTHY",
                "monitor": result,
                **result,
            },
        )
        return result
    result = {"ok": True, "status": "HEALTHY", "current": str(current.resolve()), **metrics}
    state = _read_state(state_path)
    _atomic_json(
        state_path,
        {
            **state,
            "schema_id": "confenge.feed_publication_state.v1",
            "last_monitor_at": clock.isoformat().replace("+00:00", "Z"),
            "last_monitor_status": "HEALTHY",
            **result,
            "error": None,
            "monitor": result,
        },
    )
    return result
