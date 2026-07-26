"""Load and hash commercial profile + signal catalog."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from scripts.commercial_leads import FORBIDDEN_LANGUAGE


@dataclass
class CommercialProfile:
    path: Path
    data: dict[str, Any]
    catalog_path: Path | None = None
    catalog: dict[str, Any] = field(default_factory=dict)
    profile_hash: str = ""
    catalog_hash: str = ""

    @property
    def profile_id(self) -> str:
        return str(self.data.get("profile_id", "unknown"))

    @property
    def version(self) -> str:
        return str(self.data.get("version", "0"))

    @property
    def queue_limit(self) -> int:
        return int(self.data.get("queue", {}).get("limit", 20))

    @property
    def weights(self) -> dict[str, float]:
        return {k: float(v) for k, v in (self.data.get("weights") or {}).items()}

    @property
    def thresholds(self) -> dict[str, Any]:
        return dict(self.data.get("thresholds") or {})

    @property
    def signal_ids(self) -> list[str]:
        sigs = self.catalog.get("signals") or []
        return [str(s["id"]) for s in sigs if isinstance(s, dict) and "id" in s]

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "version": self.version,
            "profile_hash": self.profile_hash,
            "catalog_hash": self.catalog_hash,
            "version_date": self.data.get("version_date"),
            "services": self.data.get("services"),
            "segments": [
                {"id": s.get("id"), "label": s.get("label")}
                for s in (self.data.get("segments") or [])
                if isinstance(s, dict)
            ],
            "region": self.data.get("region"),
            "ticket": self.data.get("ticket"),
            "capacity": self.data.get("capacity"),
            "queue": self.data.get("queue"),
            "weights": self.weights,
            "thresholds": self.thresholds,
            "signal_count": len(self.signal_ids),
            "signal_ids": self.signal_ids,
            "non_claims": self.data.get("non_claims") or [],
        }


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be mapping: {path}")
    return data


def load_profile(profile_path: str | Path, catalog_path: str | Path | None = None) -> CommercialProfile:
    p = Path(profile_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"profile not found: {p}")
    raw = p.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ValueError("profile YAML root must be mapping")

    cat_path: Path | None = None
    catalog: dict[str, Any] = {}
    cat_hash = ""
    if catalog_path is not None:
        cat_path = Path(catalog_path).resolve()
    else:
        sibling = p.parent / "signal_catalog.yaml"
        if sibling.is_file():
            cat_path = sibling
    if cat_path is not None:
        cat_raw = cat_path.read_text(encoding="utf-8")
        catalog = yaml.safe_load(cat_raw) or {}
        cat_hash = _sha256_text(cat_raw)

    prof = CommercialProfile(
        path=p,
        data=data,
        catalog_path=cat_path,
        catalog=catalog if isinstance(catalog, dict) else {},
        profile_hash=_sha256_text(raw),
        catalog_hash=cat_hash,
    )
    validate_language(prof)
    if len(prof.signal_ids) < 12:
        raise ValueError(f"signal catalog must have >=12 signals, got {len(prof.signal_ids)}")
    return prof


def _content_for_language_scan(data: dict) -> dict:
    """Drop meta keys that intentionally list forbidden phrases as policy."""
    skip = {"language", "forbidden_phrases", "non_claims", "claims"}
    out = {}
    for k, v in data.items():
        if k in skip:
            continue
        out[k] = v
    return out


def validate_language(profile: CommercialProfile) -> None:
    blob = json.dumps(_content_for_language_scan(profile.data), ensure_ascii=False).lower()
    for phrase in FORBIDDEN_LANGUAGE:
        if phrase in blob:
            raise ValueError(f"forbidden commercial language in profile: {phrase}")
    # catalog may document non-claims in limitations; scan hyp/name fields only
    for s in (profile.catalog.get("signals") or []):
        if not isinstance(s, dict):
            continue
        piece = json.dumps(
            {k: s.get(k) for k in ("id", "name", "hypothesis", "offer", "formula")},
            ensure_ascii=False,
        ).lower()
        for phrase in FORBIDDEN_LANGUAGE:
            if phrase in piece:
                raise ValueError(f"forbidden commercial language in catalog signal {s.get('id')}: {phrase}")
