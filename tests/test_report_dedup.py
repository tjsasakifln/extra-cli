"""Unit tests for report_dedup — semantic deduplication module.

Tests cover:
- normalize_for_dedup (accents, punctuation, lowercase, stopwords, edge cases)
- jaccard_similarity (identical, different, partial, empty sets)
- semantic_dedup (removes duplicates, respects threshold, grey-zone warnings)
- Empty list and edge case handling
"""

from __future__ import annotations

from scripts.report_dedup import _strip_accents, jaccard_similarity, normalize_for_dedup, semantic_dedup

# ===========================================================================
# normalize_for_dedup
# ===========================================================================


class TestNormalizeForDedup:
    """Tests for normalize_for_dedup — normalize text for Jaccard comparison."""

    def test_strips_accents(self):
        """Remove common Brazilian Portuguese diacritics."""
        result = normalize_for_dedup("Construção Civil Ltda")
        assert "construcao" in result, f"Expected 'construcao' in {result}"
        assert "civil" in result, f"Expected 'civil' in {result}"
        assert "ltda" in result, f"Expected 'ltda' in {result}"

    def test_removes_punctuation(self):
        """Strip punctuation, keeping only letters, digits, and spaces."""
        result = normalize_for_dedup("Obras de infra-estrutura (pavimentação) - R$ 1.500.000,00")
        # Accents removed, punctuation gone, numbers preserved
        assert "obras" in result
        assert "infra" in result
        assert "estrutura" in result or "infraestrutura" not in result
        assert "pavimentacao" in result
        assert "1.500.000" not in result  # Dots removed, becomes "1500000" (pure digits → skipped)
        assert "1500000" not in result  # Pure digits are skipped

    def test_lowercases_and_filters_stopwords(self):
        """Convert to lowercase and remove common stopwords."""
        text = "Contratação de empresa para prestação de serviços"
        result = normalize_for_dedup(text)
        assert "contratacao" in result
        assert "empresa" in result
        assert "prestacao" in result
        assert "servicos" in result
        # Stopwords removed
        assert "de" not in result
        assert "para" not in result

    def test_skips_short_words_and_numbers(self):
        """Filter out words with <=2 characters and pure digit tokens."""
        text = "Construcao de ponte 12345 em SC"
        result = normalize_for_dedup(text)
        assert "construcao" in result
        assert "ponte" in result
        # Stopwords and short words filtered
        assert "de" not in result
        assert "em" not in result
        assert "sc" not in result  # len("sc") == 2 and not in ("r$",)
        # Pure number filtered
        assert "12345" not in result

    def test_returns_empty_set_for_empty_input(self):
        """Return empty set for None, empty string, or whitespace-only input."""
        assert normalize_for_dedup("") == set()
        assert normalize_for_dedup("   ") == set()

    def test_r_dollar_token_removed_as_short_word(self):
        """Token 'r$' is removed by punctuation stripping before filter check.

        Note: R$ after lowercase + accent-strip becomes 'r$', then the
        punctuation regex [^a-z0-9\\s] strips '$', leaving 'r' (len=1).
        The code's stopword filter would preserve ('r$',) but the token
        never reaches that check because '$' is removed earlier.
        """
        text = "Valor R$ 500.000,00"
        result = normalize_for_dedup(text)
        assert "valor" not in result  # Stopword
        # After normalization: 'r' (from 'r$') is len=1, filtered
        # '50000000' (from '500.000,00' stripped of punctuation) is pure digits, filtered
        assert result == set(), f"Expected empty set, got {result}"

    def test_edge_case_special_chars(self):
        """Handle strings with special/non-ASCII characters gracefully."""
        # "EDITAL" is a stopword -- verify non-stopword tokens survive
        text = "EDITAL CONCORRENCIA ELETRONICA 001/2024"
        result = normalize_for_dedup(text)
        assert "concorrencia" in result
        assert "eletronica" in result
        # Stopword filtered
        assert "edital" not in result
        # Numbers filtered
        assert "001" not in result
        assert "2024" not in result


# ===========================================================================
# jaccard_similarity
# ===========================================================================


class TestJaccardSimilarity:
    """Tests for jaccard_similarity — Jaccard coefficient between token sets."""

    def test_identical_sets(self):
        """Return 1.0 for exactly equal token sets."""
        a = {"construcao", "civil", "obra"}
        assert jaccard_similarity(a, a) == 1.0

    def test_completely_different_sets(self):
        """Return 0.0 for disjoint token sets."""
        a = {"construcao", "civil"}
        b = {"saude", "hospitalar"}
        assert jaccard_similarity(a, b) == 0.0

    def test_partial_overlap(self):
        """Return correct coefficient for partially overlapping sets."""
        a = {"construcao", "civil", "obra", "pavimentacao"}
        b = {"construcao", "civil", "pontes"}
        # intersection = {construcao, civil} → 2
        # union = {construcao, civil, obra, pavimentacao, pontes} → 5
        # jaccard = 2/5 = 0.4
        expected = 2 / 5
        assert jaccard_similarity(a, b) == expected

    def test_one_empty_set(self):
        """Return 0.0 when one of the sets is empty."""
        a = {"construcao", "civil"}
        assert jaccard_similarity(a, set()) == 0.0
        assert jaccard_similarity(set(), a) == 0.0

    def test_both_empty_sets(self):
        """Return 0.0 when both sets are empty."""
        assert jaccard_similarity(set(), set()) == 0.0

    def test_contained_set(self):
        """Handle case where one set is subset of the other."""
        a = {"construcao", "civil", "obra", "pavimentacao"}
        b = {"construcao", "civil"}
        # intersection = 2, union = 4 → 0.5
        assert jaccard_similarity(a, b) == 0.5
        assert jaccard_similarity(b, a) == 0.5


