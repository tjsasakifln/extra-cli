#!/usr/bin/env python3
"""Pin the whole CONFENGE outbound chain to one immutable release.

The plane is autonomous by design, and split in two:

    pncp-contracts.timer        -> pncp-contracts.service         (ingestion)
    extra-confenge-target-fit-refresh.timer   -> refresh          (datalake)
    extra-confenge-target-fit-reconcile.timer -> reconcile        (datalake)
    extra-confenge-contact-cycle.timer        -> contact cycle    (datalake)
    extra-confenge-feed-cycle.timer           -> feed publication (commercial)

Ingestion no longer advances the commercial stages through ``OnSuccess``.  The
freshness gate exits non-zero for any non-FRESH contract, so an ``OnSuccess``
chain rooted at ``pncp-contracts.service`` made a source incident suppress
qualification, publication and transport over data already persisted in the
datalake.  Every downstream stage now owns an independent timer; PNCP freshness
stays visible as telemetry through ``extra-health-check`` and the on-demand
``extra-confenge-source-freshness-gate.service`` diagnostic.

Every link must run the *same* code. Hand-written ``90-immutable-release.conf``
drop-ins drifted apart (three different SHAs across the chain at once), which is
exactly the unversioned manual configuration this repository must not depend on.

This tool derives each drop-in mechanically from the versioned unit files in
``deploy/systemd`` by rewriting the ``/opt/extra-consultoria`` prefix to the
requested immutable release, applies the whole set atomically-or-not-at-all,
and keeps every stage on its own schedule.  A PNCP failure cannot suppress a
datalake-backed commercial run.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
UNIT_SOURCE = REPO_ROOT / "deploy" / "systemd"

CANONICAL_PREFIX = "/opt/extra-consultoria"
RELEASE_ROOT = Path("/opt/extra-consultoria-releases")
DROPIN_NAME = "90-immutable-release.conf"
SYSTEMD_ROOT = Path("/etc/systemd/system")

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")

# Every unit that executes CONFENGE outbound code. Instance units are pinned
# through their template so all instances follow one release.
CHAIN_UNITS = (
    "pncp-contracts.service",
    "extra-confenge-source-freshness-gate.service",
    "extra-confenge-target-fit-reconcile.service",
    "extra-confenge-target-fit-refresh.service",
    "extra-confenge-target-fit-worker.service",
    "extra-confenge-contact-cycle.service",
    "extra-contact-discovery-worker@.service",
    "extra-confenge-feed-cycle.service",
    "extra-confenge-feed-monitor.service",
)

# Timers that must survive a reboot for the plane to run without an operator.
# Ingestion, datalake maintenance and commercial publication each own one; the
# monitor observes publication health without advancing anything.  Omitting a
# stage here would orphan it: with the ``OnSuccess`` cascade gone there is no
# other trigger.
CHAIN_TIMERS = (
    "pncp-contracts.timer",
    "extra-confenge-target-fit-refresh.timer",
    "extra-confenge-target-fit-reconcile.timer",
    "extra-confenge-contact-cycle.timer",
    "extra-confenge-feed-cycle.timer",
    "extra-confenge-feed-monitor.timer",
)

# No stage may be driven by a source-triggered cascade any more, so there is no
# cadence left to suppress.  Kept as an explicit, readable empty contract: a
# future stage that must not self-schedule belongs here, not in a comment.
CHAIN_DISABLED_TIMERS: tuple[str, ...] = ()

# Long-running workers that must come back after a reboot.
CHAIN_ENABLED_SERVICES = ("extra-confenge-target-fit-worker.service",)

# Only code locations move to the immutable release. WorkingDirectory stays
# where the unit authored it, because releases are read-only and several jobs
# write evidence through paths relative to their working directory: pinning the
# cwd into the release made the PNCP crawler die on
# PermissionError: 'output/contracts/incremental-latest.json' after a window it
# had already crawled successfully.
PINNED_DIRECTIVES = (
    "Environment=PYTHONPATH=",
    "Environment=CONFENGE_COMMERCIAL_OPERATION_SCOPE=",
    "ExecStart=",
)
# Keep operational limits authored with the versioned unit. In particular, a
# host-local base unit may still have the old 150-minute PNCP limit; omitting
# this from the immutable pin would silently discard the 320-minute bounded
# two-pass recovery budget in the release being pinned.
PRESERVED_DIRECTIVES = ("WorkingDirectory=", "TimeoutStartSec=")

# With the working directory outside the release, Python would otherwise prepend
# that directory to sys.path and let the checkout at /opt/extra-consultoria
# shadow the release's own `scripts` package. -P is what makes the pin actually
# bind the code it claims to bind.
ISOLATED_INTERPRETER_FLAG = "-P"

_DURATION_PART = re.compile(
    # systemd accepts a leading `+` only before an integral component; `.5h`
    # is valid, while `+.5h` is not.
    r"(?P<value>(?:\+\d+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+))(?P<unit>"
    # Long aliases must precede their short prefixes: `month` would otherwise
    # be consumed as `m` plus an invalid `onth` suffix.
    r"seconds?|minutes?|hours?|months?|years?|days?|weeks?|usec|µs|msec|min|sec|hr|"
    r"ms|us|s|M|m|h|d|w|y)"
)
_DURATION_SECONDS = {
    "usec": Decimal("0.000001"), "µs": Decimal("0.000001"), "us": Decimal("0.000001"),
    "msec": Decimal("0.001"), "ms": Decimal("0.001"), "second": Decimal(1),
    "seconds": Decimal(1), "sec": Decimal(1), "s": Decimal(1), "minute": Decimal(60),
    "minutes": Decimal(60), "min": Decimal(60), "m": Decimal(60), "hour": Decimal(60 * 60),
    "hours": Decimal(60 * 60), "hr": Decimal(60 * 60), "h": Decimal(60 * 60),
    "day": Decimal(24 * 60 * 60), "days": Decimal(24 * 60 * 60), "d": Decimal(24 * 60 * 60),
    "week": Decimal(7 * 24 * 60 * 60), "weeks": Decimal(7 * 24 * 60 * 60), "w": Decimal(7 * 24 * 60 * 60),
    # systemd defines these calendar-independent units as fixed 30.44/365.25-day spans.
    "month": Decimal("2629800"), "months": Decimal("2629800"), "M": Decimal("2629800"),
    "year": Decimal("31557600"), "years": Decimal("31557600"), "y": Decimal("31557600"),
}
_MICROSECOND = Decimal("0.000001")


class PinError(RuntimeError):
    """A pin was refused before anything on the host changed."""


def _duration_seconds(value: str) -> Decimal | None:
    """Parse systemd time spans, returning ``None`` for an infinite timeout."""
    normalized = re.sub(r"\s+", "", value.strip())
    if normalized == "infinity":
        return None
    if re.fullmatch(r"(?:\+\d+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)", normalized):
        return Decimal(normalized)
    parts = list(_DURATION_PART.finditer(normalized))
    if not parts or "".join(part.group(0) for part in parts) != normalized:
        raise PinError(f"unsupported systemd duration: {value!r}")
    return sum(
        (Decimal(part["value"]) * _DURATION_SECONDS[part["unit"]] for part in parts),
        Decimal(0),
    )


def _systemd_timeout_seconds(value: str) -> Decimal | None:
    """Mirror systemd's integer-microsecond timeout resolution."""
    parsed = _duration_seconds(value)
    if parsed is None:
        return None
    return Decimal(int(parsed / _MICROSECOND)) * _MICROSECOND


