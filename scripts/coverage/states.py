"""Coverage State Machine — Story 1.5.

Implementa os 9 estados de coverage e as transicoes entre eles,
conforme Secao 9 do plano mestre (P0-05).

Estados:
    not_applicable   — Fonte nao se aplica a este ente/capacidade
    pending          — Fonte aplicavel mas ainda nao verificada
    running          — Execucao em andamento
    success_with_data — Execucao concluida com dados encontrados
    success_zero     — Execucao concluida: zero registros (paginacao completa comprovada)
    partial          — Execucao incompleta (paginacao parcial, timeout)
    error            — Falha na execucao (rede, parse, auth, persist)
    blocked          — Execucao bloqueada (credencial ausente, dependencia indisponivel)
    stale            — Dados desatualizados (freshness SLA violado)

Regras (nunca violadas):
    1. ``not_applicable`` e estado terminal — nunca transiciona
    2. ``success_zero`` exige paginacao completa comprovada
    3. ``error`` pode ser qualquer um dos sub-tipos (connection, auth, parse, transform, persist)
    4. ``stale`` sempre parte de ``success_with_data`` ou ``success_zero`` quando SLA vence
    5. Data presence nunca altera coverage — metricas sao independentes
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal


class CoverageState(StrEnum):
    """The 9 coverage states from Secao 9."""

    NOT_APPLICABLE = "not_applicable"
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS_WITH_DATA = "success_with_data"
    SUCCESS_ZERO = "success_zero"
    PARTIAL = "partial"
    ERROR = "error"
    BLOCKED = "blocked"
    STALE = "stale"

    def __str__(self) -> str:
        return self.value


# Sub-tipos de erro (mantidos para compatibilidade com evidence_state)
ErrorSubType = Literal[
    "connection_failed",
    "auth_failed",
    "parse_failed",
    "transform_failed",
    "persist_failed",
    "runtime_error",
]

# Estados terminais — nunca transicionam sem acao externa
TERMINAL_STATES: frozenset[CoverageState] = frozenset(
    {
        CoverageState.NOT_APPLICABLE,
    }
)

# Estados que indicam cobertura positiva (contam como "covered")
COVERED_STATES: frozenset[CoverageState] = frozenset(
    {
        CoverageState.SUCCESS_WITH_DATA,
        CoverageState.SUCCESS_ZERO,
    }
)

# Estados que exigem acao (nao covered, nao terminal)
ACTION_REQUIRED_STATES: frozenset[CoverageState] = frozenset(
    {
        CoverageState.PENDING,
        CoverageState.PARTIAL,
        CoverageState.ERROR,
        CoverageState.BLOCKED,
        CoverageState.STALE,
    }
)


# ---------------------------------------------------------------------------
# Transition rules
# ---------------------------------------------------------------------------

# Mapa de transicoes validas: {from_state: [to_state1, to_state2, ...]}
_VALID_TRANSITIONS: dict[CoverageState, list[CoverageState]] = {
    CoverageState.NOT_APPLICABLE: [],  # Terminal — sem saida
    CoverageState.PENDING: [
        CoverageState.RUNNING,
        CoverageState.BLOCKED,
        CoverageState.NOT_APPLICABLE,
    ],
    CoverageState.RUNNING: [
        CoverageState.SUCCESS_WITH_DATA,
        CoverageState.SUCCESS_ZERO,
        CoverageState.PARTIAL,
        CoverageState.ERROR,
        CoverageState.BLOCKED,
        CoverageState.PENDING,  # Reset para pending se abortado
    ],
    CoverageState.SUCCESS_WITH_DATA: [
        CoverageState.STALE,
        CoverageState.RUNNING,  # Novo ciclo
        CoverageState.PARTIAL,  # Reavaliacao revelou incompletude
    ],
    CoverageState.SUCCESS_ZERO: [
        CoverageState.STALE,
        CoverageState.RUNNING,  # Novo ciclo
        CoverageState.SUCCESS_WITH_DATA,  # Dados apareceram
    ],
    CoverageState.PARTIAL: [
        CoverageState.RUNNING,  # Retentativa
        CoverageState.SUCCESS_WITH_DATA,
        CoverageState.SUCCESS_ZERO,
        CoverageState.ERROR,
        CoverageState.STALE,  # Dados parciais envelheceram
    ],
    CoverageState.ERROR: [
        CoverageState.PENDING,  # Reset para retentativa
        CoverageState.RUNNING,  # Retentativa direta
        CoverageState.BLOCKED,  # Erro recorrente → blocked
    ],
    CoverageState.BLOCKED: [
        CoverageState.PENDING,  # Bloqueio removido
        CoverageState.NOT_APPLICABLE,  # Bloqueio permanente
    ],
    CoverageState.STALE: [
        CoverageState.RUNNING,  # Novo ciclo de verificacao
        CoverageState.PENDING,  # Reset
    ],
}


def is_valid_transition(
    from_state: CoverageState | str,
    to_state: CoverageState | str,
) -> bool:
    """Check if a state transition is valid.

    Args:
        from_state: Current state (CoverageState enum or string).
        to_state: Desired next state (CoverageState enum or string).

    Returns:
        True if the transition is valid.
    """
    if isinstance(from_state, str):
        try:
            from_state = CoverageState(from_state)
        except ValueError:
            return False
    if isinstance(to_state, str):
        try:
            to_state = CoverageState(to_state)
        except ValueError:
            return False

    valid_targets = _VALID_TRANSITIONS.get(from_state, [])
    return to_state in valid_targets


# ---------------------------------------------------------------------------
# Coverage evidence creation helpers
# ---------------------------------------------------------------------------


@dataclass
class CoverageEvidence:
    """Schema for a coverage_evidence row (Story 1.5 / Secao 9).

    Not a DB model — this is the domain object used by the state machine.
    """

    # Identity
    canonical_entity_key: str | None = None
    entity_id: int | None = None
    capability: str = "open_tenders"
    source: str = ""
    data_type: str = "bids"

    # Applicability
    applicability: str = "unknown"  # applicable | not_applicable | unknown
    applicability_reason: str = ""

    # Scope
    scope_key: str = ""
    period_start: datetime | None = None
    period_end: datetime | None = None
    source_run_id: str = ""

    # State
    state: CoverageState = CoverageState.PENDING

    # Pagination proof (required for success_zero)
    pages_expected: int | None = None
    pages_processed: int | None = None
    records_expected: int | None = None
    records_fetched: int = 0
    records_transformed: int = 0
    records_persisted: int = 0

    # Freshness
    freshness_status: str = "unknown"  # fresh | stale | unknown | overdue
    checked_at: datetime | None = None
    next_due_at: datetime | None = None

    # Error
    error_code: str = ""
    error_message: str = ""

    # Metadata
    evidence_metadata: dict | None = None


def determine_initial_state(
    source_info: dict,
    applicability: str = "unknown",
) -> CoverageState:
    """Determine the initial coverage state for a (entity, source) pair.

    Args:
        source_info: SourceInfo-like dict with keys like
                     ``supports_zero_proof``, ``supports_pagination``, etc.
        applicability: Pre-determined applicability decision.

    Returns:
        Initial CoverageState.
    """
    if applicability == "not_applicable":
        return CoverageState.NOT_APPLICABLE
    if applicability == "unknown":
        return CoverageState.PENDING
    # applicable
    if source_info.get("is_blocked", False):
        return CoverageState.BLOCKED
    return CoverageState.PENDING


def determine_run_result_state(
    fetched: int,
    transformed: int,
    persisted: int,
    *,
    fetch_complete: bool,
    supports_zero_proof: bool = False,
    records_expected: int | None = None,
    pages_expected: int | None = None,
    pages_processed: int | None = None,
) -> CoverageState:
    """Determine coverage state after a crawl run.

    Args:
        fetched: Number of records fetched from the source.
        transformed: Number of records after transformation.
        persisted: Number of records persisted to DB.
        fetch_complete: Whether the full pagination scope completed without errors.
        supports_zero_proof: Whether the source can prove zero results.
        records_expected: Number of records expected (if known).
        pages_expected: Number of pages expected.
        pages_processed: Number of pages processed.

    Returns:
        The appropriate CoverageState.
    """
    if fetched > 0 or transformed > 0 or persisted > 0:
        return CoverageState.SUCCESS_WITH_DATA

    # Zero records — determine if it's legitimate success_zero or partial
    if fetch_complete:
        # Must prove pagination completeness for success_zero
        if supports_zero_proof and pages_expected is not None and pages_processed is not None:
            if pages_processed >= pages_expected:
                return CoverageState.SUCCESS_ZERO
            else:
                return CoverageState.PARTIAL
        elif records_expected is not None and records_expected == 0:
            return CoverageState.SUCCESS_ZERO
        else:
            # Conservative: without pagination proof, it's partial
            return CoverageState.PARTIAL
    else:
        return CoverageState.PARTIAL


def evaluate_freshness(
    state: CoverageState,
    checked_at: datetime | None,
    freshness_sla_hours: int = 24,
) -> tuple[CoverageState, str]:
    """Evaluate freshness and return (new_state, freshness_status).

    Args:
        state: Current coverage state.
        checked_at: When the last check happened.
        freshness_sla_hours: SLA in hours for this source.

    Returns:
        Tuple of (updated_state, freshness_status).
    """
    if state not in COVERED_STATES and state != CoverageState.PARTIAL:
        return state, "unknown"

    if checked_at is None:
        return state, "unknown"

    now = datetime.now(UTC)
    if checked_at.tzinfo is None:
        now = now.replace(tzinfo=None)

    elapsed = (now - checked_at).total_seconds() / 3600

    if elapsed <= freshness_sla_hours:
        return state, "fresh"
    elif elapsed <= freshness_sla_hours * 2:
        return state, "stale"
    else:
        return CoverageState.STALE, "overdue"


def map_monitor_state_to_evidence(
    monitor_status: str,
    error_code: str = "",
    fetched: int = 0,
) -> tuple[CoverageState, str]:
    """Map monitor.py status/error_code to unified CoverageState + error_code.

    Args:
        monitor_status: Status string from monitor.py (success, failed, etc.).
        error_code: Error code string.
        fetched: Number of records fetched.

    Returns:
        Tuple of (CoverageState, normalized_error_code).
    """
    # Explicit error codes
    if error_code:
        error_state_map: dict[str, CoverageState] = {
            "crawler_not_implemented": CoverageState.NOT_APPLICABLE,
            "missing_credentials": CoverageState.BLOCKED,
            "fetch_failed": CoverageState.ERROR,
            "persist_failed": CoverageState.ERROR,
            "runtime_error": CoverageState.ERROR,
            "empty_result": CoverageState.PARTIAL,
        }
        if error_code in error_state_map:
            return error_state_map[error_code], error_code

    # Monitor status mapping
    status_map: dict[str, CoverageState] = {
        "success": CoverageState.SUCCESS_WITH_DATA if fetched > 0 else CoverageState.SUCCESS_ZERO,
        "degraded": CoverageState.PARTIAL,
        "failed": CoverageState.ERROR,
        "empty": CoverageState.SUCCESS_ZERO if fetched == 0 else CoverageState.PARTIAL,
        "skipped": CoverageState.PENDING,
    }
    mapped = status_map.get(monitor_status, CoverageState.PENDING)
    return mapped, error_code


__all__ = [
    "ACTION_REQUIRED_STATES",
    "COVERED_STATES",
    "CoverageEvidence",
    "CoverageState",
    "ErrorSubType",
    "TERMINAL_STATES",
    "determine_initial_state",
    "determine_run_result_state",
    "evaluate_freshness",
    "is_valid_transition",
    "map_monitor_state_to_evidence",
]
