"""Root-CNPJ dedupe with optional independent decision-brand exception."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from scripts.linkage.keys import normalize_name

# Corporate suffixes stripped before brand comparison
_CORP_SUFFIXES = re.compile(
    r"\b(LTDA|EIRELI|S/?A|SA|ME|EPP|SPE|SS|S\/S|CIA|COMPANHIA|"
    r"CONSTRUTORA|CONSTRUCOES|CONSTRUCAO|ENGENHARIA|EMPREENDIMENTOS|"
    r"PARTICIPACOES|HOLDING|GROUP|GRUPO)\b",
    re.I,
)


def brand_core(name: str | None) -> str:
    """Normalize to brand core tokens for independent-brand detection."""
    n = normalize_name(name or "")
    n = _CORP_SUFFIXES.sub(" ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def brand_tokens(name: str | None) -> frozenset[str]:
    core = brand_core(name)
    return frozenset(t for t in core.split() if len(t) >= 3)


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


@dataclass(frozen=True)
class EntityKey:
    """Canonical entity key after root dedupe / independent-brand split."""

    cnpj_root: str
    brand_slug: str | None = None  # None = default root collapse

    @property
    def key(self) -> str:
        if self.brand_slug:
            return f"{self.cnpj_root}:{self.brand_slug}"
        return self.cnpj_root


def _slug(tokens: frozenset[str]) -> str:
    s = "-".join(sorted(tokens)[:4]).lower()
    s = re.sub(r"[^a-z0-9-]", "", s)
    return s[:48] or "brand"


def should_split_independent_brand(
    name_a: str | None,
    name_b: str | None,
    *,
    both_have_construction: bool,
    min_jaccard: float = 0.30,
) -> bool:
    """True only with explicit brand divergence + construction evidence on both.

    Same root, near-identical names (matriz/filial) → do NOT split.
    Distinct decision brands under same root → split.
    """
    if not both_have_construction:
        return False
    ta, tb = brand_tokens(name_a), brand_tokens(name_b)
    if not ta or not tb:
        return False
    # Require at least 2 distinctive tokens each to avoid noise
    if len(ta) < 1 or len(tb) < 1:
        return False
    sim = jaccard(ta, tb)
    if sim >= min_jaccard:
        return False
    # Additional guard: shared non-empty intersection of long tokens → keep together
    long_a = {t for t in ta if len(t) >= 5}
    long_b = {t for t in tb if len(t) >= 5}
    if long_a and long_b and long_a & long_b:
        return False
    return True


def entity_key_for_establishment(
    cnpj_root: str,
    razao_social: str | None,
    *,
    independent_brand: bool,
) -> EntityKey:
    if independent_brand:
        tokens = brand_tokens(razao_social)
        return EntityKey(cnpj_root=cnpj_root, brand_slug=_slug(tokens))
    return EntityKey(cnpj_root=cnpj_root, brand_slug=None)


def fold_accents(text: str) -> str:
    s = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def prefer_matriz_cnpj(establishments: list[dict[str, Any]]) -> str | None:
    """Prefer ordem 0001 (matriz) as representative cnpj14."""
    cnpjs = [str(e.get("cnpj14") or "") for e in establishments if e.get("cnpj14")]
    if not cnpjs:
        return None
    for c in sorted(cnpjs):
        if len(c) == 14 and c[8:12] == "0001":
            return c
    return sorted(cnpjs)[0]
