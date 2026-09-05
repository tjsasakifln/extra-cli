"""Contract truth and durability primitives (#309, #312, #314, #319, #306, #304).

Pure classification plus small I/O seams. Raw official payloads are never
mutated; facts receive status/quality labels. Production writers take a
PostgreSQL advisory fence; checkpoints refuse the git/release worktree.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

ACTIVITY_RULE_VERSION = "contract-activity-v1"
QUALITY_RULE_VERSION = "contract-quality-v1"
IDENTITY_RULE_VERSION = "canonical-contract-v1"
PAGINATION_RULE_VERSION = "pagination-reconcile-v2"

# Explicit monotonic-growth policy. Totals are classified; 44515/44517 is not special.
GROWTH_BUDGET_ABS = 8
GROWTH_BUDGET_RATIO = 0.01
MAX_CONVERGENCE_PASSES = 2
MAX_CONVERGENCE_SECONDS = 90.0
MAX_PAGE_GROWTH = 1

DRIFT_OK = "ok"
DRIFT_CONVERGED = "converged"
DRIFT_NEEDS_RETRY = "needs_retry"
DRIFT_SOURCE = "source_population_drift"
DRIFT_RECONCILE = "reconcile_failed"

REASON_STABLE = "population_stable"
REASON_MONOTONIC_GROWTH = "monotonic_growth_within_budget"
REASON_GROWTH_UNPROVEN = "monotonic_growth_unproven"
REASON_SHRINK = "population_shrink"
REASON_OSCILLATION = "population_oscillation"
REASON_JUMP = "growth_above_budget"
REASON_PAGE_JUMP = "page_count_jump"
REASON_PAGE_SHRINK = "page_count_shrink"
REASON_REORDER_OMIT = "pagination_reorder_omission"
REASON_DUPLICATE_CONFLICT = "duplicate_conflicting_page"
REASON_IMPOSSIBLE = "impossible_population"
REASON_TIMEOUT_BEFORE = "timeout_before_checkpoint"
REASON_TIMEOUT_AFTER = "timeout_after_checkpoint"
REASON_PERSIST_FAIL = "persistence_failed"
REASON_CRASH_BEFORE_COMMIT = "crash_after_insert_before_state_commit"
REASON_IDS_UNSEEN = "new_ids_not_seen"
REASON_CONVERGENCE_CAP = "convergence_pass_limit"
REASON_REPLAY_IDEMPOTENT = "replay_idempotent"
REASON_INCONSISTENT_COUNT = "inconsistent_count"
REASON_TIME_BUDGET = "convergence_time_budget"

ACTIVE_PROVEN = "ACTIVE_PROVEN"
COMPLETED = "COMPLETED"
CANCELLED = "CANCELLED"
TERMINATED = "TERMINATED"
SUSPENDED = "SUSPENDED"
UNKNOWN = "UNKNOWN"
REVIEW = "REVIEW"

VALID = "VALID"
QUARANTINED = "QUARANTINED"

ACTIVITY_STATES = frozenset({ACTIVE_PROVEN, COMPLETED, CANCELLED, TERMINATED, SUSPENDED, UNKNOWN})
QUALITY_STATES = frozenset({VALID, REVIEW, QUARANTINED})

PG_FENCE_KEY = 0x45585452  # 'EXTR'
PRODUCTION_STATE_ROOT = Path("/var/lib/extra-consultoria")
FORBIDDEN_CHECKPOINT_PREFIXES = (
    "/opt/extra-consultoria",
    "/opt/extra-cli",
)

_ACTIVE_TOKENS = frozenset(
    {
        "vigente",
        "ativo",
        "ativa",
        "em execucao",
        "em execução",
        "assinado",
        "publicado",
        "active",
    }
)
_COMPLETED_TOKENS = frozenset({"encerrado", "concluido", "concluído", "finalizado", "completed", "findado"})
_CANCELLED_TOKENS = frozenset({"cancelado", "anulado", "cancelled", "canceled"})
_TERMINATED_TOKENS = frozenset({"rescindido", "resilido", "resilído", "terminated", "distratado"})
_SUSPENDED_TOKENS = frozenset({"suspenso", "suspended", "paralisado"})

_TRILLION_BRL = 1_000_000_000_000.0
_PLAUSIBLE_YEAR_MIN = 1994
_PLAUSIBLE_YEAR_MAX = 2100


class CheckpointLocationError(ValueError):
    """Production checkpoint path is inside the release/worktree."""


class WriterFenceBusyError(RuntimeError):
    """A second national writer tried to mutate under an active fence."""


class WriterFenceBypassError(RuntimeError):
    """Production attempted to skip the national writer fence."""


@dataclass(frozen=True)
class ContractActivity:
    state: str
    raw_status: str | None
    rule_version: str
    source: str
    observed_at: str | None
    reasons: tuple[str, ...]

    @property
    def is_active_proven(self) -> bool:
        return self.state == ACTIVE_PROVEN


@dataclass(frozen=True)
class ContractQuality:
    state: str
    rule_version: str
    reasons: tuple[str, ...]
    financial_impact: float | None = None


@dataclass(frozen=True)
class CanonicalContract:
    canonical_contract_id: str
    source: str
    source_contract_id: str
    parent_procurement_id: str | None
    method: str
    rule_version: str
    ambiguous: bool = False


@dataclass(frozen=True)
class PopulationDriftPolicy:
    growth_budget_abs: int = GROWTH_BUDGET_ABS
    growth_budget_ratio: float = GROWTH_BUDGET_RATIO
    max_passes: int = MAX_CONVERGENCE_PASSES
    max_seconds: float = MAX_CONVERGENCE_SECONDS
    max_page_growth: int = MAX_PAGE_GROWTH

    def to_dict(self) -> dict[str, Any]:
        return {
            "growth_budget_abs": self.growth_budget_abs,
            "growth_budget_ratio": self.growth_budget_ratio,
            "max_passes": self.max_passes,
            "max_seconds": self.max_seconds,
            "max_page_growth": self.max_page_growth,
        }


DEFAULT_DRIFT_POLICY = PopulationDriftPolicy()


@dataclass(frozen=True)
class PopulationDriftDecision:
    """Pure classification of source population change. Never a success stamp."""

    status: str
    decision: str
    reason_codes: tuple[str, ...]
    first_total_registros: int | None
    last_total_registros: int | None
    first_total_paginas: int | None
    last_total_paginas: int | None
    unique_ids: int
    expected_growth: int
    new_ids_seen: int
    pass_count: int
    allows_tail_pass: bool
    policy: PopulationDriftPolicy = DEFAULT_DRIFT_POLICY

    @property
    def ok(self) -> bool:
        return self.status in {DRIFT_OK, DRIFT_CONVERGED}

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "decision": self.decision,
            "reason_codes": list(self.reason_codes),
            "first_total_registros": self.first_total_registros,
            "last_total_registros": self.last_total_registros,
            "first_total_paginas": self.first_total_paginas,
            "last_total_paginas": self.last_total_paginas,
            "unique_ids": self.unique_ids,
            "expected_growth": self.expected_growth,
            "new_ids_seen": self.new_ids_seen,
            "pass_count": self.pass_count,
            "allows_tail_pass": self.allows_tail_pass,
            "ok": self.ok,
            "policy": self.policy.to_dict(),
        }


def growth_within_budget(
    first_total: int,
    last_total: int,
    policy: PopulationDriftPolicy = DEFAULT_DRIFT_POLICY,
) -> bool:
    """True when last-first is a small monotonic increase inside the published policy."""
    if last_total <= first_total:
        return False
    delta = last_total - first_total
    if delta > policy.growth_budget_abs:
        return False
    if first_total <= 0:
        return False
    return (delta / first_total) <= policy.growth_budget_ratio


def _oscillated(sequence: Sequence[int]) -> bool:
    if len(sequence) < 3:
        return False
    saw_up = False
    saw_down = False
    previous = sequence[0]
    for value in sequence[1:]:
        if value > previous:
            saw_up = True
        elif value < previous:
            saw_down = True
        previous = value
        if saw_up and saw_down:
            return True
    return False


def _conflicting_duplicate_pages(
    page_id_sequences: Sequence[tuple[int, tuple[str, ...]]],
) -> bool:
    seen: dict[int, tuple[str, ...]] = {}
    for page_no, ids in page_id_sequences:
        previous = seen.get(page_no)
        if previous is None:
            seen[page_no] = ids
            continue
        previous_set = set(previous)
        current_set = set(ids)
        if previous_set == current_set:
            continue
        if previous_set < current_set:
            seen[page_no] = ids
            continue
        return True
    return False


def _reorder_omitted(
    page_id_sequences: Sequence[tuple[int, tuple[str, ...]]],
    all_ids: set[str],
) -> bool:
    """Reordered pages that drop a previously seen id from the universe fail."""
    del all_ids
    first_by_page: dict[int, set[str]] = {}
    latest_by_page: dict[int, set[str]] = {}
    for page_no, ids in page_id_sequences:
        current = set(ids)
        first_by_page.setdefault(page_no, current)
        latest_by_page[page_no] = current
    universe: set[str] = set()
    for ids in latest_by_page.values():
        universe.update(ids)
    for page_no, first_set in first_by_page.items():
        latest = latest_by_page[page_no]
        if first_set == latest:
            continue
        lost = first_set - latest
        if lost - universe:
            return True
    return False


def classify_population_drift(
    *,
    first_total_registros: int | None,
    last_total_registros: int | None,
    first_total_paginas: int | None = None,
    last_total_paginas: int | None = None,
    unique_ids: int = 0,
    seen_ids: Iterable[str] = (),
    tail_ids: Iterable[str] = (),
    totals_sequence: Sequence[int] = (),
    page_id_sequences: Sequence[tuple[int, tuple[str, ...]]] = (),
    pass_count: int = 1,
    persisted: int | None = None,
    fetched: int | None = None,
    rejected: int = 0,
    timeout: bool = False,
    checkpoint_committed: bool = True,
    persistence_failed: bool = False,
    state_committed: bool = True,
    elapsed_seconds: float = 0.0,
    policy: PopulationDriftPolicy = DEFAULT_DRIFT_POLICY,
) -> PopulationDriftDecision:
    """Classify population change. Inserts alone never become success."""
    seen = {str(item) for item in seen_ids if str(item)}
    tail = {str(item) for item in tail_ids if str(item)}
    unique = unique_ids if unique_ids else len(seen | tail)
    first = first_total_registros
    last = last_total_registros
    expected_growth = 0 if first is None or last is None else max(0, last - first)
    new_from_tail = len(tail - seen)
    covered_growth = 0
    if first is not None and unique > first:
        covered_growth = unique - first
    new_ids_seen = max(new_from_tail, covered_growth)

    reasons: list[str] = []
    allows_tail = False
    status = DRIFT_OK
    decision = "accept"

    if persistence_failed:
        reasons.append(REASON_PERSIST_FAIL)
        status = DRIFT_SOURCE
        decision = "refuse"
    if timeout and not checkpoint_committed:
        reasons.append(REASON_TIMEOUT_BEFORE)
        status = DRIFT_SOURCE
        decision = "refuse"
    elif timeout and checkpoint_committed and not state_committed:
        reasons.append(REASON_TIMEOUT_AFTER)
        if status == DRIFT_OK:
            status = DRIFT_NEEDS_RETRY
            decision = "retry"
    if not state_committed and persisted and persisted > 0 and not timeout:
        reasons.append(REASON_CRASH_BEFORE_COMMIT)
        if status == DRIFT_OK:
            status = DRIFT_NEEDS_RETRY
            decision = "retry"

    if first is not None and first < 0:
        reasons.append(REASON_IMPOSSIBLE)
        status = DRIFT_SOURCE
        decision = "refuse"
    if last is not None and last < 0:
        reasons.append(REASON_IMPOSSIBLE)
        status = DRIFT_SOURCE
        decision = "refuse"

    if totals_sequence and _oscillated(totals_sequence):
        reasons.append(REASON_OSCILLATION)
        status = DRIFT_SOURCE
        decision = "refuse"

    if page_id_sequences and _conflicting_duplicate_pages(page_id_sequences):
        reasons.append(REASON_DUPLICATE_CONFLICT)
        status = DRIFT_SOURCE
        decision = "refuse"

    if page_id_sequences and _reorder_omitted(page_id_sequences, seen | tail):
        reasons.append(REASON_REORDER_OMIT)
        status = DRIFT_SOURCE
        decision = "refuse"

    if first is not None and last is not None and last < first:
        reasons.append(REASON_SHRINK)
        status = DRIFT_SOURCE
        decision = "refuse"

    if first_total_paginas is not None and last_total_paginas is not None and last_total_paginas < first_total_paginas:
        reasons.append(REASON_PAGE_SHRINK)
        status = DRIFT_SOURCE
        decision = "refuse"

    if (
        first_total_paginas is not None
        and last_total_paginas is not None
        and last_total_paginas - first_total_paginas > policy.max_page_growth
    ):
        reasons.append(REASON_PAGE_JUMP)
        status = DRIFT_SOURCE
        decision = "refuse"

    if first is not None and last is not None and last > first:
        if not growth_within_budget(first, last, policy):
            reasons.append(REASON_JUMP)
            status = DRIFT_SOURCE
            decision = "refuse"
        elif status not in {DRIFT_SOURCE, DRIFT_RECONCILE}:
            covered_all = unique >= last
            tail_proved = bool(tail) and new_from_tail >= expected_growth
            proven = covered_all or tail_proved
            if proven:
                reasons.append(REASON_MONOTONIC_GROWTH)
                status = DRIFT_CONVERGED
                decision = "accept_converged"
            else:
                reasons.append(REASON_GROWTH_UNPROVEN)
                if unique < last:
                    reasons.append(REASON_IDS_UNSEEN)
                status = DRIFT_NEEDS_RETRY
                decision = "retry"
                allows_tail = pass_count < policy.max_passes
                # The time budget bounds an additional convergence pass. A
                # long but stable first pass is still a valid complete pass.
                if elapsed_seconds > policy.max_seconds:
                    reasons.append(REASON_TIME_BUDGET)
                    allows_tail = False
            if pass_count >= policy.max_passes and status == DRIFT_NEEDS_RETRY:
                reasons.append(REASON_CONVERGENCE_CAP)
                allows_tail = False

    if first is not None and last is not None and last == first and status == DRIFT_OK:
        reasons.append(REASON_STABLE)

    if fetched is not None and persisted is not None:
        if fetched != persisted + rejected:
            reasons.append(REASON_INCONSISTENT_COUNT)
            if status in {DRIFT_OK, DRIFT_CONVERGED}:
                status = DRIFT_RECONCILE
                decision = "refuse"

    if unique and last is not None and unique > last and status in {DRIFT_OK, DRIFT_CONVERGED}:
        reasons.append(REASON_INCONSISTENT_COUNT)
        status = DRIFT_SOURCE
        decision = "refuse"

    if not reasons:
        reasons.append(REASON_STABLE)

    # Deduplicate reason codes preserving order
    codes = tuple(dict.fromkeys(reasons))
    return PopulationDriftDecision(
        status=status,
        decision=decision,
        reason_codes=codes,
        first_total_registros=first,
        last_total_registros=last,
        first_total_paginas=first_total_paginas,
        last_total_paginas=last_total_paginas,
        unique_ids=unique,
        expected_growth=expected_growth,
        new_ids_seen=new_ids_seen,
        pass_count=pass_count,
        allows_tail_pass=allows_tail and status == DRIFT_NEEDS_RETRY,
        policy=policy,
    )


@dataclass
class PaginationReport:
    rule_version: str
    first_total_registros: int | None
    last_total_registros: int | None
    first_total_paginas: int | None
    last_total_paginas: int | None
    fetched: int
    persisted: int
    rejected: int
    unique_ids: int
    duplicate_ids: int
    status: str
    reasons: tuple[str, ...]
    reason_codes: tuple[str, ...] = ()
    decision: str = "accept"
    pass_count: int = 1
    expected_growth: int = 0
    new_ids_seen: int = 0
    allows_tail_pass: bool = False
    counts_reconciled: bool = True

    @property
    def ok(self) -> bool:
        return self.status in {DRIFT_OK, DRIFT_CONVERGED}

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_version": self.rule_version,
            "first_total_registros": self.first_total_registros,
            "last_total_registros": self.last_total_registros,
            "first_total_paginas": self.first_total_paginas,
            "last_total_paginas": self.last_total_paginas,
            "fetched": self.fetched,
            "persisted": self.persisted,
            "rejected": self.rejected,
            "unique_ids": self.unique_ids,
            "duplicate_ids": self.duplicate_ids,
            "status": self.status,
            "reasons": list(self.reasons),
            "reason_codes": list(self.reason_codes or self.reasons),
            "decision": self.decision,
            "pass_count": self.pass_count,
            "expected_growth": self.expected_growth,
            "new_ids_seen": self.new_ids_seen,
            "allows_tail_pass": self.allows_tail_pass,
            "counts_reconciled": self.counts_reconciled,
            "ok": self.ok,
        }


def _as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text or text.lower() in {"none", "null"}:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _norm_status(raw: Any) -> str:
    text = str(raw or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def classify_contract_activity(
    *,
    raw_status: Any = None,
    vigencia_inicio: Any = None,
    vigencia_fim: Any = None,
    today: date | None = None,
    source: str = "pncp",
    observed_at: str | None = None,
    is_active_default: Any = None,
) -> ContractActivity:
    """Absence of proven status/vigência is UNKNOWN — never ACTIVE.

    ``is_active=TRUE`` defaults are ignored. A later event must supply an
    explicit status token or a closed vigência window to leave UNKNOWN.
    """
    del is_active_default  # never proof of activity
    ref = today or date.today()
    raw = None if raw_status is None else str(raw_status).strip()
    token = _norm_status(raw)
    start = _as_date(vigencia_inicio)
    end = _as_date(vigencia_fim)
    reasons: list[str] = []

    if token:
        if token in _CANCELLED_TOKENS:
            return ContractActivity(CANCELLED, raw, ACTIVITY_RULE_VERSION, source, observed_at, ("raw_status",))
        if token in _TERMINATED_TOKENS:
            return ContractActivity(TERMINATED, raw, ACTIVITY_RULE_VERSION, source, observed_at, ("raw_status",))
        if token in _SUSPENDED_TOKENS:
            return ContractActivity(SUSPENDED, raw, ACTIVITY_RULE_VERSION, source, observed_at, ("raw_status",))
        if token in _COMPLETED_TOKENS:
            return ContractActivity(COMPLETED, raw, ACTIVITY_RULE_VERSION, source, observed_at, ("raw_status",))
        if token in _ACTIVE_TOKENS:
            if start and end and start > end:
                reasons.append("inverted_vigencia")
                return ContractActivity(UNKNOWN, raw, ACTIVITY_RULE_VERSION, source, observed_at, tuple(reasons))
            if end is not None and end < ref:
                return ContractActivity(COMPLETED, raw, ACTIVITY_RULE_VERSION, source, observed_at, ("vigencia_ended",))
            if start is None and end is None:
                reasons.append("active_token_without_vigencia")
                return ContractActivity(UNKNOWN, raw, ACTIVITY_RULE_VERSION, source, observed_at, tuple(reasons))
            return ContractActivity(
                ACTIVE_PROVEN, raw, ACTIVITY_RULE_VERSION, source, observed_at, ("raw_status+vigencia",)
            )

    if start and end:
        if start > end:
            return ContractActivity(UNKNOWN, raw, ACTIVITY_RULE_VERSION, source, observed_at, ("inverted_vigencia",))
        if end < ref:
            return ContractActivity(COMPLETED, raw, ACTIVITY_RULE_VERSION, source, observed_at, ("vigencia_ended",))
        if start <= ref <= end:
            return ContractActivity(
                ACTIVE_PROVEN, raw, ACTIVITY_RULE_VERSION, source, observed_at, ("vigencia_window",)
            )

    reasons.append("missing_status_and_vigencia")
    return ContractActivity(UNKNOWN, raw, ACTIVITY_RULE_VERSION, source, observed_at, tuple(reasons))


def in_active_proven(activity: ContractActivity) -> bool:
    return activity.state == ACTIVE_PROVEN


_DATE_COLUMNS_FOR_MAX = (
    "data_assinatura",
    "data_inicio",
    "data_fim",
    "data_publicacao",
    "data_publicacao_fonte",
    "data_atualizacao_fonte",
    "source_event_date",
)


def null_implausible_contract_dates(record: dict[str, Any]) -> dict[str, Any]:
    """Drop dates that would contaminate MAX/recency. Quality already labeled."""
    for name in _DATE_COLUMNS_FOR_MAX:
        parsed = _as_date(record.get(name))
        if parsed is None:
            continue
        if parsed.year >= 8000 or parsed.year > _PLAUSIBLE_YEAR_MAX or parsed.year < _PLAUSIBLE_YEAR_MIN:
            record[name] = None
    return record


def classify_contract_quality(
    *,
    data_assinatura: Any = None,
    data_inicio: Any = None,
    data_fim: Any = None,
    data_publicacao: Any = None,
    valor: Any = None,
    today: date | None = None,
) -> ContractQuality:
    """Label implausible dates/values. Raw rows are left untouched."""
    reasons: list[str] = []
    state = VALID
    impact: float | None = None

    dates = {
        "data_assinatura": _as_date(data_assinatura),
        "data_inicio": _as_date(data_inicio),
        "data_fim": _as_date(data_fim),
        "data_publicacao": _as_date(data_publicacao),
    }
    for name, parsed in dates.items():
        if parsed is None:
            raw = {
                "data_assinatura": data_assinatura,
                "data_inicio": data_inicio,
                "data_fim": data_fim,
                "data_publicacao": data_publicacao,
            }[name]
            if raw not in (None, ""):
                reasons.append(f"unparseable_date:{name}")
                state = QUARANTINED
            continue
        if parsed.year > _PLAUSIBLE_YEAR_MAX or parsed.year >= 8000:
            reasons.append(f"implausible_future_year:{name}:{parsed.isoformat()}")
            state = QUARANTINED
        elif parsed.year < _PLAUSIBLE_YEAR_MIN:
            reasons.append(f"implausible_ancient_year:{name}:{parsed.isoformat()}")
            state = REVIEW if state == VALID else state

    start, end = dates["data_inicio"], dates["data_fim"]
    if start and end and start > end:
        reasons.append("inverted_vigencia")
        state = QUARANTINED

    assinatura, pub = dates["data_assinatura"], dates["data_publicacao"]
    if assinatura and pub and assinatura > pub + (pub - pub):
        # assinatura far after publication is review, not auto-quarantine
        if (assinatura - pub).days > 3650:
            reasons.append("assinatura_far_from_publicacao")
            state = REVIEW if state == VALID else state

    if valor is not None and valor != "":
        try:
            amount = float(valor)
        except (TypeError, ValueError):
            reasons.append("unparseable_value")
            state = QUARANTINED
            amount = None
        if amount is not None:
            impact = amount
            if amount < 0:
                reasons.append("negative_value")
                state = QUARANTINED
            elif amount == 0:
                reasons.append("zero_value_without_semantics")
                state = REVIEW if state == VALID else state
            elif amount > _TRILLION_BRL:
                reasons.append("value_exceeds_one_trillion")
                state = QUARANTINED
            else:
                # Suspicious cents on huge integers (scale-break heuristic).
                if amount >= 10_000_000_000 and "e" in str(amount).lower():
                    reasons.append("scientific_scale_break")
                    state = REVIEW if state == VALID else state
                # Classic centavo-as-real: values like 12345678901 meaning 123M*100
                if amount >= 100_000_000_000:
                    reasons.append("scale_break_suspect")
                    state = QUARANTINED

    if not reasons:
        reasons.append("ok")
    return ContractQuality(
        state=state, rule_version=QUALITY_RULE_VERSION, reasons=tuple(reasons), financial_impact=impact
    )


def report_ready_allowed(quality: ContractQuality) -> bool:
    return quality.state != QUARANTINED


def canonical_contract_identity(
    *,
    source: str,
    official_id: str | None = None,
    source_contract_id: str | None = None,
    parent_procurement_id: str | None = None,
    fallback_parts: Iterable[Any] = (),
) -> CanonicalContract:
    """Namespace official IDs per source. Fallback is deterministic."""
    src = (source or "").strip().lower() or "unknown"
    official = (official_id or source_contract_id or "").strip()
    parent = (parent_procurement_id or "").strip() or None
    if official:
        return CanonicalContract(
            canonical_contract_id=f"{src}:{official}",
            source=src,
            source_contract_id=official,
            parent_procurement_id=parent,
            method="official",
            rule_version=IDENTITY_RULE_VERSION,
        )
    parts = [str(part).strip() for part in fallback_parts if part not in (None, "")]
    if parent:
        parts.append(f"parent:{parent}")
    if not parts:
        digest = hashlib.sha256(f"{src}:empty:{parent or ''}".encode()).hexdigest()[:16]
        return CanonicalContract(
            canonical_contract_id=f"{src}:fallback:{digest}",
            source=src,
            source_contract_id=f"fallback:{digest}",
            parent_procurement_id=parent,
            method="fallback",
            rule_version=IDENTITY_RULE_VERSION,
            ambiguous=True,
        )
    payload = "|".join(parts)
    digest = hashlib.sha256(f"{src}:{payload}".encode()).hexdigest()[:20]
    return CanonicalContract(
        canonical_contract_id=f"{src}:fallback:{digest}",
        source=src,
        source_contract_id=f"fallback:{digest}",
        parent_procurement_id=parent,
        method="fallback",
        rule_version=IDENTITY_RULE_VERSION,
    )


def replay_adapters_to_canonical(
    adapter_payloads: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Two adapters on the same official contract → one canonical + N observations."""
    contracts: dict[str, CanonicalContract] = {}
    observations: list[dict[str, Any]] = []
    for payload in adapter_payloads:
        ident = canonical_contract_identity(
            source=str(payload.get("source") or "pncp"),
            official_id=payload.get("official_id")
            or payload.get("numeroControlePNCP")
            or payload.get("numeroControlePncpCompra"),
            source_contract_id=payload.get("source_contract_id"),
            parent_procurement_id=payload.get("parent_procurement_id"),
            fallback_parts=payload.get("fallback_parts") or (),
        )
        contracts[ident.canonical_contract_id] = ident
        observations.append(
            {
                "canonical_contract_id": ident.canonical_contract_id,
                "source": ident.source,
                "source_contract_id": ident.source_contract_id,
                "adapter": payload.get("adapter"),
            }
        )
    return {
        "canonical_count": len(contracts),
        "observation_count": len(observations),
        "canonical_ids": sorted(contracts),
        "observations": observations,
        "ambiguous": any(item.ambiguous for item in contracts.values()),
    }


