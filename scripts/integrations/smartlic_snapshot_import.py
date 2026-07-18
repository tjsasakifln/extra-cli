"""SmartLic snapshot import bridge (DATA_BRIDGE) — Extra Consultoria.

Imports exported JSON snapshots shaped like SmartLic tables:
  - pncp_raw_bids
  - pncp_supplier_contracts

into Extra PostgreSQL with explicit field maps, provenance, and reconciliation
manifest. Does NOT require SmartLic credentials or a live SmartLic connection
for development/tests (file mode). Optional --source-dsn for operator-configured
read-only PG export sources.

Rules:
  - Snapshot is never treated as live, coverage, or freshness.
  - Universe filter against Extra canonical entities when requested.
  - Idempotent upserts via content/business keys.
  - Records inserted/updated/unchanged/rejected/errors.
  - Manifest includes source repo, source commit, table, extraction time,
    snapshot hash, import_run_id.
  - No dumps versioned; no secrets logged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

# Field maps: SmartLic-ish → Extra
BIDS_FIELD_MAP = {
    "pncp_id": "pncp_id",
    "numero_controle_pncp": "pncp_id",
    "objeto_compra": "objeto_compra",
    "valor_total_estimado": "valor_total_estimado",
    "modalidade_id": "modalidade_id",
    "modalidade_nome": "modalidade_nome",
    "esfera_id": "esfera_id",
    "uf": "uf",
    "municipio": "municipio",
    "codigo_municipio_ibge": "codigo_municipio_ibge",
    "orgao_razao_social": "orgao_razao_social",
    "orgao_cnpj": "orgao_cnpj",
    "data_publicacao": "data_publicacao",
    "data_abertura": "data_abertura",
    "data_encerramento": "data_encerramento",
    "link_pncp": "link_pncp",
    "content_hash": "content_hash",
    "source": "source",
    "source_id": "source_id",
}

CONTRACTS_FIELD_MAP = {
    "numero_controle_pncp": "contrato_id",
    "contrato_id": "contrato_id",
    "ni_fornecedor": "fornecedor_cnpj",
    "fornecedor_cnpj": "fornecedor_cnpj",
    "nome_fornecedor": "fornecedor_nome",
    "fornecedor_nome": "fornecedor_nome",
    "orgao_cnpj": "orgao_cnpj",
    "orgao_nome": "orgao_nome",
    "uf": "uf",
    "municipio": "municipio",
    "valor_global": "valor_total",
    "valor_total": "valor_total",
    "data_assinatura": "data_publicacao",
    "data_publicacao": "data_publicacao",
    "objeto_contrato": "objeto_contrato",
    "source": "source",
    "source_id": "source_id",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_s() -> str:
    return utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def digits_only(value: Any) -> str | None:
    if value is None:
        return None
    d = "".join(c for c in str(value) if c.isdigit())
    return d or None


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def content_hash_record(record: dict[str, Any], keys: list[str]) -> str:
    payload = {k: record.get(k) for k in keys}
    raw = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_date(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    s = str(value)[:10]
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return s
    return None


def load_json_records(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        for key in ("records", "rows", "data", "items"):
            if isinstance(data.get(key), list):
                return [r for r in data[key] if isinstance(r, dict)]
        # single object
        return [data]
    raise ValueError(f"Unsupported JSON structure in {path}")


def map_record(
    raw: dict[str, Any],
    field_map: dict[str, str],
    *,
    table: str,
    import_run_id: str,
    source_repo: str,
    source_commit: str,
    extraction_ts: str,
    snapshot_hash: str,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for src, dst in field_map.items():
        if src in raw and raw[src] is not None and dst not in out:
            out[dst] = raw[src]
    # normalize
    if "orgao_cnpj" in out:
        out["orgao_cnpj"] = digits_only(out["orgao_cnpj"])
    if "fornecedor_cnpj" in out:
        out["fornecedor_cnpj"] = digits_only(out["fornecedor_cnpj"])
    if table == "pncp_supplier_contracts":
        out["data_publicacao"] = parse_date(out.get("data_publicacao"))
        out["source"] = out.get("source") or "smartlic_snapshot"
        if not out.get("contrato_id"):
            # reject later
            pass
        if not out.get("content_hash"):
            out["content_hash"] = content_hash_record(
                out, ["contrato_id", "fornecedor_cnpj", "valor_total", "objeto_contrato"]
            )
    else:
        for dkey in ("data_publicacao", "data_abertura", "data_encerramento"):
            if dkey in out:
                out[dkey] = parse_date(out[dkey])
        out["source"] = out.get("source") or "smartlic_snapshot"
        if not out.get("content_hash") and out.get("pncp_id"):
            out["content_hash"] = content_hash_record(
                out, ["pncp_id", "objeto_compra", "valor_total_estimado", "orgao_cnpj"]
            )
    # provenance (not all columns exist — stored in manifest + optional JSON notes)
    out["_provenance"] = {
        "source_repo": source_repo,
        "source_commit": source_commit,
        "source_table": table,
        "extraction_ts": extraction_ts,
        "snapshot_hash": snapshot_hash,
        "import_run_id": import_run_id,
        "not_live": True,
        "not_coverage": True,
        "not_freshness": True,
    }
    return out


def in_period(record: dict[str, Any], date_from: str | None, date_to: str | None) -> bool:
    d = record.get("data_publicacao") or record.get("data_assinatura")
    if not d:
        return True  # keep undated unless strict later
    ds = str(d)[:10]
    if date_from and ds < date_from:
        return False
    if date_to and ds > date_to:
        return False
    return True


def filter_universe(
    records: Iterable[dict[str, Any]],
    universe_cnpjs8: set[str] | None,
    *,
    table: str,
) -> tuple[list[dict[str, Any]], int]:
    if not universe_cnpjs8:
        return list(records), 0
    kept: list[dict[str, Any]] = []
    rejected = 0
    for r in records:
        if table == "pncp_supplier_contracts":
            org = digits_only(r.get("orgao_cnpj")) or ""
            key = org[:8] if org else ""
        else:
            org = digits_only(r.get("orgao_cnpj")) or ""
            key = org[:8] if org else ""
        if key and key in universe_cnpjs8:
            kept.append(r)
        else:
            rejected += 1
    return kept, rejected


@dataclass
class ImportStats:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    rejected: int = 0
    errors: int = 0
    read: int = 0
    mapped: int = 0
    universe_rejected: int = 0
    period_rejected: int = 0
    error_samples: list[str] = field(default_factory=list)


def load_universe_cnpjs8(dsn: str) -> set[str]:
    import psycopg2

    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            # Prefer 8-digit key if column exists; else left(cnpj,8)
            cur.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema='public' AND table_name='sc_public_entities'
                """
            )
            cols = {r[0] for r in cur.fetchall()}
            if "cnpj_8" in cols:
                cur.execute(
                    "SELECT DISTINCT cnpj_8 FROM sc_public_entities WHERE cnpj_8 IS NOT NULL"
                )
            elif "cnpj" in cols:
                cur.execute(
                    "SELECT DISTINCT left(regexp_replace(cnpj, '[^0-9]', '', 'g'), 8) "
                    "FROM sc_public_entities WHERE cnpj IS NOT NULL"
                )
            else:
                return set()
            return {r[0] for r in cur.fetchall() if r[0]}
    finally:
        conn.close()


