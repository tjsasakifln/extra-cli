"""Fail-closed collect for complementary registry crawlers.

A missing tenant, fixture or DSN is BLOCKED/NOT_APPLICABLE evidence.
Never return an empty list (that would look like silent success_zero).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from scripts.complementary.contract import RunResult
from scripts.complementary.licitacoes_e import classify_surface
from scripts.complementary.portals import bind_entity, run_portal

FIXTURE_ENV = "COMPLEMENTARY_FIXTURE"


def blocked_observation(source: str, reason: str) -> dict[str, Any]:
    return {
        "source": source,
        "terminal": "BLOCKED",
        "reason": reason,
        "fetched": 0,
        "silent_zero": False,
    }


def observations_from_result(result: RunResult) -> list[dict[str, Any]]:
    if result.records:
        packed = []
        for row in result.records:
            item = dict(row)
            item.setdefault("source", result.source)
            item.setdefault("terminal", result.terminal)
            packed.append(item)
        return packed
    return [
        {
            "source": result.source,
            "terminal": result.terminal,
            "reason": result.reason,
            "fetched": result.fetched,
            "silent_zero": False,
            "job": result.job,
        }
    ]


def load_fixture(path: str | Path | None = None) -> dict[str, Any] | None:
    raw = path or os.environ.get(FIXTURE_ENV)
    if not raw:
        return None
    p = Path(raw)
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def crawl_portal(platform: str, mode: str = "full") -> list[dict[str, Any]]:
    del mode
    payload = load_fixture()
    if payload is None:
        return [blocked_observation(platform, "missing_tenant_binding_or_fixture")]
    binding = payload.get("binding")
    if binding:
        binding = bind_entity(
            binding["url"],
            cnpj=binding.get("cnpj") or "",
            ibge=binding.get("ibge") or "",
            municipio=binding.get("municipio") or "",
        )
    result = run_portal(
        platform=platform,
        pages=payload.get("pages") or [],
        binding=binding,
    )
    return observations_from_result(result)


def crawl_licitacoes_e(mode: str = "full") -> list[dict[str, Any]]:
    del mode
    payload = load_fixture()
    if payload is None:
        return [
            {
                "source": "licitacoes_e",
                "terminal": "BLOCKED",
                "reason": "surface_unclassified_without_probe",
                "fetched": 0,
                "silent_zero": False,
            }
        ]
    return observations_from_result(classify_surface(payload))
