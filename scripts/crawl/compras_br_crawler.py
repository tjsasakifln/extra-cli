"""Compras BR public adapter — listing/detail/documents/status. Refs #264."""

from __future__ import annotations

from typing import Any

from scripts.public_platforms.collect import crawl_source, transform_records

SOURCE = "compras_br"


def crawl(mode: str = "incremental", fixture: str | None = None) -> list[dict[str, Any]]:
    return crawl_source(SOURCE, mode=mode, fixture=fixture)


def transform(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return transform_records(SOURCE, records)
