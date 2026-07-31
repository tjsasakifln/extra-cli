"""Correction → regenerate deliverable version without erasing decision history."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.command_center.run_manifest import sha256_file
from scripts.command_center.workflows.runner import run_workflow


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def apply_corrections_to_source(
    source_path: Path,
    corrections: list[dict[str, Any]],
) -> Path:
    """Apply field patches to a source JSON file; write sibling corrected version.

    corrections: [{item_key|id|cnpj|orgao: ..., fields: {k:v}, note?: str}]
    """
    data = json.loads(source_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]]
    wrapper_key: str | None = None
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        for key in ("companies", "opportunities", "items", "rows", "leads", "documents"):
            if isinstance(data.get(key), list):
                rows = data[key]
                wrapper_key = key
                break
        else:
            raise ValueError("Fonte JSON sem lista de registros reconhecível")
    else:
        raise ValueError("Fonte JSON inválida")

    def match_key(row: dict[str, Any], corr: dict[str, Any]) -> bool:
        for k in ("item_key", "id", "cnpj", "orgao", "nome", "key"):
            if corr.get(k) is not None and str(row.get(k) or row.get("id") or "") == str(corr.get(k)):
                return True
            if corr.get("item_key") and str(corr["item_key"]) in {
                str(row.get("id")),
                str(row.get("cnpj")),
                str(row.get("orgao")),
            }:
                return True
        return False

    applied = 0
    for corr in corrections:
        fields = corr.get("fields") or {}
        if not isinstance(fields, dict):
            continue
        for row in rows:
            if match_key(row, corr):
                for fk, fv in fields.items():
                    row[fk] = fv
                row["_human_correction"] = {
                    "note": corr.get("note") or corr.get("rationale") or "",
                    "at": _utcnow(),
                }
                applied += 1
                break
    if applied == 0:
        raise ValueError("Nenhuma correção casou com registros da fonte")

    out = source_path.parent / f"{source_path.stem}.corrected{source_path.suffix}"
    if wrapper_key:
        data[wrapper_key] = rows
        data["_corrections_applied"] = corrections
        data["_corrected_at"] = _utcnow()
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        payload = {"rows": rows, "_corrections_applied": corrections, "_corrected_at": _utcnow()}
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def regenerate_workflow_version(
    *,
    workflow_id: str,
    params: dict[str, Any],
    out_dir: Path,
    code_sha: str | None,
    job_id: str | None,
    parent_run_id: str | None,
    corrections: list[dict[str, Any]] | None = None,
    prior_source: Path | None = None,
) -> dict[str, Any]:
    """Create a new deliverable version; optionally apply corrections first.

    History: prior decision rows remain in SQLite; new run_id/version in new out_dir.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # seed prior source into out_dir if provided so runner can be extended later
    if prior_source and prior_source.is_file():
        dest = out_dir / prior_source.name
        shutil.copy2(prior_source, dest)
        if corrections:
            apply_corrections_to_source(dest, corrections)

    # Always fixture-backed for guided workflows (honest)
    params = {**params, "use_fixture": True}
    result = run_workflow(
        workflow_id,
        params,
        out_dir=out_dir,
        code_sha=code_sha,
        job_id=job_id,
    )
    # annotate version lineage in manifest
    man_path = Path(result["manifest_path"])
    mf = json.loads(man_path.read_text(encoding="utf-8"))
    mf["parent_run_id"] = parent_run_id
    mf["version_note"] = "regenerated_after_human_correction" if corrections else "rerun"
    mf["corrections"] = corrections or []
    mf["generated_at"] = _utcnow()
    man_path.write_text(json.dumps(mf, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    result["manifest"] = mf
    result["parent_run_id"] = parent_run_id
    result["content_hashes"] = {
        "manifest": sha256_file(man_path),
    }
    # primary source hash if present
    for name in ("opportunities.json", "suppliers.json", "public_agencies.json", "documents-index.json"):
        p = out_dir / name
        if p.is_file():
            result["content_hashes"]["source"] = sha256_file(p)
            break
    # write version meta for compare UI
    meta = {
        "parent_run_id": parent_run_id,
        "run_id": result.get("run_id"),
        "corrections": corrections or [],
        "at": _utcnow(),
        "hashes": result["content_hashes"],
    }
    (out_dir / "version-meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    result["version_meta_path"] = str(out_dir / "version-meta.json")
    return result
