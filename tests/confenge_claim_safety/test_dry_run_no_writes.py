"""AC 18 — ``--dry-run`` writes nothing under the feed, and reports honestly."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.confenge.claim_safety_audit.cli import EXIT_OK, EXIT_REFUSED, EXIT_UNSAFE_FOUND, main
from scripts.confenge_claim_safety.policy import REASON_ACTIVE_PROVEN_UNREACHABLE
from tests.confenge_claim_safety.conftest import TODAY, build_feed, default_leads


def _snapshot(root: Path) -> dict[str, tuple[str, float]]:
    snapshot: dict[str, tuple[str, float]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            snapshot[str(path.relative_to(root))] = (digest, path.stat().st_mtime)
    return snapshot


def test_ac18_dry_run_leaves_feed_and_publication_state_untouched(tmp_path: Path) -> None:
    publish_dir = tmp_path / "public"
    releases = publish_dir / "releases"
    feed = build_feed(releases / "run-a", default_leads())
    current = publish_dir / "current"
    current.symlink_to(Path("releases") / "run-a", target_is_directory=True)
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"last_status": "PUBLISHED"}), encoding="utf-8")

    before_feed = _snapshot(publish_dir)
    before_state = state_path.read_bytes(), state_path.stat().st_mtime
    before_releases = sorted(p.name for p in releases.iterdir())
    before_target = current.readlink()

    report_path = tmp_path / "report.json"
    code = main(
        [
            "--dry-run",
            "--feed-dir",
            str(feed),
            "--publish-dir",
            str(publish_dir),
            "--state-path",
            str(state_path),
            "--report-json",
            str(report_path),
            "--today",
            str(TODAY),
        ]
    )

    assert code == EXIT_UNSAFE_FOUND
    assert _snapshot(publish_dir) == before_feed
    assert (state_path.read_bytes(), state_path.stat().st_mtime) == before_state
    assert sorted(p.name for p in releases.iterdir()) == before_releases
    assert current.readlink() == before_target
    assert report_path.is_file()


def test_ac18_report_names_the_unreachable_active_proven_class(tmp_path: Path) -> None:
    feed = build_feed(tmp_path / "feed", default_leads())
    report_path = tmp_path / "report.json"
    main(["--feed-dir", str(feed), "--report-json", str(report_path), "--today", str(TODAY)])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["class_distribution"]["SAFE_CURRENT_PROVEN"] == 0
    assert REASON_ACTIVE_PROVEN_UNREACHABLE in report["reason_codes"]
    assert report["mode"] == "dry-run"


def test_dry_run_is_the_default_mode(tmp_path: Path) -> None:
    feed = build_feed(tmp_path / "feed", default_leads())
    report_path = tmp_path / "report.json"
    assert main(["--feed-dir", str(feed), "--report-json", str(report_path)]) == EXIT_UNSAFE_FOUND
    assert json.loads(report_path.read_text(encoding="utf-8"))["mode"] == "dry-run"


def test_exit_code_zero_when_the_corpus_is_already_clean(tmp_path: Path) -> None:
    safe_only = [lead for lead in default_leads() if lead["messaging_context"]["why_now_code"] != "ADDENDUM"]
    feed = build_feed(tmp_path / "feed", safe_only)
    report_path = tmp_path / "report.json"
    assert main(["--feed-dir", str(feed), "--report-json", str(report_path), "--today", str(TODAY)]) == EXIT_OK
    assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "clean"


def test_unreadable_feed_is_a_refusal_not_a_crash(tmp_path: Path) -> None:
    assert main(["--feed-dir", str(tmp_path / "does-not-exist")]) == EXIT_REFUSED
