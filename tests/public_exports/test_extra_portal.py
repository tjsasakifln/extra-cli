import json
import stat
from datetime import UTC, date, datetime

import pytest

from scripts.public_exports.extra_portal import (
    assess_scan,
    encoded,
    official_url,
    parse_register,
    record_fingerprint,
    write_snapshot,
)

NOTICE = "12345678000199-1-002371/2026"
CONTRACT = "12345678000199-2-000001/2026"
STAMP = datetime(2026, 11, 26, 11, tzinfo=UTC)
EVIDENCE = {"kind": "projeto", "sha256": "f" * 64, "url": "https://pncp.gov.br/app/documentos/1", "locator": "p. 4"}


def raw(key=NOTICE, **fields):
    return {
        "key": key, "title": "Implantação de drenagem em São José/SC", "buyer": "Entidade",
        "buyer_key": "12345678000199", "buyer_uf": "SC", "buyer_city": "São José",
        "state": "open", "is_active": True, "source_active": True, "content_hash": "123",
        "opens_at": STAMP, "closes_at": STAMP, "status_verified_at": STAMP,
        **fields,
    }


def reviewed(row, kind="notice", **fields):
    return {
        "key": row["key"], "kind": kind, "fingerprint": record_fingerprint(row, kind),
        "decision": "verified", "reviewer": "operador-para-teste", "physicalWork": True, "family": "saneamento",
        "scopeEvidence": EVIDENCE, "statusEvidence": EVIDENCE,
        "execution": {"basis": "all_execution_sites", "sites": [{"code": "4216602", "evidence": EVIDENCE}]},
        **fields,
    }


def test_geography_and_keywords_create_review_work_never_positive_or_negative():
    strong = raw()
    subtle = raw("12345678000199-1-000002/2026", title="Implantação de estação elevatória")
    purchase = raw("12345678000199-1-000003/2026", title="Aquisição de material de construção")
    result, missed, queue = assess_scan([subtle, strong, purchase], {}, "notice", [])
    assert result == []
    assert missed == 3
    assert len({item["key"] for item in queue}) == 3
    assert queue[0]["workHint"] is True
    assert next(item for item in queue if item["key"] == subtle["key"])["workHint"] is False


def test_review_is_bound_to_identity_and_exact_source_revision():
    row = raw()
    proof = reviewed(row)
    assert not assess_scan([row], {NOTICE: proof}, "notice", [])[0]
    assert not assess_scan([row], {NOTICE: proof}, "notice", [row, row])[0]
    current = raw(content_hash="new")
    observed = assess_scan([current], {NOTICE: proof}, "notice", [current])
    assert observed[:2] == ([], 1)
    assert observed[2][0]["reason"] == "source_changed"
    accepts, _, _ = assess_scan([row], {NOTICE: proof}, "notice", [row])
    assert len(accepts) == 1
    assert accepts[0]["execution"]["sites"][0]["code"] == "4216602"
    output = encoded(accepts)
    assert b"operador-para-teste" not in output
    another = raw(status_verified_at=datetime(2026, 11, 26, 12, tzinfo=UTC), source_active=False)
    not_open, _, _ = assess_scan([another], {NOTICE: proof}, "notice", [another])
    assert not_open[0]["notice"]["state"] == "unconfirmed"


def test_unknown_or_invalid_contracts_are_not_erased_from_discovery():
    row = raw(CONTRACT, published_on=date(2026, 10, 11), ends_on=date(2027, 10, 1),
              state="ACTIVE_PROVEN", quality_state="UNKNOWN", contractor="Empresa Exemplo")
    projection, unreviewed, queue = assess_scan([row], {CONTRACT: reviewed(row, "contract")}, "contract", [row])
    assert projection == []
    assert unreviewed == 1
    assert queue[0]["reason"] == "missing_source_fields"
    supported = {**row, "quality_state": "VALID"}
    projection, unreviewed, queue = assess_scan([supported], {CONTRACT: reviewed(supported, "contract")},
                                               "contract", [supported])
    assert unreviewed == 0
    assert queue == []
    assert projection[0]["contract"]["amount"] is None


def test_rejecting_and_duplicate_review_require_unambiguous_evidence():
    row = raw()
    with pytest.raises(ValueError):
        parse_register({"schema": "extra-portal-review/v1", "reviews": [
            reviewed(row, decision="exclude", reason="unknown", scopeEvidence=None),
        ]})
    with pytest.raises(ValueError):
        parse_register({"schema": "extra-portal-review/v1", "reviews": [reviewed(row), reviewed(row)]})
    assert official_url(CONTRACT, "notice") is None
    assert official_url("https://malicious.invalid", "contract") is None
    assert official_url(CONTRACT, "contract") == "https://pncp.gov.br/app/contratos/12345678000199/2026/1"


def test_atomic_export_never_truncates_last_snapshot_on_failure(tmp_path):
    path = tmp_path / "current.json"
    write_snapshot(path, {"stamp": STAMP, "valid": True})
    assert json.loads(path.read_text()) == {"stamp": "2026-11-26T11:00:00.000Z", "valid": True}
    assert stat.S_IMODE(path.stat().st_mode) == 0o440
    previous = path.stat().st_ino
    with pytest.raises(ValueError):
        write_snapshot(path, {"data": "x" * (2 * 1024 * 1024)})
    assert path.stat().st_ino == previous
    assert list(tmp_path.iterdir()) == [path]
