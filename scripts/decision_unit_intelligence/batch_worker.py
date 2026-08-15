"""Leased contact-discovery worker. Calls run_account as a black box."""

from __future__ import annotations

import logging
import os
import signal
import socket
import threading
import time
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

from scripts.crawl.worker import AdmissionLimits, admission_blockers
from scripts.decision_unit_intelligence import POLICY_VERSION
from scripts.decision_unit_intelligence.batch_outcomes import (
    BlockedDiscoveryError,
    Outcome,
    RetryableDiscoveryError,
    classify_account,
    classify_exception,
    persist_outcome,
)
from scripts.decision_unit_intelligence.batch_queue import (
    ClaimedDiscoveryJob,
    ContactDiscoveryQueue,
    connect,
    utcnow,
)
from scripts.decision_unit_intelligence.runner import run_account
from scripts.decision_unit_intelligence.web_discovery import SearchBudget

logger = logging.getLogger(__name__)

AdmissionProbe = Callable[[], list[str]]
DiscoveryFn = Callable[[ClaimedDiscoveryJob], Any]


class Heartbeat:
    def __init__(
        self,
        *,
        dsn: str,
        job: ClaimedDiscoveryJob,
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
        self.thread = threading.Thread(
            target=self._run, name=f"cd-heartbeat-{job.id}", daemon=True
        )

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=max(1, self.interval_seconds + 1))

    def _run(self) -> None:
        while not self.stop_event.wait(self.interval_seconds):
            try:
                with connect(self.dsn) as connection:
                    owned = ContactDiscoveryQueue(connection).heartbeat(
                        self.job,
                        worker_id=self.worker_id,
                        lease_seconds=self.lease_seconds,
                        metrics={"heartbeat_count": 1},
                    )
                    if not owned:
                        return
            except Exception as exc:  # noqa: BLE001 - lease expiry remains authority
                logger.warning("contact discovery heartbeat failed job=%s: %s", self.job.id, exc)
                continue


def default_discovery(job: ClaimedDiscoveryJob) -> Any:
    knobs = (job.cursor or {}).get("budget") or {}
    budget = SearchBudget(
        max_queries=int(knobs.get("max_queries") or 4),
        max_results_per_query=int(knobs.get("max_results_per_query") or 5),
        max_pages=int(knobs.get("max_pages") or 4),
        max_bytes=int(knobs.get("max_bytes") or 1_500_000),
        timeout_seconds=float(knobs.get("timeout_seconds") or 12.0),
        min_query_interval_seconds=float(knobs.get("min_query_interval_seconds") or 1.0),
        cache_ttl_days=int(knobs.get("cache_ttl_days") or 7),
    )
    cache_dir = Path(knobs.get("cache_dir") or ".cache/confenge-prospect")
    return run_account(
        job.canonical_account_id,
        service=job.service,
        infer_email=bool(knobs.get("infer_email", True)),
        search_backend=job.search_backend,
        searxng_url=knobs.get("searxng_url") or os.getenv("CONFENGE_SEARXNG_URL"),
        search_budget=budget,
        cache_dir=cache_dir,
        verify_email_dns=bool(knobs.get("verify_email_dns", False)),
    )


def execute_claimed(
    job: ClaimedDiscoveryJob,
    *,
    discovery: DiscoveryFn,
    output_root: Path,
) -> Outcome:
    if job.cancel_requested:
        return Outcome(job_status="CANCELLED", reason_code="CANCELLED")
    try:
        account = discovery(job)
    except RetryableDiscoveryError as exc:
        return Outcome(job_status="RETRYABLE", reason_code=exc.reason_code, error_message=exc.message)
    except BlockedDiscoveryError as exc:
        return Outcome(job_status="BLOCKED", reason_code=exc.reason_code, error_message=exc.message)
    except Exception as exc:  # noqa: BLE001 - classify, never invent "no contact"
        return classify_exception(exc)
    outcome = classify_account(account)
    return persist_outcome(outcome, job=job, output_root=output_root)


