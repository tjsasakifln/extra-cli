"""Shared public-platform adapter contract.

Listing / detail / documents / status, reconciled pagination, raw/hash,
ZERO only after complete scope, login/CAPTCHA/403 → BLOCKED.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal

Terminal = Literal["success", "ZERO", "partial", "BLOCKED", "FAILED", "skipped"]

PLATFORMS: dict[str, dict[str, Any]] = {
    "bbmnet": {
        "issue": 262,
        "canonical_url": "https://www.bbmnet.com.br/",
        "id_field": "codigo",
        "capability": "open_tenders",
        "role": "complementary",
        "freshness_sla_hours": 24,
        "aliases": ["bbm-net", "bbm"],
    },
    "licitanet": {
        "issue": 263,
        "canonical_url": "https://licitanet.com.br/",
        "id_field": "sessao_id",
        "capability": "open_tenders",
        "role": "complementary",
        "freshness_sla_hours": 24,
        "aliases": ["licita-net"],
    },
    "compras_br": {
        "issue": 264,
        "canonical_url": "https://comprasbr.com.br/",
        "id_field": "idlicitacao",
        "capability": "open_tenders",
        "role": "complementary",
        "freshness_sla_hours": 24,
        "aliases": ["comprasbr", "cbr"],
    },
}


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_json(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return sha256_bytes(blob)


def classify_http_block(
    *,
    status: int | None,
    body: str = "",
    headers: dict[str, str] | None = None,
) -> str | None:
    text = (body or "").lower()
    hdrs = {str(k).lower(): str(v).lower() for k, v in (headers or {}).items()}
    if status in {401, 403}:
        return "BLOCKED"
    if "captcha" in text or "recaptcha" in text:
        return "BLOCKED"
    if "login" in text and any(token in text for token in ("senha", "password", "entrar")):
        return "BLOCKED"
    if "www-authenticate" in hdrs:
        return "BLOCKED"
    if status == 429 or (status is not None and status >= 500):
        return "FAILED"
    return None


def pagination_terminal(
    *,
    last_complete: bool,
    record_count: int,
    blocked: bool = False,
    failed: bool = False,
) -> Terminal:
    if blocked:
        return "BLOCKED"
    if failed:
        return "FAILED"
    if not last_complete:
        return "partial"
    if record_count == 0:
        return "ZERO"
    return "success"


@dataclass
class PageResult:
    page: int
    records: list[dict[str, Any]]
    raw_uri: str
    raw_hash: str
    content_hash: str
    complete: bool
    surface: str
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
    entity_key: str | None = None
    reason: str | None = None
    records: list[dict[str, Any]] = field(default_factory=list)
    pages: list[PageResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "terminal": self.terminal,
            "fetched": self.fetched,
            "persisted": self.persisted,
            "deduplicated": self.deduplicated,
            "failed": self.failed,
            "entity_key": self.entity_key,
            "reason": self.reason,
            "n_records": len(self.records),
            "pages": [
                {
                    "page": page.page,
                    "surface": page.surface,
                    "raw_uri": page.raw_uri,
                    "raw_hash": page.raw_hash,
                    "content_hash": page.content_hash,
                    "complete": page.complete,
                    "n_records": len(page.records),
                }
                for page in self.pages
            ],
        }
