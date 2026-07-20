"""Ensure architecture rebaseline pointers exist (ARCH-RESET docs PR)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_overview_and_campaign_exist() -> None:
    assert (ROOT / "docs/architecture/overview.md").is_file()
    assert (ROOT / "docs/ops/campaigns/ARCH-RESET-2026-07-20/FINAL-REPORT.md").is_file()


def test_development_points_to_extra_weekly() -> None:
    text = (ROOT / "docs/DEVELOPMENT.md").read_text(encoding="utf-8")
    assert "extra-weekly" in text
    assert "weekly_cycle" in text


def test_next_dev_step_mentions_arch_reset() -> None:
    text = (ROOT / "docs/ops/NEXT-DEV-STEP.md").read_text(encoding="utf-8")
    assert "ARCH-RESET-2026-07-20" in text
    assert "LOCAL_READY" in text
