"""Contracts crawler per-window persist helper."""
from __future__ import annotations

import os

from scripts.crawl.contracts_crawler import _persist_window_if_enabled


def test_persist_disabled_returns_zero(monkeypatch):
    monkeypatch.setenv("CONTRACTS_PERSIST_EACH_WINDOW", "0")
    assert _persist_window_if_enabled([{"foo": 1}]) == 0


def test_persist_without_dsn_returns_zero(monkeypatch):
    monkeypatch.setenv("CONTRACTS_PERSIST_EACH_WINDOW", "1")
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert _persist_window_if_enabled([{"foo": 1}]) == 0


def test_persist_empty_items_returns_zero(monkeypatch):
    monkeypatch.setenv("CONTRACTS_PERSIST_EACH_WINDOW", "1")
    monkeypatch.setenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test")
    assert _persist_window_if_enabled([]) == 0
