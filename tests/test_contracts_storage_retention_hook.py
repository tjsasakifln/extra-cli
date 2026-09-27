from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.crawl.run_contracts_90d_pilot import (
    _retain_storage_after_durable_batch,
    _retention_batch_key,
    _storage_preflight,
)
from scripts.crawl.run_contracts_incremental import EXIT_RETENTION_DEGRADED, run_with_one_retry


@dataclass
class FakeReport:
    status: str
    target_bytes: int = 100
    filesystem_freed_bytes: int = 100
    relation_reusable_bytes: int = 0

    def to_dict(self):
        return {
            "status": self.status,
            "target_bytes": self.target_bytes,
            "filesystem_freed_bytes": self.filesystem_freed_bytes,
            "relation_reusable_bytes": self.relation_reusable_bytes,
        }


def test_retention_hook_disabled_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STORAGE_RETENTION_ENABLED", raising=False)
    assert (
        _retain_storage_after_durable_batch(
            object(), [{"contrato_id": "x"}], growth_bytes=100, writer_fence_already_held=True
        )
        is None
    )


def test_retention_hook_measures_serialized_batch_and_uses_outer_fence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = {}

    def fake_run_retention(**kwargs):
        captured.update(kwargs)
        return FakeReport("SATISFIED")

    monkeypatch.setenv("STORAGE_RETENTION_ENABLED", "1")
    monkeypatch.setenv("STORAGE_RETENTION_APPLY", "1")
    monkeypatch.setenv("STORAGE_RETENTION_SPACE_PATH", str(tmp_path))
    monkeypatch.setenv("STORAGE_RETENTION_FILE_ROOTS", str(tmp_path))
    monkeypatch.setattr("scripts.ops.storage_retention.run_retention", fake_run_retention)
    monkeypatch.setattr(
        "scripts.crawl.run_contracts_90d_pilot._claim_retention_batch",
        lambda *_args, **_kwargs: ("CLAIMED_NEW", "token", None),
    )
    monkeypatch.setattr("scripts.crawl.run_contracts_90d_pilot._complete_retention_batch", lambda *_args, **_kwargs: None)

    result = _retain_storage_after_durable_batch(
        object(),
        [{"contrato_id": "abc", "valor": 12}],
        growth_bytes=80,
        writer_fence_already_held=True,
    )

    assert result and result["status"] == "SATISFIED"
    assert captured["target_bytes"] == 80
    assert captured["apply"] is True
    assert captured["writer_fence_already_held"] is True
    assert captured["canonical_required_bytes"] == 100
    assert captured["history_required_bytes"] == 0
    assert captured["lock_dir"] == Path(
        "/var/lib/extra-consultoria/locks/storage-retention.lock"
    )


def test_retention_hook_records_shortfall_without_replaying_durable_batch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("STORAGE_RETENTION_ENABLED", "1")
    monkeypatch.setenv("STORAGE_RETENTION_APPLY", "1")
    monkeypatch.setenv("STORAGE_RETENTION_SPACE_PATH", str(tmp_path))
    monkeypatch.setattr(
        "scripts.ops.storage_retention.run_retention",
        lambda **_kwargs: FakeReport("INSUFFICIENT", target_bytes=100, filesystem_freed_bytes=0),
    )
    monkeypatch.setattr(
        "scripts.crawl.run_contracts_90d_pilot._claim_retention_batch",
        lambda *_args, **_kwargs: ("CLAIMED_NEW", "token", None),
    )
    monkeypatch.setattr("scripts.crawl.run_contracts_90d_pilot._complete_retention_batch", lambda *_args, **_kwargs: None)

    result = _retain_storage_after_durable_batch(
        object(), [{"contrato_id": "abc"}], growth_bytes=100, writer_fence_already_held=True
    )
    assert result and result["status"] == "INSUFFICIENT"


def test_retention_hook_maps_reusable_capacity_to_its_growing_relation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = {}
    monkeypatch.setenv("STORAGE_RETENTION_ENABLED", "1")
    monkeypatch.setenv("STORAGE_RETENTION_SPACE_PATH", str(tmp_path))
    monkeypatch.setattr(
        "scripts.ops.storage_retention.run_retention",
        lambda **kwargs: captured.update(kwargs) or FakeReport("PLAN_SUFFICIENT"),
    )

    result = _retain_storage_after_durable_batch(
        object(),
        [{"contrato_id": "abc"}],
        growth_bytes=40,
        growth_by_relation={
            "pncp_supplier_contracts": 10,
            "contract_role_links": 10,
            "contract_version_history": 20,
        },
        writer_fence_already_held=True,
    )

    assert result and result["status"] == "PLAN_SUFFICIENT"
    assert captured["canonical_required_bytes"] == 25
    assert captured["history_required_bytes"] == 25


