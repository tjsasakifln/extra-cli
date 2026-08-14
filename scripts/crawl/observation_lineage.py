"""#305 — persist-time lineage from a contract observation back to its page.

Every persisted observation must carry run, attempt, window, page/cursor,
official URL, raw URI and SHA-256. Upsert appends occurrences; it never
collapses lineage to the first sighting. Page/window totals fail closed
unless fetched = persisted + rejected.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

REQUIRED_FIELDS = (
    "run_id",
    "attempt_id",
    "window_start",
    "window_end",
    "page",
    "official_url",
    "raw_uri",
    "raw_sha256",
)


class LineageError(ValueError):
    """Observation is not persistable."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_payload(obj: Any) -> str:
    return sha256_bytes(
        json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    )


@dataclass(frozen=True)
class Lineage:
    run_id: str
    attempt_id: str
    window_start: str
    window_end: str
    page: int
    official_url: str
    raw_uri: str
    raw_sha256: str
    cursor: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Observation:
    contract_id: str
    lineage: Lineage
    payload_hash: str
    occurrence: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "occurrence": self.occurrence,
            "payload_hash": self.payload_hash,
            **self.lineage.as_dict(),
        }


def lineage_from_envelope(raw: dict[str, Any], *, default_url: str | None = None) -> Lineage:
    page = raw.get("page")
    if page is None:
        page = raw.get("_page")
    try:
        page_no = int(page)
    except (TypeError, ValueError) as exc:
        raise LineageError("page is required") from exc
    raw_body = raw.get("_raw_bytes")
    if isinstance(raw_body, (bytes, bytearray)):
        digest = sha256_bytes(bytes(raw_body))
    else:
        digest = str(raw.get("raw_sha256") or raw.get("_raw_sha256") or "")
    lin = Lineage(
        run_id=str(raw.get("run_id") or raw.get("_run_id") or ""),
        attempt_id=str(raw.get("attempt_id") or raw.get("_attempt_id") or ""),
        window_start=str(raw.get("query_window_start") or raw.get("window_start") or ""),
        window_end=str(raw.get("query_window_end") or raw.get("window_end") or ""),
        page=page_no,
        official_url=str(raw.get("official_url") or default_url or ""),
        raw_uri=str(raw.get("raw_uri") or raw.get("_raw_uri") or ""),
        raw_sha256=digest,
        cursor=None if raw.get("cursor") is None else str(raw.get("cursor")),
    )
    missing = [name for name in REQUIRED_FIELDS if not str(getattr(lin, name) or "")]
    if missing:
        raise LineageError(f"missing_lineage:{','.join(missing)}")
    if lin.window_end < lin.window_start:
        raise LineageError("window_end precedes window_start")
    if len(lin.raw_sha256) != 64:
        raise LineageError("raw_sha256 must be 64 hex chars")
    return lin


def attach_lineage(record: dict[str, Any], lineage: Lineage) -> dict[str, Any]:
    record.update(lineage.as_dict())
    return record


def persist_observations(
    existing: tuple[Observation, ...],
    incoming: tuple[Observation, ...],
) -> tuple[Observation, ...]:
    """Append occurrences. Same contract seen again keeps every lineage row."""
    out = list(existing)
    counts: dict[str, int] = {}
    for obs in existing:
        counts[obs.contract_id] = max(counts.get(obs.contract_id, 0), obs.occurrence)
    for obs in incoming:
        next_occ = counts.get(obs.contract_id, 0) + 1
        counts[obs.contract_id] = next_occ
        out.append(
            Observation(
                contract_id=obs.contract_id,
                lineage=obs.lineage,
                payload_hash=obs.payload_hash,
                occurrence=next_occ,
            )
        )
    return tuple(out)


def reconcile_page_window(
    *,
    fetched: int,
    persisted: int,
    rejected: int,
    window_start: str,
    window_end: str,
    page: int,
) -> dict[str, Any]:
    if fetched != persisted + rejected:
        raise LineageError(
            f"page_window_totals_do_not_close:fetched={fetched} persisted={persisted} rejected={rejected}"
        )
    return {
        "window_start": window_start,
        "window_end": window_end,
        "page": page,
        "fetched": fetched,
        "persisted": persisted,
        "rejected": rejected,
        "closed": True,
    }
