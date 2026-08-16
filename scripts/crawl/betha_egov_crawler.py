"""Betha e-Gov (*.e-gov.betha.com.br) — distinct from Atende (#259)."""

from __future__ import annotations

from typing import Any

from scripts.complementary.portals import BETHA_EGOV, parse_list_payload


def crawl(mode: str = "full") -> list[dict[str, Any]]:
    del mode
    return []


def transform(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return parse_list_payload(records, platform=BETHA_EGOV)
