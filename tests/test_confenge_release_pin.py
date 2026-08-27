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


def test_rendered_dropin_repoints_code_at_the_release():
    unit = (UNIT_SOURCE / "extra-confenge-feed-cycle.service").read_text(encoding="utf-8")
    body = render_dropin(unit, SHA)
    assert f"/opt/extra-consultoria-releases/{SHA}/.venv/bin/python" in body
    assert f"Environment=EXTRA_DEPLOYED_SHA={SHA}" in body
    assert "ExecStart=\n" in body, "inherited ExecStart must be cleared before appending"
    for line in body.splitlines():
        if line.startswith(("Environment=PYTHONPATH=", "ExecStart=/")):
            assert f"{CANONICAL_PREFIX}-releases/{SHA}" in line


def test_working_directory_stays_outside_the_read_only_release():
    """Releases are read-only; several jobs write evidence via relative paths.

    Pinning the cwd into the release killed the PNCP crawler with
    PermissionError: 'output/contracts/incremental-latest.json' *after* it had
    already crawled a window successfully.
    """
    for unit_name in ("pncp-contracts.service", "extra-confenge-feed-cycle.service"):
        unit = (UNIT_SOURCE / unit_name).read_text(encoding="utf-8")
        body = render_dropin(unit, SHA)
        workdirs = [line for line in body.splitlines() if line.startswith("WorkingDirectory=")]
        assert workdirs == [f"WorkingDirectory={CANONICAL_PREFIX}"], f"{unit_name}: {workdirs}"


def test_pinned_interpreter_is_isolated_from_the_working_directory():
    """Without -P, cwd is prepended to sys.path and the checkout at
    /opt/extra-consultoria shadows the release's own `scripts` package — so the
    pin would bind a release it never actually ran."""
    unit = (UNIT_SOURCE / "extra-confenge-feed-cycle.service").read_text(encoding="utf-8")
    body = render_dropin(unit, SHA)
    exec_line = next(line for line in body.splitlines() if line.startswith("ExecStart=/"))
    assert f"/opt/extra-consultoria-releases/{SHA}/.venv/bin/python -P " in exec_line


def test_isolation_flag_is_not_duplicated():
    unit = (UNIT_SOURCE / "extra-confenge-feed-cycle.service").read_text(encoding="utf-8")
    once = render_dropin(unit, SHA)
    exec_line = next(line for line in once.splitlines() if line.startswith("ExecStart=/"))
    assert exec_line.count(" -P ") == 1


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


def test_pncp_checkpoint_dir_is_versioned_and_outside_the_release():
    """A read-only release cannot hold a crawl checkpoint.

    This lived in a hand-written host drop-in, so the release pin discarded it and
    the crawler died with PermissionError writing inside the immutable tree.
    """
    unit = (UNIT_SOURCE / "pncp-contracts.service").read_text(encoding="utf-8")
    assert "--checkpoint-dir /var/lib/extra-consultoria/checkpoints/contracts" in unit
    body = render_dropin(unit, SHA)
    exec_line = next(line for line in body.splitlines() if line.startswith("ExecStart=/"))
    assert "--checkpoint-dir /var/lib/extra-consultoria/checkpoints/contracts" in exec_line
    assert f"/opt/extra-consultoria-releases/{SHA}/data" not in exec_line
    assert "--days 7" in exec_line


def test_a_foreign_execstart_dropin_blocks_the_pin(tmp_path, monkeypatch):
    import deploy.confenge.pin_release as pin

    root = tmp_path / "systemd"
    unit_dir = root / f"{CHAIN_UNITS[0]}.d"
    unit_dir.mkdir(parents=True)
    (unit_dir / "50-host-tweak.conf").write_text("[Service]\nExecStart=\nExecStart=/bin/true\n", encoding="utf-8")
    (unit_dir / "90-immutable-release.conf").write_text("[Service]\nExecStart=/bin/true\n", encoding="utf-8")
    monkeypatch.setattr(pin, "SYSTEMD_ROOT", root)

    found = pin.foreign_execstart_dropins()
    assert found == {CHAIN_UNITS[0]: ["50-host-tweak.conf"]}


def test_our_own_dropin_is_not_reported_as_foreign(tmp_path, monkeypatch):
    import deploy.confenge.pin_release as pin

    root = tmp_path / "systemd"
    for unit in CHAIN_UNITS:
        unit_dir = root / f"{unit}.d"
        unit_dir.mkdir(parents=True)
        (unit_dir / "90-immutable-release.conf").write_text("[Service]\nExecStart=/bin/true\n", encoding="utf-8")
    monkeypatch.setattr(pin, "SYSTEMD_ROOT", root)

    assert pin.foreign_execstart_dropins() == {}
