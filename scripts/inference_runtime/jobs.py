"""#347 — asynchronous, auditable, provider-agnostic inference jobs.

Domain contract is independent of OpenAI/Anthropic/DeepSeek/Gemini/Bedrock.
A job survives restart and ends SUCCEEDED, BLOCKED or DLQ. Invalid schema,
missing evidence or low confidence never promote a fact into a dossier.

This is the durable job contract. It does not migrate to Bedrock, run a
provider bake-off, or authorize human GO.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal, Protocol

SCHEMA_VERSION = "inference-job/1.0"
TERMINAL: frozenset[str] = frozenset({"SUCCEEDED", "BLOCKED", "DLQ"})
JobState = Literal["QUEUED", "RUNNING", "SUCCEEDED", "BLOCKED", "DLQ"]

DEFAULT_CONFIDENCE_GATE = 0.70
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BUDGET_TOKENS = 8_000


class InferenceRuntimeError(ValueError):
    """Fail-closed inference contract error."""


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_payload(obj: Any) -> str:
    return hashlib.sha256(_canonical_json(obj).encode("utf-8")).hexdigest()


def idempotency_key(
    *,
    input_hash: str,
    task: str,
    prompt_version: str,
    schema_version: str,
    policy_version: str,
) -> str:
    if not all((input_hash, task, prompt_version, schema_version, policy_version)):
        raise InferenceRuntimeError("idempotency material is incomplete")
    return sha256_payload(
        {
            "input_hash": input_hash,
            "task": task,
            "prompt_version": prompt_version,
            "schema_version": schema_version,
            "policy_version": policy_version,
        }
    )


@dataclass(frozen=True)
class EvidenceLocator:
    document_id: str
    chunk_id: str | None = None
    locator: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class JobSpec:
    task: str
    input_payload: dict[str, Any]
    output_schema: dict[str, Any]
    prompt_version: str
    schema_version: str
    policy_version: str
    confidence_gate: float = DEFAULT_CONFIDENCE_GATE
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    budget_tokens: int = DEFAULT_BUDGET_TOKENS

    @property
    def input_hash(self) -> str:
        return sha256_payload(self.input_payload)

    @property
    def key(self) -> str:
        return idempotency_key(
            input_hash=self.input_hash,
            task=self.task,
            prompt_version=self.prompt_version,
            schema_version=self.schema_version,
            policy_version=self.policy_version,
        )


@dataclass(frozen=True)
class Attempt:
    attempt_no: int
    provider: str
    model: str
    prompt_version: str
    schema_version: str
    policy_version: str
    status: Literal["SUCCEEDED", "FAILED", "TIMEOUT", "RATE_LIMITED", "UNAVAILABLE"]
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    fallback_reason: str | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InferenceJob:
    job_id: str
    idempotency_key: str
    spec: JobSpec
    state: JobState
    attempts: tuple[Attempt, ...] = ()
    output: dict[str, Any] | None = None
    evidence: tuple[EvidenceLocator, ...] = ()
    confidence: float | None = None
    blocker: str | None = None
    next_action: str | None = None
    promoted: bool = False
    revision: int = 0
    tokens_used: int = 0
    cost_usd: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "job_id": self.job_id,
            "idempotency_key": self.idempotency_key,
            "state": self.state,
            "attempts": [a.as_dict() for a in self.attempts],
            "output": self.output,
            "evidence": [e.as_dict() for e in self.evidence],
            "confidence": self.confidence,
            "blocker": self.blocker,
            "next_action": self.next_action,
            "promoted": self.promoted,
            "revision": self.revision,
            "tokens_used": self.tokens_used,
            "cost_usd": self.cost_usd,
            "provider_contract": "agnostic",
        }


class Provider(Protocol):
    name: str
    model: str

    def infer(self, spec: JobSpec) -> dict[str, Any]:
        """Return output, evidence, confidence, usage. May raise ProviderError."""


class ProviderError(RuntimeError):
    def __init__(self, status: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class FakeProvider:
    """Deterministic in-process provider for contract tests."""

    name = "fake"
    model = "fake-extract-v1"

    def __init__(self, *, output: dict[str, Any] | None = None, fail: str | None = None) -> None:
        self._output = output
        self._fail = fail

    def infer(self, spec: JobSpec) -> dict[str, Any]:
        if self._fail:
            raise ProviderError(self._fail, f"fake provider {self._fail}")
        if self._output is not None:
            return dict(self._output)
        return {
            "output": {"summary": spec.input_payload.get("text", ""), "task": spec.task},
            "evidence": [{"document_id": "doc-1", "chunk_id": "c0", "locator": "p1"}],
            "confidence": 0.91,
            "tokens_in": 12,
            "tokens_out": 8,
            "cost_usd": 0.0,
            "latency_ms": 4,
        }


class EchoProvider:
    """Second opt-in adapter. Same domain contract, different provider name."""

    name = "echo"
    model = "echo-v1"

    def infer(self, spec: JobSpec) -> dict[str, Any]:
        return {
            "output": {"echo": spec.input_payload, "task": spec.task},
            "evidence": [{"document_id": "doc-echo", "locator": "body"}],
            "confidence": 0.80,
            "tokens_in": 6,
            "tokens_out": 6,
            "cost_usd": 0.0,
            "latency_ms": 1,
        }


def validate_against_schema(output: dict[str, Any], schema: dict[str, Any]) -> tuple[bool, str | None]:
    """Minimal required-object schema check. Missing required fields fail closed."""
    if schema.get("type", "object") != "object":
        return False, "schema_type_not_object"
    if not isinstance(output, dict):
        return False, "output_not_object"
    required = schema.get("required") or []
    for key in required:
        if key not in output:
            return False, f"missing_required:{key}"
    properties = schema.get("properties") or {}
    for key, value in output.items():
        declared = properties.get(key)
        if declared is None:
            continue
        expected = declared.get("type")
        if expected == "string" and not isinstance(value, str):
            return False, f"type:{key}:string"
        if expected == "number" and not isinstance(value, (int, float)):
            return False, f"type:{key}:number"
        if expected == "object" and not isinstance(value, dict):
            return False, f"type:{key}:object"
        if expected == "array" and not isinstance(value, list):
            return False, f"type:{key}:array"
    return True, None


@dataclass
class JobStore:
    """In-memory durable store used by tests and as the persist contract."""

    jobs: dict[str, InferenceJob] = field(default_factory=dict)
    by_idempotency: dict[str, str] = field(default_factory=dict)

    def put(self, job: InferenceJob) -> InferenceJob:
        existing_id = self.by_idempotency.get(job.idempotency_key)
        if existing_id is not None and existing_id != job.job_id:
            return self.jobs[existing_id]
        self.jobs[job.job_id] = job
        self.by_idempotency[job.idempotency_key] = job.job_id
        return job

    def get(self, job_id: str) -> InferenceJob:
        return self.jobs[job_id]


def submit(store: JobStore, spec: JobSpec, *, job_id: str) -> InferenceJob:
    queued = InferenceJob(
        job_id=job_id,
        idempotency_key=spec.key,
        spec=spec,
        state="QUEUED",
    )
    return store.put(queued)


def _park(job: InferenceJob, state: JobState, blocker: str, next_action: str) -> InferenceJob:
    return replace(
        job,
        state=state,
        blocker=blocker,
        next_action=next_action,
        promoted=False,
    )


def run_job(store: JobStore, job_id: str, provider: Provider) -> InferenceJob:
    job = store.get(job_id)
    if job.state in TERMINAL:
        return job
    if job.tokens_used >= job.spec.budget_tokens:
        parked = _park(job, "BLOCKED", "BUDGET_EXHAUSTED", "raise budget or shrink input")
        return store.put(parked)

    running = replace(job, state="RUNNING")
    store.put(running)
    attempt_no = len(running.attempts) + 1
    try:
        raw = provider.infer(running.spec)
        attempt = Attempt(
            attempt_no=attempt_no,
            provider=provider.name,
            model=provider.model,
            prompt_version=running.spec.prompt_version,
            schema_version=running.spec.schema_version,
            policy_version=running.spec.policy_version,
            status="SUCCEEDED",
            tokens_in=int(raw.get("tokens_in") or 0),
            tokens_out=int(raw.get("tokens_out") or 0),
            cost_usd=float(raw.get("cost_usd") or 0.0),
            latency_ms=int(raw.get("latency_ms") or 0),
        )
        output = raw.get("output")
        if not isinstance(output, dict):
            done = _park(
                replace(running, attempts=running.attempts + (attempt,)),
                "BLOCKED",
                "OUTPUT_NOT_OBJECT",
                "repair provider adapter; do not promote",
            )
            return store.put(done)
        ok, reason = validate_against_schema(output, running.spec.output_schema)
        locators = tuple(
            EvidenceLocator(
                document_id=str(item["document_id"]),
                chunk_id=item.get("chunk_id"),
                locator=item.get("locator"),
            )
            for item in (raw.get("evidence") or [])
            if isinstance(item, dict) and item.get("document_id")
        )
        confidence = raw.get("confidence")
        tokens = running.tokens_used + attempt.tokens_in + attempt.tokens_out
        cost = running.cost_usd + attempt.cost_usd
        updated = replace(
            running,
            attempts=running.attempts + (attempt,),
            tokens_used=tokens,
            cost_usd=cost,
        )
        if not ok:
            return store.put(
                _park(updated, "BLOCKED", f"SCHEMA_INVALID:{reason}", "reject output; do not write dossier fact")
            )
        if not locators:
            return store.put(
                _park(updated, "BLOCKED", "MISSING_EVIDENCE", "link document locators before promotion")
            )
        if confidence is None or float(confidence) < running.spec.confidence_gate:
            return store.put(
                _park(updated, "BLOCKED", "CONFIDENCE_GATE", "human review or richer evidence")
            )
        succeeded = replace(
            updated,
            state="SUCCEEDED",
            output=output,
            evidence=locators,
            confidence=float(confidence),
            blocker=None,
            next_action=None,
            promoted=True,
            revision=updated.revision + 1,
        )
        return store.put(succeeded)
    except ProviderError as exc:
        status = exc.status if exc.status in {"FAILED", "TIMEOUT", "RATE_LIMITED", "UNAVAILABLE"} else "FAILED"
        attempt = Attempt(
            attempt_no=attempt_no,
            provider=provider.name,
            model=provider.model,
            prompt_version=running.spec.prompt_version,
            schema_version=running.spec.schema_version,
            policy_version=running.spec.policy_version,
            status=status,  # type: ignore[arg-type]
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            latency_ms=0,
            error=exc.message,
            fallback_reason=status,
        )
        updated = replace(running, attempts=running.attempts + (attempt,))
        if attempt_no >= running.spec.max_attempts or status == "UNAVAILABLE":
            state: JobState = "DLQ" if status in {"UNAVAILABLE", "FAILED"} and attempt_no >= running.spec.max_attempts else "BLOCKED"
            if status == "UNAVAILABLE":
                state = "BLOCKED"
            parked = _park(
                updated,
                state,
                f"PROVIDER_{status}",
                "retry with fallback provider or park for operator",
            )
            return store.put(parked)
        queued = replace(updated, state="QUEUED", blocker=f"PROVIDER_{status}", next_action="retry")
        return store.put(queued)


def restart(store: JobStore, job_id: str) -> InferenceJob:
    """Process restart: persisted job is unchanged; terminal jobs stay terminal."""
    return store.get(job_id)


def replay(store: JobStore, job_id: str, provider: Provider) -> InferenceJob:
    """Replay preserves the previous result and creates a new auditable revision."""
    job = store.get(job_id)
    if job.state != "SUCCEEDED" or job.output is None:
        raise InferenceRuntimeError("replay requires a previously succeeded job")
    previous = job
    reset = replace(job, state="QUEUED", promoted=False)
    store.put(reset)
    rerun = run_job(store, job_id, provider)
    if rerun.state == "SUCCEEDED":
        return store.put(replace(rerun, revision=previous.revision + 1, output=rerun.output))
    # Failed replay keeps the last valid output servable.
    return store.put(
        replace(
            rerun,
            output=previous.output,
            evidence=previous.evidence,
            confidence=previous.confidence,
            revision=previous.revision,
            promoted=False,
        )
    )


def job_ledger(job: InferenceJob) -> dict[str, Any]:
    """Queryable per-job audit: tokens, cost, versions, latency, attempts."""
    return {
        "job_id": job.job_id,
        "state": job.state,
        "provider_attempts": [
            {
                "provider": a.provider,
                "model": a.model,
                "prompt_version": a.prompt_version,
                "schema_version": a.schema_version,
                "policy_version": a.policy_version,
                "tokens_in": a.tokens_in,
                "tokens_out": a.tokens_out,
                "cost_usd": a.cost_usd,
                "latency_ms": a.latency_ms,
                "status": a.status,
                "fallback_reason": a.fallback_reason,
            }
            for a in job.attempts
        ],
        "tokens_used": job.tokens_used,
        "cost_usd": job.cost_usd,
        "promoted": job.promoted,
    }
