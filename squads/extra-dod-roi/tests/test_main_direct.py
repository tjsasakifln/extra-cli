"""Tests for main-direct integration mode (no PR, writer lock on main)."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "squads" / "extra-dod-roi" / "scripts"
SQUAD = ROOT / "squads" / "extra-dod-roi"


class MainDirectModeTests(unittest.TestCase):
    def test_integration_mode_is_main_direct(self):
        sys.path.insert(0, str(SCRIPTS))
        from integration_mode import is_main_direct, load_integration_mode

        cfg = load_integration_mode()
        self.assertEqual(cfg.get("mode"), "main-direct")
        self.assertTrue(is_main_direct())

    def test_writer_lock_acquire_status_release(self):
        with tempfile.TemporaryDirectory() as td:
            squad = Path(td)
            (squad / "state" / "locks").mkdir(parents=True)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "main_writer_lock.py"),
                    "acquire",
                    "--squad",
                    str(squad),
                    "--agent",
                    "delivery-engineer",
                    "--task",
                    "test-task",
                    "--files",
                    "a.py,b.py",
                    "--head",
                    "abc123",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            st = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "main_writer_lock.py"),
                    "status",
                    "--squad",
                    str(squad),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            data = json.loads(st.stdout)
            self.assertTrue(data.get("held"))
            self.assertEqual(data["lock"]["agent"], "delivery-engineer")
            self.assertEqual(data["lock"]["task"], "test-task")
            self.assertIn("intended_files", data["lock"])
            # second acquire without force fails
            proc2 = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "main_writer_lock.py"),
                    "acquire",
                    "--squad",
                    str(squad),
                    "--agent",
                    "other",
                    "--task",
                    "other-task",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc2.returncode, 1)
            self.assertIn("LOCK_HELD", proc2.stdout)
            # release
            rel = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "main_writer_lock.py"),
                    "release",
                    "--squad",
                    str(squad),
                    "--force",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(rel.returncode, 0, rel.stdout + rel.stderr)
            st2 = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "main_writer_lock.py"),
                    "status",
                    "--squad",
                    str(squad),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertFalse(json.loads(st2.stdout).get("held"))

    def test_enforce_implement_on_main_requires_writer_lock(self):
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(ROOT), text=True
        ).strip()
        if branch != "main":
            self.skipTest("main-direct implement gate tested on main only")
        lock = SQUAD / "state" / "locks" / "main-writer.lock"
        if lock.exists():
            lock.unlink()
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "enforce_aiox_path.py"), "implement"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        data = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(data.get("abort_code"), "WRITER_LOCK_REQUIRED")

    def test_config_yaml_present(self):
        p = SQUAD / "config" / "integration-mode.yaml"
        self.assertTrue(p.is_file())
        text = p.read_text(encoding="utf-8")
        self.assertIn("main-direct", text)
        self.assertIn("writer_lock_path", text)


if __name__ == "__main__":
    unittest.main()
