"""Shipped-path tests: staleness rotation batch + multi-source daily collect.

Drives real functions in scripts.process_documents.collect — no reimplementation
of selection/aggregation inside the test body.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from scripts.process_documents.collect import (
    aggregate_multi_source_result,
    collect_entity,
    collect_many,
    incremental,
    load_last_visits,
    preferred_single_source,
    record_entity_visits,
    resolve_applicable_sources,
    select_batch_by_staleness,
    select_batch_static_legacy,
)
from scripts.process_documents.models import EntityDocumentDiscovery
from scripts.process_documents.statuses import ActivityStatus, DocumentRunStatus


def _entity(
    cid: str,
    *,
    portal_family: str = "pncp",
    platforms: list[str] | None = None,
    confidence: float = 0.5,
    activity: str = ActivityStatus.ACTIVE.value,
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
        activity_status=activity,
        platforms=platforms if platforms is not None else [portal_family],
        mapping_confidence=confidence,
    )


def test_static_legacy_sticky_prefix_vs_staleness_rotation() -> None:
    """With M>N eligible, legacy sort always picks the same N; staleness rotates."""
    # Mix portal families + confidence so legacy sort is non-trivial and sticky
    universe = [
        _entity("aaa:A", portal_family="other", platforms=["generic_public_html"], confidence=0.1),
        _entity("bbb:B", portal_family="pncp", platforms=["pncp"], confidence=0.9),
        _entity("ccc:C", portal_family="pncp", platforms=["pncp"], confidence=0.8),
        _entity("ddd:D", portal_family="pncp", platforms=["pncp"], confidence=0.7),
        _entity("eee:E", portal_family="other", platforms=["sc_compras"], confidence=0.99),
    ]
    limit = 2

    legacy_1 = [d.canonical_id for d in select_batch_static_legacy(universe, limit=limit)]
    legacy_2 = [d.canonical_id for d in select_batch_static_legacy(universe, limit=limit)]
    assert legacy_1 == legacy_2
    # pncp + higher confidence first
    assert legacy_1[0] == "bbb:B"
    assert legacy_1[1] == "ccc:C"

    # No visits → all "never" → order by canonical_id among never-visited
    never_batch = select_batch_by_staleness(universe, last_visits={}, limit=limit)
    never_ids = [d.canonical_id for d in never_batch]
    assert never_ids == sorted(d.canonical_id for d in universe)[:limit]

    # After visiting the first batch, second selection must differ when M>N
    visits = {cid: "2026-07-01T00:00:00+00:00" for cid in never_ids}
    second = select_batch_by_staleness(universe, last_visits=visits, limit=limit)
    second_ids = [d.canonical_id for d in second]
    assert second_ids != never_ids
    # Newly selected must be from the never-visited remainder
    assert not set(second_ids) & set(never_ids)
    assert set(second_ids).issubset({d.canonical_id for d in universe})

    # Progressive coverage: union of two batches of size N covers 2N distinct when M>=2N
    assert len(set(never_ids) | set(second_ids)) == 2 * limit


def test_staleness_oldest_before_recent() -> None:
    entities = [
        _entity("z:late"),
        _entity("a:early"),
        _entity("m:mid"),
        _entity("n:never"),
    ]
    now = datetime(2026, 8, 1, tzinfo=UTC)
    visits = {
        "z:late": (now - timedelta(hours=1)).isoformat(),
        "a:early": (now - timedelta(days=30)).isoformat(),
        "m:mid": (now - timedelta(days=7)).isoformat(),
        # n:never missing
    }
    batch = select_batch_by_staleness(entities, last_visits=visits, limit=3, now=now)
    ids = [d.canonical_id for d in batch]
    assert ids[0] == "n:never"
    assert ids[1] == "a:early"
    assert ids[2] == "m:mid"
    assert "z:late" not in ids


def test_resolve_applicable_sources_all_platforms_not_only_preferred() -> None:
    ent = _entity(
        "x:1",
        portal_family="pncp",
        platforms=["pncp", "ciga_ckan", "sc_compras", "ciga_dom"],
    )
    sources = resolve_applicable_sources(ent)
    # ciga_dom collapses into ciga_ckan adapter key
    assert "ciga_ckan" in sources
    assert "pncp" in sources
    assert "sc_compras" in sources
    assert sources.count("ciga_ckan") == 1
    # Multi-source list is strictly broader than legacy preferred single source
    preferred = preferred_single_source(ent)
    assert preferred == "ciga_ckan"
    assert set(sources) - {preferred}


def test_aggregate_multi_source_merges_status_and_docs() -> None:
    sources = ["pncp", "ciga_ckan"]
    results = [
        {
            "status": DocumentRunStatus.SUCCESS_ZERO.value,
            "source_id": "pncp",
            "documents": [],
            "documents_downloaded": 0,
            "errors": [],
        },
        {
            "status": DocumentRunStatus.SUCCESS_NONZERO.value,
            "source_id": "ciga_ckan",
            "documents": [{"sha256": "abc"}],
            "documents_downloaded": 1,
            "errors": [],
        },
    ]
    agg = aggregate_multi_source_result("e1", sources, results)
    assert agg["status"] == DocumentRunStatus.SUCCESS_NONZERO.value
    assert agg["sources_attempted"] == sources
    assert set(agg["source_results"]) == set(sources)
    assert agg["documents_downloaded"] == 1
    assert len(agg["documents"]) == 1
    assert agg["multi_source"] is True


def test_collect_entity_multi_source_calls_each_adapter() -> None:
    """Entity with ≥2 applicable sources must invoke get_adapter once per unique key."""
    ent = _entity(
        "multi:1",
        portal_family="pncp",
        platforms=["pncp", "ciga_ckan"],
    )
    called_families: list[str] = []

    def fake_get_adapter(family: str) -> Any:
        called_families.append(family)
        adapter = MagicMock()

        def _collect(entity: Any, **kwargs: Any) -> dict[str, Any]:
            return {
                "run_id": f"r-{family}",
                "canonical_entity_id": entity.canonical_id,
                "source_id": family,
                "portal_family": family,
                "status": DocumentRunStatus.SUCCESS_ZERO.value,
                "success_zero_justification": "empty window",
                "documents": [],
                "documents_downloaded": 0,
                "documents_unchanged": 0,
                "documents_failed": 0,
                "processes_seen": 0,
                "errors": [],
                "blockers": [],
            }

        adapter.collect.side_effect = _collect
        return adapter

    with patch("scripts.process_documents.collect.get_adapter", side_effect=fake_get_adapter):
        out = collect_entity(ent, multi_source=True, download=False, max_processes=2)

    assert isinstance(out, dict)
    assert set(out["sources_attempted"]) == {"pncp", "ciga_ckan"}
    assert set(called_families) == {"pncp", "ciga_ckan"}
    assert len(called_families) == 2
    assert out["source_results"]["pncp"]["status"] == DocumentRunStatus.SUCCESS_ZERO.value
    assert out["source_results"]["ciga_ckan"]["status"] == DocumentRunStatus.SUCCESS_ZERO.value


def test_collect_entity_single_source_only_preferred() -> None:
    ent = _entity("s:1", portal_family="pncp", platforms=["pncp", "ciga_ckan"])
    called: list[str] = []

    def fake_get_adapter(family: str) -> Any:
        called.append(family)
        adapter = MagicMock()
        adapter.collect.return_value = MagicMock(
            to_dict=lambda: {"status": "SUCCESS_ZERO", "portal_family": family},
            status=DocumentRunStatus.SUCCESS_ZERO,
        )
        return adapter

    with patch("scripts.process_documents.collect.get_adapter", side_effect=fake_get_adapter):
        collect_entity(ent, multi_source=False, download=False)

    assert called == ["ciga_ckan"]  # preferred only


def test_collect_many_two_runs_rotate_selected_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Second collect_many with persisted visits must not repeat the same full batch."""
    monkeypatch.setenv("PROCESS_DOCUMENTS_META_ROOT", str(tmp_path / "meta"))
    monkeypatch.setenv("PROCESS_DOCUMENTS_RAW_ROOT", str(tmp_path / "raw"))

    universe = [
        _entity(f"id{i:02d}:E", portal_family="pncp", platforms=["pncp"], confidence=1.0 - i * 0.01)
        for i in range(5)
    ]

    def fake_collect(entity: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "canonical_entity_id": entity.canonical_id,
            "status": DocumentRunStatus.SUCCESS_ZERO.value,
            "sources_attempted": ["pncp"],
            "portal_family": "pncp",
            "documents": [],
            "documents_downloaded": 0,
        }

    with (
        patch("scripts.process_documents.collect.load_discovery", return_value=universe),
        patch("scripts.process_documents.collect.collect_entity", side_effect=fake_collect),
    ):
        run1 = collect_many(
            only_active=True,
            limit=2,
            download=False,
            multi_source=True,
            rotation=True,
            persist_visits=True,
            meta_root=tmp_path / "meta",
        )
        run2 = collect_many(
            only_active=True,
            limit=2,
            download=False,
            multi_source=True,
            rotation=True,
            persist_visits=True,
            meta_root=tmp_path / "meta",
        )

    ids1 = run1["selected_canonical_ids"]
    ids2 = run2["selected_canonical_ids"]
    assert run1["selection_policy"] == "staleness_rotation"
    assert ids1 != ids2
    assert len(ids1) == 2 and len(ids2) == 2
    # No silent permanent exclusion of the first batch on run 2
    assert set(ids1).isdisjoint(set(ids2))

    visits = load_last_visits(meta_root=tmp_path / "meta")
    for cid in ids1 + ids2:
        assert cid in visits


