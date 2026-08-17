"""Orchestrator: admit DSN → ephemeral PG → migrate → seed → gate → pack → teardown."""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from scripts.coverage.covered_entity import (
    MISSING_EVIDENCE,
    dual_coverage_evidence_gate,
)
from scripts.ops.coverage_live_proof import (
    EPHEMERAL_DB_PREFIX,
    EVIDENCE_SCHEMA_VERSION,
)
from scripts.ops.coverage_live_proof.admission import (
    read_gate_threshold,
    refuse_non_postgres_scheme,
    refuse_production_dsn,
    replace_database_name,
    require_explicit_dsn,
    sanitize_text,
)
from scripts.ops.coverage_live_proof.errors import (
    EphemeralProvisionError,
    MigrationApplyError,
    ScenarioExpectationError,
    TeardownSafetyError,
)
from scripts.ops.coverage_live_proof.evidence import write_evidence_pack
from scripts.ops.coverage_live_proof.probe import assert_real_postgres, connect_real
from scripts.ops.coverage_live_proof.seed import (
    CANONICAL_ENTITY_KEY,
    apply_seed,
    count_seed_rows,
    load_seed_rows,
    seed_fixture_sha256,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_EPHEMERAL_NAME = re.compile(r"^coverage_live_proof_[0-9a-f]{12}$")
_SAFE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def repository_sha(repo_root: Path | None = None) -> str:
    env_sha = (os.environ.get("GITHUB_SHA") or os.environ.get("CONFENGE_PR_HEAD_SHA") or "").strip()
    if env_sha:
        return env_sha
    root = repo_root or _REPO_ROOT
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S603,S607
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return "unknown"
    if completed.returncode != 0:
        return "unknown"
    return (completed.stdout or "").strip() or "unknown"


def local_run_id() -> str:
    workflow = (os.environ.get("GITHUB_RUN_ID") or "").strip()
    if workflow:
        return workflow
    return f"local-{secrets.token_hex(6)}"


def quote_ident(name: str) -> str:
    if not _SAFE_IDENT.match(name):
        raise TeardownSafetyError(f"refusing unsafe identifier: {name!r}")
    return '"' + name.replace('"', "") + '"'


def is_campaign_database(name: str) -> bool:
    return bool(_EPHEMERAL_NAME.match(name))


def apply_canonical_migrations(dsn: str, *, root: Path | None = None) -> dict[str, list[str]]:
    """Call the shipped apply_range. Does not reimplement migrations."""
    from scripts.ops.apply_migrations import apply_range

    migrations_root = root or (_REPO_ROOT / "db" / "migrations")
    try:
        return apply_range(dsn, migrations_root, mode="upgrade")
    except Exception as exc:
        message = sanitize_text(str(exc), dsn)
        raise MigrationApplyError(f"canonical migration apply failed: {message}") from exc


def load_applied_migration_ids(conn: Any) -> list[str]:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT version FROM public._migrations ORDER BY version"
        )
        return [str(row[0]) for row in (cur.fetchall() or [])]
    except Exception:
        rollback = getattr(conn, "rollback", None)
        if callable(rollback):
            rollback()
        return []
    finally:
        close = getattr(cur, "close", None)
        if callable(close):
            close()


def create_ephemeral_database(admin_dsn: str) -> tuple[str, str]:
    """CREATE DATABASE coverage_live_proof_<hex> on the same cluster."""
    token = secrets.token_hex(6)
    dbname = f"{EPHEMERAL_DB_PREFIX}{token}"
    if not is_campaign_database(dbname):
        raise EphemeralProvisionError(f"generated name rejected: {dbname}")
    admin = connect_real(admin_dsn)
    try:
        admin.autocommit = True
        assert_real_postgres(admin)
        cur = admin.cursor()
        try:
            cur.execute(f"CREATE DATABASE {quote_ident(dbname)}")
        except Exception as exc:
            raise EphemeralProvisionError(
                sanitize_text(f"CREATE DATABASE failed: {exc}", admin_dsn)
            ) from exc
        finally:
            cur.close()
    finally:
        admin.close()
    return replace_database_name(admin_dsn, dbname), dbname


