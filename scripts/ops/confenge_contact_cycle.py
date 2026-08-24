#!/usr/bin/env python3
"""Continuously materialize the canonical TARGET_CONFIRMED contact projection.

The durable workers do the enrichment.  This coordinator only creates or
resumes one full-population cohort, waits for an explicit terminal state for
every account, publishes the immutable batch snapshot, and atomically advances
``contact-discovery/current``.  A failed or partial run never replaces the last
complete projection and never sends mail.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT_ROOT = Path("/var/lib/extra-consultoria/output/contact-discovery")
DEFAULT_STATE_PATH = Path("/var/lib/extra-consultoria/contact-discovery/cycle-state.json")
DEFAULT_ALERT_LEDGER = Path("/var/lib/extra-consultoria/alerts/confenge-contact-cycle.jsonl")
TERMINAL_STATES = ("succeeded", "blocked", "dlq", "cancelled")
ACTIVE_STATES = ("pending", "running", "retryable")


class CommandError(RuntimeError):
    """A contact-discovery CLI command failed or returned invalid JSON."""


JsonRunner = Callable[[list[str]], dict[str, Any]]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    finally:
        tmp.unlink(missing_ok=True)


def _read_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _append_alert(path: Path, *, reason: str, detail: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "schema_id": "confenge.contact_discovery.cycle_alert.v1",
        "at": _iso(_utcnow()),
        "reason": reason,
        **detail,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_dir(path: Path) -> None:
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _run_json(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, check=False, capture_output=True, text=True)  # noqa: S603
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout)[-4_000:].strip()
        raise CommandError(f"command exited {completed.returncode}: {detail}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise CommandError("command returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise CommandError("command returned a non-object JSON payload")
    return payload


def _batch_command(*args: str) -> list[str]:
    return [sys.executable, "-m", "scripts.decision_unit_intelligence", "batch", *args]


def _counts(progress: dict[str, Any]) -> dict[str, int]:
    counts_value = progress.get("counts")
    raw: dict[str, Any] = counts_value if isinstance(counts_value, dict) else {}
    return {name: int(raw.get(name) or 0) for name in (*ACTIVE_STATES, *TERMINAL_STATES)}


def _promote_projection(*, projection_dir: Path, output_root: Path) -> Path:
    contacts = projection_dir / "contacts.jsonl"
    report = projection_dir / "contact-projection-report.json"
    if not contacts.is_file() or not report.is_file():
        raise FileNotFoundError("complete contact projection files are required before promotion")

    current = output_root / "current"
    relative = projection_dir.relative_to(output_root)
    link_tmp = output_root / f".current.tmp-{projection_dir.name}"
    link_tmp.unlink(missing_ok=True)
    link_tmp.symlink_to(relative, target_is_directory=True)
    os.replace(link_tmp, current)
    _fsync_dir(output_root)
    return current.resolve()


def run_cycle(
    *,
    output_root: Path,
    state_path: Path,
    alert_ledger: Path,
    search_backend: str,
    searxng_url: str | None,
    service: str,
    backend_concurrency: int,
    domain_concurrency: int,
    poll_seconds: float,
    timeout_seconds: float,
    runner: JsonRunner = _run_json,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = _utcnow,
) -> dict[str, Any]:
    """Run or resume one full TARGET_CONFIRMED cycle and promote only at 100%."""
    if search_backend == "off":
        raise ValueError("continuous canonical enrichment requires a public search backend")
    if backend_concurrency < 1 or domain_concurrency < 1:
        raise ValueError("concurrency limits must be positive")

    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    projections = output_root / "projections"
    projections.mkdir(parents=True, exist_ok=True)
    state = _read_state(state_path)
    prior_active = str(state.get("active_cohort") or "").strip()
    resume = bool(prior_active and state.get("last_status") != "COMPLETED")
    cohort = prior_active if resume else f"target-confirmed-auto-{now().strftime('%Y%m%dT%H%M%SZ')}"
    started_at = now()
    started_monotonic = time.monotonic()
    projection_dir = projections / cohort

    try:
        if projection_dir.is_dir():
            current = _promote_projection(projection_dir=projection_dir, output_root=output_root)
            report = json.loads((projection_dir / "contact-projection-report.json").read_text(encoding="utf-8"))
            result = {
                "ok": True,
                "resumed": True,
                "cohort": cohort,
                "projection_dir": str(projection_dir),
                "current": str(current),
                "report": report,
                "recovered_after_projection": True,
            }
            _atomic_json(
                state_path,
                {
                    **state,
                    "schema_id": "confenge.contact_discovery.cycle_state.v1",
                    "active_cohort": None,
                    "last_status": "COMPLETED",
                    "last_success_at": _iso(now()),
                    "last_result": result,
                },
            )
            return result

        progress: dict[str, Any] | None = None
        if resume:
            progress = runner(_batch_command("progress", "--cohort", cohort))
            if int(progress.get("denominator") or 0) <= 0:
                progress = None

        if progress is None:
            enqueue = [
                "enqueue",
                "--cohort",
                cohort,
                "--out",
                str(output_root),
                "--population",
                "target-confirmed",
                "--search-backend",
                search_backend,
                "--service",
                service,
                "--backend-concurrency",
                str(backend_concurrency),
                "--domain-concurrency",
                str(domain_concurrency),
                "--search-cache-dir",
                str(output_root / "search-cache"),
                "--verify-email-dns",
            ]
            if searxng_url:
                enqueue.extend(("--searxng-url", searxng_url))
            current_contacts = output_root / "current" / "contacts.jsonl"
            if current_contacts.is_file():
                enqueue.extend(("--existing-contacts", str(current_contacts.resolve())))
            enqueued = runner(_batch_command(*enqueue))
            enqueued_progress = enqueued.get("progress")
            progress = enqueued_progress if isinstance(enqueued_progress, dict) else {}

        if progress is None:
            raise RuntimeError("contact cohort progress is unavailable")
        denominator = int(progress.get("denominator") or 0)
        if denominator <= 0:
            raise RuntimeError("canonical TARGET_CONFIRMED denominator is empty")
        _atomic_json(
            state_path,
            {
                **state,
                "schema_id": "confenge.contact_discovery.cycle_state.v1",
                "active_cohort": cohort,
                "last_status": "RUNNING",
                "last_started_at": _iso(started_at),
                "last_progress": progress,
            },
        )

        while True:
            counts = _counts(progress)
            active = sum(counts[name] for name in ACTIVE_STATES)
            terminal = sum(counts[name] for name in TERMINAL_STATES)
            denominator = int(progress.get("denominator") or 0)
            if terminal > denominator:
                raise RuntimeError("terminal job count exceeds the immutable denominator")
            if active == 0:
                if terminal != denominator:
                    raise RuntimeError(
                        f"cohort stopped without closure: terminal={terminal} denominator={denominator}"
                    )
                break
            elapsed = time.monotonic() - started_monotonic
            if elapsed >= timeout_seconds:
                raise TimeoutError(
                    f"contact cycle timed out with {active} active jobs after {elapsed:.1f}s"
                )
            _atomic_json(
                state_path,
                {
                    **_read_state(state_path),
                    "active_cohort": cohort,
                    "last_status": "RUNNING",
                    "last_progress_at": _iso(now()),
                    "last_progress": progress,
                },
            )
            sleep(poll_seconds)
            progress = runner(_batch_command("progress", "--cohort", cohort))

        published = runner(
            _batch_command("publish", "--cohort", cohort, "--out", str(output_root))
        )
        if published.get("approved") is not True:
            raise RuntimeError("terminal cohort snapshot was not approved")

        staging = Path(tempfile.mkdtemp(prefix=f".{cohort}.", dir=str(projections)))
        try:
            exported = runner(
                _batch_command(
                    "export-contacts",
                    "--cohort",
                    cohort,
                    "--out",
                    str(staging / "contacts.jsonl"),
                    "--report",
                    str(staging / "contact-projection-report.json"),
                )
            )
            if exported.get("written") is not True:
                raise RuntimeError("full contact projection was not written")
            cycle_result = {
                "schema_id": "confenge.contact_discovery.cycle_result.v1",
                "cohort": cohort,
                "completed_at": _iso(now()),
                "progress": progress,
                "snapshot": published,
                "projection": exported,
            }
            _atomic_json(staging / "cycle-result.json", cycle_result)
            for artifact in (
                staging / "contacts.jsonl",
                staging / "contact-projection-report.json",
                staging / "cycle-result.json",
            ):
                with artifact.open("rb") as handle:
                    os.fsync(handle.fileno())
            _fsync_dir(staging)
            os.replace(staging, projection_dir)
            _fsync_dir(projections)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

        current = _promote_projection(projection_dir=projection_dir, output_root=output_root)
        result = {
            "ok": True,
            "resumed": resume,
            "cohort": cohort,
            "denominator": denominator,
            "counts": _counts(progress),
            "projection_dir": str(projection_dir),
            "current": str(current),
            "snapshot": published,
            "projection": exported,
            "duration_seconds": round(time.monotonic() - started_monotonic, 6),
        }
        _atomic_json(
            state_path,
            {
                **_read_state(state_path),
                "schema_id": "confenge.contact_discovery.cycle_state.v1",
                "active_cohort": None,
                "last_status": "COMPLETED",
                "last_success_at": _iso(now()),
                "last_result": result,
            },
        )
        return result
    except Exception as exc:
        failure = {
            "schema_id": "confenge.contact_discovery.cycle_failure.v1",
            "cohort": cohort,
            "error": str(exc),
            "failed_at": _iso(now()),
            "duration_seconds": round(time.monotonic() - started_monotonic, 6),
        }
        _atomic_json(
            state_path,
            {
                **_read_state(state_path),
                "schema_id": "confenge.contact_discovery.cycle_state.v1",
                "active_cohort": cohort,
                "last_status": "FAILED",
                "last_failure": failure,
            },
        )
        _append_alert(alert_ledger, reason="CONTACT_CYCLE_FAILED", detail=failure)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--alert-ledger", type=Path, default=DEFAULT_ALERT_LEDGER)
    parser.add_argument("--search-backend", choices=("searxng", "ddgs"), default="searxng")
    parser.add_argument("--searxng-url", default=os.getenv("CONFENGE_SEARXNG_URL"))
    parser.add_argument("--service", default="reajuste_14133")
    parser.add_argument("--backend-concurrency", type=int, default=12)
    parser.add_argument("--domain-concurrency", type=int, default=1)
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    parser.add_argument("--timeout-hours", type=float, default=18.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_cycle(
            output_root=args.output_root,
            state_path=args.state,
            alert_ledger=args.alert_ledger,
            search_backend=args.search_backend,
            searxng_url=args.searxng_url,
            service=args.service,
            backend_concurrency=args.backend_concurrency,
            domain_concurrency=args.domain_concurrency,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.timeout_hours * 3600,
        )
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
