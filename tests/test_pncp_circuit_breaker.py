"""Tests for the PNCP circuit breaker wrapper (CM-06 AC-4).

Verifies that ``scripts.crawl.clients.pncp.circuit_breaker`` properly
delegates to the real ``PNCPCircuitBreaker`` and falls back to the stub
when the real implementation is unavailable.

Uses sys.modules patching to avoid importing the real circuit_breaker
module (which depends on an unavailable ``metrics`` package).
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from scripts.crawl.clients.pncp.circuit_breaker import (
    _circuit_breaker,
    _RealCircuitBreaker,
    _StubCircuitBreaker,
)


@pytest.fixture
def mock_real_cb_module():
    """Inject a mock ``scripts.crawl.circuit_breaker`` module into sys.modules.

    This avoids the real import which fails due to ``from metrics import ...``.
    The mock module exposes ``get_circuit_breaker`` as a callable.
    """
    mock_module = MagicMock()
    mock_module.get_circuit_breaker = MagicMock(return_value=MagicMock())
    mock_module.get_circuit_breaker.return_value.is_degraded = False

    with patch.dict(sys.modules, {"scripts.crawl.circuit_breaker": mock_module}):
        yield mock_module


class TestRealCircuitBreaker:
    """Tests for _RealCircuitBreaker — delegation to real implementation."""

    def test_is_degraded_delegates_to_real_breaker(
        self, mock_real_cb_module
    ) -> None:
        """is_degraded property delegates to the real breaker's is_degraded."""
        wrapper = _RealCircuitBreaker()
        result = wrapper.is_degraded

        assert result is False
        mock_real_cb_module.get_circuit_breaker.assert_called_once_with("pncp")

    def test_record_success_delegates_with_loop_running(
        self, mock_real_cb_module
    ) -> None:
        """record_success creates a task on the running event loop."""
        mock_real = MagicMock()
        mock_real_cb_module.get_circuit_breaker.return_value = mock_real

        with patch("asyncio.get_event_loop") as mock_get_loop:
            mock_loop = MagicMock()
            mock_loop.is_running.return_value = True
            mock_get_loop.return_value = mock_loop

            wrapper = _RealCircuitBreaker()
            wrapper.record_success()

            mock_loop.create_task.assert_called_once_with(
                mock_real.record_success()
            )

    def test_record_failure_delegates_with_loop_running(
        self, mock_real_cb_module
    ) -> None:
        """record_failure creates a task on the running event loop."""
        mock_real = MagicMock()
        mock_real_cb_module.get_circuit_breaker.return_value = mock_real

        with patch("asyncio.get_event_loop") as mock_get_loop:
            mock_loop = MagicMock()
            mock_loop.is_running.return_value = True
            mock_get_loop.return_value = mock_loop

            wrapper = _RealCircuitBreaker()
            wrapper.record_failure()

            mock_loop.create_task.assert_called_once_with(
                mock_real.record_failure()
            )

    def test_try_recover_delegates_with_loop_running(
        self, mock_real_cb_module
    ) -> None:
        """try_recover creates a task on the running event loop."""
        mock_real = MagicMock()
        mock_real_cb_module.get_circuit_breaker.return_value = mock_real

        with patch("asyncio.get_event_loop") as mock_get_loop:
            mock_loop = MagicMock()
            mock_loop.is_running.return_value = True
            mock_get_loop.return_value = mock_loop

            wrapper = _RealCircuitBreaker()
            wrapper.try_recover()

            mock_loop.create_task.assert_called_once_with(
                mock_real.try_recover()
            )

    def test_runs_sync_when_loop_not_running(
        self, mock_real_cb_module
    ) -> None:
        """When no loop is running, run_until_complete is used."""
        mock_real = MagicMock()
        mock_real.record_success = MagicMock()
        mock_real_cb_module.get_circuit_breaker.return_value = mock_real

        with patch("asyncio.get_event_loop") as mock_get_loop:
            mock_loop = MagicMock()
            mock_loop.is_running.return_value = False
            mock_get_loop.return_value = mock_loop

            wrapper = _RealCircuitBreaker()
            wrapper.record_success()

            mock_loop.run_until_complete.assert_called_once_with(
                mock_real.record_success()
            )

    def test_real_breaker_cached_after_first_call(
        self, mock_real_cb_module
    ) -> None:
        """_ensure_breaker only calls get_circuit_breaker once."""
        wrapper = _RealCircuitBreaker()

        # First call triggers _ensure_breaker
        _ = wrapper.is_degraded
        # Second call should NOT re-import
        _ = wrapper.is_degraded

        assert mock_real_cb_module.get_circuit_breaker.call_count == 1


class TestStubCircuitBreaker:
    """Tests for _StubCircuitBreaker — fallback when real breaker unavailable."""

    def test_stub_is_never_degraded(self) -> None:
        """Stub circuit breaker always reports is_degraded as False."""
        stub = _StubCircuitBreaker()
        assert stub.is_degraded is False

    def test_stub_record_success_does_not_raise(self) -> None:
        """record_success on stub should not raise any exception."""
        stub = _StubCircuitBreaker()

        import asyncio

        asyncio.run(stub.record_success())

    def test_stub_record_failure_does_not_raise(self) -> None:
        """record_failure on stub should not raise any exception."""
        stub = _StubCircuitBreaker()

        import asyncio

        asyncio.run(stub.record_failure())

    def test_stub_try_recover_does_not_raise(self) -> None:
        """try_recover on stub should not raise any exception."""
        stub = _StubCircuitBreaker()

        import asyncio

        asyncio.run(stub.try_recover())


class TestCircuitBreakerFallback:
    """Tests for stub fallback when real breaker unavailable."""

    def test_import_error_triggers_stub_fallback(
        self, mock_real_cb_module
    ) -> None:
        """When get_circuit_breaker raises, the wrapper falls back to stub."""
        mock_real_cb_module.get_circuit_breaker.side_effect = ImportError(
            "no module"
        )

        wrapper = _RealCircuitBreaker()
        assert wrapper.is_degraded is False

    def test_stub_fallback_never_raises_on_operations(
        self, mock_real_cb_module
    ) -> None:
        """Stub fallback handles all operations without raising."""
        mock_real_cb_module.get_circuit_breaker.side_effect = ImportError(
            "no module"
        )

        wrapper = _RealCircuitBreaker()

        # is_degraded should work
        assert wrapper.is_degraded is False

        # record_success should not raise
        wrapper.record_success()

        # record_failure should not raise
        wrapper.record_failure()

        # try_recover should not raise
        wrapper.try_recover()

    def test_module_level_singleton_is_real_circuit_breaker(self) -> None:
        """The module-level _circuit_breaker is a _RealCircuitBreaker instance."""
        assert isinstance(_circuit_breaker, _RealCircuitBreaker)
