"""Versioned public-read-integrity/1.0 types and constants."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SCHEMA_VERSION = "public-read-integrity/1.0"
PRODUCER_VERSION = "public-read-integrity-producer/1.0"
FRESHNESS_POLICY = "public-read-integrity-ttl/1.0"
DEFAULT_TTL_SECONDS = 86_400
MAX_RETRIES = 3
MAX_PAGES = 50
CONTRACTED_SOURCES = ("CEIS", "CNEP")

IntegrityState = Literal["MATCHES_FOUND", "NO_MATCH_CONFIRMED", "PARTIAL", "UNKNOWN"]
FreshnessStatus = Literal["current", "stale", "expired"]

INTEGRITY_STATES: frozenset[str] = frozenset({"MATCHES_FOUND", "NO_MATCH_CONFIRMED", "PARTIAL", "UNKNOWN"})

CEIS_SPEC = {
    "source_id": "CEIS",
    "path": "/ceis",
    "api_url": "https://api.portaldatransparencia.gov.br/api-de-dados/ceis",
    "official_url": "https://portaldatransparencia.gov.br/sancoes/ceis",
    "authority": "Controladoria-Geral da Uniao (CGU) / Portal da Transparencia",
    "query_param": "codigoSancionado",
}
CNEP_SPEC = {
    "source_id": "CNEP",
    "path": "/cnep",
    "api_url": "https://api.portaldatransparencia.gov.br/api-de-dados/cnep",
    "official_url": "https://portaldatransparencia.gov.br/sancoes/cnep",
    "authority": "Controladoria-Geral da Uniao (CGU) / Portal da Transparencia",
    "query_param": "codigoSancionado",
}
SOURCE_SPECS = {"CEIS": CEIS_SPEC, "CNEP": CNEP_SPEC}

PAYLOAD_FIELDS = (
    "schema",
    "schema_version",
    "query_id",
    "queried_cnpj",
    "checked_at",
    "as_of",
    "expires_at",
    "freshness",
    "aggregate_state",
    "sources",
    "records",
    "limitations",
    "reason_codes",
    "not_legal_conclusion",
    "content_hash",
    "producer_version",
    "contracted_sources",
)
SOURCE_FIELDS = (
    "source_id",
    "official_url",
    "api_url",
    "authority",
    "status",
    "pages_expected",
    "pages_fetched",
    "coverage_complete",
    "raw_count",
    "normalized_count",
    "deduped_count",
    "reason_codes",
    "as_of",
)
RECORD_FIELDS = (
    "source_id",
    "official_id",
    "record_type",
    "authority",
    "start_date",
    "end_date",
    "observed_status",
    "source_url",
    "captured_at",
    "original",
)
FORBIDDEN_PAYLOAD_FIELDS = frozenset(
    {
        "score",
        "risk_score",
        "legal_score",
        "commercial_score",
        "recommendation",
        "legal_conclusion",
        "hire",
        "reject",
        "index",
        "noindex",
        "canonical",
    }
)
DEFAULT_LIMITATIONS = (
    "Consulta limitada aos cadastros CEIS e CNEP do Portal da Transparencia.",
    "Cadastros nao contratados nao entram na conclusao.",
    "Valor ausente nao e fato negativo.",
    "Ocorrencias observadas nao constituem conclusao juridica, certificacao ou recomendacao.",
)


@dataclass(frozen=True)
class TransportResponse:
    status_code: int
    body: Any = None
    error_class: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    attempts: int = 1


@dataclass(frozen=True)
class ObservedRecord:
    source_id: str
    official_id: str
    record_type: str
    authority: str
    start_date: str | None
    end_date: str | None
    observed_status: str
    source_url: str
    captured_at: str
    original: dict[str, Any]
    dedupe_reasons: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "official_id": self.official_id,
            "record_type": self.record_type,
            "authority": self.authority,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "observed_status": self.observed_status,
            "source_url": self.source_url,
            "captured_at": self.captured_at,
            "original": self.original,
        }


@dataclass(frozen=True)
class SourceRun:
    source_id: str
    official_url: str
    api_url: str
    authority: str
    status: IntegrityState
    pages_expected: int | None
    pages_fetched: int
    coverage_complete: bool
    raw_count: int
    normalized_count: int
    deduped_count: int
    reason_codes: tuple[str, ...]
    as_of: str | None
    error_class: str | None
    attempts: int
    records: tuple[ObservedRecord, ...]

    def as_source_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "official_url": self.official_url,
            "api_url": self.api_url,
            "authority": self.authority,
            "status": self.status,
            "pages_expected": self.pages_expected,
            "pages_fetched": self.pages_fetched,
            "coverage_complete": self.coverage_complete,
            "raw_count": self.raw_count,
            "normalized_count": self.normalized_count,
            "deduped_count": self.deduped_count,
            "reason_codes": list(self.reason_codes),
            "as_of": self.as_of,
            "error_class": self.error_class,
            "attempts": self.attempts,
        }


@dataclass(frozen=True)
class AggregateDecision:
    aggregate_state: IntegrityState
    reason_codes: tuple[str, ...]
    records: tuple[ObservedRecord, ...]
    sources: tuple[SourceRun, ...]
