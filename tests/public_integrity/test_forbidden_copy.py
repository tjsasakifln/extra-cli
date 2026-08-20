"""Adversarial scan: no score/legal-conclusion/recommendation fields; no forbidden copy."""

from __future__ import annotations

from pathlib import Path

from scripts.public_integrity.cli import replay_fixture
from scripts.public_integrity.forbidden import scan_forbidden_copy, scan_forbidden_fields
from tests.public_integrity.helpers import FIXTURES, VALID_CNPJ

EXCLUSIVE = [
    Path("scripts/public_integrity"),
    Path("tests/public_integrity"),
    Path("exports/public-integrity"),
    Path("docs/contracts/public-read-integrity-v1.md"),
    Path("docs/contracts/public-read-integrity-v1.json"),
    Path("docs/contracts/public-read-integrity-v1.schema.json"),
]


def _iter_text_files() -> list[Path]:
    files: list[Path] = []
    for root in EXCLUSIVE:
        if root.is_file():
            files.append(root)
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".json", ".md", ".sql"}:
                files.append(path)
    return files


def test_exclusive_area_has_no_forbidden_copy_as_claim() -> None:
    # The contract lists forbidden tokens as a deny-list; skip that file's deny array.
    skip = {
        "public-read-integrity-v1.json",
        "forbidden.py",
        "test_forbidden_copy.py",
        "models.py",
    }
    hits: list[str] = []
    for path in _iter_text_files():
        if path.name in skip:
            continue
        text = path.read_text(encoding="utf-8")
        found = scan_forbidden_copy(text)
        if found:
            hits.append(f"{path}:{found}")
    assert hits == []


def test_produced_payload_has_no_score_or_recommendation_fields() -> None:
    for name in ("matches.json", "empty-complete.json", "source-degraded.json"):
        payload = replay_fixture(FIXTURES / name, cnpj=VALID_CNPJ)
        assert scan_forbidden_fields(payload) == []
        assert payload["not_legal_conclusion"] is True
        assert "score" not in payload
        assert "recommendation" not in payload
        assert scan_forbidden_copy(str(payload.get("limitations"))) == []
