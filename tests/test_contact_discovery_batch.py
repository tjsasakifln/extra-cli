"""Adversarial tests for the shipped contact-discovery batch path."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.real_db

from scripts.crawl.worker import AdmissionLimits, admission_blockers
from scripts.decision_unit_intelligence.batch_outcomes import (
    classify_account,
    classify_exception,
    persist_outcome,
)
from scripts.decision_unit_intelligence.batch_queue import (
    ContactDiscoveryQueue,
    connect,
    idempotency_key,
)
from scripts.decision_unit_intelligence.batch_snapshot import publish_snapshot
from scripts.decision_unit_intelligence.batch_worker import (
    ContactDiscoveryWorker,
    execute_claimed,
)
from scripts.decision_unit_intelligence.cli import main
from scripts.decision_unit_intelligence.models import AccountTerminal, SearchLedger

MIGRATION = Path(__file__).resolve().parents[1] / "db" / "migrations" / "093_contact_discovery_batch.sql"
DSN = (
    os.getenv("LOCAL_DATALAKE_DSN")
    or os.getenv("TEST_DSN")
    or "postgresql://test:test@127.0.0.1:5433/extra_test"
)


def _skip_without_pg() -> None:
    try:
        import psycopg2

        conn = psycopg2.connect(DSN, connect_timeout=3)
        conn.close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"test postgres unavailable: {exc}")


@pytest.fixture
def dsn() -> str:
    _skip_without_pg()
    import psycopg2

    sql = MIGRATION.read_text(encoding="utf-8")
    connection = psycopg2.connect(DSN)
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            cursor.execute(
                """
                TRUNCATE contact_discovery_snapshots,
                         contact_discovery_attempts,
                         contact_discovery_jobs,
                         contact_discovery_cohorts,
                         contact_discovery_backend_circuit
                RESTART IDENTITY CASCADE
                """
            )
            cursor.execute(
                """
                UPDATE contact_discovery_kill_switch
                SET enabled = FALSE, reason = '', changed_by = 'test'
                """
            )
    finally:
        connection.close()
    return DSN


def _account(cnpj: str, terminal: AccountTerminal = AccountTerminal.ACTIONABLE_ROUTE) -> SimpleNamespace:
    ledger = SearchLedger(duration_ms=12, bytes_touched=100, search_queries=["q1"])
    return SimpleNamespace(
        cnpj=cnpj,
        terminal=terminal,
        ledger=ledger,
        routes=[],
        candidates=[],
        extra={"domain_resolution": {"canonical_domain": "exemplo.com.br"}},
        to_dict=lambda: {
            "cnpj": cnpj,
            "terminal": terminal.value,
            "candidates": [],
            "routes": [],
            "recommendation": None,
            "policy_version": "dui.policy.v1",
        },
    )


def _seed(queue: ContactDiscoveryQueue, *, cohort: str, accounts: list[str], policy: str = "dui.policy.v1", backend: str = "off", budget: str = "budget.test", service: str = "reajuste_14133") -> list[int]:
    queue.upsert_cohort(
        cohort_id=cohort,
        service=service,
        offer_context="canary",
        discovery_policy_version=policy,
        search_backend=backend,
        budget_version=budget,
        code_sha="sha-test",
        input_evidence_version="input.v1",
    )
    ids = []
    for account in accounts:
        job_id, _created = queue.enqueue(
            cohort_id=cohort,
            canonical_account_id=account,
            service=service,
            offer_context="canary",
            discovery_policy_version=policy,
            search_backend=backend,
            budget_version=budget,
            code_sha="sha-test",
            input_evidence_version="input.v1",
        )
        ids.append(job_id)
    return ids


def test_duplicate_enqueue_does_not_create_second_truth(dsn: str) -> None:
    with connect(dsn) as connection:
        queue = ContactDiscoveryQueue(connection)
        first = _seed(queue, cohort="c-dup", accounts=["11222333000181"])
        second_id, created = queue.enqueue(
            cohort_id="c-dup",
            canonical_account_id="11.222.333/0001-81",
            service="reajuste_14133",
            offer_context="canary",
            discovery_policy_version="dui.policy.v1",
            search_backend="off",
            budget_version="budget.test",
            code_sha="sha-test",
            input_evidence_version="input.v1",
        )
        assert created is False
        assert second_id == first[0]
        jobs = queue.inspect(cohort_id="c-dup")
        assert len(jobs) == 1
        assert jobs[0]["idempotency_key"] == idempotency_key(
            canonical_account_id="11222333000181",
            service="reajuste_14133",
            discovery_policy_version="dui.policy.v1",
            input_evidence_version="input.v1",
            search_backend="off",
            budget_version="budget.test",
        )


def test_policy_change_creates_new_revision_identity(dsn: str) -> None:
    with connect(dsn) as connection:
        queue = ContactDiscoveryQueue(connection)
        _seed(queue, cohort="c-policy-a", accounts=["11222333000181"], policy="dui.policy.v1")
        queue.upsert_cohort(
            cohort_id="c-policy-b",
            service="reajuste_14133",
            offer_context="canary",
            discovery_policy_version="dui.policy.v2",
            search_backend="off",
            budget_version="budget.test",
            code_sha="sha-test",
            input_evidence_version="input.v1",
        )
        new_id, created = queue.enqueue(
            cohort_id="c-policy-b",
            canonical_account_id="11222333000181",
            service="reajuste_14133",
            offer_context="canary",
            discovery_policy_version="dui.policy.v2",
            search_backend="off",
            budget_version="budget.test",
            code_sha="sha-test",
            input_evidence_version="input.v1",
        )
        assert created is True
        assert new_id != 0
        assert len(queue.inspect(cohort_id="c-policy-a")) == 1
        assert len(queue.inspect(cohort_id="c-policy-b")) == 1


def test_two_workers_claim_same_job_exactly_once(dsn: str, tmp_path: Path) -> None:
    with connect(dsn) as connection:
        _seed(ContactDiscoveryQueue(connection), cohort="c-race", accounts=["11222333000181"])
    results: list[dict] = []

    def _run(worker_id: str) -> None:
        worker = ContactDiscoveryWorker(
            dsn=dsn,
            worker_id=worker_id,
            output_root=tmp_path,
            admission_probe=lambda: [],
            discovery=lambda job: _account(job.canonical_account_id),
        )
        results.append(worker.run_once())

    threads = [
        threading.Thread(target=_run, args=("w-a",)),
        threading.Thread(target=_run, args=("w-b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    owners = [row for row in results if row.get("status") == "SUCCEEDED"]
    idles = [row for row in results if row.get("status") == "idle"]
    assert len(owners) == 1
    assert len(idles) == 1
    with connect(dsn) as connection:
        jobs = ContactDiscoveryQueue(connection).inspect(cohort_id="c-race")
        assert len(jobs) == 1
        assert jobs[0]["status"] == "SUCCEEDED"
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS n FROM contact_discovery_attempts WHERE job_id = %s AND status = 'SUCCEEDED'",
                (jobs[0]["id"],),
            )
            assert int(cursor.fetchone()["n"]) == 1


def test_crash_before_commit_resumes_same_job(dsn: str, tmp_path: Path) -> None:
    with connect(dsn) as connection:
        queue = ContactDiscoveryQueue(connection)
        _seed(queue, cohort="c-crash-before", accounts=["11222333000181"])
        claimed = queue.claim(worker_id="doomed", lease_seconds=1)
        assert len(claimed) == 1
        outcome = execute_claimed(
            claimed[0],
            discovery=lambda job: _account(job.canonical_account_id),
            output_root=tmp_path,
        )
        assert outcome.output_pointer and Path(outcome.output_pointer).is_file()
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE contact_discovery_jobs SET lease_expires_at = now() - interval '10 seconds' WHERE id = %s",
                (claimed[0].id,),
            )
        reclaimed = queue.reclaim_expired()
        assert reclaimed == 1
        jobs = queue.inspect(job_id=claimed[0].id)
        assert jobs[0]["status"] == "RETRYABLE"
        assert jobs[0]["last_reason_code"] == "LEASE_EXPIRED"
    worker = ContactDiscoveryWorker(
        dsn=dsn,
        worker_id="survivor",
        output_root=tmp_path,
        admission_probe=lambda: [],
        discovery=lambda job: _account(job.canonical_account_id),
    )
    result = worker.run_once()
    assert result["status"] == "SUCCEEDED"
    with connect(dsn) as connection:
        jobs = ContactDiscoveryQueue(connection).inspect(cohort_id="c-crash-before")
        assert jobs[0]["status"] == "SUCCEEDED"
        assert jobs[0]["output_hash"]


def test_output_written_commit_fails_then_promotes_once(dsn: str, tmp_path: Path) -> None:
    with connect(dsn) as connection:
        queue = ContactDiscoveryQueue(connection)
        _seed(queue, cohort="c-commit-fail", accounts=["11222333000181"])
        claimed = queue.claim(worker_id="owner", lease_seconds=60)
        outcome = persist_outcome(
            classify_account(_account(claimed[0].canonical_account_id)),
            job=claimed[0],
            output_root=tmp_path,
        )
        stolen = queue.finish(
            claimed[0],
            worker_id="not-the-owner",
            outcome="SUCCEEDED",
            reason_code="ACTIONABLE_ROUTE",
            output_pointer=outcome.output_pointer,
            output_hash=outcome.output_hash,
        )
        assert stolen is False
        jobs = queue.inspect(job_id=claimed[0].id)
        assert jobs[0]["status"] == "RUNNING"
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE contact_discovery_jobs SET lease_expires_at = now() - interval '1 second' WHERE id = %s",
                (claimed[0].id,),
            )
        queue.reclaim_expired()
        claimed2 = queue.claim(worker_id="owner-2", lease_seconds=60)
        assert len(claimed2) == 1
        promoted = queue.finish(
            claimed2[0],
            worker_id="owner-2",
            outcome="SUCCEEDED",
            reason_code="ACTIONABLE_ROUTE",
            output_pointer=outcome.output_pointer,
            output_hash=outcome.output_hash,
        )
        assert promoted is True
        jobs = queue.inspect(job_id=claimed2[0].id)
        assert jobs[0]["status"] == "SUCCEEDED"


def test_terminal_commit_ack_lost_is_idempotent(dsn: str, tmp_path: Path) -> None:
    with connect(dsn) as connection:
        queue = ContactDiscoveryQueue(connection)
        _seed(queue, cohort="c-ack", accounts=["11222333000181"])
        claimed = queue.claim(worker_id="owner", lease_seconds=60)
        outcome = persist_outcome(
            classify_account(_account(claimed[0].canonical_account_id)),
            job=claimed[0],
            output_root=tmp_path,
        )
        first = queue.finish(
            claimed[0],
            worker_id="owner",
            outcome="SUCCEEDED",
            reason_code="ACTIONABLE_ROUTE",
            output_pointer=outcome.output_pointer,
            output_hash=outcome.output_hash,
        )
        second = queue.finish(
            claimed[0],
            worker_id="owner",
            outcome="SUCCEEDED",
            reason_code="ACTIONABLE_ROUTE",
            output_pointer=outcome.output_pointer,
            output_hash=outcome.output_hash,
        )
        assert first is True
        assert second is True
        jobs = queue.inspect(cohort_id="c-ack")
        assert jobs[0]["status"] == "SUCCEEDED"
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM contact_discovery_jobs WHERE cohort_id = 'c-ack'")
            assert int(cursor.fetchone()["n"]) == 1


def test_reboot_recovery_via_resume(dsn: str, tmp_path: Path) -> None:
    with connect(dsn) as connection:
        queue = ContactDiscoveryQueue(connection)
        _seed(queue, cohort="c-reboot", accounts=["11222333000181", "44555666000177"])
        claimed = queue.claim(worker_id="dead-host", lease_seconds=1)
        assert claimed
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE contact_discovery_jobs SET lease_expires_at = now() - interval '30 seconds' WHERE status = 'RUNNING'"
            )
        report = queue.resume(cohort_id="c-reboot")
        assert report["reclaimed"] >= 1
        assert report["pending"] >= 1
    worker = ContactDiscoveryWorker(
        dsn=dsn,
        worker_id="rebooted",
        output_root=tmp_path,
        admission_probe=lambda: [],
        discovery=lambda job: _account(job.canonical_account_id),
    )
    first = worker.run_once()
    second = worker.run_once()
    assert {first["status"], second["status"]} == {"SUCCEEDED"}
    with connect(dsn) as connection:
        progress = ContactDiscoveryQueue(connection).progress(cohort_id="c-reboot")
        assert progress["denominator"] == 2
        assert progress["counts"]["succeeded"] == 2
        assert progress["closable"] is True


def test_429_and_timeout_never_become_no_contact(dsn: str, tmp_path: Path) -> None:
    class Http429Error(Exception):
        def __init__(self) -> None:
            self.response = SimpleNamespace(status_code=429)
            super().__init__("429 Too Many Requests")

    class ProviderTimeoutError(TimeoutError):
        pass

    with connect(dsn) as connection:
        queue = ContactDiscoveryQueue(connection)
        _seed(queue, cohort="c-429", accounts=["11222333000181"])
        _seed(queue, cohort="c-timeout", accounts=["44555666000177"])

    def boom_429(_job):
        raise Http429Error()

    def boom_timeout(_job):
        raise ProviderTimeoutError("provider timeout")

    r429 = ContactDiscoveryWorker(
        dsn=dsn,
        worker_id="w-429",
        output_root=tmp_path,
        admission_probe=lambda: [],
        discovery=boom_429,
    ).run_once()
    rto = ContactDiscoveryWorker(
        dsn=dsn,
        worker_id="w-to",
        output_root=tmp_path,
        admission_probe=lambda: [],
        discovery=boom_timeout,
    ).run_once()
    assert r429["status"] == "RETRYABLE"
    assert r429["reason_code"] == "PROVIDER_429"
    assert rto["status"] == "RETRYABLE"
    assert rto["reason_code"] == "PROVIDER_TIMEOUT"
    assert r429["reason_code"] not in {"SEM_CONTATO", "NO_CONTACT", "NO_CONTACT_FOUND"}
    assert rto["reason_code"] not in {"SEM_CONTATO", "NO_CONTACT", "NO_CONTACT_FOUND"}
    with connect(dsn) as connection:
        queue = ContactDiscoveryQueue(connection)
        assert queue.inspect(cohort_id="c-429")[0]["status"] == "RETRYABLE"
        assert queue.inspect(cohort_id="c-timeout")[0]["status"] == "RETRYABLE"
        assert queue.inspect(cohort_id="c-429")[0]["last_reason_code"] == "PROVIDER_429"


def test_kill_switch_blocks_admission_without_false_success(dsn: str, tmp_path: Path) -> None:
    with connect(dsn) as connection:
        queue = ContactDiscoveryQueue(connection)
        _seed(queue, cohort="c-kill", accounts=["11222333000181"])
        queue.set_kill_switch(enabled=True, reason="operator pause", actor="test")
    result = ContactDiscoveryWorker(
        dsn=dsn,
        worker_id="w-kill",
        output_root=tmp_path,
        admission_probe=lambda: [],
        discovery=lambda job: _account(job.canonical_account_id),
    ).run_once()
    assert result["status"] == "blocked"
    assert result["reason_code"] == "KILL_SWITCH"
    with connect(dsn) as connection:
        jobs = ContactDiscoveryQueue(connection).inspect(cohort_id="c-kill")
        assert jobs[0]["status"] == "PENDING"


def test_cpu_disk_pressure_pauses_admission(dsn: str, tmp_path: Path) -> None:
    with connect(dsn) as connection:
        _seed(ContactDiscoveryQueue(connection), cohort="c-pressure", accounts=["11222333000181"])
    blockers = admission_blockers(
        AdmissionLimits(max_load_per_cpu=0.9, min_free_disk_ratio=0.1),
        load_average=8.0,
        cpu_count=4,
        memory_ratio=0.5,
        disk_ratio=0.05,
    )
    assert "cpu_pressure" in blockers
    assert "disk_pressure" in blockers
    result = ContactDiscoveryWorker(
        dsn=dsn,
        worker_id="w-pressure",
        output_root=tmp_path,
        admission_probe=lambda: blockers,
        discovery=lambda job: _account(job.canonical_account_id),
    ).run_once()
    assert result["status"] == "backpressure"
    assert result["reason_code"] == "ADMISSION_PRESSURE"
    with connect(dsn) as connection:
        jobs = ContactDiscoveryQueue(connection).inspect(cohort_id="c-pressure")
        assert jobs[0]["status"] == "PENDING"


def test_partial_blocked_batch_refuses_approved_snapshot(dsn: str, tmp_path: Path) -> None:
    with connect(dsn) as connection:
        queue = ContactDiscoveryQueue(connection)
        _seed(queue, cohort="c-partial", accounts=["11222333000181", "44555666000177", "99888777000166"])

    def adapter(job):
        if job.canonical_account_id.endswith("166"):
            return _account(job.canonical_account_id, AccountTerminal.BLOCKED)
        return _account(job.canonical_account_id)

    worker = ContactDiscoveryWorker(
        dsn=dsn,
        worker_id="w-partial",
        output_root=tmp_path,
        admission_probe=lambda: [],
        discovery=adapter,
    )
    worker.run_once()
    worker.run_once()
    with connect(dsn) as connection:
        queue = ContactDiscoveryQueue(connection)
        progress = queue.progress(cohort_id="c-partial")
        assert progress["counts"]["pending"] == 1
        assert progress["closable"] is False
        refused = publish_snapshot(queue, cohort_id="c-partial", output_root=tmp_path)
        assert refused["approved"] is False
        assert any("non-terminal" in reason for reason in refused["reject_reasons"])
    worker.run_once()
    with connect(dsn) as connection:
        queue = ContactDiscoveryQueue(connection)
        closed = queue.progress(cohort_id="c-partial")
        assert closed["counts"]["blocked"] == 1
        assert closed["counts"]["succeeded"] == 2
        assert closed["closable"] is True
        published = publish_snapshot(queue, cohort_id="c-partial", output_root=tmp_path)
        assert published["approved"] is True


def test_classify_never_emits_sem_contato() -> None:
    account = _account("11222333000181", AccountTerminal.EXHAUSTED)
    outcome = classify_account(account)
    assert outcome.job_status == "SUCCEEDED"
    assert outcome.reason_code == "BUDGET_EXHAUSTED"
    assert outcome.reason_code not in {"SEM_CONTATO", "NO_CONTACT"}
    classified = classify_exception(TimeoutError("slow"))
    assert classified.job_status == "RETRYABLE"
    assert classified.reason_code == "PROVIDER_TIMEOUT"


def test_cli_enqueue_worker_progress_publish_is_idempotent(dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_DATALAKE_DSN", dsn)
    monkeypatch.setenv("DATABASE_URL", dsn)
    out = tmp_path / "cli-out"
    common = [
        "--cohort",
        "c-cli",
        "--cnpjs",
        "11222333000181,44555666000177",
        "--search-backend",
        "off",
        "--dsn",
        dsn,
    ]
    assert main(["batch", "enqueue", *common, "--out", str(out)]) == 0
    monkeypatch.setenv("CONTACT_DISCOVERY_ADMISSION", "off")
    assert main(["batch", "worker", "--dsn", dsn, "--worker-id", "cli-w1", "--out", str(out)]) == 0
    assert main(["batch", "worker", "--dsn", dsn, "--worker-id", "cli-w2", "--out", str(out)]) == 0
    assert main(["batch", "inspect", "--cohort", "c-cli", "--dsn", dsn]) == 0
    assert main(["batch", "progress", "--cohort", "c-cli", "--dsn", dsn]) == 0
    rc = main(["batch", "publish", "--cohort", "c-cli", "--out", str(out), "--dsn", dsn])
    assert rc == 0
    first = main(["batch", "enqueue", *common, "--out", str(out)])
    assert first == 0
    with connect(dsn) as connection:
        progress = ContactDiscoveryQueue(connection).progress(cohort_id="c-cli")
        assert progress["denominator"] == 2
        assert progress["counts"]["succeeded"] == 2
        jobs = ContactDiscoveryQueue(connection).inspect(cohort_id="c-cli")
        assert len(jobs) == 2
        assert {job["status"] for job in jobs} == {"SUCCEEDED"}
