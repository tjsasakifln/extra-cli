"""Typed pipeline adapters for Command Center REAL mode.

Security contract:
- argv is always a list (never shell=True)
- only registered modules/commands
- secrets stay in process env; redacted in logs/manifests
- no silent fallback to fixture
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from scripts.command_center.config import REPO_ROOT, git_sha
from scripts.command_center.redaction import redact_mapping, redact_text
from scripts.command_center.security import assert_argv_list

ExecFn = Callable[[list[str], Path, dict[str, str] | None], "SubprocessResult"]


class PreflightStatus(StrEnum):
    READY = "READY"
    BLOCKED_CONFIG = "BLOCKED_CONFIG"
    BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"
    BLOCKED_DATA = "BLOCKED_DATA"
    BLOCKED_PERMISSION = "BLOCKED_PERMISSION"


class DataMode(StrEnum):
    REAL = "REAL"
    FIXTURE = "FIXTURE"


@dataclass
class PreflightCheck:
    name: str
    ok: bool
    detail: str
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PreflightResult:
    status: str
    checks: list[PreflightCheck] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    safe_to_run: bool = False
    capability_id: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checks": [c.to_dict() for c in self.checks],
            "limitations": list(self.limitations),
            "safe_to_run": self.safe_to_run,
            "capability_id": self.capability_id,
            "message": self.message,
        }


@dataclass
class SubprocessResult:
    exit_code: int
    stdout: str
    stderr: str
    started_at: str
    finished_at: str
    duration_ms: int
    argv: list[str]


@dataclass
class AdapterResult:
    status: str  # SUCCEEDED | FAILED | BLOCKED_* | PARTIAL
    exit_code: int
    data_mode: str
    argv: list[str]
    artifacts: list[Path]
    out_dir: Path
    started_at: str
    finished_at: str
    duration_ms: int
    code_sha: str
    params_public: dict[str, Any]
    preflight: dict[str, Any]
    limitations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    coverage: dict[str, Any] = field(default_factory=dict)
    source_snapshots: list[dict[str, Any]] = field(default_factory=list)
    terminal_claim: str | None = None
    stdout_tail: str = ""
    stderr_tail: str = ""
    message: str = ""
    rows: list[dict[str, Any]] = field(default_factory=list)
    pipeline_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["artifacts"] = [str(p) for p in self.artifacts]
        d["out_dir"] = str(self.out_dir)
        return d


class AdapterBlockedError(RuntimeError):
    """Raised when REAL mode cannot run; never triggers fixture fallback."""

    def __init__(self, preflight: PreflightResult, *, message: str | None = None) -> None:
        self.preflight = preflight
        super().__init__(message or preflight.message or preflight.status)


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def resolve_data_mode(params: dict[str, Any]) -> DataMode:
    """Resolve REAL vs FIXTURE from explicit params. No silent default to REAL when ambiguous.

    Priority:
    1. data_mode = REAL|FIXTURE (case-insensitive)
    2. use_fixture bool (True→FIXTURE, False→REAL)
    3. default FIXTURE (safe for guided demos / existing tests)
    """
    raw = params.get("data_mode")
    if raw is not None and str(raw).strip():
        val = str(raw).strip().upper()
        if val in {DataMode.REAL.value, DataMode.FIXTURE.value}:
            return DataMode(val)
        raise ValueError(f"data_mode inválido: {raw!r} (use REAL ou FIXTURE)")
    if "use_fixture" in params and params.get("use_fixture") is not None:
        uf = params.get("use_fixture")
        if isinstance(uf, str):
            uf = uf.lower() in {"1", "true", "yes", "sim"}
        return DataMode.FIXTURE if uf else DataMode.REAL
    return DataMode.FIXTURE


def public_params(params: dict[str, Any]) -> dict[str, Any]:
    """Non-secret params for manifests/logs."""
    blocked = {
        "dsn",
        "password",
        "token",
        "api_key",
        "secret",
        "authorization",
        "LOCAL_DATALAKE_DSN",
        "source_dsn",
    }
    clean: dict[str, Any] = {}
    for k, v in (params or {}).items():
        lk = str(k).lower()
        if any(b in lk for b in blocked):
            clean[k] = "[REDACTED]"
            continue
        clean[k] = v
    return redact_mapping(clean)


def default_exec(
    argv: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    *,
    timeout_sec: int = 3600,
) -> SubprocessResult:
    """Run allowlisted argv with shell=False; capture + redact streams."""
    safe_argv = assert_argv_list(list(argv))
    started = _utcnow()
    t0 = time.monotonic()
    merged = os.environ.copy()
    if env:
        merged.update(env)
    # Never inject secrets from params into env here — caller owns env.
    try:
        completed = subprocess.run(  # noqa: S603 — argv allowlisted; shell=False
            safe_argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            shell=False,
            timeout=timeout_sec,
            env=merged,
            check=False,
        )
        exit_code = int(completed.returncode)
        stdout = redact_text(completed.stdout or "")
        stderr = redact_text(completed.stderr or "")
    except subprocess.TimeoutExpired as exc:
        exit_code = 124
        stdout = redact_text((exc.stdout or b"").decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else str(exc.stdout or ""))
        stderr = redact_text(f"TIMEOUT after {timeout_sec}s: {exc}")
    except OSError as exc:
        exit_code = 127
        stdout = ""
        stderr = redact_text(str(exc))
    finished = _utcnow()
    duration_ms = int((time.monotonic() - t0) * 1000)
    return SubprocessResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        started_at=started,
        finished_at=finished,
        duration_ms=duration_ms,
        argv=safe_argv,
    )


def python_module_argv(module: str, *args: str) -> list[str]:
    return [sys.executable, "-m", module, *[str(a) for a in args if a is not None]]


def check_module_importable(module: str) -> PreflightCheck:
    try:
        __import__(module)
        return PreflightCheck(name=f"module:{module}", ok=True, detail="importável")
    except Exception as exc:  # noqa: BLE001 — preflight surface
        return PreflightCheck(
            name=f"module:{module}",
            ok=False,
            detail=f"não importável: {type(exc).__name__}",
            required=True,
        )


def check_env_present(name: str, *, required: bool = True) -> PreflightCheck:
    val = os.environ.get(name)
    if val and str(val).strip():
        return PreflightCheck(name=f"env:{name}", ok=True, detail="presente", required=required)
    return PreflightCheck(
        name=f"env:{name}",
        ok=False,
        detail="ausente",
        required=required,
    )


def check_dir_writable(path: Path, *, name: str | None = None) -> PreflightCheck:
    label = name or f"dir:{path}"
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".cc_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return PreflightCheck(name=label, ok=True, detail=str(path))
    except OSError as exc:
        return PreflightCheck(name=label, ok=False, detail=str(exc), required=True)


def check_postgres_optional(dsn_env: str = "LOCAL_DATALAKE_DSN") -> PreflightCheck:
    dsn = os.environ.get(dsn_env)
    if not dsn:
        return PreflightCheck(
            name="postgres",
            ok=False,
            detail=f"{dsn_env} ausente",
            required=True,
        )
    try:
        import psycopg  # type: ignore[import-untyped]
    except ImportError:
        try:
            import psycopg2  # type: ignore[import-untyped]
        except ImportError:
            return PreflightCheck(
                name="postgres",
                ok=False,
                detail="driver psycopg/psycopg2 ausente",
                required=True,
            )
        try:
            conn = psycopg2.connect(dsn, connect_timeout=3)
            conn.close()
            return PreflightCheck(name="postgres", ok=True, detail="conectado (psycopg2)")
        except Exception as exc:  # noqa: BLE001
            return PreflightCheck(
                name="postgres",
                ok=False,
                detail=f"falha de conexão: {type(exc).__name__}",
                required=True,
            )
    try:
        with psycopg.connect(dsn, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return PreflightCheck(name="postgres", ok=True, detail="conectado")
    except Exception as exc:  # noqa: BLE001
        return PreflightCheck(
            name="postgres",
            ok=False,
            detail=f"falha de conexão: {type(exc).__name__}",
            required=True,
        )


def finalize_preflight(
    checks: list[PreflightCheck],
    *,
    capability_id: str,
    limitations: list[str] | None = None,
) -> PreflightResult:
    failed_required = [c for c in checks if c.required and not c.ok]
    if not failed_required:
        return PreflightResult(
            status=PreflightStatus.READY.value,
            checks=checks,
            limitations=list(limitations or []),
            safe_to_run=True,
            capability_id=capability_id,
            message="Preflight READY — pipelines canônicos podem executar.",
        )
    # Classify first failure
    names = " ".join(c.name for c in failed_required)
    if "env:" in names or "module:" in names or "driver" in names.lower():
        status = PreflightStatus.BLOCKED_CONFIG.value
    elif "postgres" in names or "external" in names:
        # postgres connectivity without env missing → external/data
        if any(c.name.startswith("env:") for c in failed_required):
            status = PreflightStatus.BLOCKED_CONFIG.value
        else:
            status = PreflightStatus.BLOCKED_EXTERNAL.value
    elif "dir:" in names or "permission" in names:
        status = PreflightStatus.BLOCKED_PERMISSION.value
    elif "data" in names or "table" in names or "freshness" in names:
        status = PreflightStatus.BLOCKED_DATA.value
    else:
        status = PreflightStatus.BLOCKED_CONFIG.value
    msg = "; ".join(f"{c.name}: {c.detail}" for c in failed_required[:5])
    return PreflightResult(
        status=status,
        checks=checks,
        limitations=list(limitations or []) + [f"Bloqueado: {msg}"],
        safe_to_run=False,
        capability_id=capability_id,
        message=f"{status}: {msg}",
    )


def discover_artifacts(root: Path, *, patterns: tuple[str, ...] = ("**/*",)) -> list[Path]:
    """Discover generated files under root (files only, skip huge dirs)."""
    found: list[Path] = []
    if not root.exists():
        return found
    skip_names = {".cc_write_probe", "__pycache__"}
    for pat in patterns:
        for p in root.glob(pat):
            if not p.is_file():
                continue
            if p.name in skip_names:
                continue
            if p.suffix.lower() in {".pyc", ".pyo"}:
                continue
            # skip very large blobs (>50MB) from auto-discovery listing
            try:
                if p.stat().st_size > 50 * 1024 * 1024:
                    continue
            except OSError:
                continue
            found.append(p)
    # unique preserve order
    seen: set[str] = set()
    out: list[Path] = []
    for p in found:
        key = str(p.resolve())
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def write_adapter_logs(out_dir: Path, result: SubprocessResult) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stdout_p = out_dir / "adapter-stdout.log"
    stderr_p = out_dir / "adapter-stderr.log"
    stdout_p.write_text(result.stdout[-500_000:], encoding="utf-8")
    stderr_p.write_text(result.stderr[-500_000:], encoding="utf-8")
    return stdout_p, stderr_p


def write_run_meta(out_dir: Path, payload: dict[str, Any]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "adapter-run.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


class PipelineAdapter(Protocol):
    workflow_id: str
    capability_id: str

    def preflight(self, params: dict[str, Any], *, out_dir: Path) -> PreflightResult: ...

    def build_argv(self, params: dict[str, Any], *, out_dir: Path) -> list[str]: ...

    def interpret(
        self,
        params: dict[str, Any],
        *,
        out_dir: Path,
        proc: SubprocessResult,
        preflight: PreflightResult,
    ) -> AdapterResult: ...


def run_real_adapter(
    adapter: PipelineAdapter,
    params: dict[str, Any],
    *,
    out_dir: Path,
    exec_fn: ExecFn | None = None,
    timeout_sec: int = 3600,
) -> AdapterResult:
    """Execute REAL pipeline via adapter. Fail closed on blocked preflight — never fixture."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pf = adapter.preflight(params, out_dir=out_dir)
    if not pf.safe_to_run:
        raise AdapterBlockedError(pf)

    argv = assert_argv_list(adapter.build_argv(params, out_dir=out_dir))
    runner = exec_fn or (
        lambda a, cwd, env: default_exec(a, cwd, env, timeout_sec=timeout_sec)
    )
    proc = runner(argv, REPO_ROOT, None)
    write_adapter_logs(out_dir, proc)
    result = adapter.interpret(params, out_dir=out_dir, proc=proc, preflight=pf)
    result.data_mode = DataMode.REAL.value
    result.code_sha = result.code_sha or git_sha()
    result.params_public = public_params(params)
    write_run_meta(
        out_dir,
        {
            "data_mode": DataMode.REAL.value,
            "capability_id": adapter.capability_id,
            "workflow_id": adapter.workflow_id,
            "argv": argv,
            "exit_code": result.exit_code,
            "status": result.status,
            "code_sha": result.code_sha,
            "params": result.params_public,
            "preflight": pf.to_dict(),
            "started_at": result.started_at,
            "finished_at": result.finished_at,
            "limitations": result.limitations,
            "no_auto_outreach": True,
            "no_auto_dod_accept": True,
        },
    )
    return result
