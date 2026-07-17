"""Tests for promote_from_evidence acquisition strategy."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from scripts.source_registry.acquisition.promote_from_evidence import (
    normalize_registry_blockers,
    promote_from_pipeline_evidence,
    resolve_provenance_for_sources,
)
from scripts.source_registry.gap_report import derive_blocker_class, gap_rows
from scripts.source_registry.models import EntitySourceRecord, is_strict_operational


def _full_provenance(**overrides: object) -> dict:
    base = {
        "pipeline_run_id": "run-test-001",
        "run_id": "run-test-001",
        "raw_uri": "/tmp/fake/contratacoes.jsonl",
        "raw_sha256": "a" * 64,
        "normalized_record_ids": ["pncp:83102343:1"],
        "reconciliation_id": "recon-test-001",
        "provenance_source": "/tmp/fake/evidence.json",
    }
    base.update(overrides)
    return base


@pytest.mark.unit
def test_promote_sets_verified_strict_operational_with_provenance() -> None:
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
        sla_hours=24,
    )
    fake_evidence = [
        {
            "entity_db_id": 82,
            "cnpj_8": "83102343",
            "razao_social": "MUNICIPIO DE BRUSQUE",
            "municipio": "BRUSQUE",
            "sources": ["pncp"],
            "is_covered": True,
            "last_seen_at": datetime.now(UTC),
            "total_bids": 5,
            "normalized": True,
            "reconciled": True,
            "opp_count": 0,
            "official_act_matches": 0,
            "provenance": _full_provenance(),
        }
    ]
    with patch(
        "scripts.source_registry.acquisition.promote_from_evidence.fetch_pipeline_evidence",
        return_value=fake_evidence,
    ):
        summary = promote_from_pipeline_evidence([rec], persist=False)

    assert summary["promoted"] == 1
    assert summary["dry_run"] is False
    assert rec.access_status == "verified"
    assert rec.last_success_at is not None
    assert rec.current_blocker is None
    assert is_strict_operational(rec) is True
    ev = next(e for e in rec.evidences if e.get("type") == "pipeline_evidence_promote")
    assert ev["dry_run"] is False
    assert ev["run_id"] == "run-test-001"
    assert ev["raw_sha256"] == "a" * 64
    assert ev["normalized_record_ids"]
    assert ev["reconciliation_id"]
    stages = ev["stages"]
    assert stages["collected"] is True
    assert stages["normalized"] is True
    assert stages["reconciled"] is True
    assert stages["verified_within_sla"] is True


@pytest.mark.unit
def test_promote_skips_without_provenance() -> None:
    rec = EntitySourceRecord(
        canonical_id="83102343:MUNICIPIO_DE_BRUSQUE",
        razao_social="MUNICIPIO DE BRUSQUE",
        cnpj="83102343",
        natureza_juridica="prefeitura",
        municipio="BRUSQUE",
        access_status="mapped",
        current_blocker="pending_collection",
        plataformas=["pncp"],
    )
    fake_evidence = [
        {
            "entity_db_id": 82,
            "cnpj_8": "83102343",
            "sources": ["pncp"],
            "is_covered": True,
            "last_seen_at": datetime.now(UTC),
            "total_bids": 5,
            "normalized": True,
            "reconciled": True,
            # no provenance and no on-disk artifact → skip
        }
    ]
    with (
        patch(
            "scripts.source_registry.acquisition.promote_from_evidence.fetch_pipeline_evidence",
            return_value=fake_evidence,
        ),
        patch(
            "scripts.source_registry.acquisition.promote_from_evidence.resolve_provenance_for_sources",
            return_value=None,
        ),
    ):
        summary = promote_from_pipeline_evidence([rec], persist=False)
    assert summary["promoted"] == 0
    assert rec.access_status == "mapped"


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
        "last_seen_at": datetime.now(UTC),
        "sources": ["pncp"],
        "is_covered": True,
        "normalized": True,
        "reconciled": True,
        "provenance": _full_provenance(),
    }
    with patch(
        "scripts.source_registry.acquisition.promote_from_evidence.fetch_pipeline_evidence",
        return_value=[dict(base, entity_db_id=1), dict(base, entity_db_id=2)],
    ):
        summary = promote_from_pipeline_evidence([rec], persist=False)
    assert summary["promoted"] == 0
    assert summary["unmatched_registry_skipped"] == 1
    assert rec.access_status == "mapped"


@pytest.mark.unit
def test_resolve_provenance_from_real_pncp_artifact() -> None:
    """Uses on-disk crawl evidence when present (real shipped path)."""
    prov = resolve_provenance_for_sources(
        ["pncp"],
        entity_key="test-entity",
        last_seen_iso=datetime.now(UTC).isoformat(),
        record_ids=["x1"],
    )
    if prov is None:
        pytest.skip("no pncp_sc evidence.json artifacts in this checkout")
    assert prov["run_id"]
    assert prov["raw_uri"]
    assert len(prov["raw_sha256"]) >= 32
    assert prov["normalized_record_ids"] == ["x1"]
    assert prov["reconciliation_id"].startswith("recon-")
