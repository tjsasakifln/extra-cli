"""Atomic feed publication: build temp → validate → hash → promote.

Never leave Warmbly observing partial chunks with a new manifest.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


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


def atomic_publish_directory(
    build_dir: Path,
    publish_dir: Path,
    *,
    current_name: str = "current",
) -> dict[str, Any]:
    """Atomically promote build_dir contents to publish_dir/current via rename.

    Layout:
      publish_dir/
        current -> releases/<run_id>   (symlink, atomic replace)
        releases/<run_id>/...
    If build_dir already contains a complete feed (manifest + chunks), we copy
    into a new release directory then swap the symlink.
    """
    build_dir = Path(build_dir)
    publish_dir = Path(publish_dir)
    publish_dir.mkdir(parents=True, exist_ok=True)
    releases = publish_dir / "releases"
    releases.mkdir(parents=True, exist_ok=True)

    manifest_path = build_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"no manifest.json in {build_dir}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
    run_id = str(source.get("run_id") or "run-unknown")
    # Validate chunks listed in manifest exist and match hashes when present
    chunks = manifest.get("chunks") or []
    for ch in chunks:
        if not isinstance(ch, dict):
            continue
        fname = ch.get("file")
        if not fname:
            continue
        fp = build_dir / str(fname)
        if not fp.is_file():
            raise FileNotFoundError(f"manifest references missing chunk {fname}")
        expected = ch.get("content_hash")
        if expected:
            actual = _sha256_file(fp)
            if actual != expected:
                raise ValueError(f"chunk hash mismatch for {fname}: {actual} != {expected}")

    release_dir = releases / run_id
    if release_dir.exists():
        shutil.rmtree(release_dir)
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
        _fsync_dir(tmp)
        os.replace(str(tmp), str(release_dir))
        _fsync_dir(releases)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise

    # Atomic symlink swap: current -> releases/<run_id>
    current = publish_dir / current_name
    link_tmp = publish_dir / f".{current_name}.tmp-{run_id}"
    if link_tmp.exists() or link_tmp.is_symlink():
        link_tmp.unlink()
    # Relative symlink for portability
    rel_target = Path("releases") / run_id
    link_tmp.symlink_to(rel_target, target_is_directory=True)
    os.replace(str(link_tmp), str(current))
    _fsync_dir(publish_dir)

    return {
        "ok": True,
        "publish_dir": str(publish_dir.resolve()),
        "current": str(current.resolve()),
        "release_dir": str(release_dir.resolve()),
        "run_id": run_id,
        "snapshot_hash": source.get("snapshot_hash"),
        "chunk_count": len(chunks),
    }
