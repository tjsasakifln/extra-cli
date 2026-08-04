"""Resume/checkpoint helpers for reajuste pipeline (idempotent restarts)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CHECKPOINT_NAME = "checkpoint.json"
RAW_BATCHES_DIR = "checkpoint_raw"
CLASSIFIED_NAME = "checkpoint_classified.jsonl"
PARAMS_NAME = "checkpoint_params.json"


def checkpoint_dir(run_dir: Path) -> Path:
    d = run_dir / ".checkpoint"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_params(run_dir: Path, params: dict[str, Any]) -> Path:
    p = checkpoint_dir(run_dir) / PARAMS_NAME
    p.write_text(json.dumps(params, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return p


def load_params(run_dir: Path) -> dict[str, Any] | None:
    p = checkpoint_dir(run_dir) / PARAMS_NAME
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save_raw_rows(run_dir: Path, rows: list[dict[str, Any]]) -> Path:
    p = checkpoint_dir(run_dir) / "raw_rows.json"
    p.write_text(json.dumps(rows, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    _write_stage(run_dir, "raw_fetched", {"n": len(rows)})
    return p


def load_raw_rows(run_dir: Path) -> list[dict[str, Any]] | None:
    p = checkpoint_dir(run_dir) / "raw_rows.json"
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else None


def append_classified(run_dir: Path, lead: dict[str, Any]) -> None:
    p = checkpoint_dir(run_dir) / CLASSIFIED_NAME
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(lead, ensure_ascii=False, default=str) + "\n")


def load_classified(run_dir: Path) -> list[dict[str, Any]]:
    p = checkpoint_dir(run_dir) / CLASSIFIED_NAME
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        out.append(json.loads(line))
    return out


def classified_keys(run_dir: Path) -> set[str]:
    keys: set[str] = set()
    for lead in load_classified(run_dir):
        k = lead.get("dedupe_key") or lead.get("contrato_id")
        if k:
            keys.add(str(k))
    return keys


def clear_classified(run_dir: Path) -> None:
    p = checkpoint_dir(run_dir) / CLASSIFIED_NAME
    if p.exists():
        p.unlink()


def _write_stage(run_dir: Path, stage: str, payload: dict[str, Any]) -> None:
    p = checkpoint_dir(run_dir) / CHECKPOINT_NAME
    state: dict[str, Any] = {}
    if p.exists():
        try:
            state = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
    state["stage"] = stage
    state.update(payload)
    p.write_text(json.dumps(state, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def load_stage(run_dir: Path) -> dict[str, Any]:
    p = checkpoint_dir(run_dir) / CHECKPOINT_NAME
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def mark_stage(run_dir: Path, stage: str, **payload: Any) -> None:
    _write_stage(run_dir, stage, payload)
