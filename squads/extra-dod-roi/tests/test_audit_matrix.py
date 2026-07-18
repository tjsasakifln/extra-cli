#!/usr/bin/env python3
"""Tests for campaign audit-matrix falsifiers."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "squads" / "extra-dod-roi" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from audit_matrix import (  # noqa: E402
    falsify_score_not_probability,
    falsify_url_centralization,
    falsify_win_rate,
    audit_matrix,
)


class AuditMatrixFalsifiers(unittest.TestCase):
    def test_url_centralization_fails_on_real_repo(self) -> None:
        row = {
            "dod_item_id": "dod:test-url",
            "texto": "URLs de fontes são centralizadas.",
            "evidência": "url-centralization.txt",
            "comando": "scan",
            "exit_code": 0,
            "qa_verdict": "PASS",
        }
        r = falsify_url_centralization(ROOT, row)
        self.assertFalse(r.ok)

    def test_win_rate_fails_on_base_defaults(self) -> None:
        row = {
            "dod_item_id": "dod:test-wr",
            "texto": "Win rate não é calculado sem propostas enviadas.",
            "evidência": "scoring.py — no unguarded win_rate",
            "comando": "grep",
            "exit_code": 0,
            "qa_verdict": "PASS",
        }
        r = falsify_win_rate(ROOT, row)
        self.assertFalse(r.ok)

    def test_score_probability_fails_on_report_labels(self) -> None:
        row = {
            "dod_item_id": "dod:test-sc",
            "texto": "Score não é chamado de probabilidade sem calibração.",
            "evidência": "scoring.py",
            "comando": "grep",
            "exit_code": 0,
            "qa_verdict": "PASS",
        }
        r = falsify_score_not_probability(ROOT, row)
        self.assertFalse(r.ok)

    def test_audit_matrix_readonly_clean_or_reports(self) -> None:
        result = audit_matrix(ROOT, write=False)
        self.assertIn("matrix_count", result)
        self.assertIn("exit", result)
        # After purge, should be clean
        self.assertEqual(result["exit"], 0, result.get("remaining_failures"))
        self.assertGreaterEqual(result["matrix_count"], 50)


if __name__ == "__main__":
    unittest.main()
