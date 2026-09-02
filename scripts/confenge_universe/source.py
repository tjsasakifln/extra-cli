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

from scripts.confenge_contract_identity import public_contract_id

# Logical (internal) column names used by identity/aggregate/construction.
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

# Physical datalake column → logical name. ``id`` is a surrogate cursor, not
# a public contract identity; real tables can also carry the PNCP control ID.
PHYSICAL_TO_LOGICAL: dict[str, str] = {
    "contrato_id": "contrato_id",
    "numero_controle_pncp": "contrato_id",
    "id": "surrogate_id",
    "orgao_cnpj": "orgao_cnpj",
    "orgao_nome": "orgao_nome",
    "fornecedor_cnpj": "fornecedor_cnpj",
    "ni_fornecedor": "fornecedor_cnpj",
    "fornecedor_nome": "fornecedor_nome",
    "nome_fornecedor": "fornecedor_nome",
    "objeto_contrato": "objeto_contrato",
    "valor_total": "valor_total",
    "valor_global": "valor_total",
    "data_inicio": "data_inicio",
    "data_fim": "data_fim",
    "data_fim_vigencia": "data_fim",
    "data_publicacao": "data_publicacao",
    "data_assinatura": "data_assinatura",
    "uf": "uf",
    "municipio": "municipio",
    "is_active": "is_active",
    "source": "source",
}

# Preferred physical candidates per logical field (order = priority).
LOGICAL_CANDIDATES: dict[str, tuple[str, ...]] = {
    "contrato_id": ("contrato_id", "numero_controle_pncp"),
    "orgao_cnpj": ("orgao_cnpj",),
    "orgao_nome": ("orgao_nome",),
    "fornecedor_cnpj": ("fornecedor_cnpj", "ni_fornecedor"),
    "fornecedor_nome": ("fornecedor_nome", "nome_fornecedor"),
    "objeto_contrato": ("objeto_contrato",),
    "valor_total": ("valor_total", "valor_global"),
    "data_inicio": ("data_inicio", "data_assinatura"),
    "data_fim": ("data_fim", "data_fim_vigencia"),
    "data_publicacao": ("data_publicacao", "data_assinatura"),
    "data_assinatura": ("data_assinatura",),
    "uf": ("uf",),
    "municipio": ("municipio",),
    "is_active": ("is_active",),
    "source": ("source",),
}


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
    allow_legacy_surrogate_contract_id: bool = False


def resolve_source(
    dsn: str | None = None,
    *,
    csv_path: str | None = None,
    allow_legacy_surrogate_contract_id: bool = False,
) -> SourceConfig:
    if csv_path:
        return SourceConfig(mode="csv", csv_path=csv_path, read_only=True, allow_legacy_surrogate_contract_id=allow_legacy_surrogate_contract_id)
    env_dsn = (
        dsn
        or os.environ.get("CONFENGE_UNIVERSE_DSN")
        or os.environ.get("CONFENGE_COMMERCIAL_SOURCE_DSN")
        or os.environ.get("REAJUSTE_SOURCE_DSN")
        or os.environ.get("LOCAL_DATALAKE_DSN")
        or os.environ.get("DATABASE_URL")
    )
    if env_dsn:
        return SourceConfig(mode="dsn", dsn=env_dsn, read_only=True, allow_legacy_surrogate_contract_id=allow_legacy_surrogate_contract_id)
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


def resolve_physical_map(available: list[str], *, allow_legacy_surrogate_contract_id: bool = False) -> dict[str, str]:
    """Map logical fields without silently replacing official identity."""
    avail = set(available)
    out: dict[str, str] = {}
    for logical, candidates in LOGICAL_CANDIDATES.items():
        for phys in candidates:
            if phys in avail:
                out[logical] = phys
                break
    if "contrato_id" not in out and allow_legacy_surrogate_contract_id and "id" in avail:
        out["contrato_id"] = "id"
    return out


def _select_list(available: list[str], *, cursor_column: str | None = None) -> list[str]:
    """Return physical column names to SELECT (unique, validated)."""
    physical_map = resolve_physical_map(available)
    if not physical_map:
        # Fall back to logical names when discovery fails (tests / empty info_schema).
        return list(CONTRACT_COLUMNS)
    # Preserve physical uniqueness while covering all resolved logicals.
    seen: set[str] = set()
    cols: list[str] = []
    for logical in CONTRACT_COLUMNS:
        phys = physical_map.get(logical)
        if phys and phys not in seen:
            seen.add(phys)
            cols.append(phys)
    if cursor_column and cursor_column in set(available) and cursor_column not in seen:
        cols.append(cursor_column)
    return cols or list(CONTRACT_COLUMNS)


