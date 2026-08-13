"""Crawler SSRF, archive limits and systemd sandbox contracts."""

from __future__ import annotations

import os
import socket
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.crawl.security import validate_public_url, validate_redirect_chain
from scripts.ops.validate_crawler_runtime_security import (
    MINIMUM_SCORE,
    unit_hardening_score,
    validate_environment_file,
)
from scripts.process_documents import storage
from scripts.source_registry.continuous_inventory import (
    CoverageAttempt,
    SurfaceObservation,
    classify_surface,
    finalize_discovery_run,
    record_coverage_attempt,
)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://localhost/admin",
        "https://127.0.0.1/admin",
        "https://10.0.0.1/admin",
        "https://169.254.169.254/latest/meta-data",
        "https://[::1]/admin",
        "https://public.example/a/%2e%2e/private",
    ],
)
def test_public_url_guard_rejects_ssrf_and_traversal(url: str) -> None:
    with pytest.raises(ValueError):
        validate_public_url(url, resolve_dns=False)


def test_public_url_guard_rejects_private_dns_and_redirect() -> None:
    private_dns = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.10", 443))]
    with patch("socket.getaddrinfo", return_value=private_dns):
        with pytest.raises(ValueError, match="non-public"):
            validate_public_url("https://public.example/path")

    class Redirect:
        url = "https://127.0.0.1/internal"
        history: list[object] = []

    with pytest.raises(ValueError, match="non-public"):
        validate_redirect_chain(Redirect())


def test_pdf_limits_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(storage, "MAX_PDF_BYTES", 32)
    with pytest.raises(ValueError, match="MAX_PDF_BYTES"):
        storage.validate_pdf_limits(b"%PDF" + b"x" * 40)

    monkeypatch.setattr(storage, "MAX_PDF_BYTES", 10_000)
    monkeypatch.setattr(storage, "MAX_PDF_PAGES", 2)
    with pytest.raises(ValueError, match="MAX_PDF_PAGES"):
        storage.validate_pdf_limits(b"%PDF /Type /Page /Type /Page /Type /Page")


def test_crawler_units_meet_documented_static_threshold() -> None:
    for name in ("extra-crawl-scheduler.service", "extra-crawl-worker@.service"):
        result = unit_hardening_score(Path("deploy/systemd") / name)
        assert result["score"] >= MINIMUM_SCORE
        assert result["passed"] is True


def test_environment_file_must_be_mode_0600(tmp_path: Path) -> None:
    path = tmp_path / "crawler.env"
    path.write_text("LOCAL_DATALAKE_DSN=postgresql://redacted\n", encoding="utf-8")
    path.chmod(0o640)
    assert validate_environment_file(path, expected_uid=os.geteuid())["passed"] is False
    path.chmod(0o600)
    assert validate_environment_file(path, expected_uid=os.geteuid())["passed"] is True


def test_discovery_classifies_new_domain_block_and_exhaustion() -> None:
    unknown = classify_surface(
        SurfaceObservation(
            kind="procurement",
            canonical_url="https://new-vendor.example/bids",
            platform=None,
            anchor_url="https://entity.example",
            method="anchor",
            http_status=200,
        ),
        known_domains={"pncp.gov.br"},
    )
    blocked = classify_surface(
        SurfaceObservation(
            kind="transparency",
            canonical_url="https://portal.example/login",
            platform="vendor",
            anchor_url=None,
            method="probe",
            http_status=403,
        ),
        known_domains={"portal.example"},
    )
    exhausted = classify_surface(
        SurfaceObservation(
            kind="gazette",
            canonical_url=None,
            platform=None,
            anchor_url=None,
            method="exhaustive_search",
        ),
        known_domains=set(),
    )
    assert unknown[0] == "UNCLASSIFIED"
    assert blocked[0] == "BLOCKED"
    assert exhausted[0] == "DISCOVERY_EXHAUSTED_NO_SURFACE"


def test_zero_confirmed_never_accepts_absence_of_execution() -> None:
    now = datetime.now(UTC)
    attempt = CoverageAttempt(
        universe_run_id=1,
        canonical_entity_key="entity",
        entity_id=1,
        source="pncp",
        capability="open_tenders",
        status="ZERO_CONFIRMED",
        applicability=True,
        applicability_reason="rule",
        canonical_url="https://pncp.gov.br",
        checked_at=now,
        http_statuses=[],
        pages_fetched=0,
        pages_expected=None,
        records_observed=0,
        request_completed=False,
        scope_complete=False,
        pagination_reconciled=False,
        raw_uri=None,
        raw_sha256=None,
        freshness_deadline=now,
        next_action="retry",
        next_check_at=now,
    )
    with pytest.raises(ValueError, match="complete reconciled request"):
        record_coverage_attempt(object(), attempt)


def test_partial_discovery_run_closes_without_claiming_audit() -> None:
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.fetchone.side_effect = [
        {"universe_run_id": 7, "mode": "stratified_pilot", "expected_entity_count": 30},
        {"complete_entities": 0},
    ]
    cursor.fetchall.return_value = [{"canonical_entity_key": "only-one"}]
    connection = MagicMock()
    connection.cursor.return_value = cursor

    result = finalize_discovery_run(connection, 42, audited=True)

    assert result["outcome"] == "partial"
    assert result["entity_count"] == 1
    assert result["completion_errors"]
    update = [call for call in cursor.execute.call_args_list if "UPDATE discovery_runs" in call.args[0]]
    assert len(update) == 1
    assert update[0].args[1][2:] == (False, "partial", 42)


def test_discovery_schema_models_terminal_partial_outcome() -> None:
    sql = Path("db/migrations/082_public_surface_coverage.sql").read_text(encoding="utf-8")
    assert "outcome IN ('complete', 'partial', 'aborted')" in sql
    assert "outcome <> 'complete' OR observed_entity_count = expected_entity_count" in sql
