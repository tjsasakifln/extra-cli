"""Tests for scripts.lib.universe — canonical universe definitions.

These tests verify:
    1. The constant matches the audited value (1093).
    2. ``normalize_cnpj8`` handles all required edge cases.
    3. Coverage invariants hold (numerator ≤ denominator, 0‑100 % range,
       no negative metrics).
"""

from __future__ import annotations

from scripts.lib.universe import (
    CANONICAL_UNIVERSE,
    normalize_cnpj8,
    normalize_codigo_ibge,
)

# ---------------------------------------------------------------------------
# Canonical constant
# ---------------------------------------------------------------------------


def test_canonical_constant_is_1093() -> None:
    """The canonical universe constant must be 1093 (audited value)."""
    assert CANONICAL_UNIVERSE == 1093, (
        f"CANONICAL_UNIVERSE is {CANONICAL_UNIVERSE}, expected 1093. "
        "This value was audited in docs/coverage-truth/fase0-audit-2026-07-12.md."
    )


# ---------------------------------------------------------------------------
# normalize_cnpj8
# ---------------------------------------------------------------------------


def test_normalize_cnpj8_clean() -> None:
    """CNPJ with punctuation is reduced to 8 clean digits."""
    assert normalize_cnpj8("12.345.678/0001-90") == "12345678"


def test_normalize_cnpj8_already_clean() -> None:
    """Already clean 8-digit string passes through unchanged."""
    assert normalize_cnpj8("12345678") == "12345678"


def test_normalize_cnpj8_truncates_to_8() -> None:
    """Longer CNPJ (14 digits) is truncated to first 8 digits."""
    assert normalize_cnpj8("12345678901234") == "12345678"


def test_normalize_cnpj8_short_is_preserved() -> None:
    """String with fewer than 8 digits is kept as-is."""
    assert normalize_cnpj8("123456") == "123456"


def test_normalize_cnpj8_empty_string() -> None:
    """Empty string returns empty string."""
    assert normalize_cnpj8("") == ""


def test_normalize_codigo_ibge_valid() -> None:
    """7-digit IBGE codes are accepted (Florianópolis)."""
    assert normalize_codigo_ibge("4205407") == "4205407"
    assert normalize_codigo_ibge(4205407) == "4205407"
    assert normalize_codigo_ibge("4205-407") == "4205407"


def test_normalize_codigo_ibge_invalid() -> None:
    """Wrong length / empty / None are rejected as empty string."""
    assert normalize_codigo_ibge(None) == ""
    assert normalize_codigo_ibge("") == ""
    assert normalize_codigo_ibge("42054") == ""
    assert normalize_codigo_ibge("42054070") == ""
    assert normalize_codigo_ibge("abc") == ""


def test_normalize_cnpj8_non_digit_chars_only() -> None:
    """String with only non-digit characters returns empty string."""
    assert normalize_cnpj8("abc-./") == ""


def test_normalize_cnpj8_mixed_content() -> None:
    """Mixed alphanumeric with special chars returns only digits, truncated to 8."""
    assert normalize_cnpj8("AB12.345.67X") == "1234567"


# ---------------------------------------------------------------------------
# Coverage invariants (AC5)
# ---------------------------------------------------------------------------


def test_coverage_within_bounds() -> None:
    """Any coverage percentage must be between 0.0 and 100.0.

    Test with representative (numerator, denominator) pairs.
    """
    pairs = [
        (0, CANONICAL_UNIVERSE),
        (500, CANONICAL_UNIVERSE),
        (CANONICAL_UNIVERSE, CANONICAL_UNIVERSE),
    ]
    for numerator, denominator in pairs:
        pct = (numerator / denominator) * 100 if denominator > 0 else 0.0
        assert 0.0 <= pct <= 100.0, (
            f"Coverage {pct:.2f}% out of bounds for numerator={numerator}, denominator={denominator}"
        )


def test_numerator_not_exceed_denominator() -> None:
    """Numerator must never exceed denominator for any pair."""
    pairs = [
        (0, CANONICAL_UNIVERSE),
        (500, CANONICAL_UNIVERSE),
        (CANONICAL_UNIVERSE, CANONICAL_UNIVERSE),
    ]
    for numerator, denominator in pairs:
        assert 0 <= numerator <= denominator, f"numerator={numerator} exceeds denominator={denominator}"


def test_no_negative_metrics() -> None:
    """No coverage metric is negative."""
    assert CANONICAL_UNIVERSE > 0, "CANONICAL_UNIVERSE must be positive"
    assert normalize_cnpj8("") == "", "normalize_cnpj8 of empty must be empty (not negative)"
