"""Tests for #317 ingest / report / backup isolation admission."""

from __future__ import annotations

from scripts.national_contract_truth.workload_isolation import (
    CalendarEvent,
    HostPressure,
    IsolationLimits,
    SessionSettings,
    admit_ingest,
)

SESSION = SessionSettings(
    application_name="pncp-contracts",
    statement_timeout_ms=30_000,
    lock_timeout_ms=5_000,
    idle_in_transaction_session_timeout_ms=15_000,
    max_connections=8,
)
LIMITS = IsolationLimits(
    cpu_quota_percent=40,
    memory_max_mb=2048,
    io_weight=100,
    worker_limit=2,
    slice="extra-ingest.slice",
)


def test_overlap_with_backup_reschedules_and_is_not_success() -> None:
    report = admit_ingest(
        workload="national_ingest",
        job_start="02:00",
        job_end="04:00",
        calendar=(CalendarEvent("backup", "03:00", "05:00"),),
        session=SESSION,
        limits=LIMITS,
        pressure=HostPressure(
            disk_free_ratio=0.5,
            cpu_util=0.2,
            checkpoint_intact=True,
            last_approved_snapshot_readable=True,
        ),
    )
    assert report["decision"] == "RESCHEDULE"
    assert report["success"] is False
    assert report["false_success"] is False
    assert report["claim_vps_isolated"] is False
    assert report["soak_seal"] == "UNPROVEN"


def test_overload_pauses_with_intact_checkpoint() -> None:
    report = admit_ingest(
        workload="pncp_contracts",
        job_start="10:00",
        job_end="12:00",
        calendar=(),
        session=SESSION,
        limits=LIMITS,
        pressure=HostPressure(
            disk_free_ratio=0.05,
            cpu_util=0.95,
            checkpoint_intact=True,
            last_approved_snapshot_readable=True,
        ),
    )
    assert report["decision"] == "PAUSE"
    assert report["checkpoint_intact"] is True
    assert report["success"] is False
    assert "disk_pressure" in report["blockers"]


def test_admit_requires_session_settings_and_readable_snapshot() -> None:
    ok = admit_ingest(
        workload="national_ingest",
        job_start="10:00",
        job_end="11:00",
        calendar=(),
        session=SESSION,
        limits=LIMITS,
        pressure=HostPressure(
            disk_free_ratio=0.4,
            cpu_util=0.3,
            checkpoint_intact=True,
            last_approved_snapshot_readable=True,
            soak_ran=True,
        ),
    )
    assert ok["decision"] == "ADMIT"
    assert ok["success"] is True
    assert ok["session"]["application_name"] == "pncp-contracts"
    assert ok["session"]["statement_timeout"] == 30_000
    assert ok["soak_seal"] == "PROVEN"
    blocked = admit_ingest(
        workload="national_ingest",
        job_start="10:00",
        job_end="11:00",
        calendar=(),
        session=SESSION,
        limits=LIMITS,
        pressure=HostPressure(
            disk_free_ratio=0.4,
            cpu_util=0.3,
            checkpoint_intact=True,
            last_approved_snapshot_readable=False,
        ),
    )
    assert blocked["decision"] == "REFUSE"
    assert blocked["success"] is False
    assert "approved_snapshot_unreadable" in blocked["blockers"]
    assert blocked["soak_seal"] == "UNPROVEN"


def test_overnight_job_overlaps_backup_and_unknown_stays_refuse() -> None:
    overnight = admit_ingest(
        workload="national_ingest",
        job_start="22:00",
        job_end="06:00",
        calendar=(CalendarEvent("backup", "03:00", "05:00"),),
        session=SESSION,
        limits=LIMITS,
        pressure=HostPressure(
            disk_free_ratio=0.5,
            cpu_util=0.2,
            checkpoint_intact=True,
            last_approved_snapshot_readable=True,
        ),
    )
    assert overnight["decision"] == "RESCHEDULE"
    assert overnight["success"] is False
    assert any(b.startswith("calendar_overlap") for b in overnight["blockers"])

    unknown = admit_ingest(
        workload="reports",
        job_start="22:00",
        job_end="06:00",
        calendar=(CalendarEvent("backup", "03:00", "05:00"),),
        session=SESSION,
        limits=LIMITS,
        pressure=HostPressure(
            disk_free_ratio=0.05,
            cpu_util=0.95,
            checkpoint_intact=True,
            last_approved_snapshot_readable=True,
        ),
    )
    assert unknown["decision"] == "REFUSE"
    assert unknown["success"] is False
    assert any(b.startswith("unknown_workload") for b in unknown["blockers"])
    assert any(b.startswith("calendar_overlap") for b in unknown["blockers"])
    assert "disk_pressure" in unknown["blockers"]
