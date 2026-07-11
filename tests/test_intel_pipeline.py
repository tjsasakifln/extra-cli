"""Unit tests for the intel_pipeline orchestrator and its quality gates.

Tests cover:
- Pipeline stage definitions (7 stages documented)
- CLI argument validation (CNPJ, UFs, dias, top)
- Pure helper functions (_clean_cnpj, _strip_accents, _slug, _fmt_duration)
- Quality gate functions with mock data (no DB, no API keys)
- lib.cli_validation validators
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.intel_pipeline import (
    _clean_cnpj,
    _fmt_duration,
    _slug,
    _strip_accents,
    gate1_cobertura,
    gate2_cadastral,
)
from scripts.lib.cli_validation import validate_cnpj, validate_dias, validate_ufs
from scripts.lib.constants import MAX_DIAS, MAX_PIPELINE_STEP, MAX_TOP


# ===========================================================================
# Pipeline Stage Definitions
# ===========================================================================


class TestPipelineStages:
    """Verify the pipeline has the expected 7 stages."""

    def test_pipeline_stages_count(self):
        """The pipeline must define exactly 7 stages (1-7)."""
        # MAX_PIPELINE_STEP from lib.constants is the authoritative source
        assert MAX_PIPELINE_STEP == 7, (
            f"Expected 7 pipeline stages, got MAX_PIPELINE_STEP={MAX_PIPELINE_STEP}"
        )

    def test_pipeline_steps_documented(self):
        """The module docstring must list all 7 pipeline steps."""
        from scripts import intel_pipeline as mod

        doc = (mod.__doc__ or "").lower()
        # Check that key stage markers are present in the docstring
        assert "collect" in doc, "Docstring missing stage: Collect"
        assert "enrich" in doc, "Docstring missing stage: Enrich"
        assert "llm gate" in doc or "llm_gate" in doc, "Docstring missing stage: LLM Gate"
        assert "extract docs" in doc or "extract_docs" in doc, (
            "Docstring missing stage: Extract Docs"
        )
        assert "analyze" in doc, "Docstring missing stage: Analyze"
        assert "excel" in doc, "Docstring missing stage: Excel"
        assert "pdf" in doc or "report" in doc, "Docstring missing stage: PDF Report"

    def test_gate_functions_exist(self):
        """All 5 quality gate functions must be defined."""
        from scripts import intel_pipeline as mod

        assert hasattr(mod, "gate1_cobertura")
        assert hasattr(mod, "gate2_cadastral")
        assert hasattr(mod, "gate3_ruido")
        assert hasattr(mod, "gate4_conteudo")
        assert hasattr(mod, "gate5_recomendacao")


# ===========================================================================
# Pure Helpers
# ===========================================================================


class TestCleanCnpj:
    """Tests for _clean_cnpj — strip non-digits from CNPJ strings."""

    def test_removes_formatting(self):
        """Strip dots, slashes, and dashes from formatted CNPJ."""
        assert _clean_cnpj("12.345.678/0001-99") == "12345678000199"

    def test_preserves_plain_digits(self):
        """Return the same string when already digits-only."""
        assert _clean_cnpj("12345678000199") == "12345678000199"

    def test_removes_any_non_digit(self):
        """Strip letters and other non-digit characters."""
        assert _clean_cnpj("ABC 12.345.678/0001-99 XYZ") == "12345678000199"

    def test_empty_string(self):
        """Return empty string for empty input."""
        assert _clean_cnpj("") == ""

    def test_short_cnpj(self):
        """Return only digits even if fewer than 14."""
        assert _clean_cnpj("12.345") == "12345"


class TestStripAccents:
    """Tests for _strip_accents — remove diacritics from text."""

    def test_removes_common_accents(self):
        """Strip common Brazilian Portuguese accents."""
        result = _strip_accents("São João do Sul")
        assert "ç" not in result  # ç -> c
        assert "ã" not in result  # ã -> a
        assert "á" not in result  # á -> a
        assert result == "Sao Joao do Sul", f"Got: {result}"

    def test_preserves_ascii(self):
        """Leave plain ASCII text unchanged."""
        assert _strip_accents("PREFEITURA MUNICIPAL") == "PREFEITURA MUNICIPAL"

    def test_empty_string(self):
        """Return empty string for empty input."""
        assert _strip_accents("") == ""

    def test_mixed_text(self):
        """Handle text with mixed accented and non-accented chars."""
        result = _strip_accents("Órgão emissor: SSP/SC")
        assert result == "Orgao emissor: SSP/SC", f"Got: {result}"


class TestSlug:
    """Tests for _slug — convert razao_social to URL-friendly slug."""

    def test_basic_slug(self):
        """Convert simple name to lowercase hyphenated slug."""
        result = _slug("Prefeitura Municipal")
        assert result == "prefeitura-municipal"

    def test_removes_accents(self):
        """Remove accents during slugification."""
        result = _slug("São João do Sul")
        assert result == "sao-joao-do-sul", f"Got: {result}"

    def test_max_length_40(self):
        """Crop slug at 40 characters."""
        long_name = "Empresa de Construcao Civil e Infraestrutura Ltda - EPP"
        result = _slug(long_name)
        assert len(result) <= 40, f"Slug length {len(result)} > 40: {result}"

    def test_collapses_multiple_hyphens(self):
        """Replace consecutive hyphens with a single hyphen."""
        result = _slug("foo   bar---baz")
        assert result == "foo-bar-baz", f"Got: {result}"

    def test_strips_trailing_hyphens(self):
        """Remove leading/trailing hyphens."""
        result = _slug("-hello world-")
        assert result == "hello-world"


class TestFmtDuration:
    """Tests for _fmt_duration — format seconds into human-readable duration."""

    def test_under_60_seconds(self):
        """Show seconds with one decimal for durations under 60s."""
        assert _fmt_duration(5.5) == "5.5s"
        assert _fmt_duration(0.1) == "0.1s"
        assert _fmt_duration(59.9) == "59.9s"

    def test_exactly_60_seconds(self):
        """Show 1m00s for exactly 60 seconds."""
        assert _fmt_duration(60) == "1m00s"

    def test_minutes_and_seconds(self):
        """Show minutes and seconds for longer durations."""
        result = _fmt_duration(125)
        assert result == "2m05s", f"Got: {result}"

    def test_large_duration(self):
        """Handle durations of many minutes."""
        result = _fmt_duration(3600)
        assert result == "60m00s", f"Got: {result}"


# ===========================================================================
# CLI Validation
# ===========================================================================


class TestValidateCnpj:
    """Tests for validate_cnpj — validates and normalizes CNPJ."""

    def test_valid_formatted_cnpj(self):
        """Accept a properly formatted CNPJ and return 14 digits."""
        assert validate_cnpj("12.345.678/0001-99") == "12345678000199"

    def test_valid_plain_cnpj(self):
        """Accept a plain 14-digit CNPJ."""
        assert validate_cnpj("12345678000199") == "12345678000199"

    def test_rejects_short_cnpj(self):
        """Exit when CNPJ has fewer than 14 digits."""
        with pytest.raises(SystemExit):
            validate_cnpj("12345678")

    def test_rejects_empty_cnpj(self):
        """Exit when CNPJ is empty."""
        with pytest.raises(SystemExit):
            validate_cnpj("")

    def test_rejects_long_cnpj(self):
        """Exit when CNPJ has more than 14 digits."""
        with pytest.raises(SystemExit):
            validate_cnpj("123456789012345")


class TestValidateUfs:
    """Tests for validate_ufs — validates comma-separated UF list."""

    def test_valid_single_uf(self):
        """Accept a single valid UF."""
        assert validate_ufs("SC") == ["SC"]

    def test_valid_multiple_ufs(self):
        """Accept multiple comma-separated UFs."""
        result = validate_ufs("SC,PR,RS")
        assert result == ["SC", "PR", "RS"]

    def test_trims_whitespace(self):
        """Trim whitespace around UF codes."""
        result = validate_ufs("  SC , PR ")
        assert result == ["SC", "PR"]

    def test_rejects_invalid_uf(self):
        """Exit when an invalid UF code is provided."""
        with pytest.raises(SystemExit):
            validate_ufs("SC,XYZ")

    def test_rejects_empty(self):
        """Exit when UF list is empty."""
        with pytest.raises(SystemExit):
            validate_ufs("")


class TestValidateDias:
    """Tests for validate_dias — validates the --dias argument."""

    def test_valid_dias(self):
        """Accept a valid number of days within range."""
        validate_dias(30)  # Should not raise

    def test_min_dias(self):
        """Accept the minimum valid value (1)."""
        validate_dias(1)

    def test_max_dias(self):
        """Accept the maximum valid value (MAX_DIAS)."""
        validate_dias(MAX_DIAS)

    def test_rejects_zero(self):
        """Reject zero days."""
        with pytest.raises(SystemExit):
            validate_dias(0)

    def test_rejects_negative(self):
        """Reject negative days."""
        with pytest.raises(SystemExit):
            validate_dias(-1)

    def test_rejects_above_max(self):
        """Reject days above MAX_DIAS."""
        with pytest.raises(SystemExit):
            validate_dias(MAX_DIAS + 1)


# ===========================================================================
# Quality Gates (unit-level, no DB/API)
# ===========================================================================


class TestGate1Cobertura:
    """Tests for gate1_cobertura — coverage validation gate."""

    def test_passes_with_valid_data(self):
        """Gate passes when empresa has OK status and editais exist."""
        data = {
            "editais": [
                {"uf": "SC", "cnae_compatible": True, "needs_llm_review": False},
                {"uf": "PR", "cnae_compatible": False, "needs_llm_review": True},
            ],
            "empresa": {"razao_social": "Teste Ltda", "_source": {"status": "OK"}},
            "estatisticas": {},
        }
        passed, issues, fixed = gate1_cobertura(data, ["SC", "PR"])
        assert passed is True
        # Issues may contain pagination/coverage warnings but not fatal errors

    def test_fails_on_api_failed(self):
        """Gate fails when empresa._source.status is API_FAILED."""
        data = {
            "editais": [],
            "empresa": {"razao_social": "Falhou Ltda", "_source": {"status": "API_FAILED"}},
            "estatisticas": {},
        }
        passed, issues, fixed = gate1_cobertura(data, ["SC"])
        assert passed is False
        assert any("API_FAILED" in i for i in issues)

    def test_fails_on_zero_editais(self):
        """Gate fails when there are zero editais collected."""
        data = {
            "editais": [],
            "empresa": {"razao_social": "Vazio Ltda", "_source": {"status": "OK"}},
            "estatisticas": {},
        }
        passed, issues, fixed = gate1_cobertura(data, ["SC"])
        assert passed is False
        assert any("Zero" in i for i in issues)


class TestGate2Cadastral:
    """Tests for gate2_cadastral — cadastral enrichment validation gate."""

    def test_passes_with_clean_data(self):
        """Gate passes when empresa has no sanctions and basic enrichment."""
        data = {
            "editais": [
                {
                    "cnae_compatible": True,
                    "valor_estimado": 100000.0,
                    "distancia_km": 50,
                },
            ],
            "empresa": {
                "sancionada": False,
                "sicaf": {"status": "OK"},
            },
        }
        passed, issues, fixed = gate2_cadastral(data, top_n=5)
        assert passed is True

    def test_marks_sanctioned_company(self):
        """Gate detects sanctioned company but does not abort."""
        data = {
            "editais": [
                {
                    "cnae_compatible": True,
                    "valor_estimado": 100000.0,
                },
            ],
            "empresa": {
                "sancionada": True,
                "sicaf": {"status": "OK"},
            },
        }
        passed, issues, fixed = gate2_cadastral(data, top_n=5)
        assert passed is True  # Gate does NOT abort on sanctions
        assert any("SANCIONADA" in i for i in issues)
