"""Canonical public entity contract — fail-closed validation before promote."""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

_CNPJ8 = re.compile(r"^\d{8}$")
_IBGE = re.compile(r"^\d{7}$")


class CanonicalEntity(BaseModel):
    """Entity row that may enter coverage denominators / registry promote."""

    cnpj_8: str
    razao_social: str = Field(min_length=1)
    is_active: bool = True
    raio_200km: bool = False
    municipio: str | None = None
    codigo_ibge: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    @field_validator("cnpj_8")
    @classmethod
    def cnpj8_digits(cls, v: str) -> str:
        d = re.sub(r"\D", "", v or "")
        if len(d) >= 8:
            d = d[:8]
        if not _CNPJ8.match(d):
            raise ValueError(f"cnpj_8 must be 8 digits, got {v!r}")
        return d

    @field_validator("codigo_ibge")
    @classmethod
    def ibge7(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        d = re.sub(r"\D", "", v)
        if not _IBGE.match(d):
            raise ValueError(f"codigo_ibge must be 7 digits, got {v!r}")
        return d

    @model_validator(mode="after")
    def coords_pair(self) -> CanonicalEntity:
        lat, lng = self.latitude, self.longitude
        if (lat is None) ^ (lng is None):
            raise ValueError("latitude/longitude must both be set or both null")
        if lat is not None and not (-35.0 <= lat <= 6.0):
            raise ValueError(f"latitude out of BR bounds: {lat}")
        if lng is not None and not (-75.0 <= lng <= -30.0):
            raise ValueError(f"longitude out of BR bounds: {lng}")
        return self


class CoverageEvidence(BaseModel):
    """Minimal evidence row required before operational promote."""

    entity_cnpj_8: str
    capability: str
    source: str
    result: str  # success | success_zero | failure | blocked
    run_id: str = Field(min_length=1)
    period_start: str | None = None
    period_end: str | None = None
    raw_uri: str | None = None
    content_hash: str | None = None

    @field_validator("entity_cnpj_8")
    @classmethod
    def cnpj8(cls, v: str) -> str:
        d = re.sub(r"\D", "", v or "")[:8]
        if not _CNPJ8.match(d):
            raise ValueError(f"entity_cnpj_8 invalid: {v!r}")
        return d

    @field_validator("result")
    @classmethod
    def result_enum(cls, v: str) -> str:
        allowed = {"success", "success_zero", "failure", "blocked", "partial"}
        if v not in allowed:
            raise ValueError(f"result must be one of {allowed}, got {v!r}")
        return v

    @model_validator(mode="after")
    def success_zero_needs_run(self) -> CoverageEvidence:
        if self.result == "success_zero" and not self.run_id:
            raise ValueError("success_zero requires run_id for audit")
        if self.result in {"success", "success_zero"} and not (self.content_hash or self.raw_uri):
            raise ValueError(f"{self.result} requires content_hash or raw_uri provenance")
        return self


def validate_entities(rows: list[dict[str, Any]]) -> tuple[list[CanonicalEntity], list[dict[str, Any]]]:
    ok: list[CanonicalEntity] = []
    bad: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        try:
            ok.append(CanonicalEntity.model_validate(row))
        except Exception as exc:  # noqa: BLE001 — collect field-level failures
            bad.append({"index": i, "error": str(exc), "row_keys": list(row.keys())})
    return ok, bad


def validate_coverage_evidence(rows: list[dict[str, Any]]) -> tuple[list[CoverageEvidence], list[dict[str, Any]]]:
    ok: list[CoverageEvidence] = []
    bad: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        try:
            ok.append(CoverageEvidence.model_validate(row))
        except Exception as exc:  # noqa: BLE001
            bad.append({"index": i, "error": str(exc), "row_keys": list(row.keys())})
    return ok, bad
