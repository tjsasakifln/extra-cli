"""Structural + optional JSON Schema validation for OCDS-inspired packages."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def validate_release_structure(release: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not release.get("ocid") and not release.get("id"):
        issues.append("missing_ocid_and_id")
    tags = release.get("tag") or []
    if not isinstance(tags, list) or not tags:
        issues.append("missing_tag")
    if "tender" in tags and not isinstance(release.get("tender"), dict):
        issues.append("tender_tag_without_tender_object")
    if "contract" in tags and not isinstance(release.get("contracts"), list):
        issues.append("contract_tag_without_contracts")
    prov = release.get("extra:provenance") or {}
    if not prov.get("source"):
        issues.append("missing_provenance_source")
    # Value semantics for contracts
    if "contract" in tags:
        vs = release.get("extra:value_semantics") or {}
        if vs.get("is_paid") is True:
            issues.append("contract_marked_paid_without_payment_observation")
    return issues


def validate_release_package(
    package: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    releases = package.get("releases") or []
    structural_issues: list[dict[str, Any]] = []
    for i, rel in enumerate(releases):
        if not isinstance(rel, dict):
            structural_issues.append({"index": i, "issues": ["release_not_object"]})
            continue
        iss = validate_release_structure(rel)
        if iss:
            structural_issues.append({"index": i, "ocid": rel.get("ocid"), "issues": iss})

    schema_report: dict[str, Any] = {"attempted": False}
    if schema_path and Path(schema_path).is_file():
        schema_report = _validate_against_release_schema(releases, Path(schema_path))

    return {
        "structural_ok": not structural_issues,
        "n_releases": len(releases),
        "structural_issues": structural_issues,
        "schema": schema_report,
        "notes": [
            "extra:* extension fields are intentional and typically fail strict OCDS schema",
            "local tender.status vocab is not forced into OCDS enums",
            "physical PostgreSQL model remains non-OCDS",
        ],
    }


def _validate_against_release_schema(
    releases: list[dict[str, Any]], schema_path: Path
) -> dict[str, Any]:
    try:
        import json

        import jsonschema
    except ImportError as exc:  # pragma: no cover
        return {"attempted": True, "ok": False, "error": f"jsonschema_missing:{exc}"}

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    # OCDS release-schema validates a single release object
    errors: list[dict[str, Any]] = []
    for i, rel in enumerate(releases):
        # Strip extension keys for an optional "core-only" pass is NOT done here —
        # we document honest failures when extra:* present.
        try:
            jsonschema.validate(instance=rel, schema=schema)
        except jsonschema.ValidationError as err:
            errors.append(
                {
                    "index": i,
                    "ocid": rel.get("ocid"),
                    "message": err.message,
                    "path": list(err.path),
                }
            )
    return {
        "attempted": True,
        "schema_path": str(schema_path),
        "ok": len(errors) == 0,
        "n_errors": len(errors),
        "errors_sample": errors[:10],
        "interpretation": (
            "strict_pass"
            if not errors
            else "expected_fail_with_extensions_or_local_vocab"
        ),
    }
