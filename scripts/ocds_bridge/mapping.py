"""Map Extra operational records ↔ OCDS-inspired release fragments.

Preserves official IDs, values semantics, and provenance hashes.
Does not replace operational tables — serializes for validation/export only.
"""
from __future__ import annotations

from typing import Any


RELEASE_TAGS = {
    "tender": "tender",
    "award": "award",
    "contract": "contract",
    "implementation": "implementation",
}


def bid_to_ocds_release(bid: dict[str, Any]) -> dict[str, Any]:
    """Map pncp_raw_bids-like row to OCDS-inspired release (tender-centric)."""
    ocid = bid.get("numero_controle_pncp") or bid.get("id") or bid.get("bid_id")
    value = bid.get("valor_total_estimado") or bid.get("valor_estimado")
    return {
        "ocid": f"ocds-extra-{ocid}" if ocid else None,
        "id": str(bid.get("id") or ocid or ""),
        "date": bid.get("data_publicacao_pncp") or bid.get("data_publicacao"),
        "tag": ["tender"],
        "initiationType": "tender",
        "tender": {
            "id": str(ocid or ""),
            "title": bid.get("objeto_compra") or bid.get("objeto") or "",
            "status": bid.get("situacao_nome") or bid.get("status") or "unknown",
            "value": _value(value, bid.get("moeda") or "BRL"),
            "procurementMethodDetails": bid.get("modalidade_nome") or bid.get("modalidade"),
        },
        "buyer": {
            "id": _party_id(bid.get("orgao_cnpj") or bid.get("cnpj_orgao")),
            "name": bid.get("orgao_nome") or bid.get("orgao_razao_social") or "",
        },
        "extra:provenance": {
            "source": "pncp",
            "content_hash": bid.get("content_hash") or bid.get("hash"),
            "raw_uri": bid.get("raw_uri"),
            "official_id": ocid,
        },
    }


def contract_to_ocds_release(ctr: dict[str, Any]) -> dict[str, Any]:
    """Map pncp_supplier_contracts-like row to OCDS-inspired contract release."""
    cid = ctr.get("contrato_id") or ctr.get("numero_controle_pncp") or ctr.get("id")
    value = ctr.get("valor_global") or ctr.get("valor_total") or ctr.get("valor_contratado")
    return {
        "ocid": f"ocds-extra-{cid}" if cid else None,
        "id": str(cid or ""),
        "date": ctr.get("data_publicacao_pncp") or ctr.get("data_assinatura"),
        "tag": ["contract"],
        "contracts": [
            {
                "id": str(cid or ""),
                "title": ctr.get("objeto_contrato") or ctr.get("objeto") or "",
                "status": ctr.get("situacao") or "unknown",
                "value": _value(value, "BRL"),
                "period": {
                    "startDate": ctr.get("data_vigencia_inicio") or ctr.get("vigencia_inicio"),
                    "endDate": ctr.get("data_vigencia_fim") or ctr.get("vigencia_fim"),
                },
                "dateSigned": ctr.get("data_assinatura"),
            }
        ],
        "parties": [
            {
                "id": _party_id(ctr.get("orgao_cnpj")),
                "name": ctr.get("orgao_nome") or "",
                "roles": ["buyer"],
            },
            {
                "id": _party_id(ctr.get("fornecedor_cnpj")),
                "name": ctr.get("fornecedor_nome") or ctr.get("nome_fornecedor") or "",
                "roles": ["supplier"],
            },
        ],
        "extra:value_semantics": {
            "field": "valor_global|valor_total|valor_contratado",
            "is_paid": False,
            "is_contracted": True,
            "note": "Never treat contracted value as paid without payment observation",
        },
        "extra:provenance": {
            "source": "pncp_contracts",
            "content_hash": ctr.get("content_hash") or ctr.get("hash"),
            "official_id": cid,
            "linked_tender_id": ctr.get("numero_controle_pncp_compra")
            or ctr.get("compra_id")
            or ctr.get("edital_id"),
        },
    }


def ocds_release_to_bid_stub(release: dict[str, Any]) -> dict[str, Any]:
    """Round-trip: OCDS tender release → minimal bid fields (lossy by design)."""
    tender = release.get("tender") or {}
    buyer = release.get("buyer") or {}
    prov = release.get("extra:provenance") or {}
    value = (tender.get("value") or {}).get("amount")
    return {
        "numero_controle_pncp": prov.get("official_id") or tender.get("id"),
        "objeto_compra": tender.get("title"),
        "situacao_nome": tender.get("status"),
        "valor_total_estimado": value,
        "orgao_cnpj": _digits(buyer.get("id")),
        "orgao_nome": buyer.get("name"),
        "content_hash": prov.get("content_hash"),
        "data_publicacao_pncp": release.get("date"),
        "modalidade_nome": tender.get("procurementMethodDetails"),
    }


def essential_fields_preserved(original: dict[str, Any], roundtrip: dict[str, Any], keys: list[str]) -> list[str]:
    """Return list of essential keys lost or changed in round-trip."""
    lost: list[str] = []
    for k in keys:
        o, r = original.get(k), roundtrip.get(k)
        if o in (None, "") and r in (None, ""):
            continue
        if str(o or "") != str(r or ""):
            # allow cnpj formatting differences
            if k.endswith("cnpj") and _digits(o) == _digits(r):
                continue
            lost.append(k)
    return lost


def _value(amount: Any, currency: str) -> dict[str, Any] | None:
    if amount is None or amount == "":
        return None
    try:
        amt = float(amount)
    except (TypeError, ValueError):
        return {"amount": None, "currency": currency, "raw": amount}
    return {"amount": amt, "currency": currency}


def _party_id(cnpj: Any) -> str | None:
    d = _digits(cnpj)
    return f"BR-CNPJ-{d}" if d else None


def _digits(v: Any) -> str:
    return "".join(c for c in str(v or "") if c.isdigit())
