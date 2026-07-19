"""Decision Engine V2 — multi-dimension explainable triage (EXTRA-DECISION-LOOP-01).

Internal ranking remains GO/REVIEW/NO_GO; external recommendation maps to
PARTICIPAR / REVIEW / NÃO_PARTICIPAR. Hard blockers are never score-compensated.
Stale/unknown/partial/unconfirmed data never produce PARTICIPAR.
Incomplete material profile → REVIEW (not auto NÃO_PARTICIPAR).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from scripts.opportunity_intel.ranking import compute_ranking, load_extra_profile

RECOMMENDATION_MAP = {
    "GO": "PARTICIPAR",
    "REVIEW": "REVIEW",
    "NO_GO": "NÃO_PARTICIPAR",
}
INTERNAL_FROM_EXTERNAL = {
    "PARTICIPAR": "GO",
    "REVIEW": "REVIEW",
    "NÃO_PARTICIPAR": "NO_GO",
    "NAO_PARTICIPAR": "NO_GO",
}

DISCLAIMER = (
    "Recomendação de triagem — não é garantia de vitória nem substitui "
    "análise jurídica, contábil ou técnica final."
)


@dataclass
class DimensionScore:
    name: str
    score: int  # 0–100
    label: str
    notes: list[str] = field(default_factory=list)


@dataclass
class DecisionV2:
    recommendation: str  # PARTICIPAR | REVIEW | NÃO_PARTICIPAR
    internal_ranking: str  # GO | REVIEW | NO_GO
    confidence: str  # HIGH | MEDIUM | LOW
    dimensions: dict[str, DimensionScore]
    hard_blockers: list[str]
    missing_information: list[str]
    positive_factors: list[str]
    risks: list[str]
    conditions_to_change: list[str]
    official_evidence: list[dict[str, Any]]
    profile_id: str | None
    profile_version: int | None
    profile_hash: str | None
    freshness: str
    data_semantics: dict[str, Any]
    alerts: list[str]
    ranking_score: int
    rules: list[str]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["dimensions"] = {
            k: asdict(v) if isinstance(v, DimensionScore) else v
            for k, v in self.dimensions.items()
        }
        return d


def map_internal_to_external(ranking: str) -> str:
    return RECOMMENDATION_MAP.get(ranking, "REVIEW")


def map_external_to_internal(rec: str) -> str:
    key = (rec or "").strip().upper().replace(" ", "_")
    if key in {"NAO_PARTICIPAR", "NAO-PARTICIPAR", "NÃO-PARTICIPAR"}:
        key = "NÃO_PARTICIPAR"
    return INTERNAL_FROM_EXTERNAL.get(key, "REVIEW")


def _clamp(n: int) -> int:
    return max(0, min(100, int(n)))


def _as_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def decide_opportunity(
    row: dict[str, Any],
    *,
    profile: dict[str, Any] | None = None,
    profile_meta: dict[str, Any] | None = None,
    reconfirm: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> DecisionV2:
    """Produce Decision V2 for one opportunity row."""
    now = now or datetime.now(UTC)
    prof = profile if profile is not None else load_extra_profile()
    meta = profile_meta or {}
    reconfirm = reconfirm or {}

    status = str(row.get("status_canonico") or row.get("status") or "unknown")
    data_abertura = _as_dt(row.get("data_abertura"))
    data_encerramento = _as_dt(row.get("data_encerramento"))
    data_publicacao = _as_dt(row.get("data_publicacao"))
    valor = row.get("valor_estimado")
    try:
        valor_f = float(valor) if valor is not None else None
    except (TypeError, ValueError):
        valor_f = None

    base = compute_ranking(
        status_canonico=status,
        orgao_cnpj=row.get("orgao_cnpj"),
        objeto=row.get("objeto"),
        valor_estimado=valor_f,
        modalidade=row.get("modalidade"),
        data_abertura=data_abertura,
        data_encerramento=data_encerramento,
        data_publicacao=data_publicacao,
        uf=row.get("uf"),
        municipio=row.get("municipio"),
        link_edital=row.get("link_edital") or row.get("source_url"),
        link_anexos=row.get("link_anexos") if isinstance(row.get("link_anexos"), list) else None,
        has_match_entity=bool(row.get("has_match_entity") or row.get("orgao_cnpj")),
        dentro_raio=bool(row.get("dentro_raio", True)),
        fonte_confiavel=bool(row.get("fonte_confiavel", True)),
        profile=prof if isinstance(prof, dict) else None,
        demote_go_if_profile_incomplete=True,
    )

    hard_blockers: list[str] = list(base.get("ranking_fatores", {}).get("bloqueadores") or [])
    positive = list(base.get("ranking_fatores", {}).get("positivos") or [])
    negative = list(base.get("ranking_fatores", {}).get("negativos") or [])
    rules = list(base.get("ranking_regras") or [])
    missing: list[str] = list(base.get("profile_missing") or [])

    # --- multi dimensions ---
    data_conf_notes: list[str] = []
    data_conf = 50
    if status == "open":
        data_conf += 20
        data_conf_notes.append("status_open")
    elif status == "upcoming":
        data_conf += 10
        data_conf_notes.append("status_upcoming")
    elif status in {"unknown", "partial"}:
        data_conf -= 25
        data_conf_notes.append(f"status_{status}")
    if row.get("link_edital") or row.get("source_url"):
        data_conf += 10
        data_conf_notes.append("official_url")
    else:
        missing.append("link_edital")
    if valor_f is not None:
        data_conf += 5
    else:
        missing.append("valor_estimado")
        data_conf -= 5
    if data_encerramento:
        data_conf += 5
    else:
        missing.append("data_encerramento")

    reconfirm_status = str(reconfirm.get("status") or reconfirm.get("outcome") or "not_attempted")
    freshness = str(
        reconfirm.get("freshness")
        or row.get("freshness")
        or ("reconfirmed" if reconfirm_status == "ok" else "unconfirmed")
    )
    if reconfirm_status == "ok":
        data_conf += 15
        data_conf_notes.append("official_reconfirm_ok")
    elif reconfirm_status in {"stale", "timeout", "http_429", "http_5xx", "error"}:
        data_conf -= 20
        data_conf_notes.append(f"reconfirm_{reconfirm_status}")
        freshness = reconfirm_status
    elif reconfirm_status == "http_204":
        data_conf -= 10
        data_conf_notes.append("reconfirm_http_204_empty")
        freshness = "http_204"
    elif reconfirm_status == "http_403":
        data_conf -= 15
        data_conf_notes.append("reconfirm_http_403")
        freshness = "http_403"
    else:
        data_conf_notes.append("no_official_reconfirm")
        if freshness in {"", "unconfirmed"}:
            freshness = "unconfirmed"

    # client / technical / commercial / operational / temporal
    client_fit = 50
    client_notes: list[str] = []
    objeto = str(row.get("objeto") or "").lower()
    terms: list[str] = []
    if isinstance(prof, dict):
        for ot in prof.get("desired_object_types") or []:
            if isinstance(ot, dict):
                terms.extend(str(t).lower() for t in (ot.get("terms") or []))
        terms.extend(str(t).lower() for t in (prof.get("positive_terms") or []))
    hits = [t for t in terms if t and t in objeto]
    if hits:
        client_fit += min(30, 10 * len(hits))
        client_notes.append(f"termos_aderentes:{len(hits)}")
    else:
        client_fit -= 10
        client_notes.append("objeto_sem_match_direto")

    technical = client_fit  # engineering object fit proxy
    technical_notes = list(client_notes)

    commercial = 50
    commercial_notes: list[str] = []
    band = (prof or {}).get("value_band_soft") if isinstance(prof, dict) else None
    if isinstance(band, dict) and valor_f is not None:
        lo = band.get("min_brl")
        hi = band.get("max_brl")
        if lo is not None and valor_f < float(lo):
            commercial -= 15
            commercial_notes.append("abaixo_faixa_soft")
        elif hi is not None and valor_f > float(hi):
            commercial -= 15
            commercial_notes.append("acima_faixa_soft")
        else:
            commercial += 15
            commercial_notes.append("dentro_faixa_soft")
    pending_cap = meta.get("pending_critical") or []
    if pending_cap:
        commercial -= 10
        commercial_notes.append("perfil_comercial_pendente")
        for k in pending_cap:
            if k not in missing:
                missing.append(str(k))

    operational = 55
    operational_notes: list[str] = []
    if row.get("dentro_raio", True):
        operational += 15
        operational_notes.append("dentro_raio")
    else:
        operational -= 30
        operational_notes.append("fora_raio")
        hard_blockers.append("fora_raio_200km")

    temporal = 50
    temporal_notes: list[str] = []
    if data_encerramento and data_encerramento > now:
        days = (data_encerramento - now).days
        if days >= 7:
            temporal += 20
            temporal_notes.append(f"prazo_{days}d")
        elif days >= 2:
            temporal += 5
            temporal_notes.append(f"prazo_curto_{days}d")
        else:
            temporal -= 10
            temporal_notes.append("prazo_urgente")
    elif data_encerramento and data_encerramento <= now and status != "open":
        hard_blockers.append("prazo_encerrado")
        temporal = 0
        temporal_notes.append("encerrado")

    dims = {
        "data_confidence": DimensionScore("data_confidence", _clamp(data_conf), "confiança dos dados", data_conf_notes),
        "client_fit": DimensionScore("client_fit", _clamp(client_fit), "aderência ao cliente", client_notes),
        "technical_fit": DimensionScore("technical_fit", _clamp(technical), "fit técnico", technical_notes),
        "commercial_fit": DimensionScore("commercial_fit", _clamp(commercial), "fit comercial", commercial_notes),
        "operational_fit": DimensionScore("operational_fit", _clamp(operational), "fit operacional", operational_notes),
        "temporal_fit": DimensionScore("temporal_fit", _clamp(temporal), "fit temporal", temporal_notes),
    }

    internal = str(base.get("ranking") or "NO_GO")
    confidence = str(base.get("ranking_confianca") or "LOW")
    score = int(base.get("ranking_score") or 0)

    # --- hard policy overrides (never score-compensated) ---
    if hard_blockers:
        internal = "NO_GO"
        confidence = "HIGH"
        rules.append("POLICY:hard_blocker_forces_NO_GO")

    # stale / unknown / partial / unconfirmed never PARTICIPAR
    if internal == "GO":
        if status in {"unknown", "partial", "closed", "revoked", "annulled", "failed", "suspended"}:
            internal = "REVIEW"
            confidence = "LOW"
            rules.append("POLICY:status_blocks_PARTICIPAR")
            negative.append(f"Status {status} impede PARTICIPAR")
        if freshness in {
            "stale",
            "unconfirmed",
            "unknown",
            "partial",
            "timeout",
            "http_429",
            "http_5xx",
            "http_403",
            "error",
            "not_attempted",
        }:
            internal = "REVIEW"
            confidence = "LOW"
            rules.append("POLICY:unconfirmed_or_stale_blocks_PARTICIPAR")
            negative.append(f"Freshness/reconfirmação={freshness} impede PARTICIPAR")
        if reconfirm_status not in {"ok", "skipped_offline_fixture"}:
            # only allow PARTICIPAR with explicit ok reconfirm (or test fixture skip)
            if reconfirm_status != "skipped_offline_fixture":
                internal = "REVIEW"
                confidence = "LOW"
                rules.append("POLICY:requires_official_reconfirm_for_PARTICIPAR")
                negative.append("Sem reconfirmação oficial ok — PARTICIPAR bloqueado")

    # incomplete material profile → REVIEW (already in compute_ranking for GO)
    if pending_cap and internal == "GO":
        internal = "REVIEW"
        confidence = "LOW"
        rules.append("POLICY:pending_profile_to_REVIEW")

    # closed/encerrado out of active snapshot should be NÃO_PARTICIPAR
    if status in {"closed", "revoked", "annulled", "failed"}:
        internal = "NO_GO"
        hard_blockers.append(f"status_{status}")

    recommendation = map_internal_to_external(internal)

    conditions: list[str] = []
    if recommendation != "PARTICIPAR":
        if "link_edital" in missing:
            conditions.append("Disponibilizar link oficial do edital e reconfirmar status")
        if pending_cap:
            conditions.append(
                "Completar campos críticos do perfil Extra: " + ", ".join(pending_cap[:6])
            )
        if freshness != "reconfirmed" and reconfirm_status != "ok":
            conditions.append("Reconfirmar status em fonte oficial com resposta ok")
        if "valor_estimado" in missing:
            conditions.append("Obter valor estimado ou declarar NOT_APPLICABLE com motivo")
    if recommendation == "PARTICIPAR":
        conditions.append("Validação humana de habilitação e margem antes de protocolar")

    evidence: list[dict[str, Any]] = []
    if reconfirm:
        evidence.append(
            {
                "kind": "official_reconfirm",
                "source": reconfirm.get("source") or row.get("source") or "pncp",
                "url": reconfirm.get("url") or row.get("link_edital"),
                "timestamp": reconfirm.get("timestamp"),
                "status_observed": reconfirm.get("status_observed") or reconfirm.get("status"),
                "http_status": reconfirm.get("http_status"),
                "outcome": reconfirm_status,
            }
        )
    if row.get("link_edital") or row.get("source_url"):
        evidence.append(
            {
                "kind": "source_url",
                "url": row.get("link_edital") or row.get("source_url"),
                "source": row.get("source"),
            }
        )

    alerts = [
        DISCLAIMER,
        "Scores e dimensões não são probabilidade de vitória.",
        "valor_estimado ≠ valor homologado ≠ valor pago.",
    ]
    if pending_cap:
        alerts.append(f"Perfil incompleto ({len(pending_cap)} críticos) — decisões conservadoras.")

    risks = list(negative)
    if hard_blockers:
        risks.extend(hard_blockers)

    return DecisionV2(
        recommendation=recommendation,
        internal_ranking=internal,
        confidence=confidence,
        dimensions=dims,
        hard_blockers=hard_blockers,
        missing_information=sorted(set(missing)),
        positive_factors=positive,
        risks=risks,
        conditions_to_change=conditions,
        official_evidence=evidence,
        profile_id=meta.get("profile_id") or (prof or {}).get("profile_id") if isinstance(prof, dict) else None,
        profile_version=meta.get("version") or (prof or {}).get("version") if isinstance(prof, dict) else None,
        profile_hash=meta.get("profile_hash"),
        freshness=freshness,
        data_semantics={
            "valor_tipo": row.get("valor_semantica") or "estimado_ou_nao_declarado",
            "valor_nao_e_pago": True,
            "status_canonico": status,
            "reconfirm_outcome": reconfirm_status,
        },
        alerts=alerts,
        ranking_score=score,
        rules=rules,
    )