def database_exists(admin_dsn: str, dbname: str) -> bool:
    if not _SAFE_IDENT.match(dbname):
        return False
    conn = connect_real(admin_dsn)
    try:
        cur = conn.cursor()
        try:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
            return cur.fetchone() is not None
        finally:
            cur.close()
    finally:
        conn.close()


def teardown_ephemeral(admin_dsn: str, dbname: str) -> None:
    """DROP only a campaign-created database. Never extra_test / postgres / prod."""
    if not is_campaign_database(dbname):
        raise TeardownSafetyError(
            f"refusing to drop non-campaign database {dbname!r}"
        )
    forbidden = {"extra_test", "postgres", "template0", "template1", "extra_prod"}
    if dbname in forbidden:
        raise TeardownSafetyError(f"refusing to drop reserved name {dbname!r}")
    admin = connect_real(admin_dsn)
    try:
        admin.autocommit = True
        cur = admin.cursor()
        try:
            cur.execute(
                """
                SELECT pg_terminate_backend(pid)
                  FROM pg_stat_activity
                 WHERE datname = %s AND pid <> pg_backend_pid()
                """,
                (dbname,),
            )
            cur.execute(f"DROP DATABASE IF EXISTS {quote_ident(dbname)}")
        finally:
            cur.close()
    finally:
        admin.close()


def _scenario_rows(rows: list[dict[str, Any]], *tags: str) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        if str(meta.get("live_proof_scenario") or "") in tags:
            selected.append(row)
    return selected