def _source_timeout_start_seconds(unit: str) -> tuple[bool, Decimal | None]:
    """Return whether a unit sets the timeout plus its versioned intent."""
    source = UNIT_SOURCE / unit
    timeout: str | None = None
    for line in _logical_lines(source.read_text(encoding="utf-8")):
        if line.startswith("TimeoutStartSec="):
            timeout = line.removeprefix("TimeoutStartSec=")
    parsed = _systemd_timeout_seconds(timeout) if timeout is not None else None
    # systemd treats TimeoutStartSec=0 as no start timeout and resolves it as
    # `infinity` in TimeoutStartUSec. Compare that semantic intent, not the
    # spelling in the source unit.
    return timeout is not None, None if parsed == Decimal(0) else parsed


def _logical_lines(text: str) -> list[str]:
    """Join systemd line continuations so a multi-line ExecStart stays one unit."""
    lines: list[str] = []
    buffer = ""
    for raw in text.splitlines():
        stripped = raw.rstrip()
        if stripped.endswith("\\"):
            buffer += stripped[:-1].rstrip() + " "
            continue
        lines.append((buffer + stripped.strip()) if buffer else stripped)
        buffer = ""
    if buffer:
        lines.append(buffer.strip())
    return lines


def _isolate_interpreter(exec_start: str, release: str) -> str:
    """Insert -P after the release interpreter so cwd cannot shadow the release."""
    interpreter = f"{release}/.venv/bin/python"
    if interpreter not in exec_start:
        raise PinError(f"pinned ExecStart does not invoke the release interpreter: {exec_start}")
    head, _, tail = exec_start.partition(interpreter)
    if tail.lstrip().startswith(ISOLATED_INTERPRETER_FLAG + " "):
        return exec_start
    return f"{head}{interpreter} {ISOLATED_INTERPRETER_FLAG}{tail}"


