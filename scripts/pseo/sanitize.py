"""Strip forbidden keys and enforce allowlists on public payloads."""

from __future__ import annotations

import re
from typing import Any

from scripts.pseo.allowlist import FORBIDDEN_KEYS

_SNAKE = re.compile(r"(?<!^)(?=[A-Z])")


def normalize_key(key: str) -> str:
    k = _SNAKE.sub("_", str(key)).lower().replace("-", "_")
    return k


def contains_forbidden(obj: Any, path: str = "$") -> list[str]:
    """Return list of paths where forbidden keys appear."""
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            nk = normalize_key(k)
            if nk in FORBIDDEN_KEYS or any(f in nk for f in ("score_total", "top20", "top_20", "human_notes", "commercial_state")):
                # allow benign keys like "source" — only exact/substring for critical
                if nk in FORBIDDEN_KEYS or nk.startswith("score_") or "top20" in nk or "top_20" in nk:
                    hits.append(f"{path}.{k}")
            hits.extend(contains_forbidden(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            hits.extend(contains_forbidden(item, f"{path}[{i}]"))
    return hits


def deep_strip_forbidden(obj: Any) -> Any:
    """Recursively drop forbidden keys from dicts."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            nk = normalize_key(k)
            if nk in FORBIDDEN_KEYS:
                continue
            if nk.startswith("score_") and nk not in {"score_version"}:
                continue
            if "top20" in nk or "top_20" in nk or "top10" in nk:
                continue
            out[k] = deep_strip_forbidden(v)
        return out
    if isinstance(obj, list):
        return [deep_strip_forbidden(x) for x in obj]
    return obj


def assert_public(obj: Any, context: str = "payload") -> None:
    hits = contains_forbidden(obj)
    if hits:
        raise ValueError(f"Forbidden fields in {context}: {hits[:20]}")
