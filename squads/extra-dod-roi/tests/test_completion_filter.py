#!/usr/bin/env python3
"""Tests for rank_next completion filter — skip Done ROI candidates."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "squads" / "extra-dod-roi" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from rank_next_cli import (  # noqa: E402
    apply_completion_filters,
    _story_done,
)


class CompletionFilter(unittest.TestCase):
    def test_e3_stories_done(self) -> None:
        self.assertTrue(_story_done(ROOT, "B2G-E3.S1"))
        self.assertTrue(_story_done(ROOT, "B2G-E3.S2"))

    def test_full_suite_done(self) -> None:
        self.assertTrue(_story_done(ROOT, "ROI-cand-full-suite-schema-debt"))

    def test_coverage_slice_done(self) -> None:
        self.assertTrue(_story_done(ROOT, "ROI-cand-coverage-slice-pending-collection"))

    def test_filter_removes_completed_keeps_golden_path(self) -> None:
        cands = [
            {"id": "cand-qa-po-e3-stories", "status": "UNLOCKED", "title": "e3"},
            {"id": "cand-full-suite-schema-debt", "status": "UNLOCKED", "title": "fs"},
            {"id": "cand-workspace-daily-evidence-pack", "status": "UNLOCKED", "title": "ws"},
            {"id": "cand-coverage-slice-pending-collection", "status": "UNLOCKED", "title": "cov"},
            {"id": "cand-golden-path-pncp-health", "status": "UNLOCKED", "title": "gp"},
        ]
        div: list[str] = []
        out = apply_completion_filters(ROOT, cands, div)
        ids = {c["id"] for c in out}
        self.assertNotIn("cand-qa-po-e3-stories", ids)
        self.assertNotIn("cand-full-suite-schema-debt", ids)
        self.assertNotIn("cand-workspace-daily-evidence-pack", ids)
        self.assertNotIn("cand-coverage-slice-pending-collection", ids)
        self.assertIn("cand-golden-path-pncp-health", ids)
        self.assertTrue(any("COMPLETED" in d for d in div))


if __name__ == "__main__":
    unittest.main()
