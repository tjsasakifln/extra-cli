"""Real-DB preflight: no MagicMock, explicit skip/fail, schema before SQL."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from scripts.national_claims.gate import decide
from scripts.national_claims.loader import request_from_dict
from scripts.national_claims.preflight import (
    REQUIRED_TABLES,
    admit_or_raise,
    inspect_national_claims_schema,
    live_not_executed_payload,
    live_smoke_command,
    probe_national_claims,
)
from scripts.national_claims.sample_fixtures import fixture_needs_data
from scripts.national_claims.store import StoreError, persist_decision


def test_magic_mock_is_not_postgresql() -> None:
    result = probe_national_claims(
        "postgresql://test:test@127.0.0.1:5433/extra_test",
        require_real=False,
        opener=lambda *_args, **_kwargs: MagicMock(),
    )
    assert result["outcome"] in {"skip", "fail"}
    assert "MagicMock" in result["reason"]
    with pytest.raises(RuntimeError, match="MagicMock"):
        inspect_national_claims_schema(MagicMock())
    with pytest.raises(StoreError, match="MagicMock"):
        persist_decision(
            MagicMock(),
            request_from_dict(fixture_needs_data()),
            decide(request_from_dict(fixture_needs_data())),
        )


def test_absent_dsn_is_explicit_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("NATIONAL_CLAIMS_DSN", raising=False)
    monkeypatch.delenv("REQUIRE_REAL_DB", raising=False)

    def _raise(_dsn: str, **_kwargs):
        raise ConnectionError("refused")

    result = probe_national_claims(require_real=False, opener=_raise)
    assert result["outcome"] == "skip"
    assert "unreachable" in result["reason"]


def test_required_dsn_unreachable_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQUIRE_REAL_DB", "1")

    def _raise(_dsn: str, **_kwargs):
        raise ConnectionError("refused")

    result = probe_national_claims(
        "postgresql://test:test@127.0.0.1:1/missing",
        require_real=True,
        opener=_raise,
    )
    assert result["outcome"] == "fail"
    assert "unreachable" in result["reason"]


def test_dsn_without_schema_fails_before_business_sql() -> None:
    class _Cursor:
        def execute(self, sql: str, params=None) -> None:
            assert "information_schema.tables" in sql
            assert "national_claims_decision" not in sql or "information_schema" in sql
            self._row = (False,)

        def fetchone(self):
            return self._row

        def close(self) -> None:
            return None

    class _Conn:
        def cursor(self) -> _Cursor:
            return _Cursor()

        def close(self) -> None:
            return None

    result = probe_national_claims(
        "postgresql://test:test@127.0.0.1:5433/extra_test",
        require_real=True,
        opener=lambda *_args, **_kwargs: _Conn(),
    )
    assert result["outcome"] == "fail"
    assert "schema missing" in result["reason"]
    assert set(result["missing_tables"]) == set(REQUIRED_TABLES)


def test_admit_skip_uses_pytest_skip() -> None:
    with pytest.raises(pytest.skip.Exception, match="national_claims preflight"):
        admit_or_raise(
            {
                "outcome": "skip",
                "reason": "national_claims preflight: database unreachable at localhost",
            }
        )


def test_live_not_executed_payload_names_smoke_command() -> None:
    payload = live_not_executed_payload(
        reason="host dataset not reachable",
        smoke_command=live_smoke_command(),
    )
    assert payload["LIVE_NOT_EXECUTED"] is True
    assert "apply_migrations" in payload["live_smoke_command"]
    assert payload["pii"] is False
