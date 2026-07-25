"""Fail-closed scan: unexpected module-level pytest skips / importorskip.

Usage:
  python -m scripts.ops.check_pytest_skip_policy
  python -m scripts.ops.check_pytest_skip_policy --root tests

Exit 0 = pass, 1 = violations, 2 = error.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST_PATH = REPO_ROOT / "docs" / "pytest-skip-allowlist.json"


def _load_allowlist() -> set[str]:
    if not ALLOWLIST_PATH.is_file():
        return set()
    data = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    return {str(p) for p in (data.get("module_level_skips") or [])}


def _is_module_level_skip(node: ast.AST) -> bool:
    """True for module-level pytest.importorskip(...) or pytest.skip(...)."""
    if not isinstance(node, ast.Expr):
        return False
    call = node.value
    if not isinstance(call, ast.Call):
        return False
    func = call.func
    # pytest.importorskip / pytest.skip
    if isinstance(func, ast.Attribute) and func.attr in {"importorskip", "skip"}:
        if isinstance(func.value, ast.Name) and func.value.id == "pytest":
            return True
    # bare importorskip if from pytest import importorskip — skip for now
    return False


def scan_file(path: Path) -> list[dict[str, object]]:
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as exc:
        return [{"path": str(path), "reason": f"syntax_error:{exc}"}]
    hits: list[dict[str, object]] = []
    for node in tree.body:  # module body only
        if _is_module_level_skip(node):
            hits.append(
                {
                    "path": str(path.as_posix()),
                    "lineno": getattr(node, "lineno", 0),
                    "reason": "module_level_pytest_skip",
                }
            )
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="tests", help="tests root directory")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = REPO_ROOT / args.root
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2

    allow = _load_allowlist()
    violations: list[dict[str, object]] = []
    for py in sorted(root.rglob("*.py")):
        rel = py.relative_to(REPO_ROOT).as_posix()
        for hit in scan_file(py):
            # normalize path relative
            p = hit.get("path", rel)
            if isinstance(p, str) and p.startswith(str(REPO_ROOT)):
                p = Path(p).relative_to(REPO_ROOT).as_posix()
                hit["path"] = p
            elif isinstance(p, str) and not p.startswith("tests"):
                # path may be absolute from ast
                try:
                    hit["path"] = Path(p).resolve().relative_to(REPO_ROOT).as_posix()
                except Exception:
                    hit["path"] = rel
            if hit["path"] in allow:
                continue
            violations.append(hit)

    report = {
        "ok": not violations,
        "violation_count": len(violations),
        "violations": violations,
        "allowlist": str(ALLOWLIST_PATH.relative_to(REPO_ROOT)),
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"pytest-skip-policy: violations={len(violations)} "
            f"allowlist_entries={len(allow)}"
        )
        for v in violations:
            print(f"  FAIL {v['path']}:{v.get('lineno')} — {v['reason']}")
        if not violations:
            print("  PASS")
        else:
            print(
                "\nActionable: remove module-level pytest.importorskip/skip, "
                "install the dependency in CI, or add an explicit allowlist "
                f"entry in {ALLOWLIST_PATH.name} with justification."
            )
    return 0 if not violations else 1


if __name__ == "__main__":
    sys.exit(main())
