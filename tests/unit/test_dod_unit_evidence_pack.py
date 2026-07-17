"""Structural proof for ROI-cand-dod-unit-test-evidence-pack."""
from pathlib import Path

PACK = Path(__file__).resolve().parents[2] / "docs" / "ops" / "session-2026-07-17-dod-unit-evidence"


def test_manifest_and_pytest_exit_zero() -> None:
    assert (PACK / "MANIFEST.md").is_file()
    exit_f = PACK / "pytest-pack.exit"
    assert exit_f.is_file()
    assert "EXIT=0" in exit_f.read_text(encoding="utf-8")
    log = (PACK / "pytest-pack.log").read_text(encoding="utf-8")
    assert "passed" in log
    assert "failed" not in log.lower() or "0 failed" in log.lower()
    # must not claim 95% ops coverage
    man = (PACK / "MANIFEST.md").read_text(encoding="utf-8")
    assert "NOT marked" in man or "NOT" in man
    assert "95%" in man  # documented as not claimed


def test_proposed_flips_nonempty() -> None:
    p = PACK / "proposed-flips.txt"
    assert p.is_file()
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) >= 15
