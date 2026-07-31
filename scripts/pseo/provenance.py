"""Manifest provenance, checksums and dataset_hash recomposition."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from scripts.pseo import SCHEMA_VERSION

EXPORT_ENTRYPOINT = "python -m scripts.pseo.cli_export"
EXPORT_VERSION = "1.1.0"

# Canonical body keys that compose dataset_hash (order matters for determinism)
DATASET_BODY_KEYS = (
    "archetypes",
    "markets",
    "agencies",
    "prices",
    "competition",
    "opportunities",
    "problem_service",
    "icp_methodology",
)

FILE_NAME_FOR_KEY = {
    "archetypes": "archetypes.json",
    "markets": "markets.json",
    "agencies": "agencies.json",
    "prices": "prices.json",
    "competition": "competition.json",
    "opportunities": "opportunities.json",
    "problem_service": "problem_service.json",
    "icp_methodology": "icp_methodology.json",
}


def canonical_json(data: Any) -> str:
    return json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def compute_dataset_hash(files_body: dict[str, Any]) -> str:
    """Recompose dataset_hash from canonical body keys only."""
    ordered = {k: files_body[k] for k in DATASET_BODY_KEYS if k in files_body}
    return sha256_text(canonical_json(ordered))


def file_checksum(path: Path) -> str:
    return sha256_text(path.read_text(encoding="utf-8"))


def git_sha(repo_root: Path | None = None) -> str:
    try:
        import shutil

        git = shutil.which("git")
        if not git:
            return "unknown"
        cwd = repo_root or Path(__file__).resolve().parents[2]
        out = subprocess.check_output(  # noqa: S603
            [git, "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            cwd=cwd,
        )
        return out.decode().strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def git_branch(repo_root: Path | None = None) -> str:
    try:
        import shutil

        git = shutil.which("git")
        if not git:
            return "unknown"
        cwd = repo_root or Path(__file__).resolve().parents[2]
        out = subprocess.check_output(  # noqa: S603
            [git, "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL,
            cwd=cwd,
        )
        return out.decode().strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def entrypoint_exists_in_tree(repo_root: Path | None = None) -> bool:
    root = repo_root or Path(__file__).resolve().parents[2]
    return (root / "scripts" / "pseo" / "cli_export.py").is_file() or (root / "scripts" / "pseo" / "export_web_cfg.py").is_file() or (root / "scripts" / "pseo" / "pipeline.py").is_file()


def verify_commit_has_entrypoint(
    commit_sha: str,
    *,
    repo_root: Path | None = None,
) -> bool:
    """True if commit exists and contains scripts/pseo/export_web_cfg.py."""
    if not commit_sha or commit_sha == "unknown":
        return False
    try:
        import shutil

        git = shutil.which("git")
        if not git:
            return False
        cwd = repo_root or Path(__file__).resolve().parents[2]
        # verify commit exists
        subprocess.check_output(  # noqa: S603
            [git, "cat-file", "-e", f"{commit_sha}^{{commit}}"],
            stderr=subprocess.DEVNULL,
            cwd=cwd,
        )
        # list file at commit
        subprocess.check_output(  # noqa: S603
            [git, "cat-file", "-e", f"{commit_sha}:scripts/pseo/export_web_cfg.py"],
            stderr=subprocess.DEVNULL,
            cwd=cwd,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def build_manifest(
    *,
    files_body: dict[str, Any],
    counts: dict[str, int],
    classification_counts: dict[str, int],
    freshness: dict[str, Any],
    sources: list[dict[str, Any]],
    denominators: dict[str, Any],
    limitations: list[str],
    generated_at: str,
    data_as_of: str,
    source_run_id: str,
    repo_root: Path | None = None,
    query_versions: dict[str, str] | None = None,
    horizon: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    root = repo_root or Path(__file__).resolve().parents[2]
    dataset_hash = compute_dataset_hash(files_body)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "data_as_of": data_as_of,
        "source_run_id": source_run_id,
        "source_repository": "extra-cli",
        "source_commit_sha": git_sha(root),
        "source_branch": git_branch(root),
        "export_entrypoint": EXPORT_ENTRYPOINT,
        "exporter_entrypoint": EXPORT_ENTRYPOINT,
        "export_version": EXPORT_VERSION,
        "exporter_version": EXPORT_VERSION,
        "dataset_hash": dataset_hash,
        "checksums": {},  # filled after write
        "sources": sources,
        "tables": [s.get("table") for s in sources if s.get("table")],
        "query_versions": query_versions
        or {
            "pncp_supplier_contracts": "v1_public_fields_valor_gt_0",
            "pncp_raw_bids": "v1_active_with_encerramento",
            "sc_public_entities": "v1_count_only",
        },
        "horizon": horizon or {},
        "counts": counts,
        "classification_counts": classification_counts,
        "denominators": denominators,
        "timezone": "UTC",
        "freshness": freshness,
        "freshness_by_dataset": freshness.get("by_dataset") or {},
        "limitations": limitations,
        "methodology_notes": [
            "ICP-Derived Evidence pSEO: multi-layer AEC classifier + public aggregates.",
            "Only aec_confirmed feeds indexable market/price/competition pages.",
            "dataset_hash = sha256(canonical_json of ordered body keys).",
        ],
    }


def recompute_checksums(out_dir: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for name in list(FILE_NAME_FOR_KEY.values()) + ["schema.json"]:
        path = out_dir / name
        if path.exists():
            checksums[name] = file_checksum(path)
    return checksums


def verify_snapshot_hashes(out_dir: Path, manifest: dict[str, Any]) -> list[str]:
    """Return list of error strings (empty if ok)."""
    errors: list[str] = []
    checksums = manifest.get("checksums") or {}
    for name, expected in checksums.items():
        path = out_dir / name
        if not path.exists():
            errors.append(f"missing checksum target: {name}")
            continue
        actual = file_checksum(path)
        if actual != expected:
            errors.append(f"checksum mismatch: {name}")

    # recompose dataset_hash from files
    body: dict[str, Any] = {}
    for key, fname in FILE_NAME_FOR_KEY.items():
        path = out_dir / fname
        if path.exists():
            body[key] = json.loads(path.read_text(encoding="utf-8"))
    recomputed = compute_dataset_hash(body)
    if recomputed != manifest.get("dataset_hash"):
        errors.append(
            f"dataset_hash mismatch: manifest={manifest.get('dataset_hash')} recomputed={recomputed}"
        )
    return errors
