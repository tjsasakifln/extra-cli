"""Provider protocol. Isolated failures never invent people or channels."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from scripts.decision_unit_intelligence.models import (
    ChannelObservation,
    CostObservation,
    PersonObservation,
    SearchAttempt,
)


@dataclass
class InvestigationContext:
    cnpj: str
    legal_name: str | None = None
    service: str = "generic"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderResult:
    people: list[PersonObservation] = field(default_factory=list)
    channels: list[ChannelObservation] = field(default_factory=list)
    attempts: list[SearchAttempt] = field(default_factory=list)
    cursor: dict[str, Any] = field(default_factory=dict)
    terminal: str = "ok"
    cost: CostObservation = field(default_factory=CostObservation)
    why_now: str | None = None
    company_site: str | None = None
    legal_name: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class EvidenceProvider(Protocol):
    provider_id: str
    tier: int

    def collect(self, context: InvestigationContext) -> ProviderResult: ...