def test_incremental_uses_rotation_and_multi_source_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PROCESS_DOCUMENTS_META_ROOT", str(tmp_path / "meta"))
    monkeypatch.setenv("PROCESS_DOCUMENTS_RAW_ROOT", str(tmp_path / "raw"))

    universe = [
        _entity("a:1", platforms=["pncp", "ciga_ckan"]),
        _entity("b:2", platforms=["pncp"]),
        _entity("c:3", platforms=["sc_compras", "pncp"]),
    ]
    adapter_calls: list[tuple[str, str]] = []

    def fake_get_adapter(family: str) -> Any:
        adapter = MagicMock()

        def _collect(entity: Any, **kwargs: Any) -> dict[str, Any]:
            adapter_calls.append((entity.canonical_id, family))
            return {
                "run_id": f"{entity.canonical_id}:{family}",
                "canonical_entity_id": entity.canonical_id,
                "source_id": family,
                "portal_family": family,
                "status": DocumentRunStatus.SUCCESS_ZERO.value,
                "documents": [],
                "documents_downloaded": 0,
                "documents_unchanged": 0,
                "documents_failed": 0,
                "processes_seen": 0,
                "errors": [],
            }

        adapter.collect.side_effect = _collect
        return adapter

    with (
        patch("scripts.process_documents.collect.load_discovery", return_value=universe),
        patch("scripts.process_documents.collect.get_adapter", side_effect=fake_get_adapter),
    ):
        summary = incremental(download=False, limit=1)

    assert summary["selection_policy"] == "staleness_rotation"
    assert summary["multi_source"] is True
    assert len(summary["selected_canonical_ids"]) == 1
    selected = summary["selected_canonical_ids"][0]
    # Never-visited sorted by id → a:1 first; multi-source → pncp + ciga_ckan
    assert selected == "a:1"
    families = {fam for cid, fam in adapter_calls if cid == "a:1"}
    assert families == {"pncp", "ciga_ckan"}
    result0 = summary["results"][0]
    assert len(result0.get("sources_attempted") or []) >= 2

    # Second incremental must rotate to a different entity
    with (
        patch("scripts.process_documents.collect.load_discovery", return_value=universe),
        patch("scripts.process_documents.collect.get_adapter", side_effect=fake_get_adapter),
    ):
        summary2 = incremental(download=False, limit=1)
    assert summary2["selected_canonical_ids"] != summary["selected_canonical_ids"]


