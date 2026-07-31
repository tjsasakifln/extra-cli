"""Configuration for the local Command Center (fail-closed defaults)."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _default_data_dir() -> Path:
    return REPO_ROOT / "data" / "command_center"


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8765
    data_dir: Path = field(default_factory=_default_data_dir)
    max_concurrent_jobs: int = 2
    default_job_timeout_sec: int = 3600
    max_log_bytes_per_job: int = 2_000_000
    max_artifact_read_bytes: int = 2_000_000
    artifact_sample_lines: int = 200
    csrf_cookie_name: str = "cc_csrf"
    csrf_header_name: str = "X-CC-CSRF"
    cors_origins: tuple[str, ...] = (
        "http://127.0.0.1:8765",
        "http://localhost:8765",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )
    allowed_artifact_roots: tuple[Path, ...] = field(default_factory=tuple)
    open_browser: bool = True
    spa_dist: Path | None = None

    @property
    def db_path(self) -> Path:
        return self.data_dir / "command_center.sqlite3"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"


def load_settings() -> Settings:
    data_dir = Path(os.environ.get("CC_DATA_DIR", str(_default_data_dir()))).resolve()
    host = os.environ.get("CC_HOST", "127.0.0.1")
    # Explicit denylist of public binds — never the listen address by default.
    if host in {"0.0.0.0", "::", "[::]"} and os.environ.get("CC_ALLOW_PUBLIC_BIND") != "1":  # noqa: S104
        host = "127.0.0.1"
    port = int(os.environ.get("CC_PORT", "8765"))
    spa = os.environ.get("CC_SPA_DIST")
    spa_dist = Path(spa).resolve() if spa else (REPO_ROOT / "apps" / "command-center" / "dist")
    roots = [
        (REPO_ROOT / "output").resolve(),
        (REPO_ROOT / "artifacts").resolve(),
        (REPO_ROOT / "data" / "command_center").resolve(),
        (REPO_ROOT / "docs").resolve(),
        (REPO_ROOT / "config").resolve(),
        (REPO_ROOT / ".dod").resolve(),
    ]
    extra_roots = os.environ.get("CC_ARTIFACT_ROOTS", "")
    for part in extra_roots.split(os.pathsep):
        part = part.strip()
        if part:
            roots.append(Path(part).resolve())
    return Settings(
        host=host,
        port=port,
        data_dir=data_dir,
        max_concurrent_jobs=int(os.environ.get("CC_MAX_CONCURRENT_JOBS", "2")),
        default_job_timeout_sec=int(os.environ.get("CC_JOB_TIMEOUT_SEC", "3600")),
        open_browser=os.environ.get("CC_OPEN_BROWSER", "1") not in {"0", "false", "False"},
        spa_dist=spa_dist if spa_dist.exists() else None,
        allowed_artifact_roots=tuple(roots),
    )


def git_sha(short: bool = True) -> str:
    try:
        out = subprocess.run(  # noqa: S603
            ["git", "rev-parse", "--short" if short else "HEAD", "HEAD"],  # noqa: S607
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown"
