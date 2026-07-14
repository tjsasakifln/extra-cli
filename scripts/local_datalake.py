#!/usr/bin/env python3
"""CLI de conveniência para queries ao DataLake local (PostgreSQL).

Uso:
    python scripts/local_datalake.py search --uf SP --dias 30
    python scripts/local_datalake.py search --uf SP --modalidades 5,6 --dias 90
    python scripts/local_datalake.py supplier --cnpj 12345678000199
    python scripts/local_datalake.py pricing --keywords "limpeza,conservacao" --uf SP
    python scripts/local_datalake.py competitors --cnpj 46391815000189
    python scripts/local_datalake.py stats
    python scripts/local_datalake.py detail --pncp-id 13714142000162-1-000014/2026

Requer: psycopg2, LOCAL_DATALAKE_DSN (default: postgresql://postgres@127.0.0.1:5433/pncp_datalake)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

DSN = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://postgres@127.0.0.1:5433/pncp_datalake")

_console = Console()

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_conn():
    return psycopg2.connect(DSN)


def query(sql: str, params: list[Any] | None = None) -> list[dict]:
    """Run a query and return results as list of dicts."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d[0] for d in cur.description] if cur.description else []
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def query_conn(conn, sql: str, params: list[Any] | None = None) -> list[dict]:
    """Run a query on an existing connection and return results as list of dicts."""
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def cmd_stats() -> int:
    """Show datalake table statistics."""
    CORE = [  # noqa: N806
        "pncp_raw_bids",
        "pncp_supplier_contracts",
        "enriched_entities",
        "ingestion_checkpoints",
        "ingestion_runs",
        "search_results_cache",
        "search_results_store",
        "profiles",
        "alerts",
        "pipeline_items",
        "leads",
        "classification_feedback",
        "organizations",
        "digital_products",
    ]

    total_width = 78
    print("=" * total_width)
    print(f"{'Table':<35} {'Rows':>12} {'Total':>12} {'Data':>12}")
    print("-" * total_width)

    for table in CORE:
        if not re.match(r"^[a-z_][a-z0-9_]*$", table):
            print(f"{table:<35} {'SKIP (invalid)':>12}")
            continue
        try:
            conn = get_conn()
            with conn.cursor() as cur:
                cur.execute(f'SELECT count(*) FROM "{table}"')  # noqa: S608 -- table validated by regex ^[a-z_][a-z0-9_]*$
                cnt = cur.fetchone()[0]
                cur.execute(f"SELECT pg_size_pretty(pg_total_relation_size('\"{table}\"'::regclass))")
                total_sz = cur.fetchone()[0]
                cur.execute(f"SELECT pg_size_pretty(pg_relation_size('\"{table}\"'::regclass))")
                data_sz = cur.fetchone()[0]
            conn.close()
            print(f"{table:<35} {cnt:>12,} {total_sz:>12} {data_sz:>12}")
        except Exception as e:
            print(f"{table:<35} {'ERR':>12} {'-':>12} {'-':>12}  ({e})")

    print("=" * total_width)
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    """Search pncp_raw_bids via search_datalake RPC."""
    ufs = [u.strip().upper() for u in args.uf.split(",")] if args.uf else None
    modalidades = [int(m.strip()) for m in args.modalidades.split(",")] if args.modalidades else None
    dias = args.dias or 30
    limit = min(args.limit, 5000)

    end_date = date.today()
    start_date = end_date - timedelta(days=dias)

    params: dict[str, Any] = {
        "p_ufs": ufs,
        "p_date_start": start_date.isoformat(),
        "p_date_end": end_date.isoformat(),
        "p_modalidades": modalidades,
        "p_modo": args.modo or "publicacao",
        "p_limit": limit,
    }

    if args.query:
        params["p_tsquery"] = args.query
    if args.texto:
        params["p_websearch_text"] = args.texto
    if args.valor_min:
        params["p_valor_min"] = args.valor_min
    if args.valor_max:
        params["p_valor_max"] = args.valor_max

    # Build named parameter call — use 12-param overload
    full_params: dict[str, Any] = {
        "p_ufs": ufs,
        "p_date_start": start_date,
        "p_date_end": end_date,
        "p_tsquery": args.query,
        "p_websearch_text": args.texto,
        "p_modalidades": modalidades,
        "p_valor_min": args.valor_min,
        "p_valor_max": args.valor_max,
        "p_esferas": None,
        "p_modo": args.modo or "publicacao",
        "p_limit": limit,
        "p_embedding": None,
    }
    arg_parts = [f'"{k}" := %s' for k in full_params]
    sql = f'SELECT * FROM "public"."search_datalake"({", ".join(arg_parts)})'  # noqa: S608 -- function name hardcoded, values via %s placeholders
    rows = query(sql, list(full_params.values()))

    # Output
    if args.json:
        print(json.dumps(rows, indent=2, default=str, ensure_ascii=False))
    else:
        print(f"Found: {len(rows)} editais\n")
        for i, r in enumerate(rows[: args.head]):
            print(f"--- [{i + 1}] {r.get('pncp_id')} ---")
            print(f"  Objeto:    {(r.get('objeto_compra') or '')[:120]}")
            print(f"  Órgão:     {r.get('orgao_razao_social')}")
            print(f"  UF/Mun:    {r.get('uf')}/{r.get('municipio')}")
            print(f"  Modalidade: {r.get('modalidade_nome')}")
            print(f"  Valor:     R$ {r.get('valor_total_estimado', 0):,.2f}")
            print(f"  Data pub:  {r.get('data_publicacao')}")
            print(f"  Situação:  {r.get('situacao_compra')}")
            print()
        if len(rows) > args.head:
            print(f"... and {len(rows) - args.head} more (use --head N to see more, or --json for full output)")

    return 0 if rows else 1


