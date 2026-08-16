"""MIDES BigQuery bounded public query (#266)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from scripts.complementary.contract import RunResult, sha256_json

SOURCE = "mides_bigquery"
DEFAULT_BUDGET_BYTES = 100 * 1024 * 1024 * 1024
CREDENTIAL_ENV = "GOOGLE_APPLICATION_CREDENTIALS"


def credential_status(env: dict[str, str] | None = None) -> dict[str, Any]:
    environ = env if env is not None else os.environ
    path = (environ.get(CREDENTIAL_ENV) or "").strip()
    if not path:
        return {"ok": False, "terminal": "BLOCKED", "reason": "missing_GOOGLE_APPLICATION_CREDENTIALS"}
    if not Path(path).is_file():
        return {"ok": False, "terminal": "BLOCKED", "reason": "credential_file_absent"}
    return {"ok": True, "terminal": "success", "path_set": True, "path_name": Path(path).name}


def enforce_budget(estimated_bytes: int | None, budget_bytes: int = DEFAULT_BUDGET_BYTES) -> str | None:
    if estimated_bytes is None or int(estimated_bytes) <= 0:
        return "unlimited_or_unknown_bytes"
    if int(estimated_bytes) > budget_bytes:
        return f"budget_exceeded:{estimated_bytes}>{budget_bytes}"
    return None


def redact_secrets(text: str, env: dict[str, str] | None = None) -> str:
    environ = env if env is not None else os.environ
    secret = (environ.get(CREDENTIAL_ENV) or "").strip()
    out = text
    if secret:
        out = out.replace(secret, "[REDACTED_CREDENTIAL_PATH]")
    return out


def run_bounded_job(
    *,
    interval: str,
    estimated_bytes: int | None,
    rows: list[dict[str, Any]],
    job_id: str | None = None,
    env: dict[str, str] | None = None,
    budget_bytes: int = DEFAULT_BUDGET_BYTES,
) -> RunResult:
    creds = credential_status(env)
    if not creds["ok"]:
        return RunResult(SOURCE, "BLOCKED", 0, 0, 0, 0, reason=creds["reason"], job=creds)
    budget_err = enforce_budget(estimated_bytes, budget_bytes)
    if budget_err:
        return RunResult(SOURCE, "BLOCKED", 0, 0, 0, 0, reason=budget_err)
    payload = {
        "interval": interval,
        "rows": rows,
        "estimated_bytes": estimated_bytes,
    }
    job = {
        "job_id": job_id or "fixture-job",
        "interval": interval,
        "estimated_bytes": estimated_bytes,
        "estimated_cost_usd": round((estimated_bytes or 0) / (1024**4) * 5.0, 6),
        "n_rows": len(rows),
        "hash": sha256_json(payload),
        "source": SOURCE,
        "freshness_sla_hours": 48,
    }
    return RunResult(
        SOURCE,
        "success" if rows else "ZERO_CONFIRMED",
        fetched=len(rows),
        persisted=len(rows),
        deduplicated=0,
        failed=0,
        records=rows,
        job=job,
    )
