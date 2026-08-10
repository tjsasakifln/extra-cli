"""Integration: published gate, downgrade→send-ready fail-closed, version backfill, concurrency."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from scripts.confenge_contact_resolution.send_readiness import evaluate_email_send_ready
from scripts.confenge_target_fit import (
    TARGET_CONFIRMED,
    TARGET_FIT_VERSION,
    TARGET_OUT_OF_SCOPE,
)
from scripts.confenge_target_fit.cdc import enqueue_version_backfill
from scripts.confenge_target_fit.company_key import company_key_from_raiz
from scripts.confenge_target_fit.compute import compute_materialization
from scripts.confenge_target_fit.config import TargetFitRefreshConfig
from scripts.confenge_target_fit.db import connect
from scripts.confenge_target_fit.feed import assert_warmbly_contract, enrich_outreach_row
from scripts.confenge_target_fit.loader import company_input_from_dict
from scripts.confenge_target_fit.models import MaterializedTargetFit, TransitionEvent
from scripts.confenge_target_fit.store import (
    claim_batch,
    enqueue_dirty,
    ensure_control_defaults,
    get_current,
    is_send_suppressed,
    publish_materialization,
    record_downstream_invalidation_soft,
)
from scripts.confenge_target_fit.worker import process_one
from scripts.warmbly_bridge.mapping import map_lead

DSN = os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("CONFENGE_TARGET_FIT_STATE_DSN")

pytestmark = [
    pytest.mark.real_db,
    pytest.mark.skipif(not DSN, reason="LOCAL_DATALAKE_DSN not set"),
]


def _apply_migration() -> None:
    import subprocess
    import sys
    from pathlib import Path

    subprocess.check_call(
        [sys.executable, "-m", "scripts.ops.apply_migrations", "--dsn", DSN],
        cwd=str(Path(__file__).resolve().parents[2]),
    )


@pytest.fixture(scope="module")
def dsn():
    _apply_migration()
    return DSN


def _construction(raiz: str):
    return company_input_from_dict(
        {
            "cnpj_raiz": raiz,
            "razao_social": f"CONSTRUTORA {raiz} LTDA",
            "cnae_principal": "4120400",
            "contracts": [
                {
                    "contrato_id": f"c-{raiz}-1",
                    "objeto_contrato": "Execucao de obras de pavimentacao asfaltica",
                    "valor_total": 2_000_000,
                    "orgao_nome": "PREFEITURA",
                    "fornecedor_cnpj": raiz + "000191",
                },
                {
                    "contrato_id": f"c-{raiz}-2",
                    "objeto_contrato": "Servicos de engenharia e terraplenagem",
                    "valor_total": 900_000,
                    "orgao_nome": "DNIT",
                    "fornecedor_cnpj": raiz + "000191",
                },
                {
                    "contrato_id": f"c-{raiz}-3",
                    "objeto_contrato": "Execucao de obra de drenagem urbana",
                    "valor_total": 400_000,
                    "orgao_nome": "PREFEITURA",
                    "fornecedor_cnpj": raiz + "000272",
                },
            ],
            "construction_evidence": {
                "sector_fit": "CONFIRMED",
                "activity_class": "CONSTRUCTION",
                "relevant_contract_count": 3,
                "relevant_ratio": 1.0,
            },
            "source_watermark": "2026-08-09T12:00:00Z",
        }
    )


def _supply(raiz: str):
    return company_input_from_dict(
        {
            "cnpj_raiz": raiz,
            "razao_social": f"COMERCIO {raiz} LTDA",
            "cnae_principal": "4771701",
            "contracts": [
                {
                    "contrato_id": f"s-{raiz}",
                    "objeto_contrato": "Aquisicao de medicamentos hospitalares",
                    "valor_total": 1_000_000,
                    "orgao_nome": "FUNDACAO SAUDE",
                    "fornecedor_cnpj": raiz + "000191",
                }
            ],
            "construction_evidence": {
                "sector_fit": "OUT",
                "activity_class": "COMMERCE",
                "relevant_contract_count": 0,
                "relevant_ratio": 0.0,
            },
            "source_watermark": "2026-08-09T13:00:00Z",
        }
    )


def test_process_one_active_downgrade_suppresses_send_ready(dsn):
    """ACTIVE process_one downgrade → is_send_suppressed + EMAIL_SEND_READY false."""
    # Pure digits only (cnpj_raiz CHAR(8))
    raiz = f"77{uuid.uuid4().int % 10**6:06d}"[:8]
    ck = company_key_from_raiz(raiz)
    cfg = TargetFitRefreshConfig.from_env()
    conn = connect(dsn, readonly=False)
    try:
        ensure_control_defaults(conn)
        # Seed CONFIRMED as current
        company = _construction(raiz)
        mat, evt, _ = compute_materialization(company, previous=None, mode="ACTIVE")
        assert mat.target_fit_class == TARGET_CONFIRMED
        publish_materialization(conn, mat, evt, shadow_only=False)
        conn.commit()
        assert get_current(conn, ck)["target_fit_class"] == TARGET_CONFIRMED
        assert is_send_suppressed(conn, ck) is False

        # Enqueue dirty and process with supply-only path via monkeypatch of loader
        key = f"downgrade-test-{uuid.uuid4().hex}"
        enqueue_dirty(
            conn,
            company_key=ck,
            cnpj_raiz=raiz,
            reason="test_downgrade",
            source_entity="test",
            source_id="1",
            source_updated_at=datetime.now(UTC),
            source_watermark="2026-08-09T13:00:00Z",
            priority=99,
            idempotency_key=key,
        )
        conn.commit()
        items = claim_batch(
            conn, worker_id="w-down", batch_size=5, lock_ttl_seconds=60
        )
        conn.commit()
        item = next(i for i in items if i.idempotency_key == key)

        import scripts.confenge_target_fit.worker as worker_mod

        real_load = worker_mod.load_company_input

        def load_supply(conn, *, cnpj_raiz, source_watermark="", contract_limit=200):
            return _supply(cnpj_raiz)

        worker_mod.load_company_input = load_supply  # type: ignore[assignment]
        try:
            res = process_one(conn, item, cfg=cfg, mode="ACTIVE")
            conn.commit()
        finally:
            worker_mod.load_company_input = real_load  # type: ignore[assignment]

        assert res["status"] in {"done", "skipped_same_fingerprint"}
        cur = get_current(conn, ck)
        assert cur is not None
        assert cur["target_fit_class"] != TARGET_CONFIRMED
        assert is_send_suppressed(conn, ck) is True

        # EMAIL_SEND_READY must fail closed when company carries published fields
        company_row = {
            "company_key": ck,
            "cnpj14": raiz + "000191",
            "target_fit_class": cur["target_fit_class"],
            "target_fit_confidence": cur["target_fit_confidence"],
            "target_fit_version": cur["target_fit_version"],
            "target_fit_source_watermark": cur["source_watermark"],
            "target_fit_computed_at": cur["computed_at"],
            "target_fit_send_suppressed": True,
            "service_code": "REAJUSTE",
            "factual_hook": "contrato X",
            "evidence_ids": ["e1"],
            "canonical_universe_member": True,
            "datalake_watermark": "2026-08-09T13:00:00Z",
        }
        ready = evaluate_email_send_ready(
            company=company_row,
            email="contato@empresa.com.br",
            ownership_status="COMPANY_OWNED",
            verification_status="OBSERVED",
            service_code="REAJUSTE",
            factual_evidence=True,
            evidence_ids=["e1"],
        )
        assert ready.email_send_ready is False
        assert any(
            "DOWNGRADE" in r or "target_fit" in r or "OUT" in r or "PROBABLE" in r
            for r in ready.reasons
        ) or ready.target_fit_send_tier not in {"A_AUTOMATIC", "B_EVIDENCE_SUPPORTED"}
    finally:
        conn.close()


def test_version_backfill_marks_recompute_required(dsn):
    raiz = "66112233"
    ck = company_key_from_raiz(raiz)
    conn = connect(dsn, readonly=False)
    try:
        ensure_control_defaults(conn)
        now = datetime.now(UTC)
        mat = MaterializedTargetFit(
            company_key=ck,
            cnpj_raiz=raiz,
            target_fit_class=TARGET_CONFIRMED,
            target_fit_confidence=0.9,
            target_fit_version="confenge-target-fit-OLD",
            target_fit_reason_codes=["old"],
            target_fit_evidence=[],
            computed_at=now,
            source_watermark="2026-01-01T00:00:00Z",
            source_max_updated_at=now,
            input_fingerprint="sha256:old",
            classifier_sha="sha256:x",
            schema_version="confenge-tf-store-v1",
        )
        publish_materialization(conn, mat, None, shadow_only=False)
        conn.commit()
        enqueue_version_backfill(conn, current_version=TARGET_FIT_VERSION, limit=50)
        conn.commit()
        cur = get_current(conn, ck)
        assert cur is not None
        assert cur["operational_status"] == "recompute_required"
        assert cur["target_fit_version"] == "confenge-target-fit-OLD"
    finally:
        conn.close()


def test_claim_batch_one_per_company(dsn):
    """Two dirty rows for same company_key → only one claimed."""
    from scripts.confenge_target_fit.store import reclaim_expired_locks

    raiz = "55221100"
    ck = company_key_from_raiz(raiz)
    conn = connect(dsn, readonly=False)
    try:
        ensure_control_defaults(conn)
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM confenge_target_fit_dirty WHERE company_key = %s", (ck,)
            )
        conn.commit()
        for i in range(3):
            enqueue_dirty(
                conn,
                company_key=ck,
                cnpj_raiz=raiz,
                reason=f"multi-{i}",
                source_entity="test",
                source_id=str(i),
                source_updated_at=datetime.now(UTC),
                source_watermark=f"wm-{i}",
                priority=80 - i,
                idempotency_key=f"multi-claim-{ck}-{i}-{uuid.uuid4().hex[:6]}",
            )
        conn.commit()
        reclaim_expired_locks(conn)
        batch = claim_batch(
            conn, worker_id="w-one", batch_size=10, lock_ttl_seconds=60
        )
        conn.commit()
        same = [i for i in batch if i.company_key == ck]
        assert len(same) == 1, f"expected 1 claim, got {same!r} full={batch!r}"
    finally:
        conn.close()


def test_concurrent_claim_same_company_single_writer(dsn):
    """Two parallel claim_batch calls never return the same dirty id."""
    raiz = "44110099"
    ck = company_key_from_raiz(raiz)
    conn = connect(dsn, readonly=False)
    try:
        ensure_control_defaults(conn)
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM confenge_target_fit_dirty WHERE company_key = %s", (ck,)
            )
        for i in range(5):
            enqueue_dirty(
                conn,
                company_key=ck,
                cnpj_raiz=raiz,
                reason=f"conc-{i}",
                source_entity="test",
                source_id=str(i),
                source_updated_at=datetime.now(UTC),
                source_watermark="wm-c",
                priority=90,
                idempotency_key=f"conc-{ck}-{i}-{uuid.uuid4().hex[:8]}",
            )
        conn.commit()
    finally:
        conn.close()

    def _claim(worker_id: str):
        c = connect(dsn, readonly=False)
        try:
            items = claim_batch(
                c, worker_id=worker_id, batch_size=5, lock_ttl_seconds=60
            )
            c.commit()
            return [i.id for i in items if i.company_key == ck]
        finally:
            c.close()

    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(_claim, f"cw-{i}") for i in range(2)]
        results = [f.result() for f in as_completed(futs)]
    all_ids = [i for part in results for i in part]
    # At most one id claimed across both workers for this company
    assert len(all_ids) <= 1


def test_enrich_and_warmbly_mapping_use_published_fields():
    """Feed enrichment + mapping set contract fields; Warmbly fail-closed without CONFIRMED."""
    current = {
        "company_key": "cnpj_root:11223344",
        "target_fit_class": TARGET_OUT_OF_SCOPE,
        "target_fit_confidence": 0.8,
        "target_fit_version": TARGET_FIT_VERSION,
        "source_watermark": "2026-08-09T00:00:00Z",
        "computed_at": datetime(2026, 8, 9, tzinfo=UTC),
        "operational_status": "ok",
        "target_fit_evidence": [{"id": "e1"}],
    }
    row = enrich_outreach_row(
        {"cnpj14": "11223344000191", "email_send_ready": True},
        current=current,
        datalake_watermark="2026-08-09T00:00:00Z",
        suppressed=True,
    )
    assert row["target_fit_class"] == TARGET_OUT_OF_SCOPE
    assert row["email_send_ready"] is False
    assert row["email_send_ready_target_fit_ok"] is False
    errs = assert_warmbly_contract(row)
    assert "target_fit_class_not_confirmed" in errs

    # Mapping with published fields must not re-score to A_AUTOMATIC
    universe = {
        "cnpj14": "11223344000191",
        "razao_social": "COMERCIO X",
        "canonical_universe_member": True,
        "target_fit_class": TARGET_OUT_OF_SCOPE,
        "target_fit_confidence": 0.8,
        "target_fit_version": TARGET_FIT_VERSION,
        "target_fit_source_watermark": "2026-08-09T00:00:00Z",
        "target_fit_computed_at": "2026-08-09T00:00:00Z",
        "target_fit_send_suppressed": True,
        "datalake_watermark": "2026-08-09T00:00:00Z",
        "commercial_state": "NEW",
    }
    intel = {
        "offer": {"service_code": "REAJUSTE", "service_name": "Reajuste"},
        "messaging_context": {
            "fact_to_mention": "contrato",
            "question_to_ask": "q",
            "cta": "c",
            "claims_to_avoid": [],
        },
        "evidence": [{"id": "e1", "epistemic_class": "CONFIRMED_FACT"}],
    }
    contacts_row = {
        "contacts": [
            {
                "email": "a@b.com.br",
                "ownership_status": "COMPANY_OWNED",
                "verification_status": "OBSERVED",
            }
        ]
    }
    lead = map_lead(universe, intel=intel, contacts_row=contacts_row)
    assert lead is not None
    assert lead.get("target_fit_class") == TARGET_OUT_OF_SCOPE
    assert lead.get("email_send_ready") is not True
    assert "target_fit_version" in lead
    assert lead.get("target_fit_send_tier") != "A_AUTOMATIC"


def test_confirmed_fresh_published_allows_tier_a():
    company = {
        "razao_social": "PAVIPLAN ENGENHARIA LTDA",
        "official_domain": "paviplan.com.br",
        "target_fit_class": TARGET_CONFIRMED,
        "target_fit_confidence": 0.9,
        "target_fit_version": TARGET_FIT_VERSION,
        "target_fit_source_watermark": "2026-08-09T12:00:00Z",
        "target_fit_computed_at": "2026-08-09T12:00:00Z",
        "datalake_watermark": "2026-08-09T12:00:00Z",
        "service_code": "estruturacao_pleito_reajuste",
        "factual_hook": (
            "objeto: pavimentação asfáltica CBUQ em vias urbanas; "
            "órgão: Pref. Coxilha; UF RS"
        ),
        "observed_fact": (
            "objeto: pavimentação asfáltica CBUQ em vias urbanas; "
            "órgão: Pref. Coxilha; UF RS"
        ),
        "why_this_account": (
            "PAVIPLAN com execução pública de pavimentação — "
            "objeto: pavimentação asfáltica CBUQ em vias urbanas; órgão: Pref. Coxilha"
        ),
        "why_now": (
            "aditivo recente no contrato de PAVIPLAN de pavimentação asfáltica CBUQ "
            "com a Pref. Coxilha"
        ),
        "micro_offer_code": "REAJUSTE_CHECK",
        "cta": "Posso te mandar o recorte público que encontrei?",
        "evidence_ids": ["c1"],
        "canonical_universe_member": True,
        "service_candidates": [
            {
                "service_id": "estruturacao_pleito_reajuste",
                "supporting_signal_ids": ["mature_no_reajuste"],
                "evidence_ids": ["c1"],
            }
        ],
        "primary_service": {
            "service_id": "estruturacao_pleito_reajuste",
            "supporting_signal_ids": ["mature_no_reajuste"],
            "evidence_ids": ["c1"],
        },
        "construction_evidence": {
            "sector_fit": "CONFIRMED_ENGINEERING",
            "target_fit_class": TARGET_CONFIRMED,
            "relevant_contract_count": 3,
        },
        "portfolio": {"pass_contract_count": 3},
    }
    ready = evaluate_email_send_ready(
        company=company,
        email="engenharia@paviplan.com.br",
        ownership_status="COMPANY_OWNED",
        verification_status="OBSERVED",
        service_code="estruturacao_pleito_reajuste",
        factual_evidence=True,
        evidence_ids=["c1"],
        source_type="site",
        source_url="https://paviplan.com.br/contato",
    )
    assert ready.target_fit_send_tier == "A_AUTOMATIC"
    assert ready.provenance_chain_valid is True
    assert ready.email_send_ready is True, ready.reasons
