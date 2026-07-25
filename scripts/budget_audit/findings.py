"""Finding matrix construction from audit results."""

from __future__ import annotations

from typing import Any

from scripts.budget_audit.case_store import utc_now


def _finding(
    finding_id: str,
    *,
    severity: str,
    classification: str,
    title: str,
    description: str,
    objective_observation: str,
    interpretation: str,
    source_document: str | None = None,
    sheet: str | None = None,
    cells: list[str] | None = None,
    formula: str | None = None,
    reported_value: Any = None,
    recomputed_value: Any = None,
    difference: Any = None,
    affected_amount: Any = None,
    materiality_pct: Any = None,
    evidence: Any = None,
    limitations: list[str] | None = None,
    recommended_action: str | None = None,
    review_status: str = "OPEN",
) -> dict[str, Any]:
    return {
        "finding_id": finding_id,
        "severity": severity,
        "classification": classification,
        "title": title,
        "description": description,
        "objective_observation": objective_observation,
        "interpretation": interpretation,
        "affected_amount": affected_amount,
        "materiality_pct": materiality_pct,
        "source_document": source_document,
        "sheet": sheet,
        "cells": cells or [],
        "formula": formula,
        "reported_value": reported_value,
        "recomputed_value": recomputed_value,
        "difference": difference,
        "evidence": evidence,
        "limitations": limitations or [],
        "recommended_action": recommended_action or "Human engineer review",
        "review_status": review_status,
    }


