"""Contract tests: produced feed matches Warmbly PR #4 required field shape.

Uses stdlib only (no jsonschema dep in CI). Schema files are loaded and their
``required`` keys are asserted against produced feeds.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.warmbly_bridge import (
    EPISTEMIC_CLASSES,
    REQUIRED_COMPANY_FIELDS,
    REQUIRED_FEED_FIELDS,
    REQUIRED_LEAD_FIELDS,
    REQUIRED_MESSAGING_FIELDS,
    REQUIRED_SOURCE_FIELDS,
    SCHEMA_OUTREACH,
)
from scripts.warmbly_bridge.export import ExportConfig, export_outreach


def _assert_required(obj: dict[str, Any], required: list[str] | tuple[str, ...], *, ctx: str) -> None:
    for field in required:
        assert field in obj, f"{ctx}: missing required field {field!r}"


def _validate_against_schema_required(feed: dict[str, Any], schema: dict[str, Any]) -> None:
    """Lightweight required-field / const check from frozen JSON Schema (no jsonschema lib)."""
    _assert_required(feed, schema.get("required") or [], ctx="feed")
    props = schema.get("properties") or {}
    sv = props.get("schema_version") or {}
    if "const" in sv:
        assert feed.get("schema_version") == sv["const"]
    source_schema = props.get("source") or {}
    _assert_required(feed.get("source") or {}, source_schema.get("required") or [], ctx="source")
    lead_def = (schema.get("$defs") or {}).get("lead") or {}
    lead_required = lead_def.get("required") or []
    for i, lead in enumerate(feed.get("leads") or []):
        _assert_required(lead, lead_required, ctx=f"leads[{i}]")
        company_req = ((lead_def.get("properties") or {}).get("company") or {}).get("required") or []
        _assert_required(lead.get("company") or {}, company_req, ctx=f"leads[{i}].company")
        msg_req = ((lead_def.get("properties") or {}).get("messaging_context") or {}).get("required") or []
        _assert_required(
            lead.get("messaging_context") or {},
            msg_req,
            ctx=f"leads[{i}].messaging_context",
        )


@pytest.fixture
def exported(tmp_path: Path, universe_path: Path, intel_path: Path, contacts_path: Path) -> Path:
    out = tmp_path / "out"
    result = export_outreach(
        ExportConfig(
            universe=universe_path,
            account_intelligence=intel_path,
            contacts=contacts_path,
            out_dir=out,
            generated_at="2026-08-06T12:00:00Z",
            repo_sha="testdeadbeef",
            max_leads_per_chunk=2,
        )
    )
    assert result["ok"] is True
    assert result["chunk_count"] >= 1
    return out


def test_manifest_and_chunks_exist(exported: Path) -> None:
    assert (exported / "manifest.json").is_file()
    chunks = sorted(exported.glob("chunk_*.json"))
    assert len(chunks) >= 1
    manifest = json.loads((exported / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["chunk_count"] == len(chunks)
    assert manifest["hashes"]["snapshot"]
    assert all(c["content_hash"] for c in manifest["chunks"])


def test_feed_required_fields_and_schema(
    exported: Path, schemas_dir: Path
) -> None:
    schema = json.loads((schemas_dir / "confenge.outreach.v1.json").read_text(encoding="utf-8"))
    for chunk_path in sorted(exported.glob("chunk_*.json")):
        feed = json.loads(chunk_path.read_text(encoding="utf-8"))
        for field in REQUIRED_FEED_FIELDS:
            assert field in feed, f"missing top-level {field} in {chunk_path.name}"
        assert feed["schema_version"] == SCHEMA_OUTREACH
        for field in REQUIRED_SOURCE_FIELDS:
            assert feed["source"].get(field), f"source.{field} required"
        assert "has_more" in feed["pagination"]
        assert "cursor" in feed["pagination"]
        assert feed["pagination"].get("content_hash") or feed["pagination"].get("hashes")
        _validate_against_schema_required(feed, schema)
        for lead in feed["leads"]:
            for field in REQUIRED_LEAD_FIELDS:
                assert field in lead, f"lead missing {field}"
            for field in REQUIRED_COMPANY_FIELDS:
                assert lead["company"].get(field), f"company.{field}"
            assert len(lead["company"]["cnpj14"]) == 14
            for field in REQUIRED_MESSAGING_FIELDS:
                assert field in lead["messaging_context"]
            assert isinstance(lead["contacts"], list)
            assert isinstance(lead["contracts"], list)
            assert isinstance(lead["evidence"], list)
            assert "rank" in lead["priority"]
            assert "score" in lead["priority"]
            assert "code" in lead["moment"] or "summary" in lead["moment"]
            assert "service_code" in lead["offer"] or "service_name" in lead["offer"]
            assert lead["commercial_state"]


def test_inferences_not_promoted_to_confirmed_fact(exported: Path) -> None:
    found_inference = False
    for chunk_path in sorted(exported.glob("chunk_*.json")):
        feed = json.loads(chunk_path.read_text(encoding="utf-8"))
        for lead in feed["leads"]:
            for ev in lead["evidence"]:
                assert ev["epistemic_class"] in EPISTEMIC_CLASSES
                if str(ev.get("id", "")).startswith("inf-") or "INFERENCE" in str(ev.get("type", "")).upper():
                    found_inference = True
                    assert ev["epistemic_class"] != "CONFIRMED_FACT"
                if ev.get("type") in {
                    "STRUCTURE_INFERENCE",
                    "COMMERCIAL_HYPOTHESIS",
                }:
                    assert ev["epistemic_class"] != "CONFIRMED_FACT"
    assert found_inference, "fixtures should include at least one inference evidence item"


def test_dnc_preserved_as_dominant(exported: Path) -> None:
    states = {}
    for chunk_path in sorted(exported.glob("chunk_*.json")):
        feed = json.loads(chunk_path.read_text(encoding="utf-8"))
        for lead in feed["leads"]:
            states[lead["company"]["cnpj14"]] = lead["commercial_state"]
    assert states.get("66777888000199") == "DO_NOT_CONTACT"


def test_no_final_marketing_copy_keys(exported: Path) -> None:
    forbidden = {"whatsapp_short", "email_initial", "call_script", "body_html", "subject_final"}
    for chunk_path in sorted(exported.glob("chunk_*.json")):
        blob = chunk_path.read_text(encoding="utf-8")
        for key in forbidden:
            assert key not in blob


def test_empty_contacts_allowed(exported: Path) -> None:
    """Warmbly NEEDS_CONTACT path: missing contacts stay empty."""
    found = False
    for chunk_path in sorted(exported.glob("chunk_*.json")):
        feed = json.loads(chunk_path.read_text(encoding="utf-8"))
        for lead in feed["leads"]:
            if lead["company"]["cnpj14"] == "55444333000122":
                assert lead["contacts"] == []
                found = True
    assert found
