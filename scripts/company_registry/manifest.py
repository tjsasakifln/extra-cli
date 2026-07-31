"""Immutable release manifest read/write helpers."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.company_registry.models import ReleaseStatus, empty_release_manifest
from scripts.company_registry.paths import ensure_layout, manifest_path


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def git_commit() -> str | None:
    try:
        import shutil

        git = shutil.which("git")
        if not git:
            return os.environ.get("GITHUB_SHA")
        out = subprocess.check_output(  # noqa: S603
            [git, "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return os.environ.get("GITHUB_SHA")


def load_manifest(release_id: str) -> dict[str, Any] | None:
    p = manifest_path(release_id)
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save_manifest(manifest: dict[str, Any], *, immutable_when_active: bool = True) -> Path:
    ensure_layout()
    rid = manifest["release_id"]
    p = manifest_path(rid)
    if immutable_when_active and p.is_file():
        existing = json.loads(p.read_text(encoding="utf-8"))
        if existing.get("status") == ReleaseStatus.ACTIVE.value and manifest.get("status") == ReleaseStatus.ACTIVE.value:
            # allow only additive fields via side-car — for true immutability of ACTIVE,
            # refuse full overwrite of core identity fields
            for key in ("source_urls", "sha256", "published_reference_date", "row_counts"):
                if key in existing and existing[key] and manifest.get(key) != existing[key]:
                    # still allow status machine updates pre-active; once active freeze hashes
                    if key in ("sha256", "source_urls"):
                        manifest[key] = existing[key]
    if "code_commit" not in manifest or not manifest["code_commit"]:
        manifest["code_commit"] = git_commit()
    p.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def new_manifest(release_id: str, **kwargs: Any) -> dict[str, Any]:
    m = empty_release_manifest(release_id, code_commit=git_commit())
    m.update(kwargs)
    m["discovered_at"] = m.get("discovered_at") or utc_now()
    return m


def set_status(manifest: dict[str, Any], status: str, *, error: str | None = None) -> dict[str, Any]:
    manifest["status"] = status
    if error:
        manifest.setdefault("errors", []).append(error)
    manifest["status_updated_at"] = utc_now()
    return manifest
