"""DoD §23 host monitor — disk/mem/load + journald config + optional PG."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.ops.host_monitor import (
    JOURNALD_CONF,
    check_disk,
    check_journald_config,
    check_load,
    check_memory,
    collect_host_report,
)


def test_journald_config_present() -> None:
    r = check_journald_config()
    assert r.status in {"ok", "configured"}
    assert JOURNALD_CONF.is_file()
    text = JOURNALD_CONF.read_text(encoding="utf-8")
    assert "SystemMaxUse=" in text
    assert "MaxRetentionSec=" in text


def test_disk_memory_load_reportable() -> None:
    d = check_disk("/")
    assert d.status in {"ok", "warn", "crit", "unknown"}
    assert "used_pct" in d.metrics or d.status == "unknown"
    m = check_memory()
    assert m.status in {"ok", "warn", "unknown"}
    load = check_load()
    assert load.status in {"ok", "warn", "unknown"}


def test_collect_report_shape() -> None:
    rep = collect_host_report(include_postgres=False)
    assert "overall" in rep
    names = {c["name"] for c in rep["checks"]}
    assert "disk" in names
    assert "memory" in names
    assert "load" in names
    assert "journald_retention" in names


def test_cli_json() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.ops.host_monitor",
            "--json",
            "--no-postgres",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode in {0, 1, 2}
    body = json.loads(r.stdout)
    assert body["checks"]
    assert body["overall"] in {"ok", "warn", "crit", "degraded"}


def test_missing_journald_is_crit(tmp_path: Path) -> None:
    missing = tmp_path / "nope.conf"
    r = check_journald_config(missing)
    assert r.status == "crit"