def cmd_supplier(args: argparse.Namespace) -> int:
    """Query pncp_supplier_contracts."""
    cnpj = "".join(ch for ch in (args.cnpj or "") if ch.isdigit())
    if not cnpj:
        print("ERROR: --cnpj required", file=sys.stderr)
        return 1

    dias = args.dias or 365
    end_date = date.today()
    end_date - timedelta(days=dias)

    rows = query(
        """SELECT ni_fornecedor, nome_fornecedor, orgao_cnpj, orgao_nome, uf, municipio,
                  valor_global, data_assinatura, objeto_contrato, numero_controle_pncp
           FROM pncp_supplier_contracts
           WHERE ni_fornecedor = %s AND is_active = true
           ORDER BY data_assinatura DESC
           LIMIT %s""",
        [cnpj, min(args.limit, 1000)],
    )

    if args.json:
        print(json.dumps(rows, indent=2, default=str, ensure_ascii=False))
    else:
        total_valor = sum(r.get("valor_global") or 0 for r in rows)
        print(f"Found: {len(rows)} contracts for CNPJ {cnpj}")
        print(f"Total value: R$ {total_valor:,.2f}")
        print()
        for r in rows[: args.head]:
            print(f"--- {r.get('numero_controle_pncp')} ---")
            print(f"  Fornecedor: {r.get('nome_fornecedor')}")
            print(f"  Órgão:      {r.get('orgao_nome')} ({r.get('uf')}/{r.get('municipio')})")
            print(f"  Valor:      R$ {r.get('valor_global', 0):,.2f}")
            print(f"  Data:       {r.get('data_assinatura')}")
            print(f"  Objeto:     {(r.get('objeto_contrato') or '')[:150]}")
            print()

    return 0 if rows else 1


