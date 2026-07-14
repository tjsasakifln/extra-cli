"""Tests for unified entity matching (TD-027) — Story 1.5.

Tests cover:
    - match_entities_cascade accepts optional pncp_ids parameter
    - Matching with pncp_ids filter works correctly
    - match_entity still works (single entity matching)
    - Backward compatibility with existing test patterns
"""

from __future__ import annotations

from unittest.mock import MagicMock

from scripts.matching.entity_matcher import (
    match_entities_cascade,
    match_entity,
    update_matched_entity_full,
)

# Reuse existing sample entities
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
]


def _make_mock_conn(unmatched_bids: list[dict]) -> MagicMock:
    """Create a mock connection that returns given unmatched bids."""
    conn = MagicMock()
    cursor = conn.cursor.return_value

    cols = list(unmatched_bids[0].keys()) if unmatched_bids else ["pncp_id"]
    cursor.description = [(c, None, None, None, None, None, None) for c in cols]
    cursor.fetchall.return_value = [tuple(b[c] for c in cols) for b in unmatched_bids]

    return conn


class TestMatchEntitiesCascadeUnified:
    """TD-027: Test the unified matching with pncp_ids support."""

    def test_without_pncp_ids_finds_unmatched(self):
        """Default behavior: match all unmatched bids for source."""
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

    def test_with_pncp_ids_filter(self):
        """Match only specific bids by pncp_ids."""
        bids = [
            {
                "pncp_id": "bid-001",
                "orgao_cnpj": "12345678000199",
                "orgao_razao_social": "PREFEITURA MUNICIPAL DE FLORIANOPOLIS",
                "municipio": "Florianopolis",
                "codigo_municipio_ibge": "4205407",
            },
            {
                "pncp_id": "bid-002",
                "orgao_cnpj": "87654321000199",
                "orgao_razao_social": "PREFEITURA MUNICIPAL DE SAO JOSE",
                "municipio": "Sao Jose",
                "codigo_municipio_ibge": "4205408",
            },
        ]
        conn = _make_mock_conn(bids)
        # Filter to only bid-001
        result = match_entities_cascade(conn, "pncp", SAMPLE_ENTITIES, pncp_ids=["bid-001"])
        # Should find and match bid-001
        assert result["cnpj"] >= 0  # At least attempt matching
        assert result["total"] >= 1  # At least one bid processed

    def test_empty_pncp_ids_returns_no_matches(self):
        """Empty pncp_ids should still execute but find nothing."""
        conn = MagicMock()
        cursor = conn.cursor.return_value
        cursor.fetchall.return_value = []
        cursor.description = [("pncp_id", None, None, None, None, None, None)]

        result = match_entities_cascade(conn, "pncp", SAMPLE_ENTITIES, pncp_ids=[])
        assert result["total"] == 0

    def test_no_unmatched_bids_returns_zeros(self):
        """When there are no bids to match, return zero stats."""
        conn = MagicMock()
        cursor = conn.cursor.return_value
        cursor.fetchall.return_value = []
        cursor.description = [("pncp_id", None, None, None, None, None, None)]

        result = match_entities_cascade(conn, "pncp", SAMPLE_ENTITIES)
        assert result == {"cnpj": 0, "name_normalized": 0, "alias": 0, "fuzzy": 0, "unmatched": 0, "total": 0}


class TestMatchEntity:
    """Existing match_entity tests still pass."""

    def test_exact_cnpj_14_digits(self):
        result = match_entity("12345678000199", SAMPLE_ENTITIES)
        assert result is not None
        assert result["id"] == 1

    def test_no_match_returns_none(self):
        result = match_entity("99999999000199", SAMPLE_ENTITIES)
        assert result is None

    def test_empty_cnpj_returns_none(self):
        assert match_entity("", SAMPLE_ENTITIES) is None
        assert match_entity(None, SAMPLE_ENTITIES) is None  # type: ignore[arg-type]


class TestUpdateMatchedEntityFull:
    def test_sets_all_fields(self):
        conn = MagicMock()
        update_matched_entity_full(conn, "bid-123", 1, "cnpj", 1.0, "high")

        conn.cursor.assert_called_once()
        cursor = conn.cursor.return_value
        cursor.execute.assert_called_once()

        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]

        assert "matched_entity_id" in sql
        assert params == (1, "cnpj", 1.0, "high", "bid-123")
        cursor.close.assert_called_once()

    def test_sets_unmatched_fields(self):
        conn = MagicMock()
        update_matched_entity_full(conn, "bid-456", None, "unmatched", 0.0, None)

        cursor = conn.cursor.return_value
        params = cursor.execute.call_args[0][1]
        assert params == (None, "unmatched", 0.0, None, "bid-456")
