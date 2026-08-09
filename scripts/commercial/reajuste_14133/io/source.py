"""Read-only data source for reajuste campaign.

Supports:
  - direct psycopg2 DSN (local or tunnel) — **parameterized** queries
  - SSH remote SQL via ``ec-prod`` (never prints credentials) — literals
    expanded only after allowlisted columns + sanitized scalars (digits UF/CNPJ)
  - **keyset pagination** (valor_total, contrato_id) — no LIMIT/OFFSET-only bias
  - streaming iterators — does not require full universe in memory

All access is SELECT-only. Never mutates production tables.

Temporal prefilter is soft: signature age is NOT a hard exclusion of contracts
that may already have completed interregno from the true data-base (orçamento).
"""

# ruff: noqa: S608

from __future__ import annotations

import csv
import os
import re
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

# Columns actually present on VPS pncp_supplier_contracts (verified 2026-08-04)
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
    "data_publicacao_fonte",
    "uf",
    "municipio",
    "is_active",
    "source",
)


def mask_dsn(dsn: str) -> str:
    return re.sub(r"://([^:/@]+):([^@]+)@", r"://\1:***@", dsn or "")


def digits_cnpj(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")[:14]


@dataclass
class SourceConfig:
    mode: str  # dsn | ssh | csv
    dsn: str | None = None
    ssh_host: str = "ec-prod"
    ssh_database: str = "pncp_datalake"
    csv_path: str | None = None
    read_only: bool = True


def resolve_source(
    dsn: str | None = None,
    *,
    prefer_ssh: bool = False,
    csv_path: str | None = None,
) -> SourceConfig:
    """Resolve source without logging secrets."""
    if csv_path:
        return SourceConfig(mode="csv", csv_path=csv_path, read_only=True)
    env_dsn = (
        dsn
        or os.environ.get("REAJUSTE_SOURCE_DSN")
        or os.environ.get("CONFENGE_COMMERCIAL_SOURCE_DSN")
        or os.environ.get("LOCAL_DATALAKE_DSN")
        or os.environ.get("DATABASE_URL")
    )
    if prefer_ssh or os.environ.get("REAJUSTE_SOURCE_MODE", "").lower() == "ssh":
        return SourceConfig(mode="ssh", dsn=None, read_only=True)
    if env_dsn:
        return SourceConfig(mode="dsn", dsn=env_dsn, read_only=True)
    return SourceConfig(mode="ssh", read_only=True)


def _connect_dsn(dsn: str) -> Any:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
    conn.set_session(readonly=True, autocommit=True)
    return conn


def _ssh_psql(sql: str, *, host: str, database: str, timeout: int = 600) -> str:
    """Run SQL on remote PG as postgres via SSH. SELECT-only enforced by caller."""
    head = sql.lstrip().lower()
    if any(head.startswith(w) for w in ("insert", "update", "delete", "drop", "alter", "truncate", "create", "grant")):
        raise RuntimeError("Write SQL blocked in reajuste source (read-only).")
    remote = f"sudo -u postgres psql -d {database} -v ON_ERROR_STOP=1 -P pager=off -A -t -c {repr(sql)}"
    proc = subprocess.run(  # noqa: S603
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=30", host, remote],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"SSH SQL failed (exit {proc.returncode}): {(proc.stderr or '')[:500]}")
    return proc.stdout or ""


def _ssh_json_rows(sql: str, *, host: str, database: str, timeout: int = 900) -> list[dict[str, Any]]:
    """Fetch rows as JSON array via row_to_json."""
    import json

    inner = sql.rstrip().rstrip(";")
    wrap = "SELECT COALESCE(json_agg(row_to_json(q)), '[]'::json)::text FROM (" + inner + ") q"
    out = _ssh_psql(wrap, host=host, database=database, timeout=timeout).strip()
    if not out:
        return []
    payload = "".join(ln for ln in out.splitlines() if ln.strip())
    data = json.loads(payload)
    if not isinstance(data, list):
        return []
    return [dict(x) for x in data if isinstance(x, dict)]


def discover_columns(cfg: SourceConfig) -> list[str]:
    """Return actual columns of pncp_supplier_contracts."""
    sql = (
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='pncp_supplier_contracts' "
        "ORDER BY ordinal_position"
    )
    if cfg.mode == "dsn" and cfg.dsn:
        conn = _connect_dsn(cfg.dsn)
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                return [r["column_name"] for r in cur.fetchall()]
        finally:
            conn.close()
    if cfg.mode == "ssh":
        out = _ssh_psql(sql, host=cfg.ssh_host, database=cfg.ssh_database)
        return [ln.strip() for ln in out.splitlines() if ln.strip()]
    return list(CONTRACT_COLUMNS)


def _select_list(available: list[str]) -> list[str]:
    preferred = list(CONTRACT_COLUMNS)
    for extra in (
        "data_atualizacao_fonte",
        "source_event_date",
        "source_date_semantics",
        "last_seen_at",
    ):
        if extra not in preferred:
            preferred.append(extra)
    return [c for c in preferred if c in available]


def _validate_columns(columns: list[str]) -> list[str]:
    out: list[str] = []
    for c in columns:
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", c or ""):
            raise ValueError(f"Invalid column identifier: {c!r}")
        out.append(c)
    return out


def build_prefilter_query(
    *,
    columns: list[str],
    as_of: date,
    min_contract_value: float,
    uf: str | None = None,
    municipio: str | None = None,
    supplier_cnpj: str | None = None,
    scope: str = "national",
    limit: int | None = None,
    offset: int = 0,
    require_proxy_interregno: bool = False,
    keyset_valor: float | None = None,
    keyset_contrato_id: str | None = None,
    order_for_scan: str = "keyset",
) -> tuple[str, list[Any]]:
    """Build parameterized SQL + params for psycopg2.

    Temporal: by default does NOT hard-exclude signature < 12 months
    (``require_proxy_interregno=False``). Use keyset pagination via
    ``keyset_valor`` + ``keyset_contrato_id`` instead of OFFSET.
    """
    cols = _validate_columns(columns)
    col_sql = ", ".join(cols)
    has_assinatura = "data_assinatura" in cols
    has_active = "is_active" in cols
    base_date_expr = (
        "COALESCE(data_assinatura, data_inicio, data_publicacao)"
        if has_assinatura
        else "COALESCE(data_inicio, data_publicacao)"
    )
    where = [
        "valor_total >= %s",
        f"{base_date_expr} IS NOT NULL",
        # Soft: keep contracts still potentially open (end null or not long past)
        # Do not hard-drop merely because signature is recent.
        "(data_fim IS NULL OR data_fim >= %s::date - INTERVAL '24 months')",
        "fornecedor_cnpj IS NOT NULL",
        "length(regexp_replace(fornecedor_cnpj, '[^0-9]', '', 'g')) >= 14",
    ]
    params: list[Any] = [float(min_contract_value), as_of.isoformat()]
    if require_proxy_interregno:
        # Diagnostic/legacy mode only — not for real campaign default
        where.append(f"{base_date_expr} <= %s::date - INTERVAL '12 months'")
        params.append(as_of.isoformat())
    if has_active:
        # Prefer active but do not exclusive-filter expired-with-open-obligations
        # Include active OR recently ended
        where.append("(is_active = true OR data_fim IS NULL OR data_fim >= %s::date - INTERVAL '24 months')")
        params.append(as_of.isoformat())
    if uf:
        u = re.sub(r"[^A-Za-z]", "", uf).upper()[:2]
        where.append("upper(uf) = %s")
        params.append(u)
    if municipio:
        where.append("municipio ILIKE %s")
        params.append("%" + str(municipio)[:80] + "%")
    if supplier_cnpj:
        c = digits_cnpj(supplier_cnpj)
        where.append("regexp_replace(fornecedor_cnpj, '[^0-9]', '', 'g') LIKE %s")
        params.append(c + "%")
    if scope == "sul_sc":
        where.append("upper(uf) IN ('SC','PR','RS')")
    elif scope == "sc":
        where.append("upper(uf) = 'SC'")

    # Keyset: (valor_total DESC, contrato_id ASC) walk without OFFSET
    if keyset_valor is not None and keyset_contrato_id is not None:
        where.append("(valor_total < %s OR (valor_total = %s AND contrato_id > %s))")
        params.extend([float(keyset_valor), float(keyset_valor), str(keyset_contrato_id)])

    if order_for_scan == "keyset":
        order = " ORDER BY valor_total DESC NULLS LAST, contrato_id ASC"
    elif order_for_scan == "contrato_id":
        order = " ORDER BY contrato_id ASC"
    else:
        order = " ORDER BY valor_total DESC NULLS LAST, contrato_id ASC"

    sql = f"SELECT {col_sql} FROM pncp_supplier_contracts WHERE " + " AND ".join(where) + order
    if limit is not None:
        sql += " LIMIT %s"
        params.append(int(limit))
        # OFFSET only when explicitly requested (diagnostic) AND no keyset
        if offset and keyset_valor is None:
            sql += " OFFSET %s"
            params.append(int(offset))
    return sql, params


def build_prefilter_sql(
    *,
    columns: list[str],
    as_of: date,
    min_contract_value: float,
    uf: str | None = None,
    municipio: str | None = None,
    supplier_cnpj: str | None = None,
    scope: str = "national",
    limit: int | None = None,
    offset: int = 0,
    require_proxy_interregno: bool = False,
    keyset_valor: float | None = None,
    keyset_contrato_id: str | None = None,
    order_for_scan: str = "keyset",
) -> str:
    """SSH-safe SQL with sanitized literals."""
    sql, params = build_prefilter_query(
        columns=columns,
        as_of=as_of,
        min_contract_value=min_contract_value,
        uf=uf,
        municipio=municipio,
        supplier_cnpj=supplier_cnpj,
        scope=scope,
        limit=limit,
        offset=offset,
        require_proxy_interregno=require_proxy_interregno,
        keyset_valor=keyset_valor,
        keyset_contrato_id=keyset_contrato_id,
        order_for_scan=order_for_scan,
    )
    parts = sql.split("%s")
    if len(parts) - 1 != len(params):
        raise RuntimeError("SQL placeholder/param mismatch")
    out = parts[0]
    for i, p in enumerate(params):
        if isinstance(p, (int, float)) and not isinstance(p, bool):
            lit = str(p)
        else:
            lit = "'" + str(p).replace("'", "''") + "'"
        out += lit + parts[i + 1]
    return out


def iter_contracts_keyset(
    cfg: SourceConfig,
    *,
    as_of: date,
    min_contract_value: float = 1_000_000.0,
    uf: str | None = None,
    municipio: str | None = None,
    supplier_cnpj: str | None = None,
    scope: str = "national",
    batch_size: int = 2000,
    max_rows: int | None = None,
    require_proxy_interregno: bool = False,
) -> Iterator[list[dict[str, Any]]]:
    """Yield batches via keyset pagination — bounded memory, no full-list accumulate.

    ``max_rows`` is diagnostic-only sampling; when set, callers must record sampling reason.
    """
    if cfg.mode == "csv" and cfg.csv_path:
        rows = _load_csv(Path(cfg.csv_path), min_contract_value=min_contract_value, uf=uf)
        if max_rows is not None:
            rows = rows[:max_rows]
        for i in range(0, len(rows), batch_size):
            yield rows[i : i + batch_size]
        return

    available = discover_columns(cfg)
    cols = _select_list(available)
    if not cols:
        raise RuntimeError("No usable columns on pncp_supplier_contracts")

    yielded = 0
    key_valor: float | None = None
    key_cid: str | None = None

    while True:
        limit = batch_size
        if max_rows is not None:
            remaining = max_rows - yielded
            if remaining <= 0:
                break
            limit = min(batch_size, remaining)

        if cfg.mode == "dsn" and cfg.dsn:
            sql, params = build_prefilter_query(
                columns=cols,
                as_of=as_of,
                min_contract_value=min_contract_value,
                uf=uf,
                municipio=municipio,
                supplier_cnpj=supplier_cnpj,
                scope=scope,
                limit=limit,
                require_proxy_interregno=require_proxy_interregno,
                keyset_valor=key_valor,
                keyset_contrato_id=key_cid,
            )
            batch = _execute_select_params(cfg, sql, params)
        else:
            sql = build_prefilter_sql(
                columns=cols,
                as_of=as_of,
                min_contract_value=min_contract_value,
                uf=uf,
                municipio=municipio,
                supplier_cnpj=supplier_cnpj,
                scope=scope,
                limit=limit,
                require_proxy_interregno=require_proxy_interregno,
                keyset_valor=key_valor,
                keyset_contrato_id=key_cid,
            )
            batch = _execute_select(cfg, sql, columns=cols)

        if not batch:
            break

        yield batch
        yielded += len(batch)
        last = batch[-1]
        try:
            key_valor = float(last.get("valor_total") or 0)
        except (TypeError, ValueError):
            key_valor = 0.0
        key_cid = str(last.get("contrato_id") or "")
        if len(batch) < limit:
            break
        if max_rows is not None and yielded >= max_rows:
            break


def fetch_contracts_batch(
    cfg: SourceConfig,
    *,
    as_of: date,
    min_contract_value: float = 1_000_000.0,
    uf: str | None = None,
    municipio: str | None = None,
    supplier_cnpj: str | None = None,
    scope: str = "national",
    batch_size: int = 2000,
    max_rows: int | None = None,
    require_proxy_interregno: bool = False,
) -> list[dict[str, Any]]:
    """Compatibility wrapper: materializes keyset stream into a list.

    Prefer ``iter_contracts_keyset`` for production campaigns.
    """
    rows: list[dict[str, Any]] = []
    for batch in iter_contracts_keyset(
        cfg,
        as_of=as_of,
        min_contract_value=min_contract_value,
        uf=uf,
        municipio=municipio,
        supplier_cnpj=supplier_cnpj,
        scope=scope,
        batch_size=batch_size,
        max_rows=max_rows,
        require_proxy_interregno=require_proxy_interregno,
    ):
        rows.extend(batch)
    return rows


def _normalize_row(row: dict[str, Any], columns: list[str]) -> dict[str, Any]:
    if row.get("valor_total") is not None:
        try:
            row["valor_total"] = float(row["valor_total"])
        except (TypeError, ValueError):
            row["valor_total"] = None
    if row.get("is_active") is not None:
        row["is_active"] = str(row["is_active"]).lower() in {"t", "true", "1", "yes"}
    for c in columns:
        row.setdefault(c, None)
    return row


def _execute_select_params(cfg: SourceConfig, sql: str, params: list[Any]) -> list[dict[str, Any]]:
    if not (cfg.mode == "dsn" and cfg.dsn):
        raise RuntimeError("Parameterized execute requires dsn mode")
    conn = _connect_dsn(cfg.dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _execute_select(cfg: SourceConfig, sql: str, *, columns: list[str]) -> list[dict[str, Any]]:
    if cfg.mode == "dsn" and cfg.dsn:
        conn = _connect_dsn(cfg.dsn)
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    if cfg.mode == "ssh":
        result = _ssh_json_rows(sql, host=cfg.ssh_host, database=cfg.ssh_database, timeout=900)
        return [_normalize_row(row, columns) for row in result]
    raise RuntimeError(f"Unsupported source mode: {cfg.mode}")


def count_prefilter(cfg: SourceConfig, **kwargs: Any) -> int:
    available = discover_columns(cfg)
    cols = _select_list(available)
    sql = build_prefilter_sql(
        columns=cols[:1],
        as_of=kwargs["as_of"],
        min_contract_value=kwargs.get("min_contract_value", 1_000_000),
        uf=kwargs.get("uf"),
        municipio=kwargs.get("municipio"),
        supplier_cnpj=kwargs.get("supplier_cnpj"),
        scope=kwargs.get("scope", "national"),
        require_proxy_interregno=kwargs.get("require_proxy_interregno", False),
    )
    wrap = f"SELECT COUNT(*)::text FROM ({sql}) q"
    if cfg.mode == "dsn" and cfg.dsn:
        conn = _connect_dsn(cfg.dsn)
        try:
            with conn.cursor() as cur:
                cur.execute(wrap)
                r = cur.fetchone()
                return int(r["count"] if "count" in r else list(r.values())[0])
        finally:
            conn.close()
    out = _ssh_psql(wrap, host=cfg.ssh_host, database=cfg.ssh_database)
    line = (out.strip().splitlines() or ["0"])[0].strip()
    return int(line or 0)


def fetch_supplier_registry(cfg: SourceConfig, cnpjs: list[str]) -> dict[str, dict[str, Any]]:
    """Lookup supplier_registry for contact/geo enrichment."""
    clean = [digits_cnpj(c) for c in cnpjs if len(digits_cnpj(c)) == 14]
    if not clean:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for i in range(0, len(clean), 200):
        chunk = clean[i : i + 200]
        try:
            if cfg.mode == "dsn" and cfg.dsn:
                placeholders = ",".join(["%s"] * len(chunk))
                sql = (
                    "SELECT cnpj14, razao_social, nome_fantasia, cnae_principal, situacao_cadastral, "
                    "municipio, uf, source, source_date::text "
                    f"FROM supplier_registry WHERE cnpj14 IN ({placeholders})"
                )
                conn = _connect_dsn(cfg.dsn)
                try:
                    with conn.cursor() as cur:
                        cur.execute(sql, tuple(chunk))
                        for r in cur.fetchall():
                            out[r["cnpj14"]] = dict(r)
                finally:
                    conn.close()
            elif cfg.mode == "ssh":
                literals = ",".join("'" + c + "'" for c in chunk if re.fullmatch(r"\d{14}", c))
                if not literals:
                    continue
                sql = (
                    "SELECT cnpj14, razao_social, nome_fantasia, cnae_principal, situacao_cadastral, "
                    "municipio, uf, source, source_date::text "
                    "FROM supplier_registry WHERE cnpj14 IN (" + literals + ")"
                )
                rows = _ssh_json_rows(sql, host=cfg.ssh_host, database=cfg.ssh_database)
                for row in rows:
                    if row.get("cnpj14"):
                        out[str(row["cnpj14"])] = row
        except Exception as exc:  # noqa: S112
            _ = exc
            continue
    return out


def fetch_official_acts_mentions(
    cfg: SourceConfig, contrato_ids: list[str], *, limit_per: int = 5
) -> dict[str, list[dict[str, Any]]]:
    """Link official_acts / publications by contract id fragments (best-effort).

    Returns empty dict only when inputs empty or table unavailable — never a noop
    that silently skips a real query path when IDs are provided.
    """
    if not contrato_ids:
        return {}
    out: dict[str, list[dict[str, Any]]] = {cid: [] for cid in contrato_ids if cid}
    # Discover whether a usable acts table exists
    discover_sql = (
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name IN "
        "('official_acts','diario_oficial_acts','pncp_contract_events','public_acts') "
        "ORDER BY table_name LIMIT 1"
    )
    table: str | None = None
    try:
        if cfg.mode == "dsn" and cfg.dsn:
            conn = _connect_dsn(cfg.dsn)
            try:
                with conn.cursor() as cur:
                    cur.execute(discover_sql)
                    row = cur.fetchone()
                    if row:
                        table = row.get("table_name") or list(row.values())[0]
            finally:
                conn.close()
        elif cfg.mode == "ssh":
            raw = _ssh_psql(discover_sql, host=cfg.ssh_host, database=cfg.ssh_database)
            line = (raw.strip().splitlines() or [""])[0].strip()
            if line and re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", line):
                table = line
    except Exception:
        return {cid: [] for cid in out}

    if not table:
        # Record unavailability path (callers inspect empty lists + can note gap)
        return {cid: [] for cid in out}

    # Text search on limited IDs (sanitize: only alnum and separators from PNCP ids)
    for cid in list(out.keys())[:50]:
        safe = re.sub(r"[^0-9A-Za-z\-/]", "", cid)[:80]
        if not safe:
            continue
        like = "%" + safe.replace("'", "") + "%"
        try:
            if cfg.mode == "dsn" and cfg.dsn:
                # Generic column probe — fail soft
                sql = f"SELECT * FROM {table} WHERE CAST(row_to_json({table}) AS text) ILIKE %s LIMIT %s"
                conn = _connect_dsn(cfg.dsn)
                try:
                    with conn.cursor() as cur:
                        cur.execute(sql, (like, int(limit_per)))
                        out[cid] = [dict(r) for r in cur.fetchall()]
                finally:
                    conn.close()
            elif cfg.mode == "ssh":
                lit = like.replace("'", "''")
                sql = (
                    f"SELECT row_to_json(t)::text FROM {table} t "
                    f"WHERE CAST(row_to_json(t) AS text) ILIKE '{lit}' "
                    f"LIMIT {int(limit_per)}"
                )
                raw = _ssh_psql(sql, host=cfg.ssh_host, database=cfg.ssh_database, timeout=120)
                import json

                hits: list[dict[str, Any]] = []
                for ln in raw.splitlines():
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        hits.append(json.loads(ln))
                    except json.JSONDecodeError:
                        hits.append({"raw": ln[:500]})
                out[cid] = hits
        except Exception:
            out[cid] = []
    return out


def _load_csv(path: Path, *, min_contract_value: float, uf: str | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                valor = float(r.get("valor_total") or 0)
            except ValueError:
                valor = 0.0
            if valor < min_contract_value:
                continue
            u = (r.get("uf") or "").upper()
            if uf and u != uf.upper():
                continue
            rows.append(dict(r))
    return rows


def stream_batches(items: list[Any], size: int) -> Iterator[list[Any]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def value_band(valor: float | None) -> str:
    if valor is None:
        return "unknown"
    v = float(valor)
    if v < 5_000_000:
        return "lt_5m"
    if v < 50_000_000:
        return "5m_50m"
    if v < 300_000_000:
        return "50m_300m"
    if v < 1_000_000_000:
        return "300m_1b"
    return "ge_1b"
