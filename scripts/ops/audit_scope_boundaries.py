#!/usr/bin/env python3
"""Audit product scope boundaries (negative capabilities).

Distinguishes documentation of a prohibition from real implementation.
Fail-closed: ambiguous production signals are reported as findings.
Does not treat DOD.md mentions as violations.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "scope_boundaries.yaml"

# Directories never scanned as implementation surfaces
_SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "htmlcov",
    ".coverage",
    "dist",
    "build",
    ".dod",
    ".aiox",
    ".claude",
    ".agents",
    ".grok",
    ".specify",
    "output",
    "artifacts",
    "data",
    "main-wt",
    "pr52-wt",
    ".worktrees",
}


@dataclass
class Finding:
    capability_id: str
    path: str
    line: int | None
    snippet: str
    classification: str  # implementation | documentation | disclaimer | fixture | test | dependency
    pattern: str
    severity: str = "hard"


@dataclass
class CapabilityProof:
    capability_id: str
    definition: str
    dod_item_text_contains: str
    surfaces_checked: list[str]
    findings: list[Finding] = field(default_factory=list)
    false_positives_treated: list[dict[str, str]] = field(default_factory=list)
    implementation_violations: int = 0
    conclusion: str = "NOT_PROVEN"  # PROVEN | NOT_PROVEN | REGRESSION
    limitations: list[str] = field(default_factory=list)
    code_hash: str = ""
    commands: list[str] = field(default_factory=list)
    exit_code: int = 0


def load_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or DEFAULT_CONFIG
    if yaml is None:
        raise RuntimeError("PyYAML required for scope boundary audit")
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid scope config: {cfg_path}")
    return data


def _is_doc_path(rel: str, allowlist: list[str]) -> bool:
    rel_norm = rel.replace("\\", "/")
    for glob in allowlist:
        g = glob.replace("\\", "/")
        if fnmatch.fnmatch(rel_norm, g) or fnmatch.fnmatch(rel_norm, g.lstrip("./")):
            return True
    return False


# Auditor / campaign tooling — may name excluded capabilities without implementing them.
_AUDIT_TOOLING_PREFIXES = (
    "scripts/ops/audit_scope_boundaries.py",
    "scripts/ops/audit_client_claim_boundaries.py",
    "scripts/ops/dod_low_hanging_audit.py",
    "config/scope_boundaries.yaml",
    "docs/architecture/scope-boundaries.md",
    "docs/ops/campaigns/DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01/",
    "specs/900-dod-low-hanging-boundaries-evidence/",
    "tests/test_scope_boundaries.py",
    "tests/test_client_claim_boundaries.py",
    "tests/test_dod_low_hanging_audit.py",
    "tests/test_dod_governance_invariants.py",
)


def _classify_path(rel: str, allowlist: list[str]) -> str:
    rel_n = rel.replace("\\", "/")
    if rel_n.startswith("tests/") or "/tests/" in rel_n or rel_n.endswith("_test.py"):
        return "test"
    if "fixture" in rel_n.lower() or "/fixtures/" in rel_n:
        return "fixture"
    if any(rel_n == p or rel_n.startswith(p) for p in _AUDIT_TOOLING_PREFIXES):
        return "documentation"
    if _is_doc_path(rel_n, allowlist):
        return "documentation"
    if rel_n.endswith((".md", ".rst", ".txt", ".html")) and (
        rel_n.startswith("docs/") or "README" in rel_n
    ):
        return "documentation"
    return "implementation"


# Only scan implementation-relevant roots (not whole monorepo noise).
_SCAN_ROOTS = (
    "scripts",
    "tools",
    "migrations",
    "db",
    "deploy",
    "config",
    "templates",
    "packages",
)

_SCAN_ROOT_FILES = (
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Makefile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Dockerfile",
)


def _iter_files(root: Path, max_files: int = 4000) -> list[Path]:
    out: list[Path] = []
    for name in _SCAN_ROOT_FILES:
        p = root / name
        if p.is_file():
            out.append(p)

    for scan_name in _SCAN_ROOTS:
        base = root / scan_name
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if any(part in _SKIP_DIR_NAMES for part in p.relative_to(root).parts):
                continue
            if p.suffix.lower() in {
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".pdf",
                ".xlsx",
                ".xls",
                ".zip",
                ".gz",
                ".pyc",
                ".so",
                ".whl",
                ".dump",
                ".sqlite",
            }:
                continue
            try:
                if p.stat().st_size > 800_000:
                    continue
            except OSError:
                continue
            out.append(p)
            if len(out) >= max_files:
                return out
    return out


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _dependency_names(root: Path) -> set[str]:
    names: set[str] = set()
    for fname in ("requirements.txt", "requirements-dev.txt", "pyproject.toml"):
        p = root / fname
        if not p.exists():
            continue
        text = _read_text(p).lower()
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("["):
                continue
            # name==ver or name>=ver
            m = re.match(r"^([a-zA-Z0-9_.\-]+)", line)
            if m:
                names.add(m.group(1).lower().replace("_", "-"))
    return names


def _disclaimer_near(text: str, start: int, window: int = 120) -> bool:
    lo = max(0, start - window)
    hi = min(len(text), start + window)
    chunk = text[lo:hi].lower()
    markers = (
        "não contém",
        "nao contem",
        "fora de escopo",
        "out of scope",
        "forbidden",
        "proibid",
        "excluíd",
        "never",
        "must not",
        "não deve",
        "nao deve",
        "claims_forbidden",
        "excluded",
        "scope boundaries",
        "não promete",
        "nao promete",
        "não assume",
        "nao assume",
        "não assina",
        "nao assina",
        "não protocola",
        "nao protocola",
        "não substitui",
        "nao substitui",
        "não representa",
        "nao representa",
        "não fornece",
        "nao fornece",
        "não executa",
        "nao executa",
    )
    return any(m in chunk for m in markers)


def audit_capability(
    cap_id: str,
    cap_cfg: dict[str, Any],
    *,
    root: Path,
    allowlist: list[str],
    files: list[Path],
    deps: set[str],
) -> CapabilityProof:
    definition = str(cap_cfg.get("definition") or cap_id)
    text_hint = str(cap_cfg.get("dod_item_text_contains") or "")
    proof = CapabilityProof(
        capability_id=cap_id,
        definition=definition,
        dod_item_text_contains=text_hint,
        surfaces_checked=[
            "scripts/",
            "tools/",
            "migrations/",
            "deploy/",
            "config/",
            "requirements.txt",
            "pyproject.toml",
            "templates/",
        ],
        commands=[
            f"python3 -m scripts.ops.audit_scope_boundaries --capability {cap_id}",
        ],
        limitations=[
            "Static audit; does not execute runtime services.",
            "Does not prove future code will stay in bounds without CI gate.",
        ],
    )

    patterns = cap_cfg.get("forbidden_implementation_patterns") or []
    findings: list[Finding] = []

    for pat_spec in patterns:
        if not isinstance(pat_spec, dict):
            continue
        pattern = pat_spec.get("pattern") or ""
        if not pattern:
            continue
        try:
            cre = re.compile(pattern)
        except re.error as exc:
            findings.append(
                Finding(
                    capability_id=cap_id,
                    path="config/scope_boundaries.yaml",
                    line=None,
                    snippet=f"invalid regex: {exc}",
                    classification="implementation",
                    pattern=pattern,
                    severity="soft",
                )
            )
            continue
        targets = pat_spec.get("in") or ["content", "path"]
        path_glob = pat_spec.get("path_glob")

        for fpath in files:
            rel = str(fpath.relative_to(root)).replace("\\", "/")
            if path_glob and not fnmatch.fnmatch(rel, path_glob):
                continue
            classification = _classify_path(rel, allowlist)

            if "path" in targets and cre.search(rel):
                if classification in {"documentation", "test", "fixture"}:
                    proof.false_positives_treated.append(
                        {
                            "path": rel,
                            "reason": f"matched path but classified as {classification}",
                        }
                    )
                else:
                    findings.append(
                        Finding(
                            capability_id=cap_id,
                            path=rel,
                            line=None,
                            snippet=rel,
                            classification=classification,
                            pattern=pattern,
                        )
                    )

            if "content" not in targets:
                continue
            if classification == "documentation" and rel in {
                "DOD.md",
                "config/scope_boundaries.yaml",
            }:
                # Explicit: DOD listing the prohibition is not a violation
                continue
            text = _read_text(fpath)
            if not text:
                continue
            for m in cre.finditer(text):
                # line number
                line_no = text.count("\n", 0, m.start()) + 1
                snippet = text[max(0, m.start() - 40) : m.end() + 40].replace("\n", " ")
                if classification in {"documentation", "test", "fixture"}:
                    proof.false_positives_treated.append(
                        {
                            "path": f"{rel}:{line_no}",
                            "reason": f"classified as {classification}",
                        }
                    )
                    continue
                if _disclaimer_near(text, m.start()):
                    findings.append(
                        Finding(
                            capability_id=cap_id,
                            path=rel,
                            line=line_no,
                            snippet=snippet[:200],
                            classification="disclaimer",
                            pattern=pattern,
                            severity="soft",
                        )
                    )
                    proof.false_positives_treated.append(
                        {
                            "path": f"{rel}:{line_no}",
                            "reason": "disclaimer/negation near match",
                        }
                    )
                    continue
                findings.append(
                    Finding(
                        capability_id=cap_id,
                        path=rel,
                        line=line_no,
                        snippet=snippet[:200],
                        classification="implementation",
                        pattern=pattern,
                    )
                )

    # dependency checks
    for dep in cap_cfg.get("dependency_names") or []:
        dep_n = str(dep).lower().replace("_", "-")
        if dep_n in deps:
            findings.append(
                Finding(
                    capability_id=cap_id,
                    path="requirements.txt|pyproject.toml",
                    line=None,
                    snippet=f"dependency present: {dep_n}",
                    classification="dependency",
                    pattern=dep_n,
                )
            )

    for g in cap_cfg.get("path_globs_forbidden") or []:
        for fpath in files:
            rel = str(fpath.relative_to(root)).replace("\\", "/")
            if fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(rel, g.lstrip("./")):
                classification = _classify_path(rel, allowlist)
                if classification in {"documentation", "test", "fixture"}:
                    continue
                findings.append(
                    Finding(
                        capability_id=cap_id,
                        path=rel,
                        line=None,
                        snippet=f"path matches forbidden glob {g}",
                        classification="implementation",
                        pattern=g,
                    )
                )

    # claim-only capabilities: absence of implementation patterns is enough for code audit
    primarily_claim = bool(cap_cfg.get("primarily_claim_guard"))

    impl = [
        f
        for f in findings
        if f.classification in {"implementation", "dependency"} and f.severity == "hard"
    ]
    proof.findings = findings
    proof.implementation_violations = len(impl)

    # code hash of relevant scan inputs
    h = hashlib.sha256()
    h.update(cap_id.encode())
    h.update(json.dumps(cap_cfg, sort_keys=True, default=str).encode())
    proof.code_hash = h.hexdigest()[:16]

    if impl:
        proof.conclusion = "REGRESSION"
        proof.exit_code = 1
    else:
        proof.conclusion = "PROVEN"
        proof.exit_code = 0
        if primarily_claim:
            proof.limitations.append(
                "Primary enforcement for this item is also client-claim guard language scan."
            )

    return proof


def run_audit(
    root: Path | None = None,
    config_path: Path | None = None,
    capability: str | None = None,
) -> dict[str, Any]:
    root = root or PROJECT_ROOT
    cfg = load_config(config_path)
    allowlist = list(cfg.get("documentation_allowlist_globs") or [])
    caps: dict[str, Any] = dict(cfg.get("capabilities") or {})
    if capability:
        if capability not in caps:
            raise KeyError(f"Unknown capability: {capability}")
        caps = {capability: caps[capability]}

    files = _iter_files(root)
    deps = _dependency_names(root)
    proofs: dict[str, Any] = {}
    violations = 0
    for cap_id, cap_cfg in caps.items():
        if not isinstance(cap_cfg, dict):
            continue
        proof = audit_capability(
            cap_id,
            cap_cfg,
            root=root,
            allowlist=allowlist,
            files=files,
            deps=deps,
        )
        proofs[cap_id] = {
            **{k: v for k, v in asdict(proof).items() if k != "findings"},
            "findings": [asdict(f) for f in proof.findings],
        }
        if proof.conclusion != "PROVEN":
            violations += 1

    return {
        "ok": violations == 0,
        "schema_version": cfg.get("schema_version"),
        "campaign_id": cfg.get("campaign_id"),
        "generated_at": datetime.now(UTC).isoformat(),
        "root": str(root),
        "files_scanned": len(files),
        "capabilities_audited": len(proofs),
        "violations": violations,
        "distinctions": cfg.get("distinctions"),
        "proofs": proofs,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit scope boundary exclusions")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--capability", type=str, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = run_audit(root=args.root, config_path=args.config, capability=args.capability)
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    if args.json or args.out is None:
        sys.stdout.write(payload)
    else:
        print(
            f"scope audit ok={result['ok']} capabilities={result['capabilities_audited']} "
            f"violations={result['violations']} -> {args.out}"
        )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
