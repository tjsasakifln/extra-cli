"""Canonical status calculation for bidding opportunities.

Determines the unified status from source-specific status values
and temporal evidence. Follows fail-closed principle: never mark
"open" solely based on recency.

Status values:
    open       — actively accepting proposals (data_encerramento in future)
    upcoming   — published but not yet accepting proposals
    closed     — deadline passed or explicitly closed
    suspended  — temporarily suspended (source says "suspensa")
    revoked    — cancelled/revoked (source says "revogada")
    annulled   — annulled (source says "anulada")
    failed     — no bidders, deserted, or otherwise failed
    unknown    — insufficient data to determine status

Priority order: source status (most reliable) → temporal evidence
→ conservative default (unknown).
"""

from __future__ import annotations

from datetime import UTC, datetime

# ---------------------------------------------------------------------------
# Status mapping: source-specific → canonical
# ---------------------------------------------------------------------------

# PNCP situacao_compra values → canonical
_PNCP_STATUS_MAP: dict[str, str] = {
    "recebendo proposta": "open",
    "aberta": "open",
    "em andamento": "open",
    "agendada": "upcoming",
    "divulgada": "upcoming",
    "encerrada": "closed",
    "concluída": "closed",
    "homologada": "closed",
    "suspensa": "suspended",
    "revogada": "revoked",
    "anulada": "annulled",
    "cancelada": "revoked",
    "deserta": "failed",
    "fracassada": "failed",
    "em analise": "open",
    "adjudicada": "closed",
}

# DOM-SC status values → canonical
_DOM_SC_STATUS_MAP: dict[str, str] = {
    "publicado": "open",
    "autopublicação nova": "open",
    "autopublicação assinada": "open",
    "autopublicação publicada": "open",
    "acervo público": "unknown",
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
    "concluída": "closed",
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
# Public API
# ---------------------------------------------------------------------------


def compute_canonical_status(
    status_fonte: str | None = None,
    source: str = "unknown",
    data_abertura: datetime | None = None,
    data_encerramento: datetime | None = None,
    data_publicacao: datetime | None = None,
) -> tuple[str, str]:
    """Compute canonical status with explanation.

    Strategy (fail-closed):
    1. If source has explicit status → map via source-specific table
    2. If no source status → use temporal evidence:
       - data_encerramento in future + data_abertura in past → "open"
       - data_abertura in future → "upcoming"
       - data_encerramento in past → "closed"
    3. Fallback → "unknown"

    Args:
        status_fonte: Raw status string from source.
        source: Source name (pncp, dom_sc, etc.).
        data_abertura: Opening/session date.
        data_encerramento: Closing/deadline date.
        data_publicacao: Publication date.

    Returns:
        (status_canonico, motivo) tuple.
    """
    # Step 1: Map source-specific status
    if status_fonte:
        cleaned = status_fonte.strip().lower()

        if source == "pncp":
            mapped = _PNCP_STATUS_MAP.get(cleaned)
            if mapped:
                return mapped, f"PNCP situacao_compra='{status_fonte}' → {mapped}"

        if source == "dom_sc":
            mapped = _DOM_SC_STATUS_MAP.get(cleaned)
            if mapped:
                return mapped, f"DOM-SC status='{status_fonte}' → {mapped}"

        # Generic mapping
        mapped = _GENERIC_STATUS_MAP.get(cleaned)
        if mapped:
            return mapped, f"status_fonte='{status_fonte}' → {mapped} (generic map)"

    # Step 2: Temporal evidence
    now = datetime.now(UTC)

    if data_encerramento and data_abertura:
        if data_encerramento > now and data_abertura <= now:
            return "open", "data_encerramento no futuro + data_abertura no passado → open"
        if data_encerramento <= now:
            return "closed", f"data_encerramento ({data_encerramento.date()}) no passado → closed"
        if data_abertura > now:
            return "upcoming", f"data_abertura ({data_abertura.date()}) no futuro → upcoming"

    if data_encerramento:
        if data_encerramento > now:
            # Has future deadline but no abertura — could be open
            return "open", "data_encerramento no futuro (sem data_abertura) → open (conservador)"
        if data_encerramento <= now:
            return "closed", f"data_encerramento ({data_encerramento.date()}) no passado → closed"

    if data_abertura:
        if data_abertura > now:
            return "upcoming", f"data_abertura ({data_abertura.date()}) no futuro → upcoming"
        # Past abertura without encerramento — ambiguous
        return "unknown", "data_abertura passada sem data_encerramento → unknown"

    if data_publicacao:
        # Recent publication (< 90 days) might still be open
        days_since = (now - data_publicacao).days
        if days_since <= 90:
            return "unknown", f"publicado há {days_since}d (≤90d) — status não confirmado → unknown (fail-closed)"
        return "closed", f"publicado há {days_since}d (>90d) sem status explícito → closed"

    # Step 3: Fallback
    return "unknown", "sem status_fonte e sem datas → unknown"


def is_active_status(status: str) -> bool:
    """Check if status represents an active (non-terminal) state."""
    return status in ("open", "upcoming", "suspended")


def is_terminal_status(status: str) -> bool:
    """Check if status is terminal (won't change)."""
    return status in ("closed", "revoked", "annulled", "failed")


def needs_review(status: str) -> bool:
    """Check if status requires human review."""
    return status in ("unknown", "suspended")
