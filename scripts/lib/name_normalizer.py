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
    - Deteccao de abreviacoes nao reconhecidas (para expansao futura)
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
# Siglas dictionary — loaded from config/abbreviations.yaml
# ---------------------------------------------------------------------------

_SIGLAS: dict[str, str] = {}
_SIGLAS_LOADED: bool = False


def _load_siglas() -> dict[str, str]:
    """Load siglas from config/abbreviations.yaml (``siglas`` section).

    Returns:
        Dict of sigla -> full name.
    """
    global _SIGLAS, _SIGLAS_LOADED
    if _SIGLAS_LOADED:
        return _SIGLAS

    try:
        from pathlib import Path

        project_root = Path(__file__).resolve().parent.parent.parent
        path = project_root / "config" / "abbreviations.yaml"

        import yaml

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if isinstance(data, dict) and "siglas" in data:
            siglas_raw = data["siglas"]
            if isinstance(siglas_raw, dict):
                _SIGLAS = {k.upper().strip(): v.upper().strip() for k, v in siglas_raw.items()}
    except (FileNotFoundError, ImportError, Exception):
        import logging

        logging.getLogger(__name__).warning("Failed to load siglas config, using defaults", exc_info=True)

    _SIGLAS_LOADED = True
    return _SIGLAS


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


def _expand_siglas(name: str) -> str:
    """Expand known siglas separately from abbreviations.

    Siglas are longer acronyms (3-6 chars) from ``config/abbreviations.yaml``
    that represent specific public entities.  Applied after abbreviation
    expansion to avoid conflicts.
    """
    siglas = _load_siglas()
    # Sort by length descending for greedy matching
    for sigla, full in sorted(siglas.items(), key=lambda x: -len(x[0])):
        name = re.sub(r"\b" + re.escape(sigla) + r"\b", full, name)
    return name


def _remove_irrelevant_terms(name: str) -> str:
    """Remove common irrelevant terms (addresses, contact info, etc.)."""
    for term in IRRELEVANT_TERMS:
        name = re.sub(r"\b" + re.escape(term) + r"\b", "", name)
    return name


# ---------------------------------------------------------------------------
# Unknown abbreviation detection
# ---------------------------------------------------------------------------

_ABBREVIATION_PATTERN: Final[re.Pattern] = re.compile(r"\b([A-Z]{2,6})\b")
"""Regex for potential abbreviations (2-6 uppercase letters)."""


def find_unknown_abbreviations(
    text: str,
    known_set: set[str] | None = None,
) -> list[str]:
    """Find potential abbreviations in text that are not in the known set.

    Detects tokens of 2-6 uppercase letters that look like abbreviations
    but are not in the known abbreviations/siglas dictionary.

    Args:
        text: Input text (already upper-cased and normalized).
        known_set: Optional set of known abbreviations.  Defaults to
                   ``set(ABBREVIATIONS) | set(_load_siglas())``.

    Returns:
        Sorted list of unknown abbreviation tokens found (unique).
    """
    if known_set is None:
        known_set = set(ABBREVIATIONS.keys()) | set(_load_siglas().keys())

    # Also treat common Portuguese words as known to reduce noise
    _common_words: set[str] = {
        "DE",
        "DA",
        "DO",
        "DAS",
        "DOS",
        "E",
        "A",
        "O",
        "EM",
        "COM",
        "SEM",
        "PARA",
        "POR",
        "NA",
        "NO",
        "NAS",
        "NOS",
        "UM",
        "UMA",
        "SE",
        "AO",
        "AOS",
        "PELA",
        "PELO",
        "PELAS",
        "PELOS",
    }
    known_set = known_set | _common_words

    found: set[str] = set()
    for match in _ABBREVIATION_PATTERN.finditer(text):
        token = match.group(1)
        if token not in known_set:
            found.add(token)

    return sorted(found)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalize_name(
    name: str,
    expand_abbreviations: bool = True,
    remove_irrelevant: bool = False,
    expand_siglas: bool = True,
) -> str:
    """Normaliza nome de ente publico para comparacao.

    Pipeline de normalizacao:
        1. NFKD normalize (remove acentos)
        2. Uppercase
        3. Remove pontuacao (mantem espacos)
        4. Remove numeros de CNPJ soltos (8-14 digitos)
        5. Collapse whitespace
        6. Expande abreviacoes (opcional, default True)
        7. Expande siglas da administracao publica (opcional, default True)
        8. Remove termos irrelevantes (opcional, default False)

    Args:
        name: Nome a ser normalizado.
        expand_abbreviations: Se True, expande abreviacoes do dicionario.
        remove_irrelevant: Se True, remove termos irrelevantes.
        expand_siglas: Se True, expande siglas carregadas de
                       ``config/abbreviations.yaml``.

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

    # 7. Expand siglas
    if expand_siglas:
        name = _expand_siglas(name)

    # 8. Remove irrelevant terms
    if remove_irrelevant:
        name = _remove_irrelevant_terms(name)
        name = " ".join(name.split())

    return name.strip()


def load_abbreviations_from_yaml(path: str | None = None) -> dict[str, str]:
    """Load abbreviations from YAML file (extends built-in dict).

    Also loads the ``siglas`` section and merges it into the abbreviations
    dict so both are available as a single flat dictionary.

    Args:
        path: Path to YAML file. Defaults to ``config/abbreviations.yaml``
              relative to project root.

    Returns:
        Updated abbreviations dict (including siglas).

    The project-root-relative default path is resolved using the same heuristic
    as monitor.py (_PROJECT_ROOT).
    """
    if path is None:
        from pathlib import Path

        project_root = Path(__file__).resolve().parent.parent.parent
        path = str(project_root / "config" / "abbreviations.yaml")

    merged = dict(ABBREVIATIONS)
    try:
        import yaml

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if isinstance(data, dict):
            # Load abbreviations (top-level key-value pairs)
            for k, v in data.items():
                if k != "siglas" and isinstance(k, str) and isinstance(v, str):
                    merged[k.upper().strip()] = v.upper().strip()

            # Load siglas subsection
            if "siglas" in data and isinstance(data["siglas"], dict):
                for k, v in data["siglas"].items():
                    merged[k.upper().strip()] = v.upper().strip()
    except (FileNotFoundError, ImportError):
        pass

    return merged
