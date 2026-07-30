"""Art. 117 — technical support to fiscal/gestor without substituting public powers."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any

from scripts.public_agency import FISCAL_SUPPORT_PREFERRED

# Phrases that assign exclusive public-agent powers to CONFENGE
EXCLUSIVE_POWER_PATTERNS: tuple[str, ...] = (
    "DETERMINACAO ADMINISTRATIVA EXCLUSIVA",
    "APLICACAO DE SANCOES",
    "APLICAR SANCAO",
    "APLICAR SANÇÕES",
    "AUTORIZACAO DE PAGAMENTO",
    "AUTORIZAR PAGAMENTO",
    "ORDEM ADMINISTRATIVA EM NOME DO ORGAO",
    "ORDENS ADMINISTRATIVAS EM NOME",
    "RECEBIMENTO DEFINITIVO",
    "DECISAO SOBRE ADITIVOS",
    "DECIDIR ADITIVOS",
    "HOMOLOGACAO",
    "HOMOLOGAR",
    "ADJUDICACAO",
    "ADJUDICAR",
    "APROVACAO JURIDICA",
    "ASSINATURA COMO AUTORIDADE PUBLICA",
    "SUBSTITUIR O FISCAL",
    "SUBSTITUI O FISCAL",
    "SUBSTITUICAO DO FISCAL",
    "ATUAR COMO FISCAL",
    "EXERCER A FISCALIZACAO EXCLUSIVA",
)

ALLOWED_SUPPORT_PHRASES: tuple[str, ...] = (
    "ASSISTIR",
    "SUBSIDIAR",
    "APOIO TECNICO",
    "INSPECAO TECNICA",
    "CONFERIR MEDICOES",
    "CONFERIR MEDIÇÕES",
    "RELATORIO",
    "REGISTRAR EVIDENCIAS",
    "ANALISAR CRONOGRAMA",
    "NAO CONFORMIDADE",
    "AVALIAR TECNICAMENTE",
    "SUBSIDIO PARA",
    "PARECER TECNICO",
    "NOTA TECNICA",
    "INDICADORES FISICOS E FINANCEIROS",
)


def _fold(text: str | None) -> str:
    s = unicodedata.normalize("NFKD", text or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.upper()).strip()


@dataclass
class FiscalLanguageCheck:
    allowed: bool
    preferred_expression: str = FISCAL_SUPPORT_PREFERRED
    blocked_phrases: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    supervision_term_used: bool = False
    supervision_term_ok: bool = False
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def check_commercial_text(
    text: str | None,
    *,
    supervision_object_matches: bool = False,
    responsibilities_delimited: bool = False,
    no_fiscal_substitution: bool = True,
    documents_explain_distinction: bool = False,
) -> FiscalLanguageCheck:
    blob = _fold(text)
    blocked: list[str] = []
    for pat in EXCLUSIVE_POWER_PATTERNS:
        if pat in blob:
            blocked.append(pat)

    supervision = "SUPERVISAO DE OBRAS" in blob or "SUPERVISÃO DE OBRAS" in _fold(text)
    supervision_ok = False
    warnings: list[str] = []
    if supervision:
        supervision_ok = (
            supervision_object_matches
            and responsibilities_delimited
            and no_fiscal_substitution
            and documents_explain_distinction
        )
        if not supervision_ok:
            warnings.append(
                "Expressão 'supervisão de obras' exige delimitação de responsabilidades "
                "e não substituição do fiscal público."
            )
            if not supervision_object_matches:
                blocked.append("SUPERVISAO_DE_OBRAS_SEM_DELIMITACAO")

    allowed = len(blocked) == 0
    notes = (
        f"Preferir: '{FISCAL_SUPPORT_PREFERRED}'. "
        "CONFENGE assiste e subsidia; não substitui fiscal/gestor (art. 117)."
    )
    return FiscalLanguageCheck(
        allowed=allowed,
        blocked_phrases=blocked,
        warnings=warnings,
        supervision_term_used=supervision,
        supervision_term_ok=supervision_ok,
        notes=notes,
    )


def sanitize_offer_text(text: str) -> str:
    """Replace risky fiscal-substitution wording with preferred support language."""
    out = text
    replacements = [
        (r"(?i)substituir\s+o\s+fiscal", "apoiar tecnicamente o fiscal"),
        (r"(?i)atuar\s+como\s+fiscal", "prestar apoio técnico à fiscalização"),
        (r"(?i)autorizar\s+pagamentos?", "subsidiar a conferência de medições"),
        (r"(?i)aplicar\s+san[cç][oõ]es", "apontar não conformidades tecnicamente"),
        (r"(?i)homologar", "subsidiar tecnicamente a análise para homologação pelo órgão"),
    ]
    for pat, rep in replacements:
        out = re.sub(pat, rep, out)
    return out
