"""Forbidden-claim scanner. Tokens are split so this file is not itself a hit."""

from __future__ import annotations

import re
from typing import Any


def _claim_patterns() -> tuple[re.Pattern[str], ...]:
    # Concatenate so source does not contain contiguous forbidden copy.
    tokens = (
        "habi" + "litado",
        "habi" + "litada",
        "inab" + "ilitado",
        "inab" + "ilitada",
        "inexe" + "quivel",
        "inexe" + "quível",
        "ile" + "gal",
        "chance de vi" + "toria",
        "chance de vi" + "tória",
        "parecer jur" + "idico",
        "parecer jur" + "ídico",
        "ready_to_sub" + "mit",
        "proposta apro" + "vada",
        "garantia acei" + "ta",
    )
    joined = "|".join(re.escape(token) for token in tokens)
    return (re.compile(rf"\b(?:{joined})\b", re.IGNORECASE),)


def _bdi_correctness() -> re.Pattern[str]:
    return re.compile(
        r"\bbdi\s+(correto|incorreto|certo|errado)\b",
        re.IGNORECASE,
    )


def _autonomous_action() -> re.Pattern[str]:
    return re.compile(
        r"\b(recomenda-se\s+(participar|impugnar)|participar\s+autonomamente|"
        r"impugnar\s+imediatamente)\b",
        re.IGNORECASE,
    )


def _completeness_without_denom() -> re.Pattern[str]:
    return re.compile(
        r"\b(cobertura completa|100%\s+completo|todos os requisitos atendidos|"
        r"edital integralmente coberto)\b",
        re.IGNORECASE,
    )


_PATTERNS = _claim_patterns()
_BDI = _bdi_correctness()
_ACTION = _autonomous_action()
_COMPLETE = _completeness_without_denom()


def scan_forbidden_claims(text: str) -> list[str]:
    hits: list[str] = []
    blob = text or ""
    for pattern in _PATTERNS:
        hits.extend(match.group(0) for match in pattern.finditer(blob))
    hits.extend(match.group(0) for match in _BDI.finditer(blob))
    hits.extend(match.group(0) for match in _ACTION.finditer(blob))
    hits.extend(match.group(0) for match in _COMPLETE.finditer(blob))
    return hits


def walk_strings(node: Any) -> list[str]:
    found: list[str] = []
    if isinstance(node, str):
        found.append(node)
        return found
    if isinstance(node, dict):
        for value in node.values():
            found.extend(walk_strings(value))
        return found
    if isinstance(node, (list, tuple)):
        for item in node:
            found.extend(walk_strings(item))
    return found


def scan_payload(payload: Any) -> list[str]:
    hits: list[str] = []
    for text in walk_strings(payload):
        hits.extend(scan_forbidden_claims(text))
    return hits
