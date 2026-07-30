"""Fail-closed commercial precheck gates beyond ACTIVE pointer only."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.company_registry.activate import activate_release
from scripts.company_registry.commercial_bridge import fail_closed_commercial_precheck
from scripts.company_registry.loader import load_zip_into_db
from scripts.company_registry.manifest import new_manifest, save_manifest, set_status
from scripts.company_registry.models import ReleaseStatus
from scripts.company_registry.paths import db_path_for_release, ensure_layout

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "fixtures" / "company_registry"


@pytest.fixture()
def reg_root(tmp_path, monkeypatch):
    root = tmp_path / "company_registry"
    monkeypatch.setenv("COMPANY_REGISTRY_ROOT", str(root))
    ensure_layout()
    return root


def _activate_fixture(reg_root: Path, release_id: str = "rfb-gate-fix") -> str:
    raw = reg_root / "raw" / release_id
    raw.mkdir(parents=True)
    shutil.copy2(FIX / "Estabelecimentos0.zip", raw / "Estabelecimentos0.zip")
    shutil.copy2(FIX / "Empresas0.zip", raw / "Empresas0.zip")
    m = new_manifest(release_id)
    set_status(m, ReleaseStatus.DOWNLOADED.value)
    save_manifest(m)
    db = db_path_for_release(release_id, staging=True)
    load_zip_into_db(raw / "Estabelecimentos0.zip", db, kind_hint="estabelecimentos")
    load_zip_into_db(raw / "Empresas0.zip", db, kind_hint="empresas")
    assert activate_release(release_id)["ok"]
    return release_id


def test_precheck_fails_without_active(reg_root):
    r = fail_closed_commercial_precheck()
    assert not r["ok"]
    assert r["reason"] == "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE"


def test_precheck_active_only_passes_without_candidate_lists(reg_root):
    _activate_fixture(reg_root)
    r = fail_closed_commercial_precheck()
    assert r["ok"]
    assert r["checks"]["load_non_empty"]


def test_precheck_fails_low_coverage_and_top20(reg_root):
    _activate_fixture(reg_root)
    meta = json.loads((FIX / "meta.json").read_text(encoding="utf-8"))
    candidates = meta["cnpjs"] + ["19131243000197"]
    r = fail_closed_commercial_precheck(
        candidates=candidates,
        top20=meta["cnpjs"][:2] + ["19131243000197"],
        min_official_match=0.995,
        min_usable=0.98,
        require_top20_full=True,
    )
    assert not r["ok"]
    assert r.get("errors")
    assert any("OFFICIAL_MATCH" in e or "TOP20" in e for e in r["errors"])


def test_precheck_passes_full_gates_on_fixture_universe(reg_root):
    _activate_fixture(reg_root)
    meta = json.loads((FIX / "meta.json").read_text(encoding="utf-8"))
    usable = meta["cnpjs"][:2]
    r = fail_closed_commercial_precheck(
        candidates=usable,
        top20=usable,
        min_official_match=0.995,
        min_usable=0.98,
        require_top20_full=True,
    )
    assert r["ok"], r
    assert r["coverage"]["metrics"]["official_match_coverage"] == 1.0
    assert r["coverage"]["metrics"]["top20_official_registry_coverage"] == 1.0
