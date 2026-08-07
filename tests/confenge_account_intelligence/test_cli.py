"""CLI entry path: single CNPJ and batch JSONL (offline)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MODULE = "scripts.confenge_account_intelligence"


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", MODULE, *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_catalog(repo_root: Path | None = None) -> None:
    # repo root = parents of tests/... → worktree root
    root = Path(__file__).resolve().parents[2]
    proc = _run(["catalog"], root)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["catalog_version"]
    assert len(payload["service_ids"]) >= 10
    assert "diagnostico_contratual_b2g" in payload["service_ids"]


def test_cli_single_cnpj(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    out = tmp_path / "single.jsonl"
    proc = _run(
        [
            "run",
            "--input",
            str(FIXTURES / "mature_no_reajuste.json"),
            "--cnpj",
            "77888999000126",
            "--output",
            str(out),
        ],
        root,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["schema_id"] == "confenge-account-intelligence-v1"
    assert row["primary_service"]["service_id"] == "estruturacao_pleito_reajuste"
    assert row["cnpj_root"] == "77888999"
    for key in (
        "account_snapshot",
        "confirmed_facts",
        "strong_inferences",
        "weak_inferences",
        "internal_structure_hypothesis",
        "fact_to_mention",
        "question_to_ask",
        "cta",
        "claims_to_avoid",
        "evidence",
    ):
        assert key in row


def test_cli_batch_jsonl(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    out = tmp_path / "batch.jsonl"
    proc = _run(
        [
            "run",
            "--input",
            str(FIXTURES / "batch.jsonl"),
            "--output",
            str(out),
            "--max-workers",
            "2",
        ],
        root,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 3
    assert all(r["schema_id"] == "confenge-account-intelligence-v1" for r in rows)
    services = [r["primary_service"]["service_id"] for r in rows]
    assert services[0] == "reforco_temporario_backoffice"
    assert services[1] == "auditoria_orcamento_bdi"
    assert services[2] == "diagnostico_contratual_b2g"
