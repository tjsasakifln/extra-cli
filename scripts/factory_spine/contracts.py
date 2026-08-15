"""Pure fail-closed contracts for the factory spine.

I/O stays in store/runtime. These functions are the shipped authority for
discovery terminals, coverage publication, job ranking, resilience and
window completeness.

Refs #235 #236 #246 #247 #256 #268 #269 #270 #272 #279
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from scripts.crawl.pncp_contract import (
    PNCP_CONSULTA_BASE,
    PNCP_TAMANHO_PAGINA_MAX_CONTRATACOES,
    PNCP_TAMANHO_PAGINA_MIN,
)
from scripts.crawl.resilience.diagnostics import classify_failure
from scripts.crawl.resilience.http_policy import HttpResiliencePolicy
from scripts.crawl.runtime_queue import canonical_idempotency_key
from scripts.source_registry.continuous_inventory import (
    COVERAGE_STATES,
    SURFACE_KINDS,
    SurfaceObservation,
    classify_surface,
)

CANONICAL_UNIVERSE_SIZE = 1093
DISCOVERY_TERMINALS = frozenset(
    {
        "FOUND",
        "UNCLASSIFIED",
        "BLOCKED",
        "DISCOVERY_EXHAUSTED_NO_SURFACE",
        "FAILED",
    }
)
COVERAGE_TERMINALS = frozenset(COVERAGE_STATES)
JOB_TERMINALS = frozenset({"succeeded", "failed", "blocked"})
JOB_ACTIVE = frozenset({"queued", "running"})
DEFAULT_SOURCES = ("pncp", "ciga_dom", "sc_compras", "transparencia")
DEFAULT_CAPABILITY = "open_tenders"


def canonical_entity_ids(count: int = CANONICAL_UNIVERSE_SIZE) -> tuple[str, ...]:
    if count < 1:
        raise ValueError("canonical universe count must be positive")
    return tuple(f"extra-canonical-{index:04d}" for index in range(1, count + 1))


def classify_discovery_surface(
    observation: SurfaceObservation,
    *,
    known_domains: set[str],
) -> tuple[str, str | None, str | None]:
    """Refs #235 — login/CAPTCHA/403 → BLOCKED; new domain → UNCLASSIFIED."""
    status, safe_url, domain = classify_surface(observation, known_domains=known_domains)
    if status not in DISCOVERY_TERMINALS:
        raise ValueError(f"discovery classifier returned non-terminal status: {status}")
    return status, safe_url, domain


@dataclass(frozen=True)
class SurfaceVersion:
    version_no: int
    status: str
    canonical_url: str | None
    domain: str | None
    platform: str | None
    invalidated: bool = False
    invalidation_reason: str | None = None


def apply_surface_revalidation(
    prior: SurfaceVersion | None,
    *,
    status: str,
    canonical_url: str | None,
    domain: str | None,
    platform: str | None,
) -> tuple[SurfaceVersion, tuple[SurfaceVersion, ...]]:
    """Refs #235 — invalidate the previous binding without deleting history."""
    if status not in DISCOVERY_TERMINALS:
        raise ValueError(f"invalid discovery terminal: {status}")
    if prior is None:
        current = SurfaceVersion(1, status, canonical_url, domain, platform)
        return current, (current,)
    changed = (
        prior.canonical_url != canonical_url
        or prior.domain != domain
        or prior.platform != platform
        or prior.status != status
    )
    archived = SurfaceVersion(
        version_no=prior.version_no,
        status=prior.status,
        canonical_url=prior.canonical_url,
        domain=prior.domain,
        platform=prior.platform,
        invalidated=True,
        invalidation_reason="binding_changed" if changed else "scheduled_revalidation",
    )
    current = SurfaceVersion(
        version_no=prior.version_no + 1,
        status=status,
        canonical_url=canonical_url,
        domain=domain,
        platform=platform,
    )
    return current, (archived, current)


