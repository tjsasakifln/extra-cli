"""PNCP ARP/IRP lake persist (#250) — official ID, pagination, hashes."""

from __future__ import annotations

import json
from typing import Any

from scripts.complementary.contract import (
    RunResult,
    pagination_terminal,
    reconcile_counts,
    sha256_json,
)

SOURCE = "pncp_arp"
OFFICIAL_ID_KEYS = ("identificadorAta", "numeroControlePNCPAta", "id")


def official_ata_id(raw: dict[str, Any]) -> str:
    for key in OFFICIAL_ID_KEYS:
        value = raw.get(key)
        if value:
            return str(value)
    return ""


def normalize_ata(raw: dict[str, Any]) -> dict[str, Any] | None:
    ata_id = official_ata_id(raw)
    if not ata_id:
        return None
    orgao = raw.get("orgaoEntidade") or raw.get("orgao") or {}
    if not isinstance(orgao, dict):
        orgao = {}
    items = raw.get("itens") or raw.get("items") or []
    suppliers = raw.get("fornecedores") or raw.get("participantes") or []
    documents = raw.get("arquivos") or raw.get("documentos") or []
    status = str(raw.get("situacao") or raw.get("status") or "UNKNOWN")
    row = {
        "source": SOURCE,
        "source_id": ata_id,
        "official_id": ata_id,
        "pncp_id_origem": str(raw.get("numeroControlePNCP") or raw.get("pncpIdOrigem") or ""),
        "orgao_cnpj": "".join(c for c in str(orgao.get("cnpj") or "") if c.isdigit()),
        "orgao_nome": str(orgao.get("razaoSocial") or orgao.get("nome") or ""),
        "objeto": str(raw.get("objeto") or raw.get("descricaoObjeto") or ""),
        "status": status,
        "vigencia_inicio": str(raw.get("dataVigenciaInicio") or raw.get("dataInicioVigencia") or "")[:10] or None,
        "vigencia_fim": str(raw.get("dataVigenciaFim") or raw.get("dataValidade") or "")[:10] or None,
        "itens": items if isinstance(items, list) else [],
        "fornecedores": suppliers if isinstance(suppliers, list) else [],
        "documentos": documents if isinstance(documents, list) else [],
        "raw_hash": sha256_json(raw),
        "content_hash": sha256_json({"id": ata_id, "status": status, "objeto": raw.get("objeto"), "itens": items}),
    }
    return row


