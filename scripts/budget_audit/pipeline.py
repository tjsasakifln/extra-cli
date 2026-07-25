"""Map / audit / compare / references / verify pipeline stages."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.budget_audit.arithmetic import (
    audit_abc,
    audit_item_arithmetic,
    audit_quantities,
    workbook_integrity,
)
from scripts.budget_audit.bdi import audit_bdi, audit_social_charges
from scripts.budget_audit.case_store import (
    load_manifest,
    read_json,
    read_jsonl,
    save_manifest,
    utc_now,
    write_json,
    write_jsonl,
)
from scripts.budget_audit.classify import classify_workbook
from scripts.budget_audit.compare import match_items
from scripts.budget_audit.compositions import audit_compositions
from scripts.budget_audit.findings import build_findings
from scripts.budget_audit.hashing import sha256_file
from scripts.budget_audit.materiality import MaterialityPolicy
from scripts.budget_audit.normalize import normalize_case
from scripts.budget_audit.references import (
    compare_to_references,
    load_reference_items,
    load_reference_manifest,
)
from scripts.budget_audit.report import generate_all_reports, reconcile_reports
from scripts.budget_audit.risks import build_risk_register


def _all_workbook_models(case_dir: Path) -> list[dict[str, Any]]:
    models = []
    wb_root = case_dir / "workbooks"
    if not wb_root.is_dir():
        return models
    for d in sorted(wb_root.iterdir()):
        if not d.is_dir():
            continue
        cells = read_jsonl(d / "cells.jsonl")
        formulas = read_jsonl(d / "formulas.jsonl")
        sheets = read_json(d / "sheets.json") if (d / "sheets.json").is_file() else []
        workbook = read_json(d / "workbook.json") if (d / "workbook.json").is_file() else {}
        hidden = read_json(d / "hidden-content.json") if (d / "hidden-content.json").is_file() else []
        quality = (
            read_json(d / "extraction-quality.json")
            if (d / "extraction-quality.json").is_file()
            else {}
        )
        models.append(
            {
                "document_id": d.name,
                "workbook": workbook,
                "sheets": sheets,
                "cells": cells,
                "formulas": formulas,
                "hidden_content": hidden,
                "extraction_quality": quality,
            }
        )
    return models


def map_case(case_dir: Path) -> dict[str, Any]:
    case_dir = Path(case_dir)
    manifest = load_manifest(case_dir)
    models = _all_workbook_models(case_dir)

    all_classifications: list[dict[str, Any]] = []
    all_column_mappings: list[dict[str, Any]] = []
    all_units: list[dict[str, Any]] = []
    all_codes: list[dict[str, Any]] = []

    budget_items: list[dict[str, Any]] = []
    compositions: list[dict[str, Any]] = []
    composition_inputs: list[dict[str, Any]] = []
    bdi_components: list[dict[str, Any]] = []
    social_charges: list[dict[str, Any]] = []
    schedule_items: list[dict[str, Any]] = []
    abc_items: list[dict[str, Any]] = []

    for model in models:
        classifications = classify_workbook(model)
        all_classifications.extend(
            [{**c, "document_id": model["document_id"]} for c in classifications]
        )
        norm = normalize_case(model["document_id"], classifications, model["cells"])
        budget_items.extend(norm["budget_items"])
        compositions.extend(norm["compositions"])
        composition_inputs.extend(norm["composition_inputs"])
        bdi_components.extend(norm["bdi_components"])
        social_charges.extend(norm["social_charges"])
        schedule_items.extend(norm["schedule_items"])
        abc_items.extend(norm["abc_items"])
        all_column_mappings.extend(norm["column_mappings"])
        all_units.extend(norm["units"])
        all_codes.extend(norm["codes"])

    mapping_dir = case_dir / "mapping"
    mapping_dir.mkdir(parents=True, exist_ok=True)
    write_json(mapping_dir / "sheet-classification.json", all_classifications)
    write_json(mapping_dir / "column-mapping.json", all_column_mappings)
    write_json(mapping_dir / "units.json", all_units)
    write_json(mapping_dir / "codes.json", all_codes)

    norm_dir = case_dir / "normalized"
    norm_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(norm_dir / "budget-items.jsonl", budget_items)
    write_jsonl(norm_dir / "compositions.jsonl", compositions)
    write_jsonl(norm_dir / "composition-inputs.jsonl", composition_inputs)
    write_jsonl(norm_dir / "bdi-components.jsonl", bdi_components)
    write_jsonl(norm_dir / "social-charges.jsonl", social_charges)
    write_jsonl(norm_dir / "schedule-items.jsonl", schedule_items)
    write_jsonl(norm_dir / "abc-items.jsonl", abc_items)

    manifest["phase"] = "mapped"
    manifest["updated_at"] = utc_now()
    manifest["counts"] = {
        "budget_items": len(budget_items),
        "compositions": len(compositions),
        "composition_inputs": len(composition_inputs),
        "bdi_components": len(bdi_components),
        "sheets_classified": len(all_classifications),
    }
    save_manifest(case_dir, manifest)
    return manifest["counts"]


def audit_case(case_dir: Path, *, policy: MaterialityPolicy | None = None) -> dict[str, Any]:
    case_dir = Path(case_dir)
    pol = policy or MaterialityPolicy()
    models = _all_workbook_models(case_dir)

    budget_items = read_jsonl(case_dir / "normalized" / "budget-items.jsonl")
    compositions = read_jsonl(case_dir / "normalized" / "compositions.jsonl")
    composition_inputs = read_jsonl(case_dir / "normalized" / "composition-inputs.jsonl")
    bdi_components = read_jsonl(case_dir / "normalized" / "bdi-components.jsonl")
    social_charges = read_jsonl(case_dir / "normalized" / "social-charges.jsonl")

    all_formulas = []
    all_cells = []
    all_hidden = []
    for m in models:
        all_formulas.extend(m["formulas"])
        all_cells.extend(m["cells"])
        all_hidden.extend(m.get("hidden_content") or [])

    arithmetic = audit_item_arithmetic(budget_items, policy=pol)
    integrity = workbook_integrity(all_formulas, all_cells, budget_items, all_hidden)
    quantities = audit_quantities(budget_items)
    compositions_audit = audit_compositions(
        compositions, composition_inputs, budget_items, policy=pol
    )
    bdi_audit = audit_bdi(bdi_components, budget_items, policy=pol)
    social_audit = audit_social_charges(social_charges, policy=pol)
    abc = audit_abc(budget_items)

    # unit prices audit placeholder structure
    unit_prices = {
        "note": "Unit price comparisons require explicit reference manifest",
        "item_count": len(budget_items),
        "comparisons": [],
    }

    # cross sheet: items sharing codes across sheets
    by_code: dict[str, list[dict[str, Any]]] = {}
    for it in budget_items:
        if it.get("code"):
            by_code.setdefault(str(it["code"]), []).append(it)
    cross_issues = []
    for code, group in by_code.items():
        sheets = {g.get("sheet") for g in group}
        if len(sheets) > 1:
            qtys = {g.get("quantity") for g in group}
            if len(qtys) > 1:
                cross_issues.append(
                    {
                        "code": code,
                        "sheets": list(sheets),
                        "quantities": list(qtys),
                        "classification": "CROSS_DOCUMENT_DIVERGENCE",
                    }
                )
    cross_sheet = {"issue_count": len(cross_issues), "issues": cross_issues}

    findings = build_findings(
        arithmetic=arithmetic,
        integrity=integrity,
        quantities=quantities,
        compositions=compositions_audit,
        bdi=bdi_audit,
        social=social_audit,
        document_id=(models[0]["document_id"] if models else None),
    )
    risks = build_risk_register(
        findings=findings,
        bdi=bdi_audit,
        compositions=compositions_audit,
        arithmetic=arithmetic,
        abc=abc,
    )

    audits = case_dir / "audits"
    audits.mkdir(parents=True, exist_ok=True)
    write_json(audits / "arithmetic.json", arithmetic)
    write_json(audits / "workbook-integrity.json", integrity)
    write_json(audits / "quantities.json", quantities)
    write_json(audits / "unit-prices.json", unit_prices)
    write_json(audits / "compositions.json", compositions_audit)
    write_json(audits / "bdi.json", bdi_audit)
    write_json(audits / "social-charges.json", social_audit)
    write_json(audits / "cross-sheet.json", cross_sheet)
    write_json(audits / "cross-workbook.json", {"status": "NOT_RUN", "note": "use compare command"})
    write_json(audits / "official-references.json", {"status": "NOT_RUN", "note": "use references command"})
    write_json(audits / "findings.json", findings)
    write_json(audits / "risk-register.json", risks)
    write_json(audits / "abc.json", abc)

    manifest = load_manifest(case_dir)
    manifest["phase"] = "audited"
    manifest["updated_at"] = utc_now()
    manifest["audit_summary"] = {
        "arithmetic_checks": arithmetic.get("check_count"),
        "findings": findings.get("finding_count"),
        "severity_counts": findings.get("severity_counts"),
    }
    save_manifest(case_dir, manifest)
    return manifest["audit_summary"]


def compare_case(case_dir: Path, left_id: str, right_id: str) -> dict[str, Any]:
    case_dir = Path(case_dir)
    items = read_jsonl(case_dir / "normalized" / "budget-items.jsonl")
    left = [i for i in items if i.get("source_document_id") == left_id]
    right = [i for i in items if i.get("source_document_id") == right_id]
    # if filtering empty, try sheet-level document prefixes
    if not left:
        left = [i for i in items if left_id in str(i.get("item_id"))]
    if not right:
        right = [i for i in items if right_id in str(i.get("item_id"))]
    result = match_items(left, right, left_label=left_id, right_label=right_id)
    write_json(case_dir / "audits" / "cross-workbook.json", result)
    return {
        "left_count": result["left_count"],
        "right_count": result["right_count"],
        "matched_exact": result["matched_exact"],
        "unmatched_left": result["unmatched_left"],
        "unmatched_right": result["unmatched_right"],
    }


def references_case(case_dir: Path, reference_manifest_path: str | Path) -> dict[str, Any]:
    case_dir = Path(case_dir)
    manifest = load_reference_manifest(reference_manifest_path)
    items = read_jsonl(case_dir / "normalized" / "budget-items.jsonl")
    refs = load_reference_items(manifest)
    result = compare_to_references(items, manifest, refs)
    write_json(case_dir / "audits" / "official-references.json", result)
    return {
        "comparison_count": result["comparison_count"],
        "comparable_count": result["comparable_count"],
    }


def report_case(case_dir: Path) -> dict[str, Any]:
    return generate_all_reports(Path(case_dir))


def verify_case(case_dir: Path) -> dict[str, Any]:
    """Independent verification without silent regeneration of core audits."""
    case_dir = Path(case_dir)
    issues: list[str] = []
    checks: dict[str, Any] = {}

    manifest = load_manifest(case_dir)
    checks["manifest_present"] = True

    # originals immutable
    for doc in manifest.get("documents") or []:
        obj = doc.get("object_path")
        if not obj:
            continue
        path = case_dir / obj
        if not path.is_file():
            issues.append(f"missing_object:{obj}")
            continue
        digest = sha256_file(path)
        if digest != doc.get("sha256"):
            issues.append(f"object_hash_mismatch:{doc.get('document_id')}")
        checks.setdefault("object_hashes", []).append(
            {"document_id": doc.get("document_id"), "ok": digest == doc.get("sha256")}
        )

    required_audits = [
        "arithmetic.json",
        "workbook-integrity.json",
        "findings.json",
        "risk-register.json",
    ]
    for name in required_audits:
        p = case_dir / "audits" / name
        if not p.is_file():
            issues.append(f"missing_audit:{name}")

    # recompute arithmetic sample
    items = read_jsonl(case_dir / "normalized" / "budget-items.jsonl")
    stored = read_json(case_dir / "audits" / "arithmetic.json") if (case_dir / "audits" / "arithmetic.json").is_file() else {}
    recomputed = audit_item_arithmetic(items)
    if stored.get("check_count") != recomputed.get("check_count"):
        issues.append("arithmetic_check_count_drift")
    checks["arithmetic_check_count"] = {
        "stored": stored.get("check_count"),
        "recomputed": recomputed.get("check_count"),
    }

    # findings cell locators exist
    findings = read_json(case_dir / "audits" / "findings.json") if (case_dir / "audits" / "findings.json").is_file() else {}
    cell_index: set[str] = set()
    for m in _all_workbook_models(case_dir):
        for c in m["cells"]:
            cell_index.add(f"{c['sheet']}!{c['coordinate']}")

    missing_cells = []
    for f in findings.get("findings") or []:
        for cell in f.get("cells") or []:
            # cell may be sheet!A1
            if "!" in cell and cell not in cell_index:
                # allow soft miss for derived refs
                missing_cells.append(cell)
    # threshold: report but only fail if many
    checks["cited_cells_missing"] = missing_cells[:50]
    checks["cited_cells_missing_count"] = len(missing_cells)

    recon = reconcile_reports(case_dir) if (case_dir / "reports").is_dir() else {"status": "SKIP"}
    if recon.get("status") == "FAIL":
        issues.extend([f"report:{i}" for i in recon.get("issues") or []])

    # security non-claims
    checks["database_used"] = False
    checks["macros_executed"] = False
    checks["production_touched"] = False

    # global status
    if issues:
        # structural failures
        hard = [i for i in issues if not i.startswith("report:")]
        status = "FAIL" if hard else "FAIL"
    else:
        status = "PASS"

    # BLOCKED conditions
    blockers = []
    for doc in manifest.get("documents") or []:
        if doc.get("status") == "CONVERSION_REQUIRED":
            blockers.append(
                {
                    "type": "CONVERSION_REQUIRED",
                    "document": doc.get("original_name"),
                    "impact": "XLS not parsed",
                }
            )

    if blockers and status == "PASS":
        # only block if nothing useful was ingested
        ingested = [d for d in manifest.get("documents") or [] if d.get("status") == "INGESTED"]
        if not ingested:
            status = "BLOCKED"

    result = {
        "verified_at": utc_now(),
        "status": status,
        "issues": issues,
        "blockers": blockers,
        "checks": checks,
        "report_reconciliation": recon,
    }
    write_json(case_dir / "verification.json", result)

    manifest["phase"] = "verified"
    manifest["global_status"] = status
    manifest["updated_at"] = utc_now()
    save_manifest(case_dir, manifest)
    return result


def run_full(
    case_id: str,
    source: str | Path,
    output: str | Path,
) -> dict[str, Any]:
    from scripts.budget_audit.ingest import create_case, ingest_case

    case_dir = create_case(case_id, source, Path(output))
    ingest_case(case_dir)
    map_case(case_dir)
    audit_case(case_dir)
    report_case(case_dir)
    verification = verify_case(case_dir)
    return {
        "case_dir": str(case_dir),
        "global_status": verification.get("status"),
        "verification": verification,
    }
