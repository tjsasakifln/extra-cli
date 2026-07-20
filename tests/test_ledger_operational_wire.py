"""Ledger is invoked from operational entrypoints (not only cycle1)."""
from __future__ import annotations

from pathlib import Path
from unittest import mock

from scripts.ops import crawler_monitor


def test_crawler_monitor_writes_ledger(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # seed empty ledger dir under tmp
    from scripts.ops import run_execution_ledger as led

    monkeypatch.setattr(led, "DEFAULT_LEDGER_DIR", Path("output") / "run-execution-ledger")
    # run monitor with demo data
    code = crawler_monitor.main(["--seed-demo"])
    assert code == 0
    rows = led.load_ledger(tmp_path)
    assert any((r.get("meta") or {}).get("entrypoint") == "crawler_monitor" for r in rows)
    assert all("errors" in r for r in rows)