def seal_discovery_run(
    universe_ids: tuple[str, ...] | list[str],
    results_by_id: dict[str, dict[str, Any]],
    *,
    expected_count: int = CANONICAL_UNIVERSE_SIZE,
    require_surfaces: bool = True,
) -> dict[str, Any]:
    """Refs #235 — every canonical ID must have a versioned discovery result."""
    expected = tuple(universe_ids)
    if len(expected) != expected_count or len(set(expected)) != expected_count:
        raise ValueError(
            f"discovery universe mismatch: expected_count={expected_count} "
            f"unique={len(set(expected))} rows={len(expected)}"
        )
    missing = [entity_id for entity_id in expected if entity_id not in results_by_id]
    extra = sorted(set(results_by_id) - set(expected))
    errors: list[str] = []
    if missing:
        errors.append(f"missing_discovery_results={len(missing)}")
    if extra:
        errors.append(f"unknown_discovery_ids={len(extra)}")
    for entity_id in expected:
        result = results_by_id.get(entity_id)
        if not result:
            continue
        status = str(result.get("status") or "")
        if status not in DISCOVERY_TERMINALS:
            errors.append(f"{entity_id}:invalid_status={status}")
        history = result.get("history") or ()
        if not history:
            errors.append(f"{entity_id}:missing_version_history")
        if require_surfaces:
            kinds = {str(item.get("kind")) for item in result.get("surfaces") or ()}
            if kinds != set(SURFACE_KINDS):
                errors.append(f"{entity_id}:incomplete_surfaces")
        if "checked_at" not in result or "next_check_at" not in result:
            errors.append(f"{entity_id}:missing_revalidation_schedule")
    if errors:
        raise ValueError("discovery seal failed: " + "; ".join(errors[:12]))
    return {
        "entity_count": expected_count,
        "outcome": "complete",
        "terminals": sorted(DISCOVERY_TERMINALS),
    }


def assert_publishable_coverage(
    status: str,
    *,
    executed: bool,
    request_completed: bool = False,
    scope_complete: bool = False,
    pagination_reconciled: bool = False,
    records_observed: int = 0,
    raw_uri: str | None = None,
    raw_sha256: str | None = None,
) -> None:
    """Refs #236 — absence of execution is never published as zero."""
    if status not in COVERAGE_TERMINALS:
        raise ValueError(f"invalid coverage terminal: {status}")
    if not executed:
        if status in {"FOUND", "ZERO_CONFIRMED"}:
            raise ValueError("absence of execution cannot be published as FOUND or ZERO_CONFIRMED")
        return
    if status == "ZERO_CONFIRMED" and not (
        request_completed
        and scope_complete
        and pagination_reconciled
        and records_observed == 0
        and raw_uri
        and raw_sha256
    ):
        raise ValueError("ZERO_CONFIRMED requires complete reconciled request and preserved empty raw")


def publish_coverage_cell(
    *,
    canonical_entity_key: str,
    source: str,
    capability: str = DEFAULT_CAPABILITY,
    status: str,
    executed: bool,
    applicability: bool,
    applicability_reason: str,
    request_completed: bool = False,
    scope_complete: bool = False,
    pagination_reconciled: bool = False,
    records_observed: int = 0,
    pages_fetched: int = 0,
    pages_expected: int | None = None,
    raw_uri: str | None = None,
    raw_sha256: str | None = None,
    canonical_url: str | None = None,
    http_statuses: tuple[int, ...] = (),
    checked_at: datetime | None = None,
    next_action: str = "inspect",
    next_check_at: datetime | None = None,
    history: tuple[dict[str, Any], ...] = (),
) -> dict[str, Any]:
    """Refs #236 — publish one ente×fonte cell into a terminal state only."""
    assert_publishable_coverage(
        status,
        executed=executed,
        request_completed=request_completed,
        scope_complete=scope_complete,
        pagination_reconciled=pagination_reconciled,
        records_observed=records_observed,
        raw_uri=raw_uri,
        raw_sha256=raw_sha256,
    )
    if not applicability and status not in {"NOT_APPLICABLE", "BLOCKED"}:
        raise ValueError("non-applicable pair must be NOT_APPLICABLE or BLOCKED")
    if not applicability_reason.strip():
        raise ValueError("coverage cell requires an explicit applicability reason")
    clock = (checked_at or datetime.now(UTC)).astimezone(UTC)
    return {
        "canonical_entity_key": canonical_entity_key,
        "source": source,
        "capability": capability,
        "status": status,
        "executed": executed,
        "applicability": applicability,
        "applicability_reason": applicability_reason,
        "canonical_url": canonical_url,
        "checked_at": clock.isoformat(),
        "http_statuses": list(http_statuses),
        "pages_fetched": pages_fetched,
        "pages_expected": pages_expected,
        "records_observed": records_observed,
        "request_completed": request_completed,
        "scope_complete": scope_complete,
        "pagination_reconciled": pagination_reconciled,
        "raw_uri": raw_uri,
        "raw_sha256": raw_sha256,
        "next_action": next_action,
        "next_check_at": (next_check_at or clock + timedelta(hours=24)).isoformat(),
        "history": list(history),
    }


