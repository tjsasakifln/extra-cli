"""Refs #276 — crawler sandbox, archive limits, BLOCKED, redaction, units.

Drives scripts.crawl.sandbox. Live systemd-analyze on the VPS remains residual.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from scripts.crawl.sandbox import (
    blocked_access_reason,
    classify_fetch_outcome,
    environment_file_mode_ok,
    guard_crawler_url,
    redact_crawler_evidence,
    running_as_non_root,
    validate_archive_limits,
    validate_crawler_unit_contract,
    validate_pdf_limits,
)
from scripts.process_documents import storage


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://localhost/admin",
        "https://127.0.0.1/secret",
        "https://10.0.0.8/internal",
        "https://192.168.1.20/x",
        "https://169.254.169.254/latest/meta-data",
        "https://public.example/a/%2e%2e/etc/passwd",
    ],
)
def test_issue_276_blocks_file_localhost_rfc1918_and_traversal(url: str) -> None:
    with pytest.raises(ValueError):
        guard_crawler_url(url, resolve_dns=False)


def test_issue_276_public_https_is_allowed() -> None:
    assert guard_crawler_url("https://pncp.gov.br/api/consulta", resolve_dns=False).startswith("https://")


def test_issue_276_captcha_and_login_are_blocked_never_success() -> None:
    assert blocked_access_reason(status=403, body="ok") == "http_forbidden"
    assert blocked_access_reason(status=200, body="<div class='g-recaptcha'></div>") == "captcha"
    assert blocked_access_reason(status=200, body="Login senha entrar") == "login_wall"
    assert (
        classify_fetch_outcome(
            status=200,
            body="resolva o captcha",
            records=0,
            scope_complete=True,
            pagination_reconciled=True,
        )
        == "BLOCKED"
    )
    assert (
        classify_fetch_outcome(
            status=200,
            body="ok",
            records=0,
            scope_complete=True,
            pagination_reconciled=True,
        )
        == "ZERO"
    )
    assert (
        classify_fetch_outcome(
            status=200,
            body="ok",
            records=0,
            scope_complete=False,
            pagination_reconciled=False,
        )
        == "partial"
    )


def test_issue_276_redacts_dsn_tokens_and_cookies() -> None:
    leaked = (
        "dsn=postgresql://user:supersecret@127.0.0.1:5433/extra_test "
        "Authorization: Bearer abc.def.ghi "
        "Cookie: session=abc123 "
        "token=super-token"
    )
    redacted = redact_crawler_evidence(leaked)
    assert "supersecret" not in redacted
    assert "abc123" not in redacted
    assert "super-token" not in redacted
    assert "postgresql://user:supersecret" not in redacted


def test_issue_276_pdf_and_zip_limits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(storage, "MAX_PDF_BYTES", 32)
    with pytest.raises(ValueError, match="MAX_PDF_BYTES"):
        validate_pdf_limits(b"%PDF" + b"x" * 40)

    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as zf:
        zf.writestr("../etc/passwd", "nope")
    archive = tmp_path / "evil.zip"
    archive.write_bytes(payload.getvalue())
    with pytest.raises(ValueError, match="traversal"):
        validate_archive_limits(archive, tmp_path / "out")


def test_issue_276_units_require_non_root_and_environmentfile_0600(tmp_path: Path) -> None:
    scheduler = Path("deploy/systemd/extra-crawl-scheduler.service").read_text(encoding="utf-8")
    worker = Path("deploy/systemd/extra-crawl-worker@.service").read_text(encoding="utf-8")
    for text in (scheduler, worker):
        result = validate_crawler_unit_contract(text)
        assert result["passed"] is True
        assert result["user"] == "extra-consultoria"
        assert result["environment_file_mode_required"] == "0600"

    rootish = validate_crawler_unit_contract("[Service]\nUser=root\n")
    assert rootish["passed"] is False
    assert "non_root_user_required" in rootish["errors"]

    env = tmp_path / "crawler.env"
    env.write_text("LOCAL_DATALAKE_DSN=postgresql://x\n", encoding="utf-8")
    env.chmod(0o640)
    assert environment_file_mode_ok(env) is False
    env.chmod(0o600)
    assert environment_file_mode_ok(env) is True
    assert running_as_non_root(euid=1000) is True
    assert running_as_non_root(euid=0) is False