def test_apply_requires_space_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORAGE_RETENTION_ENABLED", "1")
    monkeypatch.setenv("STORAGE_RETENTION_APPLY", "1")
    monkeypatch.delenv("STORAGE_RETENTION_SPACE_PATH", raising=False)
    monkeypatch.setattr(
        "scripts.crawl.run_contracts_90d_pilot._claim_retention_batch",
        lambda *_args, **_kwargs: ("CLAIMED_NEW", "token", None),
    )
    monkeypatch.setattr("scripts.crawl.run_contracts_90d_pilot._complete_retention_batch", lambda *_args, **_kwargs: None)

    result = _retain_storage_after_durable_batch(
        object(), [{"contrato_id": "abc"}], growth_bytes=100, writer_fence_already_held=True
    )
    assert result and result["status"] == "RETENTION_ERROR_AFTER_COMMIT"


@pytest.mark.parametrize(
    ("claim_state", "previous_status", "expected_status"),
    [
        ("ALREADY_COMPLETED", "SATISFIED", "ALREADY_COMPLETED"),
        ("ALREADY_DEGRADED", "INSUFFICIENT", "ALREADY_DEGRADED"),
        ("ALREADY_ERROR", "RETENTION_ERROR_AFTER_COMMIT", "ALREADY_ERROR"),
    ],
)
def test_completed_ledger_state_is_propagated_without_repeating_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    claim_state: str,
    previous_status: str,
    expected_status: str,
) -> None:
    monkeypatch.setenv("STORAGE_RETENTION_ENABLED", "1")
    monkeypatch.setenv("STORAGE_RETENTION_APPLY", "1")
    monkeypatch.setattr(
        "scripts.crawl.run_contracts_90d_pilot._claim_retention_batch",
        lambda *_args, **_kwargs: (claim_state, None, {"status": previous_status, "evidence": 1}),
    )
    monkeypatch.setattr(
        "scripts.ops.storage_retention.run_retention",
        lambda **_kwargs: pytest.fail("completed claims must never run cleanup again"),
    )

    result = _retain_storage_after_durable_batch(
        object(), [{"contrato_id": "abc"}], growth_bytes=100, writer_fence_already_held=True
    )

    assert result and result["status"] == expected_status
    assert result["previous_report"]["status"] == previous_status


def test_invalid_numeric_config_after_claim_is_persisted_not_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = []
    monkeypatch.setenv("STORAGE_RETENTION_ENABLED", "1")
    monkeypatch.setenv("STORAGE_RETENTION_APPLY", "1")
    monkeypatch.setenv("STORAGE_RETENTION_MIN_AGE_HOURS", "not-a-number")
    monkeypatch.setattr(
        "scripts.crawl.run_contracts_90d_pilot._claim_retention_batch",
        lambda *_args, **_kwargs: ("CLAIMED_NEW", "owner", None),
    )
    monkeypatch.setattr(
        "scripts.crawl.run_contracts_90d_pilot._complete_retention_batch",
        lambda *_args: completed.append(_args[-1]),
    )

    result = _retain_storage_after_durable_batch(
        object(), [{"contrato_id": "abc"}], growth_bytes=100, writer_fence_already_held=True
    )

    assert result and result["status"] == "RETENTION_ERROR_AFTER_COMMIT"
    assert result["error_type"] == "ValueError"
    assert completed and completed[0]["status"] == "RETENTION_ERROR_AFTER_COMMIT"


def test_root_permission_error_after_claim_is_persisted_not_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = []
    monkeypatch.setenv("STORAGE_RETENTION_ENABLED", "1")
    monkeypatch.setenv("STORAGE_RETENTION_APPLY", "1")
    monkeypatch.setenv("STORAGE_RETENTION_FILE_ROOTS", "/denied")
    monkeypatch.setattr(
        "scripts.crawl.run_contracts_90d_pilot._claim_retention_batch",
        lambda *_args, **_kwargs: ("CLAIMED_NEW", "owner", None),
    )
    monkeypatch.setattr(Path, "exists", lambda _self: (_ for _ in ()).throw(PermissionError("denied")))
    monkeypatch.setattr(
        "scripts.crawl.run_contracts_90d_pilot._complete_retention_batch",
        lambda *_args: completed.append(_args[-1]),
    )

    result = _retain_storage_after_durable_batch(
        object(), [{"contrato_id": "abc"}], growth_bytes=100, writer_fence_already_held=True
    )

    assert result and result["status"] == "RETENTION_ERROR_AFTER_COMMIT"
    assert result["error_type"] == "PermissionError"
    assert completed