def render_dropin(unit_text: str, sha: str) -> str:
    """Build the drop-in that re-points one unit at an immutable release."""
    release = f"{RELEASE_ROOT}/{sha}"
    directives: list[str] = []
    exec_start: str | None = None
    for line in _logical_lines(unit_text):
        if line.startswith(PRESERVED_DIRECTIVES):
            directives.append(line)
            continue
        if not line.startswith(PINNED_DIRECTIVES):
            continue
        rewritten = line.replace(CANONICAL_PREFIX, release)
        if line.startswith("ExecStart="):
            exec_start = _isolate_interpreter(rewritten, release)
        else:
            directives.append(rewritten)
    if exec_start is None:
        raise PinError("unit has no ExecStart to pin")
    if CANONICAL_PREFIX in exec_start.replace(release, ""):
        raise PinError(f"unpinned {CANONICAL_PREFIX} path survived rewriting: {exec_start}")
    body = [
        "# GENERATED by deploy/confenge/pin_release.py. DO NOT EDIT.",
        "# Source of truth: deploy/systemd/<unit> at the pinned release.",
        f"# Immutable release: {sha}",
        "[Service]",
        *directives,
        f"Environment=EXTRA_DEPLOYED_SHA={sha}",
        f"Environment=EXTRA_CODE_SHA={sha}",
        # A root-run diagnostic can bypass 0555 and recreate __pycache__ in an
        # otherwise immutable release. Suppress bytecode for every pinned
        # process; the venv remains the only mutable interpreter input.
        "Environment=PYTHONDONTWRITEBYTECODE=1",
        # Parent ExecStart uses -P, but children (contact-cycle DUI export)
        # inherit Environment only. PYTHONSAFEPATH stops cwd from shadowing
        # the release scripts package the same way -P does for the parent.
        "Environment=PYTHONSAFEPATH=1",
        # Clear the inherited ExecStart before appending the pinned one.
        "ExecStart=",
        exec_start,
    ]
    # A legacy base unit on the VPS may still consider lock-busy exit 75 a
    # success. The immutable PNCP drop-in must override that semantic even
    # before a fresh-install base unit is deployed.
    if "scripts.crawl.run_contracts_incremental" in unit_text:
        body.extend(["SuccessExitStatus=", "Restart=no"])
    return "\n".join(body) + "\n"


