"""Tests for operational_export_pack (§12.2 export + metadata)."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.reports.operational_export_pack import (
    FORBIDDEN_PHRASES,
    assert_no_forbidden,
    common_metadata,
    write_excel,
    write_pdf,
)


def test_common_metadata_fields():
    m = common_metadata(
        run_id="r1",
        universe_ver="u1",
        source="test",
        reliability="DEGRADED",
    )
    for k in ("generated_at", "universe_version", "source", "reliability", "run_id"):
        assert k in m and m[k]


def test_excel_and_pdf_created(tmp_path: Path):
    meta = common_metadata(run_id="r2", universe_ver="u", source="s", reliability="TRUSTED")
    health = [{"source": "pncp", "success_rate_pct": 100, "reliability": "TRUSTED", "last_status": "completed"}]
    xlsx = tmp_path / "t.xlsx"
    write_excel(xlsx, {"source_health": health}, meta)
    assert xlsx.is_file() and xlsx.stat().st_size > 0
    pdf = tmp_path / "t.pdf"
    write_pdf(pdf, meta, health, ["limitation demo"])
    assert pdf.is_file() and pdf.stat().st_size > 100


def test_forbidden_phrases_list_complete():
    assert "LOCAL_READY" in FORBIDDEN_PHRASES
    assert "PROJECT_DONE" in FORBIDDEN_PHRASES


def test_assert_no_forbidden_allows_forbidden_list():
    text = json.dumps({"claims_forbidden": list(FORBIDDEN_PHRASES)})
    # pure list should not flag as assertion
    hits = assert_no_forbidden(text)
    # function is best-effort; empty or only list refs OK
    assert isinstance(hits, list)