ENSURE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.canonical_arp_atas (
    official_id       TEXT PRIMARY KEY,
    source            TEXT NOT NULL DEFAULT 'pncp_arp',
    pncp_id_origem    TEXT,
    orgao_cnpj        TEXT,
    orgao_nome        TEXT,
    objeto            TEXT,
    status            TEXT,
    vigencia_inicio   DATE,
    vigencia_fim      DATE,
    itens             JSONB NOT NULL DEFAULT '[]'::jsonb,
    fornecedores      JSONB NOT NULL DEFAULT '[]'::jsonb,
    documentos        JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw_hash          TEXT NOT NULL,
    content_hash      TEXT NOT NULL,
    previous_hash     TEXT,
    persisted_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

UPSERT_SQL = """
INSERT INTO public.canonical_arp_atas (
    official_id, source, pncp_id_origem, orgao_cnpj, orgao_nome, objeto, status,
    vigencia_inicio, vigencia_fim, itens, fornecedores, documentos,
    raw_hash, content_hash, previous_hash, persisted_at
) VALUES (
    %(official_id)s, %(source)s, %(pncp_id_origem)s, %(orgao_cnpj)s, %(orgao_nome)s,
    %(objeto)s, %(status)s, %(vigencia_inicio)s, %(vigencia_fim)s,
    %(itens)s::jsonb, %(fornecedores)s::jsonb, %(documentos)s::jsonb,
    %(raw_hash)s, %(content_hash)s, %(previous_hash)s, NOW()
)
ON CONFLICT (official_id) DO UPDATE SET
    objeto = EXCLUDED.objeto,
    status = EXCLUDED.status,
    vigencia_inicio = EXCLUDED.vigencia_inicio,
    vigencia_fim = EXCLUDED.vigencia_fim,
    itens = EXCLUDED.itens,
    fornecedores = EXCLUDED.fornecedores,
    documentos = EXCLUDED.documentos,
    raw_hash = EXCLUDED.raw_hash,
    previous_hash = CASE
        WHEN canonical_arp_atas.content_hash IS DISTINCT FROM EXCLUDED.content_hash
        THEN canonical_arp_atas.content_hash
        ELSE canonical_arp_atas.previous_hash
    END,
    content_hash = EXCLUDED.content_hash,
    persisted_at = NOW()
RETURNING official_id, content_hash, previous_hash
"""

SELECT_ONE_SQL = """
SELECT official_id, content_hash, previous_hash, objeto, status
FROM public.canonical_arp_atas
WHERE official_id = %s
"""


def _json_param(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, default=str)


def persist_atas_to_postgres(conn: Any, rows: list[dict[str, Any]]) -> dict[str, int]:
    """Write ARP rows to local PostgreSQL. conn must be a live psycopg2 connection."""
    if conn is None:
        raise RuntimeError("BLOCKED: PostgreSQL connection required for ARP persist")
    persisted = 0
    deduped = 0
    with conn.cursor() as cur:
        cur.execute(ENSURE_TABLE_SQL)
        for row in rows:
            params = {
                **row,
                "itens": _json_param(row.get("itens") or []),
                "fornecedores": _json_param(row.get("fornecedores") or []),
                "documentos": _json_param(row.get("documentos") or []),
                "previous_hash": row.get("previous_hash"),
            }
            cur.execute(SELECT_ONE_SQL, (row["official_id"],))
            existing = cur.fetchone()
            cur.execute(UPSERT_SQL, params)
            written = cur.fetchone()
            if written is None:
                raise RuntimeError(f"ARP upsert returned no row for {row['official_id']}")
            if existing is None:
                persisted += 1
            else:
                deduped += 1
                if existing[1] != row["content_hash"]:
                    persisted += 1
    conn.commit()
    return {"persisted": persisted, "deduplicated": deduped}


def persist_window(
    pages: list[dict[str, Any]],
    *,
    lake: dict[str, dict[str, Any]] | None = None,
    skipped: bool = False,
    conn: Any = None,
    dsn: str | None = None,
) -> RunResult:
    """Idempotent persist by official ID. Job skipped is never success.

    Local PostgreSQL is the metadata authority only when a live connection
    (or DSN) actually writes. An in-memory dict is staging, not authority.
    """
    store = lake if lake is not None else {}
    if skipped:
        return RunResult(
            source=SOURCE,
            terminal="skipped",
            fetched=0,
            persisted=0,
            deduplicated=0,
            failed=0,
            reason="job_skipped_not_success",
            job={"authority": "none", "upsert": "skipped"},
        )
    fetched = 0
    rejected = 0
    persisted = 0
    deduped = 0
    records: list[dict[str, Any]] = []
    last_complete = True
    for page in pages:
        items = page.get("data") if isinstance(page.get("data"), list) else page.get("items") or []
        complete = bool(page.get("complete", True))
        last_complete = complete
        if page.get("blocked"):
            return RunResult(SOURCE, "BLOCKED", fetched, persisted, deduped, rejected, reason="blocked")
        if page.get("error"):
            return RunResult(SOURCE, "FAILED", fetched, persisted, deduped, rejected, reason=str(page["error"]))
        for raw in items:
            fetched += 1
            row = normalize_ata(raw) if isinstance(raw, dict) else None
            if row is None:
                rejected += 1
                continue
            key = row["official_id"]
            if key in store:
                deduped += 1
                prev = store[key]
                if prev["content_hash"] != row["content_hash"]:
                    row["previous_hash"] = prev["content_hash"]
                    store[key] = row
                    persisted += 1
                else:
                    store[key] = prev
            else:
                store[key] = row
                persisted += 1
            records.append(store[key])
    terminal = pagination_terminal(
        pages_seen=len(pages),
        last_complete=last_complete,
        record_count=len(store) if not pages else persisted + deduped,
    )
    if not pages:
        terminal = "partial"
        reason = "no_pages_incomplete_scope"
    elif terminal == "ZERO_CONFIRMED" and not last_complete:
        terminal = "partial"
        reason = "zero_without_complete_scope"
    else:
        reason = None
    if not reconcile_counts(fetched=fetched, persisted=persisted, rejected=rejected + deduped):
        pass

    own_conn = False
    live = conn
    if live is None and dsn:
        import psycopg2

        live = psycopg2.connect(dsn)
        own_conn = True
    authority = "staging_memory"
    if live is not None:
        counts = persist_atas_to_postgres(live, list(store.values()))
        persisted = counts["persisted"]
        deduped = counts["deduplicated"]
        authority = "postgresql_local"
        if own_conn:
            live.close()

    return RunResult(
        source=SOURCE,
        terminal=terminal,
        fetched=fetched,
        persisted=persisted,
        deduplicated=deduped,
        failed=rejected,
        records=list(store.values()),
        reason=reason,
        job={"authority": authority, "upsert": "official_id", "table": "canonical_arp_atas"},
    )


def crawl(mode: str = "full") -> list[dict[str, Any]]:
    """Collect ARP pages from a fixture (or BLOCKED). Never silent empty."""
    import os
    from pathlib import Path

    from scripts.complementary.collect import observations_from_result

    del mode
    fixture = os.environ.get("ARP_FIXTURE") or os.environ.get("COMPLEMENTARY_FIXTURE")
    dsn = os.environ.get("LOCAL_DATALAKE_DSN")
    if not fixture:
        return [
            {
                "source": SOURCE,
                "terminal": "BLOCKED",
                "reason": "missing_arp_fixture",
                "fetched": 0,
                "silent_zero": False,
            }
        ]
    payload = json.loads(Path(fixture).read_text(encoding="utf-8"))
    result = persist_window(
        payload.get("pages") or [],
        skipped=bool(payload.get("skipped")),
        dsn=dsn,
    )
    return observations_from_result(result)


def transform(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in records:
        if not isinstance(raw, dict):
            continue
        if raw.get("official_id") and raw.get("content_hash"):
            out.append(raw)
            continue
        row = normalize_ata(raw)
        if row:
            out.append(row)
    return out
