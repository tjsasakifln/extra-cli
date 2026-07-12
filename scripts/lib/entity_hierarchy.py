"""Entity hierarchy module — hierarchical matching for municipal entities.

Provides functions to build and query the entity_hierarchy table, which
links municipal entities (secretarias, fundacoes, autarquias, fundos) to
their respective prefeituras. This allows entities without direct CNPJ
matches to inherit coverage from the parent prefeitura.

Usage:
    from scripts.lib.entity_hierarchy import build_entity_hierarchy

    stats = build_entity_hierarchy(conn)
    print(f"Inserted: {stats['inserted']}")
"""

from __future__ import annotations

from typing import Any

from config.logging_config import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Relationship mapping: natureza_juridica -> relationship category
# ---------------------------------------------------------------------------

RELATIONSHIP_MAP: dict[str, str] = {
    # Administrative entities -> prefeitura
    "Órgão Público do Poder Executivo Municipal": "prefeitura",
    "Administração Municipal": "prefeitura",
    # Legislative entities -> camara
    "Órgão Público do Poder Legislativo Municipal": "camara",
    # Foundations -> fundacao
    "Fundação Pública de Direito Público Municipal": "fundacao",
    # Autonomous entities -> autarquia
    "Autarquia Municipal": "autarquia",
    "Serviço Autônomo Municipal": "autarquia",
    # Funds -> fundo
    "Fundo Público da Administração Direta Municipal": "fundo",
    "Fundo Municipal": "fundo",
    # Councils -> conselho
    "Conselho Municipal": "conselho",
}

# Naturezas juridicas that should be treated as hierarchical entities
HIERARCHICAL_NATUREZAS: frozenset[str] = frozenset(RELATIONSHIP_MAP.keys())


def build_entity_hierarchy(conn: Any) -> dict[str, int]:
    """Build entity hierarchy by linking municipal entities to their prefeituras.

    For each ``codigo_ibge``, finds the parent prefeitura (Municipio) and links
    all hierarchical entities (secretarias, fundacoes, etc.) to it.

    Args:
        conn: Database connection with ``.cursor()`` and ``.execute()`` support.

    Returns:
        Dict with stats keys:
        - ``inserted``: rows inserted into entity_hierarchy
        - ``skipped_no_ibge``: entities without codigo_ibge
        - ``skipped_no_prefeitura``: entities whose codigo_ibge has no prefeitura
        - ``skipped_inactive``: entities with is_active = FALSE
        - ``skipped_already_covered``: entities already covered via direct match
        - ``skipped_camara_with_bids``: camaras that already have their own bids
        - ``errors``: processing errors
    """
    stats: dict[str, int] = {
        "inserted": 0,
        "skipped_no_ibge": 0,
        "skipped_no_prefeitura": 0,
        "skipped_inactive": 0,
        "skipped_already_covered": 0,
        "skipped_camara_with_bids": 0,
        "errors": 0,
    }

    cur = conn.cursor()

    try:
        # ------------------------------------------------------------------
        # Passo 1: Carregar prefeituras (natureza_juridica = 'Municipio')
        # ------------------------------------------------------------------
        cur.execute("""
            SELECT id, cnpj_8, codigo_ibge, razao_social, municipio
            FROM sc_public_entities
            WHERE natureza_juridica = 'Município'
              AND is_active = TRUE
              AND codigo_ibge IS NOT NULL
        """)
        prefeituras_rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        prefeituras = [dict(zip(cols, row)) for row in prefeituras_rows]

        # Index prefeituras by codigo_ibge (1:1 — 295 municipios expected)
        pref_por_ibge: dict[str, dict[str, Any]] = {}
        for pref in prefeituras:
            ibge = pref.get("codigo_ibge")
            if ibge in pref_por_ibge:
                log.warning(
                    "Duas prefeituras para o mesmo IBGE %s: %s e %s",
                    ibge,
                    pref_por_ibge[ibge]["razao_social"],
                    pref["razao_social"],
                )
            pref_por_ibge[ibge] = {
                "id": pref["id"],
                "cnpj_8": pref["cnpj_8"],
                "razao_social": pref["razao_social"],
                "municipio": pref["municipio"],
            }

        log.info("Carregadas %d prefeituras com codigo_ibge", len(prefeituras))

        # ------------------------------------------------------------------
        # Passo 2: Carregar entidades agrupaveis
        # ------------------------------------------------------------------
        cur.execute(
            """
            SELECT id, razao_social, natureza_juridica, cnpj_8, codigo_ibge, is_active
            FROM sc_public_entities
            WHERE natureza_juridica != 'Município'
              AND natureza_juridica = ANY(%s)
            """,
            [list(HIERARCHICAL_NATUREZAS)],
        )
        entidades_rows = cur.fetchall()
        entidades_cols = [d[0] for d in cur.description]
        entidades = [dict(zip(entidades_cols, row)) for row in entidades_rows]

        log.info("Carregadas %d entidades agrupaveis", len(entidades))

        # ------------------------------------------------------------------
        # Passo 3: Para cada entidade, encontrar prefeitura e inserir
        # ------------------------------------------------------------------
        for ente in entidades:
            try:
                # Pular entidades inativas
                if not ente.get("is_active"):
                    stats["skipped_inactive"] += 1
                    continue

                # Pular entidades sem codigo_ibge
                codigo_ibge = ente.get("codigo_ibge")
                if not codigo_ibge:
                    stats["skipped_no_ibge"] += 1
                    continue

                # Pular entidades que ja tem coverage direta
                cur.execute(
                    """
                    SELECT 1 FROM entity_coverage
                    WHERE entity_id = %s
                      AND is_covered = TRUE
                      AND (match_method IS NULL OR match_method != 'hierarchical')
                    LIMIT 1
                    """,
                    [ente["id"]],
                )
                if cur.fetchone():
                    stats["skipped_already_covered"] += 1
                    continue

                # AC8: Camaras com bids proprios — manter coverage direta
                natureza = ente.get("natureza_juridica", "")
                relationship = RELATIONSHIP_MAP.get(natureza, "outros")
                if relationship == "camara":
                    cur.execute(
                        """
                        SELECT COUNT(*) FROM pncp_raw_bids
                        WHERE LEFT(orgao_cnpj, 8) = %s
                        """,
                        [ente.get("cnpj_8", "")],
                    )
                    bid_count = cur.fetchone()[0]
                    if bid_count > 0:
                        stats["skipped_camara_with_bids"] += 1
                        continue

                # Encontrar prefeitura
                pref = pref_por_ibge.get(codigo_ibge)
                if not pref:
                    stats["skipped_no_prefeitura"] += 1
                    continue

                # Inserir na hierarchy
                cur.execute(
                    """
                    INSERT INTO entity_hierarchy
                        (entity_id, parent_entity_id, relationship, match_confidence)
                    VALUES (%s, %s, %s, 'hierarchical')
                    ON CONFLICT (entity_id) DO UPDATE
                    SET parent_entity_id = EXCLUDED.parent_entity_id,
                        relationship = EXCLUDED.relationship,
                        updated_at = NOW()
                    """,
                    [ente["id"], pref["id"], relationship],
                )

                stats["inserted"] += 1

            except Exception as e:
                log.error(
                    "Erro ao processar entidade %s (%s): %s",
                    ente.get("id"),
                    ente.get("razao_social", "N/A"),
                    e,
                )
                stats["errors"] += 1

        conn.commit()
        log.info("Hierarquia construida: %s", stats)

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()

    return stats


