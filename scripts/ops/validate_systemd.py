"""Static fail-closed validation for pre-VPS systemd units."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PRIORITY = ("pncp", "ciga-dom", "sc-compras")


def validate(root: Path = Path("deploy/systemd")) -> list[str]:
    errors: list[str] = []
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
        for required in ("User=extra-consultoria", "EnvironmentFile=/opt/extra-consultoria/.env", "TimeoutStartSec=", "Restart=no", "/usr/bin/flock", "OnFailure=extra-onfailure@%n.service", "StandardOutput=journal"):
            if required not in service_text:
                errors.append(f"{service.name}: missing {required}")
        for required in ("RandomizedDelaySec=", "Persistent=true", f"Unit={service.name}"):
            if required not in timer_text:
                errors.append(f"{timer.name}: missing {required}")
    for service in root.glob("*.service"):
        text = service.read_text(encoding="utf-8")
        if "OnFailure=onfailure@" in text:
            errors.append(f"{service.name}: legacy OnFailure reference")
    return errors


def main() -> int:
    errors = validate()
    print(json.dumps({"status": "pass" if not errors else "fail", "errors": errors}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
