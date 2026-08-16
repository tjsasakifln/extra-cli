"""Monitor-facing ARP lake adapter (#250)."""

from __future__ import annotations

from typing import Any

from scripts.complementary.arp import crawl as _crawl
from scripts.complementary.arp import transform as _transform


def crawl(mode: str = "full") -> list[dict[str, Any]]:
    return _crawl(mode)


def transform(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _transform(records)
