#!/usr/bin/env python3
"""Golden Path — Pipeline de validacao completa do DataLake Extra Consultoria.

Executa a sequencia completa e idempotente:
  1. Verifica conectividade com PostgreSQL
  2. Crawl das fontes prioritarias (pncp, pcp, compras_gov) com
     timeout, retry 3x e backoff exponencial + jitter
  3. Valida freshness gate
  4. Gera relatorios (PDF executivo + Excel rastreavel)

Cada etapa e registrada em um ledger JSON para rastreabilidade.

Modo canônico (default: strict fail-closed):
  - Fonte essencial falhou ou vazia sem success_zero → exit != 0
  - Freshness gate FAIL (se não skip) → exit != 0
  - Relatório Excel/PDF FAIL (se não skip) → exit != 0
  - Zero fontes com dados e zero success_zero → exit != 0

Statuses de run: success | success_zero | partial | degraded | empty | failed

Usage:
    python scripts/golden_path.py
    python scripts/golden_path.py --sources pncp,pcp
    python scripts/golden_path.py --skip-reports
    python scripts/golden_path.py --no-strict   # legado permissivo (não canônico)
    python scripts/golden_path.py --verbose
    python scripts/golden_path.py --ledger-output custom_ledger.json

Exit codes:
    0 — success ou success_zero (todos gates obrigatórios OK)
    1 — failed / empty (sem dados utilizáveis)
    2 — partial (fontes essenciais falharam)
    3 — freshness gate reprovado (strict)
    4 — relatório obrigatório falhou (strict)
    5 — degraded (gates mistos / não essencial)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Rich console (optional dep)
# ---------------------------------------------------------------------------
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    HAS_RICH = True
    _console = Console()
except ImportError:
    HAS_RICH = False
    _console = None

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"
_OUTPUT_DIR = _PROJECT_ROOT / "output"
_GOLDEN_PATH_DIR = _OUTPUT_DIR / "golden-path"
_GOLDEN_PATH_DIR.mkdir(parents=True, exist_ok=True)
_LEDGER_PATH = _GOLDEN_PATH_DIR / "ledger.json"

# ---------------------------------------------------------------------------
# Source definitions
# ---------------------------------------------------------------------------


@dataclass
class SourceDef:
    name: str
    essential: bool
    description: str
    timeout_s: int = 120
    max_retries: int = 3


SOURCES: list[SourceDef] = [
    SourceDef(
        name="pncp",
        essential=False,  # Degradado: API não responde HTTP (TCP OK, servidor mudo)
        description="PNCP API (degradada — timeout HTTP, usando cache DB)",
        timeout_s=15,  # Reduzido: API não responde após TLS handshake
        max_retries=1,
    ),
    SourceDef(
        name="pcp",
        essential=True,
        description="PCP (Portal de Compras Publicas)",
    ),
    SourceDef(
        name="compras_gov",
        essential=True,
        description="ComprasGov (compras federais SC)",
    ),
]


def _backoff_delay(attempt: int, base: float = 4.0, max_delay: float = 60.0) -> float:
    """Exponential backoff with jitter."""
    delay = min(base * (2**attempt), max_delay)
    jitter = random.uniform(0, delay * 0.15)  # noqa: S311
    return delay + jitter


# ---------------------------------------------------------------------------
# Ledger types
# ---------------------------------------------------------------------------


@dataclass
class StepRecord:
    step: str
    status: str  # pass | fail | skipped
    duration_ms: float
    error: str | None = None
    details: dict[str, Any] | None = None


@dataclass
class SourceRecord:
    name: str
    status: str  # success | success_zero | fail | skipped
    duration_ms: float
    attempts: int
    metrics: dict[str, int] | None = None
    error: str | None = None


@dataclass
class ReportRecord:
    type: str  # excel | pdf
    status: str  # generated | skipped | fail
    path: str | None = None
    error: str | None = None


@dataclass
class FreshnessRecord:
    status: str  # pass | fail | skipped
    details: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class RunRecord:
    run_id: str
    timestamp: str
    status: str  # success | success_zero | partial | degraded | empty | failed
    wall_clock_ms: float
    steps: list[StepRecord] = field(default_factory=list)
    sources: list[SourceRecord] = field(default_factory=list)
    reports: list[ReportRecord] = field(default_factory=list)
    freshness: FreshnessRecord | None = None
    # DoD §12.1: reproducible provenance on every run
    metadata: dict[str, Any] = field(default_factory=dict)


def evaluate_run_outcome(
    source_records: list[SourceRecord],
    essential_names: set[str],
    freshness: FreshnessRecord | None,
    reports: list[ReportRecord],
    *,
    strict: bool = True,
    skip_freshness: bool = False,
    skip_reports: bool = False,
    allow_zero: bool = False,
) -> tuple[str, int]:
    """Classify overall status and exit code (pure; unit-testable).

    Fail-closed when ``strict=True`` (canonical path):
    - essential source fail → partial / exit 2
    - essential source success_zero without allow_zero → empty / exit 1
    - no success and no success_zero → failed / exit 1
    - freshness fail (not skipped) → exit 3
    - mandatory report fail (not skipped) → exit 4
    """
    if not source_records:
        return "failed", 1

    by_status: dict[str, list[SourceRecord]] = {}
    for rec in source_records:
        by_status.setdefault(rec.status, []).append(rec)

    successes = by_status.get("success", [])
    zeros = by_status.get("success_zero", [])
    fails = by_status.get("fail", [])

    essential_fail = [r for r in fails if r.name in essential_names]
    essential_zero = [r for r in zeros if r.name in essential_names]
    essential_ok = [r for r in successes if r.name in essential_names]
    non_essential_fail = [r for r in fails if r.name not in essential_names]

    freshness_status = (freshness.status if freshness else "skipped")
    if skip_freshness:
        freshness_status = "skipped"
    report_fails = [
        r for r in reports if r.status == "fail" and not skip_reports
    ]

    # --- non-strict legacy path (explicit opt-out only) ---
    if not strict:
        if not successes and not zeros:
            return "failed", 1
        if essential_fail:
            return "partial", 2
        if non_essential_fail:
            return "degraded", 0
        if successes:
            return "success", 0
        return "success_zero", 0

    # --- strict fail-closed ---
    if essential_fail:
        return "partial", 2

    if not successes and not zeros:
        return "failed", 1

    if essential_zero and not essential_ok and not allow_zero:
        # Empty essential sources are not global success in strict mode
        if freshness_status == "fail":
            return "empty", 3
        if report_fails:
            return "empty", 4
        return "empty", 1

    if not successes and zeros:
        overall = "success_zero"
    elif non_essential_fail:
        overall = "degraded"
    else:
        overall = "success"

    if freshness_status == "fail":
        return overall if overall == "empty" else "failed", 3

    if report_fails:
        return "failed", 4

    if overall == "degraded":
        # Non-essential failure with all mandatory gates green → still non-zero
        # so operators cannot treat degraded as full success.
        return "degraded", 5

    return overall, 0


# ---------------------------------------------------------------------------
# Ledger persistence
# ---------------------------------------------------------------------------


def _normalize_ledger_runs(runs: Any) -> list[dict]:
    """Return a flat list of run records; unwrap nested corruption safely."""
    # Prior bug: _save_final_ledger passed the whole ledger dict into _save_ledger,
    # producing {"version":1,"runs":{"version":1,"runs":[...]}}.
    while isinstance(runs, dict) and "runs" in runs:
        runs = runs["runs"]
    if not isinstance(runs, list):
        return []
    return [r for r in runs if isinstance(r, dict)]


def _load_ledger() -> dict:
    if _LEDGER_PATH.exists():
        try:
            with open(_LEDGER_PATH) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"version": 1, "runs": []}
        if not isinstance(data, dict):
            return {"version": 1, "runs": []}
        return {
            "version": data.get("version", 1),
            "runs": _normalize_ledger_runs(data.get("runs", [])),
        }
    return {"version": 1, "runs": []}


def _save_ledger(runs: list[dict], ledger_path: Path | None = None) -> None:
    path = ledger_path or _LEDGER_PATH
    data = _load_ledger()
    data["runs"] = _normalize_ledger_runs(runs)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_log_file = _GOLDEN_PATH_DIR / f"gp-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(_log_file)),
    ],
)
_logger = logging.getLogger("golden-path")


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _echo(msg: str = "", style: str = "default") -> None:
    if HAS_RICH and _console:
        style_map: dict[str, str] = {
            "info": "bold cyan",
            "ok": "bold green",
            "warn": "bold yellow",
            "error": "bold red",
            "header": "bold white on blue",
            "default": "",
        }
        s = style_map.get(style, "")
        if s:
            _console.print(msg, style=s)
        else:
            _console.print(msg)
    else:
        print(msg)


def _print_table(title: str, columns: list[str], rows: list[list[str]]) -> None:
    if HAS_RICH and _console:
        table = Table(title=title, title_style="bold")
        for col in columns:
            table.add_column(col)
        for row in rows:
            table.add_row(*row)
        _console.print(table)
    else:
        header = " | ".join(columns)
        sep = "-" * max(len(h) for h in columns) * 2
        print(f"\n=== {title} ===")
        print(header)
        print(sep)
        for row in rows:
            print(" | ".join(row))


# ---------------------------------------------------------------------------
# Step 1: DB Connectivity
# ---------------------------------------------------------------------------


def check_db(dsn: str) -> tuple[bool, float]:
    """Test PostgreSQL connectivity. Returns (ok, duration_ms)."""
    start = time.monotonic()
    try:
        import psycopg2

        conn = psycopg2.connect(dsn, connect_timeout=10)
        conn.close()
        dur = (time.monotonic() - start) * 1000
        return True, dur
    except Exception as exc:
        dur = (time.monotonic() - start) * 1000
        _logger.error("DB connectivity failed: %s", exc)
        return False, dur


# ---------------------------------------------------------------------------
# Step 2: Crawl Sources (with timeout, retry, backoff + jitter)
# ---------------------------------------------------------------------------


def crawl_source(
    source: SourceDef,
    dsn: str,
    output_json: Path,
) -> SourceRecord:
    """Execute a single source crawl with retry logic."""
    _echo(f"\n>>> Iniciando crawl: {source.name} — {source.description}", "info")

    attempts = 0
    last_error: str | None = None
    metrics: dict[str, int] = {}

    for attempt in range(1, source.max_retries + 1):
        start = time.monotonic()
        try:
            child_env = os.environ.copy()
            # Ensure project root is importable for `config.*` and `scripts.*`
            # when monitor.py is launched as a subprocess (not as -m package).
            root = str(_PROJECT_ROOT)
            existing = child_env.get("PYTHONPATH", "")
            child_env["PYTHONPATH"] = root if not existing else f"{root}{os.pathsep}{existing}"
            result = subprocess.run(  # noqa: S603
                [
                    sys.executable,
                    str(_SCRIPTS_DIR / "crawl" / "monitor.py"),
                    "--source",
                    source.name,
                    "--mode",
                    "incremental",  # Default: incremental (daily). Full mode too slow (365d crawl)
                    "--dsn",
                    dsn,
                    "--output-json",
                    str(output_json),
                ],
                cwd=str(_PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=source.timeout_s,
                env=child_env,
            )
            dur = (time.monotonic() - start) * 1000
            attempts = attempt

            if result.returncode == 0:
                # Parse structured output from monitor.py --output-json
                if output_json.exists():
                    try:
                        data = json.loads(output_json.read_text())
                        summary = data.get("summary", {})
                        metrics = {
                            "fetched": summary.get("total_fetched", 0),
                            "transformed": summary.get("total_transformed", 0),
                            "inserted": summary.get("total_inserted", 0),
                            "updated": summary.get("total_updated", 0),
                            "matched": summary.get("total_matched", 0),
                            "persisted": summary.get("total_persisted_opportunities", 0),
                            "external_failures": summary.get("total_external_failures", 0),
                        }
                    except (json.JSONDecodeError, KeyError):
                        pass

                fetched = int(metrics.get("fetched", 0) or 0)
                # Exit 0 with zero records is success_zero, never silent "success".
                src_status = "success_zero" if fetched == 0 else "success"
                label = "ZERO" if src_status == "success_zero" else "OK"
                _echo(
                    f"  {label} {source.name}: "
                    f"fetched={fetched}, "
                    f"inserted={metrics.get('inserted', 0)}, "
                    f"persisted={metrics.get('persisted', 0)}",
                    "ok" if src_status == "success" else "warn",
                )
                return SourceRecord(
                    name=source.name,
                    status=src_status,
                    duration_ms=dur,
                    attempts=attempts,
                    metrics=metrics,
                )

            # Non-zero exit
            last_error = (result.stderr or result.stdout or "").strip()[-300:]
            _echo(
                f"  Attempt {attempt}/{source.max_retries} failed: exit {result.returncode}",
                "warn",
            )

        except subprocess.TimeoutExpired:
            dur = (time.monotonic() - start) * 1000
            attempts = attempt
            last_error = f"timeout after {source.timeout_s}s"
            _echo(
                f"  Attempt {attempt}/{source.max_retries} timed out ({source.timeout_s}s)",
                "warn",
            )

        except Exception as exc:
            dur = (time.monotonic() - start) * 1000
            attempts = attempt
            last_error = str(exc)
            _echo(f"  Attempt {attempt}/{source.max_retries} error: {exc}", "warn")

        # Retry or fail
        if attempt < source.max_retries:
            delay = _backoff_delay(attempt - 1)
            _echo(f"  Retrying in {delay:.1f}s... (backoff+jitter)", "warn")
            time.sleep(delay)
        else:
            return SourceRecord(
                name=source.name,
                status="fail",
                duration_ms=dur,
                attempts=attempts,
                error=last_error,
            )

    return SourceRecord(
        name=source.name,
        status="fail",
        duration_ms=0,
        attempts=attempts,
        error=last_error,
    )


# ---------------------------------------------------------------------------
# Step 3: Freshness Gate
# ---------------------------------------------------------------------------


def run_freshness_gate(dsn: str) -> FreshnessRecord:
    """Execute freshness_gate.py and parse its output."""
    _echo("\n>>> Validando freshness gate...", "info")
    start = time.monotonic()
    try:
        result = subprocess.run(  # noqa: S603
            [sys.executable, str(_SCRIPTS_DIR / "freshness_gate.py")],
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
            env={
                **os.environ,
                "LOCAL_DATALAKE_DSN": dsn,
                "PYTHONPATH": f"{_PROJECT_ROOT}:{os.environ.get('PYTHONPATH', '')}",
            },
        )
        dur = (time.monotonic() - start) * 1000

        # Read output JSON produced by freshness_gate.py
        gate_path = _OUTPUT_DIR / "readiness" / "freshness-gate.json"
        details: dict[str, Any] | None = None
        if gate_path.exists():
            details = json.loads(gate_path.read_text())

        if result.returncode == 0:
            _echo(f"  Freshness gate: PASS ({dur:.0f}ms)", "ok")
            return FreshnessRecord(
                status="pass",
                details=details,
            )
        else:
            _echo(f"  Freshness gate: FAIL (stale sources) ({dur:.0f}ms)", "warn")
            if details:
                failing = details.get("overall", {}).get("failing_sources", [])
                if failing:
                    _echo(f"    Sources stale: {', '.join(failing)}", "warn")
            return FreshnessRecord(
                status="fail",
                details=details,
                error=result.stderr[-300:] if result.stderr else None,
            )
    except Exception as exc:
        dur = (time.monotonic() - start) * 1000
        _echo(f"  Freshness gate error: {exc}", "warn")
        return FreshnessRecord(
            status="fail",
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# Step 4: Reports (Excel + PDF)
# ---------------------------------------------------------------------------


def run_reports(dsn: str) -> list[ReportRecord]:
    """Generate panorama reports (Excel + PDF)."""
    reports: list[ReportRecord] = []

    # --- Excel ---
    _echo("\n>>> Gerando relatorio Excel...", "info")
    try:
        result = subprocess.run(  # noqa: S603
            [
                sys.executable,
                str(_SCRIPTS_DIR / "reports" / "panorama.py"),
                "--output-excel",
                "--dsn",
                dsn,
            ],
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            excel_files = sorted(
                (_OUTPUT_DIR / "excels").glob("panorama-*.xlsx"),
                key=lambda p: p.stat().st_mtime,
            )
            path = str(excel_files[-1]) if excel_files else None
            _echo(f"  Excel: {path or 'generated'}", "ok")
            reports.append(ReportRecord(type="excel", status="generated", path=path))
        else:
            err = (result.stderr or result.stdout or "")[-300:]
            _echo(f"  Excel report failed: {err}", "warn")
            reports.append(ReportRecord(type="excel", status="fail", error=err))
    except Exception as exc:
        _echo(f"  Excel report error: {exc}", "warn")
        reports.append(ReportRecord(type="excel", status="fail", error=str(exc)))

    # --- PDF ---
    _echo("\n>>> Gerando relatorio PDF...", "info")
    try:
        result = subprocess.run(  # noqa: S603
            [
                sys.executable,
                str(_SCRIPTS_DIR / "reports" / "panorama.py"),
                "--output-pdf",
                "--dsn",
                dsn,
            ],
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            pdf_files = sorted(
                (_OUTPUT_DIR / "pdfs").glob("panorama-*.pdf"),
                key=lambda p: p.stat().st_mtime,
            )
            path = str(pdf_files[-1]) if pdf_files else None
            _echo(f"  PDF: {path or 'generated'}", "ok")
            reports.append(ReportRecord(type="pdf", status="generated", path=path))
        else:
            err = (result.stderr or result.stdout or "")[-300:]
            _echo(f"  PDF report failed: {err}", "warn")
            reports.append(ReportRecord(type="pdf", status="fail", error=err))
    except Exception as exc:
        _echo(f"  PDF report error: {exc}", "warn")
        reports.append(ReportRecord(type="pdf", status="fail", error=str(exc)))

    return reports


# ---------------------------------------------------------------------------
# Save final ledger
# ---------------------------------------------------------------------------


def collect_run_metadata(
    *,
    dsn: str | None = None,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    """Metadata required by DoD §12.1 (git, schema, universe hash, period)."""
    git_sha: str | None = None
    git_branch: str | None = None
    try:
        from scripts.crawl.run_evidence import get_git_meta

        meta = get_git_meta()
        git_sha = meta.get("git_sha")
        git_branch = meta.get("git_branch")
    except Exception:
        try:
            git_sha = (
                subprocess.check_output(
                    ["git", "rev-parse", "HEAD"],  # noqa: S607
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    cwd=str(_PROJECT_ROOT),
                )
                .decode()
                .strip()
            )
        except (subprocess.SubprocessError, OSError, FileNotFoundError):
            git_sha = None

    spreadsheet_hash: str | None = None
    universe_count: int | None = None
    try:
        from scripts.lib.universe import (
            DEFAULT_SEED_PATH,
            load_canonical_universe,
            sha256_file,
        )

        seed = Path(DEFAULT_SEED_PATH)
        if seed.is_file():
            spreadsheet_hash = sha256_file(seed)
        uni = load_canonical_universe()
        universe_count = len(getattr(uni, "entities", uni) or [])
    except Exception as exc:  # noqa: BLE001
        limitations = list(limitations or [])
        limitations.append(f"universe_metadata_unavailable: {exc}")

    schema_version: str | None = None
    mig_count = 0
    try:
        from scripts.ops.apply_migrations import list_migrations

        migs = list_migrations(_PROJECT_ROOT / "db" / "migrations")
        mig_count = len(migs)
        if migs:
            schema_version = migs[-1].name
    except Exception:
        pass

    now = datetime.now(UTC)
    lims = list(limitations or [])
    lims.append(
        "Golden path local: coverage operacional e recall 95% não são inferidos "
        "deste run sem medição estrita separada."
    )
    return {
        "git_sha": git_sha,
        "git_branch": git_branch,
        "schema_version": schema_version,
        "migration_files_count": mig_count,
        "spreadsheet_hash": spreadsheet_hash,
        "universe_entity_count": universe_count,
        "reference_period": {
            "as_of": now.date().isoformat(),
            "timezone": "UTC",
        },
        "limitations": lims,
        "dsn_host_hint": (dsn or "").split("@")[-1] if dsn and "@" in dsn else "configured_or_default",
        "canonical_command": "python3 -m scripts.golden_path",
    }


def bootstrap_foundation(dsn: str) -> list[StepRecord]:
    """Apply migrations + validate/import universe seed (idempotent)."""
    steps: list[StepRecord] = []
    # Migrations: validate files + schema presence (idempotent; re-apply is not always safe)
    t0 = time.monotonic()
    try:
        from scripts.ops.apply_migrations import list_migrations

        root = _PROJECT_ROOT / "db" / "migrations"
        files = list_migrations(root)
        table_count = 0
        err = None
        try:
            import psycopg2

            conn = psycopg2.connect(dsn, connect_timeout=5)
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT count(*) FROM information_schema.tables "
                        "WHERE table_schema='public'"
                    )
                    table_count = int(cur.fetchone()[0])
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
        # Pass if migration files exist and DB has public tables (schema applied)
        ok = bool(files) and table_count > 0 and err is None
        steps.append(
            StepRecord(
                step="apply_migrations",
                status="pass" if ok else "fail",
                duration_ms=(time.monotonic() - t0) * 1000,
                error=err if not ok else None,
                details={
                    "migration_files": len(files),
                    "public_tables": table_count,
                    "note": "idempotent schema validation (not re-apply all SQL)",
                },
            )
        )
    except Exception as exc:  # noqa: BLE001
        steps.append(
            StepRecord(
                step="apply_migrations",
                status="fail",
                duration_ms=(time.monotonic() - t0) * 1000,
                error=str(exc),
            )
        )

    # Universe seed / planilha
    t1 = time.monotonic()
    try:
        from scripts.lib.universe import (
            DEFAULT_SEED_PATH,
            load_canonical_universe,
            sha256_file,
        )

        seed = Path(DEFAULT_SEED_PATH)
        if not seed.is_file():
            steps.append(
                StepRecord(
                    step="import_universe_seed",
                    status="fail",
                    duration_ms=(time.monotonic() - t1) * 1000,
                    error=f"seed missing: {seed}",
                )
            )
        else:
            uni = load_canonical_universe()
            try:
                n = len(uni.entities)
            except Exception:
                n = int(getattr(uni, "count", 0) or 0)
            h = sha256_file(seed)
            steps.append(
                StepRecord(
                    step="import_universe_seed",
                    status="pass" if n > 0 else "fail",
                    duration_ms=(time.monotonic() - t1) * 1000,
                    details={"entities": n, "spreadsheet_hash": h, "path": str(seed)},
                    error=None if n > 0 else "universe empty",
                )
            )
    except Exception as exc:  # noqa: BLE001
        steps.append(
            StepRecord(
                step="import_universe_seed",
                status="fail",
                duration_ms=(time.monotonic() - t1) * 1000,
                error=str(exc),
            )
        )
    return steps


def _save_final_ledger(
    run_id: str,
    timestamp: str,
    overall: str,
    steps: list[StepRecord],
    sources: list[SourceRecord],
    reports: list[ReportRecord],
    freshness: FreshnessRecord | None,
    wall_start: float,
    ledger_path_str: str | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    wall_dur = (time.monotonic() - wall_start) * 1000
    record = RunRecord(
        run_id=run_id,
        timestamp=timestamp,
        status=overall,
        wall_clock_ms=wall_dur,
        steps=steps,
        sources=sources,
        reports=reports,
        freshness=freshness,
        metadata=metadata or {},
    )
    data = _load_ledger()
    run_list = _normalize_ledger_runs(data.get("runs", []))
    run_list.append(asdict(record))
    path = Path(ledger_path_str) if ledger_path_str else _LEDGER_PATH
    _save_ledger(run_list, path)
    _echo(f"\nLedger salvo:  {path}")
    _echo(f"Log salvo:     {_log_file}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Golden Path — Pipeline de validacao completa do DataLake Extra Consultoria",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--sources",
        default="pncp,pcp,compras_gov",
        help="Comma-separated source names (default: pncp,pcp,compras_gov)",
    )
    p.add_argument(
        "--skip-freshness",
        action="store_true",
        help="Skip freshness gate validation",
    )
    p.add_argument(
        "--skip-reports",
        action="store_true",
        help="Skip report generation (Excel + PDF)",
    )
    p.add_argument(
        "--strict",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fail-closed on empty essential sources, freshness fail, report fail (default: true)",
    )
    p.add_argument(
        "--allow-zero",
        action="store_true",
        help="In strict mode, accept essential success_zero as valid global success_zero",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose/debug output",
    )
    p.add_argument(
        "--dsn",
        default=None,
        help="PostgreSQL DSN (default: LOCAL_DATALAKE_DSN env var or config.settings)",
    )
    p.add_argument(
        "--ledger-output",
        default=str(_LEDGER_PATH),
        help="Output path for execution ledger JSON (default: output/golden-path/ledger.json)",
    )
    p.add_argument(
        "--bootstrap",
        action="store_true",
        help="Apply migrations + validate universe seed before crawl (DoD §12.1 foundation)",
    )
    p.add_argument(
        "--skip-crawl",
        action="store_true",
        help="Skip live crawl (use with --bootstrap for foundation-only proof; not full product coverage)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    wall_start = time.monotonic()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # ── Resolve DSN ──
    dsn = args.dsn or os.getenv("LOCAL_DATALAKE_DSN")
    if not dsn:
        try:
            import config.settings as _cfg

            dsn = _cfg.LOCAL_DATALAKE_DSN
        except ImportError:
            dsn = "postgresql://postgres:@127.0.0.1:54399/postgres"

    # ── Resolve sources ──
    source_names_arg = [s.strip() for s in args.sources.split(",")]
    selected_sources = [s for s in SOURCES if s.name in source_names_arg]
    if not selected_sources:
        _echo(
            f"ERROR: No valid sources in '{args.sources}'. Available: {', '.join(s.name for s in SOURCES)}",
            "error",
        )
        return 1

    run_id = f"gp-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    timestamp = datetime.now(UTC).isoformat()

    steps: list[StepRecord] = []
    source_records: list[SourceRecord] = []
    report_records: list[ReportRecord] = []
    freshness_record: FreshnessRecord | None = None

    # ── Header ──
    _echo("")
    panel_text = (
        "[bold]GOLDEN PATH[/bold] — Pipeline de Validacao do DataLake\n"
        f"Run: {run_id}  |  "
        f"Fontes: {', '.join(s.name for s in selected_sources)}  |  "
        f"DSN: {dsn[:60]}..."
    )
    if HAS_RICH:
        _echo(Panel.fit(panel_text))
    else:
        _echo(f"{'=' * 60}")
        _echo(f"  GOLDEN PATH — {run_id}")
        _echo(f"{'=' * 60}")

    # =========================================================================
    # Step 1: DB Connectivity
    # =========================================================================
    _echo("\n[1/4] Verificando conectividade PostgreSQL...", "header")
    ok, dur = check_db(dsn)
    steps.append(
        StepRecord(
            step="db_connectivity",
            status="pass" if ok else "fail",
            duration_ms=dur,
        )
    )
    if not ok:
        _echo("  PostgreSQL NAO respondeu. Execute 'make db-up' primeiro.", "error")
        _echo(f"  DSN: {dsn}", "warn")
        _save_final_ledger(
            run_id,
            timestamp,
            "failed",
            steps,
            source_records,
            report_records,
            freshness_record,
            wall_start,
            args.ledger_output,
        )
        return 1
    _echo(f"  PostgreSQL OK ({dur:.0f}ms)", "ok")

    run_metadata = collect_run_metadata(dsn=dsn)

    # =========================================================================
    # Step 1b: Bootstrap (migrations + universe) — optional / recommended
    # =========================================================================
    if args.bootstrap:
        _echo("\n[1b] Bootstrap foundation (migrations + universe)...", "header")
        boot_steps = bootstrap_foundation(dsn)
        steps.extend(boot_steps)
        for st in boot_steps:
            mark = "OK" if st.status == "pass" else "FAIL"
            _echo(f"  [{mark}] {st.step} ({st.duration_ms:.0f}ms)", "ok" if st.status == "pass" else "error")
            if st.error:
                _echo(f"       {st.error}", "warn")
        if any(s.status == "fail" for s in boot_steps) and args.strict:
            _save_final_ledger(
                run_id,
                timestamp,
                "failed",
                steps,
                source_records,
                report_records,
                freshness_record,
                wall_start,
                args.ledger_output,
                metadata=run_metadata,
            )
            return 1

    # =========================================================================
    # Step 2: Crawl Sources
    # =========================================================================
    _echo("\n[2/4] Crawl das fontes de dados...", "header")
    if args.skip_crawl:
        _echo("  SKIP (--skip-crawl) — foundation/metadata only", "warn")
        for src in selected_sources:
            source_records.append(
                SourceRecord(
                    name=src.name,
                    status="success_zero",
                    duration_ms=0.0,
                    attempts=0,
                    metrics={"fetched": 0, "inserted": 0, "persisted": 0},
                    error="skip_crawl",
                )
            )
    else:
        _echo(f"  Fontes: {', '.join(s.name for s in selected_sources)}")
        _echo("  Timeout: 120s por fonte  |  Retries: 3x com backoff+jitter")

        for src in selected_sources:
            output_json = _GOLDEN_PATH_DIR / f"crawl-{src.name}-{run_id}.json"
            rec = crawl_source(src, dsn, output_json)
            source_records.append(rec)

    # Classify
    sources_success = [r for r in source_records if r.status == "success"]
    sources_zero = [r for r in source_records if r.status == "success_zero"]
    sources_fail = [r for r in source_records if r.status == "fail"]
    essential_names = {s.name for s in selected_sources if s.essential}
    essential_fail = [r for r in sources_fail if r.name in essential_names]

    def _src_label(status: str) -> str:
        return {
            "success": "OK",
            "success_zero": "ZERO",
            "fail": "FAIL",
            "skipped": "SKIP",
        }.get(status, status.upper())

    _echo("")
    _print_table(
        "Resultados por Fonte",
        ["Fonte", "Status", "Tempo", "Tentativas", "Fetched", "Inserted", "Persistidas"],
        [
            [
                r.name,
                _src_label(r.status),
                f"{r.duration_ms:.0f}ms",
                str(r.attempts),
                str((r.metrics or {}).get("fetched", "-")),
                str((r.metrics or {}).get("inserted", "-")),
                str((r.metrics or {}).get("persisted", "-")),
            ]
            for r in source_records
        ],
    )

    if sources_fail or sources_zero:
        _echo(
            f"\n  {len(sources_success)} com dados, "
            f"{len(sources_zero)} zero, {len(sources_fail)} falha(s)",
            "warn",
        )
        for r in sources_fail:
            _echo(f"    {r.name}: {r.error or 'erro desconhecido'}", "warn")
        for r in sources_zero:
            _echo(f"    {r.name}: success_zero (fetched=0)", "warn")
    else:
        _echo(f"\n  {len(sources_success)}/{len(selected_sources)} fontes OK", "ok")

    # =========================================================================
    # Step 3: Freshness Gate
    # =========================================================================
    _echo("\n[3/4] Freshness Gate...", "header")
    if args.skip_freshness:
        _echo("  SKIP (--skip-freshness)", "warn")
        freshness_record = FreshnessRecord(status="skipped")
    else:
        freshness_record = run_freshness_gate(dsn)

    # =========================================================================
    # Step 4: Reports
    # =========================================================================
    _echo("\n[4/4] Geracao de relatorios...", "header")
    if args.skip_reports:
        _echo("  SKIP (--skip-reports)", "warn")
        report_records = [
            ReportRecord(type="excel", status="skipped"),
            ReportRecord(type="pdf", status="skipped"),
        ]
    else:
        report_records = run_reports(dsn)

    # =========================================================================
    # Summary
    # =========================================================================
    wall_dur = (time.monotonic() - wall_start) * 1000

    overall, exit_code = evaluate_run_outcome(
        source_records,
        essential_names,
        freshness_record,
        report_records,
        strict=bool(args.strict),
        skip_freshness=bool(args.skip_freshness),
        skip_reports=bool(args.skip_reports),
        allow_zero=bool(args.allow_zero),
    )

    freshness_str = freshness_record.status if freshness_record else "N/A"
    excel_status = report_records[0].status if report_records else "N/A"
    pdf_status = report_records[1].status if len(report_records) > 1 else "N/A"
    mode_str = "strict" if args.strict else "no-strict"

    summary_text = (
        f"[bold]GOLDEN PATH — RESUMO[/bold]\n\n"
        f"Run ID:          {run_id}\n"
        f"Mode:            {mode_str}\n"
        f"Status:          {overall.upper()}\n"
        f"Exit code:       {exit_code}\n"
        f"Fontes c/ dados: {len(sources_success)}/{len(selected_sources)}\n"
        f"Fontes zero:     {len(sources_zero)}\n"
        f"Fontes essenciais com falha: {len(essential_fail)}\n"
        f"Freshness gate:  {freshness_str}\n"
        f"Excel:           {excel_status}\n"
        f"PDF:             {pdf_status}\n"
        f"Wall clock:      {wall_dur:.0f}ms ({wall_dur / 1000:.1f}s)"
    )

    _echo("")
    if HAS_RICH:
        _echo(Panel.fit(summary_text))
    else:
        _echo(f"\n{'=' * 60}")
        _echo("  GOLDEN PATH — RESUMO")
        _echo(f"  Mode: {mode_str}")
        _echo(f"  Status: {overall.upper()}")
        _echo(f"  Exit: {exit_code}")
        _echo(f"  Wall clock: {wall_dur:.0f}ms ({wall_dur / 1000:.1f}s)")
        _echo(f"{'=' * 60}")

    # ── Persist ledger ──
    _save_final_ledger(
        run_id,
        timestamp,
        overall,
        steps,
        source_records,
        report_records,
        freshness_record,
        wall_start,
        args.ledger_output,
        metadata=run_metadata,
    )

    # ── Exit ──
    if exit_code == 0:
        if overall == "success_zero":
            _echo("\nGolden Path: success_zero (sem registros, gates OK).", "warn")
        else:
            _echo("\nGolden Path concluido com sucesso!", "ok")
        return 0

    messages = {
        1: "FALHA/EMPTY: sem dados utilizáveis ou essential zero sem --allow-zero",
        2: "PARCIAL: fontes essenciais falharam",
        3: "FRESHNESS FAIL: gate de freshness reprovado (strict)",
        4: "REPORT FAIL: Excel/PDF obrigatório falhou (strict)",
        5: "DEGRADED: fontes não essenciais falharam (strict)",
    }
    _echo(f"\n{messages.get(exit_code, f'Exit {exit_code}')}. Verifique o ledger.", "error")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
