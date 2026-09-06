from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path

import pytest

from scripts.ops.confenge_commercial_mutex import (
    AuthorityBusyError,
    AuthorityPaths,
    OperationAbortedError,
    StageAlreadyCompletedError,
    abort_open_authority,
    acquire_stage,
    inspect_authority,
    recover_stale_authority,
)


def _contender(root: str, ready, release, results) -> None:
    paths = AuthorityPaths(Path(root))
    try:
        with acquire_stage(
            paths=paths,
            operation_id="checkpoint-468-cycle-1",
            stage="refresh",
            scope="cycle",
            owner_id="founder-session-a",
        ) as claim:
            results.put("ACQUIRED")
            ready.set()
            release.wait(10)
            claim.complete({"mutation_count": 1})
    except AuthorityBusyError:
        results.put("BUSY_BEFORE_MUTATION")


def _crash_after_acquire(root: str, ready) -> None:
    paths = AuthorityPaths(Path(root))
    with acquire_stage(
        paths=paths,
        operation_id="crashed-operation",
        stage="contact",
        scope="stage",
        owner_id="crash-test",
    ):
        ready.set()
        os._exit(91)


def test_two_concurrent_starts_only_one_acquires_before_mutation(tmp_path: Path) -> None:
    ctx = multiprocessing.get_context("fork")
    ready = ctx.Event()
    release = ctx.Event()
    results = ctx.Queue()
    first = ctx.Process(target=_contender, args=(str(tmp_path), ready, release, results))
    second = ctx.Process(target=_contender, args=(str(tmp_path), ready, release, results))

    first.start()
    assert ready.wait(5)
    second.start()
    second.join(5)
    release.set()
    first.join(5)

    assert first.exitcode == 0
    assert second.exitcode == 0
    assert sorted([results.get(timeout=1), results.get(timeout=1)]) == [
        "ACQUIRED",
        "BUSY_BEFORE_MUTATION",
    ]


def test_completed_stage_retry_cannot_create_a_second_cycle(tmp_path: Path) -> None:
    paths = AuthorityPaths(tmp_path)
    with acquire_stage(
        paths=paths,
        operation_id="checkpoint-468-cycle-1",
        stage="refresh",
        scope="cycle",
        owner_id="founder-session-a",
    ) as claim:
        claim.complete({"cycle_id": "refresh-one"})

    with pytest.raises(StageAlreadyCompletedError):
        with acquire_stage(
            paths=paths,
            operation_id="checkpoint-468-cycle-1",
            stage="refresh",
            scope="cycle",
            owner_id="founder-session-a",
        ):
            pytest.fail("replay reached the mutation boundary")


def test_old_completed_or_aborted_operation_cannot_be_reused_after_a_new_operation(tmp_path: Path) -> None:
    paths = AuthorityPaths(tmp_path)
    with acquire_stage(
        paths=paths,
        operation_id="completed-old",
        stage="feed",
        scope="stage",
        owner_id="owner",
    ) as claim:
        claim.complete({"feed": "once"})
    with acquire_stage(
        paths=paths,
        operation_id="aborted-old",
        stage="contact",
        scope="stage",
        owner_id="owner",
    ):
        pass
    with acquire_stage(
        paths=paths,
        operation_id="current",
        stage="refresh",
        scope="stage",
        owner_id="owner",
    ) as claim:
        claim.complete({"refresh": "once"})

    with pytest.raises(StageAlreadyCompletedError):
        acquire_stage(
            paths=paths,
            operation_id="completed-old",
            stage="feed",
            scope="stage",
            owner_id="owner",
        )
    with pytest.raises(OperationAbortedError):
        acquire_stage(
            paths=paths,
            operation_id="aborted-old",
            stage="contact",
            scope="stage",
            owner_id="owner",
        )


def test_cycle_reservation_blocks_another_operation_between_stages(tmp_path: Path) -> None:
    paths = AuthorityPaths(tmp_path)
    with acquire_stage(
        paths=paths,
        operation_id="cycle-a",
        stage="refresh",
        scope="cycle",
        owner_id="owner-a",
    ) as claim:
        claim.complete({"refresh": "one"})

    assert inspect_authority(paths)["status"] == "OPEN"
    with pytest.raises(AuthorityBusyError, match="reserved"):
        with acquire_stage(
            paths=paths,
            operation_id="cycle-b",
            stage="refresh",
            scope="cycle",
            owner_id="owner-b",
        ):
            pytest.fail("second cycle reached mutation between stages")

    with acquire_stage(
        paths=paths,
        operation_id="cycle-a",
        stage="reconcile",
        scope="cycle",
        owner_id="owner-a",
    ) as claim:
        claim.complete({"reconcile": "one"})


