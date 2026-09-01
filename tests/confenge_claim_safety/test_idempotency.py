"""AC 10-14 — apply, on an isolated feed.

Production ``--apply`` is deferred to the @po/@devops gate (campaign re-freeze of
``publish.py`` + serialization behind the sector-classifier release), so these
invariants are proven here against a feed fixture, never against the live feed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.confenge.claim_safety_audit.cli import (
    EXIT_OK,
    STATUS_PUBLISHED,
    STATUS_SKIPPED_NO_CHANGE,
    main,
)
from scripts.confenge_activation.publish import (
    _assert_membership_deactivation_delta,
    _published_target_roots,
    publication_semantic_hash,
)
from scripts.confenge_claim_safety.policy import PUBLISHABLE_CLASSES
from tests.confenge_claim_safety.conftest import TODAY, build_feed, default_leads

TARGET_FIT_FIELDS = ("target_fit_class", "target_fit_version")


@pytest.fixture()
def published(tmp_path: Path) -> dict:
    """Publish the baseline feed, then run ``--apply`` once."""
    publish_dir = tmp_path / "public"
    state_path = tmp_path / "state.json"
    alerts = tmp_path / "alerts.jsonl"
    build = build_feed(tmp_path / "build", default_leads())

    from scripts.confenge_activation.publish import atomic_publish_directory

    baseline = atomic_publish_directory(build, publish_dir, state_path=state_path, alert_ledger=alerts)
    assert baseline["ok"] is True

    report_path = tmp_path / "apply.json"
    code = main(
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
    assert code == EXIT_OK
    return {
        "publish_dir": publish_dir,
        "state_path": state_path,
        "alerts": alerts,
        "tmp_path": tmp_path,
        "baseline_release": Path(baseline["release_dir"]),
        "report": json.loads(report_path.read_text(encoding="utf-8")),
    }


def _leads(release: Path) -> list[dict]:
    manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
    leads: list[dict] = []
    for entry in manifest["chunks"]:
        payload = json.loads((release / entry["file"]).read_text(encoding="utf-8"))
        leads.extend(payload["leads"])
    return leads


# --- AC 10 ------------------------------------------------------------------ #
def test_ac10_published_release_carries_zero_unsafe_and_zero_unreadable_leads(published: dict) -> None:
    """Measured on the release, not on the build dir."""
    from scripts.confenge_claim_safety.classify import classify_lead

    report = published["report"]
    assert report["status"] == STATUS_PUBLISHED
    release = Path(report["release_dir"])
    classes = [classify_lead(lead, today=TODAY).safety_class for lead in _leads(release)]
    assert all(safety in PUBLISHABLE_CLASSES for safety in classes), classes
    assert report["unsafe_present_claim_count"] == 0
    assert report["non_publishable_count"] == 0


def test_ac10_manifest_carries_the_claim_safety_corpus_hash(published: dict) -> None:
    release = Path(published["report"]["release_dir"])
    manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["claim_safety"]["corpus_hash"]
    assert manifest["claim_safety"]["unsafe_present_claim_count"] == 0
    assert manifest["publication_semantic_hash"] == publication_semantic_hash(manifest)


def test_apply_produces_a_new_release_not_a_silent_replay(published: dict) -> None:
    """Without ``claim_safety_hash`` in the semantics this would be skipped_same."""
    assert Path(published["report"]["release_dir"]) != published["baseline_release"]
    assert published["report"]["skipped_same"] is False


# --- AC 11 ------------------------------------------------------------------ #
def test_ac11_second_apply_is_an_observable_skip_not_a_second_release(published: dict) -> None:
    publish_dir: Path = published["publish_dir"]
    releases = publish_dir / "releases"
    before = sorted(p.name for p in releases.iterdir())
    report_path = published["tmp_path"] / "apply-2.json"
    code = main(
        [
            "--apply",
            "--feed-dir",
            str(publish_dir / "current"),
            "--publish-dir",
            str(publish_dir),
            "--build-dir",
            str(published["tmp_path"] / "cs-build-2"),
            "--state-path",
            str(published["state_path"]),
            "--alert-ledger",
            str(published["alerts"]),
            "--report-json",
            str(report_path),
            "--today",
            str(TODAY),
        ]
    )
    assert code == EXIT_OK
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == STATUS_SKIPPED_NO_CHANGE
    assert report["published"] is False
    assert report["rewritten_lead_count"] == 0
    assert sorted(p.name for p in releases.iterdir()) == before


# --- AC 12 ------------------------------------------------------------------ #
def test_ac12_lead_count_and_source_lead_ids_are_identical(published: dict) -> None:
    before = _leads(published["baseline_release"])
    after = _leads(Path(published["report"]["release_dir"]))
    assert len(before) == len(after)
    assert {lead["source_lead_id"] for lead in before} == {lead["source_lead_id"] for lead in after}


# --- AC 13 ------------------------------------------------------------------ #
def test_ac13_target_fit_fields_are_byte_identical_and_target_confirmed_untouched(published: dict) -> None:
    before = {lead["source_lead_id"]: lead for lead in _leads(published["baseline_release"])}
    after = {lead["source_lead_id"]: lead for lead in _leads(Path(published["report"]["release_dir"]))}
    assert set(before) == set(after)
    for lead_id, original in before.items():
        updated = after[lead_id]
        original_fit = {k: v for k, v in original.items() if k.startswith("target_fit_")}
        updated_fit = {k: v for k, v in updated.items() if k.startswith("target_fit_")}
        assert json.dumps(original_fit, sort_keys=True) == json.dumps(updated_fit, sort_keys=True)
        for field in TARGET_FIT_FIELDS:
            assert original.get(field) == updated.get(field)
        assert updated["target_fit_class"] == "TARGET_CONFIRMED"
        assert original["contractor_role"] == updated["contractor_role"]
        assert original["contracts"] == updated["contracts"]


# --- AC 14 ------------------------------------------------------------------ #
def test_ac14_membership_is_unchanged_and_the_delta_guard_does_not_fire(published: dict) -> None:
    baseline = published["baseline_release"]
    release = Path(published["report"]["release_dir"])
    baseline_manifest = json.loads((baseline / "manifest.json").read_text(encoding="utf-8"))
    release_manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))

    assert (
        baseline_manifest["authoritative_target_membership"]["membership_hash"]
        == release_manifest["authoritative_target_membership"]["membership_hash"]
    )
    assert _published_target_roots(baseline, baseline_manifest) == _published_target_roots(release, release_manifest)
    # The existing guard is exercised, not reimplemented: it must stay silent.
    _assert_membership_deactivation_delta(baseline, baseline_manifest, release, release_manifest)
    assert release_manifest["deactivations"] == []


def test_only_the_claim_bearing_copy_changed(published: dict) -> None:
    before = {lead["source_lead_id"]: lead for lead in _leads(published["baseline_release"])}
    after = {lead["source_lead_id"]: lead for lead in _leads(Path(published["report"]["release_dir"]))}
    changed_fields: set[str] = set()
    for lead_id, original in before.items():
        updated = after[lead_id]
        for key in set(original) | set(updated):
            if original.get(key) != updated.get(key):
                changed_fields.add(key)
    assert changed_fields <= {"messaging_context", "moment", "claim_safety"}, changed_fields
