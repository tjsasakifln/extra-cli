#!/usr/bin/env python3
"""Run the canonical CONFENGE feed pipeline and atomically publish its result.

This is orchestration only: generation stays in confenge_outreach_pipeline and
publication stays in confenge_activation.publish. It never sends mail.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path

from scripts.confenge_activation.publish import (
    DEFAULT_ALERT_LEDGER,
    DEFAULT_MAX_AGE_HOURS,
    DEFAULT_STATE_PATH,
    atomic_publish_directory,
    record_feed_cycle_state,
)


def _run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _pipeline_runtime() -> tuple[Path, dict[str, str]]:
    """Bind the child pipeline to the same immutable checkout as this runner.

    Production deliberately runs this orchestrator from the canonical data/evidence
    directory.  Invoking the child with ``python -m`` would therefore let an older
    ``scripts`` package in that directory shadow the deployed release.  Execute the
    release entrypoint by absolute path and put its repository root first on
    ``PYTHONPATH`` while preserving the canonical working directory.
    """

    runtime_root = Path(__file__).resolve().parents[2]
    entrypoint = runtime_root / "scripts" / "confenge_outreach_pipeline" / "__main__.py"
    if not entrypoint.is_file():
        raise FileNotFoundError(f"canonical outreach pipeline entrypoint not found: {entrypoint}")
    env = os.environ.copy()
    inherited_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join(part for part in (str(runtime_root), inherited_pythonpath) if part)
    return entrypoint, env


def run_cycle(
    *,
    output_root: Path,
    durable_contacts: Path,
    publish_dir: Path,
    as_of: date,
    max_age_hours: float,
    state_path: Path,
    alert_ledger: Path,
) -> dict:
    if not durable_contacts.is_file():
        raise FileNotFoundError(f"durable contact projection not found: {durable_contacts}")
    contact_report = durable_contacts.with_name("contact-projection-report.json")
    if not contact_report.is_file():
        raise FileNotFoundError(f"durable contact projection report not found: {contact_report}")
    if not (os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL")):
        raise RuntimeError("LOCAL_DATALAKE_DSN or DATABASE_URL is required")

    run_dir = output_root / f"confenge-feed-cycle-{_run_id()}"
    run_dir.mkdir(parents=True, exist_ok=False)
    pipeline_entrypoint, pipeline_env = _pipeline_runtime()
    command = [
        sys.executable,
        str(pipeline_entrypoint),
        "run",
        "--out",
        str(run_dir),
        "--as-of",
        as_of.isoformat(),
        "--use-activation-planner",
        "--durable-contacts",
        str(durable_contacts),
        "--skip-contacts",
        "--no-resume",
        "--quiet",
    ]
    published_current = publish_dir / "current"
    if published_current.is_dir():
        # Membership deactivations are derived against what is publicly served now.
        command += ["--published-feed-dir", str(published_current)]
    completed = subprocess.run(  # noqa: S603
        command,
        check=False,
        text=True,
        capture_output=True,
        env=pipeline_env,
    )
    (run_dir / "cycle-command.json").write_text(
        json.dumps(
            {
                "command": command[1:],
                "exit_code": completed.returncode,
                "stdout": completed.stdout[-20_000:],
                "stderr": completed.stderr[-20_000:],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"canonical outreach pipeline failed with exit {completed.returncode}: {completed.stderr[-2000:].strip()}"
        )

    publication = atomic_publish_directory(
        run_dir / "06_warmbly_feed",
        publish_dir,
        max_age_hours=max_age_hours,
        state_path=state_path,
        alert_ledger=alert_ledger,
    )
    result = {
        "ok": bool(publication.get("ok")),
        "run_dir": str(run_dir),
        "durable_contacts": str(durable_contacts),
        "publication": publication,
    }
    (run_dir / "cycle-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--durable-contacts", type=Path, required=True)
    parser.add_argument("--publish-dir", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--max-age-hours", type=float, default=DEFAULT_MAX_AGE_HOURS)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--alert-ledger", type=Path, default=DEFAULT_ALERT_LEDGER)
    args = parser.parse_args(argv)
    started = time.monotonic()
    attempted_at = datetime.now(UTC)
    try:
        result = run_cycle(
            output_root=args.output_root,
            durable_contacts=args.durable_contacts,
            publish_dir=args.publish_dir,
            as_of=args.as_of,
            max_age_hours=args.max_age_hours,
            state_path=args.state,
            alert_ledger=args.alert_ledger,
        )
    except Exception as exc:  # noqa: BLE001
        record_feed_cycle_state(
            args.state,
            alert_ledger=args.alert_ledger,
            status="FAILED",
            at=attempted_at,
            alert_reason="FEED_CYCLE_FAILED",
            detail={
                "error": str(exc),
                "duration_seconds": round(time.monotonic() - started, 6),
                "output_root": str(args.output_root),
                "durable_contacts": str(args.durable_contacts),
                "publish_dir": str(args.publish_dir),
            },
        )
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    record_feed_cycle_state(
        args.state,
        alert_ledger=args.alert_ledger,
        status="PUBLISHED" if result.get("ok") else str(result.get("publication", {}).get("reason") or "FAILED"),
        at=attempted_at,
        detail={
            **result,
            "duration_seconds": round(time.monotonic() - started, 6),
        },
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 3


if __name__ == "__main__":
    raise SystemExit(main())