def test_replay_with_zero_relation_growth_does_not_prune_again(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORAGE_RETENTION_ENABLED", "1")
    called = False

    def should_not_run(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("retention must not run for a zero-growth replay")

    monkeypatch.setattr("scripts.ops.storage_retention.run_retention", should_not_run)
    result = _retain_storage_after_durable_batch(
        object(), [{"contrato_id": "abc"}], growth_bytes=0, writer_fence_already_held=True
    )
    assert result and result["status"] == "NO_PHYSICAL_GROWTH"
    assert called is False


def test_batch_key_distinguishes_new_observation_unit() -> None:
    payload = [{"contrato_id": "abc"}]
    assert _retention_batch_key(payload, "run-1:window:page:1") == _retention_batch_key(
        payload, "run-1:window:page:1"
    )
    assert _retention_batch_key(payload, "run-1:window:page:1") != _retention_batch_key(
        payload, "run-2:window:page:1"
    )


def test_low_space_preflight_attempts_file_cleanup_before_refusal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    free_values = iter((100, 2_000))
    called = {}

    monkeypatch.setenv("STORAGE_RETENTION_APPLY", "1")
    monkeypatch.setenv("STORAGE_RETENTION_LOW_FREE_BYTES", "1000")
    monkeypatch.setenv("STORAGE_RETENTION_SPACE_PATH", str(tmp_path))
    monkeypatch.setenv("STORAGE_RETENTION_FILE_ROOTS", str(tmp_path))
    monkeypatch.setattr(
        "scripts.ops.storage_retention.filesystem_free_bytes", lambda _path: next(free_values)
    )

    def fake_retention(**kwargs):
        called.update(kwargs)
        return FakeReport("SATISFIED")

    monkeypatch.setattr("scripts.ops.storage_retention.run_retention", fake_retention)
    _storage_preflight(object(), [{"contrato_id": "abc"}], writer_fence_already_held=True)
    assert called["apply"] is True
    assert called["history_connection"] is None
    assert called["writer_fence_already_held"] is True


@pytest.mark.parametrize("low_free", [None, "0", "invalid"])
def test_apply_preflight_requires_positive_low_watermark_before_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, low_free: str | None
) -> None:
    monkeypatch.setenv("STORAGE_RETENTION_APPLY", "1")
    monkeypatch.setenv("STORAGE_RETENTION_SPACE_PATH", str(tmp_path))
    if low_free is None:
        monkeypatch.delenv("STORAGE_RETENTION_LOW_FREE_BYTES", raising=False)
    else:
        monkeypatch.setenv("STORAGE_RETENTION_LOW_FREE_BYTES", low_free)
    with pytest.raises(RuntimeError, match="LOW_FREE_BYTES"):
        _storage_preflight(object(), [{"contrato_id": "abc"}], writer_fence_already_held=True)


def test_ledger_migration_is_fail_closed_and_never_deletes_canonical() -> None:
    migration = (
        Path(__file__).parents[1] / "db" / "migrations" / "109_storage_retention_ledger.sql"
    ).read_text(encoding="utf-8")
    assert "storage_retention_ledger" in migration
    assert "lease_expires_at" in migration
    assert "claim_token" in migration
    assert "CLAIMED" in migration
    assert "DELETE FROM public.pncp_supplier_contracts" not in migration


def test_degraded_retention_exit_is_not_retried() -> None:
    calls = 0

    def run() -> int:
        nonlocal calls
        calls += 1
        return EXIT_RETENTION_DEGRADED

    assert run_with_one_retry(run, sleep=lambda _seconds: None) == EXIT_RETENTION_DEGRADED
    assert calls == 1


def test_standalone_pilot_also_exits_nonzero_for_degraded_retention() -> None:
    source = (
        Path(__file__).parents[1] / "scripts" / "crawl" / "run_contracts_90d_pilot.py"
    ).read_text(encoding="utf-8")
    assert '"storage_retention",' in source
    assert 'return EXIT_RETENTION_DEGRADED' in source


@pytest.mark.real_db
def test_retention_ledger_claim_lease_and_owner_fence_real_db() -> None:
    import psycopg2

    from scripts.crawl.run_contracts_90d_pilot import (
        _claim_retention_batch,
        _complete_retention_batch,
    )

    dsn = os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL")
    assert dsn, "LOCAL_DATALAKE_DSN or DATABASE_URL is required for real_db"
    batch_key = f"test-retention-{uuid.uuid4().hex}"
    conn = psycopg2.connect(dsn)
    try:
        state, token, report = _claim_retention_batch(
            conn,
            batch_key=batch_key,
            unit_key="real-db:test-unit",
            transport_bytes=100,
            growth_bytes=80,
        )
        assert state == "CLAIMED_NEW"
        assert token
        assert report is None

        state_again, token_again, report_again = _claim_retention_batch(
            conn,
            batch_key=batch_key,
            unit_key="real-db:test-unit",
            transport_bytes=100,
            growth_bytes=80,
        )
        assert state_again == "CLAIM_IN_PROGRESS"
        assert token_again is None
        assert report_again is None

        _complete_retention_batch(
            conn,
            batch_key,
            token,
            {"status": "SATISFIED", "filesystem_freed_bytes": 80},
        )
        completed_state, completed_token, completed_report = _claim_retention_batch(
            conn,
            batch_key=batch_key,
            unit_key="real-db:test-unit",
            transport_bytes=100,
            growth_bytes=80,
        )
        assert completed_state == "ALREADY_COMPLETED"
        assert completed_token is None
        assert completed_report and completed_report["status"] == "SATISFIED"
        with pytest.raises(RuntimeError, match="lost claim ownership"):
            _complete_retention_batch(
                conn,
                batch_key,
                token,
                {"status": "SATISFIED", "filesystem_freed_bytes": 80},
            )
    finally:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM public.storage_retention_ledger WHERE batch_key = %s",
                (batch_key,),
            )
        conn.commit()
        conn.close()


