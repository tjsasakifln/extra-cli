"""Injectable clock for deterministic envelopes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def parse_clock(value: datetime | str | None) -> datetime:
    if value is None:
        return datetime.now(tz=UTC)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def expires_at(moment: datetime, ttl_seconds: int) -> datetime:
    return moment + timedelta(seconds=ttl_seconds)
