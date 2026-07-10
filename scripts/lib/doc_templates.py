#!/usr/bin/env python3
"""
Templates de Extração Estruturada — extrai campos tipados de documentos de licitação.

Cada tipo de documento (Edital, Termo de Referência, Planilha Orçamentária)
tem um template com padrões regex específicos para extrair informações
estruturadas, em vez de depender apenas de texto bruto.

Usage:
    from lib.doc_templates import extract_structured, DocType
    result = extract_structured(text, DocType.EDITAL)
    print(result["habilitacao"])  # {"found": True, "value": "..."}
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ============================================================
# DOCUMENT TYPES
# ============================================================


class DocType(str, Enum):
    EDITAL = "edital"
    TERMO_REFERENCIA = "termo_referencia"
    PLANILHA = "planilha"
    UNKNOWN = "unknown"


def detect_doc_type(titulo: str, filename: str = "") -> DocType:
    """Detect document type from title/filename."""
    t = (titulo + " " + filename).lower()
    if any(kw in t for kw in ("edital", "aviso", "pregao", "concorrencia")):
        return DocType.EDITAL
    if any(kw in t for kw in ("termo de referencia", "termo_referencia", "tr ", "projeto basico")):
        return DocType.TERMO_REFERENCIA
    if any(kw in t for kw in ("planilha", "orcamento", "bdi", "composicao", "quantitativo")):
        return DocType.PLANILHA
    return DocType.UNKNOWN


# ============================================================
# EXTRACTION PATTERNS
# ============================================================


@dataclass
class ExtractedField:
    """Result of extracting one field from document text."""
    found: bool = False
    value: str = ""
    raw_match: str = ""
    confidence: float = 0.0  # 0-1 confidence in extraction quality


@dataclass
class StructuredExtraction:
    """Complete structured extraction from a document."""
    doc_type: DocType = DocType.UNKNOWN
    fields: dict[str, ExtractedField] = field(default_factory=dict)
    total_fields: int = 0
    found_fields: int = 0

    @property
    def completeness_pct(self) -> float:
        if self.total_fields == 0:
            return 0.0
        return round(self.found_fields / self.total_fields * 100, 1)

    def get(self, key: str, default: str = "Nao consta no edital disponivel") -> str:
        f = self.fields.get(key)
        if f and f.found:
            return f.value
        return default


# ============================================================
# PATTERN LIBRARY — EDITAL
# ============================================================

# Each pattern: (field_name, [regex patterns], post_processor)

_EDITAL_PATTERNS: list[tuple[str, list[str], str | None]] = [
    (
        "patrimonio_liquido",
        [
            r"patrim[oô]nio\s+l[ií]quido\s+(?:m[ií]nimo\s+)?(?:de\s+)?(?:R\$\s*)?([0-9.,]+)",
            r"PL\s+m[ií]nimo\s+(?:de\s+)?(?:R\$\s*)?([0-9.,]+)",
            r"(?:10|cinco|dez)\s*%\s*(?:do\s+valor|da\s+contrata[cç][aã]o)",
            r"qualifica[cç][aã]o\s+econ[oô]mica[^.]*patrim[oô]nio[^.]*",
        ],
        None,
    ),
    (
        "acervo_tecnico",
        [
            r"acervo\s+t[eé]cnico[^.]*(?:CAT|atestado)[^.]*",
            r"atestado\s+de\s+capacidade\s+t[eé]cnica[^.]*",
            r"CAT\s+(?:emitid[ao]|registrad[ao])\s+(?:pel[ao]\s+)?(?:CREA|CAU)[^.]*",
            r"capacidade\s+t[eé]cnico[^.]*profissional[^.]*",
        ],
        None,
    ),
    (
        "garantia_proposta",
        [
            r"garantia\s+(?:de\s+)?proposta[^.]*(?:\d+%|R\$\s*[0-9.,]+)[^.]*",
            r"cau[cç][aã]o[^.]*(?:\d+%|R\$\s*[0-9.,]+)[^.]*",
            r"seguro[- ]garantia[^.]*(?:\d+%|R\$\s*[0-9.,]+)[^.]*",
            r"garantia\s+(?:contratual|de\s+execu[cç][aã]o)[^.]*(?:\d+%)[^.]*",
        ],
        None,
    ),
    (
        "visita_tecnica",
        [
            r"visita\s+t[eé]cnica\s+(?:ser[aá]\s+)?obrigat[oó]ria[^.]*",
            r"visita\s+t[eé]cnica\s+(?:ser[aá]\s+)?facultativa[^.]*",
            r"vistoria[^.]*(?:obrigat[oó]ria|facultativa)[^.]*",
            r"visita\s+(?:ao\s+local|t[eé]cnica)[^.]*(?:at[eé]\s+\d{2}/\d{2}/\d{4})[^.]*",
        ],
        None,
    ),
    (
        "prazo_execucao",
        [
            r"prazo\s+(?:de\s+)?execu[cç][aã]o[^.]*?(\d+)\s*(?:meses|dias\s+(?:corridos|[uú]teis))[^.]*",
            r"prazo\s+(?:de\s+)?(?:vig[eê]ncia|execu[cç][aã]o)\s*(?:de\s+|:?\s*)?(\d+)\s*(?:meses|dias)",
            r"(\d+)\s*(?:meses|dias\s+corridos)\s*(?:a\s+partir|contados?\s+d[aoe])",
        ],
        None,
    ),
    (
        "data_sessao",
        [
            r"sess[aã]o\s+p[uú]blica[^.]*?(\d{2}/\d{2}/\d{4})\s*(?:[àa]s?\s*)?(\d{1,2}[h:]\d{2})?",
            r"data\s+(?:da\s+)?(?:disputa|abertura)[^.]*?(\d{2}/\d{2}/\d{4})\s*(?:[àa]s?\s*)?(\d{1,2}[h:]\d{2})?",
            r"abertura\s+(?:das\s+)?propostas[^.]*?(\d{2}/\d{2}/\d{4})",
        ],
        None,
    ),
    (
        "prazo_proposta",
        [
            r"(?:limite|prazo)\s+(?:para\s+)?(?:envio|encaminhamento|apresenta[cç][aã]o)\s+(?:d[aoe]s?\s+)?propostas[^.]*?(\d{2}/\d{2}/\d{4})\s*(?:[àa]s?\s*)?(\d{1,2}[h:]\d{2})?",
            r"propostas\s+(?:at[eé]|encerr[^.]*?)\s*(\d{2}/\d{2}/\d{4})\s*(?:[àa]s?\s*)?(\d{1,2}[h:]\d{2})?",
        ],
        None,
    ),
    (
        "criterio_julgamento",
        [
            r"crit[eé]rio\s+de\s+julgamento[^.]*?(menor\s+pre[cç]o|t[eé]cnica\s+e\s+pre[cç]o|maior\s+desconto)",
            r"tipo\s+de\s+licita[cç][aã]o[^.]*?(menor\s+pre[cç]o|t[eé]cnica\s+e\s+pre[cç]o|maior\s+desconto)",
            r"julgamento[^.]*?(menor\s+pre[cç]o\s+(?:global|por\s+(?:item|lote)))",
        ],
        None,
    ),
    (
        "regime_execucao",
        [
            r"regime\s+de\s+execu[cç][aã]o[^.]*?(empreitada\s+(?:por\s+pre[cç]o\s+)?(?:global|unit[aá]ri[ao])|pre[cç]o\s+unit[aá]rio|semi[- ]integrada|integrada|parcelada)",
            r"empreitada\s+(?:por\s+pre[cç]o\s+)?(global|unit[aá]ri[ao])",
        ],
        None,
    ),
    (
        "consorcio",
        [
            r"cons[oó]rcio[^.]*?(permitid[ao]|vedado|n[aã]o\s+(?:ser[aá]\s+)?permitid[ao])",
            r"(?:veda[cç][aã]o|proibi[cç][aã]o)\s+(?:de\s+)?cons[oó]rcio",
            r"(?:admitid[ao]|autorizado)\s+(?:a\s+)?(?:participa[cç][aã]o\s+)?(?:em\s+)?cons[oó]rcio",
        ],
        None,
    ),
    (
        "exclusividade_me_epp",
        [
            r"exclusiv[ao]\s+(?:para\s+)?(?:ME|EPP|micro\s*empresa|empresa\s+de\s+pequeno)",
            r"(?:LC|Lei\s+Complementar)\s+123[^.]*(?:exclusiv|reserv|cota)",
            r"cota\s+reservada[^.]*?(\d+%)",
            r"(?:n[aã]o\s+)?exclusiv[ao]\s+(?:para\s+)?(?:ME|EPP)",
        ],
        None,
    ),
    (
        "plataforma",
        [
            r"(?:plataforma|sistema|portal)[^.]*?(BNC|BLL|BBMNET|ComprasGov|Compras\.gov|Portal\s+de\s+Compras|Licit[aA]net|Bolsa\s+Nacional)",
            r"(?:www\.|https?://)[^.\s]*(?:bnc|bll|bbmnet|comprasgovernamentais|portaldecompraspublicas|licitanet)",
        ],
        None,
    ),
]


# ============================================================
# PATTERN LIBRARY — TERMO DE REFERÊNCIA
# ============================================================

_TR_PATTERNS: list[tuple[str, list[str], str | None]] = [
    (
        "escopo_tecnico",
        [
            r"(?:descri[cç][aã]o|especifica[cç][aã]o)\s+t[eé]cnica[^.]*(?:\.|$)",
            r"escopo\s+(?:do\s+)?(?:servico|trabalho|obra)[^.]*",
            r"objeto\s+(?:do\s+)?(?:termo|presente)[^.]*",
        ],
        None,
    ),
    (
        "quantitativos",
        [
            r"(?:quantitativo|metragem|[aá]rea)[^.]*?(\d+[.,]?\d*)\s*(?:m[²2]|metros?\s+(?:quadrados|lineares)|ha|km)",
            r"(\d+[.,]?\d*)\s*(?:unidades|und|pç|peças)",
        ],
        None,
    ),
    (
        "bdi",
        [
            r"BDI[^.]*?(\d+[.,]\d+)\s*%",
            r"(?:bonifica[cç][aã]o|despesas\s+indiretas)[^.]*?(\d+[.,]\d+)\s*%",
        ],
        None,
    ),
    (
        "prazo_execucao",
        _EDITAL_PATTERNS[4][1],  # Reuse edital patterns
        None,
    ),
    (
        "cronograma",
        [
            r"cronograma[^.]*(?:f[ií]sico|financeiro|execu[cç][aã]o)[^.]*",
            r"etapa\s+\d+[^.]*(?:meses?|dias?|semanas?)[^.]*",
        ],
        None,
    ),
    (
        "equipe_tecnica",
        [
            r"equipe\s+t[eé]cnica[^.]*(?:engenheiro|arquiteto|t[eé]cnico)[^.]*",
            r"(?:respons[aá]vel\s+t[eé]cnico|RT)[^.]*(?:CREA|CAU)[^.]*",
        ],
        None,
    ),
]


# ============================================================
# PATTERN LIBRARY — PLANILHA ORÇAMENTÁRIA
# ============================================================

_PLANILHA_PATTERNS: list[tuple[str, list[str], str | None]] = [
    (
        "valor_total",
        [
            r"(?:valor\s+)?total\s+(?:geral|global|da\s+obra)?[^.]*?R\$\s*([0-9.,]+)",
            r"total[^.]*?R\$\s*([0-9.,]+)",
        ],
        None,
    ),
    (
        "bdi",
        [
            r"BDI[^.]*?(\d+[.,]\d+)\s*%",
            r"taxa\s+de\s+BDI[^.]*?(\d+[.,]\d+)",
        ],
        None,
    ),
    (
        "num_itens",
        [
            r"item\s+(\d+)",
        ],
        "count",  # Count matches instead of extracting
    ),
    (
        "encargos_sociais",
        [
            r"encargos\s+sociais[^.]*?(\d+[.,]\d+)\s*%",
            r"leis\s+sociais[^.]*?(\d+[.,]\d+)\s*%",
        ],
        None,
    ),
]


# ============================================================
# EXTRACTION ENGINE
# ============================================================

_PATTERN_MAP: dict[DocType, list[tuple[str, list[str], str | None]]] = {
    DocType.EDITAL: _EDITAL_PATTERNS,
    DocType.TERMO_REFERENCIA: _TR_PATTERNS,
    DocType.PLANILHA: _PLANILHA_PATTERNS,
}


def _search_pattern(text: str, patterns: list[str]) -> tuple[bool, str, str, float]:
    """Search text for any of the given patterns. Returns (found, value, raw, confidence)."""
    for i, pattern in enumerate(patterns):
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            raw = match.group(0)
            # Extract the most specific group
            value = match.group(1) if match.lastindex and match.lastindex >= 1 else raw
            # Clean up
            value = re.sub(r"\s+", " ", value.strip())
            # Confidence: earlier patterns = more specific = higher confidence
            confidence = 1.0 - (i * 0.15)
            return True, value, raw[:500], max(0.3, confidence)
    return False, "", "", 0.0


def extract_structured(
    text: str,
    doc_type: DocType | str,
    max_context: int = 2000,
) -> StructuredExtraction:
    """
    Extract structured fields from document text using regex templates.

    Args:
        text: Document text (full or truncated)
        doc_type: Type of document (edital, termo_referencia, planilha)
        max_context: Max chars to keep in raw_match for context

    Returns:
        StructuredExtraction with found/not-found fields
    """
    if isinstance(doc_type, str):
        try:
            doc_type = DocType(doc_type)
        except ValueError:
            doc_type = DocType.UNKNOWN

    patterns = _PATTERN_MAP.get(doc_type, _EDITAL_PATTERNS)
    result = StructuredExtraction(doc_type=doc_type, total_fields=len(patterns))

    for field_name, field_patterns, processor in patterns:
        if processor == "count":
            # Count occurrences instead of extracting
            total = 0
            for p in field_patterns:
                total += len(re.findall(p, text, re.IGNORECASE))
            result.fields[field_name] = ExtractedField(
                found=total > 0,
                value=str(total) if total > 0 else "",
                confidence=0.8 if total > 0 else 0.0,
            )
        else:
            found, value, raw, confidence = _search_pattern(text, field_patterns)
            result.fields[field_name] = ExtractedField(
                found=found,
                value=value,
                raw_match=raw[:max_context],
                confidence=confidence,
            )

        if result.fields[field_name].found:
            result.found_fields += 1

    return result


def extract_all_types(text: str) -> dict[str, StructuredExtraction]:
    """Run extraction for all document types and return the best match."""
    results: dict[str, StructuredExtraction] = {}
    best_type = DocType.UNKNOWN
    best_completeness = 0.0

    for dt in [DocType.EDITAL, DocType.TERMO_REFERENCIA, DocType.PLANILHA]:
        ext = extract_structured(text, dt)
        results[dt.value] = ext
        if ext.completeness_pct > best_completeness:
            best_completeness = ext.completeness_pct
            best_type = dt

    results["_best_type"] = best_type.value  # type: ignore[assignment]
    return results


def merge_extractions(extractions: list[StructuredExtraction]) -> dict[str, ExtractedField]:
    """
    Merge multiple extractions from different documents of the same edital.
    Keeps the highest-confidence extraction for each field.
    """
    merged: dict[str, ExtractedField] = {}

    for ext in extractions:
        for field_name, field_data in ext.fields.items():
            if not field_data.found:
                continue
            existing = merged.get(field_name)
            if existing is None or field_data.confidence > existing.confidence:
                merged[field_name] = field_data

    return merged
