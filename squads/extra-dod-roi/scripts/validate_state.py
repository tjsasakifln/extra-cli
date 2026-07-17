#!/usr/bin/env python3
"""Validate cycle state / ranking JSON against lightweight required fields."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def validate_ranking(data: dict) -> list[str]:
    errs = []
    if "candidates" not in data:
        errs.append("missing candidates")
    for i, c in enumerate(data.get("candidates") or []):
        for k in ("id", "title", "status", "roi"):
            if k not in c:
                errs.append(f"candidates[{i}] missing {k}")
    return errs


def validate_cycle(data: dict) -> list[str]:
    errs = []
    for k in ("cycle_id", "version", "status", "created_at"):
        if k not in data:
            errs.append(f"missing {k}")
    return errs


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("path")
    p.add_argument("--kind", choices=["ranking", "cycle", "auto"], default="auto")
    args = p.parse_args(argv)
    data = json.loads(Path(args.path).read_text(encoding="utf-8"))
    kind = args.kind
    if kind == "auto":
        kind = "cycle" if "cycle_id" in data else "ranking"
    errs = validate_cycle(data) if kind == "cycle" else validate_ranking(data)
    if errs:
        print(json.dumps({"ok": False, "errors": errs}, indent=2))
        return 1
    print(json.dumps({"ok": True, "kind": kind}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
