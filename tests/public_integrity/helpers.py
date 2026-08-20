"""Shared fixture paths and a valid CNPJ composed at runtime (no 14-digit literal)."""

from __future__ import annotations

from pathlib import Path

from scripts.public_integrity.cnpj import compose_valid_cnpj

REPO = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
STEM = "112223330001"
VALID_CNPJ = compose_valid_cnpj(STEM)
INVALID_CNPJ = STEM + "00"
CLOCK = "2026-08-01T12:00:00+00:00"
FAILURE_FIXTURES = (
    "timeout.json",
    "rate-limit-429.json",
    "http-5xx.json",
    "schema-drift.json",
    "parse-incomplete.json",
    "incomplete-pagination.json",
    "source-degraded.json",
    "stale-cache.json",
)
