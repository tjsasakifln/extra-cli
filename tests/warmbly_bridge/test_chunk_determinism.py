"""Chunk determinism + resume/idempotency."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.warmbly_bridge.export import (
    ExportConfig,
    _chunk_leads,
    _decision_cursor,
    _encode_chunk,
    _encoded_lead_item_size,
    _provisional_chunk_size,
    export_outreach,
)


def _file_hashes(out: Path) -> dict[str, str]:
    result = {}
    for p in sorted(out.glob("chunk_*.json")):
        result[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def test_incremental_provisional_size_matches_canonical_encoding() -> None:
    leads = [
        {"source_lead_id": "a", "company": {"cnpj14": "00000000000001"}, "label": "ASCII"},
        {
            "source_lead_id": "b",
            "company": {"cnpj14": "00000000000002"},
            "label": "Construção çã 🚧",
            "nested": {"items": [1, 2, {"ok": True}]},
        },
    ]
    source = {"system": "extra-cli", "run_id": "run-size"}
    generated_at = "2026-08-12T12:00:00Z"
    pagination = {
        "chunk_index": 7,
        "content_hash": "0" * 64,
        "cursor": _decision_cursor(leads[0]),
        "has_more": True,
        "hashes": {"leads": "0" * 64, "snapshot": "0" * 64},
        "next_cursor": _decision_cursor(leads[1]),
    }
    feed = {
        "schema_version": "confenge.outreach.v1",
        "generated_at": generated_at,
        "source": source,
        "pagination": pagination,
        "leads": leads,
    }

    measured = _provisional_chunk_size(
        lead_item_bytes=sum(_encoded_lead_item_size(lead) for lead in leads),
        lead_count=len(leads),
        source=source,
        generated_at=generated_at,
        cursor=pagination["cursor"],
        chunk_index=pagination["chunk_index"],
        next_cursor=pagination["next_cursor"],
        snapshot_hash="0" * 64,
    )

    assert measured == len(_encode_chunk(feed))
    packed_without_hashes = {
        **feed,
        "pagination": {
            "cursor": pagination["cursor"],
            "next_cursor": pagination["next_cursor"],
            "has_more": True,
            "chunk_index": 7,
            "content_hash": "a" * 64,
            "hashes": {"leads": "b" * 64, "snapshot": "c" * 64},
        },
    }
    assert measured == len(_encode_chunk(packed_without_hashes))


def test_packed_chunks_stay_under_byte_ceiling_after_hash_fields_are_added() -> None:
    """Live publication failed when packing ignored post-pack content hashes."""
    leads = [
        {
            "source_lead_id": f"lead-{idx}",
            "company": {"cnpj14": f"{idx:014d}"},
            "target_fit_source_watermark": "wm",
            "target_fit_computed_at": "2026-08-28T00:00:00Z",
            "note": "payload " * 40,
        }
        for idx in range(1, 40)
    ]
    source = {"system": "extra-cli", "run_id": "run-ceiling", "snapshot_hash": "s" * 64}
    generated_at = "2026-08-28T04:00:00Z"
    max_bytes = 12_000
    packed = _chunk_leads(
        leads,
        max_leads=100,
        max_bytes=max_bytes,
        source=source,
        generated_at=generated_at,
    )
    assert len(packed) > 1
    for slice_leads, pagination in packed:
        leads_hash = "a" * 64
        feed = {
            "schema_version": "confenge.outreach.v1",
            "generated_at": generated_at,
            "source": source,
            "pagination": {
                **pagination,
                "content_hash": leads_hash,
                "hashes": {"leads": leads_hash, "snapshot": source["snapshot_hash"]},
            },
            "leads": slice_leads,
        }
        assert len(_encode_chunk(feed)) <= max_bytes


def test_reexport_same_inputs_same_hashes(
    tmp_path: Path, universe_path: Path, intel_path: Path, contacts_path: Path
) -> None:
    out = tmp_path / "out"
    cfg = ExportConfig(
        universe=universe_path,
        account_intelligence=intel_path,
        contacts=contacts_path,
        out_dir=out,
        generated_at="2026-08-06T12:00:00Z",
        repo_sha="fixedsha",
        max_leads_per_chunk=2,
    )
    r1 = export_outreach(cfg)
    h1 = _file_hashes(out)
    assert r1["chunk_count"] == len(h1)

    r2 = export_outreach(cfg)
    h2 = _file_hashes(out)
    assert h1 == h2
    assert all(c["status"] == "unchanged" for c in r2["chunks"])


def test_resume_without_generated_at_override_reuses_manifest_time(
    tmp_path: Path, universe_path: Path, intel_path: Path, contacts_path: Path
) -> None:
    out = tmp_path / "out"
    cfg1 = ExportConfig(
        universe=universe_path,
        account_intelligence=intel_path,
        contacts=contacts_path,
        out_dir=out,
        generated_at="2026-08-06T12:00:00Z",
        repo_sha="fixedsha",
        max_leads_per_chunk=3,
    )
    export_outreach(cfg1)
    h1 = _file_hashes(out)

    # Second run omits generated_at; must reuse prior for same snapshot.
    cfg2 = ExportConfig(
        universe=universe_path,
        account_intelligence=intel_path,
        contacts=contacts_path,
        out_dir=out,
        generated_at=None,
        repo_sha=None,
        max_leads_per_chunk=3,
    )
    r2 = export_outreach(cfg2)
    h2 = _file_hashes(out)
    assert h1 == h2
    assert all(c["status"] == "unchanged" for c in r2["chunks"])


def test_pagination_has_more_and_cursor(
    tmp_path: Path, universe_path: Path, intel_path: Path, contacts_path: Path
) -> None:
    out = tmp_path / "out"
    export_outreach(
        ExportConfig(
            universe=universe_path,
            account_intelligence=intel_path,
            contacts=contacts_path,
            out_dir=out,
            generated_at="2026-08-06T12:00:00Z",
            repo_sha="fixedsha",
            max_leads_per_chunk=2,
        )
    )
    chunks = sorted(out.glob("chunk_*.json"))
    assert len(chunks) >= 2
    first = json.loads(chunks[0].read_text(encoding="utf-8"))
    last = json.loads(chunks[-1].read_text(encoding="utf-8"))
    assert first["pagination"]["has_more"] is True
    assert first["pagination"]["next_cursor"]
    assert last["pagination"]["has_more"] is False
    assert last["pagination"]["next_cursor"] is None


def test_limit_smoke(
    tmp_path: Path, universe_path: Path, intel_path: Path, contacts_path: Path
) -> None:
    out = tmp_path / "out"
    result = export_outreach(
        ExportConfig(
            universe=universe_path,
            account_intelligence=intel_path,
            contacts=contacts_path,
            out_dir=out,
            limit=1,
            generated_at="2026-08-06T12:00:00Z",
            repo_sha="fixedsha",
        )
    )
    assert result["lead_count"] == 1
    feed = json.loads((out / "chunk_0000.json").read_text(encoding="utf-8"))
    assert len(feed["leads"]) == 1
