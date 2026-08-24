"""Health checks for the official company registry mirror."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from typing import Any

from scripts.company_registry.lookup import lookup_cnpj, read_active_pointer
from scripts.company_registry.manifest import load_manifest
from scripts.company_registry.models import OfficialMatchStatus
from scripts.company_registry.paths import ensure_layout, registry_root
from scripts.company_registry.store import connect_db, count_table


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def health_report(*, smoke_cnpj: str | None = None) -> dict[str, Any]:
    layout = ensure_layout()
    root = registry_root()
    usage = shutil.disk_usage(str(root))
    ptr = read_active_pointer()
    errors: list[str] = []
    warnings: list[str] = []

    if not ptr:
        errors.append("no_active_release")
    elif ptr.get("status") != "ACTIVE":
        errors.append(f"pointer_status:{ptr.get('status')}")

    db_ok = False
    counts = {}
    if ptr and ptr.get("database_path"):
        from pathlib import Path

        dbp = Path(ptr["database_path"])
        if dbp.is_file():
            conn = connect_db(dbp, readonly=True)
            try:
                counts = {
                    "establishments": count_table(conn, "establishments"),
                    "companies": count_table(conn, "companies"),
                }
                db_ok = counts["establishments"] > 0
            finally:
                conn.close()
        else:
            errors.append("active_db_missing")

    smoke = None
    if smoke_cnpj:
        rec = lookup_cnpj(smoke_cnpj)
        smoke = rec.as_dict()
        if rec.official_match_status == OfficialMatchStatus.OFFICIAL_REGISTRY_UNAVAILABLE.value:
            errors.append("lookup_unavailable")

    free_gb = usage.free / 1e9
    if free_gb < 5:
        warnings.append(f"low_disk_free_gb:{free_gb:.2f}")
    if free_gb < 1:
        errors.append(f"critical_disk_free_gb:{free_gb:.2f}")

    rid = (ptr or {}).get("release_id")
    manifest = load_manifest(str(rid)) if rid else None

    return {
        "ok": len(errors) == 0 and db_ok,
        "generated_at": utc_now(),
        "layout": layout,
        "active_pointer": ptr,
        "manifest_status": (manifest or {}).get("status"),
        "row_counts": counts,
        "disk": {
            "root": str(root),
            "total_gb": round(usage.total / 1e9, 2),
            "used_gb": round(usage.used / 1e9, 2),
            "free_gb": round(free_gb, 2),
        },
        "smoke_lookup": smoke,
        "errors": errors,
        "warnings": warnings,
    }