def cmd_pricing(args: argparse.Namespace) -> int:
    """Aggregate pricing stats."""
    keywords = [k.strip().lower() for k in (args.keywords or "").split(",") if k.strip()]
    if not keywords:
        print("ERROR: --keywords required (comma-separated)", file=sys.stderr)
        return 1

    uf = args.uf.upper() if args.uf else None
    meses = args.meses or 12
    end_date = date.today()
    start_date = end_date - timedelta(days=int(meses * 30.4))

    # Build query
    wheres = ["is_active = true", "valor_global > %s", "data_assinatura >= %s"]
    params: list[Any] = [1.0, start_date]
    if uf:
        wheres.append("uf = %s")
        params.append(uf)
    for kw in keywords:
        wheres.append("objeto_contrato ILIKE %s")
        params.append(f"%{kw}%")

    sql = f"""SELECT valor_global FROM pncp_supplier_contracts
              WHERE {" AND ".join(wheres)}
              ORDER BY data_assinatura DESC LIMIT 1000"""  # noqa: S608 -- all values parameterized via %s
    rows = query(sql, params)

    if not rows:
        print("No contracts found.")
        return 1

    valores = sorted(float(r["valor_global"]) for r in rows)
    n = len(valores)
    media = sum(valores) / n
    var = sum((v - media) ** 2 for v in valores) / n
    dp = var**0.5
    cv = (dp / media * 100) if media > 0 else 0.0

    def pct(p: float) -> float:
        if n == 1:
            return valores[0]
        k = (n - 1) * p
        f = int(k)
        c = min(f + 1, n - 1)
        return valores[f] + (valores[c] - valores[f]) * (k - f) if f != c else valores[f]

    print(f"Pricing stats for: {', '.join(keywords)}")
    print(f"Filter: UF={uf or 'all'}, {meses} months")
    print(f"Sample: {n} contracts")
    print(f"{'N':<12} {n}")
    print(f"{'P10':<12} R$ {pct(0.10):,.2f}")
    print(f"{'P25':<12} R$ {pct(0.25):,.2f}")
    print(f"{'Median':<12} R$ {pct(0.50):,.2f}")
    print(f"{'P75':<12} R$ {pct(0.75):,.2f}")
    print(f"{'P90':<12} R$ {pct(0.90):,.2f}")
    print(f"{'Mean':<12} R$ {media:,.2f}")
    print(f"{'StdDev':<12} R$ {dp:,.2f}")
    print(f"{'CV':<12} {cv:.1f}%")

    return 0


def cmd_competitors(args: argparse.Namespace) -> int:
    """Top competitors from pncp_supplier_contracts grouped by fornecedor."""
    keywords = [k.strip().lower() for k in (args.keywords or "").split(",") if k.strip()]
    meses = args.meses or 24
    end_date = date.today()
    start_date = end_date - timedelta(days=int(meses * 30.4))

    wheres = ["is_active = true", "data_assinatura >= %s"]
    params: list[Any] = [start_date]

    if keywords:
        for kw in keywords:
            wheres.append("objeto_contrato ILIKE %s")
            params.append(f"%{kw}%")

    sql = f"""SELECT ni_fornecedor, nome_fornecedor,
                     count(*) as n_contratos,
                     sum(valor_global) as valor_total,
                     max(data_assinatura) as ultimo_contrato
              FROM pncp_supplier_contracts
              WHERE {" AND ".join(wheres)}
              GROUP BY ni_fornecedor, nome_fornecedor
              ORDER BY n_contratos DESC, valor_total DESC
              LIMIT %s"""  # noqa: S608 -- all values parameterized via %s
    params.append(min(args.limit, 20))

    rows = query(sql, params)

    print(f"Top {len(rows)} competitors")
    if keywords:
        print(f"Sector: {', '.join(keywords)}")
    print(f"Period: {meses} months")
    print()
    print(f"{'#':<4} {'Fornecedor':<40} {'Contratos':>10} {'Valor Total':>18} {'Último':>12}")
    print("-" * 86)
    for i, r in enumerate(rows):
        print(
            f"{i + 1:<4} {(r['nome_fornecedor'] or 'N/A')[:39]:<40} "
            f"{r['n_contratos']:>10,} R$ {r['valor_total']:>15,.2f} "
            f"{str(r['ultimo_contrato'])[:10]:>12}"
        )

    return 0


def cmd_detail(args: argparse.Namespace) -> int:
    """Get details for a specific PNCP bid."""
    if not args.pncp_id:
        print("ERROR: --pncp-id required", file=sys.stderr)
        return 1

    rows = query(
        """SELECT * FROM pncp_raw_bids
           WHERE pncp_id = %s AND is_active = true
           LIMIT 1""",
        [args.pncp_id],
    )

    if not rows:
        print(f"Bid not found: {args.pncp_id}")
        return 1

    r = rows[0]
    if args.json:
        print(json.dumps(r, indent=2, default=str, ensure_ascii=False))
    else:
        for k, v in r.items():
            val = str(v) if v is not None else "(null)"
            if len(val) > 200:
                val = val[:200] + "..."
            print(f"{k:<30} {val}")

    return 0


# ---------------------------------------------------------------------------
# Coverage Dashboard
# ---------------------------------------------------------------------------


