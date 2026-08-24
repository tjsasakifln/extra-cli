"""CLI: python -m scripts.confenge_activation plan|publish"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from scripts.confenge_activation import MODULE_VERSION, PLANNER_ID
from scripts.confenge_activation.planner import run_activation_cycle
from scripts.confenge_activation.policy import load_policy
from scripts.confenge_activation.publish import (
    DEFAULT_ALERT_LEDGER,
    DEFAULT_MAX_AGE_HOURS,
    DEFAULT_STATE_PATH,
    atomic_publish_directory,
    check_current_publication,
)
from scripts.confenge_activation.store import (
    load_projections_jsonl,
    write_hot_set_jsonl,
    write_projections_jsonl,
)


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if t and not t.startswith("#"):
            rows.append(json.loads(t))
    return rows


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m scripts.confenge_activation",
        description="CONFENGE commercial activation planner (cheap scan of full reservoir).",
    )
    p.add_argument("--version", action="version", version=f"{PLANNER_ID} {MODULE_VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="Run activation cycle on universe JSONL")
    plan.add_argument("--universe", required=True, help="Universe JSONL path")
    plan.add_argument("--out", required=True, help="Output directory")
    plan.add_argument("--as-of", default=None, help="YYYY-MM-DD")
    plan.add_argument("--policy", default=None, help="Policy YAML path")
    plan.add_argument("--prior", default=None, help="Prior projections JSONL")
    plan.add_argument("--capacity", type=int, default=None, help="Override hot-set capacity")

    pub = sub.add_parser("publish", help="Atomically publish a built feed directory")
    pub.add_argument("--build-dir", required=True, help="Completed feed build dir")
    pub.add_argument("--publish-dir", required=True, help="Publication root (current symlink)")
    pub.add_argument("--max-age-hours", type=float, default=DEFAULT_MAX_AGE_HOURS)
    pub.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    pub.add_argument("--alert-ledger", type=Path, default=DEFAULT_ALERT_LEDGER)

    check = sub.add_parser("check-publication", help="Validate freshness and integrity of the public current feed")
    check.add_argument("--publish-dir", required=True, help="Publication root containing current symlink")
    check.add_argument("--max-age-hours", type=float, default=DEFAULT_MAX_AGE_HOURS)
    check.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    check.add_argument("--alert-ledger", type=Path, default=DEFAULT_ALERT_LEDGER)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "publish":
        try:
            result = atomic_publish_directory(
                Path(args.build_dir),
                Path(args.publish_dir),
                max_age_hours=args.max_age_hours,
                state_path=args.state,
                alert_ledger=args.alert_ledger,
            )
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 3 if result.get("skipped_same") else 0

    if args.command == "check-publication":
        result = check_current_publication(
            Path(args.publish_dir),
            max_age_hours=args.max_age_hours,
            state_path=args.state,
            alert_ledger=args.alert_ledger,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("ok") else 1

    if args.command == "plan":
        universe = Path(args.universe)
        if not universe.is_file():
            print(f"universe not found: {universe}", file=sys.stderr)
            return 2
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
        policy = load_policy(args.policy)
        prior = load_projections_jsonl(args.prior) if args.prior else {}
        rows = _read_jsonl(universe)
        cycle = run_activation_cycle(
            rows,
            policy=policy,
            as_of=as_of,
            prior_projections=prior,
            capacity_override=args.capacity,
        )
        write_projections_jsonl(out / "activation-projections.jsonl", cycle.projections)
        write_hot_set_jsonl(out / "hot-set.jsonl", cycle.hot_set)
        (out / "deactivations.json").write_text(
            json.dumps(cycle.deactivations, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        summary = cycle.summary()
        (out / "activation-summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
