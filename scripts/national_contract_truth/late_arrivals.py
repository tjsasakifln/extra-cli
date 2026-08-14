"""#308 — re-query mutable historical contract windows.

Hot / warm / cold policy is versioned. Completed windows get revalidate_after
and are never sealed forever. Checkpoint advances only after raw + persist +
reconcile.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

POLICY_VERSION = "late-arrivals-v1"
HOT_DAYS = 7
WARM_DAYS = 90

WindowClass = Literal["hot", "warm", "cold"]


@dataclass(frozen=True)
class WindowPolicy:
    version: str
    klass: WindowClass
    lookback: timedelta
    revalidate_after: timedelta


@dataclass(frozen=True)
class WindowState:
    window_id: str
    klass: WindowClass
    complete: bool
    revalidate_after: datetime | None
    last_reconciled_at: datetime | None


def classify_window(age: timedelta) -> WindowClass:
    if age <= timedelta(days=HOT_DAYS):
        return "hot"
    if age <= timedelta(days=WARM_DAYS):
        return "warm"
    return "cold"


def window_policy(klass: WindowClass) -> WindowPolicy:
    if klass == "hot":
        return WindowPolicy(POLICY_VERSION, "hot", timedelta(days=HOT_DAYS), timedelta(hours=12))
    if klass == "warm":
        return WindowPolicy(POLICY_VERSION, "warm", timedelta(days=WARM_DAYS), timedelta(days=7))
    return WindowPolicy(POLICY_VERSION, "cold", timedelta(days=3650), timedelta(days=30))


def stamp_complete(window_id: str, klass: WindowClass, now: datetime) -> WindowState:
    policy = window_policy(klass)
    return WindowState(
        window_id=window_id,
        klass=klass,
        complete=True,
        revalidate_after=now + policy.revalidate_after,
        last_reconciled_at=now,
    )


def is_sealed_forever(state: WindowState) -> bool:
    return False if state.revalidate_after is not None else state.complete


def due_for_revalidation(state: WindowState, now: datetime) -> bool:
    if state.revalidate_after is None:
        return True
    return now >= state.revalidate_after


def late_arrival_is_in_scope(
    *,
    event_date: datetime,
    published_at: datetime,
    now: datetime,
    incremental_lookback: timedelta,
) -> bool:
    """A contract published today with an event date older than lookback must still be discovered."""
    if published_at > now:
        return False
    published_inside_hot = (now - published_at) <= incremental_lookback
    event_older_than_lookback = (now - event_date) > incremental_lookback
    return published_inside_hot and event_older_than_lookback


def may_advance_checkpoint(*, raw_ok: bool, persist_ok: bool, reconcile_ok: bool) -> bool:
    return raw_ok and persist_ok and reconcile_ok
