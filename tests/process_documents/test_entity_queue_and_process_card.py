"""Shipped tests: entity queue (success lag, drain, SLA) + process cards + ops health."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts.process_documents.backup_restore_proof import pack_meta_snapshot, restore_snapshot_verify
from scripts.process_documents.collect import collect_many, incremental, select_batch_static_legacy
from scripts.process_documents.entity_queue import (
    EntityQueueEntry,
    apply_attempt_result,
    build_sla_alerts,
    drain_decision,
    load_entity_queue,
    queue_summary,
    save_entity_queue,
    select_batch_by_success_lag,
)
from scripts.process_documents.models import EntityDocumentDiscovery
from scripts.process_documents.ops_health import audit_directories, collect_ops_health, disk_usage_report
from scripts.process_documents.process_card import (
    build_cards_from_collect_summary,
    document_stable_key,
    merge_documents_into_card,
)
from scripts.process_documents.statuses import ActivityStatus, DocumentRunStatus


def _entity(
    cid: str,
    *,
    platforms: list[str] | None = None,
    portal_family: str = "pncp",
    confidence: float = 0.5,
) -> EntityDocumentDiscovery:
    return EntityDocumentDiscovery(
        canonical_id=cid,
        razao_social=f"Entidade {cid}",
        cnpj=cid.split(":")[0] if ":" in cid else cid,
        municipio="TESTE",
        uf="SC",
        applicability="applicable",
        applicability_reason="test",
        institutional_site=None,
        transparency_portal=None,
        procurement_portal=None,
        dispute_platform=None,
        admin_process_system=None,
        pncp_source="test",
        portal_family=portal_family,
        capabilities=["notice_documents"],
        access_status="operational",
        last_verified_at="2026-01-01T00:00:00+00:00",
        blocker=None,
        collection_strategy="api",
        fallback_strategy="none",
        activity_status=ActivityStatus.ACTIVE.value,
        platforms=platforms if platforms is not None else [portal_family],
        mapping_confidence=confidence,
    )


def test_select_by_success_lag_not_static_prefix() -> None:
    universe = [
        _entity("aaa:A", portal_family="other", confidence=0.1),
        _entity("bbb:B", portal_family="pncp", confidence=0.9),
        _entity("ccc:C", portal_family="pncp", confidence=0.8),
        _entity("ddd:D", portal_family="pncp", confidence=0.7),
        _entity("eee:E", portal_family="other", confidence=0.99),
    ]
    legacy = [d.canonical_id for d in select_batch_static_legacy(universe, limit=2)]
    assert legacy == ["bbb:B", "ccc:C"]

    now = datetime(2026, 8, 1, tzinfo=UTC)
    queue = {
        "bbb:B": EntityQueueEntry(
            canonical_id="bbb:B",
            last_success_at=(now - timedelta(hours=1)).isoformat(),
        ),
        "ccc:C": EntityQueueEntry(
            canonical_id="ccc:C",
            last_success_at=(now - timedelta(hours=2)).isoformat(),
        ),
        # others never succeeded
    }
    batch = select_batch_by_success_lag(universe, queue, limit=2, now=now)
    ids = [d.canonical_id for d in batch]
    # Never-succeeded first (aaa, ddd, eee) sorted by id
    assert ids[0] == "aaa:A"
    assert "bbb:B" not in ids  # recently successful stays out of top-2 when never exist


def test_apply_attempt_records_success_vs_failure() -> None:
    e = EntityQueueEntry(canonical_id="x")
    t0 = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    apply_attempt_result(e, status="connection_failed", attempted_at=t0)
    assert e.last_attempt_at is not None
    assert e.last_success_at is None
    assert e.consecutive_failures == 1
    assert e.attempt_count == 1
    assert e.next_run_at is not None

    apply_attempt_result(e, status=DocumentRunStatus.SUCCESS_ZERO.value, attempted_at=t0 + timedelta(hours=1))
    assert e.last_success_at is not None
    assert e.consecutive_failures == 0
    assert e.attempt_count == 2


def test_sla_alerts_when_over_24h() -> None:
    now = datetime(2026, 8, 1, tzinfo=UTC)
    targets = [_entity("stale:1"), _entity("fresh:2"), _entity("never:3")]
    queue = {
        "stale:1": EntityQueueEntry(
            canonical_id="stale:1",
            last_success_at=(now - timedelta(hours=30)).isoformat(),
        ),
        "fresh:2": EntityQueueEntry(
            canonical_id="fresh:2",
            last_success_at=(now - timedelta(hours=2)).isoformat(),
        ),
        "never:3": EntityQueueEntry(canonical_id="never:3"),
    }
    alerts = build_sla_alerts(targets, queue, now=now, sla_hours=24)
    ids = {a["canonical_id"] for a in alerts}
    assert "stale:1" in ids
    assert "never:3" in ids
    assert "fresh:2" not in ids


def test_drain_decision_lag_vs_capacity() -> None:
    stop, reason = drain_decision(
        overdue_remaining=0,
        batches_done=1,
        entities_done=10,
        max_batches=5,
        max_entities=100,
        wall_seconds=10,
        max_wall_seconds=3600,
    )
    assert stop and reason == "lag_cleared"

    stop, reason = drain_decision(
        overdue_remaining=50,
        batches_done=5,
        entities_done=100,
        max_batches=5,
        max_entities=None,
        wall_seconds=10,
        max_wall_seconds=3600,
    )
    assert stop and reason == "capacity_insufficient_batches"


def test_queue_persist_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROCESS_DOCUMENTS_META_ROOT", str(tmp_path / "meta"))
    monkeypatch.setenv("PROCESS_DOCUMENTS_RAW_ROOT", str(tmp_path / "raw"))
    q = {
        "e1": EntityQueueEntry(
            canonical_id="e1",
            last_success_at="2026-08-01T00:00:00+00:00",
            last_attempt_at="2026-08-01T00:00:00+00:00",
            attempt_count=3,
            consecutive_failures=0,
            next_run_at="2026-08-02T00:00:00+00:00",
            sources=["pncp", "ciga_ckan"],
        )
    }
    save_entity_queue(q, meta_root=tmp_path / "meta")
    loaded = load_entity_queue(meta_root=tmp_path / "meta")
    assert loaded["e1"].attempt_count == 3
    assert loaded["e1"].sources == ["pncp", "ciga_ckan"]
    assert loaded["e1"].next_run_at is not None


def test_collect_many_updates_queue_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PROCESS_DOCUMENTS_META_ROOT", str(tmp_path / "meta"))
    monkeypatch.setenv("PROCESS_DOCUMENTS_RAW_ROOT", str(tmp_path / "raw"))
    universe = [_entity(f"id{i}:E", platforms=["pncp"]) for i in range(4)]

    def fake_collect(entity: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "canonical_entity_id": entity.canonical_id,
            "status": DocumentRunStatus.SUCCESS_ZERO.value,
            "sources_attempted": ["pncp"],
            "documents": [],
            "documents_downloaded": 0,
        }

    with (
        patch("scripts.process_documents.collect.load_discovery", return_value=universe),
        patch("scripts.process_documents.collect.collect_entity", side_effect=fake_collect),
    ):
        s1 = collect_many(limit=2, download=False, meta_root=tmp_path / "meta", build_process_cards=False)
        s2 = collect_many(limit=2, download=False, meta_root=tmp_path / "meta", build_process_cards=False)

    assert s1["selection_policy"] == "success_lag_rotation"
    assert s1["selected_canonical_ids"] != s2["selected_canonical_ids"]
    q = load_entity_queue(meta_root=tmp_path / "meta")
    for cid in s1["selected_canonical_ids"]:
        assert q[cid].last_success_at is not None
        assert q[cid].attempt_count >= 1


def test_incremental_drain_until_lag_cleared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PROCESS_DOCUMENTS_META_ROOT", str(tmp_path / "meta"))
    monkeypatch.setenv("PROCESS_DOCUMENTS_RAW_ROOT", str(tmp_path / "raw"))
    universe = [_entity(f"u{i:02d}:X", platforms=["pncp"]) for i in range(5)]

    def fake_collect(entity: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "canonical_entity_id": entity.canonical_id,
            "status": DocumentRunStatus.SUCCESS_ZERO.value,
            "sources_attempted": ["pncp"],
            "documents": [],
        }

    with (
        patch("scripts.process_documents.collect.load_discovery", return_value=universe),
        patch("scripts.process_documents.collect.collect_entity", side_effect=fake_collect),
        patch("scripts.process_documents.collect._attach_daily_report", lambda *a, **k: None),
    ):
        summary = incremental(
            download=False,
            limit=2,
            drain=True,
            max_batches=10,
            max_wall_seconds=60,
            meta_root=tmp_path / "meta",
            build_daily_report=False,
        )

    assert summary["drain"] is True
    assert summary["drain_stop_reason"] == "lag_cleared"
    assert summary["lag_cleared"] is True
    assert summary["count"] == 5
    assert summary["batches"] >= 3
    assert not summary.get("capacity_insufficient")


def test_incremental_capacity_insufficient(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PROCESS_DOCUMENTS_META_ROOT", str(tmp_path / "meta"))
    monkeypatch.setenv("PROCESS_DOCUMENTS_RAW_ROOT", str(tmp_path / "raw"))
    universe = [_entity(f"c{i:02d}:X", platforms=["pncp"]) for i in range(10)]

    def fake_collect(entity: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "canonical_entity_id": entity.canonical_id,
            "status": DocumentRunStatus.SUCCESS_ZERO.value,
            "sources_attempted": ["pncp"],
            "documents": [],
        }

    with (
        patch("scripts.process_documents.collect.load_discovery", return_value=universe),
        patch("scripts.process_documents.collect.collect_entity", side_effect=fake_collect),
    ):
        summary = incremental(
            download=False,
            limit=2,
            drain=True,
            max_batches=2,
            max_wall_seconds=60,
            meta_root=tmp_path / "meta",
            build_daily_report=False,
        )

    assert summary["capacity_insufficient"] is True
    assert "capacity_insufficient" in summary["drain_stop_reason"]
    assert summary["count"] == 4  # 2 batches * 2


def test_process_card_detects_new_changed_removed() -> None:
    docs_v1 = [
        {
            "procurement_id": "PROC-1",
            "sha256": "aaa",
            "source_id": "pncp",
            "original_title": "Edital",
            "download_url": "https://example/edital.pdf",
            "canonical_entity_id": "e1",
        },
        {
            "procurement_id": "PROC-1",
            "sha256": "bbb",
            "source_id": "ciga_ckan",
            "original_title": "Anexo I",
            "download_url": "https://example/anexo.pdf",
            "canonical_entity_id": "e1",
        },
    ]
    card1 = merge_documents_into_card("PROC-1", docs_v1, previous=None)
    assert set(card1.sources_seen) == {"pncp", "ciga_ckan"}
    assert any(c["change"] == "new" for c in card1.changes)

    docs_v2 = [
        {
            "procurement_id": "PROC-1",
            "sha256": "aaa_changed",
            "source_id": "pncp",
            "original_title": "Edital",
            "download_url": "https://example/edital.pdf",
            "canonical_entity_id": "e1",
        },
        # Anexo removed
    ]
    card2 = merge_documents_into_card("PROC-1", docs_v2, previous=card1.to_dict())
    changes = {c["change"] for c in card2.changes}
    assert "changed" in changes
    assert "removed" in changes
    assert len(card2.versions[document_stable_key(docs_v1[0])]) >= 1


def test_process_card_cited_missing() -> None:
    docs = [
        {
            "procurement_id": "P2",
            "original_title": "Ata citada",
            "source_id": "sc_compras",
            "error": "404",
            "canonical_entity_id": "e2",
        }
    ]
    card = merge_documents_into_card("P2", docs)
    assert card.cited_missing
    assert card.cited_missing[0]["title"] == "Ata citada"


def test_build_cards_from_collect_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROCESS_DOCUMENTS_META_ROOT", str(tmp_path / "meta"))
    monkeypatch.setenv("PROCESS_DOCUMENTS_RAW_ROOT", str(tmp_path / "raw"))
    summary = {
        "results": [
            {
                "canonical_entity_id": "e1",
                "documents": [
                    {
                        "procurement_id": "PX",
                        "sha256": "s1",
                        "source_id": "pncp",
                        "original_title": "Edital",
                        "download_url": "http://x",
                        "canonical_entity_id": "e1",
                    }
                ],
                "source_results": {
                    "ciga_ckan": {
                        "documents": [
                            {
                                "procurement_id": "PX",
                                "sha256": "s2",
                                "source_id": "ciga_ckan",
                                "original_title": "Homologacao",
                                "download_url": "http://y",
                                "canonical_entity_id": "e1",
                            }
                        ]
                    }
                },
            }
        ]
    }
    report = build_cards_from_collect_summary(summary, meta_root=tmp_path / "meta", persist=True)
    assert report["process_count"] == 1
    assert report["change_counts"]["new"] >= 2
    card_path = tmp_path / "meta" / "process_cards" / "PX.json"
    assert card_path.is_file()


def test_ops_health_flags_missing_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # point roots at non-created nested paths without write — actually ensure_roots creates them
    monkeypatch.setenv("PROCESS_DOCUMENTS_META_ROOT", str(tmp_path / "meta"))
    monkeypatch.setenv("PROCESS_DOCUMENTS_RAW_ROOT", str(tmp_path / "raw"))
    report = collect_ops_health(discoveries=[], meta_root=tmp_path / "meta", raw_root=tmp_path / "raw", persist=True)
    assert "directories" in report
    assert report["directories"]["raw_root"]["ok"] is True
    disk = disk_usage_report(tmp_path / "raw")
    assert "used_percent" in disk
    missing = audit_directories(tmp_path / "nope_raw", tmp_path / "nope_meta")
    assert missing["raw_root"]["ok"] is False


def test_backup_restore_local_proof(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROCESS_DOCUMENTS_META_ROOT", str(tmp_path / "meta"))
    monkeypatch.setenv("PROCESS_DOCUMENTS_RAW_ROOT", str(tmp_path / "raw"))
    meta = tmp_path / "meta"
    meta.mkdir(parents=True)
    (meta / "checkpoints").mkdir()
    (meta / "checkpoints" / "entity_queue.json").write_text('{"entities":{}}\n', encoding="utf-8")
    (meta / "document-incremental-manifest.json").write_text('{"count":0}\n', encoding="utf-8")
    archive = tmp_path / "snap.tar.gz"
    pack = pack_meta_snapshot(meta, archive)
    restore = restore_snapshot_verify(archive, pack["sha256"])
    assert restore["ok"] is True
    assert restore["sha256_verified"] is True


def test_queue_summary_lag_cleared() -> None:
    now = datetime(2026, 8, 1, tzinfo=UTC)
    targets = [_entity("a:1"), _entity("b:2")]
    queue = {
        "a:1": EntityQueueEntry(
            canonical_id="a:1",
            last_success_at=(now - timedelta(hours=1)).isoformat(),
        ),
        "b:2": EntityQueueEntry(
            canonical_id="b:2",
            last_success_at=(now - timedelta(hours=2)).isoformat(),
        ),
    }
    s = queue_summary(targets, queue, now=now, sla_hours=24)
    assert s["lag_cleared"] is True
    assert s["overdue_count"] == 0
