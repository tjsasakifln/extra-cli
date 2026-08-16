"""Betha Atende.net public tenders (#257)."""

from __future__ import annotations

from typing import Any

from scripts.complementary.portals import BETHA_ATENDE, parse_list_payload


def crawl(mode: str = "full") -> list[dict[str, Any]]:
    del mode
    return []


def transform(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return parse_list_payload(records, platform=BETHA_ATENDE)
