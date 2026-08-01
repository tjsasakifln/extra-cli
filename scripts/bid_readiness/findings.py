"""Findings and objective blockers derivation."""

from __future__ import annotations

from typing import Any

from scripts.bid_readiness.models import FindingClass, FindingSeverity


def build_findings(
    *,
    match_rows: list[dict[str, Any]],
    validity_by_doc: dict[str, dict[str, Any]],
    identity_by_doc: dict[str, dict[str, Any]],
    documents: list[dict[str, Any]],
    requirements: list[dict[str, Any]],
    package_issues: list[dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    fid = 0

    def add(
        severity: FindingSeverity,
        classification: FindingClass,
        title: str,
        observation: str,
        *,
        requirement_id: str | None = None,
        document_ids: list[str] | None = None,
        impact: str = "",
        action: str = "",
    ) -> None:
        nonlocal fid
        fid += 1
        findings.append(
            {
                "finding_id": f"F-{fid:04d}",
                "severity": severity.value,
                "classification": classification.value,
                "requirement_id": requirement_id,
                "title": title,
                "objective_observation": observation,
                "interpretation": "Operational observation — not a legal opinion.",
                "document_ids": document_ids or [],
                "source_locators": [],
                "validation_rule": classification.value,
                "deadline": None,
                "impact": impact,
                "recommended_action": action,
                "limitations": ["Human review required before protocol."],
                "review_status": "OPEN",
            }
        )

    for row in match_rows:
        st = row.get("status")
        rid = row.get("requirement_id")
        if st == "MISSING" and row.get("mandatory"):
            add(
                FindingSeverity.CRITICAL,
                FindingClass.MISSING_DOCUMENT,
                f"Missing mandatory document for {rid}",
                row.get("evidence") or "no document",
                requirement_id=rid,
                impact="Risk of inabilitação",
                action="Obtain and ingest required document",
            )
        elif st == "EXPIRED":
            add(
                FindingSeverity.CRITICAL,
                FindingClass.EXPIRED_DOCUMENT,
                f"Expired document for {rid}",
                row.get("evidence") or "expired",
                requirement_id=rid,
                document_ids=row.get("document_ids"),
                impact="Risk of inabilitação",
                action="Renew document",
            )
        elif st == "EXPIRING":
            add(
                FindingSeverity.HIGH,
                FindingClass.EXPIRING_DOCUMENT,
                f"Expiring document for {rid}",
                row.get("evidence") or "expiring",
                requirement_id=rid,
                document_ids=row.get("document_ids"),
                impact="May expire before session",
                action="Plan renewal",
            )
        elif st == "INCONSISTENT":
            add(
                FindingSeverity.CRITICAL,
                FindingClass.IDENTITY_MISMATCH,
                f"Inconsistency for {rid}",
                row.get("evidence") or "inconsistent",
                requirement_id=rid,
                document_ids=row.get("document_ids"),
                impact="Risk of inabilitação",
                action="Replace document or correct cadastro",
            )
        elif st == "NEEDS_HUMAN":
            add(
                FindingSeverity.HIGH,
                FindingClass.NEEDS_HUMAN,
                f"Human review required for {rid}",
                row.get("evidence") or "needs human",
                requirement_id=rid,
                document_ids=row.get("document_ids"),
                impact="Protocol remains blocked for human decision",
                action="Engineer/legal review",
            )
        elif st == "PARTIALLY_SATISFIED":
            tech = row.get("technical") or {}
            if tech.get("match_class") == "QUANTITY_INSUFFICIENT":
                add(
                    FindingSeverity.CRITICAL,
                    FindingClass.QUANTITY_GAP,
                    f"Insufficient quantity for {rid}",
                    tech.get("reason") or "quantity gap",
                    requirement_id=rid,
                    document_ids=row.get("document_ids"),
                    impact="Technical disqualification risk",
                    action="Add complementary evidence",
                )
            else:
                add(
                    FindingSeverity.HIGH,
                    FindingClass.AMBIGUOUS_EVIDENCE,
                    f"Partial evidence for {rid}",
                    row.get("evidence") or "partial",
                    requirement_id=rid,
                    document_ids=row.get("document_ids"),
                    impact="May be insufficient",
                    action="Complete evidence",
                )

        tech = row.get("technical") or {}
        if tech.get("match_class") == "UNIT_MISMATCH":
            add(
                FindingSeverity.HIGH,
                FindingClass.UNIT_MISMATCH,
                f"Unit mismatch for {rid}",
                tech.get("reason") or "units incompatible",
                requirement_id=rid,
                document_ids=row.get("document_ids"),
                impact="Cannot sum quantities",
                action="Provide compatible unit evidence",
            )
        if tech.get("match_class") == "TEXTUAL_CANDIDATE":
            add(
                FindingSeverity.HIGH,
                FindingClass.TECHNICAL_GAP,
                f"Textual candidate only for {rid}",
                "Semantic similarity is not technical proof",
                requirement_id=rid,
                document_ids=row.get("document_ids"),
                impact="Must not be treated as SATISFIED",
                action="Engineer equivalence review",
            )

    for did, ident in identity_by_doc.items():
        if "CNPJ_MISMATCH" in (ident.get("findings") or []):
            add(
                FindingSeverity.CRITICAL,
                FindingClass.IDENTITY_MISMATCH,
                f"CNPJ mismatch on {did}",
                f"document CNPJ {ident.get('document_cnpj')} != expected {ident.get('expected_cnpj')}",
                document_ids=[did],
                impact="Wrong entity document",
                action="Remove foreign CNPJ document",
            )
        if "REPRESENTATION_POWER_UNPROVEN" in (ident.get("findings") or []):
            add(
                FindingSeverity.CRITICAL,
                FindingClass.SIGNATORY_PROBLEM,
                f"Representation power unproven on {did}",
                "powers missing or insufficient for bid acts",
                document_ids=[did],
                impact="Signature may be invalid for protocol",
                action="Obtain procura with sufficient powers",
            )
        if "SIGNATORY_NOT_FOUND" in (ident.get("findings") or []):
            add(
                FindingSeverity.HIGH,
                FindingClass.SIGNATORY_PROBLEM,
                f"Signatory problem on {did}",
                ident.get("signatory_status") or "signatory",
                document_ids=[did],
                impact="Representation unclear",
                action="Align signatory evidence",
            )

    for did, val in validity_by_doc.items():
        if val.get("status") == "EXPIRED":
            # may already be covered via match; still record doc-level
            if not any(f.get("document_ids") == [did] and f["classification"] == "EXPIRED_DOCUMENT" for f in findings):
                add(
                    FindingSeverity.CRITICAL,
                    FindingClass.EXPIRED_DOCUMENT,
                    f"Document expired: {did}",
                    val.get("reason") or "expired",
                    document_ids=[did],
                    impact="Cannot use as valid evidence",
                    action="Renew",
                )

    # duplicate hashes
    by_hash: dict[str, list[str]] = {}
    for d in documents:
        by_hash.setdefault(d.get("sha256") or "", []).append(d["document_id"])
    for h, ids in by_hash.items():
        if h and len(ids) > 1:
            add(
                FindingSeverity.MEDIUM,
                FindingClass.DUPLICATE_DOCUMENT,
                "Duplicate document content",
                f"same sha256 for {ids}",
                document_ids=ids,
                impact="Risk of double counting",
                action="Deduplicate",
            )

    for issue in package_issues or []:
        add(
            FindingSeverity.HIGH,
            FindingClass.FORMAT_PROBLEM,
            issue.get("title") or "Package issue",
            issue.get("observation") or "",
            impact=issue.get("impact") or "Package incomplete",
            action=issue.get("action") or "Fix package",
        )

    blockers = [
        f
        for f in findings
        if f["severity"] in {"CRITICAL", "HIGH"}
        and f["classification"]
        in {
            "MISSING_DOCUMENT",
            "EXPIRED_DOCUMENT",
            "IDENTITY_MISMATCH",
            "SIGNATORY_PROBLEM",
            "QUANTITY_GAP",
            "GUARANTEE_GAP",
            "PROPOSAL_DIVERGENCE",
            "FORMAT_PROBLEM",
            "TECHNICAL_GAP",
        }
    ]

    # Always keep mandatory missing in denominator via match rows; blockers mirror them
    return {
        "all": findings,
        "blockers": blockers,
        "missing": [f for f in findings if f["classification"] == "MISSING_DOCUMENT"],
        "expired": [f for f in findings if f["classification"] == "EXPIRED_DOCUMENT"],
        "expiring": [f for f in findings if f["classification"] == "EXPIRING_DOCUMENT"],
        "inconsistent": [f for f in findings if f["classification"] == "IDENTITY_MISMATCH"],
        "ambiguous": [f for f in findings if f["classification"] == "AMBIGUOUS_EVIDENCE"],
        "human-review": [f for f in findings if f["classification"] == "NEEDS_HUMAN"],
    }


def derive_package_status(
    findings_bundle: dict[str, list[dict[str, Any]]],
    match_rows: list[dict[str, Any]],
) -> str:
    blockers = findings_bundle.get("blockers") or []
    classes = {b["classification"] for b in blockers}
    if "MISSING_DOCUMENT" in classes:
        return "BLOCKED_BY_MISSING_DOCUMENT"
    if "EXPIRED_DOCUMENT" in classes:
        return "BLOCKED_BY_EXPIRED_DOCUMENT"
    if "IDENTITY_MISMATCH" in classes or "SIGNATORY_PROBLEM" in classes:
        return "BLOCKED_BY_INCONSISTENCY"
    if "QUANTITY_GAP" in classes or "TECHNICAL_GAP" in classes or "UNIT_MISMATCH" in classes:
        return "BLOCKED_BY_TECHNICAL_QUALIFICATION"
    if any(r.get("status") == "NEEDS_HUMAN" for r in match_rows):
        return "BLOCKED_BY_HUMAN_DECISION"
    if blockers:
        return "NOT_READY"
    return "READY_FOR_HUMAN_REVIEW"


def derive_system_status(
    *,
    isolation_ok: bool,
    pipeline_ok: bool,
    package_status: str,
    operational_blocked: bool,
) -> str:
    if not isolation_ok or not pipeline_ok:
        return "SYSTEM_FAIL"
    if operational_blocked:
        return "SYSTEM_BLOCKED"
    if package_status.startswith("BLOCKED_") or package_status == "NOT_READY":
        return "SYSTEM_BLOCKED"
    return "SYSTEM_PASS"
