"""HMAC accept/reject, skew, size, idempotency, no auto-WON."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from scripts.warmbly_bridge.hmac_sig import redact_for_log, sign_outcome_hmac, verify_outcome_hmac
from scripts.warmbly_bridge.outcome_mapping import OutcomeValidationError, build_outcome_record_input
from scripts.warmbly_bridge.persist import InMemoryOutcomeStore, persist_outcome
from scripts.warmbly_bridge.receptor import ReceptorConfig, process_outcome_request

SECRET = "test-warmbly-secret-not-for-prod"


@pytest.fixture
def contacted_body(outcome_fixture: Path) -> bytes:
    return outcome_fixture.read_bytes()


def test_sign_and_verify_roundtrip(contacted_body: bytes) -> None:
    ts = int(time.time())
    header = sign_outcome_hmac(SECRET, ts, contacted_body)
    ok, reason = verify_outcome_hmac(SECRET, header, contacted_body, now=float(ts))
    assert ok is True
    assert reason == ""


def test_bad_signature_rejected(contacted_body: bytes) -> None:
    ts = int(time.time())
    header = sign_outcome_hmac(SECRET, ts, contacted_body)
    # tamper
    bad = header[:-4] + "dead"
    ok, reason = verify_outcome_hmac(SECRET, bad, contacted_body, now=float(ts))
    assert ok is False
    assert reason == "bad_signature"


def test_skew_rejected(contacted_body: bytes) -> None:
    ts = int(time.time()) - 10_000
    header = sign_outcome_hmac(SECRET, ts, contacted_body)
    ok, reason = verify_outcome_hmac(
        SECRET, header, contacted_body, now=time.time(), max_skew_seconds=300
    )
    assert ok is False
    assert reason.startswith("timestamp_skew")


def test_process_valid_hmac_persists_once(contacted_body: bytes) -> None:
    store = InMemoryOutcomeStore()
    config = ReceptorConfig(secret=SECRET, store=store, client_id="confenge")
    ts = int(time.time())
    header = sign_outcome_hmac(SECRET, ts, contacted_body)
    status, payload = process_outcome_request(
        body=contacted_body, signature_header=header, config=config, now=float(ts)
    )
    assert status == 200
    assert payload["ok"] is True
    assert payload["created"] is True
    assert len(store.rows) == 1

    # replay same idempotency key
    status2, payload2 = process_outcome_request(
        body=contacted_body, signature_header=header, config=config, now=float(ts)
    )
    assert status2 == 200
    assert payload2["created"] is False
    assert payload2["status"] == "duplicate"
    assert len(store.rows) == 1


def test_bad_sig_no_persist(contacted_body: bytes) -> None:
    store = InMemoryOutcomeStore()
    config = ReceptorConfig(secret=SECRET, store=store, client_id="confenge")
    status, payload = process_outcome_request(
        body=contacted_body,
        signature_header="t=1,v1=00",
        config=config,
        now=time.time(),
    )
    assert status == 401
    assert payload["ok"] is False
    assert store.rows == []


def test_oversize_rejected(contacted_body: bytes) -> None:
    store = InMemoryOutcomeStore()
    config = ReceptorConfig(secret=SECRET, store=store, client_id="confenge", max_body_bytes=10)
    ts = int(time.time())
    header = sign_outcome_hmac(SECRET, ts, contacted_body)
    status, payload = process_outcome_request(
        body=contacted_body, signature_header=header, config=config, now=float(ts)
    )
    assert status == 413
    assert store.rows == []
    assert payload["error"] == "payload_too_large"


def test_won_machine_only_rejected() -> None:
    envelope = {
        "schema_version": "confenge.outcome.v1",
        "event_id": "evt-won-1",
        "idempotency_key": "won-machine-1",
        "occurred_at": "2026-08-06T16:00:00Z",
        "source": "warmbly",
        "source_lead_id": "lead-acme-sc",
        "cnpj14": "11222333000181",
        "event_type": "WON",
        "metadata": {"classifier": "auto_reply_class"},
    }
    with pytest.raises(OutcomeValidationError, match="WON rejected"):
        build_outcome_record_input(envelope, client_id="confenge")


def test_won_human_confirmed_accepted() -> None:
    envelope = {
        "schema_version": "confenge.outcome.v1",
        "event_id": "evt-won-2",
        "idempotency_key": "won-human-1",
        "occurred_at": "2026-08-06T16:00:00Z",
        "source": "warmbly",
        "source_lead_id": "lead-acme-sc",
        "cnpj14": "11222333000181",
        "event_type": "WON",
        "metadata": {"human_confirmed": True, "actor_type": "human"},
    }
    store = InMemoryOutcomeStore()
    result = persist_outcome(envelope, store=store, client_id="confenge")
    assert result["created"] is True
    assert result["dm_outcome_type"] == "WIN"
    assert store.rows[0]["structured_facts"]["won_human_confirmed"] is True


def test_aliases_dnc_bounce_sent() -> None:
    store = InMemoryOutcomeStore()
    for etype, expected_dm in (
        ("DNC", "NO_PARTICIPATION"),
        ("BOUNCE", "INCIDENT"),
        ("SENT", "UNKNOWN"),
        ("REVIEWED", "UNKNOWN"),
    ):
        env = {
            "schema_version": "confenge.outcome.v1",
            "event_id": f"e-{etype}",
            "idempotency_key": f"k-{etype}",
            "occurred_at": "2026-08-06T16:00:00Z",
            "source": "warmbly",
            "cnpj14": "11222333000181",
            "event_type": etype,
            "channel": "email",
        }
        r = persist_outcome(env, store=store, client_id="confenge")
        assert r["dm_outcome_type"] == expected_dm


def test_redaction_hides_email() -> None:
    payload = {
        "contact_email": "secret@example.com",
        "event_type": "CONTACTED",
        "metadata": {"email": "also@example.com"},
    }
    red = redact_for_log(payload)
    assert red["contact_email"] == "[REDACTED]"
    assert red["metadata"]["email"] == "[REDACTED]"


def test_real_receptor_path_with_signature(contacted_body: bytes) -> None:
    """Drive the same process_outcome_request the HTTP handler uses."""
    store = InMemoryOutcomeStore()
    config = ReceptorConfig(secret=SECRET, store=store, client_id="confenge")
    ts = int(time.time())
    header = sign_outcome_hmac(SECRET, ts, contacted_body)
    status, payload = process_outcome_request(
        body=contacted_body, signature_header=header, config=config, now=float(ts)
    )
    assert 200 <= status < 300
    assert payload["idempotency_key"] == json.loads(contacted_body)["idempotency_key"]
    got = store.get_outcome_by_idempotency("confenge", payload["idempotency_key"])
    assert got is not None