def reconcile_coverage_artifacts(
    universe_ids: tuple[str, ...] | list[str],
    cells: list[dict[str, Any]],
    *,
    expected_count: int = CANONICAL_UNIVERSE_SIZE,
    sources: tuple[str, ...] = DEFAULT_SOURCES,
) -> dict[str, Any]:
    """Refs #236 — Excel, manifesto and KPI share the same 1.093 IDs."""
    expected = tuple(universe_ids)
    if len(expected) != expected_count or len(set(expected)) != expected_count:
        raise ValueError("coverage universe does not match the active 1.093 IDs")
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for cell in cells:
        key = (
            str(cell["canonical_entity_key"]),
            str(cell["source"]),
            str(cell.get("capability") or DEFAULT_CAPABILITY),
        )
        if key in by_key:
            raise ValueError(f"duplicate coverage cell: {key}")
        assert_publishable_coverage(
            str(cell["status"]),
            executed=bool(cell.get("executed")),
            request_completed=bool(cell.get("request_completed")),
            scope_complete=bool(cell.get("scope_complete")),
            pagination_reconciled=bool(cell.get("pagination_reconciled")),
            records_observed=int(cell.get("records_observed") or 0),
            raw_uri=cell.get("raw_uri"),
            raw_sha256=cell.get("raw_sha256"),
        )
        by_key[key] = cell
    missing_entities = [entity_id for entity_id in expected if not any(key[0] == entity_id for key in by_key)]
    if missing_entities:
        raise ValueError(f"coverage artifacts missing {len(missing_entities)} canonical IDs")
    for entity_id in expected:
        open_route = [cell for key, cell in by_key.items() if key[0] == entity_id and key[2] == DEFAULT_CAPABILITY]
        if not open_route:
            raise ValueError(f"{entity_id} has no open_tenders route or explicit blocker")
    excel_rows = [
        {
            "canonical_entity_key": cell["canonical_entity_key"],
            "source": cell["source"],
            "capability": cell.get("capability") or DEFAULT_CAPABILITY,
            "status": cell["status"],
            "next_action": cell.get("next_action"),
        }
        for cell in cells
    ]
    manifest_ids = tuple(sorted({cell["canonical_entity_key"] for cell in cells}))
    if manifest_ids != tuple(sorted(expected)):
        raise ValueError("manifest IDs do not reconcile with the active universe")
    kpi = {
        "entity_count": expected_count,
        "cell_count": len(cells),
        "by_status": {
            status: sum(1 for cell in cells if cell["status"] == status) for status in sorted(COVERAGE_TERMINALS)
        },
        "sources": list(sources),
    }
    return {"excel_rows": excel_rows, "manifest_ids": manifest_ids, "kpi": kpi}


@dataclass(frozen=True)
class EnqueueDecision:
    canonical_entity_key: str
    entity_id: int
    source: str
    capability: str
    applicability: str
    reason: str
    binding_version: str
    action: str
    next_run_at: datetime
    freshness_deadline: datetime
    billable: bool


