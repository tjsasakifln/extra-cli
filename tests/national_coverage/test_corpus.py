"""Corpus snapshot and publisher mapping without contract rewrite."""

from __future__ import annotations

import pytest

from scripts.national_coverage.corpus import (
    CORPUS_SELECT_SQL,
    aggregate_contract_rows,
    map_publishers,
    snapshot_from_publishers,
)
from scripts.national_coverage.models import (
    MAX_INMEMORY_CONTRACT_ROWS,
    CorpusPublisher,
    NationalCoverageError,
    PublishingOrg,
)
from scripts.national_coverage.universe import build_official_universe


def _universe(*orgs: PublishingOrg):
    return build_official_universe(
        source="pncp",
        source_url="https://pncp.gov.br/api/pncp/v1/orgaos",
        competence="contratos-2026",
        cutoff="2026-08-16T00:00:00Z",
        as_of="2026-08-16T00:00:00Z",
        raw_hash="raw",
        orgs=orgs,
    )


def test_snapshot_from_publishers_is_deterministic() -> None:
    pubs = (
        CorpusPublisher("11111111000191", 4, "SC", last_seen="2026-08-15T00:00:00Z"),
        CorpusPublisher("99999999000191", 1, "SC", last_seen="2026-08-01T00:00:00Z"),
    )
    first = snapshot_from_publishers(pubs, as_of="2026-08-16T00:00:00Z", source="pncp_supplier_contracts")
    second = snapshot_from_publishers(pubs, as_of="2026-08-16T00:00:00Z", source="pncp_supplier_contracts")
    assert first.snapshot_id == second.snapshot_id
    assert first.snapshot_hash == second.snapshot_hash
    assert first.contract_count == 5
    assert first.publisher_count == 2
    assert first.relation == "pncp_supplier_contracts_aggregate"


def test_aggregate_contract_rows_groups_without_rewrite() -> None:
    rows = [
        {"org_id": "11111111000191", "uf": "SC", "published_at": "2026-01-01T00:00:00Z"},
        {"org_id": "11111111000191", "uf": "SC", "published_at": "2026-08-01T00:00:00Z"},
        {"orgao_cnpj": "22222222000191", "uf": "SP", "data_publicacao": "2026-03-01T00:00:00Z"},
    ]
    snapshot = aggregate_contract_rows(rows, as_of="2026-08-16T00:00:00Z", source="fixture")
    assert snapshot.publisher_count == 2
    assert snapshot.contract_count == 3
    by_id = {pub.raw_org_id: pub for pub in snapshot.publishers}
    assert by_id["11111111000191"].contract_count == 2
    assert by_id["11111111000191"].last_seen == "2026-08-01T00:00:00Z"


def test_inmemory_rewrite_of_full_corpus_is_refused() -> None:
    too_many = [{"org_id": "1", "uf": "SC"}] * (MAX_INMEMORY_CONTRACT_ROWS + 1)
    with pytest.raises(NationalCoverageError, match="inmemory_contract_rewrite_refused"):
        aggregate_contract_rows(too_many, as_of="2026-08-16T00:00:00Z", source="fixture")


def test_mapping_mapped_unmapped_alias_duplicate_conflict() -> None:
    universe = _universe(
        PublishingOrg("11111111000191", "A", 1, "SC", aliases=("11111111",)),
        PublishingOrg("22222222000191", "B", 1, "SP"),
        PublishingOrg("33333333000191", "C", 1, "RS", aliases=("shared-alias",)),
        PublishingOrg("44444444000191", "D", 1, "PR", aliases=("shared-alias",)),
    )
    snapshot = snapshot_from_publishers(
        (
            CorpusPublisher("11111111000191", 2, "SC"),
            CorpusPublisher("11111111", 1, "SC"),
            CorpusPublisher("unmapped-org", 1, "SC"),
            CorpusPublisher("dup-org", 1, "SC"),
            CorpusPublisher("dup-org", 3, "PR"),
            CorpusPublisher("shared-alias", 1, "RS"),
        ),
        as_of="2026-08-16T00:00:00Z",
        source="fixture",
    )
    mapping = map_publishers(snapshot, universe)
    assert mapping.mapped >= 1
    assert mapping.unmapped >= 1
    assert mapping.duplicate >= 1
    assert mapping.conflict >= 1
    assert mapping.alias >= 1
    assert mapping.unresolved_identities == mapping.unmapped + mapping.conflict
    statuses = {record.status for record in mapping.records}
    assert statuses >= {"MAPPED", "UNMAPPED", "DUPLICATE", "CONFLICT", "ALIAS"}


def test_corpus_select_is_aggregate_only() -> None:
    sql = " ".join(CORPUS_SELECT_SQL.split())
    assert "GROUP BY" in sql
    assert "SELECT *" not in sql.upper().replace("\n", " ")
    assert "pncp_supplier_contracts" in sql
