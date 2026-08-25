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
    record_feed_cycle_state,
)
from scripts.ops import confenge_feed_cycle

NOW = datetime(2026, 8, 24, 18, tzinfo=UTC)


def test_recurring_feed_cycle_runs_after_pncp_source_window() -> None:
    timer = (
        Path("deploy/systemd/extra-confenge-feed-cycle.timer")
        .read_text(encoding="utf-8")
        .splitlines()
    )

    assert "OnCalendar=*-*-* 01,13:20:00" in timer
    assert "RandomizedDelaySec=10m" in timer
    assert "OnCalendar=*-*-* 00,12:20:00" not in timer


def _build(root: Path, *, snapshot: str = "snapshot-a", generated_at: datetime = NOW) -> Path:
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
            "ordering": {"watermarks_monotonic": True},
        },
        "authoritative_source_freshness": {
            "contract_version": "PNCP_CONTRACT_FRESHNESS/1.0",
            "status": "FRESH",
            "expires_at": (generated_at + timedelta(hours=6)).isoformat().replace("+00:00", "Z"),
        },
        "authoritative_contact_projection": {
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
    first = atomic_publish_directory(
        _build(tmp_path / "first"), public, state_path=state, alert_ledger=alerts, now=NOW
    )
    prior = Path(first["current"]).resolve()
    bad = _build(tmp_path / "bad", snapshot="snapshot-b")
    manifest = json.loads((bad / "manifest.json").read_text())
    manifest["authoritative_target_fit"]["coverage_complete"] = False
    (bad / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="coverage_complete"):
        atomic_publish_directory(bad, public, state_path=state, alert_ledger=alerts, now=NOW)
    assert (public / "current").resolve() == prior
    assert "PUBLICATION_REFUSED" in alerts.read_text()


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


def test_same_snapshot_is_not_freshness_and_alerts(tmp_path: Path) -> None:
    public, state, alerts = _paths(tmp_path)
    atomic_publish_directory(
        _build(tmp_path / "first"), public, state_path=state, alert_ledger=alerts, now=NOW
    )
    second = atomic_publish_directory(
        _build(tmp_path / "second"), public, state_path=state, alert_ledger=alerts, now=NOW
    )
    assert second["ok"] is False
    assert second["skipped_same"] is True
    assert second["reason"] == "SAME_SNAPSHOT_NOT_FRESHNESS"
    assert json.loads(state.read_text())["last_status"] == "SKIPPED_SAME_SNAPSHOT"
    assert "SAME_SNAPSHOT_NOT_FRESHNESS" in alerts.read_text()


def test_monitor_fails_after_24_hours_without_touching_publication(tmp_path: Path) -> None:
    public, state, alerts = _paths(tmp_path)
    atomic_publish_directory(
        _build(tmp_path / "first"), public, state_path=state, alert_ledger=alerts, now=NOW
    )
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
    atomic_publish_directory(
        _build(tmp_path / "first"), public, state_path=state, alert_ledger=alerts, now=NOW
    )
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
    atomic_publish_directory(
        _build(tmp_path / "first"), public, state_path=state, alert_ledger=alerts, now=NOW
    )
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
