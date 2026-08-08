"""Durable commercial funnel status for progressive national processing.

Activation states (WATCH / ACTIONABLE_NOW / …) answer "who deserves attention now".
Funnel / downstream status answers "where is this company in the expensive path"
so round N+1 advances the cursor instead of re-picking the same top-N.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

# Downstream / expensive-stage lifecycle (per company).
DOWNSTREAM_PENDING = "PENDING"
DOWNSTREAM_SELECTED = "SELECTED"
DOWNSTREAM_INTEL_DONE = "INTEL_DONE"
DOWNSTREAM_CONTACTS_DONE = "CONTACTS_DONE"
DOWNSTREAM_EXPORTED = "EXPORTED"
DOWNSTREAM_FAILED = "FAILED"
DOWNSTREAM_COOLDOWN = "COOLDOWN"
DOWNSTREAM_NO_CONTACT = "NO_CONTACT"
DOWNSTREAM_SKIPPED = "SKIPPED"

DOWNSTREAM_STATUSES = frozenset(
    {
        DOWNSTREAM_PENDING,
        DOWNSTREAM_SELECTED,
        DOWNSTREAM_INTEL_DONE,
        DOWNSTREAM_CONTACTS_DONE,
        DOWNSTREAM_EXPORTED,
        DOWNSTREAM_FAILED,
        DOWNSTREAM_COOLDOWN,
        DOWNSTREAM_NO_CONTACT,
        DOWNSTREAM_SKIPPED,
    }
)

# Already consumed capacity this cycle — skip unless re-eligible.
DOWNSTREAM_CONSUMED = frozenset(
    {
        DOWNSTREAM_SELECTED,
        DOWNSTREAM_INTEL_DONE,
        DOWNSTREAM_CONTACTS_DONE,
        DOWNSTREAM_EXPORTED,
        DOWNSTREAM_NO_CONTACT,
        DOWNSTREAM_COOLDOWN,
    }
)

# Priority bands (order/approach, not permanent exclusion).
BAND_PRIORITARIO = "PRIORITARIO_AGORA"
BAND_PROCESSAR_DEPOIS = "PROCESSAR_DEPOIS"
BAND_ABM = "CONTA_ESTRATEGICA_ABM"
BAND_BAIXA = "BAIXA_PRIORIDADE"
BAND_SEM_CONTATO = "SEM_CONTATO_ATUAL"
BAND_TEMP_INADEQUADO = "TEMPORARIAMENTE_INADEQUADO"
BAND_DNC = "DNC"
BAND_INELIGIVEL = "INELIGIVEL_COM_MOTIVO_OBJETIVO"

# Commercial states that must never re-enter cold outreach.
HARD_BLOCK_COMMERCIAL = frozenset(
    {
        "DO_NOT_CONTACT",
        "DNC",
        "WON",
        "LOST",
        "BLOCKED",
    }
)

# Block automatic parallel cadence (still monitored).
ACTIVE_CADENCE_BLOCK = frozenset(
    {
        "REPLIED",
        "MEETING",
        "PROPOSAL",
        "SENT",
        "ENROLLED",
    }
)


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _parse_iso_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        raw = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def priority_band_for(
    *,
    activation_state: str,
    activation_score: float,
    commercial_state: str,
    downstream_status: str,
    value_total: float = 0.0,
) -> str:
    cs = (commercial_state or "").upper()
    if cs in HARD_BLOCK_COMMERCIAL or cs == "DNC":
        return BAND_DNC
    if downstream_status == DOWNSTREAM_NO_CONTACT:
        return BAND_SEM_CONTATO
    if cs == "NOT_NOW":
        return BAND_TEMP_INADEQUADO
    if activation_state == "SUPPRESSED":
        return BAND_INELIGIVEL
    if activation_state == "ACTIONABLE_NOW" and activation_score >= 50:
        return BAND_PRIORITARIO
    if activation_state in {"ACTIONABLE_NOW", "RESEARCH_REQUIRED"}:
        return BAND_PROCESSAR_DEPOIS
    # Very large portfolio without strong trigger → ABM, not exclusion
    if value_total >= 50_000_000 or activation_score >= 70:
        return BAND_ABM
    if activation_score >= 40:
        return BAND_PROCESSAR_DEPOIS
    return BAND_BAIXA


def is_reeligible(
    prior: dict[str, Any] | None,
    *,
    as_of: date,
    current_source_hash: str | None = None,
    cooldown_days: int = 14,
) -> bool:
    """True when a previously selected company may re-enter the hot set."""
    if not prior:
        return True
    cs = str(prior.get("commercial_state") or prior.get("last_outcome") or "").upper()
    if cs in HARD_BLOCK_COMMERCIAL:
        return False
    if cs in ACTIVE_CADENCE_BLOCK:
        return False

    nba = _parse_iso_date(prior.get("next_eligible_at") or prior.get("next_best_action_at"))
    if nba is not None and nba > as_of:
        return False

    # Material portfolio change reopens the company.
    prior_hash = str(prior.get("source_hash") or "")
    if current_source_hash and prior_hash and current_source_hash != prior_hash:
        return True

    status = str(prior.get("downstream_status") or DOWNSTREAM_PENDING).upper()
    if status not in DOWNSTREAM_CONSUMED:
        return True

    last = _parse_iso_dt(prior.get("last_downstream_at") or prior.get("last_hot_set_at"))
    if last is None:
        return True
    # Cooldown after expensive processing
    cool_until = last.date() + timedelta(days=max(0, int(cooldown_days)))
    return as_of >= cool_until


def apply_commercial_memory(
    row: dict[str, Any],
    memory: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    """Overlay Decision/Outcome commercial memory onto a universe row (copy).

    memory keys: cnpj14 → {commercial_state, next_eligible_at, last_outcome,
    bounced_emails, ...}
    """
    out = dict(row)
    if not memory:
        return out
    cnpj = "".join(ch for ch in str(out.get("cnpj14") or out.get("cnpj") or "") if ch.isdigit())
    if len(cnpj) != 14:
        return out
    mem = memory.get(cnpj)
    if not mem:
        return out
    st = str(mem.get("commercial_state") or mem.get("last_outcome") or "").upper()
    if st:
        out["commercial_state"] = st
        if st in {"DO_NOT_CONTACT", "DNC"}:
            out["outreach_eligibility"] = "DNC"
    if mem.get("next_eligible_at"):
        out["next_eligible_at"] = mem["next_eligible_at"]
    if mem.get("last_outcome"):
        out["last_outcome"] = mem["last_outcome"]
    # Bounced emails invalidate addresses, not the whole company.
    bounced = mem.get("bounced_emails") or mem.get("invalid_emails") or []
    if bounced:
        out["bounced_emails"] = list(bounced)
    return out


def load_commercial_memory_jsonl(path: str | Any) -> dict[str, dict[str, Any]]:
    """Load commercial memory overlay from JSONL (cnpj14 per line)."""
    from pathlib import Path
    import json

    p = Path(path)
    if not p.is_file():
        return {}
    out: dict[str, dict[str, Any]] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        row = json.loads(text)
        cnpj = "".join(ch for ch in str(row.get("cnpj14") or row.get("cnpj") or "") if ch.isdigit())
        if len(cnpj) == 14:
            out[cnpj] = row
    return out


def mark_downstream(
    proj_dict: dict[str, Any],
    *,
    status: str,
    at: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Return updated projection dict with funnel progress."""
    d = dict(proj_dict)
    d["downstream_status"] = status
    stamp = at or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    d["last_downstream_at"] = stamp
    if status == DOWNSTREAM_SELECTED:
        d["last_hot_set_at"] = stamp
        d["processing_attempts"] = int(d.get("processing_attempts") or 0) + 1
    if error:
        d["last_error"] = error[:500]
    return d
