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
    CHAIN_DISABLED_TIMERS,
    CHAIN_ENABLED_SERVICES,
    CHAIN_TIMERS,
    CHAIN_UNITS,
    UNIT_SOURCE,
    PinError,
    _duration_seconds,
    plan,
    render_dropin,
    verify,
)

SHA = "a" * 40


def test_every_chain_unit_has_a_versioned_source_file():
    for unit in CHAIN_UNITS:
        assert (UNIT_SOURCE / unit).is_file(), f"{unit} must be versioned in deploy/systemd"


def test_every_chain_timer_has_a_versioned_source_file():
    for timer in (*CHAIN_TIMERS, *CHAIN_DISABLED_TIMERS):
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
    assert "Environment=PYTHONDONTWRITEBYTECODE=1" in body
    assert "Environment=PYTHONSAFEPATH=1" in body
    assert "ExecStart=\n" in body, "inherited ExecStart must be cleared before appending"
    for line in body.splitlines():
        if line.startswith(("Environment=PYTHONPATH=", "ExecStart=/")):
            assert f"{CANONICAL_PREFIX}-releases/{SHA}" in line


def test_pncp_dropin_clears_legacy_lock_success_and_disables_systemd_restart():
    unit = (UNIT_SOURCE / "pncp-contracts.service").read_text(encoding="utf-8")
    body = render_dropin(unit, SHA)
    assert "SuccessExitStatus=\n" in body
    assert "Restart=no\n" in body
    assert "TimeoutStartSec=320min\n" in body


def test_dropins_preserve_versioned_timeout_intent_for_every_bounded_unit():
    for unit_name in CHAIN_UNITS:
        unit = (UNIT_SOURCE / unit_name).read_text(encoding="utf-8")
        source_timeout = next((line for line in unit.splitlines() if line.startswith("TimeoutStartSec=")), None)
        body = render_dropin(unit, SHA)
        rendered_timeout = next((line for line in body.splitlines() if line.startswith("TimeoutStartSec=")), None)
        assert rendered_timeout == source_timeout, unit_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1hour", "3600"),
        ("1msec", "0.001"),
        ("+1h", "3600"),
        (".5h", "1800"),
        ("1h\t20min", "4800"),
        ("1month", "2629800"),
        ("1M", "2629800"),
        ("1y", "31557600"),
        ("infinity", None),
    ],
)
def test_duration_parser_accepts_systemd_timeout_spellings(raw, expected):
    parsed = _duration_seconds(raw)
    assert (None if parsed is None else f"{parsed.normalize():f}") == expected


def test_calendar_timeout_aliases_match_systemd_timespan_semantics():
    assert _duration_seconds("1month") == _duration_seconds("1months") == _duration_seconds("1M")
    assert _duration_seconds("1month") == _duration_seconds("2629800s")
    assert _duration_seconds("1y") == _duration_seconds("1year") == _duration_seconds("1years")
    assert _duration_seconds("1y") == _duration_seconds("31557600s")


@pytest.mark.parametrize(
    ("source_timeout", "expected"),
    [("0", None), ("0.1us", None), ("1.1us", "0.000001")],
)
def test_source_timeout_is_quantized_to_systemd_microseconds(tmp_path, monkeypatch, source_timeout, expected):
    import deploy.confenge.pin_release as pin

    source_root = tmp_path / "units"
    source_root.mkdir()
    (source_root / "pncp-contracts.service").write_text(
        f"[Service]\nTimeoutStartSec={source_timeout}\n", encoding="utf-8"
    )
    monkeypatch.setattr(pin, "UNIT_SOURCE", source_root)

    has_timeout, parsed = pin._source_timeout_start_seconds("pncp-contracts.service")
    assert has_timeout is True
    assert (None if parsed is None else f"{parsed:f}") == expected


@pytest.mark.parametrize(
    "raw",
    [
        "1usecs", "1msecx", "1secs", "1mins", "1hrs", "1millisecond",
        "1H", "1MS", "1SEC", "1Hour", "INFINITY", "+.5h", "1h+.5min",
    ],
)
def test_duration_parser_rejects_non_systemd_timeout_aliases(raw):
    with pytest.raises(PinError, match="unsupported systemd duration"):
        _duration_seconds(raw)


