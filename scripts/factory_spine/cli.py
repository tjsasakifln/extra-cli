"""CLI for the durable crawl factory spine.

Refs #235 #236 #246 #247 #256 #268 #269 #270 #272 #279
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.factory_spine.runtime import launch_spine
from scripts.factory_spine.store import FactoryStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Durable fail-closed crawl factory spine")
    sub = parser.add_subparsers(dest="command", required=True)
    launch = sub.add_parser("launch", help="enqueue/inspect one spine job and persist evidence")
    launch.add_argument("--state-dir", type=Path, required=True)
    launch.add_argument("--entity-key", default="extra-canonical-0001")
    launch.add_argument("--entity-id", type=int, default=1)
    launch.add_argument("--source", default="transparencia")
    launch.add_argument("--worker-id", default="factory-spine-local")
    inspect = sub.add_parser("inspect", help="inspect a persisted job")
    inspect.add_argument("--state-dir", type=Path, required=True)
    inspect.add_argument("--job-id", type=int, required=True)
    args = parser.parse_args(argv)
    if args.command == "launch":
        result = launch_spine(
            args.state_dir,
            entity_key=args.entity_key,
            entity_id=args.entity_id,
            source=args.source,
            worker_id=args.worker_id,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 1
    job = FactoryStore(args.state_dir).inspect(args.job_id)
    if job is None:
        print(json.dumps({"ok": False, "error": "job_not_found", "job_id": args.job_id}))
        return 1
    print(json.dumps({"ok": True, "job": job}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
