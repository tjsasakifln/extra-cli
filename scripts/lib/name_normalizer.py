"""Normalizacao de nomes de entes publicos — acentos, abreviacoes, pontuacao.

Uso:
    from scripts.lib.name_normalizer import normalize_name

    nome = normalize_name("SEC MUN DE EDUCACAO DE XANXERE")
    # => "SECRETARIA MUNICIPIO DE EDUCACAO DE XANXERE"

Funcionalidades:
    - Remocao de acentos via NFKD normalize
    - Uppercase consistente
    - Remocao de pontuacao e espacos extras
    - Expansao de abreviacoes comuns (SEC -> SECRETARIA, MUN -> MUNICIPIO, etc.)
    - Remocao de numeros de CNPJ soltos
    - Remocao de termos irrelevantes (opcional)
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

# ---------------------------------------------------------------------------
# Abbreviations dictionary — public administration in Brazil
# ---------------------------------------------------------------------------

ABBREVIATIONS: Final[dict[str, str]] = {
    "SEC": "SECRETARIA",
    "MUN": "MUNICIPIO",
    "FUNDO MUN": "FUNDO MUNICIPAL",
    "CAMARA": "CAMARA",
    "CM": "CAMARA MUNICIPAL",
    "FMS": "FUNDO MUNICIPAL DE SAUDE",
    "FME": "FUNDO MUNICIPAL DE EDUCACAO",
    "PM": "PREFEITURA MUNICIPAL",
    "GOV": "GOVERNO",
    "DEP": "DEPARTAMENTO",
    "DEPT": "DEPARTAMENTO",
    "ADM": "ADMINISTRACAO",
    "REG": "REGIONAL",
    "HOSP": "HOSPITAL",
    "UNIV": "UNIVERSIDADE",
    "INST": "INSTITUTO",
    "FUND": "FUNDACAO",
    "AUT": "AUTARQUIA",
    "CONS": "CONSORCIO",
}

# Sorted by length (longest first) so multi-word abbreviations match first
_ABBREV_SORTED: Final[list[tuple[str, str]]] = sorted(ABBREVIATIONS.items(), key=lambda x: -len(x[0]))

# ---------------------------------------------------------------------------
# Irrelevant terms that can be stripped from names
# ---------------------------------------------------------------------------

IRRELEVANT_TERMS: Final[list[str]] = [
    "CNPJ",
    "CPF",
    "END",
    "ENDERECO",
    "CEP",
    "FONE",
    "TELEFONE",
    "EMAIL",
    "SITE",
    "HTTP",
    "HTTPS",
    "WWW",
]


def _expand_abbreviations(name: str) -> str:
    """Expand known abbreviations using word-boundary regex replacement.

    Multi-word abbreviations (e.g. "FUNDO MUN") are matched before single-word
    ones to avoid partial expansions ("FUNDO MUNICIPIO" instead of
    "FUNDO MUNICIPAL").
    """
    for abbr, full in _ABBREV_SORTED:
        name = re.sub(r"\b" + re.escape(abbr) + r"\b", full, name)
    return name


def _remove_irrelevant_terms(name: str) -> str:
    """Remove common irrelevant terms (addresses, contact info, etc.)."""
    for term in IRRELEVANT_TERMS:
        name = re.sub(r"\b" + re.escape(term) + r"\b", "", name)
    return name


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalize_name(
    name: str,
    expand_abbreviations: bool = True,
    remove_irrelevant: bool = False,
) -> str:
    """Normaliza nome de ente publico para comparacao.

    Pipeline de normalizacao:
        1. NFKD normalize (remove acentos)
        2. Uppercase
        3. Remove pontuacao (mantem espacos)
        4. Remove numeros de CNPJ soltos (8-14 digitos)
        5. Collapse whitespace
        6. Expande abreviacoes (opcional, default True)
        7. Remove termos irrelevantes (opcional, default False)

    Args:
        name: Nome a ser normalizado.
        expand_abbreviations: Se True, expande abreviacoes do dicionario.
        remove_irrelevant: Se True, remove termos irrelevantes.

    Returns:
        String normalizada, ou string vazia se input for None/vazio.
    """
    if not name:
        return ""

    # 1. NFKD normalize — remove acentos
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ASCII", "ignore").decode("ASCII")

    # 2. Uppercase
    name = name.upper()

    # 3. Remove pontuacao (mantem espacos)
    name = re.sub(r"[^\w\s]", " ", name)

    # 4. Remove numeros de CNPJ soltos
    name = re.sub(r"\b\d{8,14}\b", "", name)

    # 5. Collapse whitespace
    name = " ".join(name.split())

    # 6. Expand abbreviations
    if expand_abbreviations:
        name = _expand_abbreviations(name)

    # 7. Remove irrelevant terms
    if remove_irrelevant:
        name = _remove_irrelevant_terms(name)
        name = " ".join(name.split())

    return name.strip()


def load_abbreviations_from_yaml(path: str | None = None) -> dict[str, str]:
    """Load abbreviations from YAML file (extends built-in dict).

    Args:
        path: Path to YAML file. Defaults to ``config/abbreviations.yaml``
              relative to project root.

    Returns:
        Updated abbreviations dict.

    The project-root-relative default path is resolved using the same heuristic
    as monitor.py (_PROJECT_ROOT).
    """
    if path is None:
        from pathlib import Path

        project_root = Path(__file__).resolve().parent.parent.parent
        path = str(project_root / "config" / "abbreviations.yaml")

    try:
        import yaml

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if isinstance(data, dict):
            merged = dict(ABBREVIATIONS)
            merged.update(data)
            return merged
    except (FileNotFoundError, ImportError):
        pass

    return dict(ABBREVIATIONS)
