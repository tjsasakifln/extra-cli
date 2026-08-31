"""Fail-closed systemd graph for the contemporary CONFENGE data refresh."""

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


def test_pncp_ingestion_is_not_a_commercial_trigger() -> None:
    graph = {
        SOURCE: _on_success(SOURCE),
        GATE: _on_success(GATE),
        TARGET: _on_success(TARGET),
        CONTACT: _on_success(CONTACT),
        FEED: _on_success(FEED),
    }

    assert graph == {
        SOURCE: [],
        GATE: [TARGET],
        TARGET: [CONTACT],
        CONTACT: [FEED],
        FEED: [],
    }
    assert all((UNIT_DIR / successor).is_file() for values in graph.values() for successor in values)


def test_source_is_ingestion_only_and_keeps_failure_semantics() -> None:
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
    assert f"OnSuccess={TARGET}" not in _unit_section(source)
    assert (
        "ExecStart=/opt/extra-consultoria/.venv/bin/python -m scripts.ops.pncp_contract_freshness --live --health"
    ) in gate
    assert "SuccessExitStatus=" not in gate


def test_each_promoting_stage_alerts_and_only_success_can_advance() -> None:
    for name in (SOURCE, GATE, TARGET, CONTACT, FEED):
        text = _unit(name)
        assert "Type=oneshot" in text
        assert "OnFailure=extra-onfailure@%n.service" in _unit_section(text)

    assert "OnSuccess=" not in _unit_section(_unit(FEED))


def test_commercial_feed_has_an_independent_persistent_timer() -> None:
    timer_names = {path.name for path in UNIT_DIR.glob("*.timer")}

    assert "extra-confenge-source-freshness-gate.timer" not in timer_names
    assert "extra-confenge-feed-cycle.timer" in timer_names
    timer = _unit("extra-confenge-feed-cycle.timer")
    assert "Persistent=true" in timer
    assert "Unit=extra-confenge-feed-cycle.service" in timer
    assert "PNCP" in timer
    feed = _unit(FEED)
    assert "flock --nonblock /run/extra-confenge-feed/feed-cycle.lock" in feed
    assert "extra-confenge-source-freshness-gate.service" not in feed
