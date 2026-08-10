"""Human-readable explanation of a company's target-fit state."""

from __future__ import annotations

import json
from typing import Any

from scripts.confenge_target_fit.cdc import company_from_any_cnpj
from scripts.confenge_target_fit.db import connect
from scripts.confenge_target_fit.freshness import freshness_for_company
from scripts.confenge_target_fit.store import get_current, history_for_company


def explain_cnpj(dsn: str, cnpj: str) -> dict[str, Any]:
    company_key, raiz = company_from_any_cnpj(cnpj)
    conn = connect(dsn, readonly=True)
    try:
        current = get_current(conn, company_key)
        history = history_for_company(conn, company_key, limit=10)
        # reopen rw-less path for freshness (uses readonly ok if control exists)
    finally:
        conn.close()

    conn2 = connect(dsn, readonly=False)
    try:
        fresh = freshness_for_company(conn2, company_key)
        with conn2.cursor() as cur:
            cur.execute(
                """
                SELECT event_type, old_class, new_class, created_at, reason_codes
                FROM confenge_target_fit_events
                WHERE company_key = %s
                ORDER BY created_at DESC
                LIMIT 10
                """,
                (company_key,),
            )
            events = [dict(r) for r in (cur.fetchall() or [])]
            cur.execute(
                """
                SELECT status, reason, priority, attempt_count, last_error,
                       detected_at, source_watermark
                FROM confenge_target_fit_dirty
                WHERE company_key = %s
                ORDER BY detected_at DESC
                LIMIT 5
                """,
                (company_key,),
            )
            dirty = [dict(r) for r in (cur.fetchall() or [])]
    finally:
        conn2.close()

    # Shadow row when async mode has not promoted to current yet
    conn3 = connect(dsn, readonly=True)
    try:
        with conn3.cursor() as cur:
            cur.execute(
                "SELECT * FROM confenge_target_fit_shadow WHERE company_key = %s",
                (company_key,),
            )
            shadow = cur.fetchone()
            shadow = dict(shadow) if shadow else None
    finally:
        conn3.close()

    return {
        "company_key": company_key,
        "cnpj_raiz": raiz,
        "current": _serialize(current),
        "shadow": _serialize(shadow),
        "freshness": fresh.as_dict(),
        "history": [_serialize(h) for h in history],
        "events": [_serialize(e) for e in events],
        "dirty_recent": [_serialize(d) for d in dirty],
    }


def format_explain(data: dict[str, Any]) -> str:
    lines = [
        f"company_key: {data['company_key']}",
        f"cnpj_raiz:   {data['cnpj_raiz']}",
        "",
        "== CURRENT ==",
    ]
    cur = data.get("current") or {}
    if not cur:
        lines.append("(no ACTIVE materialization)")
    else:
        lines.extend(
            [
                f"class:       {cur.get('target_fit_class')}",
                f"confidence:  {cur.get('target_fit_confidence')}",
                f"version:     {cur.get('target_fit_version')}",
                f"fingerprint: {cur.get('input_fingerprint')}",
                f"computed_at: {cur.get('computed_at')}",
                f"watermark:   {cur.get('source_watermark')}",
                f"ops_status:  {cur.get('operational_status')}",
                f"reasons:     {cur.get('target_fit_reason_codes')}",
                f"evidence:    {json.dumps(cur.get('target_fit_evidence') or [], ensure_ascii=False)[:500]}",
            ]
        )
    sh = data.get("shadow") or {}
    if sh:
        lines.extend(
            [
                "",
                "== SHADOW ==",
                f"shadow_class: {sh.get('shadow_class')}",
                f"vs_current:   {sh.get('current_class')}",
                f"transition:   {sh.get('transition')}",
                f"version:      {sh.get('target_fit_version')}",
                f"fingerprint:  {sh.get('input_fingerprint')}",
            ]
        )
    fr = data.get("freshness") or {}
    lines.extend(
        [
            "",
            "== FRESHNESS ==",
            f"fresh:  {fr.get('target_fit_fresh')}",
            f"reason: {fr.get('reason')}",
            f"blocks_send: {fr.get('blocks_send')}",
            "",
            "== RECENT HISTORY ==",
        ]
    )
    for h in data.get("history") or []:
        lines.append(
            f"  {h.get('computed_at')}: {h.get('previous_class')} → "
            f"{h.get('target_fit_class')} ({h.get('transition_event')})"
        )
    lines.append("")
    lines.append("== EVENTS ==")
    for e in data.get("events") or []:
        lines.append(
            f"  {e.get('created_at')}: {e.get('event_type')} "
            f"{e.get('old_class')}→{e.get('new_class')}"
        )
    lines.append("")
    lines.append("== DIRTY QUEUE ==")
    for d in data.get("dirty_recent") or []:
        lines.append(
            f"  {d.get('detected_at')}: {d.get('status')} prio={d.get('priority')} "
            f"reason={d.get('reason')} err={d.get('last_error')}"
        )
    return "\n".join(lines)


def _serialize(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if hasattr(v, "isoformat"):
                out[k] = v.isoformat()
            else:
                out[k] = v
        return out
    return obj
