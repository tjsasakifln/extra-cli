from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.confenge_activation.publish import (
    atomic_publish_directory,
    check_current_publication,
    producer_identity,
    record_feed_cycle_state,
)
from scripts.confenge_outreach_pipeline.party_role import PARTY_ROLE_POLICY_V1
from scripts.confenge_target_fit.company_key import canonical_target_membership
from scripts.ops import confenge_feed_cycle

NOW = datetime(2026, 8, 24, 18, tzinfo=UTC)


def test_recurring_feed_cycle_runs_after_pncp_source_window() -> None:
    timer = Path("deploy/systemd/extra-confenge-feed-cycle.timer").read_text(encoding="utf-8").splitlines()

    assert "OnCalendar=*-*-* 01,13:20:00" in timer
    assert "RandomizedDelaySec=10m" in timer
    assert "OnCalendar=*-*-* 00,12:20:00" not in timer


def _build(
    root: Path,
    *,
    snapshot: str = "snapshot-a",
    generated_at: datetime = NOW,
    declared_lead_count: int | None = None,
    declared_chunk_count: int | None = None,
) -> Path:
    root.mkdir()
    generated = generated_at.isoformat().replace("+00:00", "Z")
    source = {
        "system": "extra-cli",
        "run_id": f"run-{snapshot}",
        "snapshot_hash": snapshot,
        "repo_sha": "abc123",
        "datalake_watermark": generated,
    }
    lead = {
        "company": {"cnpj14": "12345678000195"},
        "target_fit_class": "TARGET_CONFIRMED",
        "target_fit_version": "confenge-target-fit-v2",
        "email_send_ready": True,
        "contractor_role": {
            "policy_version": PARTY_ROLE_POLICY_V1,
            "status": "CONTRACTOR_ROLE_CONFIRMED",
            "target_party_role": "SUPPLIER",
        },
        "contacts": [
            {
                "email": "licitacao@example.com",
                "route_class": "ROLE_OR_DEPARTMENT",
                "source": "public_company_registry",
                "preferred_initial": True,
            }
        ],
    }
    chunk = {
        "schema_version": "confenge.outreach.v1",
        "generated_at": generated,
        "source": source,
        "pagination": {"chunk_index": 0, "has_more": False},
        "leads": [lead],
    }
    raw = (json.dumps(chunk, ensure_ascii=False, sort_keys=True) + "\n").encode()
    (root / "chunk_0000.json").write_bytes(raw)
    manifest = {
        "schema_version": "confenge.outreach.manifest.v1",
        "generated_at": generated,
        "source": source,
        "lead_count": 1,
        "chunk_count": 1,
        "chunks": [
            {
                "file": "chunk_0000.json",
                "chunk_index": 0,
                "content_hash": hashlib.sha256(raw).hexdigest(),
                "lead_count": 1,
                "has_more": False,
            }
        ],
        "authoritative_target_fit": {
            "coverage_complete": True,
            "omission_preserves_authorization": False,
            "full_decision_count": 1,
            "universe_count": 1,
            "declared_universe_count": 1,
            "shipped_lead_count": 1,
            "feed_scope": "TARGET_CONFIRMED_MEMBERSHIP",
            "decision_class_distribution": {"TARGET_CONFIRMED": 1},
            "ordering": {"watermarks_monotonic": True},
        },
        "authoritative_feed_scope": {
            "scope": "TARGET_CONFIRMED_MEMBERSHIP",
            "identity_key": "cnpj_root8",
            "decision_universe_count": 1,
            "shipped_lead_count": 1,
            "withheld_decision_count": 0,
            "branch_duplicates_collapsed": 0,
            "membership_hash_reproduced_from_feed": True,
        },
        "authoritative_target_membership": {
            **canonical_target_membership(["12345678000195"]),
            "target_fit_class": "TARGET_CONFIRMED",
            "target_confirmed_count": 1,
            "supplier_confirmed_count": 1,
            "source_member_count": 1,
            "membership_complete": True,
            "target_fit_policy_versions": ["confenge-target-fit-v2"],
            "target_party_role_distribution": {"SUPPLIER": 1},
            "contractor_role_status_distribution": {"CONTRACTOR_ROLE_CONFIRMED": 1},
        },
        "authoritative_party_roles": {
            "policy_version": PARTY_ROLE_POLICY_V1,
            "target_party_role_distribution": {"SUPPLIER": 1},
            "status_distribution": {"CONTRACTOR_ROLE_CONFIRMED": 1},
            "supplier_confirmed_count": 1,
            "buyer_supplier_conflict_fails_closed": True,
        },
        "authoritative_source_freshness": {
            "contract_version": "PNCP_CONTRACT_FRESHNESS/1.0",
            "status": "FRESH",
            "expires_at": (generated_at + timedelta(hours=6)).isoformat().replace("+00:00", "Z"),
        },
        "authoritative_contact_projection": {
            "schema_id": "confenge.contact_discovery.projection_report.v1",
            "report_sha256": "a" * 64,
            "cohort_id": "cohort-test",
            "generated_at": generated,
            "population_hash": "b" * 64,
            "population_as_of": generated,
            "projection_hash": "c" * 64,
            "controlled_email_policy_version": "controlled-email-policy.v3",
            "discovery_policy_version": "dui.policy.v1",
            "input_evidence_version": "target-fit.test",
            "code_sha": "abc123",
            "coverage_complete": True,
            "terminal_coverage_complete": True,
            "terminal_equation": {"holds": True},
            "population_count": 1,
            "membership_schema_version": canonical_target_membership(["12345678000195"])["schema_version"],
            "membership_identity_key": canonical_target_membership(["12345678000195"])["identity_key"],
            "membership_hash_algorithm": canonical_target_membership(["12345678000195"])["hash_algorithm"],
            "membership_count": 1,
            "membership_hash": canonical_target_membership(["12345678000195"])["membership_hash"],
            "enrichment_states": {"EMAIL_ROUTE_READY": 1},
            "recipient_states": {
                "RECIPIENT_ATTRIBUTED": 1,
                "READY": 1,
                "NO_PUBLIC_EMAIL_FOUND": 0,
                "BLOCKED_WITH_REASON": 0,
            },
            "output_preferred_route_class_distribution": {"ROLE_OR_DEPARTMENT": 1},
            "input_declared": True,
            "input_preferred_route_count": 1,
            "output_preferred_route_count": 1,
            "preferred_routes_reconciled": True,
            "input_preferred_routes_hash": "preferred-route-hash",
            "output_preferred_routes_hash": "preferred-route-hash",
        },
        "deactivations": [],
        "deactivation_count": 0,
    }
    if declared_lead_count is not None:
        manifest["lead_count"] = declared_lead_count
    if declared_chunk_count is not None:
        manifest["chunk_count"] = declared_chunk_count
        manifest["chunks"] = [
            {**manifest["chunks"][0], "chunk_index": index} for index in range(declared_chunk_count)
        ]
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    return tmp_path / "public", tmp_path / "state.json", tmp_path / "alerts.jsonl"


