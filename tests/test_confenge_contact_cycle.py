from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.ops.confenge_contact_cycle import _batch_command, _child_env, run_cycle

NOW = datetime(2026, 8, 24, 20, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]


class FakeRunner:
    def __init__(self, progress: list[dict], *, existing: bool = False) -> None:
        self.progress = iter(progress)
        self.commands: list[list[str]] = []
        self.existing = existing

    def __call__(self, command: list[str]) -> dict:
        self.commands.append(command)
        action = command[command.index("batch") + 1]
        if action == "enqueue":
            return {
                "progress": {
                    "denominator": 3,
                    "counts": {"pending": 3},
                }
            }
        if action == "progress":
            return next(self.progress)
        if action == "publish":
            return {"approved": True, "snapshot_hash": "abc123"}
        if action == "export-contacts":
            out = Path(command[command.index("--out") + 1])
            report = Path(command[command.index("--report") + 1])
            out.write_text('{"canonical_account_id":"1","contacts":[]}\n', encoding="utf-8")
            report.write_text(
                json.dumps({"written": True, "population_count": 3}) + "\n",
                encoding="utf-8",
            )
            return {"written": True, "contacts_sha256": "def456"}
        raise AssertionError(command)


def terminal_progress(*, blocked: int = 0) -> dict:
    return {
        "denominator": 3,
        "counts": {
            "pending": 0,
            "running": 0,
            "retryable": 0,
            "succeeded": 3 - blocked,
            "blocked": blocked,
            "dlq": 0,
            "cancelled": 0,
        },
    }


def test_full_cycle_promotes_only_after_terminal_projection(tmp_path: Path) -> None:
    output = tmp_path / "contact-discovery"
    previous = output / "projections" / "previous"
    previous.mkdir(parents=True)
    (previous / "contacts.jsonl").write_text("old\n", encoding="utf-8")
    (previous / "contact-projection-report.json").write_text("{}\n", encoding="utf-8")
    (output / "current").symlink_to(Path("projections") / "previous", target_is_directory=True)
    runner = FakeRunner(
        [
            {"denominator": 3, "counts": {"pending": 2, "running": 1}},
            terminal_progress(blocked=1),
        ]
    )

    result = run_cycle(
        output_root=output,
        state_path=tmp_path / "state.json",
        alert_ledger=tmp_path / "alerts.jsonl",
        search_backend="searxng",
        searxng_url="https://search.internal",
        service="reajuste_14133",
        backend_concurrency=12,
        domain_concurrency=1,
        poll_seconds=0,
        timeout_seconds=60,
        runner=runner,
        sleep=lambda _seconds: None,
        now=lambda: NOW,
    )

    assert result["ok"] is True
    assert result["counts"]["blocked"] == 1
    assert (output / "current" / "contacts.jsonl").read_text(encoding="utf-8").startswith("{")
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["last_status"] == "COMPLETED"
    assert state["active_cohort"] is None
    enqueue = next(command for command in runner.commands if command[command.index("batch") + 1] == "enqueue")
    assert "target-confirmed" in enqueue
    assert str((previous / "contacts.jsonl").resolve()) in enqueue
    assert "--verify-email-dns" in enqueue
    assert str(output / "search-cache") in enqueue
    assert sum(command[command.index("batch") + 1] == "publish" for command in runner.commands) == 1
    assert sum(command[command.index("batch") + 1] == "export-contacts" for command in runner.commands) == 1
    export = next(command for command in runner.commands if command[command.index("batch") + 1] == "export-contacts")
    assert export[export.index("--prior-contacts") + 1] == str((previous / "contacts.jsonl").resolve())


def test_failed_partial_cycle_keeps_previous_projection_and_is_resumable(tmp_path: Path) -> None:
    output = tmp_path / "contact-discovery"
    previous = output / "projections" / "previous"
    previous.mkdir(parents=True)
    (previous / "contacts.jsonl").write_text("old\n", encoding="utf-8")
    (previous / "contact-projection-report.json").write_text("{}\n", encoding="utf-8")
    (output / "current").symlink_to(Path("projections") / "previous", target_is_directory=True)
    runner = FakeRunner([{"denominator": 3, "counts": {"pending": 3}}])

    with pytest.raises(TimeoutError):
        run_cycle(
            output_root=output,
            state_path=tmp_path / "state.json",
            alert_ledger=tmp_path / "alerts.jsonl",
            search_backend="searxng",
            searxng_url=None,
            service="reajuste_14133",
            backend_concurrency=12,
            domain_concurrency=1,
            poll_seconds=0,
            timeout_seconds=0,
            runner=runner,
            sleep=lambda _seconds: None,
            now=lambda: NOW,
        )

    assert (output / "current" / "contacts.jsonl").read_text(encoding="utf-8") == "old\n"
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["last_status"] == "FAILED"
    assert state["active_cohort"].startswith("target-confirmed-auto-")
    assert "CONTACT_CYCLE_FAILED" in (tmp_path / "alerts.jsonl").read_text(encoding="utf-8")
    assert all(command[command.index("batch") + 1] not in {"publish", "export-contacts"} for command in runner.commands)


