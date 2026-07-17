"""Fail-closed checks: pilot evidence JSON vs ledger docs (NEXT-30D / K3.2).

Detects doc/artifact divergence on pilot 90d status and 3y go/no-go.
Does not invent pilot metrics; only asserts key facts are present.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PILOT_JSON = ROOT / "output" / "contracts" / "pilot-90d-next30d.json"
SCORECARD = ROOT / "docs" / "ops" / "ledger" / "NEXT-30D-FINAL-SCORECARD.md"

TERMINAL_STATUSES = frozenset({"partial", "failed", "success"})


def _load_pilot() -> dict:
    assert PILOT_JSON.is_file(), f"pilot artifact missing: {PILOT_JSON}"
    return json.loads(PILOT_JSON.read_text(encoding="utf-8"))


def test_pilot_status_is_terminal():
    data = _load_pilot()
    status = data.get("status")
    assert status in TERMINAL_STATUSES, f"unexpected pilot status: {status!r}"
    assert status != "running"


def test_partial_or_failed_implies_no_go_3y():
    data = _load_pilot()
    status = data.get("status")
    if status != "success":
        assert data.get("go_no_go_3y") == "NO-GO", (
            f"status={status!r} requires go_no_go_3y=NO-GO, "
            f"got {data.get('go_no_go_3y')!r}"
        )


def test_claims_forbidden_includes_full_90d_success_when_present():
    data = _load_pilot()
    forbidden = data.get("claims_forbidden")
    if forbidden is None:
        return
    assert isinstance(forbidden, list)
    blob = " ".join(str(x) for x in forbidden).lower()
    assert any(
        token in blob
        for token in (
            "full 90-day",
            "full 90d",
            "90-day national",
            "90d national",
        )
    ), f"claims_forbidden must ban full 90d success claim; got {forbidden!r}"


def test_scorecard_aligned_when_pilot_partial():
    """If pilot JSON is partial, scorecard must state partial + NO-GO near K3.2."""
    data = _load_pilot()
    if data.get("status") != "partial":
        return

    assert SCORECARD.is_file(), f"scorecard missing: {SCORECARD}"
    text = SCORECARD.read_text(encoding="utf-8")

    # Metrics row must not claim full pilot success
    assert re.search(
        r"\|\s*pilot status\s*\|[^|]*\|\s*\*\*partial",
        text,
        flags=re.IGNORECASE,
    ), "scorecard metrics must show pilot status | **partial** when artifact is partial"

    # K3.2 section / row: require partial and NO-GO nearby (same document region)
    k32_idx = text.find("K3.2")
    assert k32_idx >= 0, "scorecard must mention K3.2"
    window = text[k32_idx : k32_idx + 800]
    assert "partial" in window.lower() or "DONE_PARTIAL" in window, (
        "K3.2 region must mention partial / DONE_PARTIAL"
    )
    assert "NO-GO" in window, "K3.2 region must mention NO-GO when pilot is partial"

    # Global ban: metrics row must not say success alone for pilot status
    bad = re.search(
        r"\|\s*pilot status\s*\|[^|]*\|\s*\*\*success\*\*\s*\|",
        text,
        flags=re.IGNORECASE,
    )
    assert bad is None, (
        "misleading pattern: pilot status | success while JSON status=partial"
    )
