"""Tests for #281 canonical source IDs and fail-closed pack totals."""

from __future__ import annotations

import pytest

from scripts.source_registry.source_identity import (
    InventoryRecord,
    SourceIdentityError,
    SourceObservation,
    canonical_source_id,
    reconcile_pack_totals,
    resolve_observation,
)


def test_pncp_and_pncp_opportunities_share_canonical_id() -> None:
    assert canonical_source_id("pncp") == "pncp"
    assert canonical_source_id("pncp_opportunities") == "pncp"
    assert canonical_source_id("PNCP-Oportunidades") == "pncp"


def test_observation_references_canonical_source_and_capability() -> None:
    row = resolve_observation(
        SourceObservation(
            observation_id="o1",
            raw_source="pncp_opportunities",
            capability="opportunities",
            entity_id="ente-1",
        )
    )
    assert row["source_id"] == "pncp"
    assert row["capability"] == "opportunities"
    assert row["observation_id"] == "o1"


def test_alias_does_not_duplicate_pack_count() -> None:
    observations = (
        SourceObservation("a", "pncp", "opportunities"),
        SourceObservation("b", "pncp_opportunities", "opportunities"),
        SourceObservation("c", "ciga_ckan", "documents"),
    )
    inventory = (
        InventoryRecord("pncp", "opportunities", 2, aliases=("pncp_opportunities",)),
        InventoryRecord("ciga", "documents", 1, aliases=("ciga_ckan",)),
    )
    pack = reconcile_pack_totals(observations, inventory)
    assert pack.closed is True
    assert pack.by_source == {"ciga": 1, "pncp": 2}
    assert pack.observation_count == 3
    assert "pncp_opportunities" not in pack.by_source
    assert pack.by_source_capability["pncp:opportunities"] == 2


def test_orphan_alias_fail_closed() -> None:
    observations = (SourceObservation("x", "portal_desconhecido", "opportunities"),)
    inventory = (InventoryRecord("pncp", "opportunities", 0),)
    with pytest.raises(SourceIdentityError, match="orphan_alias"):
        reconcile_pack_totals(observations, inventory)


def test_divergent_inventory_count_fail_closed() -> None:
    observations = (
        SourceObservation("a", "pncp", "opportunities"),
        SourceObservation("b", "pncp_opportunities", "opportunities"),
    )
    # Inventory still counts the alias as a second source — illegal.
    inventory = (
        InventoryRecord("pncp", "opportunities", 1),
        InventoryRecord("pncp_opportunities", "opportunities", 1),
    )
    with pytest.raises(SourceIdentityError, match="divergent_source_counts"):
        reconcile_pack_totals(observations, inventory)
