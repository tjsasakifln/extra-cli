"""Base types for multi-source consolidation.

STUB: Minimal definitions to enable imports without ImportError.
Full implementation deferred to future epic.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any


class SourceCapability(StrEnum):
    """Capabilities a data source may support."""

    PAGINATION = "pagination"
    DATE_RANGE = "date_range"
    FILTER_BY_UF = "filter_by_uf"
    FILTER_BY_MODALITY = "filter_by_modality"


class SourceStatus(StrEnum):
    """Operational status of a data source."""

    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class SourceMetadata:
    """Metadata about a data source."""

    def __init__(
        self,
        name: str = "",
        code: str = "",
        base_url: str = "",
        capabilities: set[SourceCapability] | None = None,
        rate_limit_rps: float = 10.0,
        priority: int = 1,
    ):
        self.name = name
        self.code = code
        self.base_url = base_url
        self.capabilities = capabilities or set()
        self.rate_limit_rps = rate_limit_rps
        self.priority = priority


class UnifiedProcurement:
    """Unified procurement record across all sources.

    STUB: Full implementation deferred.
    """

    def __init__(
        self,
        source_id: str = "",
        source_name: str = "",
        objeto: str = "",
        valor_estimado: float = 0.0,
        orgao: str = "",
        cnpj_orgao: str = "",
        uf: str = "",
        municipio: str = "",
        data_publicacao: datetime | None = None,
        data_abertura: datetime | None = None,
        data_encerramento: datetime | None = None,
        numero_edital: str = "",
        ano: str = "",
        esfera: str = "",
        modalidade: str = "",
        modalidade_id: int | None = None,
        situacao: str = "",
        link_edital: str = "",
        link_portal: str = "",
        raw_data: dict[str, Any] | None = None,
    ):
        self.source_id = source_id
        self.source_name = source_name
        self.objeto = objeto
        self.valor_estimado = valor_estimado
        self.orgao = orgao
        self.cnpj_orgao = cnpj_orgao
        self.uf = uf
        self.municipio = municipio
        self.data_publicacao = data_publicacao
        self.data_abertura = data_abertura
        self.data_encerramento = data_encerramento
        self.numero_edital = numero_edital
        self.ano = ano
        self.esfera = esfera
        self.modalidade = modalidade
        self.modalidade_id = modalidade_id
        self.situacao = situacao
        self.link_edital = link_edital
        self.link_portal = link_portal
        self.raw_data = raw_data


__all__ = [
    "SourceCapability",
    "SourceMetadata",
    "SourceStatus",
    "UnifiedProcurement",
]
