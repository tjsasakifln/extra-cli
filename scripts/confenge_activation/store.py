"""Persistent activation projection store (JSONL + optional Postgres).

Activation state is a recomputable projection — NOT Decision & Outcome Memory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.confenge_activation.models import ActivationProjection


def load_projections_jsonl(path: Path | str) -> dict[str, dict[str, Any]]:
    p = Path(path)
    if not p.is_file():
        return {}
    out: dict[str, dict[str, Any]] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        row = json.loads(text)
        cnpj = str(row.get("cnpj14") or "")
        if len(cnpj) == 14:
            out[cnpj] = row
    return out


def write_projections_jsonl(path: Path | str, projections: list[ActivationProjection]) -> dict[str, Any]:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for proj in sorted(projections, key=lambda x: x.cnpj14):
            f.write(json.dumps(proj.as_dict(), ensure_ascii=False, sort_keys=True) + "\n")
    return {"path": str(p), "count": len(projections)}


def write_hot_set_jsonl(path: Path | str, hot: list[ActivationProjection]) -> dict[str, Any]:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for proj in hot:
            f.write(json.dumps(proj.as_dict(), ensure_ascii=False, sort_keys=True) + "\n")
    return {"path": str(p), "count": len(hot)}


def upsert_projections_pg(dsn: str, projections: list[ActivationProjection]) -> int:
    """Optional Postgres upsert into confenge_activation_projections."""
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("psycopg required for PG activation store") from exc

    sql = """
    INSERT INTO confenge_activation_projections (
        cnpj14, activation_state, activation_score, reason_codes,
        evaluated_at, next_best_action_at, expires_at,
        source_hash, trigger_hash, last_hot_set_at, policy_version,
        score_components, commercial_state, updated_at
    ) VALUES (
        %(cnpj14)s, %(activation_state)s, %(activation_score)s, %(reason_codes)s::jsonb,
        %(evaluated_at)s, %(next_best_action_at)s, %(expires_at)s,
        %(source_hash)s, %(trigger_hash)s, %(last_hot_set_at)s, %(policy_version)s,
        %(score_components)s::jsonb, %(commercial_state)s, now()
    )
    ON CONFLICT (cnpj14) DO UPDATE SET
        activation_state = EXCLUDED.activation_state,
        activation_score = EXCLUDED.activation_score,
        reason_codes = EXCLUDED.reason_codes,
        evaluated_at = EXCLUDED.evaluated_at,
        next_best_action_at = EXCLUDED.next_best_action_at,
        expires_at = EXCLUDED.expires_at,
        source_hash = EXCLUDED.source_hash,
        trigger_hash = EXCLUDED.trigger_hash,
        last_hot_set_at = COALESCE(EXCLUDED.last_hot_set_at, confenge_activation_projections.last_hot_set_at),
        policy_version = EXCLUDED.policy_version,
        score_components = EXCLUDED.score_components,
        commercial_state = EXCLUDED.commercial_state,
        updated_at = now()
    """
    n = 0
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            for proj in projections:
                d = proj.as_dict()
                cur.execute(
                    sql,
                    {
                        "cnpj14": d["cnpj14"],
                        "activation_state": d["activation_state"],
                        "activation_score": d["activation_score"],
                        "reason_codes": json.dumps(d["reason_codes"]),
                        "evaluated_at": d["evaluated_at"],
                        "next_best_action_at": d["next_best_action_at"],
                        "expires_at": d["expires_at"],
                        "source_hash": d["source_hash"],
                        "trigger_hash": d["trigger_hash"],
                        "last_hot_set_at": d["last_hot_set_at"],
                        "policy_version": d["policy_version"],
                        "score_components": json.dumps(d["score_components"]),
                        "commercial_state": d["commercial_state"],
                    },
                )
                n += 1
        conn.commit()
    return n


def load_projections_pg(dsn: str) -> dict[str, dict[str, Any]]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("psycopg required for PG activation store") from exc

    sql = """
    SELECT cnpj14, activation_state, activation_score, reason_codes,
           evaluated_at, next_best_action_at, expires_at,
           source_hash, trigger_hash, last_hot_set_at, policy_version,
           score_components, commercial_state,
           active_contract_count, contract_count_recent
    FROM confenge_activation_projections
    """
    out: dict[str, dict[str, Any]] = {}
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            for row in cur.fetchall():
                cnpj = str(row["cnpj14"])
                d = dict(row)
                # normalize JSON
                for k in ("reason_codes", "score_components"):
                    if isinstance(d.get(k), str):
                        d[k] = json.loads(d[k])
                for k in ("evaluated_at", "next_best_action_at", "expires_at", "last_hot_set_at"):
                    if d.get(k) is not None and hasattr(d[k], "isoformat"):
                        d[k] = d[k].isoformat().replace("+00:00", "Z")
                out[cnpj] = d
    return out
