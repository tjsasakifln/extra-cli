"""This slice is SELECT-only and does not schedule crawlers or migrations."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.public_read_consumers.select_guard import assert_select_only, scan_paths_for_writes

REPO = Path(__file__).resolve().parents[2]
OWNED = [
    REPO / "scripts" / "public_read_consumers",
    REPO / "tests" / "public_read_consumers",
    REPO / "docs" / "contracts" / "public-read-consumers",
]


def test_assert_select_only_accepts_select() -> None:
    sql = "SELECT canonical_contract_id FROM public_read_v1.contracts WHERE process_key = $1 LIMIT 20"
    assert assert_select_only(sql).startswith("SELECT")


@pytest.mark.parametrize(
    "sql", ["INSERT INTO x VALUES (1)", "UPDATE x SET a=1", "DELETE FROM x", "CREATE TABLE x(a int)"]
)
def test_assert_select_only_refuses_writes(sql: str) -> None:
    with pytest.raises(ValueError, match="refused"):
        assert_select_only(sql)


def test_owned_paths_have_no_write_sql_or_crawler_jobs() -> None:
    hits: list[str] = []
    for root in OWNED:
        hits.extend(scan_paths_for_writes(root))
    assert hits == []


def test_no_migration_in_this_slice() -> None:
    migrations = REPO / "db" / "migrations"
    owned_marker = "public_read_consumers"
    leaked = []
    if migrations.is_dir():
        for path in migrations.glob("*.sql"):
            text = path.read_text(encoding="utf-8")
            if owned_marker in text:
                leaked.append(path.name)
    assert leaked == []
