"""Load the inbound golden corpus and named canary cases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.contract_comparables.models import ContractRecord, PeerRequest
from scripts.contract_comparables.normalize import records_from_mappings

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parents[1]
DEFAULT_CORPUS = REPO_ROOT / "tests" / "contract_comparables" / "fixtures" / "golden_corpus.json"

CANARY_CASES = (
    "comparable_clear",
    "regime_incompatible",
    "geo_period_inadequate",
    "insufficient_sample",
    "missing_values",
    "duplicate_rectification",
    "statistical_outlier",
)


def load_corpus(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else DEFAULT_CORPUS
    return json.loads(target.read_text(encoding="utf-8"))


def case_records(corpus: dict[str, Any], case_id: str) -> tuple[ContractRecord, ...]:
    case = corpus["cases"][case_id]
    return records_from_mappings(case["contracts"])


def case_request(corpus: dict[str, Any], case_id: str, *, producer_sha: str | None = None) -> PeerRequest:
    case = corpus["cases"][case_id]
    return PeerRequest(
        focal_contract_id=str(case["focal_id"]),
        as_of=str(case.get("as_of") or corpus["as_of"]),
        catalog_mode=str(corpus.get("catalog_mode") or "fixture"),
        source=str(corpus.get("source") or "fixture"),
        producer_sha=producer_sha,
    )


def case_expected_status(corpus: dict[str, Any], case_id: str) -> str:
    return str(corpus["cases"][case_id]["expected_status"])