def test_plan_rejects_an_unsupported_timeout_before_any_host_write(tmp_path, monkeypatch):
    import deploy.confenge.pin_release as pin

    source_root = tmp_path / "units"
    source_root.mkdir()
    release_root = tmp_path / "releases"
    (release_root / SHA / ".venv" / "bin").mkdir(parents=True)
    (release_root / SHA / ".venv" / "bin" / "python").touch()
    for unit_name in CHAIN_UNITS:
        timeout = "TimeoutStartSec=1fortnight\n" if unit_name == CHAIN_UNITS[-1] else ""
        (source_root / unit_name).write_text(
            "[Service]\n"
            "ExecStart=/opt/extra-consultoria/.venv/bin/python -m scripts.example\n"
            f"{timeout}",
            encoding="utf-8",
        )
    monkeypatch.setattr(pin, "UNIT_SOURCE", source_root)
    monkeypatch.setattr(pin, "RELEASE_ROOT", release_root)
    monkeypatch.setattr(pin, "SYSTEMD_ROOT", tmp_path / "systemd")

    with pytest.raises(PinError, match="extra-confenge-feed-monitor.service: unsupported systemd duration"):
        pin.apply(SHA)
    assert not pin.SYSTEMD_ROOT.exists()


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


def test_release_cut_uses_the_exact_git_tree_and_an_isolated_import_guard():
    source = (Path(__file__).resolve().parents[1] / "deploy" / "confenge" / "cut_release.sh").read_text(
        encoding="utf-8"
    )
    assert 'git -C "$APP" archive "$SHA"' in source
    assert 'PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$STAGING" "$STAGING/.venv/bin/python" -P -c' in source
    assert "git checkout" not in source
    assert "git reset" not in source


def test_existing_release_is_reverified_before_pin():
    source = (Path(__file__).resolve().parents[1] / "deploy" / "confenge" / "cut_release.sh").read_text(
        encoding="utf-8"
    )
    assert 'find "$TARGET" -xdev \\( -type f -o -type d \\) -perm /222' in source
    assert 'find "$TARGET" -xdev \\( ! -user root -o ! -group root \\)' in source
    assert 'git -C "$APP" show "$SHA:$CRITICAL_PATH" | cmp -s - "$TARGET/$CRITICAL_PATH"' in source
    assert source.index('echo "CUT_RELEASE_SKIP:') < source.index('if find "$TARGET"')
    pin = 'PYTHONDONTWRITEBYTECODE=1 python3 -P "$TARGET/deploy/confenge/pin_release.py"'
    assert pin in source
    assert source.index('if find "$TARGET"') < source.index(pin)


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


def test_ingestion_commercial_and_monitor_timers_are_scheduled_independently():
    source = (Path(__file__).resolve().parents[1] / "deploy" / "confenge" / "pin_release.py").read_text(
        encoding="utf-8"
    )
    assert '"enable", "--now", *CHAIN_TIMERS' in source
    assert '"disable", "--now", *CHAIN_DISABLED_TIMERS' in source
    assert '"timers_not_active"' in source, "verification must read back whether the timer is loaded"
    assert set(CHAIN_TIMERS) == {
        "pncp-contracts.timer",
        "extra-confenge-feed-cycle.timer",
        "extra-confenge-feed-monitor.timer",
    }
    assert set(CHAIN_DISABLED_TIMERS) == {
        "extra-confenge-target-fit-reconcile.timer",
        "extra-confenge-target-fit-refresh.timer",
        "extra-confenge-contact-cycle.timer",
    }


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


