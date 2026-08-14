"""Fixed-seed selection of the 30 priority commercial accounts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.decision_unit_intelligence.models import normalize_cnpj

SEED = "dui-track-a-30-2026-08-14"
POLICY_VERSION = "dui.policy.v1"

# Top-30 of the 2026-08-05 national reajuste campaign (AI-assisted evidence review).
# These are the commercially prioritized accounts of that run — not a cherry-pick of emails.
TRACK_A_CNPJS: list[str] = [
    "00820854000114",
    "52639513000140",
    "01341214000194",
    "29095199000160",
    "95865044000190",
    "74111709000109",
    "82743832000162",
    "04406660000128",
    "43887548000108",
    "23773012000154",
    "03620927000112",
    "05895635000118",
    "21157133000146",
    "03574370000120",
    "03094645000129",
    "27743102000153",
    "83665141000150",
    "06145928000140",
    "03257777000124",
    "10249046000100",
    "12218083000179",
    "84689066000392",
    "05133291000100",
    "09223659000181",
    "22798043000105",
    "12535370000102",
    "01650178000140",
    "80996861000100",
    "07455659000181",
    "80095466000157",
]


def load_top30_cnpjs_from_artifact(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [normalize_cnpj(r["cnpj"]) for r in payload.get("reviews") or [] if r.get("cnpj")]


def selection_rule() -> dict[str, Any]:
    return {
        "seed": SEED,
        "n": 30,
        "rule": (
            "Take the 30 accounts of artifacts/outreach/reajuste-2026-08-05-full-datalake-pr200/"
            "ai_assisted_evidence_review_top30.json in listed order. "
            "These are the commercially prioritized construction suppliers of the 2026-08-05 "
            "national reajuste scan (highest ranking / Sul priority / document-request ready). "
            "Not selected by presence of a named email."
        ),
        "justification": (
            "The campaign already ranked these companies by contract value, maturity proxy "
            "and construction-object fit. Decision-Unit Reachability must be proven on the "
            "same commercial front of the line, including accounts that only have QSA + "
            "company switchboard."
        ),
        "source_run": "reajuste_14133-2026-08-05-56dc6c48",
        "policy_version": POLICY_VERSION,
    }


def build_manifest(cnpjs: list[str] | None = None) -> dict[str, Any]:
    ids = [normalize_cnpj(c) for c in (cnpjs or TRACK_A_CNPJS)]
    return {
        "schema_id": "confenge.dui.cohort.v1",
        "accounts": [{"cnpj": c, "rank": i + 1} for i, c in enumerate(ids)],
        "n": len(ids),
        "selection": selection_rule(),
    }
