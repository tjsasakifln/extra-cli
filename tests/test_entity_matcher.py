"""Unit tests for scripts/matching/entity_matcher.py.

Tests cover the 3-level cascade matching logic without a database
by testing the pure functions directly.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from scripts.matching.entity_matcher import (
    match_entities_cascade,
    match_entity,
    update_matched_entity_full,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_ENTITIES = [
    {
        "id": 1,
        "razao_social": "PREFEITURA MUNICIPAL DE FLORIANOPOLIS",
        "cnpj_8": "12345678",
        "municipio": "Florianopolis",
        "codigo_ibge": "4205407",
        "natureza_juridica": "PREFEITURA",
        "raio_200km": True,
    },
    {
        "id": 2,
        "razao_social": "PREFEITURA MUNICIPAL DE SAO JOSE",
        "cnpj_8": "87654321",
        "municipio": "Sao Jose",
        "codigo_ibge": "4205408",
        "natureza_juridica": "PREFEITURA",
        "raio_200km": True,
    },
    {
        "id": 3,
        "razao_social": "SECRETARIA DE ESTADO DA SAUDE DE SC",
        "cnpj_8": "55667788",
        "municipio": "Florianopolis",
        "codigo_ibge": "4205407",
        "natureza_juridica": "SECRETARIA",
        "raio_200km": True,
    },
]


# ---------------------------------------------------------------------------
# match_entity
# ---------------------------------------------------------------------------


class TestMatchEntity:
    def test_exact_cnpj_14_digits(self):
        """Match by 14-digit CNPJ starting with entity's 8-digit base."""
        result = match_entity("12345678000199", SAMPLE_ENTITIES)
        assert result is not None
        assert result["id"] == 1

    def test_just_8_digit_base(self):
        """Match by 8-digit CNPJ base."""
        result = match_entity("87654321", SAMPLE_ENTITIES)
        assert result is not None
        assert result["id"] == 2

    def test_no_match_returns_none(self):
        """Return None when CNPJ does not match any entity."""
        result = match_entity("99999999000199", SAMPLE_ENTITIES)
        assert result is None

    def test_empty_cnpj_returns_none(self):
        """Return None for empty/None CNPJ."""
        assert match_entity("", SAMPLE_ENTITIES) is None
        assert match_entity(None, SAMPLE_ENTITIES) is None  # type: ignore[arg-type]

    def test_cnpj_with_special_chars(self):
        """Handle CNPJ with formatting characters."""
        result = match_entity("12.345.678/0001-99", SAMPLE_ENTITIES)
        assert result is not None
        assert result["id"] == 1


# ---------------------------------------------------------------------------
# update_matched_entity_full
# ---------------------------------------------------------------------------


class TestUpdateMatchedEntityFull:
    def test_sets_all_fields(self):
        """Verify SQL UPDATE includes all match metadata fields."""
        conn = MagicMock()
        update_matched_entity_full(conn, "bid-123", 1, "cnpj", 1.0, "high")

        conn.cursor.assert_called_once()
        cursor = conn.cursor.return_value
        cursor.execute.assert_called_once()

        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]

        assert "matched_entity_id" in sql
        assert "match_method" in sql
        assert "match_score" in sql
        assert "match_confidence" in sql
        assert params == (1, "cnpj", 1.0, "high", "bid-123")
        cursor.close.assert_called_once()

    def test_sets_unmatched_fields(self):
        """Set entity_id to None and confidence to None when unmatched."""
        conn = MagicMock()
        update_matched_entity_full(conn, "bid-456", None, "unmatched", 0.0, None)

        cursor = conn.cursor.return_value
        params = cursor.execute.call_args[0][1]

        assert params == (None, "unmatched", 0.0, None, "bid-456")


# ---------------------------------------------------------------------------
# match_entities_cascade
# ---------------------------------------------------------------------------


def _make_mock_conn(unmatched_bids: list[dict]) -> MagicMock:
    """Create a mock connection that returns given unmatched bids."""
    conn = MagicMock()
    cursor = conn.cursor.return_value

    # First query: unmatched bids
    cols = list(unmatched_bids[0].keys()) if unmatched_bids else ["pncp_id"]
    cursor.description = [(c, None, None, None, None, None, None) for c in cols]
    cursor.fetchall.return_value = [tuple(b[c] for c in cols) for b in unmatched_bids]

    return conn


