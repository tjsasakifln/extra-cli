#!/usr/bin/env python3
"""Coverage gate — fail-closed quality gate for module coverage thresholds.

Reads ``.coveragerc`` for the module list, threshold, and output path
(section ``[coverage_gate]``).  Uses ``coverage.CoverageData`` via the
``coverage.py`` API to load ``.coverage``, then calculates per-module and
per-file line coverage percentages.

For directory modules, all ``.py`` files under that directory are aggregated.
Modules that do not exist on the filesystem are reported at 0 % without
crashing.

Output
    ``output/coverage/coverage-gate-report.json`` (configurable)

Exit codes
    0 — all modules meet or exceed the threshold (pass)
    2 — one or more modules below threshold (fail-closed per ADR-014)
    3 — ``.coverage`` not found or unreadable
"""

from __future__ import annotations

import configparser
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# NOTE: ``scripts/coverage/`` is a local package that shadows the third-party
# ``coverage`` library.  When this script (inside ``scripts/``) runs, Python
# prepends ``scripts/`` to ``sys.path`` and resolves ``import coverage`` to
# the local package instead of the installed library.  We remove the script's
# directory from ``sys.path`` before the third-party import to avoid that.
_script_dir = Path(__file__).resolve().parent
if str(_script_dir) in sys.path:
    sys.path.remove(str(_script_dir))

import coverage  # noqa: E402 — safe import after path fix

_logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )


def _load_gate_config(project_root: Path) -> dict[str, Any]:
    """Read ``[coverage_gate]`` from ``.coveragerc``."""
    coveragerc = project_root / ".coveragerc"
    if not coveragerc.exists():
        _logger.error(".coveragerc not found at %s", coveragerc)
        sys.exit(3)

    parser = configparser.ConfigParser()
    parser.read(str(coveragerc))

    if not parser.has_section("coverage_gate"):
        _logger.error("Section [coverage_gate] not found in .coveragerc — add 'modules', 'threshold' and 'output' keys")
        sys.exit(3)

    modules_raw = parser.get("coverage_gate", "modules", fallback="")
    modules = [m.strip() for m in modules_raw.strip().split("\n") if m.strip()]

    if not modules:
        _logger.error("[coverage_gate] modules list is empty")
        sys.exit(3)

    threshold = parser.getint("coverage_gate", "threshold", fallback=80)
    output_rel = parser.get("coverage_gate", "output", fallback="output/coverage/coverage-gate-report.json")

    return {
        "modules": modules,
        "threshold": threshold,
        "output": output_rel,
    }


# ---------------------------------------------------------------------------
# File / module resolution
# ---------------------------------------------------------------------------


def _resolve_module_files(module_path: str, project_root: Path) -> list[Path]:
    """Resolve a module path to its ``.py`` files.

    * Directories are walked recursively.
    * Single-file entries are returned as-is.
    * Non-existent paths return an empty list (reported as 0 % per spec).
    """
    full = project_root / module_path
    if not full.exists():
        return []
    if full.is_dir():
        return sorted(full.rglob("*.py"))
    if full.is_file():
        return [full]
    return []


# ---------------------------------------------------------------------------
# Per-file analysis
# ---------------------------------------------------------------------------


def _analyze_file(
    cov: coverage.Coverage,
    py_file: Path,
    project_root: Path,
) -> dict[str, Any]:
    """Analyze a single ``.py`` file for coverage statistics.

    Uses ``coverage.Coverage.analysis2()`` which parses the source file and
    cross-references with the loaded coverage data.  Files that were not
    measured at all return 0 executed lines.
    """
    abs_path = str(py_file.resolve())

    try:
        _fname, statements, executed, _missing, _excluded = cov.analysis2(abs_path)
    except Exception as exc:
        _logger.warning("Could not analyze %s: %s", abs_path, exc)
        return {
            "file": str(py_file.relative_to(project_root)),
            "total_lines": 0,
            "covered_lines": 0,
            "coverage_pct": 0.0,
        }

    total = len(statements)
    covered = len(executed)
    pct = (covered / total * 100) if total > 0 else 100.0

    return {
        "file": str(py_file.relative_to(project_root)),
        "total_lines": total,
        "covered_lines": covered,
        "coverage_pct": round(pct, 1),
    }


# ---------------------------------------------------------------------------
# Module-level aggregation
# ---------------------------------------------------------------------------


