"""Interactive human review CLI for CONFENGE EMAIL_SEND_READY sample.

Never auto-approves. Records A/R/S with attributable human reviewer.

Usage:
  python -m scripts.confenge.human_review
  python -m scripts.confenge human_review --sample artifacts/confenge/national-commercial-ready/HUMAN-REVIEW-SAMPLE.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.confenge_contact_resolution.human_review import (
    HUMAN_REVIEW_APPROVED,
    HUMAN_REVIEW_PENDING,
    HUMAN_REVIEW_REJECTED,
    is_forbidden_reviewer,
    mint_human_review_decision,
)

DEFAULT_SAMPLE = Path(
    "artifacts/confenge/national-commercial-ready/HUMAN-REVIEW-SAMPLE.json"
)
DEFAULT_DECISIONS = Path(
    "artifacts/confenge/national-commercial-ready/HUMAN-REVIEW-DECISIONS.jsonl"
)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_sample(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(
            f"Sample not found: {path}. Generate with national pack builder first."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("leads", "sample", "items", "companies"):
            if isinstance(data.get(key), list):
                return [x for x in data[key] if isinstance(x, dict)]
    raise ValueError(f"Unrecognized sample format in {path}")


def _display_lead(lead: dict[str, Any], idx: int, total: int) -> None:
    print("\n" + "=" * 72)
    print(f"LEAD {idx + 1}/{total}")
    print("=" * 72)
    fields = [
        ("empresa", lead.get("legal_name") or lead.get("razao_social") or lead.get("empresa")),
        ("CNPJ", lead.get("cnpj_raiz") or lead.get("cnpj") or lead.get("cnpj14")),
        ("email", lead.get("email") or (lead.get("contact") or {}).get("email")),
        ("fonte do email", lead.get("source_url") or lead.get("email_source") or lead.get("source_type")),
        (
            "ownership",
            lead.get("ownership_status")
            or (lead.get("contact") or {}).get("ownership_status"),
        ),
        (
            "mailbox_purpose",
            lead.get("mailbox_purpose")
            or (lead.get("contact") or {}).get("mailbox_purpose"),
        ),
        (
            "serviço sugerido",
            lead.get("recommended_service") or lead.get("service_code"),
        ),
        ("why_this_account", lead.get("why_this_account")),
        ("why_now", lead.get("why_now")),
        ("micro_offer", lead.get("micro_offer")),
        ("draft", lead.get("draft") or lead.get("email_draft") or lead.get("subject")),
    ]
    for label, val in fields:
        text = str(val if val is not None else "—")
        if len(text) > 500:
            text = text[:500] + "…"
        print(f"{label}:\n  {text}\n")
    # provenance evidence excerpt
    evidence = lead.get("supporting_evidence") or lead.get("evidence") or []
    if evidence:
        print("supporting_evidence:")
        for e in evidence[:5]:
            print(f"  - {json.dumps(e, ensure_ascii=False)[:200]}")
    status = lead.get("review_status") or lead.get("human_review_status") or HUMAN_REVIEW_PENDING
    print(f"\ncurrent_status: {status}")
    print("Commands: [A]pprove  [R]eject  [S]kip  [Q]uit")


def _append_decision(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def run_interactive(
    *,
    sample_path: Path,
    decisions_path: Path,
    reviewer: str,
    only_pending: bool = True,
) -> int:
    if is_forbidden_reviewer(reviewer):
        print(
            f"ERROR: reviewer={reviewer!r} is forbidden (automation identity). "
            "Use a real human identifier (e.g. tiago).",
            file=sys.stderr,
        )
        return 2

    leads = load_sample(sample_path)
    if only_pending:
        pending = [
            L
            for L in leads
            if str(L.get("review_status") or L.get("human_review_status") or HUMAN_REVIEW_PENDING)
            == HUMAN_REVIEW_PENDING
        ]
    else:
        pending = leads

    if not pending:
        print(f"No pending leads in {sample_path} ({len(leads)} total).")
        return 0

    print(
        f"Human review: {len(pending)} pending / {len(leads)} total\n"
        f"Reviewer: {reviewer}\nDecisions → {decisions_path}"
    )

    for i, lead in enumerate(pending):
        _display_lead(lead, i, len(pending))
        while True:
            try:
                raw = input("> ").strip().upper()
            except EOFError:
                print("\nEOF — stopping.")
                return 0
            if raw in {"Q", "QUIT"}:
                print("Stopped by operator.")
                return 0
            if raw in {"S", "SKIP"}:
                row = {
                    "cnpj_raiz": lead.get("cnpj_raiz") or lead.get("cnpj"),
                    "email": lead.get("email"),
                    "decision": "SKIP",
                    "review_status": HUMAN_REVIEW_PENDING,
                    "reviewer": reviewer,
                    "reviewed_at": _now(),
                    "evidence_inspected": ["ui_lead_card"],
                }
                _append_decision(decisions_path, row)
                print("skipped")
                break
            if raw in {"A", "APPROVE", "R", "REJECT"}:
                approve = raw in {"A", "APPROVE"}
                try:
                    decision = mint_human_review_decision(
                        reviewer=reviewer,
                        decision=HUMAN_REVIEW_APPROVED if approve else HUMAN_REVIEW_REJECTED,
                        evidence_inspected=[
                            "empresa",
                            "cnpj",
                            "email",
                            "source",
                            "ownership",
                            "service",
                            "why_this_account",
                            "why_now",
                            "micro_offer",
                            "draft",
                        ],
                    )
                except ValueError as exc:
                    print(f"ERROR: {exc}")
                    continue
                row = {
                    "cnpj_raiz": lead.get("cnpj_raiz") or lead.get("cnpj"),
                    "email": lead.get("email"),
                    "legal_name": lead.get("legal_name") or lead.get("razao_social"),
                    **decision,
                    "review_status": decision["status"],
                }
                _append_decision(decisions_path, row)
                # update in-memory for optional sample rewrite
                lead["review_status"] = decision["status"]
                lead["human_review"] = decision
                print(f"recorded {decision['status']}")
                break
            print("Invalid — use A / R / S / Q")

    # Persist updated sample statuses
    try:
        original = json.loads(sample_path.read_text(encoding="utf-8"))
        if isinstance(original, dict) and isinstance(original.get("leads"), list):
            # map by cnpj+email
            by_key = {
                (
                    str(L.get("cnpj_raiz") or L.get("cnpj")),
                    str(L.get("email") or ""),
                ): L
                for L in pending
            }
            for item in original["leads"]:
                k = (
                    str(item.get("cnpj_raiz") or item.get("cnpj")),
                    str(item.get("email") or ""),
                )
                if k in by_key and by_key[k].get("human_review"):
                    item["review_status"] = by_key[k]["review_status"]
                    item["human_review"] = by_key[k]["human_review"]
            sample_path.write_text(
                json.dumps(original, indent=2, ensure_ascii=False, default=str) + "\n",
                encoding="utf-8",
            )
    except OSError as exc:
        print(f"warning: could not rewrite sample: {exc}", file=sys.stderr)

    print(f"\nDone. Decisions appended to {decisions_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m scripts.confenge.human_review",
        description="Interactive CONFENGE human review (A/R/S). Never auto-approves.",
    )
    p.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    p.add_argument("--decisions", type=Path, default=DEFAULT_DECISIONS)
    p.add_argument(
        "--reviewer",
        default=None,
        help="Human reviewer id (required; not an automation identity)",
    )
    p.add_argument(
        "--all",
        action="store_true",
        help="Show all leads, not only HUMAN_REVIEW_PENDING",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    reviewer = args.reviewer
    if not reviewer:
        try:
            reviewer = input("Reviewer name (human, e.g. tiago): ").strip()
        except EOFError:
            reviewer = ""
    if not reviewer:
        print("ERROR: --reviewer is required for attributable human review.", file=sys.stderr)
        return 2
    try:
        return run_interactive(
            sample_path=args.sample,
            decisions_path=args.decisions,
            reviewer=reviewer,
            only_pending=not args.all,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