def upsert_bids(conn: Any, records: list[dict[str, Any]], stats: ImportStats) -> None:
    sql = """
    INSERT INTO pncp_raw_bids (
        pncp_id, objeto_compra, valor_total_estimado, modalidade_id, modalidade_nome,
        esfera_id, uf, municipio, codigo_municipio_ibge, orgao_razao_social, orgao_cnpj,
        data_publicacao, data_abertura, data_encerramento, link_pncp, content_hash,
        source, source_id, is_active
    ) VALUES (
        %(pncp_id)s, %(objeto_compra)s, %(valor_total_estimado)s, %(modalidade_id)s,
        %(modalidade_nome)s, %(esfera_id)s, %(uf)s, %(municipio)s, %(codigo_municipio_ibge)s,
        %(orgao_razao_social)s, %(orgao_cnpj)s, %(data_publicacao)s, %(data_abertura)s,
        %(data_encerramento)s, %(link_pncp)s, %(content_hash)s, %(source)s, %(source_id)s, TRUE
    )
    ON CONFLICT (pncp_id) DO UPDATE SET
        objeto_compra = EXCLUDED.objeto_compra,
        valor_total_estimado = EXCLUDED.valor_total_estimado,
        content_hash = EXCLUDED.content_hash,
        updated_at = NOW(),
        is_active = TRUE
    WHERE pncp_raw_bids.content_hash IS DISTINCT FROM EXCLUDED.content_hash
    RETURNING (xmax = 0) AS inserted
    """
    with conn.cursor() as cur:
        for r in records:
            if not r.get("pncp_id"):
                stats.rejected += 1
                continue
            payload = {
                "pncp_id": r.get("pncp_id"),
                "objeto_compra": r.get("objeto_compra"),
                "valor_total_estimado": r.get("valor_total_estimado"),
                "modalidade_id": r.get("modalidade_id"),
                "modalidade_nome": r.get("modalidade_nome"),
                "esfera_id": r.get("esfera_id"),
                "uf": r.get("uf"),
                "municipio": r.get("municipio"),
                "codigo_municipio_ibge": r.get("codigo_municipio_ibge"),
                "orgao_razao_social": r.get("orgao_razao_social"),
                "orgao_cnpj": r.get("orgao_cnpj"),
                "data_publicacao": r.get("data_publicacao"),
                "data_abertura": r.get("data_abertura"),
                "data_encerramento": r.get("data_encerramento"),
                "link_pncp": r.get("link_pncp"),
                "content_hash": r.get("content_hash"),
                "source": r.get("source") or "smartlic_snapshot",
                "source_id": r.get("source_id"),
            }
            try:
                cur.execute(sql, payload)
                row = cur.fetchone()
                if row is None:
                    stats.unchanged += 1
                elif row[0]:
                    stats.inserted += 1
                else:
                    stats.updated += 1
            except Exception as exc:  # noqa: BLE001 — collect and continue batch
                stats.errors += 1
                if len(stats.error_samples) < 10:
                    stats.error_samples.append(f"{payload.get('pncp_id')}: {type(exc).__name__}: {exc}")
                conn.rollback()
                # reopen transaction for next rows
                continue
    conn.commit()