def _analyze_module(
    cov: coverage.Coverage,
    module: str,
    project_root: Path,
    threshold: int,
) -> dict[str, Any]:
    """Calculate aggregate coverage for a module (directory or single file).

    Returns a dict with ``module``, ``coverage_pct``, ``pass``,
    ``total_lines``, ``covered_lines`` and ``files``.
    """
    py_files = _resolve_module_files(module, project_root)

    if not py_files:
        # Module path does not exist on filesystem
        return {
            "module": module,
            "coverage_pct": 0.0,
            "pass": 0.0 >= threshold,
            "total_lines": 0,
            "covered_lines": 0,
            "files": [],
        }

    file_results = [_analyze_file(cov, pf, project_root) for pf in py_files]

    total_lines = sum(f["total_lines"] for f in file_results)
    covered_lines = sum(f["covered_lines"] for f in file_results)
    module_pct = (covered_lines / total_lines * 100) if total_lines > 0 else 100.0

    return {
        "module": module,
        "coverage_pct": round(module_pct, 1),
        "pass": module_pct >= threshold,
        "total_lines": total_lines,
        "covered_lines": covered_lines,
        "files": file_results,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Execute the coverage gate: validate all modules against threshold.

    Reads ``.coveragerc`` section ``[coverage_gate]`` to obtain the list
    of modules (files or directories), the minimum coverage percentage,
    and the output report path.  Loads ``.coverage`` data produced by
    ``pytest --cov=scripts``, computes per-module and per-file coverage,
    then writes a JSON report.

    Exit codes:
        0 — All modules meet or exceed the coverage threshold (pass).
        2 — One or more modules are below the threshold (fail-closed,
            per ADR-014).
        3 — ``.coverage`` not found, ``.coveragerc`` missing/invalid,
            or section ``[coverage_gate]`` is misconfigured.

    Args:
        None.  Configuration is read from ``.coveragerc`` via
        ``_load_gate_config()`` and coverage data from the ``.coverage``
        file in the project root.

    Returns:
        None.  The function exits via ``sys.exit()`` with one of the
        documented exit codes.

    Raises:
        SystemExit: Always — the function never returns normally.
            Exit code 0 (pass), 2 (fail), or 3 (configuration error).

    Example:
        Run after a coverage-enabled test suite::

            $ pytest --cov=scripts
            $ python scripts/coverage_gate.py
            # Output:
            #   INFO | Coverage gate starting
            #   INFO | Threshold: 80 %
            #   INFO | Modules  : 5
            #   INFO | Result: pass  (failed=0, threshold=80 %)

    Edge cases:
        Missing .coverage: If the coverage data file does not exist (tests
            were not run yet), the function logs an error and exits with
            code 3 — fail-closed, never silently pass.
        Non-existent module path: A module listed in ``.coveragerc`` that
            does not exist on the filesystem is reported at 0 % coverage
            without crashing.  This allows gradual module addition.
        Empty modules list: If ``[coverage_gate] modules`` is empty or
            missing entirely, the function exits with code 3.
        Zero-line file: A ``.py`` file with no executable statements (e.g.,
            only imports and docstrings) is treated as 100 % coverage
            (``100.0`` when ``total_lines == 0``).
        Directory modules: Directories are walked recursively.  All
            ``.py`` files found contribute to the module aggregate.  A
            directory with zero ``.py`` files reports 0 % coverage.
        Missing .coveragerc section: If the ``[coverage_gate]`` section
            does not exist in ``.coveragerc``, the function exits with
            code 3 before attempting any analysis.
    """
    _setup_logging()
    _logger.info("Coverage gate starting")

    config = _load_gate_config(PROJECT_ROOT)
    threshold: int = config["threshold"]
    output_rel: str = config["output"]
    output_path = PROJECT_ROOT / output_rel
    modules: list[str] = config["modules"]

    _logger.info("Threshold: %d %%", threshold)
    _logger.info("Modules  : %d", len(modules))
    _logger.info("Output   : %s", output_path)

    # ------------------------------------------------------------------
    # Load .coverage data
    # ------------------------------------------------------------------
    coverage_file = PROJECT_ROOT / ".coverage"
    if not coverage_file.exists():
        _logger.error(
            ".coverage not found at %s — run 'pytest --cov=scripts' first",
            coverage_file,
        )
        sys.exit(3)

    try:
        cov = coverage.Coverage()
        cov.load()
    except Exception as exc:
        _logger.error("Failed to load .coverage data: %s", exc)
        sys.exit(3)

    # ------------------------------------------------------------------
    # Analyze every module
    # ------------------------------------------------------------------
    module_results = [_analyze_module(cov, mod, PROJECT_ROOT, threshold) for mod in modules]

    failed_count = sum(1 for r in module_results if not r["pass"])
    overall_result = "pass" if failed_count == 0 else "fail"

    # ------------------------------------------------------------------
    # Build + write JSON report
    # ------------------------------------------------------------------
    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "threshold": threshold,
        "modules": module_results,
        "result": overall_result,
        "failed_count": failed_count,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    _logger.info("Report written to %s", output_path)

    # ------------------------------------------------------------------
    # Summary & exit
    # ------------------------------------------------------------------
    for mod in module_results:
        status = "PASS" if mod["coverage_pct"] >= threshold else "FAIL"
        _logger.info(
            "  %s: %s (%.1f %% of %d lines)",
            status,
            mod["module"],
            mod["coverage_pct"],
            mod["total_lines"],
        )

    _logger.info(
        "Result: %s  (failed=%d, threshold=%d %%)",
        overall_result,
        failed_count,
        threshold,
    )

    if overall_result == "fail":
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
