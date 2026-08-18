"""AEC eligibility and documentary-signal ranking for official-live candidates.

Selection is fail-closed: locação de veículos, generic purchases and objects
without an engineering/construction token never enter the READY shortlist.
Keyword hits are ranking signals only — they are not facts and not insight.
"""

from __future__ import annotations

import re
from typing import Any

AEC_TOKENS = (
    "obra",
    "constru",
    "paviment",
    "edific",
    "reforma",
    "drenagem",
    "saneamento",
    "terraplen",
    "infraestrutura",
    "engenharia",
    "recapeamento",
    "asfalt",
    "cbuq",
    "microrevestimento",
    "ponte",
    "viaduto",
    "contenc",
    "contenção",
    "recuperacao estrutural",
    "recuperação estrutural",
    "projeto executivo",
    "projeto de engenharia",
    "fiscalizacao de obra",
    "fiscalização de obra",
    "servico de engenharia",
    "serviço de engenharia",
    "servicos de engenharia",
    "serviços de engenharia",
)

NON_AEC_PATTERNS = (
    re.compile(r"loca[cç][aã]o de ve[ií]cul", re.I),
    re.compile(r"aluguel de ve[ií]cul", re.I),
    re.compile(r"loca[cç][aã]o de autom[oó]ve", re.I),
    re.compile(r"loca[cç][aã]o de frota", re.I),
    re.compile(r"frota de ve[ií]cul", re.I),
    re.compile(r"loca[cç][aã]o de onibus", re.I),
    re.compile(r"loca[cç][aã]o de [oô]nibus", re.I),
)

GENERIC_PURCHASE_PATTERNS = (
    re.compile(r"aquisic[aã]o de (g[eê]nero|alimento|medicament|material de expediente|material de escrit)", re.I),
    re.compile(r"aquisição de (gênero|alimento|medicament|material de expediente|material de escrit)", re.I),
    re.compile(r"compra de (g[eê]nero aliment|medicament|material de expediente)", re.I),
    re.compile(r"fornecimento de (g[eê]nero aliment|merenda|refei[cç]|vale[- ]refei)", re.I),
)

DOCUMENTARY_TOKENS = (
    ("aditivo", ("aditiv", "apostila")),
    ("prazo", ("prorrog", "amplia[cç][aã]o de prazo", "aditivo de prazo")),
    ("reajuste", ("reajuste", "repactu", "data[- ]base")),
    ("reequilibrio", ("reequilibr", "recomposi")),
    ("medicao_glosa", ("medi[cç][aã]o", "glosa")),
    ("paralisacao", ("paralis", "suspens", "retomad")),
    ("rescisao", ("rescis",)),
)

REASON_LOCACAO_VEICULOS = "non_aec_locacao_veiculos"
REASON_GENERIC_PURCHASE = "non_aec_generic_purchase"
REASON_INSUFFICIENT_AEC = "insufficient_aec_signal"
REASON_AEC = "aec_engineering_or_construction"


def _blob(*texts: str | None) -> str:
    return " ".join(item for item in texts if item).casefold()


def is_locacao_veiculos(*texts: str | None) -> bool:
    blob = _blob(*texts)
    return any(pattern.search(blob) for pattern in NON_AEC_PATTERNS)


def is_generic_purchase(*texts: str | None) -> bool:
    blob = _blob(*texts)
    return any(pattern.search(blob) for pattern in GENERIC_PURCHASE_PATTERNS)


def is_aec_object(*texts: str | None) -> bool:
    blob = _blob(*texts)
    blob = re.sub(r"m[aã]o\s+de\s+obra", " ", blob)
    blob = re.sub(r"contenc[aã]o.{0,60}anim", " ", blob)
    return any(token in blob for token in AEC_TOKENS)


def documentary_signals(*texts: str | None) -> tuple[str, ...]:
    blob = _blob(*texts)
    found: list[str] = []
    for name, tokens in DOCUMENTARY_TOKENS:
        if any(re.search(token, blob, re.I) for token in tokens):
            found.append(name)
    return tuple(found)


def aec_disposition(*texts: str | None) -> tuple[bool, str]:
    """Return (eligible, reason_code). Non-AEC always wins over a coincidental AEC token."""
    if is_locacao_veiculos(*texts):
        return False, REASON_LOCACAO_VEICULOS
    if is_generic_purchase(*texts):
        return False, REASON_GENERIC_PURCHASE
    if is_aec_object(*texts):
        return True, REASON_AEC
    return False, REASON_INSUFFICIENT_AEC


def documentary_score(texts: tuple[str | None, ...], *, has_amendment_artifact: bool = False) -> int:
    eligible, _reason = aec_disposition(*texts)
    if not eligible:
        return 0
    signals = documentary_signals(*texts)
    score = 10 + len(signals) * 5
    blob = _blob(*texts)
    if any(token in blob for token in ("cbuq", "paviment", "asfalt", "recapeamento")):
        score += 15
    if has_amendment_artifact:
        score += 20
    return score


def rank_aec_candidates(
    rows: list[dict[str, Any]],
    *,
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Split rows into entered AEC shortlist and a full disposition log."""
    scored: list[tuple[int, str, dict[str, Any]]] = []
    log: list[dict[str, str]] = []
    for row in rows:
        contract_id = str(row.get("contract_id") or row.get("contract_identifier") or "")
        objeto = str(row.get("object_text") or row.get("objeto") or "")
        eligible, reason = aec_disposition(objeto)
        has_amd = bool(row.get("has_amendment_artifact"))
        score = documentary_score((objeto,), has_amendment_artifact=has_amd) if eligible else 0
        if not contract_id:
            log.append({"contract_id": "", "disposition": "UNKNOWN", "reason": "missing_contract_identifier"})
            continue
        if not eligible:
            log.append(
                {
                    "contract_id": contract_id,
                    "disposition": "exited",
                    "reason": reason,
                    "score": str(score),
                }
            )
            continue
        scored.append((score, contract_id, row))
    scored.sort(key=lambda item: (-item[0], item[1]))
    chosen = scored[: max(0, int(limit))]
    chosen_ids = {item[1] for item in chosen}
    entered = [item[2] for item in chosen]
    for score, contract_id, _row in scored:
        if contract_id in chosen_ids:
            log.append(
                {
                    "contract_id": contract_id,
                    "disposition": "entered",
                    "reason": REASON_AEC,
                    "score": str(score),
                }
            )
        else:
            log.append(
                {
                    "contract_id": contract_id,
                    "disposition": "exited",
                    "reason": "beyond_candidate_cap",
                    "score": str(score),
                }
            )
    return entered, log
