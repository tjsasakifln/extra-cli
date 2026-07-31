"""Atomic activation, rollback, and load validation for registry releases."""

from __future__ import annotations

import json
import shutil
from typing import Any

from scripts.company_registry.lookup import lookup_cnpj
from scripts.company_registry.manifest import load_manifest, save_manifest, set_status, utc_now
from scripts.company_registry.models import ReleaseStatus
from scripts.company_registry.paths import (
    active_pointer_path,
    db_path_for_release,
    ensure_layout,
    releases_dir,
)
from scripts.company_registry.store import connect_db, count_table, set_meta


def validate_load(release_id: str, *, min_establishments: int = 1) -> dict[str, Any]:
    """Smoke + plausibility checks before ACTIVE."""
    staging = db_path_for_release(release_id, staging=True)
    final = db_path_for_release(release_id, staging=False)
    db = staging if staging.is_file() else final
    if not db.is_file():
        return {
            "ok": False,
            "release_id": release_id,
            "errors": ["database_missing"],
            "status": ReleaseStatus.FAILED.value,
        }
    conn = connect_db(db)
    try:
        n_est = count_table(conn, "establishments")
        n_co = count_table(conn, "companies")
        errors: list[str] = []
        if n_est < min_establishments:
            errors.append(f"establishments_below_min:{n_est}<{min_establishments}")
        # smoke: pick one row and lookup
        row = conn.execute("SELECT cnpj14 FROM establishments LIMIT 1").fetchone()
        smoke: dict[str, Any] = {}
        if row:
            cnpj = row["cnpj14"]
            # ensure join works
            joined = conn.execute(
                """
                SELECT e.cnpj14, c.razao_social FROM establishments e
                LEFT JOIN companies c ON c.cnpj_basico = e.cnpj_basico
                WHERE e.cnpj14 = ?
                """,
                (cnpj,),
            ).fetchone()
            smoke = {"cnpj14": cnpj, "has_row": joined is not None}
        else:
            errors.append("no_rows_for_smoke")
        ok = len(errors) == 0
        report = {
            "ok": ok,
            "release_id": release_id,
            "database_path": str(db),
            "row_counts": {"establishments": n_est, "companies": n_co},
            "smoke": smoke,
            "errors": errors,
            "status": ReleaseStatus.VALIDATING_LOAD.value if ok else ReleaseStatus.FAILED.value,
            "validated_at": utc_now(),
        }
        set_meta(conn, "validate_load", report)
        conn.commit()
        return report
    finally:
        conn.close()