def _fetch_dashboard_data(conn) -> dict:
    """Fetch all coverage dashboard data in a single pass."""
    data: dict[str, Any] = {}

    # Overall coverage stats
    data["overall"] = query_conn(
        conn,
        """SELECT
            COUNT(DISTINCT e.id) AS total_entities,
            COUNT(DISTINCT CASE WHEN ec.is_covered THEN e.id END) AS covered,
            ROUND(100.0 * COUNT(DISTINCT CASE WHEN ec.is_covered THEN e.id END)
                  / NULLIF(COUNT(DISTINCT e.id), 0), 1) AS pct
         FROM sc_public_entities e
         LEFT JOIN entity_coverage ec ON e.id = ec.entity_id AND ec.is_covered = TRUE
         WHERE e.is_active = TRUE""",
    )[0]

    # Per-source coverage
    data["by_source"] = query_conn(
        conn,
        """SELECT
            ec.source,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE ec.is_covered) AS covered,
            ROUND(100.0 * COUNT(*) FILTER (WHERE ec.is_covered) / NULLIF(COUNT(*), 0), 1) AS pct
         FROM entity_coverage ec
         WHERE EXISTS (SELECT 1 FROM sc_public_entities e WHERE e.id = ec.entity_id AND e.is_active = TRUE)
         GROUP BY ec.source
         ORDER BY ec.source""",
    )

    # By natureza juridica
    data["by_natureza"] = query_conn(
        conn,
        """SELECT
            e.natureza_juridica,
            COUNT(DISTINCT e.id) AS total,
            COUNT(DISTINCT CASE WHEN ec.is_covered THEN e.id END) AS covered,
            ROUND(100.0 * COUNT(DISTINCT CASE WHEN ec.is_covered THEN e.id END)
                  / NULLIF(COUNT(DISTINCT e.id), 0), 1) AS pct
         FROM sc_public_entities e
         LEFT JOIN entity_coverage ec ON e.id = ec.entity_id AND ec.is_covered = TRUE
         WHERE e.is_active = TRUE AND e.natureza_juridica IS NOT NULL
         GROUP BY e.natureza_juridica
         ORDER BY total DESC""",
    )

    # Top 10 municipios com gaps (using v_coverage_gaps_by_municipio)
    data["top_gaps_municipio"] = query_conn(
        conn,
        """SELECT municipio, entes_descobertos
           FROM v_coverage_gaps_by_municipio
           ORDER BY entes_descobertos DESC
           LIMIT 10""",
    )

    # Snapshot count
    data["snapshot_count"] = query_conn(
        conn,
        """SELECT COUNT(*) AS cnt FROM coverage_snapshots""",
    )[0]["cnt"]

    # Recent trend (last 4 weeks)
    data["trend"] = query_conn(
        conn,
        """SELECT snapshot_date AS week_start, pct_covered,
                  variacao_pct AS pct_change
           FROM v_coverage_trend
           WHERE source = 'total'
           ORDER BY snapshot_date DESC
           LIMIT 4""",
    )

    return data


