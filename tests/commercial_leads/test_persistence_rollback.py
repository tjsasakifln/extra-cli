"""Persistence fail-closed: partial insert must not leave orphan leads."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from scripts.commercial_leads.pipeline import persist_run
from scripts.commercial_leads.profile import load_profile
from pathlib import Path


class _BoomCursor:
    def __init__(self, fail_on_lead: int = 11):
        self.n_leads = 0
        self.fail_on_lead = fail_on_lead
        self.statements: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.statements.append(sql.strip().split()[0:3])
        sql_l = sql.lower()
        if "insert into commercial_leads" in sql_l:
            self.n_leads += 1
            if self.n_leads >= self.fail_on_lead:
                raise RuntimeError("simulated failure on 11th lead")


class _BoomConn:
    def __init__(self):
        self.cursor_obj = _BoomCursor(fail_on_lead=11)
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def test_persist_run_raises_before_commit_on_mid_insert_failure() -> None:
    """Run insert + 10 leads OK; exception on 11th → no commit (caller rolls back)."""
    profile = load_profile(Path("config/commercial_profiles/confenge.yaml"))
    leads = [
        {
            "cnpj14": f"{i:014d}",
            "razao_social": f"EMPRESA {i}",
            "score_total": float(i),
            "priority": "MEDIUM",
            "score_decomposition": {},
            "signals_fired": [],
            "signals_not_computable": [],
            "evidence": [],
            "suggested_offer": None,
            "next_human_step": None,
            "limitations": [],
            "commercial_state": "NEW",
            "rank_position": i,
        }
        for i in range(1, 15)
    ]
    conn = _BoomConn()
    with pytest.raises(RuntimeError, match="simulated failure"):
        persist_run(
            conn,
            run_id="test-run-partial",
            profile=profile,
            snapshot_hash="abc",
            snapshot_manifest={},
            status="PASS",
            leads=leads,
            exclusions=[],
            metrics={"eligible_companies": 15},
            git="deadbeef",
        )
    assert conn.committed is False
    # 1 run insert + 10 successful lead inserts then boom on 11
    assert conn.cursor_obj.n_leads == 11
