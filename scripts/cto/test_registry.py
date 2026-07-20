"""Human-versioned authorized test registry for the CTO verifier.

DeepSeek/Grok may select only test_id values. Free-form shell is never executed.
Legacy free-string commands are resolved via aliases or rejected fail-closed.
"""
from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

from scripts.cto.paths import cto_dir, repo_root

# Substrings/tokens that must never appear in argv resolved from the registry.
_FORBIDDEN_ARGV_TOKENS = frozenset(
    {
        "bash",
        "sh",
        "zsh",
        "curl",
        "wget",
        "git",
        "gh",
        "sudo",
        "rm",
        "chmod",
        "chown",
    }
)
_FORBIDDEN_ARGV_FLAGS = frozenset({"-c", "--eval", "-e"})
_SHELL_METACHAR = frozenset({";", "&&", "||", "|", "`", "$(", "\n", ">", "<"})


class AuthorizedTestError(ValueError):
    """Unknown, unsafe, or malformed authorized test entry."""


# Back-compat alias
TestRegistryError = AuthorizedTestError


def authorized_tests_path(root: Path | None = None) -> Path:
    return cto_dir(root) / "authorized_tests.yaml"


@lru_cache(maxsize=8)
def _load_raw(path_str: str) -> dict[str, Any]:
    import yaml

    path = Path(path_str)
    if not path.is_file():
        raise TestRegistryError(f"authorized tests registry missing: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise TestRegistryError("authorized_tests.yaml must be a mapping")
    return data


def load_registry(root: Path | None = None, *, force_reload: bool = False) -> dict[str, Any]:
    path = authorized_tests_path(root)
    if force_reload:
        _load_raw.cache_clear()
    return _load_raw(str(path.resolve()))


def list_test_ids(root: Path | None = None) -> list[str]:
    data = load_registry(root)
    return [str(t["test_id"]) for t in (data.get("tests") or []) if t.get("test_id")]


def get_entry(test_id: str, root: Path | None = None) -> dict[str, Any]:
    data = load_registry(root)
    for entry in data.get("tests") or []:
        if str(entry.get("test_id")) == test_id:
            return dict(entry)
    raise TestRegistryError(f"unknown test_id: {test_id!r}")


def resolve_legacy_command(cmd: str, root: Path | None = None) -> str | None:
    """Map a legacy free-string command to a test_id, or None if unknown."""
    data = load_registry(root)
    aliases = data.get("legacy_command_aliases") or {}
    key = " ".join(str(cmd).split())
    if key in aliases:
        return str(aliases[key])
    # Normalize python/python3
    alt = key.replace("python3 -m", "python -m").replace("python -m", "python3 -m")
    if alt in aliases:
        return str(aliases[alt])
    key2 = key.replace("python3 ", "python ")
    if key2 in aliases:
        return str(aliases[key2])
    return None


def normalize_test_ids(
    decision: dict[str, Any],
    *,
    root: Path | None = None,
    allow_legacy_commands: bool = True,
) -> list[str]:
    """Return authorized test_ids from decision.test_ids and/or legacy test_commands.

    Model output path must pass ``allow_legacy_commands=False`` so free-form
    ``test_commands`` never enter the system as new decisions. Legacy import /
    registry seeds may set ``allow_legacy_commands=True`` for deterministic alias
    resolution only — aliases never become shell execution of the raw string.

    Unknown test_ids always raise.
    """
    ids: list[str] = []
    raw_ids = decision.get("test_ids")
    if raw_ids is None:
        raw_ids = []
    if not isinstance(raw_ids, list):
        raise TestRegistryError("test_ids must be a list")
    for tid in raw_ids:
        tid_s = str(tid).strip()
        if not tid_s:
            continue
        get_entry(tid_s, root)  # validates existence
        if tid_s not in ids:
            ids.append(tid_s)

    cmds = decision.get("test_commands") or []
    if not isinstance(cmds, list):
        raise TestRegistryError("test_commands must be a list")
    if cmds and not allow_legacy_commands:
        raise TestRegistryError(
            "test_commands are forbidden on model-authored decisions; use test_ids only"
        )
    for cmd in cmds:
        if not isinstance(cmd, str) or not cmd.strip():
            raise TestRegistryError(f"invalid test_commands entry: {cmd!r}")
        # Reject metacharacters immediately — never split/execute free shell
        if any(m in cmd for m in _SHELL_METACHAR):
            raise TestRegistryError(f"rejected unsafe free-form test command: {cmd[:120]!r}")
        mapped = resolve_legacy_command(cmd, root)
        if mapped is None:
            # Allow if the string itself is a known test_id
            try:
                get_entry(cmd.strip(), root)
                mapped = cmd.strip()
            except TestRegistryError as exc:
                raise TestRegistryError(
                    f"free-form test_commands not in registry/aliases: {cmd[:120]!r}"
                ) from exc
        if mapped not in ids:
            get_entry(mapped, root)
            ids.append(mapped)
    return ids


def describe_authorized_tests(
    test_ids: list[str],
    *,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Human-readable registry detail for executor prompts (no free shell)."""
    out: list[dict[str, Any]] = []
    for tid in test_ids:
        entry = get_entry(tid, root)
        out.append(
            {
                "test_id": tid,
                "description": entry.get("description") or "",
                "expected_files": list(entry.get("expected_files") or []),
                "argv_resolved": list(entry.get("argv") or []),
                "risk_class": entry.get("risk_class") or "low",
            }
        )
    return out


def _validate_argv(argv: list[str]) -> list[str]:
    if not argv or not isinstance(argv, list):
        raise TestRegistryError("argv must be a non-empty list")
    out: list[str] = []
    for part in argv:
        if not isinstance(part, str) or not part:
            raise TestRegistryError(f"invalid argv token: {part!r}")
        if any(m in part for m in _SHELL_METACHAR):
            raise TestRegistryError(f"argv token contains shell metachar: {part!r}")
        out.append(part)
    head = out[0].lower()
    base = Path(head).name.lower()
    if base in _FORBIDDEN_ARGV_TOKENS and base not in {"grep"}:
        # grep is allowed as a registered binary; git/gh/bash never
        if base in {"bash", "sh", "zsh", "curl", "wget", "sudo", "rm"}:
            raise TestRegistryError(f"forbidden interpreter/tool in argv[0]: {out[0]!r}")
        if base in {"git", "gh"}:
            raise TestRegistryError(f"forbidden VCS/API tool in argv: {out[0]!r}")
    # Reject python -c / bash -c style
    for i, tok in enumerate(out):
        if tok in _FORBIDDEN_ARGV_FLAGS and i > 0:
            prev = out[i - 1].lower()
            if any(x in prev for x in ("python", "bash", "sh", "zsh", "node", "perl", "ruby")):
                raise TestRegistryError(f"forbidden eval-style flag {tok!r} after {prev!r}")
    return out


def resolve_argv(
    test_id: str,
    *,
    root: Path | None = None,
    worktree: Path | None = None,
) -> dict[str, Any]:
    """Resolve test_id to executable argv + metadata. Never parses free shell."""
    root = root or repo_root()
    entry = get_entry(test_id, root)
    argv = _validate_argv(list(entry.get("argv") or []))
    cwd_policy = str(entry.get("cwd") or "repo_root")
    if cwd_policy == "repo_root":
        cwd = Path(worktree) if worktree else root
    elif cwd_policy == "worktree":
        cwd = Path(worktree) if worktree else root
    else:
        raise TestRegistryError(f"unsupported cwd policy: {cwd_policy!r}")
    return {
        "test_id": test_id,
        "argv": argv,
        "cwd": cwd,
        "timeout_sec": int(entry.get("timeout_sec") or 300),
        "env_allowlist": list(entry.get("env_allowlist") or ["PATH", "HOME", "LANG"]),
        "needs_db": bool(entry.get("needs_db")),
        "network": str(entry.get("network") or "deny"),
        "expected_files": list(entry.get("expected_files") or []),
        "risk_class": str(entry.get("risk_class") or "low"),
        "description": str(entry.get("description") or ""),
    }


def build_minimal_env(allowlist: list[str], *, base: dict[str, str] | None = None) -> dict[str, str]:
    src = base if base is not None else os.environ
    out: dict[str, str] = {}
    for key in allowlist:
        val = src.get(key)
        if val is not None:
            out[key] = val
    # Always provide a PATH if missing so python3 resolves
    if "PATH" not in out and "PATH" in src:
        out["PATH"] = src["PATH"]
    return out


def run_authorized_test(
    test_id: str,
    *,
    root: Path | None = None,
    worktree: Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Execute a single authorized test_id with shell=False."""
    resolved = resolve_argv(test_id, root=root, worktree=worktree)
    child_env = build_minimal_env(resolved["env_allowlist"], base=env)
    try:
        proc = subprocess.run(
            resolved["argv"],
            cwd=str(resolved["cwd"]),
            capture_output=True,
            text=True,
            timeout=resolved["timeout_sec"],
            check=False,
            shell=False,
            env=child_env,
        )
        return {
            "test_id": test_id,
            "cmd": resolved["argv"],
            "argv": resolved["argv"],
            "exit_code": proc.returncode,
            "stdout": (proc.stdout or "")[-12000:],
            "stderr": (proc.stderr or "")[-6000:],
            "timeout_sec": resolved["timeout_sec"],
            "cwd": str(resolved["cwd"]),
            "shell": False,
        }
    except subprocess.TimeoutExpired:
        return {
            "test_id": test_id,
            "cmd": resolved["argv"],
            "argv": resolved["argv"],
            "exit_code": -1,
            "stdout": "",
            "stderr": "timeout",
            "timeout_sec": resolved["timeout_sec"],
            "cwd": str(resolved["cwd"]),
            "shell": False,
        }
    except FileNotFoundError:
        return {
            "test_id": test_id,
            "cmd": resolved["argv"],
            "argv": resolved["argv"],
            "exit_code": -2,
            "stdout": "",
            "stderr": "not_found",
            "timeout_sec": resolved["timeout_sec"],
            "cwd": str(resolved["cwd"]),
            "shell": False,
        }