def upsert_contracts(conn: Any, records: list[dict[str, Any]], stats: ImportStats) -> None:
    # Prefer RPC if present
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM pg_proc WHERE proname = 'upsert_pncp_supplier_contracts' LIMIT 1"
        )
        has_rpc = cur.fetchone() is not None
    if has_rpc:
        batch: list[dict[str, Any]] = []
        for r in records:
            if not r.get("contrato_id"):
                stats.rejected += 1
                continue
            batch.append(
                {
                    "contrato_id": r.get("contrato_id"),
                    "orgao_cnpj": r.get("orgao_cnpj"),
                    "orgao_nome": r.get("orgao_nome"),
                    "fornecedor_cnpj": r.get("fornecedor_cnpj"),
                    "fornecedor_nome": r.get("fornecedor_nome"),
                    "objeto_contrato": r.get("objeto_contrato"),
                    "valor_total": r.get("valor_total"),
                    "data_publicacao": r.get("data_publicacao"),
                    "uf": r.get("uf"),
                    "municipio": r.get("municipio"),
                    "source": r.get("source") or "smartlic_snapshot",
                    "source_id": r.get("source_id"),
                }
            )
        # chunk
        chunk_size = 100
        with conn.cursor() as cur:
            for i in range(0, len(batch), chunk_size):
                chunk = batch[i : i + chunk_size]
                try:
                    cur.execute(
                        "SELECT action FROM upsert_pncp_supplier_contracts(%s::jsonb)",
                        (json.dumps(chunk, default=str),),
                    )
                    for row in cur.fetchall():
                        action = (row[0] or "").lower()
                        if action in ("insert", "inserted"):
                            stats.inserted += 1
                        elif action in ("update", "updated"):
                            stats.updated += 1
                        elif action in ("unchanged", "noop", "skip"):
                            stats.unchanged += 1
                        else:
                            stats.updated += 1
                    conn.commit()
                except Exception as exc:  # noqa: BLE001
                    stats.errors += 1
                    if len(stats.error_samples) < 10:
                        stats.error_samples.append(f"rpc_batch: {type(exc).__name__}: {exc}")
                    conn.rollback()
        return

    # Fallback direct upsert on contrato_id
    sql = """
    INSERT INTO pncp_supplier_contracts (
        contrato_id, orgao_cnpj, orgao_nome, fornecedor_cnpj, fornecedor_nome,
        objeto_contrato, valor_total, data_publicacao, uf, municipio, source, source_id
    ) VALUES (
        %(contrato_id)s, %(orgao_cnpj)s, %(orgao_nome)s, %(fornecedor_cnpj)s,
        %(fornecedor_nome)s, %(objeto_contrato)s, %(valor_total)s, %(data_publicacao)s,
        %(uf)s, %(municipio)s, %(source)s, %(source_id)s
    )
    ON CONFLICT (contrato_id) DO UPDATE SET
        objeto_contrato = EXCLUDED.objeto_contrato,
        valor_total = EXCLUDED.valor_total,
        fornecedor_cnpj = EXCLUDED.fornecedor_cnpj,
        orgao_cnpj = EXCLUDED.orgao_cnpj
    RETURNING (xmax = 0) AS inserted
    """
    with conn.cursor() as cur:
        for r in records:
            if not r.get("contrato_id"):
                stats.rejected += 1
                continue
            payload = {
                "contrato_id": r.get("contrato_id"),
                "orgao_cnpj": r.get("orgao_cnpj"),
                "orgao_nome": r.get("orgao_nome"),
                "fornecedor_cnpj": r.get("fornecedor_cnpj"),
                "fornecedor_nome": r.get("fornecedor_nome"),
                "objeto_contrato": r.get("objeto_contrato"),
                "valor_total": r.get("valor_total"),
                "data_publicacao": r.get("data_publicacao"),
                "uf": r.get("uf"),
                "municipio": r.get("municipio"),
                "source": r.get("source") or "smartlic_snapshot",
                "source_id": r.get("source_id"),
            }
            try:
                cur.execute(sql, payload)
                row = cur.fetchone()
                if row is None:
                    stats.unchanged += 1
                elif row[0]:
                    stats.inserted += 1
                else:
                    stats.updated += 1
            except Exception as exc:  # noqa: BLE001
                stats.errors += 1
                if len(stats.error_samples) < 10:
                    stats.error_samples.append(f"{payload.get('contrato_id')}: {type(exc).__name__}: {exc}")
                conn.rollback()
                continue
    conn.commit()


