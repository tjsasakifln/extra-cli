"""Output profiles for consulting deliverables."""

from __future__ import annotations

from enum import StrEnum


class OutputProfile(StrEnum):
    INTERNAL_ANALYSIS = "INTERNAL_ANALYSIS"
    CLIENT_READY = "CLIENT_READY"
    AUDIT_EVIDENCE = "AUDIT_EVIDENCE"


# capability_id or workflow_id → supported profiles
PROFILE_MATRIX: dict[str, tuple[str, ...]] = {
    "workflow.extra.opportunities": (
        OutputProfile.INTERNAL_ANALYSIS.value,
        OutputProfile.CLIENT_READY.value,
        OutputProfile.AUDIT_EVIDENCE.value,
    ),
    "workflow.confenge.suppliers": (
        OutputProfile.INTERNAL_ANALYSIS.value,
        OutputProfile.CLIENT_READY.value,
        OutputProfile.AUDIT_EVIDENCE.value,
    ),
    "workflow.confenge.public_agencies": (
        OutputProfile.INTERNAL_ANALYSIS.value,
        OutputProfile.CLIENT_READY.value,
        OutputProfile.AUDIT_EVIDENCE.value,
    ),
    "workflow.process_documents": (
        OutputProfile.INTERNAL_ANALYSIS.value,
        OutputProfile.AUDIT_EVIDENCE.value,
    ),
    "ops.health": (OutputProfile.INTERNAL_ANALYSIS.value,),
}


def profile_supports(capability_or_workflow: str, profile: str | OutputProfile) -> bool:
    p = profile.value if isinstance(profile, OutputProfile) else str(profile)
    supported = PROFILE_MATRIX.get(capability_or_workflow)
    if not supported:
        # default: internal only for unknown
        return p == OutputProfile.INTERNAL_ANALYSIS.value
    return p in supported
