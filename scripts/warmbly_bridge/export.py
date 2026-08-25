"""Path-based confenge.outreach.v1 exporter with deterministic chunking + manifest."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.confenge_outreach_pipeline.party_role import project_contractor_role
from scripts.confenge_target_fit.published import build_published_index_from_rows
from scripts.warmbly_bridge import (
    DEFAULT_MAX_BYTES_PER_CHUNK,
    DEFAULT_MAX_LEADS_PER_CHUNK,
    DEFAULT_PROFILE_ID,
    DEFAULT_PROFILE_VERSION,
    DEFAULT_SYSTEM,
    MODULE_VERSION,
    SCHEMA_OUTREACH,
)
from scripts.warmbly_bridge.io_jsonl import InputError, content_hash_obj, read_jsonl, require_readable_file
from scripts.warmbly_bridge.mapping import build_leads


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _git_sha() -> str:
    import shutil

    git_bin = shutil.which("git")
    if not git_bin:
        return "unknown"
    try:
        out = subprocess.check_output(  # noqa: S603 — absolute git path, fixed argv
            [git_bin, "-C", str(Path(__file__).resolve().parents[2]), "rev-parse", "--short=12", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return out.strip() or "unknown"
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return "unknown"


def _snapshot_hash(universe: Path, intel: Path, contacts: Path, target_fit: Path | None) -> str:
    h = hashlib.sha256()
    for p in (universe, intel, contacts, target_fit):
        if p is None:
            continue
        h.update(p.name.encode())
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def _run_id(
    snapshot_hash: str,
    profile_id: str,
    profile_version: str,
    authoritative_freshness_hash: str | None = None,
) -> str:
    raw = (
        f"{snapshot_hash}|{profile_id}|{profile_version}|{MODULE_VERSION}|"
        f"{authoritative_freshness_hash or 'no-source-freshness'}"
    )
    return "run-" + hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class ExportConfig:
    universe: Path
    account_intelligence: Path
    contacts: Path
    out_dir: Path
    target_fit_snapshot: Path | None = None
    expected_universe_count: int | None = None
    limit: int | None = None
    max_leads_per_chunk: int = DEFAULT_MAX_LEADS_PER_CHUNK
    max_bytes_per_chunk: int = DEFAULT_MAX_BYTES_PER_CHUNK
    profile_id: str = DEFAULT_PROFILE_ID
    profile_version: str = DEFAULT_PROFILE_VERSION
    system: str = DEFAULT_SYSTEM
    generated_at: str | None = None  # inject for deterministic tests
    datalake_watermark: str | None = None
    require_authoritative_target_fit_metadata: bool = True
    repo_sha: str | None = None
    authoritative_source_freshness: dict[str, Any] | None = None
    require_authoritative_source_freshness: bool = False
    # Delta deactivations for accounts leaving ACTIONABLE_NOW (manifest section)
    deactivations: list[dict[str, Any]] | None = None


def validate_inputs(cfg: ExportConfig) -> None:
    """Fail-closed: all three required inputs must exist and be readable."""
    require_readable_file(cfg.universe, label="--universe")
    require_readable_file(cfg.account_intelligence, label="--account-intelligence")
    require_readable_file(cfg.contacts, label="--contacts")
    if cfg.target_fit_snapshot is not None:
        require_readable_file(cfg.target_fit_snapshot, label="--target-fit-snapshot")
    if cfg.max_leads_per_chunk < 1:
        raise InputError("--max-leads-per-chunk must be >= 1")
    if cfg.max_bytes_per_chunk < 1024:
        raise InputError("--max-bytes-per-chunk must be >= 1024")
    if cfg.expected_universe_count is not None and cfg.expected_universe_count < 1:
        raise InputError("--expected-universe-count must be >= 1")
    freshness = cfg.authoritative_source_freshness or {}
    if cfg.require_authoritative_source_freshness:
        if freshness.get("contract_version") != "PNCP_CONTRACT_FRESHNESS/1.0":
            raise InputError("authoritative PNCP freshness contract missing or unsupported")
        if freshness.get("status") != "FRESH":
            raise InputError(
                "authoritative PNCP freshness must be FRESH before export; "
                f"observed={freshness.get('status') or 'MISSING'}"
            )
        try:
            expires_at = datetime.fromisoformat(str(freshness.get("expires_at") or "").replace("Z", "+00:00"))
        except ValueError as exc:
            raise InputError("authoritative PNCP freshness expires_at missing or invalid") from exc
        if expires_at <= datetime.now(UTC):
            raise InputError("authoritative PNCP freshness expired before export")


def _encode_chunk(feed: dict[str, Any]) -> bytes:
    # Canonical serialization for stable content hashes (resume/idempotency).
    text = json.dumps(feed, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
    return text.encode("utf-8")


def _encoded_lead_item_size(lead: dict[str, Any]) -> int:
    """Exact byte contribution of one lead inside an indented ``leads`` array."""
    raw = json.dumps(lead, ensure_ascii=False, indent=2, sort_keys=True, default=str).encode("utf-8")
    # ``leads`` is a top-level value, so every line of each array item is
    # shifted four spaces relative to the standalone representation.
    return len(raw) + 4 * (raw.count(b"\n") + 1)


def _provisional_chunk_size(
    *,
    lead_item_bytes: int,
    lead_count: int,
    source: dict[str, Any],
    generated_at: str,
    cursor: str,
    chunk_index: int,
) -> int:
    """Measure a provisional chunk in O(1) after each lead is encoded once."""
    envelope = {
        "schema_version": SCHEMA_OUTREACH,
        "generated_at": generated_at,
        "source": source,
        "pagination": {
            "cursor": cursor,
            "next_cursor": None,
            "has_more": False,
            "chunk_index": chunk_index,
        },
        "leads": [],
    }
    empty_size = len(_encode_chunk(envelope))
    if lead_count == 0:
        return empty_size
    # Replace the two bytes of ``[]`` with the exact pretty-printed array:
    # "[\n" + indented items joined by ",\n" + "\n  ]".
    array_size = 2 + lead_item_bytes + (2 * (lead_count - 1)) + 4
    return empty_size - 2 + array_size


def _decision_cursor(lead: dict[str, Any]) -> str:
    return "|".join(
        (
            str(lead.get("target_fit_source_watermark") or ""),
            str(lead.get("target_fit_computed_at") or ""),
            str((lead.get("company") or {}).get("cnpj14") or ""),
        )
    )


def _parse_timestamp(value: Any, *, field: str, cnpj: str) -> datetime:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InputError(f"invalid {field} timestamp for {cnpj}: {text!r}") from exc
    if parsed.tzinfo is None:
        raise InputError(f"timezone required in {field} for {cnpj}: {text!r}")
    return parsed.astimezone(UTC)


def _rfc3339_timestamp(value: Any, *, field: str, cnpj: str) -> str:
    """Return the contract timestamp in canonical UTC RFC 3339 form."""
    return _parse_timestamp(value, field=field, cnpj=cnpj).isoformat().replace("+00:00", "Z")


def _normalize_authoritative_timestamps(leads: list[dict[str, Any]]) -> None:
    """Normalize database datetime strings before schema serialization and hashing."""
    for lead in leads:
        cnpj = str((lead.get("company") or {}).get("cnpj14") or "")
        for field in ("target_fit_source_watermark", "target_fit_computed_at"):
            lead[field] = _rfc3339_timestamp(lead.get(field), field=field, cnpj=cnpj)


def _attach_contractor_roles(leads: list[dict[str, Any]], *, run_id: str, observed_at: str) -> None:
    """Bind typed supplier/buyer truth at the canonical publication boundary."""
    for lead in leads:
        company = lead.get("company") if isinstance(lead.get("company"), dict) else {}
        contracts = lead.get("contracts") if isinstance(lead.get("contracts"), list) else []
        lead["contractor_role"] = project_contractor_role(
            company.get("cnpj14"),
            contracts,
            source_run_id=run_id,
            observed_at=observed_at,
        )


def _decision_order_key(lead: dict[str, Any]) -> tuple[datetime, datetime, str, str]:
    cnpj = str((lead.get("company") or {}).get("cnpj14") or "")
    return (
        _parse_timestamp(
            lead.get("target_fit_source_watermark"),
            field="target_fit_source_watermark",
            cnpj=cnpj,
        ),
        _parse_timestamp(
            lead.get("target_fit_computed_at"),
            field="target_fit_computed_at",
            cnpj=cnpj,
        ),
        cnpj,
        str(lead.get("source_lead_id") or ""),
    )


def _assert_authoritative_leads(leads: list[dict[str, Any]]) -> dict[str, Any]:
    required = (
        "target_fit_class",
        "target_fit_fresh",
        "target_fit_version",
        "target_fit_computed_at",
        "target_fit_source_watermark",
        "target_fit_evidence_ids",
        "target_fit_send_tier",
        "email_send_ready",
    )
    cursors: list[str] = []
    order_keys: list[tuple[datetime, datetime, str, str]] = []
    seen: set[str] = set()
    for lead in leads:
        cnpj = str((lead.get("company") or {}).get("cnpj14") or "")
        missing = [field for field in required if field not in lead or lead[field] is None]
        if missing:
            raise InputError(f"authoritative target-fit decision incomplete for {cnpj}: {missing}")
        if not str(lead["target_fit_class"]):
            raise InputError(f"authoritative target-fit class empty for {cnpj}")
        if not str(lead["target_fit_version"]):
            raise InputError(f"authoritative target-fit version empty for {cnpj}")
        if not str(lead["target_fit_computed_at"]):
            raise InputError(f"authoritative target-fit computed_at empty for {cnpj}")
        if not str(lead["target_fit_source_watermark"]):
            raise InputError(f"authoritative target-fit watermark empty for {cnpj}")
        if cnpj in seen:
            raise InputError(f"duplicate authoritative decision for CNPJ {cnpj}")
        seen.add(cnpj)
        cursors.append(_decision_cursor(lead))
        order_keys.append(_decision_order_key(lead))
    monotonic = all(a <= b for a, b in zip(order_keys, order_keys[1:]))
    if not monotonic:
        raise InputError("target-fit source watermarks are not monotonically ordered")
    return {
        "key": [
            "target_fit_source_watermark",
            "target_fit_computed_at",
            "company.cnpj14",
        ],
        "direction": "ascending",
        "watermarks_monotonic": True,
        "first_cursor": cursors[0] if cursors else None,
        "last_cursor": cursors[-1] if cursors else None,
    }


def _chunk_leads(
    leads: list[dict[str, Any]],
    *,
    max_leads: int,
    max_bytes: int,
    source: dict[str, Any],
    generated_at: str,
) -> list[tuple[list[dict[str, Any]], dict[str, Any]]]:
    """Return list of (lead_slice, pagination_stub_without_hash)."""
    if not leads:
        return [([], {"cursor": None, "next_cursor": None, "has_more": False, "chunk_index": 0})]

    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_item_bytes = 0
    for lead in leads:
        item_size = _encoded_lead_item_size(lead)
        trial_count = len(current) + 1
        size = _provisional_chunk_size(
            lead_item_bytes=current_item_bytes + item_size,
            lead_count=trial_count,
            source=source,
            generated_at=generated_at,
            cursor=_decision_cursor(current[0] if current else lead),
            chunk_index=len(chunks),
        )
        over_count = trial_count > max_leads
        over_bytes = size > max_bytes and len(current) >= 1
        if (over_count or over_bytes) and current:
            chunks.append(current)
            current = [lead]
            current_item_bytes = item_size
        else:
            current.append(lead)
            current_item_bytes += item_size
    if current:
        chunks.append(current)

    result: list[tuple[list[dict[str, Any]], dict[str, Any]]] = []
    for idx, slice_leads in enumerate(chunks):
        cursor = _decision_cursor(slice_leads[0]) if slice_leads else None
        has_more = idx < len(chunks) - 1
        next_cursor = _decision_cursor(chunks[idx + 1][0]) if has_more else None
        pagination = {
            "cursor": cursor,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "chunk_index": idx,
        }
        result.append((slice_leads, pagination))
    return result


def export_outreach(cfg: ExportConfig) -> dict[str, Any]:
    """Export chunked confenge.outreach.v1 feed. Idempotent for same inputs."""
    validate_inputs(cfg)
    out = cfg.out_dir
    out.mkdir(parents=True, exist_ok=True)

    universe_rows = read_jsonl(cfg.universe, label="--universe")
    intel_rows = read_jsonl(cfg.account_intelligence, label="--account-intelligence")
    contact_rows = read_jsonl(cfg.contacts, label="--contacts")

    if not universe_rows:
        raise InputError("--universe has no records; refusing empty shallow export")

    if cfg.limit is not None and cfg.limit < 0:
        raise InputError("--limit must be >= 0")

    snapshot_hash = _snapshot_hash(
        cfg.universe,
        cfg.account_intelligence,
        cfg.contacts,
        cfg.target_fit_snapshot,
    )
    freshness = dict(cfg.authoritative_source_freshness or {})
    freshness_hash = content_hash_obj(freshness) if freshness else None
    run_id = _run_id(snapshot_hash, cfg.profile_id, cfg.profile_version, freshness_hash)
    # Deterministic resume: reuse generated_at/repo_sha from prior manifest when
    # snapshot_hash matches so re-export yields identical chunk hashes.
    prior_manifest_path = out / "manifest.json"
    prior: dict[str, Any] = {}
    if prior_manifest_path.is_file():
        try:
            prior = json.loads(prior_manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            prior = {}
    prior_source = prior.get("source") if isinstance(prior.get("source"), dict) else {}
    same_snapshot = (
        str(prior_source.get("snapshot_hash") or "") == snapshot_hash
        and prior_source.get("authoritative_freshness_hash") == freshness_hash
    )
    if cfg.generated_at:
        generated_at = cfg.generated_at
    elif same_snapshot and prior.get("generated_at"):
        generated_at = str(prior["generated_at"])
    else:
        generated_at = _utcnow()
    datalake_watermark = str(cfg.datalake_watermark or generated_at)
    _parse_timestamp(
        datalake_watermark,
        field="datalake_watermark",
        cnpj="authoritative-snapshot",
    )
    if cfg.repo_sha is not None:
        repo_sha = cfg.repo_sha
    elif same_snapshot and prior_source.get("repo_sha"):
        repo_sha = str(prior_source["repo_sha"])
    else:
        repo_sha = _git_sha()

    if cfg.target_fit_snapshot is not None:
        target_fit_rows = read_jsonl(cfg.target_fit_snapshot, label="--target-fit-snapshot")
        # Seed every addressable company as an explicit missing tombstone.  The
        # authoritative snapshot then overwrites the companies it contains;
        # omission can never preserve a CONFIRMED decision from an older feed.
        published_index = build_published_index_from_rows(
            [{"cnpj14": row.get("cnpj14") or row.get("cnpj")} for row in universe_rows],
            computed_at=generated_at,
            source_watermark=generated_at,
        )
        try:
            published_index.update(
                build_published_index_from_rows(
                    target_fit_rows,
                    computed_at=generated_at,
                    source_watermark=generated_at,
                    require_authoritative_metadata=cfg.require_authoritative_target_fit_metadata,
                )
            )
        except ValueError as exc:
            raise InputError(str(exc)) from exc
    else:
        target_fit_rows = universe_rows
        try:
            published_index = build_published_index_from_rows(
                target_fit_rows,
                computed_at=generated_at,
                source_watermark=generated_at,
                require_authoritative_metadata=cfg.require_authoritative_target_fit_metadata,
            )
        except ValueError as exc:
            raise InputError(str(exc)) from exc
    leads = build_leads(
        universe_rows,
        intel_rows,
        contact_rows,
        published_index=published_index,
        datalake_watermark=datalake_watermark,
    )
    _attach_contractor_roles(leads, run_id=run_id, observed_at=datalake_watermark)
    _normalize_authoritative_timestamps(leads)
    leads.sort(key=_decision_order_key)
    if cfg.limit is not None:
        leads = leads[: cfg.limit]
    ordering = _assert_authoritative_leads(leads)

    source = {
        "system": cfg.system,
        "run_id": run_id,
        "snapshot_hash": snapshot_hash,
        "repo_sha": repo_sha,
        "profile_id": cfg.profile_id,
        "profile_version": cfg.profile_version,
        "datalake_watermark": datalake_watermark,
        "authoritative_freshness": freshness or None,
        "authoritative_freshness_hash": freshness_hash,
    }

    chunk_specs = _chunk_leads(
        leads,
        max_leads=cfg.max_leads_per_chunk,
        max_bytes=cfg.max_bytes_per_chunk,
        source=source,
        generated_at=generated_at,
    )

    chunk_meta: list[dict[str, Any]] = []
    for slice_leads, pagination in chunk_specs:
        # First pass: compute content hash of leads+source (stable) for hashes block.
        leads_hash = content_hash_obj({"leads": slice_leads, "source": source})
        pagination = {
            **pagination,
            "content_hash": leads_hash,
            "hashes": {
                "leads": leads_hash,
                "snapshot": snapshot_hash,
            },
        }
        feed = {
            "schema_version": SCHEMA_OUTREACH,
            "generated_at": generated_at,
            "source": source,
            "pagination": pagination,
            "leads": slice_leads,
        }
        raw = _encode_chunk(feed)
        file_hash = hashlib.sha256(raw).hexdigest()
        idx = int(pagination["chunk_index"])
        filename = f"chunk_{idx:04d}.json"
        path = out / filename
        # Resume/idempotency: if file exists with same hash, leave it; else overwrite.
        if path.is_file():
            existing = path.read_bytes()
            if hashlib.sha256(existing).hexdigest() == file_hash:
                chunk_meta.append(
                    {
                        "file": filename,
                        "chunk_index": idx,
                        "content_hash": file_hash,
                        "leads_hash": leads_hash,
                        "lead_count": len(slice_leads),
                        "cursor": pagination.get("cursor"),
                        "next_cursor": pagination.get("next_cursor"),
                        "has_more": pagination.get("has_more"),
                        "status": "unchanged",
                    }
                )
                continue
        path.write_bytes(raw)
        chunk_meta.append(
            {
                "file": filename,
                "chunk_index": idx,
                "content_hash": file_hash,
                "leads_hash": leads_hash,
                "lead_count": len(slice_leads),
                "cursor": pagination.get("cursor"),
                "next_cursor": pagination.get("next_cursor"),
                "has_more": pagination.get("has_more"),
                "status": "written",
            }
        )

    # Remove stale chunks from previous larger runs with different snapshot (same out dir).
    # Only delete chunk_*.json not in this run when snapshot changes — safer: delete extras.
    keep = {m["file"] for m in chunk_meta}
    for stale in sorted(out.glob("chunk_*.json")):
        if stale.name not in keep:
            # Only remove if manifest will supersede; keep if same snapshot resume partial
            stale.unlink(missing_ok=True)

    deacts = list(cfg.deactivations or [])
    coverage_complete = bool(
        cfg.expected_universe_count is not None
        and cfg.limit is None
        and len(leads) == len(universe_rows) == cfg.expected_universe_count
    )
    manifest = {
        "schema_version": "confenge.outreach.manifest.v1",
        "module_version": MODULE_VERSION,
        "generated_at": generated_at,
        "source": source,
        "inputs": {
            "universe": str(cfg.universe.resolve()),
            "account_intelligence": str(cfg.account_intelligence.resolve()),
            "contacts": str(cfg.contacts.resolve()),
            "target_fit_snapshot": (
                str(cfg.target_fit_snapshot.resolve())
                if cfg.target_fit_snapshot is not None
                else str(cfg.universe.resolve())
            ),
        },
        "lead_count": len(leads),
        "chunk_count": len(chunk_meta),
        "max_leads_per_chunk": cfg.max_leads_per_chunk,
        "max_bytes_per_chunk": cfg.max_bytes_per_chunk,
        "limit": cfg.limit,
        "authoritative_target_fit": {
            "source": "target_fit_snapshot" if cfg.target_fit_snapshot is not None else "universe_embedded_snapshot",
            "full_decision_count": len(leads),
            "universe_count": len(universe_rows),
            "declared_universe_count": cfg.expected_universe_count,
            "coverage_complete": coverage_complete,
            "omission_preserves_authorization": not coverage_complete,
            "ordering": ordering,
        },
        "authoritative_source_freshness": freshness or None,
        "chunks": chunk_meta,
        # Approach B: explicit deactivation delta (idempotent; Warmbly applies without DB coupling)
        "deactivations": deacts,
        "deactivation_count": len(deacts),
        "hashes": {
            "snapshot": snapshot_hash,
            "manifest_inputs": content_hash_obj(
                {
                    "snapshot": snapshot_hash,
                    "run_id": run_id,
                    "chunks": [m["content_hash"] for m in chunk_meta],
                    "deactivations": deacts,
                }
            ),
        },
    }
    manifest_path = out / "manifest.json"
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n").encode(
        "utf-8"
    )
    manifest_path.write_bytes(manifest_bytes)
    manifest["manifest_content_hash"] = hashlib.sha256(manifest_bytes).hexdigest()
    # rewrite with self hash
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n").encode(
        "utf-8"
    )
    manifest_path.write_bytes(manifest_bytes)

    return {
        "ok": True,
        "out_dir": str(out.resolve()),
        "run_id": run_id,
        "snapshot_hash": snapshot_hash,
        "lead_count": len(leads),
        "chunk_count": len(chunk_meta),
        "manifest": str(manifest_path.resolve()),
        "chunks": chunk_meta,
    }
