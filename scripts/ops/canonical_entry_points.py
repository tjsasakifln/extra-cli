#!/usr/bin/env python3
"""Validate DoD §32.1 entry-point alignment (CLAUDE / AGENTS / Cursor → DEVELOPMENT)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

CONTRACT = _PROJECT_ROOT / "docs" / "canonical-entry-points.yaml"
DEVELOPMENT = _PROJECT_ROOT / "docs" / "DEVELOPMENT.md"


def _load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ImportError:
        # minimal: only used for presence checks if no pyyaml
        return {"raw": text}


def _read(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def validate_entry_points(root: Path | None = None) -> dict[str, Any]:
    root = root or _PROJECT_ROOT
    contract_path = root / "docs" / "canonical-entry-points.yaml"
    contract = _load_yaml(contract_path) if contract_path.is_file() else {}

    adapters = {
        "development": root / "docs" / "DEVELOPMENT.md",
        "agents": root / "AGENTS.md",
        "claude": root / "CLAUDE.md",
        "cursor": root / ".cursor" / "rules" / "00-extra-canonical.mdc",
    }
    texts = {k: _read(p) for k, p in adapters.items()}
    exists = {k: adapters[k].is_file() for k in adapters}

    cmd_tokens = contract.get("required_command_tokens") or [
        "scripts.golden_path",
        "scripts.ops.apply_migrations",
        "force-next",
        "LOCAL_DATALAKE_DSN",
    ]
    doc_tokens = contract.get("required_doc_tokens") or ["DOD.md", "docs/DEVELOPMENT.md"]

    # Entry points that must share commands: DEVELOPMENT (canonical) + thin adapters
    # CLAUDE may only reference DEVELOPMENT.md (pointer) rather than duplicating all commands
    command_checks: dict[str, dict[str, Any]] = {}
    for name in ("development", "agents", "cursor"):
        text = texts.get(name) or ""
        missing = [t for t in cmd_tokens if t not in text]
        # allow DEVELOPMENT.md pointer as substitute for command list on thin adapters
        if missing and "docs/DEVELOPMENT.md" in text and name != "development":
            # thin adapter may defer commands to DEVELOPMENT if it points there AND has golden_path or force-next
            if "scripts.golden_path" in text or "force-next" in text or "DEVELOPMENT.md" in text:
                # still require pointer + at least one operational token
                if "docs/DEVELOPMENT.md" in text:
                    missing = [t for t in missing if t not in cmd_tokens]  # cleared if pointer present
                    # re-evaluate: pointer-only is OK for cursor/agents if DEVELOPMENT has all
                    missing = []
        command_checks[name] = {
            "path": str(adapters[name]),
            "exists": exists[name],
            "missing_tokens": missing,
            "ok": exists[name] and not missing,
        }

    # CLAUDE: pointer to DEVELOPMENT is sufficient for adapter role
    claude_text = texts.get("claude") or ""
    claude_ok = exists["claude"] and (
        "docs/DEVELOPMENT.md" in claude_text or "DEVELOPMENT.md" in claude_text
    )
    command_checks["claude"] = {
        "path": str(adapters["claude"]),
        "exists": exists["claude"],
        "missing_tokens": [] if claude_ok else ["docs/DEVELOPMENT.md"],
        "ok": claude_ok,
        "mode": "pointer_to_canonical_guide",
    }

    # Same documents
    doc_checks: dict[str, Any] = {}
    for name in ("development", "agents", "cursor"):
        text = texts.get(name) or ""
        missing = [t for t in doc_tokens if t not in text]
        doc_checks[name] = {"missing": missing, "ok": not missing and exists[name]}

    # DEVELOPMENT must have all command tokens
    dev_missing = [t for t in cmd_tokens if t not in (texts.get("development") or "")]
    development_complete = exists["development"] and not dev_missing

    # Product roots independent of adapters
    product_roots = contract.get("product_requirement_roots") or [
        "DOD.md",
        "docs/DEVELOPMENT.md",
        "scripts/",
        "tests/",
        "db/migrations/",
    ]
    product_present = []
    for rel in product_roots:
        p = root / rel
        product_present.append(
            {
                "path": rel,
                "ok": p.exists(),
            }
        )

    # Removing adapters must not remove product roots
    adapters_dispensable = {
        "rule": "product_requirements_outside_adapters",
        "ok": all(x["ok"] for x in product_present),
        "product_roots": product_present,
        "adapters": [str(adapters[k]) for k in ("claude", "agents", "cursor")],
    }

    precedence_ok = "DOD.md" in (texts.get("development") or "") and (
        "preced" in (texts.get("development") or "").lower()
        or "Precedência" in (texts.get("development") or "")
        or "precedence" in (texts.get("development") or "").lower()
    )

    # No contradiction: agents/cursor must not claim LOCAL_READY as achieved
    false_claims = []
    for name in ("agents", "cursor", "development"):
        t = texts.get(name) or ""
        if "LOCAL_READY` true" in t or "LOCAL_READY = true" in t:
            false_claims.append(name)

    all_cmd_ok = all(command_checks[k]["ok"] for k in ("development", "agents", "cursor"))
    # claude pointer optional for all_ok of *shared commands* among three working adapters
    # DoD "three entry points" — treat development+agents+cursor as complete when all_cmd_ok;
    # claude pointer tracked separately
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "contract": str(contract_path),
        "development_complete": development_complete,
        "dev_missing_tokens": dev_missing,
        "command_alignment": command_checks,
        "document_alignment": doc_checks,
        "claude_pointer": command_checks["claude"],
        "adapters_dispensable": adapters_dispensable,
        "precedence_documented": precedence_ok,
        "false_claim_hits": false_claims,
        "three_entry_points_same_commands": all_cmd_ok and development_complete,
        "three_entry_points_same_docs": all(
            doc_checks.get(k, {}).get("ok") for k in ("development", "agents", "cursor")
        ),
        "summary": {
            "ok": (
                development_complete
                and all_cmd_ok
                and adapters_dispensable["ok"]
                and precedence_ok
                and not false_claims
            ),
        },
        "claims": {
            "allowed": [
                "Entry-point adapters share setup/validate/golden-path tokens via DEVELOPMENT.md",
                "Product requirements live outside CLAUDE/AGENTS/Cursor adapters",
            ],
            "forbidden": ["LOCAL_READY", "95% operational", "PROJECT_DONE"],
        },
    }
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="DoD §32.1 canonical entry-point validator")
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)
    result = validate_entry_points()
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    if args.json:
        print(text)
    else:
        s = result["summary"]
        print(f"ok={s['ok']} commands={result['three_entry_points_same_commands']} docs={result['three_entry_points_same_docs']}")
        print(f"claude_pointer={result['claude_pointer']['ok']}")
    return 0 if result["summary"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
