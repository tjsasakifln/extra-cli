"""Official SINAPI/SICRO reference ingest and comparison (no fixture-as-official).

Requires an external official snapshot with a complete provenance manifest.
Never labels synthetic/fixture rows as official reference.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.budget_audit.hashing import sha256_file
from scripts.budget_audit.references import (
    compare_to_references,
    load_reference_items,
    validate_reference_manifest,
)
from scripts.budget_audit.units import units_compatible


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _norm_desc(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^a-zA-Z0-9\s]", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def load_official_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    errors = validate_reference_manifest(data)
    if errors:
        raise ValueError(f"invalid official reference manifest: {errors}")
    system = str(data.get("system") or "").upper()
    if not any(s in system for s in ("SINAPI", "SICRO")):
        raise ValueError(
            f"manifest system={data.get('system')!r} is not an official SINAPI/SICRO source; "
            "refusing to treat as official"
        )
    if data.get("is_fixture") or data.get("synthetic") or data.get("is_demo_structure"):
        raise ValueError("fixture/synthetic/demo reference cannot be used as official")
    claim = str(data.get("claim_level") or "")
    if claim.startswith("STRUCTURE") or "NOT_OFFICIAL" in claim:
        raise ValueError(f"claim_level={claim!r} cannot be used as official")
    # verify file hash when present
    ref_file = data.get("file_path") or data.get("resolved_path")
    if ref_file and Path(ref_file).is_file():
        digest = sha256_file(ref_file)
        if digest != data.get("sha256"):
            raise ValueError("reference file sha256 mismatch")
    return data


def match_items(
    budget_items: list[dict[str, Any]],
    reference_manifest: dict[str, Any],
    reference_items: list[dict[str, Any]] | None = None,
    *,
    budget_competence: str | None = None,
    budget_locality: str | None = None,
) -> dict[str, Any]:
    refs = reference_items if reference_items is not None else load_reference_items(reference_manifest)
    ref_by_code = {str(r["code"]): r for r in refs if r.get("code")}
    ref_by_desc = {_norm_desc(str(r.get("description") or "")): r for r in refs if r.get("description")}

    ref_month = str(reference_manifest.get("reference_month") or "")
    ref_locality = str(reference_manifest.get("locality") or "")
    results: list[dict[str, Any]] = []

    for it in budget_items:
        code = str(it["code"]) if it.get("code") else None
        desc = _norm_desc(str(it.get("description") or it.get("descricao") or ""))
        unit = str(it.get("unit") or it.get("unidade") or "")
        ref = ref_by_code.get(code) if code else None
        status = "missing"
        score = 0.0
        human = True
        evidence: dict[str, Any] = {
            "budget_side": {
                "code": code,
                "description": it.get("description") or it.get("descricao"),
                "unit": unit,
                "competence": budget_competence,
                "locality": budget_locality,
            },
            "reference_side": {
                "system": reference_manifest.get("system"),
                "publisher": reference_manifest.get("publisher"),
                "source_url": reference_manifest.get("source_url"),
                "reference_month": ref_month,
                "locality": ref_locality,
                "sha256": reference_manifest.get("sha256"),
            },
        }

        if budget_competence and ref_month and budget_competence != ref_month:
            status = "competence_incompatible"
            score = 0.0
            human = True
            evidence["note"] = "competence_mismatch"
        elif ref is None and desc and desc in ref_by_desc:
            ref = ref_by_desc[desc]
            status = "approximate"
            score = 0.75
            human = True
            evidence["match_method"] = "normalized_description"
        elif ref is not None:
            ref_unit = str(ref.get("unit") or ref.get("unidade") or "")
            if unit and ref_unit and not units_compatible(unit, ref_unit):
                status = "unit_incompatible"
                score = 0.4
                human = True
                evidence["match_method"] = "code"
            else:
                status = "exact"
                score = 1.0
                human = False
                evidence["match_method"] = "code"
        else:
            status = "missing"
            score = 0.0
            human = True

        if ref is not None:
            evidence["reference_item"] = {
                "code": ref.get("code"),
                "description": ref.get("description"),
                "unit": ref.get("unit") or ref.get("unidade"),
                "price": ref.get("price") or ref.get("unit_price"),
            }

        results.append(
            {
                "status": status,
                "score": score,
                "requires_human_review": human,
                "budget_item_id": it.get("item_id") or it.get("code"),
                "evidence": evidence,
                "layer": {
                    "official_reference": ref is not None and status in {"exact", "approximate", "unit_incompatible"},
                    "edital_composition": True,
                    "internal_composition": False,
                    "inference": status == "approximate",
                },
            }
        )

    counts = {
        "exact": sum(1 for r in results if r["status"] == "exact"),
        "approximate": sum(1 for r in results if r["status"] == "approximate"),
        "missing": sum(1 for r in results if r["status"] == "missing"),
        "unit_incompatible": sum(1 for r in results if r["status"] == "unit_incompatible"),
        "competence_incompatible": sum(1 for r in results if r["status"] == "competence_incompatible"),
    }
    return {
        "generated_at": _now(),
        "reference_manifest_system": reference_manifest.get("system"),
        "reference_source_url": reference_manifest.get("source_url"),
        "is_official": True,
        "is_fixture": False,
        "counts": counts,
        "matches": results,
        "human_review_required": any(r["requires_human_review"] for r in results),
    }


def build_demo_official_snapshot(out_dir: Path) -> dict[str, Any]:
    """Create a *labeled* demo snapshot that is NOT claimable as live official download.

    Used only to exercise matching paths in CI when no licensed SINAPI dump is
    present. Manifest sets publisher note and is_demo_structure=true; loaders
    that require live official must still fail closed without a real file.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    items = [
        {"code": "88389", "description": "Concreto fck 25 MPa", "unit": "m3", "price": 450.0},
        {"code": "74109/001", "description": "Servente", "unit": "h", "price": 22.5},
        {"code": "99901", "description": "Tubo PVC 100mm", "unit": "m", "price": 35.0},
    ]
    items_path = out_dir / "items.json"
    items_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    digest = sha256_file(items_path)
    manifest = {
        "system": "SINAPI",
        "publisher": "CAIXA (demo structure — not a live official acquisition)",
        "source_url": "https://www.caixa.gov.br/site/Paginas/downloads.aspx",
        "acquired_at": _now(),
        "reference_month": "2026-06",
        "locality": "SC",
        "tax_regime": "desonerado",
        "file_name": "items.json",
        "file_path": str(items_path),
        "items_path": str(items_path),
        "size": items_path.stat().st_size,
        "sha256": digest,
        "license_or_access_note": (
            "Demo structure for matcher tests only. Not an official bulk dump. "
            "Do not present as live SINAPI acquisition."
        ),
        "parser_version": "production-readiness-1",
        "is_demo_structure": True,
        "is_fixture": False,
        "synthetic": False,
        "claim_level": "STRUCTURE_ONLY_NOT_OFFICIAL_ACQUISITION",
    }
    man_path = out_dir / "manifest.json"
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def compare_budget_to_official(
    budget_items: list[dict[str, Any]],
    manifest_path: Path,
    *,
    budget_competence: str | None = None,
    budget_locality: str | None = None,
    allow_demo_structure: bool = False,
) -> dict[str, Any]:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if manifest.get("is_demo_structure") and not allow_demo_structure:
        raise ValueError(
            "manifest is demo structure only; pass allow_demo_structure=True for "
            "matcher tests, never claim as official acquisition"
        )
    if not manifest.get("is_demo_structure"):
        manifest = load_official_manifest(manifest_path)
    else:
        errors = validate_reference_manifest(manifest)
        if errors:
            raise ValueError(errors)
    report = match_items(
        budget_items,
        manifest,
        budget_competence=budget_competence,
        budget_locality=budget_locality,
    )
    # also run budget_audit compare for arithmetic/value fields when codes match
    try:
        report["value_compare"] = compare_to_references(budget_items, manifest)
    except Exception as exc:  # noqa: BLE001
        report["value_compare_error"] = str(exc)
    report["claim_level"] = manifest.get("claim_level") or "OFFICIAL"
    report["is_demo_structure"] = bool(manifest.get("is_demo_structure"))
    return report
