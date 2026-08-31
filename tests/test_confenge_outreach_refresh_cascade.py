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


def test_refresh_graph_is_exact_linear_and_acyclic() -> None:
    graph = {
        SOURCE: _on_success(SOURCE),
        GATE: _on_success(GATE),
        TARGET: _on_success(TARGET),
        CONTACT: _on_success(CONTACT),
        FEED: _on_success(FEED),
    }

    assert graph == {
        SOURCE: [GATE],
        GATE: [TARGET],
        TARGET: [CONTACT],
        CONTACT: [FEED],
        FEED: [],
    }
    assert all((UNIT_DIR / successor).is_file() for values in graph.values() for successor in values)


def test_source_never_bypasses_the_semantic_freshness_gate() -> None:
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
    assert f"OnSuccess={GATE}" in _unit_section(source)
    assert f"OnSuccess={TARGET}" not in _unit_section(source)
    assert (
        "ExecStart=/opt/extra-consultoria/.venv/bin/python "
        "-m scripts.ops.pncp_contract_freshness --live --health"
    ) in gate
    assert "SuccessExitStatus=" not in gate


def test_each_promoting_stage_alerts_and_only_success_can_advance() -> None:
    for name in (SOURCE, GATE, TARGET, CONTACT, FEED):
        text = _unit(name)
        assert "Type=oneshot" in text
        assert "OnFailure=extra-onfailure@%n.service" in _unit_section(text)

    assert "OnSuccess=" not in _unit_section(_unit(FEED))


def test_refresh_cascade_does_not_create_or_enable_a_commercial_timer() -> None:
    timer_names = {path.name for path in UNIT_DIR.glob("*.timer")}

    assert "extra-confenge-source-freshness-gate.timer" not in timer_names
    assert all("commercial" not in name for name in timer_names if "confenge" in name)
