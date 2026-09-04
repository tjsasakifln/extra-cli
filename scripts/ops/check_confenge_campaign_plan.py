"""Lint a CONFENGE campaign plan for superseded PNCP→commercial coupling.

Usage:
  python3 -m scripts.ops.check_confenge_campaign_plan --file <arquivo>
  python3 -m scripts.ops.check_confenge_campaign_plan --root .   # active globs only

Does not grep full history. Documents labeled HISTORICAL or SUPERSEDED pass.
Exit 0 = accept, 1 = reject, 2 = usage/error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.ops.confenge_commercial_plane import classify_plan, iter_active_plan_files

REPO_ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", action="append", dest="files", default=[])
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    paths = [Path(item) for item in args.files] if args.files else iter_active_plan_files(root)
    if not paths:
        print("ERROR: no files to scan", file=sys.stderr)
        return 2

    verdicts = []
    for path in paths:
        if not path.is_file():
            print(f"ERROR: not a file: {path}", file=sys.stderr)
            return 2
        text = path.read_text(encoding="utf-8")
        verdicts.append(classify_plan(text, path=str(path)))

    rejected = [v for v in verdicts if not v.accepted]
    payload = {
        "ok": not rejected,
        "scanned": len(verdicts),
        "rejected": [
            {"path": v.path, "violations": v.violations} for v in rejected
        ],
        "accepted": [v.path for v in verdicts if v.accepted],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not args.json_only:
        for v in verdicts:
            status = "ACCEPT" if v.accepted else "REJECT"
            extra = "" if v.accepted else " " + ",".join(v.violations)
            hist = " HISTORICAL" if v.historical else ""
            print(f"{status}{hist} {v.path}{extra}")
    return 0 if not rejected else 1


if __name__ == "__main__":
    raise SystemExit(main())