def normalize_contract_row(
    row: dict[str, Any],
    *,
    physical_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Project a physical (or already-logical) row into internal logical fields."""
    pmap = physical_map or {}
    # Invert for reverse lookup when map empty and row already uses physical names.
    out: dict[str, Any] = {}
    for logical in CONTRACT_COLUMNS:
        phys = pmap.get(logical)
        if phys and phys in row:
            out[logical] = row[phys]
            continue
        if logical in row:
            out[logical] = row[logical]
            continue
        # Direct physical alias without map
        for cand in LOGICAL_CANDIDATES.get(logical, ()):
            if cand in row:
                out[logical] = row[cand]
                break
        else:
            out[logical] = None
    # contrato_id must be string for keyset + identity
    out["contrato_id"] = public_contract_id(out)
    return out


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
    physical_map: dict[str, str] | None = None,
    cursor_column: str | None = None,
) -> tuple[str, list[Any]]:
    """Keyset by contrato id ASC — stable full-table walk, no OFFSET bias.

    ``columns`` are physical SQL identifiers. ``physical_map`` maps logical
    → physical so WHERE clauses use the real datalake names.
    """
    cols = _validate_columns(columns)
    col_sql = ", ".join(cols)
    pmap = physical_map or {c: c for c in CONTRACT_COLUMNS}
    supplier_col = pmap.get("fornecedor_cnpj", "fornecedor_cnpj")
    valor_col = pmap.get("valor_total", "valor_total")
    uf_col = pmap.get("uf", "uf")
    id_col = cursor_column or pmap.get("contrato_id", "contrato_id")
    for ident in (supplier_col, valor_col, uf_col, id_col):
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", ident or ""):
            raise ValueError(f"Invalid column identifier: {ident!r}")

    where = [
        f"{supplier_col} IS NOT NULL",
        f"btrim({supplier_col}::text) <> ''",
        f"length(regexp_replace({supplier_col}::text, '[^0-9]', '', 'g')) >= 11",
    ]
    params: list[Any] = []
    if min_contract_value > 0:
        where.append(f"COALESCE({valor_col}, 0) >= %s")
        params.append(float(min_contract_value))
    if uf:
        u = re.sub(r"[^A-Za-z]", "", uf).upper()[:2]
        where.append(f"upper({uf_col}) = %s")
        params.append(u)
    if keyset_contrato_id is not None:
        # Prefer numeric keyset when the id looks integer (real table uses bigserial id).
        # Text keyset for string contrato_id / numero_controle_pncp schemas.
        key = str(keyset_contrato_id)
        if re.fullmatch(r"-?\d+", key) and id_col == "id":
            where.append(f"{id_col} > %s")
            params.append(int(key))
        else:
            where.append(f"{id_col}::text > %s")
            params.append(key)
    sql = (
        f"SELECT {col_sql} FROM public.pncp_supplier_contracts WHERE "
        + " AND ".join(where)
        + f" ORDER BY {id_col} ASC"
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
                # Resolve physical id column (id / contrato_id / numero_controle_pncp).
                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name='pncp_supplier_contracts'"
                )
                available = [r["column_name"] for r in cur.fetchall()]
                pmap = resolve_physical_map(available, allow_legacy_surrogate_contract_id=cfg.allow_legacy_surrogate_contract_id)
                id_col = pmap.get("contrato_id", "id")
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", id_col):
                    raise ValueError(f"invalid id column: {id_col!r}")
                cur.execute(
                    f"SELECT MAX({id_col})::text AS m FROM public.pncp_supplier_contracts"
                )
                row = cur.fetchone()
                base["max_contrato_id"] = row["m"] if row else None
                base["id_column"] = id_col
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
    physical_map = resolve_physical_map(available, allow_legacy_surrogate_contract_id=cfg.allow_legacy_surrogate_contract_id)
    if "contrato_id" not in physical_map:
        raise RuntimeError("pncp_supplier_contracts has no official contract identity (expected contrato_id or numero_controle_pncp); refusing to publish surrogate id")
    cursor_column = "id" if "id" in available else physical_map["contrato_id"]
    cols = _select_list(available, cursor_column=cursor_column)
    if "fornecedor_cnpj" not in physical_map and "ni_fornecedor" not in available:
        # Legacy logical-only schema (tests / old DBs)
        if "fornecedor_cnpj" not in available:
            raise RuntimeError(
                "pncp_supplier_contracts has no supplier CNPJ column "
                "(expected fornecedor_cnpj or ni_fornecedor)"
            )
    yielded = 0
    key_cid: str | None = None
    id_phys = cursor_column

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
            physical_map=physical_map or None,
            cursor_column=cursor_column,
        )
        conn = _connect_dsn(cfg.dsn)
        try:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                # fetch batch only — never the full table
                raw_batch = [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

        if not raw_batch:
            break
        batch = [normalize_contract_row(r, physical_map=physical_map) for r in raw_batch]
        if any(not row["contrato_id"] for row in batch):
            raise RuntimeError(
                "pncp_supplier_contracts row missing official contract identity; refusing to publish"
            )
        yield batch
        yielded += len(batch)
        # Keyset advances on physical id of last raw row (stable).
        last_raw = raw_batch[-1]
        key_cid = str(last_raw.get(id_phys) or last_raw.get("contrato_id") or batch[-1].get("contrato_id") or "")
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
