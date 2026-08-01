"""Fail-closed run and operational statuses for process documents.

Maps intentionally to the contracts_crawler semantics while using the
document-capability vocabulary from the DOD (SUCCESS_NONZERO / SUCCESS_ZERO).

Never treat timeout / 403 / 429 / 5xx / partial pagination as SUCCESS_ZERO.
"""

from __future__ import annotations

from enum import StrEnum


class DocumentRunStatus(StrEnum):
    """Outcome of a single document collection run for an entity/source."""

    SUCCESS_NONZERO = "SUCCESS_NONZERO"
    SUCCESS_ZERO = "SUCCESS_ZERO"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    SOURCE_UNAVAILABLE = "source_unavailable"
    MANUAL_ONLY = "manual_only"
    IMPLEMENTED_NOT_PROVEN = "implemented_not_proven"
    PENDING = "pending"
    UNKNOWN = "unknown"
    CONNECTION_FAILED = "connection_failed"
    HTTP_CLIENT_ERROR = "http_client_error"
    HTTP_SERVER_ERROR = "http_server_error"
    HTTP_RATE_LIMIT = "http_rate_limit"
    PARSE_FAILED = "parse_failed"
    SCHEMA_FAILED = "schema_failed"
    PAGINATION_INCOMPLETE = "pagination_incomplete"
    DOWNLOAD_INCOMPLETE = "download_incomplete"
    PERSISTENCE_FAILED = "persistence_failed"
    CHECKPOINT_INCONSISTENT = "checkpoint_inconsistent"
    TIMEOUT = "timeout"
    AUTH_REQUIRED = "auth_required"
    CAPTCHA = "captcha"
    UNEXPECTED_EMPTY = "unexpected_empty"
    NOT_QUERIED_BUDGET = "NOT_QUERIED_BUDGET"
    NOT_QUERIED = "NOT_QUERIED"
    PARTIAL_CAPACITY_EXHAUSTED = "PARTIAL_CAPACITY_EXHAUSTED"


# Statuses that count toward operational document coverage of active entities.
OPERATIONAL_SUCCESS: frozenset[DocumentRunStatus] = frozenset(
    {
        DocumentRunStatus.SUCCESS_NONZERO,
        DocumentRunStatus.SUCCESS_ZERO,
    }
)

# Explicit non-coverage (remain in denominator when entity is active).
NON_COVERAGE: frozenset[DocumentRunStatus] = frozenset(
    {
        DocumentRunStatus.PARTIAL,
        DocumentRunStatus.BLOCKED,
        DocumentRunStatus.SOURCE_UNAVAILABLE,
        DocumentRunStatus.MANUAL_ONLY,
        DocumentRunStatus.IMPLEMENTED_NOT_PROVEN,
        DocumentRunStatus.PENDING,
        DocumentRunStatus.UNKNOWN,
        DocumentRunStatus.CONNECTION_FAILED,
        DocumentRunStatus.HTTP_CLIENT_ERROR,
        DocumentRunStatus.HTTP_SERVER_ERROR,
        DocumentRunStatus.HTTP_RATE_LIMIT,
        DocumentRunStatus.PARSE_FAILED,
        DocumentRunStatus.SCHEMA_FAILED,
        DocumentRunStatus.PAGINATION_INCOMPLETE,
        DocumentRunStatus.DOWNLOAD_INCOMPLETE,
        DocumentRunStatus.PERSISTENCE_FAILED,
        DocumentRunStatus.CHECKPOINT_INCONSISTENT,
        DocumentRunStatus.TIMEOUT,
        DocumentRunStatus.AUTH_REQUIRED,
        DocumentRunStatus.CAPTCHA,
        DocumentRunStatus.UNEXPECTED_EMPTY,
        DocumentRunStatus.NOT_QUERIED_BUDGET,
        DocumentRunStatus.NOT_QUERIED,
        DocumentRunStatus.PARTIAL_CAPACITY_EXHAUSTED,
    }
)


class DiscoveryStatus(StrEnum):
    """Per-entity document-source discovery classification (never leave unknown)."""

    MAPPED = "mapped"
    ACCESSIBLE = "accessible"
    COLLECTED = "collected"
    VERIFIED = "verified"
    OPERATIONAL = "operational"
    BLOCKED = "blocked"
    SOURCE_NOT_IDENTIFIED = "source_not_identified"
    NOT_APPLICABLE = "not_applicable"
    FAILED = "failed"
    # unknown is forbidden for final discovery reports


