"""Tests for CIGA/DOM-SC public discovery (#239)."""

from __future__ import annotations

import io
import zipfile

import pytest

from scripts.crawl.ciga_public_discovery import (
    classify_http,
    detect_mime,
    discovery_report,
    fetch_public,
    invalidate_checkpoint,
    page_evidence,
    period_covers,
    reconcile_municipalities,
    resolve_package,
    safe_extract_zip,
    sha256_bytes,
)


def test_slug_drift_falls_back_to_public_search_then_show() -> None:
    calls: list[str] = []

    def http(url: str) -> tuple[int, bytes, str]:
        calls.append(url)
        if "package_show?id=dom-sc-publicacoes-de-07-2026" in url:
            return 404, b"missing", "2026-08-13T00:00:00Z"
        if "package_search" in url:
            return 200, b'{"success":true}', "2026-08-13T00:00:00Z"
        if "package_show?id=domsc-publicacoes-de-07-2026" in url:
            return 200, b'{"success":true}', "2026-08-13T00:00:00Z"
        return 404, b"", "2026-08-13T00:00:00Z"

    resolved = resolve_package("dom-sc-publicacoes-de-07-2026", http=http)
    assert resolved["ok"] is True
    assert resolved["via"] == "search+show"
    assert resolved["slug"] == "domsc-publicacoes-de-07-2026"
    assert resolved["drift_alert"] is True
    assert any("package_search" in u for u in calls)


def test_404_is_drift_and_429_is_retryable() -> None:
    retryable, drift = classify_http(404)
    assert drift is True
    assert retryable is False
    retryable, drift = classify_http(429)
    assert retryable is True
    assert drift is False
    retryable, drift = classify_http(503)
    assert retryable is True


def test_missing_municipality_is_not_zero_without_complete_scope() -> None:
    universe = {"Abelardo Luz", "Florianopolis"}
    found = {"Florianopolis"}
    incomplete = reconcile_municipalities(found, universe, scope_complete=False)
    by_name = {v.municipio: v.status for v in incomplete}
    assert by_name["Florianopolis"] == "FOUND"
    assert by_name["Abelardo Luz"] == "SCOPE_INCOMPLETE"
    complete = reconcile_municipalities(found, universe, scope_complete=True)
    by_name = {v.municipio: v.status for v in complete}
    assert by_name["Abelardo Luz"] == "ZERO_CONFIRMED"


def test_zip_slip_and_bomb_fail_closed() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../etc/passwd", "nope")
    with pytest.raises(ValueError, match="zip_slip"):
        safe_extract_zip(buffer.getvalue())

    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w") as archive:
        for i in range(5):
            archive.writestr(f"f{i}.txt", "x" * 10)
    with pytest.raises(ValueError, match="zip_bomb_too_many_members"):
        safe_extract_zip(bomb.getvalue(), max_members=2)
    with pytest.raises(ValueError, match="mime_mismatch"):
        safe_extract_zip(b"%PDF-1.4 not-a-zip", declared_mime="application/zip")
    assert detect_mime(bomb.getvalue()) == "application/zip"


def test_page_evidence_has_raw_uri_and_sha256() -> None:
    def http(url: str) -> tuple[int, bytes, str]:
        return 200, b"payload-bytes", "2026-08-13T12:00:00Z"

    outcome = fetch_public("https://dados.ciga.sc.gov.br/dataset/x", http)
    evidence = page_evidence(outcome, raw_uri="cas://ciga/" + sha256_bytes(b"payload-bytes"))
    assert evidence.status == 200
    assert evidence.sha256 == sha256_bytes(b"payload-bytes")
    assert evidence.raw_uri.startswith("cas://")
    assert evidence.fetched_at.endswith("Z")


def test_period_covers_2025_and_report_forbids_silent_zero() -> None:
    assert period_covers("2024-12-01", "2026-08-13") is True
    report = discovery_report(
        resolved={"ok": False, "drift_alert": True},
        verdicts=reconcile_municipalities(set(), {"A"}, scope_complete=False),
        pages=[],
    )
    assert report["silent_zero_forbidden"] is False
    assert report["municipalities"][0]["status"] == "SCOPE_INCOMPLETE"
    assert report["sla_hours"] == 24
    assert invalidate_checkpoint("aaa", "bbb") == "invalidate"
    drifted = discovery_report(
        resolved={"ok": True},
        verdicts=[],
        pages=[],
        previous_snapshot_hash="old",
        current_snapshot_hash="new",
    )
    assert drifted["checkpoint"] == "invalidate"
