"""Committed public fixture is redacted, SELECT-only, and does not authorize a page."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.bid_readiness_public.forbidden import scan_payload
from scripts.bid_readiness_public.pii import scan_payload_for_pii, scan_text_for_pii
from scripts.bid_readiness_public.select_guard import assert_select_only, scan_paths_for_writes

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
