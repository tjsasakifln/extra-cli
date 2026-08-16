"""Licitações-e public surface stub (#265)."""

from __future__ import annotations

from typing import Any

from scripts.complementary.collect import crawl_licitacoes_e
from scripts.complementary.licitacoes_e import classify_surface


def crawl(mode: str = "full") -> list[dict[str, Any]]:
    return crawl_licitacoes_e(mode)


def transform(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in records:
        result = classify_surface(raw if isinstance(raw, dict) else {"body": str(raw)})
        out.append(result.to_dict())
    return out
