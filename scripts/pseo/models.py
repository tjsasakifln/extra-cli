"""Typed public models for pSEO export — fail closed on unexpected fields.

Nested models replace free ``dict[str, Any]`` / ``list[Any]`` in the public
schema. Field sets reconciled with pipeline emitters (aggregate, archetypes,
opportunities, comparison, privacy, icp).

Rules:
- ``extra=forbid`` at every level
- no ``Any`` in public schema fields
- validated dates/datetimes; ISO serialization
- slug regex; UF enum (27); CNPJ8 = 8 digits; hex hashes fixed length
- HTTPS-only URLs; official domain allowlist for OfficialReference
- reject javascript:/data:/file:/opaque schemes
- max lengths; finite numbers (reject NaN/Infinity)
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# ---------------------------------------------------------------------------
# Primitives / validators
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_CNPJ8_RE = re.compile(r"^\d{8}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_HEX_SHA_RE = re.compile(r"^[0-9a-f]{7,64}$")

# Official Brazilian public-domain suffixes for OfficialReference URLs
_OFFICIAL_HOST_SUFFIXES: tuple[str, ...] = (
    ".gov.br",
    "gov.br",
    ".planalto.gov.br",
    "planalto.gov.br",
    ".caixa.gov.br",
    "caixa.gov.br",
    ".tcu.gov.br",
    "tcu.gov.br",
    ".bcb.gov.br",
    "bcb.gov.br",
    ".ibge.gov.br",
    "ibge.gov.br",
)

_DANGEROUS_SCHEMES = ("javascript:", "data:", "file:", "vbscript:", "about:")

UF_CODES = (
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
)


class UF(StrEnum):
    """27 unidades federativas do Brasil."""

    AC = "AC"
    AL = "AL"
    AP = "AP"
    AM = "AM"
    BA = "BA"
    CE = "CE"
    DF = "DF"
    ES = "ES"
    GO = "GO"
    MA = "MA"
    MT = "MT"
    MS = "MS"
    MG = "MG"
    PA = "PA"
    PB = "PB"
    PR = "PR"
    PE = "PE"
    PI = "PI"
    RJ = "RJ"
    RN = "RN"
    RS = "RS"
    RO = "RO"
    RR = "RR"
    SC = "SC"
    SP = "SP"
    SE = "SE"
    TO = "TO"


def _finite_number(v: float | None) -> float | None:
    if v is None:
        return None
    if isinstance(v, bool):
        raise ValueError("bool is not a number")
    f = float(v)
    if not math.isfinite(f):
        raise ValueError("number must be finite (reject NaN/Infinity)")
    return f


def _finite_required(v: float) -> float:
    out = _finite_number(v)
    if out is None:
        raise ValueError("number required")
    return out


FiniteFloat = Annotated[float, AfterValidator(_finite_required)]
FiniteFloatOpt = Annotated[float | None, AfterValidator(_finite_number)]


def _https_url(v: str | None, *, official_only: bool = False) -> str | None:
    if v is None or v == "":
        return None
    s = str(v).strip()
    low = s.lower()
    if any(low.startswith(sch) for sch in _DANGEROUS_SCHEMES):
        raise ValueError("dangerous URL scheme")
    # Opaque / scheme-relative / non-http
    if low.startswith("//") or "\\" in s:
        raise ValueError("opaque or unsafe URL form")
    parsed = urlparse(s)
    if parsed.scheme.lower() != "https":
        raise ValueError("URLs must be https")
    if not parsed.netloc:
        raise ValueError("URL missing host")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or host in {".", "localhost"}:
        raise ValueError("invalid URL host")
    # Reject credentials in netloc
    if parsed.username or parsed.password:
        raise ValueError("URL must not embed credentials")
    if official_only:
        if not any(host == suf.lstrip(".") or host.endswith(suf if suf.startswith(".") else f".{suf}")
                   for suf in _OFFICIAL_HOST_SUFFIXES):
            # Also accept exact suffix match helpers
            ok = host.endswith(".gov.br") or host == "gov.br"
            if not ok:
                raise ValueError(f"URL host not on official allowlist: {host}")
    return s


def _https_public(v: str | None) -> str | None:
    return _https_url(v, official_only=False)


def _https_official(v: str | None) -> str | None:
    return _https_url(v, official_only=True)


def _optional_slug(v: str | None) -> str | None:
    if v is None or v == "":
        return None
    s = str(v).strip().lower()
    if not _SLUG_RE.match(s):
        raise ValueError(f"invalid slug: {v!r}")
    if len(s) > 120:
        raise ValueError("slug too long")
    return s


def _required_slug(v: str) -> str:
    out = _optional_slug(v)
    if out is None:
        raise ValueError("slug required")
    return out


def _optional_cnpj8(v: str | None) -> str | None:
    if v is None or v == "":
        return None
    digits = re.sub(r"\D", "", str(v))
    if len(digits) >= 8:
        digits = digits[:8]
    if not _CNPJ8_RE.match(digits):
        raise ValueError("cnpj8 must be exactly 8 digits")
    return digits


def _optional_uf(v: str | None) -> str | None:
    if v is None or v == "":
        return None
    u = str(v).strip().upper()
    if u not in UF_CODES:
        raise ValueError(f"invalid UF: {v!r}")
    return u


def _iso_date_str(v: str | date | datetime | None) -> str | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    # Accept date or datetime ISO prefixes
    if "T" in s:
        s = s.split("T", 1)[0]
    s = s[:10]
    date.fromisoformat(s)  # raises on invalid
    return s


def _iso_datetime_str(v: str | datetime | None) -> str | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        if v.tzinfo is not None:
            return v.isoformat().replace("+00:00", "Z")
        return v.isoformat() + "Z"
    s = str(v).strip()
    # Basic sanity — full parse if possible
    try:
        if s.endswith("Z"):
            datetime.fromisoformat(s.replace("Z", "+00:00"))
        else:
            datetime.fromisoformat(s)
    except ValueError:
        # allow date-only coerced to midnight Z for verified_at style fields
        d = date.fromisoformat(s[:10])
        return d.isoformat()
    return s


TimezoneName = Literal["America/Sao_Paulo", "UTC"]


class PublicModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


# ---------------------------------------------------------------------------
# Nested public models (B2)
# ---------------------------------------------------------------------------


class ValueBand(PublicModel):
    """Percentile band for archetype/market value distributions."""

    p25: FiniteFloatOpt = None
    median: FiniteFloatOpt = None
    p75: FiniteFloatOpt = None
    n: int = Field(default=0, ge=0)
    currency: str = Field(default="BRL", max_length=8)

    @model_validator(mode="after")
    def _order(self) -> ValueBand:
        vals = [v for v in (self.p25, self.median, self.p75) if v is not None]
        if len(vals) == 3 and not (vals[0] <= vals[1] <= vals[2] + 1e-9):
            raise ValueError("p25 <= median <= p75 required")
        return self


class PrivacyCellMeta(PublicModel):
    min_cell_count: int = Field(ge=0)
    suppressed_cells: int = Field(ge=0)
    suppressed_contract_count: int = Field(ge=0)
    policy: str = Field(max_length=400)


class PrivacyMetadata(PublicModel):
    """Small-cell privacy suppression metadata attached to markets/competition."""

    top_buyers: PrivacyCellMeta | None = None
    top_suppliers: PrivacyCellMeta | None = None
    policy: str | None = Field(default=None, max_length=400)
    min_cell_count: int | None = Field(default=None, ge=0)


class Modality(PublicModel):
    name: str = Field(max_length=200)
    count: int = Field(ge=0)


class UfObservation(PublicModel):
    uf: str
    contract_count: int = Field(ge=0)

    @field_validator("uf")
    @classmethod
    def _uf(cls, v: str) -> str:
        out = _optional_uf(v)
        if out is None:
            raise ValueError("uf required")
        return out


class BuyerTypeObservation(PublicModel):
    type: str = Field(max_length=80)
    contract_count: int = Field(ge=0)


class StatusBreakdown(PublicModel):
    abertas: int = Field(default=0, ge=0)
    encerradas_recentes: int = Field(default=0, ge=0)
    suspensas: int = Field(default=0, ge=0)
    historico: int = Field(default=0, ge=0)


class Freshness(PublicModel):
    """Radar / dataset freshness evaluation."""

    status: Literal["ok", "warning", "fail"]
    age_hours: FiniteFloatOpt = None
    warning_hours: int = Field(default=24, ge=0)
    fail_hours: int = Field(default=72, ge=0)
    reason: str | None = Field(default=None, max_length=400)
    source_unavailable: bool = False
    now_source: str | None = Field(default=None, max_length=80)
    data_as_of: str | None = None
    evaluated_at: str | None = None

    @field_validator("data_as_of", "evaluated_at", mode="before")
    @classmethod
    def _dates(cls, v: object) -> str | None:
        return _iso_date_str(v)  # type: ignore[arg-type]


class OfficialReference(PublicModel):
    name: str = Field(max_length=300)
    url: str = Field(max_length=2000)

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        out = _https_official(v)
        if out is None:
            raise ValueError("official URL required")
        return out


class ClaimEvidence(PublicModel):
    claim: str = Field(max_length=500)
    evidence_kind: str | None = Field(default=None, max_length=80)
    count: int | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=500)
    source: str | None = Field(default=None, max_length=120)


class DocumentSignal(PublicModel):
    signal: str = Field(max_length=120)
    count: int = Field(default=0, ge=0)
    note: str | None = Field(default=None, max_length=400)


class BudgetSignal(PublicModel):
    signal: str = Field(max_length=120)
    count: int = Field(default=0, ge=0)
    amount: FiniteFloatOpt = None
    note: str | None = Field(default=None, max_length=400)


class HistogramBin(PublicModel):
    key: str = Field(max_length=120)
    count: int = Field(ge=0)


class ClassifierMetadata(PublicModel):
    labels: list[str] = Field(default_factory=list, max_length=20)
    indexable_class: str = Field(default="aec_confirmed", max_length=40)


class InternalSignatureAggregates(PublicModel):
    available: bool = False
    n_accounts_internal: int | None = Field(default=None, ge=0)
    activity_class_histogram: list[HistogramBin] = Field(default_factory=list, max_length=50)
    sector_fit_histogram: list[HistogramBin] = Field(default_factory=list, max_length=50)
    public_signal_frequency: list[HistogramBin] = Field(default_factory=list, max_length=80)
    note: str | None = Field(default=None, max_length=800)

    @field_validator(
        "activity_class_histogram",
        "sector_fit_histogram",
        "public_signal_frequency",
        mode="before",
    )
    @classmethod
    def _hist_from_dict(cls, v: object) -> object:
        if v is None:
            return []
        if isinstance(v, dict):
            return [{"key": str(k), "count": int(c)} for k, c in sorted(v.items())]
        return v


class MethodologyMetadata(PublicModel):
    """Structured methodology block when not a plain string."""

    summary: str | None = Field(default=None, max_length=2000)
    steps: list[str] = Field(default_factory=list, max_length=30)
    notes: list[str] = Field(default_factory=list, max_length=30)


class LabeledCount(PublicModel):
    label: str = Field(max_length=120)
    count: int = Field(ge=0)


class ValueBandLabel(PublicModel):
    """Competition value-band histogram entry (label + count)."""

    band: str = Field(max_length=40)
    count: int = Field(default=0, ge=0)
    contract_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if out.get("count") is None and out.get("contract_count") is not None:
            out["count"] = out["contract_count"]
        if out.get("band") is None:
            out["band"] = out.get("label") or out.get("name") or out.get("value_band")
        return out


# ---------------------------------------------------------------------------
# Leaf cells
# ---------------------------------------------------------------------------


class BuyerCell(PublicModel):
    name: str | None = Field(default=None, max_length=300)
    cnpj8: str | None = None
    uf: str | None = None
    municipio: str | None = Field(default=None, max_length=120)
    contract_count: int = Field(ge=0)
    total_value: FiniteFloat = Field(default=0)
    suppressed: bool | None = None
    original_cells: int | None = Field(default=None, ge=0)

    @field_validator("cnpj8", mode="before")
    @classmethod
    def _c(cls, v: object) -> str | None:
        return _optional_cnpj8(v if v is None else str(v))  # type: ignore[arg-type]

    @field_validator("uf", mode="before")
    @classmethod
    def _u(cls, v: object) -> str | None:
        return _optional_uf(v if v is None else str(v))  # type: ignore[arg-type]

    @field_validator("total_value", mode="before")
    @classmethod
    def _tv(cls, v: object) -> float:
        return _finite_required(float(v or 0))


class ObjectCell(PublicModel):
    label: str = Field(max_length=300)
    count: int = Field(ge=0)
    median_value: FiniteFloatOpt = None
    example_objeto: str | None = Field(default=None, max_length=500)


class YearValue(PublicModel):
    year: str = Field(max_length=4, min_length=4)
    contract_count: int = Field(ge=0)
    total_value: FiniteFloat = Field(default=0)

    @field_validator("total_value", mode="before")
    @classmethod
    def _tv(cls, v: object) -> float:
        return _finite_required(float(v or 0))


class SeasonalityPoint(PublicModel):
    period: str = Field(max_length=7)  # YYYY-MM
    contract_count: int = Field(ge=0)


class ArchetypeMixEntry(PublicModel):
    archetype_id: str = Field(max_length=80)
    contract_count: int = Field(ge=0)


class OfficialChannel(PublicModel):
    name: str = Field(max_length=200)
    url: str | None = Field(default=None, max_length=2000)

    @field_validator("url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        return _https_official(v) if v else None


class SupplierObservation(PublicModel):
    display_name: str | None = Field(default=None, max_length=200)
    contract_count: int = Field(ge=0)
    total_value: FiniteFloat = Field(default=0)
    agencies_count: int = Field(default=0, ge=0)
    value_band: str | None = Field(default=None, max_length=40)

    @field_validator("total_value", mode="before")
    @classmethod
    def _tv(cls, v: object) -> float:
        return _finite_required(float(v or 0))


class PublicPriceExample(PublicModel):
    objeto: str | None = Field(default=None, max_length=500)
    valor: FiniteFloatOpt = None
    uf: str | None = None
    municipio: str | None = Field(default=None, max_length=120)
    orgao_nome: str | None = Field(default=None, max_length=300)
    data_publicacao: str | None = None
    source: str | None = Field(default=None, max_length=40)
    contrato_id: str | None = Field(default=None, max_length=80)
    link_oficial: str | None = Field(default=None, max_length=2000)
    portal_origem: str | None = Field(default=None, max_length=40)

    @field_validator("uf", mode="before")
    @classmethod
    def _u(cls, v: object) -> str | None:
        return _optional_uf(v if v is None else str(v))  # type: ignore[arg-type]

    @field_validator("data_publicacao", mode="before")
    @classmethod
    def _d(cls, v: object) -> str | None:
        return _iso_date_str(v)  # type: ignore[arg-type]

    @field_validator("link_oficial")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        return _https_public(v)

    @field_validator("valor", mode="before")
    @classmethod
    def _val(cls, v: object) -> float | None:
        if v is None or v == "":
            return None
        return _finite_number(float(v))


class ComparisonMeta(PublicModel):
    nature: str | None = Field(default=None, max_length=40)
    scope: str | None = Field(default=None, max_length=40)
    typology: str | None = Field(default=None, max_length=80)
    regime: str | None = Field(default=None, max_length=40)
    comparison_group: str | None = Field(default=None, max_length=200)
    comparison_confidence: FiniteFloatOpt = None
    # Emitter uses inclusion_criteria / exclusion_criteria (as_dict)
    inclusion_criteria: list[str] = Field(default_factory=list, max_length=30)
    exclusion_criteria: list[str] = Field(default_factory=list, max_length=30)
    inclusion: list[str] = Field(default_factory=list, max_length=30)  # legacy alias
    exclusion: list[str] = Field(default_factory=list, max_length=30)
    heterogeneity_flags: list[str] = Field(default_factory=list, max_length=20)


class ScopeCount(PublicModel):
    scope: str = Field(max_length=80)
    count: int = Field(ge=0)


# ---------------------------------------------------------------------------
# Top-level public artifacts
# ---------------------------------------------------------------------------


class Archetype(PublicModel):
    id: str | None = Field(default=None, max_length=80)
    slug: str | None = None
    label: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    object_patterns_public: list[str] = Field(default_factory=list, max_length=50)
    ufs_observed: list[UfObservation] = Field(default_factory=list, max_length=30)
    value_band: ValueBand | None = None
    modalities_observed: list[Modality] = Field(default_factory=list, max_length=30)
    buyer_types_observed: list[BuyerTypeObservation] = Field(default_factory=list, max_length=30)
    confenge_service_slugs: list[str] = Field(default_factory=list, max_length=40)
    evidence_contract_count: int = Field(default=0, ge=0)
    evidence_buyer_count: int = Field(default=0, ge=0)
    methodology: str | None = Field(default=None, max_length=4000)
    limitations: list[str] = Field(default_factory=list, max_length=30)
    sources: list[str] = Field(default_factory=list, max_length=20)
    theme: str | None = Field(default=None, max_length=80)
    related_services: list[str] = Field(default_factory=list, max_length=40)

    @field_validator("slug", mode="before")
    @classmethod
    def _slug(cls, v: object) -> str | None:
        return _optional_slug(v if v is None else str(v))  # type: ignore[arg-type]

    @field_validator("ufs_observed", mode="before")
    @classmethod
    def _ufs(cls, v: object) -> object:
        # Accept legacy list[str]
        if isinstance(v, list) and v and isinstance(v[0], str):
            return [{"uf": u, "contract_count": 0} for u in v]
        return v

    @field_validator("modalities_observed", mode="before")
    @classmethod
    def _mods(cls, v: object) -> object:
        if isinstance(v, list) and v and isinstance(v[0], str):
            return [{"name": m, "count": 0} for m in v]
        return v

    @field_validator("buyer_types_observed", mode="before")
    @classmethod
    def _bt(cls, v: object) -> object:
        if isinstance(v, list) and v and isinstance(v[0], str):
            return [{"type": t, "contract_count": 0} for t in v]
        return v


class Market(PublicModel):
    id: str = Field(max_length=120)
    slug: str
    archetype_id: str | None = Field(default=None, max_length=80)
    segment: str | None = Field(default=None, max_length=200)
    region: str | None = None
    region_label: str | None = Field(default=None, max_length=80)
    period_start: str | None = None
    period_end: str | None = None
    contract_count: int = Field(default=0, ge=0)
    buyer_count: int = Field(default=0, ge=0)
    supplier_count: int = Field(default=0, ge=0)
    total_value: FiniteFloat = Field(default=0)
    median_value: FiniteFloatOpt = None
    p25_value: FiniteFloatOpt = None
    p75_value: FiniteFloatOpt = None
    top_buyers: list[BuyerCell] = Field(default_factory=list, max_length=20)
    top_objects: list[ObjectCell] = Field(default_factory=list, max_length=20)
    value_by_year: list[YearValue] = Field(default_factory=list, max_length=40)
    modalities: list[Modality] = Field(default_factory=list, max_length=30)
    open_opportunity_count: int = Field(default=0, ge=0)
    sources: list[str] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=30)
    interpretation_hooks: list[str] = Field(default_factory=list, max_length=30)
    privacy: PrivacyMetadata | None = None

    @field_validator("slug", mode="before")
    @classmethod
    def _slug(cls, v: object) -> str:
        return _required_slug(str(v))

    @field_validator("region", mode="before")
    @classmethod
    def _region(cls, v: object) -> str | None:
        return _optional_uf(v if v is None else str(v))  # type: ignore[arg-type]

    @field_validator("period_start", "period_end", mode="before")
    @classmethod
    def _periods(cls, v: object) -> str | None:
        return _iso_date_str(v)  # type: ignore[arg-type]

    @field_validator("modalities", mode="before")
    @classmethod
    def _mods(cls, v: object) -> object:
        if isinstance(v, list) and v and isinstance(v[0], str):
            return [{"name": m, "count": 0} for m in v]
        return v

    @field_validator("total_value", mode="before")
    @classmethod
    def _tv(cls, v: object) -> float:
        return _finite_required(float(v or 0))

    @model_validator(mode="after")
    def _percentiles(self) -> Market:
        vals = [v for v in (self.p25_value, self.median_value, self.p75_value) if v is not None]
        if len(vals) == 3 and not (vals[0] <= vals[1] <= vals[2] + 1e-9):
            raise ValueError("p25 <= mediana <= p75 required")
        return self


class Agency(PublicModel):
    id: str | None = Field(default=None, max_length=120)
    slug: str | None = None
    # Legacy aliases still accepted alongside emitter fields
    cnpj8: str | None = None
    name: str | None = Field(default=None, max_length=300)
    agency_name: str | None = Field(default=None, max_length=300)
    agency_cnpj8: str | None = None
    orgao_nome: str | None = Field(default=None, max_length=300)
    uf: str | None = None
    municipio: str | None = Field(default=None, max_length=120)
    period_start: str | None = None
    period_end: str | None = None
    contract_count: int = Field(default=0, ge=0)
    total_value: FiniteFloat = Field(default=0)
    median_value: FiniteFloatOpt = None
    p25_value: FiniteFloatOpt = None
    p75_value: FiniteFloatOpt = None
    archetype_ids: list[str] = Field(default_factory=list, max_length=40)
    archetype_mix: list[ArchetypeMixEntry] = Field(default_factory=list, max_length=40)
    related_archetypes: list[str] = Field(default_factory=list, max_length=40)
    top_objects: list[ObjectCell] = Field(default_factory=list, max_length=20)
    modalities: list[Modality] = Field(default_factory=list, max_length=30)
    seasonality: list[SeasonalityPoint] = Field(default_factory=list, max_length=36)
    supplier_count: int = Field(default=0, ge=0)
    open_opportunities: list[OpportunityItem] = Field(default_factory=list, max_length=20)
    official_channels: list[OfficialChannel] = Field(default_factory=list, max_length=20)
    sources: list[str] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=30)
    practical_notes: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("slug", mode="before")
    @classmethod
    def _slug(cls, v: object) -> str | None:
        return _optional_slug(v if v is None else str(v))  # type: ignore[arg-type]

    @field_validator("cnpj8", "agency_cnpj8", mode="before")
    @classmethod
    def _c(cls, v: object) -> str | None:
        return _optional_cnpj8(v if v is None else str(v))  # type: ignore[arg-type]

    @field_validator("uf", mode="before")
    @classmethod
    def _u(cls, v: object) -> str | None:
        return _optional_uf(v if v is None else str(v))  # type: ignore[arg-type]

    @field_validator("period_start", "period_end", mode="before")
    @classmethod
    def _periods(cls, v: object) -> str | None:
        return _iso_date_str(v)  # type: ignore[arg-type]

    @field_validator("total_value", mode="before")
    @classmethod
    def _tv(cls, v: object) -> float:
        return _finite_required(float(v or 0))


class Price(PublicModel):
    id: str | None = Field(default=None, max_length=120)
    slug: str | None = None
    archetype_id: str | None = Field(default=None, max_length=80)
    object_label: str | None = Field(default=None, max_length=300)
    object_pattern: str | None = Field(default=None, max_length=80)
    region: str | None = None
    region_label: str | None = Field(default=None, max_length=80)
    mesh_slug: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    # Emitter fields
    observation_count: int = Field(default=0, ge=0)
    n: int = Field(default=0, ge=0)  # legacy alias
    median_value: FiniteFloatOpt = None
    p25_value: FiniteFloatOpt = None
    p75_value: FiniteFloatOpt = None
    min_value: FiniteFloatOpt = None
    max_value: FiniteFloatOpt = None
    # legacy names
    min: FiniteFloatOpt = None
    p25: FiniteFloatOpt = None
    mediana: FiniteFloatOpt = None
    p75: FiniteFloatOpt = None
    max: FiniteFloatOpt = None
    dispersion_iqr: FiniteFloatOpt = None
    outlier_count: int = Field(default=0, ge=0)
    comparison_group: str | None = Field(default=None, max_length=200)
    comparison_confidence: FiniteFloatOpt = None
    comparison_meta: ComparisonMeta | None = None
    scope_distribution: list[ScopeCount] = Field(default_factory=list, max_length=20)
    inclusion_criteria: list[str] = Field(default_factory=list, max_length=40)
    exclusion_criteria: list[str] = Field(default_factory=list, max_length=40)
    public_examples: list[PublicPriceExample] = Field(default_factory=list, max_length=10)
    heterogeneity_flags: list[str] = Field(default_factory=list, max_length=20)
    warning: str | None = Field(default=None, max_length=1000)
    limitations: list[str] = Field(default_factory=list, max_length=30)
    segment: str | None = Field(default=None, max_length=200)
    unit: str | None = Field(default=None, max_length=40)
    sources: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("slug", "mesh_slug", mode="before")
    @classmethod
    def _slug(cls, v: object) -> str | None:
        return _optional_slug(v if v is None else str(v))  # type: ignore[arg-type]

    @field_validator("region", mode="before")
    @classmethod
    def _region(cls, v: object) -> str | None:
        if v is None or v == "":
            return None
        s = str(v).strip().upper()
        if s == "BR":
            return s  # national rollup allowed on prices
        return _optional_uf(s)

    @field_validator("period_start", "period_end", mode="before")
    @classmethod
    def _periods(cls, v: object) -> str | None:
        return _iso_date_str(v)  # type: ignore[arg-type]

    @field_validator("scope_distribution", mode="before")
    @classmethod
    def _scopes(cls, v: object) -> object:
        if isinstance(v, dict):
            return [{"scope": str(k), "count": int(c)} for k, c in sorted(v.items())]
        return v


class Competition(PublicModel):
    id: str | None = Field(default=None, max_length=120)
    slug: str | None = None
    archetype_id: str | None = Field(default=None, max_length=80)
    segment: str | None = Field(default=None, max_length=200)
    region: str | None = None
    region_label: str | None = Field(default=None, max_length=80)
    period_start: str | None = None
    period_end: str | None = None
    buyer_count: int = Field(default=0, ge=0)
    supplier_count: int = Field(default=0, ge=0)
    contract_count: int = Field(default=0, ge=0)
    hhi_proxy: FiniteFloatOpt = None
    observed_suppliers: list[SupplierObservation] = Field(default_factory=list, max_length=20)
    concentration_top3_share: FiniteFloatOpt = None
    agencies_with_activity: int = Field(default=0, ge=0)
    value_bands: list[ValueBandLabel] = Field(default_factory=list, max_length=20)
    recent_changes: list[str] = Field(default_factory=list, max_length=30)
    language_note: str | None = Field(default=None, max_length=1000)
    limitations: list[str] = Field(default_factory=list, max_length=30)
    privacy: PrivacyMetadata | None = None
    sources: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("slug", mode="before")
    @classmethod
    def _slug(cls, v: object) -> str | None:
        return _optional_slug(v if v is None else str(v))  # type: ignore[arg-type]

    @field_validator("region", mode="before")
    @classmethod
    def _region(cls, v: object) -> str | None:
        return _optional_uf(v if v is None else str(v))  # type: ignore[arg-type]

    @field_validator("period_start", "period_end", mode="before")
    @classmethod
    def _periods(cls, v: object) -> str | None:
        return _iso_date_str(v)  # type: ignore[arg-type]

    @field_validator("value_bands", mode="before")
    @classmethod
    def _bands(cls, v: object) -> object:
        if isinstance(v, list) and v and isinstance(v[0], dict):
            out = []
            for item in v:
                band = (
                    item.get("band")
                    or item.get("label")
                    or item.get("name")
                    or item.get("value_band")
                )
                count = item.get("count")
                if count is None:
                    count = item.get("contract_count") or 0
                out.append(
                    {
                        "band": str(band),
                        "count": int(count),
                        "contract_count": int(item.get("contract_count") or count),
                    }
                )
            return out
        if isinstance(v, dict):
            return [{"band": str(k), "count": int(c), "contract_count": int(c)} for k, c in sorted(v.items())]
        return v

    @field_validator("recent_changes", mode="before")
    @classmethod
    def _recent(cls, v: object) -> object:
        if v is None:
            return []
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return [json_safe_str(x) for x in v]
        return v


def json_safe_str(obj: object) -> str:
    import json as _json

    if isinstance(obj, str):
        return obj
    return _json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)[:500]


class OpportunityItem(PublicModel):
    id: str | None = Field(default=None, max_length=120)
    pncp_id: str | None = Field(default=None, max_length=80)
    title: str | None = Field(default=None, max_length=400)
    objeto: str | None = Field(default=None, max_length=500)
    uf: str | None = None
    municipio: str | None = Field(default=None, max_length=120)
    orgao_nome: str | None = Field(default=None, max_length=300)
    orgao_cnpj8: str | None = None
    valor_estimado: FiniteFloatOpt = None
    modalidade: str | None = Field(default=None, max_length=120)
    data_encerramento: str | None = None
    data_publicacao: str | None = None
    link_pncp: str | None = Field(default=None, max_length=2000)
    link_oficial: str | None = Field(default=None, max_length=2000)
    source: str | None = Field(default=None, max_length=40)
    status: str | None = Field(default=None, max_length=40)
    status_bucket: str | None = Field(default=None, max_length=40)
    status_raw: str | None = Field(default=None, max_length=120)
    uncertainty: bool | None = None
    verified_at: str | None = None
    archetype_ids: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("uf", mode="before")
    @classmethod
    def _u(cls, v: object) -> str | None:
        return _optional_uf(v if v is None else str(v))  # type: ignore[arg-type]

    @field_validator("orgao_cnpj8", mode="before")
    @classmethod
    def _c(cls, v: object) -> str | None:
        return _optional_cnpj8(v if v is None else str(v))  # type: ignore[arg-type]

    @field_validator("data_encerramento", "data_publicacao", "verified_at", mode="before")
    @classmethod
    def _d(cls, v: object) -> str | None:
        return _iso_date_str(v)  # type: ignore[arg-type]

    @field_validator("link_pncp", "link_oficial")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        return _https_public(v)

    @field_validator("valor_estimado", mode="before")
    @classmethod
    def _val(cls, v: object) -> float | None:
        if v is None or v == "":
            return None
        return _finite_number(float(v))


# Rebuild Agency forward ref for OpportunityItem
Agency.model_rebuild()


class Opportunity(PublicModel):
    id: str = Field(max_length=120)
    slug: str
    label: str | None = Field(default=None, max_length=200)
    segment: str | None = Field(default=None, max_length=200)
    related_market_slug: str | None = None
    archetype_id: str | None = Field(default=None, max_length=80)
    region: str | None = None
    region_label: str | None = Field(default=None, max_length=80)
    open_count: int = Field(default=0, ge=0)
    closed_recent_count: int = Field(default=0, ge=0)
    suspended_count: int = Field(default=0, ge=0)
    historical_count: int = Field(default=0, ge=0)
    items: list[OpportunityItem] = Field(default_factory=list, max_length=200)
    truncated: bool = False
    as_of: str | None = None
    verified_at: str | None = None
    timezone: TimezoneName | str | None = Field(default="America/Sao_Paulo", max_length=64)
    status_breakdown: StatusBreakdown | None = None
    sources: list[str] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=30)
    freshness: Freshness | None = None

    @field_validator("slug", "related_market_slug", mode="before")
    @classmethod
    def _slug(cls, v: object) -> str | None:
        if v is None or v == "":
            return None
        return _optional_slug(str(v))

    @field_validator("id", mode="before")
    @classmethod
    def _id(cls, v: object) -> str:
        s = str(v).strip()
        if not s:
            raise ValueError("id required")
        return s[:120]

    @field_validator("region", mode="before")
    @classmethod
    def _region(cls, v: object) -> str | None:
        return _optional_uf(v if v is None else str(v))  # type: ignore[arg-type]

    @field_validator("as_of", "verified_at", mode="before")
    @classmethod
    def _dates(cls, v: object) -> str | None:
        return _iso_date_str(v)  # type: ignore[arg-type]

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return "America/Sao_Paulo"
        allowed = {"America/Sao_Paulo", "UTC", "America/Fortaleza", "America/Manaus"}
        if v not in allowed:
            # accept IANA-like strings with slash
            if "/" not in v or len(v) > 64:
                raise ValueError(f"unsupported timezone: {v}")
        return v


class ProblemService(PublicModel):
    id: str | None = Field(default=None, max_length=80)
    slug: str | None = None
    problem: str | None = Field(default=None, max_length=300)
    problem_label: str | None = Field(default=None, max_length=300)
    service: str | None = Field(default=None, max_length=200)
    confenge_service_slug: str | None = None
    theme: str | None = Field(default=None, max_length=80)
    observed_pattern: str | None = Field(default=None, max_length=2000)
    related_archetypes: list[str] = Field(default_factory=list, max_length=40)
    archetype_ids: list[str] = Field(default_factory=list, max_length=40)
    evidence_count: int | None = Field(default=None, ge=0)
    official_references: list[OfficialReference] = Field(default_factory=list, max_length=30)
    technical_guide_paths: list[str] = Field(default_factory=list, max_length=30)
    sources: list[str] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=30)
    claim_evidence: list[ClaimEvidence] = Field(default_factory=list, max_length=50)
    evidence_signals: list[str] = Field(default_factory=list, max_length=40)
    evidence_kind: str | None = Field(default=None, max_length=80)
    amendment_count: int | None = Field(default=None, ge=0)
    reference_mentions: int | None = Field(default=None, ge=0)
    document_divergence_count: int | None = Field(default=None, ge=0)
    document_signals: list[DocumentSignal] = Field(default_factory=list, max_length=40)
    budget_signals: list[BudgetSignal] = Field(default_factory=list, max_length=40)

    @field_validator("slug", "confenge_service_slug", mode="before")
    @classmethod
    def _slug(cls, v: object) -> str | None:
        return _optional_slug(v if v is None else str(v))  # type: ignore[arg-type]


class ICPMethodology(PublicModel):
    """Methodology document — structured nested models, no free Any bags."""

    model_config = ConfigDict(extra="forbid")
    version: str | None = Field(default=None, max_length=20)
    schema_version: str | None = Field(default=None, max_length=20)
    description: str | None = Field(default=None, max_length=2000)
    methodology: str | MethodologyMetadata | None = Field(default=None)
    classifier: ClassifierMetadata | None = None
    sources: list[str] = Field(default_factory=list, max_length=30)
    limitations: list[str] = Field(default_factory=list, max_length=30)
    internal_signature_aggregates: InternalSignatureAggregates | None = None

    @field_validator("methodology", mode="before")
    @classmethod
    def _meth(cls, v: object) -> object:
        if isinstance(v, dict):
            return v  # MethodologyMetadata
        return v

    @field_validator("classifier", mode="before")
    @classmethod
    def _clf(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        return v

    @field_validator("internal_signature_aggregates", mode="before")
    @classmethod
    def _isa(cls, v: object) -> object:
        if v is None:
            return None
        return v


class ApprovalArtifact(PublicModel):
    decision: str
    dataset_hash: str = Field(min_length=64, max_length=64)
    schema_version: str = Field(max_length=20)
    exporter_version: str = Field(max_length=40)
    source_commit_sha: str = Field(min_length=7, max_length=64)
    actor: str = Field(min_length=1, max_length=200)
    approved_at: str
    notes: str | None = Field(default=None, max_length=2000)
    approval_hash: str | None = Field(default=None, max_length=64)

    @field_validator("decision")
    @classmethod
    def _dec(cls, v: str) -> str:
        if v not in {"APPROVED", "APPROVED_WITH_NOTES", "REJECTED"}:
            raise ValueError("invalid decision")
        return v

    @field_validator("dataset_hash", "approval_hash")
    @classmethod
    def _hex(cls, v: str | None) -> str | None:
        if v is None:
            return None
        low = v.lower()
        if not _HEX64_RE.match(low):
            raise ValueError("hash must be 64 lowercase hex chars")
        return low

    @field_validator("source_commit_sha")
    @classmethod
    def _sha(cls, v: str) -> str:
        low = v.lower()
        if not _HEX_SHA_RE.match(low):
            raise ValueError("source_commit_sha must be hex")
        return low

    @field_validator("approved_at", mode="before")
    @classmethod
    def _at(cls, v: object) -> str:
        out = _iso_datetime_str(v)  # type: ignore[arg-type]
        if not out:
            raise ValueError("approved_at required")
        return out


def validate_public_payload(kind: str, data: object) -> object:
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
        return [
            model.model_validate(item).model_dump(mode="json", exclude_none=False) for item in data
        ]
    except Exception as exc:
        raise ValueError(f"{kind} validation failed: {exc}") from exc


# Public nested model names for schema export / tests
PUBLIC_NESTED_MODELS: tuple[type[BaseModel], ...] = (
    ValueBand,
    PrivacyMetadata,
    PrivacyCellMeta,
    Modality,
    StatusBreakdown,
    Freshness,
    OfficialReference,
    ClaimEvidence,
    DocumentSignal,
    BudgetSignal,
    ClassifierMetadata,
    InternalSignatureAggregates,
    MethodologyMetadata,
    HistogramBin,
    UfObservation,
    BuyerTypeObservation,
)