class PaginationReconcile:
    """Accumulate page totals and fail closed on source drift."""

    def __init__(self) -> None:
        self.first_total_registros: int | None = None
        self.last_total_registros: int | None = None
        self.first_total_paginas: int | None = None
        self.last_total_paginas: int | None = None
        self.fetched = 0
        self.persisted = 0
        self.rejected = 0
        self._ids: set[str] = set()
        self.duplicate_ids = 0
        self._page_ids: list[str] = []
        self._totals_sequence: list[int] = []
        self._page_id_sequences: list[tuple[int, tuple[str, ...]]] = []
        self._tail_ids: set[str] = set()
        self._first_pass_ids: set[str] = set()
        self._pass_count = 1

    @property
    def seen_ids(self) -> frozenset[str]:
        return frozenset(self._ids)

    @property
    def tail_ids(self) -> frozenset[str]:
        return frozenset(self._tail_ids)

    @property
    def page_id_sequences(self) -> tuple[tuple[int, tuple[str, ...]], ...]:
        return tuple(self._page_id_sequences)

    @property
    def totals_sequence(self) -> tuple[int, ...]:
        return tuple(self._totals_sequence)

    def observe_page(
        self,
        *,
        total_registros: int | None,
        total_paginas: int | None,
        items: Iterable[Mapping[str, Any]],
        id_field: str = "numeroControlePNCP",
        page: int | None = None,
        tail: bool = False,
    ) -> None:
        if total_registros is not None:
            if self.first_total_registros is None:
                self.first_total_registros = int(total_registros)
            self.last_total_registros = int(total_registros)
            self._totals_sequence.append(int(total_registros))
        if total_paginas is not None:
            if self.first_total_paginas is None:
                self.first_total_paginas = int(total_paginas)
            self.last_total_paginas = int(total_paginas)
        page_ids: list[str] = []
        for item in items:
            item_id = str(item.get(id_field) or item.get("id") or "").strip()
            self.fetched += 1
            if not item_id:
                self.rejected += 1
                continue
            if item_id in self._ids:
                self.duplicate_ids += 1
            self._ids.add(item_id)
            self._page_ids.append(item_id)
            page_ids.append(item_id)
            if tail:
                self._tail_ids.add(item_id)
        if page is not None:
            self._page_id_sequences.append((int(page), tuple(page_ids)))

    def mark_first_pass_complete(self) -> None:
        self._first_pass_ids = set(self._ids)

    def observe_tail_page(
        self,
        *,
        total_registros: int | None,
        total_paginas: int | None,
        items: Iterable[Mapping[str, Any]],
        id_field: str = "numeroControlePNCP",
        page: int | None = None,
    ) -> None:
        self._pass_count = max(self._pass_count, 2)
        self.observe_page(
            total_registros=total_registros,
            total_paginas=total_paginas,
            items=items,
            id_field=id_field,
            page=page,
            tail=True,
        )

    def record_persisted(self, count: int = 1) -> None:
        self.persisted += int(count)

    def record_rejected(self, count: int = 1) -> None:
        self.rejected += int(count)

    def finish(
        self,
        *,
        pass_count: int | None = None,
        timeout: bool = False,
        checkpoint_committed: bool = True,
        persistence_failed: bool = False,
        state_committed: bool = True,
        elapsed_seconds: float = 0.0,
        policy: PopulationDriftPolicy = DEFAULT_DRIFT_POLICY,
        reconcile_counts: bool = True,
    ) -> PaginationReport:
        passes = int(pass_count if pass_count is not None else self._pass_count)
        first_pass = self._first_pass_ids or (self._ids - self._tail_ids)
        decision = classify_population_drift(
            first_total_registros=self.first_total_registros,
            last_total_registros=self.last_total_registros,
            first_total_paginas=self.first_total_paginas,
            last_total_paginas=self.last_total_paginas,
            unique_ids=len(self._ids),
            seen_ids=first_pass,
            tail_ids=self._tail_ids,
            totals_sequence=self._totals_sequence,
            page_id_sequences=tuple(self._page_id_sequences),
            pass_count=passes,
            persisted=self.persisted if reconcile_counts else None,
            fetched=self.fetched if reconcile_counts else None,
            rejected=self.rejected,
            timeout=timeout,
            checkpoint_committed=checkpoint_committed,
            persistence_failed=persistence_failed,
            state_committed=state_committed,
            elapsed_seconds=elapsed_seconds,
            policy=policy,
        )
        reasons: list[str] = list(decision.reason_codes)
        if (
            self.first_total_registros is not None
            and self.last_total_registros is not None
            and self.first_total_registros != self.last_total_registros
        ):
            reasons.append(f"totalRegistros {self.first_total_registros} -> {self.last_total_registros}")
        if (
            self.first_total_paginas is not None
            and self.last_total_paginas is not None
            and self.first_total_paginas != self.last_total_paginas
            and decision.status == DRIFT_SOURCE
        ):
            reasons.append(f"totalPaginas {self.first_total_paginas} -> {self.last_total_paginas}")
        if reconcile_counts and self.fetched != self.persisted + self.rejected:
            reasons.append(f"fetched={self.fetched} != persisted+rejected={self.persisted + self.rejected}")
        if not reasons:
            reasons.append("ok")
        return PaginationReport(
            rule_version=PAGINATION_RULE_VERSION,
            first_total_registros=self.first_total_registros,
            last_total_registros=self.last_total_registros,
            first_total_paginas=self.first_total_paginas,
            last_total_paginas=self.last_total_paginas,
            fetched=self.fetched,
            persisted=self.persisted,
            rejected=self.rejected,
            unique_ids=len(self._ids),
            duplicate_ids=self.duplicate_ids,
            status=decision.status,
            reasons=tuple(dict.fromkeys(reasons)),
            reason_codes=decision.reason_codes,
            decision=decision.decision,
            pass_count=decision.pass_count,
            expected_growth=decision.expected_growth,
            new_ids_seen=decision.new_ids_seen,
            allows_tail_pass=decision.allows_tail_pass,
            counts_reconciled=reconcile_counts,
        )


