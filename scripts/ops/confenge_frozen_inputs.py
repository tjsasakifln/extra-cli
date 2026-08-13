#!/usr/bin/env python3
"""Frozen CONFENGE campaign inputs — monorepo-safe freeze policy.

Policy model
------------
Legacy model (REJECTED for monorepo work):
  "entire tree is frozen except ALLOWED_POST_FREEZE_PREFIXES"

Current model:
  "only explicitly frozen CONFENGE inputs are protected.
   Unrelated monorepo paths may change freely without editing an allowlist.
   Changing a protected input invalidates freeze evidence and requires re-freeze."

The freeze gates themselves are protected inputs: editing
``confenge_code_freeze.py`` or ``verify_confenge_artifact_binding.py`` after
freeze MUST fail until a new freeze SHA + manifest are produced.

Shared surfaces (Makefile, CI workflow) are not whole-file frozen. Only the
CONFENGE sections (marker-delimited, fail-closed parser) are hashed as
synthetic inputs.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "confenge-frozen-inputs/1.0"
CAMPAIGN = "CONFENGE-COMMERCIAL-READY-01"

# Synthetic keys for shared-surface sections (not repo file paths).
MAKEFILE_SECTION_KEY = "Makefile#CONFENGE"
CI_SECTION_KEY = ".github/workflows/ci.yml#CONFENGE"

# Post-freeze evidence lag still allowed (campaign artifacts / ops docs / real holdout).
EVIDENCE_LAG_PREFIXES: tuple[str, ...] = (
    "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/",
    "docs/ops/",
    "evals/commercial_leads/real/",
)

# Seed paths derived from canonical CONFENGE execution surface
# (Makefile targets, CI jobs, commercial_leads entrypoints, freeze gates).
# Import discovery expands local package deps; do not invent unrelated paths.
_SEED_PATHS: tuple[str, ...] = (
    # Gates (MUST be protected — self-modification invalidates evidence)
    "scripts/ops/confenge_code_freeze.py",
    "scripts/ops/verify_confenge_artifact_binding.py",
    "scripts/ops/confenge_frozen_inputs.py",
    # Ops / campaign machinery
    "scripts/ops/confenge_make_gates.py",
    "scripts/ops/confenge_commercial_cycle.py",
    "scripts/ops/confenge_commercial_gates.py",
    "scripts/ops/confenge_historical_snapshot.py",
    "scripts/ops/confenge_dump_restore.py",
    "scripts/ops/confenge_full_universe_e2e.py",
    "scripts/ops/confenge_full_pipeline_e2e.py",
    "scripts/ops/confenge_official_cnpj.py",
    "scripts/ops/confenge_final_status.py",
    "scripts/ops/confenge_offer_sensitivity.py",
    "scripts/ops/confenge_human_review_packages.py",
    "scripts/ops/confenge_registry_ingest.py",
    "scripts/ops/confenge_rerank_after_registry.py",
    "scripts/ops/confenge_contract_status.py",
    "scripts/ops/confenge_opencnpj_bulk.py",
    "scripts/ops/eval_contract_relevance_holdout.py",
    "scripts/ops/eval_contract_relevance_real_holdout.py",
    "scripts/ops/extract_confenge_real_holdout_corpus.py",
    "scripts/ops/verify_confenge_denominator_integrity.py",
    # Canonical activation authority and full-universe classifiers.
    "scripts/confenge_activation/emit_final_closure_pack.py",
    "scripts/confenge_activation/pilot_go_policy.py",
    "scripts/confenge_sector/rebuild.py",
    "scripts/confenge_sector/store.py",
    "scripts/confenge_target_fit/compute.py",
    "scripts/warmbly_bridge/mapping.py",
    # Commercial package entrypoints (rest expanded via imports / package listing)
    "scripts/commercial_leads/__init__.py",
    "scripts/commercial_leads/__main__.py",
    "scripts/commercial_leads/pipeline.py",
    "scripts/commercial_leads/sector_fit.py",
    "scripts/commercial_leads/scoring.py",
    "scripts/commercial_leads/snapshot.py",
    "scripts/commercial_leads/supplier_registry.py",
    "scripts/commercial_leads/profile.py",
    "scripts/commercial_leads/cli.py",
    "scripts/commercial_leads/contract_relevance.py",
    "scripts/commercial_leads/signals.py",
    "scripts/commercial_leads/baseline.py",
    "scripts/commercial_leads/commercial_validity.py",
    "scripts/commercial_leads/dbutil.py",
    "scripts/commercial_leads/exports.py",
    "scripts/commercial_leads/geography.py",
    "scripts/commercial_leads/identity.py",
    "scripts/commercial_leads/isolation.py",
    "scripts/commercial_leads/review.py",
    # Config
    "config/commercial_profiles/confenge.yaml",
    "config/commercial_profiles/signal_catalog.yaml",
    # Schema effectively used by commercial campaign
    "db/migrations/062_commercial_leads_ledger.sql",
    "db/migrations/063_supplier_registry.sql",
    "db/migrations/064_snapshot_write_guard.sql",
)

# Markers for Makefile CONFENGE sections (fail-closed: both markers required).
_MAKEFILE_SECTION_STARTS: tuple[str, ...] = (
    "# --- CONFENGE commercial ready",
    "# --- CONFENGE final evidence closure",
)

# CI: capture jobs whose keys or display names are CONFENGE-scoped.
_CI_CONFENGE_JOB_KEY_RE = re.compile(r"^\s{2}(confenge-[A-Za-z0-9_-]+):\s*$")
_CI_JOB_KEY_RE = re.compile(r"^\s{2}([A-Za-z0-9_-]+):\s*$")


def _git(root: Path, *args: str, strip: bool = True) -> str:
    git = shutil.which("git") or "git"
    out = subprocess.check_output(  # noqa: S603
        [git, *args],
        cwd=str(root),
        text=True,
        stderr=subprocess.DEVNULL,
    )
    # File blob contents must keep trailing newlines for stable section hashes.
    return out.strip() if strip else out


def _try_git(root: Path, *args: str, strip: bool = True) -> str | None:
    try:
        return _git(root, *args, strip=strip)
    except (subprocess.CalledProcessError, OSError):
        return None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def is_evidence_lag_path(path: str) -> bool:
    return any(path.startswith(p) for p in EVIDENCE_LAG_PREFIXES)


def extract_makefile_confenge_section(makefile_text: str) -> str:
    """Extract CONFENGE Makefile sections between known markers (fail-closed).

    Collects every block that starts with a CONFENGE marker and continues until
    the next top-level ``# --- `` section header (or EOF). Missing markers raise.
    """
    lines = makefile_text.splitlines(keepends=True)
    starts: list[int] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if any(stripped.startswith(m) for m in _MAKEFILE_SECTION_STARTS):
            starts.append(i)
    if not starts:
        raise ValueError(
            "CONFENGE Makefile section markers not found; "
            "refusing silent empty hash (fail-closed)"
        )
    chunks: list[str] = []
    for si, start in enumerate(starts):
        end = len(lines)
        for j in range(start + 1, len(lines)):
            s = lines[j].strip()
            if s.startswith("# --- ") and not any(
                s.startswith(m) for m in _MAKEFILE_SECTION_STARTS
            ):
                end = j
                break
        # Avoid double-including if markers nest; clip to next start if earlier
        if si + 1 < len(starts) and starts[si + 1] < end:
            end = starts[si + 1]
        chunks.append("".join(lines[start:end]))
    body = "".join(chunks)
    if not body.strip():
        raise ValueError("CONFENGE Makefile section empty after extract (fail-closed)")
    return body


def extract_ci_confenge_section(ci_text: str) -> str:
    """Extract CONFENGE job definitions from GitHub Actions workflow YAML.

    Fail-closed: requires at least one ``confenge-*`` job key under ``jobs:``.
    Captures each confenge job block until the next top-level job key.
    """
    lines = ci_text.splitlines(keepends=True)
    # Find jobs: block start
    jobs_idx = None
    for i, line in enumerate(lines):
        if re.match(r"^jobs:\s*$", line):
            jobs_idx = i
            break
    if jobs_idx is None:
        raise ValueError("CI workflow missing top-level jobs: (fail-closed)")

    job_starts: list[tuple[int, str]] = []
    for i in range(jobs_idx + 1, len(lines)):
        m = _CI_JOB_KEY_RE.match(lines[i])
        if m:
            job_starts.append((i, m.group(1)))

    confenge_indices = [i for i, (idx, name) in enumerate(job_starts) if name.startswith("confenge-")]
    if not confenge_indices:
        raise ValueError("No confenge-* CI jobs found (fail-closed)")

    chunks: list[str] = []
    for ci in confenge_indices:
        start_line = job_starts[ci][0]
        if ci + 1 < len(job_starts):
            end_line = job_starts[ci + 1][0]
        else:
            end_line = len(lines)
        chunks.append("".join(lines[start_line:end_line]))
    body = "".join(chunks)
    if not body.strip():
        raise ValueError("CONFENGE CI section empty after extract (fail-closed)")
    return body


def _module_path_from_import(mod: str, root: Path) -> Path | None:
    """Map ``scripts.x.y`` import to a file under root, if present."""
    if not (mod.startswith("scripts.") or mod == "scripts"):
        return None
    parts = mod.split(".")
    base = root.joinpath(*parts)
    py = base.with_suffix(".py")
    init = base / "__init__.py"
    if py.is_file():
        return py
    if init.is_file():
        return init
    return None


def _local_imports_from_file(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return set()
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("scripts."):
                    mods.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("scripts."):
                mods.add(node.module)
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    mods.add(f"{node.module}.{alias.name}")
    return mods


def discover_frozen_input_paths(root: Path) -> list[str]:
    """Return sorted unique repo-relative frozen input file paths.

    Starts from seed list, includes all ``scripts/commercial_leads/*.py``,
    expands transitive local imports under ``scripts/``, and always includes
    the gate modules themselves.
    """
    root = root.resolve()
    found: set[str] = set()

    def add_rel(rel: str) -> None:
        rel = rel.replace("\\", "/").lstrip("./")
        p = root / rel
        if p.is_file():
            found.add(rel)

    for s in _SEED_PATHS:
        add_rel(s)

    # Entire commercial_leads package (execution graph core)
    cl = root / "scripts" / "commercial_leads"
    if cl.is_dir():
        for p in sorted(cl.rglob("*.py")):
            add_rel(str(p.relative_to(root)).replace("\\", "/"))

    # Transitive local imports from seeds (BFS)
    queue = [root / r for r in sorted(found) if (root / r).suffix == ".py"]
    seen_files: set[Path] = set()
    while queue:
        f = queue.pop()
        if f in seen_files:
            continue
        seen_files.add(f)
        for mod in _local_imports_from_file(f):
            # Trim attribute imports to module path
            candidate = mod
            mapped = _module_path_from_import(candidate, root)
            if mapped is None and "." in candidate:
                mapped = _module_path_from_import(candidate.rsplit(".", 1)[0], root)
            if mapped is None:
                continue
            rel = str(mapped.relative_to(root)).replace("\\", "/")
            if rel not in found:
                found.add(rel)
                queue.append(mapped)

    # Gates must always be present even if temporarily missing on disk (fail later)
    for mandatory in (
        "scripts/ops/confenge_code_freeze.py",
        "scripts/ops/verify_confenge_artifact_binding.py",
        "scripts/ops/confenge_frozen_inputs.py",
    ):
        found.add(mandatory)

    return sorted(found)


def _blob_and_hash_at_ref(root: Path, ref: str, path: str) -> tuple[str | None, str | None]:
    """Return (git blob oid, sha256 of content) for path at ref."""
    blob = _try_git(root, "rev-parse", f"{ref}:{path}")
    content = _try_git(root, "show", f"{ref}:{path}", strip=False)
    if content is None:
        # Working tree fallback when path is new (not yet committed)
        p = root / path
        if p.is_file():
            data = p.read_bytes()
            return None, sha256_bytes(data)
        return None, None
    return blob, sha256_text(content)


def _section_entry(key: str, content: str) -> dict[str, Any]:
    return {
        "path": key,
        "kind": "section_hash",
        "blob_sha": None,
        "sha256": sha256_text(content),
        "content_length": len(content.encode("utf-8")),
    }


def build_frozen_inputs_manifest(
    *,
    root: Path,
    freeze_sha: str,
    campaign: str = CAMPAIGN,
) -> dict[str, Any]:
    """Build manifest of frozen CONFENGE inputs at ``freeze_sha`` (real hashes)."""
    root = root.resolve()
    paths = discover_frozen_input_paths(root)
    inputs: list[dict[str, Any]] = []
    missing: list[str] = []
    for path in paths:
        blob, digest = _blob_and_hash_at_ref(root, freeze_sha, path)
        if digest is None:
            missing.append(path)
            continue
        inputs.append(
            {
                "path": path,
                "kind": "file",
                "blob_sha": blob,
                "sha256": digest,
            }
        )

    # Shared surfaces: section hashes only
    makefile_text = _try_git(root, "show", f"{freeze_sha}:Makefile", strip=False)
    if makefile_text is None and (root / "Makefile").is_file():
        makefile_text = (root / "Makefile").read_text(encoding="utf-8")
    if makefile_text is None:
        raise ValueError("Makefile not available at freeze_sha (fail-closed)")
    mk_section = extract_makefile_confenge_section(makefile_text)
    inputs.append(_section_entry(MAKEFILE_SECTION_KEY, mk_section))

    ci_path = ".github/workflows/ci.yml"
    ci_text = _try_git(root, "show", f"{freeze_sha}:{ci_path}", strip=False)
    if ci_text is None and (root / ci_path).is_file():
        ci_text = (root / ci_path).read_text(encoding="utf-8")
    if ci_text is None:
        raise ValueError("CI workflow not available at freeze_sha (fail-closed)")
    ci_section = extract_ci_confenge_section(ci_text)
    inputs.append(_section_entry(CI_SECTION_KEY, ci_section))

    # Stable order
    inputs.sort(key=lambda x: x["path"])

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "campaign": campaign,
        "freeze_sha": freeze_sha,
        "policy": "frozen_confenge_inputs_v1",
        "inputs": inputs,
        "missing_at_build": missing,
        "evidence_lag_prefixes": list(EVIDENCE_LAG_PREFIXES),
        "notes": [
            "Protected set is explicit CONFENGE inputs, not monorepo-wide freeze.",
            "Gates themselves are protected; changing them requires re-freeze.",
            "Makefile/CI only freeze CONFENGE sections (tested extractors).",
            "Unrelated paths (e.g. edital relevance) do not require allowlist edits.",
        ],
    }
    # Fail closed if gate files missing from inputs
    input_paths = {i["path"] for i in inputs}
    for mandatory in (
        "scripts/ops/confenge_code_freeze.py",
        "scripts/ops/verify_confenge_artifact_binding.py",
        "scripts/ops/confenge_frozen_inputs.py",
        MAKEFILE_SECTION_KEY,
        CI_SECTION_KEY,
    ):
        if mandatory not in input_paths:
            raise ValueError(f"mandatory frozen input missing from manifest: {mandatory}")
    return manifest


def write_frozen_inputs_manifest(
    manifest: dict[str, Any],
    *,
    art_dir: Path,
) -> Path:
    art_dir.mkdir(parents=True, exist_ok=True)
    out = art_dir / "frozen-inputs-manifest.json"
    out.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return out


def load_frozen_inputs_manifest(
    *,
    art_dir: Path,
    root: Path | None = None,
    freeze_sha: str | None = None,
) -> dict[str, Any]:
    """Load manifest from art_dir, or rebuild from freeze_sha when missing."""
    path = art_dir / "frozen-inputs-manifest.json"
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported frozen-inputs schema: {data.get('schema_version')!r}"
            )
        if not isinstance(data, dict):
            raise ValueError("frozen-inputs manifest must be a JSON object")
        return dict(data)
    if root is None or not freeze_sha:
        raise FileNotFoundError(f"missing frozen-inputs-manifest.json at {path}")
    # Rebuild (used during transition / first mark after policy)
    return build_frozen_inputs_manifest(root=root, freeze_sha=freeze_sha)


def protected_path_set(manifest: dict[str, Any]) -> set[str]:
    """Repo file paths only (excludes synthetic section keys like Makefile#CONFENGE)."""
    out: set[str] = set()
    for i in manifest.get("inputs") or []:
        if i.get("kind") != "file":
            continue
        path = str(i["path"])
        if "#" in path:
            continue
        out.add(path)
    return out


def section_hashes_from_manifest(manifest: dict[str, Any]) -> dict[str, str]:
    return {
        str(i["path"]): str(i["sha256"])
        for i in manifest.get("inputs") or []
        if i.get("kind") == "section_hash"
    }


def file_digest_map(manifest: dict[str, Any]) -> dict[str, str]:
    return {
        str(i["path"]): str(i["sha256"])
        for i in manifest.get("inputs") or []
        if i.get("kind") == "file" and i.get("sha256")
    }


def classify_changed_paths(
    changed: Iterable[str],
    *,
    protected: set[str],
) -> dict[str, list[str]]:
    """Split changed paths into protected / evidence_lag / free."""
    prot: list[str] = []
    lag: list[str] = []
    free: list[str] = []
    for raw in changed:
        path = raw.strip().replace("\\", "/")
        if not path:
            continue
        if path in protected:
            prot.append(path)
        elif is_evidence_lag_path(path):
            lag.append(path)
        else:
            free.append(path)
    return {
        "protected_changed": sorted(set(prot)),
        "evidence_lag_changed": sorted(set(lag)),
        "free_changed": sorted(set(free)),
    }


def verify_shared_surface_sections(
    *,
    root: Path,
    tip: str,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Compare Makefile/CI CONFENGE section hashes at tip vs freeze manifest."""
    expected = section_hashes_from_manifest(manifest)
    issues: list[str] = []
    current: dict[str, str] = {}

    makefile_text = _try_git(root, "show", f"{tip}:Makefile", strip=False)
    if makefile_text is None and (root / "Makefile").is_file():
        # uncommitted tip: use working tree when tip == HEAD
        head = _try_git(root, "rev-parse", "HEAD")
        if tip == head:
            makefile_text = (root / "Makefile").read_text(encoding="utf-8")
    if makefile_text is None:
        issues.append("makefile_unavailable_at_tip")
    else:
        try:
            section = extract_makefile_confenge_section(makefile_text)
            current[MAKEFILE_SECTION_KEY] = sha256_text(section)
            exp = expected.get(MAKEFILE_SECTION_KEY)
            if exp and current[MAKEFILE_SECTION_KEY] != exp:
                issues.append("makefile_confenge_section_changed")
        except ValueError as exc:
            issues.append(f"makefile_section_extract_failed:{exc}")

    ci_path = ".github/workflows/ci.yml"
    ci_text = _try_git(root, "show", f"{tip}:{ci_path}", strip=False)
    if ci_text is None and (root / ci_path).is_file():
        head = _try_git(root, "rev-parse", "HEAD")
        if tip == head:
            ci_text = (root / ci_path).read_text(encoding="utf-8")
    if ci_text is None:
        issues.append("ci_unavailable_at_tip")
    else:
        try:
            section = extract_ci_confenge_section(ci_text)
            current[CI_SECTION_KEY] = sha256_text(section)
            exp = expected.get(CI_SECTION_KEY)
            if exp and current[CI_SECTION_KEY] != exp:
                issues.append("ci_confenge_section_changed")
        except ValueError as exc:
            issues.append(f"ci_section_extract_failed:{exc}")

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "expected_section_sha256": expected,
        "current_section_sha256": current,
    }


def verify_frozen_input_digests_at_tip(
    *,
    root: Path,
    tip: str,
    manifest: dict[str, Any],
    changed_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Verify protected file digests when listed in changed_paths (or all if None)."""
    digests = file_digest_map(manifest)
    protected = set(digests)
    to_check = protected if changed_paths is None else (set(changed_paths) & protected)
    mismatched: list[dict[str, str]] = []
    missing: list[str] = []
    for path in sorted(to_check):
        _blob, digest = _blob_and_hash_at_ref(root, tip, path)
        if digest is None:
            missing.append(path)
            continue
        if digest != digests[path]:
            mismatched.append(
                {
                    "path": path,
                    "freeze_sha256": digests[path],
                    "tip_sha256": digest,
                }
            )
    return {
        "ok": not mismatched and not missing,
        "mismatched": mismatched,
        "missing": missing,
        "checked": sorted(to_check),
    }


def evaluate_post_freeze_diff(
    *,
    root: Path,
    freeze_sha: str,
    tip: str,
    manifest: dict[str, Any] | None = None,
    art_dir: Path | None = None,
) -> dict[str, Any]:
    """Core policy check: protected inputs must not change freeze→tip.

    Free (unrelated) paths and evidence-lag prefixes are allowed without
    allowlist maintenance.
    """
    root = root.resolve()
    if art_dir is None:
        art_dir = root / "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01"

    if manifest is None:
        try:
            manifest = load_frozen_inputs_manifest(
                art_dir=art_dir, root=root, freeze_sha=freeze_sha
            )
        except (OSError, ValueError, json.JSONDecodeError, FileNotFoundError) as exc:
            return {
                "ok": False,
                "status": "BLOCKED_FROZEN_INPUTS_MANIFEST",
                "reason": str(exc),
                "protected_changed": [],
                "free_changed": [],
                "evidence_lag_changed": [],
                "files_changed_after_freeze": [],
            }

    # When evaluating a historical bound/freeze SHA that differs from the on-disk
    # manifest freeze, rebuild digests at that freeze_sha (honest comparison).
    man_freeze = str(manifest.get("freeze_sha") or "")
    freeze_mismatch = False
    if man_freeze and man_freeze != freeze_sha:
        try:
            manifest = build_frozen_inputs_manifest(root=root, freeze_sha=freeze_sha)
            man_freeze = freeze_sha
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            freeze_mismatch = True
            return {
                "ok": False,
                "status": "BLOCKED_FROZEN_INPUTS_MANIFEST",
                "reason": f"cannot_rebuild_manifest_at_freeze:{exc}",
                "manifest_freeze_sha": man_freeze,
                "freeze_sha": freeze_sha,
                "protected_changed": [],
                "free_changed": [],
                "evidence_lag_changed": [],
                "files_changed_after_freeze": [],
            }

    changed: list[str] = []
    if freeze_sha != tip:
        out = _try_git(root, "diff", "--name-only", f"{freeze_sha}..{tip}")
        if out is None:
            # try log name-only
            out = _try_git(root, "log", "--name-only", "--pretty=format:", f"{freeze_sha}..{tip}")
        if out:
            changed = [ln.strip() for ln in out.splitlines() if ln.strip()]

    # Protected path *names* always come from code-defined discovery (not only
    # the artifact manifest, which lives under an evidence-lag prefix and must
    # not be a soft self-weakening surface). Digests still come from the
    # freeze-time manifest when present.
    discovered = set(discover_frozen_input_paths(root))
    protected = discovered | protected_path_set(manifest)
    classified = classify_changed_paths(changed, protected=protected)
    digest_check = verify_frozen_input_digests_at_tip(
        root=root,
        tip=tip,
        manifest=manifest,
        changed_paths=classified["protected_changed"] or None
        if classified["protected_changed"]
        else [],
    )
    # If no protected path names in diff, still verify section hashes
    section_check = verify_shared_surface_sections(root=root, tip=tip, manifest=manifest)

    protected_changed = list(classified["protected_changed"])
    # Section drift counts as protected change
    if not section_check["ok"]:
        for issue in section_check["issues"]:
            if issue.endswith("_section_changed"):
                if "makefile" in issue:
                    protected_changed.append(MAKEFILE_SECTION_KEY)
                if issue.startswith("ci_"):
                    protected_changed.append(CI_SECTION_KEY)
    protected_changed = sorted(set(protected_changed))

    ok = (
        len(protected_changed) == 0
        and digest_check["ok"]
        and section_check["ok"]
        and not freeze_mismatch
    )
    return {
        "ok": ok,
        "status": "PASS" if ok else "BLOCKED_PROTECTED_INPUT_CHANGED",
        "policy": "frozen_confenge_inputs_v1",
        "freeze_sha": freeze_sha,
        "tip": tip,
        "manifest_freeze_sha": man_freeze,
        "manifest_freeze_sha_mismatch": freeze_mismatch,
        "files_changed_after_freeze": changed,
        "protected_changed": protected_changed,
        "free_changed": classified["free_changed"],
        "evidence_lag_changed": classified["evidence_lag_changed"],
        # Backward-compatible alias used by freeze gates:
        # "non_artifact" now means "protected input drift" (not monorepo-wide).
        "non_artifact_files_changed": protected_changed,
        "digest_check": digest_check,
        "section_check": section_check,
        "protected_input_count": len(protected),
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="CONFENGE frozen-inputs manifest tools")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="Build and write frozen-inputs-manifest.json")
    b.add_argument("--freeze-sha", default=None)
    b.add_argument(
        "--art",
        default="artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01",
    )
    v = sub.add_parser("verify", help="Verify tip against frozen inputs")
    v.add_argument("--freeze-sha", default=None)
    v.add_argument("--tip", default=None)
    v.add_argument(
        "--art",
        default="artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01",
    )
    args = ap.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    if args.cmd == "build":
        freeze = args.freeze_sha or _git(root, "rev-parse", "HEAD")
        man = build_frozen_inputs_manifest(root=root, freeze_sha=freeze)
        out = write_frozen_inputs_manifest(man, art_dir=root / args.art)
        print(json.dumps({"ok": True, "path": str(out), "inputs": len(man["inputs"])}, indent=2))
        return 0
    freeze = args.freeze_sha
    art = root / args.art
    if not freeze:
        for name in ("FINAL_INTEGRITY_CODE_FREEZE_SHA.txt", "FINAL_CODE_FREEZE_SHA.txt"):
            p = art / name
            if p.is_file():
                freeze = p.read_text(encoding="utf-8").strip().split()[0]
                break
    if not freeze:
        print(json.dumps({"ok": False, "reason": "missing_freeze_sha"}))
        return 2
    tip = args.tip or _git(root, "rev-parse", "HEAD")
    rep = evaluate_post_freeze_diff(
        root=root, freeze_sha=freeze, tip=tip, art_dir=art
    )
    print(json.dumps(rep, indent=2, default=str))
    return 0 if rep.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
