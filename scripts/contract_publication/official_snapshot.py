"""Bounded official SC snapshot for publication ranking.

Read-only SELECTs against ``pncp_supplier_contracts``. Does not invent
amendments, units, or peer groups. Keyword hits are selection signals only.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any

from scripts.contract_publication.schema import canonical_dumps, content_hash

SCHEMA = "contract-publication-snapshot/1.0"
SOURCE_KIND_OFFICIAL = "official_select"
SOURCE_KIND_FIXTURE = "fixture"
SOURCE_KIND_BLOCKED = "blocked"
UF_SC = "SC"
DEFAULT_LIMIT = 40
MAX_LIMIT = 80

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
)
EDITORIAL_TOKENS = (
    "aditivo",
    "apostila",
    "reajuste",
    "reequilibr",
    "prorrog",
    "suspens",
    "paralis",
    "rescis",
    "escopo",
)


def resolve_dsn(explicit: str | None = None) -> str | None:
    return explicit or os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL")


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        stamp = value if value.tzinfo else value.replace(tzinfo=UTC)
        return stamp.isoformat().replace("+00:00", "Z")
    text = str(value).strip()
    return text or None


def editorial_signal(objeto: str | None) -> bool:
    blob = (objeto or "").casefold()
    return any(token in blob for token in EDITORIAL_TOKENS)


def aec_signal(objeto: str | None) -> bool:
    blob = (objeto or "").casefold()
    return any(token in blob for token in AEC_TOKENS)


def official_select_sql() -> str:
    if len(AEC_TOKENS) != 10 or len(EDITORIAL_TOKENS) != 9:
        raise RuntimeError("official_select_sql placeholders out of sync with token lists")
    return """
SELECT contrato_id, orgao_cnpj, orgao_nome, fornecedor_cnpj, fornecedor_nome,
       objeto_contrato, valor_total, data_inicio, data_fim, data_publicacao,
       data_assinatura, uf, municipio, source, source_id, ingested_at, is_active,
       codigo_municipio_ibge
FROM pncp_supplier_contracts
WHERE uf = %s
  AND is_active IS DISTINCT FROM FALSE
  AND (
        objeto_contrato ILIKE %s OR objeto_contrato ILIKE %s OR objeto_contrato ILIKE %s
     OR objeto_contrato ILIKE %s OR objeto_contrato ILIKE %s OR objeto_contrato ILIKE %s
     OR objeto_contrato ILIKE %s OR objeto_contrato ILIKE %s OR objeto_contrato ILIKE %s
     OR objeto_contrato ILIKE %s
  )
ORDER BY
  CASE WHEN (
        objeto_contrato ILIKE %s OR objeto_contrato ILIKE %s OR objeto_contrato ILIKE %s
     OR objeto_contrato ILIKE %s OR objeto_contrato ILIKE %s OR objeto_contrato ILIKE %s
     OR objeto_contrato ILIKE %s OR objeto_contrato ILIKE %s OR objeto_contrato ILIKE %s
  ) THEN 0 ELSE 1 END,
  ingested_at DESC NULLS LAST,
  contrato_id