def test_publish_records_live_contact_metrics_and_immutable_release(tmp_path: Path) -> None:
    public, state, alerts = _paths(tmp_path)
    result = atomic_publish_directory(
        _build(tmp_path / "build"),
        public,
        state_path=state,
        alert_ledger=alerts,
        now=NOW,
    )
    assert result["ok"] is True
    assert result["lead_count"] == 1
    assert result["accounts_with_contacts"] == 1
    assert result["accounts_with_preferred_route"] == 1
    assert result["route_class_distribution"] == {"ROLE_OR_DEPARTMENT": 1}
    assert result["authoritative_contact_projection"]["preferred_routes_reconciled"] is True
    assert result["snapshot_changed"] is True
    assert result["contact_count_delta"] is None
    assert (public / "current").is_symlink()
    assert (public / "current" / "manifest.json").is_file()
    assert json.loads(state.read_text())["last_status"] == "PUBLISHED"
    assert not alerts.exists()


def test_publish_is_readable_by_a_separate_web_server_user(tmp_path: Path) -> None:
    public, state, alerts = _paths(tmp_path)
    prior_umask = os.umask(0o077)
    try:
        result = atomic_publish_directory(
            _build(tmp_path / "build"),
            public,
            state_path=state,
            alert_ledger=alerts,
            now=NOW,
        )
    finally:
        os.umask(prior_umask)

    release = Path(result["release_dir"])
    assert stat.S_IMODE(release.stat().st_mode) == 0o755
    assert stat.S_IMODE((release / "manifest.json").stat().st_mode) == 0o644
    assert stat.S_IMODE((release / "chunk_0000.json").stat().st_mode) == 0o644


