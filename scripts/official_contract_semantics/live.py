"""Small read-only SC window. Unavailability is unavailability, never absence of a fact."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.official_contract_semantics.constants import (
    DEFAULT_LIVE_LIMIT,
    LIVE_VERSION,
    MAX_LIVE_LIMIT,
    USER_AGENT,
)
from scripts.official_contract_semantics.extract import extract_payload, extract_record
from scripts.official_contract_semantics.http_client import fetch_official
from scripts.official_contract_semantics.models import OfficialContractObservation, SourceUnavailability
from scripts.official_contract_semantics.reconcile import reconcile
from scripts.official_contract_semantics.serialize import content_hash, write_json, write_jsonl

PNCP_CONTRACT_URL = "https://pncp.gov.br/app/contratos/{contrato_id}"
# Same consulta contract as scripts/crawl/pncp_crawler_adapter.py.
# UF query param is not used: the official API has treated it as broken/ignored.
PNCP_API_URL = (
    "https://pncp.gov.br/api/consulta/v1/contratos?dataInicial={start}&dataFinal={end}&pagina=1&tamanhoPagina=10"
)

SC_SELECT = """
SELECT contrato_id, orgao_cnpj, orgao_nome, fornecedor_cnpj, fornecedor_nome,
       objeto_contrato, valor_total, data_inicio, data_fim, data_publicacao,
       data_assinatura, uf, municipio, source, source_id, ingested_at
FROM pncp_supplier_contracts
WHERE uf = %s
  AND is_active IS DISTINCT FROM FALSE
  AND (
        objeto_contrato ILIKE %s OR objeto_contrato ILIKE %s OR objeto_contrato ILIKE %s
     OR objeto_contrato ILIKE %s OR objeto_contrato ILIKE %s OR objeto_contrato ILIKE %s
  )