def isolated_test_environment() -> bool:
    return bool(os.getenv("PYTEST_CURRENT_TEST") or os.getenv("EXTRA_ISOLATED_TEST") == "1")


def is_production_contracts() -> bool:
    if os.getenv("EXTRA_CONTRACTS_PRODUCTION", "0") == "1":
        return True
    cwd = Path.cwd().as_posix()
    return cwd == "/opt/extra-consultoria" or cwd.startswith("/opt/extra-consultoria/")


def refuse_writer_bypass(*, skip_lock: bool = False, env_skip: str | None = None) -> None:
    """Production units must not skip the fence."""
    env_requested = (env_skip if env_skip is not None else os.getenv("CONTRACTS_SKIP_WRITER_LOCK", "0")) == "1"
    if not (skip_lock or env_requested):
        return
    if isolated_test_environment():
        return
    raise WriterFenceBypassError("national writer bypass refused outside isolated test")


class PostgresWriterFence:
    """Exclusive PostgreSQL advisory lock for national contract writers."""

    def __init__(self, key: int = PG_FENCE_KEY) -> None:
        self.key = key
        self.owned = False
        self._conn: Any = None

    def acquire(self, conn: Any) -> bool:
        cur = conn.cursor()
        try:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (self.key,))
            row = cur.fetchone()
        finally:
            close = getattr(cur, "close", None)
            if callable(close):
                close()
        locked = bool(row[0]) if row else False
        if locked:
            self.owned = True
            self._conn = conn
        return locked

    def release(self) -> None:
        if not self.owned or self._conn is None:
            return
        cur = self._conn.cursor()
        try:
            cur.execute("SELECT pg_advisory_unlock(%s)", (self.key,))
        finally:
            close = getattr(cur, "close", None)
            if callable(close):
                close()
        self.owned = False
        self._conn = None

    def run_exclusive(self, conn: Any, mutate) -> Any:
        """Refuse the second writer before calling ``mutate``."""
        if not self.acquire(conn):
            raise WriterFenceBusyError("national writer fence busy")
        try:
            return mutate()
        finally:
            self.release()


