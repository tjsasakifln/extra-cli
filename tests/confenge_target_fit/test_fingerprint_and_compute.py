"""Property tests for fingerprint + pure compute path (no DB)."""

from __future__ import annotations

from datetime import UTC, datetime

from scripts.confenge_target_fit import (
    TARGET_CONFIRMED,
    TARGET_FIT_VERSION,
    TARGET_OUT_OF_SCOPE,
    TARGET_PROBABLE_RESEARCH,
)
from scripts.confenge_target_fit.compute import compute_materialization, should_apply_active
from scripts.confenge_target_fit.fingerprint import compute_input_fingerprint
from scripts.confenge_target_fit.loader import company_input_from_dict
from scripts.confenge_target_fit.transitions import is_downgrade, is_upgrade, transition_key


def _construction_company(**over):
    base = {
        "cnpj_raiz": "11222333",
        "razao_social": "CONSTRUTORA EXEMPLO LTDA",
        "cnae_principal": "4120400",
        "contracts": [
            {
                "contrato_id": "c1",
                "objeto_contrato": "Execucao de obras de pavimentacao asfaltica",
                "valor_total": 1_500_000,
                "orgao_nome": "PREFEITURA MUNICIPAL",
                "fornecedor_cnpj": "11222333000191",
            },
            {
                "contrato_id": "c2",
                "objeto_contrato": "Servicos de engenharia e terraplenagem",
                "valor_total": 800_000,
                "orgao_nome": "DEPARTAMENTO DE ESTRADAS",
                "fornecedor_cnpj": "11222333000191",
            },
            {
                "contrato_id": "c3",
                "objeto_contrato": "Execucao de obra de drenagem urbana",
                "valor_total": 400_000,
                "orgao_nome": "PREFEITURA",
                "fornecedor_cnpj": "11222333000272",
            },
        ],
        "construction_evidence": {
            "sector_fit": "CONFIRMED",
            "activity_class": "CONSTRUCTION",
            "relevant_contract_count": 3,
            "relevant_ratio": 1.0,
        },
    }
    base.update(over)
    return company_input_from_dict(base)


def _supply_only_company():
    return company_input_from_dict(
        {
            "cnpj_raiz": "99887766",
            "razao_social": "COMERCIO DE MEDICAMENTOS LTDA",
            "cnae_principal": "4771701",
            "contracts": [
                {
                    "contrato_id": "s1",
                    "objeto_contrato": "Aquisicao de medicamentos hospitalares",
                    "valor_total": 5_000_000,
                    "orgao_nome": "FUNDACAO DE SAUDE",
                    "fornecedor_cnpj": "99887766000100",
                }
            ],
            "construction_evidence": {
                "sector_fit": "OUT",
                "activity_class": "COMMERCE",
                "relevant_contract_count": 0,
                "relevant_ratio": 0.0,
            },
        }
    )


def test_same_input_same_version_same_fingerprint():
    c = _construction_company()
    a = compute_input_fingerprint(c, target_fit_version=TARGET_FIT_VERSION)
    b = compute_input_fingerprint(c, target_fit_version=TARGET_FIT_VERSION)
    assert a == b
    assert a.startswith("sha256:")


def test_irrelevant_timestamp_does_not_change_fingerprint():
    c1 = _construction_company()
    c2 = _construction_company()
    # Inject noise timestamps on contracts (must be ignored by fingerprint)
    for ct in c2.contracts:
        ct["ingested_at"] = "2099-01-01T00:00:00Z"
        ct["updated_at"] = "2099-01-02T00:00:00Z"
    assert compute_input_fingerprint(
        c1, target_fit_version=TARGET_FIT_VERSION
    ) == compute_input_fingerprint(c2, target_fit_version=TARGET_FIT_VERSION)


def test_version_change_changes_fingerprint():
    c = _construction_company()
    a = compute_input_fingerprint(c, target_fit_version="v1")
    b = compute_input_fingerprint(c, target_fit_version="v2")
    assert a != b


