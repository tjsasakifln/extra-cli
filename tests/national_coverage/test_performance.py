"""Coverage work stays on publisher aggregates, not a 4.5M rewrite."""

from __future__ import annotations

import inspect
import time

from scripts.national_coverage import corpus as corpus_mod
from scripts.national_coverage.corpus import snapshot_from_publishers
from scripts.national_coverage.evaluate import evaluate_from_dict
from scripts.national_coverage.models import MAX_INMEMORY_CONTRACT_ROWS, CorpusPublisher


def test_select_path_is_group_by_aggregate() -> None:
    source = inspect.getsource(corpus_mod)
    assert "GROUP BY" in corpus_mod.CORPUS_SELECT_SQL
    assert "rewrite" in source.lower()
    assert MAX_INMEMORY_CONTRACT_ROWS <= 50_000


def test_evaluate_bounded_publisher_catalog() -> None:
    orgs = [{"org_id": f"{index:014d}", "name": f"Org {index}", "uf": "SC"} for index in range(200)]
    pubs = [CorpusPublisher(f"{index:014d}", 1, "SC", last_seen="2026-08-15T00:00:00Z") for index in range(40)]
    started = time.perf_counter()
    payload = evaluate_from_dict(
        {
            "official": {
                "status": "AVAILABLE",
                "source": "pncp",
                "source_url": "https://pncp.gov.br/api/pncp/v1/orgaos",
                "competence": "contratos-2026",
                "cutoff": "2026-08-16T00:00:00Z",
                "as_of": "2026-08-16T00:00:00Z",
                "raw_hash": "perf-raw",
                "method_version": "pncp-orgaos-publicantes-v1",
                "orgs": orgs,
            },
            "corpus": {
                "as_of": "2026-08-16T00:00:00Z",
                "source": "pncp_supplier_contracts",
                "publishers": [
                    {
                        "raw_org_id": pub.raw_org_id,
                        "contract_count": pub.contract_count,
                        "uf": pub.uf,
                        "last_seen": pub.last_seen,
                    }
                    for pub in pubs
                ],
            },
            "request": {
                "geography": "BR",
                "period": "2026-01/2026-08",
                "source": "pncp",
                "grain": "publishing_org",
            },
        }
    )
    elapsed = time.perf_counter() - started
    assert payload["verdict"] == "PARTIAL"
    assert payload["national_claim_authorized"] is False
    assert payload["partitions"]["expected"] == 200
    assert elapsed < 2.0
    again = snapshot_from_publishers(pubs, as_of="2026-08-16T00:00:00Z", source="pncp_supplier_contracts")
    assert again.publisher_count == 40
