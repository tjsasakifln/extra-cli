#!/usr/bin/env python3
"""Opportunity Intelligence CLI — consult and export open bidding opportunities.

Commands:
    radar        — Execute the QW-01 auditable radar
    list         — List opportunities with filters
    show ID      — Show full details for one opportunity
    explain ID   — Explain ranking factors for one opportunity
    coverage     — Coverage dashboard by source/entity
    source-health — Health check per source
    update       — Run crawl for one or all sources
    export       — Export as JSON or CSV

Usage:
    python scripts/opportunity_intel/cli.py list --status open --uf SC --limit 20
    python scripts/opportunity_intel/cli.py show 42
    python scripts/opportunity_intel/cli.py explain 42
    python scripts/opportunity_intel/cli.py coverage
    python scripts/opportunity_intel/cli.py source-health
    python scripts/opportunity_intel/cli.py update --source pncp
    python scripts/opportunity_intel/cli.py export --format csv --output opportunities.csv
    python -m scripts.opportunity_intel.cli radar --profile config/client_profiles/extra.yaml
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
import psycopg2.sql

# Auto-load .env from project root
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"
if _ENV_FILE.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_ENV_FILE)
    except ImportError:
        pass

_logger = logging.getLogger(__name__)

DEFAULT_DSN = os.getenv(
    "LOCAL_DATALAKE_DSN",
    "postgresql://test:test@127.0.0.1:5433/pncp_datalake",
)

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _get_conn(dsn: str | None = None) -> Any:
    conn = psycopg2.connect(dsn or DEFAULT_DSN)
    conn.autocommit = True
    return conn


def _query(conn: Any, sql: Any, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> None:
    """List opportunities with filters."""
    conn = _get_conn(args.dsn)
    conditions = ["is_active = TRUE"]
    params: list[Any] = []

    if args.status:
        statuses = [s.strip() for s in args.status.split(",")]
        placeholders = ",".join(["%s"] * len(statuses))
        conditions.append(f"status_canonico IN ({placeholders})")
        params.extend(statuses)
    if args.uf:
        conditions.append("uf = %s")
        params.append(args.uf.upper())
    if args.municipio:
        conditions.append("municipio ILIKE %s")
        params.append(f"%{args.municipio}%")
    if args.modalidade:
        conditions.append("modalidade ILIKE %s")
        params.append(f"%{args.modalidade}%")
    if args.ranking:
        rankings = [r.strip() for r in args.ranking.split(",")]
        placeholders = ",".join(["%s"] * len(rankings))
        conditions.append(f"ranking IN ({placeholders})")
        params.extend(rankings)
    if args.source:
        conditions.append("source = %s")
        params.append(args.source)
    if args.search:
        conditions.append("objeto ILIKE %s")
        params.append(f"%{args.search}%")
    if args.valor_min:
        conditions.append("valor_estimado >= %s")
        params.append(float(args.valor_min))

    where = " AND ".join(conditions)
    order = "ORDER BY ranking_score DESC, data_abertura ASC NULLS LAST"
    limit = min(500, max(1, args.limit or 50))
    query = psycopg2.sql.SQL("SELECT * FROM opportunity_intel WHERE {} {} LIMIT %s").format(
        psycopg2.sql.SQL(where),
        psycopg2.sql.SQL(order),
    )
    params.append(limit)
    rows = _query(conn, query, tuple(params))

    if not rows:
        print("Nenhuma oportunidade encontrada.")
        return

    _print_table(rows, args.format)
    conn.close()


def cmd_show(args: argparse.Namespace) -> None:
    """Show full details for one opportunity."""
    conn = _get_conn(args.dsn)

    if args.id.isdigit():
        sql = "SELECT * FROM opportunity_intel WHERE id = %s"
        rows = _query(conn, sql, (int(args.id),))
    else:
        sql = "SELECT * FROM opportunity_intel WHERE numero_controle_pncp = %s"
        rows = _query(conn, sql, (args.id,))

    if not rows:
        print(f"Oportunidade não encontrada: {args.id}")
        sys.exit(1)

    row = rows[0]
    _print_detail(row)
    conn.close()


def cmd_explain(args: argparse.Namespace) -> None:
    """Explain ranking factors for one opportunity."""
    conn = _get_conn(args.dsn)

    if args.id.isdigit():
        sql = "SELECT * FROM opportunity_intel WHERE id = %s"
        rows = _query(conn, sql, (int(args.id),))
    else:
        sql = "SELECT * FROM opportunity_intel WHERE numero_controle_pncp = %s"
        rows = _query(conn, sql, (args.id,))

    if not rows:
        print(f"Oportunidade não encontrada: {args.id}")
        sys.exit(1)

    row = rows[0]
    _print_explain(row)
    conn.close()


def cmd_coverage(args: argparse.Namespace) -> None:
    """Coverage dashboard."""
    conn = _get_conn(args.dsn)

    # Overall stats
    print("\n=== COBERTURA DE OPORTUNIDADES ===\n")

    rows = _query(
        conn,
        """
        SELECT
            source,
            status_canonico,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE ranking = 'GO') AS go_count,
            COUNT(*) FILTER (WHERE ranking = 'REVIEW') AS review_count,
            COUNT(*) FILTER (WHERE ranking = 'NO_GO') AS no_go_count
        FROM opportunity_intel
        WHERE is_active = TRUE
        GROUP BY source, status_canonico
        ORDER BY source, status_canonico
    """,
    )

    if rows:
        _print_table(rows, args.format)

    # Coverage summary
    print("\n--- POR ENTIDADE ---\n")
    cov_rows = _query(conn, "SELECT * FROM v_opportunity_coverage_summary")
    if cov_rows:
        _print_table(cov_rows, args.format)
    else:
        print("Nenhum dado de cobertura disponível (execute 'update' primeiro).")

    conn.close()


def cmd_source_health(args: argparse.Namespace) -> None:
    """Health check per source."""
    conn = _get_conn(args.dsn)

    rows = _query(
        conn,
        """
        SELECT
            source,
            COUNT(*) AS total_records,
            COUNT(*) FILTER (WHERE status_canonico = 'open') AS open_count,
            COUNT(*) FILTER (WHERE status_canonico = 'upcoming') AS upcoming_count,
            COUNT(*) FILTER (WHERE status_canonico = 'unknown') AS unknown_count,
            MIN(ingested_at) AS first_ingested,
            MAX(ingested_at) AS last_ingested,
            MAX(data_encerramento) AS latest_deadline
        FROM opportunity_intel
        WHERE is_active = TRUE
        GROUP BY source
        ORDER BY source
    """,
    )

    if rows:
        _print_table(rows, args.format)
    else:
        print("Nenhum dado de oportunidade disponível.")

    # Run history
    print("\n--- ÚLTIMAS EXECUÇÕES ---\n")
    run_rows = _query(
        conn,
        """
        SELECT id, source, status, started_at, finished_at,
               records_fetched, records_new, records_updated, error_message
        FROM opportunity_runs
        ORDER BY started_at DESC
        LIMIT 10
    """,
    )
    if run_rows:
        _print_table(run_rows, args.format)

    conn.close()


def cmd_update(args: argparse.Namespace) -> None:
    """Run crawl for specified source(s)."""
    # Add project root to sys.path for cross-package import
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.abspath(os.path.join(_script_dir, "..", ".."))
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)

    from scripts.opportunity_intel.pncp_crawler import (
        PncpOpportunityCrawler,
        PncpPublicationCrawler,
    )

    sources = args.source.split(",") if args.source != "all" else ["pncp", "pncp_publication"]

    for source in sources:
        source = source.strip()
        print(f"\n=== Atualizando fonte: {source} ===\n")

        crawler: Any = None
        if source == "pncp":
            crawler = PncpOpportunityCrawler(dsn=args.dsn)
        elif source == "pncp_publication":
            crawler = PncpPublicationCrawler(dsn=args.dsn)
        else:
            print(f"Fonte não suportada para update: {source}")
            continue

        try:
            from scripts.crawl.pncp_contract import DEFAULT_MODALIDADES
            from scripts.opportunity_intel.crawler_base import CrawlRequest

            # PNCP /contratacoes/proposta requires codigoModalidadeContratacao.
            # Without a target, loop modalidades 1–19 (UF=SC in crawler).
            targets: list[str | None]
            if source == "pncp":
                targets = [f"modalidade:{m}" for m in DEFAULT_MODALIDADES]
            else:
                targets = [None]

            aggregated: dict[str, Any] = {
                "status": "success",
                "counts": {"fetched": 0, "new": 0, "updated": 0, "modalidades_ok": 0, "modalidades_failed": 0},
                "error": None,
                "errors": [],
            }
            for target in targets:
                request = CrawlRequest(
                    source=source,
                    date_from=date.today() - timedelta(days=7),
                    date_to=date.today(),
                    mode=args.mode or "full",
                    limit=args.limit,
                    target=target,
                )
                result = crawler.run(request)
                counts = result.get("counts") or {}
                for k in ("fetched", "new", "updated"):
                    if k in counts and isinstance(counts[k], int):
                        aggregated["counts"][k] = aggregated["counts"].get(k, 0) + counts[k]
                st = str(result.get("status") or "")
                # completed_zero = auditable empty result (success_zero path) — counts as OK
                if st in {"success", "ok", "partial", "completed_zero", "completed"}:
                    aggregated["counts"]["modalidades_ok"] += 1
                    if st == "partial":
                        aggregated["status"] = "partial"
                else:
                    aggregated["counts"]["modalidades_failed"] += 1
                    aggregated["status"] = (
                        "partial" if aggregated["counts"]["modalidades_ok"] else "failed"
                    )
                    if result.get("error"):
                        aggregated["errors"].append({"target": target, "error": result["error"]})
                print(
                    f"  target={target or '-'} status={result.get('status')} "
                    f"counts={json.dumps(counts, default=str)}"
                )
            if aggregated["errors"]:
                aggregated["error"] = "; ".join(
                    f"{e['target']}:{e['error']}" for e in aggregated["errors"][:5]
                )
            print(f"Status: {aggregated['status']}")
            print(f"Counts: {json.dumps(aggregated['counts'], indent=2)}")
            if aggregated["error"]:
                print(f"Error: {aggregated['error']}")
        finally:
            crawler.close()


def cmd_export(args: argparse.Namespace) -> None:
    """Export opportunities as JSON or CSV."""
    conn = _get_conn(args.dsn)

    conditions = ["is_active = TRUE"]
    params: list[Any] = []

    if args.status:
        statuses = [s.strip() for s in args.status.split(",")]
        placeholders = ",".join(["%s"] * len(statuses))
        conditions.append(f"status_canonico IN ({placeholders})")
        params.extend(statuses)
    if args.ranking:
        rankings = [r.strip() for r in args.ranking.split(",")]
        placeholders = ",".join(["%s"] * len(rankings))
        conditions.append(f"ranking IN ({placeholders})")
        params.extend(rankings)

    where = " AND ".join(conditions)
    limit = min(5000, max(1, args.limit or 500))
    query = psycopg2.sql.SQL("SELECT * FROM opportunity_intel WHERE {} ORDER BY ranking_score DESC LIMIT %s").format(
        psycopg2.sql.SQL(where)
    )
    params.append(limit)

    rows = _query(conn, query, tuple(params))

    output_path = args.output or f"opportunity_export.{args.format}"

    if args.format == "json":
        with open(output_path, "w") as f:
            json.dump(rows, f, default=str, indent=2, ensure_ascii=False)
    elif args.format == "csv":
        if not rows:
            print("Nenhum dado para exportar.")
            return
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            for row in rows:
                # Convert JSONB/arrays to string for CSV
                clean_row = {}
                for k, v in row.items():
                    if isinstance(v, (dict, list)):
                        clean_row[k] = json.dumps(v, default=str)
                    else:
                        clean_row[k] = v
                writer.writerow(clean_row)

    print(f"Exportado {len(rows)} registros para {output_path}")
    conn.close()


def cmd_radar(args: argparse.Namespace) -> None:
    """Execute the PostgreSQL-only QW-01 auditable radar."""
    from scripts.opportunity_intel.radar import run_radar

    execution = run_radar(
        dsn=args.dsn,
        profile_path=args.profile,
        seed_path=args.seed,
        window_days=args.window_days,
        output_root=args.output_dir,
        update_mode=args.update,
        timeout=args.timeout,
        max_retries=args.max_retries,
        max_pages=args.max_pages,
        max_records=args.max_records,
    )
    print(json.dumps(execution.__dict__, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(execution.exit_code)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def _print_table(rows: list[dict[str, Any]], fmt: str = "table") -> None:
    """Print rows as table or JSON."""
    if fmt == "json":
        print(json.dumps(rows, default=str, indent=2, ensure_ascii=False))
        return

    if not rows:
        print("Nenhum resultado.")
        return

    # Simple columnar output
    columns = list(rows[0].keys())
    # Truncate to terminal-friendly columns
    display_cols = [
        c
        for c in columns
        if c
        not in (
            "content_hash",
            "tsv",
            "qualidade_fatores",
            "ranking_fatores",
            "proveniencia",
            "metadata",
            "link_anexos",
        )
    ][:10]

    # Header
    header = " | ".join(f"{c[:20]:20s}" for c in display_cols)
    print(header)
    print("-" * len(header))

    for row in rows[:50]:
        values = []
        for c in display_cols:
            v = row.get(c, "")
            s = str(v)[:20] if v is not None else ""
            values.append(f"{s:20s}")
        print(" | ".join(values))


def _print_detail(row: dict[str, Any]) -> None:
    """Print full detail for one opportunity."""
    print(f"\n{'=' * 70}")
    print(f"OPORTUNIDADE #{row.get('id')}")
    print(f"{'=' * 70}")

    sections: list[tuple[str, list[tuple[str, Any]]]] = [
        (
            "Identificação",
            [
                ("Fonte", row.get("source")),
                ("ID na Fonte", row.get("source_id")),
                ("PNCP ID", row.get("numero_controle_pncp")),
                ("URL", row.get("source_url")),
                ("Content Hash", row.get("content_hash")),
            ],
        ),
        (
            "Órgão/Ente",
            [
                ("CNPJ", row.get("orgao_cnpj")),
                ("Nome", row.get("orgao_nome")),
                ("UF", row.get("uf")),
                ("Município", row.get("municipio")),
                ("Código IBGE", row.get("codigo_ibge")),
            ],
        ),
        (
            "Processo",
            [
                ("Nº Processo", row.get("numero_processo")),
                ("Nº Edital", row.get("numero_edital")),
                ("Modalidade", row.get("modalidade")),
            ],
        ),
        (
            "Objeto",
            [
                ("Descrição", row.get("objeto")),
                ("Categoria", row.get("categoria")),
            ],
        ),
        (
            "Valor",
            [
                ("Estimado", _fmt_money(row.get("valor_estimado"))),
                ("Homologado", _fmt_money(row.get("valor_homologado"))),
                ("Semântica", row.get("valor_semantica")),
            ],
        ),
        (
            "Datas",
            [
                ("Publicação", _fmt_date(row.get("data_publicacao"))),
                ("Abertura", _fmt_date(row.get("data_abertura"))),
                ("Encerramento", _fmt_date(row.get("data_encerramento"))),
                ("Homologação", _fmt_date(row.get("data_homologacao"))),
            ],
        ),
        (
            "Status",
            [
                ("Fonte", row.get("status_fonte")),
                ("Canônico", row.get("status_canonico")),
                ("Motivo", row.get("status_motivo")),
            ],
        ),
        (
            "Ranking",
            [
                ("Tier", row.get("ranking")),
                ("Score", row.get("ranking_score")),
                ("Confiança", row.get("ranking_confianca")),
            ],
        ),
        (
            "Documentos",
            [
                ("Edital", row.get("link_edital")),
            ],
        ),
    ]

    for section_title, fields in sections:
        print(f"\n--- {section_title} ---")
        for label, value in fields:
            print(f"  {label:15s}: {value or '(não informado)'}")

    print(f"\n{'=' * 70}\n")


def _print_explain(row: dict[str, Any]) -> None:
    """Print ranking explanation for one opportunity."""
    print(f"\n{'=' * 70}")
    print(f"EXPLICAÇÃO DE RANKING — Oportunidade #{row.get('id')}")
    print(f"{'=' * 70}")
    print(f"\n  Tier:        {row.get('ranking')}")
    print(f"  Score:       {row.get('ranking_score')}/100")
    print(f"  Confiança:   {row.get('ranking_confianca')}")

    fatores = row.get("ranking_fatores", {})
    if isinstance(fatores, str):
        fatores = json.loads(fatores)
    if fatores:
        if fatores.get("positivos"):
            print("\n  FATORES POSITIVOS (+):")
            for f in fatores["positivos"]:
                print(f"    ✓ {f}")
        if fatores.get("negativos"):
            print("\n  FATORES NEGATIVOS (−):")
            for f in fatores["negativos"]:
                print(f"    ✗ {f}")
        if fatores.get("bloqueadores"):
            print("\n  BLOQUEADORES (⊘):")
            for f in fatores["bloqueadores"]:
                print(f"    ⊘ {f}")

    regras = row.get("ranking_regras", [])
    if isinstance(regras, str):
        regras = json.loads(regras)
    if regras:
        print("\n  REGRAS APLICADAS:")
        for r in regras:
            print(f"    • {r}")

    dados_ausentes = row.get("dados_ausentes", [])
    if dados_ausentes:
        print("\n  DADOS AUSENTES:")
        for d in dados_ausentes:
            print(f"    ? {d}")

    print(f"\n{'=' * 70}\n")


def _fmt_money(val: Any) -> str:
    if val is None:
        return "(não informado)"
    try:
        return f"R$ {float(val):,.2f}"
    except (ValueError, TypeError):
        return str(val)


def _fmt_date(val: Any) -> str:
    if val is None:
        return "(não informado)"
    if isinstance(val, datetime):
        return val.strftime("%d/%m/%Y")
    return str(val)[:10]


def cmd_briefing(args: argparse.Namespace) -> None:
    """Briefing diário de oportunidades — foco em decisão comercial.

    Filtra por AEC (engenharia/construção/obras), SC, e raio 200km.
    """
    from datetime import date, timedelta

    conn = _get_conn(args.dsn)
    cur = conn.cursor()

    horizon = date.today() + timedelta(days=args.dias)

    query = """
        SELECT COALESCE(e.razao_social, oi.orgao_nome) AS orgao_nome,
               oi.uf, oi.modalidade, oi.objeto,
               oi.valor_estimado, oi.data_abertura, oi.data_publicacao,
               oi.status_canonico, oi.link_edital,
               e.municipio AS municipio_orgao, e.distancia_fk
        FROM opportunity_intel oi
        LEFT JOIN sc_public_entities e ON LEFT(oi.orgao_cnpj, 8) = e.cnpj_8
        WHERE oi.is_active = TRUE
          AND oi.data_abertura IS NOT NULL
          AND oi.data_abertura >= CURRENT_DATE
          AND oi.data_abertura <= %s
          AND oi.uf = 'SC'
          AND (e.raio_200km = TRUE OR e.raio_200km IS NULL)
          AND (
              oi.objeto ~* '(obra|construção|edificação|pavimentação|drenagem|saneamento|reforma|manutenção.*predial|engenharia|infraestrutura|instalação|fiscalização.*obra|serviço.*técnico.*eng|execução|edifício|rodovia|ponte|galeria|concreto|asfalto|terraplenagem|fundação|estrutura|contenção|revestimento|telhado|cobertura|hidráulica|elétrica.*predial|combate.*incêndio|acessibilidade|calçada|passeio|praça|urbanização|paisagismo|arquitet*)'
              OR oi.objeto ~* '(elaboração.*projeto|projeto.*executivo|projeto.*básico|estudo.*viabilidade|orçamento.*obra|memorial.*descritivo|CAD|BIM|as built|ART|RRT|CREA|CAU)'
              OR oi.modalidade ~* '(concorrência|tomada.*preço|RDC|regime.*diferenciado|pregão|dispensa|convite)'
          )
        ORDER BY oi.data_abertura ASC, oi.valor_estimado DESC NULLS LAST
        LIMIT %s
    """
    cur.execute(query, (horizon, args.limit))
    rows = cur.fetchall()

    if not rows:
        print("Nenhuma oportunidade AEC em SC no raio de 200km com data definida.")
        print(f"Tente aumentar --dias (atual: {args.dias}) ou verifique dados PNCP.")
        cur.close()
        conn.close()
        return

    # Count by urgency
    hoje = date.today()
    urgentes = [r for r in rows if r[5] and r[5].date() <= hoje + timedelta(days=7)]
    proximas = [r for r in rows if r[5] and hoje + timedelta(days=7) < r[5].date() <= horizon]

    print("\n=== BRIEFING DIÁRIO — Extra Construtora ===")
    print(f"Gerado: {date.today().strftime('%d/%m/%Y')} | Fonte: PNCP")
    print(f"Filtros: AEC | SC | Raio 200km | Horizonte: {args.dias} dias")
    print(f"Oportunidades: {len(rows)} ({len(urgentes)} urgentes, {len(proximas)} em breve)")
    print()

    if urgentes:
        print(f"🔴 URGENTE (próximos 7 dias): {len(urgentes)}")
        print("-" * 80)
        for r in urgentes[:10]:
            nome, uf, mod, obj, valor, dt_ab, dt_pub, sit, link, mun, dist = r
            obj_short = (obj or "Sem objeto")[:80]
            val_str = f"R$ {float(valor or 0):,.2f}" if valor else "N/D"
            dt_str = dt_ab.strftime("%d/%m/%Y") if dt_ab else "N/D"
            dist_str = f"{float(dist):.0f}km" if dist else "?"
            print(f"  [{mod or '?'}] {obj_short}")
            print(f"  Órgão: {nome or '?'} — {mun or '?'} ({dist_str}) | Valor: {val_str} | Abertura: {dt_str}")
            if link:
                print(f"  Link: {link}")
            print()

    if proximas:
        print(f"🟡 EM BREVE (8-{args.dias} dias): {len(proximas)}")
        print("-" * 80)
        for r in proximas[:10]:
            nome, uf, mod, obj, valor, dt_ab, dt_pub, sit, link, mun, dist = r
            obj_short = (obj or "Sem objeto")[:80]
            val_str = f"R$ {float(valor or 0):,.2f}" if valor else "N/D"
            dt_str = dt_ab.strftime("%d/%m/%Y") if dt_ab else "N/D"
            dist_str = f"{float(dist):.0f}km" if dist else "?"
            print(f"  [{mod or '?'}] {obj_short}")
            print(f"  Órgão: {nome or '?'} — {mun or '?'} ({dist_str}) | Valor: {val_str} | Abertura: {dt_str}")
            print()

    # Summary stats — AEC + SC + 200km only
    cur.execute("""
        SELECT COUNT(*), COUNT(DISTINCT oi.orgao_cnpj),
               COALESCE(SUM(oi.valor_estimado), 0)
        FROM opportunity_intel oi
        LEFT JOIN sc_public_entities e ON LEFT(oi.orgao_cnpj, 8) = e.cnpj_8
        WHERE oi.is_active = TRUE AND oi.uf = 'SC' AND (e.raio_200km = TRUE OR e.raio_200km IS NULL)
          AND (
              oi.objeto ~* '(obra|construção|edificação|pavimentação|drenagem|saneamento|reforma|manutenção.*predial|engenharia|infraestrutura|instalação|fiscalização.*obra|serviço.*técnico.*eng|execução|edifício|rodovia|ponte|galeria|concreto|asfalto|terraplenagem|fundação|estrutura|contenção|revestimento|telhado|cobertura|hidráulica|elétrica.*predial|combate.*incêndio|acessibilidade|calçada|passeio|praça|urbanização|paisagismo|arquitet*)'
              OR oi.objeto ~* '(elaboração.*projeto|projeto.*executivo|projeto.*básico|estudo.*viabilidade|orçamento.*obra|memorial.*descritivo|CAD|BIM|as built|ART|RRT|CREA|CAU)'
              OR oi.modalidade ~* '(concorrência|tomada.*preço|RDC|regime.*diferenciado|pregão|dispensa|convite)'
          )
    """)
    total, orgs, soma = cur.fetchone()
    print(f"📊 TOTAL AEC NO RAIO 200km: {total} editais | {orgs} órgãos | Valor: R$ {float(soma):,.2f}")

    cur.close()
    conn.close()


def cmd_reconcile(args: argparse.Namespace) -> None:
    """Target universe reconciliation report (CM-03)."""
    # Add project root to sys.path for cross-package import
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.abspath(os.path.join(_script_dir, "..", ".."))
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)

    from scripts.coverage.reconcile_targets import run_reconcile

    output = run_reconcile(
        manifest_path=args.manifest,
        reconciliation_path=args.reconciliation,
        source_coverage_path=args.source_coverage,
        fmt=args.format,
        output_csv=args.output_csv,
    )
    print(output)


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Opportunity Intelligence CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/opportunity_intel/cli.py list --status open --limit 20
  python scripts/opportunity_intel/cli.py show 42
  python scripts/opportunity_intel/cli.py explain 42
  python scripts/opportunity_intel/cli.py coverage
  python scripts/opportunity_intel/cli.py source-health
  python scripts/opportunity_intel/cli.py update --source pncp
  python scripts/opportunity_intel/cli.py export --format csv -o ops.csv
  python -m scripts.opportunity_intel.cli radar --profile config/client_profiles/extra.yaml
        """,
    )
    sub = parser.add_subparsers(dest="command", help="Comando")

    # QW-01 auditable radar
    p_radar = sub.add_parser("radar", help="Executar radar auditável QW-01")
    p_radar.add_argument("--profile", default="config/client_profiles/extra.yaml")
    p_radar.add_argument("--seed", default="Extra - alvos de licitação. R-0.xlsx")
    p_radar.add_argument("--window-days", type=int, default=45)
    p_radar.add_argument("--output-dir", default="output/qw-01")
    p_radar.add_argument("--update", choices=["auto", "always", "never"], default="auto")
    p_radar.add_argument("--timeout", type=int, default=10)
    p_radar.add_argument("--max-retries", type=int, default=0)
    p_radar.add_argument("--max-pages", type=int)
    p_radar.add_argument("--max-records", type=int)
    p_radar.add_argument("--dsn", default=DEFAULT_DSN)

    # list
    p_list = sub.add_parser("list", help="Listar oportunidades")
    p_list.add_argument("--status", help="Status: open,upcoming,closed,unknown")
    p_list.add_argument("--uf", default="SC", help="UF (default: SC)")
    p_list.add_argument("--municipio", help="Município (filtro parcial)")
    p_list.add_argument("--modalidade", help="Modalidade")
    p_list.add_argument("--ranking", help="Ranking: GO,REVIEW,NO_GO")
    p_list.add_argument("--source", help="Fonte")
    p_list.add_argument("--search", help="Busca textual no objeto")
    p_list.add_argument("--valor-min", type=float, help="Valor mínimo")
    p_list.add_argument("--limit", type=int, default=50, help="Limite (default: 50)")
    p_list.add_argument("--format", default="table", choices=["table", "json"])
    p_list.add_argument("--dsn", default=DEFAULT_DSN)

    # show
    p_show = sub.add_parser("show", help="Mostrar detalhes de uma oportunidade")
    p_show.add_argument("id", help="ID (numérico) ou PNCP ID")
    p_show.add_argument("--dsn", default=DEFAULT_DSN)

    # explain
    p_exp = sub.add_parser("explain", help="Explicar ranking de uma oportunidade")
    p_exp.add_argument("id", help="ID (numérico) ou PNCP ID")
    p_exp.add_argument("--dsn", default=DEFAULT_DSN)

    # coverage
    p_cov = sub.add_parser("coverage", help="Dashboard de cobertura")
    p_cov.add_argument("--format", default="table", choices=["table", "json"])
    p_cov.add_argument("--dsn", default=DEFAULT_DSN)

    # source-health
    p_sh = sub.add_parser("source-health", help="Health check por fonte")
    p_sh.add_argument("--format", default="table", choices=["table", "json"])
    p_sh.add_argument("--dsn", default=DEFAULT_DSN)

    # update
    p_upd = sub.add_parser("update", help="Executar crawl")
    p_upd.add_argument("--source", default="pncp", help="Fonte ou 'all'")
    p_upd.add_argument("--mode", default="full", choices=["full", "incremental", "dry-run"])
    p_upd.add_argument("--limit", type=int, help="Limitar páginas")
    p_upd.add_argument("--dsn", default=DEFAULT_DSN)

    # export
    p_exp2 = sub.add_parser("export", help="Exportar JSON/CSV")
    p_exp2.add_argument("--format", default="json", choices=["json", "csv"])
    p_exp2.add_argument("--output", "-o", help="Output path")
    p_exp2.add_argument("--status", help="Filtrar por status")
    p_exp2.add_argument("--ranking", help="Filtrar por ranking")
    p_exp2.add_argument("--limit", type=int, default=500)
    p_exp2.add_argument("--dsn", default=DEFAULT_DSN)

    # reconcile
    p_rec = sub.add_parser("reconcile", help="Relatório de reconciliação do universo-alvo (CM-03)")
    p_rec.add_argument("--format", default="table", choices=["table", "json"], help="Formato de saída")
    p_rec.add_argument("--output-csv", default="", help="Exportar entes não encontrados para CSV")
    p_rec.add_argument(
        "--manifest",
        default="output/readiness/target-universe-manifest.json",
        help="Caminho para o manifest do universo-alvo",
    )
    p_rec.add_argument(
        "--reconciliation",
        default="output/readiness/target-reconciliation.csv",
        help="Caminho para o CSV de reconciliação",
    )
    p_rec.add_argument(
        "--source-coverage",
        default="output/readiness/source-entity-coverage.csv",
        help="Caminho para o CSV de cobertura por fonte",
    )

    p_brief = sub.add_parser("briefing", help="Briefing diário de oportunidades")
    p_brief.add_argument("--dias", type=int, default=7, help="Horizonte em dias (default: 7)")
    p_brief.add_argument("--uf", default=None, help="Filtrar por UF")
    p_brief.add_argument("--limit", type=int, default=20, help="Máximo de oportunidades")
    p_brief.add_argument("--dsn", default=DEFAULT_DSN)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "radar": cmd_radar,
        "list": cmd_list,
        "show": cmd_show,
        "explain": cmd_explain,
        "coverage": cmd_coverage,
        "source-health": cmd_source_health,
        "update": cmd_update,
        "export": cmd_export,
        "briefing": cmd_briefing,
        "reconcile": cmd_reconcile,
    }

    cmd_fn = commands.get(args.command)
    if not cmd_fn:
        print(f"Comando não encontrado: {args.command}")
        parser.print_help()
        sys.exit(1)

    try:
        cmd_fn(args)
    except psycopg2.Error as e:
        _logger.error("Database error: %s", e)
        print(f"Erro de banco de dados: {e}")
        sys.exit(1)
    except Exception as e:
        _logger.exception("Unexpected error while executing %s", args.command)
        print(f"Erro: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
