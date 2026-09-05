"""Drive the shipped commercial-plane preflight, not a reimplementation."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ops.check_confenge_commercial_plane import main as preflight_main
from scripts.ops.confenge_commercial_plane import (
    apply_host_readback,
    evaluate_host_onsuccess,
    evaluate_repo,
    on_success_targets,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/confenge_campaign_plans"


def _run_preflight(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.ops.check_confenge_commercial_plane", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def test_preflight_emits_objective_tokens_twice() -> None:
    first = _run_preflight([])
    second = _run_preflight([])
    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    for blob in (first.stdout, second.stdout):
        assert "PNCP_LIVE_ROLE=ASYNC_INGESTION_AND_TELEMETRY_ONLY" in blob
        assert "COMMERCIAL_OPERATIONAL_SOURCE=PERSISTED_CANONICAL_DATALAKE" in blob
        assert "PNCP_FRESH_IS_COMMERCIAL_GATE=NO" in blob
        assert "COMMERCIAL_STAGE_ORPHANS=ZERO" in blob
        assert "DATALAKE_FAIL_CLOSED_GATES=PASS" in blob
        assert "ARCHITECTURE_AUTHORITY=PASS" in blob
        payload = json.loads(blob.split("\n\n", 1)[0])
        assert payload["ok"] is True
        assert payload["tokens"]["PNCP_FRESH_IS_COMMERCIAL_GATE"] == "NO"


def test_preflight_main_function_same_tokens() -> None:
    code = preflight_main(["--root", str(ROOT), "--json-only"])
    assert code == 0


def test_evaluate_repo_requires_adr_accepted() -> None:
    ev = evaluate_repo(ROOT)
    names = {c.name: c.ok for c in ev.checks}
    assert names["adr_accepted_effective"] is True
    assert names["adr_index_coherent"] is True
    assert names["dod_p0_section"] is True
    assert names["versioned_onsuccess_zero"] is True
    assert names["pncp_fresh_not_commercial_gate"] is True
    assert names["pr528_not_current_implementation"] is True


def test_versioned_chain_has_zero_onsuccess() -> None:
    unit_dir = ROOT / "deploy/systemd"
    for name in (
        "pncp-contracts.service",
        "extra-confenge-source-freshness-gate.service",
        "extra-confenge-target-fit-refresh.service",
        "extra-confenge-target-fit-reconcile.service",
        "extra-confenge-contact-cycle.service",
        "extra-confenge-feed-cycle.service",
    ):
        assert on_success_targets((unit_dir / name).read_text(encoding="utf-8")) == []


def test_host_onsuccess_zero_on_empty_live_units() -> None:
    n, coupled = evaluate_host_onsuccess(
        {
            "pncp-contracts.service": "",
            "extra-confenge-feed-cycle.service": "",
        }
    )
    assert n == 0
    assert coupled == []


def test_reintroducing_onsuccess_fails(tmp_path: Path) -> None:
    clone = _minimal_tree(tmp_path)
    unit = clone / "deploy/systemd/pncp-contracts.service"
    text = unit.read_text(encoding="utf-8")
    text = text.replace(
        "[Unit]\n",
        "[Unit]\nOnSuccess=extra-confenge-source-freshness-gate.service\n",
        1,
    )
    unit.write_text(text, encoding="utf-8")
    ev = evaluate_repo(clone)
    assert any(c.name == "versioned_onsuccess_zero" and not c.ok for c in ev.checks)
    assert ev.tokens["ARCHITECTURE_AUTHORITY"] == "FAIL"


def test_removing_independent_timer_fails(tmp_path: Path) -> None:
    clone = _minimal_tree(tmp_path)
    pin = clone / "deploy/confenge/pin_release.py"
    pin.write_text(
        pin.read_text(encoding="utf-8").replace(
            '    "extra-confenge-feed-cycle.timer",\n',
            "",
            1,
        ),
        encoding="utf-8",
    )
    ev = evaluate_repo(clone)
    assert any(c.name == "chain_timers_cover_commercial" and not c.ok for c in ev.checks)


def test_stale_as_commercial_block_fails(tmp_path: Path) -> None:
    clone = _minimal_tree(tmp_path)
    pipeline = clone / "scripts/confenge_outreach_pipeline/pipeline.py"
    pipeline.write_text(
        pipeline.read_text(encoding="utf-8")
        + '\nif freshness.get("status") != "FRESH":\n    raise ValueError("stale blocks commerce")\n',
        encoding="utf-8",
    )
    ev = evaluate_repo(clone)
    assert any(c.name == "pncp_fresh_not_commercial_gate" and not c.ok for c in ev.checks)


@pytest.mark.parametrize(
    "assignment",
    [
        "datalake_watermark = source_observed_at",
        'projected["source_watermark"] = source_observed_at',
    ],
)
def test_telemetry_watermark_restamp_fails(tmp_path: Path, assignment: str) -> None:
    clone = _minimal_tree(tmp_path)
    pipeline = clone / "scripts/confenge_outreach_pipeline/pipeline.py"
    pipeline.write_text(
        pipeline.read_text(encoding="utf-8")
        + '\nif freshness.get("status") == "FRESH":\n    ' + assignment + "\n",
        encoding="utf-8",
    )
    ev = evaluate_repo(clone)
    assert any(c.name == "pncp_fresh_not_commercial_gate" and not c.ok for c in ev.checks)


def test_dropping_datalake_gate_fails(tmp_path: Path) -> None:
    clone = _minimal_tree(tmp_path)
    path = clone / "docs/contracts/confenge-commercial-plane/v1/operating-authority.json"
    contract = json.loads(path.read_text(encoding="utf-8"))
    contract["datalake_fail_closed_gates"] = [
        item for item in contract["datalake_fail_closed_gates"] if item != "coverage_ratio"
    ]
    path.write_text(json.dumps(contract), encoding="utf-8")
    ev = evaluate_repo(clone)
    assert any(c.name == "datalake_gates_present" and not c.ok for c in ev.checks)


def test_host_readback_detects_coupling() -> None:
    ev = evaluate_repo(ROOT)
    apply_host_readback(
        ev,
        {"pncp-contracts.service": "extra-confenge-source-freshness-gate.service"},
    )
    assert ev.tokens["HOST_ONSUCCESS_COUPLING"] != "ZERO"
    assert any(c.name == "host_onsuccess_zero" and not c.ok for c in ev.checks)


def _minimal_tree(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    rels = [
        "docs/contracts/confenge-commercial-plane/v1/operating-authority.json",
        "docs/architecture/adr/ADR-039-confenge-pncp-outbound-decoupling.md",
        "docs/architecture/adr/INDEX.md",
        "DOD.md",
        "docs/ops/confenge-commercial-plane-authority.md",
        "deploy/confenge/pin_release.py",
        "deploy/confenge/__init__.py",
        "deploy/__init__.py",
        "scripts/confenge_outreach_pipeline/cli.py",
        "scripts/confenge_outreach_pipeline/pipeline.py",
        "scripts/confenge_activation/publish.py",
        "scripts/warmbly_bridge/export.py",
        "scripts/ops/build_controlled_email_cohort.py",
        "deploy/systemd/pncp-contracts.service",
        "deploy/systemd/extra-confenge-source-freshness-gate.service",
        "deploy/systemd/extra-confenge-target-fit-refresh.service",
        "deploy/systemd/extra-confenge-target-fit-reconcile.service",
        "deploy/systemd/extra-confenge-contact-cycle.service",
        "deploy/systemd/extra-confenge-feed-cycle.service",
    ]
    for rel in rels:
        src = ROOT / rel
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
    return dest