@pytest.mark.real_db
def test_canonical_retention_deletes_only_cold_completed_contract_and_cascades_role_real_db() -> None:
    import psycopg2
    from psycopg2 import sql

    from scripts.ops.storage_retention import RetentionError, reclaim_canonical_contracts

    dsn = os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL")
    assert dsn, "LOCAL_DATALAKE_DSN or DATABASE_URL is required for real_db"
    if os.getenv("ALLOW_DESTRUCTIVE_REAL_DB_TESTS") != "1":
        pytest.skip("set ALLOW_DESTRUCTIVE_REAL_DB_TESTS=1 on an isolated test database")
    suffix = uuid.uuid4().hex
    contract_id = f"test-retention-cold-{suffix}"
    active_id = f"test-retention-active-{suffix}"
    hot_id = f"test-retention-hot-{suffix}"
    guard_trigger = f"test_retention_trigger_{suffix}"
    guard_function = f"test_retention_function_{suffix}"
    guard_table = f"test_retention_fk_{suffix}"
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO public.pncp_supplier_contracts (
                    contrato_id, source, data_publicacao, data_inicio, data_fim,
                    ingested_at, first_seen_at, last_seen_at, source_updated_at
                ) VALUES
                    (%s, 'retention-real-db', DATE '1900-01-01', DATE '1900-01-01',
                     DATE '1900-01-02', TIMESTAMPTZ '1900-01-03 00:00:00+00',
                     TIMESTAMPTZ '1900-01-03 00:00:00+00',
                     TIMESTAMPTZ '1900-01-03 00:00:00+00',
                     TIMESTAMPTZ '1900-01-03 00:00:00+00'),
                    (%s, 'retention-real-db', DATE '1900-01-01', DATE '1900-01-01',
                     NULL, TIMESTAMPTZ '1900-01-03 00:00:00+00',
                     TIMESTAMPTZ '1900-01-03 00:00:00+00',
                     TIMESTAMPTZ '1900-01-03 00:00:00+00',
                     TIMESTAMPTZ '1900-01-03 00:00:00+00'),
                    (%s, 'retention-real-db', DATE '2026-01-01', DATE '2026-01-01',
                     DATE '2026-01-02', TIMESTAMPTZ '2026-01-03 00:00:00+00',
                     TIMESTAMPTZ '2026-01-03 00:00:00+00',
                     TIMESTAMPTZ '2026-01-03 00:00:00+00',
                     TIMESTAMPTZ '2026-01-03 00:00:00+00')
                """,
                (contract_id, active_id, hot_id),
            )
            cursor.execute(
                """
                INSERT INTO public.contract_role_links (
                    contract_id, buyer_entity_id, supplier_identity_id,
                    buyer_match_method, buyer_match_confidence, buyer_reason_codes,
                    supplier_match_method, supplier_match_confidence, supplier_reason_codes,
                    match_run_id, snapshot_id
                ) VALUES (%s, NULL, NULL, 'unresolved', 0, '{}',
                          'unresolved', 0, '{}', 'retention-test', 'retention-test')
                ON CONFLICT (contract_id) DO UPDATE SET match_run_id = EXCLUDED.match_run_id
                """,
                (contract_id,),
            )
        conn.commit()

        rows, reusable, vacuumed = reclaim_canonical_contracts(
            conn,
            target_bytes=1,
            cutoff=datetime(2000, 1, 1, tzinfo=UTC),
            batch_rows=1,
            max_rows=1,
            apply=True,
        )
        assert rows == 1
        assert reusable > 0
        assert vacuumed is True
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM public.pncp_supplier_contracts WHERE contrato_id = %s",
                (contract_id,),
            )
            assert cursor.fetchone() == (0,)
            cursor.execute(
                "SELECT COUNT(*) FROM public.contract_role_links WHERE contract_id = %s",
                (contract_id,),
            )
            assert cursor.fetchone() == (0,)
            cursor.execute(
                "SELECT contrato_id FROM public.pncp_supplier_contracts WHERE contrato_id IN (%s, %s)",
                (active_id, hot_id),
            )
            assert {row[0] for row in cursor.fetchall()} == {active_id, hot_id}

            cursor.execute(
                sql.SQL(
                    "CREATE FUNCTION public.{}() RETURNS trigger LANGUAGE plpgsql "
                    "AS $$ BEGIN RETURN OLD; END $$"
                ).format(sql.Identifier(guard_function))
            )
            cursor.execute(
                sql.SQL(
                    "CREATE TRIGGER {} BEFORE DELETE ON public.pncp_supplier_contracts "
                    "FOR EACH ROW EXECUTE FUNCTION public.{}()"
                ).format(sql.Identifier(guard_trigger), sql.Identifier(guard_function))
            )
        conn.commit()
        with pytest.raises(RetentionError, match="unexpected user triggers"):
            reclaim_canonical_contracts(
                conn,
                target_bytes=1,
                cutoff=datetime(2000, 1, 1, tzinfo=UTC),
                batch_rows=1,
                max_rows=1,
                apply=False,
            )
        with conn.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP TRIGGER {} ON public.pncp_supplier_contracts").format(
                    sql.Identifier(guard_trigger)
                )
            )
            cursor.execute(
                sql.SQL("DROP FUNCTION public.{}()").format(sql.Identifier(guard_function))
            )
            cursor.execute(
                sql.SQL(
                    "CREATE TABLE public.{} (contract_id text REFERENCES "
                    "public.pncp_supplier_contracts(contrato_id))"
                ).format(sql.Identifier(guard_table))
            )
        conn.commit()
        with pytest.raises(RetentionError, match="expected exactly contract_role_links"):
            reclaim_canonical_contracts(
                conn,
                target_bytes=1,
                cutoff=datetime(2000, 1, 1, tzinfo=UTC),
                batch_rows=1,
                max_rows=1,
                apply=False,
            )
    finally:
        with conn.cursor() as cursor:
            cursor.execute(sql.SQL("DROP TABLE IF EXISTS public.{} CASCADE").format(sql.Identifier(guard_table)))
            cursor.execute(
                sql.SQL("DROP TRIGGER IF EXISTS {} ON public.pncp_supplier_contracts").format(
                    sql.Identifier(guard_trigger)
                )
            )
            cursor.execute(
                sql.SQL("DROP FUNCTION IF EXISTS public.{}()").format(sql.Identifier(guard_function))
            )
            cursor.execute(
                "DELETE FROM public.pncp_supplier_contracts WHERE contrato_id = ANY(%s)",
                ([contract_id, active_id, hot_id],),
            )
        conn.commit()
        conn.close()