def test_visit_checkpoint_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROCESS_DOCUMENTS_META_ROOT", str(tmp_path / "meta"))
    monkeypatch.setenv("PROCESS_DOCUMENTS_RAW_ROOT", str(tmp_path / "raw"))
    path = record_entity_visits(
        ["e1", "e2"],
        visited_at="2026-08-01T12:00:00+00:00",
        statuses={"e1": "SUCCESS_ZERO"},
        sources_by_entity={"e1": ["pncp", "ciga_ckan"]},
        meta_root=tmp_path / "meta",
    )
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "e1" in data["entities"]
    loaded = load_last_visits(meta_root=tmp_path / "meta")
    assert loaded["e1"] == "2026-08-01T12:00:00+00:00"
    assert loaded["e2"] == "2026-08-01T12:00:00+00:00"


def test_cli_incremental_help_exposes_daily_flags() -> None:
    from scripts.process_documents.cli import build_parser

    parser = build_parser()
    help_inc = parser.parse_args(["incremental", "--help"]) if False else None
    # argparse help exits; inspect option strings instead
    inc_action = None
    for action in parser._subparsers._group_actions:  # noqa: SLF001
        if getattr(action, "choices", None) and "incremental" in action.choices:
            inc_action = action.choices["incremental"]
            break
    assert inc_action is not None
    option_strings = {opt for a in inc_action._actions for opt in a.option_strings}  # noqa: SLF001
    assert "--single-source" in option_strings
    assert "--no-rotation" in option_strings
    assert "--limit" in option_strings
    _ = help_inc
