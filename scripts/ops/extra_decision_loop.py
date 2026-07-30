#!/usr/bin/env python3
"""EXTRA-PROFILE-TO-ACTIONABLE-DECISION-01 orchestrator.

Chains: profile stamp → weekly pack (or reuse) → actionable classify → package → review state.

  python3 -m scripts.ops.extra_decision_loop run \\
      --weekly-dir PATH \\
      --out PATH \\
      [--profile config/client_profiles/extra.yaml] \\
      [--max-shortlist 5]

Does not invent human acceptance. Terminal default: READY_FOR_HUMAN_ACCEPTANCE.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.ops.extra_actionable import classify_batch
from scripts.ops.extra_decision_review import READY_FOR_HUMAN, STATE_NAME
from scripts.ops.extra_first_client_delivery import (
    sha256_file,
    validate_weekly_pack,
)
from scripts.ops.extra_profile import stamp, validate_profile

SCHEMA = "extra-decision-loop/1.0"
CAMPAIGN = "EXTRA-PROFILE-TO-ACTIONABLE-DECISION-01"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _load_opportunities_csv(weekly_dir: Path) -> list[dict[str, Any]]:
    """Best-effort load of opportunities from weekly pack layouts."""
    candidates = [
        weekly_dir / "intelligence" / "opportunities.csv",
        weekly_dir / "opportunities.csv",
        weekly_dir / "delivery" / "opportunities.csv",
        weekly_dir / "lists" / "opportunities.csv",
    ]
    # also scan one level
    for p in weekly_dir.rglob("opportunities*.csv"):
        candidates.append(p)
    seen: set[str] = set()
    for c in candidates:
        key = str(c.resolve()) if c.exists() else ""
        if not key or key in seen:
            continue
        seen.add(key)
        if c.is_file() and c.stat().st_size > 0:
            with c.open(encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            if rows:
                return rows
    # JSONL fallbacks
    for name in ("opportunities.jsonl", "intelligence/opportunities.jsonl"):
        p = weekly_dir / name
        if p.is_file():
            out = []
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    out.append(json.loads(line))
            if out:
                return out
    return []


def run_loop(
    *,
    weekly_dir: Path,
    out_dir: Path,
    profile_path: Path,
    max_shortlist: int = 5,
    require_weekly_ok: bool = True,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    profile_val = validate_profile(profile_path)
    if not profile_val["ok"]:
        return {
            "ok": False,
            "terminal_state": "BLOCKED_INVALID_PROFILE",
            "errors": profile_val["errors"],
            "profile": profile_val,
        }
    profile_stamp = stamp(profile_path)

    weekly = validate_weekly_pack(weekly_dir)
    weekly_ok = bool(getattr(weekly, "ok", False))
    weekly_exit = getattr(weekly, "exit_code", None)
    if require_weekly_ok and (not weekly_ok or weekly_exit not in (None, 0)):
        payload = {
            "ok": False,
            "terminal_state": "BLOCKED_WEEKLY_NOT_CONSULTIVE",
            "weekly": {
                "ok": weekly_ok,
                "exit_code": weekly_exit,
                "errors": list(getattr(weekly, "errors", []) or []),
                "cycle_id": getattr(weekly, "cycle_id", None),
                "weekly_dir": str(weekly_dir),
            },
            "profile_stamp": profile_stamp,
        }
        _write_json(out_dir / "result.json", payload)
        return payload

    # Prefer path declared by weekly pack validation when present
    rows: list[dict[str, Any]] = []
    opp_path = getattr(weekly, "opportunities_path", None)
    if opp_path and Path(opp_path).is_file():
        import csv as _csv

        with Path(opp_path).open(encoding="utf-8", newline="") as f:
            rows = list(_csv.DictReader(f))
    if not rows:
        rows = _load_opportunities_csv(weekly_dir)
    summary = classify_batch(
        rows,
        profile_path=str(profile_path),
        max_shortlist=max_shortlist,
    )
    summary["weekly_dir"] = str(weekly_dir)
    summary["campaign"] = CAMPAIGN
    summary["run_generated_at"] = utc_now()
    summary["profile_stamp"] = profile_stamp

    _write_json(out_dir / "actionable-summary.json", {k: v for k, v in summary.items() if k != "all_results"})
    _write_json(out_dir / "actionable-all.json", summary.get("all_results") or [])
    _write_json(out_dir / "shortlist.json", {
        "schema": SCHEMA,
        "result": summary["result"],
        "shortlist": summary["shortlist"],
        "shortlist_count": summary["shortlist_count"],
        "profile_stamp": profile_stamp,
        "by_state": summary["by_state"],
        "candidates_evaluated": summary["candidates_evaluated"],
        "coverage_actions": summary["coverage_actions"],
        "critical_profile_pending": summary["critical_profile_pending"],
    })

    # Executive markdown
    md = _executive_md(summary, profile_stamp, weekly_dir)
    (out_dir / "executive-summary.md").write_text(md, encoding="utf-8")

    # Initial state — ready for human, never PASS (no auto-finalize)
    ready = {
        "schema": "extra-decision-review/1.0",
        "terminal_state": READY_FOR_HUMAN,
        "finalized_at": None,
        "finalized_by": None,
        "package_decision": None,
        "notes": "Package generated; awaiting human decisions via extra_decision_review",
        "decisions": [],
        "n_decisions": 0,
        "shortlist_count": summary["shortlist_count"],
        "result": summary["result"],
        "bundle_hash": sha256_file(out_dir / "actionable-summary.json"),
        "profile_stamp": profile_stamp,
        "ready_reason": "Human must record decisions and finalize",
        "generated_at": utc_now(),
    }
    _write_json(out_dir / STATE_NAME, ready)

    result = {
        "ok": True,
        "schema": SCHEMA,
        "campaign": CAMPAIGN,
        "terminal_state": READY_FOR_HUMAN,
        "result": summary["result"],
        "shortlist_count": summary["shortlist_count"],
        "candidates_evaluated": summary["candidates_evaluated"],
        "by_state": summary["by_state"],
        "profile_stamp": profile_stamp,
        "out_dir": str(out_dir),
        "weekly_dir": str(weekly_dir),
        "soak_touched": False,
        "human_acceptance": "NOT_PROVIDED",
        "next_commands": [
            f"python3 -m scripts.ops.extra_decision_review list --run-dir {out_dir}",
            (
                f"python3 -m scripts.ops.extra_decision_review accept-empty --run-dir {out_dir} "
                f'--actor tiago --reason "..."'
                if summary["result"] == "NO_ACTIONABLE_TENDER"
                else f"python3 -m scripts.ops.extra_decision_review decide <ID> --run-dir {out_dir} "
                f"--decision ACCEPT|REJECT|DEFER --reason '...' --actor tiago"
            ),
            f"python3 -m scripts.ops.extra_decision_review finalize --run-dir {out_dir} "
            f"--actor tiago --package-decision ACCEPTED",
        ],
    }
    _write_json(out_dir / "result.json", result)
    return result


def _executive_md(summary: dict[str, Any], profile_stamp: dict[str, Any], weekly_dir: Path) -> str:
    lines = [
        f"# Extra — Decision loop ({CAMPAIGN})",
        "",
        f"- **Gerado:** {summary.get('run_generated_at')}",
        f"- **Weekly:** `{weekly_dir}`",
        f"- **Perfil:** `{profile_stamp.get('stamp')}`",
        f"- **profile_hash:** `{profile_stamp.get('profile_hash')}`",
        f"- **Resultado:** **{summary.get('result')}**",
        f"- **Candidatos avaliados:** {summary.get('candidates_evaluated')}",
        f"- **Shortlist:** {summary.get('shortlist_count')}",
        "",
        "## Distribuição de estados",
        "",
    ]
    for k, v in sorted((summary.get("by_state") or {}).items()):
        lines.append(f"- `{k}`: {v}")
    lines.extend(["", "## Shortlist acionável", ""])
    sl = summary.get("shortlist") or []
    if not sl:
        lines.append(
            f"**NO_ACTIONABLE_TENDER** — vazio defensável. "
            f"Expirados={summary.get('expired')}, "
            f"sem prazo verificável={summary.get('no_verifiable_future_deadline')}, "
            f"bloqueados por perfil={summary.get('profile_blocked')}, "
            f"fonte insuficiente={summary.get('insufficient_source')}."
        )
        lines.append("")
        lines.append("### Ações para aumentar cobertura")
        for a in summary.get("coverage_actions") or []:
            lines.append(f"- {a}")
    else:
        lines.append("| # | ID | Estado | Órgão | Objeto | Dias |")
        lines.append("|---|----|--------|-------|--------|------|")
        for i, item in enumerate(sl, 1):
            ev = item.get("evidence") or {}
            days = item.get("score_components", {}).get("days_remaining")
            days_s = f"{days:.1f}" if isinstance(days, (int, float)) else "—"
            lines.append(
                f"| {i} | `{item.get('opportunity_id')}` | {item.get('state')} | "
                f"{(ev.get('orgao') or '')[:40]} | {(ev.get('objeto') or '')[:50]} | {days_s} |"
            )
    lines.extend(
        [
            "",
            "## Premissas e ausências",
            "",
            f"- Campos críticos PENDING no perfil: "
            f"{', '.join(summary.get('critical_profile_pending') or []) or 'nenhum listado'}",
            "- Ausência de dado **não** foi convertida em capacidade.",
            "- Aceite humano **não** foi fabricado (estado READY_FOR_HUMAN_ACCEPTANCE).",
            "",
            "## Próximo passo",
            "",
            "Registrar decisões com `scripts.ops.extra_decision_review` e só então emitir "
            "`PASS_EXTRA_DECISION_LOOP_ACCEPTED` via finalize com package-decision humana.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extra profile→actionable→decision loop")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run", help="Run decision loop from weekly pack")
    p_run.add_argument("--weekly-dir", required=True)
    p_run.add_argument("--out", required=True)
    p_run.add_argument(
        "--profile",
        default="config/client_profiles/extra.yaml",
    )
    p_run.add_argument("--max-shortlist", type=int, default=5)
    p_run.add_argument(
        "--allow-unreliable-weekly",
        action="store_true",
        help="Do not block when weekly exit_code != 0 (not for consultive claims)",
    )
    args = parser.parse_args(argv)
    if args.cmd == "run":
        result = run_loop(
            weekly_dir=Path(args.weekly_dir),
            out_dir=Path(args.out),
            profile_path=Path(args.profile),
            max_shortlist=args.max_shortlist,
            require_weekly_ok=not args.allow_unreliable_weekly,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return 0 if result.get("ok") else 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
