"""CLI: plan / run / report / replay / shadow."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.decision_unit_intelligence import POLICY_VERSION, PROVIDER_VERSION, SCHEMA_VERSION
from scripts.decision_unit_intelligence.benchmark import funnel, replay_report
from scripts.decision_unit_intelligence.cohort import TRACK_A_CNPJS, build_manifest
from scripts.decision_unit_intelligence.operator_pack import build_card, write_operator_pack
from scripts.decision_unit_intelligence.projection import project_warmbly_outreach
from scripts.decision_unit_intelligence.repository import JsonRunRepository, account_hash, write_json
from scripts.decision_unit_intelligence.runner import run_account


def _load_cnpjs(args: argparse.Namespace) -> list[str]:
    if args.cnpjs:
        return [c.strip() for c in args.cnpjs.split(",") if c.strip()]
    if args.manifest:
        payload = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        return [a["cnpj"] for a in payload.get("accounts") or []]
    limit = args.limit or 30
    if limit <= len(TRACK_A_CNPJS):
        return TRACK_A_CNPJS[:limit]
    from scripts.decision_unit_intelligence.providers.historical_campaign import load_campaign_index

    extra = [c for c in load_campaign_index() if c not in TRACK_A_CNPJS]
    extra.sort()
    return (TRACK_A_CNPJS + extra)[:limit]


def cmd_plan(args: argparse.Namespace) -> int:
    out = Path(args.out)
    manifest = build_manifest(_load_cnpjs(args))
    write_json(out, manifest)
    print(json.dumps({"wrote": str(out), "n": manifest["n"], "seed": manifest["selection"]["seed"]}, ensure_ascii=False))
    return 0


def _execute(args: argparse.Namespace, *, label: str) -> int:
    cnpjs = _load_cnpjs(args)
    repo = JsonRunRepository(Path(args.out))
    accounts = []
    for cnpj in cnpjs:
        acc = run_account(cnpj, service=args.service, infer_email=not args.no_infer_email)
        payload = acc.to_dict()
        payload["replay_hash"] = account_hash(payload)
        repo.save_account(payload)
        accounts.append(acc)
        print(f"{label}\t{acc.cnpj}\t{acc.terminal.value}\t{acc.extra.get('account_reachability_class')}\t{acc.legal_name}")
    fun = funnel(accounts)
    repo.save_funnel(fun)
    cards = [build_card(a) for a in accounts]
    operator_dir = Path(args.operator_out) if args.operator_out else Path(args.out) / "operator"
    pack_paths = write_operator_pack(cards, operator_dir)
    warmbly = [project_warmbly_outreach(a) for a in accounts]
    email_safe = sum(w["email_safe_count"] for w in warmbly)
    write_json(Path(args.out) / "warmbly_outreach.json", {"accounts": warmbly, "email_safe_total": email_safe})
    manifest = {
        "schema_id": "confenge.dui.run.v1",
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "provider_version": PROVIDER_VERSION,
        "n": len(accounts),
        "cnpjs": cnpjs,
        "funnel": fun,
        "operator_pack": pack_paths,
        "email_safe_warmbly": email_safe,
        "selection": build_manifest(cnpjs)["selection"],
        "auto_send": False,
    }
    repo.save_manifest(manifest)
    print(json.dumps({"out": args.out, "operator": pack_paths, "funnel": fun}, ensure_ascii=False, indent=2))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    return _execute(args, label="RUN")


def cmd_shadow(args: argparse.Namespace) -> int:
    return _execute(args, label="SHADOW")


def cmd_report(args: argparse.Namespace) -> int:
    repo = JsonRunRepository(Path(args.run))
    accounts = repo.load_accounts()
    print(json.dumps({"n": len(accounts), "path": args.run, "sample": accounts[0]["cnpj"] if accounts else None}, indent=2))
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    first = JsonRunRepository(Path(args.run_a)).load_accounts()
    second = JsonRunRepository(Path(args.run_b)).load_accounts()
    print(json.dumps(replay_report(first, second), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="decision-unit-intelligence")
    sub = p.add_subparsers(dest="cmd", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--out", required=True)
    plan.add_argument("--manifest")
    plan.add_argument("--cnpjs")
    plan.add_argument("--limit", type=int, default=30)
    plan.set_defaults(func=cmd_plan)

    run = sub.add_parser("run")
    run.add_argument("--out", required=True)
    run.add_argument("--operator-out")
    run.add_argument("--manifest")
    run.add_argument("--cnpjs")
    run.add_argument("--limit", type=int, default=30)
    run.add_argument("--service", default="reajuste_14133")
    run.add_argument("--no-infer-email", action="store_true")
    run.set_defaults(func=cmd_run)

    shadow = sub.add_parser("shadow")
    shadow.add_argument("--out", required=True)
    shadow.add_argument("--operator-out")
    shadow.add_argument("--manifest")
    shadow.add_argument("--cnpjs")
    shadow.add_argument("--limit", type=int, default=100)
    shadow.add_argument("--service", default="reajuste_14133")
    shadow.add_argument("--no-infer-email", action="store_true")
    shadow.set_defaults(func=cmd_shadow)

    report = sub.add_parser("report")
    report.add_argument("--run", required=True)
    report.set_defaults(func=cmd_report)

    replay = sub.add_parser("replay")
    replay.add_argument("--run-a", required=True)
    replay.add_argument("--run-b", required=True)
    replay.set_defaults(func=cmd_replay)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = args.func(args)
    return int(result)


if __name__ == "__main__":
    sys.exit(main())
