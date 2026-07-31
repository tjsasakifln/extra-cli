"""ExportBundle: checksummed package of run deliverables."""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.command_center.run_manifest import load_manifest, sha256_file, validate_manifest


def build_export_bundle(
    run_dir: Path,
    *,
    out_path: Path | None = None,
    include_logs: bool = False,
) -> dict[str, Any]:
    """Create a ZIP bundle with declared artifacts + manifest + checksums.

    Fail-closed: requires valid run-manifest.json.
    """
    run_dir = Path(run_dir)
    manifest_path = run_dir / "run-manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("run-manifest.json ausente — não é possível publicar o pacote.")
    mf = load_manifest(manifest_path)
    errors = validate_manifest(mf)
    if errors:
        raise ValueError("run-manifest inválido: " + "; ".join(errors))

    out_path = Path(out_path or (run_dir / f"export-bundle-{mf['run_id'][:8]}.zip"))
    checksums: dict[str, str] = {}
    members: list[tuple[Path, str]] = []

    for art in mf.get("artifacts") or []:
        p = Path(art["path"])
        if not p.is_file():
            # try relative to run_dir
            alt = run_dir / p.name
            if alt.is_file():
                p = alt
            else:
                raise FileNotFoundError(f"Artefato declarado ausente: {art.get('path')}")
        if not include_logs and art.get("role") == "log":
            continue
        arc = p.name
        # zip-slip defense: only basename
        if ".." in arc or arc.startswith("/") or "\\" in arc:
            raise ValueError(f"Nome de artefato inseguro: {arc}")
        members.append((p, arc))
        checksums[arc] = sha256_file(p)

    # always include manifest
    if "run-manifest.json" not in checksums:
        members.append((manifest_path, "run-manifest.json"))
        checksums["run-manifest.json"] = sha256_file(manifest_path)

    bundle_meta = {
        "schema_version": "1.0.0",
        "run_id": mf["run_id"],
        "created_at": datetime.now(UTC).isoformat(),
        "checksums": checksums,
        "members": [m[1] for m in members],
        "workflow_id": mf.get("workflow_id"),
        "capability_id": mf.get("capability_id"),
        "limitations": mf.get("limitations") or [],
    }
    meta_path = run_dir / "export-bundle-manifest.json"
    meta_path.write_text(json.dumps(bundle_meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    members.append((meta_path, "export-bundle-manifest.json"))
    checksums["export-bundle-manifest.json"] = sha256_file(meta_path)
    bundle_meta["checksums"] = checksums
    meta_path.write_text(json.dumps(bundle_meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fs_path, arc in members:
            # only write basename into zip root
            zf.write(fs_path, arcname=Path(arc).name)

    return {
        "bundle_path": str(out_path),
        "checksums": checksums,
        "run_id": mf["run_id"],
        "members": [m[1] for m in members],
        "sha256": sha256_file(out_path),
    }
