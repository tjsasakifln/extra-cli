"""AC 17 — rollback end to end, with the membership delta guard revalidated."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.confenge.claim_safety_audit.cli import EXIT_OK, EXIT_REFUSED, ROLLBACK_ANCHOR_KEY, main
from scripts.confenge_activation.publish import (
    CLAIM_SAFETY_ROLLBACK_ANCHOR_KEY,
    _assert_membership_deactivation_delta,
    _published_target_roots,
    atomic_publish_directory,
)
from tests.confenge_claim_safety.conftest import TODAY, build_feed, default_leads


@pytest.fixture()
def applied(tmp_path: Path) -> dict:
    publish_dir = tmp_path / "public"
    state_path = tmp_path / "state.json"
    alerts = tmp_path / "alerts.jsonl"
    build = build_feed(tmp_path / "build", default_leads())
    baseline = atomic_publish_directory(build, publish_dir, state_path=state_path, alert_ledger=alerts)

    report_path = tmp_path / "apply.json"
    assert (
        main(
            [
                "--apply",
                "--feed-dir",
                str(publish_dir / "current"),
                "--publish-dir",
                str(publish_dir),
                "--build-dir",
                str(tmp_path / "cs-build"),
                "--state-path",
                str(state_path),
                "--alert-ledger",
                str(alerts),
                "--report-json",
                str(report_path),
                "--today",
                str(TODAY),
            ]
        )
        == EXIT_OK
    )
    return {
        "publish_dir": publish_dir,
        "state_path": state_path,
        "alerts": alerts,
        "tmp_path": tmp_path,
        "baseline_release": Path(baseline["release_dir"]),
        "report": json.loads(report_path.read_text(encoding="utf-8")),
    }


def test_anchor_is_written_before_the_swap_and_names_the_superseded_release(applied: dict) -> None:
    state = json.loads(applied["state_path"].read_text(encoding="utf-8"))
    assert state[CLAIM_SAFETY_ROLLBACK_ANCHOR_KEY] == applied["baseline_release"].name
    # Distinct from last_good_publication, which the apply itself overwrites.
    assert state.get("release_dir") == applied["report"]["release_dir"]
    assert applied["report"]["rollback_plan"]["anchor"] == applied["baseline_release"].name


def test_a_routine_publish_does_not_write_or_clobber_the_anchor(tmp_path: Path) -> None:
    """The anchor is a claim-safety artefact, not a side effect of every publish.

    An unconditional write would let the next feed-cycle publication move the
    anchor onto the claim-safety release itself, turning a later rollback into a
    silent no-op that still reports success.
    """
    publish_dir = tmp_path / "public"
    state_path = tmp_path / "state.json"
    alerts = tmp_path / "alerts.jsonl"

    first = build_feed(tmp_path / "build-1", default_leads(), snapshot="snapshot-one")
    atomic_publish_directory(first, publish_dir, state_path=state_path, alert_ledger=alerts)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert CLAIM_SAFETY_ROLLBACK_ANCHOR_KEY not in state

    second = build_feed(tmp_path / "build-2", default_leads(), snapshot="snapshot-two")
    result = atomic_publish_directory(second, publish_dir, state_path=state_path, alert_ledger=alerts)
    assert result["ok"] is True
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert CLAIM_SAFETY_ROLLBACK_ANCHOR_KEY not in state


def test_a_routine_publish_after_an_apply_leaves_the_anchor_intact(applied: dict) -> None:
    """The anchor must keep naming the pre-apply release, not drift forward."""
    anchor_before = json.loads(applied["state_path"].read_text(encoding="utf-8"))[CLAIM_SAFETY_ROLLBACK_ANCHOR_KEY]
    routine = build_feed(applied["tmp_path"] / "build-routine", default_leads(), snapshot="snapshot-routine")
    atomic_publish_directory(
        routine,
        applied["publish_dir"],
        state_path=applied["state_path"],
        alert_ledger=applied["alerts"],
    )
    state = json.loads(applied["state_path"].read_text(encoding="utf-8"))
    assert state[CLAIM_SAFETY_ROLLBACK_ANCHOR_KEY] == anchor_before == applied["baseline_release"].name


def test_ac17_rollback_restores_the_anchored_release(applied: dict) -> None:
    publish_dir: Path = applied["publish_dir"]
    current = publish_dir / "current"
    assert current.resolve() == Path(applied["report"]["release_dir"]).resolve()
    before_releases = sorted(p.name for p in (publish_dir / "releases").iterdir())

    report_path = applied["tmp_path"] / "rollback.json"
    code = main(
        [
            "rollback",
            "--publish-dir",
            str(publish_dir),
            "--state-path",
            str(applied["state_path"]),
            "--report-json",
            str(report_path),
        ]
    )
    assert code == EXIT_OK
    assert current.resolve() == applied["baseline_release"].resolve()
    # Rollback moves the pointer; it never deletes or rewrites an immutable release.
    assert sorted(p.name for p in (publish_dir / "releases").iterdir()) == before_releases
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "rolled_back"
    assert report["anchor"] == applied["baseline_release"].name


def test_ac17_delta_guard_is_revalidated_after_the_rollback(applied: dict) -> None:
    publish_dir: Path = applied["publish_dir"]
    post_apply = Path(applied["report"]["release_dir"])
    assert (
        main(
            [
                "rollback",
                "--publish-dir",
                str(publish_dir),
                "--state-path",
                str(applied["state_path"]),
            ]
        )
        == EXIT_OK
    )
    restored = (publish_dir / "current").resolve()
    restored_manifest = json.loads((restored / "manifest.json").read_text(encoding="utf-8"))
    post_manifest = json.loads((post_apply / "manifest.json").read_text(encoding="utf-8"))

    # The post-rollback state must reflect the pre-apply feed, without extra drops.
    assert _published_target_roots(post_apply, post_manifest) == _published_target_roots(restored, restored_manifest)
    _assert_membership_deactivation_delta(post_apply, post_manifest, restored, restored_manifest)
    assert restored_manifest["lead_count"] == post_manifest["lead_count"]


def test_rollback_without_an_anchor_refuses(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"last_status": "PUBLISHED"}), encoding="utf-8")
    assert (
        main(["rollback", "--publish-dir", str(tmp_path / "public"), "--state-path", str(state_path)]) == EXIT_REFUSED
    )


def test_rollback_refuses_a_path_traversing_anchor(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({ROLLBACK_ANCHOR_KEY: "../../etc"}), encoding="utf-8")
    assert (
        main(["rollback", "--publish-dir", str(tmp_path / "public"), "--state-path", str(state_path)]) == EXIT_REFUSED
    )


def test_rollback_refuses_when_the_anchored_release_is_gone(applied: dict) -> None:
    import shutil

    shutil.rmtree(applied["baseline_release"])
    assert (
        main(
            [
                "rollback",
                "--publish-dir",
                str(applied["publish_dir"]),
                "--state-path",
                str(applied["state_path"]),
            ]
        )
        == EXIT_REFUSED
    )
