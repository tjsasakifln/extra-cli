"""End-to-end refresh orchestration for official registry releases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.company_registry.activate import activate_release, validate_load
from scripts.company_registry.diff import diff_releases
from scripts.company_registry.downloader import download_file
from scripts.company_registry.loader import load_jsonl_selective, load_zip_into_db
from scripts.company_registry.locks import RegistryLock
from scripts.company_registry.lookup import read_active_pointer
from scripts.company_registry.manifest import load_manifest, new_manifest, save_manifest, set_status, utc_now
from scripts.company_registry.models import ReleaseStatus
from scripts.company_registry.paths import db_path_for_release, ensure_layout, raw_dir
from scripts.company_registry.release_discovery import discover_release


def refresh(
    *,
    force: bool = False,
    interest_cnpjs: list[str] | None = None,
    jsonl_path: str | Path | None = None,
    local_raw_dir: str | Path | None = None,
    max_workers: int = 2,
    source_label: str = "rfb_public_cadastral",
) -> dict[str, Any]:
    """Discover → download/load → validate → activate. No auto-outreach.

    Modes:
    - bulk: from RFB open-data discovery + ZIPs
    - local_raw: operator-staged ZIPs under raw/<release_id>/
    - selective_jsonl: pre-normalized JSONL of interest CNPJs
    """
    ensure_layout()
    with RegistryLock("refresh"):
        active = read_active_pointer()
        discovery = discover_release()
        release_id = discovery.get("release_id") or f"rfb-cnpj-local-{utc_now()[:10]}"

        if (
            not force
            and active
            and active.get("status") == "ACTIVE"
            and active.get("release_id") == release_id
            and not jsonl_path
            and not local_raw_dir
        ):
            return {
                "ok": True,
                "noop": True,
                "reason": "release_already_active",
                "release_id": release_id,
                "active": active,
            }

        # Prefer staged local raw / jsonl when discovery failed
        if discovery.get("status") == "FAILED" and not jsonl_path and not local_raw_dir:
            # auto-detect staged raw folders
            raw_root = raw_dir()
            staged = sorted([p for p in raw_root.iterdir() if p.is_dir()]) if raw_root.is_dir() else []
            if staged:
                local_raw_dir = staged[-1]
                release_id = local_raw_dir.name
            else:
                return {
                    "ok": False,
                    "status": "FAILED",
                    "errors": discovery.get("errors") or ["discovery_failed"],
                    "warnings": discovery.get("warnings"),
                    "hint": (
                        "Stage RFB ZIPs in data/company_registry/raw/<release_id>/ "
                        "or provide --jsonl for selective interest mode."
                    ),
                    "discovery": discovery,
                }

        if jsonl_path:
            release_id = release_id if release_id.startswith("rfb") else f"selective-{utc_now()[:10]}"
            if Path(str(jsonl_path)).name:
                release_id = f"selective-{Path(str(jsonl_path)).stem}"[:80]
            manifest = new_manifest(
                release_id,
                mode="selective",
                ingestion_mode="selective_jsonl",
                source_authority="RECEITA_FEDERAL",
            )
            set_status(manifest, ReleaseStatus.LOADING.value)
            manifest["source_urls"] = [f"file:{jsonl_path}"]
            manifest["warnings"].append(
                "Selective JSONL mode — bulk RFB completeness is NOT claimed."
            )
            # if redistributor lineage
            if "opencnpj" in source_label.lower():
                manifest["warnings"].append(
                    "source_label indicates RFB public data via redistributor; "
                    "not a private CRM API as authority, but not direct bulk RFB zip either."
                )
            save_manifest(manifest)
            db = db_path_for_release(release_id, staging=True)
            if db.exists():
                db.unlink()
            load_res = load_jsonl_selective(jsonl_path, db, source_label=source_label)
            manifest["row_counts"] = load_res.get("db_counts") or {}
            manifest["load_started_at"] = utc_now()
            manifest["load_finished_at"] = utc_now()
            if not load_res.get("ok"):
                set_status(manifest, ReleaseStatus.FAILED.value, error="jsonl_load_failed")
                save_manifest(manifest)
                return {"ok": False, "load": load_res, "manifest": manifest}
            set_status(manifest, ReleaseStatus.VALIDATING_LOAD.value)
            save_manifest(manifest)
            act = activate_release(release_id, min_establishments=1)
            prev = (active or {}).get("release_id")
            d = (
                diff_releases(str(prev), release_id)
                if prev and prev != release_id
                else {"ok": True, "note": "no_previous"}
            )
            return {
                "ok": bool(act.get("ok")),
                "release_id": release_id,
                "mode": "selective_jsonl",
                "load": load_res,
                "activate": act,
                "diff": d,
                "manifest": load_manifest(release_id),
            }

        # ZIP path (discovered or local)
        files: list[dict[str, Any]] = []
        if local_raw_dir:
            release_id = Path(local_raw_dir).name
            manifest = new_manifest(
                release_id,
                mode="bulk" if not interest_cnpjs else "selective",
                ingestion_mode="local_raw_zip",
            )
            for z in sorted(Path(local_raw_dir).glob("*.zip")):
                files.append({"file_name": z.name, "url": None, "local_path": str(z), "kind": None})
            manifest["source_urls"] = [f"file:{local_raw_dir}"]
        else:
            manifest = discovery
            release_id = manifest["release_id"]
            files = (manifest.get("discovery") or {}).get("files") or []
            set_status(manifest, ReleaseStatus.DOWNLOADING.value)
            save_manifest(manifest)
            # download
            raw = raw_dir(release_id)
            raw.mkdir(parents=True, exist_ok=True)
            downloaded = []
            for f in files:
                dest = raw / f["file_name"]
                if f.get("url"):
                    res = download_file(f["url"], dest)
                    f["download"] = res
                    if res.get("ok"):
                        downloaded.append(f["file_name"])
                        manifest.setdefault("sha256", {})[f["file_name"]] = res.get("sha256")
                        manifest.setdefault("content_lengths", {})[f["file_name"]] = res.get(
                            "size_bytes"
                        )
                elif dest.is_file():
                    downloaded.append(f["file_name"])
            manifest["files_downloaded"] = downloaded
            if not downloaded:
                set_status(manifest, ReleaseStatus.FAILED.value, error="no_files_downloaded")
                save_manifest(manifest)
                return {"ok": False, "manifest": manifest, "errors": ["download_empty"]}
            set_status(manifest, ReleaseStatus.DOWNLOADED.value)
            save_manifest(manifest)
            files = [
                {
                    **f,
                    "local_path": str(raw_dir(release_id) / f["file_name"]),
                }
                for f in files
                if f["file_name"] in downloaded
            ]

        set_status(manifest, ReleaseStatus.LOADING.value)
        manifest["load_started_at"] = utc_now()
        save_manifest(manifest)
        db = db_path_for_release(release_id, staging=True)
        if db.exists():
            db.unlink()
        interest = set(interest_cnpjs) if interest_cnpjs else None
        roots = {c[:8] for c in interest} if interest else None
        load_reports = []
        for f in files:
            lp = Path(f.get("local_path") or raw_dir(release_id) / f["file_name"])
            if not lp.is_file():
                continue
            load_reports.append(
                load_zip_into_db(
                    lp,
                    db,
                    kind_hint=f.get("kind"),
                    interest_cnpjs=interest,
                    interest_roots=roots,
                )
            )
        manifest["load_finished_at"] = utc_now()
        manifest["row_counts"] = {
            "loads": [
                {"zip": r.get("zip"), "db_counts": r.get("db_counts"), "ok": r.get("ok")}
                for r in load_reports
            ]
        }
        if not any(r.get("ok") for r in load_reports):
            set_status(manifest, ReleaseStatus.FAILED.value, error="all_loads_failed")
            save_manifest(manifest)
            return {"ok": False, "loads": load_reports, "manifest": manifest}
        set_status(manifest, ReleaseStatus.VALIDATING_LOAD.value)
        save_manifest(manifest)
        act = activate_release(release_id, min_establishments=1)
        prev = (active or {}).get("release_id")
        d = (
            diff_releases(str(prev), release_id)
            if prev and prev != release_id
            else {"ok": True, "note": "no_previous"}
        )
        return {
            "ok": bool(act.get("ok")),
            "release_id": release_id,
            "mode": manifest.get("mode"),
            "loads": load_reports,
            "activate": act,
            "diff": d,
            "manifest": load_manifest(release_id),
            "discovery": discovery if not local_raw_dir else None,
        }
