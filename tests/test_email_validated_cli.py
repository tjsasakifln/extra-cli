"""CLI entry points: import, evaluate, policy-diff, regression."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

from scripts.decision_unit_intelligence.email_validated.cli import main
from scripts.decision_unit_intelligence.email_validated.schema import REQUIRED_RECORD_FIELDS, load_jsonl

GOLD = "evals/email_validated/gold/gold-set.v1.jsonl"
IMPORT_SAMPLE = "evals/email_validated/fixtures/import-sample.json"
STOP = "evals/email_validated/fixtures/stop-the-line-wrong-person.jsonl"
POLICY_V0 = "evals/email_validated/policy/email-validated-promotion.v0.json"
POLICY_V1 = "evals/email_validated/policy/email-validated-promotion.v1.json"


def test_import_round_trips_required_fields(tmp_path: Path):
    out = tmp_path / "imported.jsonl"
    code = main(["import", "--in", IMPORT_SAMPLE, "--out", str(out)])
    assert code == 0
    records = load_jsonl(out)
    assert len(records) == 1
    payload = records[0].to_dict()
    for field in REQUIRED_RECORD_FIELDS:
        assert field in payload
    assert payload["account_id"] == "00820854000114"
    assert payload["email"] == "contato@qualidademineracao.com.br"
    assert payload["human_verdict"] == "GENERIC_ROLE"
    adj = tmp_path / "adjudicated.jsonl"
    assert main(["adjudicate", "--in", IMPORT_SAMPLE, "--out", str(adj)]) == 0
    assert load_jsonl(adj)[0].case_id == records[0].case_id


def test_evaluate_cli_writes_identical_reports(tmp_path: Path):
    out1 = tmp_path / "eval1.json"
    out2 = tmp_path / "eval2.json"
    assert main(["evaluate", "--gold", GOLD, "--out", str(out1)]) == 0
    assert main(["evaluate", "--gold", GOLD, "--out", str(out2)]) == 0
    first = json.loads(out1.read_text(encoding="utf-8"))
    second = json.loads(out2.read_text(encoding="utf-8"))
    assert first == second
    assert first["precision_denominator"] == "no predicted positives"
    assert first["policy_version"]
    assert first["gold_set_version"]


def test_policy_diff_reports_version_and_content_change():
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(["policy-diff", "--left", POLICY_V0, "--right", POLICY_V1])
    assert code == 0
    diff = json.loads(buf.getvalue())
    assert diff["noop"] is False
    assert diff["version_changed"] is True
    assert diff["content_changed"] is True
    assert diff["left_version"] != diff["right_version"]


def test_regression_clean_gold_passes_and_planted_fixture_fails():
    assert main(["regression", "--gold", GOLD]) == 0
    assert main(["regression", "--gold", STOP]) == 2
