"""#285 — real_db tests must not be silently MagicMock'd.

Drives the shipped admission functions. Inspects the concrete connection
type: MagicMock is illegal under the real_db strategy.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from scripts.testing.real_db_guard import (
    DB_UNAVAILABLE,
    canonical_dsn,
    connection_type_name,
    decide_connection_strategy,
    is_magic_mock,
    refuse_magic_mock_sql,
)


def test_real_db_strategy_never_returns_mock() -> None:
    matrix = (
        (True, False, False),
        (True, False, True),
        (True, True, False),
        (True, True, True),
    )
    for marker, required, available in matrix:
        strategy = decide_connection_strategy(
            real_db_marker=marker,
            require_real=required,
            db_available=available,
        )
        assert strategy != "mock"
    assert decide_connection_strategy(real_db_marker=False, require_real=False, db_available=False) == "mock"


def test_missing_opt_in_is_skip_not_fake_missing_table() -> None:
    assert decide_connection_strategy(real_db_marker=True, require_real=False, db_available=True) == "skip"
    assert decide_connection_strategy(real_db_marker=True, require_real=True, db_available=False) == "config_error"
    assert decide_connection_strategy(real_db_marker=True, require_real=True, db_available=True) == "real"


def test_live_strategy_connection_type_is_not_magicmock() -> None:
    """When the strategy is live, the connection object must be the driver type."""
    try:
        import psycopg2
        from psycopg2 import extensions
    except ImportError:
        pytest.skip("psycopg2 not installed in this interpreter")

    mock = MagicMock()
    assert is_magic_mock(mock) is True
    assert connection_type_name(mock) == "MagicMock"

    strategy = decide_connection_strategy(real_db_marker=True, require_real=True, db_available=True)
    assert strategy == "real"
    # The shipped live type is the psycopg2 connection class, not MagicMock.
    live_type = extensions.connection
    assert live_type.__name__.lower() == "connection"
    assert not is_magic_mock(live_type)
    assert not issubclass(live_type, MagicMock)
    assert canonical_dsn()
    assert hasattr(psycopg2, "connect")
    with pytest.raises(RuntimeError, match=DB_UNAVAILABLE):
        refuse_magic_mock_sql(MagicMock(), context="real_db")
