"""Load the versioned traffic-opportunity-frontier consumer contract."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

CONTRACT_RELATIVE = Path("docs/contracts/traffic-opportunity-frontier-v1.json")
REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / CONTRACT_RELATIVE


@lru_cache(maxsize=1)
def load_contract() -> dict[str, Any]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
