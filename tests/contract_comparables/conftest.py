"""Shared helpers for inbound comparables tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.contract_comparables.corpus import case_records, case_request, load_corpus
from scripts.contract_comparables.engine import build_document, build_peer_group

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
CORPUS_PATH = FIXTURE_DIR / "golden_corpus.json"


@pytest.fixture(scope="session")
def corpus() -> dict[str, Any]:
    return load_corpus(CORPUS_PATH)


def document_for(corpus: dict[str, Any], case_id: str) -> dict[str, Any]:
    return build_document(case_records(corpus, case_id), case_request(corpus, case_id))


def result_for(corpus: dict[str, Any], case_id: str):
    return build_peer_group(case_records(corpus, case_id), case_request(corpus, case_id))


def dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
