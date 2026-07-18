"""DoD §14 — file metadata hash/size/type/origin; PDFs not in PG by default."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ops.file_metadata import assert_not_in_postgres, file_metadata


def test_file_metadata_hash_size_type_origin(tmp_path: Path) -> None:
    f = tmp_path / "edital.pdf"
    f.write_bytes(b"%PDF-1.4 sample")
    meta = file_metadata(f, origin="pncp://sample")
    assert meta["sha256"]
    assert meta["size_bytes"] == len(b"%PDF-1.4 sample")
    assert "pdf" in (meta["content_type"] or "") or meta["content_type"]
    assert meta["origin"] == "pncp://sample"
    assert meta["stored_in_postgres"] is False


def test_assert_not_in_postgres_requires_justification() -> None:
    meta = {
        "stored_in_postgres": True,
        "path": "x.pdf",
    }
    with pytest.raises(ValueError):
        assert_not_in_postgres(meta)
    assert_not_in_postgres(meta, justification="temporary quarantine LOB approved")
