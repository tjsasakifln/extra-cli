"""PostgreSQL persistence for the canonical entity source registry."""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any

from scripts.source_registry.models import EntitySourceRecord

COLUMNS = (
    "canonical_id", "razao_social", "nome_fantasia", "cnpj",
    "natureza_juridica", "municipio", "uf", "ibge_code", "lat", "lon",
    "distance_km", "portal_institucional", "portal_transparencia",
    "portal_licitacoes", "diario_oficial", "plataformas", "external_ids",
    "url_patterns", "integration_type", "access_status", "last_success_at",
    "last_attempt_at", "sla_hours", "collection_strategy", "current_blocker",
    "next_action", "priority", "mapping_confidence", "evidences",
)


def record_to_row(record: EntitySourceRecord) -> tuple[Any, ...]:
    """Produce a stable SQL row; JSON conversion is handled at execution time."""
    data = record.to_dict()
    return tuple(data[column] for column in COLUMNS)


def sync_registry_to_postgres(
    records: Iterable[EntitySourceRecord], *, dsn: str | None = None
) -> dict[str, int]:
    """Idempotently upsert all registry records into migration 053."""
    try:
        import psycopg2
        from psycopg2.extras import Json, execute_values
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("psycopg2 is required for sync-db") from exc

    resolved = dsn or os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL")
    if not resolved:
        raise RuntimeError("Set LOCAL_DATALAKE_DSN or pass --dsn")

    source_rows = [record_to_row(record) for record in records]
    json_cols = {
        COLUMNS.index("external_ids"), COLUMNS.index("url_patterns"),
        COLUMNS.index("evidences"),
    }
    rows = [
        tuple(Json(value) if idx in json_cols else value for idx, value in enumerate(row))
        for row in source_rows
    ]
    updates = ", ".join(
        f"{column}=EXCLUDED.{column}"
        for column in COLUMNS
        if column != "canonical_id"
    )
    sql = f"""
        INSERT INTO public.entity_source_registry ({', '.join(COLUMNS)})
        VALUES %s
        ON CONFLICT (canonical_id) DO UPDATE SET {updates}
    """  # noqa: S608 - fixed internal column allow-list
    with psycopg2.connect(resolved) as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, rows, page_size=250)
            cur.execute("SELECT COUNT(*) FROM public.entity_source_registry")
            total = int(cur.fetchone()[0])
    return {"submitted": len(rows), "persisted_total": total}
