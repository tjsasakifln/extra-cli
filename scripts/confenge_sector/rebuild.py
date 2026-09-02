"""Atomic full-lake rebuild of the independent CONFENGE sector dimension.

The source scan runs in one PostgreSQL REPEATABLE READ transaction. There is
deliberately no limit/sample/Top-N option. Human-readable evidence is bounded,
while every contract contributes to the exact per-root denominator.
"""

# ruff: noqa: S608 -- all dynamic identifiers come from validated information_schema names.

from __future__ import annotations

import argparse
import hashlib
import json
import re
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.commercial_leads.sector_fit import ContractHistoryAccumulator
from scripts.commercial_leads.supplier_registry import (
    SupplierRegistryRecord,
    load_registry_map,
)
from scripts.confenge_sector.classification import (
    SECTOR_CLASSIFIER_VERSION,
    classify_company_sector,
)
from scripts.confenge_sector.store import sector_classifier_sha256
from scripts.confenge_target_fit.company_key import company_key_from_raiz
from scripts.confenge_universe.source import (
    _select_list,
    normalize_contract_row,
    resolve_physical_map,
)
from scripts.linkage.keys import is_valid_cnpj14


@dataclass(slots=True)
class SectorRootBucket:
    cnpj_raiz: str
    razao_social: str | None = None
    branch_cnpjs: set[str] = field(default_factory=set)
    history: ContractHistoryAccumulator = field(default_factory=ContractHistoryAccumulator)

    def add(self, row: dict[str, Any]) -> None:
        cnpj = re.sub(r"\D", "", str(row.get("fornecedor_cnpj") or ""))[:14]
        if is_valid_cnpj14(cnpj) and cnpj[:8] == self.cnpj_raiz:
            self.branch_cnpjs.add(cnpj)
        name = str(row.get("fornecedor_nome") or "").strip()
        if name:
            self.razao_social = name
        self.history.add(row)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _relation_columns(conn: Any) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'pncp_supplier_contracts'
            ORDER BY ordinal_position
            """
        )
        return [str(row["column_name"]) for row in cur.fetchall()]


def _source_sql(available: list[str]) -> tuple[str, str, str]:
    # This historical sector rebuild has an explicit legacy compatibility
    # contract; CONFENGE outbound source loading does not opt into it.
    physical = resolve_physical_map(available, allow_legacy_surrogate_contract_id=True)
    supplier = physical.get("fornecedor_cnpj")
    contract_id = physical.get("contrato_id")
    if not supplier or not contract_id:
        raise RuntimeError("canonical contract table lacks supplier CNPJ or stable contract id")
    identifiers = [supplier, contract_id]
    if not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item) for item in identifiers):
        raise ValueError("unsafe physical identifier")
    selected = _select_list(available, cursor_column=contract_id)
    root_expr = (
        "fornecedor_cnpj_8::text"
        if "fornecedor_cnpj_8" in available
        else f"left(regexp_replace({supplier}::text, '[^0-9]', '', 'g'), 8)"
    )
    stream_sql = f"""
        SELECT {", ".join(selected)}, {root_expr} AS __cnpj_root
        FROM public.pncp_supplier_contracts
        WHERE {root_expr} IS NOT NULL
          AND length({root_expr}) = 8
          AND {root_expr} <> '00000000'
        ORDER BY {root_expr} ASC, {contract_id} ASC
    """
    denominator_sql = f"""
        SELECT
            COUNT(*)::bigint AS source_contract_rows,
            (COUNT(*) FILTER (
                WHERE {root_expr} IS NOT NULL
                  AND length({root_expr}) = 8
                  AND {root_expr} <> '00000000'
            ))::bigint AS contract_rows_with_supplier_root,
            (COUNT(DISTINCT {root_expr}) FILTER (
                WHERE {root_expr} IS NOT NULL
                  AND length({root_expr}) = 8
                  AND {root_expr} <> '00000000'
            ))::bigint AS supplier_roots_observed,
            MAX({contract_id})::text AS source_max_contract_id
        FROM public.pncp_supplier_contracts
    """
    return stream_sql, denominator_sql, contract_id


def _snapshot_metadata(conn: Any, denominator_sql: str, available: list[str]) -> dict[str, Any]:
    timestamp_cols = [name for name in ("updated_at", "ingested_at") if name in available]
    max_timestamp_sql = (
        "SELECT max(greatest(" + ",".join(f"coalesce({c}, '-infinity')" for c in timestamp_cols) + ")) AS m "
        "FROM public.pncp_supplier_contracts"
        if timestamp_cols
        else None
    )
    with conn.cursor() as cur:
        cur.execute(
            "SELECT txid_current_snapshot()::text AS snapshot, "
            "transaction_timestamp() AS transaction_timestamp, "
            "pg_current_wal_lsn()::text AS wal"
        )
        metadata = dict(cur.fetchone())
        cur.execute(denominator_sql)
        metadata.update(dict(cur.fetchone()))
        metadata["source_max_updated_at"] = None
        if max_timestamp_sql:
            cur.execute(max_timestamp_sql)
            metadata["source_max_updated_at"] = cur.fetchone()["m"]
    metadata["source_cdc_watermark"] = (
        f"max_updated_at={metadata['source_max_updated_at'] or ''};"
        f"max_contract_id={metadata['source_max_contract_id'] or ''};wal={metadata['wal']}"
    )
    return metadata


def _stream_bucket_batches(
    conn: Any,
    *,
    stream_sql: str,
    available: list[str],
    row_batch_size: int,
    root_batch_size: int,
) -> Iterator[list[SectorRootBucket]]:
    """Yield complete root buckets with bounded resident memory.

    The source query is ordered by CNPJ root, so a root is never split across
    batches. ``root_batch_size`` controls only I/O/memory and cannot truncate
    the population.
    """
    physical = resolve_physical_map(available)
    completed: list[SectorRootBucket] = []
    current: SectorRootBucket | None = None
    with conn.cursor(name=f"confenge_sector_{uuid.uuid4().hex[:12]}") as cur:
        cur.itersize = row_batch_size
        cur.execute(stream_sql)
        while True:
            raw_batch = cur.fetchmany(row_batch_size)
            if not raw_batch:
                break
            for raw in raw_batch:
                root = str(raw["__cnpj_root"] or "").strip()
                if len(root) != 8 or not root.isdigit():
                    raise RuntimeError(f"invalid root escaped source closure: {root!r}")
                if current is None or current.cnpj_raiz != root:
                    if current is not None:
                        completed.append(current)
                    if len(completed) >= root_batch_size:
                        yield completed
                        completed = []
                    current = SectorRootBucket(cnpj_raiz=root)
                row = normalize_contract_row(dict(raw), physical_map=physical)
                current.add(row)
    if current is not None:
        completed.append(current)
    if completed:
        yield completed


def _registry_for_bucket(
    bucket: SectorRootBucket,
    registry: dict[str, SupplierRegistryRecord],
) -> SupplierRegistryRecord | None:
    ordered = sorted(bucket.branch_cnpjs, key=lambda value: (value[8:12] != "0001", value))
    return next((registry[cnpj] for cnpj in ordered if cnpj in registry), None)


def _stage_tuple(
    bucket: SectorRootBucket,
    registry: dict[str, SupplierRegistryRecord],
    *,
    source_watermark: str,
    source_max_updated_at: datetime | None,
    computed_at: datetime,
    classifier_hash: str,
) -> tuple[Any, ...]:
    reg = _registry_for_bucket(bucket, registry)
    observed_branches = sorted(
        bucket.branch_cnpjs,
        key=lambda value: (value[8:12] != "0001", value),
    )
    stats = bucket.history.as_stats()
    sector = classify_company_sector(
        razao_social=(reg.razao_social if reg and reg.razao_social else bucket.razao_social),
        nome_fantasia=reg.nome_fantasia if reg else None,
        contracts=[],
        cnae_principal=reg.cnae_principal if reg else None,
        cnaes_secundarios=reg.cnaes_secundarios if reg else [],
        history_is_full=True,
        history_stats=stats,
    )
    fingerprint = "sha256:" + _sha256(
        {
            "root": bucket.cnpj_raiz,
            "razao_social": bucket.razao_social,
            "registry": {
                "razao_social": reg.razao_social if reg else None,
                "nome_fantasia": reg.nome_fantasia if reg else None,
                "cnae_principal": reg.cnae_principal if reg else None,
                "cnaes_secundarios": reg.cnaes_secundarios if reg else [],
            },
            "history": {
                key: value
                for key, value in stats.items()
                if key not in {"evidence_relevant", "conflicting_contracts", "object_labels"}
            },
            "classifier": classifier_hash,
        }
    )
    return (
        company_key_from_raiz(bucket.cnpj_raiz),
        bucket.cnpj_raiz,
        observed_branches[0] if observed_branches else None,
        sector.sector_class,
        sector.confidence,
        SECTOR_CLASSIFIER_VERSION,
        classifier_hash,
        _json(sector.reason_codes),
        _json(sector.evidence),
        sector.source_sector_fit,
        sector.activity_class,
        sector.relevant_contract_count,
        sector.total_contract_count,
        fingerprint,
        source_watermark,
        source_max_updated_at,
        computed_at,
    )


_STAGE_COLUMNS = (
    "company_key, cnpj_raiz, representative_cnpj14, sector_class, sector_confidence, sector_version, "
    "sector_classifier_sha256, sector_reason_codes, sector_evidence, source_sector_fit, "
    "activity_class, relevant_contract_count, total_contract_count, input_fingerprint, "
    "source_watermark, source_max_updated_at, computed_at"
)


def _publish(
    source: Any,
    dsn: str,
    *,
    run_id: uuid.UUID,
    stream_sql: str,
    available: list[str],
    metadata: dict[str, Any],
    query_hash: str,
    classifier_hash: str,
    row_batch_size: int,
    root_batch_size: int,
) -> dict[str, Any]:
    import psycopg2
    from psycopg2.extras import RealDictCursor, execute_values

    started_at = datetime.now(UTC)
    conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
    conn.autocommit = False
    base_manifest = {
        "schema": "confenge.sector_rebuild.v1",
        "run_id": str(run_id),
        "database_snapshot": metadata["snapshot"],
        "transaction_timestamp": metadata["transaction_timestamp"],
        "source_cdc_watermark": metadata["source_cdc_watermark"],
        "source_contract_rows": int(metadata["source_contract_rows"]),
        "supplier_roots_observed": int(metadata["supplier_roots_observed"]),
        "query_sha256": query_hash,
        "construction_classifier_sha256": classifier_hash,
        "full_scale": True,
        "truncated": False,
        "processing_mode": "ROOT_ORDERED_BOUNDED_STAGING",
        "row_batch_size": row_batch_size,
        "root_batch_size": root_batch_size,
    }
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO confenge_sector_rebuild_runs (
                    run_id, status, started_at, database_snapshot,
                    transaction_timestamp, source_cdc_watermark,
                    source_contract_rows, supplier_roots_observed,
                    materialized_roots, sector_classes, query_sha256,
                    classifier_sha256, manifest
                ) VALUES (%s, 'RUNNING', %s, %s, %s, %s, %s, %s, 0, '{}'::jsonb, %s, %s, %s::jsonb)
                """,
                (
                    str(run_id),
                    started_at,
                    metadata["snapshot"],
                    metadata["transaction_timestamp"],
                    metadata["source_cdc_watermark"],
                    metadata["source_contract_rows"],
                    metadata["supplier_roots_observed"],
                    query_hash,
                    classifier_hash,
                    _json(base_manifest),
                ),
            )
        conn.commit()

        computed_at = datetime.now(UTC)
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TEMP TABLE confenge_sector_stage "
                "(LIKE confenge_company_sector_current INCLUDING DEFAULTS) ON COMMIT PRESERVE ROWS"
            )
            cur.execute("ALTER TABLE confenge_sector_stage ADD PRIMARY KEY (company_key)")
            cur.execute("CREATE UNIQUE INDEX ON confenge_sector_stage (cnpj_raiz)")
        conn.commit()

        staged_roots = 0
        rows_seen = 0
        for bucket_batch in _stream_bucket_batches(
            source,
            stream_sql=stream_sql,
            available=available,
            row_batch_size=row_batch_size,
            root_batch_size=root_batch_size,
        ):
            branches = sorted(
                {
                    cnpj
                    for bucket in bucket_batch
                    for cnpj in bucket.branch_cnpjs
                }
            )
            registry = load_registry_map(source, branches)
            pending = [
                _stage_tuple(
                    bucket,
                    registry,
                    source_watermark=metadata["source_cdc_watermark"],
                    source_max_updated_at=metadata["source_max_updated_at"],
                    computed_at=computed_at,
                    classifier_hash=classifier_hash,
                )
                for bucket in bucket_batch
            ]
            rows_seen += sum(bucket.history.total for bucket in bucket_batch)
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    f"INSERT INTO confenge_sector_stage ({_STAGE_COLUMNS}) VALUES %s",
                    pending,
                    page_size=root_batch_size,
                )
                staged_roots += len(pending)
                progress_manifest = {
                    **base_manifest,
                    "checkpoint_roots_staged": staged_roots,
                    "checkpoint_contract_rows_seen": rows_seen,
                }
                cur.execute(
                    "UPDATE confenge_sector_rebuild_runs "
                    "SET materialized_roots = %s, manifest = %s::jsonb "
                    "WHERE run_id = %s AND status = 'RUNNING'",
                    (staged_roots, _json(progress_manifest), str(run_id)),
                )
            conn.commit()

        expected_rows = int(metadata["contract_rows_with_supplier_root"])
        if rows_seen != expected_rows:
            raise RuntimeError(
                f"source row closure failed: streamed={rows_seen} expected={expected_rows}"
            )

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*)::bigint AS n FROM confenge_sector_stage")
            staged = int(cur.fetchone()["n"])
            if staged != staged_roots:
                raise RuntimeError(
                    f"sector staging checkpoint mismatch: table={staged} checkpoints={staged_roots}"
                )
            if staged != int(metadata["supplier_roots_observed"]):
                raise RuntimeError(
                    f"sector stage closure failed: staged={staged} supplier_roots={metadata['supplier_roots_observed']}"
                )
            cur.execute(
                """
                INSERT INTO confenge_company_sector_history (
                    company_key, cnpj_raiz, representative_cnpj14,
                    sector_class, sector_confidence,
                    sector_version, sector_classifier_sha256, sector_reason_codes,
                    sector_evidence, source_sector_fit, activity_class,
                    relevant_contract_count, total_contract_count, input_fingerprint,
                    source_watermark, source_max_updated_at, computed_at,
                    previous_sector_class
                )
                SELECT s.company_key, s.cnpj_raiz, s.representative_cnpj14,
                       s.sector_class, s.sector_confidence,
                       s.sector_version, s.sector_classifier_sha256, s.sector_reason_codes,
                       s.sector_evidence, s.source_sector_fit, s.activity_class,
                       s.relevant_contract_count, s.total_contract_count, s.input_fingerprint,
                       s.source_watermark, s.source_max_updated_at, s.computed_at,
                       c.sector_class
                FROM confenge_sector_stage s
                LEFT JOIN confenge_company_sector_current c USING (company_key)
                WHERE c.company_key IS NULL
                   OR c.input_fingerprint <> s.input_fingerprint
                   OR c.sector_version <> s.sector_version
                """
            )
            history_appended = cur.rowcount or 0
            cur.execute(
                f"""
                INSERT INTO confenge_company_sector_current ({_STAGE_COLUMNS})
                SELECT {_STAGE_COLUMNS} FROM confenge_sector_stage
                WHERE true
                ON CONFLICT (company_key) DO UPDATE SET
                    cnpj_raiz = EXCLUDED.cnpj_raiz,
                    representative_cnpj14 = EXCLUDED.representative_cnpj14,
                    sector_class = EXCLUDED.sector_class,
                    sector_confidence = EXCLUDED.sector_confidence,
                    sector_version = EXCLUDED.sector_version,
                    sector_classifier_sha256 = EXCLUDED.sector_classifier_sha256,
                    sector_reason_codes = EXCLUDED.sector_reason_codes,
                    sector_evidence = EXCLUDED.sector_evidence,
                    source_sector_fit = EXCLUDED.source_sector_fit,
                    activity_class = EXCLUDED.activity_class,
                    relevant_contract_count = EXCLUDED.relevant_contract_count,
                    total_contract_count = EXCLUDED.total_contract_count,
                    input_fingerprint = EXCLUDED.input_fingerprint,
                    source_watermark = EXCLUDED.source_watermark,
                    source_max_updated_at = EXCLUDED.source_max_updated_at,
                    computed_at = EXCLUDED.computed_at,
                    updated_at = now()
                """
            )
            cur.execute(
                "DELETE FROM confenge_company_sector_current c "
                "WHERE NOT EXISTS (SELECT 1 FROM confenge_sector_stage s WHERE s.company_key = c.company_key)"
            )
            stale_archived = cur.rowcount or 0
            cur.execute(
                "SELECT sector_class, COUNT(*)::bigint AS n "
                "FROM confenge_company_sector_current GROUP BY sector_class"
            )
            classes = {str(row["sector_class"]): int(row["n"]) for row in cur.fetchall()}
            materialized = sum(classes.values())
            if materialized != staged:
                raise RuntimeError(
                    f"sector current closure failed: current={materialized} staged={staged}"
                )
            completed_at = datetime.now(UTC)
            manifest = {
                **base_manifest,
                "completed_at": completed_at,
                "contract_rows_with_supplier_root": rows_seen,
                "materialized_roots": materialized,
                "sector_classes": classes,
                "history_rows_appended": history_appended,
                "stale_current_roots_archived": stale_archived,
                "FULLY_RECONCILED": materialized == int(metadata["supplier_roots_observed"]),
            }
            cur.execute(
                """
                UPDATE confenge_sector_rebuild_runs
                SET status = 'COMPLETED', completed_at = %s,
                    materialized_roots = %s, stale_current_roots_archived = %s,
                    sector_classes = %s::jsonb, manifest = %s::jsonb
                WHERE run_id = %s
                """,
                (
                    completed_at,
                    materialized,
                    stale_archived,
                    _json(classes),
                    _json(manifest),
                    str(run_id),
                ),
            )
        conn.commit()
        return manifest
    except Exception as exc:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE confenge_sector_rebuild_runs SET status = 'FAILED', completed_at = now(), "
                "manifest = %s::jsonb WHERE run_id = %s",
                (_json({**base_manifest, "error": str(exc)[:1000]}), str(run_id)),
            )
        conn.commit()
        raise
    finally:
        conn.close()


