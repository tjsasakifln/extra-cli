"""Adapter protocol — returns provenance-bearing raw observations only."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from scripts.confenge_contact_resolution.models import RawObservation


@dataclass
class AdapterContext:
    """Runtime context shared by adapters (no secrets required for default path)."""

    cnpj14: str
    fixtures_dir: Path | None = None
    # Optional injected registry record (tests / offline)
    registry_record: dict[str, Any] | None = None
    # Optional injected public docs / pages as dicts
    public_docs: list[dict[str, Any]] = field(default_factory=list)
    site_pages: list[dict[str, Any]] = field(default_factory=list)
    contact_pages: list[dict[str, Any]] = field(default_factory=list)
    human_outcomes: list[dict[str, Any]] = field(default_factory=list)
    allow_network: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


class ContactAdapter(Protocol):
    name: str

    def collect(self, ctx: AdapterContext) -> list[RawObservation]:
        """Return zero or more observations; never invent people."""
        ...
