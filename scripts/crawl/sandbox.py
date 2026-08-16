"""#276 — crawler sandbox: URL allowlist, archive limits, BLOCKED, redaction.

I/O stays at the edge. Decision functions are pure so tests drive the
shipped units with fakes only at the transport boundary.
"""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from typing import Any

from scripts.crawl.security import validate_public_url, validate_redirect_chain
from scripts.lib.structured_logging import redact_secrets
from scripts.ops.validate_crawler_runtime_security import (
    validate_environment_file,
)
from scripts.process_documents.storage import (
    MAX_PDF_BYTES,
    MAX_PDF_PAGES,
    MAX_ZIP_MEMBERS,
    MAX_ZIP_UNCOMPRESSED,
    safe_extract_zip,
    validate_pdf_limits,
)

__all__ = [
    "MAX_PDF_BYTES",
    "MAX_PDF_PAGES",
    "MAX_ZIP_MEMBERS",
    "MAX_ZIP_UNCOMPRESSED",
    "blocked_access_reason",
    "classify_fetch_outcome",
    "guard_crawler_url",
    "redact_crawler_evidence",
    "validate_archive_limits",
    "validate_crawler_unit_contract",
    "validate_environment_file",
    "validate_pdf_limits",
    "validate_redirect_chain",
]

_COOKIE_PATTERN = re.compile(r"(?i)(cookie|set-cookie)\s*[:=]\s*[^\s;]+")
_DSN_PATTERN = re.compile(r"(?i)(postgres|postgresql|mysql|mongodb)://[^\s]+")


def guard_crawler_url(url: str, *, resolve_dns: bool = False) -> str:
    """Block file://, localhost/RFC1918 and path traversal before fetch."""
    return validate_public_url(url, resolve_dns=resolve_dns)


def blocked_access_reason(
    *,
    status: int | None,
    body: str = "",
    headers: dict[str, str] | None = None,
    url: str = "",
) -> str | None:
    """Return a BLOCKED reason for login/CAPTCHA/403. Never success."""
    text = f"{body} {url}".lower()
    hdrs = {str(k).lower(): str(v).lower() for k, v in (headers or {}).items()}
    if status in {401, 403}:
        return "http_forbidden"
    if "captcha" in text or "recaptcha" in text or "hcaptcha" in text:
        return "captcha"
    if "login" in text and any(token in text for token in ("senha", "password", "entrar", "sign in")):
        return "login_wall"
    if "www-authenticate" in hdrs:
        return "auth_challenge"
    location = hdrs.get("location", "")
    if status in {301, 302, 303, 307, 308} and any(
        token in location for token in ("login", "signin", "captcha", "challenge")
    ):
        return "auth_redirect"
    return None


def classify_fetch_outcome(
    *,
    status: int | None,
    body: str = "",
    headers: dict[str, str] | None = None,
    url: str = "",
    records: int = 0,
    scope_complete: bool = False,
    pagination_reconciled: bool = False,
) -> str:
    """Terminal state. ZERO only after a complete reconciled scope."""
    blocked = blocked_access_reason(status=status, body=body, headers=headers, url=url)
    if blocked:
        return "BLOCKED"
    if status is not None and status >= 500:
        return "FAILED"
    if status == 429:
        return "FAILED"
    if not scope_complete or not pagination_reconciled:
        return "partial"
    if records == 0:
        return "ZERO"
    return "success"


def redact_crawler_evidence(text: str) -> str:
    """DSN, tokens and cookies must never appear in logs or evidence."""
    out = redact_secrets(text)
    out = _COOKIE_PATTERN.sub(r"\1=[REDACTED]", out)
    out = _DSN_PATTERN.sub("[REDACTED_DSN]", out)
    return out


def validate_archive_limits(path: Path, dest_dir: Path) -> list[Path]:
    """ZIP size/expansion limits plus path traversal. Delegates to storage."""
    return safe_extract_zip(path, dest_dir)


def validate_crawler_unit_contract(unit_text: str) -> dict[str, Any]:
    """Units must run as non-root and load an EnvironmentFile (mode 0600)."""
    user = None
    env_file = None
    for raw in unit_text.splitlines():
        line = raw.strip()
        if line.startswith("User="):
            user = line.split("=", 1)[1].strip()
        if line.startswith("EnvironmentFile="):
            env_file = line.split("=", 1)[1].strip().lstrip("-")
    errors: list[str] = []
    if not user or user in {"root", "0"}:
        errors.append("non_root_user_required")
    if not env_file:
        errors.append("environment_file_required")
    return {
        "user": user,
        "environment_file": env_file,
        "environment_file_mode_required": "0600",
        "passed": not errors,
        "errors": errors,
    }


def environment_file_mode_ok(path: Path, *, expected_uid: int | None = None) -> bool:
    result = validate_environment_file(path, expected_uid=expected_uid)
    if result.get("passed"):
        return True
    if not path.exists():
        return False
    return stat.S_IMODE(path.stat().st_mode) == 0o600


def running_as_non_root(euid: int | None = None) -> bool:
    uid = os.geteuid() if euid is None else euid
    return uid != 0
