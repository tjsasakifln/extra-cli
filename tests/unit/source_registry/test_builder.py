"""Unit tests for entity source registry builder + gap report."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.source_registry.builder import (
    EXPECTED_ENTITY_COUNT,
    build_registry_from_csv,
    find_by_cnpj,
    summarize_registry,
)
from scripts.source_registry.gap_report import gap_rows, generate_gap_report
from scripts.source_registry.models import OPERATIONAL_STATUSES, EntitySourceRecord
from scripts.source_registry.acquisition.ciga_municipio_expand import expand_ciga_by_municipio
from scripts.source_registry.acquisition.pncp_orgao_probe import probe_pncp_orgaos

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SEED_CSV = PROJECT_ROOT / "config" / "target_entities_200km.csv"


@pytest.fixture(scope="module")
def registry(tmp_path_factory: pytest.TempPathFactory) -> list[EntitySourceRecord]:
    """Build registry once per module into a temp dir (no clobber of data/)."""
    tmp = tmp_path_factory.mktemp("registry")
    records = build_registry_from_csv(
        SEED_CSV,
        persist=True,
        registry_path=tmp / "entity_source_registry.jsonl",
        summary_path=tmp / "entity_source_registry_summary.json",
    )
    return records


@pytest.mark.unit
class TestBuildRegistry:
    def test_builds_exactly_1093_records(self, registry: list[EntitySourceRecord]) -> None:
        assert len(registry) == EXPECTED_ENTITY_COUNT
        assert len(registry) == 1093

    def test_every_record_has_access_status_and_next_action(
        self, registry: list[EntitySourceRecord]
    ) -> None:
        for rec in registry:
            assert rec.access_status, f"missing access_status: {rec.canonical_id}"
            assert rec.next_action, f"missing next_action: {rec.canonical_id}"
            assert rec.canonical_id
            assert rec.razao_social
            assert rec.natureza_juridica

    def test_no_entity_missing(self, registry: list[EntitySourceRecord]) -> None:
        """Every CSV row produces a unique canonical_id."""
        ids = [r.canonical_id for r in registry]
        assert len(ids) == len(set(ids))
        # All have CNPJ (partial ok)
        assert all(r.cnpj for r in registry)

    def test_all_have_pncp_platform_seed(self, registry: list[EntitySourceRecord]) -> None:
        missing = [r.canonical_id for r in registry if "pncp" not in r.plataformas]
        assert missing == []

    def test_municipal_have_ciga_or_dom(self, registry: list[EntitySourceRecord]) -> None:
        mun = [
            r
            for r in registry
            if r.natureza_juridica
            in {
                "prefeitura",
                "camara_municipal",
                "secretaria_municipal",
                "autarquia_municipal",
                "fundacao_municipal",
            }
        ]
        assert mun
        for r in mun:
            assert "ciga_ckan" in r.plataformas or "dom_sc" in r.plataformas

    def test_summary_counts(self, registry: list[EntitySourceRecord]) -> None:
        summary = summarize_registry(registry)
        assert summary["total_entities"] == 1093
        assert "by_status" in summary
        assert "by_blocker" in summary
        assert summary["mapped_pct"] >= 0

    def test_find_by_cnpj(self, registry: list[EntitySourceRecord]) -> None:
        sample = registry[0]
        hits = find_by_cnpj(registry, sample.cnpj)
        assert hits
        assert any(h.canonical_id == sample.canonical_id for h in hits)

    def test_to_dict_roundtrip(self, registry: list[EntitySourceRecord]) -> None:
        rec = registry[0]
        restored = EntitySourceRecord.from_dict(rec.to_dict())
        assert restored.canonical_id == rec.canonical_id
        assert restored.access_status == rec.access_status
        assert restored.plataformas == rec.plataformas


@pytest.mark.unit
class TestGapReport:
    def test_gap_report_groups_by_blocker(
        self, registry: list[EntitySourceRecord], tmp_path: Path
    ) -> None:
        summary = generate_gap_report(registry, output_dir=tmp_path)
        assert summary["total_entities"] == 1093
        assert summary["gaps"] == len(gap_rows(registry))
        assert "by_blocker_class" in summary
        assert isinstance(summary["by_blocker_class"], dict)
        # All non-operational entities are gaps
        operational = sum(1 for r in registry if r.access_status in OPERATIONAL_STATUSES)
        assert summary["gaps"] == 1093 - operational

        jsonl = tmp_path / "entity-source-gaps.jsonl"
        md = tmp_path / "entity-source-gaps.md"
        assert jsonl.exists()
        assert md.exists()
        lines = [ln for ln in jsonl.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == summary["gaps"]
        # Each line is valid JSON with required fields
        row = json.loads(lines[0])
        for key in (
            "canonical_id",
            "name",
            "municipio",
            "blocker_class",
            "next_action",
            "priority",
            "strategy",
        ):
            assert key in row

    def test_gap_rows_exclude_operational(self) -> None:
        recs = [
            EntitySourceRecord(
                canonical_id="1",
                razao_social="A",
                cnpj="123",
                natureza_juridica="prefeitura",
                municipio="X",
                access_status="collected",  # only collected/verified/operational close gaps
                next_action="monitor",
                current_blocker="none",
                last_success_at="2026-07-17T00:00:00+00:00",
            ),
            EntitySourceRecord(
                canonical_id="2",
                razao_social="B",
                cnpj="456",
                natureza_juridica="prefeitura",
                municipio="Y",
                access_status="unknown",
                next_action="probe",
                current_blocker="no_api",
            ),
            EntitySourceRecord(
                canonical_id="3",
                razao_social="C",
                cnpj="789",
                natureza_juridica="prefeitura",
                municipio="Z",
                access_status="mapped",
                next_action="ingest_ciga_dom_publications_for_municipio",
                current_blocker="none",  # must be derived — never bare none in gaps
                collection_strategy="ciga_ckan_shared_municipio",
            ),
        ]
        rows = gap_rows(recs)
        assert len(rows) == 2
        by_id = {r["canonical_id"]: r for r in rows}
        assert "1" not in by_id
        assert by_id["2"]["blocker_class"] == "no_api"
        assert by_id["3"]["blocker_class"] != "none"
        assert by_id["3"]["blocker_class"] == "pending_collection"
        assert by_id["3"]["cause"] == "pending_collection"


@pytest.mark.unit
class TestAcquisitionStrategies:
    def test_pncp_orgao_probe_local_hit_updates_status(self) -> None:
        rec = EntitySourceRecord(
            canonical_id="83169623:MUNICIPIO_DE_JOINVILLE",
            razao_social="MUNICIPIO DE JOINVILLE",
            cnpj="83169623",
            natureza_juridica="prefeitura",
            municipio="JOINVILLE",
            access_status="unknown",
            next_action="probe_pncp",
            collection_strategy="pncp_cnpj_lookup",
            plataformas=["pncp"],
            current_blocker="none",
        )
        local_index = {
            "83169623": {
                "cnpj14": "83169623000110",
                "razao_social": "MUNICIPIO DE JOINVILLE",
                "sample_count": 3,
                "sources": ["output/pncp_sc/fake.jsonl"],
            }
        }
        summary = probe_pncp_orgaos(
            [rec],
            limit=10,
            dry_run=True,
            persist=False,
            local_index=local_index,
        )
        assert summary["local_hits"] == 1
        assert summary["updated"] == 1
        # Offline local index hit maps path only — NOT operational accessible/collected
        assert rec.access_status == "mapped"
        assert rec.current_blocker == "pending_live_verification"
        assert rec.last_success_at is None
        assert rec.external_ids.get("cnpj14") == "83169623000110"
        assert any(e.get("type") == "pncp_orgao_probe" for e in rec.evidences)
        assert any(e.get("outcome") == "local_hit_index_only" for e in rec.evidences)

    def test_pncp_orgao_probe_records_miss_evidence(self) -> None:
        rec = EntitySourceRecord(
            canonical_id="99999999:FAKE",
            razao_social="FAKE ENTITY",
            cnpj="99999999",
            natureza_juridica="prefeitura",
            municipio="NOWHERE",
            access_status="unknown",
            next_action="probe",
            plataformas=["pncp"],
        )
        summary = probe_pncp_orgaos(
            [rec],
            limit=5,
            dry_run=True,
            persist=False,
            local_index={},
        )
        assert summary["attempted"] == 1
        assert summary["local_hits"] == 0
        assert rec.last_attempt_at is not None
        assert any(e.get("type") == "pncp_orgao_probe" for e in rec.evidences)

    def test_ciga_municipio_expand_links_all_municipal(self) -> None:
        recs = [
            EntitySourceRecord(
                canonical_id="1:PREF",
                razao_social="MUNICIPIO DE TESTE",
                cnpj="11111111",
                natureza_juridica="prefeitura",
                municipio="TESTE",
                ibge_code="4200001",
                access_status="unknown",
                next_action="x",
                plataformas=["pncp"],
                external_ids={"sphere": "municipal"},
                priority=1,
            ),
            EntitySourceRecord(
                canonical_id="2:CAM",
                razao_social="CAMARA DE TESTE",
                cnpj="22222222",
                natureza_juridica="camara_municipal",
                municipio="TESTE",
                ibge_code="4200001",
                access_status="source_not_identified",
                next_action="x",
                plataformas=["pncp"],
                external_ids={"sphere": "municipal"},
                priority=1,
            ),
            EntitySourceRecord(
                canonical_id="3:FED",
                razao_social="ORGAO FEDERAL",
                cnpj="33333333",
                natureza_juridica="orgao_federal",
                municipio="TESTE",
                ibge_code="4200001",
                access_status="unknown",
                next_action="x",
                plataformas=["pncp"],
                external_ids={"sphere": "federal"},
                priority=4,
            ),
        ]
        summary = expand_ciga_by_municipio(recs, persist=False)
        assert summary["entities_linked"] == 2
        assert recs[0].access_status == "mapped"
        assert recs[1].access_status == "mapped"
        assert recs[0].current_blocker == "pending_collection"
        assert recs[0].last_success_at is None  # path known ≠ operational success
        assert "ciga_ckan" in recs[0].plataformas
        assert "ciga_ckan" in recs[1].plataformas
        assert recs[0].diario_oficial
        # Federal untouched
        assert recs[2].access_status == "unknown"
        assert "ciga_ckan" not in recs[2].plataformas
