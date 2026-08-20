"""Frozen clock helpers. Replay never depends on wall-clock."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def parse_clock(value: str | datetime | None, *, default: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if value:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    if default is not None:
        return parse_clock(default)
    return datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def iso(moment: datetime) -> str:
    moment = parse_clock(moment)
    return moment.isoformat()


def expires_at(moment: datetime, ttl_seconds: int) -> datetime:
    return parse_clock(moment) + timedelta(seconds=ttl_seconds)