def _run(argv: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(argv, check=check, text=True, capture_output=True, timeout=120)  # noqa: S603


def plan(sha: str) -> dict[str, str]:
    """Render every drop-in up front so a bad unit aborts before any write."""
    if not FULL_SHA.fullmatch(sha):
        raise PinError(f"a full 40-character release SHA is required, got {sha!r}")
    release = RELEASE_ROOT / sha
    if not release.is_dir():
        raise PinError(f"release directory does not exist: {release}")
    if not (release / ".venv" / "bin" / "python").is_file():
        raise PinError(f"release has no interpreter: {release}/.venv/bin/python")
    rendered: dict[str, str] = {}
    for unit in CHAIN_UNITS:
        source = UNIT_SOURCE / unit
        if not source.is_file():
            raise PinError(f"versioned unit file is missing: {source}")
        try:
            # Validate every preserved timeout before the first host write, so
            # an unsupported source directive cannot leave a half-pinned chain.
            _source_timeout_start_seconds(unit)
            rendered[unit] = render_dropin(source.read_text(encoding="utf-8"), sha)
        except PinError as exc:
            raise PinError(f"{unit}: {exc}") from exc
    return rendered


def foreign_execstart_dropins() -> dict[str, list[str]]:
    """Find drop-ins other than ours that also override ExecStart.

    The pinned drop-in sorts last and clears ExecStart before setting its own, so
    any earlier drop-in that added an argument would be silently discarded. That
    is not hypothetical: a hand-written 50-durable-checkpoint.conf carried
    --checkpoint-dir, the pin dropped it, and the crawler died writing into the
    read-only release. Whatever such a drop-in configures belongs in the
    versioned unit file; until it moves there, refuse to pin.
    """
    found: dict[str, list[str]] = {}
    for unit in CHAIN_UNITS:
        directory = SYSTEMD_ROOT / f"{unit}.d"
        if not directory.is_dir():
            continue
        offenders = [
            path.name
            for path in sorted(directory.glob("*.conf"))
            if path.name != DROPIN_NAME and "ExecStart=" in path.read_text(encoding="utf-8")
        ]
        if offenders:
            found[unit] = offenders
    return found


def timer_states() -> dict[str, dict[str, str]]:
    """Return the observable enabled/active state of every canonical timer."""
    return {
        unit: {
            "enabled": _run(["systemctl", "is-enabled", unit], check=False).stdout.strip() or "unknown",
            "active": _run(["systemctl", "is-active", unit], check=False).stdout.strip() or "unknown",
        }
        for unit in CHAIN_TIMERS
    }


def _systemd_readback_unit(unit: str) -> str:
    """Return a concrete unit name that systemd can resolve for readback.

    ``systemctl show foo@.service`` succeeds but returns empty properties on
    the production systemd version.  A synthetic, inactive instance resolves
    the same template and drop-ins without starting it or changing its enabled
    state, so verification observes the effective configuration fail-closed.
    """
    if unit.endswith("@.service"):
        return f"{unit.removesuffix('@.service')}@pin-readback.service"
    return unit


def apply(
    sha: str,
    *,
    dry_run: bool = False,
    preserve_timer_state: bool = False,
) -> dict[str, object]:
    rendered = plan(sha)
    if foreign := foreign_execstart_dropins():
        raise PinError(
            "drop-ins outside this tool also set ExecStart and would be discarded by the pin; "
            f"move their configuration into deploy/systemd and remove them: {foreign}"
        )
    written: list[str] = []
    timer_states_before = timer_states() if preserve_timer_state and not dry_run else None
    if not dry_run:
        for unit, body in rendered.items():
            target_dir = SYSTEMD_ROOT / f"{unit}.d"
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / DROPIN_NAME
            tmp = target.with_suffix(".conf.tmp")
            tmp.write_text(body, encoding="utf-8")
            tmp.replace(target)
            written.append(str(target))
        _run(["systemctl", "daemon-reload"])
        if not preserve_timer_state:
            # --now is required for both the source trigger and independent monitor;
            # enabling alone would defer them until the next boot.
            _run(["systemctl", "enable", "--now", *CHAIN_TIMERS])
            if CHAIN_DISABLED_TIMERS:
                # `systemctl disable --now` with no unit argument is a usage error,
                # so an empty suppression contract must be a no-op, not a failure.
                _run(["systemctl", "disable", "--now", *CHAIN_DISABLED_TIMERS])
        _run(["systemctl", "enable", *CHAIN_ENABLED_SERVICES])
        if preserve_timer_state and timer_states() != timer_states_before:
            raise PinError("timer state changed while a pause-preserving release pin was applied")
    return {
        "schema": "confenge.release_pin.v1",
        "release_sha": sha,
        "units_pinned": list(rendered),
        "timer_policy": "PRESERVE" if preserve_timer_state else "CANONICAL_SCHEDULE",
        "timers_enabled": [] if preserve_timer_state else list(CHAIN_TIMERS),
        "timers_disabled": [] if preserve_timer_state else list(CHAIN_DISABLED_TIMERS),
        "timer_states_before": timer_states_before,
        "services_enabled": list(CHAIN_ENABLED_SERVICES),
        "dropins_written": written,
        "dry_run": dry_run,
    }


def verify(
    sha: str,
    *,
    require_canonical_schedule: bool = True,
    expected_timer_states: dict[str, dict[str, str]] | None = None,
) -> dict[str, object]:
    """Read back what systemd actually resolved, not what we intended to write."""
    drift: list[dict[str, str]] = []
    unsafe_python_path: list[dict[str, str]] = []
    bytecode_writes_enabled: list[dict[str, str]] = []
    working_directory_drift: list[dict[str, str]] = []
    working_directory_not_writable: list[dict[str, str]] = []
    timeout_start_drift: list[dict[str, str]] = []
    release = f"{RELEASE_ROOT}/{sha}"
    for unit in CHAIN_UNITS:
        readback_unit = _systemd_readback_unit(unit)
        result = _run(["systemctl", "show", readback_unit, "-p", "ExecStart", "--value"], check=False)
        resolved = (result.stdout or "").strip()
        if release not in resolved:
            drift.append({"unit": unit, "resolved": resolved[:400]})
        interpreter = f"{release}/.venv/bin/python"
        if interpreter not in resolved or re.search(r"(?:^|\s)-P(?:\s|$)", resolved) is None:
            unsafe_python_path.append({"unit": unit, "resolved": resolved[:400]})

        environment = (
            _run(["systemctl", "show", readback_unit, "-p", "Environment", "--value"], check=False).stdout
            or ""
        ).strip()
        if f"PYTHONPATH={release}" not in environment:
            drift.append({"unit": unit, "resolved": environment[:400]})
        if "PYTHONDONTWRITEBYTECODE=1" not in environment:
            bytecode_writes_enabled.append({"unit": unit, "resolved": environment[:400]})
        if "PYTHONSAFEPATH=1" not in environment:
            unsafe_python_path.append({"unit": unit, "resolved": environment[:400]})

        working_directory = (
            _run(["systemctl", "show", readback_unit, "-p", "WorkingDirectory", "--value"], check=False).stdout
            or ""
        ).strip()
        user = (
            _run(["systemctl", "show", readback_unit, "-p", "User", "--value"], check=False).stdout or ""
        ).strip()
        if not working_directory or working_directory == release or working_directory.startswith(f"{release}/"):
            working_directory_drift.append({"unit": unit, "working_directory": working_directory or "MISSING"})
        else:
            writable_probe = (
                ["test", "-w", working_directory]
                if user in {"", "root"}
                else ["runuser", "-u", user, "--", "test", "-w", working_directory]
            )
            if _run(writable_probe, check=False).returncode != 0:
                working_directory_not_writable.append(
                    {"unit": unit, "user": user or "root", "working_directory": working_directory}
                )
        has_timeout, expected_timeout = _source_timeout_start_seconds(unit)
        if has_timeout:
            observed_timeout = (
                _run(
                    ["systemctl", "show", readback_unit, "-p", "TimeoutStartUSec", "--value"],
                    check=False,
                ).stdout
                or ""
            ).strip()
            try:
                actual_timeout = _systemd_timeout_seconds(observed_timeout)
            except PinError:
                actual_timeout = None
                timeout_was_parsed = False
            else:
                timeout_was_parsed = True
            if not timeout_was_parsed or actual_timeout != expected_timeout:
                timeout_start_drift.append(
                    {
                        "unit": unit,
                        "expected": (
                            "infinity" if expected_timeout is None else f"{expected_timeout.normalize():f}s"
                        ),
                        "observed": observed_timeout or "MISSING",
                    }
                )
    observed_timer_states = timer_states()
    timer_state_drift = (
        []
        if expected_timer_states is None or observed_timer_states == expected_timer_states
        else [{"expected": expected_timer_states, "observed": observed_timer_states}]
    )
    disabled: list[str] = []
    scheduled_units = (*CHAIN_TIMERS, *CHAIN_ENABLED_SERVICES) if require_canonical_schedule else CHAIN_ENABLED_SERVICES
    for unit in scheduled_units:
        state = _run(["systemctl", "is-enabled", unit], check=False).stdout.strip()
        if state != "enabled":
            disabled.append(f"{unit}={state or 'unknown'}")
    # A timer that is enabled but not loaded fires nothing until the next boot.
    inactive_timers: list[str] = []
    if require_canonical_schedule:
        for unit in CHAIN_TIMERS:
            state = observed_timer_states[unit]["active"]
            if state != "active":
                inactive_timers.append(f"{unit}={state or 'unknown'}")
    independently_scheduled: list[str] = []
    for unit in CHAIN_DISABLED_TIMERS:
        enabled = _run(["systemctl", "is-enabled", unit], check=False).stdout.strip()
        active = _run(["systemctl", "is-active", unit], check=False).stdout.strip()
        if enabled not in {"disabled", "masked"} or active != "inactive":
            independently_scheduled.append(
                f"{unit}=enabled:{enabled or 'unknown'},active:{active or 'unknown'}"
            )
    pncp_service_semantic_drift: list[dict[str, str]] = []
    for prop in ("SuccessExitStatus", "Restart"):
        observed = (
            _run(["systemctl", "show", "pncp-contracts.service", "-p", prop, "--value"], check=False).stdout
            or ""
        ).strip()
        if prop == "SuccessExitStatus":
            if observed:
                pncp_service_semantic_drift.append({"property": prop, "observed": observed})
        elif observed != "no":
            pncp_service_semantic_drift.append({"property": prop, "observed": observed})
    return {
        "schema": "confenge.release_pin_verification.v1",
        "release_sha": sha,
        "ok": not any(
            (
                drift,
                unsafe_python_path,
                bytecode_writes_enabled,
                working_directory_drift,
                working_directory_not_writable,
                timeout_start_drift,
                disabled,
                inactive_timers,
                timer_state_drift,
                independently_scheduled,
                pncp_service_semantic_drift,
            )
        ),
        "release_drift": drift,
        "unsafe_python_path": unsafe_python_path,
        "bytecode_writes_enabled": bytecode_writes_enabled,
        "working_directory_drift": working_directory_drift,
        "working_directory_not_writable": working_directory_not_writable,
        "timeout_start_drift": timeout_start_drift,
        "not_enabled": disabled,
        "timers_not_active": inactive_timers,
        "timer_policy": "CANONICAL_SCHEDULE" if require_canonical_schedule else "PRESERVE",
        "timer_states": observed_timer_states,
        "timer_state_drift": timer_state_drift,
        "downstream_timers_scheduled": independently_scheduled,
        "pncp_service_semantic_drift": pncp_service_semantic_drift,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sha", help="full 40-character release SHA under /opt/extra-consultoria-releases")
    parser.add_argument("--dry-run", action="store_true", help="render and validate without touching the host")
    parser.add_argument("--verify-only", action="store_true", help="only read back the resolved host state")
    parser.add_argument(
        "--preserve-timer-state",
        action="store_true",
        help="pin code without enabling, disabling, starting, or stopping any timer",
    )
    args = parser.parse_args(argv)
    try:
        if args.verify_only:
            report = verify(args.sha, require_canonical_schedule=not args.preserve_timer_state)
        else:
            report = apply(
                args.sha,
                dry_run=args.dry_run,
                preserve_timer_state=args.preserve_timer_state,
            )
            if not args.dry_run:
                report = {
                    **report,
                    "verification": verify(
                        args.sha,
                        require_canonical_schedule=not args.preserve_timer_state,
                        expected_timer_states=report.get("timer_states_before"),
                    ),
                }
    except (PinError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    verification = report.get("verification") if isinstance(report, dict) else None
    if isinstance(verification, dict) and verification.get("ok") is False:
        return 2
    if report.get("ok") is False:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
