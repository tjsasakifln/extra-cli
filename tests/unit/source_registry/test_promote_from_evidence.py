"""Tests for promote_from_evidence acquisition strategy."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from scripts.source_registry.acquisition.promote_from_evidence import (
    normalize_registry_blockers,
    promote_from_pipeline_evidence,
)
from scripts.source_registry.gap_report import derive_blocker_class, gap_rows
from scripts.source_registry.models import EntitySourceRecord


@pytest.mark.unit
def test_promote_sets_collected_with_pipeline_evidence() -> None:
    rec = EntitySourceRecord(
        canonical_id="83102343:MUNICIPIO_DE_BRUSQUE",
        razao_social="MUNICIPIO DE BRUSQUE",
        cnpj="83102343",
        natureza_juridica="prefeitura",
        municipio="BRUSQUE",
        access_status="mapped",
        next_action="pending",
        current_blocker="pending_collection",
        plataformas=["pncp"],
    )
    fake_evidence = [
        {
            "entity_db_id": 82,
            "cnpj_8": "83102343",
            "razao_social": "MUNICIPIO DE BRUSQUE",
            "municipio": "BRUSQUE",
            "sources": ["pncp"],
            "is_covered": True,
            "last_seen_at": datetime.now(timezone.utc),
            "total_bids": 5,
            "normalized": True,
            "reconciled": True,
            "opp_count": 0,
            "official_act_matches": 0,
        }
    ]
    with patch(
        "scripts.source_registry.acquisition.promote_from_evidence.fetch_pipeline_evidence",
        return_value=fake_evidence,
    ):
        summary = promote_from_pipeline_evidence([rec], persist=False)

    assert summary["promoted"] == 1
    assert summary["dry_run"] is False
    assert rec.access_status in {"collected", "verified"}
    assert rec.last_success_at is not None
    # Collected evidence is still a gap until raw/hash/reconciliation/SLA
    # attestation satisfies the strict operational contract.
    assert rec.current_blocker not in {None, "none"}
    assert any(
        e.get("type") == "pipeline_evidence_promote" and e.get("dry_run") is False
        for e in rec.evidences
    )
    stages = next(e for e in rec.evidences if e.get("type") == "pipeline_evidence_promote")["stages"]
    assert stages["collected"] is True
    assert stages["normalized"] is True
    assert stages["reconciled"] is True


@pytest.mark.unit
def test_normalize_blockers_eliminates_none() -> None:
    recs = [
        EntitySourceRecord(
            canonical_id="1",
            razao_social="A",
            cnpj="111",
            natureza_juridica="prefeitura",
            municipio="X",
            access_status="mapped",
            next_action="ingest_ciga_dom_publications_for_municipio",
            current_blocker="none",
            collection_strategy="ciga_ckan_shared_municipio",
        ),
        EntitySourceRecord(
            canonical_id="2",
            razao_social="B",
            cnpj="222",
            natureza_juridica="orgao_estadual",
            municipio="Y",
            access_status="unknown",
            next_action="x",
            current_blocker=None,
            collection_strategy="sc_compras_and_doe_sc",
        ),
    ]
    summary = normalize_registry_blockers(recs, persist=False)
    assert summary["fixed"] >= 1
    assert recs[0].current_blocker not in {None, "none"}
    assert recs[1].current_blocker not in {None, "none"}
    rows = gap_rows(recs)
    assert all(r["blocker_class"] != "none" for r in rows)


@pytest.mark.unit
def test_derive_blocker_never_none_for_gaps() -> None:
    rec = EntitySourceRecord(
        canonical_id="x",
        razao_social="Z",
        cnpj="000",
        natureza_juridica="prefeitura",
        municipio="Z",
        access_status="mapped",
        next_action="ingest_ciga",
        current_blocker="none",
        collection_strategy="ciga_ckan_shared_municipio",
    )
    assert derive_blocker_class(rec) != "none"


@pytest.mark.unit
def test_promote_rejects_ambiguous_cnpj_root() -> None:
    rec = EntitySourceRecord(
        canonical_id="shared-root",
        razao_social="ORGAO A",
        cnpj="00394494",
        natureza_juridica="orgao_estadual",
        municipio="FLORIANOPOLIS",
        access_status="mapped",
    )
    base = {
        "cnpj_8": "00394494",
        "last_seen_at": datetime.now(timezone.utc),
        "sources": ["pncp"],
        "is_covered": True,
        "normalized": True,
        "reconciled": True,
    }
    with patch(
        "scripts.source_registry.acquisition.promote_from_evidence.fetch_pipeline_evidence",
        return_value=[dict(base, entity_db_id=1), dict(base, entity_db_id=2)],
    ):
        summary = promote_from_pipeline_evidence([rec], persist=False)
    assert summary["promoted"] == 0
    assert summary["unmatched_registry_skipped"] == 1
    assert rec.access_status == "mapped"
