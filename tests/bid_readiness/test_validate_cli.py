"""CLI validate re-evaluates validity with --reference-date (shipped entrypoint)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "scripts/bid_readiness/fixtures/golden"


@pytest.fixture(scope="module")
def case_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = Path(os.environ.get("BID_CASE_ROOT", "/tmp/extra-cli-bid-readiness-01/cases")) / "pytest-validate"
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.bid_readiness",
            "run",
            "--case-id",
            "pytest-validate",
            "--requirements",
            str(FIXTURES / "requirements.json"),
            "--documents",
            str(FIXTURES / "documents"),
            "--reference-date",
            "2026-07-01",
            "--output",
            str(out),
            "--entity",
            str(FIXTURES / "entity.json"),
            "--allow-non-isolated",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return out


def test_validate_reevaluates_with_future_reference_date(case_dir: Path) -> None:
    """Docs valid until mid-2026 must become EXPIRED when reference_date is 2027-01-01."""
    before = json.loads((case_dir / "documents" / "validity.json").read_text(encoding="utf-8"))
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.bid_readiness",
            "validate",
            "--case",
            str(case_dir),
            "--reference-date",
            "2027-01-01",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["ok"] is True
    assert result["reference_date"] == "2027-01-01"
    after = result["validity"]
    expired_after = sum(1 for v in after.values() if v.get("status") == "EXPIRED")
    expired_before = sum(1 for v in before.values() if v.get("status") == "EXPIRED")
    assert expired_after > expired_before
    disk = json.loads((case_dir / "documents" / "validity.json").read_text(encoding="utf-8"))
    assert disk == after
    assert result["summary"]["revalidated"] is True
