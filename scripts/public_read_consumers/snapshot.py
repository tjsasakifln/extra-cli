"""Last-known-good snapshots, invalidation and version diffs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.public_read_consumers.gates import (
    REASON_GATE_FAILED,
    REASON_LIVE_ABSENT,
    REASON_LKG_EXPIRED,
    expires_at,
    lkg_usable,
)
from scripts.public_read_consumers.hashutil import attach_hash, canonical_dumps, content_hash

CURRENT = "current"
LKG = "lkg"
PREVIOUS = "previous"
MANIFEST = "manifest.json"
MAX_LKG_HOURS = 168


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def snapshot_root(output_dir: str | Path) -> Path:
    return Path(output_dir)


def current_dir(output_dir: str | Path) -> Path:
    return snapshot_root(output_dir) / CURRENT


def lkg_dir(output_dir: str | Path) -> Path:
    return snapshot_root(output_dir) / LKG


def load_manifest(directory: Path) -> dict[str, Any] | None:
    return _load_json(directory / MANIFEST)


def diff_manifests(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    left_hash = (left or {}).get("content_hash")
    right_hash = (right or {}).get("content_hash")
    left_keys = set((left or {}).keys())
    right_keys = set((right or {}).keys())
    return {
        "equal": left_hash is not None and left_hash == right_hash,
        "left_content_hash": left_hash,
        "right_content_hash": right_hash,
        "added_keys": sorted(right_keys - left_keys),
        "removed_keys": sorted(left_keys - right_keys),
        "changed": left_hash != right_hash,
    }


def invalidation_keys_hit(previous: dict[str, Any] | None, current: dict[str, Any]) -> list[str]:
    if not previous:
        return []
    watched = current.get("freshness", {}).get("invalidation_keys") or ()
    hits: list[str] = []
    for key in watched:
        if previous.get(key) != current.get(key):
            hits.append(str(key))
    prev_hash = previous.get("content_hash")
    if prev_hash and prev_hash != current.get("content_hash") and "content_hash" not in hits:
        hits.append("content_hash")
    return hits


def label_lkg(manifest: dict[str, Any], *, source_as_of: str | None) -> dict[str, Any]:
    labeled = {
        **manifest,
        "last_known_good": True,
        "lkg_max_age_hours": MAX_LKG_HOURS,
        "lkg_expires_at": expires_at(
            source_as_of or manifest.get("source_as_of") or manifest.get("as_of"), max_age_hours=MAX_LKG_HOURS
        ),
    }
    return attach_hash({key: value for key, value in labeled.items() if key != "content_hash"})


def should_publish_current(gate_ok: bool, *, live: bool, official_live_present: bool) -> tuple[bool, str | None]:
    if live and not official_live_present:
        return False, REASON_LIVE_ABSENT
    if not gate_ok:
        return False, REASON_GATE_FAILED
    return True, None


def preserve_or_fail(
    *,
    output_dir: str | Path,
    now: str,
    gate_ok: bool,
    live: bool,
    official_live_present: bool,
) -> dict[str, Any]:
    publish, reason = should_publish_current(gate_ok, live=live, official_live_present=official_live_present)
    existing_lkg = load_manifest(lkg_dir(output_dir))
    if publish:
        return {"action": "publish", "reason_code": None, "lkg": existing_lkg}
    if existing_lkg and lkg_usable(existing_lkg, now=now):
        return {"action": "preserve_lkg", "reason_code": reason, "lkg": existing_lkg}
    if existing_lkg:
        return {"action": "fail", "reason_code": REASON_LKG_EXPIRED, "lkg": existing_lkg}
    return {"action": "fail", "reason_code": reason or REASON_GATE_FAILED, "lkg": None}


def write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def retain_previous(path: Path, new_document: dict[str, Any]) -> Path | None:
    if not path.is_file():
        return None
    previous = _load_json(path)
    if not previous:
        return None
    if previous.get("content_hash") == new_document.get("content_hash"):
        return None
    dest = path.parent / PREVIOUS / f"{path.stem}.{previous.get('content_hash') or content_hash(previous)}{path.suffix}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(canonical_dumps(previous).encode("utf-8"))
    return dest
