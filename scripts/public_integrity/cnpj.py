"""CNPJ normalize + check-digit validation. Invalid is never a confirmed miss."""

from __future__ import annotations

import re

_NON_DIGIT = re.compile(r"\D")
_WEIGHTS_1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_WEIGHTS_2 = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)


def digits_only(value: str | None) -> str:
    return _NON_DIGIT.sub("", str(value or ""))


def _check_digit(nums: str, weights: tuple[int, ...]) -> int:
    total = sum(int(num) * weight for num, weight in zip(nums, weights, strict=True))
    remainder = total % 11
    return 0 if remainder < 2 else 11 - remainder


def is_valid_cnpj(value: str | None) -> bool:
    digits = digits_only(value)
    if len(digits) != 14 or digits == digits[0] * 14:
        return False
    return _check_digit(digits[:12], _WEIGHTS_1) == int(digits[12]) and _check_digit(digits[:13], _WEIGHTS_2) == int(
        digits[13]
    )


def normalize_cnpj(value: str | None) -> str | None:
    """Return 14 digits when valid; otherwise None. Does not invent a miss."""
    digits = digits_only(value)
    if not is_valid_cnpj(digits):
        return None
    return digits


def compose_valid_cnpj(stem12: str) -> str:
    """Build a check-digit-valid CNPJ from 12 stem digits (tests / fixtures)."""
    digits = digits_only(stem12)
    if len(digits) != 12 or not digits.isdigit():
        raise ValueError("cnpj_stem_must_be_12_digits")
    first = str(_check_digit(digits, _WEIGHTS_1))
    second = str(_check_digit(digits + first, _WEIGHTS_2))
    composed = digits + first + second
    if not is_valid_cnpj(composed):
        raise ValueError("cnpj_compose_failed")
    return composed