def activate_release(
    release_id: str,
    *,
    min_establishments: int = 1,
    force: bool = False,
) -> dict[str, Any]:
    """Promote staging DB to releases/ and flip ACTIVE pointer atomically."""
    ensure_layout()
    manifest = load_manifest(release_id)
    if not manifest:
        return {"ok": False, "errors": ["manifest_missing"], "release_id": release_id}

    # Fail closed: partial never activates
    if manifest.get("status") in {
        ReleaseStatus.FAILED.value,
        ReleaseStatus.QUARANTINED.value,
        ReleaseStatus.DOWNLOADING.value,
    } and not force:
        return {
            "ok": False,
            "errors": [f"cannot_activate_from_status:{manifest.get('status')}"],
            "release_id": release_id,
        }

    validation = validate_load(release_id, min_establishments=min_establishments)
    if not validation["ok"]:
        set_status(manifest, ReleaseStatus.FAILED.value, error="validate_load_failed")
        manifest["validate_load"] = validation
        save_manifest(manifest)
        return {"ok": False, "validation": validation, "release_id": release_id}

    staging = db_path_for_release(release_id, staging=True)
    final_dir = releases_dir() / release_id
    final_dir.mkdir(parents=True, exist_ok=True)
    final_db = final_dir / "registry.sqlite"
    if staging.is_file():
        # copy then atomic replace
        tmp = final_db.with_suffix(".sqlite.tmp")
        shutil.copy2(staging, tmp)
        tmp.replace(final_db)
    elif not final_db.is_file():
        return {"ok": False, "errors": ["no_db_to_activate"], "release_id": release_id}

    previous = None
    ptr_path = active_pointer_path()
    if ptr_path.is_file():
        previous = json.loads(ptr_path.read_text(encoding="utf-8"))

    pointer = {
        "status": ReleaseStatus.ACTIVE.value,
        "release_id": release_id,
        "database_path": str(final_db),
        "database_snapshot_id": f"{release_id}:{final_db.stat().st_size}",
        "activated_at": utc_now(),
        "previous_release_id": (previous or {}).get("release_id"),
        "source_authority": manifest.get("source_authority", "RECEITA_FEDERAL"),
        "mode": manifest.get("mode") or manifest.get("ingestion_mode"),
        "sha256_manifest": manifest.get("sha256"),
        "code_commit": manifest.get("code_commit"),
    }
    tmp_ptr = ptr_path.with_suffix(".json.tmp")
    tmp_ptr.write_text(json.dumps(pointer, indent=2) + "\n", encoding="utf-8")
    tmp_ptr.replace(ptr_path)

    # mark previous as rolled-back recoverable (not deleted)
    if previous and previous.get("release_id") and previous.get("release_id") != release_id:
        prev_m = load_manifest(previous["release_id"])
        if prev_m and prev_m.get("status") == ReleaseStatus.ACTIVE.value:
            set_status(prev_m, ReleaseStatus.ROLLED_BACK.value)
            save_manifest(prev_m)

    set_status(manifest, ReleaseStatus.ACTIVE.value)
    manifest["database_snapshot_id"] = pointer["database_snapshot_id"]
    manifest["activated_at"] = pointer["activated_at"]
    manifest["validate_load"] = validation
    save_manifest(manifest)

    # smoke via public lookup API
    smoke_cnpj = (validation.get("smoke") or {}).get("cnpj14")
    smoke_lookup = None
    if smoke_cnpj:
        smoke_lookup = lookup_cnpj(smoke_cnpj).as_dict()

    return {
        "ok": True,
        "release_id": release_id,
        "status": ReleaseStatus.ACTIVE.value,
        "pointer": pointer,
        "previous": previous,
        "validation": validation,
        "smoke_lookup": smoke_lookup,
    }


def rollback_release(target_release_id: str | None = None) -> dict[str, Any]:
    """Restore previous ACTIVE release (or explicit target)."""
    ptr_path = active_pointer_path()
    if not ptr_path.is_file():
        return {"ok": False, "errors": ["no_active_pointer"]}
    current = json.loads(ptr_path.read_text(encoding="utf-8"))
    rid = target_release_id or current.get("previous_release_id")
    if not rid:
        return {"ok": False, "errors": ["no_previous_release"]}
    db = db_path_for_release(str(rid), staging=False)
    if not db.is_file():
        return {"ok": False, "errors": [f"previous_db_missing:{rid}"]}
    # re-activate without re-validation min (already was active)
    pointer = {
        "status": ReleaseStatus.ACTIVE.value,
        "release_id": rid,
        "database_path": str(db),
        "database_snapshot_id": f"{rid}:{db.stat().st_size}",
        "activated_at": utc_now(),
        "previous_release_id": current.get("release_id"),
        "rolled_back_from": current.get("release_id"),
        "source_authority": "RECEITA_FEDERAL",
    }
    tmp_ptr = ptr_path.with_suffix(".json.tmp")
    tmp_ptr.write_text(json.dumps(pointer, indent=2) + "\n", encoding="utf-8")
    tmp_ptr.replace(ptr_path)

    cur_m = load_manifest(str(current.get("release_id")))
    if cur_m:
        set_status(cur_m, ReleaseStatus.ROLLED_BACK.value)
        save_manifest(cur_m)
    tgt = load_manifest(str(rid))
    if tgt:
        set_status(tgt, ReleaseStatus.ACTIVE.value)
        save_manifest(tgt)
    return {"ok": True, "active_release_id": rid, "pointer": pointer, "from": current.get("release_id")}
