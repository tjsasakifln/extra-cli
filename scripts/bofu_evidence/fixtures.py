"""Load frozen snapshot and live-state fixtures for #435 / #437."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
SNAPSHOT_PATH = FIXTURE_DIR / "snapshot.json"
PR435_PATH = FIXTURE_DIR / "pr435_comparable.json"
PR437_PATH = FIXTURE_DIR / "pr437_national.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_snapshot(path: Path | None = None) -> dict[str, Any]:
    return load_json(path or SNAPSHOT_PATH)


def load_comparable(path: Path | None = None) -> dict[str, Any]:
    return load_json(path or PR435_PATH)


def load_national_coverage(path: Path | None = None) -> dict[str, Any]:
    return load_json(path or PR437_PATH)