def plan_freshness_enqueue(
    pairs: list[dict[str, Any]],
    *,
    now: datetime,
    expected_entities: int = CANONICAL_UNIVERSE_SIZE,
    sla_hours: float = 24.0,
    recheck_blocked_hours: float = 72.0,
    recheck_failed_hours: float = 12.0,
    recheck_not_applicable_hours: float = 168.0,
) -> list[EnqueueDecision]:
    """Refs #268 — every applicable pair is queued or has a dated recheck reason."""
    clock = now.astimezone(UTC)
    entities = {str(pair["canonical_entity_key"]) for pair in pairs}
    if len(entities) != expected_entities:
        raise ValueError(f"freshness enqueue universe mismatch: expected {expected_entities}, observed {len(entities)}")
    decisions: list[EnqueueDecision] = []
    for pair in pairs:
        applicability = str(pair.get("applicability") or "APPLICABLE")
        reason = str(pair.get("reason") or "").strip()
        if not reason:
            raise ValueError("freshness pair requires an explicit reason")
        if applicability == "APPLICABLE":
            delay = timedelta(hours=0)
            action = "enqueue"
            billable = True
        elif applicability == "NOT_APPLICABLE":
            delay = timedelta(hours=recheck_not_applicable_hours)
            action = "defer_not_applicable"
            billable = False
        elif applicability == "BLOCKED":
            delay = timedelta(hours=recheck_blocked_hours)
            action = "recheck_blocked"
            billable = False
        elif applicability == "FAILED":
            delay = timedelta(hours=recheck_failed_hours)
            action = "recheck_failed"
            billable = False
        else:
            raise ValueError(f"invalid applicability: {applicability}")
        decisions.append(
            EnqueueDecision(
                canonical_entity_key=str(pair["canonical_entity_key"]),
                entity_id=int(pair.get("entity_id") or 0),
                source=str(pair["source"]),
                capability=str(pair.get("capability") or DEFAULT_CAPABILITY),
                applicability=applicability,
                reason=reason,
                binding_version=str(pair.get("binding_version") or "binding-v1"),
                action=action,
                next_run_at=clock + delay,
                freshness_deadline=clock + timedelta(hours=sla_hours),
                billable=billable,
            )
        )
    open_routes = {decision.canonical_entity_key for decision in decisions if decision.capability == DEFAULT_CAPABILITY}
    missing = sorted(entities - open_routes)
    if missing:
        raise ValueError(f"entities without open-tender route or blocker: {missing[:10]}")
    return decisions


def job_idempotency_key(
    *,
    canonical_entity_key: str,
    source: str,
    capability: str,
    window_start: datetime,
    window_end: datetime,
    binding_version: str,
) -> str:
    """Refs #246 — unique key includes job type inputs and versioning."""
    return canonical_idempotency_key(
        canonical_entity_key=canonical_entity_key,
        source=source,
        capability=capability,
        window_start=window_start,
        window_end=window_end,
        binding_version=binding_version,
    )


@dataclass(frozen=True)
class RankedJob:
    id: int
    domain_key: str
    priority: int
    freshness_deadline: datetime
    next_run_at: datetime
    status: str
    domain_concurrency_limit: int


def rank_claim_candidates(
    jobs: list[RankedJob],
    *,
    now: datetime,
    active_by_domain: dict[str, int] | None = None,
    limit: int = 1,
) -> list[RankedJob]:
    """Refs #269 — domain slots + freshness order; no starvation of late domains."""
    clock = now.astimezone(UTC)
    active = dict(active_by_domain or {})
    queued = [job for job in jobs if job.status == "queued" and job.next_run_at <= clock]
    queued.sort(
        key=lambda job: (
            -job.priority,
            job.freshness_deadline,
            job.next_run_at,
            job.id,
        )
    )
    claimed: list[RankedJob] = []
    domain_taken: dict[str, int] = {}
    for job in queued:
        used = active.get(job.domain_key, 0) + domain_taken.get(job.domain_key, 0)
        if used >= job.domain_concurrency_limit:
            continue
        claimed.append(job)
        domain_taken[job.domain_key] = domain_taken.get(job.domain_key, 0) + 1
        if len(claimed) >= limit:
            break
    return claimed


def window_is_complete(
    *,
    outcome: str,
    pages_fetched: int,
    pages_expected: int | None,
    request_completed: bool,
    scope_complete: bool,
    pagination_reconciled: bool,
) -> bool:
    """Refs #270 — a partial fetch never closes the window as complete."""
    if outcome != "succeeded":
        return False
    if not (request_completed and scope_complete and pagination_reconciled):
        return False
    if pages_expected is not None and pages_fetched < pages_expected:
        return False
    return True


@dataclass(frozen=True)
class ResilienceDecision:
    action: str
    transient: bool
    error_class: str | None
    next_action: str
    sleep_seconds: float
    window_complete: bool
    terminal: str | None
    metrics: dict[str, Any] = field(default_factory=dict)


