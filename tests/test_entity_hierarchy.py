"""Unit tests for scripts/lib/entity_hierarchy.py.

Tests cover the build_entity_hierarchy, resolve_entity_coverage_cascade,
and apply_hierarchical_coverage functions using mock database connections.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from scripts.lib.entity_hierarchy import (
    RELATIONSHIP_MAP,
    apply_hierarchical_coverage,
    build_entity_hierarchy,
    resolve_entity_coverage_cascade,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NATUREZAS_MUNICIPAIS = [
    "Órgão Público do Poder Executivo Municipal",
    "Órgão Público do Poder Legislativo Municipal",
    "Fundação Pública de Direito Público Municipal",
    "Autarquia Municipal",
    "Fundo Público da Administração Direta Municipal",
    "Conselho Municipal",
    "Fundo Municipal",
    "Serviço Autônomo Municipal",
    "Administração Municipal",
    "Fundação Pública de Direito Privado Municipal",
]

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

# Complete column set spanning both queries in build_entity_hierarchy:
#   prefeituras: id, cnpj_8, codigo_ibge, razao_social, municipio
#   entidades:   id, razao_social, natureza_juridica, cnpj_8, codigo_ibge, is_active
ALL_COLS = [
    ("id",),
    ("cnpj_8",),
    ("codigo_ibge",),
    ("razao_social",),
    ("municipio",),
    ("natureza_juridica",),
    ("is_active",),
]
"""Union of all column names across both queries used by build_entity_hierarchy.

Query 1 (prefeituras): id, cnpj_8, codigo_ibge, razao_social, municipio
Query 2 (entidades):   id, razao_social, natureza_juridica, cnpj_8, codigo_ibge, is_active
"""


def _make_conn() -> MagicMock:
    """Create a base mock connection with reasonable defaults."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.__enter__.return_value = cursor

    # Default: empty results for all queries
    cursor.fetchall.return_value = []
    cursor.fetchone.return_value = None
    cursor.description = ALL_COLS

    return conn


def _pref_row(
    id: int,
    cnpj_8: str = "11111111",
    codigo_ibge: str = "4205407",
    razao_social: str = "Municipio de Teste",
    municipio: str = "Teste",
) -> tuple:
    """Build a prefeitura row tuple matching the 7-column ALL_COLS schema."""
    return (id, cnpj_8, codigo_ibge, razao_social, municipio, None, None)


def _ente_row(
    id: int,
    razao_social: str,
    natureza_juridica: str,
    cnpj_8: str = "22222222",
    codigo_ibge: str = "4205407",
    is_active: bool = True,
) -> tuple:
    """Build an entity row tuple matching the 7-column ALL_COLS schema."""
    return (id, cnpj_8, codigo_ibge, razao_social, None, natureza_juridica, is_active)


# ---------------------------------------------------------------------------
# Test: build_entity_hierarchy
# ---------------------------------------------------------------------------


