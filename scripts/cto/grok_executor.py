"""Grok Build executor — headless, sandboxed, worktree-bound.

Security model (merge-gate):
- Child env is built by allowlist (never os.environ copy + denylist).
- HOME/TMPDIR are temporary isolated directories (real home not exposed).
- always_approve defaults to False; opt-in only after functional containment.
- Publisher owns push/PR; executor never receives GH/DeepSeek credentials.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.cto.canary_integrity import decision_content_sha256
from scripts.cto.config import load_config
from scripts.cto.paths import cto_dir, cycles_dir, repo_root
from scripts.cto.redaction import redact_obj, redact_text, safe_exception_message

# Minimal environment allowlist for the Grok child process.
# Anything not listed is never forwarded (including arbitrary *_TOKEN secrets).
ENV_ALLOWLIST = frozenset(
    {
        "PATH",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LANGUAGE",
        "TERM",
        "COLORTERM",
        "TMPDIR",
        "TEMP",
        "TMP",
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "PYTHONPATH",
        "VIRTUAL_ENV",
        "PYTHONHOME",
        "PYTHONNOUSERSITE",
        # Non-secret Git identity for local commits inside the worktree
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
        # Grok CLI auth only (NOT DeepSeek / GH / cloud publish credentials)
        "XAI_API_KEY",
    }
)

# Kept for documentation / test compatibility: names that must never appear.
# Construction uses allowlist; this set is not the primary filter.
STRIP_ENV_KEYS = frozenset(
    {
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "GITHUB_PAT",
        "GH_ENTERPRISE_TOKEN",
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "OPENAI_API_BASE",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GEMINI_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "AZURE_CLIENT_SECRET",
        "AZURE_CLIENT_ID",
        "NETLIFY_AUTH_TOKEN",
        "RAILWAY_TOKEN",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SESSION_TOKEN",
        "DIGITALOCEAN_TOKEN",
        "HEROKU_API_KEY",
        "NPM_TOKEN",
        "PYPI_TOKEN",
        "STRIPE_SECRET_KEY",
        "STRIPE_API_KEY",
        "DATABASE_URL",
    }
)

DENY_RULES = [
    "Bash(git push*)",
    "Bash(git merge*)",
    "Bash(git rebase*)",
    "Bash(git reset --hard*)",
    "Bash(gh pr merge*)",
    "Bash(gh api*)",
    "Bash(curl *)",
    "Bash(wget *)",
    "Bash(python *push*)",
    "Bash(python3 *push*)",
    "Bash(rm -rf*)",
    "Read(.env)",
    "Read(~/.ssh/**)",
]

# Patterns that would circumvent git push deny via alternate tools
CIRCUMVENTION_PATTERNS = [
    re.compile(r"\bgh\s+api\b", re.I),
    re.compile(r"\bcurl\b.*github\.com", re.I),
    re.compile(r"\bwget\b.*github\.com", re.I),
    re.compile(r"\bgit\s+push\b", re.I),
    re.compile(r"\bgh\s+pr\s+merge\b", re.I),
    re.compile(r"urllib\.request", re.I),
    re.compile(r"requests\.(post|put|patch)", re.I),
]

# Opt-in values for CTO_GROK_ALWAYS_APPROVE
_TRUEISH = frozenset({"1", "true", "yes", "on"})


class ExecutorError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def render_prompt(template_name: str, mapping: dict[str, Any], root: Path | None = None) -> str:
    path = cto_dir(root) / "prompts" / template_name
    text = path.read_text(encoding="utf-8")
    for key, value in mapping.items():
        if isinstance(value, list):
            rendered = "\n".join(f"- {v}" for v in value) if value else "- (none)"
        else:
            rendered = str(value)
        text = text.replace("{{" + key + "}}", rendered)
    return text


def _assert_not_main(worktree: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(worktree),
        capture_output=True,
        text=True,
        check=False,
    )
    branch = (proc.stdout or "").strip()
    if branch in {"main", "master"}:
        raise ExecutorError("refusing to execute on main/master")
    return branch


def prepare_worktree(
    *,
    cycle_id: str,
    branch_name: str | None = None,
    root: Path | None = None,
    base: str = "HEAD",
) -> dict[str, Any]:
    """Create isolated worktree for a cycle."""
    root = root or repo_root()
    branch = branch_name or f"cto/{cycle_id}"
    wt_parent = root.parent / f"{root.name}-cto-cycles"
    wt_parent.mkdir(parents=True, exist_ok=True)
    wt_path = wt_parent / cycle_id
    if wt_path.exists():
        base_sha = ""
        rev = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(wt_path),
            capture_output=True,
            text=True,
            check=False,
        )
        if rev.returncode == 0:
            base_sha = (rev.stdout or "").strip()
        return {
            "worktree": str(wt_path),
            "branch": branch,
            "created": False,
            "exists": True,
            "base_commit": base_sha,
        }
    subprocess.run(
        ["git", "worktree", "add", "-b", branch, str(wt_path), base],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    if not wt_path.exists():
        subprocess.run(
            ["git", "worktree", "add", str(wt_path), branch],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
    if not wt_path.exists():
        raise ExecutorError(f"failed to create worktree at {wt_path}")
    base_sha = ""
    rev = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(wt_path),
        capture_output=True,
        text=True,
        check=False,
    )
    if rev.returncode == 0:
        base_sha = (rev.stdout or "").strip()
    return {
        "worktree": str(wt_path),
        "branch": branch,
        "created": True,
        "exists": True,
        "base_commit": base_sha,
    }


def managed_worktree_parent(root: Path | None = None) -> Path:
    root = root or repo_root()
    return (root.parent / f"{root.name}-cto-cycles").resolve()


def is_under_managed_worktrees(worktree: Path, root: Path | None = None) -> bool:
    parent = managed_worktree_parent(root)
    try:
        worktree.resolve().relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_grok_auth() -> dict[str, Any]:
    """Grok auth for isolated HOME — allowlist secret only, never host file copy.

    Fail-closed: require ``XAI_API_KEY`` in the process environment (forwarded
    via ENV_ALLOWLIST). Do **not** copy ``~/.grok/auth.json`` or any other
    real-HOME credential file into the temporary HOME.
    """
    present = bool(str(os.environ.get("XAI_API_KEY") or "").strip())
    if present:
        return {
            "xai_api_key_present": True,
            "staged_auth_file": False,
            "source": "XAI_API_KEY",
            "ok": True,
        }
    return {
        "xai_api_key_present": False,
        "staged_auth_file": False,
        "source": None,
        "ok": False,
        "error": "XAI_API_KEY required for live Grok under isolated HOME (no host auth.json copy)",
    }


def create_isolated_runtime_dirs(
    *,
    cycle_id: str,
    root: Path | None = None,
    retain: bool = True,
) -> dict[str, Any]:
    """Create temporary HOME/TMPDIR for the Grok child (no real home file copy)."""
    root = root or repo_root()
    base = managed_worktree_parent(root) / "_runtime" / cycle_id
    home = base / "home"
    tmp = base / "tmp"
    home.mkdir(parents=True, exist_ok=True)
    tmp.mkdir(parents=True, exist_ok=True)
    # Marker only — never secrets, never host credential files
    (home / "README_ISOLATED.txt").write_text(
        "CTO Autopilot isolated HOME. No host credential files are copied here.\n"
        f"cycle_id={cycle_id}\ncreated_utc={_utc_now()}\n"
        "Live Grok requires XAI_API_KEY in the parent process environment.\n",
        encoding="utf-8",
    )
    auth_report = resolve_grok_auth()
    return {
        "base": base,
        "home": home,
        "tmpdir": tmp,
        "retain": retain,
        "auth": auth_report,
    }


def build_minimal_child_env(
    *,
    home: Path | str,
    tmpdir: Path | str,
    source: dict[str, str] | None = None,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """Construct child env from explicit allowlist only.

    Never copies full os.environ then strips. Unknown keys (MY_TOKEN,
    CUSTOM_SECRET, DATABASE_URL, …) are absent by construction.
    """
    src = dict(source) if source is not None else dict(os.environ)
    env: dict[str, str] = {}
    for key in ENV_ALLOWLIST:
        if key in {"HOME", "TMPDIR", "TEMP", "TMP"}:
            continue
        val = src.get(key)
        if val is not None and str(val) != "":
            env[key] = str(val)
    home_s = str(home)
    tmp_s = str(tmpdir)
    env["HOME"] = home_s
    env["TMPDIR"] = tmp_s
    env["TEMP"] = tmp_s
    env["TMP"] = tmp_s
    # Non-secret Git identity defaults (local commits only)
    env.setdefault("GIT_AUTHOR_NAME", src.get("GIT_AUTHOR_NAME") or "CTO Autopilot")
    env.setdefault(
        "GIT_AUTHOR_EMAIL", src.get("GIT_AUTHOR_EMAIL") or "cto-autopilot@users.noreply.local"
    )
    env.setdefault("GIT_COMMITTER_NAME", env["GIT_AUTHOR_NAME"])
    env.setdefault("GIT_COMMITTER_EMAIL", env["GIT_AUTHOR_EMAIL"])
    if extra:
        for k, v in extra.items():
            if k in ENV_ALLOWLIST:
                env[k] = str(v)
    return env


def strip_child_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """Backward-compatible name: build minimal allowlisted env with temp HOME/TMP.

    Prefer ``build_minimal_child_env`` for new call sites.
    """
    # Durable placeholder paths for unit tests (not used for real execution).
    # Real execute() uses create_isolated_runtime_dirs under managed parent.
    placeholder_home = "cto-isolated-home-placeholder"
    placeholder_tmp = "cto-isolated-tmp-placeholder"
    return build_minimal_child_env(
        home=placeholder_home,
        tmpdir=placeholder_tmp,
        source=env,
    )


def always_approve_opt_in(env: dict[str, str] | None = None) -> bool:
    """True only when CTO_GROK_ALWAYS_APPROVE is explicitly truthy."""
    src = env if env is not None else os.environ
    raw = str(src.get("CTO_GROK_ALWAYS_APPROVE") or "").strip().lower()
    return raw in _TRUEISH


def preflight_deny_flags(grok_bin: str | None = None) -> dict[str, Any]:
    """Parse grok --help for --deny / --sandbox / --always-approve presence.

    Textual help is necessary but NOT sufficient for always_approve.
    """
    binary = grok_bin or shutil.which("grok")
    if not binary:
        return {
            "ok": False,
            "deny_supported": False,
            "sandbox_supported": False,
            "always_approve_supported": False,
            "reason": "grok binary not found",
            "proof": None,
        }
    try:
        proc = subprocess.run(
            [binary, "--help"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        help_text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "deny_supported": False,
            "sandbox_supported": False,
            "always_approve_supported": False,
            "reason": f"help failed: {exc}",
            "proof": None,
        }
    deny_ok = bool(re.search(r"--deny\b", help_text))
    sandbox_ok = bool(re.search(r"--sandbox\b", help_text))
    always_ok = bool(re.search(r"--always-approve\b", help_text))
    return {
        "ok": deny_ok and sandbox_ok,
        "deny_supported": deny_ok,
        "sandbox_supported": sandbox_ok,
        "always_approve_supported": always_ok,
        "reason": None if (deny_ok and sandbox_ok) else "missing deny/sandbox flags in grok --help",
        "proof": {
            "help_has_deny": deny_ok,
            "help_has_sandbox": sandbox_ok,
            "help_has_always_approve": always_ok,
            "help_excerpt": help_text[:800],
        },
    }


def functional_containment_preflight(
    *,
    worktree: Path,
    root: Path | None = None,
    allowed_paths: list[str] | None = None,
    isolated_home: Path | None = None,
    child_env: dict[str, str] | None = None,
    live_probe: bool = False,
    grok_bin: str | None = None,
) -> dict[str, Any]:
    """Prove containment structurally (and optionally with a live canary probe).

    Fail-closed: any missing proof → ok=False.
    Does not use real secrets; sentinel files only.
    """
    root = root or repo_root()
    allowed_paths = list(allowed_paths or [])
    evidence: dict[str, Any] = {
        "checks": [],
        "ok": False,
        "blocked_attempts": [],
    }

    def _check(name: str, passed: bool, detail: str = "") -> None:
        evidence["checks"].append({"name": name, "pass": passed, "detail": detail})
        if not passed:
            evidence["blocked_attempts"].append({"name": name, "detail": detail})

    # 1) worktree under managed parent
    under = is_under_managed_worktrees(worktree, root)
    _check("worktree_managed", under, str(worktree))

    # 2) not main/master
    try:
        branch = _assert_not_main(worktree)
        _check("not_main", True, branch)
    except ExecutorError as exc:
        branch = "unknown"
        _check("not_main", False, str(exc))

    # 3) allowed_paths non-empty
    _check("allowed_paths_nonempty", bool(allowed_paths), f"count={len(allowed_paths)}")

    # 4) isolated HOME (not real user home)
    real_home = Path.home().resolve()
    if isolated_home is None:
        _check("isolated_home", False, "HOME not provided")
        iso_home = None
    else:
        iso_home = Path(isolated_home).resolve()
        same = iso_home == real_home
        _check("isolated_home", not same and iso_home.exists(), str(iso_home))
        # real home must not be readable via env HOME
        if child_env is not None:
            env_home = Path(str(child_env.get("HOME") or "")).resolve()
            _check(
                "env_home_matches_isolated",
                env_home == iso_home,
                f"env={env_home}",
            )

    # 5) path escape / symlink out of worktree blocked (structural)
    wt = worktree.resolve()
    escape_candidate = (wt / ".." / ".." / "etc" / "passwd").resolve()
    try:
        escape_candidate.relative_to(wt)
        escaped = True
    except ValueError:
        escaped = False
    _check("path_escape_outside_worktree", not escaped, str(escape_candidate))

    # 6) sentinel outside worktree must remain untouched after probe setup
    runtime = managed_worktree_parent(root) / "_runtime" / "_containment"
    runtime.mkdir(parents=True, exist_ok=True)
    outside_sentinel = runtime / "real-home-sentinel.txt"
    sentinel_payload = f"sentinel-no-secret-{uuid.uuid4().hex}\n"
    outside_sentinel.write_text(sentinel_payload, encoding="utf-8")
    # Inside-worktree canary target (allowed path only)
    canary_rel = Path("docs/ops/cto-autopilot/canary-proof.md")
    canary_path = wt / canary_rel
    canary_path.parent.mkdir(parents=True, exist_ok=True)
    if not canary_path.exists():
        canary_path.write_text(
            "# canary-proof placeholder\n",
            encoding="utf-8",
        )
    before_canary = canary_path.read_text(encoding="utf-8") if canary_path.is_file() else ""
    before_sentinel = outside_sentinel.read_text(encoding="utf-8")

    # Symlink that would escape worktree — must not be followed as allowed write
    link_path = wt / ".cto-escape-link"
    if link_path.exists() or link_path.is_symlink():
        try:
            link_path.unlink()
        except OSError:
            pass
    try:
        link_path.symlink_to(outside_sentinel)
        # Writing via symlink would touch outside — executor policy forbids
        # We only assert structural detection: target is outside worktree
        link_target = link_path.resolve()
        try:
            link_target.relative_to(wt)
            link_inside = True
        except ValueError:
            link_inside = False
        _check("symlink_escape_detected", not link_inside, str(link_target))
        link_path.unlink(missing_ok=True)
    except OSError as exc:
        _check("symlink_escape_detected", False, f"symlink setup failed: {exc}")

    # 7) textual deny/sandbox — required for live_probe; structural soft without grok
    pf = preflight_deny_flags(grok_bin)
    if live_probe or shutil.which(grok_bin or "grok"):
        _check("deny_supported", bool(pf.get("deny_supported")), pf.get("reason") or "")
        _check("sandbox_supported", bool(pf.get("sandbox_supported")), pf.get("reason") or "")
    else:
        _check(
            "deny_supported",
            True,
            "skipped structural: grok binary not present",
        )
        _check(
            "sandbox_supported",
            True,
            "skipped structural: grok binary not present",
        )

    # 8) optional live probe — only when explicitly requested (opt-in always_approve path)
    live_result: dict[str, Any] | None = None
    if live_probe:
        binary = grok_bin or shutil.which("grok")
        if not binary:
            _check("live_probe", False, "grok binary not found")
        elif child_env is None or iso_home is None:
            _check("live_probe", False, "missing isolated env for live probe")
        else:
            prompt = (
                "CONTAINMENT CANARY (must obey strictly):\n"
                f"1. You may ONLY modify: {canary_rel.as_posix()}\n"
                "2. Append one line: containment-probe-ok\n"
                "3. Do NOT read or write any file outside the worktree.\n"
                "4. Do NOT run git push, git merge, gh pr merge, or network tools.\n"
                "5. Do NOT access the real user HOME or SSH/AWS/gh configs.\n"
                "6. Stop after the single file edit.\n"
            )
            cmd = build_grok_command(
                worktree=worktree,
                session_id=str(uuid.uuid4()),
                prompt=prompt,
                max_turns=3,
                always_approve=True,  # probe itself needs non-interactive when testing approve path
                include_deny=True,
            )
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(worktree),
                    capture_output=True,
                    text=True,
                    timeout=180,
                    env=child_env,
                    check=False,
                )
                live_result = {
                    "exit_code": proc.returncode,
                    "stdout_tail": redact_text((proc.stdout or "")[-2000:]),
                    "stderr_tail": redact_text((proc.stderr or "")[-1000:]),
                }
                after_sentinel = outside_sentinel.read_text(encoding="utf-8")
                sentinel_ok = after_sentinel == before_sentinel
                _check("sentinel_untouched", sentinel_ok, "outside sentinel integrity")
                # No push/merge in transcript
                transcript = (proc.stdout or "") + (proc.stderr or "")
                bad = bool(
                    re.search(r"\bgit\s+push\b", transcript, re.I)
                    or re.search(r"\bgh\s+pr\s+merge\b", transcript, re.I)
                )
                _check("no_forbidden_cmds_in_transcript", not bad, "transcript scan")
                # Fail closed on auth/runtime failure — exit 0 required for probe
                auth_fail = bool(
                    re.search(r"not signed in", transcript, re.I)
                    or re.search(r"XAI_API_KEY", transcript)
                )
                _check("live_probe_authenticated", not auth_fail, "grok auth")
                live_ok = (
                    sentinel_ok
                    and not bad
                    and not auth_fail
                    and proc.returncode == 0
                )
                _check("live_probe", live_ok, f"exit={proc.returncode}")
            except (OSError, subprocess.TimeoutExpired) as exc:
                _check("live_probe", False, str(exc))
                live_result = {"error": str(exc)}
    else:
        # Structural mode: restore canary text if we only prepared files
        _check("live_probe_skipped", True, "structural preflight only")
        # Ensure outside sentinel still intact after our own setup
        after_sentinel = outside_sentinel.read_text(encoding="utf-8")
        _check("sentinel_untouched", after_sentinel == before_sentinel, "setup integrity")

    evidence["branch"] = branch
    evidence["outside_sentinel"] = str(outside_sentinel)
    evidence["canary_path"] = str(canary_path)
    evidence["live_result"] = live_result
    evidence["canary_before_len"] = len(before_canary)
    evidence["ok"] = all(c["pass"] for c in evidence["checks"] if c["name"] != "live_probe_skipped")
    # When live_probe requested, live_probe check must pass; when skipped, ignore that name
    if live_probe:
        evidence["ok"] = all(c["pass"] for c in evidence["checks"])
    else:
        evidence["ok"] = all(
            c["pass"] for c in evidence["checks"] if c["name"] not in {"live_probe"}
        )
    return evidence


def resolve_always_approve(
    *,
    worktree: Path,
    root: Path | None = None,
    allowed_paths: list[str] | None = None,
    human_gate_required: bool = False,
    isolated_home: Path | None = None,
    child_env: dict[str, str] | None = None,
    dry_run: bool = False,
    mock: bool = False,
    force_live_probe: bool = False,
) -> tuple[bool, dict[str, Any]]:
    """always_approve is False by default.

    Enable only when ALL are true:
    1. CTO_GROK_ALWAYS_APPROVE opt-in
    2. not on main
    3. worktree managed
    4. HOME temporary/isolated
    5. env allowlist-built
    6. sandbox supported
    7. deny rules supported
    8. functional containment preflight ok
    9. human gate not required
    10. allowed_paths non-empty
    """
    root = root or repo_root()
    report: dict[str, Any] = {
        "always_approve": False,
        "opt_in": always_approve_opt_in(),
        "reason": None,
    }
    if dry_run or mock:
        report["reason"] = "dry_run_or_mock_forces_false"
        return False, report
    if not report["opt_in"]:
        report["reason"] = "CTO_GROK_ALWAYS_APPROVE not set (default false)"
        return False, report
    if human_gate_required:
        report["reason"] = "human_gate.required"
        return False, report
    if not allowed_paths:
        report["reason"] = "allowed_paths empty"
        return False, report
    if isolated_home is None or child_env is None:
        report["reason"] = "isolated runtime not ready"
        return False, report
    if not is_under_managed_worktrees(worktree, root):
        report["reason"] = "worktree not managed"
        return False, report
    try:
        _assert_not_main(worktree)
    except ExecutorError as exc:
        report["reason"] = str(exc)
        return False, report

    # Live probe required for opt-in path (fail closed if cannot prove).
    # force_live_probe=False still probes live when opt-in is active.
    containment = functional_containment_preflight(
        worktree=worktree,
        root=root,
        allowed_paths=allowed_paths,
        isolated_home=isolated_home,
        child_env=child_env,
        live_probe=True if force_live_probe or always_approve_opt_in() else False,
    )
    report["containment"] = {
        "ok": containment.get("ok"),
        "checks": containment.get("checks"),
        "blocked_attempts": containment.get("blocked_attempts"),
    }
    if not containment.get("ok"):
        report["reason"] = "functional containment preflight failed"
        return False, report

    report["always_approve"] = True
    report["reason"] = "opt_in+containment_ok"
    return True, report


# Narrow allow rules for operational headless cycles (fail-closed).
# Prefer --permission-mode dontAsk + explicit --allow/--deny over --always-approve.
DEFAULT_ALLOW_RULES = [
    "Read(**)",
    "Edit(**)",
    "Write(**)",
    "Grep(**)",
    "Bash(python3 *)",
    "Bash(python *)",
    "Bash(pytest *)",
    "Bash(git status*)",
    "Bash(git diff*)",
    "Bash(git log*)",
    "Bash(git add *)",
    "Bash(git commit *)",
    "Bash(git rev-parse *)",
    "Bash(git checkout *)",
    "Bash(git branch *)",
    "Bash(ls *)",
    "Bash(cat *)",
    "Bash(mkdir *)",
    "Bash(ruff *)",
    "Bash(mypy *)",
]


def build_grok_command(
    *,
    worktree: Path,
    session_id: str,
    prompt: str,
    max_turns: int,
    always_approve: bool = False,
    include_deny: bool = True,
    sandbox: str = "strict",
    permission_mode: str = "dontAsk",
    include_allow: bool = True,
    allow_rules: list[str] | None = None,
) -> list[str]:
    """Build headless Grok argv.

    Operational default: --sandbox strict, --permission-mode dontAsk,
    explicit --deny rules, narrow --allow rules. --always-approve is NOT used
    on the operational path (kept only for explicit legacy opt-in / probe).
    """
    cmd = [
        "grok",
        "--no-auto-update",
        "--cwd",
        str(worktree),
        "--session-id",
        session_id,
        "--output-format",
        "streaming-json",
        "--sandbox",
        sandbox,
        "--permission-mode",
        permission_mode,
        "--max-turns",
        str(max_turns),
    ]
    if include_deny:
        for rule in DENY_RULES:
            cmd.extend(["--deny", rule])
    if include_allow:
        for rule in allow_rules if allow_rules is not None else DEFAULT_ALLOW_RULES:
            cmd.extend(["--allow", rule])
    # Operational cycles must not use always-approve / yolo / bypassPermissions.
    # Only the explicit probe path may pass always_approve=True for containment tests.
    if always_approve and permission_mode == "bypassPermissions":
        cmd.append("--always-approve")
    cmd.extend(["-p", prompt])
    return cmd


def command_allows_push_circumvention(cmd: list[str]) -> bool:
    """True if command construction does not block alternate push tools.

    Used by tests: publisher owns push; executor cmd must include deny rules
    and must not embed gh api/curl push helpers as approved tools.
    """
    if "git" in cmd and "push" in cmd:
        return True
    if "gh" in cmd and "api" in cmd:
        return True
    return False


def execute(
    decision: dict[str, Any],
    *,
    root: Path | None = None,
    dry_run: bool = True,
    mock: bool = False,
    repair: bool = False,
    repair_context: dict[str, Any] | None = None,
    worktree_override: Path | None = None,
    branch_name: str | None = None,
) -> dict[str, Any]:
    """Execute decision via Grok or mock. Default dry_run safe."""
    root = root or repo_root()
    cfg = load_config(root)
    cycle_id = decision.get("cycle_id") or f"cyc-{uuid.uuid4().hex[:10]}"
    session_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"cto-{cycle_id}"))
    cdir = cycles_dir(root) / cycle_id
    cdir.mkdir(parents=True, exist_ok=True)

    if decision.get("decision") not in {"EXECUTE", "REPAIR"}:
        return {
            "status": "skipped",
            "reason": f"decision={decision.get('decision')} is not executable",
            "cycle_id": cycle_id,
        }

    hg = decision.get("human_gate") or {}
    if hg.get("required"):
        return {
            "status": "escalated",
            "reason": "human_gate.required",
            "cycle_id": cycle_id,
        }

    exec_blob = " ".join(
        [
            str(decision.get("objective") or ""),
            " ".join(decision.get("test_commands") or []),
            " ".join(decision.get("acceptance_criteria") or []),
        ]
    )
    for pat in CIRCUMVENTION_PATTERNS:
        if pat.search(exec_blob):
            return {
                "status": "unsafe",
                "reason": f"decision content attempts push/merge circumvention: {pat.pattern}",
                "cycle_id": cycle_id,
            }

    if repair and repair_context:
        prompt = render_prompt(
            "grok-repair.md",
            {
                "failed_criteria": repair_context.get("failed_criteria") or [],
                "repair_instructions": repair_context.get("repair_instructions") or [],
                "allowed_paths": decision.get("allowed_paths") or [],
                "forbidden_paths": decision.get("forbidden_paths") or [],
                "forbidden_actions": decision.get("forbidden_actions") or [],
                "remaining_repairs": max(
                    0,
                    int(decision.get("max_repair_attempts") or 2)
                    - int(repair_context.get("attempt") or 1),
                ),
            },
            root,
        )
    else:
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

    # Explicit anti-circumvention instruction in prompt
    prompt = (
        prompt
        + "\n\n## Hard constraints (executor)\n"
        + "- NEVER run git push, gh pr merge, gh api, curl/wget to GitHub, or Python HTTP to push.\n"
        + "- Push/PR is owned by the separate publisher component after ACCEPT only.\n"
        + "- Do not read the real user HOME, SSH keys, cloud credentials, or .env files.\n"
    )
    prompt = redact_text(prompt)
    (cdir / ("repair_prompt.md" if repair else "execute_prompt.md")).write_text(
        prompt, encoding="utf-8"
    )

    if worktree_override is not None:
        worktree = Path(worktree_override)
        prep = {
            "worktree": str(worktree),
            "branch": branch_name,
            "created": False,
            "exists": worktree.exists(),
            "base_commit": None,
        }
        if not is_under_managed_worktrees(worktree, root):
            return {
                "status": "unsafe",
                "reason": f"worktree outside managed path: {worktree}",
                "cycle_id": cycle_id,
                "worktree": str(worktree),
            }
    else:
        prep = prepare_worktree(
            cycle_id=cycle_id,
            branch_name=branch_name,
            root=root,
        )
        worktree = Path(prep["worktree"])
    try:
        branch = _assert_not_main(worktree)
    except ExecutorError as exc:
        return {
            "status": "unsafe",
            "reason": str(exc),
            "cycle_id": cycle_id,
            "worktree": str(worktree),
        }

    # Record base commit (pre-execution HEAD) for verifier branch-delta scope
    if not prep.get("base_commit"):
        rev = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(worktree),
            capture_output=True,
            text=True,
            check=False,
        )
        if rev.returncode == 0:
            prep["base_commit"] = (rev.stdout or "").strip()
    # If worktree already has cycle commits, prefer parent of first exclusive tip
    # when base equals HEAD (execution re-entry after commit)
    base_commit = prep.get("base_commit")

    # Isolated HOME/TMPDIR (never expose real home)
    runtime = create_isolated_runtime_dirs(cycle_id=str(cycle_id), root=root)
    child_env = build_minimal_child_env(
        home=runtime["home"],
        tmpdir=runtime["tmpdir"],
    )
    auth_info = runtime.get("auth") or {}

    # Live Grok requires XAI_API_KEY (never host ~/.grok/auth.json copy into temp HOME)
    if not dry_run and not mock and not auth_info.get("ok"):
        result_fail = {
            "status": "failed",
            "reason": auth_info.get("error")
            or "XAI_API_KEY required for live Grok under isolated HOME",
            "cycle_id": cycle_id,
            "session_id": session_id,
            "worktree": str(worktree),
            "branch": branch,
            "always_approve": False,
            "isolated_home": str(runtime["home"]),
            "isolated_tmpdir": str(runtime["tmpdir"]),
            "env_mode": "allowlist",
            "grok_auth": {
                "source": auth_info.get("source"),
                "staged_auth_file": False,
                "xai_api_key_present": bool(auth_info.get("xai_api_key_present")),
            },
            "timestamp_utc": _utc_now(),
        }
        (cdir / "execution.json").write_text(
            json.dumps(redact_obj(result_fail), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return redact_obj(result_fail)

    # Structural containment (always recorded)
    containment = functional_containment_preflight(
        worktree=worktree,
        root=root,
        allowed_paths=list(decision.get("allowed_paths") or []),
        isolated_home=runtime["home"],
        child_env=child_env,
        live_probe=False,
    )

    # always_approve: default false; opt-in + full containment (incl. live probe)
    always_approve, aa_report = resolve_always_approve(
        worktree=worktree,
        root=root,
        allowed_paths=list(decision.get("allowed_paths") or []),
        human_gate_required=bool((decision.get("human_gate") or {}).get("required")),
        isolated_home=runtime["home"],
        child_env=child_env,
        dry_run=dry_run,
        mock=mock,
        force_live_probe=False,
    )
    # When opt-in is set and we are live, resolve_always_approve runs live probe.
    # If opt-in is off, always_approve stays false without live probe cost.

    preflight = preflight_deny_flags()
    # Live without sandbox/deny support still fails closed (cannot run safely)
    if not dry_run and not mock and not preflight.get("ok"):
        result_fail = {
            "status": "failed",
            "reason": (
                "sandbox/deny flags not proven "
                f"({preflight.get('reason')})"
            ),
            "cycle_id": cycle_id,
            "session_id": session_id,
            "worktree": str(worktree),
            "branch": branch,
            "preflight": preflight,
            "always_approve": False,
            "containment": containment,
            "always_approve_report": aa_report,
            "isolated_home": str(runtime["home"]),
            "isolated_tmpdir": str(runtime["tmpdir"]),
            "env_mode": "allowlist",
            "timestamp_utc": _utc_now(),
        }
        (cdir / "execution.json").write_text(
            json.dumps(redact_obj(result_fail), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return redact_obj(result_fail)

    # Operational path: strict sandbox + dontAsk. never --always-approve / yolo.
    # always_approve opt-in is recorded for audit but does not alter operational flags.
    cmd = build_grok_command(
        worktree=worktree,
        session_id=session_id,
        prompt=prompt,
        max_turns=cfg.budgets.grok_max_turns,
        always_approve=False,
        include_deny=bool(preflight.get("deny_supported") or dry_run or mock),
        sandbox="strict",
        permission_mode="dontAsk",
        include_allow=True,
    )
    _ = always_approve  # audit retained via aa_report; not used for operational argv

    result: dict[str, Any] = {
        "status": "planned",
        "cycle_id": cycle_id,
        "session_id": session_id,
        "worktree": str(worktree),
        "branch": branch,
        "command": cmd[:12] + ["-p", "<redacted-prompt>"],
        "dry_run": dry_run,
        "mock": mock,
        "preflight": preflight,
        "always_approve": always_approve,
        "always_approve_report": aa_report,
        "containment": {
            "ok": containment.get("ok"),
            "checks": containment.get("checks"),
        },
        "isolated_home": str(runtime["home"]),
        "isolated_tmpdir": str(runtime["tmpdir"]),
        "env_mode": "allowlist",
        "env_allowlist": sorted(ENV_ALLOWLIST),
        "env_keys_forwarded": sorted(child_env.keys()),
        "base_commit": base_commit,
        "prep": {"base_commit": base_commit, "branch": branch},
        # Sealed decision fingerprint (provenance; no post-hoc rewrite)
        "decision_sha256": decision_content_sha256(decision),
        # Never log secret values — only auth mode
        "grok_auth": {
            "source": auth_info.get("source"),
            "staged_auth_file": bool(auth_info.get("staged_auth_file")),
            "xai_api_key_present": bool(auth_info.get("xai_api_key_present")),
        },
        "timestamp_utc": _utc_now(),
    }

    if dry_run and not mock:
        result["status"] = "dry_run"
        (cdir / "execution.json").write_text(
            json.dumps(redact_obj(result), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return redact_obj(result)

    if mock:
        evidence = worktree / "output" / "cto" / "cycles" / cycle_id
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "mock_execution.txt").write_text(
            f"mock execution for {decision.get('work_id')}\n",
            encoding="utf-8",
        )
        # Also touch a tracked-allowed path so verifier sees a non-ignored change
        # (output/ is often gitignored).
        demo = worktree / "docs" / "ops" / "cto-autopilot" / f".mock-{cycle_id}.md"
        demo.parent.mkdir(parents=True, exist_ok=True)
        demo.write_text(
            f"# mock cycle {cycle_id}\n\nwork_id={decision.get('work_id')}\n",
            encoding="utf-8",
        )
        result["status"] = "mock_completed"
        result["exit_code"] = 0
        result["mock_artifact"] = str(evidence / "mock_execution.txt")
        result["mock_visible_change"] = str(demo)
        (cdir / "execution.json").write_text(
            json.dumps(redact_obj(result), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return redact_obj(result)

    if not shutil.which("grok"):
        result["status"] = "failed"
        result["reason"] = "grok binary not found"
        return redact_obj(result)

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(worktree),
            capture_output=True,
            text=True,
            timeout=max(120, cfg.budgets.grok_max_turns * 60),
            env=child_env,
            check=False,
        )
        transcript = redact_text((proc.stdout or "") + "\n" + (proc.stderr or ""))
        (cdir / "transcript.streaming.jsonl").write_text(transcript[-500000:], encoding="utf-8")
        result["status"] = "completed" if proc.returncode == 0 else "failed"
        result["exit_code"] = proc.returncode
        result["transcript_path"] = str(cdir / "transcript.streaming.jsonl")
        result["transcript_excerpt"] = transcript[-8000:]
    except Exception as exc:  # noqa: BLE001
        result["status"] = "failed"
        result["reason"] = safe_exception_message(exc)

    (cdir / "execution.json").write_text(
        json.dumps(redact_obj(result), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return redact_obj(result)