def build_manifest(
    *,
    import_run_id: str,
    table: str,
    source_repo: str,
    source_commit: str,
    snapshot_path: str | None,
    snapshot_hash: str,
    extraction_ts: str,
    stats: ImportStats,
    date_from: str | None,
    date_to: str | None,
    universe_filtered: bool,
    head_extra: str,
) -> dict[str, Any]:
    return {
        "version": "1.0.0",
        "import_run_id": import_run_id,
        "ts": utcnow_s(),
        "extra_head": head_extra,
        "source_repo": source_repo,
        "source_commit": source_commit,
        "source_table": table,
        "snapshot_path": snapshot_path,
        "snapshot_hash": snapshot_hash,
        "extraction_ts": extraction_ts,
        "period": {"from": date_from, "to": date_to},
        "universe_filtered": universe_filtered,
        "stats": asdict(stats),
        "disclaimers": [
            "snapshot_not_live",
            "presence_not_coverage",
            "history_not_freshness",
            "extra_incremental_required_after_import",
        ],
    }


def run_import(args: argparse.Namespace) -> int:
    import_run_id = args.import_run_id or str(uuid.uuid4())
    source_repo = args.source_repo
    source_commit = args.source_commit or "unknown"
    extraction_ts = args.extraction_ts or utcnow_s()
    table = args.table
    field_map = BIDS_FIELD_MAP if table == "pncp_raw_bids" else CONTRACTS_FIELD_MAP

    if not args.json_file and not args.source_dsn:
        print("ERROR: provide --json-file and/or --source-dsn", file=sys.stderr)
        return 2

    snapshot_path = None
    snapshot_hash = "none"
    raw_records: list[dict[str, Any]] = []

    if args.json_file:
        path = Path(args.json_file)
        if not path.is_file():
            print(f"ERROR: file not found: {path}", file=sys.stderr)
            return 2
        snapshot_path = str(path)
        snapshot_hash = file_sha256(path)
        raw_records = load_json_records(path)
    elif args.source_dsn:
        # Optional live read of SmartLic-shaped table (operator-provided DSN only)
        import psycopg2
        import psycopg2.extras

        conn_src = psycopg2.connect(args.source_dsn)
        try:
            with conn_src.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # paginated full scan
                offset = 0
                page = max(1, int(args.page_size))
                while True:
                    cur.execute(
                        f"SELECT * FROM {table} ORDER BY 1 OFFSET %s LIMIT %s",  # noqa: S608 — table allowlisted
                        (offset, page),
                    )
                    rows = cur.fetchall()
                    if not rows:
                        break
                    raw_records.extend([dict(r) for r in rows])
                    offset += page
                    if len(rows) < page:
                        break
            snapshot_hash = hashlib.sha256(
                json.dumps([r.get("id") for r in raw_records[:1000]], default=str).encode()
            ).hexdigest()
        finally:
            conn_src.close()

    if table not in ("pncp_raw_bids", "pncp_supplier_contracts"):
        print(f"ERROR: unsupported table {table}", file=sys.stderr)
        return 2

    stats = ImportStats(read=len(raw_records))
    mapped: list[dict[str, Any]] = []
    for raw in raw_records:
        try:
            rec = map_record(
                raw,
                field_map,
                table=table,
                import_run_id=import_run_id,
                source_repo=source_repo,
                source_commit=source_commit,
                extraction_ts=extraction_ts,
                snapshot_hash=snapshot_hash,
            )
            if not in_period(rec, args.date_from, args.date_to):
                stats.period_rejected += 1
                continue
            mapped.append(rec)
        except Exception as exc:  # noqa: BLE001
            stats.errors += 1
            if len(stats.error_samples) < 10:
                stats.error_samples.append(f"map: {type(exc).__name__}: {exc}")
    stats.mapped = len(mapped)

    universe_set: set[str] | None = None
    if args.filter_universe:
        if not args.dsn:
            print("ERROR: --filter-universe requires --dsn", file=sys.stderr)
            return 2
        universe_set = load_universe_cnpjs8(args.dsn)
        mapped, urej = filter_universe(mapped, universe_set, table=table)
        stats.universe_rejected = urej

    if args.dry_run:
        stats.rejected += sum(
            1
            for r in mapped
            if (table == "pncp_raw_bids" and not r.get("pncp_id"))
            or (table == "pncp_supplier_contracts" and not r.get("contrato_id"))
        )
        manifest = build_manifest(
            import_run_id=import_run_id,
            table=table,
            source_repo=source_repo,
            source_commit=source_commit,
            snapshot_path=snapshot_path,
            snapshot_hash=snapshot_hash,
            extraction_ts=extraction_ts,
            stats=stats,
            date_from=args.date_from,
            date_to=args.date_to,
            universe_filtered=bool(args.filter_universe),
            head_extra=args.extra_head or "unknown",
        )
        manifest["dry_run"] = True
        manifest["sample_mapped"] = [
            {k: v for k, v in r.items() if k != "_provenance"} for r in mapped[:3]
        ]
        _write_manifest(args.manifest_out, manifest)
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        return 0

    if not args.dsn:
        print("ERROR: --dsn required for non-dry-run import", file=sys.stderr)
        return 2

    import psycopg2

    conn = psycopg2.connect(args.dsn)
    try:
        if table == "pncp_raw_bids":
            upsert_bids(conn, mapped, stats)
        else:
            upsert_contracts(conn, mapped, stats)
    finally:
        conn.close()

    manifest = build_manifest(
        import_run_id=import_run_id,
        table=table,
        source_repo=source_repo,
        source_commit=source_commit,
        snapshot_path=snapshot_path,
        snapshot_hash=snapshot_hash,
        extraction_ts=extraction_ts,
        stats=stats,
        date_from=args.date_from,
        date_to=args.date_to,
        universe_filtered=bool(args.filter_universe),
        head_extra=args.extra_head or "unknown",
    )
    _write_manifest(args.manifest_out, manifest)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    # fail-closed if total hard errors dominate empty success with errors
    if stats.errors and stats.inserted == 0 and stats.updated == 0 and stats.read > 0:
        return 1
    return 0


