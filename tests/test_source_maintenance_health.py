"""Source/target maintenance liveness and readback regressions."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from scripts import health_check
from scripts.confenge_target_fit.status import (
    dirty_progress_stale,
    target_fit_progress_watermark,
)
from scripts.confenge_target_fit.store import max_current_watermark
from scripts.ops.source_maintenance_health import (
    DECOUPLED_ON_SUCCESS,
    HEALTH_TIMER,
    PNCP_SERVICE,
    PNCP_TIMER,
    READBACK_UNITS,
    SOURCE_FRESHNESS_SERVICE,
    TARGET_FIT_RECONCILE_SERVICE,
    TARGET_FIT_RECONCILE_TIMER,
    TARGET_FIT_REFRESH_TIMER,
    TARGET_FIT_WORKER,
    TIMER_TO_SERVICE,
    build_contract,
    sanitize_error,
)

NOW = datetime(2026, 8, 27, 15, 0, tzinfo=UTC)
SHA = "c02aad71259f13d2f019939442a1bca469344760"
ROOT = Path(__file__).resolve().parents[1]


def _timer_state() -> dict[str, str]:
    return {
        "LoadState": "loaded",
        "UnitFileState": "enabled",
        "ActiveState": "active",
        "SubState": "waiting",
        "Persistent": "yes",
        "NextElapseUSecRealtime": "Thu 2026-08-27 16:03:00 -03",
        "StopWhenUnneeded": "no",
        "Requires": "",
        "Requisite": "",
        "BindsTo": "",
        "PartOf": "",
        "Conflicts": "",
        "PropagatesStopTo": "",
    }


def _snapshot() -> dict:
    units = {unit: {"LoadState": "loaded"} for unit in READBACK_UNITS}
    for timer in TIMER_TO_SERVICE:
        units[timer] = _timer_state()
    units[TARGET_FIT_WORKER].update(
        {"UnitFileState": "enabled", "ActiveState": "active", "SubState": "running"}
    )
    for source in DECOUPLED_ON_SUCCESS:
        units[source]["OnSuccess"] = ""
    return {
        "as_of": NOW.isoformat(),
        "release_sha": SHA,
        "units": units,
        "progress_max_age_seconds": {
            "worker": 1800,
            "refresh": 5400,
            "reconcile": 111600,
        },
        "progress": {
            "worker": {
                "last_success_at": "2026-08-27T14:59:40Z",
                "latest_attempt": {"status": "success", "cycle_id": "worker-live"},
            },
            "refresh": {
                "last_success_at": "2026-08-27T14:31:55Z",
                "latest_attempt": {"status": "success", "cycle_id": "refresh-live"},
            },
            "reconcile": {
                "last_success_at": "2026-08-27T11:10:28Z",
                "latest_attempt": {"status": "success", "cycle_id": "reconcile-live"},
            },
        },
    }


def test_healthy_readback_has_exact_release_and_per_kind_progress() -> None:
    contract = build_contract(_snapshot())

    assert contract["status"] == "HEALTHY"
    assert contract["health_exit"] == 0
    assert contract["release_sha"] == SHA
    assert set(contract["progress"]) == {"worker", "refresh", "reconcile"}
    assert contract["progress"]["worker"]["age_seconds"] == 20


def test_worker_refresh_reconcile_each_alarm_independently() -> None:
    for kind in ("worker", "refresh", "reconcile"):
        snapshot = _snapshot()
        snapshot["progress"][kind]["last_success_at"] = "2026-08-25T00:00:00Z"
        contract = build_contract(snapshot)
        assert f"TARGET_FIT_{kind.upper()}_PROGRESS_STALE" in contract["reason_codes"]
        assert contract["health_exit"] == 2


def test_latest_failure_is_reported_without_erasing_last_good() -> None:
    snapshot = _snapshot()
    snapshot["progress"]["refresh"] = {
        "last_success_at": "2026-08-27T14:31:55Z",
        "latest_attempt": {
            "status": "failed",
            "cycle_id": "refresh-failed",
            "error": "lock busy",
        },
    }
    contract = build_contract(snapshot)

    assert "TARGET_FIT_REFRESH_LAST_CYCLE_FAILED" in contract["reason_codes"]
    assert contract["progress"]["refresh"]["last_success_at"] == "2026-08-27T14:31:55Z"
    assert contract["progress"]["refresh"]["latest_attempt"]["error"] == "lock busy"


def test_failed_oneshot_does_not_demote_a_live_timer() -> None:
    snapshot = _snapshot()
    snapshot["units"][PNCP_SERVICE].update({"Result": "exit-code", "ExecMainStatus": "1"})
    contract = build_contract(snapshot)

    assert not any(
        reason.startswith("PNCP_CONTRACTS_TIMER_LIFECYCLE")
        for reason in contract["reason_codes"]
    )
    assert contract["units"][PNCP_TIMER]["ActiveState"] == "active"
    assert contract["units"][PNCP_TIMER]["NextElapseUSecRealtime"]


def test_running_timer_has_no_next_elapse_until_oneshot_finishes() -> None:
    snapshot = _snapshot()
    snapshot["units"][PNCP_TIMER].update(
        {"SubState": "running", "NextElapseUSecRealtime": ""}
    )
    snapshot["units"][PNCP_SERVICE]["ActiveState"] = "activating"
    contract = build_contract(snapshot)

    assert "PNCP_CONTRACTS_TIMER_NO_NEXT_TRIGGER" not in contract["reason_codes"]


def test_release_sha_drift_is_visible_and_fail_closed() -> None:
    snapshot = _snapshot()
    snapshot["release_identity"] = {
        "effective_sha": SHA,
        "marker_sha": "623acdcd251a20fb4d2f185cd8fedcfea474bb4a",
        "checkout_sha": SHA,
        "consistent": False,
    }
    contract = build_contract(snapshot)

    assert "RELEASE_SHA_DRIFT" in contract["reason_codes"]
    assert contract["release_identity"]["marker_sha"].startswith("623acdcd")


def test_timer_lifecycle_coupling_or_missing_persistence_fails_closed() -> None:
    snapshot = _snapshot()
    snapshot["units"][PNCP_TIMER]["Requires"] = PNCP_SERVICE
    snapshot["units"][HEALTH_TIMER]["Persistent"] = "no"
    contract = build_contract(snapshot)

    assert "PNCP_CONTRACTS_TIMER_LIFECYCLE_COUPLED_REQUIRES" in contract["reason_codes"]
    assert "EXTRA_HEALTH_CHECK_TIMER_NOT_PERSISTENT" in contract["reason_codes"]


def test_shipped_timers_survive_oneshot_failure_and_catch_up_after_reboot() -> None:
    for timer_name, service_name in TIMER_TO_SERVICE.items():
        text = (ROOT / "deploy" / "systemd" / timer_name).read_text(encoding="utf-8")
        active_lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        assert "Persistent=true" in active_lines
        for relationship in (
            "Requires",
            "Requisite",
            "BindsTo",
            "PartOf",
            "Conflicts",
            "PropagatesStopTo",
        ):
            assert f"{relationship}={service_name}" not in active_lines


def test_a_recoupled_source_is_reported_as_unhealthy() -> None:
    """A drifted host that re-adds the OnSuccess must fail the readback.

    The gate exits non-zero for any non-FRESH contract, so re-coupling turns a
    source incident back into a silent commercial outage.
    """
    for coupled in (PNCP_SERVICE, SOURCE_FRESHNESS_SERVICE):
        snapshot = _snapshot()
        snapshot["units"][coupled]["OnSuccess"] = TARGET_FIT_RECONCILE_SERVICE
        contract = build_contract(snapshot)

        expected = f"{coupled.upper().replace('-', '_').replace('.', '_')}_ONSUCCESS_COUPLED"
        assert expected in contract["reason_codes"]
        assert contract["status"] != "HEALTHY"


def test_the_shipped_decoupled_units_pass_the_readback() -> None:
    contract = build_contract(_snapshot())

    assert not any(reason.endswith("_ONSUCCESS_COUPLED") for reason in contract["reason_codes"])


def test_ingestion_and_source_health_carry_no_on_success_and_locks_are_verbose() -> None:
    pncp = (ROOT / "deploy/systemd/pncp-contracts.service").read_text(encoding="utf-8")
    gate = (ROOT / "deploy/systemd/extra-confenge-source-freshness-gate.service").read_text(
        encoding="utf-8"
    )
    refresh = (ROOT / "deploy/systemd/extra-confenge-target-fit-refresh.service").read_text(
        encoding="utf-8"
    )
    reconcile = (ROOT / "deploy/systemd/extra-confenge-target-fit-reconcile.service").read_text(
        encoding="utf-8"
    )
    assert "OnSuccess=" not in pncp.split("[Service]", 1)[0]
    assert "OnSuccess=" not in gate.split("[Service]", 1)[0]
    assert f"OnSuccess={TARGET_FIT_RECONCILE_SERVICE}" not in pncp
    assert "/usr/bin/flock --verbose --nonblock" in refresh
    assert "/usr/bin/flock --verbose --nonblock" in reconcile
    assert "OnFailure=extra-onfailure@%n.service" in refresh
    worker = (ROOT / "deploy/systemd/extra-confenge-target-fit-worker.service").read_text(
        encoding="utf-8"
    )
    assert "OnFailure=extra-onfailure@%n.service" in worker


def test_health_contract_includes_target_fit_timers_and_worker() -> None:
    assert TARGET_FIT_REFRESH_TIMER in health_check.CRITICAL_TIMERS
    assert TARGET_FIT_RECONCILE_TIMER in health_check.CRITICAL_TIMERS
    assert TARGET_FIT_WORKER in health_check.CRITICAL_SERVICES


def test_target_fit_dirty_queue_alarms_at_the_configured_slo() -> None:
    assert dirty_progress_stale(1801, slo_minutes=30) is True
    assert dirty_progress_stale(1800, slo_minutes=30) is False


class _Cursor:
    def __init__(self) -> None:
        self.query = ""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query: str) -> None:
        self.query = query
        assert "key = 'cdc_watermark'" not in query

    def fetchall(self):
        return []

    def fetchone(self):
        return None


class _Connection:
    def cursor(self) -> _Cursor:
        return _Cursor()


def test_cdc_watermark_cannot_impersonate_worker_progress() -> None:
    assert max_current_watermark(_Connection()) == ""
    assert (
        target_fit_progress_watermark(
            control_watermark="",
            materialized_watermark="",
        )
        == ""
    )
    assert target_fit_progress_watermark(
        control_watermark="2026-08-27T12:00:00Z",
        materialized_watermark="2026-08-27T11:00:00Z",
    ) == "2026-08-27T12:00:00Z"


def test_error_sanitization_keeps_cause_without_credentials() -> None:
    message = sanitize_error(
        "OperationalError: postgresql://alice:secret@db/internal password=hunter2 timeout"
    )
    assert "timeout" in message
    assert "alice:secret" not in message
    assert "hunter2" not in message
    assert "[REDACTED]" in message
