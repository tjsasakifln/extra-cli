"""Unit tests for fail-closed edital relevance recall foundation (DOD §8.4)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from scripts.coverage.edital_relevance_recall import (
    BLOCKED_HUMAN_DUAL_LABELING,
    DEV_SELECTION_BASIS,
    DEV_SELECTION_RULE,
    DIAGNOSTIC_ONLY,
    FAILED_DEVELOPMENT_INTEGRITY,
    RECALL_THRESHOLD,
    check_corpus_integrity,
    check_development_integrity,
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
        "reviewed_at_a": "",
        "reviewed_at_b": "",
        "label_reviewer_a_reason": "",
        "label_reviewer_b_reason": "",
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

def test_cli_diagnose_on_pilot_36_is_diagnostic_only(tmp_path):
    root = Path(__file__).resolve().parents[2]
    corpus = root / "evals" / "edital_relevance" / "pilot_36.jsonl"
    manifest = root / "evals" / "edital_relevance" / "pilot_36-manifest.json"
    assert corpus.is_file() and manifest.is_file()
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


def _human_holdout_rows(n_relevant: int = 100, n_irrelevant: int = 20) -> list[dict]:
    """Build stratified human dual-labeled rows for final-gate tests."""
    rows: list[dict] = []
    sources = ["pncp", "sc_compras", "ciga"]
    buckets = ["grande", "medio", "pequeno"]
    naturezas = ["admin_direta", "admin_indireta"]
    human_fields = {
        "label_authority": "human_dual_independent",
        "human_reviewer_a_id": "tiago",
        "human_reviewer_b_id": "reviewer2",
        "reviewed_at_a": "2026-07-27T03:15:00Z",
        "reviewed_at_b": "2026-07-27T04:15:00+00:00",
        "label_reviewer_a_reason": "objeto de engenharia aderente",
        "label_reviewer_b_reason": "pavimentacao/obras civis",
    }
    for i in range(n_relevant):
        rows.append(
            _base_rec(
                f"R{i}",
                "RELEVANT",
                ENG_OBJ,
                source=sources[i % 3],
                municipio_bucket=buckets[i % 3],
                natureza_juridica=naturezas[i % 2],
                label_reviewer_a="RELEVANT",
                label_reviewer_b="RELEVANT",
                adjudication_reason="agreement:RELEVANT",
                **human_fields,
            )
        )
    for i in range(n_irrelevant):
        rows.append(
            _base_rec(
                f"I{i}",
                "IRRELEVANT",
                NON_OBJ,
                source=sources[i % 3],
                municipio_bucket=buckets[i % 3],
                natureza_juridica=naturezas[i % 2],
                label_reviewer_a="IRRELEVANT",
                label_reviewer_b="IRRELEVANT",
                adjudication_reason="agreement:IRRELEVANT",
                **human_fields,
            )
        )
    return rows


def _final_manifest(corpus_path: Path, **extra) -> dict:
    man = {
        "role": "human_sealed_holdout",
        "frozen_at": "2026-07-26T00:00:00Z",
        "sealed_holdout": True,
        "sealed_before_classifier_edits": True,
        "corpus_sha256": sha256_file(corpus_path),
        "stratum_blockers": {},
        "label_authority": "human_dual_independent",
        "pilot_human_approved_at": "2026-07-26T00:00:00Z",
        "pilot_human_approved_by": "tiago",
        "acceptance_eligible": True,
        "dod_item_accepted": False,
    }
    man.update(extra)
    return man


def _dev_record(oid: str, **extra) -> dict:
    rec = {
        "official_id": oid,
        "source": "pncp",
        "url": f"https://pncp.gov.br/app/editais/dev/{oid}",
        "objeto": "objeto público de desenvolvimento",
        "titulo": "",
        "observed_at": "2026-07-20T00:00:00Z",
        "content_hash": f"hash-{oid}",
        "selection_method": "public_inventory_stratified_content_sample",
        "selection_provenance": "public_inventory:pncp",
        "selected_by_classifier": False,
        "selected_by_db_presence": False,
        "selected_by_success_zero": False,
        "synthetic": False,
        "split": "development_candidate_pool",
    }
    rec.update(extra)
    return rec


def _write_dev_pair(tmp_path: Path, rows: list[dict], **man_extra) -> tuple[Path, Path]:
    """Write development corpus + manifest with matching sha/n_records/role flags.

    Uses absolute resolved path in the manifest (production requires exact path identity;
    basename-only matching is forbidden).
    """
    dev = tmp_path / "development_candidate_pool.jsonl"
    _write_jsonl(dev, rows)
    man = {
        "schema_version": "edital-relevance-corpus/1.1.0",
        "role": "development",
        "campaign": "EDITAL-RELEVANCE-RECALL-95-01",
        "acceptance_eligible": False,
        "sealed_holdout": False,
        "label_authority": "machine_criteria_draft",
        "corpus_path": str(dev.resolve()),
        "corpus_sha256": sha256_file(dev),
        "n_records": len(rows),
        "selection_rule": DEV_SELECTION_RULE,
        "selection_basis": DEV_SELECTION_BASIS,
        "selection_independent_of_classifier": True,
        "contamination_note": (
            "Development-only corpus. Never eligible for final holdout or DOD acceptance."
        ),
    }
    man.update(man_extra)
    if "corpus_sha256" not in man_extra:
        man["corpus_sha256"] = sha256_file(dev)
    if "n_records" not in man_extra:
        man["n_records"] = len(rows)
    if "corpus_path" not in man_extra:
        man["corpus_path"] = str(dev.resolve())
    mp = tmp_path / "development_candidate_pool-manifest.json"
    mp.write_text(json.dumps(man), encoding="utf-8")
    return dev, mp


def _valid_dev(tmp_path: Path, holdout_ids: set[str] | None = None) -> tuple[Path, Path]:
    """Non-empty development with no holdout overlap."""
    holdout_ids = holdout_ids or set()
    rows: list[dict] = []
    i = 0
    while len(rows) < 3:
        oid = f"DEV-{i}"
        i += 1
        if oid in holdout_ids:
            continue
        rows.append(_dev_record(oid))
    return _write_dev_pair(tmp_path, rows)


def _run_final(tmp_path: Path, rows: list[dict], man_extra: dict | None = None):
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    man = _final_manifest(p, **(man_extra or {}))
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(man), encoding="utf-8")
    hold_ids = {str(r["official_id"]) for r in rows}
    dev, dman = _valid_dev(tmp_path, hold_ids)
    code, result = evaluate(
        p,
        manifest_path=mp,
        mode="final",
        development_path=dev,
        development_manifest_path=dman,
    )
    return code, result


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
    code, result = _run_final(tmp_path, rows, {
        "role": "diagnostic_machine_draft",
        "sealed_holdout": False,
        "sealed_before_classifier_edits": False,
        "label_authority": "machine_criteria_draft",
        "acceptance_eligible": False,
        "pilot_human_approved_at": None,
        "pilot_human_approved_by": None,
    })
    # recompute sha after man_extra may have left corpus_sha256 from helper incorrectly
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
    code, result = _run_final(tmp_path, rows, {"role": "locked_holdout"})
    assert code != 0
    assert result["blocker"] == BLOCKED_HUMAN_DUAL_LABELING
    assert any(
        "human_sealed_holdout" in e or "locked_holdout" in e
        for e in result["integrity"]["errors"]
    )


def test_final_gate_rejects_missing_seal(tmp_path):
    rows = _human_holdout_rows()
    code, result = _run_final(
        tmp_path,
        rows,
        {"sealed_holdout": False, "sealed_before_classifier_edits": False},
    )
    assert code != 0
    assert any("sealed" in e for e in result["integrity"]["errors"])


def test_final_gate_rejects_missing_dual_labels(tmp_path):
    rows = _human_holdout_rows()
    for r in rows:
        r.pop("label_reviewer_a", None)
        r.pop("label_reviewer_b", None)
    code, result = _run_final(tmp_path, rows)
    assert code != 0
    assert result["pass"] is False
    assert result.get("status") != "ACCEPTED"
    assert result["blocker"] == BLOCKED_HUMAN_DUAL_LABELING
    errs = " ".join(result["integrity"]["errors"]).lower()
    assert "label_reviewer_a" in errs or "label_reviewer_b" in errs


def test_final_gate_rejects_label_final_contradicting_agreed_duals(tmp_path):
    rows = _human_holdout_rows()
    for r in rows:
        if r["official_id"] == "I0":
            r["label_final"] = "RELEVANT"
            r["label_reviewer_a"] = "IRRELEVANT"
            r["label_reviewer_b"] = "IRRELEVANT"
            r["adjudication_reason"] = "agreement:IRRELEVANT"
            break
    code, result = _run_final(tmp_path, rows)
    assert code != 0
    assert result["pass"] is False
    assert any("contradicts agreed dual" in e for e in result["integrity"]["errors"])


def test_final_gate_rejects_divergence_without_adjudication(tmp_path):
    rows = _human_holdout_rows()
    for r in rows:
        if r["official_id"] == "R0":
            r["label_reviewer_a"] = "RELEVANT"
            r["label_reviewer_b"] = "IRRELEVANT"
            r["label_final"] = "RELEVANT"
            r["adjudication_reason"] = ""
            r["labels_agreed"] = False
            break
    code, result = _run_final(tmp_path, rows)
    assert code != 0
    assert result["pass"] is False
    assert any("adjudication" in e.lower() for e in result["integrity"]["errors"])


def test_final_gate_requires_both_seal_flags_and(tmp_path):
    rows = _human_holdout_rows()
    for seal, before in ((True, False), (False, True)):
        code, result = _run_final(
            tmp_path,
            rows,
            {"sealed_holdout": seal, "sealed_before_classifier_edits": before},
        )
        assert code != 0
        assert result["pass"] is False
        errs = " ".join(result["integrity"]["errors"])
        assert "sealed_holdout" in errs or "sealed_before_classifier_edits" in errs


def test_final_gate_rejects_missing_corpus_sha256(tmp_path):
    rows = _human_holdout_rows()
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    man = _final_manifest(p)
    man.pop("corpus_sha256", None)
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(man), encoding="utf-8")
    dev, dman = _valid_dev(tmp_path, {r["official_id"] for r in rows})
    code, result = evaluate(
        p, manifest_path=mp, mode="final", development_path=dev, development_manifest_path=dman
    )
    assert code != 0
    assert any("corpus_sha256" in e for e in result["integrity"]["errors"])


def test_final_gate_rejects_omitted_development(tmp_path):
    rows = _human_holdout_rows()
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(_final_manifest(p)), encoding="utf-8")
    code, result = evaluate(p, manifest_path=mp, mode="final", development_path=None)
    assert code != 0
    assert any("development" in e.lower() for e in result["integrity"]["errors"])
    assert result["blocker"] == FAILED_DEVELOPMENT_INTEGRITY


def _assert_dev_integrity_blocker(result: dict) -> None:
    """Development technical failure must never surface as human dual-labeling primary."""
    assert result["development_integrity"]["pass"] is False
    assert result["blocker"] == FAILED_DEVELOPMENT_INTEGRITY
    assert result["blocker"] != BLOCKED_HUMAN_DUAL_LABELING
    blockers = set(result.get("blockers") or [])
    assert FAILED_DEVELOPMENT_INTEGRITY in blockers or result["blocker"] == FAILED_DEVELOPMENT_INTEGRITY


def test_final_gate_rejects_empty_development(tmp_path):
    rows = _human_holdout_rows()
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(_final_manifest(p)), encoding="utf-8")
    dev = tmp_path / "empty.jsonl"
    dev.write_text("", encoding="utf-8")
    dman = tmp_path / "empty-man.json"
    dman.write_text(
        json.dumps(
            {
                "role": "development",
                "acceptance_eligible": False,
                "sealed_holdout": False,
                "corpus_path": str(dev.resolve()),
                "corpus_sha256": sha256_file(dev),
                "n_records": 0,
                "selection_rule": DEV_SELECTION_RULE,
                "selection_basis": DEV_SELECTION_BASIS,
                "selection_independent_of_classifier": True,
            }
        ),
        encoding="utf-8",
    )
    code, result = evaluate(
        p, manifest_path=mp, mode="final", development_path=dev, development_manifest_path=dman
    )
    assert code != 0
    assert any("empty" in e.lower() for e in result["integrity"]["errors"])
    _assert_dev_integrity_blocker(result)


def test_final_gate_rejects_missing_development_manifest(tmp_path):
    rows = _human_holdout_rows()
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(_final_manifest(p)), encoding="utf-8")
    dev, _ = _valid_dev(tmp_path, {r["official_id"] for r in rows})
    code, result = evaluate(
        p, manifest_path=mp, mode="final", development_path=dev, development_manifest_path=None
    )
    assert code != 0
    assert any("development-manifest" in e.lower() or "development manifest" in e.lower()
               for e in result["integrity"]["errors"])
    _assert_dev_integrity_blocker(result)


def test_final_gate_rejects_development_missing_hash(tmp_path):
    rows = _human_holdout_rows()
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(_final_manifest(p)), encoding="utf-8")
    dev, dman = _write_dev_pair(tmp_path, [_dev_record("DEV-X")], corpus_sha256="")
    code, result = evaluate(
        p, manifest_path=mp, mode="final", development_path=dev, development_manifest_path=dman
    )
    assert code != 0
    assert any("corpus_sha256" in e for e in result["integrity"]["errors"])
    _assert_dev_integrity_blocker(result)


def test_final_gate_rejects_development_wrong_hash(tmp_path):
    rows = _human_holdout_rows()
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(_final_manifest(p)), encoding="utf-8")
    dev, dman = _write_dev_pair(
        tmp_path, [_dev_record("DEV-Y")], corpus_sha256="0" * 64
    )
    code, result = evaluate(
        p, manifest_path=mp, mode="final", development_path=dev, development_manifest_path=dman
    )
    assert code != 0
    assert any("mismatch" in e.lower() for e in result["integrity"]["errors"])
    _assert_dev_integrity_blocker(result)


def test_final_gate_rejects_development_wrong_n_records(tmp_path):
    rows = _human_holdout_rows()
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(_final_manifest(p)), encoding="utf-8")
    dev, dman = _write_dev_pair(tmp_path, [_dev_record("DEV-Z")], n_records=99)
    code, result = evaluate(
        p, manifest_path=mp, mode="final", development_path=dev, development_manifest_path=dman
    )
    assert code != 0
    assert any("n_records" in e for e in result["integrity"]["errors"])
    _assert_dev_integrity_blocker(result)


def test_final_gate_rejects_development_wrong_role(tmp_path):
    rows = _human_holdout_rows()
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(_final_manifest(p)), encoding="utf-8")
    dev, dman = _write_dev_pair(tmp_path, [_dev_record("DEV-R")], role="holdout")
    code, result = evaluate(
        p, manifest_path=mp, mode="final", development_path=dev, development_manifest_path=dman
    )
    assert code != 0
    assert any("role" in e.lower() for e in result["integrity"]["errors"])
    _assert_dev_integrity_blocker(result)


def test_final_gate_rejects_development_acceptance_eligible(tmp_path):
    rows = _human_holdout_rows()
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(_final_manifest(p)), encoding="utf-8")
    dev, dman = _write_dev_pair(
        tmp_path, [_dev_record("DEV-A")], acceptance_eligible=True
    )
    code, result = evaluate(
        p, manifest_path=mp, mode="final", development_path=dev, development_manifest_path=dman
    )
    assert code != 0
    assert any("acceptance_eligible" in e for e in result["integrity"]["errors"])
    _assert_dev_integrity_blocker(result)


def test_final_gate_rejects_development_sealed_holdout(tmp_path):
    rows = _human_holdout_rows()
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(_final_manifest(p)), encoding="utf-8")
    dev, dman = _write_dev_pair(tmp_path, [_dev_record("DEV-S")], sealed_holdout=True)
    code, result = evaluate(
        p, manifest_path=mp, mode="final", development_path=dev, development_manifest_path=dman
    )
    assert code != 0
    assert any("sealed_holdout" in e for e in result["integrity"]["errors"])
    _assert_dev_integrity_blocker(result)


def test_final_gate_rejects_development_duplicate_ids(tmp_path):
    rows = _human_holdout_rows()
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(_final_manifest(p)), encoding="utf-8")
    dev_rows = [_dev_record("DUP"), _dev_record("DUP")]
    dev, dman = _write_dev_pair(tmp_path, dev_rows)
    code, result = evaluate(
        p, manifest_path=mp, mode="final", development_path=dev, development_manifest_path=dman
    )
    assert code != 0
    assert result["development_integrity"]["duplicate_ids"]
    assert any("duplicate" in e.lower() for e in result["integrity"]["errors"])
    _assert_dev_integrity_blocker(result)


def test_final_gate_rejects_development_leak(tmp_path):
    rows = _human_holdout_rows()
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(_final_manifest(p)), encoding="utf-8")
    leak = dict(rows[0])
    # strip to development-shaped record with same id
    dev_rows = [_dev_record(str(leak["official_id"]))]
    dev, dman = _write_dev_pair(tmp_path, dev_rows)
    code, result = evaluate(
        p, manifest_path=mp, mode="final", development_path=dev, development_manifest_path=dman
    )
    assert code != 0
    assert result["development_integrity"]["holdout_overlap_count"] >= 1
    assert any("leakage" in e.lower() for e in result["integrity"]["errors"])
    _assert_dev_integrity_blocker(result)


def test_final_gate_rejects_synthetic_development(tmp_path):
    rows = _human_holdout_rows()
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(_final_manifest(p)), encoding="utf-8")
    dev, dman = _write_dev_pair(tmp_path, [_dev_record("SYN", synthetic=True)])
    code, result = evaluate(
        p, manifest_path=mp, mode="final", development_path=dev, development_manifest_path=dman
    )
    assert code != 0
    assert any("synthetic" in e.lower() for e in result["integrity"]["errors"])
    _assert_dev_integrity_blocker(result)


def test_final_gate_rejects_classifier_selected_development(tmp_path):
    rows = _human_holdout_rows()
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(_final_manifest(p)), encoding="utf-8")
    dev, dman = _write_dev_pair(
        tmp_path, [_dev_record("CLF", selected_by_classifier=True)]
    )
    code, result = evaluate(
        p, manifest_path=mp, mode="final", development_path=dev, development_manifest_path=dman
    )
    assert code != 0
    assert any("selected_by_classifier" in e for e in result["integrity"]["errors"])
    _assert_dev_integrity_blocker(result)


def test_final_gate_rejects_db_presence_selected_development(tmp_path):
    rows = _human_holdout_rows()
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(_final_manifest(p)), encoding="utf-8")
    dev, dman = _write_dev_pair(
        tmp_path, [_dev_record("DB", selected_by_db_presence=True)]
    )
    code, result = evaluate(
        p, manifest_path=mp, mode="final", development_path=dev, development_manifest_path=dman
    )
    assert code != 0
    assert any("selected_by_db_presence" in e for e in result["integrity"]["errors"])
    _assert_dev_integrity_blocker(result)


def test_final_gate_rejects_success_zero_selected_development(tmp_path):
    rows = _human_holdout_rows()
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(_final_manifest(p)), encoding="utf-8")
    dev, dman = _write_dev_pair(
        tmp_path, [_dev_record("SZ", selected_by_success_zero=True)]
    )
    code, result = evaluate(
        p, manifest_path=mp, mode="final", development_path=dev, development_manifest_path=dman
    )
    assert code != 0
    assert any("selected_by_success_zero" in e for e in result["integrity"]["errors"])
    _assert_dev_integrity_blocker(result)


def test_final_gate_valid_development_no_overlap(tmp_path):
    rows = _human_holdout_rows()
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(_final_manifest(p)), encoding="utf-8")
    dev, dman = _valid_dev(tmp_path, {r["official_id"] for r in rows})
    di, errs = check_development_integrity(
        development_path=dev,
        development_manifest_path=dman,
        holdout_ids=[r["official_id"] for r in rows],
        required=True,
    )
    assert errs == []
    assert di["pass"] is True
    assert di["n_records"] >= 3
    assert di["holdout_overlap_count"] == 0
    assert di["duplicate_ids"] == []
    assert di["sha256"] == sha256_file(dev)


def test_committed_development_candidate_pool_integrity():
    root = Path(__file__).resolve().parents[2]
    dev = root / "evals" / "edital_relevance" / "development_candidate_pool.jsonl"
    dman = root / "evals" / "edital_relevance" / "development_candidate_pool-manifest.json"
    pilot = root / "evals" / "edital_relevance" / "pilot_36.jsonl"
    assert dev.is_file() and dman.is_file()
    assert dev.stat().st_size > 0
    pilot_ids = [
        __import__("json").loads(line)["official_id"]
        for line in pilot.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    di, errs = check_development_integrity(
        development_path=dev,
        development_manifest_path=dman,
        holdout_ids=pilot_ids,
        required=True,
    )
    assert errs == [], errs
    assert di["pass"] is True
    assert di["n_records"] >= 20
    assert di["holdout_overlap_count"] == 0


def test_cli_evaluate_final_on_pilot_36_blocks(tmp_path):
    """Operational honest state: valid development + human dual labeling absent."""
    root = Path(__file__).resolve().parents[2]
    corpus = root / "evals" / "edital_relevance" / "pilot_36.jsonl"
    manifest = root / "evals" / "edital_relevance" / "pilot_36-manifest.json"
    dev = root / "evals" / "edital_relevance" / "development_candidate_pool.jsonl"
    dman = root / "evals" / "edital_relevance" / "development_candidate_pool-manifest.json"
    out = tmp_path / "final.json"
    code = main(
        [
            "evaluate-final",
            "--corpus",
            str(corpus),
            "--manifest",
            str(manifest),
            "--development",
            str(dev),
            "--development-manifest",
            str(dman),
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
    assert result["sealed_holdout"] is False
    di = result["development_integrity"]
    assert di["pass"] is True
    assert di["n_records"] == 24
    assert di["duplicate_ids"] == []
    assert di["holdout_overlap_count"] == 0
    assert di["holdout_overlap_ids"] == []
    assert di["sha256"]
    assert FAILED_DEVELOPMENT_INTEGRITY not in {
        result.get("blocker"),
        *(result.get("blockers") or []),
    }


def test_final_gate_cli_requires_development_flag(tmp_path):
    root = Path(__file__).resolve().parents[2]
    corpus = root / "evals" / "edital_relevance" / "pilot_36.jsonl"
    manifest = root / "evals" / "edital_relevance" / "pilot_36-manifest.json"
    with pytest.raises(SystemExit):
        main(
            [
                "evaluate-final",
                "--corpus",
                str(corpus),
                "--manifest",
                str(manifest),
            ]
        )


def test_final_gate_cli_requires_development_manifest_flag(tmp_path):
    root = Path(__file__).resolve().parents[2]
    corpus = root / "evals" / "edital_relevance" / "pilot_36.jsonl"
    manifest = root / "evals" / "edital_relevance" / "pilot_36-manifest.json"
    dev = root / "evals" / "edital_relevance" / "development_candidate_pool.jsonl"
    with pytest.raises(SystemExit):
        main(
            [
                "evaluate-final",
                "--corpus",
                str(corpus),
                "--manifest",
                str(manifest),
                "--development",
                str(dev),
            ]
        )


def test_final_gate_accepts_agreed_human_duals_with_integrity(tmp_path, monkeypatch):
    """Honest path: dual labels present, agree with final, seal + pilot → integrity ok."""
    rows = _human_holdout_rows()
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(_final_manifest(p)), encoding="utf-8")
    dev, dman = _valid_dev(tmp_path, {r["official_id"] for r in rows})

    class FakeClf:
        def __init__(self, label: str):
            self.label = label
            self.reason = "stub"
            self.rule_version = "extra-sector-classifier/test"

    def always_eng(objeto=None, **kwargs):
        return FakeClf("ENGINEERING_HIGH_CONFIDENCE")

    monkeypatch.setattr(
        "scripts.coverage.edital_relevance_recall.classify_object",
        always_eng,
    )
    monkeypatch.setattr(
        "scripts.coverage.edital_relevance_recall.is_engineering_for_e",
        lambda clf: True,
    )
    code, result = evaluate(
        p,
        manifest_path=mp,
        mode="final",
        development_path=dev,
        development_manifest_path=dman,
    )
    dual_errs = [
        e
        for e in result["integrity"]["errors"]
        if any(
            k in e.lower()
            for k in (
                "label_reviewer",
                "contradict",
                "adjudication",
                "human dual",
                "machine",
                "sealed",
                "pilot",
                "development",
                "corpus_sha256",
            )
        )
    ]
    assert dual_errs == [], dual_errs
    assert result["development_integrity"]["pass"] is True
    assert result["relevance_recall"] == pytest.approx(1.0)
    assert code == 0
    assert result["pass"] is True
    assert result["dod_item_accepted"] is False


# ---------------------------------------------------------------------------
# Fail-closed residual patch: precedence, path identity, reviewer final gate
# ---------------------------------------------------------------------------


def test_precedence_wrong_hash_is_development_not_human(tmp_path):
    rows = _human_holdout_rows()
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(_final_manifest(p)), encoding="utf-8")
    dev, dman = _write_dev_pair(
        tmp_path, [_dev_record("DEV-HASH")], corpus_sha256="deadbeef" * 8
    )
    code, result = evaluate(
        p, manifest_path=mp, mode="final", development_path=dev, development_manifest_path=dman
    )
    assert code != 0
    assert result["blocker"] == FAILED_DEVELOPMENT_INTEGRITY
    assert result["blocker"] != BLOCKED_HUMAN_DUAL_LABELING
    assert result["development_integrity"]["pass"] is False


def test_precedence_overlap_is_development_integrity(tmp_path):
    rows = _human_holdout_rows()
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(_final_manifest(p)), encoding="utf-8")
    dev, dman = _write_dev_pair(tmp_path, [_dev_record(str(rows[0]["official_id"]))])
    code, result = evaluate(
        p, manifest_path=mp, mode="final", development_path=dev, development_manifest_path=dman
    )
    assert code != 0
    assert result["blocker"] == FAILED_DEVELOPMENT_INTEGRITY
    assert result["development_integrity"]["holdout_overlap_count"] >= 1


def test_precedence_multiple_dev_invalid_and_human_absent(tmp_path):
    """Development invalid + human gold absent → primary is technical."""
    # Machine pilot-like holdout (human absent) + wrong development hash
    rows = [
        _base_rec(
            f"R{i}",
            "RELEVANT",
            ENG_OBJ,
            source=["pncp", "sc_compras", "ciga"][i % 3],
            municipio_bucket=["grande", "medio", "pequeno"][i % 3],
            natureza_juridica=["admin_direta", "admin_indireta"][i % 2],
            label_authority="machine_criteria_draft",
        )
        for i in range(100)
    ]
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    mp = tmp_path / "m.json"
    man = _final_manifest(
        p,
        role="pilot_candidate",
        sealed_holdout=False,
        sealed_before_classifier_edits=False,
        label_authority="machine_criteria_draft",
        acceptance_eligible=False,
        pilot_human_approved_at=None,
        pilot_human_approved_by=None,
    )
    mp.write_text(json.dumps(man), encoding="utf-8")
    dev, dman = _write_dev_pair(
        tmp_path, [_dev_record("DEV-MULTI")], corpus_sha256="0" * 64
    )
    code, result = evaluate(
        p, manifest_path=mp, mode="final", development_path=dev, development_manifest_path=dman
    )
    assert code != 0
    assert result["blocker"] == FAILED_DEVELOPMENT_INTEGRITY
    # Human may appear as secondary, never as primary when development fails.
    blockers = result.get("blockers") or []
    assert FAILED_DEVELOPMENT_INTEGRITY in blockers or result["blocker"] == FAILED_DEVELOPMENT_INTEGRITY
    if BLOCKED_HUMAN_DUAL_LABELING in blockers:
        assert result["blocker"] != BLOCKED_HUMAN_DUAL_LABELING


def test_development_manifest_wrong_path_same_basename(tmp_path):
    """Manifest path in dir A + CLI file in dir B with same basename must fail."""
    rows = _human_holdout_rows()
    p = tmp_path / "hold.jsonl"
    _write_jsonl(p, rows)
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(_final_manifest(p)), encoding="utf-8")
    dir_a = tmp_path / "dir_a"
    dir_b = tmp_path / "dir_b"
    dir_a.mkdir()
    dir_b.mkdir()
    dev_a = dir_a / "development_candidate_pool.jsonl"
    dev_b = dir_b / "development_candidate_pool.jsonl"
    recs = [_dev_record("DEV-PATH-A"), _dev_record("DEV-PATH-B"), _dev_record("DEV-PATH-C")]
    _write_jsonl(dev_a, recs)
    _write_jsonl(dev_b, recs)
    # Manifest points at dir_a; CLI provides dir_b (same basename).
    dman = tmp_path / "dev-man.json"
    dman.write_text(
        json.dumps(
            {
                "role": "development",
                "acceptance_eligible": False,
                "sealed_holdout": False,
                "corpus_path": str(dev_a.resolve()),
                "corpus_sha256": sha256_file(dev_b),  # hash of CLI file
                "n_records": 3,
                "selection_rule": DEV_SELECTION_RULE,
                "selection_basis": DEV_SELECTION_BASIS,
                "selection_independent_of_classifier": True,
            }
        ),
        encoding="utf-8",
    )
    code, result = evaluate(
        p,
        manifest_path=mp,
        mode="final",
        development_path=dev_b,
        development_manifest_path=dman,
    )
    assert code != 0
    assert result["blocker"] == FAILED_DEVELOPMENT_INTEGRITY
    assert any("corpus_path mismatch" in e for e in result["integrity"]["errors"])


@pytest.mark.parametrize(
    "a_id,b_id",
    [
        ("Tiago", "tiago"),
        ("Tiago", "TIAGO"),
        ("Tiago", " Tiago "),
        ("A  B", "a b"),
    ],
)
def test_final_evaluator_rejects_normalized_same_reviewer(tmp_path, a_id, b_id):
    rows = _human_holdout_rows()
    for r in rows:
        r["human_reviewer_a_id"] = a_id
        r["human_reviewer_b_id"] = b_id
    code, result = _run_final(tmp_path, rows)
    assert code != 0
    assert result["blocker"] == BLOCKED_HUMAN_DUAL_LABELING
    errs = " ".join(result["integrity"]["errors"]).lower()
    assert "distinct" in errs or "normalize" in errs


@pytest.mark.parametrize(
    "ts",
    [
        "2026-07-27T03:15:00",  # naive
        "2026-07-27",  # date-only
        "03:15:00",
        "pending",
        "null",
        "tbd",
        "",
    ],
)
def test_final_evaluator_rejects_invalid_reviewed_at(tmp_path, ts):
    rows = _human_holdout_rows()
    for r in rows:
        r["reviewed_at_a"] = ts
    code, result = _run_final(tmp_path, rows)
    assert code != 0
    assert result["blocker"] == BLOCKED_HUMAN_DUAL_LABELING
    assert any("reviewed_at_a" in e for e in result["integrity"]["errors"])


def test_final_evaluator_rejects_missing_reason_a(tmp_path):
    rows = _human_holdout_rows()
    for r in rows:
        r["label_reviewer_a_reason"] = ""
    code, result = _run_final(tmp_path, rows)
    assert code != 0
    assert any("label_reviewer_a_reason" in e for e in result["integrity"]["errors"])


def test_final_evaluator_rejects_missing_reason_b(tmp_path):
    rows = _human_holdout_rows()
    for r in rows:
        r["label_reviewer_b_reason"] = ""
    code, result = _run_final(tmp_path, rows)
    assert code != 0
    assert any("label_reviewer_b_reason" in e for e in result["integrity"]["errors"])


def test_final_evaluator_accepts_timezone_variants(tmp_path, monkeypatch):
    rows = _human_holdout_rows()
    for r in rows:
        r["reviewed_at_a"] = "2026-07-27T03:15:00Z"
        r["reviewed_at_b"] = "2026-07-27T00:15:00-03:00"

    class FakeClf:
        def __init__(self, label: str):
            self.label = label
            self.reason = "stub"
            self.rule_version = "extra-sector-classifier/test"

    monkeypatch.setattr(
        "scripts.coverage.edital_relevance_recall.classify_object",
        lambda *a, **k: FakeClf("ENGINEERING_HIGH_CONFIDENCE"),
    )
    monkeypatch.setattr(
        "scripts.coverage.edital_relevance_recall.is_engineering_for_e",
        lambda clf: True,
    )
    code, result = _run_final(tmp_path, rows)
    assert not any("reviewed_at" in e for e in result["integrity"]["errors"])
    assert result["development_integrity"]["pass"] is True
    assert code == 0
    assert result["pass"] is True


def test_valid_development_human_pending_blocker(tmp_path):
    """Valid development + machine holdout → BLOCKED_HUMAN_DUAL_LABELING only."""
    rows = [
        _base_rec(
            f"R{i}",
            "RELEVANT",
            ENG_OBJ,
            source=["pncp", "sc_compras", "ciga"][i % 3],
            municipio_bucket=["grande", "medio", "pequeno"][i % 3],
            natureza_juridica=["admin_direta", "admin_indireta"][i % 2],
            label_authority="machine_criteria_draft",
        )
        for i in range(100)
    ]
    code, result = _run_final(
        tmp_path,
        rows,
        {
            "role": "pilot_candidate",
            "sealed_holdout": False,
            "sealed_before_classifier_edits": False,
            "label_authority": "machine_criteria_draft",
            "acceptance_eligible": False,
            "pilot_human_approved_at": None,
            "pilot_human_approved_by": None,
        },
    )
    assert code != 0
    assert result["blocker"] == BLOCKED_HUMAN_DUAL_LABELING
    assert result["development_integrity"]["pass"] is True
    assert FAILED_DEVELOPMENT_INTEGRITY not in {
        result.get("blocker"),
        *(result.get("blockers") or []),
    }