def test_partial_manifest_is_refused_without_replacing_current(tmp_path: Path) -> None:
    public, state, alerts = _paths(tmp_path)
    first = atomic_publish_directory(_build(tmp_path / "first"), public, state_path=state, alert_ledger=alerts, now=NOW)
    prior = Path(first["current"]).resolve()
    bad = _build(tmp_path / "bad", snapshot="snapshot-b")
    manifest = json.loads((bad / "manifest.json").read_text())
    manifest["authoritative_target_fit"]["coverage_complete"] = False
    (bad / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="coverage_complete"):
        atomic_publish_directory(bad, public, state_path=state, alert_ledger=alerts, now=NOW)
    assert (public / "current").resolve() == prior
    assert "PUBLICATION_REFUSED" in alerts.read_text()


def test_membership_hash_mismatch_is_refused_without_replacing_current(tmp_path: Path) -> None:
    public, state, alerts = _paths(tmp_path)
    first = atomic_publish_directory(_build(tmp_path / "first"), public, state_path=state, alert_ledger=alerts, now=NOW)
    prior = Path(first["current"]).resolve()
    bad = _build(tmp_path / "bad", snapshot="snapshot-b")
    manifest = json.loads((bad / "manifest.json").read_text())
    manifest["authoritative_target_membership"]["membership_hash"] = "0" * 64
    (bad / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="membership_hash is not reproducible from the feed"):
        atomic_publish_directory(bad, public, state_path=state, alert_ledger=alerts, now=NOW)

    assert (public / "current").resolve() == prior


def test_buyer_supplier_conflict_with_authorized_route_is_refused(tmp_path: Path) -> None:
    public, state, alerts = _paths(tmp_path)
    bad = _build(tmp_path / "bad")
    chunk_path = bad / "chunk_0000.json"
    chunk = json.loads(chunk_path.read_text())
    role = chunk["leads"][0]["contractor_role"]
    role.update({"status": "PARTY_ROLE_CONFLICT", "target_party_role": "BUYER_CONFLICT"})
    raw = (json.dumps(chunk, ensure_ascii=False, sort_keys=True) + "\n").encode()
    chunk_path.write_bytes(raw)
    manifest = json.loads((bad / "manifest.json").read_text())
    manifest["chunks"][0]["content_hash"] = hashlib.sha256(raw).hexdigest()
    manifest["authoritative_target_membership"]["target_party_role_distribution"] = {"BUYER_CONFLICT": 1}
    manifest["authoritative_target_membership"]["contractor_role_status_distribution"] = {"PARTY_ROLE_CONFLICT": 1}
    manifest["authoritative_party_roles"]["target_party_role_distribution"] = {"BUYER_CONFLICT": 1}
    manifest["authoritative_party_roles"]["status_distribution"] = {"PARTY_ROLE_CONFLICT": 1}
    (bad / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="conflict authorizes outreach"):
        atomic_publish_directory(bad, public, state_path=state, alert_ledger=alerts, now=NOW)

    assert not (public / "current").exists()


def test_unreconciled_contact_projection_is_refused_before_publication(tmp_path: Path) -> None:
    public, state, alerts = _paths(tmp_path)
    bad = _build(tmp_path / "bad")
    manifest = json.loads((bad / "manifest.json").read_text())
    manifest["authoritative_contact_projection"]["output_preferred_route_count"] = 0
    (bad / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="preferred route count mismatch"):
        atomic_publish_directory(bad, public, state_path=state, alert_ledger=alerts, now=NOW)

    assert not (public / "current").exists()
    assert "PUBLICATION_REFUSED" in alerts.read_text()


