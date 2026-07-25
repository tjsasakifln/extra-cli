"""Shared enums, constants and small helpers for edital case store."""

from __future__ import annotations

from typing import Any

DOCUMENT_TYPES = (
    "EDITAL",
    "TERMO_DE_REFERENCIA",
    "ESTUDO_TECNICO_PRELIMINAR",
    "PROJETO",
    "MEMORIAL_DESCRITIVO",
    "PLANILHA_ORCAMENTARIA",
    "CRONOGRAMA",
    "COMPOSICOES",
    "BDI",
    "MINUTA_CONTRATUAL",
    "MODELO_DECLARACAO",
    "ANEXO_TECNICO",
    "ANEXO_ADMINISTRATIVO",
    "AVISO",
    "ERRATA",
    "ESCLARECIMENTO",
    "IMPUGNACAO",
    "OUTRO",
    "UNKNOWN",
    "UNSUPPORTED",
)

CHECKLIST_STATUSES = (
    "SATISFIED",
    "RISK",
    "BLOCKER",
    "MISSING_EVIDENCE",
    "NOT_FOUND",
    "NOT_APPLICABLE",
    "NEEDS_HUMAN",
    "EXTRACTION_FAILED",
)

RECOMMENDATIONS = ("GO", "REVIEW", "NO_GO")

CONFLICT_CLASSES = (
    "CONFIRMED_CONFLICT",
    "POSSIBLE_CONFLICT",
    "FORMAT_VARIATION",
    "NOT_COMPARABLE",
)

# Expanded technical checklist (≥20, covers campaign §13)
CHECKLIST_ITEMS: list[tuple[str, str, str, bool]] = [
    # id, label, category, critical
    ("objeto_escopo", "Objeto e escopo da contratação", "administrativo", True),
    ("aderencia_perfil", "Aderência ao perfil operacional Extra", "administrativo", True),
    ("datas_horarios", "Datas e horários críticos", "prazo", True),
    ("esclarecimentos_impugnacoes", "Prazos de esclarecimentos e impugnações", "prazo", True),
    ("modalidade", "Modalidade licitatória", "administrativo", True),
    ("criterio_julgamento", "Critério de julgamento", "administrativo", True),
    ("modo_disputa", "Modo de disputa", "administrativo", False),
    ("condicoes_participacao", "Condições de participação", "juridico", True),
    ("consorcio", "Consórcio — permissão e condições", "juridico", False),
    ("subcontratacao", "Subcontratação — limites e vedações", "juridico", False),
    ("habilitacao_juridica", "Habilitação jurídica", "juridico", True),
    ("regularidade_fiscal", "Regularidade fiscal", "fiscal", True),
    ("regularidade_trabalhista", "Regularidade trabalhista (CNDT)", "trabalhista", True),
    ("qualificacao_economica", "Qualificação econômico-financeira", "economico-financeiro", True),
    ("capital_patrimonio", "Capital social / patrimônio líquido mínimo", "economico-financeiro", False),
    ("indices_economicos", "Índices econômicos (LG, SG, LC etc.)", "economico-financeiro", False),
    ("garantia_proposta", "Garantia de proposta", "garantia", False),
    ("garantia_contrato", "Garantia contratual", "garantia", False),
    ("qualificacao_tecnica_operacional", "Qualificação técnica operacional", "tecnico-operacional", True),
    ("qualificacao_tecnica_profissional", "Qualificação técnica profissional", "tecnico-profissional", True),
    ("atestados_cat_art", "Atestados, CAT, ART ou RRT", "tecnico-profissional", True),
    ("parcelas_relevancia", "Parcelas de maior relevância", "tecnico-operacional", False),
    ("quantitativos_minimos", "Quantitativos mínimos de atestação", "tecnico-operacional", False),
    ("visita_tecnica", "Visita técnica", "logistica", False),
    ("declaracoes_obrigatorias", "Declarações obrigatórias", "administrativo", False),
    ("formato_proposta", "Formato e validade da proposta", "proposta", True),
    ("orcamento_estimado", "Orçamento estimado e eventual sigilo", "orcamento", False),
    ("regime_execucao", "Regime de execução", "contrato", False),
    ("reajuste", "Reajuste / repactuação", "contrato", False),
    ("sancoes", "Sanções e multas", "contrato", False),
    ("riscos_contratuais", "Riscos contratuais relevantes", "contrato", True),
    ("inconsistencias", "Inconsistências e ambiguidades entre documentos", "administrativo", True),
    ("anexos_ausentes", "Anexos referidos e ausentes do pacote", "administrativo", True),
    ("prazo_execucao", "Prazo de execução e cronograma", "prazo", True),
    ("local_obra", "Local da obra/serviço e logística", "logistica", False),
    ("me_epp", "Tratamento ME/EPP e cotas", "juridico", False),
]

ANNEX_PATTERNS: list[tuple[str, str]] = [
    (r"anexo\s+[ivxlcdm0-9]+[a-z]?", "ANEXO"),
    (r"termo\s+de\s+refer[eê]ncia", "TERMO_DE_REFERENCIA"),
    (r"projeto\s+b[aá]sico", "PROJETO"),
    (r"projeto\s+executivo", "PROJETO"),
    (r"planilha\s+or[cç]ament[aá]ria", "PLANILHA_ORCAMENTARIA"),
    (r"cronograma\s+f[ií]sico[- ]?financeiro", "CRONOGRAMA"),
    (r"cronograma", "CRONOGRAMA"),
    (r"minuta\s+(do\s+)?contrato", "MINUTA_CONTRATUAL"),
    (r"modelo\s+de\s+proposta", "MODELO_DECLARACAO"),
    (r"composi[cç][aã]o\s+(do\s+)?bdi", "BDI"),
    (r"\bbdi\b", "BDI"),
    (r"memorial\s+descritivo", "MEMORIAL_DESCRITIVO"),
    (r"estudo\s+t[eé]cnico\s+preliminar", "ESTUDO_TECNICO_PRELIMINAR"),
    (r"modelo\s+de\s+declara[cç][aã]o", "MODELO_DECLARACAO"),
]

CLASSIFY_RULE_VERSION = "edital-classify-v1"

EXECUTABLE_EXTENSIONS = frozenset(
    {
        ".exe",
        ".bat",
        ".cmd",
        ".com",
        ".msi",
        ".dll",
        ".sh",
        ".bash",
        ".ps1",
        ".vbs",
        ".js",
        ".jar",
        ".scr",
        ".cpl",
        ".msi",
        ".app",
        ".dmg",
        ".so",
        ".dylib",
    }
)

SUPPORTED_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".docx",
        ".xlsx",
        ".xls",
        ".html",
        ".htm",
        ".txt",
        ".csv",
        ".md",
        ".json",
        ".xml",
        ".zip",
        ".odt",
        ".ods",
        ".rtf",
    }
)

# Safe ZIP limits
ZIP_MAX_FILES = 200
ZIP_MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024  # 200 MiB
ZIP_MAX_RATIO = 100  # uncompressed/compressed
ZIP_MAX_SINGLE_FILE = 80 * 1024 * 1024

SAFETY_FLAGS = {
    "production_touched": False,
    "soak_touched": False,
    "vps_accessed": False,
    "database_used": False,
}


def empty_evidence() -> dict[str, Any]:
    return {
        "document_id": None,
        "document_sha256": None,
        "page": None,
        "section": None,
        "paragraph": None,
        "cell": None,
        "locator": None,
        "excerpt": None,
        "analysis": None,
        "rule_id": None,
        "confidence": 0.0,
        "review_status": "PENDING",
    }
