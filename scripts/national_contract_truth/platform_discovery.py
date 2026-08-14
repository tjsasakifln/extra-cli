"""#267 — quarantine newly discovered platforms until evidence + contract test.

A new domain is never merged into generic transparencia.
Until promotion the only legal terminals are BLOCKED / FAILED /
DISCOVERY_EXHAUSTED_NO_SURFACE — never FOUND or ZERO.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

DiscoveryTerminal = Literal[
    "BLOCKED",
    "FAILED",
    "DISCOVERY_EXHAUSTED_NO_SURFACE",
    "PROMOTED",
]
GENERIC_TRANSPARENCIA = "transparencia"


@dataclass(frozen=True)
class SurfaceEvidence:
    domain: str
    terms_or_robots: str | None
    public_surface: str | None
    technology: str | None
    login_required: bool
    captcha: bool
    contract_test_pass: bool


@dataclass(frozen=True)
class DiscoveryDecision:
    source_id: str
    terminal: DiscoveryTerminal
    reason: str
    merged_into: str | None


def quarantine_source_id(url_or_domain: str) -> str:
    host = url_or_domain.strip().casefold()
    if "://" in host:
        host = urlparse(host).netloc or host
    host = host.split("/")[0].removeprefix("www.")
    if not host:
        raise ValueError("empty_domain")
    return f"unknown:{host}"


def classify_discovery(evidence: SurfaceEvidence) -> DiscoveryDecision:
    source_id = quarantine_source_id(evidence.domain)
    if source_id == f"unknown:{GENERIC_TRANSPARENCIA}" or evidence.domain.casefold() == GENERIC_TRANSPARENCIA:
        return DiscoveryDecision(
            source_id=source_id,
            terminal="BLOCKED",
            reason="refuse_generic_transparencia_merge",
            merged_into=None,
        )
    if evidence.login_required or evidence.captcha:
        return DiscoveryDecision(
            source_id=source_id,
            terminal="BLOCKED",
            reason="login_or_captcha",
            merged_into=None,
        )
    if not evidence.public_surface:
        return DiscoveryDecision(
            source_id=source_id,
            terminal="DISCOVERY_EXHAUSTED_NO_SURFACE",
            reason="no_public_surface",
            merged_into=None,
        )
    if not evidence.terms_or_robots or not evidence.technology:
        return DiscoveryDecision(
            source_id=source_id,
            terminal="FAILED",
            reason="incomplete_surface_inventory",
            merged_into=None,
        )
    if evidence.contract_test_pass:
        return DiscoveryDecision(
            source_id=source_id.removeprefix("unknown:"),
            terminal="PROMOTED",
            reason="evidence_and_contract_test",
            merged_into=None,
        )
    return DiscoveryDecision(
        source_id=source_id,
        terminal="BLOCKED",
        reason="awaiting_contract_test",
        merged_into=None,
    )


def refuse_found_or_zero(decision: DiscoveryDecision) -> bool:
    """Promotion is the only path that leaves quarantine. FOUND/ZERO are illegal."""
    return decision.terminal in {"BLOCKED", "FAILED", "DISCOVERY_EXHAUSTED_NO_SURFACE", "PROMOTED"}
