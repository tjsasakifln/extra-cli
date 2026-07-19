"""Refresh executive HTML with derived CTO/DoD/Issues projection — no secrets."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.cto.paths import (
    decision_path,
    executive_html_path,
    observation_path,
    repo_root,
    state_path,
)
from scripts.cto.redaction import redact_obj, redact_text

CTO_PANEL_START = "<!-- CTO-AUTOPILOT-PANEL:START -->"
CTO_PANEL_END = "<!-- CTO-AUTOPILOT-PANEL:END -->"
CTO_JSON_START = "<!-- CTO-AUTOPILOT-DATA:START -->"
CTO_JSON_END = "<!-- CTO-AUTOPILOT-DATA:END -->"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def build_executive_payload(root: Path | None = None) -> dict[str, Any]:
    root = root or repo_root()
    obs = _load_json(observation_path(root))
    decision = _load_json(decision_path(root))
    state = _load_json(state_path(root))
    git = obs.get("git") or {}
    dod = obs.get("dod") or {}
    issues = obs.get("issues") or {}
    prs = obs.get("prs") or []

    by_state = issues.get("by_state") or {}
    # Prefer explicit counts (not truncated samples)
    issues_summary = dict(issues.get("by_state_counts") or {})
    if not issues_summary:
        issues_summary = {k: len(v) for k, v in by_state.items()}

    payload = {
        "generated_at_utc": _utc_now(),
        "commit": git.get("commit"),
        "branch": git.get("branch"),
        "dod": {
            "checked": dod.get("checked"),
            "open": dod.get("open"),
            "total": dod.get("total"),
            "percent_checked": dod.get("percent_checked"),
        },
        "gates": dod.get("gates") or {},
        "claims": obs.get("claims") or {},
        "prs_open": [
            {
                "number": p.get("number"),
                "title": p.get("title"),
                "draft": p.get("isDraft"),
                "head": p.get("headRefName"),
            }
            for p in prs[:15]
        ],
        "issues": {
            "open_count": issues.get("open_count"),
            "by_state": issues_summary,
        },
        "blockers_count": len(obs.get("blockers") or []),
        "work_item_current": {
            "work_id": state.get("work_id") or decision.get("work_id"),
            "issue_number": state.get("issue_number") or decision.get("issue_number"),
            "cycle_id": state.get("cycle_id") or decision.get("cycle_id"),
        },
        "last_decision": {
            "decision": decision.get("decision"),
            "objective": decision.get("objective"),
            "strategic_reason": decision.get("strategic_reason"),
            "confidence": decision.get("confidence"),
        },
        "cto_state": state.get("status"),
        "next_action": _next_action(state, decision),
        "distinctions": {
            "open_work": issues.get("open_count"),
            "implemented": "see PRs / branches — not auto-integrated",
            "in_review": issues_summary.get("state:review", 0),
            "accepted": "Issue closed ≠ DoD done",
            "integrated": "only after human merge to main",
            "dod_complete": dod.get("checked"),
        },
    }
    return redact_obj(payload)


def _next_action(state: dict[str, Any], decision: dict[str, Any]) -> str:
    status = state.get("status") or "IDLE"
    if status == "WAITING_HUMAN":
        return "Human gate: review WAITING_HUMAN reason and authorize/reject"
    if status == "BLOCKED":
        return "Inspect blockers; restore DeepSeek or clear block"
    if status == "PAUSED":
        return "python -m scripts.cto.cli resume"
    if decision.get("decision") == "EXECUTE":
        return "run-once or prepare → execute → verify"
    if decision.get("decision") == "NOOP":
        return "observe again later; no work selected"
    return "python -m scripts.cto.cli observe && python -m scripts.cto.cli decide"


def render_panel_html(payload: dict[str, Any]) -> str:
    dod = payload.get("dod") or {}
    ld = payload.get("last_decision") or {}
    wi = payload.get("work_item_current") or {}
    issues = payload.get("issues") or {}
    prs = payload.get("prs_open") or []
    pr_lines = "".join(
        f"<li>#{p.get('number')} {redact_text(str(p.get('title') or ''))[:80]}"
        f"{' (draft)' if p.get('draft') else ''}</li>"
        for p in prs[:8]
    ) or "<li>(none)</li>"
    return f"""{CTO_PANEL_START}
