"""Independent commercial capacity metrics — never conflate pilot sample with reservoir.

Three independent quantities:

  PILOT_ACCEPTANCE_SAMPLE          — quality audit sample size only (default 50)
  NATIONAL_EMAIL_SEND_READY_RESERVOIR — distinct companies with EMAIL_SEND_READY
  ACTIVE_HOT_SET                   — rolling operational window for current throughput

50 is NEVER capacity, enrichment limit, materialization limit, or Warmbly limit.
"""

from __future__ import annotations

from typing import Any

# Quality-only pilot sample. DO NOT use as pipeline/reservoir capacity.
PILOT_ACCEPTANCE_SAMPLE = 50
MINIMUM_PILOT_ACCEPTANCE_SAMPLE = PILOT_ACCEPTANCE_SAMPLE  # alias for existing imports

# Explicit operating policy, not a measured universe count.
CONFENGE_PILOT_EMAILS_PER_HOUR = 10
CONFENGE_BUSINESS_HOURS_PER_DAY = 9
CONFENGE_RESERVE_BUSINESS_DAYS = 10
MIN_OPERATIONAL_RESERVE = 900

# Metric names (stable keys for artifacts / observability)
METRIC_PILOT_ACCEPTANCE_SAMPLE = "PILOT_ACCEPTANCE_SAMPLE"
METRIC_NATIONAL_EMAIL_SEND_READY_RESERVOIR = "NATIONAL_EMAIL_SEND_READY_RESERVOIR"
METRIC_ACTIVE_HOT_SET = "ACTIVE_HOT_SET"


def min_operational_reserve(
    *,
    emails_per_hour: float,
    business_hours_per_day: float,
    business_days: int = 10,
) -> int:
    """Minimum EMAIL_SEND_READY distinct companies for continuous ops.

    MIN_OPERATIONAL_RESERVE =
      configured_emails_per_hour
      × configured_business_hours_per_day
      × business_days  (default 10)
    """
    if emails_per_hour <= 0 or business_hours_per_day <= 0 or business_days <= 0:
        return 0
    return int(emails_per_hour * business_hours_per_day * business_days)


def business_hours_from_window(start: str, end: str) -> float:
    """Parse HH:MM window into hours (same-day window only)."""
    def _mins(hhmm: str) -> int:
        parts = str(hhmm).strip().split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        return h * 60 + m

    try:
        delta = _mins(end) - _mins(start)
    except (TypeError, ValueError, IndexError):
        return 0.0
    if delta <= 0:
        return 0.0
    return delta / 60.0


def warmbly_ops_config_from_env(env: dict[str, str] | None = None) -> dict[str, Any]:
    """Read real Warmbly CONFENGE rate config (defaults match host .env.confenge)."""
    import os

    e = env if env is not None else os.environ
    start = e.get("CONFENGE_SEND_WINDOW_START", "09:00")
    end = e.get("CONFENGE_SEND_WINDOW_END", "18:00")
    eph = float(
        e.get("CONFENGE_RATE_MAX_PER_HOUR")
        or e.get("CONFENGE_GLOBAL_SENDS_PER_HOUR")
        or e.get("CONFENGE_RATE_START_PER_HOUR")
        or CONFENGE_PILOT_EMAILS_PER_HOUR
    )
    hours = business_hours_from_window(start, end)
    if hours <= 0:
        hours = 8.0  # last-resort default only if window unparsable
    whatsapp = str(e.get("CONFENGE_WHATSAPP_ENABLED", "false")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return {
        "emails_per_hour": eph,
        "send_window_start": start,
        "send_window_end": end,
        "business_hours_per_day": hours,
        "business_days_only": str(e.get("CONFENGE_SEND_BUSINESS_DAYS_ONLY", "true")).lower()
        in {"1", "true", "yes"},
        "whatsapp_enabled": whatsapp,
        "email_only": not whatsapp,
        "auto_send_enabled": str(e.get("CONFENGE_AUTO_SEND_ENABLED", "false")).lower()
        in {"1", "true", "yes"},
        "sending_paused": str(e.get("CONFENGE_SENDING_PAUSED", "false")).lower()
        in {"1", "true", "yes"},
    }


def build_capacity_metrics(
    *,
    email_send_ready_distinct_companies: int,
    active_hot_set_size: int,
    pilot_acceptance_sample: int = PILOT_ACCEPTANCE_SAMPLE,
    emails_per_hour: float | None = None,
    business_hours_per_day: float | None = None,
    business_days: int = 10,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Independent metrics block — never use pilot sample as reservoir size."""
    ops = warmbly_ops_config_from_env(env)
    eph = float(emails_per_hour if emails_per_hour is not None else ops["emails_per_hour"])
    bhd = float(
        business_hours_per_day
        if business_hours_per_day is not None
        else ops["business_hours_per_day"]
    )
    reserve = min_operational_reserve(
        emails_per_hour=eph,
        business_hours_per_day=bhd,
        business_days=business_days,
    )
    esr = int(email_send_ready_distinct_companies)
    hot = int(active_hot_set_size)
    pilot = int(pilot_acceptance_sample)
    return {
        "schema": "confenge.operational_capacity_metrics.v1",
        METRIC_PILOT_ACCEPTANCE_SAMPLE: pilot,
        METRIC_NATIONAL_EMAIL_SEND_READY_RESERVOIR: esr,
        METRIC_ACTIVE_HOT_SET: hot,
        "MIN_OPERATIONAL_RESERVE": reserve,
        "operational_reserve_days": business_days,
        "emails_per_hour": eph,
        "business_hours_per_day": bhd,
        "reserve_gate_ok": esr >= reserve,
        "hot_set_le_reservoir": hot <= esr if esr > 0 else hot == 0,
        "pilot_is_not_capacity": True,
        "note": (
            f"{pilot} is PILOT_ACCEPTANCE_SAMPLE (quality only). "
            f"Reservoir={esr}, hot_set={hot}, min_reserve={reserve}."
        ),
        "warmbly": {
            "email_only": ops["email_only"],
            "whatsapp_enabled": ops["whatsapp_enabled"],
            "auto_send_enabled": ops["auto_send_enabled"],
            "sending_paused": ops["sending_paused"],
            "send_window_start": ops["send_window_start"],
            "send_window_end": ops["send_window_end"],
        },
    }


def assert_not_pilot_as_capacity(limit: int | None, *, context: str = "") -> None:
    """Fail closed when operational code treats 50 as capacity."""
    if limit is None:
        return
    if int(limit) == PILOT_ACCEPTANCE_SAMPLE:
        raise ValueError(
            f"Refusing operational hard cap of {limit} ({context}). "
            "PILOT_ACCEPTANCE_SAMPLE is quality-only, never national capacity."
        )
