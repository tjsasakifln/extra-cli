#!/usr/bin/env python3
"""Structural + content tests for cand-full-suite-schema-debt evidence pack.

Drives real on-disk artifacts (MANIFEST, CI workflow, critical-path exit)
— does not invent coverage or claim full-suite green.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACK = ROOT / "docs" / "ops" / "session-2026-07-17-full-suite-debt"
CI = ROOT / ".github" / "workflows" / "ci.yml"
MAKEFILE = ROOT / "Makefile"


class FullSuiteDebtManifest(unittest.TestCase):
    def test_manifest_exists_with_required_sections(self) -> None:
        path = PACK / "MANIFEST.md"
        self.assertTrue(path.is_file(), f"missing {path}")
        text = path.read_text(encoding="utf-8")
        for needle in (
            "Critical path",
            "Skips on critical path",
            "workflow_dispatch",
            "NOT claim",
            "AC1",
            "AC2",
            "CRITICAL_EXIT",
            "load_target_universe",
        ):
            self.assertIn(needle, text, f"MANIFEST missing section/token: {needle}")
        # Must not claim READY seals
        self.assertNotRegex(
            text,
            r"(?i)claim[^\n]{0,80}LOCAL_RESILIENCE_READY\s*=\s*READY",
        )
        self.assertIn("Do NOT claim", text)

    def test_critical_path_exit_artifact_is_zero(self) -> None:
        exit_path = PACK / "01-critical-readiness.exit"
        self.assertTrue(exit_path.is_file(), exit_path)
        raw = exit_path.read_text(encoding="utf-8").strip()
        self.assertRegex(raw, r"CRITICAL_EXIT=0", msg=raw)

    def test_critical_readiness_log_reports_passed_and_skips(self) -> None:
        log = PACK / "01-critical-readiness.txt"
        self.assertTrue(log.is_file(), log)
        text = log.read_text(encoding="utf-8")
        self.assertRegex(text, r"\d+ passed")
        # Skips may be 0 in some envs, but if present must be visible as skipped
        if "skipped" in text:
            self.assertRegex(text, r"\d+ skipped")

    def test_ci_test_all_is_workflow_dispatch_only_not_hidden(self) -> None:
        self.assertTrue(CI.is_file(), CI)
        ci = CI.read_text(encoding="utf-8")
        # Job exists
        self.assertIn("test-all:", ci)
        self.assertIn("Test All (full suite)", ci)
        # Gated — not silent skip of a required PR job
        self.assertIn("workflow_dispatch", ci)
        # Locate the test-all job and require workflow_dispatch gate in that job block
        m = re.search(r"(?m)^  test-all:\s*$", ci)
        self.assertIsNotNone(m, "test-all job key missing")
        # Next job starts at same indent (2 spaces) with a key; take a window
        start = m.start()
        next_job = re.search(r"(?m)^  [a-zA-Z0-9_-]+:\s*$", ci[start + 1 :])
        end = start + 1 + next_job.start() if next_job else start + 1200
        block = ci[start:end]
        self.assertIn("workflow_dispatch", block)
        self.assertRegex(
            block,
            r"if:\s*github\.event_name\s*==\s*['\"]workflow_dispatch['\"]",
        )
        # Fail-closed: no continue-on-error on the job definition vicinity
        self.assertNotIn("continue-on-error: true", block)
        self.assertNotIn("|| true", block)

    def test_makefile_exposes_test_and_test_all(self) -> None:
        text = MAKEFILE.read_text(encoding="utf-8")
        self.assertIn(".PHONY: test", text)
        self.assertIn(".PHONY: test-all", text)
        self.assertIn("not slow", text)
        self.assertIn("resilient-smoke", text)

    def test_pack_contains_ci_snippet_matching_gate(self) -> None:
        snippet = PACK / "ci-test-all-snippet.yml"
        self.assertTrue(snippet.is_file(), snippet)
        s = snippet.read_text(encoding="utf-8")
        self.assertIn("test-all:", s)
        self.assertIn("workflow_dispatch", s)

    def test_skip_reasons_file_lists_known_debts(self) -> None:
        # Prefer refreshed summary if present; else accept skip-reasons capture
        for name in ("02-critical-skip-reasons.txt", "01-critical-readiness.txt"):
            p = PACK / name
            if not p.is_file():
                continue
            text = p.read_text(encoding="utf-8")
            if "SKIPPED" in text or "skipped" in text or "load_target_universe" in text:
                # At least one documented skip debt token when skips exist
                self.assertTrue(
                    "load_target_universe" in text
                    or "datalake" in text.lower()
                    or re.search(r"\d+ skipped", text),
                    f"expected skip honesty in {name}",
                )
                return
        self.fail("no skip/readiness artifact found for honesty check")


if __name__ == "__main__":
    unittest.main()
