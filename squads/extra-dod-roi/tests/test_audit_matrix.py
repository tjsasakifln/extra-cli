#!/usr/bin/env python3
"""Tests for campaign audit-matrix falsifiers and surface consistency gates."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "squads" / "extra-dod-roi" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from audit_matrix import (  # noqa: E402
    _surface_consistency_failures,
    audit_matrix,
    falsify_score_not_probability,
    falsify_theater_evidence,
    falsify_url_centralization,
    falsify_win_rate,
)
from canonical_count import (  # noqa: E402
    assert_surfaces_consistent,
    is_generic_command,
    is_theater_evidence,
    rebuild_canonical_set,
)
from dod_ids import normalize_text, stable_dod_id  # noqa: E402


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

    def test_generic_command_detection(self) -> None:
        self.assertTrue(is_generic_command("batch2 adversarial"))
        self.assertTrue(is_generic_command("batch4 file+code verification"))
        self.assertTrue(is_generic_command("path exists / content scan"))
        self.assertTrue(is_generic_command("ops --help suite"))
        self.assertTrue(is_generic_command(""))
        self.assertFalse(
            is_generic_command(
                "pytest tests/test_value_semantics.py tests/test_universe.py -o addopts="
            )
        )

    def test_theater_evidence_detection(self) -> None:
        self.assertTrue(is_theater_evidence("file inventory session batch2"))
        self.assertTrue(is_theater_evidence("docs/ops/... + QA PASS"))
        self.assertFalse(is_theater_evidence("scripts/lib/value_semantics.py"))

    def test_theater_falsifier_rejects_generic_ledger_command(self) -> None:
        row = {
            "dod_item_id": "dod:test-gen",
            "texto": "README descreve fontes.",
            "evidência": "docs/ops/session-2026-07-18-campaign-batch2/ + QA PASS",
            "comando": "batch2 adversarial",
            "exit_code": 0,
            "qa_verdict": "PASS",
            "evidence_type": "DOCUMENT_CONTENT_PROOF",
        }
        r = falsify_theater_evidence(ROOT, row)
        self.assertFalse(r.ok)

    def test_theater_falsifier_rejects_file_inventory_proof(self) -> None:
        row = {
            "dod_item_id": "dod:test-inv",
            "texto": "Existe runbook local.",
            "evidência": "file inventory session batch2",
            "comando": "path exists / content scan",
            "exit_code": 0,
            "qa_verdict": "PASS",
        }
        r = falsify_theater_evidence(ROOT, row)
        self.assertFalse(r.ok)

    def test_theater_falsifier_rejects_backup_without_executed_proof(self) -> None:
        row = {
            "dod_item_id": "dod:test-bk",
            "texto": "O arquivo de backup possui integridade verificada.",
            "evidência": "gzip -t in backup script",
            "comando": "ops --help suite",
            "exit_code": 0,
            "qa_verdict": "PASS",
            "evidence_type": "EXECUTED_PROOF",
        }
        r = falsify_theater_evidence(ROOT, row)
        self.assertFalse(r.ok)

    def test_exit_code_zero_without_reproducible_command(self) -> None:
        row = {
            "dod_item_id": "dod:test-ex",
            "texto": "Some claim.",
            "evidência": "something",
            "comando": "batch2 adversarial",
            "exit_code": 0,
            "qa_verdict": "PASS",
        }
        r = falsify_theater_evidence(ROOT, row)
        self.assertFalse(r.ok)

    def test_surface_count_divergence_detected(self) -> None:
        errs = assert_surfaces_consistent(
            canonical_count=53,
            report_count=53,
            qa_pass_count=56,
            panel_count=51,
        )
        self.assertTrue(errs)
        self.assertIn("diverge", errs[0])

    def test_surface_equal_ok(self) -> None:
        errs = assert_surfaces_consistent(
            canonical_count=50,
            report_count=50,
            qa_pass_count=50,
            panel_count=50,
            story_breakdown_sum=50,
        )
        self.assertEqual(errs, [])

    def test_story_breakdown_mismatch(self) -> None:
        errs = assert_surfaces_consistent(
            canonical_count=50,
            story_breakdown_sum=48,
        )
        self.assertTrue(errs)

    def test_duplicate_stable_id_in_matrix_fails_surface(self) -> None:
        ledger = {
            "matrix": [
                {"dod_item_id": "dod:a", "qa_verdict": "PASS", "story_id": "s1", "texto": "x"},
                {"dod_item_id": "dod:a", "qa_verdict": "PASS", "story_id": "s1", "texto": "x"},
            ],
            "accepted": [
                {"dod_item_id": "dod:a"},
                {"dod_item_id": "dod:a"},
            ],
            "counts": {"accepted": 2},
            "final_panel": {"Aceitos_PASS": 2},
            "baseline": {"open_ids": ["dod:a"]},
        }
        fails = _surface_consistency_failures(ROOT, ledger)
        probes = {f.get("probe") for f in fails}
        self.assertIn("unique_ids", probes)

    def test_panel_vs_counts_divergence(self) -> None:
        ledger = {
            "matrix": [{"dod_item_id": "dod:a", "qa_verdict": "PASS", "story_id": "s", "texto": "t"}],
            "accepted": [{"dod_item_id": "dod:a"}],
            "counts": {"accepted": 51},
            "final_panel": {"Aceitos_PASS": 53},
            "baseline": {"open_ids": ["dod:a"]},
        }
        fails = _surface_consistency_failures(ROOT, ledger)
        self.assertTrue(any("panel" in (f.get("reason") or "") or f.get("probe") == "panel_vs_counts" for f in fails))

    def test_batch4_revoked_in_qa_detected(self) -> None:
        """If batch4 QA still has revoked claims, surface check fails (live file may already be clean)."""
        # Unit-level: simulate via temporary override is heavy; assert current clean file has none
        qa4 = ROOT / "squads/extra-dod-roi/state/qa/cyc-2026-07-18-batch4-qa.json"
        if qa4.is_file():
            data = json.loads(qa4.read_text(encoding="utf-8"))
            texts = [normalize_text(i.get("text") or "") for i in data.get("items") or []]
            revoked = {
                normalize_text("URLs de fontes são centralizadas."),
                normalize_text("Win rate não é calculado sem propostas enviadas."),
                normalize_text("Score não é chamado de probabilidade sem calibração."),
            }
            self.assertTrue(revoked.isdisjoint(set(texts)))
            self.assertEqual(len(texts), len(set(texts)), "batch4 QA duplicates")

    def test_evidence_suffix_does_not_change_stable_id(self) -> None:
        s = "31. Documentação operacional"
        a = stable_dod_id(s, "README descreve fontes.")
        b = stable_dod_id(s, "README descreve fontes. Evidência: batch2 foo")
        self.assertEqual(a, b)

    def test_audit_matrix_readonly_clean_or_reports(self) -> None:
        result = audit_matrix(ROOT, write=False)
        self.assertIn("matrix_count", result)
        self.assertIn("exit", result)
        self.assertEqual(result["exit"], 0, result.get("remaining_failures") or result.get("failures"))
        self.assertGreaterEqual(result["matrix_count"], 50)
        self.assertTrue(result.get("consistency_ok"))

    def test_canonical_count_matches_ledger(self) -> None:
        result = rebuild_canonical_set(ROOT, require_final_head_review=True)
        ledger = json.loads(
            (ROOT / "squads/extra-dod-roi/state/campaigns/dod-50-current.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(result["counts"]["accepted"], ledger["counts"]["accepted"])
        self.assertEqual(result["counts"]["accepted"], len(ledger["matrix"]))
        self.assertEqual(
            result["counts"]["accepted"], ledger["final_panel"]["Aceitos_PASS"]
        )
        self.assertEqual(len(result.get("rejected") or []), 0)

    def test_no_generic_commands_in_live_matrix(self) -> None:
        ledger = json.loads(
            (ROOT / "squads/extra-dod-roi/state/campaigns/dod-50-current.json").read_text(
                encoding="utf-8"
            )
        )
        for row in ledger.get("matrix") or []:
            cmd = row.get("comando") or ""
            self.assertFalse(
                is_generic_command(cmd),
                f"generic command on {row.get('dod_item_id')}: {cmd}",
            )
            self.assertFalse(
                is_theater_evidence(row.get("evidência") or ""),
                f"theater evidence on {row.get('dod_item_id')}",
            )

    def test_report_qa_panel_same_count(self) -> None:
        ledger = json.loads(
            (ROOT / "squads/extra-dod-roi/state/campaigns/dod-50-current.json").read_text(
                encoding="utf-8"
            )
        )
        n = ledger["counts"]["accepted"]
        report = (ROOT / "squads/extra-dod-roi/state/campaigns/dod-50-final-report.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(f"**PASS matrix (canonical):** {n}", report)
        qa = json.loads(
            (
                ROOT
                / "squads/extra-dod-roi/state/qa/cyc-2026-07-18-campaign-final-audit.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(qa["pass_matrix_count"], n)
        self.assertEqual(ledger["final_panel"]["Aceitos_PASS"], n)

    def test_matrix_subset_of_baseline_open(self) -> None:
        ledger = json.loads(
            (ROOT / "squads/extra-dod-roi/state/campaigns/dod-50-current.json").read_text(
                encoding="utf-8"
            )
        )
        baseline_open = set((ledger.get("baseline") or {}).get("open_ids") or [])
        for row in ledger.get("matrix") or []:
            self.assertIn(row["dod_item_id"], baseline_open)

    def test_no_revoked_in_accepted(self) -> None:
        ledger = json.loads(
            (ROOT / "squads/extra-dod-roi/state/campaigns/dod-50-current.json").read_text(
                encoding="utf-8"
            )
        )
        revoked = {
            normalize_text(x)
            for x in (
                "URLs de fontes são centralizadas.",
                "Win rate não é calculado sem propostas enviadas.",
                "Score não é chamado de probabilidade sem calibração.",
                "Scripts destrutivos exigem confirmação ou flag explícita.",
            )
        }
        for row in ledger.get("matrix") or []:
            self.assertNotIn(normalize_text(row.get("texto") or ""), revoked)


if __name__ == "__main__":
    unittest.main()