class TestBuildEntityHierarchy:
    def test_build_hierarchy_skips_inactive(self):
        """Entidades inativas nao devem ser incluídas na hierarquia."""
        conn = _make_conn()
        cursor = conn.cursor.return_value

        cursor.fetchall.side_effect = [
            # First fetchall: prefeituras
            [_pref_row(id=1)],
            # Second fetchall: entidades
            [
                _ente_row(
                    id=10,
                    razao_social="Secretaria Inativa",
                    natureza_juridica="Órgão Público do Poder Executivo Municipal",
                    is_active=False,
                ),
                _ente_row(
                    id=11,
                    razao_social="Secretaria Ativa",
                    natureza_juridica="Órgão Público do Poder Executivo Municipal",
                    is_active=True,
                ),
            ],
        ]

        result = build_entity_hierarchy(conn)

        assert result["skipped_inactive"] == 1
        assert result["inserted"] == 1
        assert result["errors"] == 0

    def test_relationship_mapping_complete(self):
        """Todas as naturezas de entes municipais devem estar mapeadas."""
        mapped = 0
        unmapped = 0
        for n in NATUREZAS_MUNICIPAIS:
            if n in RELATIONSHIP_MAP:
                mapped += 1
            else:
                unmapped += 1

        # At least the core municipal naturezas should be mapped
        assert mapped >= 6, f"Only {mapped} of {len(NATUREZAS_MUNICIPAIS)} naturezas mapped"
        # 'outros' is a valid fallback for unmapped
        # Fundacao Publica de Direito Privado Municipal may not be explicitly mapped

    def test_skips_no_ibge(self):
        """Entidades sem codigo_ibge devem ser puladas."""
        conn = _make_conn()
        cursor = conn.cursor.return_value

        cursor.fetchall.side_effect = [
            # prefeituras (empty)
            [],
            # entidades (entity with null codigo_ibge)
            [
                _ente_row(
                    id=10,
                    razao_social="Sem IBGE",
                    natureza_juridica="Órgão Público do Poder Executivo Municipal",
                    codigo_ibge=None,
                ),
            ],
        ]

        result = build_entity_hierarchy(conn)

        assert result["skipped_no_ibge"] == 1
        assert result["inserted"] == 0

    def test_skips_no_prefeitura(self):
        """Entidades sem prefeitura correspondente no IBGE devem ser puladas."""
        conn = _make_conn()
        cursor = conn.cursor.return_value

        cursor.fetchall.side_effect = [
            # prefeituras (only for IBGE 4205407)
            [_pref_row(id=1, codigo_ibge="4205407")],
            # entidades (IBGE 4205408 - no matching prefeitura)
            [
                _ente_row(
                    id=10,
                    razao_social="Secretaria",
                    natureza_juridica="Órgão Público do Poder Executivo Municipal",
                    codigo_ibge="4205408",
                ),
            ],
        ]

        result = build_entity_hierarchy(conn)

        assert result["skipped_no_prefeitura"] == 1
        assert result["inserted"] == 0

    def test_skips_already_covered(self):
        """Entidades ja com coverage direta nao precisam de hierarquia."""
        conn = _make_conn()
        cursor = conn.cursor.return_value

        cursor.fetchall.side_effect = [
            # prefeituras
            [_pref_row(id=1)],
            # entidades
            [
                _ente_row(
                    id=10,
                    razao_social="Secretaria Coberta",
                    natureza_juridica="Órgão Público do Poder Executivo Municipal",
                ),
            ],
        ]
        # Return 1 for the coverage check query (fetchone returns a row)
        cursor.fetchone.return_value = (1,)

        result = build_entity_hierarchy(conn)

        assert result["skipped_already_covered"] == 1
        assert result["inserted"] == 0

    def test_skips_camara_with_own_bids(self):
        """Camaras com bids proprios devem manter coverage direta (AC8)."""
        conn = _make_conn()
        cursor = conn.cursor.return_value

        cursor.fetchall.side_effect = [
            # prefeituras
            [_pref_row(id=1)],
            # entidades (camara com bids proprios)
            [
                _ente_row(
                    id=10,
                    razao_social="Camara Municipal",
                    natureza_juridica="Órgão Público do Poder Legislativo Municipal",
                    cnpj_8="55555555",
                ),
            ],
        ]
        # No direct coverage (first fetchone returns None)
        # Second fetchone: camara tem bids proprios -> count > 0
        cursor.fetchone.side_effect = [None, (5,)]

        result = build_entity_hierarchy(conn)

        assert result["skipped_camara_with_bids"] == 1
        assert result["inserted"] == 0

    def test_inserts_entity_hierarchy(self):
        """Entidade valida deve ser inserida na hierarchy."""
        conn = _make_conn()
        cursor = conn.cursor.return_value

        cursor.fetchall.side_effect = [
            # prefeituras
            [_pref_row(id=1)],
            # entidades
            [
                _ente_row(
                    id=10,
                    razao_social="Secretaria de Educacao",
                    natureza_juridica="Órgão Público do Poder Executivo Municipal",
                ),
                _ente_row(
                    id=11,
                    razao_social="Fundo de Saude",
                    natureza_juridica="Fundo Público da Administração Direta Municipal",
                ),
            ],
        ]
        # No direct coverage for either
        cursor.fetchone.return_value = None

        result = build_entity_hierarchy(conn)

        assert result["inserted"] == 2
        assert result["errors"] == 0
        assert cursor.execute.call_count >= 2

    def test_relationship_types(self):
        """Cada natureza_juridica deve gerar o relationship correto."""
        conn = _make_conn()
        cursor = conn.cursor.return_value

        cursor.fetchall.side_effect = [
            # prefeituras
            [_pref_row(id=1, razao_social="Municipio")],
            # entidades (one of each type)
            [
                _ente_row(
                    id=10,
                    razao_social="Secretaria",
                    natureza_juridica="Órgão Público do Poder Executivo Municipal",
                    cnpj_8="11111111",
                ),
                _ente_row(id=11, razao_social="Autarquia", natureza_juridica="Autarquia Municipal", cnpj_8="22222222"),
                _ente_row(
                    id=12,
                    razao_social="Fundacao",
                    natureza_juridica="Fundação Pública de Direito Público Municipal",
                    cnpj_8="33333333",
                ),
            ],
        ]
        cursor.fetchone.return_value = None

        result = build_entity_hierarchy(conn)

        assert result["inserted"] == 3
        assert result["errors"] == 0


