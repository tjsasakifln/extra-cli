"""Compare two run manifests / source datasets for consulting workbench."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _rows_from_source(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        for key in (
            "companies",
            "opportunities",
            "items",
            "rows",
            "leads",
            "documents",
            "records",
            "data",
        ):
            val = data.get(key)
            if isinstance(val, list) and val and isinstance(val[0], dict):
                return [r for r in val if isinstance(r, dict)]
        # single-level dict of id -> row
        if all(isinstance(v, dict) for v in data.values()):
            return list(data.values())  # type: ignore[arg-type]
    return []


def _item_key(row: dict[str, Any]) -> str:
    for k in ("id", "cnpj", "orgao", "nome", "processo_id", "item_key", "key"):
        if row.get(k) not in (None, ""):
            return f"{k}:{row[k]}"
    # stable-ish fallback
    return json.dumps(row, sort_keys=True, ensure_ascii=False)[:200]


def compare_row_sets(
    previous: list[dict[str, Any]],
    current: list[dict[str, Any]],
    *,
    score_field: str = "score",
) -> dict[str, Any]:
    prev_map = {_item_key(r): r for r in previous}
    curr_map = {_item_key(r): r for r in current}
    prev_keys = set(prev_map)
    curr_keys = set(curr_map)

    added = [curr_map[k] for k in sorted(curr_keys - prev_keys)]
    removed = [prev_map[k] for k in sorted(prev_keys - curr_keys)]
    common = prev_keys & curr_keys

    changed: list[dict[str, Any]] = []
    score_up: list[dict[str, Any]] = []
    score_down: list[dict[str, Any]] = []
    for k in sorted(common):
        a, b = prev_map[k], curr_map[k]
        if a != b:
            entry = {"key": k, "before": a, "after": b, "fields": []}
            fields = sorted(set(a) | set(b))
            for f in fields:
                if a.get(f) != b.get(f):
                    entry["fields"].append({"field": f, "before": a.get(f), "after": b.get(f)})
            changed.append(entry)
            if score_field in a or score_field in b:
                try:
                    sa = float(a.get(score_field) if a.get(score_field) is not None else 0)
                    sb = float(b.get(score_field) if b.get(score_field) is not None else 0)
                    if sb > sa:
                        score_up.append({"key": k, "before": sa, "after": sb})
                    elif sb < sa:
                        score_down.append({"key": k, "before": sa, "after": sb})
                except (TypeError, ValueError):
                    pass

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "score_increased": score_up,
        "score_decreased": score_down,
        "counts": {
            "previous": len(previous),
            "current": len(current),
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
        },
    }


def compare_manifests(prev_path: Path, curr_path: Path) -> dict[str, Any]:
    """Compare two run-manifest.json files and their linked source datasets when present."""
    prev_mf = _load_json(prev_path)
    curr_mf = _load_json(curr_path)
    if not isinstance(prev_mf, dict) or not isinstance(curr_mf, dict):
        raise ValueError("Manifests must be JSON objects")

    prev_arts = {a.get("logical_name"): a for a in (prev_mf.get("artifacts") or []) if isinstance(a, dict)}
    curr_arts = {a.get("logical_name"): a for a in (curr_mf.get("artifacts") or []) if isinstance(a, dict)}
    art_added = sorted(set(curr_arts) - set(prev_arts))
    art_removed = sorted(set(prev_arts) - set(curr_arts))
    art_changed = []
    for name in sorted(set(prev_arts) & set(curr_arts)):
        if prev_arts[name].get("sha256") and curr_arts[name].get("sha256"):
            if prev_arts[name]["sha256"] != curr_arts[name]["sha256"]:
                art_changed.append(
                    {
                        "logical_name": name,
                        "before_sha": prev_arts[name]["sha256"],
                        "after_sha": curr_arts[name]["sha256"],
                    }
                )

    coverage_delta = {
        "previous": prev_mf.get("coverage") or {},
        "current": curr_mf.get("coverage") or {},
        "changed": (prev_mf.get("coverage") or {}) != (curr_mf.get("coverage") or {}),
    }

    # Try to load source_data JSON siblings for row-level diff
    row_diff: dict[str, Any] | None = None
    for candidate_names in (
        ("opportunities.json", "opportunities.json"),
        ("suppliers.json", "suppliers.json"),
        ("public_agencies.json", "public_agencies.json"),
        ("documents-index.json", "documents-index.json"),
    ):
        p_src = prev_path.parent / candidate_names[0]
        c_src = curr_path.parent / candidate_names[1]
        if p_src.is_file() and c_src.is_file():
            score_field = "score"
            if "opportunities" in candidate_names[0]:
                score_field = "aderencia_perfil"
            row_diff = compare_row_sets(
                _rows_from_source(_load_json(p_src)),
                _rows_from_source(_load_json(c_src)),
                score_field=score_field,
            )
            row_diff["source_files"] = {"previous": str(p_src), "current": str(c_src)}
            break

    blockers_prev = set(prev_mf.get("blockers") or [])
    blockers_curr = set(curr_mf.get("blockers") or [])

    return {
        "previous_run_id": prev_mf.get("run_id"),
        "current_run_id": curr_mf.get("run_id"),
        "workflow_id": curr_mf.get("workflow_id") or prev_mf.get("workflow_id"),
        "artifacts": {
            "added": art_added,
            "removed": art_removed,
            "changed": art_changed,
        },
        "coverage": coverage_delta,
        "blockers": {
            "new": sorted(blockers_curr - blockers_prev),
            "resolved": sorted(blockers_prev - blockers_curr),
        },
        "limitations_current": curr_mf.get("limitations") or [],
        "rows": row_diff,
        "summary": _human_summary(art_added, art_removed, art_changed, row_diff, coverage_delta),
    }


def _human_summary(
    art_added: list[str],
    art_removed: list[str],
    art_changed: list[dict[str, Any]],
    row_diff: dict[str, Any] | None,
    coverage_delta: dict[str, Any],
) -> str:
    parts: list[str] = []
    if row_diff:
        c = row_diff["counts"]
        parts.append(
            f"Itens: +{c['added']} novos, −{c['removed']} removidos, {c['changed']} alterados "
            f"(antes {c['previous']}, agora {c['current']})."
        )
        if row_diff.get("score_increased"):
            parts.append(f"Score/aderência subiu em {len(row_diff['score_increased'])} item(ns).")
        if row_diff.get("score_decreased"):
            parts.append(f"Score/aderência caiu em {len(row_diff['score_decreased'])} item(ns).")
    if art_added or art_removed or art_changed:
        parts.append(
            f"Artefatos: +{len(art_added)} · −{len(art_removed)} · {len(art_changed)} com hash diferente."
        )
    if coverage_delta.get("changed"):
        parts.append("Cobertura mudou entre as execuções.")
    if not parts:
        return "Nenhuma diferença material detectada entre as duas execuções."
    return " ".join(parts)


def find_previous_manifest(
    *,
    workflow_id: str | None,
    current_manifest: Path,
    jobs_dir: Path,
) -> Path | None:
    """Find the most recent prior run-manifest for the same workflow under jobs_dir."""
    current_manifest = current_manifest.resolve()
    candidates: list[tuple[float, Path]] = []
    if not jobs_dir.is_dir():
        return None
    for mf in jobs_dir.rglob("run-manifest.json"):
        try:
            if mf.resolve() == current_manifest:
                continue
            data = _load_json(mf)
            if workflow_id and data.get("workflow_id") != workflow_id and data.get("capability_id") != workflow_id:
                continue
            mtime = mf.stat().st_mtime
            candidates.append((mtime, mf))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]
