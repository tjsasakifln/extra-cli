"""Unit tests for fail-closed edital relevance recall evaluator (DOD §8.4)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from scripts.coverage.edital_relevance_recall import (
    RECALL_THRESHOLD,
    check_corpus_integrity,
    evaluate,
    predicted_relevant,
    score_records,
    sha256_file,
    wilson_ci,
)
from scripts.ops.sector_classifier import RULE_VERSION, classify_object

FIXTURES = Path(__file__).parent / "fixtures" / "edital_relevance"


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


ENG_OBJ = "Execução de pavimentação asfáltica em vias urbanas do município"
NON_OBJ = "Aquisição de medicamentos para a farmácia municipal"


def test_wilson_ci_bounds():
    low, high = wilson_ci(95, 100)
    assert 0.0 <= low <= 0.95 <= high <= 1.0


def test_confusion_math_via_score_records(tmp_path, monkeypatch):
    """Precision/recall/matrix computed correctly; denominator = RELEVANT only."""
    rows = [
        _base_rec("E1", "RELEVANT", ENG_OBJ),
        _base_rec("E2", "RELEVANT", ENG_OBJ),
        _base_rec("E3", "RELEVANT", NON_OBJ),  # FN likely
        _base_rec("I1", "IRRELEVANT", NON_OBJ),
        _base_rec("I2", "IRRELEVANT", ENG_OBJ),  # FP likely
        _base_rec("U1", "UNDECIDABLE", "objeto ambíguo genérico xyz"),
    ]
    # Use real classifier
    m = score_records(rows)
    conf = m["confusion"]
    assert conf["tp"] + conf["fn"] == m["relevant_denominator"] == 3
    assert m["undecidable_excluded"] == 1
    # recall = tp/(tp+fn)
    if conf["tp"] + conf["fn"]:
        assert math.isclose(conf["recall"], conf["tp"] / (conf["tp"] + conf["fn"]), rel_tol=1e-9)
    if conf["tp"] + conf["fp"]:
        assert math.isclose(conf["precision"], conf["tp"] / (conf["tp"] + conf["fp"]), rel_tol=1e-9)


def test_db_presence_and_success_zero_do_not_influence(tmp_path):
    rows = [
        _base_rec(
            "E1",
            "RELEVANT",
            ENG_OBJ,
            in_database=True,
            success_zero=True,
            db_presence=True,
        ),
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


def test_missing_label_fails(tmp_path):
    rows = [_base_rec("E1", "RELEVANT", ENG_OBJ)]
    rows[0].pop("label_final")
    rep = check_corpus_integrity(rows)
    assert not rep.ok
    assert any("missing label_final" in e for e in rep.errors)


def test_duplicate_fails(tmp_path):
    rows = [
        _base_rec("E1", "RELEVANT", ENG_OBJ),
        _base_rec("E1", "RELEVANT", ENG_OBJ),
    ]
    rep = check_corpus_integrity(rows)
    assert not rep.ok
    assert any("duplicate" in e for e in rep.errors)


def test_empty_corpus_fails(tmp_path):
    p = tmp_path / "empty.jsonl"
    p.write_text("", encoding="utf-8")
    code, result = evaluate(
        p,
        require_holdout_floor=False,
        allow_synthetic=True,
    )
    assert code != 0
    assert result["pass"] is False


def test_only_irrelevant_fails(tmp_path):
    rows = [_base_rec(f"I{i}", "IRRELEVANT", NON_OBJ) for i in range(5)]
    p = tmp_path / "irr.jsonl"
    _write_jsonl(p, rows)
    code, result = evaluate(p, require_holdout_floor=False, allow_synthetic=True)
    assert code != 0
    assert result["pass"] is False
    assert result["relevant_denominator"] == 0


def test_hash_mismatch_fails(tmp_path):
    rows = [_base_rec("E1", "RELEVANT", ENG_OBJ)]
    p = tmp_path / "c.jsonl"
    _write_jsonl(p, rows)
    man = {
        "role": "locked_holdout",
        "frozen_at": "2026-07-26T00:00:00Z",
        "sealed_before_classifier_edits": True,
        "corpus_sha256": "0" * 64,
    }
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(man), encoding="utf-8")
    code, result = evaluate(
        p,
        manifest_path=mp,
        require_holdout_floor=False,
        allow_synthetic=True,
    )
    assert code != 0
    assert any("sha256" in e for e in result["integrity"]["errors"])


def test_development_leakage_fails(tmp_path):
    hold = [_base_rec("SHARED1", "RELEVANT", ENG_OBJ)]
    dev = [_base_rec("SHARED1", "RELEVANT", ENG_OBJ)]
    hp = tmp_path / "hold.jsonl"
    dp = tmp_path / "dev.jsonl"
    _write_jsonl(hp, hold)
    _write_jsonl(dp, dev)
    code, result = evaluate(
        hp,
        development_path=dp,
        require_holdout_floor=False,
        allow_synthetic=True,
    )
    assert code != 0
    assert any("leakage" in e for e in result["integrity"]["errors"])


def test_synthetic_cannot_final_pass(tmp_path):
    rows = [
        _base_rec("S1", "RELEVANT", ENG_OBJ, synthetic=True),
        _base_rec("S2", "RELEVANT", ENG_OBJ, synthetic=True),
    ]
    p = tmp_path / "syn.jsonl"
    _write_jsonl(p, rows)
    code, result = evaluate(p, require_holdout_floor=False, allow_synthetic=False)
    assert code != 0
    assert any("synthetic" in e for e in result["integrity"]["errors"])


def test_stratum_floor_fails_without_blocker(tmp_path):
    # few records, require holdout floor
    rows = [_base_rec(f"E{i}", "RELEVANT", ENG_OBJ) for i in range(5)]
    p = tmp_path / "thin.jsonl"
    _write_jsonl(p, rows)
    man = {
        "role": "locked_holdout",
        "frozen_at": "2026-07-26T00:00:00Z",
        "sealed_before_classifier_edits": True,
        "corpus_sha256": sha256_file(p),
        "stratum_blockers": {},
    }
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(man), encoding="utf-8")
    code, result = evaluate(
        p, manifest_path=mp, require_holdout_floor=True, allow_machine_labels=True, allow_synthetic=True
    )
    assert code != 0


def test_partial_error_not_pass(tmp_path):
    """Integrity error even with high recall → fail."""
    rows = [_base_rec("E1", "RELEVANT", ENG_OBJ)]
    rows[0]["url"] = ""  # missing url
    p = tmp_path / "partial.jsonl"
    _write_jsonl(p, rows)
    code, result = evaluate(p, require_holdout_floor=False, allow_synthetic=True)
    assert code != 0
    assert result["pass"] is False


def test_output_records_sha_rule_profile(tmp_path):
    rows = [_base_rec("E1", "RELEVANT", ENG_OBJ), _base_rec("E2", "RELEVANT", ENG_OBJ)]
    p = tmp_path / "ok.jsonl"
    out = tmp_path / "result.json"
    _write_jsonl(p, rows)
    code, result = evaluate(
        p,
        require_holdout_floor=False,
        allow_synthetic=True,
        output_path=out,
    )
    # may pass or fail on recall depending on classifier; versions must be present
    assert "versions" in result
    assert result["versions"]["rule_version"] == RULE_VERSION
    assert result["versions"]["profile_hash"]
    assert result["versions"]["git_sha"]
    assert out.is_file()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["versions"]["rule_version"] == RULE_VERSION


def test_recall_exactly_95_passes_gate_logic():
    """Unit gate: 95/100 => pass threshold; 94.99 fails.

    We test the threshold comparison directly (metric path) without faking
    classifier — pure arithmetic gate used by evaluate().
    """
    assert 0.95 + 1e-15 >= RECALL_THRESHOLD
    assert not (0.9499 + 1e-15 >= RECALL_THRESHOLD)
    # 95/100
    assert (95 / 100) >= RECALL_THRESHOLD
    # 94.99% as float
    assert (94.99 / 100) < RECALL_THRESHOLD


def test_recall_95_percent_with_stubbed_predictions(tmp_path, monkeypatch):
    """End-to-end evaluate path with controlled predictions: 95% passes, 94.99% fails.

    Stubs only the prediction mapper, still runs real integrity + evaluate plumbing.
    """
    # Build 100 RELEVANT with enough strata metadata + blockers to skip floor issues
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
            )
        )
    # add IRRELEVANT fillers
    for i in range(20):
        rows.append(
            _base_rec(
                f"I{i}",
                "IRRELEVANT",
                NON_OBJ,
                source=sources[i % 3],
                municipio_bucket=buckets[i % 3],
                natureza_juridica=naturezas[i % 2],
            )
        )

    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    man = {
        "role": "locked_holdout",
        "frozen_at": "2026-07-26T00:00:00Z",
        "sealed_before_classifier_edits": True,
        "corpus_sha256": sha256_file(p),
        "stratum_blockers": {},
    }
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(man), encoding="utf-8")

    # Force 95 TP + 5 FN among RELEVANT via classify_object stub
    call_i = {"n": 0}

    class FakeClf:
        def __init__(self, label: str):
            self.label = label
            self.reason = "stub"
            self.rule_version = RULE_VERSION

    def fake_classify(objeto=None, **kwargs):
        # Only count RELEVANT gold rows for sequencing via objeto+call
        call_i["n"] += 1
        # We'll map by call order on relevant-only inside score_records
        return FakeClf("ENGINEERING_HIGH_CONFIDENCE")

    # Better approach: monkeypatch predicted_relevant / score via classify labels
    # Use sequential labels: first 95 relevant-ish calls HIGH, next 5 NON
    seq = {"i": 0}

    def fake_classify2(objeto=None, **kwargs):
        # score_records calls classify for every non-UNDECIDABLE
        # RELEVANT are first 100 in our list, then 20 IRRELEVANT
        idx = seq["i"]
        seq["i"] += 1
        if idx < 95:
            return FakeClf("ENGINEERING_HIGH_CONFIDENCE")
        if idx < 100:
            return FakeClf("NON_ENGINEERING")  # FN
        return FakeClf("NON_ENGINEERING")  # TN for irrelevant

    monkeypatch.setattr("scripts.coverage.edital_relevance_recall.classify_object", fake_classify2)
    monkeypatch.setattr(
        "scripts.coverage.edital_relevance_recall.is_engineering_for_e",
        lambda clf: clf.label in {"ENGINEERING_HIGH_CONFIDENCE", "ENGINEERING_REVIEW"},
    )

    code, result = evaluate(
        p,
        manifest_path=mp,
        require_holdout_floor=True,
        allow_machine_labels=True,
        allow_synthetic=True,
        development_path=tmp_path / "empty-dev.jsonl",
    )
    assert result["relevance_recall"] == pytest.approx(0.95)
    assert code == 0
    assert result["pass"] is True

    # 94/100 fails
    seq["i"] = 0

    def fake_classify_94(objeto=None, **kwargs):
        idx = seq["i"]
        seq["i"] += 1
        if idx < 94:
            return FakeClf("ENGINEERING_HIGH_CONFIDENCE")
        if idx < 100:
            return FakeClf("NON_ENGINEERING")
        return FakeClf("NON_ENGINEERING")

    monkeypatch.setattr("scripts.coverage.edital_relevance_recall.classify_object", fake_classify_94)
    code2, result2 = evaluate(
        p,
        manifest_path=mp,
        require_holdout_floor=True,
        allow_machine_labels=True,
        allow_synthetic=True,
        development_path=tmp_path / "empty-dev.jsonl",
    )
    assert result2["relevance_recall"] == pytest.approx(0.94)
    assert code2 != 0
    assert result2["pass"] is False


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


def test_real_classifier_on_known_engineering():
    clf = classify_object(ENG_OBJ)
    assert clf.label in {
        "ENGINEERING_HIGH_CONFIDENCE",
        "ENGINEERING_REVIEW",
    }


def test_final_gate_rejects_machine_labels(tmp_path):
    """Final accept must fail-closed without human dual-independent labels."""
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
        "role": "locked_holdout",
        "frozen_at": "2026-07-26T00:00:00Z",
        "sealed_before_classifier_edits": True,
        "corpus_sha256": sha256_file(p),
        "stratum_blockers": {},
        "label_authority": "machine_criteria_draft",
    }
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(man), encoding="utf-8")
    code, result = evaluate(
        p,
        manifest_path=mp,
        require_holdout_floor=True,
        allow_machine_labels=False,
        allow_synthetic=True,
        development_path=tmp_path / "empty-dev.jsonl",
    )
    assert code != 0
    assert result["pass"] is False
    errs = " ".join(result["integrity"]["errors"])
    assert "human" in errs.lower() or "machine" in errs.lower()


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
        "role": "locked_holdout",
        "frozen_at": "2026-07-26T00:00:00Z",
        "sealed_before_classifier_edits": False,  # explicit fail
        "corpus_sha256": sha256_file(p),
        "stratum_blockers": {},
        "label_authority": "human_dual_independent",
        "pilot_human_approved_at": "2026-07-26T00:00:00Z",
    }
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(man), encoding="utf-8")
    code, result = evaluate(
        p,
        manifest_path=mp,
        require_holdout_floor=True,
        allow_machine_labels=False,
        allow_synthetic=True,
        development_path=tmp_path / "empty-dev.jsonl",
    )
    assert code != 0
    assert any("sealed" in e for e in result["integrity"]["errors"])
