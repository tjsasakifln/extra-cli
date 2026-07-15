#!/usr/bin/env python3
"""Cross-source deduplication engine.

Story: CM-13 — Deduplicação Multicanal e Aliases de Compradores.

Identifica registros duplicados entre fontes diferentes usando hash canônico.
Um mesmo edital publicado no PNCP e no portal da transparência gera o mesmo
hash → agrupados como duplicatas.

Usage:
    from scripts.lib.dedup import DedupEngine

    engine = DedupEngine(conn)
    groups = engine.dedup_opportunities()
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from psycopg2.extras import RealDictCursor

from scripts.crawl.common import generate_cross_source_hash

_logger = logging.getLogger(__name__)


class DedupEngine:
    """Motor de deduplicação cross-source.

    Detecta duplicatas comparando hash canônico entre oportunidades
    de fontes diferentes. Registra grupos no banco (dedup_cross_source).
    """

    def __init__(self, conn: Any):
        self.conn = conn

    def dedup_opportunities(self, dry_run: bool = False) -> dict[str, Any]:
        """Executa dedup cross-source em todas as oportunidades ativas.

        Algoritmo:
          1. Busca todas as oportunidades ativas.
          2. Calcula hash canônico em Python.
          3. Agrupa por hash onde há ao menos 2 fontes distintas.
          4. Para cada grupo: elege 1 registro canônico (menor ID).
          5. Insere/atualiza tabela dedup_cross_source.

        Returns:
            Dict com estatísticas: total_ops, groups_found, duplicates, inserted.
        """
        stats: dict[str, Any] = {
            "total_ops": 0,
            "groups_found": 0,
            "duplicates": 0,
            "inserted": 0,
        }

        cur = self.conn.cursor(cursor_factory=RealDictCursor)

        # Passo 1: Busca todas as oportunidades ativas
        cur.execute(
            """
            SELECT id, source, source_id, orgao_cnpj, modalidade, objeto,
                   data_publicacao, valor_estimado
            FROM opportunity_intel
            WHERE is_active IS TRUE
            ORDER BY id
            """
        )
        rows = cur.fetchall()
        stats["total_ops"] = len(rows)

        if stats["total_ops"] == 0:
            cur.close()
            return stats

        # Passo 2: Calcula hash canônico para cada registro
        hash_map: dict[str, list[dict]] = {}
        for row in rows:
            h = generate_cross_source_hash(
                modalidade=row.get("modalidade"),
                objeto=row.get("objeto"),
                orgao_cnpj_raiz=row.get("orgao_cnpj"),
                data_publicacao=(
                    str(row.get("data_publicacao"))[:10]
                    if row.get("data_publicacao") else None
                ),
                valor_total=(
                    float(row["valor_estimado"])
                    if row.get("valor_estimado") is not None else None
                ),
            )
            if h not in hash_map:
                hash_map[h] = []
            hash_map[h].append({
                "id": row["id"],
                "source": row["source"],
                "source_id": row["source_id"],
            })

        # Passo 3: Filtra grupos com ao menos 2 fontes distintas
        dup_groups: dict[str, list[dict]] = {}
        for h, members in hash_map.items():
            sources = {m["source"] for m in members}
            if len(sources) >= 2:
                dup_groups[h] = members

        stats["groups_found"] = len(dup_groups)
        stats["duplicates"] = sum(len(g) for g in dup_groups.values())

        if dry_run:
            _logger.info(
                "[DRY-RUN] %d grupos de duplicatas encontrados, %d registros duplicados",
                stats["groups_found"],
                stats["duplicates"],
            )
            cur.close()
            return stats

        # Passo 4-5: Insere/atualiza
        inserted = 0
        for canonical_hash, members in dup_groups.items():
            group_id = str(uuid.uuid4())
            sorted_members = sorted(members, key=lambda m: m["id"])
            canonical_id = sorted_members[0]["id"]

            for member in sorted_members:
                cur.execute(
                    """
                    INSERT INTO dedup_cross_source
                        (canonical_hash, opportunity_id, source, source_id,
                         is_canonical, dedup_group_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (opportunity_id)
                    DO UPDATE SET
                        canonical_hash = EXCLUDED.canonical_hash,
                        is_canonical = EXCLUDED.is_canonical,
                        dedup_group_id = EXCLUDED.dedup_group_id
                    """,
                    (
                        canonical_hash,
                        member["id"],
                        member["source"],
                        member["source_id"],
                        member["id"] == canonical_id,
                        group_id,
                    ),
                )
                inserted += 1

        self.conn.commit()
        stats["inserted"] = inserted
        _logger.info(
            "Dedup concluído: %d grupos, %d registros inseridos/atualizados",
            stats["groups_found"],
            stats["inserted"],
        )

        cur.close()
        return stats

    def get_group(self, opportunity_id: int) -> list[dict]:
        """Retorna todos os registros no mesmo grupo de dedup."""
        cur = self.conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT d.*, oi.orgao_cnpj, oi.modalidade, oi.objeto, oi.data_publicacao
            FROM dedup_cross_source d
            JOIN opportunity_intel oi ON d.opportunity_id = oi.id
            WHERE d.dedup_group_id = (
                SELECT dedup_group_id FROM dedup_cross_source WHERE opportunity_id = %s
            )
            ORDER BY d.is_canonical DESC, d.opportunity_id
            """,
            (opportunity_id,),
        )
        rows = cur.fetchall()
        cur.close()
        return rows

    def dedup_stats(self) -> dict:
        """Estatísticas de dedup atuais."""
        cur = self.conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT
                count(DISTINCT dedup_group_id) as total_groups,
                count(*) as total_records,
                count(*) FILTER (WHERE is_canonical) as canonical_records,
                count(DISTINCT source) as sources_involved
            FROM dedup_cross_source
            """
        )
        row = cur.fetchone()
        cur.close()
        return dict(row) if row else {}
