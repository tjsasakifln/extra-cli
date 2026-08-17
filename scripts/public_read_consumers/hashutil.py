"""Deterministic canonicalize and content hashing."""

from __future__ import annotations

import hashlib
import json
from typing import Any

FORBIDDEN_PUBLIC_TOKENS = (
    "CONFENGE",
    "confenge",
    "SmartLic",
    "smartlic",
    "extra-cli",
    "scripts.public_read",
    "Extra 1093",
    "extra_1093",
)

PII_FIELD_NAMES = frozenset(
    {
        "email",
        "e_mail",
        "phone",
        "telefone",
        "cpf",
        "raw_cpf",
        "consent",
        "consentimento",
        "whatsapp",
        "password",
        "secret",
        "token",
        "dsn",
    }
)


def canonical_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_dumps(payload).encode("utf-8")).hexdigest()


def attach_hash(document: dict[str, Any]) -> dict[str, Any]:
    body = {key: value for key, value in document.items() if key != "content_hash"}
    return {**body, "content_hash": content_hash(body)}


def scan_forbidden_tokens(document: Any) -> list[str]:
    text = canonical_dumps(document) if not isinstance(document, str) else document
    hits: list[str] = []
    lowered = text.lower()
    for token in FORBIDDEN_PUBLIC_TOKENS:
        if token.lower() in lowered:
            hits.append(token)
    return hits


def assert_public_clean(document: Any) -> None:
    hits = scan_forbidden_tokens(document)
    if hits:
        raise ValueError(f"public_consumer_forbidden_token:{hits[0]}")


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


def find_pii_fields(node: Any, *, path: str = "") -> list[str]:
    hits: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            next_path = f"{path}.{key}" if path else str(key)
            if str(key).lower() in PII_FIELD_NAMES:
                hits.append(next_path)
            hits.extend(find_pii_fields(value, path=next_path))
        return hits
    if isinstance(node, list):
        for index, item in enumerate(node):
            hits.extend(find_pii_fields(item, path=f"{path}[{index}]"))
    return hits