def test_open_cycle_requires_explicit_abort_and_aborted_operation_is_not_reused(tmp_path: Path) -> None:
    paths = AuthorityPaths(tmp_path)
    with acquire_stage(
        paths=paths,
        operation_id="interrupted-cycle",
        stage="refresh",
        scope="cycle",
        owner_id="owner-a",
    ) as claim:
        claim.complete({"refresh": "done"})

    aborted = abort_open_authority(
        paths,
        expected_operation_id="interrupted-cycle",
        aborted_by="recovery-operator",
        reason="founder checkpoint invalidated",
    )
    assert aborted["status"] == "ABORTED"
    with pytest.raises(OperationAbortedError):
        acquire_stage(
            paths=paths,
            operation_id="interrupted-cycle",
            stage="reconcile",
            scope="cycle",
            owner_id="owner-a",
        )

    with acquire_stage(
        paths=paths,
        operation_id="fresh-cycle",
        stage="refresh",
        scope="cycle",
        owner_id="owner-b",
    ) as claim:
        claim.complete({"refresh": "fresh"})


def test_recovery_cannot_release_a_live_owner(tmp_path: Path) -> None:
    paths = AuthorityPaths(tmp_path)
    with acquire_stage(
        paths=paths,
        operation_id="live-operation",
        stage="contact",
        scope="stage",
        owner_id="live-owner",
    ) as claim:
        with pytest.raises(AuthorityBusyError, match="lock is active"):
            recover_stale_authority(
                paths,
                expected_operation_id="live-operation",
                recovered_by="unsafe-takeover",
            )
        assert inspect_authority(paths)["status"] == "ACTIVE"
        claim.complete({"still_owned": True})


def test_all_mutating_systemd_entrypoints_use_the_same_internal_authority() -> None:
    root = Path(__file__).resolve().parents[1]
    units = (
        "extra-confenge-target-fit-refresh.service",
        "extra-confenge-target-fit-reconcile.service",
        "extra-confenge-contact-cycle.service",
        "extra-confenge-feed-cycle.service",
    )
    for name in units:
        unit = (root / "deploy" / "systemd" / name).read_text(encoding="utf-8")
        assert "CONFENGE_COMMERCIAL_OPERATION_SCOPE=stage" in unit
        assert "/usr/bin/flock" not in unit

    assert "acquire_stage_from_env" in (root / "scripts" / "confenge_target_fit" / "cli.py").read_text(encoding="utf-8")
    assert "acquire_stage_from_env" in (root / "scripts" / "ops" / "confenge_contact_cycle.py").read_text(
        encoding="utf-8"
    )
    assert "acquire_stage_from_env" in (root / "scripts" / "ops" / "confenge_feed_cycle.py").read_text(encoding="utf-8")
    assert "acquire_stage_from_env" in (root / "scripts" / "confenge_activation" / "cli.py").read_text(encoding="utf-8")

    from scripts.ops.confenge_frozen_inputs import discover_frozen_input_paths

    frozen = set(discover_frozen_input_paths(root))
    assert {
        "scripts/ops/confenge_commercial_mutex.py",
        "scripts/ops/confenge_contact_cycle.py",
        "scripts/ops/confenge_feed_cycle.py",
        "scripts/confenge_target_fit/cli.py",
        "scripts/confenge_target_fit/hook_after_datalake.py",
        "scripts/confenge_activation/cli.py",
        "scripts/decision_unit_intelligence/cli.py",
    } <= frozen


def test_crash_requires_controlled_recovery_and_never_takes_live_lock(tmp_path: Path) -> None:
    ctx = multiprocessing.get_context("fork")
    ready = ctx.Event()
    crashed = ctx.Process(target=_crash_after_acquire, args=(str(tmp_path), ready))
    crashed.start()
    assert ready.wait(5)
    crashed.join(5)
    assert crashed.exitcode == 91

    paths = AuthorityPaths(tmp_path)
    status = inspect_authority(paths)
    assert status["status"] == "STALE_CANDIDATE"
    with pytest.raises(AuthorityBusyError, match="explicit recovery"):
        with acquire_stage(
            paths=paths,
            operation_id="new-operation",
            stage="contact",
            scope="stage",
            owner_id="recovery-test",
        ):
            pytest.fail("stale authority was taken over implicitly")

    recovered = recover_stale_authority(
        paths,
        expected_operation_id="crashed-operation",
        recovered_by="recovery-test",
    )
    assert recovered["status"] == "ABORTED"
    with pytest.raises(OperationAbortedError):
        with acquire_stage(
            paths=paths,
            operation_id="crashed-operation",
            stage="contact",
            scope="stage",
            owner_id="crash-test",
        ):
            pytest.fail("aborted operation was reused")


def test_active_record_is_observable_with_owner_and_acquisition_time(tmp_path: Path) -> None:
    paths = AuthorityPaths(tmp_path)
    with acquire_stage(
        paths=paths,
        operation_id="observable-operation",
        stage="feed",
        scope="stage",
        owner_id="operator@example",
    ) as claim:
        status = inspect_authority(paths)
        assert status["status"] == "ACTIVE"
        record = status["record"]
        assert record["operation_id"] == "observable-operation"
        assert record["active_stage"] == "feed"
        assert record["acquired_at"]
        assert record["owner"]["id"] == "operator@example"
        assert record["owner"]["pid"] == os.getpid()
        assert record["owner"]["boot_id"]
        assert record["owner"]["process_start_ticks"]
        claim.complete({"feed": "preserved-test"})


