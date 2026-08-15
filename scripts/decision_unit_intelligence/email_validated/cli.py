"""CLI: import/adjudicate, evaluate, policy-diff, regression.

Offline only. Does not fetch the web and does not enable send.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.decision_unit_intelligence.email_validated.evaluate import evaluate_gold_set, regression_gate
from scripts.decision_unit_intelligence.email_validated.policy import load_policy_document, policy_diff, policy_document
from scripts.decision_unit_intelligence.email_validated.schema import (
    AdjudicationRecord,
    load_jsonl,
    validate_record,
    write_jsonl,
)

DEFAULT_GOLD = Path("evals/email_validated/gold/gold-set.v1.jsonl")


def _read_payload(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if path.suffix == ".json" and not text.startswith("["):
        payload = json.loads(text)
        if isinstance(payload, list):
            return payload
        return [payload]
    if text.startswith("["):
        payload = json.loads(text)
        if not isinstance(payload, list):
            raise ValueError("JSON array expected")
        return payload
    rows = []
    for line in text.splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def cmd_import(args: argparse.Namespace) -> int:
    rows = _read_payload(Path(args.source))
    records = []
    errors = []
    for index, raw in enumerate(rows):
        record = AdjudicationRecord.from_dict(raw)
        problems = validate_record(record)
        if problems:
            errors.append({"index": index, "case_id": record.case_id, "errors": problems})
            continue
        records.append(record)
    if errors and not args.allow_invalid:
        print(json.dumps({"ok": False, "imported": 0, "errors": errors}, ensure_ascii=False, indent=2))
        return 2
    write_jsonl(args.out, records)
    print(
        json.dumps(
            {
                "ok": True,
                "imported": len(records),
                "out": str(args.out),
                "errors": errors,
                "round_trip_fields": [record.to_dict() for record in records],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    records = load_jsonl(args.gold)
    report = evaluate_gold_set(records)
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_policy_diff(args: argparse.Namespace) -> int:
    left = load_policy_document(args.left) if args.left else policy_document()
    right = load_policy_document(args.right)
    diff = policy_diff(left, right)
    print(json.dumps(diff, ensure_ascii=False, indent=2))
    return 0 if not args.require_change or not diff["noop"] else 3


def cmd_regression(args: argparse.Namespace) -> int:
    records = load_jsonl(args.gold)
    report = evaluate_gold_set(records)
    gate = regression_gate(report)
    payload = {
        "gate": gate,
        "precision_email_validated": report["precision_email_validated"],
        "precision_denominator": report["precision_denominator"],
        "false_positives": report["false_positives"],
        "stop_the_line_cases": report["stop_the_line_cases"],
        "policy_version": report["policy_version"],
        "gold_set_version": report["gold_set_version"],
    }
    if args.out:
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if gate["stop_the_line"]:
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="email-validated-policy")
    sub = parser.add_subparsers(dest="cmd", required=True)

    imp = sub.add_parser("import", aliases=["adjudicate"])
    imp.add_argument("--in", dest="source", required=True)
    imp.add_argument("--out", required=True)
    imp.add_argument("--allow-invalid", action="store_true")
    imp.set_defaults(func=cmd_import)

    ev = sub.add_parser("evaluate")
    ev.add_argument("--gold", default=str(DEFAULT_GOLD))
    ev.add_argument("--out")
    ev.set_defaults(func=cmd_evaluate)

    diff = sub.add_parser("policy-diff")
    diff.add_argument("--left", help="Older policy JSON. Defaults to shipped v1.")
    diff.add_argument("--right", required=True)
    diff.add_argument("--require-change", action="store_true")
    diff.set_defaults(func=cmd_policy_diff)

    reg = sub.add_parser("regression")
    reg.add_argument("--gold", default=str(DEFAULT_GOLD))
    reg.add_argument("--out")
    reg.set_defaults(func=cmd_regression)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
