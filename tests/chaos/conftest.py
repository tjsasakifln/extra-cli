"""Shared fault injection fixtures for chaos tests."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


class FaultInjector:
    """Simulates HTTP and network failures for chaos testing."""

    def __init__(self):
        self.calls: list[dict] = []
        self._mode = "pass"  # pass, fail_all, fail_once, slow

    def set_mode(self, mode: str):
        self._mode = mode

    def inject(self, url: str = "", **kwargs) -> MagicMock:
        self.calls.append({"url": url, **kwargs})
        if self._mode == "fail_all":
            raise ConnectionError("Simulated connection failure")
        if self._mode == "fail_once" and len(self.calls) == 1:
            raise TimeoutError("Simulated timeout")
        mock = MagicMock()
        mock.status = 200
        mock.read.return_value = json.dumps({"data": [], "totalRegistros": 0}).encode()
        return mock


@pytest.fixture
def fault_injector():
    """Fixture providing a FaultInjector instance."""
    return FaultInjector()


@pytest.fixture
def patch_urllib_request(fault_injector):
    """Patch urllib.request.urlopen with fault injector."""
    with patch("urllib.request.urlopen", side_effect=fault_injector.inject):
        yield fault_injector


@pytest.fixture
def mock_dlq():
    """Fixture providing a mock DLQ for testing."""
    with patch("scripts.crawl.dlq_sync.dlq_write") as mock:
        mock.return_value = 1
        yield mock
