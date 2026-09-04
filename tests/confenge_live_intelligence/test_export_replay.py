"""Replay 100x do export embarcado e recusa de fixture como official_live.

Drive ``export.build_bundle`` / ``export_bundle`` (nao uma reimplementacao).
Um snapshot selado e a entrada; 100 leituras sem re-persist produzem o mesmo
envelope. Rotulos live-looking no snapshot nunca promovem o default fixture.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.confenge_live_intelligence import export as li_export
from scripts.confenge_live_intelligence import public_policy as policy
from scripts.confenge_live_intelligence import schema as li_schema
from scripts.confenge_live_intelligence.producer import build_snapshot
from scripts.confenge_live_intelligence.schema import canonical_json, live_hash

UTC_NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
AS_OF = date(2026, 9, 2)
CREATED_BY = "LI-TEST-export-replay"

pytestmark = pytest.mark.real_db


def _opportunity(**overrides) -> li_schema.LiveOpportunity:
    base = dict(
        opportunity_id="LI-TEST-REPLAY-1",
        source="pncp",
        source_as_of=UTC_NOW,
        objeto="Reforma de escola municipal com estrutura metalica",
        objeto_state=li_schema.OBSERVED,
        valor_estimado_brl=Decimal("250000.00"),
        valor_state=li_schema.OBSERVED,
        valor_band="100K_1M",
        modalidade="Pregao",
        modalidade_id="6",
        modalidade_state=li_schema.OBSERVED,
        uf="SC",
        municipio="Florianopolis",
        geo_state=li_schema.OBSERVED,
        orgao_cnpj="12345678000195",
        orgao_nome="Prefeitura Sintetica",
        orgao_state=li_schema.OBSERVED,
        data_publicacao=date(2026, 8, 1),
        data_encerramento=date(2026, 10, 1),
        deadline_state=li_schema.DEADLINE_OPEN,
    )
    base.update(overrides)
    return li_schema.LiveOpportunity(**base)


def _company(**overrides) -> li_schema.LiveCompany:
    base = dict(
        company_root8="11222333",
        source_as_of=UTC_NOW + timedelta(hours=3),
        date_resolver_version="ca-v2-precedence/1.0",
        razao_social="Construtora Sintetica",
        portfolio_contract_ids=("LI-TEST-C1",),
        observed_objects=("Reforma de escola municipal com estrutura metalica",),
        observed_value_bands=("100K_1M",),
        observed_ufs=("SC",),
        observed_buyer_cnpjs=("12345678000195",),
        observed_establishment_cnpjs=("11222333000181",),
        most_recent_contracting_date=date(2026, 5, 1),
        contracting_date_state=li_schema.OBSERVED,
    )
    base.update(overrides)
    return li_schema.LiveCompany(**base)


def _seal(live_conn):
    result = build_snapshot(
        live_conn,
        as_of=AS_OF,
        created_by=CREATED_BY,
        opportunities=[_opportunity()],
        companies=[_company()],
    )
    assert result.state == li_schema.SNAPSHOT_READY, result.state
    return result


def _envelope(manifest: dict, files: dict) -> dict:
    return {
        "snapshot_id": manifest["snapshot_id"],
        "source_run_id": manifest["source_run_id"],
        "as_of": manifest["as_of"],
        "manifest_hash": manifest["manifest_hash"],
        "content_hashes": tuple(sorted(payload["content_hash"] for payload in files.values())),
        "catalog_mode": manifest["catalog_mode"],
        "official_live": manifest["official_live"],
        "public_decision": manifest["public_decision"],
        "producer_status": manifest["producer_status"],
        "schema": manifest["schema"],
    }


def test_public_decision_is_fail_closed_without_all_three_axes() -> None:
    """Funcao pura: fixture, hold e stale nunca viram public_safe."""
    assert (
        policy.public_decision_for(
            catalog_mode=policy.CATALOG_MODE_OFFICIAL_LIVE,
            data_state=policy.DATA_READY,
            freshness_state=policy.FRESHNESS_FRESH,
        )
        == policy.PUBLIC_SAFE
    )
    assert (
        policy.public_decision_for(
            catalog_mode=policy.CATALOG_MODE_FIXTURE,
            data_state=policy.DATA_READY,
            freshness_state=policy.FRESHNESS_FRESH,
        )
        == policy.NOT_PUBLIC_SAFE
    )
    assert (
        policy.public_decision_for(
            catalog_mode=policy.CATALOG_MODE_OFFICIAL_LIVE,
            data_state=policy.DATA_HOLD,
            freshness_state=policy.FRESHNESS_FRESH,
        )
        == policy.NOT_PUBLIC_SAFE
    )
    assert (
        policy.public_decision_for(
            catalog_mode=policy.CATALOG_MODE_OFFICIAL_LIVE,
            data_state=policy.DATA_READY,
            freshness_state=policy.FRESHNESS_STALE,
        )
        == policy.NOT_PUBLIC_SAFE
    )


def test_export_replay_100x_is_deterministic(live_conn, tmp_path: Path) -> None:
    """100 exports do mesmo snapshot selado (sem re-persist) = um envelope."""
    result = _seal(live_conn)
    first = li_export.export_bundle(
        live_conn,
        snapshot_id=result.snapshot_id,
        out_dir=tmp_path / "r0",
        catalog_mode=policy.CATALOG_MODE_OFFICIAL_LIVE,
    )
    first_files = li_export.load_bundle(tmp_path / "r0")["files"]
    expected = _envelope(first, first_files)
    assert expected["snapshot_id"] == result.snapshot_id
    assert expected["source_run_id"] == result.snapshot_id
    assert expected["as_of"] == AS_OF.isoformat()
    assert expected["schema"] == policy.CONTRACT_SCHEMA
    assert expected["public_decision"] in policy.PUBLIC_DECISIONS

    seen = [expected]
    for i in range(1, 100):
        bundle = li_export.build_bundle(
            live_conn,
            result.snapshot_id,
            catalog_mode=policy.CATALOG_MODE_OFFICIAL_LIVE,
        )
        seen.append(_envelope(bundle["manifest"], bundle["files"]))
    assert all(item == expected for item in seen), (
        f"replay diverged at index {[i for i, item in enumerate(seen) if item != expected][:3]}"
    )


def test_live_looking_labels_never_promote_fixture_to_official_live(live_conn, tmp_path: Path) -> None:
    """created_by/generated_at/schema-looking labels nao reivindicam official_live.

    O default do export e fixture. Catalog_mode e o unico eixo de proveniencia;
    um timestamp fresco ou um created_by com a palavra official_live nao muda
    o rotulo. Drive ``export_bundle``, nao uma copia da regra.
    """
    result = build_snapshot(
        live_conn,
        as_of=AS_OF,
        created_by="official_live production generator 2026-09-03T12:00:00Z",
        opportunities=[_opportunity()],
        companies=[_company()],
    )
    manifest = li_export.export_bundle(
        live_conn,
        snapshot_id=result.snapshot_id,
        out_dir=tmp_path / "unclaimed-live-labels",
    )
    assert manifest["catalog_mode"] == policy.CATALOG_MODE_FIXTURE
    assert manifest["official_live"] is False
    assert manifest["producer_status"] == policy.PRODUCER_STATUS_FIXTURE
    assert manifest["public_decision"] == policy.NOT_PUBLIC_SAFE
    assert manifest["schema"] == policy.CONTRACT_SCHEMA
    # generated_at existe e parece live; isso nao e reivindicacao.
    assert manifest["generated_at"]
    assert manifest["source_run_id"] == result.snapshot_id


def test_claimed_official_live_sets_identity_and_public_decision(live_conn, tmp_path: Path) -> None:
    result = _seal(live_conn)
    manifest = li_export.export_bundle(
        live_conn,
        snapshot_id=result.snapshot_id,
        out_dir=tmp_path / "claimed",
        catalog_mode=policy.CATALOG_MODE_OFFICIAL_LIVE,
    )
    assert manifest["snapshot_id"] == result.snapshot_id
    assert manifest["source_run_id"] == result.snapshot_id
    assert manifest["catalog_mode"] == policy.CATALOG_MODE_OFFICIAL_LIVE
    assert manifest["official_live"] is True
    assert manifest["producer_status"] == policy.PRODUCER_STATUS_OFFICIAL_LIVE
    assert manifest["schema"] == policy.CONTRACT_SCHEMA
    assert manifest["as_of"] == AS_OF.isoformat()
    assert manifest["manifest_hash"]
    assert manifest["freshness"]["state"] in {policy.FRESHNESS_FRESH, policy.FRESHNESS_STALE}
    expected_decision = policy.public_decision_for(
        catalog_mode=manifest["catalog_mode"],
        data_state=manifest["data_state"],
        freshness_state=manifest["freshness"]["state"],
    )
    assert manifest["public_decision"] == expected_decision
    on_disk = (tmp_path / "claimed" / li_export.MANIFEST_FILE).read_bytes()
    parsed = json.loads(on_disk)
    recomputed = live_hash({k: v for k, v in parsed.items() if k != "manifest_hash"})
    assert parsed["manifest_hash"] == recomputed
    assert parsed["manifest_hash"] == manifest["manifest_hash"]
    # canonical bytes on disk match the in-memory manifest (hash covers the same dict).
    assert canonical_json(parsed) == canonical_json(manifest)