def evaluate_identity_scenarios(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Run the shipped dual_coverage_evidence_gate on each scenario slice."""
    from scripts.coverage.covered_entity import compute_coverage_kpis

    slice_a = _scenario_rows(rows, "A")
    slice_b = _scenario_rows(rows, "A", "B")
    slice_c = _scenario_rows(rows, "C")

    gate_a = dual_coverage_evidence_gate(slice_a)
    gate_b = dual_coverage_evidence_gate(slice_b)
    gate_c = dual_coverage_evidence_gate(slice_c)
    kpis_a = compute_coverage_kpis(slice_a, universe_entity_ids=[CANONICAL_ENTITY_KEY])
    kpis_b = compute_coverage_kpis(slice_b, universe_entity_ids=[CANONICAL_ENTITY_KEY])

    scenario_a = {
        "id": "A",
        "name": "source_wide_only",
        "classification": gate_a["classification"],
        "reason": gate_a["reason"],
        "measurement_success": gate_a["measurement_success"],
        "source_wide_count": gate_a["source_wide_count"],
        "identified_count": gate_a["identified_count"],
        "unmapped_count": gate_a["unmapped_count"],
        "entity_scoped_numerator": len(gate_a["numerator_rows"]),
        "entity_denominator": 1,
        "evaluated_entities": [CANONICAL_ENTITY_KEY],
        "entity_status": MISSING_EVIDENCE,
        "covered_count": kpis_a.covered_count,
    }
    scenario_b = {
        "id": "B",
        "name": "source_wide_plus_entity_scoped",
        "classification": gate_b["classification"],
        "reason": gate_b["reason"],
        "measurement_success": gate_b["measurement_success"],
        "source_wide_count": gate_b["source_wide_count"],
        "identified_count": gate_b["identified_count"],
        "unmapped_count": gate_b["unmapped_count"],
        "entity_scoped_numerator": len(gate_b["numerator_rows"]),
        "entity_denominator": 1,
        "evaluated_entities": [CANONICAL_ENTITY_KEY],
        "covered_count": kpis_b.covered_count,
    }
    scenario_c = {
        "id": "C",
        "name": "null_or_incompatible_identity",
        "classification": gate_c["classification"],
        "reason": gate_c["reason"],
        "measurement_success": gate_c["measurement_success"],
        "source_wide_count": gate_c["source_wide_count"],
        "identified_count": gate_c["identified_count"],
        "unmapped_count": gate_c["unmapped_count"],
        "entity_scoped_numerator": len(gate_c["numerator_rows"]),
        "entity_denominator": 1,
        "evaluated_entities": ["ghost-unmappable"],
    }

    expectations = []
    if scenario_a["reason"] != "source_wide_aggregate_without_identity":
        expectations.append("A reason != source_wide_aggregate_without_identity")
    if scenario_a["entity_scoped_numerator"] != 0:
        expectations.append("A entity-scoped numerator increased")
    if scenario_a["classification"] != MISSING_EVIDENCE:
        expectations.append("A classification != MISSING_EVIDENCE")
    if scenario_a["covered_count"] != 0:
        expectations.append("A covered_count != 0")
    if scenario_b["identified_count"] != 1 or scenario_b["entity_scoped_numerator"] != 1:
        expectations.append("B did not count exactly one entity-scoped row")
    if scenario_b["source_wide_count"] != 1:
        expectations.append("B lost the source-wide aggregate")
    if scenario_b["measurement_success"] is not True:
        expectations.append("B measurement_success is not true")
    if scenario_c["reason"] != "unmappable_evidence_cannot_drop":
        expectations.append("C reason != unmappable_evidence_cannot_drop")
    if scenario_c["measurement_success"] is not False:
        expectations.append("C did not fail-close")
    if scenario_c["entity_scoped_numerator"] != 0:
        expectations.append("C entity-scoped numerator is not empty")

    return {
        "A": scenario_a,
        "B": scenario_b,
        "C": scenario_c,
        "source_wide_count": gate_a["source_wide_count"],
        "entity_scoped_count": gate_b["identified_count"],
        "evaluated_entities": [CANONICAL_ENTITY_KEY, "ghost-unmappable"],
        "expectation_errors": expectations,
    }


def execute_golden_path(proof_dsn: str, output_dir: Path, repo_root: Path) -> dict[str, Any]:
    """Invoke the shipped golden-path entry on the ephemeral DSN."""
    ledger = output_dir / "golden_path_ledger.json"
    argv = [
        sys.executable,
        "-m",
        "scripts.golden_path",
        "--dsn",
        proof_dsn,
        "--execute-dual-coverage-only",
        "--capability",
        "both",
        "--ledger-output",
        str(ledger),
    ]
    env = os.environ.copy()
    env["LOCAL_DATALAKE_DSN"] = proof_dsn
    completed = subprocess.run(  # noqa: S603
        argv,
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    ledger_payload: dict[str, Any] | None = None
    if ledger.is_file():
        try:
            loaded = json.loads(ledger.read_text(encoding="utf-8"))
            ledger_payload = loaded if isinstance(loaded, dict) else {"raw": loaded}
        except json.JSONDecodeError:
            ledger_payload = None
    recorded_argv = [
        sys.executable,
        "-m",
        "scripts.golden_path",
        "--dsn",
        "<redacted>",
        "--execute-dual-coverage-only",
        "--capability",
        "both",
        "--ledger-output",
        "golden_path_ledger.json",
    ]
    details: dict[str, Any] = {}
    if ledger_payload:
        steps = ledger_payload.get("steps") or []
        for step in steps:
            if isinstance(step, dict) and step.get("step") in {
                "dual_capability_coverage",
                "coverage",
                "calculate_coverage",
            }:
                details = step.get("details") or {}
                break
        if not details:
            details = {
                "measurement_success": ledger_payload.get("measurement_success"),
                "overall": ledger_payload.get("overall") or ledger_payload.get("status"),
            }
    return {
        "returncode": completed.returncode,
        "argv": recorded_argv,
        "stdout_sanitized": sanitize_text(completed.stdout or "", proof_dsn),
        "stderr_sanitized": sanitize_text(completed.stderr or "", proof_dsn),
        "ledger_present": ledger_payload is not None,
        "measurement_success": bool((details or {}).get("measurement_success")),
        "missing_evidence_reason": (details or {}).get("missing_evidence_reason"),
        "source_wide_evidence_count": (details or {}).get("source_wide_evidence_count"),
        "details": {
            key: details[key]
            for key in (
                "measurement_success",
                "coverage_gate_pass",
                "missing_evidence_reason",
                "source_wide_evidence_count",
                "unmapped_evidence_count",
                "method",
                "dual_gate_status",
            )
            if key in details
        },
    }


def _write_sanitized_log(path: Path, lines: list[str], dsn: str) -> None:
    path.write_text(
        "\n".join(sanitize_text(line, dsn) for line in lines) + "\n",
        encoding="utf-8",
    )


def run_live_proof(
    *,
    dsn: str | None,
    output_dir: Path,
    repo_root: Path | None = None,
    migrations_root: Path | None = None,
    execute_golden: bool = True,
    skip_teardown: bool = False,
    inject_failure: str | None = None,
) -> dict[str, Any]:
    """Run the hermetic proof. Always tears down the ephemeral DB unless skipped."""
    started = time.monotonic()
    root = repo_root or _REPO_ROOT
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_lines: list[str] = []
    errors: list[str] = []
    commands: list[dict[str, Any]] = []
    ephemeral_name: str | None = None
    admin_dsn = require_explicit_dsn(dsn)
    refuse_non_postgres_scheme(admin_dsn)
    refuse_production_dsn(admin_dsn)
    run_id = local_run_id()
    threshold = read_gate_threshold()
    proof_dsn: str | None = None
    pack: dict[str, Any] | None = None

    def log(message: str) -> None:
        log_lines.append(sanitize_text(message, admin_dsn))

    try:
        admin_conn = connect_real(admin_dsn)
        try:
            probe = assert_real_postgres(admin_conn)
        finally:
            admin_conn.close()
        log(f"admin_probe driver={probe['driver']}")

        if inject_failure == "before_create":
            raise RuntimeError("injected failure before_create")

        proof_dsn, ephemeral_name = create_ephemeral_database(admin_dsn)
        log(f"created {ephemeral_name}")
        commands.append(
            {
                "step": "create_ephemeral_database",
                "argv": ["CREATE DATABASE", "<ephemeral>"],
            }
        )

        if inject_failure == "after_create":
            raise RuntimeError("injected failure after_create")

        proof_conn = connect_real(proof_dsn)
        try:
            probe = assert_real_postgres(proof_conn)
        finally:
            proof_conn.close()

        migrate_cmd = [
            sys.executable,
            "-m",
            "scripts.ops.apply_migrations",
            "--dsn",
            "<redacted>",
        ]
        commands.append({"step": "apply_migrations", "argv": migrate_cmd})
        migration_summary = apply_canonical_migrations(proof_dsn, root=migrations_root)
        log(
            "migrations applied={a} skipped={s} repaired={r}".format(
                a=len(migration_summary.get("applied", [])),
                s=len(migration_summary.get("skipped", [])),
                r=len(migration_summary.get("repaired", [])),
            )
        )

        if inject_failure == "after_migrate":
            raise RuntimeError("injected failure after_migrate")

        proof_conn = connect_real(proof_dsn)
        try:
            first_seed = apply_seed(proof_conn)
            rows = load_seed_rows(proof_conn)
            first_count = count_seed_rows(proof_conn)
            scenarios = evaluate_identity_scenarios(rows)
            second_seed = apply_seed(proof_conn)
            second_count = count_seed_rows(proof_conn)
            replay_rows = load_seed_rows(proof_conn)
            replay_scenarios = evaluate_identity_scenarios(replay_rows)
            migration_ids = load_applied_migration_ids(proof_conn)
        finally:
            proof_conn.close()

        if scenarios["expectation_errors"]:
            raise ScenarioExpectationError(
                "; ".join(scenarios["expectation_errors"])
            )
        if first_count != second_count:
            raise ScenarioExpectationError(
                f"replay duplicated rows: first={first_count} second={second_count}"
            )
        if second_seed["inserted"] != 0:
            raise ScenarioExpectationError(
                f"replay inserted {second_seed['inserted']} extra rows"
            )

        golden: dict[str, Any] = {"executed": False}
        if execute_golden:
            golden = execute_golden_path(proof_dsn, output_dir, root)
            golden["executed"] = True
            commands.append({"step": "golden_path", "argv": golden.get("argv", [])})
            log(f"golden_path returncode={golden.get('returncode')}")

        duration_ms = int((time.monotonic() - started) * 1000)
        payload = {
            "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
            "repository_sha": repository_sha(root),
            "run_id": run_id,
            "workflow_run_id": os.environ.get("GITHUB_RUN_ID") or run_id,
            "postgres_version": probe["postgres_version"],
            "connection": {
                "driver": probe["driver"],
                "type": probe["driver"].rsplit(".", 1)[-1],
            },
            "migrations": {
                "applied": list(migration_summary.get("applied") or []),
                "skipped": list(migration_summary.get("skipped") or []),
                "repaired": list(migration_summary.get("repaired") or []),
                "identifiers": migration_ids,
            },
            "seed_fixture_sha256": seed_fixture_sha256(),
            "source_wide_count": scenarios["source_wide_count"],
            "entity_scoped_count": scenarios["entity_scoped_count"],
            "evaluated_entities": scenarios["evaluated_entities"],
            "scenarios": {
                "A": scenarios["A"],
                "B": scenarios["B"],
                "C": scenarios["C"],
                "D": {
                    "id": "D",
                    "name": "replay_idempotent",
                    "row_count_first": first_count,
                    "row_count_second": second_count,
                    "inserted_first": first_seed["inserted"],
                    "inserted_second": second_seed["inserted"],
                    "skipped_second": second_seed["skipped"],
                    "row_counts_stable": first_count == second_count,
                    "scenarios_equal": scenarios["A"] == replay_scenarios["A"]
                    and scenarios["B"] == replay_scenarios["B"]
                    and scenarios["C"] == replay_scenarios["C"],
                },
            },
            "measurement_success": bool(scenarios["B"]["measurement_success"]),
            "threshold": threshold,
            "commands": commands,
            "duration_ms": duration_ms,
            "errors": errors,
            "golden_path": {
                "executed": golden.get("executed"),
                "returncode": golden.get("returncode"),
                "measurement_success": golden.get("measurement_success"),
                "missing_evidence_reason": golden.get("missing_evidence_reason"),
                "source_wide_evidence_count": golden.get("source_wide_evidence_count"),
                "details": golden.get("details") or {},
            },
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ephemeral_database": ephemeral_name,
        }
        pack = write_evidence_pack(output_dir, payload)
        log(f"normalized_semantic_hash={pack['normalized_semantic_hash']}")
        _write_sanitized_log(output_dir / "coverage-live-proof.log", log_lines, admin_dsn)
        if inject_failure == "after_pack":
            raise RuntimeError("injected failure after_pack")
        return pack
    except Exception as exc:
        errors.append(sanitize_text(f"{type(exc).__name__}: {exc}", admin_dsn))
        log(f"ERROR {type(exc).__name__}: {exc}")
        _write_sanitized_log(output_dir / "coverage-live-proof.log", log_lines, admin_dsn)
        raise
    finally:
        if ephemeral_name and not skip_teardown:
            try:
                teardown_ephemeral(admin_dsn, ephemeral_name)
                log(f"dropped {ephemeral_name}")
            except Exception as teardown_exc:
                # Teardown errors must not hide the original failure.
                _write_sanitized_log(
                    output_dir / "coverage-live-proof.log",
                    [*log_lines, f"teardown_error: {teardown_exc}"],
                    admin_dsn,
                )
                if pack is not None:
                    raise
                # If the run already failed, keep the original exception.
                if not errors:
                    raise


def resolve_cli_dsn(cli_dsn: str | None) -> str | None:
    """CLI DSN wins; otherwise LOCAL_DATALAKE_DSN. Never invent a default."""
    if cli_dsn and cli_dsn.strip():
        return cli_dsn.strip()
    env = os.environ.get("LOCAL_DATALAKE_DSN")
    return env.strip() if env and env.strip() else None
