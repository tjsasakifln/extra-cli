#!/usr/bin/env python3
"""CLI for complementary-source contracts.

    python3 -m scripts.complementary.cli arp --fixture PATH
    python3 -m scripts.complementary.cli dados-abertos --fixture PATH
    python3 -m scripts.complementary.cli mides --fixture PATH
    python3 -m scripts.complementary.cli portal --platform betha_atende --fixture PATH
    python3 -m scripts.complementary.cli licitacoes-e --fixture PATH
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.complementary.arp import persist_window
from scripts.complementary.dados_abertos import run_inventory
from scripts.complementary.licitacoes_e import classify_surface
from scripts.complementary.mides import run_bounded_job
from scripts.complementary.portals import bind_entity, run_portal


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Complementary source contracts")
    p.add_argument(
        "source",
        choices=["arp", "dados-abertos", "mides", "portal", "licitacoes-e"],
    )
    p.add_argument("--fixture", type=Path, required=True)
    p.add_argument("--platform", default="betha_atende")
    args = p.parse_args(argv)
    payload = _load(args.fixture)

    if args.source == "arp":
        result = persist_window(
            payload.get("pages") or [],
            skipped=bool(payload.get("skipped")),
            dsn=payload.get("dsn") or None,
        )
    elif args.source == "dados-abertos":
        result = run_inventory(
            payload.get("packages") or [],
            processed_ids=set(payload.get("processed_ids") or []),
            truncated=bool(payload.get("truncated")),
            drift=payload.get("drift"),
            sc_compras_rows=payload.get("sc_compras"),
        )
    elif args.source == "mides":
        result = run_bounded_job(
            interval=str(payload.get("interval") or "2024-01/2024-12"),
            estimated_bytes=payload.get("estimated_bytes"),
            rows=payload.get("rows") or [],
            job_id=payload.get("job_id"),
            env=payload.get("env"),
            budget_bytes=int(payload.get("budget_bytes") or 100 * 1024 * 1024 * 1024),
        )
    elif args.source == "portal":
        binding = payload.get("binding")
        if binding:
            binding = bind_entity(
                binding["url"],
                cnpj=binding.get("cnpj") or "",
                ibge=binding.get("ibge") or "",
                municipio=binding.get("municipio") or "",
            )
        result = run_portal(
            platform=args.platform,
            pages=payload.get("pages") or [],
            binding=binding,
        )
    else:
        result = classify_surface(payload)

    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0 if result.terminal in {"success", "ZERO_CONFIRMED", "NOT_APPLICABLE"} else 2


if __name__ == "__main__":
    sys.exit(main())
