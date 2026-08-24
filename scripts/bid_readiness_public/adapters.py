"""Thin adapters over existing engines. No second extraction/audit/match engine."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.bid_readiness_public.hashing import sha256_file, sha256_text
from scripts.bid_readiness_public.models import INTERPRETIVE_LIMIT
from scripts.bid_readiness_public.validators import EnvelopeValidationError, refuse_finding

_CONSORCIO_PERMITIDO = re.compile(
    r"cons[oó]rcio.{0,40}(permitido|admitido|poder[aã]o\s+participar)",
    re.IGNORECASE,
)
_CONSORCIO_VEDADO = re.compile(
    r"cons[oó]rcio.{0,40}(vedado|proibido|n[aã]o\s+(ser[aá]\s+)?admitido|n[aã]o\s+poder[aã]o)",
    re.IGNORECASE,
)


@dataclass
class AdapterBundle:
    module: str
    available: bool
    findings: list[dict[str, Any]] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    covered: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    unevaluated: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


def _locator(**kwargs: Any) -> dict[str, Any]:
    return {
        "page": kwargs.get("page"),
        "section": kwargs.get("section"),
        "cell": kwargs.get("cell"),
        "sheet": kwargs.get("sheet"),
        "paragraph": kwargs.get("paragraph"),
    }


def make_finding(
    *,
    finding_id: str,
    requirement_id: str | None,
    category: str,
    state: str,
    statement: str,
    source_document_id: str,
    locator: dict[str, Any],
    evidence_hash: str,
    evidence_ref: str,
    confidence: float,
    coverage: dict[str, Any],
    reason_codes: list[str],
    contradiction_links: list[str] | None = None,
    method: str | None = None,
    human_review_required: bool = True,
) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "finding_id": finding_id,
        "requirement_id": requirement_id,
        "category": category,
        "state": state,
        "statement": statement,
        "source_document_id": source_document_id,
        "locator": locator,
        "evidence_hash": evidence_hash,
        "evidence_ref": evidence_ref,
        "confidence": confidence,
        "coverage": coverage,
        "reason_codes": list(reason_codes),
        "contradiction_links": list(contradiction_links or []),
        "interpretive_limit": INTERPRETIVE_LIMIT,
        "human_review_required": True if state in {"RISK", "UNKNOWN"} else human_review_required,
    }
    if method:
        finding["method"] = method
        finding["rule"] = method
    try:
        refuse_finding(finding)
    except EnvelopeValidationError as exc:
        message = str(exc)
        if state == "FACT" and ("fact_without_evidence_hash" in message or "fact_without_locator" in message):
            finding["state"] = "UNKNOWN"
            finding["reason_codes"] = [*finding["reason_codes"], "fact_refused"]
            finding["human_review_required"] = True
            if "fact_without_locator" in message:
                finding["reason_codes"].append("locator_missing")
            finding["statement"] = (
                "Observation could not be emitted as FACT because evidence hash or locator is missing. "
                "Coverage remains UNKNOWN pending human review."
            )
        elif state == "RISK" and "risk_without_method" in message:
            finding["state"] = "UNKNOWN"
            finding["reason_codes"] = [*finding["reason_codes"], "risk_refused"]
            finding["human_review_required"] = True
            finding["statement"] = (
                "Technical condition could not be emitted as RISK because method/rule is missing. "
                "Coverage remains UNKNOWN pending human review."
            )
        else:
            raise
        refuse_finding(finding)
    return finding


def _unknown_module(
    module: str,
    *,
    finding_id: str,
    reason: str,
    statement: str,
    category: str = "coverage",
) -> AdapterBundle:
    finding = make_finding(
        finding_id=finding_id,
        requirement_id=None,
        category=category,
        state="UNKNOWN",
        statement=statement,
        source_document_id=f"{module}:unavailable",
        locator={"section": module},
        evidence_hash=sha256_text(f"{module}:{reason}"),
        evidence_ref=f"adapter:{module}",
        confidence=0.0,
        coverage={"evaluated": 0, "denominator": 1, "ratio": 0.0},
        reason_codes=[reason],
    )
    missing = [module]
    return AdapterBundle(
        module=module,
        available=reason != "engine_unavailable",
        findings=[finding],
        reason_codes=[reason],
        missing=missing,
        unevaluated=[module],
        blockers=[reason],
    )


def run_edital_adapter(
    path: Path | None,
    *,
    available: bool = True,
) -> AdapterBundle:
    if not available:
        return _unknown_module(
            "edital_case",
            finding_id="ED-ENG-001",
            reason="engine_unavailable",
            statement="edital_case engine is unavailable. Coverage is UNKNOWN; no fallback was invented.",
        )
    if path is None or not Path(path).is_file():
        return _unknown_module(
            "edital_case",
            finding_id="ED-MISS-001",
            reason="missing_edital",
            statement="No edital path was supplied. Absence is not a negative eligibility finding.",
        )

    from scripts.edital_case.extract import extract_pdf, extract_txt

    target = Path(path)
    document_id = f"edital:{target.name}"
    suffix = target.suffix.lower()
    if suffix == ".pdf":
        extracted = extract_pdf(target, document_id)
    elif suffix in {".txt", ".md"}:
        extracted = extract_txt(target, document_id)
    else:
        extracted = extract_txt(target, document_id)

    status = str(extracted.get("status") or extracted.get("quality_status") or "")
    total_chars = int(extracted.get("total_chars") or 0)
    quality = str(extracted.get("quality_status") or "")
    file_hash = sha256_file(target)
    findings: list[dict[str, Any]] = []
    codes: list[str] = []
    covered: list[str] = []
    missing: list[str] = []
    unevaluated: list[str] = []
    conflicts: list[str] = []
    blockers: list[str] = []

    if status in {"EXTRACTION_FAILED", "UNSUPPORTED"} or quality in {"EXTRACTION_FAILED"}:
        codes.append("unreadable_pdf")
        blockers.append("unreadable_pdf")
        findings.append(
            make_finding(
                finding_id="ED-READ-001",
                requirement_id=None,
                category="edital",
                state="UNKNOWN",
                statement=(
                    "Edital bytes were not readable as text. Coverage is UNKNOWN; this is not a rejection of the bid."
                ),
                source_document_id=document_id,
                locator={"section": "document"},
                evidence_hash=file_hash,
                evidence_ref=f"sha256:{file_hash}",
                confidence=0.0,
                coverage={"evaluated": 0, "denominator": 1, "ratio": 0.0},
                reason_codes=["unreadable_pdf"],
                method="edital_case.extract_pdf",
            )
        )
        return AdapterBundle(
            module="edital_case",
            available=True,
            findings=findings,
            reason_codes=codes,
            unevaluated=["edital"],
            blockers=blockers,
        )

    if total_chars == 0 or quality in {"EMPTY", "OCR_REQUIRED"}:
        codes.append("incomplete_document")
        blockers.append("incomplete_document")
        findings.append(
            make_finding(
                finding_id="ED-INC-001",
                requirement_id=None,
                category="edital",
                state="UNKNOWN",
                statement=(
                    "Edital extraction produced empty or OCR-required text. "
                    "Coverage is UNKNOWN pending a readable source."
                ),
                source_document_id=document_id,
                locator={"section": "document"},
                evidence_hash=file_hash,
                evidence_ref=f"sha256:{file_hash}",
                confidence=0.0,
                coverage={"evaluated": 0, "denominator": 1, "ratio": 0.0},
                reason_codes=["incomplete_document", "unreadable_pdf"],
                method="edital_case.extract",
            )
        )
        return AdapterBundle(
            module="edital_case",
            available=True,
            findings=findings,
            reason_codes=codes,
            unevaluated=["edital"],
            blockers=blockers,
        )

    blocks = list(extracted.get("blocks") or [])
    full_text = " ".join(str(block.get("text") or "") for block in blocks)
    first = blocks[0] if blocks else {}
    locator = _locator(page=first.get("page"), paragraph=first.get("paragraph"), section="objeto")
    excerpt = (first.get("text") or full_text)[:400]
    findings.append(
        make_finding(
            finding_id="ED-FACT-001",
            requirement_id="edital.text",
            category="edital",
            state="FACT",
            statement="Edital text was extracted with an explicit locator. Human review of scope remains required.",
            source_document_id=document_id,
            locator=locator if locator else _locator(section="document"),
            evidence_hash=sha256_text(excerpt),
            evidence_ref=f"sha256:{file_hash}",
            confidence=0.8 if quality == "OK" else 0.4,
            coverage={"evaluated": 1, "denominator": 1, "ratio": 1.0},
            reason_codes=["edital_extracted"],
        )
    )
    covered.append("edital.text")

    if _CONSORCIO_PERMITIDO.search(full_text) and _CONSORCIO_VEDADO.search(full_text):
        codes.append("contradictory_requirement")
        conflicts.append("consorcio")
        findings.append(
            make_finding(
                finding_id="ED-CONTRA-001",
                requirement_id="edital.consorcio",
                category="edital",
                state="UNKNOWN",
                statement=(
                    "Edital text contains both permitting and forbidding language for consortia. "
                    "Contradiction is unresolved; not an eligibility decision."
                ),
                source_document_id=document_id,
                locator=_locator(section="consorcio"),
                evidence_hash=sha256_text(full_text[:2000]),
                evidence_ref=f"sha256:{file_hash}",
                confidence=0.2,
                coverage={"evaluated": 1, "denominator": 1, "ratio": 1.0},
                reason_codes=["contradictory_requirement"],
                contradiction_links=["ED-FACT-001"],
                method="edital_case.extract + consorcio_pattern_pair",
            )
        )

    if total_chars < 200:
        codes.append("incomplete_document")
        missing.append("edital.checklist")
        findings.append(
            make_finding(
                finding_id="ED-INC-002",
                requirement_id="edital.checklist",
                category="edital",
                state="UNKNOWN",
                statement="Extracted edital text is too short to treat checklist coverage as evaluated.",
                source_document_id=document_id,
                locator=_locator(section="document"),
                evidence_hash=file_hash,
                evidence_ref=f"sha256:{file_hash}",
                confidence=0.2,
                coverage={"evaluated": 1, "denominator": 4, "ratio": 0.25},
                reason_codes=["incomplete_document", "insufficient_coverage"],
                method="edital_case.extract.char_count",
            )
        )

    return AdapterBundle(
        module="edital_case",
        available=True,
        findings=findings,
        reason_codes=codes,
        covered=covered,
        missing=missing,
        unevaluated=unevaluated,
        conflicts=conflicts,
        blockers=blockers,
    )


def run_budget_adapter(
    path: Path | None,
    *,
    available: bool = True,
) -> AdapterBundle:
    if not available:
        return _unknown_module(
            "budget_audit",
            finding_id="BD-ENG-001",
            reason="engine_unavailable",
            statement="budget_audit engine is unavailable. Coverage is UNKNOWN; no fallback was invented.",
        )
    if path is None or not Path(path).is_file():
        return _unknown_module(
            "budget_audit",
            finding_id="BD-MISS-001",
            reason="missing_planilha",
            statement="No planilha path was supplied. Absence is not a finding that prices are invalid.",
        )

    from scripts.budget_audit.arithmetic import audit_item_arithmetic, workbook_integrity
    from scripts.budget_audit.classify import classify_workbook
    from scripts.budget_audit.normalize import normalize_case
    from scripts.budget_audit.units import units_compatible
    from scripts.budget_audit.workbook_reader import WorkbookReadError, read_workbook

    target = Path(path)
    document_id = f"planilha:{target.name}"
    file_hash = sha256_file(target)
    try:
        model = read_workbook(target, document_id=document_id)
    except WorkbookReadError:
        return AdapterBundle(
            module="budget_audit",
            available=True,
            findings=[
                make_finding(
                    finding_id="BD-READ-001",
                    requirement_id=None,
                    category="budget",
                    state="UNKNOWN",
                    statement="Planilha could not be read by budget_audit.workbook_reader. Coverage is UNKNOWN.",
                    source_document_id=document_id,
                    locator=_locator(section="workbook"),
                    evidence_hash=file_hash,
                    evidence_ref=f"sha256:{file_hash}",
                    confidence=0.0,
                    coverage={"evaluated": 0, "denominator": 1, "ratio": 0.0},
                    reason_codes=["incomplete_document"],
                    method="budget_audit.workbook_reader.read_workbook",
                )
            ],
            reason_codes=["incomplete_document"],
            unevaluated=["planilha"],
            blockers=["incomplete_document"],
        )

    classifications = classify_workbook(model)
    normalized = normalize_case(document_id, classifications, model["cells"])
    items = list(normalized.get("budget_items") or [])
    integrity = workbook_integrity(
        model.get("formulas") or [],
        model.get("cells") or [],
        items,
        hidden_content=model.get("hidden_content"),
    )
    arithmetic = audit_item_arithmetic(items) if items else {"checks": []}

    findings: list[dict[str, Any]] = []
    codes: list[str] = []
    covered: list[str] = []
    missing: list[str] = []
    conflicts: list[str] = []
    blockers: list[str] = []
    n = 0

    def nid() -> str:
        nonlocal n
        n += 1
        return f"BD-{n:04d}"

    if not items:
        codes.append("insufficient_coverage")
        missing.append("budget.items")
        findings.append(
            make_finding(
                finding_id=nid(),
                requirement_id=None,
                category="budget",
                state="UNKNOWN",
                statement="Workbook was opened but no budget items were classified. Coverage is UNKNOWN.",
                source_document_id=document_id,
                locator=_locator(
                    sheet=(
                        (model.get("sheets") or [{}])[0].get("name")
                        if model.get("sheets") and isinstance((model.get("sheets") or [{}])[0], dict)
                        else "workbook"
                    )
                ),
                evidence_hash=file_hash,
                evidence_ref=f"sha256:{file_hash}",
                confidence=0.2,
                coverage={"evaluated": 0, "denominator": 1, "ratio": 0.0},
                reason_codes=["insufficient_coverage"],
                method="budget_audit.classify_workbook+normalize_case",
            )
        )

    for issue in integrity.get("formula_issues") or []:
        kind = str(issue.get("kind") or "FORMULA")
        cells = issue.get("cells") or []
        cell = cells[0] if cells else None
        findings.append(
            make_finding(
                finding_id=nid(),
                requirement_id=None,
                category="budget",
                state="RISK",
                statement=(
                    f"Formula issue {kind} observed under budget_audit.workbook_integrity. "
                    "Cached value was not treated as zero. Human engineer review required."
                ),
                source_document_id=document_id,
                locator=_locator(sheet=issue.get("sheet"), cell=cell),
                evidence_hash=sha256_text(json.dumps(issue, sort_keys=True, default=str)),
                evidence_ref=f"formula:{issue.get('formula')}",
                confidence=0.7,
                coverage={"evaluated": 1, "denominator": 1, "ratio": 1.0},
                reason_codes=["formula_value_conflict"],
                method="budget_audit.arithmetic.workbook_integrity",
            )
        )
        codes.append("formula_value_conflict")
        conflicts.append(str(cell or kind))

    for check in arithmetic.get("checks") or []:
        if check.get("status") == "MATERIAL_DIFFERENCE":
            cells = check.get("source_cells") or []
            findings.append(
                make_finding(
                    finding_id=nid(),
                    requirement_id=str(check.get("item_id") or "budget.item"),
                    category="budget",
                    state="RISK",
                    statement=(
                        "Reported total diverges from quantity × unit price under "
                        f"{check.get('formula_expected')}. Method-scoped arithmetic only; "
                        "not a bid ineligibility decision."
                    ),
                    source_document_id=document_id,
                    locator=_locator(cell=cells[0] if cells else None),
                    evidence_hash=sha256_text(json.dumps(check, sort_keys=True, default=str)),
                    evidence_ref=str(check.get("check_id") or "arith"),
                    confidence=0.8,
                    coverage={"evaluated": 1, "denominator": 1, "ratio": 1.0},
                    reason_codes=["arithmetic_divergence"],
                    method=str(check.get("formula_expected") or "quantity * unit_price = total"),
                )
            )
            conflicts.append(str(check.get("item_id")))

    by_code: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        code = str(item.get("code") or "")
        if code:
            by_code.setdefault(code, []).append(item)
    for code, group in by_code.items():
        units = {str(item.get("unit") or "") for item in group}
        if len(units) > 1:
            unit_list = list(units)
            if not units_compatible(unit_list[0], unit_list[1]):
                findings.append(
                    make_finding(
                        finding_id=nid(),
                        requirement_id=code,
                        category="budget",
                        state="RISK",
                        statement=(
                            f"Units {unit_list[0]!r} and {unit_list[1]!r} for code {code} are not compatible "
                            "under budget_audit.units.units_compatible. No auto-conversion was applied."
                        ),
                        source_document_id=document_id,
                        locator=_locator(cell=code, sheet="items"),
                        evidence_hash=sha256_text(code + "|".join(sorted(units))),
                        evidence_ref=f"unit:{code}",
                        confidence=0.9,
                        coverage={"evaluated": 1, "denominator": 1, "ratio": 1.0},
                        reason_codes=["incompatible_unit"],
                        method="budget_audit.units.units_compatible",
                    )
                )
                codes.append("incompatible_unit")
                conflicts.append(code)

    if items and not any(f["state"] == "UNKNOWN" for f in findings):
        covered.append("budget.items")
        first_item = items[0]
        sc = first_item.get("source_cells") or {}
        cell = next(iter(sc.values()), "A2")
        findings.append(
            make_finding(
                finding_id=nid(),
                requirement_id="budget.items",
                category="budget",
                state="FACT",
                statement=f"{len(items)} budget item(s) classified from the workbook under budget_audit.normalize_case.",
                source_document_id=document_id,
                locator=_locator(cell=str(cell), sheet=str(first_item.get("sheet") or "Orcamento")),
                evidence_hash=file_hash,
                evidence_ref=f"sha256:{file_hash}",
                confidence=0.7,
                coverage={"evaluated": len(items), "denominator": len(items), "ratio": 1.0},
                reason_codes=["budget_items_classified"],
            )
        )

    return AdapterBundle(
        module="budget_audit",
        available=True,
        findings=findings,
        reason_codes=codes,
        covered=covered,
        missing=missing,
        conflicts=conflicts,
        blockers=blockers,
    )


def run_acervo_adapter(
    store_path: Path | None,
    *,
    available: bool = True,
    service: str = "pavimentacao asfaltica",
    quantity: float | None = 100.0,
    unit: str = "m2",
) -> AdapterBundle:
    if not available:
        return _unknown_module(
            "technical_acervo",
            finding_id="AC-ENG-001",
            reason="engine_unavailable",
            statement="technical_acervo engine is unavailable. Coverage is UNKNOWN; default extra acervo was not loaded.",
        )
    if store_path is None or not Path(store_path).is_file():
        return _unknown_module(
            "technical_acervo",
            finding_id="AC-MISS-001",
            reason="missing_acervo",
            statement=(
                "No explicit acervo path was supplied. The producer does not load "
                "data/extra_technical_acervo.json by default."
            ),
        )

    from scripts.technical_acervo.guards import scan_store_for_pii
    from scripts.technical_acervo.match import match_requirement
    from scripts.technical_acervo.store import DEFAULT_ACERVO_PATH, load_store

    target = Path(store_path).resolve()
    if target == Path(DEFAULT_ACERVO_PATH).resolve():
        return _unknown_module(
            "technical_acervo",
            finding_id="AC-SENS-001",
            reason="sensitive_acervo",
            statement=(
                "Canonical extra acervo path was refused for this public-read producer. "
                "Supply a fictional/redacted store."
            ),
        )

    store = load_store(target)
    pii = scan_store_for_pii(store)
    findings: list[dict[str, Any]] = []
    codes: list[str] = []
    covered: list[str] = []
    missing: list[str] = []
    blockers: list[str] = []
    file_hash = sha256_file(target)

    if pii.get("issues"):
        codes.append("sensitive_acervo")
        blockers.append("sensitive_acervo")
        findings.append(
            make_finding(
                finding_id="AC-PII-001",
                requirement_id=None,
                category="acervo",
                state="RISK",
                statement=(
                    "Acervo store triggered technical_acervo.guards PII scan. "
                    "Public fixture must not include these fields."
                ),
                source_document_id="acervo:store",
                locator=_locator(section="store"),
                evidence_hash=file_hash,
                evidence_ref="technical_acervo.guards.scan_store_for_pii",
                confidence=0.9,
                coverage={"evaluated": 1, "denominator": 1, "ratio": 1.0},
                reason_codes=["sensitive_acervo"],
                method="technical_acervo.guards.scan_store_for_pii",
            )
        )

    result = match_requirement(store, service=service, quantity=quantity, unit=unit, allow_sum=False)
    adherence = str(result.get("adherence_level") or result.get("adherence") or "no_match")
    best: dict[str, Any] | None = None
    if isinstance(result.get("best_individual"), dict):
        best = result["best_individual"]
    elif result.get("candidates"):
        first_candidate = result["candidates"][0]
        if isinstance(first_candidate, dict):
            best = first_candidate
    page = None
    cert = None
    if isinstance(best, dict):
        page = best.get("page") or best.get("source_page")
        cert = best.get("certificate_number") or best.get("document_id")
    if adherence in {"full_individual", "partial_individual", "only_with_sum", "evidence_limited"}:
        covered.append(service)
        state = "FACT" if adherence == "full_individual" and page is not None else "RISK"
        if state == "FACT" and not cert:
            state = "RISK"
        findings.append(
            make_finding(
                finding_id="AC-MATCH-001",
                requirement_id=service,
                category="acervo",
                state=state,
                statement=(
                    f"technical_acervo.match_requirement returned adherence={adherence} "
                    "for the supplied service. This is documentary coverage, not a qualification decision."
                ),
                source_document_id=str(cert or "acervo:item"),
                locator=_locator(page=page, section=service),
                evidence_hash=file_hash,
                evidence_ref=f"adherence:{adherence}",
                confidence=0.6,
                coverage={"evaluated": 1, "denominator": 1, "ratio": 1.0},
                reason_codes=["acervo_match", adherence],
                method="technical_acervo.match.match_requirement",
            )
        )
    else:
        missing.append(service)
        findings.append(
            make_finding(
                finding_id="AC-NONE-001",
                requirement_id=service,
                category="acervo",
                state="UNKNOWN",
                statement=(
                    "No service-relevant acervo item matched the requirement. "
                    "Absence is not a silent negative qualification finding."
                ),
                source_document_id="acervo:store",
                locator=_locator(section=service),
                evidence_hash=file_hash,
                evidence_ref="adherence:no_match",
                confidence=0.4,
                coverage={"evaluated": 1, "denominator": 1, "ratio": 1.0},
                reason_codes=["missing_acervo_match"],
                method="technical_acervo.match.match_requirement",
            )
        )

    return AdapterBundle(
        module="technical_acervo",
        available=True,
        findings=findings,
        reason_codes=codes,
        covered=covered,
        missing=missing,
        blockers=blockers,
    )


def _map_bid_status(status: str) -> tuple[str, list[str]]:
    if status == "SATISFIED":
        return "FACT", ["requirement_supported"]
    if status in {"MISSING", "NOT_APPLICABLE"}:
        return "UNKNOWN", ["missing_document"]
    if status in {"EXPIRED", "EXPIRING", "INCONSISTENT", "PARTIALLY_SATISFIED", "AMBIGUOUS", "NEEDS_HUMAN"}:
        return "RISK", [f"bid_{status.lower()}"]
    if status == "EXTRACTION_FAILED":
        return "UNKNOWN", ["incomplete_document"]
    return "UNKNOWN", ["insufficient_coverage"]


def run_bid_adapter(
    documents: Path | None,
    requirements: Path | None,
    *,
    available: bool = True,
    work_dir: Path,
    entity: dict[str, Any] | None = None,
    reference_date: str = "2026-08-20",
) -> AdapterBundle:
    if not available:
        return _unknown_module(
            "bid_readiness",
            finding_id="BR-ENG-001",
            reason="engine_unavailable",
            statement="bid_readiness engine is unavailable. Coverage is UNKNOWN; no fallback was invented.",
        )
    if documents is None or not Path(documents).exists():
        return _unknown_module(
            "bid_readiness",
            finding_id="BR-MISS-DOC",
            reason="missing_documents",
            statement="No documents path was supplied. Missing files are UNKNOWN, not a silent denial.",
        )
    if requirements is None or not Path(requirements).is_file():
        return _unknown_module(
            "bid_readiness",
            finding_id="BR-MISS-REQ",
            reason="insufficient_coverage",
            statement="No requirements path was supplied. Requirement coverage cannot be evaluated.",
        )

    from scripts.bid_readiness.pipeline import run_pipeline

    case_dir = Path(work_dir) / "bid_case"
    case_dir.mkdir(parents=True, exist_ok=True)
    result = run_pipeline(
        case_id="public-read-bid-readiness",
        requirements_path=Path(requirements),
        documents_source=Path(documents),
        reference_date=reference_date,
        output_dir=case_dir,
        entity=entity,
        operational=False,
        isolation_ok=True,
    )
    match_rows = list(result.get("match_rows") or [])
    if not match_rows:
        matrix_path = case_dir / "matrices" / "requirement-document.json"
        if matrix_path.is_file():
            match_rows = list(json.loads(matrix_path.read_text(encoding="utf-8")).get("rows") or [])

    documents_index = {str(doc.get("document_id")): doc for doc in result.get("documents") or []}
    findings: list[dict[str, Any]] = []
    codes: list[str] = []
    covered: list[str] = []
    missing: list[str] = []
    conflicts: list[str] = []
    blockers: list[str] = []

    for index, row in enumerate(match_rows, start=1):
        rid = str(row.get("requirement_id") or f"REQ-{index:03d}")
        status = str(row.get("status") or "UNKNOWN")
        state, row_codes = _map_bid_status(status)
        doc_ids = [str(item) for item in (row.get("document_ids") or [])]
        first_doc = documents_index.get(doc_ids[0]) if doc_ids else None
        evidence_hash = str((first_doc or {}).get("sha256") or "")
        locators = row.get("source_locators") or []
        locator: dict[str, Any] = {}
        if locators and isinstance(locators[0], dict):
            locator = dict(locators[0])
        if not locator:
            locator = {
                "page": row.get("page"),
                "section": row.get("section") or row.get("category"),
                "cell": row.get("cell"),
                "sheet": row.get("sheet"),
            }
        tech = row.get("technical") or {}
        method = None
        if tech.get("match_class") == "UNIT_MISMATCH":
            state = "RISK"
            row_codes = ["incompatible_unit"]
            method = "bid_readiness.match.UNIT_MISMATCH"
            conflicts.append(rid)
        if state == "FACT" and not evidence_hash:
            state = "UNKNOWN"
            row_codes = [*row_codes, "fact_refused"]
        if state == "UNKNOWN" and status == "MISSING":
            missing.append(rid)
            statement = (
                f"Requirement {rid} has no matching document in the submitted package. "
                "Absence is recorded as UNKNOWN coverage, not as an eligibility denial."
            )
        elif state == "FACT":
            covered.append(rid)
            statement = (
                f"Requirement {rid} is supported by document {doc_ids[0] if doc_ids else 'n/a'} "
                "with an evidence hash. Human review remains required."
            )
        else:
            statement = (
                f"Requirement {rid} is in technical state {status} under bid_readiness.match. "
                "This is not a legal conclusion."
            )
            if status in {"INCONSISTENT", "EXPIRED"}:
                conflicts.append(rid)
                blockers.append(rid)
        findings.append(
            make_finding(
                finding_id=f"BR-{index:04d}",
                requirement_id=rid,
                category=str(row.get("category") or "bid"),
                state=state,
                statement=statement,
                source_document_id=doc_ids[0] if doc_ids else f"requirement:{rid}",
                locator=locator if isinstance(locator, dict) else _locator(section=str(locator)),
                evidence_hash=evidence_hash or sha256_text(f"{rid}:{status}"),
                evidence_ref=f"bid_readiness:{status}",
                confidence=0.7 if state == "FACT" else 0.4,
                coverage={"evaluated": 1, "denominator": 1, "ratio": 1.0},
                reason_codes=row_codes,
                method=method or f"bid_readiness.match:{status}",
            )
        )
        codes.extend(row_codes)

    package_status = str(result.get("package_status") or "")
    if package_status.startswith("BLOCKED_") or package_status == "NOT_READY":
        codes.append("mapped_from_" + package_status.lower())
        blockers.append(package_status)

    return AdapterBundle(
        module="bid_readiness",
        available=True,
        findings=findings,
        reason_codes=sorted(set(codes)),
        covered=covered,
        missing=missing,
        conflicts=conflicts,
        blockers=blockers,
    )
