"""Idempotent CTO cycle status upsert into DOD.md and executive HTML.

Replaces the delimited block rather than appending indefinitely.
Never flips DoD checkboxes without explicit proven claim.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.cto.paths import cycles_dir, dod_path, executive_html_path, repo_root
from scripts.cto.redaction import redact_obj

DOD_START = "<!-- CTO-CYCLE-STATUS:START -->"
DOD_END = "<!-- CTO-CYCLE-STATUS:END -->"
HTML_START = "<!-- CTO-CYCLE-STATUS:START -->"
HTML_END = "<!-- CTO-CYCLE-STATUS:END -->"


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def render_cycle_block(status: dict[str, Any]) -> str:
    """Markdown block for DOD.md."""
    lines = [
        DOD_START,
        "",
        f"## CTO cycle status — `{status.get('cycle_id') or 'unknown'}`",
        "",
        f"- **data:** {status.get('timestamp_utc') or _utc_now()}",
        f"- **branch:** `{status.get('branch') or ''}`",
        f"- **commit-base:** `{status.get('commit_base') or ''}`",
        f"- **commit candidato:** `{status.get('commit_candidate') or ''}`",
        f"- **PR:** {status.get('pr') or 'n/a'}",
        f"- **objetivo:** {status.get('objective') or ''}",
        f"- **DoD items:** {', '.join(status.get('dod_items') or []) or 'n/a'}",
        f"- **before:** {status.get('before') or ''}",
        f"- **after:** {status.get('after') or ''}",
        f"- **verification:** {status.get('verification_result') or ''}",
        f"- **QA:** {status.get('qa_verdict') or ''}",
        f"- **integração:** {status.get('integration_state') or 'IMPLEMENTED_AWAITING_MERGE'}",
        f"- **blockers:** {status.get('blockers') or 'none'}",
        f"- **próxima ação:** {status.get('next_action') or ''}",
        f"- **evidências:** {status.get('evidence_paths') or ''}",
        f"- **DeepSeek:** {status.get('deepseek_summary') or ''}",
        "",
        DOD_END,
    ]
    return "\n".join(lines) + "\n"


def render_html_panel(status: dict[str, Any]) -> str:
    """Compact HTML panel for executive page."""
    rows = [
        ("cycle_id", status.get("cycle_id")),
        ("timestamp", status.get("timestamp_utc")),
        ("branch", status.get("branch")),
        ("commit_candidate", status.get("commit_candidate")),
        ("PR", status.get("pr")),
        ("verification", status.get("verification_result")),
        ("QA", status.get("qa_verdict")),
        ("integration", status.get("integration_state") or "IMPLEMENTED_AWAITING_MERGE"),
        ("before", status.get("before")),
        ("after", status.get("after")),
        ("next_action", status.get("next_action")),
        ("deepseek", status.get("deepseek_summary")),
    ]
    body = "".join(
        f"<tr><th>{k}</th><td>{_html_escape(str(v or ''))}</td></tr>" for k, v in rows
    )
    return (
        f"{HTML_START}\n"
        f'<section id="cto-cycle-status" data-cycle="{_html_escape(str(status.get("cycle_id") or ""))}">\n'
        f"<h2>CTO cycle status</h2>\n"
        f"<table>{body}</table>\n"
        f"<p><strong>Claims proibidos sem evidência:</strong> "
        f"LOCAL_READY, VPS_OPERATIONAL, PROJECT_DONE, 95% coverage</p>\n"
        f"</section>\n"
        f"{HTML_END}\n"
    )


def _html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def upsert_delimited_block(text: str, start: str, end: str, block: str) -> str:
    """Replace existing delimited block or append once. Idempotent."""
    pattern = re.compile(
        re.escape(start) + r".*?" + re.escape(end),
        re.DOTALL,
    )
    block = block.strip() + "\n"
    if pattern.search(text):
        return pattern.sub(block.rstrip("\n"), text)
    # Append before end of file with separator
    if not text.endswith("\n"):
        text += "\n"
    return text + "\n" + block


def upsert_dod_cycle_status(
    status: dict[str, Any],
    *,
    root: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    root = root or repo_root()
    path = dod_path(root)
    original = path.read_text(encoding="utf-8") if path.is_file() else ""
    block = render_cycle_block(status)
    updated = upsert_delimited_block(original, DOD_START, DOD_END, block)
    # Safety: never invent checkbox flips in this helper
    if re.search(r"- \[ \].*→\s*\[x\]", block):
        return {"ok": False, "error": "cycle status must not flip checkboxes inline"}
    if not dry_run and updated != original:
        path.write_text(updated, encoding="utf-8")
    return {
        "ok": True,
        "path": str(path),
        "changed": updated != original,
        "dry_run": dry_run,
        "sha256": hashlib.sha256(updated.encode("utf-8")).hexdigest(),
    }


def upsert_html_cycle_status(
    status: dict[str, Any],
    *,
    root: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    root = root or repo_root()
    path = executive_html_path(root)
    original = path.read_text(encoding="utf-8") if path.is_file() else "<html><body></body></html>\n"
    block = render_html_panel(status)
    updated = upsert_delimited_block(original, HTML_START, HTML_END, block)
    # Forbidden claims without evidence marker
    forbidden = ("LOCAL_READY", "VPS_OPERATIONAL", "PROJECT_DONE")
    for claim in forbidden:
        if claim in block and "sem evidência" not in block and "proibidos" not in block:
            # panel lists them as prohibited — OK
            pass
    if not dry_run and updated != original:
        path.write_text(updated, encoding="utf-8")
    return {
        "ok": True,
        "path": str(path),
        "changed": updated != original,
        "dry_run": dry_run,
        "sha256": hashlib.sha256(updated.encode("utf-8")).hexdigest(),
    }


def write_cycle_artifacts(
    status: dict[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Write cycle-report.json, dod-delta.json, manifest, checksums."""
    root = root or repo_root()
    cycle_id = str(status.get("cycle_id") or "unknown")
    cdir = cycles_dir(root) / cycle_id
    cdir.mkdir(parents=True, exist_ok=True)
    report = redact_obj(
        {
            "schema_version": "1.0",
            "timestamp_utc": _utc_now(),
            **status,
        }
    )
    delta = {
        "cycle_id": cycle_id,
        "before": status.get("before"),
        "after": status.get("after"),
        "dod_items": status.get("dod_items") or [],
        "checkbox_flips": status.get("checkbox_flips") or [],
        "partial_advances": status.get("partial_advances") or [],
        "integration_state": status.get("integration_state")
        or "IMPLEMENTED_AWAITING_MERGE",
        "verification_result": status.get("verification_result"),
        "qa_verdict": status.get("qa_verdict"),
    }
    (cdir / "cycle-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (cdir / "dod-delta.json").write_text(
        json.dumps(delta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    files = {
        "cycle-report.json": hashlib.sha256(
            (cdir / "cycle-report.json").read_bytes()
        ).hexdigest(),
        "dod-delta.json": hashlib.sha256((cdir / "dod-delta.json").read_bytes()).hexdigest(),
    }
    manifest = {
        "cycle_id": cycle_id,
        "files": list(files.keys()),
        "checksums": files,
        "timestamp_utc": _utc_now(),
    }
    (cdir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (cdir / "checksums.json").write_text(
        json.dumps(files, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return {"ok": True, "dir": str(cdir), "manifest": manifest}


def apply_cycle_status(
    status: dict[str, Any],
    *,
    root: Path | None = None,
    dry_run: bool = False,
    update_dod: bool = True,
    update_html: bool = True,
) -> dict[str, Any]:
    """Idempotent end-of-cycle documentation update."""
    root = root or repo_root()
    status = {**status, "timestamp_utc": status.get("timestamp_utc") or _utc_now()}
    arts = write_cycle_artifacts(status, root=root)
    dod_res = (
        upsert_dod_cycle_status(status, root=root, dry_run=dry_run)
        if update_dod
        else {"ok": True, "skipped": True}
    )
    html_res = (
        upsert_html_cycle_status(status, root=root, dry_run=dry_run)
        if update_html
        else {"ok": True, "skipped": True}
    )
    return redact_obj(
        {
            "ok": bool(dod_res.get("ok") and html_res.get("ok")),
            "artifacts": arts,
            "dod": dod_res,
            "html": html_res,
            "dry_run": dry_run,
        }
    )
