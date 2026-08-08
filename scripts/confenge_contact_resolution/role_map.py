"""Map free-text cargo/função to role_class enum."""

from __future__ import annotations

import re
import unicodedata

from scripts.confenge_contact_resolution.models import RoleClass


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.lower()).strip()


# Ordered rules: first match wins.
# Use stem prefixes (no trailing \b on stems) so "licitacoes" matches "licitac".
# Prefer domain function (contratos/licitacoes/…) over bare hierarchy titles when both appear.
_RULES: list[tuple[re.Pattern[str], str]] = [
    # Domain roles first (more specific than "diretor")
    (
        re.compile(
            r"\b(licitac\w*|pregao\w*|preg[aã]o\w*|edital(?:es)?|"
            r"captacao\w*|capta[cç][aã]o de contratos)"
        ),
        RoleClass.LICITACOES.value,
    ),
    (
        re.compile(
            r"\b(contratos?\b|aditivo\w*|reajuste\w*|reequil\w*|"
            r"medi[cç][aã]o contratual)"
        ),
        RoleClass.CONTRATOS.value,
    ),
    (
        re.compile(
            r"\b(engenh\w*|or[cç]ament\w*|medi[cç][aã]o(?:es)?\b|"
            r"obras?\b|fiscal de obra|projetista\w*)"
        ),
        RoleClass.ENGENHARIA.value,
    ),
    (
        re.compile(
            r"\b(financeir\w*|controller\b|contab\w*|tesourar\w*|"
            r"cobranca\w*|cobran[cç]a\w*|faturamento\w*)"
        ),
        RoleClass.FINANCEIRO.value,
    ),
    (
        re.compile(
            r"\b(comercial\w*|vendas?\b|sales\b|business development|"
            r"relacionamento\b|account\b)"
        ),
        RoleClass.COMERCIAL.value,
    ),
    (
        re.compile(
            r"\b(propriet\w*|s[oó]cios?\b|socio\b|dono\b|owner\b|"
            r"fundador\w*|\bmei\b)"
        ),
        RoleClass.OWNER.value,
    ),
    (
        re.compile(
            r"\b(diretor\w*|diretoria\b|ceo\b|cto\b|cfo\b|presidente\b|"
            r"vp\b|vice[- ]presidente\b|superintendente\w*)"
        ),
        RoleClass.DIRETORIA.value,
    ),
]


def map_role_class(cargo: str | None, *, name_hint: str | None = None) -> str:
    """Return role_class from cargo text; generic if unknown.

    Absence of cargo → generic. Never invents a decision-maker title.
    """
    text = " ".join(x for x in (cargo or "", name_hint or "") if x)
    if not text.strip():
        return RoleClass.GENERIC.value
    folded = _fold(text)
    for pat, role in _RULES:
        if pat.search(folded):
            return role
    return RoleClass.GENERIC.value


def is_small_firm_porte(porte: str | None, *, mei: bool | None = None) -> bool:
    """Heuristic: ME/EPP/MEI or explicit small size codes → small firm ranking bias."""
    if mei is True:
        return True
    if not porte:
        return False
    p = _fold(str(porte))
    if p in {"05", "5", "demais", "grande"}:
        return False
    if any(x in p for x in ("mei", "epp", "micro", "pequeno", " me", "me ")):
        return True
    if p in {"01", "02", "03", "me"}:
        return True
    return False