def test_export_failure_after_snapshot_keeps_current_projection_unchanged(tmp_path: Path) -> None:
    """A failed cohort never atomically swaps a partial contact projection into current."""
    output = tmp_path / "contact-discovery"
    previous = output / "projections" / "previous"
    previous.mkdir(parents=True)
    (previous / "contacts.jsonl").write_text("old\n", encoding="utf-8")
    (previous / "contact-projection-report.json").write_text("{}\n", encoding="utf-8")
    (output / "current").symlink_to(Path("projections") / "previous", target_is_directory=True)
    runner = FakeRunner([terminal_progress()])

    def fail_export(command: list[str]) -> dict:
        if command[command.index("batch") + 1] == "export-contacts":
            partial = Path(command[command.index("--out") + 1])
            partial.parent.mkdir(parents=True, exist_ok=True)
            partial.write_text('{"partial":true}\n', encoding="utf-8")
            raise RuntimeError("simulated projection export failure")
        return runner(command)

    with pytest.raises(RuntimeError, match="simulated projection export failure"):
        run_cycle(
            output_root=output,
            state_path=tmp_path / "state.json",
            alert_ledger=tmp_path / "alerts.jsonl",
            search_backend="searxng",
            searxng_url=None,
            service="reajuste_14133",
            backend_concurrency=12,
            domain_concurrency=1,
            poll_seconds=0,
            timeout_seconds=60,
            runner=fail_export,
            sleep=lambda _seconds: None,
            now=lambda: NOW,
        )

    assert (output / "current" / "contacts.jsonl").read_text(encoding="utf-8") == "old\n"
    assert (output / "current").resolve() == previous.resolve()
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["last_status"] == "FAILED"


def test_resume_terminal_cohort_does_not_enqueue_again(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "schema_id": "confenge.contact_discovery.cycle_state.v1",
                "active_cohort": "target-confirmed-auto-existing",
                "last_status": "FAILED",
            }
        ),
        encoding="utf-8",
    )
    runner = FakeRunner([terminal_progress()])

    result = run_cycle(
        output_root=tmp_path / "contact-discovery",
        state_path=state,
        alert_ledger=tmp_path / "alerts.jsonl",
        search_backend="searxng",
        searxng_url=None,
        service="reajuste_14133",
        backend_concurrency=12,
        domain_concurrency=1,
        poll_seconds=0,
        timeout_seconds=60,
        runner=runner,
        sleep=lambda _seconds: None,
        now=lambda: NOW,
    )

    assert result["resumed"] is True
    assert all(command[command.index("batch") + 1] != "enqueue" for command in runner.commands)


def test_public_backend_and_positive_concurrency_are_required(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="public search backend"):
        run_cycle(
            output_root=tmp_path / "out",
            state_path=tmp_path / "state.json",
            alert_ledger=tmp_path / "alerts.jsonl",
            search_backend="off",
            searxng_url=None,
            service="reajuste_14133",
            backend_concurrency=1,
            domain_concurrency=1,
            poll_seconds=0,
            timeout_seconds=1,
        )


def test_systemd_cycle_and_workers_share_private_search_endpoint_contract() -> None:
    env_path = ROOT / "deploy/systemd/contact-discovery.env.example"
    cycle_path = ROOT / "deploy/systemd/extra-confenge-contact-cycle.service"
    worker_path = ROOT / "deploy/systemd/extra-contact-discovery-worker@.service"

    env = env_path.read_text(encoding="utf-8")
    cycle = cycle_path.read_text(encoding="utf-8")
    worker = worker_path.read_text(encoding="utf-8")

    assert "CONFENGE_SEARXNG_URL=http://127.0.0.1:18888" in env
    for unit in (cycle, worker):
        assert "EnvironmentFile=-/etc/extra-consultoria/contact-discovery.env" in unit
    assert "--out /var/lib/extra-consultoria/output/contact-discovery" in worker


def test_batch_children_use_isolated_interpreter() -> None:
    command = _batch_command("export-contacts", "--cohort", "c1")
    assert command[1] == "-P"
    assert command[2:5] == ["-m", "scripts.decision_unit_intelligence", "batch"]
    assert command[5] == "export-contacts"


def test_child_env_keeps_release_ahead_of_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTHONPATH", "/opt/extra-consultoria")
    env = _child_env()
    assert env["PYTHONSAFEPATH"] == "1"
    pythonpath = env["PYTHONPATH"].split(":")
    assert pythonpath[0] == str(ROOT)
    assert "/opt/extra-consultoria" in pythonpath
