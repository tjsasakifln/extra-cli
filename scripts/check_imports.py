#!/usr/bin/env python3
"""
Import checker — verifica que todos os 127+ arquivos Python do projeto
podem ser importados sem ``ImportError``.

Usage:
    python scripts/check_imports.py
    python scripts/check_imports.py --verbose   # mostra cada import

Exit codes:
    0 = OK (zero ImportErrors)
    1 = FAIL (um ou mais ImportErrors encontrados)
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path

# Setup: project root and scripts/ on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"
for p in [_PROJECT_ROOT, _SCRIPTS_DIR]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# Files/dirs to skip (not importable as modules)
SKIP_PATTERNS = (
    "/__pycache__/",
    ".egg-info",
    ".pyc",
    ".pyo",
)

# Known non-importable files (entry-point scripts, __main__ modules, etc.)
SKIP_FILES = frozenset(
    {
        # Entry-point scripts (run via python path/to/script.py, not as modules)
        "scripts/run.py",
        "scripts/validate-report-data.py",
        "scripts/generate-report-b2g.py",
        "scripts/export-sc-200km-final.py",  # module-level DB connection side effect
        # __main__ variant
        "scripts/intel-enrich.py",  # hyphen in name, needs importlib
    }
)

# Files with hyphens that need importlib import
HYPHENATED_FILES = {
    "scripts/intel-enrich.py",
    "scripts/intel-extract-docs.py",
    "scripts/intel-collect.py",
}


def _is_importable(filepath: Path, scripts_dir: Path) -> bool:
    """Check if a .py file is meant to be importable as a module."""
    rel = filepath.relative_to(scripts_dir.parent)  # Relative to project root
    rel_str = str(rel).replace("\\", "/")

    # Hyphenated files are importable via importlib
    if rel_str in HYPHENATED_FILES:
        return True

    # Skip known non-importable files
    if rel_str in SKIP_FILES:
        return False

    # Skip __init__.py (they're imported as packages, not standalone)
    if filepath.name == "__init__.py":
        return False

    # Skip __main__.py
    if filepath.name == "__main__.py":
        return False

    return True


def _try_import_module(filepath: Path, scripts_dir: Path) -> tuple[bool, str]:
    """Try to import a .py file as a module.

    Returns:
        Tuple of (success, error_message).
    """
    rel_path = filepath.relative_to(scripts_dir.parent)
    rel_str = str(rel_path).replace("\\", "/")

    # Determine module name
    # Files under scripts/ → scripts.xxx.yyy
    # Files under project root → check differently
    try:
        rel_to_scripts = filepath.relative_to(scripts_dir)
        parts = list(rel_to_scripts.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        elif parts[-1].endswith(".py"):
            parts[-1] = parts[-1][:-3]
        # Handle files with hyphens in the name
        if "-" in parts[-1]:
            # Can't import with hyphen; use importlib
            return _try_import_via_importlib(filepath, rel_str)
        module_name = "scripts." + ".".join(parts)
    except ValueError:
        # Not under scripts/ - handle as top-level
        return False, f"{rel_str}: outside scripts/ — skipped"

    try:
        importlib.import_module(module_name)
        return True, ""
    except ImportError as e:
        return False, f"{rel_str}: ImportError: {e}"
    except Exception as e:
        return False, f"{rel_str}: {type(e).__name__}: {e}"


def _try_import_via_importlib(filepath: Path, rel_str: str) -> tuple[bool, str]:
    """Try to import a file with a non-standard name (e.g., hyphenated)."""
    try:
        safe_name = filepath.stem.replace("-", "_")
        spec = importlib.util.spec_from_file_location(safe_name, str(filepath))
        if spec is None or spec.loader is None:
            return False, f"{rel_str}: could not create spec"
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return True, ""
    except ImportError as e:
        return False, f"{rel_str}: ImportError: {e}"
    except Exception as e:
        return False, f"{rel_str}: {type(e).__name__}: {e}"


def main() -> int:
    verbose = "--verbose" in sys.argv

    scripts_dir = _SCRIPTS_DIR
    all_py_files: list[Path] = []

    # Collect all .py files under scripts/ (except __pycache__)
    for root, dirs, files in os.walk(str(scripts_dir)):
        # Skip __pycache__
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if not f.endswith(".py"):
                continue
            fp = Path(root) / f
            if any(p in str(fp) for p in SKIP_PATTERNS):
                continue
            if not _is_importable(fp, scripts_dir):
                if verbose:
                    print(f"  SKIP: {fp.relative_to(scripts_dir.parent)} (non-importable)")
                continue
            all_py_files.append(fp)

    total = len(all_py_files)
    passed = 0
    failed = 0
    errors: list[tuple[str, str]] = []

    print(f"Checking {total} Python files for ImportError...\n")

    for i, fp in enumerate(all_py_files, 1):
        success, error = _try_import_module(fp, scripts_dir)
        rel = fp.relative_to(scripts_dir.parent)
        if success:
            passed += 1
            if verbose:
                print(f"  [{i}/{total}] OK:  {rel}")
        else:
            failed += 1
            errors.append((str(rel), error))
            print(f"  [{i}/{total}] FAIL: {rel}")
            if verbose:
                print(f"         {error}")

    print(f"\n{'=' * 50}")
    print(f"Total: {total} | Passed: {passed} | Failed: {failed}")

    if errors:
        print(f"\nFailed files ({len(errors)}):")
        for rel, err in errors:
            print(f"  - {rel}: {err}")
        print("\n❌ CHECK FAILED: Some files have ImportErrors")
        return 1

    print("\n✅ CHECK PASSED: All files import without ImportError")
    return 0


if __name__ == "__main__":
    sys.exit(main())
