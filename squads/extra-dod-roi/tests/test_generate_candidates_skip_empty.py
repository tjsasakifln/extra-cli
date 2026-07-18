"""Empty DoD checkbox lines must never become ranking candidates."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from generate_candidates import generate_dynamic_candidates  # noqa: E402


def test_empty_text_items_skipped() -> None:
    matrix = {
        "items": [
            {
                "id": "dod:empty",
                "checkbox": False,
                "section": "25. Verdade, linguagem e claims permitidos",
                "text": "   ",
                "line": 1,
            },
            {
                "id": "dod:real",
                "checkbox": False,
                "section": "25. Verdade, linguagem e claims permitidos",
                "text": "Algo real.",
                "line": 2,
            },
        ]
    }
    cands, _blocked = generate_dynamic_candidates(matrix)
    ids = [i for c in cands for i in c.get("dod_item_ids") or []]
    assert "dod:empty" not in ids
    assert "dod:real" in ids