<section id="cto-autopilot-panel" style="margin:1.5rem 0;padding:1rem;border:1px solid #8883;border-radius:10px;font-family:system-ui,sans-serif">
  <h2 style="margin-top:0">CTO Autopilot — projeção operacional</h2>
  <p style="opacity:.8">Derivado de DoD + git + Issues + decisão. <strong>Não</strong> é fonte canônica. Issues fechadas ≠ DoD concluído.</p>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:.75rem">
    <div><strong>DoD</strong><br>{dod.get('checked')}/{dod.get('total')} ({dod.get('percent_checked')}%)</div>
    <div><strong>Issues abertas</strong><br>{issues.get('open_count')}</div>
    <div><strong>Estado CTO</strong><br>{payload.get('cto_state') or 'IDLE'}</div>
    <div><strong>Branch</strong><br><code>{payload.get('branch')}</code></div>
    <div><strong>Commit</strong><br><code>{(payload.get('commit') or '')[:12]}</code></div>
    <div><strong>Atualizado</strong><br>{payload.get('generated_at_utc')}</div>
  </div>
  <h3>Trabalho atual</h3>
  <ul>
    <li>work_id: <code>{wi.get('work_id')}</code></li>
    <li>issue: <code>{wi.get('issue_number')}</code></li>
    <li>cycle: <code>{wi.get('cycle_id')}</code></li>
  </ul>
  <h3>Última decisão</h3>
  <p><strong>{ld.get('decision')}</strong> — {redact_text(str(ld.get('objective') or ''))[:200]}</p>
  <p style="opacity:.85">{redact_text(str(ld.get('strategic_reason') or ''))[:300]}</p>
  <h3>PRs abertas</h3>
  <ul>{pr_lines}</ul>
  <h3>Próxima ação</h3>
  <p>{redact_text(str(payload.get('next_action') or ''))}</p>
  <h3>Distinções obrigatórias</h3>
  <ul>
    <li>Trabalho aberto ≠ implementado ≠ em revisão ≠ aceito ≠ integrado ≠ requisito DoD concluído</li>
    <li>Claims proibidos sem evidência: LOCAL_READY, PRE_VPS_FINAL_READY, VPS_OPERATIONAL, PROJECT_DONE, 95%</li>
  </ul>
</section>
{CTO_PANEL_END}
"""


def upsert_panel(html: str, panel: str, data_json: str) -> str:
    # Remove existing panel
    html = re.sub(
        re.escape(CTO_PANEL_START) + r".*?" + re.escape(CTO_PANEL_END),
        "",
        html,
        flags=re.S,
    )
    html = re.sub(
        re.escape(CTO_JSON_START) + r".*?" + re.escape(CTO_JSON_END),
        "",
        html,
        flags=re.S,
    )
    data_block = f"{CTO_JSON_START}\n<script type=\"application/json\" id=\"cto-autopilot-data\">{data_json}</script>\n{CTO_JSON_END}\n"
    inject = data_block + panel
    # Prefer insert before </body>
    if re.search(r"</body>", html, re.I):
        return re.sub(r"</body>", inject + "\n</body>", html, count=1, flags=re.I)
    return html + "\n" + inject


def refresh_executive(root: Path | None = None) -> dict[str, Any]:
    root = root or repo_root()
    path = executive_html_path(root)
    if not path.is_file():
        return {"ok": False, "error": "executive HTML not found"}
    payload = build_executive_payload(root)
    # Ensure no secrets
    raw_json = json.dumps(payload, ensure_ascii=False)
    if re.search(r"sk-[A-Za-z0-9]{10,}|gho_|ghp_|api_key\s*=\s*\S+", raw_json, re.I):
        raw_json = redact_text(raw_json)
        payload = json.loads(raw_json)
    panel = render_panel_html(payload)
    original = path.read_text(encoding="utf-8", errors="replace")
    updated = upsert_panel(original, panel, raw_json)
    path.write_text(updated, encoding="utf-8")
    return {
        "ok": True,
        "path": str(path.relative_to(root)),
        "sha256": hashlib.sha256(updated.encode("utf-8")).hexdigest(),
        "generated_at_utc": payload.get("generated_at_utc"),
        "dod_percent": (payload.get("dod") or {}).get("percent_checked"),
    }
