"""Optional live snapshot over official pncp_supplier_contracts columns only."""

from __future__ import annotations

import os
from typing import Any

from scripts.contract_comparables.constants import (
    CATALOG_FIXTURE_ONLY,
    CATALOG_LIVE_CANDIDATE,
    LIVE_MISSING_SEMANTIC_COLUMNS,
    LIVE_OFFICIAL_COLUMNS,
    REASON_LIVE_COLUMNS,
)
from scripts.contract_comparables.engine import build_peer_group
from scripts.contract_comparables.models import PeerRequest
from scripts.contract_comparables.normalize import records_from_mappings

LIVE_SELECT = """
SELECT contrato_id, orgao_cnpj, orgao_nome, fornecedor_cnpj, fornecedor_nome,
       objeto_contrato, valor_total, data_inicio, data_fim, data_publicacao,
       uf, municipio, source, source_id, ingested_at, is_active,
       codigo_municipio_ibge
FROM pncp_supplier_contracts
WHERE is_active IS TRUE
ORDER BY contrato_id
LIMIT %s
"""


def resolve_dsn(explicit: str | None = None) -> str | None:
    return explicit or os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("NATIONAL_INTEL_DSN")


def inspect_columns(conn: Any) -> tuple[tuple[str, ...], tuple[str, ...]]:
    sql = """
    SELECT column_name
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'pncp_supplier_contracts'
    ORDER BY column_name
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        names = tuple(str(row[0]) for row in cur.fetchall())
    missing = tuple(column for column in LIVE_MISSING_SEMANTIC_COLUMNS if column not in names)
    official = tuple(column for column in LIVE_OFFICIAL_COLUMNS if column in names)
    return official, missing


def rows_to_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for row in rows:
        payload.append(
            {
                "contract_id": row.get("contrato_id"),
                "objeto": row.get("objeto_contrato") or "",
                "valor": row.get("valor_total"),
                "valor_is_unknown": row.get("valor_total") is None,
                "valor_semantic": "unknown",
                "value_basis": "unknown",
                "unidade": None,
                "quantidade": None,
                "uf": row.get("uf"),
                "municipio": row.get("municipio"),
                "regime": None,
                "modalidade": None,
                "data_referencia": str(row.get("data_publicacao") or row.get("data_inicio") or ""),
                "evidence_ref": f"pncp_supplier_contracts:{row.get('contrato_id')}",
                "source": "pncp_supplier_contracts",
                "orgao_id": row.get("orgao_cnpj"),
                "orgao_nome": row.get("orgao_nome"),
                "fornecedor_id": row.get("fornecedor_cnpj"),
                "fornecedor_nome": row.get("fornecedor_nome"),
            }
        )
    return payload


def live_or_fixture_only(
    *,
    dsn: str | None,
    focal_id: str | None,
    as_of: str,
    limit: int = 200,
) -> dict[str, Any]:
    resolved = resolve_dsn(dsn)
    if not resolved:
        return {
            "mode": CATALOG_FIXTURE_ONLY,
            "reason": "LOCAL_DATALAKE_DSN absent",
            "live_smoke": live_smoke_instructions(),
        }
    try:
        from scripts.national_intel.db import connect, fetch_all
    except ImportError:
        return {
            "mode": CATALOG_FIXTURE_ONLY,
            "reason": "national_intel.db unavailable",
            "live_smoke": live_smoke_instructions(),
        }
    try:
        with connect(resolved) as conn:
            _official, missing = inspect_columns(conn)
            rows = fetch_all(conn, LIVE_SELECT, (limit,))
    except Exception as exc:  # noqa: BLE001 — live probe must fail closed, not crash the CLI
        return {
            "mode": CATALOG_FIXTURE_ONLY,
            "reason": f"live probe failed: {exc}",
            "live_smoke": live_smoke_instructions(),
        }
    mappings = [item for item in rows_to_records(rows) if item.get("contract_id")]
    if not mappings:
        return {
            "mode": CATALOG_LIVE_CANDIDATE,
            "reason": "empty snapshot",
            "missing_semantic_columns": list(missing),
            "document": None,
        }
    focal = focal_id or str(mappings[0]["contract_id"])
    request = PeerRequest(
        focal_contract_id=focal,
        as_of=as_of,
        catalog_mode=CATALOG_LIVE_CANDIDATE,
        source="pncp_supplier_contracts",
        live_semantic_columns_present=not missing,
    )
    _result, document = build_peer_group(records_from_mappings(mappings), request)
    if missing and REASON_LIVE_COLUMNS not in document["reason_codes"]:
        document["reason_codes"] = [*document["reason_codes"], REASON_LIVE_COLUMNS]
    document["catalog_mode"] = CATALOG_LIVE_CANDIDATE
    if document.get("catalog_mode") == "official_live":
        raise RuntimeError("live probe must not self-label official_live")
    return {
        "mode": CATALOG_LIVE_CANDIDATE,
        "as_of": as_of,
        "coverage": document.get("coverage"),
        "missing_semantic_columns": list(missing),
        "status": document["status"],
        "content_hash": document["content_hash"],
        "document": document,
        "replay": "re-run the same --dsn --focal --as-of; hashes must match if the snapshot is unchanged",
    }


def live_smoke_instructions() -> dict[str, Any]:
    return {
        "when": "A Postgres snapshot with public.pncp_supplier_contracts is available.",
        "command": (
            "export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test && "
            "python3 -m scripts.contract_comparables live --as-of 2026-08-01 --limit 200"
        ),
        "expect": (
            "If unidade/quantidade/regime/modalidade/valor_semantic are absent, status is "
            "HOLD_FOR_DATA with live_columns_unavailable. Do not invent semantics. "
            "Replay the same command and compare content_hash."
        ),
        "never": "Do not label the result official_live until those columns exist and coverage is proven.",
    }
