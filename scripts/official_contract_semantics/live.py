"""Small read-only SC window. Unavailability is unavailability, never absence of a fact."""

from __future__ import annotations

import os
from datetime import UTC, datetime
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


def _api_records(limit: int, cache_dir: Path | None) -> tuple[list[dict[str, Any]], list[SourceUnavailability]]:
    url = PNCP_API_URL.format(start="20260701", end="20260707")
    fetched = fetch_official(url, cache_dir=cache_dir)
    if not fetched.ok or not fetched.body:
        return [], [fetched.unavailability] if fetched.unavailability else [
            SourceUnavailability(official_url=url, error_kind="unavailable", message="empty_body")
        ]
    try:
        payload = __import__("json").loads(fetched.body)
    except ValueError as exc:
        return [], [SourceUnavailability(official_url=url, error_kind="parser_error", message=str(exc))]
    data = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(data, list):
        return [], [SourceUnavailability(official_url=url, error_kind="unexpected_shape", message="data_not_list")]
    records: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        contrato_id = str(
            item.get("numeroControlePncp") or item.get("numeroControlePNCP") or item.get("numeroContratoEmpenho") or ""
        )
        unidade = item.get("unidadeOrgao") if isinstance(item.get("unidadeOrgao"), dict) else {}
        uf = str(item.get("uf") or item.get("siglaUf") or unidade.get("ufSigla") or unidade.get("uf") or "")
        if uf.upper() not in {"SC", "SANTA CATARINA"}:
            continue
        records.append(
            {
                "source_system": "pncp",
                "source_kind": "contract",
                "official_url": PNCP_CONTRACT_URL.format(contrato_id=contrato_id) if contrato_id else url,
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
                "extra": {
                    "uf": "SC",
                    "municipio": item.get("nomeUnidade") or unidade.get("municipioNome") or item.get("municipio"),
                },
            }
        )
        if len(records) >= limit:
            break
    return records, []


def run_live_readonly(
    *,
    dsn: str | None = None,
    limit: int = DEFAULT_LIVE_LIMIT,
    out_dir: str | Path | None = None,
    cache_dir: str | Path | None = None,
    fetch_pages: bool = True,
    as_of: str | None = None,
) -> dict[str, Any]:
    bounded = max(1, min(int(limit), MAX_LIVE_LIMIT))
    started = _now()
    stamp = as_of or started
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
        api_rows, api_errors = _api_records(bounded, cache)
        unavailabilities.extend(api_errors)
        failed.extend(item.as_dict() for item in api_errors)
        rows = api_rows

    considered = len(rows)
    extract_inputs: list[dict[str, Any]] = []
    for row in rows:
        record = _row_to_record(row) if "contrato_id" in row else row
        if record.get("extra") is None and row.get("uf"):
            record["extra"] = {"uf": row.get("uf"), "municipio": row.get("municipio")}
        extract_inputs.append({**record, **(record.get("extra") or {})})
        url = record.get("official_url")
        if fetch_pages and url:
            fetched = fetch_official(str(url), cache_dir=cache)
            if fetched.ok and fetched.body:
                obtained += 1
                page_identity = {
                    **record,
                    "source_kind": "official_page",
                    "source_document_id": f"{record.get('source_document_id')}:page",
                    "source_document_sha256": fetched.sha256,
                    "html": fetched.body,
                }
                page_result = extract_record(page_identity)
                observations.extend(page_result.observations)
                unavailabilities.extend(page_result.unavailabilities)
            else:
                failed.append(
                    (
                        fetched.unavailability or SourceUnavailability(official_url=str(url), error_kind="unavailable")
                    ).as_dict()
                )
                unavailabilities.append(
                    fetched.unavailability or SourceUnavailability(official_url=str(url), error_kind="unavailable")
                )
        else:
            obtained += 1

    row_result = extract_payload(extract_inputs)
    observations.extend(row_result.observations)
    unavailabilities.extend(row_result.unavailabilities)
    reconciled = reconcile(observations)

    commands = [f"python3 -m scripts.official_contract_semantics live-readonly --limit {bounded} --as-of {stamp}"]
    manifest: dict[str, Any] = {
        "schema": "official-contract-semantics-live-manifest/1.0",
        "live_version": LIVE_VERSION,
        "user_agent": USER_AGENT,
        "started_at": started,
        "finished_at": _now(),
        "as_of": stamp,
        "period": {"start": "2026-07-01", "end": "2026-07-07", "uf": "SC"},
        "limit": bounded,
        "sources": sources_used,
        "commands": commands,
        "documents_considered": considered,
        "documents_obtained": obtained,
        "documents_failed": len(failed),
        "failures": failed,
        "unavailabilities": [item.as_dict() if hasattr(item, "as_dict") else item for item in unavailabilities],
        "valid_observations": len(reconciled),
        "production_write": False,
        "backfill": False,
        "inferred_from_absence": False,
        "note": "unavailability is recorded as unavailability, never as absence of a fact",
    }
    if out_dir is not None:
        out = Path(out_dir)
        obs_path = out / "live-observations.jsonl"
        man_path = out / "live-manifest.json"
        obs_hash = write_jsonl(obs_path, [item.as_dict() for item in reconciled])
        manifest["artifact_sha256"] = {
            "live-observations.jsonl": obs_hash,
        }
        manifest["replay_command"] = commands[0] + f" --out {out}"
        man_hash = write_json(man_path, manifest)
        manifest["artifact_sha256"]["live-manifest.json"] = man_hash
        write_json(man_path, manifest)
    manifest["content_hash"] = content_hash({key: value for key, value in manifest.items() if key != "content_hash"})
    manifest["observations"] = [item.as_dict() for item in reconciled]
    return manifest