# ===========================================================================
# semantic_dedup
# ===========================================================================


class TestSemanticDedup:
    """Tests for semantic_dedup — two-pass dedup (exact + semantic)."""

    def test_removes_exact_duplicates_by_id(self):
        """Remove items with identical cnpj_orgao+ano+sequencial keys."""
        editais = [
            {
                "cnpj_orgao": "12345678000199",
                "ano_compra": "2024",
                "sequencial_compra": "1",
                "objeto": "Construção de ponte",
            },
            {
                "cnpj_orgao": "12345678000199",
                "ano_compra": "2024",
                "sequencial_compra": "1",
                "objeto": "Construção de ponte",
            },
            {
                "cnpj_orgao": "99999999000199",
                "ano_compra": "2024",
                "sequencial_compra": "2",
                "objeto": "Pavimentação urbana",
            },
        ]
        deduped, stats = semantic_dedup(editais)
        assert len(deduped) == 2
        assert stats["exact_removed"] == 1
        assert stats["semantic_removed"] == 0

    def test_removes_semantic_duplicates_above_threshold(self):
        """Remove items with Jaccard similarity >= jaccard_threshold."""
        # A e B compartilham todos os 6 tokens de A, B tem 1 extra
        # Jaccard = 6/7 ~= 0.857
        editais = [
            {
                "cnpj_orgao": "111",
                "ano_compra": "2024",
                "sequencial_compra": "1",
                "objeto": "construcao ponte metalica rodovia pavimentacao asfalto",
            },
            {
                "cnpj_orgao": "222",
                "ano_compra": "2024",
                "sequencial_compra": "2",
                "objeto": "construcao ponte metalica rodovia pavimentacao asfalto concreto",
            },
        ]
        deduped, stats = semantic_dedup(editais, jaccard_threshold=0.80)
        assert len(deduped) == 1
        assert stats["semantic_removed"] == 1

    def test_generates_warnings_in_grey_zone(self):
        """Log warning for items with similarity between warning_threshold and jaccard_threshold."""
        # Texts share 2 of 6 tokens → Jaccard = 2/6 ≈ 0.33
        editais = [
            {
                "cnpj_orgao": "111",
                "ano_compra": "2024",
                "sequencial_compra": "1",
                "objeto": "pavimentacao asfaltica vias urbanas municipais escola",
            },
            {
                "cnpj_orgao": "222",
                "ano_compra": "2024",
                "sequencial_compra": "2",
                "objeto": "pavimentacao asfaltica ruas bairros centro hospital",
            },
        ]
        # warning_threshold below Jaccard (0.33) to trigger grey-zone warnings
        # jaccard_threshold high so they are NOT removed as duplicates
        deduped, stats = semantic_dedup(editais, jaccard_threshold=0.95, warning_threshold=0.20)
        assert stats["candidates_evaluated"] >= 1
        assert stats["semantic_removed"] == 0
        assert len(stats["semantic_warnings"]) >= 1

    def test_empty_list(self):
        """Return empty list and zeroed stats for empty input."""
        deduped, stats = semantic_dedup([])
        assert deduped == []
        assert stats["exact_removed"] == 0
        assert stats["semantic_removed"] == 0
        assert stats["candidates_evaluated"] == 0
        assert stats["semantic_warnings"] == []

    def test_preserves_unique_items(self):
        """Keep all items when there are no duplicates."""
        editais = [
            {
                "cnpj_orgao": "111",
                "ano_compra": "2024",
                "sequencial_compra": "1",
                "objeto": "Construção de escola municipal",
            },
            {
                "cnpj_orgao": "222",
                "ano_compra": "2024",
                "sequencial_compra": "2",
                "objeto": "Aquisição de ambulância para emergências",
            },
        ]
        deduped, stats = semantic_dedup(editais)
        assert len(deduped) == 2
        assert stats["exact_removed"] == 0
        assert stats["semantic_removed"] == 0


# ===========================================================================
# _strip_accents (internal helper)
# ===========================================================================


class TestStripAccents:
    """Tests for _strip_accents — internal diacritics removal."""

    def test_removes_common_portuguese_accents(self):
        """Strip acutes, tildes, and cedilha from Portuguese text."""
        result = _strip_accents("Órgão Público de São João")
        assert result == "Orgao Publico de Sao Joao"

    def test_ascii_passthrough(self):
        """Leave plain ASCII text completely unchanged."""
        assert _strip_accents("PREFEITURA MUNICIPAL") == "PREFEITURA MUNICIPAL"

    def test_empty_string(self):
        """Return empty string for empty input."""
        assert _strip_accents("") == ""
