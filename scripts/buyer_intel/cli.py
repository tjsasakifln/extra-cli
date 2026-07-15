"""
Buyer Intelligence CLI — Perfil e Ranking de Órgãos Compradores.

Uso:
  python scripts/buyer_intel/cli.py ranking --limit 20
  python scripts/buyer_intel/cli.py perfil <cnpj_8>
  python scripts/buyer_intel/cli.py export --format csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import date
from io import StringIO
from typing import Any

import psycopg2
import psycopg2.extras

from scripts.buyer_intel.ranking import (
    BuyerProfile,
    compute_buyer_ranking,
)

# ---------------------------------------------------------------------------
# DB connection
# ---------------------------------------------------------------------------


def _get_conn(dsn: str | None = None) -> Any:
    """Obtém conexão ao banco."""
    dsn = dsn or os.environ.get("LOCAL_DATALAKE_DSN", "")
    if not dsn:
        # Fallback: SQLite
        import sqlite3
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data", "contract_intel.db"
        )
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    return psycopg2.connect(dsn)


def _is_pg(conn: Any) -> bool:
    return hasattr(conn, "cursor") and not str(type(conn)).lower().endswith("sqlite3.connection'>")


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------


def fetch_buyer_profiles(conn: Any, min_contratos: int = 3) -> list[BuyerProfile]:
    """Busca perfis de todos os órgãos no raio 200km com contratos."""

    if _is_pg(conn):
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # Main query: buyer profiles from contracts + entities
        cur.execute("""
            WITH buyer_stats AS (
                SELECT
                    c.orgao_cnpj_8,
                    c.orgao_nome,
                    MAX(c.municipio) AS municipio_contrato,
                    COUNT(*) AS total_contratos,
                    COUNT(*) FILTER (WHERE (
                        c.objeto_contrato ~* '(obra|construção|edificação|pavimentação|drenagem|saneamento|reforma|manutenção.*predial|engenharia|infraestrutura|instalação|fiscalização.*obra|execução|edifício|rodovia|ponte|galeria|concreto|asfalto|terraplenagem|fundação|estrutura|contenção|revestimento|telhado|cobertura|hidráulica|elétrica.*predial|arquitet|projeto.*executivo|projeto.*básico)'
                    )) AS contratos_aec,
                    COALESCE(SUM(c.valor_total), 0) AS valor_total,
                    COALESCE(SUM(c.valor_total) FILTER (WHERE (
                        c.objeto_contrato ~* '(obra|construção|edificação|pavimentação|drenagem|saneamento|reforma|manutenção.*predial|engenharia|infraestrutura|instalação|fiscalização.*obra|execução|edifício|rodovia|ponte|galeria|concreto|asfalto|terraplenagem|fundação|estrutura|contenção|revestimento|telhado|cobertura|hidráulica|elétrica.*predial|arquitet|projeto.*executivo|projeto.*básico)'
                    )), 0) AS valor_total_aec,
                    AVG(c.valor_total) AS ticket_medio,
                    AVG(c.valor_total) FILTER (WHERE (
                        c.objeto_contrato ~* '(obra|construção|edificação|pavimentação|drenagem|saneamento|reforma|manutenção.*predial|engenharia|infraestrutura|instalação|fiscalização.*obra|execução|edifício|rodovia|ponte|galeria|concreto|asfalto|terraplenagem|fundação|estrutura|contenção|revestimento|telhado|cobertura|hidráulica|elétrica.*predial|arquitet|projeto.*executivo|projeto.*básico)'
                    )) AS ticket_medio_aec,
                    MIN(c.data_publicacao) AS primeira_data,
                    MAX(c.data_publicacao) AS ultima_data,
                    COUNT(DISTINCT c.fornecedor_cnpj_8) AS fornecedores_distintos,
                    COUNT(*) FILTER (WHERE c.data_fim BETWEEN CURRENT_DATE AND CURRENT_DATE + 90) AS vencendo_90d,
                    COUNT(*) FILTER (WHERE c.data_fim BETWEEN CURRENT_DATE AND CURRENT_DATE + 180) AS vencendo_180d,
                    COUNT(*) FILTER (WHERE c.data_fim BETWEEN CURRENT_DATE AND CURRENT_DATE + 365) AS vencendo_365d,
                    COUNT(*) FILTER (WHERE c.data_publicacao >= CURRENT_DATE - INTERVAL '365 days') AS contratos_ultimo_ano
                FROM pncp_supplier_contracts c
                WHERE c.uf = 'SC' AND c.is_active = TRUE
                GROUP BY c.orgao_cnpj_8, c.orgao_nome
                HAVING COUNT(*) >= %s
            ),
            supplier_concentration AS (
                SELECT
                    c2.orgao_cnpj_8,
                    SUM(POWER(c2.valor_fornecedor * 1.0 / NULLIF(c3.valor_total_orgao, 0), 2)) * 10000 AS hhi
                FROM (
                    SELECT orgao_cnpj_8, fornecedor_cnpj_8,
                           SUM(valor_total) AS valor_fornecedor
                    FROM pncp_supplier_contracts
                    WHERE uf = 'SC' AND is_active = TRUE
                    GROUP BY orgao_cnpj_8, fornecedor_cnpj_8
                ) c2
                JOIN (
                    SELECT orgao_cnpj_8, SUM(valor_total) AS valor_total_orgao
                    FROM pncp_supplier_contracts
                    WHERE uf = 'SC' AND is_active = TRUE
                    GROUP BY orgao_cnpj_8
                ) c3 ON c2.orgao_cnpj_8 = c3.orgao_cnpj_8
                GROUP BY c2.orgao_cnpj_8
            ),
            top_fornecedores AS (
                SELECT orgao_cnpj_8, fornecedor_nome, fornecedor_cnpj_8,
                       SUM(valor_total) AS total_fornecedor,
                       ROW_NUMBER() OVER (PARTITION BY orgao_cnpj_8 ORDER BY SUM(valor_total) DESC) AS rn
                FROM pncp_supplier_contracts
                WHERE uf = 'SC' AND is_active = TRUE
                GROUP BY orgao_cnpj_8, fornecedor_cnpj_8, fornecedor_nome
            ),
            open_opportunities AS (
                SELECT orgao_cnpj_8, COUNT(*) AS abertas
                FROM pncp_raw_bids
                WHERE uf = 'SC' AND is_active = TRUE
                  AND situacao_compra ~* '(abert|public|divulg|receb)'
                GROUP BY orgao_cnpj_8
            )
            SELECT
                bs.*,
                e.razao_social,
                e.municipio,
                e.distancia_fk,
                e.raio_200km,
                COALESCE(sc.hhi, 0) AS hhi,
                COALESCE(oo.abertas, 0) AS oportunidades_abertas
            FROM buyer_stats bs
            JOIN sc_public_entities e ON bs.orgao_cnpj_8 = e.cnpj_8
            LEFT JOIN supplier_concentration sc ON bs.orgao_cnpj_8 = sc.orgao_cnpj_8
            LEFT JOIN open_opportunities oo ON bs.orgao_cnpj_8 = oo.orgao_cnpj_8
            WHERE e.raio_200km = TRUE
            ORDER BY bs.valor_total DESC
        """, (min_contratos,))
        rows = cur.fetchall()
        cur.close()
    else:
        # SQLite fallback — limited functionality
        return []

    # Calculate percentiles per buyer
    profiles = []
    for row in rows:
        # Get percentiles for this buyer
        if _is_pg(conn):
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY valor_total),
                    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY valor_total),
                    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY valor_total)
                FROM pncp_supplier_contracts
                WHERE orgao_cnpj_8 = %s AND uf = 'SC' AND is_active = TRUE
            """, (row["orgao_cnpj_8"],))
            p25, p50, p75 = cur.fetchone()
            cur.close()
        else:
            p25, p50, p75 = 0, 0, 0

        # Get top 3 suppliers
        if _is_pg(conn):
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT fornecedor_nome, SUM(valor_total) AS total
                FROM pncp_supplier_contracts
                WHERE orgao_cnpj_8 = %s AND uf = 'SC' AND is_active = TRUE
                GROUP BY fornecedor_nome
                ORDER BY total DESC LIMIT 3
            """, (row["orgao_cnpj_8"],))
            top_suppliers = [
                {"nome": s["fornecedor_nome"], "valor_total": float(s["total"])}
                for s in cur.fetchall()
            ]
            cur.close()
        else:
            top_suppliers = []

        # Calculate annual frequency
        days_span = 365.0
        if row["primeira_data"] and row["ultima_data"]:
            span = (row["ultima_data"] - row["primeira_data"]).days
            if span > 0:
                days_span = span
        freq_anual = row["total_contratos"] / max(days_span, 1) * 365

        # Quality assessment
        qualidade = "boa" if row["total_contratos"] >= 10 else "limitada"
        limitations = []
        if row["total_contratos"] < 5:
            limitations.append("poucos contratos — perfil instável")
        if row["contratos_aec"] == 0:
            limitations.append("zero contratos AEC identificados")
        if not row["distancia_fk"]:
            limitations.append("sem distância calculada")

        profiles.append(BuyerProfile(
            cnpj_8=row["orgao_cnpj_8"],
            razao_social=row.get("razao_social") or row["orgao_nome"],
            municipio=row.get("municipio") or row["municipio_contrato"] or "?",
            distancia_km=row["distancia_fk"],
            total_contratos=row["total_contratos"],
            contratos_aec=row["contratos_aec"],
            valor_total=float(row["valor_total"]),
            valor_total_aec=float(row["valor_total_aec"]),
            ticket_medio=float(row["ticket_medio"]) if row["ticket_medio"] else 0,
            ticket_medio_aec=float(row["ticket_medio_aec"]) if row.get("ticket_medio_aec") else 0,
            mediana_valor=float(p50) if p50 else 0,
            p25_valor=float(p25) if p25 else 0,
            p75_valor=float(p75) if p75 else 0,
            primeira_data=row["primeira_data"].isoformat() if row["primeira_data"] else None,
            ultima_data=row["ultima_data"].isoformat() if row["ultima_data"] else None,
            frequencia_anual=freq_anual,
            contratos_ultimo_ano=row["contratos_ultimo_ano"],
            fornecedores_distintos=row["fornecedores_distintos"],
            top_fornecedores=top_suppliers,
            hhi_concentracao=float(row["hhi"]) if row["hhi"] else 0,
            contratos_vencendo_90d=row["vencendo_90d"],
            contratos_vencendo_180d=row["vencendo_180d"],
            contratos_vencendo_365d=row["vencendo_365d"],
            oportunidades_abertas=row["oportunidades_abertas"],
            qualidade_dados=qualidade,
            limitations=limitations,
        ))

    return profiles


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_ranking(args: argparse.Namespace) -> None:
    """Exibe ranking de órgãos compradores."""
    conn = _get_conn(args.dsn)
    profiles = fetch_buyer_profiles(conn, min_contratos=args.min_contratos)

    if not profiles:
        print("Nenhum órgão encontrado no raio 200km com dados suficientes.")
        print("Verifique se o banco possui contratos SC carregados.")
        conn.close()
        return

    rankings = compute_buyer_ranking(profiles)

    print("\n=== RANKING DE ÓRGÃOS COMPRADORES — Extra Construtora ===")
    print(f"Data: {date.today().strftime('%d/%m/%Y')} | Filtros: AEC | SC | Raio 200km")
    print(f"Órgãos avaliados: {len(rankings)} | Mín. contratos: {args.min_contratos}")
    print()

    limit = min(args.limit, len(rankings))

    if args.format == "json":
        print(json.dumps([r.to_dict() for r in rankings[:limit]], indent=2, ensure_ascii=False))
    elif args.format == "csv":
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            "cnpj_8", "razao_social", "municipio", "distancia_km",
            "score_total", "score_aderencia", "score_volume", "score_frequencia",
            "score_ticket", "score_proximidade", "score_oportunidades",
            "score_renovacao", "score_concentracao", "classificacao"
        ])
        writer.writeheader()
        for r in rankings[:limit]:
            writer.writerow(r.to_dict())
        print(output.getvalue())
    else:
        # Pretty-print top entries
        for i, r in enumerate(rankings[:limit], 1):
            icon = {"PRIORITARIO": "⭐", "ATIVO": "🟢", "REVIEW": "🟡", "BAIXA_PRIORIDADE": "⚪"}
            dist_str = f"{r.distancia_km:.0f}km" if r.distancia_km else "?"
            print(f"{i:2d}. {icon.get(r.classificacao, '?')} [{r.classificacao}] {r.razao_social[:55]}")
            print(f"    {r.municipio} ({dist_str}) | Score: {r.score_total:.0f}/100")
            print(f"    Aderência:{r.score_aderencia:.0f} Vol:{r.score_volume:.0f} Freq:{r.score_frequencia:.0f} "
                  f"Ticket:{r.score_ticket:.0f} Prox:{r.score_proximidade:.0f} "
                  f"Oport:{r.score_oportunidades:.0f} Renov:{r.score_renovacao:.0f} Conc:{r.score_concentracao:.0f}")
            print()

    conn.close()


def cmd_perfil(args: argparse.Namespace) -> None:
    """Exibe perfil detalhado de um órgão."""
    conn = _get_conn(args.dsn)
    profiles = fetch_buyer_profiles(conn)

    # Find by CNPJ8 or partial name match
    target = None
    for p in profiles:
        if p.cnpj_8 == args.id or args.id.lower() in p.razao_social.lower():
            target = p
            break

    if not target:
        print(f"Órgão não encontrado: {args.id}")
        print("Use o comando 'ranking' para listar órgãos disponíveis.")
        conn.close()
        return

    ranking = compute_buyer_ranking([target])[0]

    print("\n=== PERFIL DO ÓRGÃO ===")
    print(f"Razão Social: {target.razao_social}")
    print(f"CNPJ (raiz):  {target.cnpj_8}")
    print(f"Município:    {target.municipio}")
    print(f"Distância:    {target.distancia_km:.0f} km" if target.distancia_km else "Distância:    N/D")
    print()
    print("--- CONTRATOS ---")
    print(f"Total:        {target.total_contratos}")
    print(f"AEC:          {target.contratos_aec} ({target.contratos_aec/max(target.total_contratos,1)*100:.0f}%)")
    print(f"Valor Total:  R$ {target.valor_total:,.2f}")
    print(f"Valor AEC:    R$ {target.valor_total_aec:,.2f}")
    print(f"Ticket Médio: R$ {target.ticket_medio:,.2f}")
    print(f"Ticket AEC:   R$ {target.ticket_medio_aec:,.2f}" if target.ticket_medio_aec else "")
    print(f"Mediana:      R$ {target.mediana_valor:,.2f}")
    print(f"P25-P75:      R$ {target.p25_valor:,.2f} — R$ {target.p75_valor:,.2f}")
    print()
    print("--- TEMPORAL ---")
    print(f"Período:      {target.primeira_data or '?'} → {target.ultima_data or '?'}")
    print(f"Freq/ano:     {target.frequencia_anual:.1f}")
    print(f"Último ano:   {target.contratos_ultimo_ano} contratos")
    print()
    print("--- FORNECEDORES ---")
    print(f"Distintos:    {target.fornecedores_distintos}")
    print(f"HHI:          {target.hhi_concentracao:.0f} ", end="")
    if target.hhi_concentracao <= 1500:
        print("(não concentrado)")
    elif target.hhi_concentracao <= 2500:
        print("(moderadamente concentrado)")
    else:
        print("(concentrado)")
    if target.top_fornecedores:
        print("Top 3:")
        for s in target.top_fornecedores:
            print(f"  • {s['nome'][:50]}: R$ {s['valor_total']:,.2f}")
    print()
    print("--- VENCIMENTOS ---")
    print(f"90 dias:      {target.contratos_vencendo_90d}")
    print(f"180 dias:     {target.contratos_vencendo_180d}")
    print(f"365 dias:     {target.contratos_vencendo_365d}")
    print()
    print("--- RANKING ---")
    print(f"Score Total:  {ranking.score_total:.0f}/100 [{ranking.classificacao}]")
    print(f"Aderência:    {ranking.score_aderencia:.0f}/25")
    print(f"Volume:       {ranking.score_volume:.0f}/20")
    print(f"Frequência:   {ranking.score_frequencia:.0f}/15")
    print(f"Ticket:       {ranking.score_ticket:.0f}/10")
    print(f"Proximidade:  {ranking.score_proximidade:.0f}/10")
    print(f"Oportunidades:{ranking.score_oportunidades:.0f}/10")
    print(f"Renovação:    {ranking.score_renovacao:.0f}/5")
    print(f"Concentração: {ranking.score_concentracao:.0f}/5")
    print()
    if target.limitations:
        print("⚠️  Limitações:")
        for lim in target.limitations:
            print(f"  • {lim}")

    if args.format == "json":
        print("\n--- JSON ---")
        print(json.dumps(target.to_dict(), indent=2, ensure_ascii=False, default=str))

    conn.close()


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Buyer Intelligence CLI — Perfil e Ranking de Órgãos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/buyer_intel/cli.py ranking --limit 10
  python scripts/buyer_intel/cli.py ranking --format csv --limit 20 > ranking.csv
  python scripts/buyer_intel/cli.py perfil 12345678
  python scripts/buyer_intel/cli.py perfil "PREFEITURA MUNICIPAL DE FLORIANOPOLIS"
""",
    )
    sub = parser.add_subparsers(dest="command")

    # ranking
    rank = sub.add_parser("ranking", help="Ranking de órgãos compradores")
    rank.add_argument("--limit", type=int, default=20)
    rank.add_argument("--min-contratos", type=int, default=3)
    rank.add_argument("--format", choices=["text", "json", "csv"], default="text")
    rank.add_argument("--dsn")

    # perfil
    prof = sub.add_parser("perfil", help="Perfil detalhado de um órgão")
    prof.add_argument("id", help="CNPJ8 ou parte do nome do órgão")
    prof.add_argument("--format", choices=["text", "json"], default="text")
    prof.add_argument("--dsn")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "ranking":
        cmd_ranking(args)
    elif args.command == "perfil":
        cmd_perfil(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
