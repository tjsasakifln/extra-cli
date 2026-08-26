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
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.confenge_outreach_pipeline.party_role import PARTY_ROLE_POLICY_V1
from scripts.confenge_target_fit.company_key import canonical_target_membership

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
        return str(provenance.get("source") or provenance.get("source_type") or provenance.get("provider") or "UNKNOWN")
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

    target_membership = manifest.get("authoritative_target_membership")
    target_membership = target_membership if isinstance(target_membership, dict) else {}
    if target_membership.get("membership_complete") is not True:
        raise ValueError("authoritative TARGET_CONFIRMED membership_complete=true is required")

    party_roles = manifest.get("authoritative_party_roles")
    party_roles = party_roles if isinstance(party_roles, dict) else {}
    if party_roles.get("policy_version") != PARTY_ROLE_POLICY_V1:
        raise ValueError("authoritative contractor role policy is required")
    if party_roles.get("buyer_supplier_conflict_fails_closed") is not True:
        raise ValueError("buyer/supplier conflict must fail closed")

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
    target_accounts_with_preferred_route = 0
    contacts_total = 0
    route_classes: dict[str, int] = {}
    preferred_route_classes: Counter[str] = Counter()
    provenance_sources: dict[str, int] = {}
    target_member_cnpjs: list[str] = []
    target_role_distribution: Counter[str] = Counter()
    target_role_status_distribution: Counter[str] = Counter()
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
            is_target = str(lead.get("target_fit_class") or "") == "TARGET_CONFIRMED"
            if is_target:
                company = lead.get("company") if isinstance(lead.get("company"), dict) else {}
                target_member_cnpjs.append(str(company.get("cnpj14") or ""))
                contractor_role = lead.get("contractor_role")
                contractor_role = contractor_role if isinstance(contractor_role, dict) else {}
                if contractor_role.get("policy_version") != PARTY_ROLE_POLICY_V1:
                    raise ValueError("TARGET_CONFIRMED lead is missing typed contractor_role")
                target_role = str(contractor_role.get("target_party_role") or "UNKNOWN")
                target_status = str(contractor_role.get("status") or "UNKNOWN")
                target_role_distribution[target_role] += 1
                target_role_status_distribution[target_status] += 1
                if target_role == "BUYER_CONFLICT" or target_status == "PARTY_ROLE_CONFLICT":
                    if lead.get("email_send_ready") is True or lead.get("preferred_email_route"):
                        raise ValueError("buyer/supplier conflict authorizes outreach at lead level")
                    if any(
                        contact.get(field) is True
                        for contact in contacts
                        for field in (
                            "controlled_email_eligible",
                            "email_send_ready",
                            "enrollable",
                            "preferred_initial",
                            "recommended",
                        )
                    ):
                        raise ValueError("buyer/supplier conflict authorizes outreach at contact level")
            contacts_total += len(contacts)
            if contacts:
                accounts_with_contacts += 1
            has_preferred = any(item.get("preferred_initial") is True for item in contacts) or bool(
                lead.get("preferred_email_route")
            )
            if has_preferred:
                accounts_with_preferred_route += 1
                if is_target:
                    target_accounts_with_preferred_route += 1
            for contact in contacts:
                route = str(contact.get("route_class") or "UNKNOWN")
                if is_target and contact.get("preferred_initial") is True:
                    preferred_route_classes[route] += 1
                source_name = _provenance_source(contact)
                route_classes[route] = route_classes.get(route, 0) + 1
                provenance_sources[source_name] = provenance_sources.get(source_name, 0) + 1
    if total_leads != int(manifest.get("lead_count", -1)):
        raise ValueError("manifest lead_count does not match chunk payloads")
    if int(authority.get("full_decision_count", -1)) != total_leads:
        raise ValueError("authoritative target-fit decision count does not match feed")
    try:
        observed_membership = canonical_target_membership(target_member_cnpjs)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    for field in (
        "schema_version",
        "identity_key",
        "hash_algorithm",
        "population_count",
        "membership_hash",
        "duplicate_member_count",
    ):
        if target_membership.get(field) != observed_membership[field]:
            raise ValueError(f"authoritative TARGET_CONFIRMED membership {field} mismatch")
    if int(target_membership.get("source_member_count", -1)) != len(target_member_cnpjs):
        raise ValueError("authoritative TARGET_CONFIRMED source_member_count mismatch")
    if target_membership.get("target_fit_class") != "TARGET_CONFIRMED":
        raise ValueError("authoritative target membership class must be TARGET_CONFIRMED")
    if not target_membership.get("target_fit_policy_versions"):
        raise ValueError("authoritative target membership policy versions are required")
    if target_membership.get("target_party_role_distribution") != dict(sorted(target_role_distribution.items())):
        raise ValueError("authoritative TARGET_CONFIRMED party role distribution mismatch")
    if int(target_membership.get("target_confirmed_count", -1)) != observed_membership["population_count"]:
        raise ValueError("authoritative TARGET_CONFIRMED named count mismatch")
    if int(target_membership.get("supplier_confirmed_count", -1)) != int(target_role_distribution.get("SUPPLIER") or 0):
        raise ValueError("authoritative SUPPLIER_CONFIRMED count mismatch")
    if target_membership.get("contractor_role_status_distribution") != dict(
        sorted(target_role_status_distribution.items())
    ):
        raise ValueError("authoritative TARGET_CONFIRMED contractor role status distribution mismatch")
    if party_roles.get("target_party_role_distribution") != dict(sorted(target_role_distribution.items())):
        raise ValueError("authoritative party role projection does not match feed")
    if int(party_roles.get("supplier_confirmed_count", -1)) != int(target_role_distribution.get("SUPPLIER") or 0):
        raise ValueError("authoritative party role supplier count does not match feed")
    contact_projection = manifest.get("authoritative_contact_projection")
    if not isinstance(contact_projection, dict):
        raise ValueError("authoritative contact projection is required")
    if contact_projection.get("schema_id") != "confenge.contact_discovery.projection_report.v1":
        raise ValueError("authoritative contact projection schema is required")
    required_contact_metadata = (
        "report_sha256",
        "cohort_id",
        "generated_at",
        "population_hash",
        "population_as_of",
        "projection_hash",
        "controlled_email_policy_version",
        "discovery_policy_version",
        "input_evidence_version",
        "code_sha",
    )
    if missing := [
        field for field in required_contact_metadata if not str(contact_projection.get(field) or "").strip()
    ]:
        raise ValueError(f"authoritative contact projection metadata is missing: {missing}")
    contact_generated = _parse_timestamp(
        contact_projection.get("generated_at"), field="authoritative_contact_projection.generated_at"
    )
    contact_population_as_of = _parse_timestamp(
        contact_projection.get("population_as_of"), field="authoritative_contact_projection.population_as_of"
    )
    if contact_generated > now + timedelta(minutes=5) or contact_population_as_of > now + timedelta(minutes=5):
        raise ValueError("authoritative contact projection timestamp is in the future")
    if max(0.0, (now - contact_generated).total_seconds() / 3600) > max_age_hours:
        raise ValueError("authoritative contact projection is stale")
    if max(0.0, (now - contact_population_as_of).total_seconds() / 3600) > max_age_hours:
        raise ValueError("authoritative contact population is stale")
    if contact_projection.get("coverage_complete") is not True:
        raise ValueError("authoritative contact projection coverage_complete=true is required")
    terminal_equation = contact_projection.get("terminal_equation")
    terminal_equation = terminal_equation if isinstance(terminal_equation, dict) else {}
    if contact_projection.get("terminal_coverage_complete") is not True or terminal_equation.get("holds") is not True:
        raise ValueError("authoritative contact projection terminal coverage is incomplete")
    if int(contact_projection.get("population_count", -1)) != observed_membership["population_count"]:
        raise ValueError("authoritative contact projection population_count mismatch")
    if int(contact_projection.get("membership_count", -1)) != observed_membership["population_count"]:
        raise ValueError("authoritative contact projection membership_count mismatch")
    if contact_projection.get("membership_hash") != observed_membership["membership_hash"]:
        raise ValueError("authoritative contact projection membership_hash mismatch")
    for report_field, membership_field in (
        ("membership_schema_version", "schema_version"),
        ("membership_identity_key", "identity_key"),
        ("membership_hash_algorithm", "hash_algorithm"),
    ):
        if contact_projection.get(report_field) != observed_membership[membership_field]:
            raise ValueError(f"authoritative contact projection {report_field} mismatch")
    terminal_states = contact_projection.get("enrichment_states")
    terminal_states = terminal_states if isinstance(terminal_states, dict) else {}
    allowed_terminal_states = {
        "EMAIL_ROUTE_READY",
        "NO_PUBLIC_EMAIL_FOUND",
        "BLOCKED_WITH_REASON",
    }
    if set(terminal_states) - allowed_terminal_states:
        raise ValueError("authoritative contact projection contains a non-terminal state")
    if (
        sum(int(terminal_states.get(name) or 0) for name in allowed_terminal_states)
        != observed_membership["population_count"]
    ):
        raise ValueError("authoritative contact projection terminal states do not close membership")
    if contact_projection.get("input_declared") is True:
        input_count = int(contact_projection.get("input_preferred_route_count", -1))
        output_count = int(contact_projection.get("output_preferred_route_count", -1))
        if contact_projection.get("preferred_routes_reconciled") is not True:
            raise ValueError("authoritative contact projection is not reconciled")
        if input_count != output_count or output_count != target_accounts_with_preferred_route:
            raise ValueError("authoritative contact projection preferred route count mismatch")
        if contact_projection.get("input_preferred_routes_hash") != contact_projection.get(
            "output_preferred_routes_hash"
        ):
            raise ValueError("authoritative contact projection preferred route hash mismatch")
    recipient_states = contact_projection.get("recipient_states")
    recipient_states = recipient_states if isinstance(recipient_states, dict) else {}
    if int(recipient_states.get("RECIPIENT_ATTRIBUTED", -1)) != target_accounts_with_preferred_route:
        raise ValueError("authoritative RECIPIENT_ATTRIBUTED count does not match feed")
    if int(recipient_states.get("READY", -1)) != target_accounts_with_preferred_route:
        raise ValueError("authoritative READY count does not match feed")
    if contact_projection.get("output_preferred_route_class_distribution") != dict(
        sorted(preferred_route_classes.items())
    ):
        raise ValueError("authoritative preferred route_class distribution does not match feed")
    if (
        int(recipient_states.get("READY") or 0)
        + int(recipient_states.get("NO_PUBLIC_EMAIL_FOUND") or 0)
        + int(recipient_states.get("BLOCKED_WITH_REASON") or 0)
        != observed_membership["population_count"]
    ):
        raise ValueError("authoritative recipient states do not close TARGET_CONFIRMED membership")
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
        "target_accounts_with_preferred_route": target_accounts_with_preferred_route,
        "contacts_total": contacts_total,
        "route_class_distribution": dict(sorted(route_classes.items())),
        "preferred_route_class_distribution": dict(sorted(preferred_route_classes.items())),
        "provenance_source_distribution": dict(sorted(provenance_sources.items())),
        "authoritative_target_membership": target_membership,
        "authoritative_party_roles": party_roles,
        "authoritative_contact_projection": contact_projection,
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
            int(metrics["contacts_total"]) - int(previous_contacts) if previous_contacts is not None else None
        ),
        "accounts_with_contacts_delta": (
            int(metrics["accounts_with_contacts"]) - int(previous_accounts) if previous_accounts is not None else None
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
