"""CNPJ validation lives in the shipped module and never confirms a miss."""

from __future__ import annotations

from scripts.public_integrity.cnpj import compose_valid_cnpj, is_valid_cnpj, normalize_cnpj
from tests.public_integrity.helpers import INVALID_CNPJ, STEM, VALID_CNPJ


def test_compose_valid_cnpj_roundtrip() -> None:
    assert is_valid_cnpj(VALID_CNPJ)
    assert normalize_cnpj(VALID_CNPJ) == VALID_CNPJ
    assert compose_valid_cnpj(STEM) == VALID_CNPJ


def test_invalid_checksum_is_not_normalized() -> None:
    assert is_valid_cnpj(INVALID_CNPJ) is False
    assert normalize_cnpj(INVALID_CNPJ) is None
    assert normalize_cnpj("0" * 14) is None
