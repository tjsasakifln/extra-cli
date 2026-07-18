"""Tests for DoD §7.2 applicability matrix."""
from __future__ import annotations

from scripts.coverage.applicability_matrix import (
    MANDATORY_SOURCES,
    MIN_SOURCE_COMBINATION,
    ApplicabilityDecision,
    build_matrix,
    decide_for_entity_source,
    write_matrix,
)


def test_min_combination_explicit():
    assert "open_tenders" in MIN_SOURCE_COMBINATION
    assert "pncp" in MIN_SOURCE_COMBINATION["open_tenders"]
    assert "historical_contracts" in MANDATORY_SOURCES


def test_decide_capability_not_on_source():
    d = decide_for_entity_source(
        entity={"esfera": "municipal", "natureza": "pref"},
        entity_id="e1",
        source_name="pncp",
        capability="open_tenders",
        cfg={"sources": {"pncp": {"default_applicable": True, "rules": []}}},
        registry_role="primary",
        validated_at="2026-07-18",
    )
    assert d.decision in {"applicable", "not_applicable", "unknown"}
    assert d.justification
    assert d.validated_at
    assert d.decision_source


def test_build_matrix_sample():
    entities = [
        {"cnpj": "123", "esfera": "municipal", "natureza": "pref", "razao_social": "Pref A"},
        {"cnpj": "456", "esfera": "estadual", "natureza": "gov", "razao_social": "Gov B"},
    ]
    m = build_matrix(entities=entities, limit_entities=None, sources=["pncp", "ciga_ckan", "contracts"])
    assert m["n_entities"] == 2
    assert m["n_decisions"] == 2 * 3 * 2  # entities * sources * caps
    assert m["min_source_combination"]
    assert m["substitution_guard"]["enforced"] is True
    # each decision has justification + decision_source
    for d in m["decisions"]:
        assert d["justification"]
        assert d["decision_source"]
        assert d["validated_at"]
        assert d["capability"] in {"open_tenders", "historical_contracts"}


def test_write_matrix(tmp_path):
    entities = [{"cnpj": "1", "esfera": "municipal", "natureza": "pref"}]
    m = build_matrix(entities=entities, sources=["pncp"], limit_entities=None)
    path = write_matrix(tmp_path, m)
    assert path.is_file()
    assert (tmp_path / "unknown-gaps.json").is_file()