def test_same_event_twice_same_effective_state():
    c = _construction_company()
    mat1, evt1, meta1 = compute_materialization(c, previous=None, mode="ACTIVE")
    prev = mat1.as_dict()
    # Second compute with same inputs must skip recompute
    mat2, evt2, meta2 = compute_materialization(c, previous=prev, mode="ACTIVE")
    assert meta2["skipped_fingerprint"] is True
    assert evt2 is None
    assert mat2.target_fit_class == mat1.target_fit_class
    assert mat2.input_fingerprint == mat1.input_fingerprint


def test_same_fingerprint_with_missing_classifier_lineage_recomputes() -> None:
    c = _construction_company()
    mat1, _, _ = compute_materialization(c, previous=None, mode="ACTIVE")
    previous = mat1.as_dict()
    previous["classifier_sha"] = ""

    mat2, _, meta2 = compute_materialization(c, previous=previous, mode="ACTIVE")

    assert meta2["skipped_fingerprint"] is False
    assert mat2.classifier_sha == mat1.classifier_sha


def test_new_source_watermark_is_republished_even_when_inputs_are_unchanged():
    first = _construction_company(source_watermark="2026-08-12T09:00:00Z")
    mat1, _, _ = compute_materialization(first, previous=None, mode="ACTIVE")
    refreshed = _construction_company(source_watermark="2026-08-12T10:00:00Z")

    mat2, _, meta2 = compute_materialization(
        refreshed,
        previous=mat1.as_dict(),
        mode="ACTIVE",
    )

    assert meta2["skipped_fingerprint"] is False
    assert mat2.source_watermark == "2026-08-12T10:00:00Z"


def test_supply_only_never_confirms():
    c = _supply_only_company()
    mat, evt, meta = compute_materialization(c, previous=None, mode="ACTIVE")
    assert mat.target_fit_class == TARGET_OUT_OF_SCOPE
    assert mat.target_fit_class != TARGET_CONFIRMED


def test_new_irrelevant_contract_no_false_promotion():
    c = _supply_only_company()
    mat1, _, _ = compute_materialization(c, previous=None, mode="ACTIVE")
    assert mat1.target_fit_class != TARGET_CONFIRMED
    # Add another supply contract (more contracts must not confirm)
    c.contracts.append(
        {
            "contrato_id": "s2",
            "objeto_contrato": "Fornecimento de materiais hospitalares",
            "valor_total": 9_000_000,
            "orgao_nome": "SECRETARIA DE SAUDE",
            "fornecedor_cnpj": "99887766000100",
        }
    )
    mat2, _, _ = compute_materialization(c, previous=mat1.as_dict(), mode="ACTIVE")
    assert mat2.target_fit_class != TARGET_CONFIRMED
    assert mat2.target_fit_class == TARGET_OUT_OF_SCOPE


def test_downgrade_detection():
    assert is_downgrade(TARGET_CONFIRMED, TARGET_PROBABLE_RESEARCH)
    assert is_downgrade(TARGET_CONFIRMED, TARGET_OUT_OF_SCOPE)
    assert is_upgrade(TARGET_OUT_OF_SCOPE, TARGET_CONFIRMED)
    assert transition_key(TARGET_CONFIRMED, TARGET_OUT_OF_SCOPE) == "CONFIRMED→OUT"


def test_downgrade_path_emits_event():
    c = _construction_company()
    mat1, _, _ = compute_materialization(c, previous=None, mode="ACTIVE")
    # Force previous CONFIRMED then classify as supply-only company under same key
    supply = _supply_only_company()
    supply.company_key = mat1.company_key
    supply.cnpj_raiz = mat1.cnpj_raiz
    prev = mat1.as_dict()
    mat2, evt, meta = compute_materialization(supply, previous=prev, mode="ACTIVE")
    assert meta["downgrade"] is True
    assert mat2.target_fit_class != TARGET_CONFIRMED
    assert evt is not None
    assert evt.old_class == TARGET_CONFIRMED


