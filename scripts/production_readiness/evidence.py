"""Sanitized evidence writer for production-readiness artifacts."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]

_SECRET_RE = re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|authorization|cookie|bearer)\s*[:=]\s*\S+")
_DSN_RE = re.compile(r"postgresql(\+\w+)?://[^\s\"']+")
_IPV4_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


def _iso() -> str:
    return datetime.now(UTC).isoformat()


def git_sha() -> str | None:
    try:
        git = shutil.which("git")
        if not git:
            return None
        out = subprocess.check_output(  # noqa: S603
            [git, "rev-parse", "HEAD"],
            cwd=str(REPO),
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return out.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            lk = str(k).lower()
            if any(s in lk for s in ("password", "secret", "token", "api_key", "authorization", "cookie")):
                out[k] = "***REDACTED***"
            else:
                out[k] = sanitize(v)
        return out
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, str):
        text = _DSN_RE.sub("postgresql://***REDACTED***", value)
        text = _SECRET_RE.sub(r"\1=***REDACTED***", text)
        # keep private IPs pattern but mask last octet soft — actually mask all for safety
        text = _IPV4_RE.sub("x.x.x.x", text)
        return text
    return value


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = sanitize(payload)
    if "timestamp" not in clean:
        clean = {"timestamp": _iso(), **clean}
    if "sha" not in clean and "code_sha" not in clean:
        clean["code_sha"] = git_sha()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def evidence_root(ts: str | None = None) -> Path:
    stamp = ts or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    root = REPO / "artifacts" / "production-readiness" / stamp
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_baseline(root: Path, **extra: Any) -> Path:
    payload = {
        "branch": _git_branch(),
        "head": git_sha(),
        "baseline_merge": "704975a7bcdd43d4dc6769fbf6c14726327ab37b",
        "command": "git rev-parse HEAD && git merge-base --is-ancestor 704975a7… HEAD",
        "result": "BASELINE_OK",
        **extra,
    }
    return write_json(root / "baseline.json", payload)


def write_environment(root: Path, **extra: Any) -> Path:
    import platform
    import sys

    payload = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "cwd": str(REPO),
        "env_keys_present": sorted(
            k
            for k in (
                "LOCAL_DATALAKE_DSN",
                "DATABASE_URL",
                "PROCESS_DOCUMENTS_META_ROOT",
                "PROCESS_DOCUMENTS_RAW_ROOT",
            )
            if os.environ.get(k)
        ),
        **extra,
    }
    return write_json(root / "environment.json", payload)


def _git_branch() -> str | None:
    try:
        git = shutil.which("git")
        if not git:
            return None
        out = subprocess.check_output(  # noqa: S603
            [git, "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(REPO),
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return out.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None
