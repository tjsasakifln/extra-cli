"""Tests for CANONICAL-ENTITY-LINKAGE-01 — pure decisions + isolation + shipped entry points.

No test theater: drives real modules under scripts.linkage and scripts.workspace.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.linkage.isolation import check_dsn, mask_dsn, scan_command_line
from scripts.linkage.keys import (
    conflicting_strong_ids,
    extract_organ_keys,
    extract_person_keys,
    is_valid_cnpj14,
    organ_canonical_key,
    supplier_canonical_key,
)
from scripts.linkage.resolve import (
    decide_contract_to_opportunity,
    decide_opportunity_organ,
    decide_supplier_from_contract,
    refuse_merge_if_conflict,
)

# Known-valid CNPJ for tests (Receita check digits)
VALID_CNPJ_A = "11222333000181"  # may fail check — compute below
VALID_CNPJ_B = "11444777000161"


def _make_cnpj(base12: str) -> str:
    """Build a valid CNPJ14 from 12-digit base."""
    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    def dv(nums: str, weights: list[int]) -> int:
        total = sum(int(n) * w for n, w in zip(nums, weights, strict=True))
        rem = total % 11
        return 0 if rem < 2 else 11 - rem

    d12 = base12[:12]
    d13 = d12 + str(dv(d12, weights1))
    return d13 + str(dv(d13, weights2))


CNPJ1 = _make_cnpj("123456780001")
CNPJ2 = _make_cnpj("987654320001")
assert is_valid_cnpj14(CNPJ1)
assert is_valid_cnpj14(CNPJ2)
assert CNPJ1 != CNPJ2


class TestKeys:
    def test_never_merge_conflicting_cnpj14(self):
        a = extract_organ_keys(CNPJ1, "PREFEITURA A")
        b = extract_organ_keys(CNPJ2, "PREFEITURA B")
        codes = conflicting_strong_ids(a, b)
        assert "conflict_cnpj14" in codes
        refuse = refuse_merge_if_conflict(a, b)
        assert refuse is not None
        assert refuse.classification == "ambiguous"
        assert refuse.target_key is None

    def test_organ_exact_cnpj14(self):
        d = decide_opportunity_organ(CNPJ1, "MUNICIPIO X")
        assert d.classification == "exact"
        assert d.score == 1.0
        assert d.auto_accept
        assert d.target_key == f"org:cnpj14:{CNPJ1}"
        assert d.claim_level == "fact"

    def test_name_only_unresolved(self):
        d = decide_opportunity_organ(None, "SECRETARIA SEM CNPJ")
        assert d.classification == "unresolved"
        assert d.target_key is None
        assert not d.auto_accept

    def test_supplier_canonical_prefers_cnpj14(self):
        k = extract_person_keys(CNPJ1, "FORNECEDOR XYZ LTDA")
        assert supplier_canonical_key(k) == f"sup:cnpj14:{CNPJ1}"

    def test_contract_link_same_organ_is_similarity_not_participation(self):
        d = decide_contract_to_opportunity(
            opp_organ_cnpj=CNPJ1,
            opp_organ_name="ORGAO",
            opp_objeto="REFORMA PREDIAL ESCOLA",
            opp_uf="SC",
            contract_organ_cnpj=CNPJ1,
            contract_organ_name="ORGAO",
            contract_objeto="REFORMA PREDIAL",
            contract_uf="SC",
            contract_id="CTR-1",
            supplier_cnpj=CNPJ2,
        )
        assert d.classification == "exact"
        assert d.claim_level == "similarity"
        assert "not_observed_participant_of_open_tender" in d.non_claims
        assert "similarity_not_participation" in d.non_claims

    def test_different_organ_unresolved(self):
        d = decide_contract_to_opportunity(
            opp_organ_cnpj=CNPJ1,
            opp_organ_name="A",
            opp_objeto="X",
            opp_uf="SC",
            contract_organ_cnpj=CNPJ2,
            contract_organ_name="B",
            contract_objeto="X",
            contract_uf="SC",
            contract_id="CTR-2",
        )
        assert d.classification == "unresolved"
        assert "different_organ" in d.reason_codes or "conflict_cnpj14" in d.reason_codes

    def test_supplier_observed_winner_fact(self):
        d = decide_supplier_from_contract(CNPJ2, "SUP LTDA", contract_id="C1")
        assert d.classification == "exact"
        assert d.claim_level == "fact"
        assert "observed_contract_winner" in d.reason_codes
        assert "not_observed_participant_of_open_tender" in d.non_claims


class TestIsolation:
    def test_local_5438_ok(self):
        chk = check_dsn("postgresql://test:test@127.0.0.1:5438/extra_linkage_rc")
        assert chk.ok
        assert chk.production_touched is False
        assert "***" in mask_dsn("postgresql://test:secret@127.0.0.1:5438/db")

    def test_blocks_ec_prod(self):
        chk = check_dsn("postgresql://u:p@ec-prod.example:5432/extra")
        assert chk.ok is False
        assert chk.production_touched is True
        assert any("ec-prod" in h for h in chk.forbidden_hits)

    def test_blocks_opt_extra_path(self):
        hits = scan_command_line("rsync /opt/extra-consultoria/data x")
        assert any("opt/extra" in h or "extra-consultoria" in h for h in hits)

    def test_blocks_soak_marker(self):
        hits = scan_command_line("cat artifacts/campaigns/X/soak/status.json")
        assert "soak" in hits


class TestShippedEntryPoints:
    def test_linkage_module_importable(self):
        import scripts.linkage as L
        from scripts.linkage import RULE_VERSION

        assert RULE_VERSION == "linkage-v1"
        assert L.RULE_VERSION == RULE_VERSION

    def test_workspace_parser_has_entity(self):
        from scripts.workspace.cli import build_parser

        p = build_parser()
        # parse entity --json
        args = p.parse_args(["entity", "--json"])
        assert args.command == "entity"
        args2 = p.parse_args(["competitors", "--opportunity-id", "1", "--json"])
        assert args2.opportunity_id == 1

    def test_migration_061_present(self):
        root = Path(__file__).resolve().parents[1]
        mig = root / "db" / "migrations" / "061_canonical_entity_linkage.sql"
        assert mig.is_file()
        text = mig.read_text(encoding="utf-8")
        assert "canonical_organs" in text
        assert "opportunity_contract_links" in text
        assert "observed_supplier_relations" in text

    def test_dossier_builder(self):
        from scripts.linkage.dossier import build_dossier, write_dossier

        inv = {
            "run_id": "t1",
            "opportunity_id": 1,
            "status": "OK",
            "opportunity": {"id": 1, "orgao_cnpj": CNPJ1, "objeto": "x"},
            "organs": [{"classification": "exact", "score": 1.0}],
            "contracts": [],
            "observed_suppliers": [
                {
                    "supplier_canonical_key": f"sup:cnpj14:{CNPJ2}",
                    "relation_kind": "historical_winner",
                    "classification": "exact",
                    "score": 1.0,
                    "contract_id": "C",
                    "claim_level": "fact",
                }
            ],
            "claims": ["organ_identity_from_official_keys"],
            "non_claims": ["not_observed_participant_of_open_tender"],
        }
        d = build_dossier(inv, metrics={"x": 1})
        assert d["campaign_id"] == "CANONICAL-ENTITY-LINKAGE-01"
        assert "not_observed_participant_of_open_tender" in d["non_claims"]
        out = write_dossier(d, Path(os.environ.get("TMPDIR", "/tmp")) / "linkage-dossier-test")
        assert Path(out["html"]).is_file()
        assert Path(out["json"]).is_file()


@pytest.mark.real_db
def test_linkage_pipeline_on_isolated_dsn():
    dsn = os.environ.get("LINKAGE_TEST_DSN")
    if not dsn:
        pytest.skip("LINKAGE_TEST_DSN not set")
    from scripts.linkage.isolation import check_dsn
    from scripts.linkage.pipeline import connect, run_linkage

    chk = check_dsn(dsn)
    if not chk.ok:
        pytest.skip(f"DSN not isolated: {chk.as_dict()}")
    conn = connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.entity_linkage_runs') AS t")
            row = cur.fetchone()
            reg = row["t"] if isinstance(row, dict) else row[0]
            if reg is None:
                pytest.skip("migration 061 not applied")
            cur.execute("SELECT count(*) AS n FROM opportunity_intel WHERE is_active")
            row = cur.fetchone()
            n = int(row["n"] if isinstance(row, dict) else row[0])
            if n == 0:
                pytest.skip("no opportunities seeded")
    finally:
        conn.close()

    res = run_linkage(dsn, run_id="test-pytest-linkage", contract_limit_per_opp=10, max_opportunities=3)
    assert res.status == "completed"
    assert res.production_touched is False
    assert res.metrics["organ_links"]["total"] >= 1
    # unresolved stay in denominator
    assert res.metrics["organ_links"]["unresolved_in_denominator"] is True
    assert res.metrics["organ_links"]["hard_cases_excluded"] is False
