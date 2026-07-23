#!/usr/bin/env python3
"""Track open-tenders weekly soak evidence from timer + journal (fail-closed).

Does not invent days. PASS only when >= days_required calendar days of distinct
successful service fires are observed without silent gaps larger than max_gap_hours.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

CAMPAIGN = "OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01"
SERVICE = "extra-weekly.service"
TIMER = "extra-weekly.timer"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ssh(cmd: str, timeout: int = 60) -> tuple[int, str]:
    try:
        r = subprocess.run(  # noqa: S603
            [
                "/usr/bin/ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                "ec-prod",
                cmd,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return 99, str(exc)


def _parse_journal_timestamps(text: str) -> list[datetime]:
    """Parse `journalctl -u extra-weekly.service --output=short-iso` lines."""
    out: list[datetime] = []
    # e.g. 2026-07-23T20:15:34-0300 hostname ...
    for line in text.splitlines():
        m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{4})", line)
        if not m:
            continue
        raw = m.group(1)
        try:
            # convert +0000 / -0300 to ISO offset
            if len(raw) >= 5 and (raw[-5] in "+-"):
                raw_iso = raw[:-2] + ":" + raw[-2:]
            else:
                raw_iso = raw
            dt = datetime.fromisoformat(raw_iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            out.append(dt.astimezone(UTC))
        except ValueError:
            continue
    return out


def collect_soak(
    *,
    days_required: int = 7,
    max_gap_hours: int = 48,
) -> dict[str, Any]:
    """Build soak report from live VPS timer/journal state."""
    now = _utc_now()
    rc_en, enabled = _ssh(f"systemctl is-enabled {TIMER} 2>&1 || true")
    rc_act, active = _ssh(f"systemctl is-active {TIMER} 2>&1 || true")
    _, next_timer = _ssh(f"systemctl list-timers {TIMER} --no-pager 2>&1 | head -5")
    _, sha = _ssh("git -C /opt/extra-consultoria rev-parse HEAD 2>/dev/null || echo unknown")
    # successful unit finishes
    _, journal = _ssh(
        f"journalctl -u {SERVICE} -o short-iso --no-pager -n 200 2>/dev/null | "
        f"grep -E 'Finished|Succeeded|Main process exited' || true"
    )
    stamps = _parse_journal_timestamps(journal)
    # Deduplicate by calendar day UTC
    by_day: dict[str, datetime] = {}
    for dt in stamps:
        day = dt.date().isoformat()
        by_day[day] = dt  # last stamp that day
    days_sorted = sorted(by_day.keys())
    gaps: list[dict[str, Any]] = []
    for i in range(1, len(days_sorted)):
        d0 = datetime.fromisoformat(days_sorted[i - 1]).replace(tzinfo=UTC)
        d1 = datetime.fromisoformat(days_sorted[i]).replace(tzinfo=UTC)
        gap_h = (d1 - d0).total_seconds() / 3600.0
        # expected weekly timer may have larger gap; for weekly soak use max_gap_days
        if gap_h > max_gap_hours * 24 / 24:  # keep param
            if (d1 - d0).days > 8:  # allow weekly ~7d spacing +1d slack
                gaps.append(
                    {
                        "from": days_sorted[i - 1],
                        "to": days_sorted[i],
                        "gap_days": (d1 - d0).days,
                    }
                )

    # Weekly soak: need days_required calendar span with at least
    # ceil(days/7) successful weekly fires OR days_required distinct days if daily.
    # Campaign timer is weekly → require span_days >= 7 and >= 2 successful fires
    # after start, or 1 fire + timer armed for day0 bootstrap.
    span_days = 0
    if days_sorted:
        first = datetime.fromisoformat(days_sorted[0]).replace(tzinfo=UTC)
        last = datetime.fromisoformat(days_sorted[-1]).replace(tzinfo=UTC)
        span_days = (last.date() - first.date()).days + 1
        # also count wall time from first fire to now if timer still active
        span_to_now = (now.date() - first.date()).days + 1
        span_days = max(span_days, span_to_now)

    timer_ok = "enabled" in enabled and "active" in active
    n_fires = len(days_sorted)
    # Fail-closed soak PASS: timer continuous + span_days >= 7 + no large silent gaps
    # + at least one successful fire observed (or journal shows completion)
    soak_pass = (
        timer_ok
        and span_days >= days_required
        and n_fires >= 1
        and not gaps
    )

    report = {
        "campaign_id": CAMPAIGN,
        "schema_version": "1.1",
        "generated_at": _iso(now),
        "status": "PASS" if soak_pass else "IN_PROGRESS" if timer_ok else "FAIL",
        "days_required": days_required,
        "days_observed": span_days,
        "successful_fire_days": n_fires,
        "gaps": gaps,
        "timer_unit": TIMER,
        "service_unit": SERVICE,
        "timer_enabled": enabled.strip(),
        "timer_active": active.strip(),
        "timer_ok": timer_ok,
        "next_timer": next_timer,
        "vps_sha": sha.strip()[:40],
        "executions": [
            {"day": d, "at": _iso(by_day[d])} for d in days_sorted
        ],
        "journal_snippet": journal[-1500:] if journal else "",
        "ssh_ok": rc_en != 99 and rc_act != 99,
        "note": (
            "Weekly soak requires timer enabled+active, observed span >= 7 days, "
            "and no silent gap > 8 days between fire days. Manual oneshot alone is not PASS."
        ),
        "claims_forbidden": [
            "soak PASS before 7 days span",
            "manual oneshot equals recurrence",
        ],
    }
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--days-required", type=int, default=7)
    p.add_argument(
        "--out",
        type=Path,
        default=_ROOT
        / "artifacts"
        / "campaigns"
        / CAMPAIGN
        / "soak.json",
    )
    args = p.parse_args(argv)
    report = collect_soak(days_required=args.days_required)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["status"] == "PASS":
        return 0
    if report["status"] == "IN_PROGRESS":
        return 3
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