def decide_resilience(
    *,
    http_status: int | None,
    error: Any,
    attempt: int,
    max_attempts: int,
    retry_after: float | None = None,
    circuit_state: str = "closed",
    pages_fetched: int = 0,
    pages_expected: int | None = None,
    policy: HttpResiliencePolicy | None = None,
) -> ResilienceDecision:
    """Refs #270 — Retry-After, permanent 403/CAPTCHA, partial window stays open."""
    resolved = policy or HttpResiliencePolicy()
    complete = window_is_complete(
        outcome="succeeded" if http_status == 200 and error is None else "failed",
        pages_fetched=pages_fetched,
        pages_expected=pages_expected,
        request_completed=http_status == 200 and error is None,
        scope_complete=pages_expected is None or pages_fetched >= pages_expected,
        pagination_reconciled=pages_expected is None or pages_fetched >= pages_expected,
    )
    if circuit_state == "open":
        return ResilienceDecision(
            action="wait_circuit",
            transient=True,
            error_class="CIRCUIT_OPEN",
            next_action="retry_after_circuit_cooldown",
            sleep_seconds=float(resolved.circuit_breaker_cooldown),
            window_complete=False,
            terminal=None,
            metrics={"attempt": attempt, "circuit_state": circuit_state},
        )
    if http_status == 200 and error is None:
        return ResilienceDecision(
            action="succeed",
            transient=False,
            error_class=None,
            next_action="persist_and_continue",
            sleep_seconds=0.0,
            window_complete=complete,
            terminal="FOUND" if complete else None,
            metrics={"attempt": attempt, "pages_fetched": pages_fetched},
        )
    classified = classify_failure(http_status=http_status, error=error)
    if not classified.transient:
        return ResilienceDecision(
            action="block" if classified.error_class == "AUTH_BLOCKED" else "fail",
            transient=False,
            error_class=classified.error_class,
            next_action=classified.next_action,
            sleep_seconds=0.0,
            window_complete=False,
            terminal="BLOCKED" if classified.error_class == "AUTH_BLOCKED" else "FAILED",
            metrics={"attempt": attempt, "http_status": http_status},
        )
    if attempt >= max_attempts:
        return ResilienceDecision(
            action="fail",
            transient=True,
            error_class=classified.error_class,
            next_action="inspect_exhausted_retries",
            sleep_seconds=0.0,
            window_complete=False,
            terminal="FAILED",
            metrics={"attempt": attempt, "max_attempts": max_attempts},
        )
    sleep = resolved.retry_delay(max(0, attempt - 1), retry_after)
    return ResilienceDecision(
        action="retry",
        transient=True,
        error_class=classified.error_class,
        next_action=classified.next_action,
        sleep_seconds=sleep,
        window_complete=False,
        terminal=None,
        metrics={"attempt": attempt, "retry_after": retry_after, "http_status": http_status},
    )


def build_pncp_consulta_envelope(
    *,
    pagina: int,
    tamanho_pagina: int,
    data_inicial: str,
    data_final: str,
    endpoint: str = "contratacoes/publicacao",
) -> dict[str, str]:
    """Refs #270 — never emit an invalid PNCP tamanhoPagina on the consulta path."""
    if pagina < 1:
        raise ValueError("pagina must be >= 1")
    if tamanho_pagina < PNCP_TAMANHO_PAGINA_MIN or tamanho_pagina > PNCP_TAMANHO_PAGINA_MAX_CONTRATACOES:
        raise ValueError(
            "invalid PNCP tamanhoPagina for contratacoes: "
            f"{tamanho_pagina} not in [{PNCP_TAMANHO_PAGINA_MIN}, {PNCP_TAMANHO_PAGINA_MAX_CONTRATACOES}]"
        )
    params = {
        "dataInicial": data_inicial,
        "dataFinal": data_final,
        "pagina": str(pagina),
        "tamanhoPagina": str(tamanho_pagina),
    }
    return {
        "url": f"{PNCP_CONSULTA_BASE}/{endpoint}?{urlencode(params)}",
        "pagina": str(pagina),
        "tamanhoPagina": str(tamanho_pagina),
    }
