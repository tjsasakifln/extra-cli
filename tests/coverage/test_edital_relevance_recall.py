"""Unit tests for fail-closed edital relevance recall foundation (DOD §8.4)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from scripts.coverage.edital_relevance_recall import (
    BLOCKED_HUMAN_DUAL_LABELING,
    DIAGNOSTIC_ONLY,
    RECALL_THRESHOLD,
    check_corpus_integrity,
    evaluate,
    main,
    predicted_relevant,
    score_records,
    sha256_file,
    wilson_ci,
)

ENG_OBJ = "Execução de pavimentação asfáltica em vias urbanas do município"
NON_OBJ = "Aquisição de medicamentos para a farmácia municipal"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def _base_rec(oid: str, label: str, objeto: str, **extra) -> dict:
    rec = {
        "official_id": oid,
        "source": "pncp",
        "url": f"https://pncp.gov.br/app/editais/test/{oid}",
        "objeto": objeto,
        "titulo": "",
        "municipio": "FLORIANOPOLIS",
        "municipio_bucket": "grande",
        "natureza_juridica": "admin_direta",
        "observed_at": "2026-07-20T00:00:00Z",
        "content_hash": "abc",
        "label_reviewer_a": label,
        "label_reviewer_b": label,
        "label_final": label,
        "adjudication_reason": f"agreement:{label}",
        "labels_agreed": True,
        "selection_provenance": "public_inventory_pncp_api",
        "selection_method": "public_inventory_stratified_content_sample",
        "selected_by_classifier": False,
        "selected_by_db_presence": False,
        "selected_by_success_zero": False,
        "synthetic": False,
        "label_authority": "machine_criteria_draft",
        "human_reviewer_a_id": "",
        "human_reviewer_b_id": "",
    }
    rec.update(extra)
    return rec


def test_wilson_ci_bounds():
    low, high = wilson_ci(95, 100)
    assert 0.0 <= low <= 0.95 <= high <= 1.0


def test_confusion_math_via_score_records():
    rows = [
        _base_rec("E1", "RELEVANT", ENG_OBJ),
        _base_rec("E2", "RELEVANT", ENG_OBJ),
        _base_rec("E3", "RELEVANT", NON_OBJ),
        _base_rec("I1", "IRRELEVANT", NON_OBJ),
        _base_rec("I2", "IRRELEVANT", ENG_OBJ),
        _base_rec("U1", "UNDECIDABLE", "objeto ambíguo genérico xyz"),
    ]
    m = score_records(rows)
    conf = m["confusion"]
    assert conf["tp"] + conf["fn"] == m["relevant_denominator"] == 3
    assert m["undecidable_excluded"] == 1
    if conf["tp"] + conf["fn"]:
        assert math.isclose(conf["recall"], conf["tp"] / (conf["tp"] + conf["fn"]), rel_tol=1e-9)


def test_db_presence_does_not_influence_score():
    rows = [
        _base_rec("E1", "RELEVANT", ENG_OBJ, in_database=True, success_zero=True),
        _base_rec("E2", "RELEVANT", ENG_OBJ, in_database=False, success_zero=False),
    ]
    m1 = score_records(rows)
    m2 = score_records(
        [
            _base_rec("E1", "RELEVANT", ENG_OBJ),
            _base_rec("E2", "RELEVANT", ENG_OBJ),
        ]
    )
    assert m1["relevance_recall"] == m2["relevance_recall"]
    assert m1["confusion"] == m2["confusion"]


def test_missing_label_fails_integrity():
    rows = [_base_rec("E1", "RELEVANT", ENG_OBJ)]
    rows[0].pop("label_final")
    rep = check_corpus_integrity(rows, mode="diagnostic")
    assert not rep.ok
    assert any("missing label_final" in e for e in rep.errors)


def test_duplicate_fails_integrity():
    rows = [_base_rec("E1", "RELEVANT", ENG_OBJ), _base_rec("E1", "RELEVANT", ENG_OBJ)]
    rep = check_corpus_integrity(rows, mode="diagnostic")
    assert not rep.ok
    assert any("duplicate" in e for e in rep.errors)


def test_empty_corpus_diagnostic_fails(tmp_path):
    p = tmp_path / "empty.jsonl"
    p.write_text("", encoding="utf-8")
    code, result = evaluate(p, mode="diagnostic")
    assert code != 0
    assert result["pass"] is False
    assert result["status"] == DIAGNOSTIC_ONLY
    assert result["acceptance_eligible"] is False
    assert result["dod_item_accepted"] is False


def test_diagnostic_never_accepts_machine_draft(tmp_path):
    rows = [
        _base_rec("E1", "RELEVANT", ENG_OBJ),
        _base_rec("E2", "RELEVANT", ENG_OBJ),
        _base_rec("I1", "IRRELEVANT", NON_OBJ),
    ]
    p = tmp_path / "draft.jsonl"
    _write_jsonl(p, rows)
    man = {
        "role": "diagnostic_machine_draft",
        "label_authority": "machine_criteria_draft",
        "acceptance_eligible": False,
        "dod_item_accepted": False,
        "sealed_holdout": False,
        "corpus_sha256": sha256_file(p),
        "frozen_at": "2026-07-26T00:00:00Z",
    }
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(man), encoding="utf-8")
    code, result = evaluate(p, manifest_path=mp, mode="diagnostic")
    assert result["status"] == DIAGNOSTIC_ONLY
    assert result["pass"] is False
    assert result["acceptance_eligible"] is False
    assert result["dod_item_accepted"] is False
    assert result["sealed_holdout"] is False
    assert "ACCEPTED" not in str(result["status"])
    assert code == 0  # diagnostic run succeeds as infrastructure
    assert "diagnostic" in result["relevance_recall_note"].lower()


def test_final_gate_rejects_machine_labels(tmp_path):
    rows = []
    sources = ["pncp", "sc_compras", "ciga"]
    buckets = ["grande", "medio", "pequeno"]
    naturezas = ["admin_direta", "admin_indireta"]
    for i in range(100):
        rows.append(
            _base_rec(
                f"R{i}",
                "RELEVANT",
                ENG_OBJ,
                source=sources[i % 3],
                municipio_bucket=buckets[i % 3],
                natureza_juridica=naturezas[i % 2],
                label_authority="machine_criteria_draft",
            )
        )
    for i in range(20):
        rows.append(
            _base_rec(
                f"I{i}",
                "IRRELEVANT",
                NON_OBJ,
                source=sources[i % 3],
                municipio_bucket=buckets[i % 3],
                natureza_juridica=naturezas[i % 2],
                label_authority="machine_criteria_draft",
            )
        )
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    man = {
        "role": "diagnostic_machine_draft",
        "frozen_at": "2026-07-26T00:00:00Z",
        "sealed_holdout": False,
        "sealed_before_classifier_edits": False,
        "corpus_sha256": sha256_file(p),
        "stratum_blockers": {},
        "label_authority": "machine_criteria_draft",
        "acceptance_eligible": False,
        "dod_item_accepted": False,
    }
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(man), encoding="utf-8")
    code, result = evaluate(p, manifest_path=mp, mode="final")
    assert code != 0
    assert result["pass"] is False
    assert result["blocker"] == BLOCKED_HUMAN_DUAL_LABELING
    assert result["dod_item_accepted"] is False
    errs = " ".join(result["integrity"]["errors"]).lower()
    assert "human" in errs or "machine" in errs or "role" in errs


def test_final_gate_rejects_legacy_locked_holdout_role(tmp_path):
    rows = [
        _base_rec(
            f"R{i}",
            "RELEVANT",
            ENG_OBJ,
            source=["pncp", "sc_compras", "ciga"][i % 3],
            municipio_bucket=["grande", "medio", "pequeno"][i % 3],
            natureza_juridica=["admin_direta", "admin_indireta"][i % 2],
            label_authority="human_dual_independent",
            human_reviewer_a_id="tiago",
            human_reviewer_b_id="reviewer2",
        )
        for i in range(100)
    ]
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    man = {
        "role": "locked_holdout",  # contaminated legacy role — must reject
        "frozen_at": "2026-07-26T00:00:00Z",
        "sealed_holdout": True,
        "sealed_before_classifier_edits": True,
        "corpus_sha256": sha256_file(p),
        "stratum_blockers": {},
        "label_authority": "human_dual_independent",
        "pilot_human_approved_at": "2026-07-26T00:00:00Z",
    }
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(man), encoding="utf-8")
    code, result = evaluate(p, manifest_path=mp, mode="final")
    assert code != 0
    assert result["blocker"] == BLOCKED_HUMAN_DUAL_LABELING
    assert any("human_sealed_holdout" in e or "locked_holdout" in e for e in result["integrity"]["errors"])


def test_final_gate_rejects_missing_seal(tmp_path):
    rows = [
        _base_rec(
            f"R{i}",
            "RELEVANT",
            ENG_OBJ,
            source=["pncp", "sc_compras", "ciga"][i % 3],
            municipio_bucket=["grande", "medio", "pequeno"][i % 3],
            natureza_juridica=["admin_direta", "admin_indireta"][i % 2],
            label_authority="human_dual_independent",
            human_reviewer_a_id="reviewer_alpha",
            human_reviewer_b_id="reviewer_beta",
        )
        for i in range(100)
    ]
    for i in range(20):
        rows.append(
            _base_rec(
                f"I{i}",
                "IRRELEVANT",
                NON_OBJ,
                source=["pncp", "sc_compras", "ciga"][i % 3],
                municipio_bucket=["grande", "medio", "pequeno"][i % 3],
                natureza_juridica=["admin_direta", "admin_indireta"][i % 2],
                label_authority="human_dual_independent",
                human_reviewer_a_id="reviewer_alpha",
                human_reviewer_b_id="reviewer_beta",
            )
        )
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    man = {
        "role": "human_sealed_holdout",
        "frozen_at": "2026-07-26T00:00:00Z",
        "sealed_holdout": False,
        "sealed_before_classifier_edits": False,
        "corpus_sha256": sha256_file(p),
        "stratum_blockers": {},
        "label_authority": "human_dual_independent",
        "pilot_human_approved_at": "2026-07-26T00:00:00Z",
    }
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(man), encoding="utf-8")
    code, result = evaluate(p, manifest_path=mp, mode="final")
    assert code != 0
    assert any("sealed" in e for e in result["integrity"]["errors"])


def test_denominator_only_adjudicated_relevant():
    rows = [
        _base_rec("E1", "RELEVANT", ENG_OBJ),
        _base_rec("U1", "UNDECIDABLE", "talvez obra talvez não"),
        _base_rec("I1", "IRRELEVANT", NON_OBJ),
    ]
    m = score_records(rows)
    assert m["relevant_denominator"] == 1
    assert m["undecidable_excluded"] == 1


def test_predicted_relevant_mapping():
    assert predicted_relevant("ENGINEERING_HIGH_CONFIDENCE")
    assert predicted_relevant("ENGINEERING_REVIEW")
    assert not predicted_relevant("NON_ENGINEERING")
    assert not predicted_relevant("AMBIGUOUS")


def test_recall_threshold_gate_math():
    assert 0.95 + 1e-15 >= RECALL_THRESHOLD
    assert not (0.9499 + 1e-15 >= RECALL_THRESHOLD)
    assert (95 / 100) >= RECALL_THRESHOLD
    assert (94.99 / 100) < RECALL_THRESHOLD


def test_cli_evaluate_final_on_machine_draft_blocks(tmp_path):
    """Drive real CLI entrypoint: final mode on machine draft must non-zero + blocker."""
    root = Path(__file__).resolve().parents[2]
    corpus = root / "evals" / "edital_relevance" / "machine_draft_candidate_pool.jsonl"
    manifest = root / "evals" / "edital_relevance" / "machine_draft_candidate_pool-manifest.json"
    if not corpus.is_file():
        pytest.skip("machine draft corpus not present")
    out = tmp_path / "final.json"
    code = main(
        [
            "evaluate-final",
            "--corpus",
            str(corpus),
            "--manifest",
            str(manifest),
            "--output",
            str(out),
        ]
    )
    assert code != 0
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["pass"] is False
    assert result["blocker"] == BLOCKED_HUMAN_DUAL_LABELING
    assert result["dod_item_accepted"] is False
    assert result["acceptance_eligible"] is False


def test_cli_diagnose_on_machine_draft_is_diagnostic_only(tmp_path):
    root = Path(__file__).resolve().parents[2]
    corpus = root / "evals" / "edital_relevance" / "machine_draft_candidate_pool.jsonl"
    manifest = root / "evals" / "edital_relevance" / "machine_draft_candidate_pool-manifest.json"
    if not corpus.is_file():
        pytest.skip("machine draft corpus not present")
    out = tmp_path / "diag.json"
    code = main(
        [
            "diagnose",
            "--corpus",
            str(corpus),
            "--manifest",
            str(manifest),
            "--output",
            str(out),
        ]
    )
    assert code == 0
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["status"] == DIAGNOSTIC_ONLY
    assert result["pass"] is False
    assert result["acceptance_eligible"] is False
    assert result["dod_item_accepted"] is False
    assert result["sealed_holdout"] is False
    # no accept theater
    blob = json.dumps(result)
    assert '"ACCEPTED"' not in blob
    assert result.get("pass") is False


def test_no_allow_machine_labels_flag_in_parser():
    """Regression: no flag may promote machine labels to accept."""
    from scripts.coverage.edital_relevance_recall import build_parser

    help_text = build_parser().format_help()
    assert "allow-machine-labels" not in help_text
    assert "allow_machine" not in help_text
