"""LI-4 — accessor UNICO de data de contrato (Decisao 7, §7.3).

Todo o motor resolve "quando a empresa contratou" por aqui, nunca lendo campos
de data soltos. Isso torna a troca pelo ``contract_contracting_date_v1()`` do
PR #531 uma mudanca de UMA funcao, e nao um caça-campo pelo pacote.

A precedencia e ``QUALIFYING_DATE_PRECEDENCE`` de
``scripts/confenge_activation/commercial_authority_v2.py`` — reusada, nao
reimplementada (IDS: REUSE). ``data_fim`` permanece deliberadamente fora: e
estimativa de fim de execucao e tornaria a janela nao deterministica.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

from scripts.confenge_activation.commercial_authority_v2 import (
    QUALIFYING_DATE_PRECEDENCE,
    contracting_date,
)

DATE_RESOLVER_VERSION = "ca-v2-precedence/1.0"

TRUST_OBSERVED = "OBSERVED"
TRUST_UNKNOWN = "UNKNOWN"

__all__ = [
    "DATE_RESOLVER_VERSION",
    "QUALIFYING_DATE_PRECEDENCE",
    "TRUST_OBSERVED",
    "TRUST_UNKNOWN",
    "resolve_contracting_date",
    "most_recent_contracting_date",
]


def resolve_contracting_date(contract: Mapping[str, Any]) -> tuple[date | None, str, str]:
    """``(data, trust, campo_de_origem)``.

    ``trust`` e ``OBSERVED`` somente quando algum campo da precedencia resolveu.
    Ausencia NUNCA vira ``date.today()`` nem ``UNKNOWN`` implicito: retorna
    ``(None, "UNKNOWN", "")`` e o chamador e obrigado a declarar a exclusao.
    """
    resolved, field_name = contracting_date(contract)
    if resolved is None:
        return None, TRUST_UNKNOWN, ""
    return resolved, TRUST_OBSERVED, field_name


def most_recent_contracting_date(
    contracts: list[Mapping[str, Any]],
) -> tuple[date | None, str, tuple[str, ...]]:
    """Data mais recente do portfolio + os campos de origem efetivamente usados."""
    best: date | None = None
    fields_used: list[str] = []
    for contract in contracts:
        resolved, trust, field_name = resolve_contracting_date(contract)
        if trust != TRUST_OBSERVED or resolved is None:
            continue
        fields_used.append(field_name)
        if best is None or resolved > best:
            best = resolved
    if best is None:
        return None, TRUST_UNKNOWN, ()
    return best, TRUST_OBSERVED, tuple(sorted(set(fields_used)))
