"""Idempotent PNCP contract terms / lifecycle events (#548)."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from scripts.commercial_leads.contract_relevance import normalize_text
from scripts.crawl.pncp_contract import digits_only

PNCP_API_V1 = "https://pncp.gov.br/api/pncp/v1"
PNCP_CONTROLE_ID = re.compile(r"^(\d{14})-\d+-(\d+)/(\d{4})$")

RULE_VERSION = "pncp-contract-terms-v1"
TERMINAL = frozenset({"RESCISAO", "REVOGACAO", "ANULACAO"})


def parse_pncp_controle_id(value: str | None) -> tuple[str, int, int] | None:
    match = PNCP_CONTROLE_ID.match((value or "").strip())
    if not match:
        return None
    return match.group(1), int(match.group(3)), int(match.group(2))


def contract_terms_url(cnpj: str, ano: int, sequencial: int) -> str:
    return f"{PNCP_API_V1}/orgaos/{digits_only(cnpj)}/contratos/{int(ano)}/{int(sequencial)}/termos"


def classify_term_type(nome: str | None, situacao: str | None = None) -> str:
    blob = normalize_text(" ".join(x for x in (nome, situacao) if x))
    if "aditiv" in blob:
        return "ADITIVO"
    if "retific" in blob or "apostil" in blob:
        return "RETIFICACAO"
    if "rescis" in blob:
        return "RESCISAO"
    if "revog" in blob:
        return "REVOGACAO"
    if "anul" in blob:
        return "ANULACAO"
    return "OUTRO"


def map_pncp_term(payload: Mapping[str, Any], *, contrato_id: str | None = None) -> dict[str, Any] | None:
    cid = str(contrato_id or payload.get("contrato_id") or payload.get("numeroControlePNCP") or "").strip()
    if not cid:
        return None
    tipo = classify_term_type(
        str(payload.get("tipoTermoNome") or payload.get("tipoTermo") or payload.get("tipo") or ""),
        str(payload.get("situacao") or ""),
    )
    seq = payload.get("numeroTermo") or payload.get("sequencial") or payload.get("id") or ""
    key = f"{cid}|{tipo}|{seq}|{payload.get('dataAssinatura') or ''}"
    term_id = "pncp_term_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    valor = payload.get("valorGlobal") or payload.get("valor") or payload.get("valorAcrescimo")
    try:
        valor_num = float(valor) if valor not in (None, "") else None
    except (TypeError, ValueError):
        valor_num = None
    data = str(payload.get("dataAssinatura") or payload.get("dataVigenciaInicio") or "")[:10] or None
    return {
        "term_id": term_id,
        "contrato_id": cid,
        "tipo_termo": tipo,
        "numero_termo": str(seq) if seq not in (None, "") else None,
        "data_assinatura": data,
        "valor": valor_num,
        "prazo_dias": payload.get("prazoAditadoDias") or payload.get("prazo"),
        "first_seen_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "rule_version": RULE_VERSION,
        "payload_hash": hashlib.sha256(
            json.dumps(dict(payload), sort_keys=True, default=str).encode("utf-8")
        ).hexdigest(),
        "is_terminal": tipo in TERMINAL,
    }


def plan_term_ingest(
    payloads: list[Mapping[str, Any]],
    *,
    contrato_id: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for payload in payloads:
        mapped = map_pncp_term(payload, contrato_id=contrato_id)
        if not mapped or mapped["term_id"] in seen:
            continue
        seen.add(mapped["term_id"])
        rows.append(mapped)
    return rows


def expand_term_payloads(
    documents: Iterable[Any],
    *,
    contrato_id: str | None = None,
) -> list[Mapping[str, Any]]:
    out: list[Mapping[str, Any]] = []
    for document in documents:
        out.extend(_expand_one(document, contrato_id=contrato_id))
    return out


def _expand_one(document: Any, *, contrato_id: str | None) -> list[Mapping[str, Any]]:
    if isinstance(document, list):
        rows: list[Mapping[str, Any]] = []
        for item in document:
            rows.extend(_expand_one(item, contrato_id=contrato_id))
        return rows
    if not isinstance(document, Mapping):
        return []
    cid = contrato_id or document.get("contrato_id") or document.get("numeroControlePNCP")
    nested = document.get("termos") or document.get("data")
    looks_like_term = bool(
        document.get("tipoTermoNome")
        or document.get("tipoTermo")
        or document.get("tipo_termo")
        or document.get("numeroTermo")
    )
    if isinstance(nested, list) and not looks_like_term:
        rows = []
        for item in nested:
            rows.extend(_expand_one(item, contrato_id=cid))
        return rows
    payload = dict(document)
    if cid:
        payload.setdefault("contrato_id", cid)
        payload.setdefault("numeroControlePNCP", cid)
    return [payload]
