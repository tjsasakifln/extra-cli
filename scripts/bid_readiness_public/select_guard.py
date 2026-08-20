"""SELECT-only guard for the web-cfg#155 consumer fixture."""

from __future__ import annotations

import re
from pathlib import Path

WRITE_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|ALTER|DROP|CREATE|GRANT|REVOKE|COPY\s+\w+\s+FROM)\b",
    re.IGNORECASE,
)
CRAWLER_HINTS = re.compile(
    r"\b(schedule_crawler|enqueue_crawl|crawl_job|register_crawler|agenda_crawler|"
    r"upload_endpoint|create_bucket|put_object)\b",
    re.IGNORECASE,
)
INDEX_GRANT = re.compile(
    r"\b(index_authorization\s*=\s*true|authorize_page|publication_authorization\s*=\s*true)\b",
    re.IGNORECASE,
)


def assert_select_only(sql: str) -> str:
    text = str(sql or "").strip()
    if not text:
        raise ValueError("empty_sql")
    if WRITE_SQL.search(text):
        raise ValueError("write_sql_refused")
    if not re.match(r"^\s*SELECT\b", text, re.IGNORECASE | re.MULTILINE):
        raise ValueError("non_select_sql_refused")
    return text


def scan_paths_for_writes(root: Path) -> list[str]:
    hits: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in {".py", ".sql", ".json", ".md"}:
            continue
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".sql" and WRITE_SQL.search(text):
            hits.append(str(path))
        if path.suffix == ".py" and path.name != "select_guard.py" and CRAWLER_HINTS.search(text):
            hits.append(f"{path}:crawler")
        if INDEX_GRANT.search(text) and path.name not in {"select_guard.py", "validators.py", "compose.py"}:
            hits.append(f"{path}:index_or_publication_grant")
    return hits
