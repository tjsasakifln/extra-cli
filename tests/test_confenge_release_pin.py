"""The whole CONFENGE outbound chain must run one release, reproducibly.

Hand-written ``90-immutable-release.conf`` drop-ins drifted to three different
SHAs across a single chain. These tests pin the rendering contract so the
generated drop-ins stay derived from the versioned unit files.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deploy.confenge.pin_release import (
    CANONICAL_PREFIX,
    CHAIN_ENABLED_SERVICES,
    CHAIN_TIMERS,
    CHAIN_UNITS,
    UNIT_SOURCE,
    PinError,
    plan,
    render_dropin,
)

SHA = "a" * 40


def test_every_chain_unit_has_a_versioned_source_file():
    for unit in CHAIN_UNITS:
        assert (UNIT_SOURCE / unit).is_file(), f"{unit} must be versioned in deploy/systemd"


def test_every_chain_timer_has_a_versioned_source_file():
    for timer in CHAIN_TIMERS:
        assert (UNIT_SOURCE / timer).is_file(), f"{timer} must be versioned in deploy/systemd"


def test_the_canonical_chain_order_is_covered():
    for unit in (
        "pncp-contracts.service",
        "extra-confenge-source-freshness-gate.service",
        "extra-confenge-target-fit-reconcile.service",
        "extra-confenge-contact-cycle.service",
        "extra-confenge-feed-cycle.service",
    ):
        assert unit in CHAIN_UNITS


def test_rendered_dropin_repoints_every_path_at_the_release():
    unit = (UNIT_SOURCE / "extra-confenge-feed-cycle.service").read_text(encoding="utf-8")
    body = render_dropin(unit, SHA)
    assert f"/opt/extra-consultoria-releases/{SHA}/.venv/bin/python" in body
    assert f"Environment=EXTRA_DEPLOYED_SHA={SHA}" in body
    assert "ExecStart=\n" in body, "inherited ExecStart must be cleared before appending"
    for line in body.splitlines():
        if line.startswith(("WorkingDirectory=", "Environment=PYTHONPATH=", "ExecStart=/")):
            assert f"{CANONICAL_PREFIX}-releases/{SHA}" in line
            assert not line.replace(f"{CANONICAL_PREFIX}-releases/{SHA}", "").count(CANONICAL_PREFIX)


def test_multi_line_execstart_is_joined_not_truncated():
    unit = (UNIT_SOURCE / "extra-confenge-target-fit-reconcile.service").read_text(encoding="utf-8")
    assert "\\\n" in unit, "fixture relies on a real continued ExecStart"
    body = render_dropin(unit, SHA)
    exec_lines = [line for line in body.splitlines() if line.startswith("ExecStart=/")]
    assert len(exec_lines) == 1
    assert "\\" not in exec_lines[0]
    assert "reconcile" in exec_lines[0]


def test_environment_placeholders_survive_rendering():
    unit = (UNIT_SOURCE / "extra-confenge-contact-cycle.service").read_text(encoding="utf-8")
    body = render_dropin(unit, SHA)
    assert "${CONFENGE_CONTACT_OUTPUT_ROOT}" in body


def test_a_unit_without_execstart_is_refused():
    with pytest.raises(PinError, match="no ExecStart"):
        render_dropin("[Service]\nType=oneshot\n", SHA)


def test_short_sha_is_refused_before_touching_the_host():
    with pytest.raises(PinError, match="full 40-character"):
        plan("deadbeef")


def test_unknown_release_is_refused_before_touching_the_host():
    with pytest.raises(PinError, match="release directory does not exist"):
        plan("b" * 40)


def test_long_running_worker_is_marked_for_reboot_persistence():
    assert "extra-confenge-target-fit-worker.service" in CHAIN_ENABLED_SERVICES


def test_timers_are_started_not_only_enabled():
    """`systemctl enable` alone leaves a timer unloaded until the next boot.

    That is exactly how the contact-cycle and feed-cycle safety nets came to
    report `enabled` while `systemctl list-timers` showed neither of them.
    """
    source = (Path(__file__).resolve().parents[1] / "deploy" / "confenge" / "pin_release.py").read_text(
        encoding="utf-8"
    )
    assert '"enable", "--now", *CHAIN_TIMERS' in source
    assert '"timers_not_active"' in source, "verification must read back whether the timer is loaded"
