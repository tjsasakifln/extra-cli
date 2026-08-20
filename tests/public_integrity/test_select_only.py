"""Consumer fixture is SELECT-only, no_index, not live, no crawler jobs."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.public_integrity.cli import main
from scripts.public_integrity.export import READ_MODEL_SQL, consumer_read_model
from scripts.public_integrity.select_guard import assert_select_only, scan_paths_for_writes
from tests.public_integrity.helpers import FIXTURES, REPO, VALID_CNPJ

OWNED = [
    REPO / "scripts" / "public_integrity",
    REPO / "tests" / "public_integrity",
    REPO / "exports" / "public-integrity",
]


def test_assert_select_only_accepts_shipped_sql() -> None:
    assert assert_select_only(READ_MODEL_SQL).lstrip().upper().startswith("SELECT")


def test_owned_paths_have_no_write_sql_or_crawler_jobs() -> None:
    hits: list[str] = []
    for root in OWNED:
        hits.extend(scan_paths_for_writes(root))
    assert hits == []


def test_committed_consumer_fixture_is_not_live() -> None:
    export_dir = REPO / "exports" / "public-integrity"
    sql = (export_dir / "web-cfg-156-read-model.sql").read_text(encoding="utf-8")
    assert_select_only(sql)
    model = json.loads((export_dir / "web-cfg-156-read-model.json").read_text(encoding="utf-8"))
    assert model["consumer"] == "web-cfg#156"
    assert model["no_index"] is True
    assert model["publication_authority"] is False
    assert model["not_live"] is True
    assert model["select_only"] is True
    readme = (export_dir / "README.md").read_text(encoding="utf-8")
    assert "web-cfg#156" in readme
    assert "no_index" in readme


def test_export_consumer_from_payload(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    assert (
        main(
            [
                "replay",
                "--fixture",
                str(FIXTURES / "matches.json"),
                "--cnpj",
                VALID_CNPJ,
                "--out",
                str(payload_path),
            ]
        )
        == 0
    )
    dest = tmp_path / "consumer"
    assert main(["export-consumer", "--payload", str(payload_path), "--out", str(dest)]) == 0
    model = json.loads((dest / "web-cfg-156-read-model.json").read_text(encoding="utf-8"))
    assert model["no_index"] is True
    assert model["not_live"] is True
    assert model["select_only"] is True
    public = json.loads((dest / "payload.public.json").read_text(encoding="utf-8"))
    assert VALID_CNPJ not in json.dumps(public)
    assert consumer_read_model(json.loads(payload_path.read_text(encoding="utf-8")))["no_index"] is True
