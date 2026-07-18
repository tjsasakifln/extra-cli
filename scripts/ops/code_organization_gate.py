#!/usr/bin/env python3
"""DoD §27 code organization gate — module names, sys.path policy, bare excepts.

Does not rewrite the whole tree. Produces inventory + policy verdict for evidence.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Allowed bootstrap pattern: insert project root only (parents[1] or parents[2] of scripts/)
ALLOWED_SYS_PATH_MARKERS = (
    "parents[1]",
    "parents[2]",
    "PROJECT_ROOT",
    "_PROJECT_ROOT",
    "project_root",
    "REPO_ROOT",
)

SNAKE_MODULE = re.compile(r"^[a-z][a-z0-9_]*\.py$")


@dataclass
class Finding:
    path: str
    kind: str
    detail: str
    severity: str = "MEDIUM"


def iter_py_files(root: Path, *, under: str = "scripts") -> list[Path]:
    base = root / under
    if not base.is_dir():
        return []
    out: list[Path] = []
    for p in base.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        out.append(p)
    return sorted(out)


def check_module_names(files: list[Path], root: Path) -> list[Finding]:
    """Package modules must be snake_case; root scripts/ CLI may use hyphens (legacy)."""
    findings: list[Finding] = []
    scripts_root = root / "scripts"
    for p in files:
        name = p.name
        if name in {"__init__.py", "__main__.py"}:
            continue
        rel = p.relative_to(root)
        # private modules _foo.py allowed
        if name.startswith("_") and SNAKE_MODULE.match(name.lstrip("_")) or name.startswith("_"):
            if re.match(r"^_[a-z][a-z0-9_]*\.py$", name):
                continue
        # legacy CLI scripts directly under scripts/ with hyphens
        if p.parent == scripts_root and re.match(r"^[a-z0-9]+(-[a-z0-9]+)+\.py$", name):
            continue
        if not SNAKE_MODULE.match(name):
            findings.append(
                Finding(str(rel), "module_name", f"non-snake_case package module: {name}", "LOW")
            )
    return findings


def check_sys_path_hacks(files: list[Path], root: Path) -> tuple[list[Finding], list[dict[str, Any]]]:
    findings: list[Finding] = []
    inventory: list[dict[str, Any]] = []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            findings.append(Finding(str(p), "read_error", str(exc), "HIGH"))
            continue
        if "sys.path" not in text:
            continue
        # classify
        lines = text.splitlines()
        for i, line in enumerate(lines, 1):
            if "sys.path" not in line:
                continue
            window = "\n".join(lines[max(0, i - 3) : i + 2])
            allowed = any(m in window for m in ALLOWED_SYS_PATH_MARKERS)
            # also allow if inserting dirname of __file__ parents as project root
            if "path.insert" in line or "path.append" in line:
                inv = {
                    "path": str(p.relative_to(root)),
                    "line": i,
                    "snippet": line.strip()[:120],
                    "allowed_bootstrap": allowed,
                }
                inventory.append(inv)
                if not allowed:
                    findings.append(
                        Finding(
                            str(p.relative_to(root)),
                            "sys_path_hack",
                            f"L{i}: {line.strip()[:80]}",
                            "MEDIUM",
                        )
                    )
    return findings, inventory


def check_bare_except_pass(files: list[Path], root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for p in files:
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(src, filename=str(p))
        except SyntaxError:
            continue
        except OSError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            # except: or except Exception:
            is_bare = node.type is None
            is_exception = (
                isinstance(node.type, ast.Name) and node.type.id == "Exception"
            ) or (
                isinstance(node.type, ast.Tuple)
                and any(isinstance(e, ast.Name) and e.id == "Exception" for e in node.type.elts)
            )
            body = node.body
            only_pass = len(body) == 1 and isinstance(body[0], ast.Pass)
            only_pass_ellipsis = len(body) == 1 and isinstance(body[0], ast.Expr) and isinstance(
                getattr(body[0], "value", None), ast.Constant
            )
            if (is_bare or is_exception) and only_pass:
                findings.append(
                    Finding(
                        str(p.relative_to(root)),
                        "except_exception_pass",
                        f"L{node.lineno}: except Exception/bare: pass",
                        "HIGH",
                    )
                )
            elif is_bare and only_pass_ellipsis:
                findings.append(
                    Finding(
                        str(p.relative_to(root)),
                        "except_bare_pass",
                        f"L{node.lineno}",
                        "HIGH",
                    )
                )
    return findings


def sample_public_docstrings(files: list[Path], root: Path, *, limit: int = 30) -> dict[str, Any]:
    """Sample public functions in critical modules for docstring + return annotation."""
    critical = [
        root / "scripts" / "golden_path.py",
        root / "scripts" / "ops" / "canonical_entry_points.py",
        root / "scripts" / "ops" / "source_contract_tests.py",
        root / "scripts" / "coverage" / "applicability_matrix.py",
        root / "scripts" / "reports" / "operational_outputs.py",
        root / "scripts" / "crawl" / "registry.py",
    ]
    stats = {"n_public_funcs": 0, "with_docstring": 0, "with_return_hint": 0, "samples": []}
    for p in critical:
        if not p.is_file():
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except (OSError, SyntaxError):
            continue
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("_"):
                continue
            stats["n_public_funcs"] += 1
            doc = ast.get_docstring(node)
            if doc:
                stats["with_docstring"] += 1
            if node.returns is not None:
                stats["with_return_hint"] += 1
            if len(stats["samples"]) < limit:
                stats["samples"].append(
                    {
                        "file": str(p.relative_to(root)),
                        "func": node.name,
                        "docstring": bool(doc),
                        "return_hint": node.returns is not None,
                    }
                )
    n = stats["n_public_funcs"] or 1
    stats["docstring_pct"] = round(100 * stats["with_docstring"] / n, 1)
    stats["return_hint_pct"] = round(100 * stats["with_return_hint"] / n, 1)
    return stats


def run_gate(root: Path | None = None) -> dict[str, Any]:
    root = root or _PROJECT_ROOT
    files = iter_py_files(root)
    name_findings = check_module_names(files, root)
    path_findings, path_inv = check_sys_path_hacks(files, root)
    bare = check_bare_except_pass(files, root)
    docs = sample_public_docstrings(files, root)

    # Policy: zero HIGH bare-except-pass in scripts/ops and scripts/reports (critical path)
    critical_bare = [
        f
        for f in bare
        if f.path.startswith("scripts/ops/")
        or f.path.startswith("scripts/reports/")
        or f.path.startswith("scripts/coverage/")
    ]

    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "n_py_files": len(files),
        "module_names": {
            "n_non_snake": len(name_findings),
            "findings": [asdict(f) for f in name_findings[:50]],
            "ok": len(name_findings) == 0,
        },
        "sys_path": {
            "n_inserts": len(path_inv),
            "n_disallowed": len(path_findings),
            "inventory_sample": path_inv[:40],
            "disallowed": [asdict(f) for f in path_findings[:40]],
            "policy": "Only project-root bootstrap via _PROJECT_ROOT/parents[N] allowed",
            "ok": len(path_findings) < 20,  # brownfield tolerance; track debt
        },
        "except_exception_pass": {
            "n_total": len(bare),
            "n_critical_path": len(critical_bare),
            "critical": [asdict(f) for f in critical_bare[:30]],
            "ok": len(critical_bare) == 0,
        },
        "public_api_sample": docs,
        "public_api_ok": docs.get("docstring_pct", 0) >= 50 and docs.get("return_hint_pct", 0) >= 40,
        "claims": {
            "allowed": [
                "Module naming audited under scripts/",
                "sys.path policy documented with inventory",
                "Critical path free of except Exception: pass",
            ],
            "forbidden": [
                "Entire codebase free of sys.path (brownfield false claim)",
                "LOCAL_READY",
            ],
        },
    }
    result["summary"] = {
        "ok": (
            result["module_names"]["ok"]
            and result["except_exception_pass"]["ok"]
            and result["public_api_ok"]
        ),
    }
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="DoD §27 code organization gate")
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)
    result = run_gate()
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    if args.json:
        print(text)
    else:
        print(f"ok={result['summary']['ok']} py={result['n_py_files']} bare_crit={result['except_exception_pass']['n_critical_path']}")
    return 0 if result["summary"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
