"""Independent data-confidence and Extra-fit scoring for human triage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from scripts.lib.universe import CanonicalEntity, normalize_identity_text
from scripts.opportunity_intel.profile import ClientProfile

TRIAGE_VALUES = ("PRIORITARIA", "REVISAR", "DESCARTAR")
TERMINAL_OR_SUSPENDED = {"closed", "suspended", "revoked", "annulled", "failed"}


@dataclass(frozen=True)
class RadarScores:
    data_confidence_score: int
    client_fit_score: int
    triage_recommendation: str
    category: str | None
    positive_factors: tuple[str, ...]
    negative_factors: tuple[str, ...]
    blockers: tuple[str, ...]
    missing_fields: tuple[str, ...]


def score_opportunity(
    row: dict[str, Any],
    entity: CanonicalEntity,
    profile: ClientProfile,
    status_evidence: str,
    now: datetime | None = None,
    freshness_window_days: int = 45,
) -> RadarScores:
    """Calculate two scores; never emit a definitive participation verdict."""
    now = now or datetime.now(UTC)
    data_weights = profile.weights.get("data_confidence", {})
    fit_weights = profile.weights.get("client_fit", {})
    positive: list[str] = []
    negative: list[str] = []
    blockers: list[str] = []
    missing = _missing_fields(row)

    data_score = 0
    if row.get("source") == "pncp":
        data_score += data_weights.get("official_source", 0)
        positive.append("Fonte oficial PNCP")
    if status_evidence in {"pncp_open_proposals_endpoint", "future_deadline"}:
        data_score += data_weights.get("status_evidence", 0)
        positive.append(f"Status comprovado: {status_evidence}")
    deadline = _as_datetime(row.get("data_encerramento"))
    if deadline is not None and deadline > now:
        data_score += data_weights.get("future_deadline", 0)
        positive.append("Data de encerramento futura")
    official_url = row.get("source_url") or row.get("link_edital")
    if official_url:
        data_score += data_weights.get("official_url", 0)
        positive.append("Link oficial disponível")
    if entity.entity_id:
        data_score += data_weights.get("entity_match", 0)
        positive.append("Correspondência com universo canônico")
    last_seen = _as_datetime(row.get("last_seen_at") or row.get("ingested_at"))
    if last_seen is not None and (now - last_seen).total_seconds() <= freshness_window_days * 86400:
        data_score += data_weights.get("freshness", 0)
        positive.append("Registro dentro da janela de freshness")
    complete_ratio = (7 - len(missing)) / 7
    data_score += round(data_weights.get("field_completeness", 0) * max(0.0, complete_ratio))

    fit_score = 0
    object_text = normalize_identity_text(str(row.get("objeto") or ""))
    category = _match_object_type(object_text, profile)
    if category:
        fit_score += fit_weights.get("desired_object_type", 0)
        positive.append(f"Objeto aderente: {category}")
    else:
        negative.append("Objeto sem correspondência direta com os três tipos priorizados")

    matched_positive_terms = [term for term in profile.positive_terms if normalize_identity_text(term) in object_text]
    if matched_positive_terms:
        fit_score += min(
            fit_weights.get("positive_terms", 0),
            len(matched_positive_terms) * max(1, fit_weights.get("positive_terms", 0) // 3),
        )
        positive.append("Termos positivos: " + ", ".join(matched_positive_terms))

    matched_negative_terms = [term for term in profile.negative_terms if normalize_identity_text(term) in object_text]
    if matched_negative_terms:
        negative.append("Termos negativos: " + ", ".join(matched_negative_terms))
        blockers.append("Objeto contém termo negativo configurado")

    if entity.distancia_km is not None and profile.priority_distance_km is not None:
        distance_ratio = max(0.0, 1.0 - entity.distancia_km / max(profile.priority_distance_km, 1.0))
        fit_score += round(fit_weights.get("distance", 0) * (0.5 + 0.5 * distance_ratio))
        positive.append(f"Distância no raio: {entity.distancia_km:.1f} km")

    modalidade = normalize_identity_text(str(row.get("modalidade") or ""))
    if profile.allowed_modalities is None:
        negative.append("Modalidades admitidas não configuradas; sem bônus ou bloqueio")
    else:
        allowed = {normalize_identity_text(value) for value in profile.allowed_modalities}
        if modalidade in allowed:
            fit_score += fit_weights.get("modality", 0)
            positive.append("Modalidade admitida no perfil")
        else:
            blockers.append("Modalidade fora da lista configurada")

    days_remaining = int((deadline - now).total_seconds() // 86400) if deadline else None
    if profile.minimum_days_to_deadline is None:
        negative.append("Prazo mínimo não configurado; sem bloqueio comercial por urgência")
    elif days_remaining is not None and days_remaining >= profile.minimum_days_to_deadline:
        fit_score += fit_weights.get("deadline", 0)
        positive.append("Prazo atende ao mínimo configurado")
    else:
        blockers.append("Prazo abaixo do mínimo configurado")

    value = _optional_float(row.get("valor_estimado"))
    if profile.minimum_value is not None and (value is None or value < profile.minimum_value):
        blockers.append("Valor abaixo do mínimo configurado")
    if profile.maximum_value is not None and (value is None or value > profile.maximum_value):
        blockers.append("Valor acima do máximo configurado")

    has_notice = bool(official_url)
    has_attachments = bool(row.get("link_anexos"))
    if has_notice:
        fit_score += fit_weights.get("documents", 0) // 2
    if has_attachments:
        fit_score += fit_weights.get("documents", 0) - fit_weights.get("documents", 0) // 2
    if profile.documents.get("require_official_notice") and not has_notice:
        blockers.append("Edital/link oficial exigido e ausente")
    if profile.documents.get("require_attachments") and not has_attachments:
        blockers.append("Anexos exigidos e ausentes")

    status = str(row.get("status_canonico") or "unknown")
    if profile.hard_blocks.get("exclude_terminal_or_suspended") and status in TERMINAL_OR_SUSPENDED:
        blockers.append(f"Status {status} bloqueado")
    if profile.hard_blocks.get("require_future_deadline") and (deadline is None or deadline <= now):
        blockers.append("Encerramento futuro não comprovado")
    if profile.hard_blocks.get("require_within_radius") and entity.within_radius is not True:
        blockers.append("Fora do universo de até 200 km")
    if profile.hard_blocks.get("require_official_url") and not official_url:
        blockers.append("Link oficial obrigatório ausente")

    data_score = _bounded_score(data_score)
    fit_score = _bounded_score(fit_score)
    thresholds = profile.triage_thresholds
    if blockers or fit_score <= thresholds.get("discard_max_client_fit", 20):
        triage = "DESCARTAR"
    elif data_score >= thresholds.get("priority_min_data_confidence", 70) and fit_score >= thresholds.get(
        "priority_min_client_fit", 55
    ):
        triage = "PRIORITARIA"
    else:
        triage = "REVISAR"

    return RadarScores(
        data_confidence_score=data_score,
        client_fit_score=fit_score,
        triage_recommendation=triage,
        category=category,
        positive_factors=tuple(dict.fromkeys(positive)),
        negative_factors=tuple(dict.fromkeys(negative)),
        blockers=tuple(dict.fromkeys(blockers)),
        missing_fields=tuple(missing),
    )


def _match_object_type(object_text: str, profile: ClientProfile) -> str | None:
    for object_type in profile.desired_object_types:
        if any(normalize_identity_text(term) in object_text for term in object_type.terms):
            return object_type.id
    return None


def _missing_fields(row: dict[str, Any]) -> list[str]:
    fields = {
        "identificacao_ente": row.get("orgao_cnpj") or row.get("orgao_nome"),
        "objeto": row.get("objeto"),
        "status": row.get("status_canonico"),
        "data_encerramento": row.get("data_encerramento"),
        "link_oficial": row.get("source_url") or row.get("link_edital"),
        "modalidade": row.get("modalidade"),
        "municipio": row.get("municipio"),
    }
    return [name for name, value in fields.items() if value in (None, "", [])]


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bounded_score(value: int) -> int:
    return min(100, max(0, int(value)))
