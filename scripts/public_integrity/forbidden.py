"""Forbidden copy and payload-field scans. Absence of risk is never certified."""

from __future__ import annotations

import re
from typing import Any

from scripts.public_integrity.models import FORBIDDEN_PAYLOAD_FIELDS


def _copy_tokens() -> tuple[str, ...]:
    # Split so this file does not contain the forbidden words as contiguous copy.
    return (
        "lim" + "pa",
        "id" + "onea",
        "id" + "oneo",
        "id" + "\u00f4nea",
        "id" + "\u00f4neo",
        "reg" + "ular",
        "ap" + "ta",
        "sem" + " risco",
        "certid" + "ao",
        "certid" + "\u00e3o",
    )


FORBIDDEN_COPY = re.compile(
    r"\b(" + "|".join(re.escape(token) for token in _copy_tokens()) + r")\b",
    re.IGNORECASE,
)


def scan_forbidden_copy(text: str) -> list[str]:
    return [match.group(0) for match in FORBIDDEN_COPY.finditer(text or "")]


def collect_keys(node: Any, *, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            next_path = f"{path}.{key}" if path else str(key)
            found.append(next_path)
            found.extend(collect_keys(value, path=next_path))
        return found
    if isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(collect_keys(item, path=f"{path}[{index}]"))
    return found


def scan_forbidden_fields(node: Any) -> list[str]:
    hits: list[str] = []
    for path in collect_keys(node):
        leaf = path.rsplit(".", 1)[-1]
        leaf = re.sub(r"\[\d+\]$", "", leaf)
        if leaf in FORBIDDEN_PAYLOAD_FIELDS:
            hits.append(path)
    return hits
