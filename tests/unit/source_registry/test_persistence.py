from scripts.source_registry.models import EntitySourceRecord
from scripts.source_registry.persistence import COLUMNS, record_to_row


def test_record_to_row_preserves_explicit_unknowns_and_evidence():
    record = EntitySourceRecord(
        canonical_id="1:A",
        razao_social="A",
        cnpj="12345678",
        natureza_juridica="autarquia",
        municipio="X",
        portal_licitacoes=None,
        access_status="unknown",
        current_blocker="fragmented",
        evidences=[{"type": "manual_review", "result": "unknown"}],
    )
    row = dict(zip(COLUMNS, record_to_row(record), strict=True))
    assert row["portal_licitacoes"] is None
    assert row["access_status"] == "unknown"
    assert row["current_blocker"] == "fragmented"
    assert row["evidences"][0]["result"] == "unknown"