def _write_manifest(path: str | None, manifest: dict[str, Any]) -> None:
    if not path:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Import SmartLic-shaped snapshots into Extra DataLake")
    p.add_argument("--table", choices=["pncp_raw_bids", "pncp_supplier_contracts"], required=True)
    p.add_argument("--json-file", help="Exported JSON file (list or {records:[]})")
    p.add_argument("--source-dsn", help="Optional read-only source DSN (operator-configured)")
    p.add_argument("--dsn", help="Target Extra PostgreSQL DSN", default=os.getenv("LOCAL_DATALAKE_DSN"))
    p.add_argument("--date-from", help="YYYY-MM-DD inclusive")
    p.add_argument("--date-to", help="YYYY-MM-DD inclusive")
    p.add_argument("--filter-universe", action="store_true", help="Keep only orgao_cnpj in sc_public_entities")
    p.add_argument("--years", type=int, default=3, help="Hint for docs (period still via date-from/to)")
    p.add_argument("--page-size", type=int, default=500)
    p.add_argument("--source-repo", default="https://github.com/tjsasakifln/SmartLic")
    p.add_argument("--source-commit", default="")
    p.add_argument("--extraction-ts", default="")
    p.add_argument("--import-run-id", default="")
    p.add_argument("--extra-head", default="")
    p.add_argument("--manifest-out", default="")
    p.add_argument("--dry-run", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_import(args)


if __name__ == "__main__":
    raise SystemExit(main())
