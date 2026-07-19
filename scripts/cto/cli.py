#!/usr/bin/env python3
"""CTO Autopilot CLI.

Commands:
  doctor, observe, status, issues-plan, issues-sync, issues-audit,
  rank, decide, prepare, run-once, resume, pause, verify,
  refresh-executive, audit, deepseek-smoke
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
from datetime import datetime, timezone
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
    work_registry_path,
)
from scripts.cto.redaction import redact_obj  # noqa: E402
from scripts.cto.state_machine import LockError, StateMachine  # noqa: E402
from scripts.cto.verifier import verify  # noqa: E402
from scripts.cto.work_registry import (  # noqa: E402
    build_initial_registry,
    load_registry,
    save_registry,
)


def _print(data: Any) -> None:
    print(json.dumps(redact_obj(data), indent=2, ensure_ascii=False, default=str))


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    # Never print key
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

    ok_all = all(c["ok"] for c in checks if c["name"] != "grok_cli")  # grok optional for dry-run
    # soft: grok optional
    _print({"ok": ok_all, "checks": checks})
    return 0 if ok_all else 1


def cmd_observe(args: argparse.Namespace) -> int:
    root = repo_root()
    sm = StateMachine(root)
    try:
        sm.lock.acquire("observe")
    except LockError as exc:
        _print({"ok": False, "error": str(exc)})
        return 2
    try:
        sm.transition("OBSERVING", reason="cli observe")
        obs = observe(root, write=not args.no_write)
        sm.transition("IDLE", reason="observe complete", cycle_id=(obs.get("roi_cycle") or {}).get("cycle_id"))
        append_ledger("observe", {"keys": list(obs.keys())}, root=root)
        _print({"ok": True, "path": str(observation_path(root)), "summary": {
            "branch": (obs.get("git") or {}).get("branch"),
            "commit": (obs.get("git") or {}).get("commit"),
            "dod": obs.get("dod"),
            "open_issues": (obs.get("issues") or {}).get("open_count"),
            "open_prs": len(obs.get("prs") or []),
        }})
        return 0
    finally:
        sm.lock.release()


def cmd_status(_: argparse.Namespace) -> int:
    _print(status_summary(repo_root()))
    return 0


def cmd_issues_plan(_: argparse.Namespace) -> int:
    root = repo_root()
    # Ensure registry exists
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
    return 0


def cmd_issues_sync(args: argparse.Namespace) -> int:
    root = repo_root()
    reg = load_registry(root)
    if not reg.get("work_items"):
        obs = observe(root, write=True)
        reg = build_initial_registry(root, observation=obs)
        save_registry(reg, root)
    result = sync_issues(root, apply=args.apply)
    _print(result)
    return 0


def cmd_issues_audit(_: argparse.Namespace) -> int:
    _print(audit_issues(repo_root()))
    return 0


def cmd_rank(_: argparse.Namespace) -> int:
    """Advisory ranker bridge — read-only."""
    root = repo_root()
    obs = observe(root, write=False)
    _print({"ranking": obs.get("ranking"), "note": "advisory only — CTO decides"})
    return 0


def cmd_decide(args: argparse.Namespace) -> int:
    root = repo_root()
    cfg = load_config(root)
    sm = StateMachine(root)
    try:
        sm.lock.acquire("decide")
    except LockError as exc:
        _print({"ok": False, "error": str(exc)})
        return 2
    try:
        ok_b, reason = check_budget(cfg.budgets, root)
        if not ok_b:
            sm.transition("PAUSED", reason=f"budget: {reason}")
            _print({"ok": False, "error": reason, "status": "PAUSED"})
            return 3
        if not observation_path(root).is_file() or args.refresh:
            observe(root, write=True)
        obs = json.loads(observation_path(root).read_text(encoding="utf-8"))
        sm.transition("DECIDING", reason="cli decide")
        decision = decide_from_observation(
            obs,
            config=cfg,
            dry_run=args.dry_run,
        )
        save_decision(decision, root)
        usage = (decision.get("_meta") or {}).get("usage") or {}
        if usage:
            record_usage(
                api_calls=1,
                tokens=int(usage.get("total_tokens") or 0),
                root=root,
            )
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
        append_ledger("decide", {"decision": action, "decision_id": decision.get("decision_id")}, root=root, cycle_id=cycle_id)
        _print({"ok": True, "decision": decision, "path": str(decision_path(root))})
        return 0
    finally:
        sm.lock.release()


def cmd_prepare(args: argparse.Namespace) -> int:
    root = repo_root()
    sm = StateMachine(root)
    if not decision_path(root).is_file():
        _print({"ok": False, "error": "no decision.json — run decide first"})
        return 1
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
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    root = repo_root()
    if not decision_path(root).is_file():
        _print({"ok": False, "error": "no decision.json"})
        return 1
    decision = json.loads(decision_path(root).read_text(encoding="utf-8"))
    sm = StateMachine(root)
    sm.transition("VERIFYING", reason="cli verify", cycle_id=decision.get("cycle_id"))
    result = verify(
        decision=decision,
        root=root,
        skip_tests=args.skip_tests,
    )
    sm.transition("IDLE", reason=f"verify {result.get('result')}", cycle_id=decision.get("cycle_id"))
    _print(result)
    return 0 if result.get("result") == "PASS" else 1


def cmd_run_once(args: argparse.Namespace) -> int:
    """Full safe cycle: observe → decide → prepare → execute → verify → review."""
    root = repo_root()
    cfg = load_config(root)
    sm = StateMachine(root)
    try:
        sm.lock.acquire("run-once")
    except LockError as exc:
        _print({"ok": False, "error": str(exc)})
        return 2

    report: dict[str, Any] = {"steps": [], "ok": False}
    try:
        ok_b, reason = check_budget(cfg.budgets, root)
        if not ok_b:
            sm.transition("PAUSED", reason=f"budget: {reason}")
            report["error"] = reason
            _print(report)
            return 3

        # Normalize terminal states so a new cycle can start
        cur = sm.load()
        if cur.status in {"DONE", "ACCEPTED", "FAILED", "BLOCKED"}:
            try:
                sm.transition("IDLE", reason="run-once re-entry")
            except Exception:  # noqa: BLE001
                st = sm.load()
                st.status = "IDLE"
                sm.save(st)

        sm.transition("OBSERVING", reason="run-once")
        obs = observe(root, write=True)
        report["steps"].append({"step": "observe", "ok": True})

        sm.transition("DECIDING", reason="run-once")
        decision = decide_from_observation(obs, config=cfg, dry_run=args.dry_run)
        save_decision(decision, root)
        usage = (decision.get("_meta") or {}).get("usage") or {}
        if usage:
            record_usage(api_calls=1, tokens=int(usage.get("total_tokens") or 0), root=root)
        report["steps"].append({"step": "decide", "decision": decision.get("decision")})
        cycle_id = decision.get("cycle_id")

        if decision.get("decision") in {"BLOCK", "ESCALATE", "NOOP", "ACCEPT"}:
            if decision.get("decision") == "ESCALATE" or (decision.get("human_gate") or {}).get("required"):
                sm.transition("WAITING_HUMAN", reason=decision.get("strategic_reason") or "", cycle_id=cycle_id)
            elif decision.get("decision") == "BLOCK":
                sm.transition("BLOCKED", reason=decision.get("strategic_reason") or "", cycle_id=cycle_id)
            else:
                sm.transition("DONE", reason=decision.get("decision"), cycle_id=cycle_id)
            report["decision"] = decision
            report["ok"] = True
            refresh_executive(root)
            report["steps"].append({"step": "refresh-executive", "ok": True})
            _print(report)
            return 0

        sm.transition("PREPARING", reason="run-once", cycle_id=cycle_id)
        # execute
        sm.transition("EXECUTING", reason="run-once", cycle_id=cycle_id)
        execution = grok_execute(
            decision,
            root=root,
            dry_run=args.dry_run,
            mock=args.mock,
        )
        report["steps"].append({"step": "execute", "status": execution.get("status")})

        sm.transition("VERIFYING", reason="run-once", cycle_id=cycle_id)
        verification = verify(
            decision=decision,
            worktree=Path(execution["worktree"]) if execution.get("worktree") else None,
            root=root,
            skip_tests=args.skip_tests or args.dry_run,
        )
        report["steps"].append({"step": "verify", "result": verification.get("result")})

        sm.transition("REVIEWING", reason="run-once", cycle_id=cycle_id)
        review = review_execution(
            decision=decision,
            verification=verification,
            execution=execution,
            config=cfg,
            dry_run=args.dry_run,
        )
        report["steps"].append({"step": "review", "verdict": review.get("verdict")})
        (cycles_dir(root) / str(cycle_id)).mkdir(parents=True, exist_ok=True)
        (cycles_dir(root) / str(cycle_id) / "review.json").write_text(
            json.dumps(review, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        repair_attempt = 0
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
            )
            review = review_execution(
                decision=decision,
                verification=verification,
                execution=execution,
                config=cfg,
                dry_run=False,
            )
            report["steps"].append(
                {
                    "step": f"repair_{repair_attempt}",
                    "verify": verification.get("result"),
                    "review": review.get("verdict"),
                }
            )

        if review.get("verdict") == "ACCEPT":
            sm.transition("ACCEPTED", reason="review ACCEPT", cycle_id=cycle_id)
            sm.transition("DONE", reason="cycle complete", cycle_id=cycle_id)
        elif review.get("verdict") == "ESCALATE":
            sm.transition("WAITING_HUMAN", reason=review.get("summary") or "", cycle_id=cycle_id)
        elif review.get("verdict") == "BLOCK":
            sm.transition("BLOCKED", reason=review.get("summary") or "", cycle_id=cycle_id)
        else:
            sm.transition(
                "WAITING_HUMAN" if repair_attempt >= max_repairs else "FAILED",
                reason=review.get("summary") or review.get("verdict") or "unresolved",
                cycle_id=cycle_id,
            )

        refresh_executive(root)
        report["steps"].append({"step": "refresh-executive", "ok": True})
        record_usage(cycles=1, root=root)
        report["ok"] = True
        report["decision"] = {
            "decision": decision.get("decision"),
            "decision_id": decision.get("decision_id"),
            "work_id": decision.get("work_id"),
        }
        report["review"] = review
        report["verification"] = {"result": verification.get("result")}
        append_ledger("run_once", {"ok": True, "cycle_id": cycle_id}, root=root, cycle_id=cycle_id)
        _print(report)
        return 0
    except Exception as exc:  # noqa: BLE001
        try:
            sm.transition("FAILED", reason=str(exc))
        except Exception:  # noqa: BLE001
            pass
        report["error"] = str(exc)
        _print(report)
        return 1
    finally:
        sm.lock.release()


def cmd_resume(_: argparse.Namespace) -> int:
    root = repo_root()
    sm = StateMachine(root)
    target = sm.resume_target()
    state = sm.load()
    if state.status == "PAUSED":
        sm.transition("IDLE", reason="resume from pause")
    _print({"status": sm.load().to_dict(), "resume_target": target})
    return 0


def cmd_pause(_: argparse.Namespace) -> int:
    root = repo_root()
    sm = StateMachine(root)
    try:
        sm.transition("PAUSED", reason="cli pause")
    except Exception as exc:  # noqa: BLE001
        # force from any via IDLE first if needed
        st = sm.load()
        st.status = "PAUSED"
        st.last_error = f"forced pause from {st.status}: {exc}"
        sm.save(st)
    _print({"ok": True, "status": sm.load().to_dict()})
    return 0


def cmd_refresh_executive(_: argparse.Namespace) -> int:
    result = refresh_executive(repo_root())
    _print(result)
    return 0 if result.get("ok") else 1


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
            "ledger_tail": read_ledger(root, limit=10),
            "state": status_summary(root).get("state"),
        }
    )
    return 0


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
        return 0
    except Exception as exc:  # noqa: BLE001
        _print({"ok": False, "error": str(exc)})
        return 1


def cmd_bootstrap(_: argparse.Namespace) -> int:
    """Create registry, observe, plan issues (no apply)."""
    root = repo_root()
    current_dir(root).mkdir(parents=True, exist_ok=True)
    cycles_dir(root).mkdir(parents=True, exist_ok=True)
    obs = observe(root, write=True)
    reg = build_initial_registry(root, observation=obs)
    path = save_registry(reg, root)
    plan = plan_issues(root)
    _print(
        {
            "ok": True,
            "registry_path": str(path),
            "work_items": len(reg.get("work_items") or []),
            "issues_plan": plan,
        }
    )
    return 0


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
    sub.add_parser("rank", help="Show advisory ranker top")
    p_dec = sub.add_parser("decide", help="CTO decide")
    p_dec.add_argument("--dry-run", action="store_true")
    p_dec.add_argument("--refresh", action="store_true")
    sub.add_parser("prepare", help="Prepare worktree + prompt from decision")
    p_run = sub.add_parser("run-once", help="One autonomous cycle")
    p_run.add_argument("--dry-run", action="store_true")
    p_run.add_argument("--mock", action="store_true", help="Mock executor (controlled)")
    p_run.add_argument("--skip-tests", action="store_true")
    sub.add_parser("resume", help="Resume after pause/crash")
    sub.add_parser("pause", help="Pause autopilot")
    p_ver = sub.add_parser("verify", help="Run verifier on current decision")
    p_ver.add_argument("--skip-tests", action="store_true")
    sub.add_parser("refresh-executive", help="Update executive HTML panel")
    sub.add_parser("audit", help="Full local audit snapshot")
    sub.add_parser("deepseek-smoke", help="Live DeepSeek smoke (opt-in)")
    return p


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
        "rank": cmd_rank,
        "decide": cmd_decide,
        "prepare": cmd_prepare,
        "run-once": cmd_run_once,
        "resume": cmd_resume,
        "pause": cmd_pause,
        "verify": cmd_verify,
        "refresh-executive": cmd_refresh_executive,
        "audit": cmd_audit,
        "deepseek-smoke": cmd_deepseek_smoke,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
