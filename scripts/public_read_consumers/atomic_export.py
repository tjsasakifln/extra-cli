"""Staging + fsync + rename export. Invalid output never replaces LKG."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

LKG = "lkg"
STAGING_PREFIX = ".staging-"


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_tree_atomic(destination: Path, files: dict[str, bytes]) -> Path:
    """Write ``files`` into ``destination`` via a sibling staging directory.

    Existing destination is replaced only after every file is fsynced.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f"{STAGING_PREFIX}{destination.name}.{os.getpid()}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        for relative, payload in files.items():
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            _fsync_file(target)
        _fsync_dir(staging)
        if destination.exists():
            backup = destination.parent / f"{destination.name}.prev"
            if backup.exists():
                shutil.rmtree(backup)
            destination.rename(backup)
            staging.rename(destination)
            shutil.rmtree(backup, ignore_errors=True)
        else:
            staging.rename(destination)
        _fsync_dir(destination.parent)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination


def copy_lkg(source: Path, *, root: Path | None = None) -> Path:
    dest = (root or source) / LKG
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source, dest, ignore=shutil.ignore_patterns(LKG, ".staging-*", "*.prev"))
    _fsync_dir(dest)
    return dest
