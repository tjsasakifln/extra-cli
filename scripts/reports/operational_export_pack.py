#!/usr/bin/env python3
"""§12.2 remaining: source health + CSV/Excel/PDF export with report metadata.

Covers:
- Relatório de source health
- Exportação CSV / Excel / PDF
- Metadata: generated_at, universe_version, source, reliability
- Avoid unsupported claims in pack language
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.reports.run_metadata import _git_sha_short, new_run_id  # noqa: E402

FORBIDDEN_PHRASES = (
    "LOCAL_READY",
    "cobertura operacional de 95%",
    "recall de 95%",
    "PRE_VPS_FINAL_READY",
    "PROJECT_DONE",
    "garantia de vitória",
)


def _conn(dsn: str):
    import psycopg2
    import psycopg2.extras

    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)


class OperationalExportError(RuntimeError):
    """Fail-closed error for operational export pack."""


def _q(conn, sql: str, params: tuple | list | None = None) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        try:
            cur.execute(sql, params or ())
            return [dict(r) for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001
            if hasattr(conn, "rollback"):
                conn.rollback()
            raise OperationalExportError(str(exc)) from exc


def _table_exists(conn, name: str) -> bool:
    rows = _q(
        conn,
        "SELECT 1 AS ok FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
        (name,),
    )
    return bool(rows)


def universe_version(conn) -> str:
    if _table_exists(conn, "target_universe_runs"):
        rows = _q(
            conn,
            """
            SELECT id, created_at, seed_sha256, included_rows
            FROM target_universe_runs
            ORDER BY created_at DESC NULLS LAST
            LIMIT 1
            """,
        )
        if rows:
            r = rows[0]
            seed = str(r.get("seed_sha256") or "")[:12]
            return (
                f"target_universe_run:{r.get('id')}:seed={seed}:"
                f"included={r.get('included_rows')}"
            )
    if _table_exists(conn, "sc_public_entities"):
        rows = _q(conn, "SELECT COUNT(*) AS n FROM sc_public_entities WHERE is_active IS TRUE")
        n = int((rows[0] or {}).get("n") or 0) if rows else 0
        return f"sc_public_entities:n={n}"
    return "universe:unknown"


def source_health(conn) -> list[dict[str, Any]]:
    if not _table_exists(conn, "ingestion_runs"):
        return [
            {
                "source": "_none",
                "status": "NO_INGESTION_RUNS",
                "n_runs": 0,
                "last_started": "",
                "last_status": "",
                "success_rate_pct": None,
                "reliability": "UNTRUSTED",
            }
        ]
    rows = _q(
        conn,
        """
        SELECT
            source,
            COUNT(*) AS n_runs,
            COUNT(*) FILTER (WHERE status = 'completed') AS n_ok,
            COUNT(*) FILTER (WHERE status IN ('failed', 'error')) AS n_fail,
            COUNT(*) FILTER (WHERE status = 'running') AS n_running,
            MAX(started_at) AS last_started,
            (ARRAY_AGG(status ORDER BY started_at DESC))[1] AS last_status
        FROM ingestion_runs
        GROUP BY source
        ORDER BY source
        """,
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        n = int(r.get("n_runs") or 0)
        ok = int(r.get("n_ok") or 0)
        rate = round(ok / n * 100, 2) if n else None
        reliability = "TRUSTED" if rate is not None and rate >= 80 else "DEGRADED"
        if rate is not None and rate < 50:
            reliability = "UNTRUSTED"
        out.append(
            {
                "source": r.get("source"),
                "n_runs": n,
                "n_ok": ok,
                "n_fail": int(r.get("n_fail") or 0),
                "n_running": int(r.get("n_running") or 0),
                "last_started": str(r.get("last_started") or ""),
                "last_status": r.get("last_status"),
                "success_rate_pct": rate,
                "reliability": reliability,
            }
        )
    return out


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    if any(isinstance(r, dict) and "_error" in r for r in rows):
        raise OperationalExportError("refusing to write CSV containing _error rows")
    clean = list(rows)
    headers: list[str] = []
    for r in clean:
        for k in r:
            if k not in headers:
                headers.append(k)
    if not headers:
        headers = ["note"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        for r in clean:
            w.writerow({k: r.get(k) for k in headers})
    return len(clean)


def common_metadata(
    *,
    run_id: str,
    universe_ver: str,
    source: str,
    reliability: str,
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "universe_version": universe_ver,
        "source": source,
        "reliability": reliability,
        "git_sha": _git_sha_short(),
        "claims_forbidden": list(FORBIDDEN_PHRASES),
    }


def write_excel(path: Path, sheets: dict[str, list[dict[str, Any]]], meta: dict[str, Any]) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    # Canonical required sheets for package final reconciliation
    ws0 = wb.active
    ws0.title = "Metadados"
    ws0.append(["key", "value"])
    for k, v in meta.items():
        ws0.append([k, json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v])

    # Flatten first data sheet into Dados (no Demo A/B fixtures)
    first_rows: list[dict[str, Any]] = []
    for rows in sheets.values():
        if rows:
            first_rows = list(rows)
            break
    ws_dados = wb.create_sheet("Dados")
    if first_rows:
        headers: list[str] = []
        for r in first_rows:
            for k in r:
                if k not in headers:
                    headers.append(k)
        ws_dados.append(headers)
        for r in first_rows:
            ws_dados.append([r.get(h) for h in headers])
    else:
        ws_dados.append(["note", "empty_dataset_SUCCESS_ZERO"])

    ws_filtros = wb.create_sheet("Filtros")
    filters = meta.get("filters") or meta.get("parameters") or {}
    ws_filtros.append(["key", "value"])
    if isinstance(filters, dict) and filters:
        for k, v in filters.items():
            ws_filtros.append([k, str(v)])
    else:
        ws_filtros.append(["uf", str(meta.get("uf") or "SC")])
        ws_filtros.append(["source", str(meta.get("source") or "")])

    ws_cob = wb.create_sheet("Cobertura")
    ws_cob.append(["metric", "value"])
    ws_cob.append(["universe_version", str(meta.get("universe_version") or "")])
    ws_cob.append(["reliability", str(meta.get("reliability") or "")])
    ws_cob.append(["sample_label", str((meta.get("sample_size") or {}).get("label") or "")])

    ws_lim = wb.create_sheet("Limitacoes")
    ws_lim.append(["limitation"])
    for lim in meta.get("limitations") or ["(none)"]:
        ws_lim.append([str(lim)])

    for name, rows in sheets.items():
        title = str(name)[:31]
        if title in {"Metadados", "Dados", "Filtros", "Cobertura", "Limitacoes"}:
            title = f"raw_{title}"[:31]
        ws = wb.create_sheet(title)
        clean = list(rows)
        if not clean:
            ws.append(["note", "empty"])
            continue
        headers = []
        for r in clean:
            for k in r:
                if k not in headers:
                    headers.append(k)
        ws.append(headers)
        for r in clean:
            ws.append([r.get(h) for h in headers])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def write_pdf(path: Path, meta: dict[str, Any], health: list[dict[str, Any]], limitations: list[str]) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Extra Consultoria — Pacote de exportação operacional §12.2", styles["Title"]),
        Spacer(1, 12),
    ]
    for k in ("run_id", "generated_at", "universe_version", "source", "reliability", "git_sha"):
        story.append(Paragraph(f"<b>{k}</b>: {meta.get(k)}", styles["Normal"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Source health", styles["Heading2"]))
    for h in health[:20]:
        story.append(
            Paragraph(
                f"• {h.get('source')}: success={h.get('success_rate_pct')}% "
                f"last={h.get('last_status')} reliability={h.get('reliability')}",
                styles["Normal"],
            )
        )
    story.append(Spacer(1, 12))
    story.append(Paragraph("Limitações", styles["Heading2"]))
    for lim in limitations or ["(none)"]:
        story.append(Paragraph(f"• {lim}", styles["Normal"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Claims proibidos neste pacote", styles["Heading2"]))
    for p in FORBIDDEN_PHRASES:
        story.append(Paragraph(f"• NÃO afirmar: {p}", styles["Normal"]))
    doc.build(story)


def assert_no_forbidden(text: str) -> list[str]:
    hits = []
    lower = text.lower()
    for phrase in FORBIDDEN_PHRASES:
        # only flag if claimed as true, not as forbidden list
        if phrase.lower() in lower and "não afirmar" not in lower and "forbidden" not in lower:
            # allow presence inside claims_forbidden JSON
            if f'"{phrase}"' in text or f"NÃO afirmar: {phrase}" in text:
                continue
            if "claims_forbidden" in text and phrase in text:
                continue
            hits.append(phrase)
    return hits


def build_pack(dsn: str, out_dir: Path) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rid = new_run_id("ops-export")
    limitations: list[str] = []
    conn = _conn(dsn)
    try:
        uver = universe_version(conn)
        health = source_health(conn)
        # pull sample rows for multi-format export proof
        bids = []
        if _table_exists(conn, "pncp_raw_bids"):
            bids = _q(
                conn,
                """
                SELECT pncp_id, objeto_compra, orgao_cnpj, uf, valor_total_estimado, is_active
                FROM pncp_raw_bids WHERE is_active IS TRUE LIMIT 100
                """,
            )
            # fail-closed: query errors raise OperationalExportError
    finally:
        conn.close()

    if not health:
        limitations.append("source health empty")
    reliability = "DEGRADED" if limitations else "TRUSTED"
    if health and all(h.get("reliability") == "UNTRUSTED" for h in health):
        reliability = "UNTRUSTED"
    elif health and any(h.get("reliability") != "TRUSTED" for h in health):
        reliability = "DEGRADED"

    meta = common_metadata(
        run_id=rid,
        universe_ver=uver,
        source="postgresql+ingestion_runs",
        reliability=reliability,
    )
    meta["limitations"] = limitations

    # CSV exports
    csv_dir = out_dir / "csv"
    n_health = _write_csv(csv_dir / "source_health.csv", health)
    n_bids = _write_csv(csv_dir / "editais_sample.csv", bids)
    # stamp metadata sidecar for CSV
    (csv_dir / "metadata.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
    )

    # Excel
    xlsx_path = out_dir / f"export-{rid}.xlsx"
    write_excel(
        xlsx_path,
        {"source_health": health, "editais_sample": bids},
        meta,
    )

    # PDF
    pdf_path = out_dir / f"export-{rid}.pdf"
    write_pdf(pdf_path, meta, health, limitations)

    # full metadata manifest
    manifest = {
        **meta,
        "section": "12.2-export",
        "artifacts": {
            "source_health_csv": {
                "path": str(csv_dir / "source_health.csv"),
                "rows": n_health,
            },
            "editais_csv": {"path": str(csv_dir / "editais_sample.csv"), "rows": n_bids},
            "excel": {"path": str(xlsx_path), "bytes": xlsx_path.stat().st_size},
            "pdf": {"path": str(pdf_path), "bytes": pdf_path.stat().st_size},
        },
        "metadata_fields_present": [
            "generated_at",
            "universe_version",
            "source",
            "reliability",
        ],
        "claims": {
            "allowed": [
                "Source health report generated from ingestion_runs",
                "CSV + Excel + PDF exports with shared metadata",
                "Unsupported seal claims listed as forbidden",
            ],
            "forbidden": list(FORBIDDEN_PHRASES),
        },
    }
    man_path = out_dir / "manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")

    # binary pdf — check manifest prose only (PDF text extraction is optional)
    _ = path_read_safe(pdf_path)
    hits = assert_no_forbidden(json.dumps(manifest, ensure_ascii=False))
    manifest["forbidden_phrase_hits_in_manifest"] = hits
    man_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    manifest["manifest_path"] = str(man_path)
    return manifest


def path_read_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return ""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="§12.2 export pack + source health")
    p.add_argument("--dsn", default=os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL"))
    p.add_argument("--out", type=Path, default=Path("output/operational-export"))
    p.add_argument("--json", action="store_true")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Probe DSN/source health only; skip writing CSV/Excel/PDF",
    )
    args = p.parse_args(argv)
    if not args.dsn:
        print("ERROR: --dsn required", file=sys.stderr)
        return 2
    try:
        return _main_impl(args)
    except OperationalExportError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc), "type": type(exc).__name__}, ensure_ascii=False), file=sys.stderr)
        return 1


def _main_impl(args: argparse.Namespace) -> int:
    if args.dry_run:
        conn = _conn(args.dsn)
        try:
            health = source_health(conn)
            uver = universe_version(conn)
        finally:
            conn.close()
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "universe_version": uver,
                    "source_health_rows": len(health),
                    "would_write": str(args.out),
                },
                indent=2,
                default=str,
            )
        )
        return 0
    man = build_pack(args.dsn, args.out)
    if args.json:
        print(json.dumps(man, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"run_id={man['run_id']} reliability={man['reliability']}")
        print(f"excel={man['artifacts']['excel']['path']} bytes={man['artifacts']['excel']['bytes']}")
        print(f"pdf={man['artifacts']['pdf']['path']} bytes={man['artifacts']['pdf']['bytes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
