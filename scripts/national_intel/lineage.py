"""JSON product envelope + claim class helpers."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


CLAIM_LEGEND = {
    "fact": "Directly observed from contract rows (counts, UF set, sums).",
    "indicator": "Derived statistic (percentiles, shares, modes); not a legal finding.",
    "hypothesis": "Business inference requiring human validation; not proven relationship.",
}


def git_sha(root: Path | None = None) -> str | None:
    try:
        cwd = str(root or Path.cwd())
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None


def mask_dsn(dsn: str | None) -> str:
    if not dsn:
        return "unset"
    # postgresql://user:pass@host:port/db → postgresql://***@host:port/db
    if "@" in dsn and "://" in dsn:
        scheme, rest = dsn.split("://", 1)
        creds, hostpart = rest.split("@", 1)
        return f"{scheme}://***@{hostpart}"
    return "***"


def envelope(
    *,
    product_id: str,
    scope_label: str,
    filters: dict[str, Any],
    rows: list[dict[str, Any]],
    limitations: list[str],
    dsn: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "product_id": product_id,
        "scope_label": scope_label,
        "as_of": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "filters": filters,
        "row_count": len(rows),
        "limitations": limitations,
        "claim_class_legend": CLAIM_LEGEND,
        "lineage": {
            "git_sha": git_sha(),
            "dsn_host_port_masked": mask_dsn(dsn or os.environ.get("NATIONAL_INTEL_DSN")),
            "query_id": product_id,
            "module_version": "0.1.0",
        },
        "rows": rows,
    }
    if extra:
        body.update(extra)
    return body


def write_json(path: Path | str | None, data: dict[str, Any]) -> None:
    if not path:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
