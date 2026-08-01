"""Security tests driving shipped ingest_path guards."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from scripts.bid_readiness.ingest import IngestError, ingest_path


def test_symlink_blocked(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    src = tmp_path / "docs"
    src.mkdir()
    real = src / "real.txt"
    real.write_text("ok", encoding="utf-8")
    link = src / "link.txt"
    try:
        link.symlink_to(real)
    except OSError:
        pytest.skip("symlinks not supported on this filesystem")
    objects, warnings = ingest_path(vault, src)
    names = {o.original_name for o in objects}
    assert "real.txt" in names
    assert "link.txt" not in names or any("symlink" in w.get("error", "").lower() for w in warnings)
    with pytest.raises(IngestError, match="symlink"):
        from scripts.bid_readiness.ingest import _ingest_file

        _ingest_file(vault, link, source_label="link.txt")


def test_zip_bomb_ratio_blocked(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    zpath = tmp_path / "bomb.zip"
    payload = b"0" * (2 * 1024 * 1024)
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("zeros.txt", payload)
    with pytest.raises(IngestError, match="zip bomb"):
        ingest_path(vault, zpath)


def test_zip_uncompressed_size_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.bid_readiness import ingest as ingest_mod

    monkeypatch.setattr(ingest_mod, "MAX_ZIP_UNCOMPRESSED", 1000)
    vault = tmp_path / "vault"
    zpath = tmp_path / "big.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("a.txt", b"x" * 2000)
    with pytest.raises(IngestError, match="zip bomb|uncompressed"):
        ingest_path(vault, zpath)


def test_executable_extension_blocked(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    src = tmp_path / "docs"
    src.mkdir()
    evil = src / "payload.exe"
    evil.write_bytes(b"MZ\x00\x00fake")
    objects, warnings = ingest_path(vault, src)
    assert objects == []
    assert any("blocked extension" in w.get("error", "") for w in warnings)


def test_macro_extension_blocked(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    src = tmp_path / "docs"
    src.mkdir()
    (src / "planilha.xlsm").write_bytes(b"PK\x03\x04fake")
    objects, warnings = ingest_path(vault, src)
    assert objects == []
    assert any("blocked extension" in w.get("error", "") for w in warnings)


def test_corrupt_document_blocked(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    src = tmp_path / "docs"
    src.mkdir()
    bad = src / "broken.txt"
    bad.write_bytes(b"CORRUPT\x00\x00\x00")
    objects, warnings = ingest_path(vault, src)
    assert objects == []
    assert any("corrupt" in w.get("error", "").lower() for w in warnings)


def test_single_file_executable_raises(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    exe = tmp_path / "run.sh"
    exe.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    with pytest.raises(IngestError, match="blocked extension"):
        ingest_path(vault, exe)


def test_csv_injection_blocked(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    csv = tmp_path / "evil.csv"
    csv.write_text("=cmd|'/c calc'!A0,1,2\n", encoding="utf-8")
    with pytest.raises(IngestError, match="injection"):
        ingest_path(vault, csv)