def test_failure_does_not_preserve_confirmed():
    """If classifier path fails, publish REFRESH_FAILED — never keep CONFIRMED silently."""
    c = _construction_company()
    mat1, _, _ = compute_materialization(c, previous=None, mode="ACTIVE")
    assert mat1.target_fit_class in {
        TARGET_CONFIRMED,
        TARGET_PROBABLE_RESEARCH,
        TARGET_OUT_OF_SCOPE,
    }

    # Monkeypatch classify to raise. Bust fingerprint so skip path is not taken.
    import scripts.confenge_target_fit.compute as compute_mod

    real = compute_mod.classify_target_fit

    def boom(**kwargs):
        raise RuntimeError("synthetic classifier failure")

    compute_mod.classify_target_fit = boom  # type: ignore[assignment]
    try:
        prev = mat1.as_dict()
        prev["input_fingerprint"] = "sha256:stale-force-recompute"
        prev["target_fit_class"] = TARGET_CONFIRMED
        mat2, evt, meta = compute_materialization(c, previous=prev, mode="ACTIVE")
        assert mat2.target_fit_class == "REFRESH_FAILED"
        assert mat2.operational_status == "refresh_failed"
        assert mat2.target_fit_class != TARGET_CONFIRMED
        assert evt is not None
        assert meta["error"]
    finally:
        compute_mod.classify_target_fit = real  # type: ignore[assignment]


def test_shadow_mode_should_not_apply_active():
    assert should_apply_active(mode="SHADOW", company_key="cnpj_root:11222333", canary_percent=5) is False
    assert should_apply_active(mode="ACTIVE", company_key="cnpj_root:11222333", canary_percent=5) is True


def test_canary_bucket_stable():
    from scripts.confenge_target_fit.company_key import canary_bucket

    k = "cnpj_root:11222333"
    assert canary_bucket(k) == canary_bucket(k)
    assert 0 <= canary_bucket(k) < 100


def test_consortium_marked_conservative():
    c = _construction_company(
        contracts=[
            {
                "contrato_id": "cons1",
                "objeto_contrato": "Execucao de obras em consorcio com parceiro",
                "valor_total": 10_000_000,
                "orgao_nome": "DNIT",
                "fornecedor_cnpj": "11222333000191",
                "fornecedor_nome": "CONSORCIO ABC OBRAS",
                "is_consortium": True,
            }
        ]
    )
    assert c.is_consortium_member is True
    mat, _, _ = compute_materialization(c, previous=None, mode="ACTIVE")
    assert "CONSORTIUM_EVIDENCE" in mat.target_fit_reason_codes


def test_filial_maps_to_root_company_key():
    from scripts.confenge_target_fit.company_key import resolve_company_from_contract

    resolved = resolve_company_from_contract(
        {"fornecedor_cnpj": "11222333000272", "objeto_contrato": "x"}
    )
    assert resolved is not None
    key, raiz = resolved
    assert raiz == "11222333"
    assert key == "cnpj_root:11222333"


def test_freshness_stale_blocks_send():
    from scripts.confenge_target_fit.freshness import evaluate_freshness

    current = {
        "target_fit_class": TARGET_CONFIRMED,
        "operational_status": "ok",
        "computed_at": datetime(2020, 1, 1, tzinfo=UTC),
        "source_watermark": "2020-01-01T00:00:00Z",
    }
    d = evaluate_freshness(
        company_key="cnpj_root:11222333",
        current=current,
        datalake_watermark="2026-08-09T12:00:00Z",
    )
    assert d.target_fit_fresh is False
    assert d.blocks_send is True
    assert d.reason == "TARGET_FIT_STALE"


def test_feed_warmbly_contract_fail_closed():
    from scripts.confenge_target_fit.feed import assert_warmbly_contract, enrich_outreach_row

    row = enrich_outreach_row(
        {"cnpj14": "11222333000191"},
        current={
            "company_key": "cnpj_root:11222333",
            "target_fit_class": TARGET_PROBABLE_RESEARCH,
            "target_fit_confidence": 0.4,
            "target_fit_version": TARGET_FIT_VERSION,
            "source_watermark": "2026-08-09T00:00:00Z",
            "computed_at": datetime(2026, 8, 9, tzinfo=UTC),
            "operational_status": "ok",
            "target_fit_evidence": [{"id": "c1"}],
        },
        datalake_watermark="2026-08-09T00:00:00Z",
    )
    errs = assert_warmbly_contract(row)
    assert "target_fit_class_not_confirmed" in errs
