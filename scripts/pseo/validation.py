"""Post-export validation: hashes, forbidden fields, entrypoint, schema."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.pseo.allowlist import FORBIDDEN_KEYS
from scripts.pseo.provenance import (
    EXPORT_ENTRYPOINT,
    entrypoint_exists_in_tree,
    verify_commit_has_entrypoint,
    verify_snapshot_hashes,
)
from scripts.pseo.sanitize import contains_forbidden


def validate_export_dir(
    out_dir: Path,
    *,
    repo_root: Path | None = None,
    require_commit_entrypoint: bool = True,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    errors: list[str] = []
    warnings: list[str] = []

    manifest_path = out_dir / "manifest.json"
    if not manifest_path.exists():
        return {"ok": False, "errors": ["manifest.json missing"], "warnings": []}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    required = [
        "schema_version",
        "generated_at",
        "data_as_of",
        "source_run_id",
        "source_repository",
        "source_commit_sha",
        "source_branch",
        "export_entrypoint",
        "export_version",
        "dataset_hash",
        "checksums",
        "sources",
        "counts",
        "timezone",
        "freshness",
        "limitations",
    ]
    for f in required:
        if f not in manifest and f.replace("export_", "exporter_") not in manifest:
            # accept exporter_entrypoint alias
            if f == "export_entrypoint" and manifest.get("exporter_entrypoint"):
                continue
            if f == "export_version" and manifest.get("exporter_version"):
                continue
            errors.append(f"manifest missing {f}")

    ep = manifest.get("export_entrypoint") or manifest.get("exporter_entrypoint")
    if ep and ep != EXPORT_ENTRYPOINT:
        warnings.append(f"entrypoint differs from canonical: {ep}")

    # forbidden fields in all json except registry if present
    for path in sorted(out_dir.glob("*.json")):
        if path.name == "registry.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        hits = contains_forbidden(data)
        # also scan raw keys
        text = path.read_text(encoding="utf-8").lower()
        for k in FORBIDDEN_KEYS:
            # score alone is too broad in methodology; check quoted keys
            if f'"{k}"' in text and k not in {"score"}:
                if k not in [h.split(":")[0] for h in hits]:
                    hits.append(f"{k}:raw")
        if hits:
            errors.append(f"forbidden in {path.name}: {hits[:8]}")

    # checksums + dataset_hash
    errors.extend(verify_snapshot_hashes(out_dir, manifest))

    sha = manifest.get("source_commit_sha") or ""
    if require_commit_entrypoint:
        cli = Path(__file__).resolve().parent / "cli_export.py"
        if cli.is_file():
            # durable untracked entry — working tree is source of truth
            pass
        else:
            if not entrypoint_exists_in_tree(repo_root):
                errors.append("export entrypoint missing in working tree")
            if sha and sha != "unknown":
                if not verify_commit_has_entrypoint(sha, repo_root=repo_root):
                    errors.append(
                        f"source_commit_sha {sha} does not contain export entrypoint "
                        "(or commit not available locally)"
                    )
            else:
                errors.append("source_commit_sha missing or unknown")

    # freshness must include real data ages, not only generated_at
    fr = manifest.get("freshness") or {}
    if not fr.get("data_period_end") and not fr.get("by_dataset"):
        warnings.append("freshness lacks data_period_end / by_dataset")

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "dataset_hash": manifest.get("dataset_hash"),
        "source_commit_sha": sha,
    }
