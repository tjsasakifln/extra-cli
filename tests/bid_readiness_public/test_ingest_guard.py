"""REJECT-before-parse: drive shipped ingest_guard.preflight_path."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from scripts.bid_readiness import ingest as ingest_mod
from scripts.bid_readiness_public.ingest_guard import RejectedInputError, preflight_path


def test_path_traversal_zip_is_rejected_before_parse(tmp_path: Path) -> None:
    zpath = tmp_path / "trav.zip"
    with zipfile.ZipFile(zpath, "w") as archive:
        archive.writestr("../evil.txt", "nope")
    with pytest.raises(RejectedInputError, match="traversal") as caught:
        preflight_path(zpath)
    assert caught.value.reason_code == "path_traversal"


def test_zip_bomb_is_rejected_before_parse(tmp_path: Path) -> None:
    zpath = tmp_path / "bomb.zip"
    payload = b"0" * (2 * 1024 * 1024)
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("zeros.txt", payload)
    with pytest.raises(RejectedInputError) as caught:
        preflight_path(zpath)
    assert caught.value.reason_code == "zip_bomb"


def test_oversized_file_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ingest_mod, "MAX_FILE_BYTES", 64)
    import scripts.bid_readiness_public.ingest_guard as guard

    monkeypatch.setattr(guard, "MAX_FILE_BYTES", 64)
    big = tmp_path / "huge.txt"
    big.write_bytes(b"x" * 128)
    with pytest.raises(RejectedInputError) as caught:
        preflight_path(big)
    assert caught.value.reason_code == "oversized"


def test_disallowed_type_is_rejected(tmp_path: Path) -> None:
    exe = tmp_path / "payload.exe"
    exe.write_bytes(b"MZ\x00fake")
    with pytest.raises(RejectedInputError) as caught:
        preflight_path(exe)
    assert caught.value.reason_code == "malware_like"


def test_csv_injection_is_rejected(tmp_path: Path) -> None:
    csv_path = tmp_path / "evil.csv"
    csv_path.write_text("=cmd|'/c calc'!A0,1,2\n", encoding="utf-8")
    with pytest.raises(RejectedInputError) as caught:
        preflight_path(csv_path)
    assert caught.value.reason_code == "csv_injection"


def test_macro_workbook_is_disallowed(tmp_path: Path) -> None:
    xlsm = tmp_path / "macro.xlsm"
    xlsm.write_bytes(b"PK\x03\x04fake")
    with pytest.raises(RejectedInputError) as caught:
        preflight_path(xlsm)
    assert caught.value.reason_code == "disallowed_type"
