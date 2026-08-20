"""Drive the shipped CLI twice on the same frozen as_of."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.bofu_evidence.cli import main
from scripts.bofu_evidence.models import FAMILIES, SCHEMA


def test_cli_main_twice_same_hashes(tmp_path: Path, capsys) -> None:
    one = tmp_path / "run1"
    two = tmp_path / "run2"
    as_of = "2026-08-19T00:00:00Z"
    assert main(["--out", str(one), "--as-of", as_of]) == 0
    first = json.loads(capsys.readouterr().out)
    assert main(["--out", str(two), "--as-of", as_of]) == 0
    second = json.loads(capsys.readouterr().out)

    assert first["ok"] is True
    assert first["schema"] == SCHEMA
    assert first["as_of"] == as_of
    assert second["as_of"] == as_of
    assert first["pack_count"] == 8
    assert first["hashes"] == second["hashes"]
    assert (one / "SHA256SUMS.txt").read_text(encoding="utf-8") == (two / "SHA256SUMS.txt").read_text(encoding="utf-8")

    manifest = json.loads((one / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == SCHEMA
    assert manifest["publication"] is False
    assert manifest["index"] is False
    assert manifest["national"] is False
    assert set(manifest["families"]) == set(FAMILIES)
    for family in FAMILIES:
        pack_path = one / "packs" / f"{family}.json"
        assert pack_path.is_file()
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        assert pack["family"] == family
        assert pack["as_of"] == as_of
