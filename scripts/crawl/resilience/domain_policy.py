"""Versioned, fail-closed transport policy registry by public-source domain."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

SCHEMA_VERSION = "crawl-domain-policy/v1"
DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[3] / "config" / "crawl-domain-policies.json"


@dataclass(frozen=True)
class ResolvedDomainPolicy:
    name: str
    policy_version: str
    matched_suffix: str | None
    values: dict[str, int | float]
    fingerprint: str


def _number(mapping: dict[str, Any], key: str, *, minimum: float = 0.0) -> int | float:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"domain policy {key!r} must be numeric")
    if float(value) < minimum:
        raise ValueError(f"domain policy {key!r} must be >= {minimum}")
    return value


class DomainPolicyRegistry:
    """Load and resolve the checked-in domain policy without network access."""

    REQUIRED_NUMBERS = {
        "connect_timeout": 0.1,
        "read_timeout": 0.1,
        "max_retries": 0,
        "base_delay": 0,
        "max_delay": 0,
        "jitter": 0,
        "retry_after_fallback": 0,
        "request_delay": 0,
        "circuit_breaker_threshold": 1,
        "circuit_breaker_cooldown": 1,
        "daily_request_budget": 1,
    }

    def __init__(self, payload: dict[str, Any], *, source_path: Path):
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"unsupported crawl domain policy schema: {payload.get('schema_version')!r}")
        version = str(payload.get("policy_version") or "").strip()
        if not version:
            raise ValueError("crawl domain policy requires policy_version")
        default = payload.get("default")
        rules = payload.get("domains")
        if not isinstance(default, dict) or not isinstance(rules, list):
            raise ValueError("crawl domain policy requires default object and domains list")
        self.policy_version = version
        self.source_path = source_path
        self.default = self._validated_values(default)
        self.rules: list[tuple[str, tuple[str, ...], dict[str, int | float]]] = []
        seen_suffixes: set[str] = set()
        for item in rules:
            if not isinstance(item, dict):
                raise ValueError("domain policy entry must be an object")
            name = str(item.get("name") or "").strip()
            suffixes_raw = item.get("suffixes")
            if not name or not isinstance(suffixes_raw, list) or not suffixes_raw:
                raise ValueError("domain policy entry requires name and suffixes")
            suffixes = tuple(str(value).lower().strip(".") for value in suffixes_raw)
            if any(not value or value in seen_suffixes for value in suffixes):
                raise ValueError(f"invalid or duplicate domain suffix in {name!r}")
            seen_suffixes.update(suffixes)
            merged = dict(self.default)
            merged.update({key: item[key] for key in self.REQUIRED_NUMBERS if key in item})
            self.rules.append((name, suffixes, self._validated_values(merged)))

    @classmethod
    def load(cls, path: Path | None = None) -> DomainPolicyRegistry:
        source = (path or DEFAULT_POLICY_PATH).resolve()
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("crawl domain policy root must be an object")
        return cls(payload, source_path=source)

    def _validated_values(self, mapping: dict[str, Any]) -> dict[str, int | float]:
        values = {key: _number(mapping, key, minimum=minimum) for key, minimum in self.REQUIRED_NUMBERS.items()}
        if float(values["max_delay"]) < float(values["base_delay"]):
            raise ValueError("domain policy max_delay must be >= base_delay")
        if float(values["jitter"]) > 1:
            raise ValueError("domain policy jitter must be between 0 and 1")
        return values

    def resolve(self, url_or_host: str | None) -> ResolvedDomainPolicy:
        raw = (url_or_host or "").strip().lower()
        hostname = (urlsplit(raw).hostname if "://" in raw else raw.split(":", 1)[0]) or ""
        name = "default"
        matched: str | None = None
        values = self.default
        best_length = -1
        for candidate_name, suffixes, candidate_values in self.rules:
            for suffix in suffixes:
                if (hostname == suffix or hostname.endswith(f".{suffix}")) and len(suffix) > best_length:
                    name = candidate_name
                    matched = suffix
                    values = candidate_values
                    best_length = len(suffix)
        canonical = json.dumps(
            {"policy_version": self.policy_version, "name": name, "suffix": matched, "values": values},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return ResolvedDomainPolicy(
            name=name,
            policy_version=self.policy_version,
            matched_suffix=matched,
            values=dict(values),
            fingerprint=hashlib.sha256(canonical).hexdigest(),
        )
