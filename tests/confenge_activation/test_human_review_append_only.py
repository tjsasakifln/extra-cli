"""Human decisions are append-only authority; generated sample stays immutable."""

from __future__ import annotations

import json

from scripts.confenge.human_review.cli import run_interactive


def test_review_appends_attributed_decision_and_never_rewrites_sample(
    tmp_path, monkeypatch
) -> None:  # noqa: ANN001
    sample = tmp_path / "HUMAN-REVIEW-SAMPLE.json"
    decisions = tmp_path / "HUMAN-REVIEW-DECISIONS.jsonl"
    payload = {
        "leads": [
            {
                "cnpj_raiz": "12345678",
                "email": "Comercial@Empresa.example",
                "razao_social": "EMPRESA LTDA",
                "review_status": "HUMAN_REVIEW_PENDING",
            }
        ]
    }
    original = json.dumps(payload, indent=2) + "\n"
    sample.write_text(original, encoding="utf-8")
    monkeypatch.setattr("builtins.input", lambda _prompt="": "A")

    assert (
        run_interactive(
            sample_path=sample,
            decisions_path=decisions,
            reviewer="tiago",
        )
        == 0
    )
    assert sample.read_text(encoding="utf-8") == original
    row = json.loads(decisions.read_text(encoding="utf-8").strip())
    assert row["lead_key"] == "12345678|comercial@empresa.example"
    assert row["cnpj_root"] == "12345678"
    assert row["review_status"] == "HUMAN_REVIEW_APPROVED"
    assert row["reviewer"] == "tiago"
    assert row["reviewed_at"]
    assert row["evidence_inspected"]

    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt="": (_ for _ in ()).throw(AssertionError("must not prompt reviewed lead")),
    )
    assert (
        run_interactive(
            sample_path=sample,
            decisions_path=decisions,
            reviewer="tiago",
        )
        == 0
    )