def acquire_national_writer_fence(
    dsn: str,
    *,
    skip: bool = False,
    connect: Any = None,
) -> PostgresWriterFence | None:
    """Acquire the PostgreSQL fence used by every national contracts writer.

    Host-local flock is not sufficient. A second writer is refused before
    ``connect`` returns a session that can mutate.
    """
    refuse_writer_bypass(skip_lock=skip)
    if skip or os.getenv("CONTRACTS_SKIP_WRITER_LOCK", "0") == "1":
        return None
    if not dsn:
        raise WriterFenceBypassError("national writer fence requires a DSN")
    if connect is None:
        import psycopg2

        connect = psycopg2.connect
    conn = connect(dsn)
    fence = PostgresWriterFence()
    if not fence.acquire(conn):
        close = getattr(conn, "close", None)
        if callable(close):
            close()
        raise WriterFenceBusyError("national writer fence busy")
    return fence


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def resolve_checkpoint_dir(
    requested: str | Path | None,
    *,
    production: bool | None = None,
    repo_root: str | Path | None = None,
    state_root: str | Path | None = None,
) -> Path:
    """Production checkpoints live under /var/lib/extra-consultoria, never the worktree."""
    if production is None:
        production = is_production_contracts()
    repo = Path(repo_root) if repo_root else Path(__file__).resolve().parents[1]
    durable = (
        Path(state_root) if state_root else Path(os.getenv("EXTRA_CONTRACTS_STATE_DIR") or str(PRODUCTION_STATE_ROOT))
    )
    if requested:
        raw = Path(requested)
    elif production:
        raw = durable / "checkpoints" / "contracts"
    else:
        raw = repo / "data" / "contracts_checkpoints"
    path = raw.expanduser()
    if not path.is_absolute():
        path = (durable / path) if production else (repo / path)
    path = path.resolve() if path.exists() else Path(os.path.normpath(str(path)))
    if not production:
        return path
    posix = path.as_posix()
    if any(posix == prefix or posix.startswith(prefix + "/") for prefix in FORBIDDEN_CHECKPOINT_PREFIXES):
        raise CheckpointLocationError(f"production checkpoint refuses release tree: {path}")
    if _is_relative_to(path, repo):
        raise CheckpointLocationError(f"production checkpoint refuses git worktree: {path}")
    if not _is_relative_to(path, durable):
        raise CheckpointLocationError(f"production checkpoint must live under {durable}, got {path}")
    return path


