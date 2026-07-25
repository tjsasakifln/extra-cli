"""Gates comerciais do client-ready-frozen-rc-v2 (sem reimplementar o classificador)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.ops.sector_classifier import classify_object, is_engineering_for_e

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "artifacts/campaigns/CLIENT-READY-RECURRING-CONSULTING-CYCLE-01"
PACK = CAMPAIGN / "pack-v2"
STG = CAMPAIGN / "client-ready-frozen-rc-v2"

E_OK = {"ENGINEERING_HIGH_CONFIDENCE", "ENGINEERING_REVIEW"}
E_BAD = {"NON_ENGINEERING", "EXCLUDED_CATEGORY"}


def test_deliverable_e_zero_non_engineering_when_present() -> None:
    if not (PACK / "deliverable_e.json").is_file():
        return
    e = json.loads((PACK / "deliverable_e.json").read_text(encoding="utf-8"))
    for rec in e.get("recommendations") or []:
        lab = (rec.get("sector_classification") or {}).get("label")
        assert lab in E_OK
        obj = rec.get("titulo") or rec.get("objeto") or ""
        if obj:
            assert is_engineering_for_e(classify_object(str(obj)))
    if not (e.get("recommendations") or []):
        assert e.get("status") == "SUCCESS_ZERO_ENGINEERING_OPPORTUNITIES"


def test_deliverable_c_only_engineering() -> None:
    """Reclassify every C object text — no label theater, no FP allowed."""
    if not (PACK / "deliverable_c.json").is_file():
        return
    c = json.loads((PACK / "deliverable_c.json").read_text(encoding="utf-8"))
    banned_substr = (
        "institui",
        "arrecada",
        "banco central",
        "airless",
        "motobomb",
        "equipamento de pintura",
        "castra",
        "karate",
        "combustivel",
        "gasolina",
    )
    for row in c.get("rows") or []:
        obj = str(row.get("objeto") or "")
        assert obj.strip(), "empty object in C"
        low = obj.lower()
        for ban in banned_substr:
            assert ban not in low, f"C banned topic '{ban}': {obj[:120]}"
        clf = classify_object(obj)
        assert clf.label in E_OK, f"C FP: {clf.label} | {obj[:100]}"
        assert "probabilidade_pct" not in row
        assert "probability_pct" not in row
        stored = (row.get("sector_classification") or {}).get("label")
        assert stored in E_OK
        assert stored is not None


def test_deliverable_a_engineering_metric() -> None:
    if not (PACK / "deliverable_a.json").is_file():
        return
    a = json.loads((PACK / "deliverable_a.json").read_text(encoding="utf-8"))
    assert (a.get("population") or {}).get("ranking_metric") == (
        "engineering_activity_not_general_volume"
    )
    for row in a.get("rows") or []:
        for s in row.get("sample_objetos") or []:
            clf = classify_object(str(s))
            assert clf.label in E_OK, f"A sample FP: {clf.label} | {s[:100]}"


def test_deliverable_b_peer_competitors() -> None:
    if not (PACK / "deliverable_b.json").is_file():
        return
    b = json.loads((PACK / "deliverable_b.json").read_text(encoding="utf-8"))
    for row in b.get("rows") or []:
        nome = str(row.get("nome") or "").lower()
        assert "fundacao de ensino" not in nome
        assert "universidade" not in nome
        classe = row.get("classe_concorrente") or row.get("competitor_class")
        assert classe in {"concorrente_direto", "concorrente_adjacente"}
        ufs = row.get("ufs") or list((row.get("distribuicao_geografica") or {}).keys())
        assert ufs, f"missing UFs for {row.get('nome')}"
        for ex in row.get("exemplos_contratos") or []:
            clf = classify_object(str(ex))
            assert clf.label == "ENGINEERING_HIGH_CONFIDENCE", (
                f"B evidence not HIGH_CONFIDENCE: {clf.label} | {ex[:80]}"
            )


def test_deliverable_d_no_absurd_ok_medians_on_global() -> None:
    if not (PACK / "deliverable_d.json").is_file():
        return
    d = json.loads((PACK / "deliverable_d.json").read_text(encoding="utf-8"))
    for p in d.get("panels") or []:
        if p.get("status") == "OK":
            unit = (p.get("dimensions") or {}).get("unidade")
            assert unit not in {"contrato_global", "global", "heterogeneo"}
            assert p.get("median") is not None
        if (p.get("dimensions") or {}).get("unidade") == "contrato_global":
            assert p.get("status") == "INSUFFICIENT_COMPARABLE_DATA"
            assert p.get("median") is None


def test_identity_no_self_hash_and_pending() -> None:
    ua = json.loads((CAMPAIGN / "user-acceptance.json").read_text(encoding="utf-8"))
    assert ua["status"] == "PENDING_HUMAN"
    assert ua.get("accepted_by") is None
    if not (STG / "ARTIFACT-IDENTITY.json").is_file():
        return
    identity = json.loads((STG / "ARTIFACT-IDENTITY.json").read_text(encoding="utf-8"))
    assert "ARTIFACT-IDENTITY.json" not in (identity.get("file_sha256") or {})
    assert identity.get("artifact_name") == "client-ready-frozen-rc-v2"
    assert (STG / "ARTIFACT-IDENTITY.sha256").is_file()
    for name in ("executive-report.pdf", "consulting-pack.xlsx"):
        if (STG / name).is_file() and name in ua.get("package_checksums", {}):
            dig = hashlib.sha256((STG / name).read_bytes()).hexdigest()
            assert dig == ua["package_checksums"][name]


def test_frozen_checksums_only_existing_files() -> None:
    """checksums.json must not reference files absent from the frozen artifact."""
    if not (STG / "checksums.json").is_file():
        return
    ck = json.loads((STG / "checksums.json").read_text(encoding="utf-8"))
    for name, digest in ck.items():
        p = STG / name
        assert p.is_file(), f"orphan checksum key: {name}"
        assert hashlib.sha256(p.read_bytes()).hexdigest() == digest


def test_v1_remains_changes_requested() -> None:
    hist = CAMPAIGN / "rc-v1-CHANGES_REQUESTED.json"
    assert hist.is_file()
    data = json.loads(hist.read_text(encoding="utf-8"))
    assert data["status"] == "CHANGES_REQUESTED"


def test_classifier_rejects_v1_polluters() -> None:
    for obj in (
        "AQUISIÇÃO DE LENÇÓIS E MANTAS",
        "computador All in One",
        "exames laboratoriais",
        "manutenção da frota municipal",
        "SEGURO DE FROTA DE VEICULOS DO DEPARTAMENTO DE ESGOTO",
        "TELEFONIA VOIP",
        "LIMPEZA E JARDINAGEM EM AREAS PAVIMENTADAS",
        "GRAMA SINTETICA FIFA COM DRENAGEM",
        "SANEAMENTO DE INCONFORMIDADES LEGAIS",
        "CREDENCIAMENTO DE INSTITUIÇÕES FINANCEIRAS PARA ARRECADAÇÃO DE FATURAS DE ESGOTAMENTO SANITÁRIO",
        "AQUISIÇÃO DE EQUIPAMENTO DE PINTURA AIRLESS PARA MEIO-FIO",
        "AQUISIÇÃO DE CONJUNTOS MOTOBOMBAS SUBMERSÍVEIS PARA ESGOTAMENTO SANITÁRIO",
    ):
        assert not is_engineering_for_e(classify_object(obj)), obj


def test_ua_checksums_identity_triple_equality_for_checksums_json() -> None:
    """Criterion 4: ua.package_checksums[checksums.json] == disk == identity.file_sha256."""
    if not (STG / "checksums.json").is_file():
        return
    if not (STG / "user-acceptance.json").is_file():
        return
    if not (STG / "ARTIFACT-IDENTITY.json").is_file():
        return
    ua = json.loads((STG / "user-acceptance.json").read_text(encoding="utf-8"))
    identity = json.loads((STG / "ARTIFACT-IDENTITY.json").read_text(encoding="utf-8"))
    disk = hashlib.sha256((STG / "checksums.json").read_bytes()).hexdigest()
    ua_ck = (ua.get("package_checksums") or {}).get("checksums.json")
    id_ck = (identity.get("file_sha256") or {}).get("checksums.json")
    assert ua_ck is not None, "ua.package_checksums missing checksums.json"
    assert id_ck is not None, "identity.file_sha256 missing checksums.json"
    assert ua_ck == disk == id_ck, (
        f"triple mismatch checksums.json ua={ua_ck[:16]} id={id_ck[:16]} disk={disk[:16]}"
    )


def test_assert_full_reconciliation_detects_checksums_mutation(tmp_path: Path) -> None:
    """Mutation after freeze must fail assert_full_reconciliation (no silent OK)."""
    from scripts.ops.publish_commercial_rc_v2 import assert_full_reconciliation, freeze_staging

    if not PACK.is_dir() or not (PACK / "executive-report.pdf").is_file():
        return
    # Need pack members present
    for name in (
        "executive-report.pdf",
        "consulting-pack.xlsx",
        "executive-summary.md",
        "pack-manifest.json",
        "deliverable_a.json",
        "deliverable_b.json",
        "deliverable_c.json",
        "deliverable_d.json",
        "deliverable_e.json",
    ):
        if not (PACK / name).is_file():
            return

    campaign = tmp_path / "campaign"
    staging = tmp_path / "staging"
    campaign.mkdir()
    pm = json.loads((PACK / "pack-manifest.json").read_text(encoding="utf-8"))
    run_id = str(pm.get("run_id") or "test-run")
    product_rc_sha = "a" * 64
    result = freeze_staging(
        campaign_dir=campaign,
        pack_dir=PACK,
        staging_dir=staging,
        run_id=run_id,
        product_rc_sha=product_rc_sha,
    )
    assert result["status"] == "READY_FOR_SECOND_HUMAN_PRODUCT_REVIEW", result
    assert assert_full_reconciliation(staging) == []

    # Mutate checksums.json after freeze — must be detected
    ck_path = staging / "checksums.json"
    ck = json.loads(ck_path.read_text(encoding="utf-8"))
    ck["executive-report.pdf"] = "0" * 64
    ck_path.write_text(json.dumps(ck, indent=2) + "\n", encoding="utf-8")
    div = assert_full_reconciliation(staging)
    assert div, "mutation of checksums.json must produce divergences"
    assert any("checksums" in d or "ua_package" in d or "triple" in d for d in div)
