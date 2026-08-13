"""Static fail-closed validation for pre-VPS systemd units.

Validates not only crawl priority pairs but runtime-relevant defects observed
on the Netcup host: invalid OnCalendar, StartLimit* outside [Unit], system
python without venv, empty WEBHOOK patterns that always fail OnFailure.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PRIORITY = ("pncp", "ciga-dom", "sc-compras")

# Observed bad calendars that systemd rejects or silently mis-schedules
INVALID_ONCALENDAR = (
    re.compile(r"OnCalendar=\*:0/60:00"),
    re.compile(r"OnCalendar=\*:0/60"),
)

VENV_PYTHON_MARKERS = (
    "/opt/extra-consultoria/.venv/bin/python",
    "/opt/extra-consultoria/.venv/bin/python3",
)
SYSTEM_PYTHON_MARKERS = (
    "ExecStart=/usr/bin/python3",
    "ExecStart=/usr/bin/python ",
)

PROCESS_DOCUMENTS_SERVICE = "extra-process-documents-incremental.service"
PROCESS_DOCUMENTS_TIMER = "extra-process-documents-incremental.timer"


def _sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = "_preamble"
    sections[current] = []
    for line in text.splitlines():
        m = re.match(r"^\[([^\]]+)\]\s*$", line)
        if m:
            current = m.group(1)
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {k: "\n".join(v) for k, v in sections.items()}


def validate(root: Path = Path("deploy/systemd")) -> list[str]:
    errors: list[str] = []
    if not root.is_dir():
        return [f"systemd dir missing: {root}"]

    if len(list(root.glob("*onfailure@.service"))) != 1:
        errors.append("exactly one OnFailure template is required")

    for source in PRIORITY:
        service = root / f"extra-crawl-{source}.service"
        timer = root / f"extra-crawl-{source}.timer"
        if not service.is_file() or not timer.is_file():
            errors.append(f"missing pair for {source}")
            continue
        service_text = service.read_text(encoding="utf-8")
        timer_text = timer.read_text(encoding="utf-8")
        for required in (
            "User=extra-consultoria",
            "EnvironmentFile=/opt/extra-consultoria/.env",
            "TimeoutStartSec=",
            "Restart=no",
            "/usr/bin/flock",
            "OnFailure=extra-onfailure@%n.service",
            "StandardOutput=journal",
        ):
            if required not in service_text:
                errors.append(f"{service.name}: missing {required}")
        for required in ("RandomizedDelaySec=", "Persistent=true", f"Unit={service.name}"):
            if required not in timer_text:
                errors.append(f"{timer.name}: missing {required}")

    process_service = root / PROCESS_DOCUMENTS_SERVICE
    process_timer = root / PROCESS_DOCUMENTS_TIMER
    if not process_service.is_file() or not process_timer.is_file():
        errors.append("missing canonical process-documents service/timer pair")
    else:
        service_text = process_service.read_text(encoding="utf-8")
        timer_text = process_timer.read_text(encoding="utf-8")
        for required in (
            "User=extra-consultoria",
            "Group=extra-consultoria",
            "WorkingDirectory=/opt/extra-consultoria",
            "EnvironmentFile=/opt/extra-consultoria/.env",
            "PROCESS_DOCUMENTS_RAW_ROOT=/var/lib/extra-consultoria/raw/process_documents",
            "PROCESS_DOCUMENTS_META_ROOT=/var/lib/extra-consultoria/output/process_documents",
            "ExecStart=/opt/extra-consultoria/.venv/bin/python",
        ):
            if required not in service_text:
                errors.append(f"{process_service.name}: missing {required}")
        for forbidden in ("User=extra\n", "/opt/extra-cli", "/var/lib/extra-cli"):
            if forbidden in service_text:
                errors.append(f"{process_service.name}: forbidden legacy value {forbidden!r}")
        if f"Unit={PROCESS_DOCUMENTS_SERVICE}" not in timer_text:
            errors.append(f"{process_timer.name}: timer does not bind canonical service")
        for marker in ("ExtraDeploySHA", "ExtraConfigSHA"):
            service_match = re.search(rf"^# {marker}=(.+)$", service_text, flags=re.MULTILINE)
            timer_match = re.search(rf"^# {marker}=(.+)$", timer_text, flags=re.MULTILINE)
            if not service_match or not timer_match or service_match.group(1) != timer_match.group(1):
                errors.append(f"process-documents pair has divergent {marker}")
    # Contracts / backup / health / metrics — operational surface for campaign
    for service in sorted(root.glob("*.service")):
        text = service.read_text(encoding="utf-8")
        if "OnFailure=onfailure@" in text:
            errors.append(f"{service.name}: legacy OnFailure reference")

        sections = _sections(text)
        unit_sec = sections.get("Unit", "")
        service_sec = sections.get("Service", "")

        # StartLimit* belongs in [Unit] on modern systemd; [Service] is rejected
        for key in ("StartLimitIntervalSec=", "StartLimitBurst="):
            if key in service_sec and key not in unit_sec:
                errors.append(
                    f"{service.name}: {key.rstrip('=')} must be in [Unit], not [Service]"
                )

        # Prefer venv for app python entrypoints
        if any(m in text for m in SYSTEM_PYTHON_MARKERS):
            if not any(m in text for m in VENV_PYTHON_MARKERS):
                # health/alerts may use system python only if module is stdlib — still flag app scripts
                if "scripts/" in text or "monitor.py" in text or "weekly_cycle" in text:
                    errors.append(
                        f"{service.name}: uses system python for app scripts; "
                        "prefer /opt/extra-consultoria/.venv/bin/python"
                    )

    for timer in sorted(root.glob("*.timer")):
        text = timer.read_text(encoding="utf-8")
        # Ignore comment lines when checking calendar directives
        active = "\n".join(
            ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")
        )
        for pat in INVALID_ONCALENDAR:
            if pat.search(active):
                errors.append(
                    f"{timer.name}: invalid OnCalendar (use hourly: OnCalendar=hourly "
                    "or OnCalendar=*-*-* *:00:00)"
                )
        if (
            "OnCalendar=" not in active
            and "OnUnitActiveSec=" not in active
            and "OnBootSec=" not in active
        ):
            errors.append(f"{timer.name}: missing schedule directive")

    # OnFailure template must not hard-require empty WEBHOOK without guard
    onfailure = next(iter(root.glob("*onfailure@.service")), None)
    if onfailure is not None:
        text = onfailure.read_text(encoding="utf-8")
        if "WEBHOOK_URL" in text and "test -n" not in text and "if " not in text:
            # curl with empty URL fails the unit and cascades failed OnFailure jobs
            if "curl" in text and "${WEBHOOK_URL}" in text:
                errors.append(
                    f"{onfailure.name}: WEBHOOK_URL used without empty-guard; "
                    "OnFailure will fail when webhook unset"
                )

    return errors


def main() -> int:
    errors = validate()
    print(json.dumps({"status": "pass" if not errors else "fail", "errors": errors}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
