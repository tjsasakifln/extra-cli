"""Last-known-good policy on the shipped evaluator."""

from __future__ import annotations

from scripts.national_claims.gate import decide
from scripts.national_claims.lkg import (
    LKG_INVALIDATED,
    LKG_NOT_AUTHORIZED,
    evaluate_lkg,
    make_lkg,
)
from scripts.national_claims.loader import request_from_dict
from scripts.national_claims.models import LkgRecord
from scripts.national_claims.sample_fixtures import fixture_authorized_national, fixture_stale_lkg


def test_lkg_only_after_authorized() -> None:
    request = request_from_dict(fixture_authorized_national())
    prior = LkgRecord(
        claim_id="prior-needs",
        authorization_state="NEEDS_DATA",
        national_universe_id=request.universes.national.universe_id,
        catalog_hash=request.universes.national.catalog_hash,
        method_version=request.universes.national.method_version,
        source_version="pncp/1.0",
        content_hash="abc",
        authorized_at="2026-08-14T00:00:00Z",
        expires_at="2026-08-16T00:00:00Z",
    )
    status, triggers, record = evaluate_lkg(
        prior,
        current_universe=request.universes.national,
        source_version="pncp/1.0",
        as_of="2026-08-15T00:00:00Z",
    )
    assert status == LKG_NOT_AUTHORIZED
    assert record is None
    assert "lkg_requires_prior_authorized" in triggers


def test_universe_change_invalidates_lkg() -> None:
    request = request_from_dict(fixture_authorized_national())
    prior = make_lkg(
        claim_id="prior",
        national_universe_id=request.universes.national.universe_id,
        catalog_hash="0" * 64,
        method_version=request.universes.national.method_version,
        source_version="pncp/1.0",
        content_hash="abc",
        authorized_at="2026-08-14T00:00:00Z",
    )
    status, triggers, record = evaluate_lkg(
        prior,
        current_universe=request.universes.national,
        source_version="pncp/1.0",
        as_of="2026-08-15T00:00:00Z",
    )
    assert status == LKG_INVALIDATED
    assert "universe_hash_change" in triggers
    assert record is not None
    assert record.claim_id == "prior"


def test_method_change_invalidates_lkg() -> None:
    request = request_from_dict(fixture_authorized_national())
    prior = make_lkg(
        claim_id="prior",
        national_universe_id=request.universes.national.universe_id,
        catalog_hash=request.universes.national.catalog_hash,
        method_version="old-method",
        source_version="pncp/1.0",
        content_hash="abc",
        authorized_at="2026-08-14T00:00:00Z",
    )
    status, triggers, _record = evaluate_lkg(
        prior,
        current_universe=request.universes.national,
        source_version="pncp/1.0",
        as_of="2026-08-15T00:00:00Z",
    )
    assert status == LKG_INVALIDATED
    assert "method_version_change" in triggers


def test_expired_lkg_does_not_authorize_current() -> None:
    document = fixture_stale_lkg()
    document["prior_lkg"]["expires_at"] = "2026-08-14T12:00:00Z"
    payload = decide(request_from_dict(document))
    assert payload["authorization_state"] == "STALE"
    assert payload["consumer_view"] == "blocked"
    assert "lkg_expired" in payload["reason_codes"]
    assert payload["nacional_completo"] is False
