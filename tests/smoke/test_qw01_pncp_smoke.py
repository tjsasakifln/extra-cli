"""Opt-in real PNCP smoke for the QW-01 open-proposals endpoint."""

from __future__ import annotations

import os
from datetime import date

import pytest

from scripts.lib.universe import load_canonical_universe
from scripts.opportunity_intel.pncp_audit import run_pncp_open_monitoring

pytestmark = [pytest.mark.smoke, pytest.mark.slow]


def test_pncp_open_monitoring_smoke_is_fail_closed() -> None:
    if os.getenv("RUN_QW01_SMOKE") != "1":
        pytest.skip("Set RUN_QW01_SMOKE=1 to call the real PNCP endpoint")

    outcome = run_pncp_open_monitoring(
        dsn="postgresql://unused",
        external_run_id="qw01-smoke-no-persist",
        universe=load_canonical_universe(),
        period_start=date.today(),
        period_end=date.today(),
        mode="dry-run",
        max_pages=1,
        max_records=1,
        persist=False,
        timeout=20,
        max_retries=0,
        request_delay=0.0,
    )

    assert len(outcome.scopes) == 19
    assert outcome.status in {"completed", "completed_zero", "partial", "failed"}
    if not outcome.scope_complete:
        assert outcome.status in {"partial", "failed"}
        assert outcome.status != "completed_zero"
