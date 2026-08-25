"""Tests for contracts checkpoint v2 contract and writer lock."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.crawl.contracts_checkpoint_contract import (
    LOGICAL_JOB_INCREMENTAL,
    CheckpointContractError,
    apply_attempt_to_checkpoint_dict,
    can_legitimately_rebind,
    diagnose,
    load_raw,
    save_raw,
)
from scripts.crawl.contracts_writer_lock import (
    EXIT_LOCK_BUSY,
    ContractsWriterLock,
)


def test_rebind_same_logical_job_preserves_windows(tmp_path: Path) -> None:
    path = tmp_path / "contracts_full.json"
    data = {
        "source": "pncp_contracts",
        "mode": "full",
        "completed_windows": ["20260701_20260707"],
        "meta": {
            "run_id": "contracts-90d-old",
            "logical_job_id": LOGICAL_JOB_INCREMENTAL,
            "incremental_days": 7,
            "campaign_id": "historical_contracts_incremental",
            "checkpoint_version": 2,
        },
    }
    save_raw(path, data)
    out = apply_attempt_to_checkpoint_dict(
        load_raw(path),
        "contracts-90d-new-attempt",
        logical_job_id=LOGICAL_JOB_INCREMENTAL,
        campaign_id="historical_contracts_incremental",
        incremental_days=7,
    )
    assert out["completed_windows"] == ["20260701_20260707"]
    assert out["meta"]["attempt_run_id"] == "contracts-90d-new-attempt"
    assert out["meta"]["run_id"] == "contracts-90d-new-attempt"
    assert "contracts-90d-old" in out["meta"]["previous_run_ids"]
    assert out["meta"]["foreign_resume"] is False
    assert out["meta"]["logical_job_id"] == LOGICAL_JOB_INCREMENTAL


def test_legacy_checkpoint_migrates_and_rebinds(tmp_path: Path) -> None:
    """VPS failure mode: bound run_id without logical_job_id."""
    data = {
        "source": "pncp_contracts",
        "mode": "full",
        "completed_windows": ["20260716_20260722"],
        "meta": {
            "run_id": "contracts-90d-20260723T201229Z-4da85aaee0",
            "run_ids": ["contracts-90d-20260723T201229Z-4da85aaee0"],
            "previous_run_ids": [],
            "foreign_resume": False,
        },
    }
    ok, reason = can_legitimately_rebind(
        data,
        logical_job_id=LOGICAL_JOB_INCREMENTAL,
        campaign_id="historical_contracts_incremental",
        incremental_days=7,
    )
    assert ok, reason
    out = apply_attempt_to_checkpoint_dict(
        data,
        "contracts-90d-20260729T090256Z-98168e293a",
        logical_job_id=LOGICAL_JOB_INCREMENTAL,
        campaign_id="historical_contracts_incremental",
        incremental_days=7,
    )
    assert out["meta"]["logical_job_id"] == LOGICAL_JOB_INCREMENTAL
    assert out["completed_windows"] == ["20260716_20260722"]


def test_campaign_mismatch_refuses(tmp_path: Path) -> None:
    data = {
        "source": "pncp_contracts",
        "mode": "full",
        "completed_windows": [],
        "meta": {
            "logical_job_id": LOGICAL_JOB_INCREMENTAL,
            "campaign_id": "OTHER-CAMPAIGN",
            "run_id": "x",
            "checkpoint_version": 2,
        },
    }
    with pytest.raises(CheckpointContractError):
        apply_attempt_to_checkpoint_dict(
            data,
            "new",
            logical_job_id=LOGICAL_JOB_INCREMENTAL,
            campaign_id="historical_contracts_incremental",
            incremental_days=7,
            allow_foreign=False,
        )


def test_days_mismatch_refuses() -> None:
    data = {
        "meta": {
            "logical_job_id": LOGICAL_JOB_INCREMENTAL,
            "incremental_days": 14,
            "run_id": "x",
        },
        "completed_windows": [],
    }
    with pytest.raises(CheckpointContractError):
        apply_attempt_to_checkpoint_dict(
            data,
            "new",
            logical_job_id=LOGICAL_JOB_INCREMENTAL,
            incremental_days=7,
        )


def test_diagnose_missing_ok(tmp_path: Path) -> None:
    r = diagnose(tmp_path)
    assert r.exists is False
    assert r.ok is True


def test_apply_via_pilot_helper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Shipped path: _apply_run_id_to_checkpoint with logical job."""
    from scripts.crawl import run_contracts_90d_pilot as pilot
    from scripts.crawl.contracts_crawler import CrawlCheckpoint

    monkeypatch.setenv("CONTRACTS_INCREMENTAL_MODE", "1")
    cp = CrawlCheckpoint(
        source="pncp_contracts",
        mode="full",
        completed_windows=["20260701_20260707"],
        meta={
            "run_id": "old-attempt",
            "logical_job_id": LOGICAL_JOB_INCREMENTAL,
            "incremental_days": 7,
            "campaign_id": "historical_contracts_incremental",
        },
    )
    prev = pilot._apply_run_id_to_checkpoint(
        cp,
        "new-attempt",
        logical_job_id=LOGICAL_JOB_INCREMENTAL,
        campaign_id="historical_contracts_incremental",
        incremental_days=7,
    )
    assert "old-attempt" in prev or cp.meta.get("previous_run_ids")
    assert cp.meta["run_id"] == "new-attempt"
    assert cp.meta["attempt_run_id"] == "new-attempt"
    assert cp.completed_windows == ["20260701_20260707"]


