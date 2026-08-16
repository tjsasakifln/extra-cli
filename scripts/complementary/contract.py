"""Shared terminal states, hashing and pagination for complementary sources."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal

Terminal = Literal[
    "success",
    "success_zero",
    "ZERO_CONFIRMED",
    "partial",
    "BLOCKED",
    "NOT_APPLICABLE",
    "FAILED",
    "skipped",
]


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_json(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return sha256_bytes(blob)


def classify_http_block(*, status: int | None, body: str = "", headers: dict[str, str] | None = None) -> str | None:
    text = (body or "").lower()
    hdrs = {str(k).lower(): str(v).lower() for k, v in (headers or {}).items()}
    if status in {401, 403}:
        return "BLOCKED"
    if "captcha" in text or "recaptcha" in text:
        return "BLOCKED"
    if "login" in text and ("senha" in text or "password" in text or "entrar" in text):
        return "BLOCKED"
    if "www-authenticate" in hdrs:
        return "BLOCKED"
    if status == 429 or (status is not None and status >= 500):
        return "FAILED"
    return None


@dataclass
class PageResult:
    page: int
    records: list[dict[str, Any]]
    raw_uri: str
    raw_hash: str
    content_hash: str
    complete: bool
    status: int = 200
    body: str = ""


@dataclass
class RunResult:
    source: str
    terminal: Terminal
    fetched: int
    persisted: int
    deduplicated: int
    failed: int
    records: list[dict[str, Any]] = field(default_factory=list)
    reason: str | None = None
    job: dict[str, Any] = field(default_factory=dict)
    pages: list[PageResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "terminal": self.terminal,
            "fetched": self.fetched,
            "persisted": self.persisted,
            "deduplicated": self.deduplicated,
            "failed": self.failed,
            "reason": self.reason,
            "job": self.job,
            "n_records": len(self.records),
        }


def reconcile_counts(*, fetched: int, persisted: int, rejected: int) -> bool:
    return fetched == persisted + rejected


def pagination_terminal(
    *,
    pages_seen: int,
    last_complete: bool,
    record_count: int,
    blocked: bool = False,
    failed: bool = False,
    skipped: bool = False,
) -> Terminal:
    if skipped:
        return "skipped"
    if blocked:
        return "BLOCKED"
    if failed:
        return "FAILED"
    if not last_complete:
        return "partial"
    if record_count == 0:
        return "ZERO_CONFIRMED"
    return "success"