def resolve_entity_coverage_cascade(entity_id: int, conn: Any) -> dict[str, Any] | None:
    """Resolve coverage for an entity with hierarchical fallback.

    Tries direct coverage first, then falls back to hierarchical coverage
    via entity_hierarchy parent.

    Args:
        entity_id: ID of the entity to resolve.
        conn: Database connection.

    Returns:
        Dict with ``is_covered``, ``match_method``, ``source_entity_id``,
        and optionally ``relationship``; or ``None`` if no coverage found.
    """
    cur = conn.cursor()

    try:
        # Nivel 1: Cobertura direta
        cur.execute(
            """
            SELECT is_covered, match_method, source
            FROM entity_coverage
            WHERE entity_id = %s
            LIMIT 1
            """,
            [entity_id],
        )
        row = cur.fetchone()

        if row and row[0]:  # is_covered = TRUE
            return {
                "is_covered": True,
                "match_method": row[1] or "direct",
                "source_entity_id": entity_id,
            }

        # Nivel 2: Cobertura via hierarquia
        cur.execute(
            """
            SELECT h.parent_entity_id, h.relationship, ec.is_covered as parent_covered
            FROM entity_hierarchy h
            LEFT JOIN entity_coverage ec
                ON ec.entity_id = h.parent_entity_id AND ec.source = 'pncp'
            WHERE h.entity_id = %s
            LIMIT 1
            """,
            [entity_id],
        )
        hierarchy_row = cur.fetchone()

        if hierarchy_row and hierarchy_row[2]:  # parent_covered = TRUE
            return {
                "is_covered": True,
                "match_method": "hierarchical",
                "source_entity_id": hierarchy_row[0],
                "relationship": hierarchy_row[1],
            }

        return None

    finally:
        cur.close()


def apply_hierarchical_coverage(conn: Any, source: str = "pncp") -> dict[str, int]:
    """Apply hierarchical coverage for all entities in entity_hierarchy.

    For each entity in entity_hierarchy whose parent has coverage but the
    entity itself does not, update entity_coverage with is_covered = TRUE
    and match_method = 'hierarchical'.

    Args:
        conn: Database connection.
        source: Data source to update (default: 'pncp').

    Returns:
        Dict with ``updated`` count and ``skipped_parent_uncovered`` count.
    """
    stats: dict[str, int] = {"updated": 0, "skipped_parent_uncovered": 0, "errors": 0}
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT h.entity_id, h.parent_entity_id, h.relationship
            FROM entity_hierarchy h
            JOIN entity_coverage pec
                ON pec.entity_id = h.parent_entity_id
                AND pec.source = %s
                AND pec.is_covered = TRUE
            LEFT JOIN entity_coverage ec
                ON ec.entity_id = h.entity_id
                AND ec.source = %s
            WHERE (ec.is_covered IS NULL OR ec.is_covered = FALSE)
               OR (ec.is_covered = TRUE AND ec.match_method = 'hierarchical')
            """,
            [source, source],
        )
        rows = cur.fetchall()

        for entity_id, parent_id, relationship in rows:
            try:
                cur.execute(
                    """
                    INSERT INTO entity_coverage
                        (entity_id, source, is_covered, match_method, last_seen_at)
                    VALUES (%s, %s, TRUE, 'hierarchical', NOW())
                    ON CONFLICT (entity_id, source) DO UPDATE
                    SET is_covered = TRUE,
                        match_method = 'hierarchical',
                        last_seen_at = NOW()
                    """,
                    [entity_id, source],
                )
                stats["updated"] += 1
            except Exception as e:
                log.error("Erro ao atualizar coverage para entity %s: %s", entity_id, e)
                stats["errors"] += 1

        conn.commit()
        log.info("Coverage hierarquica aplicada: %s", stats)

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()

    return stats