ORDER BY contrato_id
LIMIT %s
"""
SC_TOKENS = ("%paviment%", "%recapeamento%", "%cbuq%", "%asfalt%", "%microrevestimento%", "%aditiv%")


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_live_window(
    *,
    start: str | None = None,
    end: str | None = None,
    as_of: str | None = None,
    days: int = 30,
) -> tuple[str, str]:
    """Current configurable window. Never depends on a hardcoded campaign date."""
    if start and end:
        return start[:10], end[:10]
    if as_of:
        try:
            end_dt = datetime.fromisoformat(as_of.replace("Z", "+00:00")).date()
        except ValueError:
            end_dt = datetime.now(UTC).date()
    else:
        end_dt = datetime.now(UTC).date()
    start_dt = end_dt - timedelta(days=max(1, days))
    if start:
        return start[:10], end_dt.isoformat()
    if end:
        end_dt = datetime.fromisoformat(end[:10]).date()
        start_dt = end_dt - timedelta(days=max(1, days))
    return start_dt.isoformat(), end_dt.isoformat()


def pncp_ymd(iso_date: str) -> str:
    return iso_date.replace("-", "")[:8]


def resolve_dsn(explicit: str | None = None) -> str | None:
    return explicit or os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL")


def _row_to_record(row: dict[str, Any]) -> dict[str, Any]:
    contrato_id = str(row.get("contrato_id") or "").strip()
    return {
        "source_system": str(row.get("source") or "pncp"),
        "source_kind": "contract",
        "official_url": PNCP_CONTRACT_URL.format(contrato_id=contrato_id) if contrato_id else None,
        "source_document_id": contrato_id,
        "contract_identifier": contrato_id,
        "process_identifier": None,
        "contracting_entity_identifier": row.get("orgao_cnpj"),
        "supplier_identifier": row.get("fornecedor_cnpj"),
        "object_text": row.get("objeto_contrato"),
        "observed_at": str(row.get("data_publicacao") or row.get("ingested_at") or ""),
        "effective_at": str(row.get("data_assinatura") or "") or None,
        "period_start": str(row.get("data_inicio") or "") or None,
        "period_end": str(row.get("data_fim") or "") or None,
        "valor_total": row.get("valor_total"),
        "extra": {"uf": row.get("uf") or "SC", "municipio": row.get("municipio")},
        "confidence_class": "explicit_structured_field",
    }


def _select_rows(dsn: str, limit: int) -> tuple[list[dict[str, Any]] | None, SourceUnavailability | None]:
    try:
        from scripts.national_intel.db import connect, fetch_all
    except ImportError:
        return None, SourceUnavailability(
            official_url="postgresql://local/pncp_supplier_contracts",
            error_kind="dependency_unavailable",
            message="national_intel.db unavailable",
        )
    try:
        with connect(dsn) as conn:
            rows = fetch_all(conn, SC_SELECT, ("SC", *SC_TOKENS, limit))
        return [dict(row) for row in rows], None
    except Exception as exc:  # noqa: BLE001 — live path must record unavailability, not raise as absence
        return None, SourceUnavailability(
            official_url="postgresql://local/pncp_supplier_contracts",
            error_kind="dsn_query_failed",
            message=str(exc),
        )


def records_from_consulta_listing(
    *,
    listing_url: str,
    listing_body: str,
    listing_sha256: str,
    retrieved_at: str,
    limit: int,
) -> tuple[list[dict[str, Any]], list[SourceUnavailability], bool]:
    """Bind each record to the listing URL whose bytes produced listing_sha256.

    The HTML portal (/app/contratos/...) is kept as portal_url only. It must never
    inherit the consulta listing hash. The bool is True when the listing page had items.
    """
    try:
        payload = __import__("json").loads(listing_body)
    except ValueError as exc:
        return [], [SourceUnavailability(official_url=listing_url, error_kind="parser_error", message=str(exc))], False
    data = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(data, list):
        return (
            [],
            [SourceUnavailability(official_url=listing_url, error_kind="unexpected_shape", message="data_not_list")],
            False,
        )
    records: list[dict[str, Any]] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        contrato_id = str(
            item.get("numeroControlePncp") or item.get("numeroControlePNCP") or item.get("numeroContratoEmpenho") or ""
        )
        unidade = item.get("unidadeOrgao") if isinstance(item.get("unidadeOrgao"), dict) else {}
        uf = str(item.get("uf") or item.get("siglaUf") or unidade.get("ufSigla") or unidade.get("uf") or "")
        if uf.upper() not in {"SC", "SANTA CATARINA"}:
            continue
        portal_url = PNCP_CONTRACT_URL.format(contrato_id=contrato_id) if contrato_id else None
        records.append(
            {
                "source_system": "pncp",
                "source_kind": "contract",
                "official_url": listing_url,
                "source_document_id": contrato_id or None,
                "contract_identifier": contrato_id or None,
                "contracting_entity_identifier": (
                    item.get("cnpjOrgao") or (item.get("orgaoEntidade") or {}).get("cnpj")
                    if isinstance(item.get("orgaoEntidade"), dict)
                    else item.get("cnpjOrgao")
                ),
                "supplier_identifier": item.get("niFornecedor")
                or ((item.get("fornecedor") or {}).get("ni") if isinstance(item.get("fornecedor"), dict) else None),
                "object_text": item.get("objetoContrato") or item.get("objeto"),
                "valor_global": item.get("valorGlobal") or item.get("valorInicial"),
                "period_start": item.get("dataVigenciaInicio"),
                "period_end": item.get("dataVigenciaFim"),
                "effective_at": item.get("dataAssinatura"),
                "observed_at": item.get("dataPublicacaoPncp"),
                "event_effective_at": item.get("dataAssinatura"),
                "source_published_at": item.get("dataPublicacaoPncp"),
                "retrieved_at": retrieved_at,
                "verified_at": retrieved_at,
                "source_document_sha256": listing_sha256,
                "locator": {"json_path": f"$.data[{index}].objetoContrato"},
                "extra": {
                    "uf": "SC",
                    "municipio": item.get("nomeUnidade") or unidade.get("municipioNome") or item.get("municipio"),
                    "portal_url": portal_url,
                    "listing_index": index,
                },
            }
        )
        if len(records) >= limit:
            break
    return records, [], bool(data)


def _api_records(
    limit: int,
    cache_dir: Path | None,
    *,
    start: str,
    end: str,
    retrieved_at: str,
) -> tuple[list[dict[str, Any]], list[SourceUnavailability]]:
    records: list[dict[str, Any]] = []
    errors: list[SourceUnavailability] = []
    page = 1
    max_pages = 3
    while len(records) < limit and page <= max_pages:
        url = (
            "https://pncp.gov.br/api/consulta/v1/contratos"
            f"?dataInicial={pncp_ymd(start)}&dataFinal={pncp_ymd(end)}"
            f"&pagina={page}&tamanhoPagina=10"
        )
        fetched = fetch_official(url, cache_dir=cache_dir)
        if not fetched.ok or not fetched.body or not fetched.sha256:
            errors.append(
                fetched.unavailability
                or SourceUnavailability(official_url=url, error_kind="unavailable", message="empty_body")
            )
            break
        page_rows, page_errors, saw_items = records_from_consulta_listing(
            listing_url=url,
            listing_body=fetched.body,
            listing_sha256=fetched.sha256,
            retrieved_at=retrieved_at,
            limit=limit - len(records),
        )
        errors.extend(page_errors)
        if page_errors and not page_rows:
            break
        records.extend(page_rows)
        if not saw_items or len(records) >= limit:
            break
        page += 1
    return records, errors


def build_replay_command(
    *,
    limit: int,
    as_of: str,
    out_dir: str | Path | None = None,
    cache_dir: str | Path | None = None,
    fetch_pages: bool = True,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    parts = [
        "python3 -m scripts.official_contract_semantics live-readonly",
        f"--limit {int(limit)}",
        f"--as-of {as_of}",
    ]
    if start_date:
        parts.append(f"--start-date {start_date}")
    if end_date:
        parts.append(f"--end-date {end_date}")
    if not fetch_pages:
        parts.append("--skip-pages")
    if cache_dir is not None:
        parts.append(f"--cache-dir {Path(cache_dir)}")
    if out_dir is not None:
        parts.append(f"--out {Path(out_dir)}")
    return " ".join(parts)


def run_live_readonly(
    *,
    dsn: str | None = None,
    limit: int = DEFAULT_LIVE_LIMIT,
    out_dir: str | Path | None = None,
    cache_dir: str | Path | None = None,
    fetch_pages: bool = True,
    as_of: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    bounded = max(1, min(int(limit), MAX_LIVE_LIMIT))
    started = _now()
    stamp = as_of or started
    window_start, window_end = default_live_window(start=start_date, end=end_date, as_of=stamp)
    cache = Path(cache_dir) if cache_dir else None
    considered = 0
    obtained = 0
    failed: list[dict[str, Any]] = []
    unavailabilities: list[SourceUnavailability] = []
    observations: list[OfficialContractObservation] = []
    sources_used: list[str] = []

    resolved = resolve_dsn(dsn)
    rows: list[dict[str, Any]] = []
    if resolved:
        sources_used.append("pncp_supplier_contracts")
        selected, error = _select_rows(resolved, bounded)
        if error:
            unavailabilities.append(error)
            failed.append(error.as_dict())
        else:
            rows = selected or []
    else:
        unavailabilities.append(
            SourceUnavailability(
                official_url="postgresql://local/pncp_supplier_contracts",
                error_kind="dsn_unavailable",
                message="LOCAL_DATALAKE_DSN absent",
            )
        )

    if not rows:
        sources_used.append("pncp_consulta_api")
        api_rows, api_errors = _api_records(bounded, cache, start=window_start, end=window_end, retrieved_at=started)
        unavailabilities.extend(api_errors)
        failed.extend(item.as_dict() for item in api_errors)
        rows = api_rows
        obtained += sum(1 for item in api_rows if item.get("source_document_sha256"))

    considered = len(rows)
    extract_inputs: list[dict[str, Any]] = []
    for row in rows:
        record = _row_to_record(row) if "contrato_id" in row else row
        if record.get("extra") is None and row.get("uf"):
            record["extra"] = {"uf": row.get("uf"), "municipio": row.get("municipio")}
        record.setdefault("event_effective_at", record.get("effective_at"))
        record.setdefault("source_published_at", record.get("observed_at"))
        extra = dict(record.get("extra") or {})
        extract_inputs.append({**record, **extra})
        portal_url = extra.get("portal_url")
        if fetch_pages and portal_url:
            fetched = fetch_official(str(portal_url), cache_dir=cache)
            if fetched.ok and fetched.body:
                obtained += 1
                page_identity = {
                    "source_system": record.get("source_system"),
                    "source_kind": "official_page",
                    "official_url": portal_url,
                    "source_document_id": f"{record.get('source_document_id')}:page",
                    "source_document_sha256": fetched.sha256,
                    "contract_identifier": record.get("contract_identifier"),
                    "contracting_entity_identifier": record.get("contracting_entity_identifier"),
                    "supplier_identifier": record.get("supplier_identifier"),
                    "retrieved_at": started,
                    "verified_at": started,
                    "locator": {"section": "official-page"},
                    "html": fetched.body,
                    "extra": extra,
                }
                page_result = extract_record(page_identity)
                observations.extend(page_result.observations)
                unavailabilities.extend(page_result.unavailabilities)
            else:
                failed.append(
                    (
                        fetched.unavailability
                        or SourceUnavailability(official_url=str(portal_url), error_kind="unavailable")
                    ).as_dict()
                )
                unavailabilities.append(
                    fetched.unavailability
                    or SourceUnavailability(official_url=str(portal_url), error_kind="unavailable")
                )

    row_result = extract_payload(extract_inputs)
    observations.extend(row_result.observations)
    unavailabilities.extend(row_result.unavailabilities)
    reconciled = reconcile(observations)

    replay = build_replay_command(
        limit=bounded,
        as_of=stamp,
        out_dir=out_dir,
        cache_dir=cache_dir,
        fetch_pages=fetch_pages,
        start_date=window_start,
        end_date=window_end,
    )
    artifact_sha256: dict[str, str] = {}
    if out_dir is not None:
        out = Path(out_dir)
        artifact_sha256["live-observations.jsonl"] = write_jsonl(
            out / "live-observations.jsonl", [item.as_dict() for item in reconciled]
        )
    manifest: dict[str, Any] = {
        "schema": "official-contract-semantics-live-manifest/1.1",
        "live_version": LIVE_VERSION,
        "user_agent": USER_AGENT,
        "started_at": started,
        "finished_at": _now(),
        "as_of": stamp,
        "period": {"start": window_start, "end": window_end, "uf": "SC"},
        "limit": bounded,
        "sources": sources_used,
        "commands": [replay],
        "replay_command": replay,
        "documents_considered": considered,
        "documents_obtained": obtained,
        "documents_failed": len(failed),
        "failures": failed,
        "unavailabilities": [item.as_dict() if hasattr(item, "as_dict") else item for item in unavailabilities],
        "valid_observations": len(reconciled),
        "production_write": False,
        "backfill": False,
        "inferred_from_absence": False,
        "official_live": obtained > 0,
        "note": "unavailability is recorded as unavailability, never as absence of a fact",
        "artifact_sha256": artifact_sha256,
    }
    manifest["content_hash"] = content_hash({key: value for key, value in manifest.items() if key != "content_hash"})
    if out_dir is not None:
        man_path = Path(out_dir) / "live-manifest.json"
        manifest_file_sha256 = write_json(man_path, manifest)
        manifest["manifest_file_sha256"] = manifest_file_sha256
    manifest["observations"] = [item.as_dict() for item in reconciled]
    return manifest
