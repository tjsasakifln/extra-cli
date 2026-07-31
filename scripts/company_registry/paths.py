"""Filesystem layout for the official registry mirror (outside Git bulk)."""

from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def registry_root() -> Path:
    env = os.environ.get("COMPANY_REGISTRY_ROOT") or os.environ.get(
        "CONFENGE_COMPANY_REGISTRY_ROOT"
    )
    if env:
        return Path(env)
    return _ROOT / "data" / "company_registry"


def raw_dir(release_id: str | None = None) -> Path:
    base = registry_root() / "raw"
    return base / release_id if release_id else base


def staging_dir(release_id: str | None = None) -> Path:
    base = registry_root() / "staging"
    return base / release_id if release_id else base


def active_dir() -> Path:
    return registry_root() / "active"


def releases_dir() -> Path:
    return registry_root() / "releases"


def locks_dir() -> Path:
    return registry_root() / "locks"


def manifests_dir() -> Path:
    return registry_root() / "manifests"


def ensure_layout() -> dict[str, str]:
    paths = {
        "root": registry_root(),
        "raw": raw_dir(),
        "staging": staging_dir(),
        "active": active_dir(),
        "releases": releases_dir(),
        "locks": locks_dir(),
        "manifests": manifests_dir(),
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    return {k: str(v) for k, v in paths.items()}


def db_path_for_release(release_id: str, *, staging: bool = False) -> Path:
    if staging:
        p = staging_dir(release_id)
    else:
        p = releases_dir() / release_id
    p.mkdir(parents=True, exist_ok=True)
    return p / "registry.sqlite"


def active_pointer_path() -> Path:
    return active_dir() / "ACTIVE_RELEASE.json"


def manifest_path(release_id: str) -> Path:
    return manifests_dir() / f"{release_id}.json"
