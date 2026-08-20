"""Drive the shipped producer: eight packs, provenance, hash replay."""

from __future__ import annotations

from scripts.bofu_evidence.hashutil import hash_without_content_hash
from scripts.bofu_evidence.models import (
    COMPARABLE_PERTINENT_FAMILIES,
    COMPARABLE_UNIT,
    EPISTEMIC_CLASSES,
    FAMILIES,
    PACK_STATES,
    REQUIRED_PACK_FIELDS,
    SCHEMA,
)
from scripts.bofu_evidence.producer import build_family_pack, build_packs


def test_build_packs_emits_eight_nominal_families() -> None:
    bundle = build_packs()
    assert bundle["schema"] == SCHEMA
    assert len(bundle["packs"]) == 8
    assert [item["family"] for item in bundle["packs"]] == list(FAMILIES)
    assert bundle["manifest"]["pack_count"] == 8
    assert bundle["manifest"]["schema"] == SCHEMA


def test_each_pack_has_contract_fields_and_epistemic_classes() -> None:
    bundle = build_packs()
    for pack in bundle["packs"]:
        for field in REQUIRED_PACK_FIELDS:
            assert field in pack
        assert pack["state"] in PACK_STATES
        assert pack["publication"] is False
        assert pack["index"] is False
        assert pack["national"] is False
        assert pack["as_of"] == bundle["as_of"]
        labeled = list(pack["claims"]) + list(pack["calculations"])
        assert labeled
        for item in labeled:
            assert item["epistemic_class"] in EPISTEMIC_CLASSES
            if item["epistemic_class"] in {"FACT", "CALCULATION"}:
                assert item["evidence_refs"]


def test_replay_same_input_same_content_hash() -> None:
    first = build_packs()
    second = build_packs()
    assert first["as_of"] == second["as_of"]
    assert first["sha256sums"] == second["sha256sums"]
    for left, right in zip(first["packs"], second["packs"], strict=True):
        assert left["content_hash"] == right["content_hash"]
        recomputed = hash_without_content_hash(left)
        assert recomputed == left["content_hash"]
        assert recomputed == right["content_hash"]


def test_as_of_comes_from_snapshot_not_wall_clock() -> None:
    bundle = build_packs(as_of="2026-08-19T00:00:00Z")
    assert bundle["as_of"] == "2026-08-19T00:00:00Z"
    for pack in bundle["packs"]:
        assert pack["as_of"] == "2026-08-19T00:00:00Z"
        assert pack["as_of_source"] != "wall_clock"


def test_pr435_attached_only_where_pertinent_and_stays_brl_total() -> None:
    bundle = build_packs()
    attached = [item for item in bundle["packs"] if item["comparable_attached"]]
    assert attached
    assert {item["family"] for item in attached} <= set(COMPARABLE_PERTINENT_FAMILIES)
    budget = next(item for item in bundle["packs"] if item["family"] == "orcamento_bdi")
    assert budget["comparable_attached"] is True
    units = {item.get("unit") for item in budget["claims"] + budget["calculations"] if item.get("unit")}
    assert units == {COMPARABLE_UNIT}
    glosa = next(item for item in bundle["packs"] if item["family"] == "medicoes_glosas")
    assert glosa["comparable_attached"] is False
    bid = next(item for item in bundle["packs"] if item["family"] == "pre_licitacao_bid_room")
    assert bid["comparable_attached"] is False


def test_absence_is_unknown_not_negative_fact() -> None:
    pack = build_family_pack("aditivos")
    unknowns = [item for item in pack["claims"] if item["epistemic_class"] == "UNKNOWN"]
    assert unknowns
    assert any(item["reason_code"] == "document_not_observed" for item in unknowns)
    for item in pack["claims"]:
        if item["epistemic_class"] == "FACT":
            statement = item["statement"].lower()
            assert "nao houve" not in statement
            assert "não houve" not in statement
            assert "no amendment occurred" not in statement
