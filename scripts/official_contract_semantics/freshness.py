"""Operational freshness uses verification clocks, never contractual event age."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

FRESHNESS_POLICY = "official-authority-freshness/1.1"
STALE_REASON_UNVERIFIED = "unverified_source"
STALE_REASON_NO_BYTES = "url_without_retrieved_bytes"
STALE_REASON_CLOCK = "verification_clock_stale"
NOT_STALE = "not_stale"

# Wall-clock fields that must never enter a semantic/content hash.
TEMPORAL_HASH_EXCLUSIONS = frozenset(
    {
        "retrieved_at",
        "verified_at",
        "extracted_at",
        "generated_at",
        "started_at",
        "finished_at",
        "content_hash",
    }
)


def parse_instant(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        if len(text) == 10:
            try:
                parsed = datetime.fromisoformat(text + "T00:00:00+00:00")
            except ValueError:
                return None
        else:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def event_is_recent(*, event_effective_at: str | None, now: str, recent_hours: int = 48) -> bool:
    """An old contractual event stays historically old even if re-verified now."""
    event = parse_instant(event_effective_at)
    clock = parse_instant(now)
    if event is None or clock is None:
        return False
    return (clock - event) <= timedelta(hours=recent_hours)


@dataclass(frozen=True)
class TemporalFields:
    event_effective_at: str | None
    source_published_at: str | None
    retrieved_at: str | None
    verified_at: str | None
    source_as_of: str | None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "event_effective_at": self.event_effective_at,
            "source_published_at": self.source_published_at,
            "retrieved_at": self.retrieved_at,
            "verified_at": self.verified_at,
            "source_as_of": self.source_as_of,
        }


def resolve_temporal_fields(
    *,
    event_effective_at: str | None = None,
    source_published_at: str | None = None,
    retrieved_at: str | None = None,
    verified_at: str | None = None,
    source_as_of: str | None = None,
    effective_at: str | None = None,
    observed_at: str | None = None,
    bytes_obtained: bool = False,
) -> TemporalFields:
    retrieved = retrieved_at if bytes_obtained else None
    verified = verified_at if bytes_obtained else None
    return TemporalFields(
        event_effective_at=event_effective_at or effective_at,
        source_published_at=source_published_at or observed_at,
        retrieved_at=retrieved,
        verified_at=verified,
        source_as_of=source_as_of,
    )


def operational_clock(*, verified_at: str | None, retrieved_at: str | None) -> str | None:
    return verified_at or retrieved_at


def is_stale_evidence(
    *,
    event_effective_at: str | None,
    source_published_at: str | None,
    retrieved_at: str | None,
    verified_at: str | None,
    as_of: str,
    bytes_obtained: bool,
    max_age_hours: int = 48,
) -> tuple[bool, str]:
    """Freshness is operational. Event age never makes a just-verified source stale."""
    del event_effective_at, source_published_at
    if not bytes_obtained:
        return True, STALE_REASON_NO_BYTES
    clock = operational_clock(verified_at=verified_at, retrieved_at=retrieved_at)
    if clock is None:
        return True, STALE_REASON_UNVERIFIED
    verified = parse_instant(clock)
    as_of_dt = parse_instant(as_of)
    if verified is None or as_of_dt is None:
        return True, STALE_REASON_UNVERIFIED
    if as_of_dt - verified > timedelta(hours=max_age_hours):
        return True, STALE_REASON_CLOCK
    return False, NOT_STALE


def freshness_block(
    temporal: TemporalFields,
    *,
    as_of: str,
    bytes_obtained: bool,
    max_age_hours: int = 48,
) -> dict[str, Any]:
    stale, reason = is_stale_evidence(
        event_effective_at=temporal.event_effective_at,
        source_published_at=temporal.source_published_at,
        retrieved_at=temporal.retrieved_at,
        verified_at=temporal.verified_at,
        as_of=as_of,
        bytes_obtained=bytes_obtained,
        max_age_hours=max_age_hours,
    )
    return {
        "policy": FRESHNESS_POLICY,
        "as_of": as_of,
        "operational_clock": "verified_at|retrieved_at",
        "max_age_hours": max_age_hours,
        "stale": stale,
        "reason": reason,
        "event_is_recent": event_is_recent(
            event_effective_at=temporal.event_effective_at,
            now=as_of,
            recent_hours=max_age_hours,
        ),
        **temporal.as_dict(),
    }


def strip_temporal_for_hash(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            str(key): strip_temporal_for_hash(value)
            for key, value in payload.items()
            if key not in TEMPORAL_HASH_EXCLUSIONS
        }
    if isinstance(payload, list):
        return [strip_temporal_for_hash(item) for item in payload]
    if isinstance(payload, tuple):
        return [strip_temporal_for_hash(item) for item in payload]
    return payload
