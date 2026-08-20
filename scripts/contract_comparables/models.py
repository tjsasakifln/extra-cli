"""Immutable records for the inbound contract-comparables engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class ContractRecord:
    contract_id: str
    objeto: str
    valor: Decimal | None
    valor_is_unknown: bool = False
    valor_semantic: str = "unknown"
    value_basis: str = "unknown"
    unidade: str | None = None
    quantidade: Decimal | None = None
    uf: str | None = None
    municipio: str | None = None
    regime: str | None = None
    modalidade: str | None = None
    porte: str | None = None
    data_referencia: str | None = None
    year: int | None = None
    revision: int = 1
    superseded_by: str | None = None
    evidence_ref: str | None = None
    source: str = "fixture"
    orgao_id: str | None = None
    orgao_nome: str | None = None
    fornecedor_id: str | None = None
    fornecedor_nome: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Recorte:
    contract: ContractRecord
    typology: str
    typology_confidence: float
    scope: str
    regime: str
    unit: str
    value_semantic: str
    value_basis: str
    uf: str | None
    region: str | None
    year: int | None
    porte: str | None
    modalidade: str | None
    unknown_fields: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract.contract_id,
            "typology": self.typology,
            "typology_confidence": self.typology_confidence,
            "scope": self.scope,
            "regime": self.regime,
            "unit": self.unit,
            "value_semantic": self.value_semantic,
            "value_basis": self.value_basis,
            "uf": self.uf,
            "region": self.region,
            "year": self.year,
            "porte": self.porte,
            "modalidade": self.modalidade,
            "unknown_fields": list(self.unknown_fields),
        }


@dataclass(frozen=True)
class Exclusion:
    contract_id: str
    reason_codes: tuple[str, ...]
    detail: str
    match_distance: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "reason_codes": list(self.reason_codes),
            "detail": self.detail,
            "match_distance": self.match_distance,
        }


@dataclass(frozen=True)
class SelectedPeer:
    recorte: Recorte
    match_distance: float
    match_quality: str

    def as_dict(self) -> dict[str, Any]:
        payload = self.recorte.as_dict()
        payload["valor"] = (
            None
            if self.recorte.contract.valor is None
            else format(self.recorte.contract.valor.quantize(Decimal("0.01")), "f")
        )
        payload["match_distance"] = self.match_distance
        payload["match_quality"] = self.match_quality
        payload["evidence_ref"] = self.recorte.contract.evidence_ref
        return payload


@dataclass(frozen=True)
class RectificationEvent:
    rectification_id: str
    contract_id: str
    as_of: str
    fields: dict[str, Any]
    note: str | None = None


@dataclass(frozen=True)
class PeerRequest:
    focal_contract_id: str
    as_of: str
    question_id: str = "paving_nominal_total_value_position"
    consumer_id: str = "public-read-contract-analysis/#400"
    catalog_mode: str = "fixture"
    source: str = "fixture"
    policy_version: str = "contract-comparables-policy/1.0"
    allow_text_similarity_authority: bool = False
    allow_embeddings: bool = False
    allow_physical_unit_price: bool = False
    producer_sha: str | None = None
    live_semantic_columns_present: bool = True
    monetary_normalization: str | None = None
    require_known_regime: bool = True


@dataclass(frozen=True)
class MetricsBundle:
    n: int
    median: Decimal
    p25: Decimal
    p75: Decimal
    iqr: Decimal
    mad: Decimal
    focal_percentile: float
    robust_distance: float | None
    minimum: Decimal
    maximum: Decimal
    min_max_caution: str
    coverage: float
    missingness: float
    stratum: dict[str, int]
    outlier_flag: bool
    outlier_method: str

    def as_public_dict(self) -> dict[str, Any]:
        def money(value: Decimal) -> str:
            return format(value.quantize(Decimal("0.01")), "f")
        valor_block = {
            "n": self.n,
            "percentiles": {
                "p25": money(self.p25),
                "median": money(self.median),
                "p75": money(self.p75),
            },
        }
        return {
            "n": self.n,
            "median": money(self.median),
            "p25": money(self.p25),
            "p75": money(self.p75),
            "iqr": money(self.iqr),
            "mad": money(self.mad),
            "focal_percentile": round(self.focal_percentile, 4),
            "robust_distance": None if self.robust_distance is None else round(self.robust_distance, 4),
            "min": money(self.minimum),
            "max": money(self.maximum),
            "min_max_caution": self.min_max_caution,
            "coverage": round(self.coverage, 4),
            "missingness": round(self.missingness, 4),
            "stratum": dict(sorted(self.stratum.items())),
            "outlier_flag": self.outlier_flag,
            "outlier_method": self.outlier_method,
            "valor": valor_block,
            "value_semantic": "valor_integral_nominal",
            "unit": "BRL_TOTAL",
        }


@dataclass(frozen=True)
class PeerGroupResult:
    status: str
    reason_codes: tuple[str, ...]
    focal: Recorte
    peers: tuple[SelectedPeer, ...]
    exclusions: tuple[Exclusion, ...]
    total_n: int
    eligible_n: int
    usable_n: int
    coverage: float
    missingness: float
    metrics: MetricsBundle | None
    limitations: tuple[str, ...]
    inclusion_rules: tuple[str, ...]
    exclusion_rules: tuple[str, ...]
    outlier_treatment: str
    request: PeerRequest
    suppressed: bool = False
    late_arrival_invalidated: bool = False
