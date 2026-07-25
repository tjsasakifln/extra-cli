"""Golden case end-to-end via shipped CLI entrypoint."""

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
def golden_case(tmp_path_factory: pytest.TempPathFactory) -> Path:
    case_dir = Path(os.environ.get("BID_CASE_ROOT", "/tmp/extra-cli-bid-readiness-01/cases")) / "pytest-golden"
    case_dir.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.bid_readiness",
            "run",
            "--case-id",
            "pytest-golden",
            "--requirements",
            str(FIXTURES / "requirements.json"),
            "--documents",
            str(FIXTURES / "documents"),
            "--reference-date",
            "2026-07-01",
            "--output",
            str(case_dir),
            "--entity",
            str(FIXTURES / "entity.json"),
            "--allow-non-isolated",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    return case_dir


def test_golden_structure(golden_case: Path) -> None:
    for rel in [
        "case-manifest.json",
        "requirements.json",
        "documents/inventory.json",
        "documents/validity.json",
        "documents/identity.json",
        "matrices/requirement-document.json",
        "findings/blockers.json",
        "findings/all.json",
        "package/package-manifest.json",
        "package/submission-package.zip",
        "package/SIMULATION_ONLY.txt",
        "reports/executive-summary.md",
        "reports/readiness-report.html",
        "reports/readiness-workbook.xlsx",
        "reports/readiness-report.pdf",
        "verification.json",
    ]:
        assert (golden_case / rel).exists(), rel


def test_golden_detects_planted_defects(golden_case: Path) -> None:
    blockers = json.loads((golden_case / "findings/blockers.json").read_text(encoding="utf-8"))["items"]
    all_f = json.loads((golden_case / "findings/all.json").read_text(encoding="utf-8"))["items"]
    assert len(all_f) >= 5
    assert len(blockers) >= 1
    classes = {b["classification"] for b in blockers} | {f["classification"] for f in all_f}
    # planted: expired estadual, foreign CNPJ municipal, missing garantia, weak procura, declaration unsigned, etc.
    assert "EXPIRED_DOCUMENT" in classes or any("EXPIRED" in f["title"].upper() for f in all_f)
    assert "IDENTITY_MISMATCH" in classes or "CNPJ" in json.dumps(all_f)
    assert "MISSING_DOCUMENT" in classes  # garantia ausente

    matrix = json.loads((golden_case / "matrices/requirement-document.json").read_text(encoding="utf-8"))
    rows = matrix["rows"]
    assert len(rows) >= 20
    missing = [r for r in rows if r["status"] == "MISSING"]
    assert any(r["requirement_id"] == "REQ-GAR-001" for r in missing)

    expired_rows = [r for r in rows if r["status"] == "EXPIRED"]
    assert any(r["requirement_id"] == "REQ-FIS-002" for r in expired_rows)

    inconsistent = [r for r in rows if r["status"] == "INCONSISTENT"]
    assert any(r["requirement_id"] in {"REQ-FIS-003", "REQ-FIS-006"} for r in inconsistent)

    # Weak procura / identity-failed docs must never be false SATISFIED
    by_id = {r["requirement_id"]: r for r in rows}
    assert by_id["REQ-JUR-003"]["status"] != "SATISFIED"
    assert by_id["REQ-JUR-003"]["status"] == "INCONSISTENT"
    for rid in ("REQ-JUR-003", "REQ-FIS-003", "REQ-FIS-006"):
        assert by_id[rid]["status"] != "SATISFIED", rid

    pkg = json.loads((golden_case / "package/package-manifest.json").read_text(encoding="utf-8"))
    assert pkg["simulation_only"] is True
    assert pkg["package_status"] not in {"READY_TO_SUBMIT", "HABILITADA", "PROPOSTA APROVADA"}
    assert "SIMULATION_ONLY" in (golden_case / "package/SIMULATION_ONLY.txt").read_text(encoding="utf-8")
    # Foreign CNPJ cert must not be labeled VALID_EVIDENCE in package
    alerted = [f for f in (pkg.get("files") or []) if "CNPJ_MISMATCH" in (f.get("alerts") or [])]
    assert alerted, "expected CNPJ_MISMATCH package alert on foreign certidão"
    for f in alerted:
        assert f["included_as"] != "VALID_EVIDENCE"

    ver = json.loads((golden_case / "verification.json").read_text(encoding="utf-8"))
    assert ver["ok"] is True


def test_verify_detects_hash_corruption(golden_case: Path, tmp_path: Path) -> None:
    # copy case lightly by mutating vault object in place then restore
    inv = json.loads((golden_case / "documents/inventory.json").read_text(encoding="utf-8"))
    sha = inv["documents"][0]["sha256"]
    obj = golden_case / "vault/objects" / sha
    original = obj.read_bytes()
    try:
        obj.write_bytes(original + b"X")
        proc = subprocess.run(
            [sys.executable, "-m", "scripts.bid_readiness", "verify", "--case", str(golden_case)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        assert proc.returncode != 0
        assert "hash" in proc.stdout.lower() or "hash" in proc.stderr.lower() or "mismatch" in proc.stdout
    finally:
        obj.write_bytes(original)
