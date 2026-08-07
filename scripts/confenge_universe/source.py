"""Streaming contract source for the national construction universe.

Reuses the canonical ``pncp_supplier_contracts`` datalake table. Production
path uses keyset pagination with bounded batches — never requires full
materialization via ``fetchall`` of the entire table.
"""

# ruff: noqa: S608  # column list validated via _validate_columns (identifier-only)

from __future__ import annotations

import csv
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

CONTRACT_COLUMNS = (
    "contrato_id",
    "orgao_cnpj",
    "orgao_nome",
    "fornecedor_cnpj",
    "fornecedor_nome",
    "objeto_contrato",
    "valor_total",
    "data_inicio",
    "data_fim",
    "data_publicacao",
    "data_assinatura",
    "uf",
    "municipio",
    "is_active",
    "source",
)


def mask_dsn(dsn: str) -> str:
    return re.sub(r"://([^:/@]+):([^@]+)@", r"://\1:***@", dsn or "")


def digits_cnpj(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")[:14]


@dataclass(frozen=True)
class SourceConfig:
    mode: str  # dsn | csv | iterator
    dsn: str | None = None
    csv_path: str | None = None
    read_only: bool = True


def resolve_source(
    dsn: str | None = None,
    *,
    csv_path: str | None = None,
) -> SourceConfig:
    if csv_path:
        return SourceConfig(mode="csv", csv_path=csv_path, read_only=True)
    env_dsn = (
        dsn
        or os.environ.get("CONFENGE_UNIVERSE_DSN")
        or os.environ.get("CONFENGE_COMMERCIAL_SOURCE_DSN")
        or os.environ.get("REAJUSTE_SOURCE_DSN")
        or os.environ.get("LOCAL_DATALAKE_DSN")
        or os.environ.get("DATABASE_URL")
    )
    if env_dsn:
        return SourceConfig(mode="dsn", dsn=env_dsn, read_only=True)
    raise RuntimeError(
        "No datalake source configured. Set LOCAL_DATALAKE_DSN / "
        "CONFENGE_UNIVERSE_DSN or pass --csv / --dsn."
    )


def _connect_dsn(dsn: str) -> Any:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
    conn.set_session(readonly=True, autocommit=True)
    return conn


def discover_columns(cfg: SourceConfig) -> list[str]:
    if cfg.mode == "csv":
        return list(CONTRACT_COLUMNS)
    if cfg.mode != "dsn" or not cfg.dsn:
        return list(CONTRACT_COLUMNS)
    sql = (
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='pncp_supplier_contracts' "
        "ORDER BY ordinal_position"
    )
    conn = _connect_dsn(cfg.dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            return [r["column_name"] for r in cur.fetchall()]
    finally:
        conn.close()


def _select_list(available: list[str]) -> list[str]:
    preferred = list(CONTRACT_COLUMNS)
    return [c for c in preferred if c in available] or list(CONTRACT_COLUMNS)


def _validate_columns(columns: list[str]) -> list[str]:
    out: list[str] = []
    for c in columns:
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", c or ""):
            raise ValueError(f"Invalid column identifier: {c!r}")
        out.append(c)
    return out


def build_keyset_query(
    *,
    columns: list[str],
    min_contract_value: float = 0.0,
    uf: str | None = None,
    batch_size: int = 2000,
    keyset_contrato_id: str | None = None,
) -> tuple[str, list[Any]]:
    """Keyset by contrato_id ASC — stable full-table walk, no OFFSET bias."""
    cols = _validate_columns(columns)
    col_sql = ", ".join(cols)
    where = [
        "fornecedor_cnpj IS NOT NULL",
        "btrim(fornecedor_cnpj) <> ''",
        "length(regexp_replace(fornecedor_cnpj, '[^0-9]', '', 'g')) >= 11",
    ]
    params: list[Any] = []
    if min_contract_value > 0:
        where.append("COALESCE(valor_total, 0) >= %s")
        params.append(float(min_contract_value))
    if uf:
        u = re.sub(r"[^A-Za-z]", "", uf).upper()[:2]
        where.append("upper(uf) = %s")
        params.append(u)
    if keyset_contrato_id is not None:
        where.append("contrato_id > %s")
        params.append(str(keyset_contrato_id))
    sql = (
        f"SELECT {col_sql} FROM public.pncp_supplier_contracts WHERE "
        + " AND ".join(where)
        + " ORDER BY contrato_id ASC"
        + " LIMIT %s"
    )
    params.append(int(batch_size))
    return sql, params


def source_fingerprint(cfg: SourceConfig, *, as_of: date) -> dict[str, Any]:
    """Cheap provenance fingerprint without full-table scan when unavailable."""
    base: dict[str, Any] = {
        "mode": cfg.mode,
        "as_of": as_of.isoformat(),
        "table": "pncp_supplier_contracts",
        "dsn_masked": mask_dsn(cfg.dsn or "") if cfg.dsn else None,
        "csv_path": cfg.csv_path,
        "row_count": None,
        "max_contrato_id": None,
        "source_hash": None,
    }
    if cfg.mode == "csv" and cfg.csv_path:
        path = Path(cfg.csv_path)
        if path.is_file():
            import hashlib

            h = hashlib.sha256()
            n = 0
            with path.open("rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
                    n += len(chunk)
            base["source_hash"] = h.hexdigest()
            base["byte_size"] = n
            # line count without materializing rows
            with path.open(encoding="utf-8", errors="replace") as f:
                base["row_count"] = max(sum(1 for _ in f) - 1, 0)
        return base
    if cfg.mode == "dsn" and cfg.dsn:
        conn = _connect_dsn(cfg.dsn)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*)::bigint AS n FROM public.pncp_supplier_contracts")
                base["row_count"] = int(cur.fetchone()["n"])
                cur.execute(
                    "SELECT MAX(contrato_id)::text AS m FROM public.pncp_supplier_contracts"
                )
                row = cur.fetchone()
                base["max_contrato_id"] = row["m"] if row else None
                import hashlib

                payload = f"{base['row_count']}|{base['max_contrato_id']}|{as_of.isoformat()}"
                base["source_hash"] = hashlib.sha256(payload.encode()).hexdigest()
        except Exception as exc:  # noqa: BLE001
            base["fingerprint_error"] = str(exc)[:200]
        finally:
            conn.close()
    return base


def iter_contracts_keyset(
    cfg: SourceConfig,
    *,
    min_contract_value: float = 0.0,
    uf: str | None = None,
    batch_size: int = 2000,
    max_rows: int | None = None,
) -> Iterator[list[dict[str, Any]]]:
    """Yield batches via keyset on contrato_id. Bounded memory per batch.

    ``max_rows`` is diagnostic sampling only; production full-scale leaves it None.
    """
    if cfg.mode == "csv" and cfg.csv_path:
        yield from _iter_csv_batches(
            Path(cfg.csv_path),
            min_contract_value=min_contract_value,
            uf=uf,
            batch_size=batch_size,
            max_rows=max_rows,
        )
        return

    if cfg.mode != "dsn" or not cfg.dsn:
        raise RuntimeError(f"Unsupported source mode for keyset: {cfg.mode}")

    available = discover_columns(cfg)
    cols = _select_list(available)
    yielded = 0
    key_cid: str | None = None

    while True:
        limit = batch_size
        if max_rows is not None:
            remaining = max_rows - yielded
            if remaining <= 0:
                break
            limit = min(batch_size, remaining)

        sql, params = build_keyset_query(
            columns=cols,
            min_contract_value=min_contract_value,
            uf=uf,
            batch_size=limit,
            keyset_contrato_id=key_cid,
        )
        conn = _connect_dsn(cfg.dsn)
        try:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                # fetch batch only — never the full table
                batch = [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

        if not batch:
            break
        yield batch
        yielded += len(batch)
        key_cid = str(batch[-1].get("contrato_id") or "")
        if len(batch) < limit:
            break
        if max_rows is not None and yielded >= max_rows:
            break


def _iter_csv_batches(
    path: Path,
    *,
    min_contract_value: float,
    uf: str | None,
    batch_size: int,
    max_rows: int | None,
) -> Iterator[list[dict[str, Any]]]:
    """Stream CSV without loading entire file into a single list."""
    batch: list[dict[str, Any]] = []
    yielded = 0
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if max_rows is not None and yielded + len(batch) >= max_rows:
                break
            try:
                valor = float(r.get("valor_total") or 0)
            except ValueError:
                valor = 0.0
            if valor < min_contract_value:
                continue
            u = (r.get("uf") or "").upper()
            if uf and u != uf.upper():
                continue
            batch.append(dict(r))
            if len(batch) >= batch_size:
                yield batch
                yielded += len(batch)
                batch = []
        if batch:
            yield batch


def iter_contract_rows(
    row_iter: Iterator[dict[str, Any]],
    *,
    batch_size: int = 2000,
) -> Iterator[list[dict[str, Any]]]:
    """Adapter: any row iterator → batches (for fixtures / synthetic scale)."""
    batch: list[dict[str, Any]] = []
    for row in row_iter:
        batch.append(row)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch
