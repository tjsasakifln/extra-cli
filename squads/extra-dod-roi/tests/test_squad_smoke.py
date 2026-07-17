#!/usr/bin/env python3
"""Smoke tests for extra-dod-roi deterministic scripts."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # repo root (squads/extra-dod-roi/tests -> +3)
SQUAD = Path(__file__).resolve().parents[1]
SCRIPTS = SQUAD / "scripts"


class SquadSmoke(unittest.TestCase):
    def test_manifest_exists(self):
        yml = SQUAD / "squad.yaml"
        self.assertTrue(yml.is_file())
        text = yml.read_text(encoding="utf-8")
        self.assertIn("name: extra-dod-roi", text)
        self.assertIn("slashPrefix: extra-roi", text)
        self.assertIn("UNLICENSED", text)
        self.assertIn("5.3.0", text)

    def test_required_agents_tasks(self):
        for a in [
            "roi-orchestrator.md",
            "codebase-cartographer.md",
            "dod-truth-auditor.md",
            "critical-path-roi-planner.md",
            "delivery-engineer.md",
            "adversarial-qa-auditor.md",
            "evidence-release-steward.md",
        ]:
            self.assertTrue((SQUAD / "agents" / a).is_file(), a)
        for t in [
            "codebase-cartographer-snapshot-project-state.md",
            "dod-truth-auditor-reconcile-dod-truth.md",
            "critical-path-roi-planner-build-dependency-graph.md",
            "critical-path-roi-planner-generate-candidate-work.md",
            "critical-path-roi-planner-rank-unlocked-work-by-roi.md",
            "critical-path-roi-planner-materialize-execution-card.md",
            "delivery-engineer-implement-selected-slice.md",
            "adversarial-qa-auditor-run-adversarial-verification.md",
            "evidence-release-steward-publish-evidence-and-handoff.md",
            "roi-orchestrator-run-evergreen-roi-cycle.md",
            "critical-path-roi-planner-explain-next-best-action.md",
        ]:
            self.assertTrue((SQUAD / "tasks" / t).is_file(), t)
        self.assertTrue((SQUAD / "workflows" / "evergreen-roi-cycle.yaml").is_file())

    def test_score_roi(self):
        payload = {
            "candidates": [
                {
                    "id": "a",
                    "title": "A",
                    "status": "UNLOCKED",
                    "value": {
                        "gate_value": 5,
                        "unlock_power": 4,
                        "operational_impact": 3,
                        "risk_reduction": 5,
                        "evidence_gain": 4,
                    },
                    "cost": {
                        "effort": 2,
                        "uncertainty": 2,
                        "external_dependency": 1,
                        "change_surface": 2,
                    },
                },
                {
                    "id": "b",
                    "title": "B",
                    "status": "UNLOCKED",
                    "value": {
                        "gate_value": 1,
                        "unlock_power": 1,
                        "operational_impact": 1,
                        "risk_reduction": 1,
                        "evidence_gain": 1,
                    },
                    "cost": {
                        "effort": 5,
                        "uncertainty": 5,
                        "external_dependency": 5,
                        "change_surface": 5,
                    },
                },
            ]
        }
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "score_roi.py"), "--input", "-", "--weights", str(SQUAD / "data" / "roi-weights.yaml")],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=str(ROOT),
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["candidates"][0]["id"], "a")
        self.assertGreater(data["candidates"][0]["roi"], data["candidates"][1]["roi"])

    def test_parse_dod_summary(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "parse_dod.py"), "--summary-only"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertGreater(data["item_count"], 10)
        self.assertIn("dod_sha256", data)

    def test_snapshot_and_rank(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "rank_next_cli.py"), "--top", "5", "--json"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["mode"], "read-only")
        self.assertGreaterEqual(len(data["ranking"]), 1)
        self.assertIn("selected_id", data)
        self.assertTrue(data["selected_id"])

    def test_no_absolute_paths_in_manifest_components(self):
        text = (SQUAD / "squad.yaml").read_text(encoding="utf-8")
        self.assertNotRegex(text, r"/mnt/|/home/|[A-Z]:\\")



class FoolproofEnforcement(unittest.TestCase):
    def test_policy_and_binding_exist(self):
        self.assertTrue((SQUAD / "data" / "enforcement-policy.yaml").is_file())
        self.assertTrue((SQUAD / "data" / "aiox-binding.yaml").is_file())
        self.assertTrue((SQUAD / "docs" / "FOOLPROOF.md").is_file())
        self.assertTrue((SQUAD / "scripts" / "force_next.py").is_file())
        self.assertTrue((SQUAD / "scripts" / "enforce_aiox_path.py").is_file())

    def test_implement_blocked_without_ready_cycle(self):
        # Without a Ready story, implement gate must fail closed
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "enforce_aiox_path.py"), "implement"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        # May be MAIN_WRITE if on main, or SKIP_PHASE / NO_STORY / PO_NOT_READY
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        self.assertFalse(data.get("ok", True))
        self.assertIn(
            data.get("abort_code"),
            {
                "MAIN_WRITE",
                "SKIP_PHASE",
                "NO_STORY",
                "PO_NOT_READY",
                "MISSING_ARTIFACT",
                "WRONG_CANDIDATE",
                "STALE_RANK",
            },
        )

    def test_cycle_illegal_transition_aborts(self):
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "cycle_state.py"),
                "init",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc2 = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "cycle_state.py"),
                "advance",
                "--to",
                "IMPLEMENTING",
                "--actor",
                "test",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(proc2.returncode, 0)


if __name__ == "__main__":
    unittest.main()
