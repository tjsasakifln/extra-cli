"""Version documents and official status of each PNCP candidate.

Fan-out contract: official page, files, history, items and results. Shortlist
accepts only a complete inventory. Revoked/annulled/suspended/closed do not
remain open. 429/5xx resume without losing progress.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

TERMINAL_OPEN_KILLERS = {
    "revogado": "revoked",
    "revoked": "revoked",
    "anulado": "annulled",
    "annulled": "annulled",
    "suspenso": "suspended",
    "suspended": "suspended",
    "encerrado": "closed",
    "closed": "closed",
    "cancelado": "closed",
}

RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})
REQUIRED_DOC_KINDS = ("edital", "tr", "anexo")


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class DocumentVersion:
    kind: str
    url: str
    sha256: str
    mime: str
    size: int
    version: int
    raw_uri: str
    blocker: str | None = None


@dataclass(frozen=True)
class FetchAttempt:
    url: str
    status: int
    attempt: int
    resume: bool


@dataclass
class CandidateInventory:
    candidate_id: str
    official_page: str | None
    official_reconfirmed: bool
    status: str
    documents: list[DocumentVersion] = field(default_factory=list)
    attempts: list[FetchAttempt] = field(default_factory=list)
    items_fetched: bool = False
    history_fetched: bool = False
    results_fetched: bool = False

    @property
    def inventory_complete(self) -> bool:
        if not self.official_reconfirmed or not self.official_page:
            return False
        if not (self.items_fetched and self.history_fetched and self.results_fetched):
            return False
        kinds = {doc.kind for doc in self.documents if doc.blocker is None}
        return all(kind in kinds for kind in REQUIRED_DOC_KINDS)

    @property
    def shortlist_eligible(self) -> bool:
        return self.inventory_complete and self.status == "open"


def classify_status(official: str, current: str = "open") -> str:
    key = official.strip().lower()
    if key in TERMINAL_OPEN_KILLERS:
        return TERMINAL_OPEN_KILLERS[key]
    return current if current else "open"


def record_attempt(url: str, status: int, attempt: int) -> FetchAttempt:
    return FetchAttempt(url=url, status=status, attempt=attempt, resume=status in RETRYABLE_STATUS)


def version_document(
    *,
    kind: str,
    url: str,
    body: bytes,
    mime: str,
    previous: DocumentVersion | None = None,
    blocker: str | None = None,
) -> DocumentVersion:
    digest = sha256_bytes(body) if body else ""
    version = 1
    if previous is not None:
        version = previous.version if previous.sha256 == digest else previous.version + 1
    if blocker:
        return DocumentVersion(
            kind=kind,
            url=url,
            sha256=digest,
            mime=mime,
            size=len(body),
            version=version,
            raw_uri="",
            blocker=blocker,
        )
    if not url or not digest or not mime:
        raise ValueError("document requires url, sha256 and mime unless a blocker is set")
    return DocumentVersion(
        kind=kind,
        url=url,
        sha256=digest,
        mime=mime,
        size=len(body),
        version=version,
        raw_uri=f"cas://pncp-docs/{digest}",
        blocker=None,
    )


def apply_fanout(
    inventory: CandidateInventory,
    *,
    official_page: str,
    official_status: str,
    documents: list[DocumentVersion],
    items_fetched: bool,
    history_fetched: bool,
    results_fetched: bool,
) -> CandidateInventory:
    inventory.official_page = official_page
    inventory.official_reconfirmed = bool(official_page)
    inventory.status = classify_status(official_status, inventory.status)
    inventory.documents = list(documents)
    inventory.items_fetched = items_fetched
    inventory.history_fetched = history_fetched
    inventory.results_fetched = results_fetched
    return inventory


def resume_progress(attempts: list[FetchAttempt], url: str) -> int:
    """Next attempt number; retryable failures do not drop prior successful pages."""
    related = [a for a in attempts if a.url == url]
    if not related:
        return 1
    return max(a.attempt for a in related) + 1


def inventory_report(inventory: CandidateInventory) -> dict[str, Any]:
    return {
        "candidate_id": inventory.candidate_id,
        "status": inventory.status,
        "official_page": inventory.official_page,
        "official_reconfirmed": inventory.official_reconfirmed,
        "inventory_complete": inventory.inventory_complete,
        "shortlist_eligible": inventory.shortlist_eligible,
        "documents": [asdict(d) for d in inventory.documents],
        "attempts": [asdict(a) for a in inventory.attempts],
        "generated_at": _utc_now(),
    }
