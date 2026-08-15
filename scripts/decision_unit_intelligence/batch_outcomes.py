"""Map shipped run_account results onto durable job states.

Discovery remains a black box. This module only classifies outcomes so
429/timeout/budget/source-block never become “sem contato encontrado”.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.decision_unit_intelligence.batch_queue import ClaimedDiscoveryJob
from scripts.decision_unit_intelligence.models import AccountTerminal, ChannelType
from scripts.decision_unit_intelligence.repository import account_hash, write_json

FORBIDDEN_REASON_CODES = frozenset(
    {
        "SEM_CONTATO",
        "NO_CONTACT",
        "NO_CONTACT_FOUND",
        "sem contato encontrado",
        "SEM_CONTATO_ENCONTRADO",
    }
)

RETRYABLE_TOKENS = (
    "HTTPStatusError",
    "HTTPError",
    "RateLimit",
    "Ratelimit",
    "TooManyRequests",
    "TimeoutException",
    "ReadTimeout",
    "ConnectTimeout",
    "TimeoutError",
    "ConnectError",
    "RemoteProtocolError",
)


@dataclass
class Outcome:
    job_status: str
    reason_code: str
    discovery_terminal: str | None = None
    error_message: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    domain_key: str | None = None
    account_payload: dict[str, Any] | None = None
    output_pointer: str | None = None
    output_hash: str | None = None


class RetryableDiscoveryError(Exception):
    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code
        self.message = message


class BlockedDiscoveryError(Exception):
    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code
        self.message = message


def classify_exception(exc: BaseException) -> Outcome:
    name = type(exc).__name__
    text = f"{name}:{exc}"
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status == 429 or "429" in text or "RateLimit" in name or "Ratelimit" in name:
        return Outcome(job_status="RETRYABLE", reason_code="PROVIDER_429", error_message=text[:500])
    if status is not None and int(status) >= 500:
        return Outcome(job_status="RETRYABLE", reason_code="PROVIDER_5XX", error_message=text[:500])
    if "timeout" in name.lower() or "timeout" in text.lower():
        return Outcome(job_status="RETRYABLE", reason_code="PROVIDER_TIMEOUT", error_message=text[:500])
    if "5" in str(status or "") and "HTTP" in name:
        return Outcome(job_status="RETRYABLE", reason_code="PROVIDER_5XX", error_message=text[:500])
    return Outcome(job_status="RETRYABLE", reason_code="PROVIDER_ERROR", error_message=text[:500])


def _failure_blob(account: Any) -> str:
    parts: list[str] = []
    ledger = getattr(account, "ledger", None)
    if ledger is not None:
        parts.extend(str(item) for item in (ledger.blocked_sources or []))
        for attempt in ledger.attempts or []:
            extra = getattr(attempt, "extra", {}) or {}
            parts.extend(str(item) for item in (extra.get("failures") or []))
            parts.extend(str(item) for item in (extra.get("crawl_failures") or []))
            if getattr(attempt, "reason", None):
                parts.append(str(attempt.reason))
            if getattr(attempt, "stop_reason", None):
                parts.append(str(attempt.stop_reason))
    return " ".join(parts)


def _provider_failure_count(account: Any) -> int:
    ledger = getattr(account, "ledger", None)
    if ledger is None:
        return 0
    count = 0
    for attempt in ledger.attempts or []:
        extra = getattr(attempt, "extra", {}) or {}
        count += len(extra.get("failures") or [])
        count += len(extra.get("crawl_failures") or [])
    return count


def classify_account(account: Any) -> Outcome:
    blob = _failure_blob(account)
    terminal = getattr(account.terminal, "value", str(account.terminal))
    metrics = extract_metrics(account)
    domain = _domain_from_account(account)
    payload = account.to_dict() if hasattr(account, "to_dict") else dict(account)

    if any(token in blob for token in ("429", "RateLimit", "Ratelimit", "TooManyRequests")):
        return Outcome(
            job_status="RETRYABLE",
            reason_code="PROVIDER_429",
            discovery_terminal=terminal,
            error_message=blob[:500] or None,
            metrics=metrics,
            domain_key=domain,
            account_payload=payload,
        )
    if any(token in blob for token in ("TimeoutException", "ReadTimeout", "ConnectTimeout", "TimeoutError")):
        return Outcome(
            job_status="RETRYABLE",
            reason_code="PROVIDER_TIMEOUT",
            discovery_terminal=terminal,
            error_message=blob[:500] or None,
            metrics=metrics,
            domain_key=domain,
            account_payload=payload,
        )
    if "HTTPStatusError" in blob or re.search(r"\b5\d\d\b", blob):
        return Outcome(
            job_status="RETRYABLE",
            reason_code="PROVIDER_5XX" if re.search(r"\b5\d\d\b", blob) else "PROVIDER_HTTP_ERROR",
            discovery_terminal=terminal,
            error_message=blob[:500] or None,
            metrics=metrics,
            domain_key=domain,
            account_payload=payload,
        )

    if terminal == AccountTerminal.BLOCKED.value:
        return Outcome(
            job_status="BLOCKED",
            reason_code="SOURCE_BLOCKED",
            discovery_terminal=terminal,
            error_message=blob[:500] or None,
            metrics=metrics,
            domain_key=domain,
            account_payload=payload,
        )

    reason = "DISCOVERY_COMPLETED"
    if terminal == AccountTerminal.ACTIONABLE_ROUTE.value:
        reason = "ACTIONABLE_ROUTE"
    elif terminal == AccountTerminal.EXHAUSTED.value:
        reason = "BUDGET_EXHAUSTED"
    elif terminal == AccountTerminal.DECISION_UNIT_IDENTIFIED_REACHABILITY_UNRESOLVED.value:
        reason = "PERSON_WITHOUT_ROUTE"
    elif terminal == AccountTerminal.NEEDS_ENRICHMENT.value:
        reason = "NEEDS_ENRICHMENT"
    return Outcome(
        job_status="SUCCEEDED",
        reason_code=reason,
        discovery_terminal=terminal,
        metrics=metrics,
        domain_key=domain,
        account_payload=payload,
    )


def extract_metrics(account: Any) -> dict[str, Any]:
    ledger = getattr(account, "ledger", None)
    routes = list(getattr(account, "routes", None) or [])
    people = list(getattr(account, "candidates", None) or [])
    extra = getattr(account, "extra", None) or {}
    attempts = list(getattr(ledger, "attempts", None) or []) if ledger else []
    cache_hits = 0
    cache_misses = 0
    pages = int(getattr(ledger, "documents_checked", 0) or 0) if ledger else 0
    searches = len(getattr(ledger, "search_queries", None) or []) if ledger else 0
    for attempt in attempts:
        extra_a = getattr(attempt, "extra", {}) or {}
        cache_hits += int(extra_a.get("cache_hits") or 0)
        cache_misses += int(extra_a.get("cache_misses") or 0)
    domain_resolution = extra.get("domain_resolution") or {}
    observed = 0
    inferred = 0
    for route in routes:
        channel_type = getattr(route, "channel_type", None)
        value = getattr(channel_type, "value", channel_type)
        if value == ChannelType.DIRECT_EMAIL.value:
            observed += 1
        elif value == ChannelType.INFERRED_DIRECT_EMAIL.value:
            inferred += 1
    reports = extra.get("email_verification") or []
    email_validated = sum(
        1
        for report in reports
        if isinstance(report, dict)
        and (
            report.get("final_classification") == "EMAIL_VALIDATED"
            or report.get("mx") == "MX_PRESENT"
            and report.get("final_classification") == "EMAIL_VALIDATED"
        )
    )
    return {
        "searches": searches,
        "pages": pages,
        "bytes_touched": int(getattr(ledger, "bytes_touched", 0) or 0) if ledger else 0,
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "external_cost_brl": float(getattr(ledger, "cost_brl", 0) or 0) if ledger else 0.0,
        "domains_resolved": 1 if domain_resolution.get("canonical_domain") else 0,
        "named_people": len(people),
        "observed_direct_email": observed,
        "inferred_email": inferred,
        "email_validated": email_validated,
        "provider_failures": _provider_failure_count(account),
        "retries": 0,
        "discovery_terminal": getattr(account.terminal, "value", str(account.terminal)),
        "duration_ms": int(getattr(ledger, "duration_ms", 0) or 0) if ledger else 0,
    }


def _domain_from_account(account: Any) -> str | None:
    extra = getattr(account, "extra", None) or {}
    domain = (extra.get("domain_resolution") or {}).get("canonical_domain")
    if domain:
        return f"domain:{domain}"
    return None


def persist_outcome(outcome: Outcome, *, job: ClaimedDiscoveryJob, output_root: Path) -> Outcome:
    if outcome.reason_code in FORBIDDEN_REASON_CODES:
        raise ValueError(f"forbidden reason code: {outcome.reason_code}")
    payload = {
        "schema_id": "confenge.contact_discovery.job_output.v1",
        "job_type": "CONFENGE_CONTACT_DISCOVERY",
        "job_id": job.id,
        "cohort_id": job.cohort_id,
        "canonical_account_id": job.canonical_account_id,
        "revision": job.revision,
        "attempt_id": job.attempt_id,
        "run_id": job.run_id,
        "job_status": outcome.job_status,
        "reason_code": outcome.reason_code,
        "discovery_terminal": outcome.discovery_terminal,
        "policy_version": job.discovery_policy_version,
        "search_backend": job.search_backend,
        "budget_version": job.budget_version,
        "code_sha": job.code_sha,
        "input_evidence_version": job.input_evidence_version,
        "metrics": outcome.metrics,
        "account": outcome.account_payload,
    }
    directory = Path(output_root) / job.cohort_id
    path = directory / f"{job.canonical_account_id}.json"
    write_json(path, payload)
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    if outcome.account_payload:
        payload["account_hash"] = account_hash(outcome.account_payload)
        write_json(path, payload)
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
    outcome.output_pointer = str(path)
    outcome.output_hash = digest
    return outcome
