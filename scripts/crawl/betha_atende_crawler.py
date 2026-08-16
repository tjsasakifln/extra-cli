"""Betha Atende.net public tenders (#257)."""

from __future__ import annotations

from typing import Any

from scripts.complementary.collect import crawl_portal
from scripts.complementary.portals import BETHA_ATENDE, parse_list_payload


def crawl(mode: str = "full") -> list[dict[str, Any]]:
    return crawl_portal(BETHA_ATENDE, mode)


def transform(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return parse_list_payload(records, platform=BETHA_ATENDE)
