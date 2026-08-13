"""Leased crawl worker with heartbeat, graceful shutdown and admission control."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import signal
import socket
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from scripts.crawl.runtime_queue import ClaimedJob, CrawlQueue, connect, utcnow
from scripts.crawl.scheduler import SchedulePolicyRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdmissionLimits:
    max_load_per_cpu: float = 0.9
    min_available_memory_ratio: float = 0.1
    min_free_disk_ratio: float = 0.1


def _available_memory_ratio(meminfo_path: Path = Path("/proc/meminfo")) -> float:
    values: dict[str, int] = {}
    for line in meminfo_path.read_text(encoding="utf-8").splitlines():
        key, raw = line.split(":", 1)
        values[key] = int(raw.strip().split()[0])
    total = values.get("MemTotal", 0)
    return values.get("MemAvailable", 0) / total if total else 0.0


def admission_blockers(
    limits: AdmissionLimits,
    *,
    state_path: Path = Path("output/resilience"),
    load_average: float | None = None,
    cpu_count: int | None = None,
    memory_ratio: float | None = None,
    disk_ratio: float | None = None,
) -> list[str]:
    cpus = cpu_count or os.cpu_count() or 1
    load = load_average if load_average is not None else os.getloadavg()[0]
    memory = memory_ratio if memory_ratio is not None else _available_memory_ratio()
    if disk_ratio is None:
        usage = shutil.disk_usage(state_path if state_path.exists() else Path.cwd())
        disk_ratio = usage.free / usage.total if usage.total else 0.0
    blockers: list[str] = []
    if load / cpus > limits.max_load_per_cpu:
        blockers.append("cpu_pressure")
    if memory < limits.min_available_memory_ratio:
        blockers.append("memory_pressure")
    if disk_ratio < limits.min_free_disk_ratio:
        blockers.append("disk_pressure")
    return blockers


class Heartbeat:
    def __init__(
        self,
        *,
        dsn: str,
        job: ClaimedJob,
        worker_id: str,
        interval_seconds: int,
        lease_seconds: int,
    ):
        self.dsn = dsn
        self.job = job
        self.worker_id = worker_id
        self.interval_seconds = interval_seconds
        self.lease_seconds = lease_seconds
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name=f"crawl-heartbeat-{job.id}", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=max(1, self.interval_seconds + 1))

    def _run(self) -> None:
        while not self.stop_event.wait(self.interval_seconds):
            try:
                with connect(self.dsn) as connection:
                    owned = CrawlQueue(connection).heartbeat(
                        self.job,
                        worker_id=self.worker_id,
                        lease_seconds=self.lease_seconds,
                        metrics={"heartbeat_count": 1},
                    )
                    if not owned:
                        return
            except Exception as exc:  # noqa: BLE001 - the lease remains authoritative
                # Lease expiry remains the fail-closed recovery authority.
                logger.warning("crawl heartbeat failed job=%s: %s", self.job.id, exc)
                continue


Executor = Callable[[ClaimedJob, Any], dict[str, Any]]


class CrawlWorker:
    def __init__(
        self,
        *,
        dsn: str,
        worker_id: str | None = None,
        lease_seconds: int = 300,
        heartbeat_seconds: int = 30,
        limits: AdmissionLimits | None = None,
        executor: Executor | None = None,
    ):
        self.dsn = dsn
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}"
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.limits = limits or AdmissionLimits()
        self.executor = executor or execute_job
        self.shutdown_requested = threading.Event()

    def request_shutdown(self, *_args: Any) -> None:
        self.shutdown_requested.set()

    def run_once(self) -> dict[str, Any]:
        blockers = admission_blockers(self.limits)
        if blockers:
            return {"status": "backpressure", "worker_id": self.worker_id, "blockers": blockers}
        policy_registry = SchedulePolicyRegistry.load()
        with connect(self.dsn) as connection:
            queue = CrawlQueue(connection)
            claimed = queue.claim(
                worker_id=self.worker_id,
                limit=1,
                lease_seconds=self.lease_seconds,
            )
        if not claimed:
            return {"status": "idle", "worker_id": self.worker_id}
        job = claimed[0]
        policy = policy_registry.for_source(job.source)
        heartbeat = Heartbeat(
            dsn=self.dsn,
            job=job,
            worker_id=self.worker_id,
            interval_seconds=self.heartbeat_seconds,
            lease_seconds=self.lease_seconds,
        )
        started = time.monotonic()
        heartbeat.start()
        outcome = "failed"
        error_class: str | None = None
        error_message: str | None = None
        cursor_state = job.cursor
        result: dict[str, Any] = {}
        try:
            if self.shutdown_requested.is_set():
                outcome = "interrupted"
            else:
                with connect(self.dsn) as execution_connection:
                    result = self.executor(job, execution_connection)
                outcome = str(result.get("outcome") or "failed")
                cursor_state = dict(result.get("cursor") or job.cursor)
                error_class = result.get("error_class")
                error_message = result.get("error")
                if self.shutdown_requested.is_set() and outcome != "succeeded":
                    outcome = "interrupted"
        except Exception as exc:  # noqa: BLE001 - attempt must close durably
            outcome = "interrupted" if self.shutdown_requested.is_set() else "failed"
            error_class = type(exc).__name__
            error_message = str(exc)
        finally:
            heartbeat.stop()

        if outcome == "succeeded":
            delay = timedelta(hours=float(policy["sla_hours"]))
        elif outcome == "blocked":
            delay = timedelta(hours=float(policy["recheck_blocked_hours"]))
        elif outcome == "interrupted":
            delay = timedelta(minutes=5)
        else:
            delay = timedelta(
                hours=min(
                    float(policy["recheck_failed_hours"]),
                    2 ** max(0, job.attempt_count - 1),
                )
            )
        metrics = {
            **dict(result.get("metrics") or {}),
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
            "run_id": job.run_id,
        }
        with connect(self.dsn) as connection:
            owned = CrawlQueue(connection).finish(
                job,
                worker_id=self.worker_id,
                outcome=outcome,
                next_run_at=utcnow() + delay,
                cursor_state=cursor_state,
                metrics=metrics,
                error_class=error_class,
                error_message=error_message,
            )
        if not owned:
            raise RuntimeError(f"crawl job lease lost before finish: {job.id}")
        return {
            "status": outcome,
            "worker_id": self.worker_id,
            "job_id": job.id,
            "attempt_id": job.attempt_id,
            "run_id": job.run_id,
            "metrics": metrics,
        }


def _entity_target(connection: Any, job: ClaimedJob) -> tuple[str, str] | None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT cnpj_8, codigo_ibge, municipio FROM sc_public_entities WHERE id = %s AND is_active",
            (job.entity_id,),
        )
        entity = cursor.fetchone()
    if not entity:
        return None
    if job.source == "pncp" and entity.get("codigo_ibge"):
        return f"municipio:{entity['codigo_ibge']}", str(entity["cnpj_8"])
    if job.source in {"ciga_dom", "ciga_ckan", "sc_compras"} and entity.get("municipio"):
        return f"municipio_nome:{entity['municipio']}", str(entity["cnpj_8"])
    return None


def _canonical_contains_entity(source_result: dict[str, Any], *, entity_id: int, cnpj8: str) -> bool:
    canonical_path = source_result.get("canonical")
    if not canonical_path or not Path(str(canonical_path)).is_file():
        return False
    try:
        records = json.loads(Path(str(canonical_path)).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(records, list):
        return False
    for record in records:
        if not isinstance(record, dict):
            continue
        if str(record.get("matched_entity_id") or "") == str(entity_id):
            return True
        for field in ("orgao_cnpj", "cnpj", "entity_cnpj"):
            digits = "".join(character for character in str(record.get(field) or "") if character.isdigit())
            if digits.startswith(cnpj8):
                return True
    return False


def execute_job(job: ClaimedJob, connection: Any) -> dict[str, Any]:
    from scripts.ops.resilient_cycle import run_cycle

    source = "ciga_dom" if job.source == "ciga_ckan" else job.source
    if source not in {"pncp", "ciga_dom", "sc_compras"}:
        return {
            "outcome": "blocked",
            "error_class": "UNSUPPORTED_SOURCE_ADAPTER",
            "error": f"no resilient adapter for {job.source}",
        }
    target_info = _entity_target(connection, job)
    if target_info is None:
        return {
            "outcome": "blocked",
            "error_class": "ENTITY_TARGET_UNRESOLVED",
            "error": "active entity has no source-compatible target",
        }
    target, cnpj8 = target_info
    previous_attempt = os.environ.get("CRAWL_JOB_ATTEMPT_ID")
    previous_job = os.environ.get("CRAWL_JOB_ID")
    os.environ["CRAWL_JOB_ATTEMPT_ID"] = str(job.attempt_id)
    os.environ["CRAWL_JOB_ID"] = str(job.id)
    try:
        code, summary = run_cycle(
            live=True,
            source=source,
            target=target,
            date_from=job.window_start.date(),
            date_to=job.window_end.date(),
            run_id=job.run_id,
        )
    finally:
        if previous_attempt is None:
            os.environ.pop("CRAWL_JOB_ATTEMPT_ID", None)
        else:
            os.environ["CRAWL_JOB_ATTEMPT_ID"] = previous_attempt
        if previous_job is None:
            os.environ.pop("CRAWL_JOB_ID", None)
        else:
            os.environ["CRAWL_JOB_ID"] = previous_job
    source_result = dict((summary.get("results") or {}).get(source) or {})
    entity_confirmed = _canonical_contains_entity(
        source_result,
        entity_id=job.entity_id,
        cnpj8=cnpj8,
    )
    if source_result.get("terminal_status") == "blocked":
        outcome = "blocked"
    else:
        outcome = "succeeded" if code == 0 and entity_confirmed else "failed"
    entity_scope_error = None
    if code == 0 and not entity_confirmed:
        entity_scope_error = (
            "entity scope not confirmed; municipality/source-wide empty or nonmatching data "
            "cannot become entity success/zero"
        )
    return {
        "outcome": outcome,
        "cursor": source_result.get("checkpoint") or job.cursor,
        "error": "; ".join(source_result.get("errors") or []) or entity_scope_error,
        "error_class": "ENTITY_SCOPE_NOT_CONFIRMED"
        if entity_scope_error
        else source_result.get("status")
        if code
        else None,
        "metrics": {
            "pages_fetched": source_result.get("pages_fetched", 0),
            "records_fetched": source_result.get("records_fetched", 0),
            "db_records_committed": source_result.get("db_records_committed", 0),
            "cycle_exit_code": code,
            "entity_scope_confirmed": entity_confirmed,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Leased PostgreSQL crawl worker")
    parser.add_argument("--dsn", default=os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL"))
    parser.add_argument("--worker-id")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--idle-sleep", type=float, default=10)
    parser.add_argument("--lease-seconds", type=int, default=300)
    parser.add_argument("--heartbeat-seconds", type=int, default=30)
    args = parser.parse_args(argv)
    if not args.dsn:
        parser.error("--dsn or LOCAL_DATALAKE_DSN is required")
    worker = CrawlWorker(
        dsn=args.dsn,
        worker_id=args.worker_id,
        lease_seconds=args.lease_seconds,
        heartbeat_seconds=args.heartbeat_seconds,
    )
    signal.signal(signal.SIGTERM, worker.request_shutdown)
    signal.signal(signal.SIGINT, worker.request_shutdown)
    while not worker.shutdown_requested.is_set():
        result = worker.run_once()
        print(json.dumps(result, ensure_ascii=False, default=str), flush=True)
        if args.once:
            return 0 if result["status"] in {"succeeded", "idle", "backpressure"} else 1
        if result["status"] in {"idle", "backpressure"}:
            worker.shutdown_requested.wait(args.idle_sleep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