def cmd_coverage(args: argparse.Namespace) -> int:
    """Coverage dashboard and management.

    Usage:
        coverage                          Full dashboard (default)
        coverage --baseline               Detailed baseline (from monitor)
        coverage --gaps                   List specific uncovered entities
        coverage --snapshot               Generate daily snapshot
        coverage --export                  Export gaps to Excel
    """
    from scripts.crawl.monitor import print_coverage_report, report_coverage

    conn = get_conn()
    try:
        # --snapshot: generate daily snapshot
        if args.snapshot:
            try:
                result = query_conn(conn, "SELECT generate_coverage_snapshot() AS inserted")
                inserted = result[0]["inserted"] if result else 0
                _console.print(f"\n[green]Snapshot gerado: {date.today()} ({inserted} fontes)[/green]")

                # Show the snapshot data
                snap_data = query_conn(
                    conn,
                    """SELECT source, total_entities, covered_entities, pct_covered
                       FROM coverage_snapshots
                       WHERE snapshot_date = CURRENT_DATE
                       ORDER BY source""",
                )
                if snap_data:
                    snap_table = Table(title="Snapshots do Dia", box=box.SIMPLE)
                    snap_table.add_column("Fonte", style="cyan")
                    snap_table.add_column("Total", justify="right")
                    snap_table.add_column("Cobertos", justify="right")
                    snap_table.add_column("%", justify="right")
                    for r in snap_data:
                        snap_table.add_row(
                            r["source"],
                            str(r["total_entities"]),
                            str(r["covered_entities"]),
                            f"{r['pct_covered']:.1f}%",
                        )
                    _console.print(snap_table)
            except Exception as e:
                _console.print(f"[red]Erro ao gerar snapshot: {e}[/red]")
                return 1

        # --baseline: detailed coverage report from monitor
        if args.baseline:
            _console.print("\n[bold cyan]=== BASELINE ===[/bold cyan]")
            result = report_coverage(conn)
            print_coverage_report(result)

        # --gaps: list specific uncovered entities
        if args.gaps:
            gaps = query_conn(
                conn,
                """SELECT municipio, entes_descobertos
                   FROM v_coverage_gaps_by_municipio
                   ORDER BY entes_descobertos DESC
                   LIMIT 20""",
            )
            if gaps:
                gap_table = Table(title="Top 20 Municipios com Gaps", box=box.SIMPLE)
                gap_table.add_column("Municipio", style="yellow")
                gap_table.add_column("Entes sem Cobertura", justify="right")
                for g in gaps:
                    gap_table.add_row(g["municipio"] or "N/A", str(g["entes_descobertos"]))
                _console.print(gap_table)
            else:
                _console.print("[green]Nenhum gap encontrado![/green]")

        # --export: export gaps to Excel
        if args.export:
            _export_gaps_to_excel(conn)

        # No flags: show full dashboard
        if not any([args.baseline, args.gaps, args.snapshot, args.export]):
            data = _fetch_dashboard_data(conn)

            # Overall coverage
            o = data["overall"]
            _console.print(
                Panel(
                    f"[bold white]Cobertura Total: [green]{o['pct']}%[/green] "
                    f"({o['covered']}/{o['total_entities']} entes)[/bold white]",
                    box=box.ROUNDED,
                    style="blue",
                )
            )

            # Per-source
            src_table = Table(title="Cobertura por Fonte", box=box.SIMPLE)
            src_table.add_column("Fonte", style="cyan")
            src_table.add_column("Total", justify="right")
            src_table.add_column("Cobertos", justify="right")
            src_table.add_column("%", justify="right")
            for s in data["by_source"]:
                src_table.add_row(s["source"], str(s["total"]), str(s["covered"]), f"{s['pct']}%")
            _console.print(src_table)

            # By natureza juridica
            nat_table = Table(title="Cobertura por Natureza Juridica", box=box.SIMPLE)
            nat_table.add_column("Natureza", style="cyan")
            nat_table.add_column("Total", justify="right")
            nat_table.add_column("Cobertos", justify="right")
            nat_table.add_column("%", justify="right")
            for n in data["by_natureza"]:
                nat_table.add_row(
                    n["natureza_juridica"][:40],
                    str(n["total"]),
                    str(n["covered"]),
                    f"{n['pct']}%",
                )
            _console.print(nat_table)

            # Top 10 municipios com gaps
            if data["top_gaps_municipio"]:
                gap_table = Table(title="Top 10 Municipios com Gaps", box=box.SIMPLE)
                gap_table.add_column("Municipio", style="yellow")
                gap_table.add_column("Entes sem Cobertura", justify="right")
                for g in data["top_gaps_municipio"]:
                    gap_table.add_row(g["municipio"] or "N/A", str(g["entes_descobertos"]))
                _console.print(gap_table)

            # Trend (if data exists)
            if data["trend"]:
                trend_table = Table(title="Tendencia (ultimas 4 semanas)", box=box.SIMPLE)
                trend_table.add_column("Data", style="cyan")
                trend_table.add_column("% Coberto", justify="right")
                trend_table.add_column("Variacao", justify="right")
                for t in data["trend"]:
                    pct_change = t.get("pct_change")
                    change_str = f"{pct_change:+.1f}" if pct_change is not None else "N/A"
                    trend_table.add_row(
                        str(t["week_start"]),
                        f"{t['pct_covered']:.1f}%",
                        change_str,
                    )
                _console.print(trend_table)

            # Snapshot info
            snap_cnt = data["snapshot_count"]
            _console.print(
                f"\n[dim]Snapshots historicos: {snap_cnt} entradas\n"
                "Use --snapshot para gerar novo snapshot\n"
                "Use --export para exportar gaps para Excel[/dim]"
            )

    finally:
        conn.close()

    return 0


