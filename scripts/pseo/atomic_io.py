"""Atomic snapshot write: temp dir → validate → promote; preserve prior on failure."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any


def write_snapshot_atomic(
    final_dir: Path,
    files: dict[str, str],
    *,
    validate: Callable[[Path], dict[str, Any]] | None = None,
    pointer_name: str = "CURRENT.json",
    dataset_hash: str | None = None,
) -> dict[str, Any]:
    """Write all files under a temp directory, validate, then promote.

    `files` maps relative name → text content.
    """
    final_dir = Path(final_dir)
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    versioned = final_dir
    if dataset_hash:
        versioned = final_dir.parent / f"snapshot-{dataset_hash[:16]}"
        versioned.mkdir(parents=True, exist_ok=True)

    tmp_root = Path(
        tempfile.mkdtemp(prefix="pseo-export-", dir=str(final_dir.parent))
    )
    try:
        for name, text in files.items():
            if ".." in name or name.startswith(("/", "\\")):
                raise ValueError(f"illegal file name: {name}")
            target = tmp_root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            # flush via reopen
            with open(target, "rb") as fh:
                os.fsync(fh.fileno())

        if validate is not None:
            result = validate(tmp_root)
            if not result.get("ok"):
                raise RuntimeError(f"validation failed before promote: {result.get('errors')}")

        # Promote: replace versioned dir contents atomically as possible
        if versioned.exists():
            backup = versioned.with_name(versioned.name + f".bak-{int(time.time())}")
            if any(versioned.iterdir()):
                # move aside previous
                shutil.move(str(versioned), str(backup))
                versioned.mkdir(parents=True, exist_ok=True)
        else:
            versioned.mkdir(parents=True, exist_ok=True)
            backup = None

        for name in files:
            src = tmp_root / name
            dest = versioned / name
            os.replace(src, dest)

        # Pointer portable (no symlink required)
        pointer = {
            "dataset_hash": dataset_hash,
            "path": str(versioned.resolve()),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "files": sorted(files.keys()),
        }
        pointer_path = final_dir.parent / pointer_name if dataset_hash else final_dir / pointer_name
        if dataset_hash:
            # when versioned under parent, also mirror into final_dir for convenience
            final_dir.mkdir(parents=True, exist_ok=True)
            for name in files:
                src = versioned / name
                dest = final_dir / name
                shutil.copy2(src, dest)
            pointer_path = final_dir / pointer_name
        pointer_path.write_text(
            json.dumps(pointer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return {
            "ok": True,
            "dir": str(versioned),
            "pointer": str(pointer_path),
            "backup": str(backup) if backup else None,
        }
    except Exception:
        # leave prior snapshot intact; tmp cleaned below
        raise
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
