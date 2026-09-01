"""AC 19 — the conditional ``claim_safety_hash`` insertion is back-compatible.

The anchor is not recomputed by the code under test: it is the published
identity of production release ``run-adb0097e32b02188``, whose release directory
name carries ``publication_semantic_hash[:12] == a77fd763126c`` and whose served
``manifest.json`` has no ``claim_safety`` block. A legacy manifest must keep that
exact digest, or every ``commercial_authority.basis_publication_semantic_hash``
already bound in production is invalidated.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.confenge_activation.publish import publication_semantic_hash

FIXTURE = Path(__file__).parent / "fixtures" / "legacy-manifest-run-adb0097e32b02188.json"

# Measured in production before this story touched publish.py.
PRODUCTION_ANCHOR = "a77fd763126cd730e8e6ebd515d6fec7820ab8fb7ebff12a0966506e21302ec7"


def _legacy_manifest() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_ac19_legacy_manifest_keeps_its_production_publication_semantic_hash() -> None:
    manifest = _legacy_manifest()
    assert "claim_safety" not in manifest
    assert publication_semantic_hash(manifest) == PRODUCTION_ANCHOR


def test_ac19_an_empty_or_hashless_claim_safety_block_is_also_inert() -> None:
    """Only a real ``corpus_hash`` participates; a stub block changes nothing."""
    anchor = publication_semantic_hash(_legacy_manifest())
    for block in ({}, {"policy_version": "confenge-claim-safety-v1"}, {"corpus_hash": ""}, None, "not-a-dict"):
        manifest = {**_legacy_manifest(), "claim_safety": block}
        assert publication_semantic_hash(manifest) == anchor, block


def test_a_claim_safety_corpus_hash_does_change_the_publication_semantics() -> None:
    """Without this, a corrected build replays as SAME_SNAPSHOT_NOT_FRESHNESS."""
    manifest = {**_legacy_manifest(), "claim_safety": {"corpus_hash": "d" * 64}}
    assert publication_semantic_hash(manifest) != PRODUCTION_ANCHOR


def test_distinct_corpora_produce_distinct_publication_semantics() -> None:
    left = publication_semantic_hash({**_legacy_manifest(), "claim_safety": {"corpus_hash": "a" * 64}})
    right = publication_semantic_hash({**_legacy_manifest(), "claim_safety": {"corpus_hash": "b" * 64}})
    assert left != right
