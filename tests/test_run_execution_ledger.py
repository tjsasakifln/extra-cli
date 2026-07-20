"""Tests for run execution ledger — cycle-1 material DoD advance."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ops.run_execution_ledger import (
    load_ledger,
    main,
    record_execution,
    record_manual_mutation,
    record_manual_override,
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
    assert "errors" in rec
    assert rec["errors"] == ["AssertionError: boom"]
    assert rec["report_run_links"][0]["run_id"] == rec["run_id"]
    assert rec["report_run_links"][0]["report"] == "output/reports/x.json"
    assert reports_for_run(rec["run_id"], root=tmp_path) == ["output/reports/x.json"]


def test_ok_run_has_empty_errors(tmp_path: Path):
    rec = record_execution(
        command="make extra-decision-pack",
        status="ok",
        exit_code=0,
        report_paths=["out/brief.md"],
        root=tmp_path,
    )
    assert "errors" in rec
    assert rec["errors"] == []
    inv = verify_invariants(tmp_path)
    assert inv["ok"] is True
    assert inv["n_runs"] == 1


def test_errors_key_present_when_none_passed(tmp_path: Path):
    """DoD §29: every execution has errors key even if caller omits errors=."""
    rec = record_execution(command="noop", status="ok", errors=None, root=tmp_path)
    assert "errors" in rec
    assert isinstance(rec["errors"], list)
    assert rec["errors"] == []
    # Durable on disk
    rows = load_ledger(tmp_path)
    assert "errors" in rows[0]
    assert isinstance(rows[0]["errors"], list)


def test_report_paths_always_link_run_id(tmp_path: Path):
    rec = record_execution(
        command="pack",
        status="ok",
        report_paths=["a/report.json", "b/brief.md"],
        run_id="run-fixed-1",
        root=tmp_path,
    )
    assert rec["run_id"] == "run-fixed-1"
    assert len(rec["report_run_links"]) == 2
    for link in rec["report_run_links"]:
        assert link["run_id"] == "run-fixed-1"
        assert link["report"] in rec["report_paths"]
    inv = verify_invariants(tmp_path)
    assert inv["unlinked_reports"] == []
    assert inv["ok"] is True


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
    assert m["actor"] == "tiago"
    assert m["reason"] == "PARTIAL annotation"
    path = tmp_path / "output" / "run-execution-ledger" / "manual-mutations.jsonl"
    assert path.is_file()
    assert "PARTIAL" in path.read_text(encoding="utf-8")


def test_manual_mutation_requires_actor_and_reason(tmp_path: Path):
    with pytest.raises(ValueError, match="actor"):
        record_manual_mutation(actor=" ", path="DOD.md", reason="x", root=tmp_path)
    with pytest.raises(ValueError, match="reason"):
        record_manual_mutation(actor="tiago", path="DOD.md", reason="", root=tmp_path)


def test_record_manual_override_requires_motivo_data_autor(tmp_path: Path):
    row = record_manual_override(
        target="entity:1",
        action="force_status",
        motivo="fonte offline; consulta manual",
        autor="tiago",
        run_id="run-ov-1",
        root=tmp_path,
    )
    assert row["motivo"]
    assert row["autor"] == "tiago"
    assert row["data"]
    assert row["kind"] == "manual_override"
    inv = verify_invariants(tmp_path)
    assert inv["override_issues"] == []
    assert inv["ok"] is True


def test_record_manual_override_missing_autor_fails(tmp_path: Path):
    with pytest.raises(ValueError, match="autor"):
        record_manual_override(
            target="entity:1",
            action="force",
            motivo="ok reason",
            autor=" ",
            root=tmp_path,
        )


def test_record_manual_override_missing_motivo_fails(tmp_path: Path):
    with pytest.raises(ValueError, match="motivo"):
        record_manual_override(
            target="entity:1",
            action="force",
            motivo="",
            autor="tiago",
            root=tmp_path,
        )


def test_load_ledger_multiple(tmp_path: Path):
    record_execution(command="1", status="ok", root=tmp_path)
    record_execution(command="2", status="ok", root=tmp_path)
    assert len(load_ledger(tmp_path)) == 2


def test_cli_record_and_verify(tmp_path: Path, capsys):
    rc = main(
        [
            "--root",
            str(tmp_path),
            "record",
            "--command",
            "pytest-demo",
            "--status",
            "ok",
            "--report",
            "docs/ops/demo-report.json",
            "--run-id",
            "run-cli-demo",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    rec = json.loads(out)
    assert rec["errors"] == []
    assert rec["report_run_links"][0]["run_id"] == "run-cli-demo"

    rc2 = main(["--root", str(tmp_path), "verify"])
    assert rc2 == 0
    inv = json.loads(capsys.readouterr().out)
    assert inv["ok"] is True
    assert inv["n_runs"] == 1


def test_cli_override_missing_autor_rejected(tmp_path: Path, capsys):
    # argparse requires --autor; empty string should fail closed in library
    rc = main(
        [
            "--root",
            str(tmp_path),
            "override",
            "--target",
            "e:1",
            "--action",
            "force",
            "--motivo",
            "reason ok",
            "--autor",
            "   ",
        ]
    )
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "autor" in payload["error"]
