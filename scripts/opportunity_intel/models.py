"""Dataclass models for Opportunity Intelligence.

Defines the canonical record shape, crawl request parameters,
and fetch result wrapper used throughout the pipeline.

Follows patterns from:
    scripts/crawl/registry.py (SourceInfo)
    scripts/crawl/pncp_contract.py (PNCPTarget)
    scripts/crawl/ingestion/_base/crawler.py (CrawlRequest, FetchResult)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------

CANONICAL_STATUSES: tuple[str, ...] = (
    "open",
    "upcoming",
    "closed",
    "suspended",
    "revoked",
    "annulled",
    "failed",
    "unknown",
)

RANKING_TIERS: tuple[str, ...] = ("GO", "REVIEW", "NO_GO")

CONFIDENCE_LEVELS: tuple[str, ...] = ("HIGH", "MEDIUM", "LOW")


# ---------------------------------------------------------------------------
# OpportunityRecord — canonical representation
# ---------------------------------------------------------------------------


@dataclass
class OpportunityRecord:
    """Single bidding opportunity, normalized from any source.

    All fields map directly to ``opportunity_intel`` table columns.
    Optional fields default to None / empty collections.
    """

    # Identity
    source: str
    source_id: str
    content_hash: str
    source_url: str | None = None
    numero_controle_pncp: str | None = None

    # Execution
    crawl_batch_id: str | None = None
    run_id: int | None = None
    ingested_at: datetime | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None

    # Entity
    orgao_cnpj: str | None = None
    orgao_nome: str | None = None
    ente_federativo: str | None = None
    uf: str = "SC"
    municipio: str | None = None
    codigo_ibge: str | None = None

    # Process
    numero_processo: str | None = None
    numero_edital: str | None = None
    modalidade: str | None = None
    modalidade_id: int | None = None

    # Object
    objeto: str = ""
    categoria: str | None = None

    # Value
    valor_estimado: float | None = None
    valor_homologado: float | None = None
    valor_semantica: str | None = None

    # Dates
    data_publicacao: datetime | None = None
    data_abertura: datetime | None = None
    data_encerramento: datetime | None = None
    data_homologacao: datetime | None = None

    # Status
    status_fonte: str | None = None
    status_canonico: str = "unknown"
    status_motivo: str | None = None
    status_data: datetime | None = None

    # Documents
    link_edital: str | None = None
    link_anexos: list[str] = field(default_factory=list)

    # Quality
    qualidade_score: int = 0
    qualidade_fatores: dict[str, Any] = field(default_factory=dict)
    dados_ausentes: list[str] = field(default_factory=list)

    # Ranking
    ranking: str = "REVIEW"
    ranking_score: int = 0
    ranking_fatores: dict[str, Any] = field(default_factory=dict)
    ranking_regras: list[str] = field(default_factory=list)
    ranking_confianca: str = "MEDIUM"

    # Provenance
    proveniencia: dict[str, str] = field(default_factory=dict)

    # Metadata
    is_active: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_db_dict(self) -> dict[str, Any]:
        """Convert to dict suitable for PostgreSQL upsert function (JSONB)."""
        return {
            "source": self.source,
            "source_id": self.source_id,
            "source_url": self.source_url,
            "content_hash": self.content_hash,
            "numero_controle_pncp": self.numero_controle_pncp,
            "crawl_batch_id": self.crawl_batch_id,
            "run_id": str(self.run_id) if self.run_id else None,
            "first_seen_at": _iso(self.first_seen_at),
            "last_seen_at": _iso(self.last_seen_at),
            "orgao_cnpj": self.orgao_cnpj,
            "orgao_nome": self.orgao_nome,
            "ente_federativo": self.ente_federativo,
            "uf": self.uf,
            "municipio": self.municipio,
            "codigo_ibge": self.codigo_ibge,
            "numero_processo": self.numero_processo,
            "numero_edital": self.numero_edital,
            "modalidade": self.modalidade,
            "modalidade_id": str(self.modalidade_id) if self.modalidade_id else None,
            "objeto": self.objeto,
            "categoria": self.categoria,
            "valor_estimado": str(self.valor_estimado) if self.valor_estimado else None,
            "valor_homologado": str(self.valor_homologado) if self.valor_homologado else None,
            "valor_semantica": self.valor_semantica,
            "data_publicacao": _iso(self.data_publicacao),
            "data_abertura": _iso(self.data_abertura),
            "data_encerramento": _iso(self.data_encerramento),
            "data_homologacao": _iso(self.data_homologacao),
            "status_fonte": self.status_fonte,
            "status_canonico": self.status_canonico,
            "status_motivo": self.status_motivo,
            "status_data": _iso(self.status_data),
            "link_edital": self.link_edital,
            "link_anexos": self.link_anexos if self.link_anexos else None,
            "qualidade_score": str(self.qualidade_score),
            "qualidade_fatores": self.qualidade_fatores,
            "dados_ausentes": self.dados_ausentes if self.dados_ausentes else None,
            "ranking": self.ranking,
            "ranking_score": str(self.ranking_score),
            "ranking_fatores": self.ranking_fatores,
            "ranking_regras": self.ranking_regras if self.ranking_regras else None,
            "ranking_confianca": self.ranking_confianca,
            "proveniencia": self.proveniencia,
            "metadata": self.metadata,
        }


def _iso(val: Any) -> str | None:
    """Convert datetime/date to ISO string for JSONB."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, date):
        return val.isoformat()
    return str(val)


# ---------------------------------------------------------------------------
# CrawlRequest — parameterized crawl target
# ---------------------------------------------------------------------------


@dataclass
class CrawlRequest:
    """Parameters for a single crawl execution.

    Mirrors the pattern in ``scripts/crawl/ingestion/_base/crawler.py``.
    """

    source: str
    target: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    mode: str = "full"  # full, incremental, dry-run
    limit: int | None = None
    page_size: int = 500


# ---------------------------------------------------------------------------
# FetchResult — result of a single HTTP fetch
# ---------------------------------------------------------------------------


@dataclass
class FetchResult:
    """Result wrapper for HTTP crawl responses.

    Follows pattern from ``scripts/crawl/ingestion/_base/crawler.py``.
    """

    status: int = 0
    raw_data: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    page: int = 1
    total_pages: int | None = None
    total_records: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status in (200, 204) and self.error is None

    @property
    def empty(self) -> bool:
        return len(self.raw_data) == 0 and self.success

    @property
    def is_last_page(self) -> bool:
        if self.total_pages is not None:
            return self.page >= self.total_pages
        return self.empty
