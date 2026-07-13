"""Canonical status calculation for bidding opportunities.

Determines the unified status from source-specific status values
and temporal evidence. Uses enhanced heuristics for bids without
explicit closing dates (data_encerramento).

Status values:
    open       — actively accepting proposals (data_encerramento in future)
    upcoming   — published but not yet accepting proposals
    closed     — deadline passed or explicitly closed
    suspended  — temporarily suspended (source says "suspensa")
    revoked    — cancelled/revoked (source says "revogada")
    annulled   — annulled (source says "anulada")
    failed     — no bidders, deserted, or otherwise failed
    unknown    — insufficient data to determine status

Priority order: source status (most reliable) -> temporal evidence
-> heuristic inference -> conservative default (unknown).
"""

from __future__ import annotations

from datetime import UTC, datetime

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Modalidades that typically don't have formal closing dates
OPEN_MODALITIES: set[str] = {
    "dispensa",
    "inexigibilidade",
    "credenciamento",
    "adesão",
    "adesao",
    "chamamento público",
    "chamamento publico",
    "chamada pública",
    "chamada publica",
    "suprimento de fundos",
    "suprimento",
}

# Window (days) within which a bid without end date is considered open
OPEN_WINDOW_DAYS = 90

# Window (days) after which a bid without end date is considered closed
CLOSED_WINDOW_DAYS = 365

# ---------------------------------------------------------------------------
# Status mapping: source-specific -> canonical
# ---------------------------------------------------------------------------

# PNCP situacao_compra values -> canonical
_PNCP_STATUS_MAP: dict[str, str] = {
    "divulgada no pncp": "open",  # Published on PNCP — active
    "recebendo proposta": "open",  # Accepting proposals
    "aberta": "open",  # Open
    "em andamento": "open",  # In progress
    "agendada": "upcoming",  # Scheduled
    "divulgada": "upcoming",  # Published (generic)
    "encerrada": "closed",  # Closed
    "concluída": "closed",  # Concluded
    "concluida": "closed",
    "homologada": "closed",  # Approved
    "suspensa": "suspended",  # Suspended
    "revogada": "revoked",  # Revoked
    "anulada": "annulled",  # Annulled
    "cancelada": "revoked",  # Cancelled
    "deserta": "failed",  # No bidders
    "fracassada": "failed",  # Failed
    "em analise": "open",  # Under analysis — still active
    "adjudicada": "closed",  # Awarded
}

# DOM-SC status values -> canonical
_DOM_SC_STATUS_MAP: dict[str, str] = {
    "publicado": "open",
    "autopublicação nova": "open",
    "autopublicacao nova": "open",
    "autopublicação assinada": "open",
    "autopublicacao assinada": "open",
    "autopublicação publicada": "open",
    "autopublicacao publicada": "open",
    "acervo público": "unknown",
    "acervo publico": "unknown",
    "cancelado": "revoked",
    "publicado equivocadamente": "revoked",
    "acervo removido": "revoked",
}

# Generic terms that appear across sources
_GENERIC_STATUS_MAP: dict[str, str] = {
    "aberto": "open",
    "aberta": "open",
    "abertos": "open",
    "abertas": "open",
    "em aberto": "open",
    "em andamento": "open",
    "publicado": "open",
    "publicada": "open",
    "divulgado": "upcoming",
    "divulgada": "upcoming",
    "agendado": "upcoming",
    "agendada": "upcoming",
    "previsto": "upcoming",
    "encerrado": "closed",
    "encerrada": "closed",
    "concluído": "closed",
    "concluida": "closed",
    "concluído": "closed",
    "concluida": "closed",
    "finalizado": "closed",
    "finalizada": "closed",
    "homologado": "closed",
    "homologada": "closed",
    "suspenso": "suspended",
    "suspensa": "suspended",
    "revogado": "revoked",
    "revogada": "revoked",
    "anulado": "annulled",
    "anulada": "annulled",
    "cancelado": "revoked",
    "cancelada": "revoked",
    "deserto": "failed",
    "deserta": "failed",
    "fracassado": "failed",
    "fracassada": "failed",
    "frustrado": "failed",
    "frustrada": "failed",
}


