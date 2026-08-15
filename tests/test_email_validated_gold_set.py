"""Gold-set inventory: schema, n≥50, splits, evidence, declared skew."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.decision_unit_intelligence.email_validated.gold_cases_v1 import SKEW, build_gold_cases
from scripts.decision_unit_intelligence.email_validated.schema import (
    GOLD_SET_VERSION,
    HUMAN_VERDICTS,
    REQUIRED_RECORD_FIELDS,
    load_jsonl,
    validate_record,
)

GOLD_PATH = Path("evals/email_validated/gold/gold-set.v1.jsonl")
META_PATH = Path("evals/email_validated/gold/gold-set.v1.meta.json")
SPLITS_PATH = Path("evals/email_validated/gold/splits.json")


def test_shipped_gold_set_meets_inventory_contract():
    assert GOLD_PATH.is_file()
    records = load_jsonl(GOLD_PATH)
    authored = build_gold_cases()
    assert len(records) >= 50
    assert len(records) == len(authored)
    assert {item.case_id for item in records} == {item.case_id for item in authored}
    present = {item.human_verdict for item in records}
    missing = [verdict for verdict in HUMAN_VERDICTS if verdict not in present]
    for verdict in missing:
        assert verdict in SKEW, f"{verdict} missing from gold set and from skew declaration"
        assert SKEW[verdict]["count"] == 0
    for record in records:
        errors = validate_record(record)
        assert not errors, (record.case_id, errors)
        payload = record.to_dict()
        for field in REQUIRED_RECORD_FIELDS:
            assert field in payload
        assert record.gold_set_version == GOLD_SET_VERSION
        assert record.has_provenance()
        assert record.split in {"development", "holdout"}
        pack = record.evidence_pack()
        assert "person_name" in pack
        assert "company" in pack
        assert "source_url" in pack or "frozen_evidence" in pack
        assert payload["auto_send"] is False
        assert payload["gold_label_is_not_send_authorization"] is True


def test_holdout_is_disjoint_from_development():
    records = load_jsonl(GOLD_PATH)
    development = {item.case_id for item in records if item.split == "development"}
    holdout = {item.case_id for item in records if item.split == "holdout"}
    assert development
    assert holdout
    assert development.isdisjoint(holdout)
    splits = json.loads(SPLITS_PATH.read_text(encoding="utf-8"))
    assert set(splits["development"]) == development
    assert set(splits["holdout"]) == holdout
    assert splits["disjoint"] is True


def test_meta_declares_version_and_skew():
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    assert meta["gold_set_version"] == GOLD_SET_VERSION
    assert meta["n"] >= 50
    assert meta["auto_send"] is False
    assert meta["human_review_approved"] is False
    assert "VALIDATED_DIRECT" in meta["skew"]
    assert meta["skew"]["VALIDATED_DIRECT"]["count"] == 0
    assert meta["by_human_verdict"].get("VALIDATED_DIRECT", 0) == 0