def test_policy_excluded_preferred_routes_can_reconcile_at_zero(tmp_path: Path) -> None:
    public, state, alerts = _paths(tmp_path)
    build = _build(tmp_path / "build")
    manifest = json.loads((build / "manifest.json").read_text())
    projection = manifest["authoritative_contact_projection"]
    projection.update(
        {
            "raw_input_preferred_route_count": 1,
            "policy_excluded_preferred_route_count": 1,
            "input_preferred_route_count": 0,
            "output_preferred_route_count": 0,
            "input_preferred_routes_hash": "empty-route-hash",
            "output_preferred_routes_hash": "empty-route-hash",
        }
    )
    projection["recipient_states"].update(
        {
            "RECIPIENT_ATTRIBUTED": 0,
            "READY": 0,
            "BLOCKED_WITH_REASON": 1,
        }
    )
    projection["output_preferred_route_class_distribution"] = {}
    chunk_path = build / "chunk_0000.json"
    chunk = json.loads(chunk_path.read_text())
    chunk["leads"][0]["contacts"][0]["preferred_initial"] = False
    raw = json.dumps(chunk, separators=(",", ":"), sort_keys=True).encode()
    chunk_path.write_bytes(raw)
    manifest["chunks"][0]["content_hash"] = hashlib.sha256(raw).hexdigest()
    (build / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    result = atomic_publish_directory(
        build,
        public,
        state_path=state,
        alert_ledger=alerts,
        now=NOW,
    )

    assert result["ok"] is True
    assert result["accounts_with_preferred_route"] == 0


def test_same_snapshot_is_not_freshness_and_alerts(tmp_path: Path) -> None:
    public, state, alerts = _paths(tmp_path)
    first = atomic_publish_directory(_build(tmp_path / "first"), public, state_path=state, alert_ledger=alerts, now=NOW)
    first_generated_at = json.loads((Path(first["current"]) / "manifest.json").read_text(encoding="utf-8"))[
        "generated_at"
    ]
    second = atomic_publish_directory(
        _build(tmp_path / "second"), public, state_path=state, alert_ledger=alerts, now=NOW
    )
    assert second["ok"] is False
    assert second["skipped_same"] is True
    assert second["reason"] == "SAME_SNAPSHOT_NOT_FRESHNESS"
    assert json.loads((public / "current" / "manifest.json").read_text())["generated_at"] == first_generated_at
    assert (public / "current").resolve() == Path(first["current"]).resolve()
    assert json.loads(state.read_text())["last_status"] == "SKIPPED_SAME_SNAPSHOT"
    assert "SAME_SNAPSHOT_NOT_FRESHNESS" in alerts.read_text()


def test_monitor_fails_after_24_hours_without_touching_publication(tmp_path: Path) -> None:
    public, state, alerts = _paths(tmp_path)
    atomic_publish_directory(_build(tmp_path / "first"), public, state_path=state, alert_ledger=alerts, now=NOW)
    result = check_current_publication(
        public,
        state_path=state,
        alert_ledger=alerts,
        now=NOW + timedelta(hours=25),
    )
    assert result["ok"] is False
    assert result["status"] == "UNHEALTHY"
    assert "stale" in result["error"]
    assert (public / "current" / "manifest.json").is_file()
    assert "PUBLIC_FEED_UNHEALTHY" in alerts.read_text()
    saved = json.loads(state.read_text())
    assert saved["last_success_at"] == NOW.isoformat().replace("+00:00", "Z")
    assert saved["last_monitor_status"] == "UNHEALTHY"


def test_cycle_failure_preserves_last_publication_and_records_alert(tmp_path: Path) -> None:
    public, state, alerts = _paths(tmp_path)
    atomic_publish_directory(_build(tmp_path / "first"), public, state_path=state, alert_ledger=alerts, now=NOW)
    record_feed_cycle_state(
        state,
        alert_ledger=alerts,
        status="FAILED",
        at=NOW + timedelta(hours=1),
        alert_reason="FEED_CYCLE_FAILED",
        detail={"error": "pipeline failed", "duration_seconds": 12.5},
    )
    saved = json.loads(state.read_text())
    assert saved["last_status"] == "PUBLISHED"
    assert saved["last_cycle_status"] == "FAILED"
    assert saved["cycle"]["error"] == "pipeline failed"
    assert "FEED_CYCLE_FAILED" in alerts.read_text()


def test_hash_mismatch_is_refused_before_promotion(tmp_path: Path) -> None:
    public, state, alerts = _paths(tmp_path)
    build = _build(tmp_path / "build")
    (build / "chunk_0000.json").write_text("corrupt", encoding="utf-8")
    with pytest.raises(ValueError, match="chunk hash mismatch"):
        atomic_publish_directory(build, public, state_path=state, alert_ledger=alerts, now=NOW)
    assert not (public / "current").exists()


def test_cycle_binds_child_pipeline_to_same_checkout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    durable_contacts = tmp_path / "contacts.jsonl"
    durable_contacts.write_text("", encoding="utf-8")
    durable_contacts.with_name("contact-projection-report.json").write_text("{}", encoding="utf-8")
    captured: dict[str, object] = {}
    monkeypatch.setenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test")

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["env"] = kwargs["env"]
        run_dir = Path(command[command.index("--out") + 1])
        (run_dir / "06_warmbly_feed").mkdir()
        return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

    monkeypatch.setattr(confenge_feed_cycle.subprocess, "run", fake_run)
    monkeypatch.setattr(
        confenge_feed_cycle,
        "atomic_publish_directory",
        lambda *_args, **_kwargs: {"ok": True},
    )

    result = confenge_feed_cycle.run_cycle(
        output_root=tmp_path / "output",
        durable_contacts=durable_contacts,
        publish_dir=tmp_path / "public",
        as_of=NOW.date(),
        max_age_hours=24,
        state_path=tmp_path / "state.json",
        alert_ledger=tmp_path / "alerts.jsonl",
    )

    command = captured["command"]
    assert isinstance(command, list)
    runtime_root = Path(confenge_feed_cycle.__file__).resolve().parents[2]
    assert Path(command[1]) == runtime_root / "scripts/confenge_outreach_pipeline/__main__.py"
    assert "-m" not in command
    assert "--durable-contacts" in command
    child_env = captured["env"]
    assert isinstance(child_env, dict)
    assert str(child_env["PYTHONPATH"]).split(os.pathsep)[0] == str(runtime_root)
    assert result["ok"] is True


def test_fresh_publication_and_monitor_clear_prior_unhealthy_state(tmp_path: Path) -> None:
    public, state, alerts = _paths(tmp_path)
    atomic_publish_directory(_build(tmp_path / "first"), public, state_path=state, alert_ledger=alerts, now=NOW)
    check_current_publication(
        public,
        state_path=state,
        alert_ledger=alerts,
        now=NOW + timedelta(hours=25),
    )
    replacement_at = NOW + timedelta(hours=25)
    atomic_publish_directory(
        _build(tmp_path / "replacement", snapshot="snapshot-b", generated_at=replacement_at),
        public,
        state_path=state,
        alert_ledger=alerts,
        now=replacement_at,
    )
    published = json.loads(state.read_text())
    assert published["status"] == "PUBLISHED"
    assert published["error"] is None

    result = check_current_publication(
        public,
        state_path=state,
        alert_ledger=alerts,
        now=replacement_at,
    )
    assert result["status"] == "HEALTHY"
    healthy = json.loads(state.read_text())
    assert healthy["status"] == "HEALTHY"
    assert healthy["last_monitor_status"] == "HEALTHY"
    assert healthy["error"] is None


def test_feed_above_consumer_lead_ceiling_is_refused_without_replacing_current(tmp_path: Path) -> None:
    """A population the consumer cannot import is refused, never truncated."""
    public, state, alerts = _paths(tmp_path)
    first = atomic_publish_directory(_build(tmp_path / "first"), public, state_path=state, alert_ledger=alerts, now=NOW)
    prior = Path(first["current"]).resolve()
    oversized = _build(tmp_path / "oversized", snapshot="snapshot-b", declared_lead_count=100_001)

    with pytest.raises(ValueError, match="exceeds the consumer lead ceiling"):
        atomic_publish_directory(oversized, public, state_path=state, alert_ledger=alerts, now=NOW)

    assert (public / "current").resolve() == prior
    assert json.loads((prior / "manifest.json").read_text())["lead_count"] == 1
    assert "PUBLICATION_REFUSED" in alerts.read_text()


def test_feed_above_consumer_chunk_ceiling_is_refused_without_replacing_current(tmp_path: Path) -> None:
    public, state, alerts = _paths(tmp_path)
    first = atomic_publish_directory(_build(tmp_path / "first"), public, state_path=state, alert_ledger=alerts, now=NOW)
    prior = Path(first["current"]).resolve()
    oversized = _build(tmp_path / "oversized", snapshot="snapshot-b", declared_chunk_count=1_001)

    with pytest.raises(ValueError, match="exceeds the consumer chunk ceiling"):
        atomic_publish_directory(oversized, public, state_path=state, alert_ledger=alerts, now=NOW)

    assert (public / "current").resolve() == prior


def test_empty_feed_is_refused_without_replacing_current(tmp_path: Path) -> None:
    public, state, alerts = _paths(tmp_path)
    first = atomic_publish_directory(_build(tmp_path / "first"), public, state_path=state, alert_ledger=alerts, now=NOW)
    prior = Path(first["current"]).resolve()
    empty = _build(tmp_path / "empty", snapshot="snapshot-b", declared_lead_count=0)

    with pytest.raises(ValueError, match="at least one TARGET_CONFIRMED lead"):
        atomic_publish_directory(empty, public, state_path=state, alert_ledger=alerts, now=NOW)

    assert (public / "current").resolve() == prior


def test_decision_universe_may_not_be_redefined_to_the_feed_size(tmp_path: Path) -> None:
    """``full_decision_count`` keeps meaning the whole decision universe."""
    public, state, alerts = _paths(tmp_path)
    build = _build(tmp_path / "wide")
    manifest = json.loads((build / "manifest.json").read_text())
    authority = manifest["authoritative_target_fit"]
    authority.update({"full_decision_count": 406_076, "universe_count": 406_076, "declared_universe_count": 406_076})
    manifest["authoritative_feed_scope"].update({"decision_universe_count": 406_076, "withheld_decision_count": 406_075})
    (build / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    result = atomic_publish_directory(build, public, state_path=state, alert_ledger=alerts, now=NOW)

    assert result["ok"] is True
    assert result["lead_count"] == 1
    assert result["decision_universe_count"] == 406_076
    assert result["withheld_decision_count"] == 406_075
    assert result["feed_scope"] == "TARGET_CONFIRMED_MEMBERSHIP"


def test_manifest_cannot_publish_and_deactivate_the_same_account(tmp_path: Path) -> None:
    public, state, alerts = _paths(tmp_path)
    build = _build(tmp_path / "contradiction")
    manifest = json.loads((build / "manifest.json").read_text())
    manifest["deactivations"] = [{"cnpj14": "12345678000195", "to_state": "WATCH"}]
    manifest["deactivation_count"] = 1
    (build / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="both publishes and deactivates"):
        atomic_publish_directory(build, public, state_path=state, alert_ledger=alerts, now=NOW)

    assert not (public / "current").exists()


def test_deactivation_to_actionable_now_is_refused(tmp_path: Path) -> None:
    public, state, alerts = _paths(tmp_path)
    build = _build(tmp_path / "actionable")
    manifest = json.loads((build / "manifest.json").read_text())
    manifest["deactivations"] = [{"cnpj14": "11222333000181", "to_state": "ACTIONABLE_NOW"}]
    manifest["deactivation_count"] = 1
    (build / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported to_state"):
        atomic_publish_directory(build, public, state_path=state, alert_ledger=alerts, now=NOW)


def test_new_producer_semantics_defeat_the_same_snapshot_skip(tmp_path: Path) -> None:
    """Same inputs + new semantics must build; only same+same may replay.

    ``snapshot_hash`` covers inputs only, so a producer whose meaning changed
    (new module version, policy, classifier or repo SHA) used to be discarded as
    SAME_SNAPSHOT_NOT_FRESHNESS and never reached the feed.
    """
    public, state, alerts = _paths(tmp_path)
    first = atomic_publish_directory(
        _build(tmp_path / "first"), public, state_path=state, alert_ledger=alerts, now=NOW
    )
    assert first["ok"] is True

    changed = _build(tmp_path / "changed")
    manifest_path = changed / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["source"]["snapshot_hash"] == "snapshot-a", "inputs deliberately unchanged"
    manifest["module_version"] = "9.9.9-new-semantics"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False) + "\n", encoding="utf-8")

    second = atomic_publish_directory(changed, public, state_path=state, alert_ledger=alerts, now=NOW)
    assert second["ok"] is True, "new producer semantics must publish"
    assert second.get("skipped_same") is not True
    assert second["snapshot_hash"] == first["snapshot_hash"]
    assert second["producer_identity"] != first["producer_identity"]
    assert (public / "current").resolve() != Path(first["current"]).resolve()


def test_identical_inputs_and_semantics_still_replay(tmp_path: Path) -> None:
    public, state, alerts = _paths(tmp_path)
    first = atomic_publish_directory(
        _build(tmp_path / "first"), public, state_path=state, alert_ledger=alerts, now=NOW
    )
    second = atomic_publish_directory(
        _build(tmp_path / "second"), public, state_path=state, alert_ledger=alerts, now=NOW
    )
    assert second["reason"] == "SAME_SNAPSHOT_NOT_FRESHNESS"
    assert second["producer_identity"] == first["producer_identity"]
    assert second["prior_producer_identity"] == first["producer_identity"]


def test_producer_identity_is_deterministic_and_clock_free() -> None:
    manifest = {
        "schema_version": "confenge.outreach.manifest.v1",
        "module_version": "1.1.1",
        "source": {"snapshot_hash": "snapshot-a", "repo_sha": "abc123", "system": "extra-cli"},
        "authoritative_contact_projection": {"code_sha": "deadbeef"},
    }
    first = producer_identity(manifest)
    assert first == producer_identity(dict(manifest)), "no clock or counter participates"
    drifted = json.loads(json.dumps(manifest))
    drifted["source"]["repo_sha"] = "cafe1234"
    assert producer_identity(drifted) != first
