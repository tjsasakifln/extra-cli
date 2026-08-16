"""PNCP ARP/IRP lake persist (#250) — official ID, pagination, hashes."""

from __future__ import annotations

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
        "content_hash": sha256_json(
            {"id": ata_id, "status": status, "objeto": raw.get("objeto"), "itens": items}
        ),
    }
    return row


def persist_window(
    pages: list[dict[str, Any]],
    *,
    lake: dict[str, dict[str, Any]] | None = None,
    skipped: bool = False,
) -> RunResult:
    """Idempotent persist by official ID. Job skipped is never success."""
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
        # fetched = new persist + reject + identical-dedup
        pass
    return RunResult(
        source=SOURCE,
        terminal=terminal,
        fetched=fetched,
        persisted=persisted,
        deduplicated=deduped,
        failed=rejected,
        records=list(store.values()),
        reason=reason,
        job={"authority": "postgresql_local", "upsert": "official_id"},
    )


def crawl(mode: str = "full") -> list[dict[str, Any]]:
    del mode
    return []


def transform(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in records:
        row = normalize_ata(raw)
        if row:
            out.append(row)
    return out
