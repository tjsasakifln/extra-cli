"""Idempotent PNCP item-result ingest (#545).

Official pre-signature events. Never fabricates contrato_id; link is
parent_procurement_id only until a real contract row exists. engineering_object
is resolved by an exact natural-key join against the parent compra
(pncp_raw_bids / pncp_supplier_contracts), never by fuzzy text matching and
never invented when the parent is absent.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from scripts.contracts_identity import normalize_supplier_identity
from scripts.crawl.pncp_contract import digits_only

PNCP_API_V1 = "https://pncp.gov.br/api/pncp/v1"
PNCP_CONTROLE_ID = re.compile(r"^(\d{14})-\d+-(\d+)/(\d{4})$")

RULE_VERSION = "pncp-procurement-results-v1"
RESULT_PUBLISHED = "RESULT_PUBLISHED"
HOMOLOGATED = "HOMOLOGATED"

# Isolation note (EXTRA-HOMOLOGATION-LIVE-EVIDENCE-DISCOVERY-01): these three
# coercion helpers were originally added by #546's pncp_structural_fields.py.
# They are generic type coercion with no dependency on structural-fields
# domain logic, so they are inlined here rather than pulling the unmerged
# #546/#544 stack into this isolated #545 candidate.
_TRUE = frozenset({"true", "t", "1", "sim", "s", "yes", "y"})
_FALSE = frozenset({"false", "f", "0", "nao", "não", "n", "no"})


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, dict):
        return _as_int(
            value.get("id")
            or value.get("codigo")
            or value.get("codigoModalidade")
            or value.get("codigoRegime")
        )
    try:
        text = str(value).strip()
        if not text:
            return None
        return int(float(text)) if "." in text else int(text)
    except (TypeError, ValueError):
        return None


def _as_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        return _as_text(
            value.get("nome")
            or value.get("descricao")
            or value.get("name")
            or value.get("label")
        )
    if isinstance(value, (bool, int, float)):
        return None
    text = str(value).strip()
    return text or None


def _as_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(int(value))
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return None


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text[:10] if text else None


def parse_pncp_controle_id(value: str | None) -> tuple[str, int, int] | None:
    """Parse ``{cnpj}-{kind}-{sequencial}/{ano}`` into ``(cnpj, ano, sequencial)``."""
    match = PNCP_CONTROLE_ID.match((value or "").strip())
    if not match:
        return None
    return match.group(1), int(match.group(3)), int(match.group(2))


def item_resultados_url(cnpj: str, ano: int, sequencial: int, item_numero: int) -> str:
    return (
        f"{PNCP_API_V1}/orgaos/{digits_only(cnpj)}/compras/{int(ano)}/{int(sequencial)}"
        f"/itens/{int(item_numero)}/resultados"
    )


def result_event_type(situacao: str | None, homologado: bool | None) -> str:
    norm = (situacao or "").strip().lower()
    if homologado is True or "homolog" in norm:
        return HOMOLOGATED
    return RESULT_PUBLISHED


def map_pncp_item_result(
    payload: Mapping[str, Any],
    *,
    parent_procurement_id: str | None = None,
    item_numero: int | None = None,
) -> dict[str, Any] | None:
    """Map a PNCP /itens/{n}/resultados item. contrato_id stays None.

    event_at is sourced ONLY from official result fields (dataResultado /
    dataHoraResultado / dataAtualizacao). If none are present, event_at is
    None (UNKNOWN) — it is never backfilled from first_seen_at/ingested_at.
    """
    parent = (
        parent_procurement_id
        or payload.get("numeroControlePNCPCompra")
        or payload.get("numeroControlePncpCompra")
        or payload.get("parent_procurement_id")
    )
    parent = str(parent).strip() if parent else ""
    if not parent:
        return None
    item = item_numero if item_numero is not None else _as_int(
        payload.get("numeroItem") or payload.get("itemNumero") or payload.get("item")
    )
    winner_raw = (
        payload.get("niFornecedor")
        or payload.get("cnpjFornecedor")
        or payload.get("ni")
    )
    identity = normalize_supplier_identity(
        winner_raw,
        declared_type=payload.get("tipoPessoa") or payload.get("tipoPessoaFornecedor"),
        country=payload.get("codigoPaisFornecedor"),
    )
    winner_cnpj = identity.fornecedor_cnpj
    situacao = _as_text(
        payload.get("situacao")
        or payload.get("situacaoResultado")
        or payload.get("nomeSituacao")
    )
    homologado = _as_bool(payload.get("homologado") or payload.get("indicadorHomologacao"))
    event_type = result_event_type(situacao, homologado)
    valor = payload.get("valorNegociado") or payload.get("valorHomologado") or payload.get("valorTotal")
    try:
        valor_num = float(valor) if valor not in (None, "") else None
    except (TypeError, ValueError):
        valor_num = None
    event_at = _as_date(
        payload.get("dataResultado")
        or payload.get("dataHoraResultado")
        or payload.get("dataAtualizacao")
    )
    published = _as_date(
        payload.get("dataPublicacaoPncp") or payload.get("dataPublicacao")
    )
    key = "|".join(
        [
            parent,
            str(item or ""),
            winner_cnpj or identity.supplier_identifier or "",
            event_type,
        ]
    )
    result_id = "pncp_result_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return {
        "result_id": result_id,
        "parent_procurement_id": parent,
        "contrato_id": None,
        "event_type": event_type,
        "item_numero": item,
        "situacao": situacao,
        "winner_cnpj": winner_cnpj,
        "winner_nome": _as_text(
            payload.get("nomeRazaoSocialFornecedor") or payload.get("nomeFornecedor")
        ),
        "valor_homologado": valor_num,
        "event_at": event_at,
        "source_published_at": published,
        "first_seen_at": _now(),
        "rule_version": RULE_VERSION,
        "payload_hash": hashlib.sha256(
            json.dumps(dict(payload), sort_keys=True, default=str).encode("utf-8")
        ).hexdigest(),
    }


def plan_result_ingest(
    payloads: list[Mapping[str, Any]],
    *,
    parent_procurement_id: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for payload in payloads:
        mapped = map_pncp_item_result(payload, parent_procurement_id=parent_procurement_id)
        if not mapped or mapped["result_id"] in seen:
            continue
        seen.add(mapped["result_id"])
        rows.append(mapped)
    return rows


def expand_result_payloads(
    documents: Iterable[Any],
    *,
    parent_procurement_id: str | None = None,
) -> list[Mapping[str, Any]]:
    """Flatten JSONL/archive envelopes into raw PNCP resultado objects."""
    out: list[Mapping[str, Any]] = []
    for document in documents:
        out.extend(_expand_one(document, parent_procurement_id=parent_procurement_id, item_numero=None))
    return out


def _expand_one(
    document: Any,
    *,
    parent_procurement_id: str | None,
    item_numero: int | None,
) -> list[Mapping[str, Any]]:
    if isinstance(document, list):
        rows: list[Mapping[str, Any]] = []
        for item in document:
            rows.extend(
                _expand_one(item, parent_procurement_id=parent_procurement_id, item_numero=item_numero)
            )
        return rows
    if not isinstance(document, Mapping):
        return []
    parent = (
        parent_procurement_id
        or document.get("parent_procurement_id")
        or document.get("numeroControlePNCPCompra")
        or document.get("numeroControlePncpCompra")
    )
    item = item_numero
    if item is None:
        raw_item = document.get("numeroItem") or document.get("item_numero") or document.get("item")
        item = _as_int(raw_item)
    nested = document.get("resultados")
    if isinstance(nested, list):
        rows = []
        for result in nested:
            rows.extend(_expand_one(result, parent_procurement_id=parent, item_numero=item))
        return rows
    data = document.get("data")
    if isinstance(data, list) and not document.get("niFornecedor") and not document.get("cnpjFornecedor"):
        rows = []
        for result in data:
            rows.extend(_expand_one(result, parent_procurement_id=parent, item_numero=item))
        return rows
    payload = dict(document)
    if parent:
        payload.setdefault("numeroControlePNCPCompra", parent)
        payload.setdefault("parent_procurement_id", parent)
    if item is not None:
        payload.setdefault("numeroItem", item)
    return [payload]
