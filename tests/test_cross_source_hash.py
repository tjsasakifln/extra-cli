"""Unit tests for generate_cross_source_hash (CM-13 / C2.8).

AC-5: formatting variants of the same edital yield the same hash.
AC-6: distinct editais yield different hashes.
"""

from __future__ import annotations

from scripts.crawl.common import generate_cross_source_hash


class TestGenerateCrossSourceHash:
    def test_deterministic_with_formatting_variants(self):
        """AC-5: accents/punctuation/case on modalidade+objeto normalize away."""
        h1 = generate_cross_source_hash(
            modalidade="Pregão Eletrônico",
            objeto="Aquisição de computadores!!",
            orgao_cnpj_raiz="82926551",
            data_publicacao="2026-01-15",
            valor_total=1000.0,
        )
        h2 = generate_cross_source_hash(
            modalidade="pregao eletronico",
            objeto="aquisicao de computadores",
            orgao_cnpj_raiz="82926551",
            data_publicacao="2026-01-15",
            valor_total=1000.0,
        )
        assert h1 == h2
        assert len(h1) == 64  # sha256

    def test_different_objeto_different_hash(self):
        """AC-6: distinct objects must not collide."""
        h1 = generate_cross_source_hash(
            modalidade="Pregão Eletrônico",
            objeto="Aquisição de computadores",
            orgao_cnpj_raiz="82926551",
            data_publicacao="2026-01-15",
            valor_total=1000.0,
        )
        h2 = generate_cross_source_hash(
            modalidade="Pregão Eletrônico",
            objeto="Aquisição de notebooks",
            orgao_cnpj_raiz="82926551",
            data_publicacao="2026-01-15",
            valor_total=1000.0,
        )
        assert h1 != h2

    def test_different_valor_different_hash(self):
        h1 = generate_cross_source_hash(
            "Pregão", "Objeto X", "82926551", "2026-01-15", 1000.0
        )
        h2 = generate_cross_source_hash(
            "Pregão", "Objeto X", "82926551", "2026-01-15", 2000.0
        )
        assert h1 != h2
