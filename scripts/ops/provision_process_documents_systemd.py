"""Render and install the canonical process-documents systemd pair."""

from __future__ import annotations

import argparse
import grp
import hashlib
import json
import os
import pwd
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = PROJECT_ROOT / "deploy" / "systemd" / "templates"
SERVICE_NAME = "extra-process-documents-incremental.service"
TIMER_NAME = "extra-process-documents-incremental.timer"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class UnitConfig:
    app_user: str
    app_group: str
    app_dir: Path
    state_dir: Path
    env_file: Path
    python: Path
    deploy_sha: str
    config_sha: str

    def replacements(self) -> dict[str, str]:
        return {
            "@APP_USER@": self.app_user,
            "@APP_GROUP@": self.app_group,
            "@APP_DIR@": str(self.app_dir),
            "@STATE_DIR@": str(self.state_dir),
            "@ENV_FILE@": str(self.env_file),
            "@PYTHON@": str(self.python),
            "@DEPLOY_SHA@": self.deploy_sha,
            "@CONFIG_SHA@": self.config_sha,
        }


def preflight(config: UnitConfig) -> list[str]:
    """Return nominal missing prerequisites without changing the host."""
    errors: list[str] = []
    try:
        pwd.getpwnam(config.app_user)
    except KeyError:
        errors.append(f"user missing: {config.app_user}")
    try:
        grp.getgrnam(config.app_group)
    except KeyError:
        errors.append(f"group principal missing: {config.app_group}")
    for label, path in (("app_dir", config.app_dir), ("state_dir", config.state_dir)):
        if not path.is_dir():
            errors.append(f"{label} missing: {path}")
    if not config.env_file.is_file():
        errors.append(f"env_file missing: {config.env_file}")
    if not config.python.is_file() or not os.access(config.python, os.X_OK):
        errors.append(f"venv python missing or not executable: {config.python}")
    if not config.deploy_sha or config.deploy_sha == "unknown":
        errors.append("deploy_sha missing")
    if not config.config_sha or len(config.config_sha) != 64:
        errors.append("config_sha missing or invalid")
    return errors


def render_units(config: UnitConfig, template_dir: Path = TEMPLATE_DIR) -> dict[str, str]:
    rendered: dict[str, str] = {}
    for name in (SERVICE_NAME, TIMER_NAME):
        template = template_dir / f"{name}.in"
        text = template.read_text(encoding="utf-8")
        for marker, value in config.replacements().items():
            text = text.replace(marker, value)
        leftovers = sorted(set(re.findall(r"@[A-Z0-9_]+@", text)))
        if leftovers:
            raise ValueError(f"unrendered markers in {name}: {leftovers}")
        rendered[name] = text
    return rendered


def verify_rendered_units(rendered: dict[str, str]) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="extra-systemd-verify-") as tmp:
        root = Path(tmp)
        paths = []
        for name, text in rendered.items():
            path = root / name
            path.write_text(text, encoding="utf-8")
            paths.append(str(path))
        try:
            proc = subprocess.run(  # noqa: S603
                ["/usr/bin/systemd-analyze", "verify", *paths],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            return False, f"systemd-analyze missing: {exc.filename}"
    output = "\n".join(part.strip() for part in (proc.stdout, proc.stderr) if part.strip())
    return proc.returncode == 0, output


def _atomic_write(path: Path, text: str) -> bool:
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return True


def install_units(
    config: UnitConfig,
    *,
    unit_dir: Path,
    daemon_reload: bool,
    smoke_output: Path | None,
) -> dict[str, Any]:
    errors = preflight(config)
    if errors:
        raise RuntimeError("preflight failed: " + "; ".join(errors))
    rendered = render_units(config)
    verified, verify_output = verify_rendered_units(rendered)
    if not verified:
        raise RuntimeError(f"systemd-analyze verify failed: {verify_output}")
    smoke_env = dict(os.environ)
    smoke_env["PYTHONPATH"] = str(config.app_dir)
    runtime_smoke = subprocess.run(  # noqa: S603
        [str(config.python), "-m", "scripts.process_documents", "--help"],
        cwd=config.app_dir,
        env=smoke_env,
        check=False,
        capture_output=True,
        text=True,
    )
    if runtime_smoke.returncode != 0:
        detail = (runtime_smoke.stderr or runtime_smoke.stdout).strip()
        raise RuntimeError(f"process-documents runtime smoke failed: {detail}")
    changed = [name for name, text in rendered.items() if _atomic_write(unit_dir / name, text)]
    if daemon_reload:
        subprocess.run(["/usr/bin/systemctl", "daemon-reload"], check=True)  # noqa: S603
    evidence = {
        "schema": "extra-process-documents-unit-smoke/v1",
        "status": "PASS",
        "claim": "UNIT_INSTALL_SMOKE_ONLY",
        "vps_operational": False,
        "user": config.app_user,
        "app_dir": str(config.app_dir),
        "state_dir": str(config.state_dir),
        "env_file": str(config.env_file),
        "deploy_sha": config.deploy_sha,
        "config_sha": config.config_sha,
        "unit_dir": str(unit_dir),
        "changed_units": changed,
        "idempotent": not changed,
        "systemd_analyze_verify": "PASS",
        "runtime_smoke": "PASS",
        "timer_service_binding": {
            "service": SERVICE_NAME,
            "timer": TIMER_NAME,
            "same_deploy_sha": True,
            "same_config_sha": True,
        },
    }
    if smoke_output is not None:
        _atomic_write(smoke_output, json.dumps(evidence, indent=2, ensure_ascii=False) + "\n")
    return evidence


def _git_sha(app_dir: Path) -> str:
    try:
        proc = subprocess.run(  # noqa: S603
            ["/usr/bin/git", "-C", str(app_dir), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return "unknown"
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-user", default="extra-consultoria")
    parser.add_argument("--app-group", default="extra-consultoria")
    parser.add_argument("--app-dir", type=Path, default=Path("/opt/extra-consultoria"))
    parser.add_argument("--state-dir", type=Path, default=Path("/var/lib/extra-consultoria"))
    parser.add_argument("--env-file", type=Path, default=Path("/opt/extra-consultoria/.env"))
    parser.add_argument("--python", type=Path, default=None)
    parser.add_argument("--deploy-sha", default=None)
    parser.add_argument("--unit-dir", type=Path, default=Path("/etc/systemd/system"))
    parser.add_argument("--smoke-output", type=Path, default=None)
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--no-daemon-reload", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    python = args.python or args.app_dir / ".venv" / "bin" / "python"
    deploy_sha = args.deploy_sha or _git_sha(args.app_dir)
    config_sha = _sha256(args.env_file) if args.env_file.is_file() else ""
    config = UnitConfig(
        app_user=args.app_user,
        app_group=args.app_group,
        app_dir=args.app_dir,
        state_dir=args.state_dir,
        env_file=args.env_file,
        python=python,
        deploy_sha=deploy_sha,
        config_sha=config_sha,
    )
    errors = preflight(config)
    if errors:
        print(json.dumps({"status": "FAIL", "errors": errors}, indent=2))
        return 2
    try:
        if not args.install:
            rendered = render_units(config)
            verified, output = verify_rendered_units(rendered)
            print(json.dumps({"status": "PASS" if verified else "FAIL", "verify": output}, indent=2))
            return 0 if verified else 2
        evidence = install_units(
            config,
            unit_dir=args.unit_dir,
            daemon_reload=not args.no_daemon_reload,
            smoke_output=args.smoke_output,
        )
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "FAIL", "errors": [str(exc)]}, indent=2))
        return 2
    print(json.dumps(evidence, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