def _export_gaps_to_excel(conn) -> None:
    """Export coverage gaps to Excel using the coverage_gaps module."""
    from scripts.reports.coverage_gaps import export_excel, fetch_all_gaps, fetch_gaps_by_municipio

    gaps = fetch_all_gaps(conn)
    gaps_by_muni = fetch_gaps_by_municipio(conn)

    if not gaps:
        _console.print("[green]Nenhum gap de cobertura encontrado.[/green]")
        return

    output_dir = _PROJECT_ROOT / "output" / "reports" / "coverage"
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / f"gaps-{date.today().isoformat()}.xlsx"

    export_excel(gaps, gaps_by_muni, str(filepath))
    _console.print(f"[green]Gaps exportados: {filepath}[/green]")


def main() -> int:
    parser = argparse.ArgumentParser(description="DataLake Local CLI")
    sub = parser.add_subparsers(dest="command")

    # stats
    sub.add_parser("stats", help="Show table statistics")

    # search
    p_search = sub.add_parser("search", help="Search pncp_raw_bids")
    p_search.add_argument("--uf", help="UF filter (comma-separated)")
    p_search.add_argument("--dias", type=int, default=30, help="Days back (default: 30)")
    p_search.add_argument("--modalidades", help="Modalidade IDs (comma-separated, e.g. 5,6)")
    p_search.add_argument("--query", help="TSQuery (Portuguese FTS)")
    p_search.add_argument("--texto", help="Free text search (websearch_to_tsquery)")
    p_search.add_argument("--valor-min", type=float, help="Min value")
    p_search.add_argument("--valor-max", type=float, help="Max value")
    p_search.add_argument("--modo", default="publicacao", help="publicacao | abertas")
    p_search.add_argument("--limit", type=int, default=200)
    p_search.add_argument("--head", type=int, default=10, help="Display first N results")
    p_search.add_argument("--json", action="store_true", help="JSON output")

    # supplier
    p_supplier = sub.add_parser("supplier", help="Query supplier contracts")
    p_supplier.add_argument("--cnpj", help="Supplier CNPJ (14 digits)")
    p_supplier.add_argument("--dias", type=int, default=365, help="Days back")
    p_supplier.add_argument("--limit", type=int, default=200)
    p_supplier.add_argument("--head", type=int, default=10)
    p_supplier.add_argument("--json", action="store_true", help="JSON output")

    # pricing
    p_pricing = sub.add_parser("pricing", help="Aggregate pricing stats")
    p_pricing.add_argument("--keywords", required=True, help="Keywords (comma-separated, AND logic)")
    p_pricing.add_argument("--uf", help="UF filter")
    p_pricing.add_argument("--meses", type=int, default=12, help="Months back")

    # competitors
    p_comp = sub.add_parser("competitors", help="Top competitors")
    p_comp.add_argument("--keywords", help="Sector keywords (comma-separated)")
    p_comp.add_argument("--meses", type=int, default=24, help="Months back")
    p_comp.add_argument("--limit", type=int, default=10)

    # detail
    p_detail = sub.add_parser("detail", help="Get PNCP bid detail")
    p_detail.add_argument("--pncp-id", help="PNCP ID (numeroControlePNCP)")
    p_detail.add_argument("--json", action="store_true", help="JSON output")

    # coverage
    p_cov = sub.add_parser("coverage", help="Coverage dashboard and management")
    p_cov.add_argument("--baseline", action="store_true", help="Show detailed baseline (from monitor)")
    p_cov.add_argument("--gaps", action="store_true", help="List top gaps by municipio")
    p_cov.add_argument("--snapshot", action="store_true", help="Generate daily coverage snapshot")
    p_cov.add_argument("--export", action="store_true", help="Export gaps to Excel")

    args = parser.parse_args()

    if args.command == "stats":
        return cmd_stats()
    elif args.command == "search":
        return cmd_search(args)
    elif args.command == "supplier":
        return cmd_supplier(args)
    elif args.command == "pricing":
        return cmd_pricing(args)
    elif args.command == "competitors":
        return cmd_competitors(args)
    elif args.command == "detail":
        return cmd_detail(args)
    elif args.command == "coverage":
        return cmd_coverage(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
