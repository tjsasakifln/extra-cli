"""Committed public fixture is redacted, SELECT-only, and does not authorize a page."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.bid_readiness_public.forbidden import scan_payload
from scripts.bid_readiness_public.hashing import content_hash
from scripts.bid_readiness_public.pii import scan_payload_for_pii, scan_text_for_pii
from scripts.bid_readiness_public.redaction import public_envelope
from scripts.bid_readiness_public.select_guard import assert_select_only, scan_paths_for_writes
from scripts.bid_readiness_public.validators import EnvelopeValidationError

ROOT = Path(__file__).resolve().parents[2]
EXPORT = ROOT / "exports" / "public-read-bid-readiness" / "1.0"


def test_committed_public_fixture_is_redacted_and_unauthorized() -> None:
    payload = json.loads((EXPORT / "fixture.public.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "public-read-bid-readiness/1.0"
    assert payload["source_access"] == "redacted_fixture"
    assert payload["publication_authorization"] is False
    assert payload["index_authorization"] is False
    assert payload["human_review_required"] is True
    assert payload["not_legal_conclusion"] is True
    assert payload["overall_state"] in {"READY_FOR_HUMAN_REVIEW", "HOLD_FOR_DATA", "REJECT"}
    body = {key: value for key, value in payload.items() if key != "content_hash"}
    assert payload["content_hash"] == content_hash(body)
    assert scan_payload(payload) == []
    assert scan_payload_for_pii(payload) == []
    for path in EXPORT.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".sql", ".md"}:
            assert scan_text_for_pii(path.read_text(encoding="utf-8")) == []


def test_committed_sql_is_select_only_and_area_has_no_writes() -> None:
    sql = (EXPORT / "web-cfg-155-read-model.sql").read_text(encoding="utf-8")
    assert_select_only(sql)
    model = json.loads((EXPORT / "web-cfg-155-read-model.json").read_text(encoding="utf-8"))
    assert model["select_only"] is True
    assert model["page_authorized"] is False
    assert model["publication_authorization"] is False
    assert model["index_authorization"] is False
    assert scan_paths_for_writes(EXPORT) == []
    assert scan_paths_for_writes(ROOT / "scripts" / "bid_readiness_public") == []


def test_public_envelope_refuses_private_source_and_is_idempotent_for_fixture() -> None:
    payload = json.loads((EXPORT / "fixture.public.json").read_text(encoding="utf-8"))
    private_like = {**payload, "source_access": "private_local"}
    private_like.pop("content_hash", None)
    from scripts.bid_readiness_public.hashing import attach_hash

    private = attach_hash(private_like)
    with pytest.raises(EnvelopeValidationError, match="public_export_requires_redacted_fixture"):
        public_envelope(private)
    public = public_envelope(payload)
    public_body = {key: value for key, value in public.items() if key != "content_hash"}
    assert public["source_access"] == "redacted_fixture"
    assert public["content_hash"] == content_hash(public_body)
    assert public["content_hash"] == payload["content_hash"]
