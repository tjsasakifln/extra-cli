"""CLI for public platform fixture crawls.

Usage:
    python3 -m scripts.public_platforms.cli --source bbmnet --fixture tests/fixtures/public_platforms/bbmnet_pages.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.public_platforms.collect import collect_from_fixture
from scripts.public_platforms.contract import PLATFORMS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Public platform fixture crawl")
    parser.add_argument("--source", required=True, choices=sorted(PLATFORMS))
    parser.add_argument("--fixture", default=None)
    args = parser.parse_args(argv)
    result = collect_from_fixture(args.source, Path(args.fixture) if args.fixture else None)
    sys.stdout.write(json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n")
    return 0 if result.terminal in {"success", "ZERO"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
