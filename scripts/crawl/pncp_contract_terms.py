"""Idempotent PNCP contract terms / lifecycle events (#548)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from scripts.commercial_leads.contract_relevance import normalize_text

RULE_VERSION = "pncp-contract-terms-v1"
TERMINAL = frozenset({"RESCISAO", "REVOGACAO", "ANULACAO"})


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
