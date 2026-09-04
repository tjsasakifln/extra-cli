"""Real Postgres: PNCP health is not the commercial abort; Data Lake gates are.

No PNCP network, no publication, no provider, no SMTP. Source-health status is
an input envelope, never mocked into PASS.
"""

from __future__ import annotations

import os
import uuid

import pytest

from scripts.confenge_outreach_pipeline.pipeline import _published_target_fit_snapshot
from scripts.confenge_target_fit.db import connect
from scripts.confenge_target_fit.store import set_control

DSN = os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL")

pytestmark = [
    pytest.mark.real_db,
    pytest.mark.skipif(
        not DSN,
        reason="LOCAL_DATALAKE_DSN not set — skipping Postgres plane-separation tests",
    ),
]


def _apply_migration() -> None:
    import subprocess
    import sys
    from pathlib import Path

    subprocess.check_call(
        [sys.executable, "-m", "scripts.ops.apply_migrations", "--dsn", DSN],
        cwd=str(Path(__file__).resolve().parents[2]),
    )


@pytest.fixture(scope="module")
def dsn() -> str:
    _apply_migration()
    assert DSN
    return DSN


def _envelope(status: str, *, reason: str, fresh_observed: bool = False) -> dict[str, object]:
    payload: dict[str, object] = {
        "contract_version": "PNCP_CONTRACT_FRESHNESS/1.0",
        "status": status,
        "reason_codes": [reason],
        "run_id": f"test-plane-{status.lower()}",
    }
    if fresh_observed:
        payload["source_observed_at"] = "2026-08-25T02:00:00+00:00"
    return payload


def _seed(conn, *, coverage_ratio: float, unexplained: int, pagination: bool) -> None:
    set_control(conn, "async_mode", {"mode": "ACTIVE"})
    set_control(
        conn,
        "cdc_watermark",
        {"watermark": "2026-08-24T03:26:43+00:00", "observed_at": "2026-08-24T03:26:43+00:00"},
    )
    set_control(
        conn,
        "target_fit_coverage",
        {
            "coverage_ratio": coverage_ratio,
            "pagination_exhausted_normally": pagination,
            "last_full_reconcile_unexplained_missing": unexplained,
            "last_full_reconcile_completed_at": "2026-08-25T02:45:00+00:00",
        },
    )
    raiz = "11222333"
    key = f"cnpj_root:{raiz}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO confenge_company_target_fit_current (
                company_key, cnpj_raiz, target_fit_class, target_fit_confidence,
                target_fit_version, computed_at, source_watermark, input_fingerprint,
                materialization_mode
            ) VALUES (%s, %s, 'TARGET_CONFIRMED', 1.0, 'confenge-target-fit-v3', now(), %s, %s, 'ACTIVE')
            ON CONFLICT (company_key) DO UPDATE
            SET source_watermark = EXCLUDED.source_watermark,
                target_fit_class = EXCLUDED.target_fit_class
            """,
            (key, raiz, "2026-08-24T03:26:43+00:00", f"fp-{uuid.uuid4().hex}"),
        )
    conn.commit()


@pytest.mark.parametrize(
    "status,reason",
    [
        ("STALE", "SOURCE_WINDOW_NOT_CLOSED"),
        ("UNKNOWN", "PNCP_TELEMETRY_UNAVAILABLE"),
        ("UNKNOWN", "HTTP_503"),
    ],
)
def test_valid_datalake_does_not_abort_on_non_fresh_source(dsn: str, status: str, reason: str) -> None:
    conn = connect(dsn, readonly=False)
    try:
        _seed(conn, coverage_ratio=1.0, unexplained=0, pagination=True)
    finally:
        conn.close()

    snapshot, authority, _watermark = _published_target_fit_snapshot(
        [{"cnpj14": "11222333000181"}],
        dsn=dsn,
        authoritative_source_freshness=_envelope(status, reason=reason),
    )
    assert authority == "published_target_fit_store"
    assert snapshot
    assert snapshot[0]["cnpj_raiz"] == "11222333"
    # Envelope was not rewritten to FRESH.
    assert _envelope(status, reason=reason)["status"] == status


def test_invalid_datalake_fails_closed_even_when_source_is_fresh(dsn: str) -> None:
    conn = connect(dsn, readonly=False)
    try:
        _seed(conn, coverage_ratio=0.5, unexplained=12, pagination=False)
    finally:
        conn.close()

    with pytest.raises(ValueError, match="target-fit national coverage is incomplete"):
        _published_target_fit_snapshot(
            [{"cnpj14": "11222333000181"}],
            dsn=dsn,
            authoritative_source_freshness=_envelope(
                "FRESH",
                reason="WINDOW_CLOSED",
                fresh_observed=True,
            ),
        )
