"""Tests for blind human labeling packages + import validation."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.campaigns.edital_relevance.human_labeling import (
    BLIND_COLUMNS,
    FORBIDDEN_BLIND_FIELDS,
    IMMUTABLE_FIELDS,
    generate_blind_packages,
    import_human_labels,
    main,
    read_blind_csv,
)


def _candidate(oid: str, objeto: str = "obra de pavimentação") -> dict:
    return {
        "official_id": oid,
        "source": "pncp",
        "url": f"https://pncp.gov.br/app/editais/test/{oid}",
        "titulo": "Edital teste",
        "objeto": objeto,
        "observed_at": "2026-07-20T00:00:00Z",
        # inducement fields that must never leak into blind packages
        "label_final": "RELEVANT",
        "label_authority": "machine_criteria_draft",
        "score": 0.99,
        "predicted_label": "ENGINEERING_HIGH_CONFIDENCE",
        "selected_by_classifier": False,
    }


def test_generate_blind_packages_empty_labels_and_same_ids(tmp_path):
    records = [_candidate(f"ID{i}") for i in range(5)]
    out_a = tmp_path / "a.csv"
    out_b = tmp_path / "b.csv"
    meta = generate_blind_packages(records, out_a=out_a, out_b=out_b)
    assert meta["n"] == 5
    assert meta["label_cells_empty"] is True

    rows_a = read_blind_csv(out_a)
    rows_b = read_blind_csv(out_b)
    assert {r["official_id"] for r in rows_a} == {r["official_id"] for r in rows_b}
    assert all(r["label"] == "" and r["reason"] == "" for r in rows_a + rows_b)
    assert list(rows_a[0].keys()) == list(BLIND_COLUMNS)
    # different order likely (different seeds)
    # but both valid
    for r in rows_a:
        for bad in FORBIDDEN_BLIND_FIELDS:
            assert bad not in r


def test_pilot_36_packages_committed_shape():
    root = Path(__file__).resolve().parents[2]
    a = root / "evals" / "edital_relevance" / "pilot_36_reviewer_a.csv"
    b = root / "evals" / "edital_relevance" / "pilot_36_reviewer_b.csv"
    assert a.is_file() and b.is_file()
    rows_a = read_blind_csv(a)
    rows_b = read_blind_csv(b)
    assert len(rows_a) == 36
    assert len(rows_b) == 36
    assert {r["official_id"] for r in rows_a} == {r["official_id"] for r in rows_b}
    assert all(r["label"] == "" and r["reason"] == "" for r in rows_a + rows_b)
    # no inducement columns
    with a.open(encoding="utf-8") as fh:
        header = fh.readline()
    for bad in ("score", "label_final", "predicted", "machine", "system_class"):
        assert bad not in header.lower()


def test_import_requires_distinct_reviewers(tmp_path):
    records = [_candidate("A1"), _candidate("A2")]
    pa = tmp_path / "a.csv"
    pb = tmp_path / "b.csv"
    generate_blind_packages(records, out_a=pa, out_b=pb)

    def fill(path: Path, label: str) -> None:
        rows = read_blind_csv(path)
        for r in rows:
            r["label"] = label
            r["reason"] = "human"
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(BLIND_COLUMNS))
            w.writeheader()
            w.writerows(rows)

    fill(pa, "RELEVANT")
    fill(pb, "RELEVANT")
    rep = import_human_labels(
        package_a=pa,
        package_b=pb,
        reviewer_a_id="same_person",
        reviewer_b_id="same_person",
        reviewed_at_a="2026-07-26T12:00:00Z",
        reviewed_at_b="2026-07-26T13:00:00Z",
    )
    assert not rep.ok
    assert any("distinct" in e for e in rep.errors)


def test_import_rejects_machine_identity(tmp_path):
    records = [_candidate("A1")]
    pa = tmp_path / "a.csv"
    pb = tmp_path / "b.csv"
    generate_blind_packages(records, out_a=pa, out_b=pb)
    for path, lab in ((pa, "RELEVANT"), (pb, "RELEVANT")):
        rows = read_blind_csv(path)
        for r in rows:
            r["label"] = lab
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(BLIND_COLUMNS))
            w.writeheader()
            w.writerows(rows)
    rep = import_human_labels(
        package_a=pa,
        package_b=pb,
        reviewer_a_id="criteria_A_MACHINE",
        reviewer_b_id="human_b",
        reviewed_at_a="2026-07-26T12:00:00Z",
        reviewed_at_b="2026-07-26T13:00:00Z",
    )
    assert not rep.ok
    assert any("machine" in e.lower() or "criteria" in e.lower() for e in rep.errors)


def test_import_requires_adjudication_on_divergence(tmp_path):
    records = [_candidate("A1"), _candidate("A2")]
    pa = tmp_path / "a.csv"
    pb = tmp_path / "b.csv"
    generate_blind_packages(records, out_a=pa, out_b=pb)

    def fill(path: Path, labels: dict[str, str]) -> None:
        rows = read_blind_csv(path)
        for r in rows:
            r["label"] = labels[r["official_id"]]
            r["reason"] = "human"
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(BLIND_COLUMNS))
            w.writeheader()
            w.writerows(rows)

    fill(pa, {"A1": "RELEVANT", "A2": "IRRELEVANT"})
    fill(pb, {"A1": "IRRELEVANT", "A2": "IRRELEVANT"})  # A1 diverges

    rep = import_human_labels(
        package_a=pa,
        package_b=pb,
        reviewer_a_id="tiago",
        reviewer_b_id="reviewer2",
        reviewed_at_a="2026-07-26T12:00:00Z",
        reviewed_at_b="2026-07-26T13:00:00Z",
    )
    assert not rep.ok
    assert any("adjudication" in e for e in rep.errors)

    rep2 = import_human_labels(
        package_a=pa,
        package_b=pb,
        reviewer_a_id="tiago",
        reviewer_b_id="reviewer2",
        reviewed_at_a="2026-07-26T12:00:00Z",
        reviewed_at_b="2026-07-26T13:00:00Z",
        adjudication={"A1": {"label": "RELEVANT", "reason": "human adjudicator: obra de engenharia"}},
    )
    assert rep2.ok
    by_id = {r["official_id"]: r for r in rep2.records}
    assert by_id["A1"]["label_final"] == "RELEVANT"
    assert by_id["A1"]["label_authority"] == "human_dual_independent"
    assert by_id["A1"]["human_reviewer_a_id"] == "tiago"
    assert by_id["A1"]["human_reviewer_b_id"] == "reviewer2"


def test_import_rejects_empty_label_no_autofill(tmp_path):
    records = [_candidate("A1")]
    pa = tmp_path / "a.csv"
    pb = tmp_path / "b.csv"
    generate_blind_packages(records, out_a=pa, out_b=pb)
    # leave labels empty (as generated)
    rep = import_human_labels(
        package_a=pa,
        package_b=pb,
        reviewer_a_id="tiago",
        reviewer_b_id="reviewer2",
        reviewed_at_a="2026-07-26T12:00:00Z",
        reviewed_at_b="2026-07-26T13:00:00Z",
    )
    assert not rep.ok
    assert any("empty label" in e or "auto-fill" in e for e in rep.errors)


def test_import_forbids_silent_undecidable_conversion(tmp_path):
    records = [_candidate("A1")]
    pa = tmp_path / "a.csv"
    pb = tmp_path / "b.csv"
    generate_blind_packages(records, out_a=pa, out_b=pb)

    def fill(path: Path, label: str) -> None:
        rows = read_blind_csv(path)
        for r in rows:
            r["label"] = label
            r["reason"] = "human"
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(BLIND_COLUMNS))
            w.writeheader()
            w.writerows(rows)

    fill(pa, "UNDECIDABLE")
    fill(pb, "IRRELEVANT")
    rep = import_human_labels(
        package_a=pa,
        package_b=pb,
        reviewer_a_id="tiago",
        reviewer_b_id="reviewer2",
        reviewed_at_a="2026-07-26T12:00:00Z",
        reviewed_at_b="2026-07-26T13:00:00Z",
        adjudication={"A1": {"label": "IRRELEVANT", "reason": "silent_undecidable"}},
    )
    assert not rep.ok
    assert any("UNDECIDABLE" in e for e in rep.errors)


def test_cli_generate_blind(tmp_path):
    corpus = tmp_path / "c.jsonl"
    corpus.write_text(
        "\n".join(json.dumps(_candidate(f"X{i}")) for i in range(3)) + "\n",
        encoding="utf-8",
    )
    out_a = tmp_path / "a.csv"
    out_b = tmp_path / "b.csv"
    code = main(
        [
            "generate-blind",
            "--corpus",
            str(corpus),
            "--out-a",
            str(out_a),
            "--out-b",
            str(out_b),
        ]
    )
    assert code == 0
    assert out_a.is_file() and out_b.is_file()


def _fill_packages(
    records: list[dict],
    tmp_path: Path,
    *,
    label_a: str = "RELEVANT",
    label_b: str = "RELEVANT",
    reason: str = "human",
    mutate_a: dict[str, str] | None = None,
) -> tuple[Path, Path, Path]:
    """Generate packages, fill labels, optionally mutate immutable field on A."""
    pa = tmp_path / "a.csv"
    pb = tmp_path / "b.csv"
    generate_blind_packages(records, out_a=pa, out_b=pb)
    corpus = tmp_path / "expected.jsonl"
    corpus.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )

    def fill(path: Path, label: str, mutate: dict[str, str] | None = None) -> None:
        rows = read_blind_csv(path)
        for r in rows:
            r["label"] = label
            r["reason"] = reason
            if mutate:
                for k, v in mutate.items():
                    r[k] = v
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(BLIND_COLUMNS))
            w.writeheader()
            w.writerows(rows)

    fill(pa, label_a, mutate_a)
    fill(pb, label_b)
    return pa, pb, corpus


def test_import_rejects_edited_objeto(tmp_path):
    records = [_candidate("A1")]
    pa, pb, corpus = _fill_packages(
        records, tmp_path, mutate_a={"objeto": "OBJETO EDITADO MALICIOSAMENTE"}
    )
    rep = import_human_labels(
        package_a=pa,
        package_b=pb,
        reviewer_a_id="tiago",
        reviewer_b_id="reviewer2",
        reviewed_at_a="2026-07-26T12:00:00Z",
        reviewed_at_b="2026-07-26T13:00:00Z",
        expected_corpus=corpus,
    )
    assert not rep.ok
    assert any("objeto" in e and "immutable" in e for e in rep.errors)


def test_import_rejects_edited_url(tmp_path):
    records = [_candidate("A1")]
    pa, pb, corpus = _fill_packages(
        records, tmp_path, mutate_a={"url": "https://evil.example/fake"}
    )
    rep = import_human_labels(
        package_a=pa,
        package_b=pb,
        reviewer_a_id="tiago",
        reviewer_b_id="reviewer2",
        reviewed_at_a="2026-07-26T12:00:00Z",
        reviewed_at_b="2026-07-26T13:00:00Z",
        expected_corpus=corpus,
    )
    assert not rep.ok
    assert any("url" in e and "immutable" in e for e in rep.errors)


def test_import_rejects_edited_source(tmp_path):
    records = [_candidate("A1")]
    pa, pb, corpus = _fill_packages(records, tmp_path, mutate_a={"source": "forged_source"})
    rep = import_human_labels(
        package_a=pa,
        package_b=pb,
        reviewer_a_id="tiago",
        reviewer_b_id="reviewer2",
        reviewed_at_a="2026-07-26T12:00:00Z",
        reviewed_at_b="2026-07-26T13:00:00Z",
        expected_corpus=corpus,
    )
    assert not rep.ok
    assert any("source" in e and "immutable" in e for e in rep.errors)


def test_import_rejects_edited_observed_at(tmp_path):
    records = [_candidate("A1")]
    pa, pb, corpus = _fill_packages(
        records, tmp_path, mutate_a={"observed_at": "2099-01-01T00:00:00Z"}
    )
    rep = import_human_labels(
        package_a=pa,
        package_b=pb,
        reviewer_a_id="tiago",
        reviewer_b_id="reviewer2",
        reviewed_at_a="2026-07-26T12:00:00Z",
        reviewed_at_b="2026-07-26T13:00:00Z",
        expected_corpus=corpus,
    )
    assert not rep.ok
    assert any("observed_at" in e and "immutable" in e for e in rep.errors)


def test_import_rejects_id_set_mismatch(tmp_path):
    records = [_candidate("A1"), _candidate("A2")]
    pa, pb, corpus = _fill_packages(records, tmp_path)
    # Drop A2 from package A by rewriting with only A1
    rows = [r for r in read_blind_csv(pa) if r["official_id"] == "A1"]
    with pa.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(BLIND_COLUMNS))
        w.writeheader()
        w.writerows(rows)
    rep = import_human_labels(
        package_a=pa,
        package_b=pb,
        reviewer_a_id="tiago",
        reviewer_b_id="reviewer2",
        reviewed_at_a="2026-07-26T12:00:00Z",
        reviewed_at_b="2026-07-26T13:00:00Z",
        expected_corpus=corpus,
    )
    assert not rep.ok
    assert any("ID set mismatch" in e for e in rep.errors)


def test_import_rejects_empty_reason(tmp_path):
    records = [_candidate("A1")]
    pa, pb, corpus = _fill_packages(records, tmp_path, reason="")
    rep = import_human_labels(
        package_a=pa,
        package_b=pb,
        reviewer_a_id="tiago",
        reviewer_b_id="reviewer2",
        reviewed_at_a="2026-07-26T12:00:00Z",
        reviewed_at_b="2026-07-26T13:00:00Z",
        expected_corpus=corpus,
    )
    assert not rep.ok
    assert any("empty reason" in e for e in rep.errors)


def test_import_cli_requires_expected_corpus(tmp_path):
    records = [_candidate("A1")]
    pa, pb, _corpus = _fill_packages(records, tmp_path)
    with pytest.raises(SystemExit):
        main(
            [
                "import",
                "--package-a",
                str(pa),
                "--package-b",
                str(pb),
                "--reviewer-a-id",
                "tiago",
                "--reviewer-b-id",
                "reviewer2",
                "--reviewed-at-a",
                "2026-07-26T12:00:00Z",
                "--reviewed-at-b",
                "2026-07-26T13:00:00Z",
            ]
        )


def test_import_ok_with_expected_corpus_immutable_match(tmp_path):
    records = [_candidate("A1"), _candidate("A2")]
    pa, pb, corpus = _fill_packages(records, tmp_path)
    rep = import_human_labels(
        package_a=pa,
        package_b=pb,
        reviewer_a_id="tiago",
        reviewer_b_id="reviewer2",
        reviewed_at_a="2026-07-26T12:00:00Z",
        reviewed_at_b="2026-07-26T13:00:00Z",
        expected_corpus=corpus,
    )
    assert rep.ok, rep.errors
    assert len(rep.records) == 2
    assert all(r["label_authority"] == "human_dual_independent" for r in rep.records)
    assert set(IMMUTABLE_FIELDS)  # constant exported
