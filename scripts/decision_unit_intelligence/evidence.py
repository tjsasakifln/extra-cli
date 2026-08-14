"""Field-level evidence helpers. Evidence is immutable once built."""

from __future__ import annotations

from scripts.decision_unit_intelligence.models import (
    EpistemicClass,
    FieldAspect,
    FieldEvidence,
    now_iso,
    stable_id,
)


def make_evidence(
    *,
    field: str,
    value: str | None,
    epistemic_class: EpistemicClass,
    source_type: str,
    source_url: str | None = None,
    source_id: str | None = None,
    document_id: str | None = None,
    document_sha256: str | None = None,
    page: int | None = None,
    section: str | None = None,
    evidence_snippet: str | None = None,
    observed_at: str | None = None,
    published_at: str | None = None,
    extraction_method: str | None = None,
    contract_id: str | None = None,
    process_id: str | None = None,
    aspects: list[FieldAspect] | None = None,
    extra: dict | None = None,
) -> FieldEvidence:
    eid = stable_id(
        field,
        value or "",
        epistemic_class.value,
        source_type,
        source_url or "",
        document_id or "",
        str(page or ""),
        evidence_snippet or "",
    )
    if epistemic_class == EpistemicClass.OBSERVED and not (source_type and (source_url or document_id or source_id)):
        raise ValueError("OBSERVED evidence requires a source (url, document or source_id)")
    return FieldEvidence(
        evidence_id=eid,
        field=field,
        value=value,
        epistemic_class=epistemic_class,
        source_type=source_type,
        source_url=source_url,
        source_id=source_id,
        document_id=document_id,
        document_sha256=document_sha256,
        page=page,
        section=section,
        evidence_snippet=evidence_snippet,
        observed_at=observed_at or now_iso(),
        published_at=published_at,
        extraction_method=extraction_method,
        extractor_version="dui.extract.v1",
        contract_id=contract_id,
        process_id=process_id,
        aspects=aspects or [],
        extra=extra or {},
    )


def assert_not_promoted_to_observed(evidence: FieldEvidence) -> None:
    """Guardrail: inferred/technical signals must not be labeled OBSERVED."""
    if evidence.epistemic_class == EpistemicClass.OBSERVED:
        method = (evidence.extraction_method or "").lower()
        if any(tok in method for tok in ("infer", "pattern", "guess", "mx-only", "constructed")):
            raise ValueError(
                f"refusing OBSERVED label for inferred method {evidence.extraction_method!r}"
            )
    for aspect in evidence.aspects:
        if (
            aspect.epistemic_class == EpistemicClass.OBSERVED
            and aspect.method
            and any(tok in aspect.method.lower() for tok in ("infer", "pattern", "guess"))
        ):
            raise ValueError(f"aspect {aspect.field} cannot be OBSERVED via {aspect.method}")
