"""Open opportunity status — never treat closed history as open."""

from __future__ import annotations

from datetime import date

from scripts.pseo.opportunities import classify_bid_status, filter_open_bids, radar_freshness


def test_closed_by_date():
    d = classify_bid_status(
        {"data_encerramento": "2026-07-10", "objeto": "obra"},
        as_of=date(2026, 7, 31),
    )
    assert d["is_open"] is False
    assert d["status_bucket"] == "encerrada"


def test_open_by_future_date():
    d = classify_bid_status(
        {"data_encerramento": "2026-08-15", "objeto": "obra"},
        as_of=date(2026, 7, 31),
    )
    assert d["is_open"] is True
    assert d["status_bucket"] == "aberta"


def test_revoked_not_open():
    d = classify_bid_status(
        {"data_encerramento": "2026-08-15", "situacao": "revogada"},
        as_of=date(2026, 7, 31),
    )
    assert d["is_open"] is False
    assert d["status_bucket"] == "revogada"


def test_suspended_not_open():
    d = classify_bid_status(
        {"data_encerramento": "2026-08-15", "status": "suspensa"},
        as_of=date(2026, 7, 31),
    )
    assert d["is_open"] is False
    assert d["status_bucket"] == "suspensa"


def test_filter_counts_do_not_mix_history():
    bids = [
        {"data_encerramento": "2026-08-20", "objeto": "a", "uf": "SC"},
        {"data_encerramento": "2026-07-01", "objeto": "b", "uf": "SC"},
        {"data_encerramento": "2026-08-10", "situacao": "anulada", "objeto": "c", "uf": "SC"},
    ]
    open_b, closed_b, counts = filter_open_bids(bids, as_of=date(2026, 7, 31))
    assert len(open_b) == 1
    assert counts["open_total"] == 1
    assert counts["closed_total"] == 2


def test_radar_freshness_fail():
    r = radar_freshness("2026-07-20", now=date(2026, 7, 31))
    assert r["status"] == "fail"
    r2 = radar_freshness("2026-07-31", now=date(2026, 7, 31))
    assert r2["status"] == "ok"
