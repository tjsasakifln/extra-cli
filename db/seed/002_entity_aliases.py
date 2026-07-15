#!/usr/bin/env python3
"""Seed 002: popula entity_aliases com resolução determinística por município.

Story: CM-13 — Deduplicação Multicanal e Aliases de Compradores

Lógica:
  Para cada ente municipal que NÃO é prefeitura (secretaria, autarquia,
  fundação, câmara), encontra a prefeitura no MESMO município e cria alias:
  cnpj_8_sub (ente) → cnpj_8_pub (prefeitura).

  Entes que JÁ SÃO prefeitura não recebem alias (resolve para si mesmos).

Usage:
  python db/seed/002_entity_aliases.py [--dry-run] [--truncate]
"""

import os
import sys
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


def get_dsn() -> str:
    for var in ("DATABASE_URL", "LOCAL_DATALAKE_DSN"):
        dsn = os.getenv(var)
        if dsn:
            return dsn
    return "postgresql://test:test@127.0.0.1:5433/pncp_datalake"


# Naturezas jurídicas que devem ser aliased para a prefeitura do mesmo município
SUBORDINATE_NATUREZAS = [
    "Órgão Público do Poder Executivo Municipal",
    "Órgão Público do Poder Legislativo Municipal",
    "Autarquia Municipal",
    "Fundação Pública de Direito Público Municipal",
    "Fundação Pública de Direito Privado Municipal",
]


def seed_aliases(conn: Any, dry_run: bool = False) -> dict[str, int]:
    """Popula entity_aliases a partir de matching por município."""

    stats: dict[str, int] = {
        "total_subordinates": 0,
        "matched": 0,
        "unmatched": 0,
        "inserted": 0,
        "skipped_self": 0,
    }

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Conta subordinates
        cur.execute(
            """
            SELECT cnpj_8, razao_social, municipio, codigo_ibge, natureza_juridica
            FROM sc_public_entities
            WHERE raio_200km IS TRUE
              AND is_active IS TRUE
              AND natureza_juridica = ANY(%s)
            ORDER BY municipio, natureza_juridica
            """,
            (SUBORDINATE_NATUREZAS,),
        )
        subordinates = cur.fetchall()
        stats["total_subordinates"] = len(subordinates)

        # Busca todas as prefeituras (Município) indexadas por municipio
        cur.execute(
            """
            SELECT cnpj_8, razao_social, municipio, codigo_ibge
            FROM sc_public_entities
            WHERE raio_200km IS TRUE
              AND is_active IS TRUE
              AND natureza_juridica = 'Município'
            """
        )
        municipios_rows = cur.fetchall()
        municipio_map: dict[str, dict[str, str]] = {}
        for row in municipios_rows:
            municipio_map[row["municipio"]] = {
                "cnpj_8": row["cnpj_8"],
                "razao_social": row["razao_social"],
                "codigo_ibge": row["codigo_ibge"],
            }

        inserts: list[tuple[str, str, str, str, str, str, str, str]] = []
        for sub in subordinates:
            mun_name = sub["municipio"]
            if not mun_name:
                stats["unmatched"] += 1
                continue

            mun = municipio_map.get(mun_name)
            if not mun:
                stats["unmatched"] += 1
                continue

            # Não criar alias para si mesmo (ex: prefeitura já é Município)
            if sub["cnpj_8"] == mun["cnpj_8"]:
                stats["skipped_self"] += 1
                continue

            stats["matched"] += 1
            inserts.append((
                sub["cnpj_8"],
                mun["cnpj_8"],
                "municipio_parent",
                sub["razao_social"],
                mun["razao_social"],
                mun_name,
                mun["codigo_ibge"],
            ))

        if dry_run:
            print(f"[DRY-RUN] {len(inserts)} aliases seriam inseridos")
            for ins in inserts[:10]:
                print(f"  {ins[0]} ({ins[3][:50]}) → {ins[1]} ({ins[4][:50]}) [{ins[5]}]")
            if len(inserts) > 10:
                print(f"  ... +{len(inserts) - 10} more")
            return stats

        # Upsert
        if inserts:
            cur.executemany(
                """
                INSERT INTO entity_aliases
                    (cnpj_8_sub, cnpj_8_pub, alias_type, source_entity,
                     target_entity, municipio, codigo_ibge)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (cnpj_8_sub, is_active)
                DO UPDATE SET
                    cnpj_8_pub = EXCLUDED.cnpj_8_pub,
                    source_entity = EXCLUDED.source_entity,
                    target_entity = EXCLUDED.target_entity,
                    municipio = EXCLUDED.municipio,
                    codigo_ibge = EXCLUDED.codigo_ibge,
                    updated_at = now()
                """,
                inserts,
            )
            stats["inserted"] = len(inserts)

        conn.commit()

    return stats


def truncate_aliases(conn: Any) -> None:
    """Remove todos os aliases existentes (idempotência)."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM entity_aliases")
        cur.execute("DELETE FROM dedup_cross_source")
        conn.commit()


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    do_truncate = "--truncate" in sys.argv

    dsn = get_dsn()
    conn = psycopg2.connect(dsn)

    try:
        if do_truncate:
            print("Truncando entity_aliases e dedup_cross_source...")
            truncate_aliases(conn)

        print(f"{'[DRY-RUN] ' if dry_run else ''}Populando entity_aliases...")
        stats = seed_aliases(conn, dry_run=dry_run)

        print("\nResultado:")
        print(f"  Entes subordinate analisados: {stats['total_subordinates']}")
        print(f"  Matched (alias criado):       {stats['matched']}")
        print(f"  Unmatched (sem prefeitura):   {stats['unmatched']}")
        print(f"  Skipped (já é prefeitura):    {stats['skipped_self']}")
        if not dry_run:
            print(f"  Inseridos/atualizados:        {stats['inserted']}")

        # Verificação
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM entity_aliases WHERE is_active")
            total = cur.fetchone()[0]
            print(f"\nTotal de aliases ativos na tabela: {total}")

            cur.execute(
                """
                SELECT alias_type, count(*) as cnt
                FROM entity_aliases WHERE is_active
                GROUP BY alias_type ORDER BY cnt DESC
                """
            )
            for row in cur.fetchall():
                print(f"  {row[0]}: {row[1]}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
