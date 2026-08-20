"""Forbidden tokens, PII and exclusive-area isolation."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from scripts.bofu_evidence.hashutil import canonical_dumps
from scripts.bofu_evidence.producer import build_packs

FORBIDDEN_TOKENS = (
    "has_right",
    "irregular",
    "fraude",
    "should_adjust",
    "seo_title",
    "cta",
    "INDEX",
    "custo/km",
    "nacional completo",
)

PII_PATTERNS = (
    re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)"),
    re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I),
    re.compile(r"(?<!\d)(?:\+55[\s-]?)?(?:\(?[1-9]\d\)?[\s-]?)(?:9\d{4}[\s-]?\d{4}|[2-8]\d{3}[\s-]?\d{4})(?!\d)"),
    re.compile(r"postgres(?:ql)?://\S+", re.I),
    re.compile(r"(?:api[_-]?key|secret|token)\s*[:=]\s*\S+", re.I),
)

PRODUCER_ROOT = Path(__file__).resolve().parents[2] / "scripts" / "bofu_evidence"
FORBIDDEN_IMPORTS = frozenset(
    {
        "scripts.contract_comparables",
        "scripts.national_coverage",
    }
)


def test_emitted_packs_omit_forbidden_tokens_and_pii() -> None:
    bundle = build_packs()
    blob = canonical_dumps(bundle["manifest"]) + "".join(canonical_dumps(pack) for pack in bundle["packs"])
    for token in FORBIDDEN_TOKENS:
        assert token not in blob
    for pattern in PII_PATTERNS:
        assert pattern.search(blob) is None
    for pack in bundle["packs"]:
        assert pack["publication"] is False
        assert pack["index"] is False
        assert pack["national"] is False


def test_producer_does_not_import_forbidden_engines() -> None:
    imported: set[str] = set()
    for path in PRODUCER_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
    assert imported.isdisjoint(FORBIDDEN_IMPORTS)
    for module in imported:
        assert not module.startswith("scripts.contract_comparables")
        assert not module.startswith("scripts.national_coverage")