def test_verify_reads_back_isolation_release_and_writable_working_directory(tmp_path, monkeypatch):
    import subprocess

    import deploy.confenge.pin_release as pin

    release_root = tmp_path / "releases"
    release = release_root / SHA
    workdir = tmp_path / "writable"
    workdir.mkdir()
    monkeypatch.setattr(pin, "RELEASE_ROOT", release_root)

    def fake_run(argv: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        del check
        if argv[:2] == ["systemctl", "show"]:
            prop = argv[argv.index("-p") + 1]
            has_timeout, timeout = pin._source_timeout_start_seconds(argv[2])
            values = {
                "ExecStart": f"{release}/.venv/bin/python -P -m scripts.example",
                "Environment": f"PYTHONPATH={release} EXTRA_DEPLOYED_SHA={SHA} PYTHONDONTWRITEBYTECODE=1 PYTHONSAFEPATH=1",
                "WorkingDirectory": str(workdir),
                "User": "extra-consultoria",
                "TimeoutStartUSec": f"{timeout:f}s" if has_timeout and timeout is not None else "infinity",
                "SuccessExitStatus": "",
                "Restart": "no",
            }
            return subprocess.CompletedProcess(argv, 0, stdout=values[prop], stderr="")
        if argv[:2] == ["systemctl", "is-enabled"] or argv[:2] == ["systemctl", "is-active"]:
            is_downstream = argv[2] in CHAIN_DISABLED_TIMERS
            if argv[1] == "is-enabled":
                value = "disabled" if is_downstream else "enabled"
            else:
                value = "inactive" if is_downstream else "active"
            return subprocess.CompletedProcess(argv, 0, stdout=value)
        if argv[:4] == ["runuser", "-u", "extra-consultoria", "--"]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        raise AssertionError(argv)

    monkeypatch.setattr(pin, "_run", fake_run)

    report = verify(SHA)
    assert report["ok"] is True
    assert report["release_drift"] == []
    assert report["unsafe_python_path"] == []
    assert report["bytecode_writes_enabled"] == []
    assert report["working_directory_drift"] == []
    assert report["working_directory_not_writable"] == []
    assert report["timeout_start_drift"] == []
    assert report["downstream_timers_scheduled"] == []
    assert report["pncp_service_semantic_drift"] == []


@pytest.mark.parametrize(
    "failure",
    [
        "unsafe-python",
        "bytecode-enabled",
        "readonly-workdir",
        "release-workdir",
        "downstream-timer",
        "pncp-restart",
        "pncp-success75",
        "pncp-success77",
        "pncp-timeout",
    ],
)
def test_verify_fails_closed_on_runtime_isolation_drift(tmp_path, monkeypatch, failure):
    import subprocess

    import deploy.confenge.pin_release as pin

    release_root = tmp_path / "releases"
    release = release_root / SHA
    workdir = release if failure == "release-workdir" else tmp_path / "work"
    monkeypatch.setattr(pin, "RELEASE_ROOT", release_root)

    def fake_run(argv: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        del check
        if argv[:2] == ["systemctl", "show"]:
            prop = argv[argv.index("-p") + 1]
            has_timeout, timeout = pin._source_timeout_start_seconds(argv[2])
            values = {
                "ExecStart": (
                    f"{release}/.venv/bin/python -m scripts.example"
                    if failure == "unsafe-python"
                    else f"{release}/.venv/bin/python -P -m scripts.example"
                ),
                "Environment": (
                    f"PYTHONPATH={release}"
                    if failure == "bytecode-enabled"
                    else f"PYTHONPATH={release} PYTHONDONTWRITEBYTECODE=1 PYTHONSAFEPATH=1"
                ),
                "WorkingDirectory": str(workdir),
                "User": "extra-consultoria",
                "TimeoutStartUSec": (
                    "150min"
                    if failure == "pncp-timeout" and argv[2] == "pncp-contracts.service"
                    else f"{timeout:f}s" if has_timeout and timeout is not None else "infinity"
                ),
                "SuccessExitStatus": (
                    "75" if failure == "pncp-success75" else "77" if failure == "pncp-success77" else ""
                ),
                "Restart": "on-failure" if failure == "pncp-restart" else "no",
            }
            return subprocess.CompletedProcess(argv, 0, stdout=values[prop], stderr="")
        if argv[:2] == ["systemctl", "is-enabled"] or argv[:2] == ["systemctl", "is-active"]:
            is_downstream = argv[2] in CHAIN_DISABLED_TIMERS
            if failure == "downstream-timer" and is_downstream:
                value = "enabled" if argv[1] == "is-enabled" else "active"
                return subprocess.CompletedProcess(argv, 0, stdout=value)
            if argv[1] == "is-enabled":
                value = "disabled" if is_downstream else "enabled"
            else:
                value = "inactive" if is_downstream else "active"
            return subprocess.CompletedProcess(argv, 0, stdout=value)
        if argv[:4] == ["runuser", "-u", "extra-consultoria", "--"]:
            code = 1 if failure == "readonly-workdir" else 0
            return subprocess.CompletedProcess(argv, code, stdout="", stderr="")
        raise AssertionError(argv)

    monkeypatch.setattr(pin, "_run", fake_run)

    report = verify(SHA)
    assert report["ok"] is False
    if failure == "unsafe-python":
        assert len(report["unsafe_python_path"]) == len(CHAIN_UNITS)
    elif failure == "bytecode-enabled":
        assert len(report["bytecode_writes_enabled"]) == len(CHAIN_UNITS)
    elif failure == "readonly-workdir":
        assert len(report["working_directory_not_writable"]) == len(CHAIN_UNITS)
    elif failure == "release-workdir":
        assert len(report["working_directory_drift"]) == len(CHAIN_UNITS)
    elif failure == "downstream-timer":
        assert len(report["downstream_timers_scheduled"]) == len(CHAIN_DISABLED_TIMERS)
    elif failure == "pncp-timeout":
        assert report["timeout_start_drift"] == [
            {"unit": "pncp-contracts.service", "expected": "19200s", "observed": "150min"}
        ]
    else:
        assert report["pncp_service_semantic_drift"]
