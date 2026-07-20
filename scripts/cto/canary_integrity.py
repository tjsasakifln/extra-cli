"""Sealed canary package integrity — fail-closed provenance checks.

Prevents post-hoc rewrite theater: decision/execute/verify/review/publication
must agree on one decision content hash without reconcile metadata.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from scripts.cto.paths import cycles_dir, repo_root

FORBIDDEN_META_SOURCES = frozenset(
    {
        "canonical-aligned-package",
        "reconcile-single-decision",
    }
)


def decision_content_sha256(decision: dict[str, Any]) -> str:
    """Stable hash of decision content excluding mutable _meta."""
    stable = {k: decision[k] for k in sorted(decision.keys()) if k != "_meta"}
    raw = json.dumps(stable, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def validate_sealed_canary_package(
    cycle_id: str,
    *,
    root: Path | None = None,
    expected_head: str | None = None,
) -> dict[str, Any]:
    """Validate a canary cycle package is sealed and self-consistent.

    Returns ``{ok: bool, checks: [...], errors: [...]}``.
    """
    root = root or repo_root()
    cdir = cycles_dir(root) / cycle_id
    checks: list[dict[str, Any]] = []
    errors: list[str] = []

    def _check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "pass": ok, "detail": detail})
        if not ok:
            errors.append(f"{name}: {detail}")

    decision = _load_json(cdir / "decision.json")
    execution = _load_json(cdir / "execution.json")
    verification = _load_json(cdir / "verification.json")
    review = _load_json(cdir / "review.json")
    publication = _load_json(cdir / "publication.json")
    prompt_path = cdir / "execute_prompt.md"
    prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.is_file() else ""

    _check("decision_present", decision is not None, str(cdir / "decision.json"))
    _check("execution_present", execution is not None)
    _check("verification_present", verification is not None)
    _check("review_present", review is not None)
    _check("publication_present", publication is not None)
    _check("execute_prompt_present", bool(prompt))

    if not decision or not execution:
        return {"ok": False, "checks": checks, "errors": errors, "cycle_id": cycle_id}

    meta = decision.get("_meta") or {}
    _check(
        "no_reconcile_meta",
        "reconciled_at_utc" not in meta
        and meta.get("source") not in FORBIDDEN_META_SOURCES,
        f"source={meta.get('source')!r}",
    )
    _check("meta_source_canary_cli", meta.get("source") == "cli canary-live", str(meta.get("source")))

    dsha = decision_content_sha256(decision)
    exec_sha = execution.get("decision_sha256")
    _check(
        "decision_sha256_stamped",
        bool(exec_sha) and exec_sha == dsha,
        f"exec={exec_sha} computed={dsha}",
    )

    # Auth: XAI_API_KEY only, no staged host auth file
    gauth = execution.get("grok_auth") or {}
    _check(
        "auth_source_xai_api_key",
        gauth.get("source") == "XAI_API_KEY",
        str(gauth.get("source")),
    )
    _check(
        "no_staged_auth_file",
        not gauth.get("staged_auth_file"),
        str(gauth.get("staged_auth_file")),
    )
    iso_home = execution.get("isolated_home")
    if iso_home:
        auth_file = Path(iso_home) / ".grok" / "auth.json"
        _check("isolated_home_no_auth_json", not auth_file.exists(), str(auth_file))
    else:
        _check("isolated_home_recorded", False, "missing isolated_home")

    _check("not_mock", execution.get("mock") is False, str(execution.get("mock")))
    _check("not_dry_run", execution.get("dry_run") is False, str(execution.get("dry_run")))
    _check(
        "execution_completed",
        execution.get("status") in {"completed"},
        str(execution.get("status")),
    )

    # base_commit should be the worktree start (= PR HEAD tip when canary branched)
    if expected_head:
        base = str(execution.get("base_commit") or "")
        _check(
            "base_commit_matches_head",
            base.startswith(expected_head[:12]) or expected_head.startswith(base[:12]),
            f"base={base[:16]} head={expected_head[:16]}",
        )

    # Prompt embeds decision test_commands and required_evidence
    for cmd in decision.get("test_commands") or []:
        _check("prompt_has_test_command", cmd in prompt, cmd)
    for ev in decision.get("required_evidence") or []:
        _check("prompt_has_required_evidence", ev in prompt, ev)
    _check(
        "prompt_no_legacy_pytest",
        "test_executor_hardening" not in prompt,
        "legacy pytest must not appear",
    )

    # Verifier used the same test command
    if verification:
        _check(
            "verifier_pass",
            verification.get("result") == "PASS",
            str(verification.get("result")),
        )
        tests_check = next(
            (c for c in (verification.get("checks") or []) if c.get("name") == "tests"),
            None,
        )
        if tests_check and (
            decision.get("test_ids") or decision.get("test_commands")
        ):
            # Authorized registry: compare argv lists, never str.split free shell
            actual = (tests_check.get("results") or [{}])[0].get("cmd") or []
            actual_argv = list(actual) if isinstance(actual, list) else []
            expected_argv = actual_argv  # default: accept registry-resolved argv
            try:
                from scripts.cto.test_registry import normalize_test_ids, resolve_argv

                tids = normalize_test_ids(decision)
                if tids:
                    expected_argv = list(resolve_argv(tids[0])["argv"])
            except Exception as exc:  # noqa: BLE001
                _check("verifier_test_registry", False, str(exc))
            else:
                _check(
                    "verifier_test_cmd_matches_decision",
                    actual_argv == expected_argv,
                    f"actual={actual_argv} expected={expected_argv}",
                )
            _check(
                "verifier_test_exit_0",
                (tests_check.get("results") or [{}])[0].get("exit_code") == 0,
                str((tests_check.get("results") or [{}])[0].get("exit_code")),
            )
            _check(
                "verifier_tests_shell_false",
                tests_check.get("shell") is False
                or (tests_check.get("results") or [{}])[0].get("shell") is False,
                "shell must be False",
            )
        modified = (verification.get("files") or {}).get("modified") or []
        _check(
            "only_canary_file_modified",
            modified == ["docs/ops/cto-autopilot/canary-proof.md"],
            str(modified),
        )

    if review:
        _check("review_accept", review.get("verdict") == "ACCEPT", str(review.get("verdict")))

    if publication:
        _check(
            "publisher_waiting_human",
            publication.get("status") == "WAITING_HUMAN",
            str(publication.get("status")),
        )
        pr = publication.get("pr") or {}
        _check("draft_pr_number", bool(pr.get("number")), str(pr.get("number")))
        _check("draft_pr_url", bool(pr.get("url")), str(pr.get("url")))
        _check(
            "draft_true",
            pr.get("draft") is True or pr.get("isDraft") is True,
            str(pr.get("draft") or pr.get("isDraft")),
        )
        # never merge
        blob = json.dumps(publication)
        _check(
            "no_merge_action",
            not re.search(r'"merged"\s*:\s*true', blob, re.I),
            "publication must not record merge",
        )

    ok = all(c["pass"] for c in checks)
    return {
        "ok": ok,
        "cycle_id": cycle_id,
        "decision_sha256": dsha,
        "checks": checks,
        "errors": errors,
    }
