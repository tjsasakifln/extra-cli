"""B1: web-cfg consumer is read-only — no apply/build, no tree mutation."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.pseo import release_snapshot, verify_web_cfg_compat


def _tree_hash(root: Path) -> str:
    """Recursive content hash of all files under root (deterministic)."""
    h = hashlib.sha256()
    if not root.exists():
        h.update(b"<missing>")
        return h.hexdigest()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix().encode()
            h.update(rel)
            h.update(b"\0")
            h.update(path.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


def test_forbidden_write_flags_documented() -> None:
    assert "apply" in verify_web_cfg_compat.FORBIDDEN_WRITE_FLAGS
    assert "build" in verify_web_cfg_compat.FORBIDDEN_WRITE_FLAGS
    # release_snapshot re-exports the same set
    assert release_snapshot.FORBIDDEN_WRITE_FLAGS is verify_web_cfg_compat.FORBIDDEN_WRITE_FLAGS


def test_apply_build_flags_rejected() -> None:
    with pytest.raises(SystemExit):
        verify_web_cfg_compat.main(["--web-cfg", "/tmp", "--apply"])
    with pytest.raises(SystemExit):
        verify_web_cfg_compat.main(["--web-cfg", "/tmp", "--build"])
    with pytest.raises(SystemExit):
        verify_web_cfg_compat.main(["--web-cfg", "/tmp", "--publish"])


def test_no_apply_build_in_source() -> None:
    src = Path("scripts/pseo/verify_web_cfg_compat.py").read_text(encoding="utf-8")
    # Executable write paths must not exist (docstring may mention removed APIs)
    assert "import shutil" not in src
    assert "shutil.copytree(" not in src
    assert "subprocess.run([npm" not in src
    assert "build:site" not in src or "Removed permanently" in src
    assert "add_argument(\"--apply\"" not in src
    assert "add_argument(\"--build\"" not in src
    shim = Path("scripts/pseo/release_snapshot.py").read_text(encoding="utf-8")
    assert "DEPRECATED" in shim
    assert "apply" in shim.lower() and "removed" in shim.lower()
    assert "import shutil" not in shim
    assert "shutil.copytree" not in shim


def test_adversarial_web_cfg_tree_byte_identical(tmp_path: Path) -> None:
    """Create temp web-cfg tree, hash before, run ALL verifier options, hash after."""
    web_cfg = tmp_path / "web-cfg"
    (web_cfg / "data" / "pseo").mkdir(parents=True)
    (web_cfg / "seo").mkdir(parents=True)
    # Seed consumer snapshot
    seed = {
        "schema_version": "1.1.0",
        "dataset_hash": "a" * 64,
        "snapshot_status": "CANDIDATE",
    }
    (web_cfg / "data" / "pseo" / "manifest.json").write_text(
        json.dumps(seed, indent=2) + "\n", encoding="utf-8"
    )
    (web_cfg / "data" / "pseo" / "markets.json").write_text("[]\n", encoding="utf-8")
    (web_cfg / "data" / "pseo" / "opportunities.json").write_text("[]\n", encoding="utf-8")
    marker = web_cfg / "DO_NOT_TOUCH.txt"
    marker.write_text("consumer-owned\n", encoding="utf-8")

    before = _tree_hash(web_cfg)

    # Pre-built export dir (so we don't depend on DSN)
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    for name in (
        "manifest.json",
        "markets.json",
        "agencies.json",
        "prices.json",
        "competition.json",
        "opportunities.json",
        "problem_service.json",
        "archetypes.json",
    ):
        if name == "manifest.json":
            (export_dir / name).write_text(
                json.dumps(
                    {
                        "schema_version": "1.1.0",
                        "dataset_hash": "b" * 64,
                        "snapshot_status": "CANDIDATE",
                        "publish_status": "REVIEW_REQUIRED",
                        "indexable": False,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        else:
            (export_dir / name).write_text("[]\n", encoding="utf-8")

    notes = tmp_path / "artifacts" / "notes.json"
    rc = verify_web_cfg_compat.main(
        [
            "--web-cfg",
            str(web_cfg),
            "--export-dir",
            str(export_dir),
            "--as-of",
            "2026-07-31",
            "--out",
            str(notes),
        ]
    )
    assert rc == 0
    assert notes.is_file()
    notes_data = json.loads(notes.read_text(encoding="utf-8"))
    assert notes_data["read_only"] is True
    assert notes_data["apply"] is False
    assert notes_data["build"] is False
    # Notes must not land under web-cfg
    assert "web-cfg" not in str(notes.resolve()) or str(web_cfg) not in str(notes.resolve())

    after = _tree_hash(web_cfg)
    assert before == after, "web-cfg tree mutated by verifier"

    # Hidden/forbidden flags cannot sneak writes
    for bad in ("--apply", "--build", "--deploy", "--publish", "--promote", "--install"):
        with pytest.raises(SystemExit):
            verify_web_cfg_compat.main(
                ["--web-cfg", str(web_cfg), "--export-dir", str(export_dir), bad, "--out", str(notes)]
            )
    assert _tree_hash(web_cfg) == before

    # CLI module entry also read-only
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.pseo.verify_web_cfg_compat",
            "--web-cfg",
            str(web_cfg),
            "--export-dir",
            str(export_dir),
            "--out",
            str(tmp_path / "notes2.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert _tree_hash(web_cfg) == before

    # Default notes path must not be under web-cfg (out-notes alias suppressed to --out)
    # and must reject notes inside consumer tree
    rc_bad = verify_web_cfg_compat.main(
        [
            "--web-cfg",
            str(web_cfg),
            "--export-dir",
            str(export_dir),
            "--out",
            str(web_cfg / "seo" / "notes.json"),
        ]
    )
    assert rc_bad == 2
    assert _tree_hash(web_cfg) == before