def rebuild_sector_dimension(
    dsn: str,
    *,
    output_dir: Path,
    batch_size: int = 5_000,
    root_batch_size: int = 2_000,
) -> dict[str, Any]:
    """Run one untruncated, atomic source rebuild and publish the exact root set."""
    import psycopg2
    from psycopg2.extras import RealDictCursor

    run_id = uuid.uuid4()
    source = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
    source.autocommit = False
    try:
        with source.cursor() as cur:
            cur.execute("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        available = _relation_columns(source)
        stream_sql, denominator_sql, _ = _source_sql(available)
        metadata = _snapshot_metadata(source, denominator_sql, available)
        query_hash = hashlib.sha256(
            (stream_sql + "\n" + denominator_sql).encode("utf-8")
        ).hexdigest()
        manifest = _publish(
            source,
            dsn,
            run_id=run_id,
            stream_sql=stream_sql,
            available=available,
            metadata=metadata,
            query_hash=query_hash,
            classifier_hash=sector_classifier_sha256(),
            row_batch_size=batch_size,
            root_batch_size=root_batch_size,
        )
        source.commit()
    except Exception:
        source.rollback()
        raise
    finally:
        source.close()

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "SECTOR-REBUILD.json"
    path.write_text(_json(manifest) + "\n", encoding="utf-8")
    return {**manifest, "artifact": str(path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild the complete CONFENGE sector dimension from one atomic datalake snapshot"
    )
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=5_000)
    parser.add_argument("--root-batch-size", type=int, default=2_000)
    args = parser.parse_args(argv)
    if args.batch_size < 100:
        parser.error("--batch-size must be >= 100; it controls I/O only, never population")
    if args.root_batch_size < 100:
        parser.error("--root-batch-size must be >= 100; it controls memory only, never population")
    result = rebuild_sector_dimension(
        args.dsn,
        output_dir=args.output_dir,
        batch_size=args.batch_size,
        root_batch_size=args.root_batch_size,
    )
    print(_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