class ContactDiscoveryWorker:
    def __init__(
        self,
        *,
        dsn: str,
        worker_id: str | None = None,
        lease_seconds: int = 300,
        heartbeat_seconds: int = 30,
        limits: AdmissionLimits | None = None,
        discovery: DiscoveryFn | None = None,
        admission_probe: AdmissionProbe | None = None,
        output_root: Path | None = None,
        claim_limit: int = 1,
        backend_filter: str | None = None,
    ):
        self.dsn = dsn
        self.worker_id = worker_id or f"cd-{socket.gethostname()}-{os.getpid()}"
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.limits = limits or AdmissionLimits()
        self.discovery = discovery or default_discovery
        if admission_probe is not None:
            self.admission_probe = admission_probe
        elif os.getenv("CONTACT_DISCOVERY_ADMISSION", "on").lower() in {"off", "0", "false"}:
            self.admission_probe = lambda: []
        else:
            self.admission_probe = lambda: admission_blockers(self.limits)
        self.output_root = Path(output_root or "output/contact-discovery")
        self.claim_limit = claim_limit
        self.backend_filter = backend_filter
        self.shutdown_requested = threading.Event()

    def request_shutdown(self, *_args: Any) -> None:
        self.shutdown_requested.set()

    def install_signal_handlers(self) -> None:
        signal.signal(signal.SIGTERM, self.request_shutdown)
        signal.signal(signal.SIGINT, self.request_shutdown)

    def run_once(self) -> dict[str, Any]:
        blockers = self.admission_probe()
        if blockers:
            return {
                "status": "backpressure",
                "worker_id": self.worker_id,
                "blockers": blockers,
                "reason_code": "ADMISSION_PRESSURE",
            }
        with connect(self.dsn) as connection:
            queue = ContactDiscoveryQueue(connection)
            switch = queue.kill_switch()
            if switch.get("enabled"):
                return {
                    "status": "blocked",
                    "worker_id": self.worker_id,
                    "reason_code": "KILL_SWITCH",
                    "reason": switch.get("reason"),
                }
            claimed = queue.claim(
                worker_id=self.worker_id,
                limit=self.claim_limit,
                lease_seconds=self.lease_seconds,
                backend_filter=self.backend_filter,
            )
        if not claimed:
            return {"status": "idle", "worker_id": self.worker_id}
        return self._run_job(claimed[0])

    def _run_job(self, job: ClaimedDiscoveryJob) -> dict[str, Any]:
        heartbeat = Heartbeat(
            dsn=self.dsn,
            job=job,
            worker_id=self.worker_id,
            interval_seconds=self.heartbeat_seconds,
            lease_seconds=self.lease_seconds,
        )
        started = time.monotonic()
        heartbeat.start()
        outcome = Outcome(job_status="RETRYABLE", reason_code="INTERRUPTED")
        try:
            if self.shutdown_requested.is_set():
                outcome = Outcome(job_status="RETRYABLE", reason_code="INTERRUPTED")
            else:
                outcome = execute_claimed(job, discovery=self.discovery, output_root=self.output_root)
                if self.shutdown_requested.is_set() and outcome.job_status not in {
                    "SUCCEEDED",
                    "BLOCKED",
                    "CANCELLED",
                }:
                    outcome.job_status = "RETRYABLE"
                    outcome.reason_code = "INTERRUPTED"
        except Exception as exc:  # noqa: BLE001 - attempt must close
            classified = classify_exception(exc)
            outcome = classified
            if self.shutdown_requested.is_set():
                outcome.job_status = "RETRYABLE"
                outcome.reason_code = "INTERRUPTED"
        finally:
            heartbeat.stop()

        duration_ms = round((time.monotonic() - started) * 1000, 3)
        metrics = {
            **dict(outcome.metrics or {}),
            "duration_ms": duration_ms,
            "run_id": job.run_id,
            "retries": max(0, job.attempt_count - 1),
            "policy_version": job.discovery_policy_version or POLICY_VERSION,
        }
        delay = utcnow()
        if outcome.job_status == "RETRYABLE":
            delay = utcnow() + timedelta(minutes=min(60, 2 ** max(0, job.attempt_count - 1)))
        elif outcome.job_status == "BLOCKED":
            delay = utcnow() + timedelta(hours=6)
        with connect(self.dsn) as connection:
            owned = ContactDiscoveryQueue(connection).finish(
                job,
                worker_id=self.worker_id,
                outcome=outcome.job_status,
                reason_code=outcome.reason_code,
                next_run_at=delay,
                cursor_state=job.cursor,
                metrics=metrics,
                error_message=outcome.error_message,
                output_pointer=outcome.output_pointer,
                output_hash=outcome.output_hash,
                domain_key=outcome.domain_key,
            )
        if not owned:
            raise RuntimeError(f"contact discovery lease lost before finish: {job.id}")
        return {
            "status": outcome.job_status,
            "reason_code": outcome.reason_code,
            "worker_id": self.worker_id,
            "job_id": job.id,
            "attempt_id": job.attempt_id,
            "run_id": job.run_id,
            "output_pointer": outcome.output_pointer,
            "output_hash": outcome.output_hash,
            "metrics": metrics,
        }

    def run_loop(self, *, idle_sleep: float = 2.0, max_jobs: int | None = None) -> dict[str, Any]:
        self.install_signal_handlers()
        processed = 0
        last: dict[str, Any] = {"status": "idle", "worker_id": self.worker_id}
        while not self.shutdown_requested.is_set():
            last = self.run_once()
            if last.get("status") not in {"idle", "backpressure", "blocked"}:
                processed += 1
                if max_jobs is not None and processed >= max_jobs:
                    break
                continue
            if max_jobs == 0:
                break
            time.sleep(idle_sleep)
            if max_jobs is not None and processed >= max_jobs:
                break
        return {"processed": processed, "last": last, "worker_id": self.worker_id}
