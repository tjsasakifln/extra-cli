"""Load the versioned research-flagship consumer contract."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

CONTRACT_RELATIVE = Path("docs/contracts/public-read-research-flagship-v1.json")
REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / CONTRACT_RELATIVE

FORBIDDEN_TRUTH_BRANDS = ("CONFENGE", "confenge")


@lru_cache(maxsize=1)
def load_contract() -> dict[str, Any]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def query_budget() -> dict[str, Any]:
    return dict(load_contract()["query_budget"])