# ---------------------------------------------------------------------------
# Status inference for NULL data_encerramento
# ---------------------------------------------------------------------------


def infer_status_from_dates(
    data_publicacao: datetime | None = None,
    data_abertura: datetime | None = None,
    modalidade: str | None = None,
    source: str = "unknown",
    status_fonte: str | None = None,
) -> tuple[str, str]:
    """Infer bid status when data_encerramento is NULL.

    Uses a cascade of heuristics based on publication age, modality,
    and source characteristics.

    Heuristics (in order):
    1. Published > CLOSED_WINDOW_DAYS ago -> CLOSED (expired)
    2. Published > OPEN_WINDOW_DAYS ago + modalidade = pregao -> CLOSED
    3. Published <= OPEN_WINDOW_DAYS ago -> OPEN (within typical window)
    4. Published > OPEN_WINDOW_DAYS ago + open modality -> OPEN (flexible window)
    5. No publication date -> UNKNOWN

    Args:
        data_publicacao: Publication date.
        data_abertura: Opening/session date.
        modalidade: Modality name (e.g., "Pregão", "Dispensa").
        source: Source name (pncp, dom_sc, etc.).
        status_fonte: Raw status string from source (for logging).

    Returns:
        (status_canonico, motivo) tuple.
    """
    now = datetime.now(UTC)
    modalidade_lower = modalidade.strip().lower() if modalidade else ""

    # Check data_abertura in future -> upcoming
    if data_abertura and data_abertura > now:
        return "upcoming", (f"data_abertura ({data_abertura.date()}) no futuro sem data_encerramento -> upcoming")

    # Check data_abertura in past -> probably already started
    if data_abertura and data_abertura <= now:
        # If abertura is in the past, the bid has started
        # Without end date, check publication age
        if data_publicacao:
            days_since_pub = (now - data_publicacao).days
            if days_since_pub <= OPEN_WINDOW_DAYS:
                return "open", (
                    f"data_abertura no passado + publicado ha {days_since_pub}d "
                    f"(<={OPEN_WINDOW_DAYS}d) sem encerramento -> open (inferido)"
                )
            if days_since_pub <= CLOSED_WINDOW_DAYS:
                return "unknown", (
                    f"data_abertura no passado + publicado ha {days_since_pub}d "
                    f"({OPEN_WINDOW_DAYS}-{CLOSED_WINDOW_DAYS}d) sem encerramento -> unknown"
                )
            return "closed", (
                f"data_abertura no passado + publicado ha {days_since_pub}d "
                f"(>{CLOSED_WINDOW_DAYS}d) sem encerramento -> closed (inferido)"
            )
        # Has abertura but no publicacao and no encerramento -> ambiguous
        return "unknown", ("data_abertura passada sem data_encerramento e sem data_publicacao -> unknown")

    # No data_abertura — use data_publicacao as primary signal
    if not data_publicacao:
        return "unknown", "sem data_publicacao e sem data_encerramento -> unknown"

    days_since = (now - data_publicacao).days

    # Rule 1: Published > CLOSED_WINDOW_DAYS ago -> CLOSED
    if days_since > CLOSED_WINDOW_DAYS:
        return "closed", (f"publicado ha {days_since}d (>{CLOSED_WINDOW_DAYS}d) sem encerramento -> closed (inferido)")

    # Rule 2: Published > OPEN_WINDOW_DAYS + pregao -> CLOSED
    if days_since > OPEN_WINDOW_DAYS and "pregao" in modalidade_lower:
        return "closed", (
            f"publicado ha {days_since}d (>{OPEN_WINDOW_DAYS}d) + "
            f"modalidade={modalidade} sem encerramento -> closed (inferido)"
        )

    # Rule 3: Published > OPEN_WINDOW_DAYS + open modality -> OPEN
    if days_since > OPEN_WINDOW_DAYS and modalidade_lower in OPEN_MODALITIES:
        return "open", (
            f"publicado ha {days_since}d + modalidade={modalidade} "
            f"sem encerramento -> open (modalidade sem prazo formal)"
        )

    # Rule 4: Published > OPEN_WINDOW_DAYS (but <= CLOSED_WINDOW) -> UNKNOWN
    if days_since > OPEN_WINDOW_DAYS:
        return "unknown", (
            f"publicado ha {days_since}d ({OPEN_WINDOW_DAYS}-{CLOSED_WINDOW_DAYS}d) sem encerramento -> unknown"
        )

    # Rule 5: Published <= OPEN_WINDOW_DAYS -> OPEN
    return "open", (f"publicado ha {days_since}d (<={OPEN_WINDOW_DAYS}d) sem encerramento -> open (inferido)")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_canonical_status(
    status_fonte: str | None = None,
    source: str = "unknown",
    data_abertura: datetime | None = None,
    data_encerramento: datetime | None = None,
    data_publicacao: datetime | None = None,
    modalidade: str | None = None,
) -> tuple[str, str]:
    """Compute canonical status with explanation.

    Strategy:
    1. If source has explicit status -> map via source-specific table
    2. If no source status but has data_encerramento -> use temporal evidence
    3. If no source status and NO data_encerramento -> use heuristic inference
    4. Fallback -> "unknown"

    Heuristic inference (step 3) considers:
    - Publication age
    - Modality (pregão closes fast, dispensa has no formal closing date)
    - Source (mides_bigquery historical data)
    - Opening date

    Args:
        status_fonte: Raw status string from source.
        source: Source name (pncp, dom_sc, etc.).
        data_abertura: Opening/session date.
        data_encerramento: Closing/deadline date.
        data_publicacao: Publication date.
        modalidade: Modality name for heuristic inference.

    Returns:
        (status_canonico, motivo) tuple.
    """
    # Step 1: Map source-specific status
    if status_fonte:
        cleaned = status_fonte.strip().lower()

        if source == "pncp":
            mapped = _PNCP_STATUS_MAP.get(cleaned)
            if mapped:
                return mapped, f"PNCP situacao_compra='{status_fonte}' -> {mapped}"

        if source == "dom_sc":
            mapped = _DOM_SC_STATUS_MAP.get(cleaned)
            if mapped:
                return mapped, f"DOM-SC status='{status_fonte}' -> {mapped}"

        # Generic mapping
        mapped = _GENERIC_STATUS_MAP.get(cleaned)
        if mapped:
            return mapped, f"status_fonte='{status_fonte}' -> {mapped} (generic map)"

    # Step 2: Temporal evidence from data_encerramento
    now = datetime.now(UTC)

    if data_encerramento is not None:
        if data_abertura is not None:
            if data_encerramento > now and data_abertura <= now:
                return "open", (
                    f"data_encerramento ({data_encerramento.date()}) no futuro + "
                    f"data_abertura ({data_abertura.date()}) no passado -> open"
                )
            if data_encerramento <= now:
                return "closed", (f"data_encerramento ({data_encerramento.date()}) no passado -> closed")
            if data_abertura > now:
                return "upcoming", (f"data_abertura ({data_abertura.date()}) no futuro -> upcoming")

        # No data_abertura but has data_encerramento
        if data_encerramento > now:
            return "open", (f"data_encerramento ({data_encerramento.date()}) no futuro (sem data_abertura) -> open")
        if data_encerramento <= now:
            return "closed", (f"data_encerramento ({data_encerramento.date()}) no passado -> closed")

    # Step 3: No data_encerramento — use heuristic inference
    if data_publicacao or data_abertura:
        return infer_status_from_dates(
            data_publicacao=data_publicacao,
            data_abertura=data_abertura,
            modalidade=modalidade,
            source=source,
            status_fonte=status_fonte,
        )

    # Step 4: Fallback
    return "unknown", "sem status_fonte, sem data_encerramento e sem data_publicacao -> unknown"