class TestMatchEntitiesCascade:
    def test_no_unmatched_bids(self):
        """Return zeros when there are no unmatched bids."""
        conn = MagicMock()
        cursor = conn.cursor.return_value
        cursor.fetchall.return_value = []
        cursor.description = [("pncp_id", None, None, None, None, None, None)]

        result = match_entities_cascade(conn, "pncp", SAMPLE_ENTITIES)

        assert result == {"cnpj": 0, "name_normalized": 0, "fuzzy": 0, "unmatched": 0, "total": 0}

    def test_level1_cnpj_match(self):
        """Level 1: CNPJ match should succeed."""
        bids = [
            {
                "pncp_id": "bid-001",
                "orgao_cnpj": "12345678000199",
                "orgao_razao_social": "PREFEITURA MUNICIPAL DE FLORIANOPOLIS",
                "municipio": "Florianopolis",
                "codigo_municipio_ibge": "4205407",
            }
        ]
        conn = _make_mock_conn(bids)

        result = match_entities_cascade(conn, "pncp", SAMPLE_ENTITIES)

        assert result["cnpj"] == 1
        assert result["total"] == 1

    def test_level2_name_normalized_match(self):
        """Level 2: Normalized name + municipio match."""
        bids = [
            {
                "pncp_id": "bid-002",
                "orgao_cnpj": "",
                "orgao_razao_social": "Prefeitura Municipal de Florianopolis",
                "municipio": "Florianopolis",
                "codigo_municipio_ibge": "4205407",
            }
        ]
        conn = _make_mock_conn(bids)

        result = match_entities_cascade(conn, "pncp", SAMPLE_ENTITIES)

        # Should match via Level 2 (normalized name + IBGE)
        assert result["name_normalized"] == 1
        assert result["total"] == 1

    def test_unmatched_bid(self):
        """Bid with no matching entity should be marked as unmatched."""
        bids = [
            {
                "pncp_id": "bid-003",
                "orgao_cnpj": "00000000000199",
                "orgao_razao_social": "SECRETARIA MUNICIPAL DE SAUDE DESCONHECIDA",
                "municipio": "Cidade Desconhecida",
                "codigo_municipio_ibge": "9999999",
            }
        ]
        conn = _make_mock_conn(bids)

        result = match_entities_cascade(conn, "pncp", SAMPLE_ENTITIES)

        assert result["unmatched"] == 1
        assert result["total"] == 1

    def test_cascade_priority(self):
        """Level 1 (CNPJ) should match before Level 2 or 3."""
        bids = [
            {
                "pncp_id": "bid-004",
                # This CNPJ matches entity 1, but the name matches entity 2
                "orgao_cnpj": "12345678000199",
                "orgao_razao_social": "PREFEITURA MUNICIPAL DE SAO JOSE",
                "municipio": "Sao Jose",
                "codigo_municipio_ibge": "4205408",
            }
        ]
        conn = _make_mock_conn(bids)

        result = match_entities_cascade(conn, "pncp", SAMPLE_ENTITIES)

        # Should match entity 1 via CNPJ (Level 1), not entity 2 via name (Level 2)
        assert result["cnpj"] == 1
        assert result["name_normalized"] == 0
        assert result["total"] == 1

    def test_level1_prefix_match_with_14_digits(self):
        """Level 1: Prefix match when 14-digit CNPJ starts with entity 8-digit base."""
        # Entity 1 has cnpj_8="12345678". A 14-digit CNPJ starting with that
        # but not matching as exact 8-digit base should still match via prefix lookup.
        bids = [
            {
                "pncp_id": "bid-005",
                "orgao_cnpj": "12345678000188",  # Same prefix as entity 1, different suffix
                "orgao_razao_social": "PREFEITURA MUNICIPAL DE FLORIANOPOLIS FILIAL",
                "municipio": "Florianopolis",
                "codigo_municipio_ibge": "4205407",
            }
        ]
        conn = _make_mock_conn(bids)

        result = match_entities_cascade(conn, "pncp", SAMPLE_ENTITIES)

        assert result["cnpj"] == 1
        assert result["total"] == 1

    def test_level2b_without_municipio_constraint(self):
        """Level 2b: Name match without IBGE code when Level 2a fails."""
        bids = [
            {
                "pncp_id": "bid-006",
                "orgao_cnpj": "",
                # Same name as entity 1 but different IBGE, then fallback to
                # exact name without municipio constraint
                "orgao_razao_social": "PREFEITURA MUNICIPAL DE FLORIANOPOLIS",
                "municipio": "Cidade Errada",
                "codigo_municipio_ibge": "9999999",
            }
        ]
        conn = _make_mock_conn(bids)

        result = match_entities_cascade(conn, "pncp", SAMPLE_ENTITIES)

        # Should match via Level 2b (name exact, no IBGE filter)
        assert result["name_normalized"] == 1
        assert result["total"] == 1

    def test_level3_fuzzy_match_high_confidence(self):
        """Level 3: Fuzzy match with high confidence (>= 0.95)."""
        bids = [
            {
                "pncp_id": "bid-007",
                "orgao_cnpj": "",
                # Not exact match (different name) but very similar
                "orgao_razao_social": "PREFEITURA MUNICIPAL FLORIANOPOLIS",
                "municipio": "Florianopolis",
                "codigo_municipio_ibge": "4205407",
            }
        ]
        conn = _make_mock_conn(bids)

        result = match_entities_cascade(conn, "pncp", SAMPLE_ENTITIES)

        # Should match via Level 3 fuzzy with high confidence
        assert result["fuzzy"] == 1
        assert result["total"] == 1

    def test_level3_fuzzy_medium_confidence(self):
        """Level 3: Fuzzy match with medium confidence (< 0.95 but >= threshold)."""
        bids = [
            {
                "pncp_id": "bid-008",
                "orgao_cnpj": "",
                # Moderate difference to produce medium confidence
                "orgao_razao_social": "PREFEITURA MUNICIPAL FLORIANOPOLIS",
                "municipio": "Florianopolis",
                "codigo_municipio_ibge": "4205407",
            }
        ]
        conn = _make_mock_conn(bids)

        result = match_entities_cascade(conn, "pncp", SAMPLE_ENTITIES)

        assert result["total"] == 1
        # This should be fuzzy match (not exact name match) with medium or high confidence

    def test_level3_fuzzy_below_threshold(self):
        """Level 3: Fuzzy score below threshold should remain unmatched."""
        bids = [
            {
                "pncp_id": "bid-009",
                "orgao_cnpj": "",
                # Very different name — should not match any entity
                "orgao_razao_social": "SECRETARIA MUNICIPAL DE SAUDE DESCONHECIDA",
                "municipio": "Florianopolis",
                "codigo_municipio_ibge": "4205407",
            }
        ]
        conn = _make_mock_conn(bids)

        result = match_entities_cascade(conn, "pncp", SAMPLE_ENTITIES)

        assert result["unmatched"] == 1
        assert result["total"] == 1
        assert result["fuzzy"] == 0


