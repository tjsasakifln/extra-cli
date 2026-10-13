"""Drive the shipped campaign-plan linter against named fixtures."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.ops.check_confenge_campaign_plan import main as linter_main
from scripts.ops.confenge_commercial_plane import classify_plan

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/confenge_campaign_plans"
BAD = FIXTURES / "bad"
GOOD = FIXTURES / "good"


def _run(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.ops.check_confenge_campaign_plan", "--file", str(path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def test_eleven_negative_fixtures_rejected_twice() -> None:
    files = sorted(BAD.glob("*.md"))
    assert len(files) == 11
    for path in files:
        first = _run(path)
        second = _run(path)
        assert first.returncode == 1, path.name + first.stdout + first.stderr
        assert second.returncode == 1, path.name + second.stdout + second.stderr
        assert "REJECT" in first.stdout
        assert linter_main(["--file", str(path)]) == 1


def test_ten_positive_fixtures_accepted_twice() -> None:
    files = sorted(GOOD.glob("*.md"))
    assert len(files) == 10
    for path in files:
        first = _run(path)
        second = _run(path)
        assert first.returncode == 0, path.name + first.stdout + first.stderr
        assert second.returncode == 0, path.name + second.stdout + second.stderr
        assert "ACCEPT" in first.stdout
        assert linter_main(["--file", str(path)]) == 0


def test_wait_for_pncp_plan_is_rejected() -> None:
    text = (BAD / "01-wait-pncp-then-feed.md").read_text(encoding="utf-8")
    verdict = classify_plan(text, path="wait")
    assert verdict.accepted is False
    assert "wait_pncp_before_feed" in verdict.violations


def test_consumer_depends_on_pncp_live_is_rejected() -> None:
    text = (BAD / "08-consumer-depends-on-pncp-live.md").read_text(encoding="utf-8")
    verdict = classify_plan(text, path="consumer-dep")
    assert verdict.accepted is False
    assert "consumer_depends_on_pncp_live" in verdict.violations


def test_session_pncp_polling_as_normal_operation_is_rejected() -> None:
    text = (BAD / "09-session-pncp-polling-normal.md").read_text(encoding="utf-8")
    verdict = classify_plan(text, path="session-poll")
    assert verdict.accepted is False
    assert "session_pncp_polling_as_normal_operation" in verdict.violations


def test_second_acquisition_path_outside_lake_is_rejected() -> None:
    text = (BAD / "10-second-acquisition-path.md").read_text(encoding="utf-8")
    verdict = classify_plan(text, path="second-path")
    assert verdict.accepted is False
    assert "second_acquisition_path_outside_lake" in verdict.violations


def test_canary_payload_as_permanent_operation_is_rejected() -> None:
    text = (BAD / "11-canary-as-permanent-operation.md").read_text(encoding="utf-8")
    verdict = classify_plan(text, path="canary-permanent")
    assert verdict.accepted is False
    assert "canary_payload_as_permanent_operation" in verdict.violations


def test_historical_cascade_is_accepted() -> None:
    path = FIXTURES / "historical/old-cascade.md"
    proc = _run(path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert classify_plan(path.read_text(encoding="utf-8")).historical is True


def test_active_runbook_is_accepted() -> None:
    path = ROOT / "docs/ops/confenge-commercial-plane-authority.md"
    proc = _run(path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