def test_state_file_is_machine_readable_and_fail_closed_on_corruption(tmp_path: Path) -> None:
    paths = AuthorityPaths(tmp_path)
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.state.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(AuthorityBusyError, match="invalid authority state"):
        with acquire_stage(
            paths=paths,
            operation_id="must-not-run",
            stage="refresh",
            scope="stage",
            owner_id="test",
        ):
            pytest.fail("corrupt state failed open")
    assert json.loads(json.dumps(inspect_authority(paths)))["status"] == "INVALID"


def test_unknown_but_valid_json_state_fails_closed(tmp_path: Path) -> None:
    paths = AuthorityPaths(tmp_path)
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.state.write_text(
        json.dumps(
            {
                "schema_id": "confenge.commercial.authority.v1",
                "operation_id": "unknown-state",
                "status": "MYSTERY",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(AuthorityBusyError, match="unknown authority status"):
        acquire_stage(
            paths=paths,
            operation_id="must-not-overwrite",
            stage="refresh",
            scope="stage",
            owner_id="test",
        )
    assert json.loads(paths.state.read_text(encoding="utf-8"))["operation_id"] == "unknown-state"


def test_open_cycle_cannot_be_downgraded_to_stage_scope(tmp_path: Path) -> None:
    paths = AuthorityPaths(tmp_path)
    with acquire_stage(
        paths=paths,
        operation_id="cycle-scope",
        stage="refresh",
        scope="cycle",
        owner_id="owner",
    ) as claim:
        claim.complete({})
    with pytest.raises(AuthorityBusyError, match="cannot be continued with stage scope"):
        acquire_stage(
            paths=paths,
            operation_id="cycle-scope",
            stage="reconcile",
            scope="stage",
            owner_id="owner",
        )


def test_mutating_clis_refuse_before_calling_their_mutation_without_operation_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from scripts.confenge_activation import cli as activation_cli
    from scripts.confenge_target_fit import cli as target_cli
    from scripts.confenge_target_fit.hook_after_datalake import notify_datalake_committed
    from scripts.decision_unit_intelligence import cli as dui_cli
    from scripts.ops import confenge_contact_cycle, confenge_feed_cycle

    monkeypatch.delenv("CONFENGE_COMMERCIAL_OPERATION_ID", raising=False)
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    monkeypatch.setenv("CONFENGE_COMMERCIAL_AUTHORITY_ROOT", str(tmp_path / "authority"))

    class Config:
        async_mode = "SHADOW"

        @staticmethod
        def resolve_state_dsn(explicit=None):
            return explicit or "postgresql://unused"

    monkeypatch.setattr(target_cli.TargetFitRefreshConfig, "from_env", lambda: Config())
    monkeypatch.setattr(
        target_cli,
        "run_refresh",
        lambda *args, **kwargs: pytest.fail("target-fit mutation ran without authority"),
    )
    monkeypatch.setattr(
        target_cli,
        "run_reconcile",
        lambda *args, **kwargs: pytest.fail("target-fit reconcile ran without authority"),
    )
    monkeypatch.setattr(
        confenge_contact_cycle,
        "run_cycle",
        lambda *args, **kwargs: pytest.fail("contact mutation ran without authority"),
    )
    monkeypatch.setattr(
        confenge_feed_cycle,
        "run_cycle",
        lambda *args, **kwargs: pytest.fail("feed mutation ran without authority"),
    )
    monkeypatch.setattr(
        activation_cli,
        "atomic_publish_directory",
        lambda *args, **kwargs: pytest.fail("direct publication ran without authority"),
    )

    assert target_cli.main(["--dsn", "postgresql://unused", "refresh"]) == 75
    assert target_cli.main(["--dsn", "postgresql://unused", "reconcile"]) == 75
    hook_result = notify_datalake_committed("postgresql://unused")
    assert hook_result and hook_result["soft_fail"] is True
    assert confenge_contact_cycle.main([]) == 75
    assert (
        confenge_feed_cycle.main(
            [
                "--output-root",
                str(tmp_path / "build"),
                "--durable-contacts",
                str(tmp_path / "contacts.jsonl"),
                "--publish-dir",
                str(tmp_path / "published"),
            ]
        )
        == 75
    )
    assert (
        activation_cli.main(
            [
                "publish",
                "--build-dir",
                str(tmp_path / "candidate"),
                "--publish-dir",
                str(tmp_path / "published"),
            ]
        )
        == 75
    )
    assert (
        dui_cli.main(
            [
                "batch",
                "publish",
                "--cohort",
                "arbitrary-name-cannot-bypass-authority",
                "--dsn",
                "postgresql://must-not-connect",
            ]
        )
        == 75
    )
