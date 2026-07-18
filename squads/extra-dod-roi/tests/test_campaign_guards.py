#!/usr/bin/env python3
"""Campaign guards: no fictitious meta, no self-QA, no premature DoD count."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "squads" / "extra-dod-roi" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from campaign import (  # noqa: E402
    ensure_baseline,
    reconstruct_accepted_from_diff,
    register_acceptance,
    validate_evidence_quality,
    validate_guards,
    parse_items,
)
from dod_ids import stable_dod_id  # noqa: E402
from generate_candidates import generate_dynamic_candidates  # noqa: E402
from parse_dod import parse_dod  # noqa: E402


class DodIds(unittest.TestCase):
    def test_stable_id_independent_of_line(self) -> None:
        a = stable_dod_id("13.1 Testes", "Normalização de IBGE.")
        b = stable_dod_id("13.1 Testes", "Normalização de IBGE.")
        c = stable_dod_id("13.1 Testes", "Normalização de CNPJ.")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertTrue(a.startswith("dod:"))


class DynamicCandidates(unittest.TestCase):
    def test_generates_from_open_items(self) -> None:
        matrix = parse_dod(ROOT / "DOD.md")
        cands, blocked = generate_dynamic_candidates(matrix, root=ROOT, max_slices=10)
        self.assertGreater(len(cands), 0)
        for c in cands:
            self.assertEqual(c["status"], "UNLOCKED")
            self.assertTrue(c["id"].startswith("cand-dyn-"))
            self.assertTrue(c.get("dod_item_ids"))


class CampaignGuards(unittest.TestCase):
    def test_evidence_quality_rejects_code_only_pass(self) -> None:
        with self.assertRaises(ValueError):
            validate_evidence_quality(
                evidence="code exists only",
                command="",
                exit_code=0,
                qa_verdict="PASS",
            )

    def test_evidence_quality_rejects_unit_as_e2e(self) -> None:
        with self.assertRaises(ValueError):
            validate_evidence_quality(
                evidence="full e2e ponta a ponta path",
                command="pytest tests/unit/test_x.py",
                exit_code=0,
                qa_verdict="PASS",
            )

    def test_evidence_quality_accepts_real_command(self) -> None:
        validate_evidence_quality(
            evidence="docs/ops/session/MANIFEST.md",
            command="pytest tests/test_universe.py -o addopts=",
            exit_code=0,
            qa_verdict="PASS",
        )

    def test_no_count_preexisting(self) -> None:
        dod_text = (
            "# Sec\n"
            "- [x] Already done item alpha.\n"
            "- [ ] Open item beta.\n"
        )
        items = parse_items(dod_text)
        open_ids = {i["id"] for i in items if not i["checked"]}
        done_ids = {i["id"] for i in items if i["checked"]}
        # after flip of beta
        dod2 = (
            "# Sec\n"
            "- [x] Already done item alpha.\n"
            "- [x] Open item beta.\n"
        )
        items2 = parse_items(dod2)
        live = reconstruct_accepted_from_diff(open_ids, items2)
        self.assertEqual(len(live), 1)
        self.assertEqual(live[0]["text"], "Open item beta.")
        # preexisting never in live
        for row in live:
            self.assertNotIn(row["dod_item_id"], done_ids)

    def test_no_duplicate_count(self) -> None:
        ledger = {
            "baseline": {
                "done_ids": ["dod:aaa"],
                "open_ids": ["dod:bbb", "dod:ccc"],
            },
            "accepted": [
                {"dod_item_id": "dod:bbb"},
                {"dod_item_id": "dod:bbb"},
            ],
            "matrix": [],
            "target_dod_items": 50,
            "status": "IN_PROGRESS",
        }
        errs = validate_guards(ledger, [])
        self.assertTrue(any("duplicate" in e for e in errs))

    def test_self_qa_forbidden(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # minimal repo shape
            (root / "DOD.md").write_text(
                "# S\n- [ ] Open item one.\n- [x] Open item one.\n",
                encoding="utf-8",
            )
            # broken on purpose: same text can't be both; use proper file
            (root / "DOD.md").write_text("# S\n- [x] Open item one.\n", encoding="utf-8")
            # build ledger manually with open baseline
            from campaign import save_ledger, utcnow

            items = parse_items("# S\n- [ ] Open item one.\n")
            open_id = items[0]["id"]
            # current file has it checked
            (root / "DOD.md").write_text("# S\n- [x] Open item one.\n", encoding="utf-8")
            ledger = {
                "version": "1.0.0",
                "campaign_id": "dod-50-current",
                "target_dod_items": 50,
                "baseline": {
                    "done_ids": [],
                    "open_ids": [open_id],
                },
                "accepted": [],
                "matrix": [],
                "counts": {"accepted": 0},
                "status": "IN_PROGRESS",
            }
            camp = root / "squads" / "extra-dod-roi" / "state" / "campaigns"
            camp.mkdir(parents=True)
            (camp / "dod-50-current.json").write_text(
                json.dumps(ledger), encoding="utf-8"
            )
            with self.assertRaises(ValueError) as ctx:
                register_acceptance(
                    root,
                    dod_item_ids=[open_id],
                    story_id="S1",
                    commit="abc",
                    evidence="e",
                    command="pytest",
                    exit_code=0,
                    qa_verdict="PASS",
                    qa_agent="dev-agent",
                    implementer="dev-agent",
                    candidate_id="c1",
                    roi=1.0,
                )
            self.assertIn("SELF_QA", str(ctx.exception))

    def test_premature_dod_refused(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "DOD.md").write_text("# S\n- [ ] Still open item.\n", encoding="utf-8")
            items = parse_items((root / "DOD.md").read_text(encoding="utf-8"))
            open_id = items[0]["id"]
            camp = root / "squads" / "extra-dod-roi" / "state" / "campaigns"
            camp.mkdir(parents=True)
            ledger = {
                "version": "1.0.0",
                "campaign_id": "dod-50-current",
                "target_dod_items": 50,
                "baseline": {"done_ids": [], "open_ids": [open_id]},
                "accepted": [],
                "matrix": [],
                "counts": {"accepted": 0},
                "status": "IN_PROGRESS",
            }
            (camp / "dod-50-current.json").write_text(json.dumps(ledger), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                register_acceptance(
                    root,
                    dod_item_ids=[open_id],
                    story_id="S1",
                    commit="abc",
                    evidence="e",
                    command="pytest",
                    exit_code=0,
                    qa_verdict="PASS",
                    qa_agent="qa-agent",
                    implementer="dev-agent",
                    candidate_id="c1",
                    roi=1.0,
                )
            self.assertIn("does not have [x]", str(ctx.exception))

    def test_success_requires_target(self) -> None:
        ledger = {
            "baseline": {"done_ids": [], "open_ids": ["dod:x"]},
            "accepted": [{"dod_item_id": "dod:x"}],
            "matrix": [
                {
                    "dod_item_id": "dod:x",
                    "estado_baseline": "[ ]",
                    "estado_final": "[x]",
                    "qa_verdict": "PASS",
                }
            ],
            "target_dod_items": 50,
            "status": "SUCCESS",
        }
        errs = validate_guards(ledger, [])
        self.assertTrue(any("SUCCESS declared" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
