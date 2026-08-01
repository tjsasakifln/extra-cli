"""Enums and pure helpers for bid readiness (no I/O)."""

from __future__ import annotations

from enum import Enum, StrEnum
from typing import Any


class DocType(StrEnum):
    CONTRATO_SOCIAL = "CONTRATO_SOCIAL"
    ALTERACAO_CONTRATUAL = "ALTERACAO_CONTRATUAL"
    CARTAO_CNPJ = "CARTAO_CNPJ"
    INSCRICAO_ESTADUAL = "INSCRICAO_ESTADUAL"
    INSCRICAO_MUNICIPAL = "INSCRICAO_MUNICIPAL"
    CERTIDAO_FEDERAL = "CERTIDAO_FEDERAL"
    CERTIDAO_ESTADUAL = "CERTIDAO_ESTADUAL"
    CERTIDAO_MUNICIPAL = "CERTIDAO_MUNICIPAL"
    FGTS = "FGTS"
    CNDT = "CNDT"
    CERTIDAO_FALENCIA = "CERTIDAO_FALENCIA"
    BALANCO_PATRIMONIAL = "BALANCO_PATRIMONIAL"
    DRE = "DRE"
    INDICES_CONTABEIS = "INDICES_CONTABEIS"
    CERTIDAO_PROFISSIONAL = "CERTIDAO_PROFISSIONAL"
    REGISTRO_CONSELHO_EMPRESA = "REGISTRO_CONSELHO_EMPRESA"
    REGISTRO_CONSELHO_PROFISSIONAL = "REGISTRO_CONSELHO_PROFISSIONAL"
    ATESTADO_CAPACIDADE_TECNICA = "ATESTADO_CAPACIDADE_TECNICA"
    CAT = "CAT"
    ART = "ART"
    RRT = "RRT"
    CURRICULO_PROFISSIONAL = "CURRICULO_PROFISSIONAL"
    VINCULO_PROFISSIONAL = "VINCULO_PROFISSIONAL"
    DECLARACAO = "DECLARACAO"
    PROCURACAO = "PROCURACAO"
    DOCUMENTO_SIGNATARIO = "DOCUMENTO_SIGNATARIO"
    GARANTIA_PROPOSTA = "GARANTIA_PROPOSTA"
    PROPOSTA_COMERCIAL = "PROPOSTA_COMERCIAL"
    PLANILHA_PRECOS = "PLANILHA_PRECOS"
    CRONOGRAMA = "CRONOGRAMA"
    COMPOSICAO = "COMPOSICAO"
    BDI = "BDI"
    OUTRO = "OUTRO"
    UNKNOWN = "UNKNOWN"


class ValidityStatus(StrEnum):
    VALID = "VALID"
    EXPIRED = "EXPIRED"
    EXPIRES_BEFORE_SUBMISSION = "EXPIRES_BEFORE_SUBMISSION"
    EXPIRES_BEFORE_CONTRACT = "EXPIRES_BEFORE_CONTRACT"
    EXPIRING_SOON = "EXPIRING_SOON"
    NO_EXPIRY = "NO_EXPIRY"
    EXPIRY_NOT_FOUND = "EXPIRY_NOT_FOUND"
    ISSUE_DATE_NOT_FOUND = "ISSUE_DATE_NOT_FOUND"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class MatchStatus(StrEnum):
    SATISFIED = "SATISFIED"
    PARTIALLY_SATISFIED = "PARTIALLY_SATISFIED"
    MISSING = "MISSING"
    EXPIRED = "EXPIRED"
    EXPIRING = "EXPIRING"
    INCONSISTENT = "INCONSISTENT"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"


class TechnicalMatch(StrEnum):
    EXACT_OBJECT_QUANTITY = "EXACT_OBJECT_QUANTITY"
    EXACT_SERVICE_PARTIAL_QUANTITY = "EXACT_SERVICE_PARTIAL_QUANTITY"
    COMPOSITE_SUMMABLE = "COMPOSITE_SUMMABLE"
    TEXTUAL_CANDIDATE = "TEXTUAL_CANDIDATE"
    UNIT_MISMATCH = "UNIT_MISMATCH"
    QUANTITY_INSUFFICIENT = "QUANTITY_INSUFFICIENT"
    PROFESSIONAL_MISMATCH = "PROFESSIONAL_MISMATCH"
    COMPANY_MISMATCH = "COMPANY_MISMATCH"
    AMBIGUOUS = "AMBIGUOUS"
    NO_MATCH = "NO_MATCH"
    NEEDS_ENGINEER_REVIEW = "NEEDS_ENGINEER_REVIEW"


class FindingSeverity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class FindingClass(StrEnum):
    MISSING_DOCUMENT = "MISSING_DOCUMENT"
    EXPIRED_DOCUMENT = "EXPIRED_DOCUMENT"
    EXPIRING_DOCUMENT = "EXPIRING_DOCUMENT"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    SIGNATORY_PROBLEM = "SIGNATORY_PROBLEM"
    TECHNICAL_GAP = "TECHNICAL_GAP"
    QUANTITY_GAP = "QUANTITY_GAP"
    UNIT_MISMATCH = "UNIT_MISMATCH"
    FINANCIAL_GAP = "FINANCIAL_GAP"
    DECLARATION_GAP = "DECLARATION_GAP"
    PROPOSAL_DIVERGENCE = "PROPOSAL_DIVERGENCE"
    GUARANTEE_GAP = "GUARANTEE_GAP"
    FORMAT_PROBLEM = "FORMAT_PROBLEM"
    DUPLICATE_DOCUMENT = "DUPLICATE_DOCUMENT"
    AMBIGUOUS_EVIDENCE = "AMBIGUOUS_EVIDENCE"
    EXTRACTION_FAILURE = "EXTRACTION_FAILURE"
    NEEDS_HUMAN = "NEEDS_HUMAN"


def digits_only(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch for ch in str(value) if ch.isdigit())


def normalize_legal_name(name: str | None) -> str:
    if not name:
        return ""
    s = str(name).upper().strip()
    for token in (
        "LTDA.",
        "LTDA",
        "S.A.",
        "S/A",
        "SA",
        "EIRELI",
        "ME",
        "EPP",
        "SOCIEDADE",
        "EMPRESARIA",
        "EMPRESÁRIA",
        "LIMITADA",
        ".",
        ",",
        "-",
        "/",
    ):
        s = s.replace(token, " ")
    while "  " in s:
        s = s.replace("  ", " ")
    return s.strip()


def names_equivalent(a: str | None, b: str | None) -> bool:
    """Abbreviation-tolerant legal name comparison (not fuzzy identity merge)."""
    na, nb = normalize_legal_name(a), normalize_legal_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # Token containment for abbreviated forms
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return False
    shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return shorter.issubset(longer)


def json_safe(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    return obj
