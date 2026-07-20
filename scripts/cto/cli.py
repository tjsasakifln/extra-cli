#!/usr/bin/env python3
"""CTO Autopilot CLI.

Commands:
  doctor, observe, status, issues-plan, issues-sync, issues-audit,
  rank, decide, prepare, run-once, resume, pause, verify,
  refresh-executive, audit, deepseek-smoke, reconcile-queue, publish
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Ensure repo root on path when run as python -m scripts.cto.cli
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.cto.budget import check_budget, record_usage  # noqa: E402
from scripts.cto.config import load_config  # noqa: E402
from scripts.cto.decision import (  # noqa: E402
    decide_from_observation,
    review_execution,
    save_decision,
)
from scripts.cto.deepseek_client import DeepSeekClient  # noqa: E402
from scripts.cto.executive_sync import refresh_executive  # noqa: E402
from scripts.cto.github_issues import (  # noqa: E402
    audit_issues,
    gh_auth_ok,
    plan_issues,
    sync_issues,
    update_issue_for_cycle,
)
from scripts.cto.grok_executor import execute as grok_execute  # noqa: E402
from scripts.cto.ledger import append_ledger, read_ledger  # noqa: E402
from scripts.cto.observer import observe, status_summary  # noqa: E402
from scripts.cto.paths import (  # noqa: E402
    cto_dir,
    current_dir,
    cycles_dir,
    decision_path,
    decision_schema_path,
    observation_path,
    policies_path,
    repo_root,
    review_schema_path,
)
from scripts.cto.publisher import publish_after_accept  # noqa: E402
from scripts.cto.redaction import redact_obj  # noqa: E402
from scripts.cto.state_machine import LockError, StateMachine  # noqa: E402
from scripts.cto.verifier import verify  # noqa: E402
from scripts.cto.work_registry import (  # noqa: E402
    apply_readiness_gates,
    build_initial_registry,
    get_by_work_id,
    load_registry,
    reconcile_implemented_items,
    save_registry,
    work_item_public_view,
)


def _reconcile_queue_for_cycle(root: Path) -> dict[str, Any]:
    """Ensure registry readiness before observe/decide. Never auto-closes Issues."""
    reg = load_registry(root)
    if not reg.get("work_items"):
        reg = build_initial_registry(root)
    moved = reconcile_implemented_items(
        reg,
        evidence=[
            "PR #48 https://github.com/tjsasakifln/extra-consultoria/pull/48",
            "scripts/cto/* + tests/cto/* on feat/cto-autopilot-issues-deepseek-20260719",
        ],
        target_state="review",
    )
    gates = apply_readiness_gates(reg)
    path = save_registry(reg, root)
    return {
        "registry_path": str(path),
        "reconciled": moved,
        "readiness_gates": gates,
        "auto_closed": False,
    }

# Exit codes: distinguish operational outcomes
EXIT_OK = 0  # work accepted + published path complete, or clean NOOP
EXIT_ERROR = 1  # unexpected failure
EXIT_LOCK = 2
EXIT_BUDGET = 3
EXIT_WAITING_HUMAN = 10
EXIT_BLOCKED = 11
EXIT_FAILED = 12
EXIT_ROLLBACK = 13
EXIT_CYCLE_COMPLETE_PENDING = 14  # executed/accepted locally but integration pending


def _print(data: Any) -> None:
    print(json.dumps(redact_obj(data), indent=2, ensure_ascii=False, default=str))


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def exit_code_for_status(status: str, *, review_verdict: str | None = None) -> int:
    """Map terminal machine status to process exit code (not generic success)."""
    if status in {"WAITING_HUMAN"}:
        return EXIT_WAITING_HUMAN
    if status in {"BLOCKED"}:
        return EXIT_BLOCKED
    if status in {"FAILED"}:
        return EXIT_FAILED
    if review_verdict == "ROLLBACK" or status == "ROLLBACK":
        return EXIT_ROLLBACK
    if status in {"DONE", "ACCEPTED", "IDLE", "ACCEPTED_DRY_RUN"}:
        return EXIT_OK
    if status == "PAUSED":
        return EXIT_BUDGET
    return EXIT_ERROR


def cmd_doctor(_: argparse.Namespace) -> int:
    root = repo_root()
    cfg = load_config(root)
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    add("repo_root", root.is_dir(), str(root))
    add("cto_dir", cto_dir(root).is_dir())
    add("charter", (cto_dir(root) / "CHARTER.md").is_file())
    add("policies", policies_path(root).is_file())
    add("decision_schema", decision_schema_path(root).is_file())
    add("review_schema", review_schema_path(root).is_file())
    add("prompts_decide", (cto_dir(root) / "prompts" / "decide.md").is_file())
    add("prompts_review", (cto_dir(root) / "prompts" / "review.md").is_file())
    add("gh_cli", shutil.which("gh") is not None)
    add("gh_auth", gh_auth_ok(root))
    add("grok_cli", shutil.which("grok") is not None)
    add("deepseek_key_present", cfg.deepseek.configured, "set=yes" if cfg.deepseek.configured else "missing")
    add("deepseek_model", bool(cfg.deepseek.model), cfg.deepseek.model)
    add("deepseek_base_url", bool(cfg.deepseek.base_url), cfg.deepseek.base_url)
    add("python_yaml", True)
    add("python_httpx", True)
    try:
        import httpx  # noqa: F401
        import yaml  # noqa: F401
    except ImportError as exc:
        add("python_deps", False, str(exc))
    else:
        add("python_deps", True)
    add("output_dir_writable", True)
    try:
        current_dir(root).mkdir(parents=True, exist_ok=True)
        probe = current_dir(root) / ".doctor_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        checks[-1] = {"name": "output_dir_writable", "ok": False, "detail": str(exc)}
    add("publisher_module", True, "scripts.cto.publisher")

    ok_all = all(c["ok"] for c in checks if c["name"] != "grok_cli")
    _print({"ok": ok_all, "checks": checks})
    return 0 if ok_all else 1


def cmd_observe(args: argparse.Namespace) -> int:
    root = repo_root()
    sm = StateMachine(root)
    try:
        sm.lock.acquire("observe")
    except LockError as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_LOCK
    try:
        sm.transition("OBSERVING", reason="cli observe")
        obs = observe(root, write=not args.no_write)
        sm.transition(
            "IDLE",
            reason="observe complete",
            cycle_id=(obs.get("roi_cycle") or {}).get("cycle_id"),
        )
        append_ledger("observe", {"keys": list(obs.keys())}, root=root)
        _print(
            {
                "ok": True,
                "path": str(observation_path(root)),
                "summary": {
                    "branch": (obs.get("git") or {}).get("branch"),
                    "commit": (obs.get("git") or {}).get("commit"),
                    "dod": obs.get("dod"),
                    "open_issues": (obs.get("issues") or {}).get("open_count"),
                    "open_prs": len(obs.get("prs") or []),
                    "ranking_stale": (obs.get("ranking") or {}).get("stale"),
                    "work_items": (obs.get("work_items") or {}).get("count"),
                    "divergences": len(obs.get("divergences") or []),
                },
            }
        )
        return EXIT_OK
    finally:
        sm.lock.release()


def cmd_status(_: argparse.Namespace) -> int:
    _print(status_summary(repo_root()))
    return EXIT_OK


def cmd_issues_plan(_: argparse.Namespace) -> int:
    root = repo_root()
    reg = load_registry(root)
    if not reg.get("work_items"):
        obs = {}
        if observation_path(root).is_file():
            try:
                obs = json.loads(observation_path(root).read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                obs = {}
        reg = build_initial_registry(root, observation=obs)
        save_registry(reg, root)
    plan = plan_issues(root)
    _print(plan)
    return EXIT_OK


def cmd_issues_sync(args: argparse.Namespace) -> int:
    root = repo_root()
    reg = load_registry(root)
    if not reg.get("work_items"):
        obs = observe(root, write=True)
        reg = build_initial_registry(root, observation=obs)
        save_registry(reg, root)
    result = sync_issues(root, apply=args.apply)
    _print(result)
    return EXIT_OK


def cmd_issues_audit(_: argparse.Namespace) -> int:
    _print(audit_issues(repo_root()))
    return EXIT_OK


def cmd_reconcile_queue(args: argparse.Namespace) -> int:
    """Reconcile readiness + mark PR#48 implemented items as review (no auto-close)."""
    root = repo_root()
    reg = load_registry(root)
    if not reg.get("work_items"):
        reg = build_initial_registry(root, observation=observe(root, write=True))
    moved = reconcile_implemented_items(
        reg,
        evidence=[
            "PR #48 https://github.com/tjsasakifln/extra-consultoria/pull/48",
            "scripts/cto/* + tests/cto/* implemented on feat/cto-autopilot-issues-deepseek-20260719",
        ],
        target_state="review" if not args.human else "human",
    )
    gates = apply_readiness_gates(reg)
    path = save_registry(reg, root)
    out = {
        "ok": True,
        "registry_path": str(path),
        "reconciled": moved,
        "readiness_gates": gates,
        "auto_closed": False,
        "note": "Issues not closed; sync labels via issues-sync --apply when ready",
    }
    if args.apply_issues:
        # update labels for moved items without closing
        for m in moved.get("moved") or []:
            if m.get("issue_number"):
                update_issue_for_cycle(
                    root=root,
                    issue_number=m["issue_number"],
                    work_id=m.get("work_id"),
                    phase="review" if not args.human else "human",
                    cycle_id="reconcile-pr48",
                    dry_run=not args.apply_issues,
                )
        out["issues_updated"] = True
    _print(out)
    return EXIT_OK