def annotate_transformed_contract(record: dict[str, Any], *, raw: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Attach activity, quality and canonical identity to a transformed row."""
    payload = raw or {}
    activity = classify_contract_activity(
        raw_status=payload.get("situacaoContrato") or payload.get("situacao") or payload.get("status"),
        vigencia_inicio=record.get("data_inicio") or payload.get("dataVigenciaInicio"),
        vigencia_fim=record.get("data_fim") or payload.get("dataVigenciaFim"),
        source="pncp",
        is_active_default=record.get("is_active"),
    )
    quality = classify_contract_quality(
        data_assinatura=record.get("data_assinatura"),
        data_inicio=record.get("data_inicio"),
        data_fim=record.get("data_fim"),
        data_publicacao=record.get("data_publicacao_fonte") or record.get("data_publicacao"),
        valor=record.get("valor_total") or record.get("valor_global") or payload.get("valorGlobal"),
    )
    ident = canonical_contract_identity(
        source=str(record.get("source") or payload.get("source") or "pncp"),
        official_id=record.get("contrato_id") or payload.get("numeroControlePNCP"),
        parent_procurement_id=payload.get("numeroControlePncpCompra"),
    )
    record["status_raw"] = activity.raw_status
    record["status_normalized"] = activity.state
    record["status_rule_version"] = activity.rule_version
    record["status_source"] = activity.source
    record["quality_state"] = quality.state
    record["quality_reasons"] = list(quality.reasons)
    record["quality_rule_version"] = quality.rule_version
    record["report_ready"] = report_ready_allowed(quality)
    # Official status observation only. Inferred vigencia never gets a timestamp.
    # When status_raw is present, the DB trigger records last_seen_at as the
    # observation time — Python must not invent now().
    if not activity.raw_status:
        record["status_observed_at"] = None
    record["canonical_contract_id"] = ident.canonical_contract_id
    record["source"] = ident.source
    record["source_contract_id"] = ident.source_contract_id
    record["parent_procurement_id"] = ident.parent_procurement_id
    lineage_keys = ("run_id", "_run_id", "attempt_id", "_attempt_id", "page", "_page")
    if payload is not None and any(payload.get(k) not in (None, "") for k in lineage_keys):
        from scripts.crawl.observation_lineage import attach_lineage, lineage_from_envelope

        official = str(record.get("source_url") or payload.get("official_url") or payload.get("url") or "")
        attach_lineage(record, lineage_from_envelope(dict(payload), default_url=official or None))
    return record


TRUTH_STAMP_FIELDS = (
    "status_raw",
    "status_normalized",
    "status_rule_version",
    "status_source",
    "quality_state",
    "quality_reasons",
    "quality_rule_version",
    "report_ready",
    "canonical_contract_id",
    "source_contract_id",
    "parent_procurement_id",
    "status_observed_at",
)


def stamp_contract_truth_labels(conn: Any, records: Iterable[Mapping[str, Any]]) -> int:
    """Write activity/quality/identity labels after the legacy upsert.

    The historical RPC does not persist these columns. Callers must stamp
    them or the lake stays unlabeled (NULL quality is not report-ready).
    """
    payload = []
    for raw in records:
        contrato_id = str(raw.get("contrato_id") or "").strip()
        if not contrato_id:
            continue
        payload.append(
            {
                "contrato_id": contrato_id,
                "status_raw": raw.get("status_raw"),
                "status_normalized": raw.get("status_normalized"),
                "status_rule_version": raw.get("status_rule_version"),
                "status_source": raw.get("status_source"),
                "quality_state": raw.get("quality_state"),
                "quality_reasons": raw.get("quality_reasons") or [],
                "quality_rule_version": raw.get("quality_rule_version"),
                "report_ready": bool(raw.get("report_ready")),
                "canonical_contract_id": raw.get("canonical_contract_id"),
                "source": raw.get("source"),
                "source_contract_id": raw.get("source_contract_id"),
                "parent_procurement_id": raw.get("parent_procurement_id"),
                "status_observed_at": raw.get("status_observed_at"),
            }
        )
    if not payload:
        return 0
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE public.pncp_supplier_contracts AS target
            SET status_raw = stamp.status_raw,
                status_normalized = stamp.status_normalized,
                status_rule_version = stamp.status_rule_version,
                status_source = stamp.status_source,
                quality_state = stamp.quality_state,
                quality_reasons = stamp.quality_reasons::jsonb,
                quality_rule_version = stamp.quality_rule_version,
                canonical_contract_id = stamp.canonical_contract_id,
                source = COALESCE(stamp.source, target.source),
                source_contract_id = stamp.source_contract_id,
                parent_procurement_id = stamp.parent_procurement_id,
                status_observed_at = stamp.status_observed_at
            FROM jsonb_to_recordset(%s::jsonb) AS stamp(
                contrato_id TEXT,
                status_raw TEXT,
                status_normalized TEXT,
                status_rule_version TEXT,
                status_source TEXT,
                quality_state TEXT,
                quality_reasons JSONB,
                quality_rule_version TEXT,
                report_ready BOOLEAN,
                canonical_contract_id TEXT,
                source TEXT,
                source_contract_id TEXT,
                parent_procurement_id TEXT,
                status_observed_at TIMESTAMPTZ
            )
            WHERE target.contrato_id = stamp.contrato_id
            """,
            (json.dumps(payload, default=str),),
        )
        return int(cur.rowcount or 0)
    finally:
        close = getattr(cur, "close", None)
        if callable(close):
            close()
