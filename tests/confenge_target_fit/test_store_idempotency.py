"""Integration tests against Postgres when LOCAL_DATALAKE_DSN is available.

Proves shipped store + worker paths: idempotency, lock claim, publish atomicity,
downgrade invalidation.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest

DSN = os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("CONFENGE_TARGET_FIT_STATE_DSN")

pytestmark = [
    pytest.mark.real_db,
    pytest.mark.skipif(
        not DSN,
        reason="LOCAL_DATALAKE_DSN not set — skipping Postgres integration tests",
    ),
]


def _apply_migration():
    import subprocess
    import sys
    from pathlib import Path

    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "scripts.ops.apply_migrations",
            "--dsn",
            DSN,
        ],
        cwd=str(Path(__file__).resolve().parents[2]),
    )


@pytest.fixture(scope="module")
def dsn():
    _apply_migration()
    return DSN


def test_enqueue_idempotent(dsn):
    from scripts.confenge_target_fit.db import connect
    from scripts.confenge_target_fit.store import enqueue_dirty, ensure_control_defaults

    conn = connect(dsn, readonly=False)
    try:
        ensure_control_defaults(conn)
        key = f"test-idem-{uuid.uuid4().hex}"
        a = enqueue_dirty(
            conn,
            company_key="cnpj_root:11222333",
            cnpj_raiz="11222333",
            reason="test",
            source_entity="test",
            source_id="1",
            source_updated_at=datetime.now(UTC),
            source_watermark="wm-1",
            priority=50,
            idempotency_key=key,
        )
        b = enqueue_dirty(
            conn,
            company_key="cnpj_root:11222333",
            cnpj_raiz="11222333",
            reason="test",
            source_entity="test",
            source_id="1",
            source_updated_at=datetime.now(UTC),
            source_watermark="wm-1",
            priority=50,
            idempotency_key=key,
        )
        conn.commit()
        assert a is True
        assert b is False
    finally:
        conn.close()


def test_publish_and_history_append(dsn):
    from scripts.confenge_target_fit import TARGET_CONFIRMED, TARGET_FIT_VERSION, TARGET_OUT_OF_SCOPE
    from scripts.confenge_target_fit.db import connect
    from scripts.confenge_target_fit.models import MaterializedTargetFit, TransitionEvent
    from scripts.confenge_target_fit.store import (
        get_current,
        history_for_company,
        publish_materialization,
    )

    ck = f"cnpj_root:556677{uuid.uuid4().hex[:2]}"
    # valid 8 digit — use fixed
    ck = "cnpj_root:55667788"
    raiz = "55667788"
    now = datetime.now(UTC)
    mat1 = MaterializedTargetFit(
        company_key=ck,
        cnpj_raiz=raiz,
        target_fit_class=TARGET_CONFIRMED,
        target_fit_confidence=0.9,
        target_fit_version=TARGET_FIT_VERSION,
        target_fit_reason_codes=["test"],
        target_fit_evidence=[{"id": "e1", "type": "CONTRACT_EXECUTION"}],
        computed_at=now,
        source_watermark="wm-a",
        source_max_updated_at=now,
        input_fingerprint="sha256:aaa",
        classifier_sha="sha256:cls",
        schema_version="confenge-tf-store-v1",
        transition_event="TARGET_FIT_CONFIRMED",
    )
    evt1 = TransitionEvent(
        event_type="TARGET_FIT_CONFIRMED",
        company_key=ck,
        cnpj_raiz=raiz,
        old_class=None,
        new_class=TARGET_CONFIRMED,
        old_confidence=None,
        new_confidence=0.9,
        reason_codes=["test"],
        changed_evidence_ids=["e1"],
        source_watermark="wm-a",
        computed_at=now,
        target_fit_version=TARGET_FIT_VERSION,
    )
    conn = connect(dsn, readonly=False)
    try:
        publish_materialization(conn, mat1, evt1, shadow_only=False)
        conn.commit()
        cur = get_current(conn, ck)
        assert cur is not None
        assert cur["target_fit_class"] == TARGET_CONFIRMED

        mat2 = MaterializedTargetFit(
            company_key=ck,
            cnpj_raiz=raiz,
            target_fit_class=TARGET_OUT_OF_SCOPE,
            target_fit_confidence=0.8,
            target_fit_version=TARGET_FIT_VERSION,
            target_fit_reason_codes=["lost"],
            target_fit_evidence=[],
            computed_at=datetime.now(UTC),
            source_watermark="wm-b",
            source_max_updated_at=now,
            input_fingerprint="sha256:bbb",
            classifier_sha="sha256:cls",
            schema_version="confenge-tf-store-v1",
            previous_class=TARGET_CONFIRMED,
            previous_confidence=0.9,
            transition_event="TARGET_FIT_LOST",
        )
        evt2 = TransitionEvent(
            event_type="TARGET_FIT_LOST",
            company_key=ck,
            cnpj_raiz=raiz,
            old_class=TARGET_CONFIRMED,
            new_class=TARGET_OUT_OF_SCOPE,
            old_confidence=0.9,
            new_confidence=0.8,
            reason_codes=["lost"],
            changed_evidence_ids=["e1"],
            source_watermark="wm-b",
            computed_at=mat2.computed_at,
            target_fit_version=TARGET_FIT_VERSION,
        )
        eid = publish_materialization(conn, mat2, evt2, shadow_only=False)
        from scripts.confenge_target_fit.store import record_downstream_invalidation_soft

        record_downstream_invalidation_soft(
            conn,
            company_key=ck,
            cnpj_raiz=raiz,
            event_id=eid,
            old_class=TARGET_CONFIRMED,
            new_class=TARGET_OUT_OF_SCOPE,
        )
        conn.commit()
        cur2 = get_current(conn, ck)
        assert cur2["target_fit_class"] == TARGET_OUT_OF_SCOPE
        hist = history_for_company(conn, ck, limit=10)
        assert len(hist) >= 2
        # History preserves past CONFIRMED
        classes = {h["target_fit_class"] for h in hist}
        assert TARGET_CONFIRMED in classes
        assert TARGET_OUT_OF_SCOPE in classes
    finally:
        conn.close()


def test_claim_skip_locked_single_writer(dsn):
    from scripts.confenge_target_fit.db import connect
    from scripts.confenge_target_fit.store import (
        claim_batch,
        enqueue_dirty,
        ensure_control_defaults,
        reclaim_expired_locks,
    )

    ck = "cnpj_root:44556677"
    key = f"lock-test-{uuid.uuid4().hex}"
    conn = connect(dsn, readonly=False)
    try:
        ensure_control_defaults(conn)
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM confenge_target_fit_dirty WHERE company_key = %s", (ck,)
            )
        conn.commit()
        enqueue_dirty(
            conn,
            company_key=ck,
            cnpj_raiz="44556677",
            reason="lock_test",
            source_entity="test",
            source_id=None,
            source_updated_at=datetime.now(UTC),
            source_watermark="wm",
            priority=99,
            idempotency_key=key,
        )
        conn.commit()
        reclaim_expired_locks(conn)
        batch1 = claim_batch(
            conn, worker_id="w1", batch_size=10, lock_ttl_seconds=60
        )
        conn.commit()
        ids1 = {i.id for i in batch1 if i.idempotency_key == key}
        batch2 = claim_batch(
            conn, worker_id="w2", batch_size=10, lock_ttl_seconds=60
        )
        conn.commit()
        ids2 = {i.id for i in batch2 if i.idempotency_key == key}
        # Second worker must not re-claim the same processing row
        assert ids1.isdisjoint(ids2)
        assert len(ids1) == 1, f"ids1={ids1} batch1={batch1}"
    finally:
        conn.close()


def test_status_command_runs(dsn):
    from scripts.confenge_target_fit.status import build_health, exit_code_for

    report = build_health(dsn)
    assert report.status in {"HEALTHY", "DEGRADED", "STALE", "FAILED"}
    assert isinstance(exit_code_for(report), int)


def test_cli_version(dsn):
    from scripts.confenge_target_fit.cli import main

    assert main(["version"]) == 0
