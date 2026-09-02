"""Systemd contract: PNCP ingestion must not govern the commercial plane."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNIT_DIR = ROOT / "deploy" / "systemd"

SOURCE = "pncp-contracts.service"
GATE = "extra-confenge-source-freshness-gate.service"
TARGET = "extra-confenge-target-fit-reconcile.service"
CONTACT = "extra-confenge-contact-cycle.service"
FEED = "extra-confenge-feed-cycle.service"


def _unit(name: str) -> str:
    return (UNIT_DIR / name).read_text(encoding="utf-8")


def _unit_section(text: str) -> str:
    return text.split("[Unit]", 1)[1].split("[Service]", 1)[0]


def _on_success(name: str) -> list[str]:
    values: list[str] = []
    for line in _unit_section(_unit(name)).splitlines():
        stripped = line.strip()
        if stripped.startswith("OnSuccess="):
            values.extend(stripped.split("=", 1)[1].split())
    return values


def test_no_stage_advances_another() -> None:
    """Two distinct hazards, one rule: no stage may chain another.

    `--health` exits non-zero on any non-FRESH contract, so an OnSuccess rooted
    at ingestion or the gate makes a source incident a silent kill switch. And
    every stage now owns a timer, so a surviving OnSuccess gives its successor a
    second trigger that lands on a held flock and alerts on work already running.
    """
    graph = {
        SOURCE: _on_success(SOURCE),
        GATE: _on_success(GATE),
        TARGET: _on_success(TARGET),
        CONTACT: _on_success(CONTACT),
        FEED: _on_success(FEED),
    }

    assert graph == {
        SOURCE: [],
        GATE: [],
        TARGET: [],
        CONTACT: [],
        FEED: [],
    }
    assert all((UNIT_DIR / successor).is_file() for values in graph.values() for successor in values)


def test_source_is_ingestion_only_and_keeps_its_failure_semantics() -> None:
    source = _unit(SOURCE)
    gate = _unit(GATE)

    assert "SuccessExitStatus=" not in source
    restart_lines = [line for line in source.splitlines() if line.startswith("Restart=")]
    assert restart_lines == ["Restart=no"]
    assert "RestartPreventExitStatus=" not in source
    assert "RestartForceExitStatus=" not in source
    assert "RestartSec=" not in source
    assert "StartLimitIntervalSec=" not in source
    assert "StartLimitBurst=" not in source
    assert "TimeoutStartSec=320min" in source
    assert "OnSuccess=" not in _unit_section(source)
    assert (
        "ExecStart=/opt/extra-consultoria/.venv/bin/python "
        "-m scripts.ops.pncp_contract_freshness --live --health"
    ) in gate
    assert "SuccessExitStatus=" not in gate


def test_every_stage_still_alerts_on_failure() -> None:
    for name in (SOURCE, GATE, TARGET, CONTACT, FEED):
        text = _unit(name)
        assert "Type=oneshot" in text
        assert "OnFailure=extra-onfailure@%n.service" in _unit_section(text)

    assert "OnSuccess=" not in _unit_section(_unit(FEED))


def test_the_freshness_gate_never_owns_a_cadence() -> None:
    """Telemetry already ships through extra-health-check/health_bundle."""
    timer_names = {path.name for path in UNIT_DIR.glob("*.timer")}

    assert "extra-confenge-source-freshness-gate.timer" not in timer_names
    assert all("commercial" not in name for name in timer_names if "confenge" in name)


def test_every_decoupled_stage_owns_exactly_one_trigger() -> None:
    """Cutting OnSuccess without a timer would orphan the stage, not free it.

    Keeping both would double-trigger it. Each needs exactly one.
    """
    for service in (
        "extra-confenge-target-fit-refresh.service",
        "extra-confenge-target-fit-reconcile.service",
        CONTACT,
        FEED,
    ):
        timer = _unit(service.replace(".service", ".timer"))
        assert "Persistent=true" in timer
        assert f"Unit={service}" in timer
        chained_by = [name for name in (SOURCE, GATE, TARGET, CONTACT, FEED) if service in _on_success(name)]
        assert chained_by == [], f"{service} has both a timer and an OnSuccess trigger from {chained_by}"


def test_feed_publication_runs_on_an_independent_four_times_daily_cadence() -> None:
    timer = _unit(FEED.replace(".service", ".timer"))

    assert "OnCalendar=*-*-* 02,08,14,20:15:00" in timer
    assert "OnCalendar=*-*-* 01,13:20:00" not in timer
    assert "Persistent=true" in timer
    assert "RandomizedDelaySec=10m" in timer
    assert "PNCP ingestion health never controls this" in timer
