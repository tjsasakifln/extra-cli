"""IPM public procurement portals (#258). Canonical name is IPM, not IPAM."""

from __future__ import annotations

from typing import Any

from scripts.complementary.portals import IPM, parse_list_payload


def crawl(mode: str = "full") -> list[dict[str, Any]]:
    del mode
    return []


def transform(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return parse_list_payload(records, platform=IPM)
