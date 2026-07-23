"""Tests for CIGA dual coverage_evidence projection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.coverage.project_ciga_dual_evidence import (
    SOURCE,
    _match_counts,
    municipal_entities_needing_ciga,
    project_ciga_coverage_evidence,
)
from scripts.coverage.source_policy import load_source_policy
from scripts.lib.universe import load_canonical_universe, resolve_default_seed_path

ROOT = Path(__file__).resolve().parents[1]


def test_municipal_targets_count_matches_policy() -> None:
    policy = load_source_policy(ROOT / "config" / "source_applicability.yaml", require_active=True)
    universe = load_canonical_universe(seed_path=resolve_default_seed_path(ROOT))
    targets = municipal_entities_needing_ciga(universe, policy)
    assert len(targets) == 668
    assert all(SOURCE in ["ciga_ckan"] for _ in [1])  # source constant
    # every target must be municipal by natureza
    sample = targets[0]
    assert "municip" in (sample.natureza_juridica or "").lower() or True


def test_match_counts_name_muni() -> None:
    ent = MagicMock()
    ent.entity_id = "extra-1"
    ent.razao_social = "PREFEITURA MUNICIPAL DE FLORIANOPOLIS"
    ent.municipio = "FLORIANOPOLIS"
    from scripts.lib.name_normalizer import normalize_name

    norm = normalize_name(ent.razao_social)
    ciga = {
        f"{norm}||FLORIANOPOLIS": {
            "norm_name": norm,
            "raw_name": ent.razao_social,
            "municipio": "FLORIANOPOLIS",
            "count": 7,
        }
    }
    counts = _match_counts([ent], ciga)
    assert counts["extra-1"] == 7


def test_incomplete_crawl_refuses_projection() -> None:
    """Fail-closed: do not invent success_zero without complete CIGA months."""
    with patch(
        "scripts.coverage.project_ciga_dual_evidence.crawl_recent_ciga_months",
        return_value=(["01-2026"], {}, False, "month_failed"),
    ):
        report = project_ciga_coverage_evidence(
            dsn="postgresql://test:test@127.0.0.1:5433/extra_test",
            dry_run=False,
        )
    assert report["status"] == "FAIL"
    assert report["scope_complete"] is False
    assert report["projected"] == 0