def test_incremental_cli_rebind_with_mocked_pilot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Drive real entry point: rebind stale run_id then invoke pilot with logical job."""
    from scripts.crawl import run_contracts_90d_pilot as pilot
    from scripts.crawl import run_contracts_incremental as inc_mod

    ckpt = tmp_path / "ckpt"
    ckpt.mkdir()
    (ckpt / "contracts_full.json").write_text(
        json.dumps(
            {
                "source": "pncp_contracts",
                "mode": "full",
                "completed_windows": ["20260720_20260726"],
                "meta": {
                    "run_id": "contracts-90d-stale",
                    "run_ids": ["contracts-90d-stale"],
                    "window_days": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out.json"
    monkeypatch.setenv("CONTRACTS_SKIP_WRITER_LOCK", "1")

    def fake_pilot(**kwargs):  # type: ignore[no-untyped-def]
        # Assert shipped path passes logical_job_id (not silent foreign fail)
        assert kwargs.get("logical_job_id") == LOGICAL_JOB_INCREMENTAL
        assert kwargs.get("campaign_id") == "historical_contracts_incremental"
        # Simulate pilot rebind on real checkpoint file
        cp = pilot.load_checkpoint("full")
        pilot._apply_run_id_to_checkpoint(
            cp,
            "contracts-90d-new-live",
            logical_job_id=kwargs["logical_job_id"],
            campaign_id=kwargs["campaign_id"],
            incremental_days=7,
        )
        pilot.save_checkpoint(cp)
        return {
            "status": "success",
            "run_id": "contracts-90d-new-live",
            "totals": {
                "inserted": 0,
                "windows_failed": 0,
                "page_errors": 0,
                "fetched": 0,
            },
        }

    monkeypatch.setattr(pilot, "run_pilot", fake_pilot)
    # configure checkpoint dir used by load_checkpoint inside fake
    pilot._configure_checkpoint_dir(str(ckpt))

    rc = inc_mod.main(
        [
            "--dsn",
            "postgresql://unused/unused",
            "--days",
            "7",
            "--checkpoint-dir",
            str(ckpt),
            "--output-json",
            str(out),
            "--skip-lock",
            "--campaign-id",
            "historical_contracts_incremental",
            "--logical-job-id",
            LOGICAL_JOB_INCREMENTAL,
        ]
    )
    assert rc == 0
    data = json.loads((ckpt / "contracts_full.json").read_text(encoding="utf-8"))
    assert data["meta"]["logical_job_id"] == LOGICAL_JOB_INCREMENTAL
    assert data["meta"]["run_id"] == "contracts-90d-new-live"
    assert "20260720_20260726" in data.get("completed_windows", [])
    assert out.is_file()


def test_writer_lock_nonblock_busy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lock_file = tmp_path / "extra-contracts-writer.lock"
    monkeypatch.setenv("EXTRA_CONTRACTS_WRITER_LOCK", str(lock_file))
    a = ContractsWriterLock(path=lock_file, blocking=False, owner_note="a")
    assert a.acquire() is True
    b = ContractsWriterLock(path=lock_file, blocking=False, owner_note="b")
    assert b.acquire() is False
    a.release()
    assert b.acquire() is True
    b.release()
    assert EXIT_LOCK_BUSY == 75


def test_restart_preserves_completed_and_archives_conflict(tmp_path: Path) -> None:
    from scripts.crawl.contracts_checkpoint_contract import archive_checkpoint
    from scripts.ops.pncp_contract_freshness import resume_units

    path = tmp_path / "contracts_full.json"
    data = {
        "source": "pncp_contracts",
        "mode": "full",
        "completed_windows": ["20260807_20260814"],
        "current_window": "20260812_20260819",
        "meta": {
            "logical_job_id": LOGICAL_JOB_INCREMENTAL,
            "attempt_run_id": "attempt-1",
            "campaign_id": "historical_contracts_incremental",
            "incremental_days": 7,
            "checkpoint_version": 2,
        },
    }
    save_raw(path, data)
    rebound = apply_attempt_to_checkpoint_dict(
        load_raw(path),
        "attempt-2-after-restart",
        logical_job_id=LOGICAL_JOB_INCREMENTAL,
        campaign_id="historical_contracts_incremental",
        incremental_days=7,
    )
    assert rebound["completed_windows"] == ["20260807_20260814"]
    pending = resume_units(
        planned=["20260807_20260814", "20260812_20260819"],
        completed=rebound["completed_windows"],
    )
    assert pending["next_unit"] == "20260812_20260819"
    assert pending["next_unit"] not in pending["skipped_resume"]
    bak = archive_checkpoint(path, reason="campaign-mismatch")
    assert bak is not None and bak.is_file()
    assert bak.read_text(encoding="utf-8")
    with pytest.raises(CheckpointContractError):
        apply_attempt_to_checkpoint_dict(
            load_raw(path),
            "foreign",
            logical_job_id=LOGICAL_JOB_INCREMENTAL,
            campaign_id="OTHER-CAMPAIGN",
            incremental_days=7,
            allow_foreign=False,
        )