class ActivityStatus(StrEnum):
    """Entity activity over the lookback window (independent of document crawler)."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    UNKNOWN_PENDING_EVIDENCE = "unknown_pending_evidence"


class DocumentCategory(StrEnum):
    """Canonical document categories for completeness metrics."""

    EDITAL = "edital"
    AVISO = "aviso"
    ANEXO = "anexo"
    RETIFICACAO = "retificacao"
    ESTUDO_TECNICO = "estudo_tecnico_preliminar"
    TERMO_REFERENCIA = "termo_referencia"
    PROJETO = "projeto"
    MEMORIAL = "memorial"
    ESPECIFICACAO = "especificacao"
    PLANILHA_ORCAMENTARIA = "planilha_orcamentaria"
    COMPOSICAO = "composicao"
    CRONOGRAMA = "cronograma"
    MINUTA = "minuta"
    ESCLARECIMENTO = "esclarecimento"
    IMPUGNACAO = "impugnacao"
    RESPOSTA = "resposta"
    ATA_SESSAO = "ata_sessao"
    REGISTRO_DISPUTA = "registro_disputa"
    HABILITACAO_JURIDICA = "habilitacao_juridica"
    DOCUMENTO_FISCAL = "documento_fiscal"
    DOCUMENTO_TRABALHISTA = "documento_trabalhista"
    ECONOMICO_FINANCEIRO = "economico_financeiro"
    QUALIFICACAO_TECNICA = "qualificacao_tecnica"
    CAT = "cat"
    ART = "art"
    RRT = "rrt"
    ATESTADO = "atestado"
    PROPOSTA_COMERCIAL = "proposta_comercial"
    PLANILHA_LICITANTE = "planilha_licitante"
    DILIGENCIA = "diligencia"
    PARECER_TECNICO = "parecer_tecnico"
    PARECER_JURIDICO = "parecer_juridico"
    DECISAO_HABILITACAO = "decisao_habilitacao"
    DECISAO_CLASSIFICACAO = "decisao_classificacao"
    RECURSO = "recurso"
    CONTRARRAZAO = "contrarrazao"
    DECISAO_RECURSAL = "decisao_recursal"
    ADJUDICACAO = "adjudicacao"
    HOMOLOGACAO = "homologacao"
    RESULTADO = "resultado"
    CONTRATO = "contrato"
    GARANTIA = "garantia"
    ORDEM_SERVICO = "ordem_servico"
    APOSTILAMENTO = "apostilamento"
    TERMO_ADITIVO = "termo_aditivo"
    SUSPENSAO = "suspensao"
    RESCISAO = "rescisao"
    SANCAO = "sancao"
    OUTRO = "outro"
    UNKNOWN = "unknown_category"


# Completeness metric buckets
NOTICE_ANNEX_CATEGORIES: frozenset[DocumentCategory] = frozenset(
    {
        DocumentCategory.EDITAL,
        DocumentCategory.AVISO,
        DocumentCategory.ANEXO,
        DocumentCategory.RETIFICACAO,
        DocumentCategory.TERMO_REFERENCIA,
        DocumentCategory.PROJETO,
        DocumentCategory.MEMORIAL,
        DocumentCategory.ESPECIFICACAO,
        DocumentCategory.PLANILHA_ORCAMENTARIA,
        DocumentCategory.COMPOSICAO,
        DocumentCategory.CRONOGRAMA,
        DocumentCategory.MINUTA,
        DocumentCategory.ESTUDO_TECNICO,
    }
)

SESSION_JUDGMENT_CATEGORIES: frozenset[DocumentCategory] = frozenset(
    {
        DocumentCategory.ATA_SESSAO,
        DocumentCategory.REGISTRO_DISPUTA,
        DocumentCategory.DILIGENCIA,
        DocumentCategory.PARECER_TECNICO,
        DocumentCategory.PARECER_JURIDICO,
        DocumentCategory.DECISAO_HABILITACAO,
        DocumentCategory.DECISAO_CLASSIFICACAO,
        DocumentCategory.ADJUDICACAO,
        DocumentCategory.HOMOLOGACAO,
        DocumentCategory.RESULTADO,
    }
)

WINNING_PROPOSAL_CATEGORIES: frozenset[DocumentCategory] = frozenset(
    {
        DocumentCategory.PROPOSTA_COMERCIAL,
        DocumentCategory.PLANILHA_LICITANTE,
        DocumentCategory.CRONOGRAMA,
        DocumentCategory.COMPOSICAO,
    }
)

QUALIFICATION_CATEGORIES: frozenset[DocumentCategory] = frozenset(
    {
        DocumentCategory.HABILITACAO_JURIDICA,
        DocumentCategory.DOCUMENTO_FISCAL,
        DocumentCategory.DOCUMENTO_TRABALHISTA,
        DocumentCategory.ECONOMICO_FINANCEIRO,
        DocumentCategory.QUALIFICACAO_TECNICA,
        DocumentCategory.CAT,
        DocumentCategory.ART,
        DocumentCategory.RRT,
        DocumentCategory.ATESTADO,
    }
)