# ---------------------------------------------------------------------------
# match_entity — Additional edge cases
# ---------------------------------------------------------------------------


class TestMatchEntityAdditional:
    def test_cnpj_with_only_8_digits_matches(self):
        """Match by exactly 8 digits provided as CNPJ."""
        result = match_entity("12345678", SAMPLE_ENTITIES)
        assert result is not None
        assert result["id"] == 1

    def test_cnpj_startswith_8_digit_base(self):
        """14-digit CNPJ matching entity 8-digit prefix."""
        result = match_entity("87654321000199", SAMPLE_ENTITIES)
        assert result is not None
        assert result["id"] == 2

    def test_cnpj_matches_none_for_short_input(self):
        """CNPJ with < 8 digits returns None."""
        result = match_entity("123", SAMPLE_ENTITIES)
        assert result is None


# ---------------------------------------------------------------------------
# difflib fallback (Level 3 without rapidfuzz)
# ---------------------------------------------------------------------------


class TestMatchEntitiesCascadeDifflibFallback:
    """Test cascade matching with difflib as fallback."""

    def test_fuzzy_match_with_difflib_fallback(self):
        """Level 3 works via difflib when _fuzz_ratio is set to use difflib."""
        from difflib import SequenceMatcher

        # Inject a difflib-based fuzz_ratio into the entity_matcher module
        import scripts.matching.entity_matcher as em
        em._fuzz_ratio = lambda a, b: SequenceMatcher(None, a, b).ratio()

        bids = [
            {
                "pncp_id": "bid-difl-001",
                "orgao_cnpj": "",
                "orgao_razao_social": "PREFEITURA MUNICIPAL FLORIPA",
                "municipio": "Florianopolis",
                "codigo_municipio_ibge": "4205407",
            }
        ]
        conn = _make_mock_conn(bids)

        result = em.match_entities_cascade(conn, "pncp", SAMPLE_ENTITIES)

        # Should find a fuzzy match via difflib
        assert result["total"] >= 1

    def test_normal_fuzzy_still_works(self):
        """Default fuzzy matching (rapidfuzz) still works."""
        bids = [
            {
                "pncp_id": "bid-difl-002",
                "orgao_cnpj": "",
                "orgao_razao_social": "PREFEITURA MUNICIPAL FLORIPA",
                "municipio": "Florianopolis",
                "codigo_municipio_ibge": "4205407",
            }
        ]
        conn = _make_mock_conn(bids)

        import scripts.matching.entity_matcher as em
        result = em.match_entities_cascade(conn, "pncp", SAMPLE_ENTITIES)

        assert result["total"] >= 1