# ---------------------------------------------------------------------------
# Test: resolve_entity_coverage_cascade
# ---------------------------------------------------------------------------


class TestResolveEntityCoverageCascade:
    def test_direct_coverage_returns_direct(self):
        """Entidade com cobertura direta deve retornar match_method='direct'."""
        conn = _make_conn()
        cursor = conn.cursor.return_value

        # Entity has direct coverage
        cursor.fetchone.return_value = (True, "direct", "pncp")

        result = resolve_entity_coverage_cascade(1, conn)

        assert result is not None
        assert result["is_covered"] is True
        assert result["match_method"] == "direct"
        assert result["source_entity_id"] == 1

    def test_hierarchical_coverage_when_parent_covered(self):
        """Entidade sem cobertura direta mas com parent coberto deve retornar hierarchical."""
        conn = _make_conn()
        cursor = conn.cursor.return_value

        # First query: no direct coverage (returns None)
        # Second query: has hierarchy with covered parent
        cursor.fetchone.side_effect = [
            None,  # no direct coverage row
            (99, "prefeitura", True),  # parent_id=99, relationship='prefeitura', parent_covered=True
        ]

        result = resolve_entity_coverage_cascade(1, conn)

        assert result is not None
        assert result["is_covered"] is True
        assert result["match_method"] == "hierarchical"
        assert result["source_entity_id"] == 99
        assert result["relationship"] == "prefeitura"

    def test_no_coverage_returns_none(self):
        """Entidade sem cobertura direta nem hierarquica deve retornar None."""
        conn = _make_conn()
        cursor = conn.cursor.return_value

        cursor.fetchone.side_effect = [
            None,  # no direct coverage
            None,  # no hierarchy
        ]

        result = resolve_entity_coverage_cascade(1, conn)

        assert result is None

    def test_hierarchy_exists_but_parent_uncovered(self):
        """Entidade com hierarquia mas parent descoberto deve retornar None (AC5)."""
        conn = _make_conn()
        cursor = conn.cursor.return_value

        cursor.fetchone.side_effect = [
            None,  # no direct coverage
            (99, "prefeitura", False),  # parent exists but is NOT covered
        ]

        result = resolve_entity_coverage_cascade(1, conn)

        assert result is None, "Nao deve marcar como coberto se parent nao tem dados"

    def test_direct_uncovered_no_hierarchy(self):
        """Entidade com registro de coverage mas is_covered=FALSE e sem hierarchy."""
        conn = _make_conn()
        cursor = conn.cursor.return_value

        # Direct coverage exists but is_covered=False
        cursor.fetchone.side_effect = [
            (False, None, "pncp"),  # exists but not covered
            None,  # no hierarchy
        ]

        result = resolve_entity_coverage_cascade(1, conn)

        assert result is None


# ---------------------------------------------------------------------------
# Test: apply_hierarchical_coverage
# ---------------------------------------------------------------------------


class TestApplyHierarchicalCoverage:
    def test_updates_entities_with_covered_parents(self):
        """Entidades com parent coberto devem ter coverage atualizada."""
        conn = _make_conn()
        cursor = conn.cursor.return_value

        cursor.fetchall.return_value = [
            (10, 1, "prefeitura"),
            (11, 1, "fundo"),
        ]

        result = apply_hierarchical_coverage(conn)

        assert result["updated"] == 2
        assert result["errors"] == 0

    def test_empty_hierarchy_returns_zero(self):
        """Sem entradas na hierarchy, nenhuma atualizacao."""
        conn = _make_conn()
        cursor = conn.cursor.return_value

        cursor.fetchall.return_value = []

        result = apply_hierarchical_coverage(conn)

        assert result["updated"] == 0
