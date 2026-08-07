"""Path-based confenge.outreach.v1 exporter with deterministic chunking + manifest."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
            [git_bin, "rev-parse", "--short=12", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return out.strip() or "unknown"
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return "unknown"


def _snapshot_hash(universe: Path, intel: Path, contacts: Path) -> str:
    h = hashlib.sha256()
    for p in (universe, intel, contacts):
        h.update(p.name.encode())
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def _run_id(snapshot_hash: str, profile_id: str, profile_version: str) -> str:
    raw = f"{snapshot_hash}|{profile_id}|{profile_version}|{MODULE_VERSION}"
    return "run-" + hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class ExportConfig:
    universe: Path
    account_intelligence: Path
    contacts: Path
    out_dir: Path
    limit: int | None = None
    max_leads_per_chunk: int = DEFAULT_MAX_LEADS_PER_CHUNK
    max_bytes_per_chunk: int = DEFAULT_MAX_BYTES_PER_CHUNK
    profile_id: str = DEFAULT_PROFILE_ID
    profile_version: str = DEFAULT_PROFILE_VERSION
    system: str = DEFAULT_SYSTEM
    generated_at: str | None = None  # inject for deterministic tests
    repo_sha: str | None = None


def validate_inputs(cfg: ExportConfig) -> None:
    """Fail-closed: all three required inputs must exist and be readable."""
    require_readable_file(cfg.universe, label="--universe")
    require_readable_file(cfg.account_intelligence, label="--account-intelligence")
    require_readable_file(cfg.contacts, label="--contacts")
    if cfg.max_leads_per_chunk < 1:
        raise InputError("--max-leads-per-chunk must be >= 1")
    if cfg.max_bytes_per_chunk < 1024:
        raise InputError("--max-bytes-per-chunk must be >= 1024")


def _encode_chunk(feed: dict[str, Any]) -> bytes:
    # Canonical serialization for stable content hashes (resume/idempotency).
    text = json.dumps(feed, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
    return text.encode("utf-8")


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
    for lead in leads:
        trial = current + [lead]
        # Measure size with a provisional feed envelope.
        provisional = {
            "schema_version": SCHEMA_OUTREACH,
            "generated_at": generated_at,
            "source": source,
            "pagination": {
                "cursor": current[0]["company"]["cnpj14"] if current else lead["company"]["cnpj14"],
                "next_cursor": None,
                "has_more": False,
                "chunk_index": len(chunks),
            },
            "leads": trial,
        }
        size = len(_encode_chunk(provisional))
        over_count = len(trial) > max_leads
        over_bytes = size > max_bytes and len(current) >= 1
        if (over_count or over_bytes) and current:
            chunks.append(current)
            current = [lead]
        else:
            current = trial
    if current:
        chunks.append(current)

    result: list[tuple[list[dict[str, Any]], dict[str, Any]]] = []
    for idx, slice_leads in enumerate(chunks):
        cursor = slice_leads[0]["company"]["cnpj14"] if slice_leads else None
        has_more = idx < len(chunks) - 1
        next_cursor = chunks[idx + 1][0]["company"]["cnpj14"] if has_more else None
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

    leads = build_leads(universe_rows, intel_rows, contact_rows)
    if cfg.limit is not None:
        if cfg.limit < 0:
            raise InputError("--limit must be >= 0")
        leads = leads[: cfg.limit]

    snapshot_hash = _snapshot_hash(cfg.universe, cfg.account_intelligence, cfg.contacts)
    run_id = _run_id(snapshot_hash, cfg.profile_id, cfg.profile_version)
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
    same_snapshot = str(prior_source.get("snapshot_hash") or "") == snapshot_hash
    if cfg.generated_at:
        generated_at = cfg.generated_at
    elif same_snapshot and prior.get("generated_at"):
        generated_at = str(prior["generated_at"])
    else:
        generated_at = _utcnow()
    if cfg.repo_sha is not None:
        repo_sha = cfg.repo_sha
    elif same_snapshot and prior_source.get("repo_sha"):
        repo_sha = str(prior_source["repo_sha"])
    else:
        repo_sha = _git_sha()

    source = {
        "system": cfg.system,
        "run_id": run_id,
        "snapshot_hash": snapshot_hash,
        "repo_sha": repo_sha,
        "profile_id": cfg.profile_id,
        "profile_version": cfg.profile_version,
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

    manifest = {
        "schema_version": "confenge.outreach.manifest.v1",
        "module_version": MODULE_VERSION,
        "generated_at": generated_at,
        "source": source,
        "inputs": {
            "universe": str(cfg.universe.resolve()),
            "account_intelligence": str(cfg.account_intelligence.resolve()),
            "contacts": str(cfg.contacts.resolve()),
        },
        "lead_count": len(leads),
        "chunk_count": len(chunk_meta),
        "max_leads_per_chunk": cfg.max_leads_per_chunk,
        "max_bytes_per_chunk": cfg.max_bytes_per_chunk,
        "limit": cfg.limit,
        "chunks": chunk_meta,
        "hashes": {
            "snapshot": snapshot_hash,
            "manifest_inputs": content_hash_obj(
                {
                    "snapshot": snapshot_hash,
                    "run_id": run_id,
                    "chunks": [m["content_hash"] for m in chunk_meta],
                }
            ),
        },
    }
    manifest_path = out / "manifest.json"
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
    ).encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)
    manifest["manifest_content_hash"] = hashlib.sha256(manifest_bytes).hexdigest()
    # rewrite with self hash
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
    ).encode("utf-8")
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
