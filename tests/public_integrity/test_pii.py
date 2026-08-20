"""Logs, public fixtures and exports never carry a full CNPJ."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from scripts.public_integrity.cli import replay_fixture
from scripts.public_integrity.redaction import install_log_redaction
from tests.public_integrity.helpers import FIXTURES, VALID_CNPJ

CNPJ_DIGITS = re.compile(r"\d{14}")
CNPJ_FORMATTED = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
PUBLIC_ROOTS = [
    Path("tests/public_integrity/fixtures"),
    Path("exports/public-integrity"),
]


def test_public_fixtures_and_exports_have_no_cnpj() -> None:
    scanned = 0
    for root in PUBLIC_ROOTS:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".json", ".md", ".sql"}:
                continue
            text = path.read_text(encoding="utf-8")
            assert CNPJ_FORMATTED.search(text) is None, path
            assert CNPJ_DIGITS.search(text) is None, path
            scanned += 1
    assert scanned >= 8


def test_logs_redact_cnpj(caplog) -> None:
    logger = install_log_redaction()
    with caplog.at_level(logging.INFO, logger=logger.name):
        payload = replay_fixture(FIXTURES / "matches.json", cnpj=VALID_CNPJ)
    assert payload["queried_cnpj"] == VALID_CNPJ
    assert CNPJ_DIGITS.search(caplog.text) is None
    assert VALID_CNPJ not in caplog.text
    assert CNPJ_FORMATTED.search(caplog.text) is None
