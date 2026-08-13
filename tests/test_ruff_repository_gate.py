"""Regression tests for the repository-wide Ruff gate and security remediations."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ci_and_make_lint_are_repository_wide() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    lint_job = ci[ci.index("  lint:\n") : ci.index("  type-check:\n")]
    assert "run: ruff check ." in lint_job
    assert "ruff check scripts/" not in lint_job

    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    lint_target = makefile[makefile.index("lint:\n") : makefile.index("lint-fix:\n")]
    assert "ruff check ." in lint_target


def test_monitor_url_rejects_non_http_and_missing_hostname() -> None:
    module = _load_module(
        "aiox_send_event", ROOT / ".aiox-core/monitor/hooks/lib/send_event.py"
    )
    assert module.validated_server_url("https://monitor.example/path/") == (
        "https://monitor.example/path"
    )
    for unsafe in (
        "file:///etc/passwd",
        "data:text/plain,x",
        "http:///events",
        "//host/path",
        "https://monitor.example/path?redirect=file:///etc/passwd",
        "https://monitor.example/path#fragment",
    ):
        assert module.validated_server_url(unsafe) is None


def test_xml_parser_does_not_resolve_external_entities(tmp_path: Path) -> None:
    helper = _load_module(
        "mcp_safe_xml", ROOT / ".claude/skills/mcp-builder/scripts/safe_xml.py"
    )
    secret = tmp_path / "secret.txt"
    secret.write_text("must-not-be-expanded", encoding="utf-8")
    payload = tmp_path / "hostile.xml"
    payload.write_text(
        f'<!DOCTYPE root [<!ENTITY xxe SYSTEM "{secret.as_uri()}">]>'
        "<root><question>&xxe;</question></root>",
        encoding="utf-8",
    )
    tree = helper.parse_xml_safely(payload)
    serialized = etree.tostring(tree, encoding="unicode")
    assert "must-not-be-expanded" not in serialized


def test_seed_executes_no_f_string_sql() -> None:
    source = (ROOT / "db/seed/seed_sc_entities.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        if isinstance(call.func, ast.Attribute) and call.func.attr == "execute" and call.args:
            assert not isinstance(call.args[0], ast.JoinedStr)
    assert "sql.Identifier(TABLE_NAME)" in source