LIMIT %s
"""


def _like_params() -> list[str]:
    return [f"%{token}%" for token in AEC_TOKENS] + [f"%{token}%" for token in EDITORIAL_TOKENS]


def query_hash(*, uf: str, limit: int) -> str:
    payload = {
        "sql_sha256": hashlib.sha256(official_select_sql().encode("utf-8")).hexdigest(),
        "uf": uf,
        "limit": limit,
        "aec_tokens": list(AEC_TOKENS),
        "editorial_tokens": list(EDITORIAL_TOKENS),
        "order": "editorial_signal, ingested_at desc, contrato_id",
        "not_order": "valor_total",
    }
    return content_hash(payload)


def row_to_record(row: dict[str, Any]) -> dict[str, Any]:
    contrato_id = str(row.get("contrato_id") or "").strip()
    objeto = row.get("objeto_contrato")
    ingested = _iso(row.get("ingested_at"))
    return {
        "canonical_contract_id": contrato_id or None,
        "source": str(row.get("source") or "pncp"),
        "source_id": str(row.get("source_id") or contrato_id),
        "numero_controle_pncp": contrato_id,
        "contrato_id": contrato_id,
        "objeto_contrato": objeto,
        "orgao_cnpj": row.get("orgao_cnpj"),
        "orgao_nome": row.get("orgao_nome"),
        "fornecedor_cnpj": row.get("fornecedor_cnpj"),
        "fornecedor_nome": row.get("fornecedor_nome"),
        "valor_total": row.get("valor_total"),
        "data_assinatura": _iso(row.get("data_assinatura")),
        "data_inicio": _iso(row.get("data_inicio")),
        "data_fim": _iso(row.get("data_fim")),
        "data_publicacao": _iso(row.get("data_publicacao")),
        "observed_at": ingested,
        "uf": row.get("uf") or UF_SC,
        "municipio": row.get("municipio"),
        "codigo_municipio_ibge": row.get("codigo_municipio_ibge"),
        "evidence_ref": f"pncp_supplier_contracts:{contrato_id}",
        "source_urls": [f"https://pncp.gov.br/app/contratos/{contrato_id}"] if contrato_id else [],
        "documents": [],
        "selection_signal": "editorial_token" if editorial_signal(str(objeto or "")) else "aec_token",
        "official_projection_authorized": True,
        "catalog_mode": "official_projection",
    }


def inspect_table(conn: Any) -> tuple[bool, tuple[str, ...]]:
    sql = """
    SELECT column_name
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'pncp_supplier_contracts'
    ORDER BY column_name
    """
    required = (
        "contrato_id",
        "objeto_contrato",
        "uf",
        "valor_total",
        "ingested_at",
    )
    with conn.cursor() as cur:
        cur.execute(sql)
        names = tuple(str(row[0]) for row in cur.fetchall())
    if not names:
        return False, required
    missing = tuple(column for column in required if column not in names)
    return True, missing


def blocked_snapshot(*, reason: str, as_of: str | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    stamp = as_of or _now()
    document = {
        "schema": SCHEMA,
        "catalog_mode": "official_unavailable",
        "source_kind": SOURCE_KIND_BLOCKED,
        "official_projection_authorized": False,
        "official_live": False,
        "live_select_executed": False,
        "as_of": stamp,
        "source_as_of": None,
        "records": [],
        "reason_codes": [reason],
        "geography": {"uf": UF_SC, "claim_scope": "SC", "claim_authorization": None},
        "query_hash": query_hash(uf=UF_SC, limit=DEFAULT_LIMIT),
    }
    if extra:
        document.update(extra)
    document["content_hash"] = content_hash({key: value for key, value in document.items() if key != "content_hash"})
    return document


def build_snapshot(
    rows: list[dict[str, Any]],
    *,
    as_of: str,
    source_as_of: str | None,
    limit: int,
    source_kind: str = SOURCE_KIND_OFFICIAL,
) -> dict[str, Any]:
    records = [row_to_record(row) for row in rows if row.get("contrato_id")]
    document = {
        "schema": SCHEMA,
        "catalog_mode": "official_projection",
        "source_kind": source_kind,
        "official_projection_authorized": source_kind == SOURCE_KIND_OFFICIAL,
        "official_live": False,
        "live_select_executed": source_kind == SOURCE_KIND_OFFICIAL,
        "as_of": as_of,
        "source_as_of": source_as_of,
        "snapshot_id": f"sc-official-{query_hash(uf=UF_SC, limit=limit)[:12]}",
        "records": records,
        "geography": {"uf": UF_SC, "claim_scope": "SC", "claim_authorization": None},
        "query_hash": query_hash(uf=UF_SC, limit=limit),
        "row_count": len(records),
        "editorial_signal_count": sum(1 for item in records if item.get("selection_signal") == "editorial_token"),
        "reason_codes": [] if records else ["empty_official_window"],
    }
    document["content_hash"] = content_hash(
        {key: value for key, value in document.items() if key not in {"content_hash", "as_of"}}
    )
    return document


def fetch_official_sc_snapshot(
    dsn: str | None,
    *,
    limit: int = DEFAULT_LIMIT,
    as_of: str | None = None,
    connect: Any = None,
) -> dict[str, Any]:
    stamp = as_of or _now()
    bounded = max(1, min(int(limit), MAX_LIMIT))
    resolved = resolve_dsn(dsn)
    if not resolved:
        return blocked_snapshot(reason="dsn_absent", as_of=stamp)
    connector = connect
    if connector is None:
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError:
            return blocked_snapshot(reason="psycopg2_absent", as_of=stamp)

        def connector(dsn_value: str) -> Any:
            return psycopg2.connect(dsn_value, cursor_factory=RealDictCursor)

    try:
        conn = connector(resolved)
    except Exception as exc:  # noqa: BLE001 — live probe must fail closed
        return blocked_snapshot(reason="dsn_connect_failed", as_of=stamp, extra={"error_class": type(exc).__name__})
    try:
        present, missing = inspect_table(conn)
        if not present:
            return blocked_snapshot(reason="table_absent", as_of=stamp)
        if missing:
            return blocked_snapshot(
                reason="columns_absent",
                as_of=stamp,
                extra={"missing_columns": list(missing)},
            )
        sql = official_select_sql()
        params = [
            UF_SC,
            *[f"%{token}%" for token in AEC_TOKENS],
            *[f"%{token}%" for token in EDITORIAL_TOKENS],
            bounded,
        ]
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = [dict(row) for row in cur.fetchall()]
    except Exception as exc:  # noqa: BLE001
        return blocked_snapshot(reason="select_failed", as_of=stamp, extra={"error_class": type(exc).__name__})
    finally:
        close = getattr(conn, "close", None)
        if callable(close):
            close()
    source_as_of = None
    for row in rows:
        candidate = _iso(row.get("ingested_at")) or _iso(row.get("data_publicacao"))
        if candidate and (source_as_of is None or candidate > source_as_of):
            source_as_of = candidate
    return build_snapshot(rows, as_of=stamp, source_as_of=source_as_of, limit=bounded)


def load_snapshot_file(path: str) -> dict[str, Any]:
    payload = json.loads(__import__("pathlib").Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("snapshot_must_be_object")
    return payload


def dumps(payload: dict[str, Any]) -> str:
    return canonical_dumps(payload)
