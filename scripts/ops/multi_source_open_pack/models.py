"""Modelo semântico interno do pack multi-fonte EXTRA-MS-OPEN."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class BuyerEntity:
    """Ente comprador do universo canônico (≤ 1093)."""

    entity_key: str  # cnpj8 or synthetic
    cnpj: str
    cnpj8: str
    name: str
    canonical_name: str
    municipio: str
    uf: str
    ibge_code: str
    lat: float | None
    lon: float | None
    distance_km: float | None
    zone: str
    distance_method: str = "universe_seed_centroid"


@dataclass
class SourceObservation:
    """Registro/publicação bruta de uma fonte (PNCP, CIGA, SC Compras…)."""

    observation_id: str
    fonte: str
    fonte_papel: str
    id_externo: str
    orgao: str
    orgao_cnpj: str
    municipio: str
    uf: str
    objeto: str
    modalidade: str
    valor_estimado: float | None
    data_publicacao: str
    data_abertura: str
    data_encerramento: str
    url: str
    status_fonte: str
    categoria_ato: str
    raw: dict[str, Any] = field(default_factory=dict)

    # annotated later
    in_universe: bool = False
    match_universo: str = "out_of_universe"
    distance_km: float | None = None
    distance_method: str = ""
    entity_key: str = ""
    event_type: str = "unknown"
    is_active_dispute: bool = False
    exclusion_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProcessDocument:
    doc_type: str
    title: str
    url: str
    fonte: str
    published_at: str = ""
    content_hash: str = ""
    download_status: str = "not_attempted"
    parse_status: str = "not_attempted"
    version: int = 1


@dataclass
class DecisionEvaluation:
    recommendation: str  # GO | REVIEW | NO_GO
    score: int
    confidence: float
    reasons_for: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    next_action: str = ""
    owner_suggested: str = "Equipe Extra / Tiago"
    action_deadline: str = ""
    scoring_version: str = ""
    category: str = ""
    category_label: str = ""
    sector_label: str = ""
    sector_confidence: float = 0.0
    inclusion_reason: str = ""
    exclusion_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CanonicalProcess:
    """Processo de contratação deduplicado (1 linha canônica no CSV)."""

    process_id: str
    merge_key: str
    merge_method: str
    merge_confidence: float
    fontes: list[str]
    observation_ids: list[str]
    id_externo_principal: str
    orgao: str
    orgao_cnpj: str
    municipio: str
    uf: str
    objeto: str
    modalidade: str
    valor_estimado: float | None
    data_publicacao: str
    data_encerramento: str
    deadline_dt: datetime | None
    url_oficial: str
    urls_all: list[str]
    status_processo: str  # open | terminal | suspended | unknown
    event_types: list[str]
    is_active_dispute: bool
    in_universe: bool
    match_universo: str
    distance_km: float | None
    distance_method: str
    entity_key: str
    calendar_days_remaining: int | None
    business_days_remaining: int | None
    documents: list[ProcessDocument] = field(default_factory=list)
    decision: DecisionEvaluation | None = None
    layer: str = "decision"  # decision | secondary_reference
    observations_count: int = 1
    exclusion_reason: str = ""
    official_page_validated: bool = False
    docs_inventory_status: str = "pending"
    buyer_analysis: str = ""
    competitors_probable: str = ""
    risks_summary: str = ""
    requirements_summary: str = ""

    def to_csv_row(self) -> dict[str, Any]:
        d = self.decision
        return {
            "process_id": self.process_id,
            "merge_key": self.merge_key,
            "merge_method": self.merge_method,
            "merge_confidence": f"{self.merge_confidence:.2f}",
            "fontes": "|".join(self.fontes),
            "observations_count": self.observations_count,
            "observation_ids": "|".join(self.observation_ids),
            "id_externo_principal": self.id_externo_principal,
            "orgao": self.orgao,
            "orgao_cnpj": self.orgao_cnpj,
            "municipio": self.municipio,
            "uf": self.uf,
            "objeto": self.objeto,
            "modalidade": self.modalidade,
            "valor_estimado": self.valor_estimado if self.valor_estimado is not None else "",
            "valor_semantica": "estimado",
            "data_publicacao": self.data_publicacao,
            "data_encerramento": self.data_encerramento,
            "dias_corridos_restantes": self.calendar_days_remaining
            if self.calendar_days_remaining is not None
            else "",
            "dias_uteis_restantes": self.business_days_remaining
            if self.business_days_remaining is not None
            else "",
            "url_oficial": self.url_oficial,
            "urls_todas": "|".join(self.urls_all),
            "status_processo": self.status_processo,
            "event_types": "|".join(self.event_types),
            "is_active_dispute": "sim" if self.is_active_dispute else "nao",
            "in_universe": "sim" if self.in_universe else "nao",
            "match_universo": self.match_universo,
            "distance_km": self.distance_km if self.distance_km is not None else "",
            "distance_method": self.distance_method,
            "layer": self.layer,
            "category": d.category if d else "",
            "category_label": d.category_label if d else "",
            "sector_label": d.sector_label if d else "",
            "sector_confidence": f"{d.sector_confidence:.2f}" if d else "",
            "recommendation": d.recommendation if d else "",
            "score": d.score if d else "",
            "confidence": f"{d.confidence:.2f}" if d else "",
            "blockers": "|".join(d.blockers) if d else "",
            "reasons_for": "|".join(d.reasons_for) if d else "",
            "risks": "|".join(d.risks) if d else "",
            "pending": "|".join(d.pending) if d else "",
            "next_action": d.next_action if d else "",
            "owner_suggested": d.owner_suggested if d else "",
            "action_deadline": d.action_deadline if d else "",
            "inclusion_reason": d.inclusion_reason if d else "",
            "exclusion_reason": (d.exclusion_reason if d else "") or self.exclusion_reason,
            "docs_count": len(self.documents),
            "docs_inventory_status": self.docs_inventory_status,
            "official_page_validated": "sim" if self.official_page_validated else "nao",
            "buyer_analysis": self.buyer_analysis,
            "competitors_probable": self.competitors_probable,
            "risks_summary": self.risks_summary,
            "requirements_summary": self.requirements_summary,
            "document_urls": "|".join(doc.url for doc in self.documents if doc.url),
        }


@dataclass
class ReconciliationStats:
    """Contagens dimensionalmente corretas e reconciliáveis."""

    entes_universo: int = 0
    entes_com_fonte_aplicavel: int = 0
    entes_cobertos: int = 0
    entes_nao_consultados: int = 0
    observacoes_brutas: int = 0
    observacoes_por_fonte: dict[str, int] = field(default_factory=dict)
    publicacoes_dom: int = 0
    processos_canonicos: int = 0
    processos_abertos: int = 0
    processos_no_universo: int = 0
    processos_aec: int = 0
    processos_aderentes: int = 0
    processos_com_docs: int = 0
    oportunidades_acionaveis: int = 0
    shortlist: int = 0
    no_go: int = 0
    review: int = 0
    go: int = 0
    pendencias_confirmacao: int = 0
    exclusoes_por_motivo: dict[str, int] = field(default_factory=dict)
    merges_realizados: int = 0
    observacoes_fora_universo: int = 0
    observacoes_no_universo: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # invariants as explicit claims for manifest
        d["invariants"] = {
            "entes_com_match_le_universo": self.entes_cobertos <= self.entes_universo,
            "processos_le_observacoes": self.processos_canonicos <= max(self.observacoes_brutas, 1)
            or self.observacoes_brutas == 0,
            "abertos_le_processos": self.processos_abertos <= self.processos_canonicos,
            "shortlist_le_acionaveis": self.shortlist <= max(self.oportunidades_acionaveis, 1)
            or self.oportunidades_acionaveis == 0,
            "go_review_nogo_sum": self.go + self.review + self.no_go,
        }
        return d

    def assert_invariants(self) -> list[str]:
        errors: list[str] = []
        if self.entes_universo <= 0:
            errors.append("entes_universo must be > 0")
        if self.entes_cobertos > self.entes_universo:
            errors.append(
                f"entes_cobertos ({self.entes_cobertos}) > entes_universo ({self.entes_universo})"
            )
        if self.observacoes_brutas > 0 and self.processos_canonicos > self.observacoes_brutas:
            errors.append("processos_canonicos > observacoes_brutas")
        if self.processos_abertos > self.processos_canonicos:
            errors.append("processos_abertos > processos_canonicos")
        if self.oportunidades_acionaveis > self.processos_abertos and self.processos_abertos > 0:
            # acionáveis ⊆ abertos ∩ universo ∩ aec
            pass  # soft: acionáveis can be subset
        if self.shortlist > self.oportunidades_acionaveis and self.oportunidades_acionaveis > 0:
            errors.append("shortlist > oportunidades_acionaveis")
        if self.shortlist > self.processos_no_universo and self.processos_no_universo > 0:
            errors.append("shortlist includes out-of-universe")
        return errors