def build_findings(
    *,
    arithmetic: dict[str, Any] | None = None,
    integrity: dict[str, Any] | None = None,
    quantities: dict[str, Any] | None = None,
    compositions: dict[str, Any] | None = None,
    bdi: dict[str, Any] | None = None,
    social: dict[str, Any] | None = None,
    references: dict[str, Any] | None = None,
    document_id: str | None = None,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    n = 0

    def nid() -> str:
        nonlocal n
        n += 1
        return f"F-{n:04d}"

    if arithmetic:
        for c in arithmetic.get("checks") or []:
            if c.get("status") == "MATERIAL_DIFFERENCE":
                findings.append(
                    _finding(
                        nid(),
                        severity=c.get("severity_hint") or "HIGH",
                        classification="ARITHMETIC_ERROR",
                        title="Material arithmetic difference",
                        description="Reported total diverges from quantity × unit price beyond materiality",
                        objective_observation=(
                            f"reported={c.get('reported_value')} recomputed={c.get('recomputed_value')} "
                            f"abs_diff={c.get('absolute_difference')}"
                        ),
                        interpretation="Objective arithmetic inconsistency under declared operands",
                        source_document=document_id,
                        cells=c.get("source_cells") or [],
                        formula=c.get("formula_expected"),
                        reported_value=c.get("reported_value"),
                        recomputed_value=c.get("recomputed_value"),
                        difference=c.get("absolute_difference"),
                        affected_amount=c.get("absolute_difference"),
                        evidence=c,
                        recommended_action="Verify source cells and formula cache",
                    )
                )
            elif c.get("status") == "ROUNDING_DIFFERENCE":
                findings.append(
                    _finding(
                        nid(),
                        severity="LOW",
                        classification="ARITHMETIC_ERROR",
                        title="Rounding difference",
                        description="Small arithmetic difference within materiality band",
                        objective_observation=str(c.get("absolute_difference")),
                        interpretation="Likely rounding; not classified as material error",
                        source_document=document_id,
                        cells=c.get("source_cells") or [],
                        reported_value=c.get("reported_value"),
                        recomputed_value=c.get("recomputed_value"),
                        difference=c.get("absolute_difference"),
                        evidence=c,
                    )
                )

    if integrity:
        for issue in integrity.get("formula_issues") or []:
            kind = issue.get("kind")
            sev = "HIGH" if kind == "BROKEN_REFERENCE" else "MEDIUM"
            findings.append(
                _finding(
                    nid(),
                    severity=sev,
                    classification="FORMULA_ERROR",
                    title=f"Formula issue: {kind}",
                    description=f"Formula status {kind}",
                    objective_observation=f"formula={issue.get('formula')} cache={issue.get('cached_value')}",
                    interpretation="Do not treat missing cache as zero",
                    source_document=document_id,
                    sheet=issue.get("sheet"),
                    cells=issue.get("cells") or [],
                    formula=issue.get("formula"),
                    evidence=issue,
                )
            )
        for issue in integrity.get("value_issues") or []:
            findings.append(
                _finding(
                    nid(),
                    severity="MEDIUM" if issue.get("kind") == "NEGATIVE_VALUE" else "LOW",
                    classification="MISSING_VALUE" if "MISSING" in str(issue.get("kind")) else "ARITHMETIC_ERROR",
                    title=str(issue.get("kind")),
                    description=str(issue),
                    objective_observation=str(issue),
                    interpretation="Structural integrity signal",
                    source_document=document_id,
                    sheet=issue.get("sheet"),
                    cells=issue.get("cells") or [],
                    evidence=issue,
                )
            )
        for issue in integrity.get("duplication_issues") or []:
            findings.append(
                _finding(
                    nid(),
                    severity="MEDIUM",
                    classification="POSSIBLE_DUPLICATION",
                    title=str(issue.get("kind")),
                    description=str(issue),
                    objective_observation=str(issue),
                    interpretation="Duplication requires engineer confirmation of intent",
                    source_document=document_id,
                    cells=issue.get("cells") or [],
                    evidence=issue,
                )
            )

    if quantities:
        for issue in quantities.get("issues") or []:
            sev = "HIGH" if issue.get("classification") == "CONFIRMED_ARITHMETIC_ERROR" else "MEDIUM"
            findings.append(
                _finding(
                    nid(),
                    severity=sev,
                    classification="QUANTITY_DIVERGENCE",
                    title=str(issue.get("kind")),
                    description=str(issue.get("classification")),
                    objective_observation=str(issue),
                    interpretation="Quantity signal — not automatic proof of error vs other sheets",
                    source_document=document_id,
                    cells=issue.get("cells") or [],
                    evidence=issue,
                    limitations=["Cross-sheet divergence is not auto-error"],
                )
            )

    if compositions:
        for issue in compositions.get("issues") or []:
            findings.append(
                _finding(
                    nid(),
                    severity="MEDIUM",
                    classification="COMPOSITION_GAP",
                    title=str(issue.get("kind")),
                    description=str(issue),
                    objective_observation=str(issue),
                    interpretation="Composition structural gap",
                    source_document=document_id,
                    cells=issue.get("cells") or [],
                    evidence=issue,
                )
            )
        for c in compositions.get("checks") or []:
            if c.get("status") == "MATERIAL_DIFFERENCE":
                findings.append(
                    _finding(
                        nid(),
                        severity="HIGH",
                        classification="COMPOSITION_GAP",
                        title="Composition arithmetic material difference",
                        description="coefficient × price ≠ total",
                        objective_observation=str(c),
                        interpretation="Objective arithmetic inconsistency in composition input",
                        source_document=document_id,
                        cells=c.get("source_cells") or [],
                        reported_value=c.get("reported_value"),
                        recomputed_value=c.get("recomputed_value"),
                        difference=c.get("absolute_difference"),
                        evidence=c,
                    )
                )

    if bdi:
        for issue in bdi.get("issues") or []:
            findings.append(
                _finding(
                    nid(),
                    severity="HIGH" if "DOUBLE_BDI" in str(issue.get("kind")) else "MEDIUM",
                    classification="BDI_INCONSISTENCY",
                    title=str(issue.get("kind")),
                    description=str(issue.get("classification") or issue.get("kind")),
                    objective_observation=str(issue),
                    interpretation="BDI structural/arithmetic signal — not legal judgment",
                    source_document=document_id,
                    cells=issue.get("cells") or [],
                    evidence=issue,
                    limitations=list(bdi.get("non_claims") or []),
                )
            )

    if social:
        for issue in social.get("issues") or []:
            findings.append(
                _finding(
                    nid(),
                    severity="MEDIUM",
                    classification="SOCIAL_CHARGE_INCONSISTENCY",
                    title=str(issue.get("kind")),
                    description="Social charge signal",
                    objective_observation=str(issue),
                    interpretation=str(
                        social.get("default_classification_without_tax_context")
                        or "NEEDS_SPECIALIST_REVIEW"
                    ),
                    source_document=document_id,
                    cells=issue.get("cells") or [],
                    evidence=issue,
                )
            )

    if references:
        for comp in references.get("comparisons") or []:
            if comp.get("comparison_status") == "NOT_COMPARABLE" and comp.get("difference_pct") is not None:
                findings.append(
                    _finding(
                        nid(),
                        severity="INFO",
                        classification="REFERENCE_LIMITATION",
                        title="Reference not comparable",
                        description="Item cannot be fairly compared to official reference",
                        objective_observation=str(comp.get("limitations")),
                        interpretation="Do not treat as overprice",
                        source_document=document_id,
                        evidence=comp,
                        limitations=comp.get("limitations") or [],
                    )
                )

    # severity summary
    from collections import Counter

    sev_counts = Counter(f["severity"] for f in findings)
    return {
        "generated_at": utc_now(),
        "finding_count": len(findings),
        "severity_counts": dict(sev_counts),
        "findings": findings,
    }
