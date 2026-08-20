#!/usr/bin/env python3
"""Versioned PNCP contracts freshness contract (PNCP_CONTRACT_FRESHNESS/1.0).

Pure classification over timestamps, window counts and checkpoint snapshots.
HTTP/systemd/PostgreSQL I/O stay behind collect_snapshot so tests do not need
the VPS. Status is fail-closed against the *desired* 6h/24h SLOs. Honesty flags
(`sustainable_*`, max inter-run) are derived from the shipped
`pncp-contracts.timer` calendar so they cannot drift from the unit file.
LOCK_BUSY / exit 75 is never a closed window and never FRESH. UNKNOWN, an
active timer, HTTP 200 or a single recent row never become FRESH.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.contracts_truth import (  # noqa: E402
    CheckpointLocationError,
    resolve_checkpoint_dir,
)
from scripts.crawl.contracts_checkpoint_contract import (  # noqa: E402
    diagnose,
)
from scripts.crawl.pncp_contract import (  # noqa: E402
    PNCP_TAMANHO_PAGINA_MAX_CONTRATOS,
    PNCP_TAMANHO_PAGINA_MIN,
)
from scripts.crawl.pncp_entity_pagination import (  # noqa: E402
    classify_http,
    prove_scope,
    record_page,
)

CONTRACT_VERSION = "PNCP_CONTRACT_FRESHNESS/1.0"
STATUSES = ("FRESH", "DEGRADED", "STALE", "UNKNOWN")

# Desired SLOs from the campaign. Cadence honesty is computed from the unit file.
DESIRED_OPERATIONAL_TARGET_HOURS = 6.0
DESIRED_OPERATIONAL_PERCENTILE = 95
DESIRED_HARD_GUARDRAIL_HOURS = 24.0
TIMER_UNIT = "pncp-contracts.timer"
SERVICE_UNIT = "pncp-contracts.service"
TIMER_UNIT_PATH = _PROJECT_ROOT / "deploy" / "systemd" / "pncp-contracts.timer"
SERVICE_UNIT_PATH = _PROJECT_ROOT / "deploy" / "systemd" / "pncp-contracts.service"
LOGICAL_JOB_ID = "pncp-contracts-incremental"
LOCK_BUSY_EXIT = 75
EXPLICIT_TIMEZONES = frozenset({"UTC", "GMT", "Z", "America/Sao_Paulo"})

REQUIRED_CONTRACT_COLUMNS = (
    "contrato_id",
    "ingested_at",
    "data_publicacao_fonte",
    "data_atualizacao_fonte",
    "first_seen_at",
)

REASON_MISSING_EVIDENCE = "MISSING_EVIDENCE"
REASON_TIMER_ACTIVE_NOT_PROOF = "TIMER_ACTIVE_NOT_PROOF"
REASON_HTTP_200_NOT_PROOF = "HTTP_200_NOT_PROOF"
REASON_SINGLE_ROW_NOT_PROOF = "SINGLE_ROW_NOT_PROOF"
REASON_WINDOW_INCOMPLETE = "WINDOW_INCOMPLETE"
REASON_WINDOW_EMPTY_COMPLETE = "WINDOW_EMPTY_COMPLETE"
REASON_WINDOW_EMPTY_INCOMPLETE = "WINDOW_EMPTY_INCOMPLETE"
REASON_LAG_ABOVE_OPERATIONAL_TARGET = "LAG_ABOVE_OPERATIONAL_TARGET"
REASON_LAG_ABOVE_HARD_GUARDRAIL = "LAG_ABOVE_HARD_GUARDRAIL"
REASON_UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
REASON_INTERNAL_DEFECT = "INTERNAL_DEFECT"
REASON_SCHEMA_DRIFT = "SCHEMA_DRIFT"
REASON_CHECKPOINT_INCONSISTENT = "CHECKPOINT_INCONSISTENT"
REASON_CHECKPOINT_IN_WORKTREE = "CHECKPOINT_IN_WORKTREE"
REASON_CHECKPOINT_CONFLICT = "CHECKPOINT_CONFLICT"
REASON_STALE_CHECKPOINT = "STALE_CHECKPOINT"
REASON_DUPLICATE_REPLAY = "DUPLICATE_REPLAY"
REASON_LATE_ARRIVAL = "LATE_ARRIVAL"
REASON_RETIFICACAO = "RETIFICACAO"
REASON_MISSING_SOURCE_TIMESTAMP = "MISSING_SOURCE_TIMESTAMP"
REASON_DB_UNAVAILABLE = "DB_UNAVAILABLE"
REASON_TIMER_DELAYED = "TIMER_DELAYED"
REASON_PAGINATION_INCOMPLETE = "PAGINATION_INCOMPLETE"
REASON_ILLEGAL_PAGE_SIZE = "ILLEGAL_PAGE_SIZE"
REASON_SOURCE_POPULATION_DRIFT = "SOURCE_POPULATION_DRIFT"
REASON_CADENCE_CANNOT_MEET_6H = "CADENCE_CANNOT_MEET_6H"
REASON_CADENCE_CANNOT_MEET_24H = "CADENCE_CANNOT_MEET_24H"
REASON_LOCK_BUSY_NO_CLOSE = "LOCK_BUSY_NO_CLOSE"
REASON_UNCLOSED_CURRENT_WINDOW = "UNCLOSED_CURRENT_WINDOW"
REASON_EXTERNAL_TRANSIENT = "EXTERNAL_TRANSIENT"
REASON_TIMER_TIMEZONE_AMBIGUOUS = "TIMER_TIMEZONE_AMBIGUOUS"
REASON_BACKUP_UNAVAILABLE = "BACKUP_UNAVAILABLE"
REASON_RESTORE_MISMATCH = "RESTORE_MISMATCH"
REASON_MISSED_TIMER = "MISSED_TIMER"
REASON_REBOOT_CATCHUP_REQUIRED = "REBOOT_CATCHUP_REQUIRED"

_ONCALENDAR_RE = re.compile(r"^OnCalendar=(?P<spec>.+?)\s*$", re.MULTILINE)
_PERSISTENT_RE = re.compile(r"^Persistent=(?P<val>\S+)", re.MULTILINE | re.IGNORECASE)
_SUCCESS_EXIT_RE = re.compile(r"^SuccessExitStatus=(?P<val>.+)$", re.MULTILINE)
_DOW_ORDER = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _is_timezone_token(token: str) -> bool:
    raw = token.strip()
    if not raw or raw in {"*-*-*", "*", "n/a"}:
        return False
    if raw in EXPLICIT_TIMEZONES or raw.startswith("America/") or raw.startswith("UTC"):
        return True
    if ":" in raw or raw[0].isdigit() or raw[0] in "+-" or "," in raw or "/" in raw and raw[0].isdigit():
        return False
    if raw[:3].title() in _DOW_ORDER or "," in raw:
        return False
    return "/" in raw


def parse_oncalendar_spec(spec: str) -> dict[str, Any]:
    """Parse one systemd OnCalendar= value into hours, timezone, max inter-run."""
    text = spec.strip()
    tokens = text.split()
    timezone = None
    if tokens and _is_timezone_token(tokens[-1]):
        timezone = tokens[-1]
        tokens = tokens[:-1]
    dow = None
    if tokens and tokens[0][0].isalpha():
        dow = tokens[0]
        tokens = tokens[1:]
    time_part = tokens[-1] if tokens else ""
    hours = _hours_from_time_part(time_part)
    max_inter = _max_inter_run_hours(hours, dow)
    return {
        "on_calendar": text,
        "timezone": timezone,
        "dow": dow,
        "hours": hours,
        "max_inter_run_hours": max_inter,
        "timezone_explicit": timezone in EXPLICIT_TIMEZONES or (timezone or "").startswith("America/"),
    }


def _hours_from_time_part(time_part: str) -> list[int]:
    if not time_part or time_part in {"hourly", "daily", "weekly"}:
        if time_part == "hourly":
            return list(range(24))
        if time_part == "daily":
            return [0]
        if time_part == "weekly":
            return [0]
        return []
    clock = time_part.split(":")[0]
    if clock == "*":
        return list(range(24))
    if "/" in clock:
        start_raw, step_raw = clock.split("/", 1)
        start_h = 0 if start_raw in {"", "*"} else int(start_raw)
        step_h = int(step_raw)
        if step_h <= 0:
            return []
        return list(range(start_h, 24, step_h))
    out: list[int] = []
    for piece in clock.split(","):
        piece = piece.strip()
        if piece == "*":
            return list(range(24))
        out.append(int(piece))
    return out


def _max_inter_run_hours(hours: Sequence[int], dow: str | None) -> float:
    if dow:
        names = {name.lower(): idx for idx, name in enumerate(_DOW_ORDER)}
        days: list[int] = []
        for token in dow.split(","):
            key = token.strip()[:3].lower()
            if key in names:
                days.append(names[key])
        if days:
            ordered_days = sorted(set(days))
            gaps: list[int] = []
            for i, day in enumerate(ordered_days):
                nxt = ordered_days[(i + 1) % len(ordered_days)]
                gap_days = (nxt - day) % 7
                if gap_days == 0:
                    gap_days = 7
                gaps.append(gap_days * 24)
            return float(max(gaps))
    if not hours:
        return 168.0
    ordered = sorted({int(h) % 24 for h in hours})
    gaps = []
    for i, hour in enumerate(ordered):
        nxt = ordered[(i + 1) % len(ordered)]
        gap = (nxt - hour) % 24
        if gap == 0:
            gap = 24
        gaps.append(gap)
    return float(max(gaps))


def cadence_from_unit_text(text: str) -> dict[str, Any]:
    """Derive cadence honesty from a systemd timer unit file."""
    specs = [match.group("spec").strip() for match in _ONCALENDAR_RE.finditer(text)]
    parsed = [parse_oncalendar_spec(spec) for spec in specs if spec]
    persistent_match = _PERSISTENT_RE.search(text)
    persistent = False
    if persistent_match:
        persistent = persistent_match.group("val").strip().lower() in {"true", "yes", "1", "on"}
    if not parsed:
        return {
            "on_calendar": "",
            "timezone": None,
            "dow": None,
            "hours": [],
            "max_inter_run_hours": 168.0,
            "timezone_explicit": False,
            "persistent": persistent,
            "specs": [],
        }
    worst = max(parsed, key=lambda item: float(item["max_inter_run_hours"]))
    return {**worst, "persistent": persistent, "specs": [item["on_calendar"] for item in parsed]}


def parse_success_exit_statuses(text: str) -> list[int]:
    found: list[int] = []
    for match in _SUCCESS_EXIT_RE.finditer(text):
        for piece in match.group("val").split():
            piece = piece.strip()
            if piece.isdigit():
                found.append(int(piece))
    return found


def load_shipped_cadence(*, timer_path: Path | None = None) -> dict[str, Any]:
    path = timer_path or TIMER_UNIT_PATH
    return cadence_from_unit_text(path.read_text(encoding="utf-8"))


def load_shipped_service_text(*, service_path: Path | None = None) -> str:
    path = service_path or SERVICE_UNIT_PATH
    return path.read_text(encoding="utf-8")


BACKUP_MAX_AGE_HOURS = 28.0
LOCAL_BACKUP_DIR = os.getenv("LOCAL_BACKUP_DIR", "/var/lib/extra-consultoria/backups/postgresql")
OFFSITE_BACKUP_DIR = os.getenv(
    "OFFSITE_BACKUP_DIR",
    str(Path(os.getenv("BACKUP_MOUNT_POINT", "/mnt/storage-box")) / "backups" / "postgresql"),
)
BACKUP_LOG_FILE = os.getenv("BACKUP_LOG_FILE", "/var/log/backup-database.log")


def _newest_dump(directory: Path) -> Path | None:
    if not directory.is_dir():
        return None
    found: list[Path] = []
    for pattern in ("*.dump", "*.dump.gz"):
        found.extend(directory.glob(pattern))
        found.extend(directory.glob(f"*/{pattern}"))
    if not found:
        return None
    return max(found, key=lambda path: path.stat().st_mtime)


def collect_backup_snapshot(
    *,
    as_of: datetime | None = None,
    local_dir: str | Path | None = None,
    offsite_dir: str | Path | None = None,
    restore_hash_identical: bool | None = None,
    restore_proof_path: str | Path | None = None,
) -> dict[str, Any]:
    """Observe local + off-host dumps. Stale/missing off-host is BACKUP_UNAVAILABLE."""
    now = as_of or datetime.now(UTC)
    local_root = Path(local_dir or LOCAL_BACKUP_DIR)
    offsite_root = Path(offsite_dir or OFFSITE_BACKUP_DIR)
    local_dump = _newest_dump(local_root)
    offsite_dump = _newest_dump(offsite_root)
    local_age = None
    if local_dump is not None:
        local_age = (now.timestamp() - local_dump.stat().st_mtime) / 3600.0
    offsite_age = None
    if offsite_dump is not None:
        offsite_age = (now.timestamp() - offsite_dump.stat().st_mtime) / 3600.0
    identical = restore_hash_identical
    proof = Path(restore_proof_path) if restore_proof_path else None
    if identical is None and proof is not None and proof.is_file():
        try:
            payload = json.loads(proof.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        if "hash_identical" in payload:
            identical = bool(payload.get("hash_identical"))
    # Recoverability for soak is off-host. Local-only is not enough.
    if offsite_age is not None:
        latest_age = offsite_age
        available = offsite_age <= BACKUP_MAX_AGE_HOURS
    elif local_age is not None:
        latest_age = local_age
        available = False  # off-host missing
    else:
        latest_age = None
        available = False
    return {
        "available": available,
        "latest_age_hours": latest_age,
        "local_age_hours": local_age,
        "offsite_age_hours": offsite_age,
        "local_path": str(local_dump) if local_dump else None,
        "offsite_path": str(offsite_dump) if offsite_dump else None,
        "restore_hash_identical": identical,
        "max_age_hours": BACKUP_MAX_AGE_HOURS,
    }


def classify_backup(
    *,
    available: bool | None,
    restore_hash_identical: bool | None = None,
    latest_age_hours: float | None = None,
    max_age_hours: float = 28.0,
) -> str | None:
    """Named backup/restore reason. Absence of a snapshot is not a PNCP FRESH proof."""
    if available is False:
        return REASON_BACKUP_UNAVAILABLE
    if restore_hash_identical is False:
        return REASON_RESTORE_MISMATCH
    if latest_age_hours is not None and float(latest_age_hours) > float(max_age_hours):
        return REASON_BACKUP_UNAVAILABLE
    return None


_SHIPPED_CADENCE = load_shipped_cadence()
TIMER_ON_CALENDAR = str(_SHIPPED_CADENCE.get("on_calendar") or "")
TIMER_MAX_INTER_RUN_HOURS = float(_SHIPPED_CADENCE.get("max_inter_run_hours") or 168.0)
TIMER_TIMEZONE = _SHIPPED_CADENCE.get("timezone")
TIMER_PERSISTENT = bool(_SHIPPED_CADENCE.get("persistent"))


_SYSTEMD_TS = re.compile(
    r"^(?:(?P<dow>[A-Za-z]{3}) )?"
    r"(?P<date>\d{4}-\d{2}-\d{2}) "
    r"(?P<time>\d{2}:\d{2}:\d{2})"
    r"(?: (?P<tz>\S+))?$"
)


def _tzinfo_from_token(token: str) -> timezone | None:
    raw = token.strip()
    if not raw or raw in {"n/a", "-", "None"}:
        return None
    if raw in {"UTC", "Z", "gmt", "GMT"}:
        return UTC
    if re.fullmatch(r"[+-]\d{2}", raw):
        hours = int(raw)
        return timezone(timedelta(hours=hours))
    if re.fullmatch(r"[+-]\d{2}:\d{2}", raw):
        sign = 1 if raw[0] == "+" else -1
        hours = int(raw[1:3])
        minutes = int(raw[4:6])
        return timezone(sign * timedelta(hours=hours, minutes=minutes))
    if re.fullmatch(r"[+-]\d{4}", raw):
        sign = 1 if raw[0] == "+" else -1
        hours = int(raw[1:3])
        minutes = int(raw[3:5])
        return timezone(sign * timedelta(hours=hours, minutes=minutes))
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(raw)
    except Exception:
        return None


def parse_dt(value: Any) -> datetime | None:
    """Parse ISO, date-only, unix epoch, or systemd show stamps to aware UTC."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if number > 1e14:
            number = number / 1_000_000.0
        elif number > 1e11:
            number = number / 1_000.0
        return datetime.fromtimestamp(number, tz=UTC)
    text = str(value).strip()
    if not text or text in {"n/a", "-", "None"}:
        return None
    if text.isdigit():
        return parse_dt(int(text))
    systemd = _SYSTEMD_TS.match(text)
    if systemd:
        stamp = f"{systemd.group('date')}T{systemd.group('time')}"
        tzinfo = _tzinfo_from_token(systemd.group("tz") or "UTC")
        dt = datetime.fromisoformat(stamp)
        dt = dt.replace(tzinfo=tzinfo or UTC)
        return dt.astimezone(UTC)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            d = date.fromisoformat(text[:10])
        except ValueError:
            return None
        return datetime(d.year, d.month, d.day, tzinfo=UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _iso_z(value: Any) -> str | None:
    parsed = parse_dt(value)
    if parsed is None:
        return None
    return parsed.isoformat().replace("+00:00", "Z")


def parse_window_key(key: str) -> tuple[date, date] | None:
    parts = str(key).split("_")
    if len(parts) != 2 or len(parts[0]) != 8 or len(parts[1]) != 8:
        return None
    try:
        start = date(int(parts[0][:4]), int(parts[0][4:6]), int(parts[0][6:8]))
        end = date(int(parts[1][:4]), int(parts[1][4:6]), int(parts[1][6:8]))
    except ValueError:
        return None
    return start, end


def last_successful_close_at(
    *,
    latest_closed: Mapping[str, Any] | None,
    snapshot: Mapping[str, Any],
    completed_keys: Sequence[str],
) -> datetime | None:
    """Lag clock is the last *successful* close. Failed attempt updated_at is not a close."""
    if latest_closed:
        closed = parse_dt(latest_closed.get("closed_at"))
        if closed is not None:
            return closed
    explicit = parse_dt(snapshot.get("last_successful_closed_at"))
    if explicit is not None:
        return explicit
    if completed_keys:
        span = parse_window_key(str(completed_keys[-1]))
        if span is not None:
            end = span[1]
            return datetime(end.year, end.month, end.day, tzinfo=UTC)
    return None


def lag_percentiles(samples: Sequence[float]) -> dict[str, float | None]:
    """Nearest-rank percentiles. Empty sample → None, never zero-as-fresh."""
    if not samples:
        return {"p50": None, "p95": None, "p99": None, "n": 0}
    ordered = sorted(float(x) for x in samples)
    n = len(ordered)

    def _pct(p: float) -> float:
        rank = max(1, math.ceil(p / 100.0 * n))
        return ordered[rank - 1]

    return {"p50": _pct(50), "p95": _pct(95), "p99": _pct(99), "n": n}


def legal_page_size(tamanho_pagina: int | None) -> bool:
    if tamanho_pagina is None:
        return False
    return PNCP_TAMANHO_PAGINA_MIN <= int(tamanho_pagina) <= PNCP_TAMANHO_PAGINA_MAX_CONTRATOS


def classify_ingest_http(
    *,
    status: int | None,
    page_size: int | None,
    body: str = "",
    kind: str | None = None,
) -> str:
    """Named fail-closed reason. Illegal page size is INTERNAL_DEFECT, never EXTERNAL_TRANSIENT."""
    if page_size is not None and int(page_size) < PNCP_TAMANHO_PAGINA_MIN:
        return REASON_ILLEGAL_PAGE_SIZE
    blob = (body or "").lower()
    if status == 400 and any(
        token in blob
        for token in (
            "must be greater than or equal",
            "tamanhopagina",
            "tamanho de página inválido",
            "tamanho de pagina invalido",
        )
    ):
        return REASON_ILLEGAL_PAGE_SIZE
    if kind in {"timeout", "network"} or status == 408:
        return REASON_EXTERNAL_TRANSIENT
    if status == 429:
        return REASON_EXTERNAL_TRANSIENT
    if status is not None and status >= 500:
        return REASON_EXTERNAL_TRANSIENT
    if status == 400:
        return REASON_INTERNAL_DEFECT
    if status is not None and status >= 400:
        return REASON_INTERNAL_DEFECT
    if kind and classify_http(int(status or 0)) in {"timeout", "retryable"}:
        return REASON_EXTERNAL_TRANSIENT
    return "OK"


def empty_window_reason(
    *,
    pages_expected: int,
    pages_fetched: int,
    found_count: int,
    query_complete: bool,
    page_size: int = 50,
) -> str:
    """ZERO is confirmed only when pagination finished. Incomplete empty is not ZERO."""
    if page_size < PNCP_TAMANHO_PAGINA_MIN:
        return REASON_ILLEGAL_PAGE_SIZE
    pages = [
        record_page(
            url=f"https://pncp.gov.br/api/consulta/v1/contratos?pagina={n}", status=200, body=b"x", page=n, records=0
        )
        for n in range(1, max(pages_fetched, 0) + 1)
    ]
    proof = prove_scope(
        ente_id="contracts-national",
        window="freshness",
        modalidade=None,
        pages_expected=pages_expected,
        pages=pages,
        found_count=found_count,
        query_complete=query_complete,
    )
    if proof.verdict == "ZERO_CONFIRMED":
        return REASON_WINDOW_EMPTY_COMPLETE
    if found_count == 0:
        return REASON_WINDOW_EMPTY_INCOMPLETE
    if not proof.pages_match or proof.verdict == "SCOPE_INCOMPLETE":
        return REASON_PAGINATION_INCOMPLETE
    return "WINDOW_COMPLETE"


def classify_schema(columns: Sequence[str]) -> str | None:
    have = set(columns)
    missing = [c for c in REQUIRED_CONTRACT_COLUMNS if c not in have]
    return REASON_SCHEMA_DRIFT if missing else None


def resume_units(*, planned: Sequence[str], completed: Sequence[str]) -> dict[str, Any]:
    """Crash/restart must resume the next pending unit, never skip it."""
    done = set(completed)
    pending = [unit for unit in planned if unit not in done]
    skipped = [unit for unit in planned if unit in done]
    return {
        "pending": pending,
        "skipped_resume": skipped,
        "next_unit": pending[0] if pending else None,
        "skipped_count": len(skipped),
    }


def classify_replay(*, inserted: int, skipped: int, rejected: int) -> str | None:
    if inserted == 0 and skipped > 0 and rejected == 0:
        return REASON_DUPLICATE_REPLAY
    return None


def classify_late_arrival(
    *, source_at: datetime | None, window_end: datetime | None, persisted_at: datetime | None
) -> str | None:
    if source_at is None or window_end is None or persisted_at is None:
        return None
    if source_at > window_end and persisted_at > window_end:
        return REASON_LATE_ARRIVAL
    return None


def classify_retificacao(
    *,
    publication_at: datetime | None,
    update_at: datetime | None,
    first_seen_at: datetime | None,
    last_seen_at: datetime | None,
) -> str | None:
    if publication_at and update_at and update_at > publication_at:
        return REASON_RETIFICACAO
    if first_seen_at and last_seen_at and last_seen_at > first_seen_at:
        return REASON_RETIFICACAO
    return None


def window_fully_covered(gap_key: str, completed: Sequence[str]) -> bool:
    parsed = parse_window_key(gap_key)
    if parsed is None:
        return False
    gap_start, gap_end = parsed
    covered: set[date] = set()
    for key in completed:
        span = parse_window_key(key)
        if span is None:
            continue
        start, end = span
        cur = start
        while cur <= end:
            covered.add(cur)
            cur = cur + timedelta(days=1)
    cur = gap_start
    while cur <= gap_end:
        if cur not in covered:
            return False
        cur = cur + timedelta(days=1)
    return True


def _unique(reasons: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in reasons:
        if not item or item == "OK" or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def classify_status(
    *,
    has_evidence: bool,
    current_lag_hours: float | None,
    material_incomplete_window: bool = False,
    pagination_incomplete: bool = False,
    timer_active_only: bool = False,
    http_200_only: bool = False,
    single_recent_row_only: bool = False,
    db_unavailable: bool = False,
    upstream_unavailable: bool = False,
    checkpoint_in_worktree: bool = False,
    checkpoint_conflict: bool = False,
    checkpoint_inconsistent: bool = False,
    schema_drift: bool = False,
    illegal_page_size: bool = False,
    missing_source_timestamp: bool = False,
    timer_delayed: bool = False,
    lock_busy_no_close: bool = False,
    extra_reasons: Sequence[str] = (),
    operational_target_hours: float = DESIRED_OPERATIONAL_TARGET_HOURS,
    hard_guardrail_hours: float = DESIRED_HARD_GUARDRAIL_HOURS,
    cadence_max_inter_run_hours: float = TIMER_MAX_INTER_RUN_HOURS,
) -> tuple[str, list[str]]:
    """Fail-closed status. UNKNOWN never becomes FRESH."""
    reasons: list[str] = list(extra_reasons)
    if cadence_max_inter_run_hours > operational_target_hours:
        reasons.append(REASON_CADENCE_CANNOT_MEET_6H)
    if cadence_max_inter_run_hours > hard_guardrail_hours:
        reasons.append(REASON_CADENCE_CANNOT_MEET_24H)

    untrustworthy = False
    if not has_evidence:
        reasons.append(REASON_MISSING_EVIDENCE)
        untrustworthy = True
    if timer_active_only:
        reasons.append(REASON_TIMER_ACTIVE_NOT_PROOF)
        untrustworthy = True
    if http_200_only:
        reasons.append(REASON_HTTP_200_NOT_PROOF)
        untrustworthy = True
    if single_recent_row_only:
        reasons.append(REASON_SINGLE_ROW_NOT_PROOF)
        untrustworthy = True
    if db_unavailable:
        reasons.append(REASON_DB_UNAVAILABLE)
        untrustworthy = True
    if checkpoint_in_worktree:
        reasons.append(REASON_CHECKPOINT_IN_WORKTREE)
        untrustworthy = True
    if checkpoint_conflict:
        reasons.append(REASON_CHECKPOINT_CONFLICT)
        untrustworthy = True
    if checkpoint_inconsistent:
        reasons.append(REASON_CHECKPOINT_INCONSISTENT)
        untrustworthy = True
    if schema_drift:
        reasons.append(REASON_SCHEMA_DRIFT)
        untrustworthy = True
    if illegal_page_size:
        reasons.append(REASON_ILLEGAL_PAGE_SIZE)
        reasons.append(REASON_INTERNAL_DEFECT)
        untrustworthy = True
    if missing_source_timestamp:
        reasons.append(REASON_MISSING_SOURCE_TIMESTAMP)
        untrustworthy = True
    if timer_delayed:
        reasons.append(REASON_TIMER_DELAYED)
    if lock_busy_no_close:
        reasons.append(REASON_LOCK_BUSY_NO_CLOSE)
    if upstream_unavailable:
        reasons.append(REASON_UPSTREAM_UNAVAILABLE)
    if material_incomplete_window:
        reasons.append(REASON_WINDOW_INCOMPLETE)
    if pagination_incomplete:
        reasons.append(REASON_PAGINATION_INCOMPLETE)
    if current_lag_hours is not None and current_lag_hours > hard_guardrail_hours:
        reasons.append(REASON_LAG_ABOVE_HARD_GUARDRAIL)
    elif current_lag_hours is not None and current_lag_hours > operational_target_hours:
        reasons.append(REASON_LAG_ABOVE_OPERATIONAL_TARGET)

    reasons = _unique(reasons)
    if untrustworthy:
        return "UNKNOWN", reasons
    if material_incomplete_window or pagination_incomplete:
        return "STALE", reasons
    if current_lag_hours is None:
        reasons = _unique([*reasons, REASON_MISSING_EVIDENCE])
        return "UNKNOWN", reasons
    if current_lag_hours > hard_guardrail_hours:
        reasons = _unique([*reasons, REASON_LAG_ABOVE_HARD_GUARDRAIL])
        return "STALE", reasons
    if lock_busy_no_close:
        # systemd SuccessExitStatus=75 must not mint FRESH / a closed window.
        return "DEGRADED", reasons
    if current_lag_hours > operational_target_hours:
        reasons = _unique([*reasons, REASON_LAG_ABOVE_OPERATIONAL_TARGET])
        return "DEGRADED", reasons
    if cadence_max_inter_run_hours > hard_guardrail_hours:
        return "STALE", reasons
    if cadence_max_inter_run_hours > operational_target_hours:
        return "DEGRADED", reasons
    return "FRESH", reasons


def health_exit(status: str) -> int:
    if status == "FRESH":
        return 0
    if status == "DEGRADED":
        return 1
    return 2


def slo_block(cadence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    resolved = dict(cadence) if cadence is not None else load_shipped_cadence()
    max_hours = float(resolved.get("max_inter_run_hours") or TIMER_MAX_INTER_RUN_HOURS)
    timezone = resolved.get("timezone")
    on_calendar = str(resolved.get("on_calendar") or TIMER_ON_CALENDAR)
    sustainable_hard = max_hours <= DESIRED_HARD_GUARDRAIL_HOURS
    sustainable_ops = max_hours <= DESIRED_OPERATIONAL_TARGET_HOURS
    if timezone in EXPLICIT_TIMEZONES or str(timezone or "").startswith("America/"):
        tz_note = f"explicit {timezone}"
    else:
        tz_note = "unit does not set an explicit timezone; host local clock is ambiguous"
    if sustainable_hard and sustainable_ops:
        honest = (
            f"pncp-contracts.timer OnCalendar={on_calendar} (max inter-run {max_hours}h). "
            "HARD <=24h and 95% <=6h are sustainable on this calendar if a run finishes "
            "inside the remaining slack (measured incremental ~21min vs 4h slot)."
        )
    elif sustainable_hard:
        honest = (
            f"pncp-contracts.timer OnCalendar={on_calendar} (max inter-run {max_hours}h) "
            "meets HARD <=24h but cannot honestly set sustainable_operational_target "
            "for 95% <=6h."
        )
    else:
        honest = (
            f"pncp-contracts.timer OnCalendar={on_calendar} (max inter-run {max_hours}h) "
            "cannot meet 95% <=6h nor 100% <=24h. Status is evaluated against the desired "
            "6h/24h SLOs and will not claim FRESH when the timer cannot meet them."
        )
    return {
        "desired_operational_target_hours": DESIRED_OPERATIONAL_TARGET_HOURS,
        "desired_operational_percentile": DESIRED_OPERATIONAL_PERCENTILE,
        "desired_hard_guardrail_hours": DESIRED_HARD_GUARDRAIL_HOURS,
        "timer_unit": TIMER_UNIT,
        "timer_on_calendar": on_calendar,
        "timer_timezone_note": tz_note,
        "timer_max_inter_run_hours": max_hours,
        "timer_persistent": bool(resolved.get("persistent", TIMER_PERSISTENT)),
        "sustainable_operational_target": sustainable_ops,
        "sustainable_hard_guardrail": sustainable_hard,
        "honest_note": honest,
    }


def resolve_effective_cadence(timer: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Shipped calendar is the policy. A worse live OnCalendar stays fail-closed."""
    shipped = load_shipped_cadence()
    live_spec = str((timer or {}).get("on_calendar") or "").strip()
    if not live_spec:
        return {**shipped, "source": "shipped"}
    live = parse_oncalendar_spec(live_spec)
    live["persistent"] = shipped.get("persistent")
    if float(live["max_inter_run_hours"]) > float(shipped["max_inter_run_hours"]):
        return {**live, "source": "live_worse_than_shipped"}
    return {**shipped, "source": "shipped", "live_on_calendar": live_spec}


def build_contract(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Build the versioned artifact from a collected or fixture snapshot."""
    as_of = parse_dt(snapshot.get("as_of")) or datetime.now(UTC)
    timer = dict(snapshot.get("timer") or {})
    cadence = resolve_effective_cadence(timer)
    checkpoint = dict(snapshot.get("checkpoint") or {})
    db = dict(snapshot.get("db") or {})
    evidence_only = dict(snapshot.get("evidence_only") or {})
    windows = list(snapshot.get("windows") or [])
    spot_checks = list(snapshot.get("spot_checks") or [])
    extra_reasons = [str(r) for r in (snapshot.get("reason_codes") or [])]

    closed = [
        w
        for w in windows
        if isinstance(w, dict) and str(w.get("status") or "").lower() in {"completed", "complete", "success"}
    ]
    incomplete = [
        w
        for w in windows
        if isinstance(w, dict)
        and str(w.get("status") or "").lower() in {"failed", "blocked", "incomplete", "partial", "partial_or_failed"}
    ]
    latest_closed = closed[-1] if closed else None
    completed_keys = [str(w.get("window_key")) for w in closed if w.get("window_key")]
    for key in checkpoint.get("completed_windows") or []:
        text = str(key)
        if text and text not in completed_keys:
            completed_keys.append(text)
    blocked = [str(k) for k in (checkpoint.get("blocked_windows") or [])]
    failed = [str(k) for k in (checkpoint.get("failed_windows") or [])]
    unresolved = [k for k in [*blocked, *failed] if k]
    oldest_gap = unresolved[0] if unresolved else None
    material_incomplete = False
    for gap in unresolved:
        if not window_fully_covered(gap, completed_keys):
            material_incomplete = True
            extra_reasons.append(REASON_WINDOW_INCOMPLETE)
            break
    for w in incomplete:
        key = str(w.get("window_key") or "")
        if key and not window_fully_covered(key, completed_keys):
            material_incomplete = True
        if str(w.get("error") or "").startswith("source_population_drift"):
            extra_reasons.append(REASON_SOURCE_POPULATION_DRIFT)

    pages_expected = latest_closed.get("pages_expected") if latest_closed else snapshot.get("pages_expected")
    pages_fetched = latest_closed.get("pages_fetched") if latest_closed else snapshot.get("pages_fetched")
    pagination_incomplete = False
    if pages_expected is not None and pages_fetched is not None:
        try:
            pagination_incomplete = int(pages_expected) != int(pages_fetched)
        except (TypeError, ValueError):
            pagination_incomplete = True
            extra_reasons.append(REASON_PAGINATION_INCOMPLETE)

    closed_at = last_successful_close_at(
        latest_closed=latest_closed,
        snapshot=snapshot,
        completed_keys=completed_keys,
    )
    current_lag_hours = None
    if closed_at is not None:
        current_lag_hours = (as_of - closed_at).total_seconds() / 3600.0
    elif snapshot.get("current_lag_hours") is not None:
        current_lag_hours = float(snapshot["current_lag_hours"])

    lags = [float(x) for x in (snapshot.get("lags_hours") or [])]
    percentiles = lag_percentiles(lags)

    source_at = parse_dt(
        snapshot.get("source_publication_or_update_at") or db.get("latest_source_publication_or_update_at")
    )
    first_observed = parse_dt(snapshot.get("first_observed_at") or db.get("latest_first_seen_at"))
    persisted = parse_dt(snapshot.get("persisted_at") or db.get("latest_ingested_at") or closed_at)

    has_evidence = bool(snapshot.get("has_evidence", True))
    if not closed and not snapshot.get("has_evidence"):
        has_evidence = False
    if evidence_only.get("timer_active") and not closed:
        has_evidence = False
    timer_active_only = bool(evidence_only.get("timer_active"))
    http_200_only = bool(evidence_only.get("http_200"))
    single_row_only = bool(evidence_only.get("single_recent_row"))
    db_unavailable = db.get("available") is False
    schema_drift = (
        classify_schema(db.get("columns") or REQUIRED_CONTRACT_COLUMNS) is not None
        if db.get("columns") is not None
        else bool(db.get("schema_drift"))
    )
    if db.get("columns") is not None and schema_drift:
        extra_reasons.append(REASON_SCHEMA_DRIFT)

    if source_at is None and persisted is not None and not snapshot.get("allow_missing_source_ts"):
        extra_reasons.append(REASON_MISSING_SOURCE_TIMESTAMP)

    last_run_at = parse_dt(timer.get("last_run_at"))
    next_run_at = parse_dt(timer.get("next_run_at"))
    cadence_max = float(cadence.get("max_inter_run_hours") or TIMER_MAX_INTER_RUN_HOURS)
    timer_delayed = False
    if next_run_at is not None and next_run_at < as_of - timedelta(minutes=10):
        timer_delayed = True
        extra_reasons.append(REASON_MISSED_TIMER)
    if last_run_at is not None and (as_of - last_run_at).total_seconds() / 3600.0 > cadence_max + 1:
        timer_delayed = True
    if snapshot.get("reboot_without_persistent"):
        extra_reasons.append(REASON_REBOOT_CATCHUP_REQUIRED)
        timer_delayed = True
    exec_status = timer.get("last_exec_status")
    try:
        exec_status_i = int(exec_status) if exec_status is not None and str(exec_status) != "" else None
    except (TypeError, ValueError):
        exec_status_i = None
    if exec_status_i == LOCK_BUSY_EXIT or bool(timer.get("lock_busy")):
        extra_reasons.append(REASON_LOCK_BUSY_NO_CLOSE)
    if not cadence.get("timezone_explicit", bool(cadence.get("timezone"))):
        extra_reasons.append(REASON_TIMER_TIMEZONE_AMBIGUOUS)

    if not closed and last_run_at is not None:
        extra_reasons.append(REASON_UNCLOSED_CURRENT_WINDOW)

    backup = dict(snapshot.get("backup") or {})
    backup_reason = classify_backup(
        available=backup.get("available"),
        restore_hash_identical=backup.get("restore_hash_identical"),
        latest_age_hours=backup.get("latest_age_hours"),
        max_age_hours=float(backup.get("max_age_hours") or 28.0),
    )
    if backup_reason:
        extra_reasons.append(backup_reason)

    status, reasons = classify_status(
        has_evidence=has_evidence and not timer_active_only and not http_200_only and not single_row_only,
        current_lag_hours=current_lag_hours,
        material_incomplete_window=material_incomplete,
        pagination_incomplete=pagination_incomplete,
        timer_active_only=timer_active_only,
        http_200_only=http_200_only,
        single_recent_row_only=single_row_only,
        db_unavailable=db_unavailable,
        upstream_unavailable=bool(snapshot.get("upstream_unavailable")),
        checkpoint_in_worktree=bool(checkpoint.get("in_worktree")),
        checkpoint_conflict=bool(checkpoint.get("conflict")),
        checkpoint_inconsistent=bool(checkpoint.get("inconsistent")),
        schema_drift=schema_drift,
        illegal_page_size=bool(snapshot.get("illegal_page_size")),
        missing_source_timestamp=REASON_MISSING_SOURCE_TIMESTAMP in extra_reasons and source_at is None,
        timer_delayed=timer_delayed,
        lock_busy_no_close=REASON_LOCK_BUSY_NO_CLOSE in extra_reasons,
        extra_reasons=extra_reasons,
        cadence_max_inter_run_hours=cadence_max,
    )

    latest_window = None
    if latest_closed:
        latest_window = latest_closed.get("window_key") or latest_closed.get("source_window")
    elif completed_keys:
        latest_window = completed_keys[-1]

    counts = {
        "expected": (latest_closed or {}).get("expected"),
        "fetched": (latest_closed or {}).get("fetched"),
        "persisted": (latest_closed or {}).get("persisted"),
        "deduplicated": (latest_closed or {}).get("deduplicated") or (latest_closed or {}).get("skipped"),
        "failed": (latest_closed or {}).get("failed") or (latest_closed or {}).get("page_errors") or 0,
        "pages_expected": pages_expected,
        "pages_fetched": pages_fetched,
    }

    artifact = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "reason_codes": reasons,
        "as_of": as_of.isoformat().replace("+00:00", "Z"),
        "deployed_sha": snapshot.get("deployed_sha"),
        "policy_version": snapshot.get("policy_version")
        or f"{TIMER_UNIT}/{cadence.get('on_calendar') or TIMER_ON_CALENDAR}",
        "slo": slo_block(cadence),
        "source_publication_or_update_at": source_at.isoformat().replace("+00:00", "Z") if source_at else None,
        "first_observed_at": first_observed.isoformat().replace("+00:00", "Z") if first_observed else None,
        "persisted_at": persisted.isoformat().replace("+00:00", "Z") if persisted else None,
        "run_id": snapshot.get("run_id") or checkpoint.get("attempt_run_id") or (latest_closed or {}).get("run_id"),
        "attempt_id": snapshot.get("attempt_id") or checkpoint.get("attempt_run_id"),
        "source_window": (latest_closed or {}).get("source_window") or snapshot.get("source_window") or latest_window,
        "expected": counts["expected"],
        "fetched": counts["fetched"],
        "persisted": counts["persisted"],
        "deduplicated": counts["deduplicated"],
        "failed": counts["failed"],
        "pages_expected": counts["pages_expected"],
        "pages_fetched": counts["pages_fetched"],
        "checkpoint_before": checkpoint.get("before"),
        "checkpoint_after": checkpoint.get("after")
        or {
            "path": checkpoint.get("path"),
            "sha256": checkpoint.get("sha256"),
            "completed_windows": checkpoint.get("completed_windows"),
            "blocked_windows": checkpoint.get("blocked_windows"),
            "logical_job_id": checkpoint.get("logical_job_id"),
            "attempt_run_id": checkpoint.get("attempt_run_id"),
        },
        "latest_successful_closed_window": latest_window,
        "oldest_unresolved_gap": oldest_gap,
        "unresolved_window_count": len(unresolved),
        "current_lag_hours": current_lag_hours,
        "lag_p50_hours": percentiles["p50"],
        "lag_p95_hours": percentiles["p95"],
        "lag_p99_hours": percentiles["p99"],
        "lag_sample_n": percentiles["n"],
        "last_run_at": last_run_at.isoformat().replace("+00:00", "Z") if last_run_at else None,
        "next_run_at": next_run_at.isoformat().replace("+00:00", "Z") if next_run_at else None,
        "last_error": checkpoint.get("last_error") or snapshot.get("last_error"),
        "timer": timer,
        "spot_checks": spot_checks,
        "checkpoint_health": {
            "path": checkpoint.get("path"),
            "sha256": checkpoint.get("sha256"),
            "ok": not bool(
                checkpoint.get("inconsistent") or checkpoint.get("in_worktree") or checkpoint.get("conflict")
            ),
            "in_worktree": bool(checkpoint.get("in_worktree")),
            "conflict": bool(checkpoint.get("conflict")),
            "inconsistent": bool(checkpoint.get("inconsistent")),
            "uid": checkpoint.get("uid"),
            "gid": checkpoint.get("gid"),
            "logical_job_id": checkpoint.get("logical_job_id"),
            "updated_at": checkpoint.get("updated_at"),
        },
        "backup_freshness": {
            "available": backup.get("available"),
            "latest_age_hours": backup.get("latest_age_hours"),
            "restore_hash_identical": backup.get("restore_hash_identical"),
            "reason_code": backup_reason,
        },
        "health_exit": health_exit(status),
        "campaign_verdict_hint": _verdict_hint(status, has_live=bool(snapshot.get("live"))),
    }
    return artifact


def _verdict_hint(status: str, *, has_live: bool) -> str:
    if not has_live:
        return "BLOCKED_ON_LIVE_HOST_EVIDENCE"
    if status == "FRESH":
        return "FRESHNESS_CERTIFIED"
    return "FRESHNESS_DEGRADED"


def _run(cmd: list[str], timeout: int = 20) -> str:
    try:
        out = subprocess.check_output(cmd, timeout=timeout, stderr=subprocess.DEVNULL)  # noqa: S603
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.decode("utf-8", errors="replace").strip()


def _deployed_sha(repo: Path | None = None) -> str | None:
    env = (os.getenv("EXTRA_DEPLOYED_SHA") or os.getenv("GIT_SHA") or "").strip()
    if env:
        return env
    root = repo or _PROJECT_ROOT
    text = _run(["git", "-C", str(root), "rev-parse", "HEAD"])
    return text or None


def _systemctl_show(unit: str) -> dict[str, str]:
    raw = _run(["systemctl", "show", unit, "--no-pager"])
    parsed: dict[str, str] = {}
    for line in raw.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed[key] = value
    return parsed


def collect_checkpoint_snapshot(
    *,
    requested: str | Path | None = None,
    production: bool | None = None,
    repo_root: Path | None = None,
    state_root: Path | None = None,
) -> dict[str, Any]:
    repo = repo_root or _PROJECT_ROOT
    try:
        path = resolve_checkpoint_dir(
            requested,
            production=production,
            repo_root=repo,
            state_root=state_root,
        )
        in_worktree = False
        conflict = False
    except CheckpointLocationError as exc:
        return {
            "path": str(requested or ""),
            "in_worktree": "worktree" in str(exc) or "release tree" in str(exc),
            "conflict": True,
            "inconsistent": True,
            "error": str(exc),
        }
    diag = diagnose(path)
    payload: dict[str, Any] = {
        "path": diag.path,
        "exists": diag.exists,
        "ok": diag.ok,
        "in_worktree": in_worktree,
        "conflict": conflict,
        "inconsistent": not diag.ok,
        "issues": diag.issues,
        "completed_windows": diag.completed_windows,
        "raw_meta": diag.raw_meta,
    }
    file_path = Path(diag.path)
    if file_path.is_file():
        raw = file_path.read_bytes()
        payload["sha256"] = hashlib.sha256(raw).hexdigest()
        st = file_path.stat()
        payload["mode"] = oct(stat.S_IMODE(st.st_mode))
        payload["uid"] = st.st_uid
        payload["gid"] = st.st_gid
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            payload["inconsistent"] = True
            return payload
        meta = dict(data.get("meta") or {})
        payload["before"] = {
            "completed_windows": list(data.get("completed_windows") or []),
            "attempt_run_id": meta.get("attempt_run_id") or meta.get("run_id"),
        }
        payload["after"] = payload["before"]
        payload["completed_windows"] = list(data.get("completed_windows") or [])
        payload["blocked_windows"] = list(data.get("blocked_windows") or [])
        payload["failed_windows"] = list(data.get("failed_windows") or [])
        payload["logical_job_id"] = meta.get("logical_job_id")
        payload["attempt_run_id"] = meta.get("attempt_run_id") or meta.get("run_id")
        payload["last_error"] = data.get("last_error")
        payload["updated_at"] = data.get("updated_at")
        payload["window_results"] = data.get("window_results") or {}
        if meta.get("logical_job_id") and meta.get("logical_job_id") != LOGICAL_JOB_ID:
            payload["conflict"] = True
    return payload


def collect_timer_snapshot(
    *,
    show_timer: Mapping[str, str] | None = None,
    show_service: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    timer = dict(show_timer) if show_timer is not None else _systemctl_show(TIMER_UNIT)
    service = dict(show_service) if show_service is not None else _systemctl_show(SERVICE_UNIT)
    last_raw = service.get("ExecMainStartTimestamp") or timer.get("LastTriggerUSec")
    next_raw = timer.get("NextElapseUSecRealtime") or timer.get("NextElapseUSec")
    last_run = _iso_z(last_raw)
    next_run = _iso_z(next_raw)
    status_raw = service.get("ExecMainStatus") or ""
    return {
        "unit": TIMER_UNIT,
        "active": timer.get("ActiveState") == "active",
        "enabled": timer.get("UnitFileState") == "enabled" or "enabled" in (timer.get("ActiveState") or ""),
        "last_run_at": last_run,
        "next_run_at": next_run,
        "last_result": service.get("Result"),
        "last_exec_status": int(status_raw) if status_raw.isdigit() else None,
        "on_calendar": TIMER_ON_CALENDAR,
        "timezone": TIMER_TIMEZONE,
        "persistent": TIMER_PERSISTENT,
        "lock_busy": status_raw.isdigit() and int(status_raw) == LOCK_BUSY_EXIT,
        "raw_last_run_at": last_raw or None,
        "raw_next_run_at": next_raw or None,
    }


def _psycopg2_connect(dsn: str) -> Any:
    import psycopg2

    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    return conn


def collect_db_snapshot(
    *,
    dsn: str | None = None,
    connect: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Read source/first_seen/ingested timestamps from pncp_supplier_contracts."""
    effective = (dsn or os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL") or "").strip()
    if not effective:
        return {"available": False, "columns": None, "error": "NO_DSN"}
    connect_fn = connect or _psycopg2_connect
    conn: Any = None
    try:
        conn = connect_fn(effective)
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position
                """,
                ("pncp_supplier_contracts",),
            )
            col_rows = cur.fetchall() or []
            columns: list[str] = []
            for row in col_rows:
                if isinstance(row, dict):
                    columns.append(str(row.get("column_name") or next(iter(row.values()))))
                elif isinstance(row, (tuple, list)):
                    columns.append(str(row[0]))
                else:
                    columns.append(str(row))
            have = set(columns)
            missing = classify_schema(columns)
            wanted = {
                "ingested_at": "latest_ingested_at",
                "first_seen_at": "latest_first_seen_at",
                "data_publicacao_fonte": "max_data_publicacao_fonte",
                "data_atualizacao_fonte": "max_data_atualizacao_fonte",
                "data_publicacao": "max_data_publicacao",
            }
            select_parts = ["COUNT(*) AS row_count"]
            for column, alias in wanted.items():
                if column in have:
                    select_parts.append(f"MAX({column}) AS {alias}")
            # Identifiers come from the allowlisted `wanted` map, never user input.
            agg_sql = "SELECT " + ", ".join(select_parts) + " FROM pncp_supplier_contracts"  # noqa: S608
            cur.execute(agg_sql)
            fetched = cur.fetchone() or {}
            if isinstance(fetched, (tuple, list)):
                keys = ["row_count"] + [wanted[c] for c in wanted if c in have]
                fetched = dict(zip(keys, fetched, strict=False))
            payload = dict(fetched) if isinstance(fetched, dict) else {}
        finally:
            close = getattr(cur, "close", None)
            if callable(close):
                close()
    except Exception as exc:
        return {"available": False, "columns": None, "error": str(exc)}
    finally:
        if conn is not None:
            closer = getattr(conn, "close", None)
            if callable(closer):
                closer()

    ingested = _iso_z(payload.get("latest_ingested_at"))
    first_seen = _iso_z(payload.get("latest_first_seen_at")) or ingested
    source = _iso_z(
        payload.get("max_data_atualizacao_fonte")
        or payload.get("max_data_publicacao_fonte")
        or payload.get("max_data_publicacao")
    )
    return {
        "available": True,
        "columns": columns,
        "schema_drift": missing is not None,
        "row_count": int(payload.get("row_count") or 0),
        "latest_ingested_at": ingested,
        "latest_first_seen_at": first_seen,
        "latest_source_publication_or_update_at": source,
        "error": None,
    }


def collect_snapshot(
    *,
    live: bool = False,
    snapshot_path: Path | None = None,
    evidence_path: Path | None = None,
    checkpoint_dir: str | Path | None = None,
    production: bool | None = None,
    repo_root: Path | None = None,
    state_root: Path | None = None,
    dsn: str | None = None,
    connect: Callable[[str], Any] | None = None,
    timer: Mapping[str, Any] | None = None,
    as_of: datetime | None = None,
    backup: Mapping[str, Any] | None = None,
    backup_local_dir: str | Path | None = None,
    backup_offsite_dir: str | Path | None = None,
    restore_proof_path: str | Path | None = None,
) -> dict[str, Any]:
    if snapshot_path is not None:
        data = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("snapshot root must be object")
        data.setdefault("live", live)
        return data

    now = as_of or datetime.now(UTC)
    evidence_json = (
        Path(evidence_path) if evidence_path is not None else Path("output/contracts/incremental-latest.json")
    )
    evidence: dict[str, Any] = {}
    if evidence_json.is_file():
        try:
            loaded = json.loads(evidence_json.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                evidence = loaded
        except json.JSONDecodeError:
            evidence = {}

    checkpoint = collect_checkpoint_snapshot(
        requested=checkpoint_dir,
        production=production,
        repo_root=repo_root,
        state_root=state_root,
    )
    timer_snap = dict(timer) if timer is not None else collect_timer_snapshot()
    windows = list(evidence.get("windows") or [])
    if not windows and checkpoint.get("window_results"):
        for key, result in dict(checkpoint["window_results"]).items():
            terminal = str((result or {}).get("terminal") or "").upper()
            status = "completed" if terminal == "COMPLETE" else terminal.lower() or "unknown"
            pages = (result or {}).get("pages")
            windows.append(
                {
                    "window_key": key,
                    "status": status,
                    "expected": (result or {}).get("expected"),
                    "fetched": (result or {}).get("fetched"),
                    "persisted": (result or {}).get("persisted"),
                    "deduplicated": (result or {}).get("skipped"),
                    "failed": (result or {}).get("page_errors") or 0,
                    "pages_expected": pages,
                    "pages_fetched": pages,
                    "closed_at": ((result or {}).get("closed_at") if terminal == "COMPLETE" else None),
                }
            )
    for window in windows:
        if window.get("pages_expected") is None and window.get("pages") is not None:
            window["pages_expected"] = window["pages"]
        if window.get("pages_fetched") is None and window.get("pages") is not None:
            window["pages_fetched"] = window["pages"]
        if window.get("status") == "completed" and not window.get("closed_at"):
            evidence_ok = str(evidence.get("status") or "").lower() in {"success", "completed", "complete", ""}
            if evidence_ok and not checkpoint.get("last_error"):
                window["closed_at"] = evidence.get("completed_at")
        if window.get("window_key") and not window.get("source_window"):
            span = parse_window_key(str(window["window_key"]))
            if span:
                window["source_window"] = {"start": span[0].isoformat(), "end": span[1].isoformat()}

    db = collect_db_snapshot(dsn=dsn, connect=connect)
    backup_snap = (
        dict(backup)
        if backup is not None
        else collect_backup_snapshot(
            as_of=now,
            local_dir=backup_local_dir,
            offsite_dir=backup_offsite_dir,
            restore_proof_path=restore_proof_path,
        )
    )
    snapshot = {
        "as_of": now.isoformat().replace("+00:00", "Z"),
        "live": live,
        "has_evidence": bool(windows) or bool(checkpoint.get("completed_windows")),
        "deployed_sha": evidence.get("git_sha") or _deployed_sha(repo_root),
        "policy_version": f"{TIMER_UNIT}/{TIMER_ON_CALENDAR}",
        "run_id": evidence.get("run_id") or checkpoint.get("attempt_run_id"),
        "attempt_id": checkpoint.get("attempt_run_id"),
        "timer": timer_snap,
        "checkpoint": checkpoint,
        "windows": windows,
        "db": db,
        "backup": backup_snap,
        "source_publication_or_update_at": db.get("latest_source_publication_or_update_at"),
        "first_observed_at": db.get("latest_first_seen_at"),
        "persisted_at": db.get("latest_ingested_at"),
        "last_error": checkpoint.get("last_error") or (evidence.get("errors") or [None])[0],
        "lags_hours": [],
        "evidence_only": {
            "timer_active": bool(timer_snap.get("active")) and not windows,
            "http_200": False,
            "single_recent_row": False,
        },
    }
    return snapshot


def evaluate_for_alerts(contract: Mapping[str, Any]) -> tuple[int, str, str]:
    """Return (severity, title, message) for check-alerts. 0=info, 1=warn, 2=crit."""
    status = str(contract.get("status") or "UNKNOWN")
    reasons = ",".join(contract.get("reason_codes") or [])
    lag = contract.get("current_lag_hours")
    lag_txt = f"{lag:.1f}h" if isinstance(lag, (int, float)) else "unknown"
    title = f"PNCP contracts freshness {status}"
    message = (
        f"status={status} lag={lag_txt} closed={contract.get('latest_successful_closed_window')} "
        f"gaps={contract.get('unresolved_window_count')} next={contract.get('next_run_at')} "
        f"last_error={contract.get('last_error')} "
        f"backup={((contract.get('backup_freshness') or {}).get('reason_code') or ((contract.get('backup_freshness') or {}).get('available')))} "
        f"checkpoint_ok={((contract.get('checkpoint_health') or {}).get('ok'))} reasons={reasons}"
    )
    if status == "FRESH":
        return 0, title, message
    if status == "DEGRADED":
        return 1, title, message
    return 2, title, message


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-snapshot", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--health", action="store_true", help="exit with freshness health code")
    parser.add_argument("--live", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    snapshot = collect_snapshot(live=args.live, snapshot_path=args.from_snapshot)
    contract = build_contract(snapshot)
    text = json.dumps(contract, ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    if args.json or args.output is None:
        print(text)
    if args.health:
        return int(contract["health_exit"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
