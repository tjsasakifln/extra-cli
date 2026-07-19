"""Unit tests for baseline data contracts (Pydantic). Pandera pilot compares later."""
from __future__ import annotations

import pytest

from scripts.data_contracts.entity import (
    CanonicalEntity,
    CoverageEvidence,
    validate_coverage_evidence,
    validate_entities,
)


def test_entity_accepts_valid_cnpj8():
    e = CanonicalEntity(cnpj_8="12.345.678/0001-90", razao_social="PREFEITURA X", raio_200km=True)
    assert e.cnpj_8 == "12345678"


def test_entity_rejects_bad_cnpj():
    with pytest.raises(Exception):
        CanonicalEntity(cnpj_8="123", razao_social="X")


def test_entity_rejects_partial_coords():
    with pytest.raises(Exception):
        CanonicalEntity(cnpj_8="12345678", razao_social="X", latitude=-27.5)


def test_success_zero_requires_provenance():
    with pytest.raises(Exception):
        CoverageEvidence(
            entity_cnpj_8="12345678",
            capability="open_tenders",
            source="pncp",
            result="success_zero",
            run_id="run-1",
        )


def test_success_zero_ok_with_hash():
    e = CoverageEvidence(
        entity_cnpj_8="12345678",
        capability="open_tenders",
        source="pncp",
        result="success_zero",
        run_id="run-1",
        content_hash="abc",
    )
    assert e.result == "success_zero"


def test_batch_validation_separates_bad():
    ok, bad = validate_entities(
        [
            {"cnpj_8": "12345678", "razao_social": "OK"},
            {"cnpj_8": "bad", "razao_social": "NO"},
        ]
    )
    assert len(ok) == 1
    assert len(bad) == 1
    assert "cnpj_8" in bad[0]["error"]


def test_batch_coverage_evidence():
    ok, bad = validate_coverage_evidence(
        [
            {
                "entity_cnpj_8": "12345678",
                "capability": "historical_contracts",
                "source": "pncp",
                "result": "success",
                "run_id": "r1",
                "raw_uri": "https://pncp.gov.br/api/x",
            },
            {
                "entity_cnpj_8": "12345678",
                "capability": "historical_contracts",
                "source": "pncp",
                "result": "success_zero",
                "run_id": "r2",
            },
        ]
    )
    assert len(ok) == 1
    assert len(bad) == 1