def cmd_rank(_: argparse.Namespace) -> int:
    root = repo_root()
    obs = observe(root, write=False)
    _print({"ranking": obs.get("ranking"), "note": "advisory only — CTO decides"})
    return EXIT_OK


def cmd_decide(args: argparse.Namespace) -> int:
    root = repo_root()
    cfg = load_config(root)
    sm = StateMachine(root)
    try:
        sm.lock.acquire("decide")
    except LockError as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_LOCK
    try:
        ok_b, reason = check_budget(cfg.budgets, root)
        if not ok_b:
            sm.transition("PAUSED", reason=f"budget: {reason}")
            _print({"ok": False, "error": reason, "status": "PAUSED"})
            return EXIT_BUDGET
        cur = sm.load()
        if cur.status in {"WAITING_HUMAN", "BLOCKED", "FAILED", "DONE", "ACCEPTED"}:
            try:
                sm.transition("IDLE", reason="decide re-entry")
            except Exception:  # noqa: BLE001
                st = sm.load()
                st.status = "IDLE"
                sm.save(st)
        recon = _reconcile_queue_for_cycle(root)
        if not observation_path(root).is_file() or args.refresh:
            observe(root, write=True)
        else:
            # Refresh observation after reconcile so ready sets are honest
            observe(root, write=True)
        obs = json.loads(observation_path(root).read_text(encoding="utf-8"))
        if sm.load().status == "IDLE":
            sm.transition("OBSERVING", reason="decide pre-observe")
            sm.transition("DECIDING", reason="cli decide")
        else:
            sm.transition("DECIDING", reason="cli decide")
        decision = decide_from_observation(
            obs,
            config=cfg,
            dry_run=args.dry_run,
            root=root,
        )
        decision.setdefault("_meta", {})["queue_reconcile"] = recon
        save_decision(decision, root)
        usage = (decision.get("_meta") or {}).get("usage") or {}
        if usage:
            raw_tokens = usage.get("total_tokens") or 0
            try:
                token_count = int(raw_tokens)
            except (TypeError, ValueError):
                token_count = 0
            record_usage(api_calls=1, tokens=token_count, root=root)
        cycle_id = decision.get("cycle_id")
        action = decision.get("decision")
        extra = {
            "decision_id": decision.get("decision_id"),
            "work_id": decision.get("work_id"),
            "issue_number": decision.get("issue_number"),
        }
        if action in {"ESCALATE", "BLOCK"} or (decision.get("human_gate") or {}).get("required"):
            sm.transition(
                "WAITING_HUMAN" if action == "ESCALATE" else "BLOCKED",
                reason=decision.get("strategic_reason") or action,
                cycle_id=cycle_id,
                extra=extra,
            )
        elif action == "NOOP":
            sm.transition("IDLE", reason="NOOP", cycle_id=cycle_id, extra=extra)
        else:
            sm.transition("IDLE", reason=f"decided {action}", cycle_id=cycle_id, extra=extra)
        append_ledger(
            "decide",
            {"decision": action, "decision_id": decision.get("decision_id")},
            root=root,
            cycle_id=cycle_id,
        )
        _print({"ok": True, "decision": decision, "path": str(decision_path(root))})
        st = sm.load().status
        return exit_code_for_status(st)
    finally:
        sm.lock.release()


