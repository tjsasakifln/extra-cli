"""Tests for #347 durable provider-agnostic inference jobs.

Drives the shipped JobStore / submit / run_job / replay entry points.
No mocked SUT. Fake and Echo providers are real adapters behind the contract.
"""

from __future__ import annotations

from scripts.inference_runtime.jobs import (
    TERMINAL,
    EchoProvider,
    FakeProvider,
    JobSpec,
    JobStore,
    idempotency_key,
    job_ledger,
    replay,
    restart,
    run_job,
    submit,
)


def _spec(**overrides: object) -> JobSpec:
    payload = {
        "task": "extract_requirements",
        "input_payload": {"text": "Prazo de 30 dias."},
        "output_schema": {
            "type": "object",
            "required": ["summary"],
            "properties": {"summary": {"type": "string"}, "task": {"type": "string"}},
        },
        "prompt_version": "p1",
        "schema_version": "s1",
        "policy_version": "pol1",
    }
    payload.update(overrides)
    return JobSpec(**payload)  # type: ignore[arg-type]


def test_job_survives_restart_and_ends_terminal_with_attempts() -> None:
    store = JobStore()
    spec = _spec()
    job = submit(store, spec, job_id="job-1")
    assert job.state == "QUEUED"
    after = restart(store, "job-1")
    assert after.job_id == "job-1"
    assert after.idempotency_key == spec.key
    done = run_job(store, "job-1", FakeProvider())
    assert done.state == "SUCCEEDED"
    assert done.state in TERMINAL
    assert done.attempts
    assert done.promoted is True
    assert restart(store, "job-1").state == "SUCCEEDED"


def test_same_idempotency_key_does_not_duplicate_promoted_output() -> None:
    store = JobStore()
    spec = _spec()
    first = submit(store, spec, job_id="job-a")
    run_job(store, "job-a", FakeProvider())
    second = submit(store, spec, job_id="job-b")
    assert second.job_id == first.job_id == "job-a"
    assert len(store.jobs) == 1
    assert store.get("job-a").promoted is True
    # Re-running a terminal job is a no-op: no extra cost or new promotion.
    again = run_job(store, "job-a", FakeProvider())
    assert len(again.attempts) == 1
    assert again.tokens_used == store.get("job-a").tokens_used


def test_invalid_schema_missing_evidence_or_low_confidence_not_promoted() -> None:
    store = JobStore()
    spec = _spec()
    submit(store, spec, job_id="schema")
    bad_schema = run_job(
        store,
        "schema",
        FakeProvider(output={"output": {"nope": 1}, "evidence": [{"document_id": "d"}], "confidence": 0.99}),
    )
    assert bad_schema.state == "BLOCKED"
    assert bad_schema.promoted is False
    assert bad_schema.blocker and bad_schema.blocker.startswith("SCHEMA_INVALID")

    store2 = JobStore()
    submit(store2, spec, job_id="evidence")
    no_ev = run_job(
        store2,
        "evidence",
        FakeProvider(output={"output": {"summary": "x"}, "evidence": [], "confidence": 0.99}),
    )
    assert no_ev.state == "BLOCKED"
    assert no_ev.blocker == "MISSING_EVIDENCE"
    assert no_ev.promoted is False

    store3 = JobStore()
    submit(store3, spec, job_id="conf")
    low = run_job(
        store3,
        "conf",
        FakeProvider(
            output={
                "output": {"summary": "x"},
                "evidence": [{"document_id": "d"}],
                "confidence": 0.1,
            }
        ),
    )
    assert low.state == "BLOCKED"
    assert low.blocker == "CONFIDENCE_GATE"
    assert low.promoted is False


def test_provider_swap_keeps_domain_contract() -> None:
    spec = _spec(
        output_schema={
            "type": "object",
            "required": ["echo"],
            "properties": {"echo": {"type": "object"}, "task": {"type": "string"}},
        }
    )
    store = JobStore()
    submit(store, spec, job_id="echo")
    done = run_job(store, "echo", EchoProvider())
    assert done.state == "SUCCEEDED"
    assert done.attempts[0].provider == "echo"
    ledger = job_ledger(done)
    assert ledger["provider_attempts"][0]["model"] == "echo-v1"
    assert ledger["provider_attempts"][0]["prompt_version"] == "p1"
    assert "tokens_used" in ledger
    # Domain job fields do not mention a mandatory vendor.
    dumped = done.as_dict()
    assert dumped["provider_contract"] == "agnostic"


def test_timeout_and_unavailable_follow_limited_policy() -> None:
    store = JobStore()
    spec = _spec(max_attempts=2)
    submit(store, spec, job_id="to")
    first = run_job(store, "to", FakeProvider(fail="TIMEOUT"))
    assert first.state == "QUEUED"
    assert first.attempts[0].status == "TIMEOUT"
    second = run_job(store, "to", FakeProvider(fail="TIMEOUT"))
    assert second.state in TERMINAL
    assert second.blocker == "PROVIDER_TIMEOUT"

    store2 = JobStore()
    submit(store2, spec, job_id="down")
    down = run_job(store2, "down", FakeProvider(fail="UNAVAILABLE"))
    assert down.state == "BLOCKED"
    assert down.blocker == "PROVIDER_UNAVAILABLE"
    assert down.next_action


def test_replay_preserves_previous_result_and_adds_revision() -> None:
    store = JobStore()
    spec = _spec()
    submit(store, spec, job_id="rp")
    first = run_job(store, "rp", FakeProvider())
    assert first.revision == 1
    replayed = replay(store, "rp", FakeProvider())
    assert replayed.state == "SUCCEEDED"
    assert replayed.revision == 2
    assert replayed.output == first.output
    failed = replay(
        store,
        "rp",
        FakeProvider(output={"output": {"summary": "x"}, "evidence": [], "confidence": 0.99}),
    )
    assert failed.output == first.output
    assert failed.promoted is False


def test_idempotency_key_is_stable_and_changes_with_policy() -> None:
    spec = _spec()
    same = _spec()
    other = _spec(policy_version="pol2")
    assert spec.key == same.key
    assert spec.key != other.key
    assert spec.key == idempotency_key(
        input_hash=spec.input_hash,
        task=spec.task,
        prompt_version=spec.prompt_version,
        schema_version=spec.schema_version,
        policy_version=spec.policy_version,
    )
