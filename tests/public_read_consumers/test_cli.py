"""Drive the shipped CLI entry point."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "public_read_consumers"


def _run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.public_read_consumers", *args],
        cwd=str(cwd or REPO),
        check=False,
        capture_output=True,
        text=True,
    )


def test_list_shows_three_consumer_ids() -> None:
    proc = _run(["list"])
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["consumer_ids"] == [
        "web-cfg/contract-analysis",
        "web-cfg/market-answer/valor-tipico-contratos-pavimentacao",
        "web-cfg/b2g-xray",
    ]


def test_validate_accepts_named_contract_and_refuses_fixture_as_live(tmp_path: Path) -> None:
    ok = _run(["validate", "--consumer", "contract-analysis"])
    assert ok.returncode == 0, ok.stderr
    bad = _run(
        [
            "validate",
            "--consumer",
            "contract-analysis",
            "--payload",
            str(FIXTURES / "contract_analysis" / "catalog_fixture_as_live.json"),
        ]
    )
    assert bad.returncode == 2
    assert "fixture_as_live" in bad.stdout


def test_export_fixture_twice_is_byte_identical(tmp_path: Path) -> None:
    first = tmp_path / "run1"
    second = tmp_path / "run2"
    fixture = FIXTURES / "contract_analysis" / "catalog.json"
    a = _run(["export", "--consumer", "contract-analysis", "--fixture", str(fixture), "--out", str(first)])
    b = _run(["export", "--consumer", "contract-analysis", "--fixture", str(fixture), "--out", str(second)])
    assert a.returncode == 0, a.stderr
    assert b.returncode == 0, b.stderr
    left = json.loads(a.stdout)
    right = json.loads(b.stdout)
    assert left["content_hash"] == right["content_hash"]
    assert (first / "manifest.json").read_bytes() == (second / "manifest.json").read_bytes()
    manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "public-read-contract-analysis/1.0"
    assert manifest["catalog_mode"] == "fixture"
    assert manifest["claimed_live"] is False
    assert manifest["official_live"] is False
    assert manifest["producer_status"] == "CONTRACT_FIXTURE"
    assert (first / "analyses" / "cand-preco-01.json").is_file()
    verify = _run(["verify", "--path", str(first)])
    assert verify.returncode == 0, verify.stderr
    compare = _run(["compare", "--left", str(first), "--right", str(second)])
    assert json.loads(compare.stdout)["equal"] is True


def test_export_live_refuses_fixture(tmp_path: Path) -> None:
    fixture = FIXTURES / "market_answer" / "ready.json"
    proc = _run(
        [
            "export",
            "--consumer",
            "market-answer-pavimentacao",
            "--fixture",
            str(fixture),
            "--out",
            str(tmp_path / "live"),
            "--live",
        ]
    )
    assert proc.returncode == 2
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert payload["reason_code"] == "fixture_as_live"


def test_export_market_and_xray_fixtures(tmp_path: Path) -> None:
    market = _run(
        [
            "export",
            "--consumer",
            "market-answer-pavimentacao",
            "--fixture",
            str(FIXTURES / "market_answer" / "ready.json"),
            "--out",
            str(tmp_path / "market"),
        ]
    )
    xray = _run(
        [
            "export",
            "--consumer",
            "b2g-xray",
            "--fixture",
            str(FIXTURES / "xray" / "ready.json"),
            "--out",
            str(tmp_path / "xray"),
        ]
    )
    assert market.returncode == 0, market.stderr
    assert xray.returncode == 0, xray.stderr
    assert json.loads(market.stdout)["official_live"] is False
    assert json.loads(xray.stdout)["official_live"] is False