def cmd_prepare(args: argparse.Namespace) -> int:
    root = repo_root()
    sm = StateMachine(root)
    if not decision_path(root).is_file():
        _print({"ok": False, "error": "no decision.json — run decide first"})
        return EXIT_ERROR
    decision = json.loads(decision_path(root).read_text(encoding="utf-8"))
    sm.transition("PREPARING", reason="cli prepare", cycle_id=decision.get("cycle_id"))
    from scripts.cto.grok_executor import prepare_worktree, render_prompt

    cycle_id = decision.get("cycle_id") or f"cyc-{uuid.uuid4().hex[:10]}"
    prep = prepare_worktree(cycle_id=cycle_id, root=root)
    prompt = render_prompt(
        "grok-execute.md",
        {
            "objective": decision.get("objective") or "",
            "cycle_id": cycle_id,
            "decision_id": decision.get("decision_id") or "",
            "issue_number": decision.get("issue_number") or "",
            "work_id": decision.get("work_id") or "",
            "acceptance_criteria": decision.get("acceptance_criteria") or [],
            "required_evidence": decision.get("required_evidence") or [],
            "allowed_paths": decision.get("allowed_paths") or [],
            "forbidden_paths": decision.get("forbidden_paths") or [],
            "test_commands": decision.get("test_commands") or [],
            "forbidden_actions": decision.get("forbidden_actions") or [],
        },
        root,
    )
    cdir = cycles_dir(root) / cycle_id
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "prepared_prompt.md").write_text(prompt, encoding="utf-8")
    (cdir / "decision.json").write_text(
        json.dumps(decision, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    sm.transition("IDLE", reason="prepare complete", cycle_id=cycle_id)
    _print({"ok": True, "prepare": prep, "prompt_path": str(cdir / "prepared_prompt.md")})
    return EXIT_OK


def cmd_verify(args: argparse.Namespace) -> int:
    root = repo_root()
    if not decision_path(root).is_file():
        _print({"ok": False, "error": "no decision.json"})
        return EXIT_ERROR
    decision = json.loads(decision_path(root).read_text(encoding="utf-8"))
    sm = StateMachine(root)
    sm.transition("VERIFYING", reason="cli verify", cycle_id=decision.get("cycle_id"))
    execution = None
    cdir = cycles_dir(root) / str(decision.get("cycle_id") or "")
    if (cdir / "execution.json").is_file():
        try:
            execution = json.loads((cdir / "execution.json").read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            execution = None
    result = verify(
        decision=decision,
        root=root,
        skip_tests=args.skip_tests,
        execution=execution,
    )
    sm.transition("IDLE", reason=f"verify {result.get('result')}", cycle_id=decision.get("cycle_id"))
    _print(result)
    return EXIT_OK if result.get("result") == "PASS" else EXIT_FAILED


def _load_cycle_artifacts(root: Path, cycle_id: str) -> dict[str, Any]:
    cdir = cycles_dir(root) / cycle_id
    out: dict[str, Any] = {"cycle_dir": str(cdir)}
    for name in (
        "decision.json",
        "execution.json",
        "verification.json",
        "review.json",
        "publication.json",
    ):
        fp = cdir / name
        if fp.is_file():
            try:
                out[name.replace(".json", "")] = json.loads(fp.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                out[name.replace(".json", "")] = {"error": "parse_error"}
    return out


def _block_live_skip_tests(
    *,
    args: argparse.Namespace,
    sm: StateMachine,
    report: dict[str, Any],
    cycle_id: str | None = None,
) -> int | None:
    """Live cycles must not skip tests (ACCEPT/publish forbidden).

    --skip-tests remains valid for dry-run, mock diagnosis, and standalone
    verify — never for a live run that could reach ACCEPT or publisher.
    """
    if not getattr(args, "skip_tests", False):
        return None
    if getattr(args, "dry_run", False):
        return None
    # mock without dry_run is still non-publishing diagnostic only if skip_publish
    # but mission: non dry-run + skip_tests → BLOCKED_UNVERIFIED
    reason = "BLOCKED_UNVERIFIED: --skip-tests forbidden on live cycle (no ACCEPT/publish)"
    try:
        sm.transition("BLOCKED", reason=reason, cycle_id=cycle_id)
    except Exception:  # noqa: BLE001
        st = sm.load()
        st.status = "BLOCKED"
        st.last_error = reason
        if cycle_id:
            st.cycle_id = cycle_id
        sm.save(st)
    report["ok"] = False
    report["operational_success"] = False
    report["error"] = reason
    report["outcome"] = "blocked_unverified"
    report["terminal_status"] = "BLOCKED"
    report["skip_tests_blocked"] = True
    _print(report)
    return EXIT_BLOCKED


def _run_cycle_from_decision(
    *,
    root: Path,
    cfg: Any,
    sm: StateMachine,
    decision: dict[str, Any],
    args: argparse.Namespace,
    report: dict[str, Any],
    start_phase: str = "PREPARING",
) -> int:
    """Shared execute→verify→review→publish path used by run-once and resume."""
    cycle_id = decision.get("cycle_id")
    blocked = _block_live_skip_tests(args=args, sm=sm, report=report, cycle_id=str(cycle_id) if cycle_id else None)
    if blocked is not None:
        return blocked
    cdir = cycles_dir(root) / str(cycle_id)
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "decision.json").write_text(
        json.dumps(decision, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    # Load prior attempts if any
    prior_attempts: list[dict[str, Any]] = []
    if (cdir / "attempts.jsonl").is_file():
        for ln in (cdir / "attempts.jsonl").read_text(encoding="utf-8").splitlines():
            try:
                prior_attempts.append(json.loads(ln))
            except json.JSONDecodeError:
                continue

    work_item = None
    if decision.get("work_id"):
        reg = load_registry(root)
        raw = get_by_work_id(reg, str(decision["work_id"]))
        if raw:
            work_item = work_item_public_view(raw)

    execution: dict[str, Any] = {}
    verification: dict[str, Any] = {}
    review: dict[str, Any] = {}

    arts = _load_cycle_artifacts(root, str(cycle_id))

    if start_phase in {"PREPARING", "EXECUTING"}:
        if start_phase == "PREPARING":
            sm.transition("PREPARING", reason="cycle prepare", cycle_id=cycle_id)
            issue_upd = update_issue_for_cycle(
                root=root,
                issue_number=decision.get("issue_number"),
                work_id=decision.get("work_id"),
                phase="preparing",
                cycle_id=cycle_id,
                decision_id=decision.get("decision_id"),
                dry_run=args.dry_run,
            )
            report["steps"].append({"step": "issue-update-preparing", **issue_upd})

        sm.transition("EXECUTING", reason="cycle execute", cycle_id=cycle_id)
        update_issue_for_cycle(
            root=root,
            issue_number=decision.get("issue_number"),
            work_id=decision.get("work_id"),
            phase="executing",
            cycle_id=cycle_id,
            decision_id=decision.get("decision_id"),
            dry_run=args.dry_run,
        )
        execution = grok_execute(
            decision,
            root=root,
            dry_run=args.dry_run,
            mock=args.mock,
        )
        report["steps"].append({"step": "execute", "status": execution.get("status")})
        start_phase = "VERIFYING"
    elif start_phase == "VERIFYING":
        execution = arts.get("execution") or {}
        if not execution:
            execution = grok_execute(
                decision, root=root, dry_run=args.dry_run, mock=args.mock
            )
    elif start_phase in {"REVIEWING", "REPAIRING"}:
        execution = arts.get("execution") or {}
        verification = arts.get("verification") or {}

    if start_phase in {"VERIFYING", "REVIEWING", "REPAIRING"} and start_phase != "REVIEWING":
        sm.transition("VERIFYING", reason="cycle verify", cycle_id=cycle_id)
        verification = verify(
            decision=decision,
            worktree=Path(execution["worktree"]) if execution.get("worktree") else None,
            root=root,
            skip_tests=args.skip_tests or args.dry_run,
            execution=execution,
        )
        report["steps"].append({"step": "verify", "result": verification.get("result")})
        start_phase = "REVIEWING"

    if start_phase in {"REVIEWING", "REPAIRING"}:
        if start_phase == "REPAIRING":
            # re-enter repair loop
            pass
        else:
            sm.transition("REVIEWING", reason="cycle review", cycle_id=cycle_id)
            transcript = None
            if execution.get("transcript_path") and Path(execution["transcript_path"]).is_file():
                transcript = Path(execution["transcript_path"]).read_text(encoding="utf-8")[-8000:]
            review = review_execution(
                decision=decision,
                verification=verification,
                execution=execution,
                config=cfg,
                dry_run=args.dry_run,
                work_item=work_item,
                prior_attempts=prior_attempts,
                transcript_excerpt=transcript,
            )
            report["steps"].append({"step": "review", "verdict": review.get("verdict")})
            (cdir / "review.json").write_text(
                json.dumps(review, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )

        repair_attempt = int(sm.load().repair_attempt or 0)
        max_repairs = int(decision.get("max_repair_attempts") or cfg.budgets.max_repair_attempts)
        while (
            review.get("verdict") == "REPAIR"
            and repair_attempt < max_repairs
            and not args.dry_run
        ):
            repair_attempt += 1
            sm.transition(
                "REPAIRING",
                reason=f"repair {repair_attempt}",
                cycle_id=cycle_id,
                extra={"repair_attempt": repair_attempt},
            )
            execution = grok_execute(
                decision,
                root=root,
                dry_run=False,
                mock=args.mock,
                repair=True,
                repair_context={
                    "failed_criteria": review.get("failed_criteria"),
                    "repair_instructions": review.get("repair_instructions"),
                    "attempt": repair_attempt,
                },
            )
            verification = verify(
                decision=decision,
                worktree=Path(execution["worktree"]) if execution.get("worktree") else None,
                root=root,
                skip_tests=args.skip_tests,
                execution=execution,
            )
            review = review_execution(
                decision=decision,
                verification=verification,
                execution=execution,
                config=cfg,
                dry_run=False,
                work_item=work_item,
                prior_attempts=prior_attempts,
            )
            with (cdir / "attempts.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(
                        {
                            "attempt": repair_attempt,
                            "verify": verification.get("result"),
                            "review": review.get("verdict"),
                        }
                    )
                    + "\n"
                )
            report["steps"].append(
                {
                    "step": f"repair_{repair_attempt}",
                    "verify": verification.get("result"),
                    "review": review.get("verdict"),
                }
            )

    publication = None
    repair_attempt = int(sm.load().repair_attempt or 0)
    max_repairs = int(decision.get("max_repair_attempts") or cfg.budgets.max_repair_attempts)
    if review.get("verdict") == "ACCEPT":
        sm.transition("ACCEPTED", reason="review ACCEPT", cycle_id=cycle_id)
        # Separate publisher — never Grok executor; sealed SHA only
        publication = publish_after_accept(
            decision=decision,
            worktree=Path(execution["worktree"]) if execution.get("worktree") else None,
            root=root,
            dry_run=args.dry_run or getattr(args, "skip_publish", False),
            skip_push=getattr(args, "skip_push", False) or args.dry_run,
            verification=verification,
            review=review,
            allow_unsealed_legacy=bool(args.dry_run),
        )
        report["steps"].append(
            {
                "step": "publish",
                **{
                    k: publication.get(k)
                    for k in ("ok", "status", "pr", "commit", "queue_mutated")
                },
            }
        )
        report["publication"] = publication
        pub_status = str(publication.get("status") or "")
        if pub_status == "WAITING_HUMAN" and (publication.get("pr") or {}).get("number"):
            sm.transition(
                "WAITING_HUMAN",
                reason="draft PR awaiting Tiago merge",
                cycle_id=cycle_id,
                extra={
                    "meta_pr_url": (publication.get("pr") or {}).get("url"),
                    "meta_pr_number": (publication.get("pr") or {}).get("number"),
                },
            )
            final_phase = "human"
        elif pub_status == "ACCEPTED_DRY_RUN":
            # Dry-run: accepted locally, no human queue pollution
            sm.transition("DONE", reason="dry-run accept without real draft PR", cycle_id=cycle_id)
            final_phase = "accepted"
        else:
            sm.transition(
                "FAILED",
                reason=publication.get("error") or "publication failed",
                cycle_id=cycle_id,
            )
            final_phase = "failed"
    elif review.get("verdict") == "ESCALATE":
        sm.transition("WAITING_HUMAN", reason=review.get("summary") or "", cycle_id=cycle_id)
        final_phase = "human"
    elif review.get("verdict") == "BLOCK":
        sm.transition("BLOCKED", reason=review.get("summary") or "", cycle_id=cycle_id)
        final_phase = "blocked"
    elif review.get("verdict") == "ROLLBACK":
        sm.transition("FAILED", reason="ROLLBACK", cycle_id=cycle_id)
        final_phase = "failed"
    else:
        final_phase = "failed"
        sm.transition(
            "WAITING_HUMAN" if repair_attempt >= max_repairs else "FAILED",
            reason=review.get("summary") or review.get("verdict") or "unresolved",
            cycle_id=cycle_id,
        )

    issue_final = update_issue_for_cycle(
        root=root,
        issue_number=decision.get("issue_number"),
        work_id=decision.get("work_id"),
        phase=final_phase,
        cycle_id=cycle_id,
        decision_id=decision.get("decision_id"),
        review_verdict=review.get("verdict"),
        verification_result=verification.get("result"),
        dry_run=args.dry_run,
    )
    report["steps"].append({"step": "issue-update-final", **issue_final})

    refresh_executive(root)
    report["steps"].append({"step": "refresh-executive", "ok": True})
    record_usage(cycles=1, root=root)

    terminal = sm.load().status
    report["decision"] = {
        "decision": decision.get("decision"),
        "decision_id": decision.get("decision_id"),
        "work_id": decision.get("work_id"),
        "issue_number": decision.get("issue_number"),
    }
    report["review"] = review
    report["verification"] = {
        "result": verification.get("result"),
        "matrix_len": len(verification.get("criterion_matrix") or []),
    }
    report["terminal_status"] = terminal
    report["operational"] = {
        "execution_completed": bool(execution),
        "work_accepted": review.get("verdict") == "ACCEPT",
        "pr_created": bool((publication or {}).get("pr", {}).get("url") or (publication or {}).get("pr", {}).get("number")),
        "integration_pending": terminal == "WAITING_HUMAN",
        "merge_authority": "Tiago",
        "auto_merge": False,
    }
    # ok means cycle ran without crash — not that work is integrated
    report["ok"] = terminal not in {"FAILED"} or bool(review)
    report["success"] = terminal in {"DONE", "ACCEPTED"} and review.get("verdict") == "ACCEPT"
    # Never report BLOCKED/FAILED/WAITING_HUMAN as generic operational success
    report["operational_success"] = terminal in {"DONE", "IDLE"} and review.get("verdict") in {
        "ACCEPT",
        None,
    }
    if terminal == "WAITING_HUMAN" and review.get("verdict") == "ACCEPT":
        report["operational_success"] = False
        report["outcome"] = "accepted_awaiting_human_merge"
    elif terminal == "WAITING_HUMAN":
        report["outcome"] = "waiting_human"
    elif terminal == "BLOCKED":
        report["outcome"] = "blocked"
    elif terminal == "FAILED":
        report["outcome"] = "failed"
    else:
        report["outcome"] = terminal.lower()

    append_ledger(
        "run_once",
        {
            "ok": report.get("ok"),
            "cycle_id": cycle_id,
            "terminal": terminal,
            "outcome": report.get("outcome"),
        },
        root=root,
        cycle_id=cycle_id,
    )
    _print(report)
    return exit_code_for_status(terminal, review_verdict=review.get("verdict"))


def cmd_run_once(args: argparse.Namespace) -> int:
    """Full safe cycle: observe → decide → prepare → execute → verify → review → publish."""
    root = repo_root()
    cfg = load_config(root)
    sm = StateMachine(root)
    try:
        sm.lock.acquire("run-once")
    except LockError as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_LOCK

    report: dict[str, Any] = {"steps": [], "ok": False, "operational_success": False}
    try:
        early = _block_live_skip_tests(args=args, sm=sm, report=report)
        if early is not None:
            return early
        ok_b, reason = check_budget(cfg.budgets, root)
        if not ok_b:
            sm.transition("PAUSED", reason=f"budget: {reason}")
            report["error"] = reason
            report["terminal_status"] = "PAUSED"
            _print(report)
            return EXIT_BUDGET

        cur = sm.load()
        if cur.status in {"DONE", "ACCEPTED", "FAILED", "BLOCKED"}:
            try:
                sm.transition("IDLE", reason="run-once re-entry")
            except Exception:  # noqa: BLE001
                st = sm.load()
                st.status = "IDLE"
                sm.save(st)

        recon = _reconcile_queue_for_cycle(root)
        report["steps"].append({"step": "reconcile-queue", **{k: recon.get(k) for k in ("auto_closed",)}})
        report["reconcile"] = recon

        sm.transition("OBSERVING", reason="run-once")
        obs = observe(root, write=True)
        report["steps"].append({"step": "observe", "ok": True})

        sm.transition("DECIDING", reason="run-once")
        decision = decide_from_observation(obs, config=cfg, dry_run=args.dry_run, root=root)
        save_decision(decision, root)
        usage = (decision.get("_meta") or {}).get("usage") or {}
        if usage:
            raw_tokens = usage.get("total_tokens") or 0
            try:
                token_count = int(raw_tokens)
            except (TypeError, ValueError):
                token_count = 0
            record_usage(api_calls=1, tokens=token_count, root=root)
        report["steps"].append({"step": "decide", "decision": decision.get("decision")})
        cycle_id = decision.get("cycle_id")

        if decision.get("decision") in {"BLOCK", "ESCALATE", "NOOP", "ACCEPT"}:
            if decision.get("decision") == "ESCALATE" or (decision.get("human_gate") or {}).get(
                "required"
            ):
                sm.transition(
                    "WAITING_HUMAN",
                    reason=decision.get("strategic_reason") or "",
                    cycle_id=cycle_id,
                )
            elif decision.get("decision") == "BLOCK":
                sm.transition(
                    "BLOCKED",
                    reason=decision.get("strategic_reason") or "",
                    cycle_id=cycle_id,
                )
            else:
                sm.transition("DONE", reason=decision.get("decision"), cycle_id=cycle_id)
            report["decision"] = decision
            report["terminal_status"] = sm.load().status
            report["ok"] = True
            report["operational_success"] = sm.load().status in {"DONE", "IDLE"}
            report["outcome"] = sm.load().status.lower()
            refresh_executive(root)
            report["steps"].append({"step": "refresh-executive", "ok": True})
            _print(report)
            return exit_code_for_status(sm.load().status)

        return _run_cycle_from_decision(
            root=root,
            cfg=cfg,
            sm=sm,
            decision=decision,
            args=args,
            report=report,
            start_phase="PREPARING",
        )
    except Exception as exc:  # noqa: BLE001
        try:
            sm.transition("FAILED", reason=str(exc))
        except Exception as exc2:  # noqa: BLE001
            report["transition_error"] = str(exc2)
        report["error"] = str(exc)
        report["terminal_status"] = "FAILED"
        report["operational_success"] = False
        _print(report)
        return EXIT_FAILED
    finally:
        sm.lock.release()


def cmd_resume(args: argparse.Namespace) -> int:
    """Idempotently continue from mid-cycle phase — not just print resume_target."""
    root = repo_root()
    cfg = load_config(root)
    sm = StateMachine(root)
    try:
        sm.lock.acquire("resume")
    except LockError as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_LOCK

    report: dict[str, Any] = {"steps": [], "ok": False, "mode": "resume"}
    try:
        state = sm.load()
        target = sm.resume_target()
        report["resume_target"] = target
        report["prior_state"] = state.to_dict()

        if state.status == "PAUSED":
            # resume into stored meta phase if present
            meta_phase = (state.meta or {}).get("resume_phase")
            if meta_phase:
                target = meta_phase
            else:
                sm.transition("IDLE", reason="resume from pause")
                _print({**report, "ok": True, "note": "resumed to IDLE from PAUSED"})
                return EXIT_OK

        if target in {"IDLE", "DONE", "WAITING_HUMAN", "BLOCKED", "PAUSED"}:
            _print(
                {
                    **report,
                    "ok": True,
                    "note": f"no active cycle work for target={target}",
                    "status": sm.load().to_dict(),
                }
            )
            return exit_code_for_status(sm.load().status)

        cycle_id = state.cycle_id
        decision = None
        if decision_path(root).is_file():
            decision = json.loads(decision_path(root).read_text(encoding="utf-8"))
        if cycle_id:
            arts = _load_cycle_artifacts(root, str(cycle_id))
            if arts.get("decision"):
                decision = arts["decision"]
        if not decision:
            _print({**report, "ok": False, "error": "no decision to resume"})
            return EXIT_ERROR

        # Preserve session/worktree/decision/attempts via cycle dir artifacts
        report["preserved"] = {
            "cycle_id": cycle_id or decision.get("cycle_id"),
            "decision_id": decision.get("decision_id"),
            "session_hint": f"cto-{cycle_id}",
            "artifacts": list((_load_cycle_artifacts(root, str(cycle_id or decision.get("cycle_id")))).keys()),
        }

        # Map resume target to start_phase
        phase_map = {
            "PREPARING": "PREPARING",
            "EXECUTING": "EXECUTING",
            "VERIFYING": "VERIFYING",
            "REVIEWING": "REVIEWING",
            "REPAIRING": "REPAIRING",
            "DECIDING": "PREPARING",
            "OBSERVING": "PREPARING",
        }
        start = phase_map.get(target, "PREPARING")
        # Ensure state machine is on a valid from-state for re-entry
        if state.status != start and state.status not in {
            "PREPARING",
            "EXECUTING",
            "VERIFYING",
            "REVIEWING",
            "REPAIRING",
        }:
            # force into target via self/allowed
            try:
                if state.status == "FAILED" and start == "REPAIRING":
                    sm.transition("REPAIRING", reason="resume after fail", cycle_id=cycle_id)
                elif state.status in {"IDLE", "DONE"}:
                    pass
            except Exception as exc:  # noqa: BLE001
                report["state_nudge"] = str(exc)

        return _run_cycle_from_decision(
            root=root,
            cfg=cfg,
            sm=sm,
            decision=decision,
            args=args,
            report=report,
            start_phase=start,
        )
    except Exception as exc:  # noqa: BLE001
        report["error"] = str(exc)
        report["operational_success"] = False
        _print(report)
        return EXIT_FAILED
    finally:
        sm.lock.release()


def cmd_pause(_: argparse.Namespace) -> int:
    root = repo_root()
    sm = StateMachine(root)
    try:
        sm.transition("PAUSED", reason="cli pause")
    except Exception as exc:  # noqa: BLE001
        st = sm.load()
        st.status = "PAUSED"
        st.last_error = f"forced pause from {st.status}: {exc}"
        sm.save(st)
    _print({"ok": True, "status": sm.load().to_dict()})
    return EXIT_OK


def cmd_publish(args: argparse.Namespace) -> int:
    """Run publisher only (post-ACCEPT), never via Grok executor."""
    root = repo_root()
    if not decision_path(root).is_file():
        _print({"ok": False, "error": "no decision.json"})
        return EXIT_ERROR
    decision = json.loads(decision_path(root).read_text(encoding="utf-8"))
    cycle_id = decision.get("cycle_id")
    wt = None
    arts = _load_cycle_artifacts(root, str(cycle_id)) if cycle_id else {}
    if (arts.get("execution") or {}).get("worktree"):
        wt = Path(arts["execution"]["worktree"])
    result = publish_after_accept(
        decision=decision,
        worktree=wt,
        root=root,
        dry_run=args.dry_run,
        skip_push=args.skip_push,
    )
    _print(result)
    return EXIT_WAITING_HUMAN if result.get("status") == "WAITING_HUMAN" else (
        EXIT_OK if result.get("ok") else EXIT_FAILED
    )


def cmd_refresh_executive(_: argparse.Namespace) -> int:
    result = refresh_executive(repo_root())
    _print(result)
    return EXIT_OK if result.get("ok") else EXIT_ERROR


def cmd_audit(_: argparse.Namespace) -> int:
    root = repo_root()
    obs = observe(root, write=False)
    issues = audit_issues(root)
    reg = load_registry(root)
    _print(
        {
            "git": obs.get("git"),
            "dod": obs.get("dod"),
            "prs": obs.get("prs"),
            "issues_audit": issues,
            "registry_count": len(reg.get("work_items") or []),
            "work_items_ready": (obs.get("work_items") or {}).get("ready_ids"),
            "ranking_stale": (obs.get("ranking") or {}).get("stale"),
            "divergences": obs.get("divergences"),
            "ledger_tail": read_ledger(root, limit=10),
            "state": status_summary(root).get("state"),
        }
    )
    return EXIT_OK


def cmd_deepseek_smoke(_: argparse.Namespace) -> int:
    if os.getenv("DEEPSEEK_LIVE_TEST") != "1":
        _print(
            {
                "ok": False,
                "error": "Set DEEPSEEK_LIVE_TEST=1 to enable live smoke test",
            }
        )
        return 2
    cfg = load_config()
    client = DeepSeekClient(cfg.deepseek)
    try:
        result = client.smoke()
        _print({"ok": True, "result": result})
        return EXIT_OK
    except Exception as exc:  # noqa: BLE001
        _print({"ok": False, "error": str(exc)})
        return EXIT_ERROR


def cmd_bootstrap(_: argparse.Namespace) -> int:
    """Create registry, observe, plan issues (no apply)."""
    root = repo_root()
    current_dir(root).mkdir(parents=True, exist_ok=True)
    cycles_dir(root).mkdir(parents=True, exist_ok=True)
    obs = observe(root, write=True)
    reg = build_initial_registry(root, observation=obs)
    recon = reconcile_implemented_items(reg)
    apply_readiness_gates(reg)
    path = save_registry(reg, root)
    plan = plan_issues(root)
    _print(
        {
            "ok": True,
            "registry_path": str(path),
            "work_items": len(reg.get("work_items") or []),
            "reconciled": recon,
            "issues_plan": plan,
        }
    )
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m scripts.cto.cli", description="CTO Autopilot")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="Check dependencies and config (no secrets)")
    p_obs = sub.add_parser("observe", help="Collect observation.json")
    p_obs.add_argument("--no-write", action="store_true")
    sub.add_parser("status", help="Show current CTO status")
    sub.add_parser("bootstrap", help="Build work registry + initial plan")
    sub.add_parser("issues-plan", help="Plan issue creates/updates")
    p_sync = sub.add_parser("issues-sync", help="Sync issues dry-run or apply")
    p_sync.add_argument("--apply", action="store_true")
    p_sync.add_argument("--dry-run", action="store_true", help="explicit dry-run (default)")
    sub.add_parser("issues-audit", help="Audit registry vs issues")
    p_rec = sub.add_parser("reconcile-queue", help="Readiness + PR#48 implemented reconcile")
    p_rec.add_argument("--human", action="store_true", help="move implemented to human not review")
    p_rec.add_argument("--apply-issues", action="store_true", help="update issue labels")
    sub.add_parser("rank", help="Show advisory ranker top")
    p_dec = sub.add_parser("decide", help="CTO decide")
    p_dec.add_argument("--dry-run", action="store_true")
    p_dec.add_argument("--refresh", action="store_true")
    sub.add_parser("prepare", help="Prepare worktree + prompt from decision")
    p_run = sub.add_parser("run-once", help="One autonomous cycle")
    p_run.add_argument("--dry-run", action="store_true")
    p_run.add_argument("--mock", action="store_true", help="Mock executor (controlled)")
    p_run.add_argument("--skip-tests", action="store_true")
    p_run.add_argument("--skip-publish", action="store_true")
    p_run.add_argument("--skip-push", action="store_true")
    p_res = sub.add_parser("resume", help="Resume mid-cycle idempotently")
    p_res.add_argument("--dry-run", action="store_true")
    p_res.add_argument("--mock", action="store_true")
    p_res.add_argument("--skip-tests", action="store_true")
    p_res.add_argument("--skip-publish", action="store_true")
    p_res.add_argument("--skip-push", action="store_true")
    sub.add_parser("pause", help="Pause autopilot")
    p_ver = sub.add_parser("verify", help="Run verifier on current decision")
    p_ver.add_argument("--skip-tests", action="store_true")
    p_pub = sub.add_parser("publish", help="Publisher path only (post-ACCEPT)")
    p_pub.add_argument("--dry-run", action="store_true")
    p_pub.add_argument("--skip-push", action="store_true")
    sub.add_parser("refresh-executive", help="Update executive HTML panel")
    sub.add_parser("audit", help="Full local audit snapshot")
    sub.add_parser("deepseek-smoke", help="Live DeepSeek smoke (opt-in)")
    p_c2 = sub.add_parser(
        "cycle2-real",
        help="Second real CTO cycle after rerank (PR #51)",
    )
    p_c2.add_argument("--dry-run", action="store_true")
    p_c2.add_argument("--require-grok", action="store_true")
    p_c2.add_argument("--cycle-id", default=None)
    p_c2.add_argument("--cycle1-selected-id", default="cand-dyn-slice:cb906bb58392")
    p_c1 = sub.add_parser(
        "cycle1-real",
        help="First real CTO cycle: ACCEPT_TOP ranking[0] + AIOX bridge (PR #50)",
    )
    p_c1.add_argument("--dry-run", action="store_true")
    p_c1.add_argument("--require-grok", action="store_true")
    p_c1.add_argument("--cycle-id", default=None)
    p_canary = sub.add_parser(
        "canary-live",
        help="One controlled live canary: only docs/ops/cto-autopilot/canary-proof.md",
    )
    p_canary.add_argument(
        "--skip-push",
        action="store_true",
        help="Execute/verify/review only (no remote push/PR)",
    )
    p_canary.add_argument(
        "--mock",
        action="store_true",
        help="Use mock executor (not valid for merge-gate proof)",
    )
    return p


def build_canary_decision(*, root: Path) -> dict[str, Any]:
    """Fixed, fail-closed decision for the live canary proof."""
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    cycle_id = f"canary-live-{ts}"
    return {
        "schema_version": "1.0",
        "decision_id": f"dec-{cycle_id}",
        "cycle_id": cycle_id,
        "decision": "EXECUTE",
        "objective": (
            f"Update exclusively docs/ops/cto-autopilot/canary-proof.md with UTC "
            f"timestamp {ts}, cycle_id {cycle_id}, and one sentence stating the "
            "controlled live canary cycle executed. Do not touch any other file."
        ),
        "issue_number": None,
        "work_id": "cto-canary-live",
        "candidate_id": None,
        "strategic_reason": "PR #48 merge-gate live canary proof",
        "acceptance_criteria": [
            "only canary-proof.md modified",
            "file contains cycle_id and UTC timestamp",
            "no merge, no main mutation",
        ],
        "required_evidence": ["docs/ops/cto-autopilot/canary-proof.md"],
        "allowed_paths": ["docs/ops/cto-autopilot/canary-proof.md"],
        "forbidden_paths": [
            "DOD.md",
            ".github/**",
            "scripts/**",
            "tests/**",
            "config/**",
            ".env",
            ".env.*",
        ],
        "test_ids": ["cto.canary.proof_grep"],
        "test_commands": [],
        "forbidden_actions": [
            "merge",
            "deploy",
            "git push",
            "issue close",
            "issue label mutation",
            "operate on main",
        ],
        "allowed_claims": [],
        "forbidden_claims": [
            "LOCAL_READY",
            "PRE_VPS_FINAL_READY",
            "VPS_OPERATIONAL",
            "PROJECT_DONE",
            "95% coverage",
            "recall 100%",
        ],
        "max_repair_attempts": 1,
        "estimated_risk": "LOW",
        "confidence": 0.99,
        "human_gate": {"required": False, "reason": None},
        "_meta": {
            "canary": True,
            "branch_name": f"cto/canary-live-{ts}",
            "source": "cli canary-live",
        },
    }


def cmd_canary_live(args: argparse.Namespace) -> int:
    """Controlled live canary: Grok real (unless --mock), publisher draft PR, no merge."""
    root = repo_root()
    cfg = load_config(root)
    sm = StateMachine(root)
    try:
        sm.lock.acquire("canary-live")
    except LockError as exc:
        _print({"ok": False, "error": str(exc)})
        return EXIT_LOCK

    report: dict[str, Any] = {
        "steps": [],
        "ok": False,
        "operational_success": False,
        "mode": "canary-live",
    }
    try:
        # Force live tests (ignore any ambient skip)
        args.skip_tests = False
        args.dry_run = False
        args.skip_publish = False
        if not hasattr(args, "skip_push"):
            args.skip_push = False

        cur = sm.load()
        if cur.status in {"DONE", "ACCEPTED", "FAILED", "BLOCKED", "WAITING_HUMAN"}:
            try:
                sm.transition("IDLE", reason="canary-live re-entry")
            except Exception:  # noqa: BLE001
                st = sm.load()
                st.status = "IDLE"
                sm.save(st)

        decision = build_canary_decision(root=root)
        branch_name = (decision.get("_meta") or {}).get("branch_name")
        save_decision(decision, root)
        report["steps"].append({"step": "canary-decision", "cycle_id": decision["cycle_id"]})
        report["canary"] = {
            "cycle_id": decision["cycle_id"],
            "decision_id": decision["decision_id"],
            "branch": branch_name,
            "allowed_paths": decision["allowed_paths"],
        }

        # prepare worktree with explicit canary branch name
        from scripts.cto.grok_executor import prepare_worktree

        prep = prepare_worktree(
            cycle_id=str(decision["cycle_id"]),
            branch_name=branch_name,
            root=root,
        )
        report["steps"].append({"step": "prepare-worktree", **prep})

        # Inject branch into decision meta for publisher
        decision["_meta"] = {**(decision.get("_meta") or {}), "worktree": prep["worktree"]}
        save_decision(decision, root)

        # Monkey-patch execute path: use worktree_override + branch
        # by calling shared cycle with decision already set
        # Override grok_execute via wrapper in this function
        import scripts.cto.cli as cli_mod
        from scripts.cto import grok_executor as ge

        original = cli_mod.grok_execute

        def _canary_execute(decision_arg, **kwargs):  # type: ignore[no-untyped-def]
            kwargs.setdefault("worktree_override", Path(prep["worktree"]))
            kwargs["branch_name"] = branch_name
            return ge.execute(decision_arg, **kwargs)

        cli_mod.grok_execute = _canary_execute  # type: ignore[assignment]
        try:
            if args.mock:
                report["error"] = "canary-live refuses --mock (not valid merge-gate proof)"
                report["ok"] = False
                _print(report)
                return EXIT_FAILED
            code = _run_cycle_from_decision(
                root=root,
                cfg=cfg,
                sm=sm,
                decision=decision,
                args=args,
                report=report,
                start_phase="PREPARING",
            )
            # Sealed package integrity — fail closed on post-hoc / wrong auth
            from scripts.cto.canary_integrity import validate_sealed_canary_package

            head_sha = (
                __import__("subprocess")
                .check_output(["git", "rev-parse", "HEAD"], cwd=str(root), text=True)
                .strip()
            )
            integrity = validate_sealed_canary_package(
                str(decision["cycle_id"]),
                root=root,
                expected_head=head_sha,
            )
            report["integrity"] = {
                "ok": integrity.get("ok"),
                "errors": integrity.get("errors"),
                "decision_sha256": integrity.get("decision_sha256"),
                "checks_failed": [
                    c["name"] for c in (integrity.get("checks") or []) if not c.get("pass")
                ],
            }
            cdir = cycles_dir(root) / str(decision["cycle_id"])
            (cdir / "integrity.json").write_text(
                json.dumps(integrity, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            if not integrity.get("ok"):
                report["ok"] = False
                report["operational_success"] = False
                report["error"] = "canary package integrity failed"
                report["outcome"] = "integrity_failed"
                _print(report)
                return EXIT_FAILED
            # Re-print with integrity (cycle already printed once inside _run_cycle)
            _print({"integrity_ok": True, "cycle_id": decision["cycle_id"], **report.get("integrity", {})})
            return code
        finally:
            cli_mod.grok_execute = original  # type: ignore[assignment]
    except Exception as exc:  # noqa: BLE001
        try:
            sm.transition("FAILED", reason=str(exc))
        except Exception as exc2:  # noqa: BLE001
            report["transition_error"] = str(exc2)
        report["error"] = str(exc)
        report["terminal_status"] = "FAILED"
        report["operational_success"] = False
        _print(report)
        return EXIT_FAILED
    finally:
        sm.lock.release()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "doctor": cmd_doctor,
        "observe": cmd_observe,
        "status": cmd_status,
        "bootstrap": cmd_bootstrap,
        "issues-plan": cmd_issues_plan,
        "issues-sync": cmd_issues_sync,
        "issues-audit": cmd_issues_audit,
        "reconcile-queue": cmd_reconcile_queue,
        "rank": cmd_rank,
        "decide": cmd_decide,
        "prepare": cmd_prepare,
        "run-once": cmd_run_once,
        "resume": cmd_resume,
        "pause": cmd_pause,
        "verify": cmd_verify,
        "publish": cmd_publish,
        "refresh-executive": cmd_refresh_executive,
        "audit": cmd_audit,
        "deepseek-smoke": cmd_deepseek_smoke,
        "cycle1-real": cmd_cycle1_real,
        "cycle2-real": cmd_cycle2_real,
        "canary-live": cmd_canary_live,
    }
    return handlers[args.cmd](args)


# --- cycle-1 real ROI binding (PR #50) ---
def cmd_cycle1_real(args: argparse.Namespace) -> int:
    from scripts.cto.cycle1_roi_integration import run_cycle1_real

    result = run_cycle1_real(
        dry_run=bool(getattr(args, "dry_run", False)),
        require_grok=bool(getattr(args, "require_grok", False)),
        cycle_id=getattr(args, "cycle_id", None),
    )
    _print(result)
    return EXIT_OK if result.get("ok") else EXIT_FAILED



def cmd_cycle2_real(args: argparse.Namespace) -> int:
    from scripts.cto.cycle2_rerank_integration import run_cycle2_real
    result = run_cycle2_real(
        dry_run=bool(getattr(args, "dry_run", False)),
        require_grok=bool(getattr(args, "require_grok", False)),
        cycle_id=getattr(args, "cycle_id", None),
        cycle1_selected_id=str(getattr(args, "cycle1_selected_id", "cand-dyn-slice:cb906bb58392")),
    )
    _print(result)
    return EXIT_OK if result.get("ok") else EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
