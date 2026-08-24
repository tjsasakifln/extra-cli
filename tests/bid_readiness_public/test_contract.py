"""Drive shipped validators, forbidden scan, PII scan, and SELECT-only guard."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.bid_readiness_public.adapters import make_finding
from scripts.bid_readiness_public.export import READ_MODEL_SQL, consumer_read_model
from scripts.bid_readiness_public.forbidden import scan_forbidden_claims, scan_payload
from scripts.bid_readiness_public.hashing import attach_hash
from scripts.bid_readiness_public.models import INTERPRETIVE_LIMIT
from scripts.bid_readiness_public.pii import scan_payload_for_pii, scan_text_for_pii
from scripts.bid_readiness_public.select_guard import assert_select_only, scan_paths_for_writes
from scripts.bid_readiness_public.validators import (
    EnvelopeValidationError,
    refuse_envelope,
    refuse_finding,
    validate_envelope,
    validate_finding,
)


def _base_finding(**overrides: object) -> dict:
    finding = {
        "finding_id": "F-0001",
        "requirement_id": "REQ-1",
        "category": "edital",
        "state": "FACT",
        "statement": "Text extracted from page 1 of the supplied edital fixture.",
        "source_document_id": "edital:edital.txt",
        "locator": {"page": 1, "section": "objeto", "cell": None, "sheet": None, "paragraph": None},
        "evidence_hash": "a" * 64,
        "evidence_ref": "sha256:fixture",
        "confidence": 0.8,
        "coverage": {"evaluated": 1, "denominator": 1, "ratio": 1.0},
        "reason_codes": ["edital_extracted"],
        "contradiction_links": [],
        "interpretive_limit": INTERPRETIVE_LIMIT,
        "human_review_required": True,
    }
    finding.update(overrides)
    return finding


def test_fact_without_evidence_hash_is_refused() -> None:
    finding = _base_finding(evidence_hash="")
    errors = validate_finding(finding)
    assert "fact_without_evidence_hash" in errors
    with pytest.raises(EnvelopeValidationError, match="fact_without_evidence_hash"):
        refuse_finding(finding)


def test_fact_without_locator_is_refused() -> None:
    finding = _base_finding(locator={"page": None, "section": None, "cell": None, "sheet": None})
    errors = validate_finding(finding)
    assert "fact_without_locator" in errors
    with pytest.raises(EnvelopeValidationError, match="fact_without_locator"):
        refuse_finding(finding)


def test_make_finding_without_locator_degrades_from_fact() -> None:
    finding = make_finding(
        finding_id="F-LOC",
        requirement_id="REQ-1",
        category="bid",
        state="FACT",
        statement="Would-be fact without locator.",
        source_document_id="doc-1",
        locator={"page": None, "section": None, "cell": None, "sheet": None},
        evidence_hash="b" * 64,
        evidence_ref="ref",
        confidence=0.5,
        coverage={"evaluated": 1, "denominator": 1, "ratio": 1.0},
        reason_codes=["requirement_supported"],
    )
    assert finding["state"] == "UNKNOWN"
    assert "locator_missing" in finding["reason_codes"]


def test_risk_without_method_is_refused() -> None:
    finding = _base_finding(
        state="RISK",
        statement="Arithmetic divergence under quantity times unit price.",
        method=None,
    )
    finding.pop("method", None)
    finding.pop("rule", None)
    errors = validate_finding(finding)
    assert "risk_without_method" in errors
    with pytest.raises(EnvelopeValidationError, match="risk_without_method"):
        refuse_finding(finding)


def test_forbidden_claims_are_detected() -> None:
    hits = scan_forbidden_claims("empresa habilitada no certame")
    assert hits
    hits = scan_payload({"statement": "parecer juridico autonomo"})
    assert hits


def test_fictional_cnpj_is_not_pii_and_email_is() -> None:
    assert scan_text_for_pii("CNPJ 12.345.678/0001-99") == []
    email_hits = scan_payload_for_pii({"n": "contato@empresa.com"})
    assert email_hits
    assert any(hit.startswith("email:") for hit in email_hits)


def test_consumer_sql_is_select_only() -> None:
    assert "SELECT" in assert_select_only(READ_MODEL_SQL)
    with pytest.raises(ValueError, match="write_sql"):
        assert_select_only("DELETE FROM envelopes")
    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "exports"
        / "public-read-bid-readiness"
        / "1.0"
        / "fixture.public.json"
    )
    import json

    model = consumer_read_model(json.loads(fixture_path.read_text(encoding="utf-8")))
    assert model["select_only"] is True
    assert model["page_authorized"] is False
    assert model["publication_authorization"] is False
    assert model["index_authorization"] is False


def test_envelope_content_hash_is_verified() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "exports"
        / "public-read-bid-readiness"
        / "1.0"
        / "fixture.public.json"
    )
    import json

    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert "content_hash_mismatch" not in validate_envelope(payload)
    tampered = {**payload, "overall_state": "REJECT"}
    assert "content_hash_mismatch" in validate_envelope(tampered)
    with pytest.raises(EnvelopeValidationError, match="content_hash_mismatch"):
        refuse_envelope(tampered)

    repaired = attach_hash(tampered)
    refuse_envelope(repaired)


def test_malformed_envelope_shapes_are_refused_without_crashing() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "exports"
        / "public-read-bid-readiness"
        / "1.0"
        / "fixture.public.json"
    )
    import json

    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    malformed = attach_hash({**payload, "input_manifest": "not-an-object", "findings": ["not-an-object"]})
    errors = validate_envelope(malformed)
    assert "input_manifest" in errors
    assert "findings[0].not_object" in errors
    with pytest.raises(EnvelopeValidationError):
        refuse_envelope(malformed)


def test_exclusive_area_has_no_write_sql_or_crawler() -> None:
    root = Path(__file__).resolve().parents[2]
    hits = scan_paths_for_writes(root / "scripts" / "bid_readiness_public")
    assert hits == []
    export_root = root / "exports" / "public-read-bid-readiness"
    if export_root.is_dir():
        assert scan_paths_for_writes(export_root) == []
