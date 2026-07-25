"""Official reference comparison — no invisible tables, no month mix."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.budget_audit.case_store import read_json, utc_now, write_json
from scripts.budget_audit.hashing import sha256_file
from scripts.budget_audit.units import units_compatible

REQUIRED_MANIFEST_FIELDS = (
    "system",
    "publisher",
    "source_url",
    "acquired_at",
    "reference_month",
    "locality",
    "tax_regime",
    "file_name",
    "size",
    "sha256",
    "license_or_access_note",
    "parser_version",
)


def validate_reference_manifest(manifest: dict[str, Any]) -> list[str]:
    errors = []
    for f in REQUIRED_MANIFEST_FIELDS:
        if f not in manifest or manifest[f] in (None, ""):
            errors.append(f"missing_field:{f}")
    return errors


def load_reference_manifest(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    data = read_json(path)
    errors = validate_reference_manifest(data)
    if errors:
        raise ValueError(f"invalid reference manifest: {errors}")
    # verify file hash if path present
    ref_file = data.get("file_path") or data.get("resolved_path")
    if ref_file and Path(ref_file).is_file():
        digest = sha256_file(ref_file)
        if digest != data["sha256"]:
            raise ValueError(
                f"reference file sha256 mismatch: manifest={data['sha256']} file={digest}"
            )
    return data


def load_reference_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Load reference items from JSON/JSONL attached to manifest."""
    items_path = manifest.get("items_path")
    if not items_path:
        return list(manifest.get("items") or [])
    p = Path(items_path)
    if not p.is_file():
        # try relative to manifest location
        return list(manifest.get("items") or [])
    if p.suffix.lower() == ".jsonl":
        rows = []
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows
    data = read_json(p)
    if isinstance(data, list):
        return data
    return list(data.get("items") or [])


def compare_to_references(
    budget_items: list[dict[str, Any]],
    reference_manifest: dict[str, Any],
    reference_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    refs = reference_items if reference_items is not None else load_reference_items(reference_manifest)
    ref_by_code: dict[str, dict[str, Any]] = {}
    for r in refs:
        if r.get("code"):
            ref_by_code[str(r["code"])] = r

    comparisons: list[dict[str, Any]] = []
    for it in budget_items:
        code = str(it["code"]) if it.get("code") else None
        ref = ref_by_code.get(code) if code else None
        if not ref:
            comparisons.append(
                {
                    "target_item": it.get("item_id"),
                    "target_value": it.get("unit_sale_price") or it.get("unit_direct_cost"),
                    "reference_item": None,
                    "comparison_status": "NO_REFERENCE",
                    "limitations": ["code_not_in_reference_snapshot"],
                }
            )
            continue

        # comparability gates
        limitations: list[str] = []
        same_unit = units_compatible(it.get("unit"), ref.get("unit"))
        if not same_unit:
            limitations.append("unit_mismatch")
        same_month = True
        if it.get("reference_month") and reference_manifest.get("reference_month"):
            same_month = str(it["reference_month"]) == str(reference_manifest["reference_month"])
            if not same_month:
                limitations.append("month_mismatch")
        same_locality = True
        if it.get("reference_locality") and reference_manifest.get("locality"):
            same_locality = str(it["reference_locality"]) == str(reference_manifest["locality"])
            if not same_locality:
                limitations.append("locality_mismatch")
        same_regime = True
        if it.get("reference_regime") and reference_manifest.get("tax_regime"):
            same_regime = str(it["reference_regime"]) == str(reference_manifest["tax_regime"])
            if not same_regime:
                limitations.append("tax_regime_mismatch")

        target_value = it.get("unit_direct_cost")
        if target_value is None:
            target_value = it.get("unit_sale_price")
            limitations.append("compared_sale_price_not_direct_cost")

        ref_value = ref.get("unit_price")
        if ref_value is None:
            ref_value = ref.get("unit_direct_cost")

        comparable = same_unit and same_month and same_locality and same_regime
        status = "COMPARABLE" if comparable and ref_value is not None else "NOT_COMPARABLE"
        if limitations and status == "COMPARABLE":
            status = "COMPARABLE_WITH_LIMITATIONS"

        diff_pct = None
        if (
            isinstance(target_value, (int, float))
            and isinstance(ref_value, (int, float))
            and ref_value != 0
        ):
            diff_pct = ((float(target_value) - float(ref_value)) / abs(float(ref_value))) * 100.0

        comparisons.append(
            {
                "target_item": it.get("item_id"),
                "target_value": target_value,
                "reference_item": ref.get("code") or ref.get("item_id"),
                "reference_value": ref_value,
                "same_code": True,
                "description_similarity": None,
                "same_unit": same_unit,
                "same_locality": same_locality,
                "same_month": same_month,
                "same_regime": same_regime,
                "same_scope": ref.get("scope") == it.get("scope") if ref.get("scope") else None,
                "comparison_status": status,
                "difference_pct": diff_pct,
                "limitations": limitations,
                "reference_system": reference_manifest.get("system"),
                "reference_month": reference_manifest.get("reference_month"),
                "note": "Difference % alone does not prove overprice/underprice/error",
            }
        )

    return {
        "compared_at": utc_now(),
        "reference_manifest": {
            k: reference_manifest.get(k) for k in REQUIRED_MANIFEST_FIELDS
        },
        "comparison_count": len(comparisons),
        "comparable_count": sum(
            1 for c in comparisons if c["comparison_status"].startswith("COMPARABLE")
        ),
        "comparisons": comparisons,
        "non_claims": [
            "Does not use internal table without origin",
            "Does not mix desonerado/nao-desonerado silently",
            "Does not call historical contract price official reference",
            "Does not treat semantic similarity as exact match",
        ],
    }


def write_official_reference_audit(case_dir: Path, result: dict[str, Any]) -> Path:
    out = Path(case_dir) / "audits" / "official-references.json"
    write_json(out, result)
    return out
