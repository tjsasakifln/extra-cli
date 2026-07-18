#!/usr/bin/env python3
"""Load integration mode (main-direct vs branch-pr)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

SCRIPT_DIR = Path(__file__).resolve().parent
SQUAD_DIR = SCRIPT_DIR.parent
CONFIG_PATH = SQUAD_DIR / "config" / "integration-mode.yaml"


def load_integration_mode(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or CONFIG_PATH
    if not cfg_path.is_file():
        return {"version": "1.0.0", "mode": "branch-pr"}
    text = cfg_path.read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(text) or {}
        if isinstance(data, dict):
            return data
        return {"version": "1.0.0", "mode": "branch-pr"}
    # minimal fallback parser for mode: line
    mode = "branch-pr"
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("mode:"):
            mode = s.split(":", 1)[1].strip().strip("\"'")
            break
    return {"version": "1.0.0", "mode": mode}


def is_main_direct(path: Path | None = None) -> bool:
    return str(load_integration_mode(path).get("mode", "")).strip().lower() in {
        "main-direct",
        "main_direct",
        "maindirect",
    }
