"""Fail-closed official-status gate for report opportunity shortlists.

The scoring pipeline may nominate an opportunity, but only a fresh observation
from the publishing source can make it actionable.  This module deliberately
does not perform HTTP itself: callers provide a source-specific fetcher and the
gate applies the same decision contract to every source.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

REPORT_TIMEZONE = ZoneInfo("America/Sao_Paulo")
SHORTLIST_RECOMMENDATIONS = frozenset({"PARTICIPAR", "AVALIAR COM CAUTELA"})

_TERMINAL_STATUS_PARTS = (
    "adjudic",
    "anulad",
    "cancelad",
    "desert",
    "encerrad",
    "finalizad",
    "fracassad",
    "homolog",
    "revogad",
)
_OPEN_STATUS_PARTS = (
    "abert",
    "divulgad",
    "publicad",
    "recebendo proposta",
    "proposta em recebimento",
)


OfficialFetcher = Callable[[dict[str, Any]], Mapping[str, Any]]


def _plain(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "".join(
        character
        for character in unicodedata.normalize("NFD", text)
        if unicodedata.category(character) != "Mn"
    )


def _parse_official_datetime(value: Any) -> datetime | None:
    """Parse a source timestamp and normalize it to America/Sao_Paulo.

    A date without time is intentionally rejected.  The acceptance contract is
    about the proposal deadline instant, not merely its calendar day.
    """

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and "T" in value:
        candidate = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=REPORT_TIMEZONE)
    return parsed.astimezone(REPORT_TIMEZONE)


def _reference(edital: Mapping[str, Any]) -> str:
    return str(
        edital.get("numero_controle")
        or edital.get("codigo_licitacao")
        or edital.get("sequencial_compra")
        or edital.get("link")
        or "oportunidade_sem_identificador"
    )


def _block(
    edital: dict[str, Any],
    *,
    checked_at: str,
    decision: str,
    source: str,
    blocker: str,
    next_action: str,
    status_native: str = "",
    deadline_at: str | None = None,
    evidence_url: str = "",
) -> None:
    original = str(edital.get("recomendacao") or "")
    edital["official_reconfirmation"] = {
        "decision": decision,
        "source": source,
        "status_native": status_native,
        "deadline_at": deadline_at,
        "checked_at": checked_at,
        "timezone": "America/Sao_Paulo",
        "evidence_url": evidence_url,
        "blocker": blocker,
        "next_action": next_action,
        "original_recommendation": original,
    }
    edital["shortlist_eligible"] = False
    edital["recomendacao"] = "NÃO RECOMENDADO"
    edital["justificativa"] = blocker


def reconfirm_shortlist(
    editais: list[dict[str, Any]],
    fetch_official: OfficialFetcher | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Reconfirm every scored shortlist candidate against its official source.

    Failures are isolated per opportunity.  A failed source observation never
    erases another source's successful GO, but the failed candidate itself is
    excluded from every downstream action list.
    """

    instant = now or datetime.now(tz=UTC)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=REPORT_TIMEZONE)
    instant_sp = instant.astimezone(REPORT_TIMEZONE)
    checked_at = instant_sp.isoformat()

    candidates = [
        edital
        for edital in editais
        if str(edital.get("recomendacao") or "").upper() in SHORTLIST_RECOMMENDATIONS
    ]
    counts = {"GO": 0, "REVIEW": 0, "NO_GO": 0}
    source_failures: list[dict[str, str]] = []

    for edital in candidates:
        source = str(edital.get("fonte") or edital.get("_source_name") or "UNKNOWN").upper()
        reference = _reference(edital)
        if fetch_official is None:
            blocker = "Shortlist bloqueada: reconfirmação oficial não foi executada."
            _block(
                edital,
                checked_at=checked_at,
                decision="NO_GO",
                source=source,
                blocker=blocker,
                next_action=f"Consultar a fonte {source} e reconfirmar status e prazo de {reference}.",
            )
            counts["NO_GO"] += 1
            source_failures.append({"source": source, "reference": reference, "blocker": blocker})
            continue

        try:
            observation = dict(fetch_official(edital))
        except Exception as exc:  # the gate must isolate any source adapter failure
            blocker = f"Fonte oficial {source} indisponível na reconfirmação: {type(exc).__name__}."
            _block(
                edital,
                checked_at=checked_at,
                decision="NO_GO",
                source=source,
                blocker=blocker,
                next_action=f"Repetir a consulta oficial de {reference} antes de preparar proposta.",
            )
            counts["NO_GO"] += 1
            source_failures.append({"source": source, "reference": reference, "blocker": blocker})
            continue

        status_native = str(
            observation.get("status_native")
            or observation.get("situacaoCompraNome")
            or observation.get("status")
            or ""
        ).strip()
        deadline = _parse_official_datetime(
            observation.get("deadline_at")
            or observation.get("dataEncerramentoProposta")
            or observation.get("dataHoraFinalPropostas")
        )
        evidence_url = str(observation.get("evidence_url") or observation.get("official_url") or "").strip()
        normalized_status = _plain(status_native)

        if not evidence_url:
            blocker = "Reconfirmação sem URL de evidência oficial."
            decision = "NO_GO"
        elif any(part in normalized_status for part in _TERMINAL_STATUS_PARTS):
            blocker = f"Evento terminal na fonte oficial: {status_native}."
            decision = "NO_GO"
            edital["status_edital"] = "ENCERRADO"
        elif deadline is None:
            blocker = "Prazo oficial ausente ou sem timestamp verificável."
            decision = "REVIEW"
        elif deadline <= instant_sp:
            blocker = f"Prazo oficial vencido em {deadline.isoformat()}."
            decision = "NO_GO"
            edital["status_edital"] = "ENCERRADO"
        elif not any(part in normalized_status for part in _OPEN_STATUS_PARTS):
            blocker = f"Status oficial ambíguo: {status_native or 'não informado'}."
            decision = "REVIEW"
        else:
            original = str(edital.get("recomendacao") or "")
            edital["official_reconfirmation"] = {
                "decision": "GO",
                "source": source,
                "status_native": status_native,
                "deadline_at": deadline.isoformat(),
                "checked_at": checked_at,
                "timezone": "America/Sao_Paulo",
                "evidence_url": evidence_url,
                "blocker": None,
                "next_action": "Monitorar a fonte oficial até o envio da proposta.",
                "original_recommendation": original,
            }
            edital["shortlist_eligible"] = True
            edital["status_edital"] = "ABERTO"
            edital["data_encerramento"] = deadline.isoformat()
            edital["dias_restantes"] = (deadline.date() - instant_sp.date()).days
            counts["GO"] += 1
            continue

        _block(
            edital,
            checked_at=checked_at,
            decision=decision,
            source=source,
            blocker=blocker,
            next_action=f"Validar manualmente {reference} na fonte oficial antes de qualquer ação.",
            status_native=status_native,
            deadline_at=deadline.isoformat() if deadline else None,
            evidence_url=evidence_url,
        )
        counts[decision] += 1

    return {
        "candidate_count": len(candidates),
        "shortlist_count": counts["GO"],
        "blocked_count": counts["REVIEW"] + counts["NO_GO"],
        "decisions": counts,
        "checked_at": checked_at,
        "timezone": "America/Sao_Paulo",
        "all_candidates_reconfirmed": bool(candidates) and counts["GO"] == len(candidates),
        "shortlist_blocked": bool(candidates) and counts["GO"] == 0,
        "source_failures": source_failures,
    }
