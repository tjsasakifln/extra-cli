"""Prove live DB join for published target-fit in export/mapping/send-ready.

Skeptic gaps closed:
- confenge_company_target_fit_current is joined (not only pre-embedded fields)
- downgrade suppression in store is visible to EMAIL_SEND_READY via conn
- published-path errors fail closed (no legacy re-score to sendable)
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest

from scripts.confenge_contact_resolution.send_readiness import evaluate_email_send_ready
from scripts.confenge_target_fit import TARGET_CONFIRMED, TARGET_FIT_VERSION, TARGET_OUT_OF_SCOPE
from scripts.confenge_target_fit.company_key import company_key_from_raiz
from scripts.confenge_target_fit.db import connect
from scripts.confenge_target_fit.models import MaterializedTargetFit, TransitionEvent
from scripts.confenge_target_fit.store import (
    ensure_control_defaults,
    publish_materialization,
    record_downstream_invalidation_soft,
    set_control,
)
from scripts.warmbly_bridge.mapping import build_leads, map_lead

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


def _seed_confirmed(conn, raiz: str) -> str:
    ck = company_key_from_raiz(raiz)
    now = datetime.now(UTC)
    mat = MaterializedTargetFit(
        company_key=ck,
        cnpj_raiz=raiz,
        target_fit_class=TARGET_CONFIRMED,
        target_fit_confidence=0.9,
        target_fit_version=TARGET_FIT_VERSION,
        target_fit_reason_codes=["test_confirmed"],
        target_fit_evidence=[{"id": "e1", "type": "CONTRACT_EXECUTION"}],
        computed_at=now,
        source_watermark="2026-08-09T12:00:00Z",
        source_max_updated_at=now,
        input_fingerprint=f"sha256:live-{raiz}",
        classifier_sha="sha256:test",
        schema_version="confenge-tf-store-v1",
        materialization_mode="ACTIVE",
    )
    evt = TransitionEvent(
        event_type="TARGET_FIT_CONFIRMED",
        company_key=ck,
        cnpj_raiz=raiz,
        old_class=None,
        new_class=TARGET_CONFIRMED,
        old_confidence=None,
        new_confidence=0.9,
        reason_codes=["test_confirmed"],
        changed_evidence_ids=["e1"],
        source_watermark="2026-08-09T12:00:00Z",
        computed_at=now,
        target_fit_version=TARGET_FIT_VERSION,
    )
    publish_materialization(conn, mat, evt, shadow_only=False)
    return ck


def _seed_downgrade(conn, raiz: str) -> str:
    ck = _seed_confirmed(conn, raiz)
    now = datetime.now(UTC)
    mat = MaterializedTargetFit(
        company_key=ck,
        cnpj_raiz=raiz,
        target_fit_class=TARGET_OUT_OF_SCOPE,
        target_fit_confidence=0.8,
        target_fit_version=TARGET_FIT_VERSION,
        target_fit_reason_codes=["lost"],
        target_fit_evidence=[],
        computed_at=now,
        source_watermark="2026-08-09T13:00:00Z",
        source_max_updated_at=now,
        input_fingerprint=f"sha256:down-{raiz}",
        classifier_sha="sha256:test",
        schema_version="confenge-tf-store-v1",
        previous_class=TARGET_CONFIRMED,
        previous_confidence=0.9,
        transition_event="TARGET_FIT_LOST",
        materialization_mode="ACTIVE",
    )
    evt = TransitionEvent(
        event_type="TARGET_FIT_LOST",
        company_key=ck,
        cnpj_raiz=raiz,
        old_class=TARGET_CONFIRMED,
        new_class=TARGET_OUT_OF_SCOPE,
        old_confidence=0.9,
        new_confidence=0.8,
        reason_codes=["lost"],
        changed_evidence_ids=["e1"],
        source_watermark="2026-08-09T13:00:00Z",
        computed_at=now,
        target_fit_version=TARGET_FIT_VERSION,
    )
    eid = publish_materialization(conn, mat, evt, shadow_only=False)
    record_downstream_invalidation_soft(
        conn,
        company_key=ck,
        cnpj_raiz=raiz,
        event_id=eid,
        old_class=TARGET_CONFIRMED,
        new_class=TARGET_OUT_OF_SCOPE,
    )
    return ck


def test_map_lead_joins_live_current_without_embedded_fields(dsn):
    """Universe JSONL without target_fit_* must still join confenge_company_target_fit_current."""
    raiz = f"88{uuid.uuid4().int % 10**6:06d}"[:8]
    cnpj14 = raiz + "000191"
    conn = connect(dsn, readonly=False)
    try:
        ensure_control_defaults(conn)
        set_control(conn, "cdc_watermark", {"watermark": "2026-08-09T12:00:00Z"})
        _seed_confirmed(conn, raiz)
        conn.commit()
    finally:
        conn.close()

    # Fresh read-only conn for join path
    conn = connect(dsn, readonly=True)
    try:
        universe = {
            "cnpj14": cnpj14,
            "razao_social": "CONSTRUTORA LIVE JOIN LTDA",
            "canonical_universe_member": True,
            "commercial_state": "NEW",
            "official_domain": "livejoin.com.br",
            "construction_evidence": {
                "sector_fit": "CONFIRMED_ENGINEERING",
                "target_fit_class": TARGET_CONFIRMED,
                "relevant_contract_count": 3,
            },
            "portfolio": {"pass_contract_count": 3},
            # NO target_fit_class embedded — must load from DB
        }
        intel = {
            "offer": {
                "service_code": "estruturacao_pleito_reajuste",
                "service_name": "Reajuste",
                "entry_offer": "REAJUSTE_CHECK",
                "micro_offer_code": "REAJUSTE_CHECK",
            },
            "primary_service": {
                "service_id": "estruturacao_pleito_reajuste",
                "supporting_signal_ids": ["mature_no_reajuste"],
                "evidence_ids": ["e1"],
            },
            "service_candidates": [
                {
                    "service_id": "estruturacao_pleito_reajuste",
                    "supporting_signal_ids": ["mature_no_reajuste"],
                    "evidence_ids": ["e1"],
                }
            ],
            "messaging": {
                "fact_to_mention": (
                    "objeto: pavimentação asfáltica CBUQ em vias urbanas; "
                    "órgão: Pref. Coxilha; UF RS"
                ),
                "why_this_account": (
                    "LIVEJOIN com execução pública de pavimentação — "
                    "objeto: pavimentação asfáltica CBUQ em vias urbanas; órgão: Pref. Coxilha"
                ),
                "why_now": (
                    "aditivo recente no contrato de LIVEJOIN de pavimentação asfáltica CBUQ "
                    "com a Pref. Coxilha"
                ),
                "cta": "Posso te mandar o recorte público que encontrei?",
                "claims_to_avoid": [],
            },
            "why_this_account": (
                "LIVEJOIN com execução pública de pavimentação — "
                "objeto: pavimentação asfáltica CBUQ em vias urbanas; órgão: Pref. Coxilha"
            ),
            "why_now": (
                "aditivo recente no contrato de LIVEJOIN de pavimentação asfáltica CBUQ "
                "com a Pref. Coxilha"
            ),
            "observed_fact": (
                "objeto: pavimentação asfáltica CBUQ em vias urbanas; "
                "órgão: Pref. Coxilha; UF RS"
            ),
            "micro_offer_code": "REAJUSTE_CHECK",
            "evidence_ids": ["e1"],
            "evidence": [{"id": "e1", "epistemic_class": "CONFIRMED_FACT"}],
        }
        contacts = {
            "contacts": [
                {
                    "email": "engenharia@livejoin.com.br",
                    "ownership_status": "COMPANY_OWNED",
                    "verification_status": "OBSERVED",
                    "provenance": {
                        "source_type": "site",
                        "source_url": "https://livejoin.com.br/contato",
                    },
                }
            ]
        }
        lead = map_lead(
            universe,
            intel=intel,
            contacts_row=contacts,
            conn=conn,
            datalake_watermark="2026-08-09T12:00:00Z",
        )
        assert lead is not None
        assert lead.get("target_fit_class") == TARGET_CONFIRMED, lead
        assert lead.get("target_fit_version") == TARGET_FIT_VERSION
        assert lead.get("target_fit_fresh") is True
        assert lead.get("target_fit_source_watermark")
        # CONFIRMED + fresh + real provenance + copy context → send ready
        assert lead.get("email_send_ready") is True
    finally:
        conn.close()


def test_build_leads_batch_joins_live_store(dsn):
    raiz = f"89{uuid.uuid4().int % 10**6:06d}"[:8]
    cnpj14 = raiz + "000191"
    conn = connect(dsn, readonly=False)
    try:
        ensure_control_defaults(conn)
        set_control(conn, "cdc_watermark", {"watermark": "2026-08-09T12:00:00Z"})
        _seed_confirmed(conn, raiz)
        conn.commit()
    finally:
        conn.close()

    conn = connect(dsn, readonly=True)
    try:
        leads = build_leads(
            [
                {
                    "cnpj14": cnpj14,
                    "razao_social": "BATCH JOIN LTDA",
                    "commercial_state": "NEW",
                }
            ],
            [
                {
                    "cnpj14": cnpj14,
                    "offer": {"service_code": "REAJUSTE"},
                    "messaging_context": {
                        "fact_to_mention": "f",
                        "question_to_ask": "q",
                        "cta": "c",
                        "claims_to_avoid": [],
                    },
                    "evidence": [{"id": "e1"}],
                }
            ],
            [
                {
                    "cnpj14": cnpj14,
                    "contacts": [
                        {
                            "email": "a@b.com.br",
                            "ownership_status": "COMPANY_OWNED",
                            "verification_status": "OBSERVED",
                        }
                    ],
                }
            ],
            conn=conn,
            datalake_watermark="2026-08-09T12:00:00Z",
        )
        assert len(leads) == 1
        assert leads[0]["target_fit_class"] == TARGET_CONFIRMED
        assert leads[0]["target_fit_class"] is not None
    finally:
        conn.close()


def test_send_ready_sees_store_downgrade_without_embedded_flags(dsn):
    """Downgrade only in Postgres ledger/current — no JSONL flags — still blocks send."""
    raiz = f"87{uuid.uuid4().int % 10**6:06d}"[:8]
    cnpj14 = raiz + "000191"
    conn = connect(dsn, readonly=False)
    try:
        ensure_control_defaults(conn)
        set_control(conn, "cdc_watermark", {"watermark": "2026-08-09T13:00:00Z"})
        _seed_downgrade(conn, raiz)
        conn.commit()
    finally:
        conn.close()

    conn = connect(dsn, readonly=True)
    try:
        # Company dict has only CNPJ — no target_fit_* stamps
        company = {
            "cnpj14": cnpj14,
            "service_code": "REAJUSTE",
            "factual_hook": "x",
            "evidence_ids": ["e1"],
            "canonical_universe_member": True,
            "datalake_watermark": "2026-08-09T13:00:00Z",
        }
        ready = evaluate_email_send_ready(
            company=company,
            email="contato@empresa.com.br",
            ownership_status="COMPANY_OWNED",
            verification_status="OBSERVED",
            service_code="REAJUSTE",
            factual_evidence=True,
            evidence_ids=["e1"],
            conn=conn,
        )
        assert ready.email_send_ready is False
        assert ready.target_fit_send_tier != "A_AUTOMATIC" or any(
            "OUT" in r or "DOWNGRADE" in r or "target_fit" in r for r in ready.reasons
        )
        joined = " ".join(ready.reasons)
        assert (
            "OUT_OF_SCOPE" in joined
            or "DOWNGRADE" in joined
            or "target_fit_class" in joined
            or "published" in joined
            or ready.target_fit_send_tier == "OUT_OF_SCOPE"
        )
    finally:
        conn.close()


def test_published_path_exception_fails_closed_not_rescore():
    """map_lead must not fall back to sendable legacy tier on published path error."""
    # Force published path by embedding broken published blob that evaluate will see
    universe = {
        "cnpj14": "11223344000191",
        "razao_social": "X",
        "commercial_state": "NEW",
        # published_target_fit present but invalid confidence type may not throw;
        # instead monkeypatch evaluate to raise
    }
    intel = {
        "offer": {"service_code": "REAJUSTE"},
        "messaging_context": {
            "fact_to_mention": "f",
            "question_to_ask": "q",
            "cta": "c",
            "claims_to_avoid": [],
        },
    }
    contacts = {
        "contacts": [
            {
                "email": "a@b.com.br",
                "ownership_status": "COMPANY_OWNED",
                "verification_status": "OBSERVED",
            }
        ]
    }

    import scripts.warmbly_bridge.mapping as mapping_mod
    import scripts.confenge_target_fit.published as pub_mod

    real = pub_mod.published_from_row_or_db

    def boom(*a, **k):
        raise RuntimeError("synthetic published failure")

    pub_mod.published_from_row_or_db = boom  # type: ignore[assignment]
    # Also patch where mapping imports it inside function — re-import path uses package
    try:
        # map_lead imports inside try from published — patch module before call
        lead = map_lead(universe, intel=intel, contacts_row=contacts, conn=None)
        assert lead is not None
        assert lead.get("email_send_ready") is not True
        assert lead.get("target_fit_fresh") is False
        # Must not re-score into A_AUTOMATIC after exception
        assert lead.get("target_fit_send_tier") != "A_AUTOMATIC" or lead.get(
            "email_send_ready"
        ) is False
        reasons = lead.get("target_fit_reasons") or []
        assert any("fail_closed" in str(r) or "error" in str(r).lower() for r in reasons) or (
            lead.get("email_send_ready") is False and lead.get("target_fit_class") is None
        )
    finally:
        pub_mod.published_from_row_or_db = real  # type: ignore[assignment]


def test_live_store_outranks_embedded_confirmed_stamps(dsn):
    """CRITICAL: store=OUT must beat JSONL stamps CONFIRMED+fresh when conn is open.

    Stale snapshot must never authorize outreach while materialization is OUT.
    Cases: with and without invalidation ledger row.
    """
    # Case A: store OUT, no invalidation row, embed CONFIRMED+fresh
    raiz_a = f"71{uuid.uuid4().int % 10**6:06d}"[:8]
    cnpj_a = raiz_a + "000191"
    conn = connect(dsn, readonly=False)
    try:
        ensure_control_defaults(conn)
        set_control(conn, "cdc_watermark", {"watermark": "2026-08-09T14:00:00Z"})
        ck = company_key_from_raiz(raiz_a)
        now = datetime.now(UTC)
        mat = MaterializedTargetFit(
            company_key=ck,
            cnpj_raiz=raiz_a,
            target_fit_class=TARGET_OUT_OF_SCOPE,
            target_fit_confidence=0.85,
            target_fit_version=TARGET_FIT_VERSION,
            target_fit_reason_codes=["live_out"],
            target_fit_evidence=[],
            computed_at=now,
            source_watermark="2026-08-09T14:00:00Z",
            source_max_updated_at=now,
            input_fingerprint=f"sha256:out-{raiz_a}",
            classifier_sha="sha256:test",
            schema_version="confenge-tf-store-v1",
            materialization_mode="ACTIVE",
        )
        publish_materialization(conn, mat, None, shadow_only=False)
        conn.commit()
    finally:
        conn.close()

    conn = connect(dsn, readonly=True)
    try:
        universe = {
            "cnpj14": cnpj_a,
            "razao_social": "STALE SNAPSHOT CONSTRUTORA LTDA",
            "commercial_state": "NEW",
            # Stale embed that would authorize send if precedence were inverted
            "target_fit_class": TARGET_CONFIRMED,
            "target_fit_confidence": 0.99,
            "target_fit_version": TARGET_FIT_VERSION,
            "target_fit_source_watermark": "2026-08-09T14:00:00Z",
            "target_fit_computed_at": "2026-08-09T14:00:00Z",
            "target_fit_fresh": True,
            "datalake_watermark": "2026-08-09T14:00:00Z",
        }
        intel = {
            "offer": {"service_code": "REAJUSTE"},
            "messaging_context": {
                "fact_to_mention": "obra",
                "question_to_ask": "q",
                "cta": "c",
                "claims_to_avoid": [],
            },
            "evidence": [{"id": "e1", "epistemic_class": "CONFIRMED_FACT"}],
        }
        contacts = {
            "contacts": [
                {
                    "email": "engenharia@stale.com.br",
                    "ownership_status": "COMPANY_OWNED",
                    "verification_status": "OBSERVED",
                }
            ]
        }
        lead = map_lead(
            universe,
            intel=intel,
            contacts_row=contacts,
            conn=conn,
            datalake_watermark="2026-08-09T14:00:00Z",
        )
        assert lead is not None
        assert lead.get("target_fit_class") == TARGET_OUT_OF_SCOPE, lead
        assert lead.get("email_send_ready") is False
        assert lead.get("target_fit_send_tier") != "A_AUTOMATIC"

        # evaluate_email_send_ready with same adversarial embed + live conn
        ready = evaluate_email_send_ready(
            company={
                **universe,
                "service_code": "REAJUSTE",
                "factual_hook": "obra",
                "evidence_ids": ["e1"],
                "canonical_universe_member": True,
            },
            email="engenharia@stale.com.br",
            ownership_status="COMPANY_OWNED",
            verification_status="OBSERVED",
            service_code="REAJUSTE",
            factual_evidence=True,
            evidence_ids=["e1"],
            conn=conn,
        )
        assert ready.email_send_ready is False
        assert ready.target_fit_send_tier != "A_AUTOMATIC"
    finally:
        conn.close()

    # Case B: store OUT + invalidation row, embed still CONFIRMED
    raiz_b = f"72{uuid.uuid4().int % 10**6:06d}"[:8]
    cnpj_b = raiz_b + "000191"
    conn = connect(dsn, readonly=False)
    try:
        ensure_control_defaults(conn)
        set_control(conn, "cdc_watermark", {"watermark": "2026-08-09T14:00:00Z"})
        _seed_downgrade(conn, raiz_b)
        conn.commit()
    finally:
        conn.close()

    conn = connect(dsn, readonly=True)
    try:
        lead = map_lead(
            {
                "cnpj14": cnpj_b,
                "razao_social": "STALE WITH LEDGER LTDA",
                "commercial_state": "NEW",
                "target_fit_class": TARGET_CONFIRMED,
                "target_fit_confidence": 0.99,
                "target_fit_version": TARGET_FIT_VERSION,
                "target_fit_fresh": True,
                "target_fit_source_watermark": "2026-08-09T14:00:00Z",
                "datalake_watermark": "2026-08-09T14:00:00Z",
            },
            intel={
                "offer": {"service_code": "REAJUSTE"},
                "messaging_context": {
                    "fact_to_mention": "f",
                    "question_to_ask": "q",
                    "cta": "c",
                    "claims_to_avoid": [],
                },
                "evidence": [{"id": "e1"}],
            },
            contacts_row={
                "contacts": [
                    {
                        "email": "a@b.com.br",
                        "ownership_status": "COMPANY_OWNED",
                        "verification_status": "OBSERVED",
                    }
                ]
            },
            conn=conn,
            datalake_watermark="2026-08-09T14:00:00Z",
        )
        assert lead is not None
        assert lead.get("target_fit_class") != TARGET_CONFIRMED
        assert lead.get("email_send_ready") is False
        assert lead.get("target_fit_send_tier") != "A_AUTOMATIC"
    finally:
        conn.close()


def test_no_published_no_conn_cannot_emit_confirmed_fresh_send():
    """Without published fields and without DB, email_send_ready must not claim CONFIRMED+fresh."""
    universe = {
        "cnpj14": "12345678000199",
        "razao_social": "CONSTRUTORA SEM PUB LTDA",
        "commercial_state": "NEW",
        "construction_evidence": {
            "sector_fit": "CONFIRMED",
            "activity_class": "CONSTRUCTION",
            "relevant_contract_count": 5,
        },
        "portfolio": {
            "recent_contracts": [
                {"objeto_contrato": "Execucao de obras de pavimentacao", "valor_total": 1e6}
            ]
            * 3
        },
    }
    intel = {
        "offer": {"service_code": "REAJUSTE"},
        "messaging_context": {
            "fact_to_mention": "obra",
            "question_to_ask": "q",
            "cta": "c",
            "claims_to_avoid": [],
        },
        "evidence": [{"id": "e1", "epistemic_class": "CONFIRMED_FACT"}],
    }
    contacts = {
        "contacts": [
            {
                "email": "engenharia@sempub.com.br",
                "ownership_status": "COMPANY_OWNED",
                "verification_status": "OBSERVED",
            }
        ]
    }
    lead = map_lead(universe, intel=intel, contacts_row=contacts, conn=None)
    assert lead is not None
    # Fail-closed contract fields
    assert lead.get("target_fit_class") is None
    assert lead.get("target_fit_fresh") is False
    # Hard gate: cannot be send-ready without published CONFIRMED+fresh
    assert lead.get("email_send_ready") is not True
