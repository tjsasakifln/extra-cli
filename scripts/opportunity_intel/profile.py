"""Validated configurable client profile for the QW-01 radar."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


@dataclass(frozen=True)
class ObjectType:
    id: str
    label: str
    terms: tuple[str, ...]


@dataclass(frozen=True)
class ClientProfile:
    profile_id: str
    display_name: str
    version: int
    desired_object_types: tuple[ObjectType, ...]
    positive_terms: tuple[str, ...]
    negative_terms: tuple[str, ...]
    allowed_modalities: tuple[str, ...] | None
    priority_municipalities: tuple[str, ...]
    priority_distance_km: float | None
    minimum_value: float | None
    maximum_value: float | None
    minimum_days_to_deadline: int | None
    documents: dict[str, bool]
    engineering_categories: tuple[str, ...]
    hard_blocks: dict[str, bool]
    weights: dict[str, dict[str, int]]
    triage_thresholds: dict[str, int]


def load_client_profile(path: str | Path) -> ClientProfile:
    """Load YAML with explicit null handling and conservative validation."""
    profile_path = Path(path)
    if not profile_path.is_file():
        raise FileNotFoundError(f"Client profile not found: {profile_path}")
    raw = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Client profile must be a YAML mapping")

    object_types = tuple(
        ObjectType(
            id=_required_text(item, "id"),
            label=_required_text(item, "label"),
            terms=tuple(str(term) for term in item.get("terms", [])),
        )
        for item in _mapping_list(raw.get("desired_object_types"), "desired_object_types")
    )
    allowed = raw.get("allowed_modalities")
    if allowed is not None and not isinstance(allowed, list):
        raise ValueError("allowed_modalities must be null or a list")

    minimum_value = _optional_float(raw.get("minimum_value"), "minimum_value")
    maximum_value = _optional_float(raw.get("maximum_value"), "maximum_value")
    if minimum_value is not None and maximum_value is not None and minimum_value > maximum_value:
        raise ValueError("minimum_value cannot be greater than maximum_value")

    minimum_days = raw.get("minimum_days_to_deadline")
    if minimum_days is not None:
        minimum_days = int(minimum_days)
        if minimum_days < 0:
            raise ValueError("minimum_days_to_deadline cannot be negative")

    weights = raw.get("weights") or {}
    if not isinstance(weights, dict):
        raise ValueError("weights must be a mapping")
    normalized_weights: dict[str, dict[str, int]] = {}
    for dimension in ("data_confidence", "client_fit"):
        values = weights.get(dimension) or {}
        if not isinstance(values, dict):
            raise ValueError(f"weights.{dimension} must be a mapping")
        normalized_weights[dimension] = {str(key): int(value) for key, value in values.items()}

    return ClientProfile(
        profile_id=_required_text(raw, "profile_id"),
        display_name=_required_text(raw, "display_name"),
        version=int(raw.get("version", 1)),
        desired_object_types=object_types,
        positive_terms=tuple(str(term) for term in raw.get("positive_terms", [])),
        negative_terms=tuple(str(term) for term in raw.get("negative_terms", [])),
        allowed_modalities=tuple(str(value) for value in allowed) if allowed is not None else None,
        priority_municipalities=tuple(str(value) for value in raw.get("priority_municipalities", [])),
        priority_distance_km=_optional_float(raw.get("priority_distance_km"), "priority_distance_km"),
        minimum_value=minimum_value,
        maximum_value=maximum_value,
        minimum_days_to_deadline=minimum_days,
        documents=_bool_mapping(raw.get("documents"), "documents"),
        engineering_categories=tuple(str(value) for value in raw.get("engineering_categories", [])),
        hard_blocks=_bool_mapping(raw.get("hard_blocks"), "hard_blocks"),
        weights=normalized_weights,
        triage_thresholds={str(key): int(value) for key, value in (raw.get("triage_thresholds") or {}).items()},
    )


def _required_text(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing required profile field: {key}")
    return value.strip()


def _mapping_list(value: Any, key: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    if not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{key} items must be mappings")
    return value


def _optional_float(value: Any, key: str) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be numeric or null") from exc


def _bool_mapping(value: Any, key: str) -> dict[str, bool]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a mapping")
    return {str(name): bool(enabled) for name, enabled in value.items()}
