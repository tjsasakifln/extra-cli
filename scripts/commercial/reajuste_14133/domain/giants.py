"""Detect large national construction groups (broader than a few hardcodes)."""

from __future__ import annotations

import re
import unicodedata

# Major groups / large EPC — low consulting fit for CONFENGE SME reajuste product
_GIANT_PATTERNS: tuple[str, ...] = (
    r"\boderbrecht\b",
    r"\bnovonor\b",
    r"\boas\b",
    r"\bcamargo\s*corr[eê]a\b",
    r"\bmover\s+participa",
    r"\bandrade\s+gutierrez\b",
    r"\bqueiroz\s+galv[aã]o\b",
    r"\bconstrutora\s+norberto\b",
    r"\bgalv[aã]o\s+engenharia\b",
    r"\bmendes\s+j[uú]nior\b",
    r"\bmendes\s+junior\b",
    r"\bengevix\b",
    r"\bdelta\s+constru[cç]",
    r"\burban\s+sa\b",
    r"\bccr\b",
    r"\becorodovias\b",
    r"\bartesp\b",  # often concession context
    r"\bconcession[aá]ria\b",
    r"\bcons[oó]rcio\s+[a-z].{0,40}(infra|rodov|metro)",
    r"\bacs\s+group\b",
    r"\bcimic\b",
    r"\bsacyr\b",
    r"\bferrovial\b",
    r"\bohl\b",
    r"\bhtep\b",
    r"\bconstrucap\b",
    r"\brizzani\b",
    r"\bmethod\s+engenharia\b",
    r"\bhtb\b",
    r"\bcarioca\s+engenharia\b",
    r"\bcarioca\s+christiani\b",
    r"\bskc\b",
    r"\begesa\b",
    r"\bserveng\b",
    r"\btribuna\s+engenharia\b",
    r"\bembraer\b",
    r"\bembraco[l]?\b",
    r"\bpetrobras\b",
    r"\bvale\s+s\.?a\.?\b",
    r"\bcrrc\b",
    r"\bcrrc\b",
)


def _norm(name: str | None) -> str:
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.lower()


def is_giant_low_consulting_fit(
    razao_social: str | None,
    *,
    valor_contrato: float | None = None,
    cnae: str | None = None,
    is_aggregate_portfolio: bool = False,
) -> bool:
    """Heuristic: large national groups / concessions — keep as intelligence, not primary outreach.

    ``valor_contrato`` must be a **single instrument** value. Never pass summed portfolio
    totals (``is_aggregate_portfolio=True`` disables the billion-scale name heuristic).
    """
    del cnae  # reserved for future porte integration
    n = _norm(razao_social)
    if not n:
        return False
    for pat in _GIANT_PATTERNS:
        if re.search(pat, n, re.I):
            return True
    # Billion-scale single contract + SA engineering name → low consulting fit signal
    if not is_aggregate_portfolio and valor_contrato is not None and valor_contrato >= 1_000_000_000:
        if re.search(r"\bs\.?a\.?\b|\bs/a\b", n) and re.search(r"constru|engenharia|infra|rodov|concess", n):
            return True
    return False


def is_sme_regional_fit(
    razao_social: str | None,
    *,
    valor_contrato: float | None = None,
    uf: str | None = None,
) -> bool:
    """Prefer small/medium regional constructors in commercial ranking."""
    if is_giant_low_consulting_fit(razao_social, valor_contrato=valor_contrato):
        return False
    if valor_contrato is not None and (valor_contrato < 5_000_000 or valor_contrato > 300_000_000):
        return False
    return True
