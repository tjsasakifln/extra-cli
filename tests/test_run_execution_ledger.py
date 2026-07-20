"""Tests for run execution ledger — cycle-1 material DoD advance."""
from __future__ import annotations

from pathlib import Path

from scripts.ops.run_execution_ledger import (
    load_ledger,
    record_execution,
    record_manual_mutation,
    reports_for_run,
    runs_with_errors,
    verify_invariants,
)


def test_record_always_has_errors_list(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rec = record_execution(
        command=["python3", "-m", "pytest", "tests/x"],
        status="failed",
        errors=["AssertionError: boom"],
        exit_code=1,
        report_paths=["output/reports/x.json"],
        root=tmp_path,
    )
    assert rec["run_id"]
    assert rec["errors"] == ["AssertionError: boom"]
    assert rec["report_run_links"][0]["run_id"] == rec["run_id"]
    assert reports_for_run(rec["run_id"], root=tmp_path) == ["output/reports/x.json"]


def test_ok_run_has_empty_errors(tmp_path: Path):
    rec = record_execution(
        command="make extra-decision-pack",
        status="ok",
        exit_code=0,
        report_paths=["out/brief.md"],
        root=tmp_path,
    )
    assert rec["errors"] == []
    inv = verify_invariants(tmp_path)
    assert inv["ok"] is True
    assert inv["n_runs"] == 1


def test_runs_with_errors_filter(tmp_path: Path):
    record_execution(command="a", status="ok", errors=[], root=tmp_path)
    record_execution(command="b", status="failed", errors=["e1"], root=tmp_path)
    bad = runs_with_errors(tmp_path)
    assert len(bad) == 1
    assert bad[0]["errors"] == ["e1"]


def test_manual_mutation_auditable(tmp_path: Path):
    m = record_manual_mutation(
        actor="tiago",
        path="DOD.md",
        reason="PARTIAL annotation",
        root=tmp_path,
    )
    assert m["kind"] == "manual_mutation"
    path = tmp_path / "output" / "run-execution-ledger" / "manual-mutations.jsonl"
    assert path.is_file()
    assert "PARTIAL" in path.read_text(encoding="utf-8")


def test_load_ledger_multiple(tmp_path: Path):
    record_execution(command="1", status="ok", root=tmp_path)
    record_execution(command="2", status="ok", root=tmp_path)
    assert len(load_ledger(tmp_path)) == 2
