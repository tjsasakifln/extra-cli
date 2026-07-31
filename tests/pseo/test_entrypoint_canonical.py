"""Documented entrypoint must remain importable and equivalent.

Canonical: python -m scripts.pseo.export_web_cfg
Aliases (if present) must resolve to the same pipeline main.
"""

from __future__ import annotations

import importlib
import runpy
from pathlib import Path


def test_export_web_cfg_module_importable():
    mod = importlib.import_module("scripts.pseo.export_web_cfg")
    assert hasattr(mod, "main")
    assert callable(mod.main)


def test_export_web_cfg_file_exists():
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "pseo" / "export_web_cfg.py"
    assert path.is_file(), "documented entrypoint scripts/pseo/export_web_cfg.py missing"


def test_pipeline_main_is_shared():
    export_mod = importlib.import_module("scripts.pseo.export_web_cfg")
    pipeline = importlib.import_module("scripts.pseo.pipeline")
    # export_web_cfg must delegate to pipeline.main (single canonical path)
    assert export_mod.main is pipeline.main


def test_module_run_entrypoint_resolves():
    """python -m scripts.pseo.export_web_cfg must not raise ImportError at load."""
    # runpy.run_module would execute main; only load the module code path
    mod = importlib.import_module("scripts.pseo.export_web_cfg")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "pipeline" in src
    assert "main" in src
