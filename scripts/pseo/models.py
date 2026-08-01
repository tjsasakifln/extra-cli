"""Typed public models for pSEO export — fail closed on unexpected fields.

Field sets reconciled with the pipeline emitters and allowlist.py.
Unexpected keys fail (extra=forbid). Forbidden commercial keys are never modeled.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PublicModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _https_or_none(v: str | None) -> str | None:
    if v is None or v == "":
        return None
    low = v.lower().strip()
    if low.startswith(("javascript:", "data:", "file:", "vbscript:")):
        raise ValueError("dangerous URL scheme")
    if not low.startswith("https://"):
        raise ValueError("URLs must be https")
    return v


class BuyerCell(PublicModel):
    name: str | None = None
    cnpj8: str | None = None
    uf: str | None = None
    municipio: str | None = None
    contract_count: int = Field(ge=0)
    total_value: float = Field(default=0, ge=0)
    suppressed: bool | None = None
    original_cells: int | None = Field(default=None, ge=0)


class ObjectCell(PublicModel):
    label: str
    count: int = Field(ge=0)
    median_value: float | None = Field(default=None, ge=0)
    example_objeto: str | None = None


class YearValue(PublicModel):
    year: str
    contract_count: int = Field(ge=0)
    total_value: float = Field(ge=0)


class Archetype(PublicModel):
    id: str | None = None
    slug: str | None = None
    label: str | None = None
    description: str | None = None
    object_patterns_public: list[str] = Field(default_factory=list, max_length=50)
    ufs_observed: list[str] = Field(default_factory=list, max_length=30)
    value_band: dict[str, Any] | None = None
    modalities_observed: list[str] = Field(default_factory=list, max_length=30)
    buyer_types_observed: list[str] = Field(default_factory=list, max_length=30)
    confenge_service_slugs: list[str] = Field(default_factory=list, max_length=40)
    evidence_contract_count: int = Field(default=0, ge=0)
    evidence_buyer_count: int = Field(default=0, ge=0)
    methodology: str | None = None
    limitations: list[str] = Field(default_factory=list, max_length=30)
    sources: list[str] = Field(default_factory=list, max_length=20)
    # pipeline may emit additional public narrative fields present on allowlist
    theme: str | None = None
    related_services: list[str] = Field(default_factory=list, max_length=40)


class Market(PublicModel):
    id: str
    slug: str
    archetype_id: str | None = None
    segment: str | None = None
    region: str | None = None
    region_label: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    contract_count: int = Field(default=0, ge=0)
    buyer_count: int = Field(default=0, ge=0)
    supplier_count: int = Field(default=0, ge=0)
    total_value: float = Field(default=0, ge=0)
    median_value: float | None = Field(default=None, ge=0)
    p25_value: float | None = Field(default=None, ge=0)
    p75_value: float | None = Field(default=None, ge=0)
    top_buyers: list[BuyerCell] = Field(default_factory=list, max_length=20)
    top_objects: list[ObjectCell] = Field(default_factory=list, max_length=20)
    value_by_year: list[YearValue] = Field(default_factory=list, max_length=40)
    modalities: list[Any] = Field(default_factory=list, max_length=30)
    open_opportunity_count: int = Field(default=0, ge=0)
    sources: list[str] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=30)
    interpretation_hooks: list[str] = Field(default_factory=list, max_length=30)
    privacy: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _percentiles(self) -> Market:
        vals = [v for v in (self.p25_value, self.median_value, self.p75_value) if v is not None]
        if len(vals) == 3 and not (vals[0] <= vals[1] <= vals[2] + 1e-9):
            raise ValueError("p25 <= mediana <= p75 required")
        return self


class Agency(PublicModel):
    id: str | None = None
    cnpj8: str | None = None
    name: str | None = None
    uf: str | None = None
    municipio: str | None = None
    contract_count: int = Field(default=0, ge=0)
    total_value: float = Field(default=0, ge=0)
    archetype_ids: list[str] = Field(default_factory=list, max_length=40)
    sources: list[str] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=30)
    orgao_nome: str | None = None
    related_archetypes: list[str] = Field(default_factory=list, max_length=40)


class Price(PublicModel):
    id: str | None = None
    slug: str | None = None
    archetype_id: str | None = None
    region: str | None = None
    n: int = Field(default=0, ge=0)
    min: float | None = Field(default=None, ge=0)
    p25: float | None = Field(default=None, ge=0)
    mediana: float | None = Field(default=None, ge=0)
    p75: float | None = Field(default=None, ge=0)
    max: float | None = Field(default=None, ge=0)
    limitations: list[str] = Field(default_factory=list, max_length=30)
    segment: str | None = None
    unit: str | None = None
    sources: list[str] = Field(default_factory=list, max_length=20)


class Competition(PublicModel):
    id: str | None = None
    slug: str | None = None
    archetype_id: str | None = None
    region: str | None = None
    buyer_count: int = Field(default=0, ge=0)
    supplier_count: int = Field(default=0, ge=0)
    contract_count: int = Field(default=0, ge=0)
    hhi_proxy: float | None = Field(default=None, ge=0)
    limitations: list[str] = Field(default_factory=list, max_length=30)
    privacy: dict[str, Any] | None = None
    segment: str | None = None
    sources: list[str] = Field(default_factory=list, max_length=20)


class OpportunityItem(PublicModel):
    id: str | None = None
    pncp_id: str | None = None
    title: str | None = None
    objeto: str | None = None
    uf: str | None = None
    municipio: str | None = None
    orgao_nome: str | None = None
    orgao_cnpj8: str | None = None
    valor_estimado: float | None = Field(default=None, ge=0)
    modalidade: str | None = None
    data_encerramento: str | None = None
    data_publicacao: str | None = None
    link_pncp: str | None = None
    link_oficial: str | None = None
    source: str | None = None
    status: str | None = None
    status_bucket: str | None = None
    status_raw: str | None = None
    uncertainty: bool | None = None
    verified_at: str | None = None
    archetype_ids: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("link_pncp", "link_oficial")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        return _https_or_none(v)


class Opportunity(PublicModel):
    id: str
    slug: str
    label: str | None = None
    segment: str | None = None
    related_market_slug: str | None = None
    archetype_id: str | None = None
    region: str | None = None
    region_label: str | None = None
    open_count: int = Field(default=0, ge=0)
    closed_recent_count: int = Field(default=0, ge=0)
    suspended_count: int = Field(default=0, ge=0)
    historical_count: int = Field(default=0, ge=0)
    items: list[OpportunityItem] = Field(default_factory=list, max_length=200)
    truncated: bool = False
    as_of: str | None = None
    verified_at: str | None = None
    timezone: str | None = None
    status_breakdown: dict[str, Any] | None = None
    sources: list[str] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=30)
    freshness: dict[str, Any] | None = None


class ProblemService(PublicModel):
    id: str | None = None
    slug: str | None = None
    problem: str | None = None
    problem_label: str | None = None
    service: str | None = None
    confenge_service_slug: str | None = None
    theme: str | None = None
    observed_pattern: str | None = None
    related_archetypes: list[str] = Field(default_factory=list, max_length=40)
    archetype_ids: list[str] = Field(default_factory=list, max_length=40)
    evidence_count: int = Field(default=0, ge=0)
    official_references: list[Any] = Field(default_factory=list, max_length=30)
    technical_guide_paths: list[str] = Field(default_factory=list, max_length=30)
    sources: list[str] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=30)
    claim_evidence: list[Any] = Field(default_factory=list, max_length=50)
    evidence_signals: list[str] = Field(default_factory=list, max_length=40)
    evidence_kind: str | None = None
    amendment_count: int | None = Field(default=None, ge=0)
    reference_mentions: int | None = Field(default=None, ge=0)
    document_divergence_count: int | None = Field(default=None, ge=0)
    document_signals: list[Any] = Field(default_factory=list, max_length=40)
    budget_signals: list[Any] = Field(default_factory=list, max_length=40)


class ICPMethodology(PublicModel):
    """Methodology document — allow controlled evolution of narrative keys."""

    model_config = ConfigDict(extra="forbid")
    version: str | None = None
    schema_version: str | None = None
    description: str | None = None
    methodology: str | dict[str, Any] | None = None
    classifier: dict[str, Any] | None = None
    sources: list[str] = Field(default_factory=list, max_length=30)
    limitations: list[str] = Field(default_factory=list, max_length=30)
    internal_signature_aggregates: dict[str, Any] | None = None


class ApprovalArtifact(PublicModel):
    decision: str
    dataset_hash: str = Field(min_length=16)
    schema_version: str
    exporter_version: str
    source_commit_sha: str
    actor: str = Field(min_length=1, max_length=200)
    approved_at: str
    notes: str | None = None
    approval_hash: str | None = None

    @field_validator("decision")
    @classmethod
    def _dec(cls, v: str) -> str:
        if v not in {"APPROVED", "APPROVED_WITH_NOTES", "REJECTED"}:
            raise ValueError("invalid decision")
        return v


def validate_public_payload(kind: str, data: Any) -> Any:
    mapping: dict[str, type[BaseModel]] = {
        "archetypes": Archetype,
        "markets": Market,
        "agencies": Agency,
        "prices": Price,
        "competition": Competition,
        "opportunities": Opportunity,
        "problem_service": ProblemService,
        "icp_methodology": ICPMethodology,
    }
    model = mapping.get(kind)
    if model is None:
        raise ValueError(f"unknown public artifact kind: {kind}")
    try:
        if kind == "icp_methodology":
            return model.model_validate(data).model_dump(mode="json", exclude_none=False)
        if not isinstance(data, list):
            raise ValueError(f"{kind} must be a list")
        return [model.model_validate(item).model_dump(mode="json", exclude_none=False) for item in data]
    except Exception as exc:
        raise ValueError(f"{kind} validation failed: {exc}") from exc