def is_active_status(status: str) -> bool:
    """Check if status represents an active (non-terminal) state."""
    return status in ("open", "upcoming", "suspended")


def is_terminal_status(status: str) -> bool:
    """Check if status is terminal (won't change)."""
    return status in ("closed", "revoked", "annulled", "failed")


def needs_review(status: str) -> bool:
    """Check if status requires human review."""
    return status in ("unknown", "suspended")


def infer_bid_status_sql() -> str:
    """Return a SQL CASE expression that implements infer_status_from_dates in SQL.

    This can be used directly in queries against pncp_raw_bids to compute
    inferred status without fetching all records into Python.

    Returns:
        SQL CASE expression string.
    """
    return f"""
    CASE
        -- Priority 1: Source-specific status mapping
        WHEN LOWER(TRIM(COALESCE(situacao_compra, ''))) IN ('recebendo proposta', 'aberta', 'em andamento', 'em analise')
             THEN 'open'
        WHEN LOWER(TRIM(COALESCE(situacao_compra, ''))) IN ('agendada', 'divulgada')
             THEN 'upcoming'
        WHEN LOWER(TRIM(COALESCE(situacao_compra, ''))) IN ('encerrada', 'concluída', 'concluida', 'homologada', 'adjudicada')
             THEN 'closed'
        WHEN LOWER(TRIM(COALESCE(situacao_compra, ''))) IN ('suspensa', 'suspenso')
             THEN 'suspended'
        WHEN LOWER(TRIM(COALESCE(situacao_compra, ''))) IN ('revogada', 'revogado', 'cancelada', 'cancelado')
             THEN 'revoked'
        WHEN LOWER(TRIM(COALESCE(situacao_compra, ''))) IN ('anulada', 'anulado')
             THEN 'annulled'
        WHEN LOWER(TRIM(COALESCE(situacao_compra, ''))) IN ('deserta', 'deserto', 'fracassada', 'fracassado', 'frustrada', 'frustrado')
             THEN 'failed'

        -- Priority 2: data_encerramento based
        WHEN data_encerramento IS NOT NULL AND data_encerramento >= CURRENT_DATE
             THEN 'open'
        WHEN data_encerramento IS NOT NULL AND data_encerramento < CURRENT_DATE
             THEN 'closed'

        -- Priority 3: data_encerramento IS NULL — heuristic inference

        -- Published > 365d ago -> closed
        WHEN data_publicacao IS NOT NULL AND data_publicacao < CURRENT_DATE - INTERVAL '{CLOSED_WINDOW_DAYS} days'
             THEN 'closed'

        -- Published > 90d ago + pregao -> closed
        WHEN data_publicacao IS NOT NULL AND data_publicacao < CURRENT_DATE - INTERVAL '{OPEN_WINDOW_DAYS} days'
             AND LOWER(TRIM(COALESCE(modalidade_nome, ''))) LIKE '%%pregao%%'
             THEN 'closed'

        -- Published > 90d ago + open modality -> open
        WHEN data_publicacao IS NOT NULL AND data_publicacao < CURRENT_DATE - INTERVAL '{OPEN_WINDOW_DAYS} days'
             AND LOWER(TRIM(COALESCE(modalidade_nome, ''))) IN ('dispensa', 'inexigibilidade', 'credenciamento', 'adesao', 'chamamento publico', 'chamada publica')
             THEN 'open'

        -- Published > 90d ago (but <=365d) -> unknown
        WHEN data_publicacao IS NOT NULL AND data_publicacao < CURRENT_DATE - INTERVAL '{OPEN_WINDOW_DAYS} days'
             THEN 'unknown'

        -- Published <= 90d ago -> open (within typical window)
        WHEN data_publicacao IS NOT NULL
             THEN 'open'

        -- data_abertura in future -> upcoming
        WHEN data_abertura IS NOT NULL AND data_abertura > CURRENT_DATE
             THEN 'upcoming'

        -- data_abertura in past -> unknown
        WHEN data_abertura IS NOT NULL AND data_abertura <= CURRENT_DATE
             THEN 'unknown'

        -- Nothing at all
        ELSE 'unknown'
    END
    """
