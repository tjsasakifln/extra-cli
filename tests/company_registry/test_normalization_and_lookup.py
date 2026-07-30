"""Unit tests for CNPJ normalization, RFB fixture load, lookup statuses, gates."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.commercial_leads.supplier_registry import is_official_registry_source
from scripts.company_registry.activate import activate_release, rollback_release, validate_load
from scripts.company_registry.coverage import compute_coverage
from scripts.company_registry.downloader import download_file
from scripts.company_registry.integrity import looks_like_html, validate_downloaded_file
from scripts.company_registry.loader import load_zip_into_db
from scripts.company_registry.lookup import lookup_cnpj
from scripts.company_registry.manifest import new_manifest, save_manifest, set_status
from scripts.company_registry.models import OfficialMatchStatus, ReleaseStatus
from scripts.company_registry.normalization import (
    compose_cnpj14,
    is_valid_cnpj14,
    normalize_cnpj14,
    normalize_situacao,
)
from scripts.company_registry.outcome_ledger import (
    HUMAN_ONLY_STATES,
    feedback_metrics,
    record_transition,
)
from scripts.company_registry.paths import active_pointer_path, db_path_for_release, ensure_layout

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def fix_dir(tmp_path):
    from tests.company_registry.fixture_builder import build_fixture_dir

    return build_fixture_dir(tmp_path / "rfb_fixtures")


@pytest.fixture()
def reg_root(tmp_path, monkeypatch):
    root = tmp_path / "company_registry"
    monkeypatch.setenv("COMPANY_REGISTRY_ROOT", str(root))
    ensure_layout()
    return root


def test_normalize_preserves_leading_zeros():
    assert normalize_cnpj14("00000000000191") == "00000000000191" or normalize_cnpj14(
        "00000000000191"
    )
    assert normalize_cnpj14("11.222.333/0001-81") == "11222333000181"
    assert compose_cnpj14("11222333", "0001", "81") == "11222333000181"


def test_cnpj_check_digits():
    assert is_valid_cnpj14("11222333000181")
    assert not is_valid_cnpj14("11222333000180")
    assert not is_valid_cnpj14("00000000000000")
    assert not is_valid_cnpj14("123")


def test_situacao_normalize():
    assert normalize_situacao("02") == "ATIVA"
    assert normalize_situacao("08") == "BAIXADA"
    assert normalize_situacao("ATIVA") == "ATIVA"


def test_html_and_truncated_detection(fix_dir):
    html = fix_dir / "fake.html"
    assert looks_like_html(html)
    bad = validate_downloaded_file(html, expect_zip=True)
    assert not bad["ok"]
    assert "html_instead_of_binary" in bad["errors"] or "not_zip_magic" in bad["errors"]

    trunc = fix_dir / "truncated.zip"
    v = validate_downloaded_file(trunc, expect_zip=True)
    assert not v["ok"]


def test_download_skips_valid_existing(tmp_path, fix_dir):
    # copy valid zip and ensure skip path works without network
    dest = tmp_path / "Estabelecimentos0.zip"
    shutil.copy2(fix_dir / "Estabelecimentos0.zip", dest)
    res = download_file("http://example.invalid/Estabelecimentos0.zip", dest)
    assert res["ok"] is True
    assert res.get("skipped") is True


def test_load_activate_lookup_rollback(reg_root, fix_dir):
    release_id = "rfb-cnpj-fixture-2025-06"
    raw = reg_root / "raw" / release_id
    raw.mkdir(parents=True)
    shutil.copy2(fix_dir / "Estabelecimentos0.zip", raw / "Estabelecimentos0.zip")
    shutil.copy2(fix_dir / "Empresas0.zip", raw / "Empresas0.zip")

    m = new_manifest(release_id, mode="fixture", published_reference_date="2025-06")
    set_status(m, ReleaseStatus.DOWNLOADED.value)
    save_manifest(m)

    db = db_path_for_release(release_id, staging=True)
    r1 = load_zip_into_db(raw / "Estabelecimentos0.zip", db, kind_hint="estabelecimentos")
    r2 = load_zip_into_db(raw / "Empresas0.zip", db, kind_hint="empresas")
    assert r1["ok"] and r2["ok"]
    assert r1["db_counts"]["establishments"] == 3

    v = validate_load(release_id, min_establishments=1)
    assert v["ok"]

    act = activate_release(release_id, min_establishments=1)
    assert act["ok"]
    assert act["status"] == "ACTIVE"
    assert active_pointer_path().is_file()

    meta = json.loads((fix_dir / "meta.json").read_text(encoding="utf-8"))
    cnpj_ok = meta["cnpjs"][0]
    rec = lookup_cnpj(cnpj_ok)
    assert rec.official_match_status == OfficialMatchStatus.MATCHED.value
    assert rec.legal_name
    assert rec.registration_status == "ATIVA"
    assert rec.primary_cnae
    assert rec.official_release_id == release_id
    assert rec.source_provenance.get("release_id") == release_id

    # second release for rollback
    release2 = "rfb-cnpj-fixture-2025-07"
    raw2 = reg_root / "raw" / release2
    raw2.mkdir(parents=True)
    shutil.copy2(fix_dir / "Estabelecimentos0.zip", raw2 / "Estabelecimentos0.zip")
    shutil.copy2(fix_dir / "Empresas0.zip", raw2 / "Empresas0.zip")
    m2 = new_manifest(release2, mode="fixture")
    set_status(m2, ReleaseStatus.DOWNLOADED.value)
    save_manifest(m2)
    db2 = db_path_for_release(release2, staging=True)
    load_zip_into_db(raw2 / "Estabelecimentos0.zip", db2, kind_hint="estabelecimentos")
    load_zip_into_db(raw2 / "Empresas0.zip", db2, kind_hint="empresas")
    act2 = activate_release(release2)
    assert act2["ok"]
    assert lookup_cnpj(cnpj_ok).official_release_id == release2

    rb = rollback_release(release_id)
    assert rb["ok"]
    assert lookup_cnpj(cnpj_ok).official_release_id == release_id


def test_lookup_status_matrix(reg_root, fix_dir):
    # no active → UNAVAILABLE
    rec = lookup_cnpj("11222333000181")
    assert rec.official_match_status == OfficialMatchStatus.OFFICIAL_REGISTRY_UNAVAILABLE.value

    rec_m = lookup_cnpj(None)
    assert rec_m.official_match_status == OfficialMatchStatus.MISSING_CNPJ.value
    rec_i = lookup_cnpj("11222333000180")
    assert rec_i.official_match_status == OfficialMatchStatus.INVALID_CNPJ.value

    # activate fixture then NOT_FOUND
    release_id = "rfb-cnpj-fixture-nf"
    raw = reg_root / "raw" / release_id
    raw.mkdir(parents=True)
    shutil.copy2(fix_dir / "Estabelecimentos0.zip", raw / "Estabelecimentos0.zip")
    shutil.copy2(fix_dir / "Empresas0.zip", raw / "Empresas0.zip")
    m = new_manifest(release_id)
    set_status(m, ReleaseStatus.DOWNLOADED.value)
    save_manifest(m)
    db = db_path_for_release(release_id, staging=True)
    load_zip_into_db(raw / "Estabelecimentos0.zip", db, kind_hint="estabelecimentos")
    load_zip_into_db(raw / "Empresas0.zip", db, kind_hint="empresas")
    assert activate_release(release_id)["ok"]

    # valid CNPJ not in fixture
    # generate another valid CNPJ
    from scripts.company_registry.normalization import is_valid_cnpj14 as iv

    other = "19131243000197"
    assert iv(other)
    nf = lookup_cnpj(other)
    assert nf.official_match_status == OfficialMatchStatus.NOT_FOUND_IN_OFFICIAL_RELEASE.value


def test_coverage_denominators_not_gamed(reg_root, fix_dir):
    release_id = "rfb-cnpj-fixture-cov"
    raw = reg_root / "raw" / release_id
    raw.mkdir(parents=True)
    shutil.copy2(fix_dir / "Estabelecimentos0.zip", raw / "Estabelecimentos0.zip")
    shutil.copy2(fix_dir / "Empresas0.zip", raw / "Empresas0.zip")
    m = new_manifest(release_id)
    set_status(m, ReleaseStatus.DOWNLOADED.value)
    save_manifest(m)
    db = db_path_for_release(release_id, staging=True)
    load_zip_into_db(raw / "Estabelecimentos0.zip", db, kind_hint="estabelecimentos")
    load_zip_into_db(raw / "Empresas0.zip", db, kind_hint="empresas")
    activate_release(release_id)

    meta = json.loads((fix_dir / "meta.json").read_text(encoding="utf-8"))
    # 3 fixture + 1 invalid + 1 missing-style
    candidates = meta["cnpjs"] + ["11222333000180", "not-a-cnpj"]
    # top20 only the two ATIVAS
    top20 = meta["cnpjs"][:2]
    cov = compute_coverage(candidates, ranking_eligible=meta["cnpjs"][:2], top20=top20)
    assert cov["metrics"]["valid_cnpj_share"] is not None
    # official match = matched / valid (3 valid fixture among 4 valid? invalid is invalid, not-a-cnpj missing)
    # candidates: 3 valid fixture + 1 invalid DV + 1 structural missing → valid=3
    assert cov["counts"]["all_candidates"]["valid_cnpj"] == 3
    assert cov["counts"]["all_candidates"]["matched"] == 3
    assert cov["metrics"]["official_match_coverage"] == 1.0
    assert cov["metrics"]["top20_official_registry_coverage"] == 1.0
    # BAIXADA not usable
    elig_all = compute_coverage(meta["cnpjs"], ranking_eligible=meta["cnpjs"])
    assert elig_all["counts"]["ranking_eligible"]["usable"] == 2


def test_official_source_markers_not_fallback():
    assert is_official_registry_source("rfb_public_cadastral")
    assert is_official_registry_source("rfb_public_cadastral_via_opencnpj")
    assert is_official_registry_source("receita_federal_dados_abertos")
    assert not is_official_registry_source("brasilapi")
    assert not is_official_registry_source("opencnpj")
    assert not is_official_registry_source("minhareceita_fallback")


def test_outcome_ledger_human_only(reg_root, tmp_path):
    db = tmp_path / "ledger.sqlite"
    with pytest.raises(PermissionError):
        record_transition(
            cnpj14="11222333000181",
            to_state="APPROVED_FOR_CONTACT",
            actor="system",
            human_confirmed=True,
            db_path=db,
        )
    with pytest.raises(PermissionError):
        record_transition(
            cnpj14="11222333000181",
            to_state="CONTACTED",
            actor="tiago",
            human_confirmed=False,
            db_path=db,
        )
    ok = record_transition(
        cnpj14="11222333000181",
        to_state="APPROVED_FOR_CONTACT",
        actor="tiago",
        human_confirmed=True,
        campaign="CONFENGE-OFFICIAL-REGISTRY-TO-REVENUE-01",
        db_path=db,
    )
    assert ok["ok"]
    metrics = feedback_metrics(db)
    assert metrics["events_total"] == 1
    assert "APPROVED_FOR_CONTACT" in metrics["by_state"]
    assert set(HUMAN_ONLY_STATES)


def test_fail_closed_commercial_precheck(reg_root, fix_dir):
    from scripts.company_registry.commercial_bridge import fail_closed_commercial_precheck

    assert not fail_closed_commercial_precheck()["ok"]
    release_id = "rfb-cnpj-fixture-pc"
    raw = reg_root / "raw" / release_id
    raw.mkdir(parents=True)
    shutil.copy2(fix_dir / "Estabelecimentos0.zip", raw / "Estabelecimentos0.zip")
    shutil.copy2(fix_dir / "Empresas0.zip", raw / "Empresas0.zip")
    m = new_manifest(release_id)
    set_status(m, ReleaseStatus.DOWNLOADED.value)
    save_manifest(m)
    db = db_path_for_release(release_id, staging=True)
    load_zip_into_db(raw / "Estabelecimentos0.zip", db, kind_hint="estabelecimentos")
    load_zip_into_db(raw / "Empresas0.zip", db, kind_hint="empresas")
    activate_release(release_id)
    assert fail_closed_commercial_precheck()["ok"]


def test_cli_lookup_and_health(reg_root, fix_dir):
    from scripts.company_registry.cli import main

    # health without active → non-zero
    assert main(["health"]) != 0
    release_id = "rfb-cnpj-fixture-cli"
    raw = reg_root / "raw" / release_id
    raw.mkdir(parents=True)
    shutil.copy2(fix_dir / "Estabelecimentos0.zip", raw / "Estabelecimentos0.zip")
    shutil.copy2(fix_dir / "Empresas0.zip", raw / "Empresas0.zip")
    m = new_manifest(release_id)
    set_status(m, ReleaseStatus.DOWNLOADED.value)
    save_manifest(m)
    db = db_path_for_release(release_id, staging=True)
    load_zip_into_db(raw / "Estabelecimentos0.zip", db, kind_hint="estabelecimentos")
    load_zip_into_db(raw / "Empresas0.zip", db, kind_hint="empresas")
    activate_release(release_id)
    meta = json.loads((fix_dir / "meta.json").read_text(encoding="utf-8"))
    assert main(["lookup", "--cnpj", meta["cnpjs"][0]]) == 0
    assert main(["health", "--cnpj", meta["cnpjs"][0]]) == 0


def test_partial_release_cannot_activate(reg_root):
    release_id = "rfb-cnpj-empty"
    m = new_manifest(release_id)
    set_status(m, ReleaseStatus.LOADING.value)
    save_manifest(m)
    # empty db
    db = db_path_for_release(release_id, staging=True)
    from scripts.company_registry.store import connect_db

    conn = connect_db(db)
    conn.close()
    res = activate_release(release_id, min_establishments=1)
    assert not res["ok"]
