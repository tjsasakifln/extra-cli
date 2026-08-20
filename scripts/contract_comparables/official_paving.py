"""Official-live paving canary adapter. Feeds the existing #415 engine.

Source order: SELECT-only snapshot → bounded PNCP consulta → official contract JSON.
Does not invent SQL semantic columns and does not open a second comparables engine.
Fixture bytes are never labeled official_live.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any

from scripts.contract_comparables.constants import (
    CATALOG_LIVE_CANDIDATE,
    CONSUMER_WEB_CFG,
    DERIVATION_UNIT_FROM_OFFICIAL_TOTAL,
    FOCAL_CANARY_CONTRACT_ID,
    LIVE_MISSING_SEMANTIC_COLUMNS,
    LIVE_PAVING_CANARY_ID,
    LIVE_PAVING_ENVELOPE_SCHEMA,
    METRIC_NOMINAL_TOTAL,
    MIN_TYPOLOGY_CONFIDENCE,
    MIN_USABLE_N_COMPARABLE,
    OFFICIAL_LIVE,
    PAVING_FAMILY_ASFALTICO,
    PAVING_FAMILY_CBUQ,
    PAVING_FAMILY_GENERIC,
    PAVING_FAMILY_PARALELEPIPEDO,
    PAVING_FAMILY_RECAPEAMENTO,
    PAVING_FAMILY_TSD,
    PRODUCER_EXTRA_CLI,
    QUESTION,
    QUESTION_ID,
    REASON_AREA_MISSING,
    REASON_CNPJ_IN_MUNICIPIO,
    REASON_CONFLICTING_OFFICIAL_VALUES,
    REASON_CONSULTA_CNPJ_ORGAO,
    REASON_DSN_UNAVAILABLE,
    REASON_FIXTURE_LABELED_LIVE,
    REASON_GRAIN_MISMATCH,
    REASON_IDENTITY_SWAP,
    REASON_INVERTED_DATES,
    REASON_LIVE_COLUMNS,
    REASON_NATIONALIZED_STATE_SAMPLE,
    REASON_PAVING_FAMILY_MISMATCH,
    REASON_PHYSICAL_UNIT,
    REASON_PNCP_UNAVAILABLE,
    REASON_REGIME_UNPUBLISHED,
    REASON_STALE_HASH,
    REASON_UNIT_FROM_OFFICIAL_TOTAL,
    REASON_ZERO_FROM_MISSING,
    STATUS_BLOCKED,
    STATUS_COMPARABLE,
    STATUS_HOLD,
    STATUS_NOT,
    UNIT_CANONICAL,
    VALUE_SEMANTIC_CANONICAL,
)
from scripts.contract_comparables.engine import build_peer_group, groups_changed_by_rectification
from scripts.contract_comparables.live import resolve_dsn
from scripts.contract_comparables.models import PeerRequest, RectificationEvent
from scripts.contract_comparables.normalize import classify_typology, fold_text, records_from_mappings
from scripts.contract_comparables.official_canary import (
    blocked_envelope,
    requested_physical_unit_metric,
    same_uf_stratum,
)
from scripts.contract_comparables.serialize import content_hash_for, fold_for_scan
from scripts.historical_contract_authority.official_live import parse_pncp_contrato_id
from scripts.official_contract_semantics.constants import CONSULTA_PAGE_SIZE, MAX_CONSULTA_PAGES
from scripts.official_contract_semantics.export_comparables import observation_to_contract_record
from scripts.official_contract_semantics.extract import extract_record
from scripts.official_contract_semantics.http_client import fetch_official
from scripts.official_contract_semantics.live import (
    default_live_window,
    pncp_ymd,
    records_from_consulta_listing,
)
from scripts.official_contract_semantics.reconcile import reconcile

DEFAULT_AS_OF = "2026-08-19"
DEFAULT_WINDOW_DAYS = 60
DEFAULT_LIMIT = 200
DEFAULT_CONSULTA_PAGES = 8
CONSULTA_TIMEOUT_S = 30.0
PNCP_API_CONTRACT = "https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/contratos/{ano}/{seq}"
PNCP_CONSULTA_COMPRA = "https://pncp.gov.br/api/consulta/v1/orgaos/{cnpj}/compras/{ano}/{seq}"
OFFICIAL_TOTAL_SEMANTICS = frozenset({"valor_global", "valor_contratado", "valor_integral_nominal"})
CNPJ_DIGITS = re.compile(r"^\d{14}$")
AREA_M2 = re.compile(
    r"(\d{1,3}(?:\.\d{3})*,\d+|\d+(?:[.,]\d+)?)\s*m(?:²|2)\b",
    re.IGNORECASE,
)
ATA_GRAIN_MARKERS = ("ata de registro", "ata registro", "registro de precos", "registro de preços")
ITEM_GRAIN_KEYS = ("lot_identifier", "item_identifier", "lote", "item")
ZERO_COERCION_SENTINELS = frozenset({"0", "0.0", "0.00", "NOT_APPLICABLE", "N/A", "NA"})
CLAIM_SCOPE_PI_PAVING = (
    "valor_integral_nominal of official paving contracts in the focal UF, grain=contrato; "
    "not a national ranking and not a physical-unit price"
)

_ENVELOPE_HASH_SKIP = frozenset(
    {
        "content_hash",
        "refresh_latency_ms",
        "per_group_ms",
        "generated_at",
        "retrieved_at",
        "verified_at",
        "unavailabilities",
        "handoff_dir",
    }
)


def documented_area_m2(objeto: str | None) -> Decimal | None:
    """Return area only when the official object text states m². Never invent."""
    if not objeto:
        return None
    match = AREA_M2.search(objeto)
    if not match:
        return None
    raw = match.group(1).strip()
    if "," in raw:
        normalized = raw.replace(".", "").replace(",", ".")
    else:
        normalized = raw
    try:
        value = Decimal(normalized)
    except (InvalidOperation, ValueError):
        return None
    if value <= 0:
        return None
    return value


def is_paving_text(text: str | None) -> bool:
    typology, confidence, _scope = classify_typology(str(text or ""))
    return typology == "pavimentacao" and confidence >= MIN_TYPOLOGY_CONFIDENCE


def paving_family(text: str | None) -> str:
    """Documented keyword family. Not embeddings. Used only after typology=pavimentacao."""
    folded = fold_text(text)
    if "paralelep" in folded or "piso intertrav" in folded:
        return PAVING_FAMILY_PARALELEPIPEDO
    if "cbuq" in folded or "concreto betuminoso" in folded:
        return PAVING_FAMILY_CBUQ
    if "tsd" in folded or "tratamento superficial" in folded:
        return PAVING_FAMILY_TSD
    if "recapeamento" in folded or "tapa buraco" in folded or "tapa-buraco" in folded:
        return PAVING_FAMILY_RECAPEAMENTO
    if "asfalt" in folded:
        return PAVING_FAMILY_ASFALTICO
    return PAVING_FAMILY_GENERIC


def same_paving_family_stratum(mappings: list[dict[str, Any]], focal_id: str) -> list[dict[str, Any]]:
    focal = next((item for item in mappings if str(item.get("contract_id")) == focal_id), None)
    if focal is None:
        return mappings
    family = paving_family(str(focal.get("objeto") or focal.get("object_text") or ""))
    kept: list[dict[str, Any]] = []
    for item in mappings:
        item_family = paving_family(str(item.get("objeto") or item.get("object_text") or ""))
        row = {**item, "paving_family": item_family}
        if str(item.get("contract_id")) == focal_id or item_family == family:
            kept.append(row)
    return kept


def consulta_contratos_url(
    *,
    start: str,
    end: str,
    page: int,
    page_size: int,
    cnpj_orgao: str | None = None,
) -> str:
    url = (
        "https://pncp.gov.br/api/consulta/v1/contratos"
        f"?dataInicial={pncp_ymd(start)}&dataFinal={pncp_ymd(end)}"
        f"&pagina={int(page)}&tamanhoPagina={int(page_size)}"
    )
    if cnpj_orgao:
        url += f"&cnpjOrgao={cnpj_orgao}"
    return url


def parse_compra_control(control: str | None) -> tuple[str, str, str] | None:
    parsed = parse_pncp_contrato_id(str(control or ""))
    if parsed is None:
        return None
    return parsed


def compra_ids_from_listing_body(body: str) -> dict[str, str]:
    payload = json.loads(body)
    items = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        items = [payload] if isinstance(payload, dict) else []
    mapping: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        contract_id = str(item.get("numeroControlePNCP") or item.get("numeroControlePncp") or "")
        compra_id = str(item.get("numeroControlePncpCompra") or "")
        if contract_id and compra_id:
            mapping[contract_id] = compra_id
    return mapping


def apply_instrument_total_semantics(mapping: dict[str, Any]) -> dict[str, Any]:
    """Map official valorGlobal/valor_contratado to instrument-total unit. Not km/m2."""
    row = dict(mapping)
    source = str(row.get("extra_value_semantic_source") or row.get("valor_semantic") or "")
    if source in OFFICIAL_TOTAL_SEMANTICS and row.get("valor") not in {None, ""}:
        row["unidade"] = UNIT_CANONICAL
        row["valor_semantic"] = VALUE_SEMANTIC_CANONICAL
        row["extra_unit_derivation"] = DERIVATION_UNIT_FROM_OFFICIAL_TOTAL
    return row


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def adapter_refusals(mapping: dict[str, Any]) -> tuple[str, ...]:
    """Fail-closed checks the engine does not own (identity, grain, dates, coercion)."""
    reasons: list[str] = []
    municipio = str(mapping.get("municipio") or "")
    municipio_digits = _digits(municipio)
    if CNPJ_DIGITS.match(municipio_digits):
        reasons.append(REASON_CNPJ_IN_MUNICIPIO)
        reasons.append(REASON_IDENTITY_SWAP)
    orgao = str(mapping.get("orgao_id") or mapping.get("contracting_entity_identifier") or "")
    if orgao and not CNPJ_DIGITS.match(_digits(orgao)) and CNPJ_DIGITS.match(municipio_digits):
        reasons.append(REASON_IDENTITY_SWAP)
    start = str(mapping.get("period_start") or mapping.get("data_inicio") or "")[:10]
    end = str(mapping.get("period_end") or mapping.get("data_fim") or "")[:10]
    if start and end and len(start) == 10 and len(end) == 10 and start > end:
        reasons.append(REASON_INVERTED_DATES)
    grain = fold_for_scan(str(mapping.get("source_kind") or mapping.get("grain") or "contract"))
    objeto = fold_for_scan(str(mapping.get("objeto") or mapping.get("object_text") or ""))
    if grain in {"ata", "empenho", "lote", "item", "aditivo"} or any(token in objeto for token in ATA_GRAIN_MARKERS):
        reasons.append(REASON_GRAIN_MISMATCH)
    if any(mapping.get(key) not in {None, ""} for key in ITEM_GRAIN_KEYS):
        reasons.append(REASON_GRAIN_MISMATCH)
    extra_status = str(mapping.get("extra_status") or "")
    if extra_status == "conflicted":
        reasons.append(REASON_CONFLICTING_OFFICIAL_VALUES)
    for field in ("valor", "quantidade"):
        raw = mapping.get(field)
        if mapping.get(f"{field}_is_unknown") and str(raw) in ZERO_COERCION_SENTINELS:
            reasons.append(REASON_ZERO_FROM_MISSING)
        if mapping.get(f"{field}_missing_coerced"):
            reasons.append(REASON_ZERO_FROM_MISSING)
    catalog = str(mapping.get("catalog_mode") or "")
    source = fold_for_scan(str(mapping.get("source") or ""))
    if catalog == OFFICIAL_LIVE and ("fixture" in source or source == "fixture"):
        reasons.append(REASON_FIXTURE_LABELED_LIVE)
    return tuple(dict.fromkeys(reasons))


def wrap_pncp_body(body: str) -> str:
    payload = json.loads(body)
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return body
    if isinstance(payload, dict):
        return json.dumps({"data": [payload]}, ensure_ascii=False)
    if isinstance(payload, list):
        return json.dumps({"data": payload}, ensure_ascii=False)
    raise ValueError("unexpected_pncp_shape")


def listing_records_from_fetch(
    *,
    url: str,
    body: str,
    sha256: str,
    retrieved_at: str,
    uf_filter: str | None = None,
) -> tuple[list[dict[str, Any]], list[Any]]:
    listing_body = wrap_pncp_body(body)
    rows, errors, _saw = records_from_consulta_listing(
        listing_url=url,
        listing_body=listing_body,
        listing_sha256=sha256,
        retrieved_at=retrieved_at,
        limit=10**6,
        uf_filter=uf_filter,
    )
    return rows, list(errors)


def fetch_consulta_paving(
    *,
    start: str,
    end: str,
    retrieved_at: str,
    max_pages: int = DEFAULT_CONSULTA_PAGES,
    page_size: int = CONSULTA_PAGE_SIZE,
    scan_limit: int = DEFAULT_LIMIT,
    opener: Callable[..., object] | None = None,
    sleeper: Callable[[float], None] | None = None,
    rate_limit_s: float = 0.0,
    retries: int = 2,
    cache_dir: Any = None,
    cnpj_orgao: str | None = None,
    timeout_s: float = CONSULTA_TIMEOUT_S,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    compra_by_contract: dict[str, str] = {}
    pages = min(max(1, max_pages), MAX_CONSULTA_PAGES)
    for page in range(1, pages + 1):
        if len(records) >= scan_limit:
            break
        url = consulta_contratos_url(
            start=start,
            end=end,
            page=page,
            page_size=page_size,
            cnpj_orgao=cnpj_orgao,
        )
        fetched = fetch_official(
            url,
            opener=opener,
            sleeper=sleeper,
            rate_limit_s=rate_limit_s,
            retries=retries,
            cache_dir=cache_dir,
            timeout_s=timeout_s,
        )
        if not fetched.ok or not fetched.body or not fetched.sha256:
            unavailable = fetched.unavailability
            errors.append(
                unavailable.as_dict()
                if unavailable
                else {"official_url": url, "error_kind": "unavailable", "message": "empty_body"}
            )
            break
        compra_by_contract.update(compra_ids_from_listing_body(fetched.body))
        rows, page_errors = listing_records_from_fetch(
            url=url,
            body=fetched.body,
            sha256=fetched.sha256,
            retrieved_at=retrieved_at,
            uf_filter=None,
        )
        errors.extend(item.as_dict() if hasattr(item, "as_dict") else dict(item) for item in page_errors)
        paving = [row for row in rows if is_paving_text(str(row.get("object_text") or ""))]
        remaining = scan_limit - len(records)
        records.extend(paving[:remaining])
        if not rows:
            break
        if cnpj_orgao and not rows:
            break
    return records, errors, compra_by_contract


def fetch_linked_compra(
    compra_id: str,
    *,
    opener: Callable[..., object] | None = None,
    sleeper: Callable[[float], None] | None = None,
    rate_limit_s: float = 0.0,
    retries: int = 1,
    cache_dir: Any = None,
    timeout_s: float = CONSULTA_TIMEOUT_S,
) -> dict[str, Any]:
    parsed = parse_compra_control(compra_id)
    if parsed is None:
        return {"ok": False, "reason": "unparseable_compra_id", "compra_id": compra_id}
    cnpj, ano, seq = parsed
    url = PNCP_CONSULTA_COMPRA.format(cnpj=cnpj, ano=ano, seq=seq)
    fetched = fetch_official(
        url,
        opener=opener,
        sleeper=sleeper,
        rate_limit_s=rate_limit_s,
        retries=retries,
        cache_dir=cache_dir,
        timeout_s=timeout_s,
    )
    if not fetched.ok or not fetched.body:
        unavailable = fetched.unavailability
        return {
            "ok": False,
            "url": url,
            "reason": unavailable.error_kind if unavailable else "unavailable",
            "compra_id": compra_id,
        }
    try:
        payload = json.loads(fetched.body)
    except json.JSONDecodeError:
        return {"ok": False, "url": url, "reason": "parser_error", "compra_id": compra_id}
    if not isinstance(payload, dict):
        return {"ok": False, "url": url, "reason": "unexpected_shape", "compra_id": compra_id}
    return {
        "ok": True,
        "url": url,
        "compra_id": compra_id,
        "sha256": fetched.sha256,
        "modalidade": payload.get("modalidadeNome"),
        "modalidade_id": payload.get("modalidadeId"),
        "objeto": payload.get("objetoCompra"),
    }


def fetch_focal_contract(
    contract_id: str,
    *,
    retrieved_at: str,
    opener: Callable[..., object] | None = None,
    sleeper: Callable[[float], None] | None = None,
    rate_limit_s: float = 0.0,
    retries: int = 2,
    cache_dir: Any = None,
) -> dict[str, Any]:
    parsed = parse_pncp_contrato_id(contract_id)
    if parsed is None:
        return {"ok": False, "reason": "unparseable_contract_id", "contract_id": contract_id}
    cnpj, ano, seq = parsed
    url = PNCP_API_CONTRACT.format(cnpj=cnpj, ano=ano, seq=seq)
    fetched = fetch_official(
        url,
        opener=opener,
        sleeper=sleeper,
        rate_limit_s=rate_limit_s,
        retries=retries,
        cache_dir=cache_dir,
        timeout_s=CONSULTA_TIMEOUT_S,
    )
    if not fetched.ok or not fetched.body or not fetched.sha256:
        unavailable = fetched.unavailability
        return {
            "ok": False,
            "url": url,
            "reason": unavailable.error_kind if unavailable else "unavailable",
            "detail": unavailable.as_dict() if unavailable else {"message": "empty_body"},
        }
    rows, errors = listing_records_from_fetch(
        url=url,
        body=fetched.body,
        sha256=fetched.sha256,
        retrieved_at=retrieved_at,
        uf_filter=None,
    )
    if errors or not rows:
        return {"ok": False, "url": url, "reason": "parser_error", "detail": errors, "sha256": fetched.sha256}
    row = rows[0]
    row["official_url"] = url
    row["source_document_sha256"] = fetched.sha256
    row["locator"] = {"json_path": "$.valorGlobal"}
    return {
        "ok": True,
        "url": url,
        "sha256": fetched.sha256,
        "status": fetched.status,
        "record": row,
        "bytes": len(fetched.body.encode("utf-8")),
    }


def observations_from_records(records: list[dict[str, Any]]) -> tuple[Any, ...]:
    extracted = []
    for record in records:
        result = extract_record(record, default_source="pncp")
        extracted.extend(result.observations)
    return reconcile(tuple(extracted))


def mappings_from_observations(observations: tuple[Any, ...]) -> list[dict[str, Any]]:
    mappings: list[dict[str, Any]] = []
    for item in observations:
        row = observation_to_contract_record(item)
        extra = item.extra or {}
        if not row.get("uf"):
            row["uf"] = extra.get("uf")
        if not row.get("municipio"):
            row["municipio"] = extra.get("municipio")
        row["object_text"] = item.object_text
        row["period_start"] = item.period_start
        row["period_end"] = item.period_end
        row["source_kind"] = item.source_kind
        row["catalog_mode"] = CATALOG_LIVE_CANDIDATE
        row["documented_area_m2"] = (
            str(documented_area_m2(item.object_text)) if documented_area_m2(item.object_text) else None
        )
        mappings.append(apply_instrument_total_semantics(row))
    return mappings


def dsn_records_to_extract(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    extract_inputs: list[dict[str, Any]] = []
    for row in rows:
        contract_id = str(row.get("contract_id") or "")
        extract_inputs.append(
            {
                "source_system": "pncp_supplier_contracts",
                "source_kind": "contract",
                "official_url": f"postgresql://local/pncp_supplier_contracts#{contract_id}",
                "source_document_id": contract_id,
                "contract_identifier": contract_id,
                "contracting_entity_identifier": row.get("orgao_id"),
                "supplier_identifier": row.get("fornecedor_id"),
                "object_text": row.get("objeto"),
                "valor_total": row.get("valor"),
                "period_start": row.get("data_referencia"),
                "observed_at": row.get("data_referencia"),
                "uf": row.get("uf"),
                "municipio": row.get("municipio"),
                "extra": {"uf": row.get("uf"), "municipio": row.get("municipio")},
            }
        )
    return extract_inputs


def brl_m2_block(focal: dict[str, Any], peers: list[dict[str, Any]]) -> dict[str, Any]:
    """Emit BRL/m² only when target and every used peer have documented area."""
    used = [focal, *peers]
    missing = [str(item.get("contract_id")) for item in used if not documented_area_m2(str(item.get("objeto") or item.get("object_text") or ""))]
    if missing:
        return {
            "emitted": False,
            "reason_codes": [REASON_AREA_MISSING, REASON_PHYSICAL_UNIT],
            "missing_contract_ids": missing,
        }
    areas: list[dict[str, str]] = []
    for item in used:
        area = documented_area_m2(str(item.get("objeto") or item.get("object_text") or ""))
        valor = item.get("valor")
        if area is None or valor in {None, ""}:
            return {
                "emitted": False,
                "reason_codes": [REASON_AREA_MISSING, REASON_PHYSICAL_UNIT],
                "missing_contract_ids": [str(item.get("contract_id"))],
            }
        unit = (Decimal(str(valor)) / area).quantize(Decimal("0.0001"))
        areas.append(
            {
                "contract_id": str(item.get("contract_id")),
                "area_m2": format(area, "f"),
                "brl_per_m2": format(unit, "f"),
            }
        )
    return {"emitted": True, "unit": "BRL/m2", "rows": areas, "reason_codes": []}


def _probe_dsn(dsn: str | None, limit: int) -> dict[str, Any]:
    from scripts.contract_comparables.official_canary import _probe_live

    resolved = resolve_dsn(dsn)
    if not resolved:
        return {"available": False, "reason": REASON_DSN_UNAVAILABLE, "mappings": []}
    probe = _probe_live(dsn=resolved, limit=limit)
    if probe.get("blocked"):
        return {
            "available": False,
            "reason": ",".join(str(item) for item in probe.get("reason_codes") or ()),
            "detail": probe.get("detail"),
            "mappings": [],
        }
    return {
        "available": True,
        "mappings": list(probe.get("mappings") or []),
        "missing": list(probe.get("missing") or []),
        "official": list(probe.get("official") or []),
        "active_n": probe.get("active_n"),
    }


def envelope_hashable(payload: dict[str, Any]) -> dict[str, Any]:
    copy: dict[str, Any] = {}
    for key, value in payload.items():
        if key in _ENVELOPE_HASH_SKIP:
            continue
        if key == "observability" and isinstance(value, dict):
            copy[key] = {obs_key: obs_value for obs_key, obs_value in value.items() if obs_key not in _ENVELOPE_HASH_SKIP}
            continue
        if key == "live" and isinstance(value, dict):
            copy[key] = {
                live_key: live_value
                for live_key, live_value in value.items()
                if live_key not in _ENVELOPE_HASH_SKIP and live_key != "focal_sha256"
            }
            continue
        if key == "evidence_refs" and isinstance(value, list):
            copy[key] = [
                {ref_key: ref_value for ref_key, ref_value in item.items() if ref_key != "sha256"}
                if isinstance(item, dict)
                else item
                for item in value
            ]
            continue
        copy[key] = value
    return copy


def stabilize_evidence_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for item in refs:
        if not isinstance(item, dict):
            continue
        key = (str(item.get("source_kind") or "contract"), str(item.get("contract_id") or ""))
        locator = item.get("locator") if isinstance(item.get("locator"), dict) else {}
        unique[key] = {
            "contract_id": item.get("contract_id"),
            "url": item.get("url"),
            "sha256": item.get("sha256"),
            "locator": {"json_path": locator.get("json_path") or "$.valorGlobal"},
            "source_kind": item.get("source_kind") or "contract",
        }
    return [unique[key] for key in sorted(unique)]


def attach_live_hash(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("evidence_refs"), list):
        payload["evidence_refs"] = stabilize_evidence_refs(payload["evidence_refs"])
    payload["content_hash"] = content_hash_for(envelope_hashable(payload))
    return payload


def replay_command(
    *,
    focal_id: str,
    as_of: str,
    start: str,
    end: str,
    limit: int,
    output: str | None,
) -> str:
    parts = [
        "python3 -m scripts.contract_comparables live-paving-handoff",
        f"--focal {focal_id}",
        f"--as-of {as_of}",
        f"--start-date {start}",
        f"--end-date {end}",
        f"--limit {int(limit)}",
        "--metric valor_integral_nominal",
    ]
    if output:
        parts.append(f"--output {output}")
    return " ".join(parts)


def run_live_paving_canary(
    *,
    dsn: str | None = None,
    focal_id: str | None = None,
    as_of: str = DEFAULT_AS_OF,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = DEFAULT_LIMIT,
    metric: str = METRIC_NOMINAL_TOTAL,
    max_pages: int = DEFAULT_CONSULTA_PAGES,
    opener: Callable[..., object] | None = None,
    sleeper: Callable[[float], None] | None = None,
    rate_limit_s: float = 1.0,
    retries: int = 2,
    cache_dir: Any = None,
    national_claim_authorized: bool = False,
    producer_sha: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    retrieved_at = as_of if "T" in as_of else f"{as_of}T00:00:00Z"
    focal = focal_id or FOCAL_CANARY_CONTRACT_ID
    window_start, window_end = default_live_window(
        start=start_date,
        end=end_date,
        as_of=as_of,
        days=DEFAULT_WINDOW_DAYS,
    )
    if requested_physical_unit_metric(metric) and fold_for_scan(metric) not in {
        fold_for_scan("cost_per_m2"),
        fold_for_scan("custo_por_m2"),
        fold_for_scan("custo/m2"),
        fold_for_scan("brl/m2"),
        fold_for_scan("brl_per_m2"),
    }:
        payload = blocked_envelope(
            reason_codes=(REASON_PHYSICAL_UNIT,),
            prerequisite="Documentary quantity, physical unit, scope and sample before custo/km.",
            next_command=replay_command(
                focal_id=focal, as_of=as_of, start=window_start, end=window_end, limit=limit, output=None
            ),
            as_of=as_of,
            metric=metric,
        )
        payload["schema"] = LIVE_PAVING_ENVELOPE_SCHEMA
        payload["status"] = STATUS_HOLD
        payload["official_live"] = False
        payload["canary_id"] = LIVE_PAVING_CANARY_ID
        payload["observability"]["refresh_latency_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
        return attach_live_hash(payload)

    dsn_probe = _probe_dsn(dsn, limit)
    dsn_available = bool(dsn_probe.get("available"))
    source_kind = "none"
    official_live = False
    extract_rows: list[dict[str, Any]] = []
    unavailabilities: list[dict[str, Any]] = []
    evidence_refs: list[dict[str, Any]] = []
    consulta_found = 0

    if dsn_available and dsn_probe.get("mappings"):
        source_kind = "pncp_supplier_contracts"
        extract_rows = dsn_records_to_extract(list(dsn_probe["mappings"]))
        official_live = False

    focal_fetch = fetch_focal_contract(
        focal,
        retrieved_at=retrieved_at,
        opener=opener,
        sleeper=sleeper,
        rate_limit_s=rate_limit_s,
        retries=retries,
        cache_dir=cache_dir,
    )
    if focal_fetch.get("ok"):
        official_live = True
        source_kind = "pncp_contrato_api" if source_kind == "none" else f"{source_kind}+pncp_contrato_api"
        evidence_refs.append(
            {
                "contract_id": focal,
                "url": focal_fetch["url"],
                "sha256": focal_fetch["sha256"],
                "locator": {"json_path": "$.valorGlobal"},
                "source_kind": "contract",
            }
        )
        extract_rows = [row for row in extract_rows if str(row.get("contract_identifier")) != focal]
        extract_rows.insert(0, focal_fetch["record"])

    parsed_focal = parse_pncp_contrato_id(focal)
    cnpj_orgao = parsed_focal[0] if parsed_focal else None
    compra_by_contract: dict[str, str] = {}
    if not dsn_available or not extract_rows or len(extract_rows) < 2 or cnpj_orgao:
        consulta_rows, consulta_errors, compra_by_contract = fetch_consulta_paving(
            start=window_start,
            end=window_end,
            retrieved_at=retrieved_at,
            max_pages=max_pages,
            scan_limit=limit,
            opener=opener,
            sleeper=sleeper,
            rate_limit_s=rate_limit_s,
            retries=retries,
            cache_dir=cache_dir,
            cnpj_orgao=cnpj_orgao,
            timeout_s=CONSULTA_TIMEOUT_S,
        )
        unavailabilities.extend(consulta_errors)
        consulta_found = len(consulta_rows)
        if consulta_rows:
            if "pncp_consulta_api" not in source_kind:
                source_kind = (
                    "pncp_consulta_api" if source_kind in {"none", "pncp_contrato_api"} else f"{source_kind}+pncp_consulta_api"
                )
            official_live = True
            known = {str(row.get("contract_identifier") or row.get("source_document_id")) for row in extract_rows}
            for row in consulta_rows:
                cid = str(row.get("contract_identifier") or "")
                if cid and cid not in known:
                    extract_rows.append(row)
                    known.add(cid)
            for row in sorted(
                consulta_rows,
                key=lambda item: str(item.get("contract_identifier") or ""),
            ):
                cid = str(row.get("contract_identifier") or "")
                if not cid:
                    continue
                evidence_refs.append(
                    {
                        "contract_id": cid,
                        "url": row.get("official_url"),
                        "sha256": row.get("source_document_sha256"),
                        "locator": {"json_path": "$.valorGlobal"},
                        "source_kind": "contract",
                    }
                )

    if not extract_rows and not focal_fetch.get("ok"):
        payload = blocked_envelope(
            reason_codes=(REASON_PNCP_UNAVAILABLE, REASON_DSN_UNAVAILABLE),
            prerequisite="Reachable official PNCP HTTP or SELECT-only DSN with public.pncp_supplier_contracts.",
            next_command=replay_command(
                focal_id=focal, as_of=as_of, start=window_start, end=window_end, limit=limit, output=None
            ),
            as_of=as_of,
            metric=METRIC_NOMINAL_TOTAL,
            extra={
                "unavailabilities": unavailabilities,
                "focal_fetch": {key: value for key, value in focal_fetch.items() if key != "record"},
            },
        )
        payload["schema"] = LIVE_PAVING_ENVELOPE_SCHEMA
        payload["official_live"] = False
        payload["source_kind"] = source_kind
        payload["canary_id"] = LIVE_PAVING_CANARY_ID
        payload["dsn_available"] = dsn_available
        payload["observability"]["refresh_latency_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
        return attach_live_hash(payload)

    observations = observations_from_records(extract_rows)
    mappings = mappings_from_observations(observations)
    adapter_reasons: list[str] = []
    for mapping in mappings:
        adapter_reasons.extend(adapter_refusals(mapping))
    if national_claim_authorized:
        adapter_reasons.append(REASON_NATIONALIZED_STATE_SAMPLE)

    paving_mappings = [item for item in mappings if is_paving_text(str(item.get("objeto") or ""))]
    family_exclusions: list[dict[str, Any]] = []
    family_filtered = same_paving_family_stratum(paving_mappings, focal)
    family = paving_family(
        str(
            (
                next((item for item in paving_mappings if str(item.get("contract_id")) == focal), paving_mappings[0] if paving_mappings else {})
            ).get("objeto")
            or ""
        )
    )
    kept_ids = {str(item.get("contract_id")) for item in family_filtered}
    for item in paving_mappings:
        cid = str(item.get("contract_id") or "")
        if cid and cid not in kept_ids:
            family_exclusions.append(
                {
                    "contract_id": cid,
                    "reason_codes": [REASON_PAVING_FAMILY_MISMATCH],
                    "paving_family": paving_family(str(item.get("objeto") or "")),
                    "focal_family": family,
                }
            )
    paving_mappings = family_filtered
    family_exclusions.sort(key=lambda item: str(item.get("contract_id") or ""))
    compra_id = compra_by_contract.get(focal)
    if not compra_id and focal_fetch.get("ok"):
        raw_record = focal_fetch.get("record") or {}
        extra = raw_record.get("extra") if isinstance(raw_record.get("extra"), dict) else {}
        compra_id = extra.get("numeroControlePncpCompra") or raw_record.get("numeroControlePncpCompra")
    compra_fetch = (
        fetch_linked_compra(
            str(compra_id),
            opener=opener,
            sleeper=sleeper,
            rate_limit_s=rate_limit_s,
            retries=retries,
            cache_dir=cache_dir,
        )
        if compra_id
        else {"ok": False, "reason": "compra_id_absent"}
    )
    if compra_fetch.get("ok") and compra_fetch.get("modalidade"):
        for item in mappings:
            if str(item.get("contract_id")) == focal:
                item["modalidade"] = compra_fetch["modalidade"]
        for item in paving_mappings:
            if str(item.get("contract_id")) == focal:
                item["modalidade"] = compra_fetch["modalidade"]
        evidence_refs.append(
            {
                "contract_id": focal,
                "url": compra_fetch.get("url"),
                "sha256": compra_fetch.get("sha256"),
                "locator": {"json_path": "$.modalidadeNome"},
                "source_kind": "compra",
            }
        )
    total_found = len(mappings)
    total_eligible = len(paving_mappings)
    if not paving_mappings:
        payload = blocked_envelope(
            reason_codes=("official_paving_sample_empty", REASON_LIVE_COLUMNS),
            prerequisite="Official snapshot/consulta produced no paving rows under the documented keyword typology.",
            next_command=replay_command(
                focal_id=focal, as_of=as_of, start=window_start, end=window_end, limit=limit, output=None
            ),
            as_of=as_of,
            metric=METRIC_NOMINAL_TOTAL,
        )
        payload["schema"] = LIVE_PAVING_ENVELOPE_SCHEMA
        payload["official_live"] = official_live
        payload["source_kind"] = source_kind
        payload["canary_id"] = LIVE_PAVING_CANARY_ID
        payload["total_found"] = total_found
        payload["total_eligible"] = 0
        payload["total_used"] = 0
        payload["dsn_available"] = dsn_available
        payload["observability"]["refresh_latency_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
        return attach_live_hash(payload)

    stratum = same_uf_stratum(paving_mappings, focal)
    totals_mapped = all(
        item.get("unidade") == UNIT_CANONICAL and item.get("valor_semantic") == VALUE_SEMANTIC_CANONICAL
        for item in stratum
        if item.get("valor") not in {None, ""}
    ) and any(item.get("extra_unit_derivation") == DERIVATION_UNIT_FROM_OFFICIAL_TOTAL for item in stratum)
    live_semantic = bool(totals_mapped)
    request = PeerRequest(
        focal_contract_id=focal,
        as_of=as_of,
        consumer_id=CONSUMER_WEB_CFG,
        catalog_mode=CATALOG_LIVE_CANDIDATE,
        source=source_kind,
        producer_sha=producer_sha,
        live_semantic_columns_present=live_semantic,
        require_known_regime=False,
    )
    _result, document = build_peer_group(records_from_mappings(stratum), request)
    if document.get("catalog_mode") == OFFICIAL_LIVE:
        raise RuntimeError("engine document must not self-label official_live")

    merged_reasons = list(document.get("reason_codes") or [])
    merged_reasons.extend(adapter_reasons)
    if family_exclusions:
        merged_reasons.append(REASON_PAVING_FAMILY_MISMATCH)
    if not live_semantic:
        if REASON_LIVE_COLUMNS not in merged_reasons:
            merged_reasons.append(REASON_LIVE_COLUMNS)
    else:
        merged_reasons = [code for code in merged_reasons if code != REASON_LIVE_COLUMNS]
        merged_reasons.append(REASON_UNIT_FROM_OFFICIAL_TOTAL)
        merged_reasons.append(REASON_REGIME_UNPUBLISHED)
        if cnpj_orgao:
            merged_reasons.append(REASON_CONSULTA_CNPJ_ORGAO)
    unique_reasons = list(dict.fromkeys(merged_reasons))
    status = document["status"]
    if any(
        code
        in {
            REASON_IDENTITY_SWAP,
            REASON_CNPJ_IN_MUNICIPIO,
            REASON_INVERTED_DATES,
            REASON_GRAIN_MISMATCH,
            REASON_CONFLICTING_OFFICIAL_VALUES,
            REASON_FIXTURE_LABELED_LIVE,
            REASON_NATIONALIZED_STATE_SAMPLE,
            REASON_ZERO_FROM_MISSING,
        }
        for code in unique_reasons
    ):
        status = STATUS_NOT
    if status == STATUS_COMPARABLE and MIN_USABLE_N_COMPARABLE > int(document.get("usable_n") or 0):
        raise RuntimeError("COMPARABLE must not lower MIN_USABLE_N_COMPARABLE")

    used_peers = list(document.get("peers") or [])
    focal_mapping = next((item for item in paving_mappings if str(item.get("contract_id")) == focal), paving_mappings[0])
    want_m2 = fold_for_scan(metric) in {
        fold_for_scan("cost_per_m2"),
        fold_for_scan("custo/m2"),
        fold_for_scan("brl/m2"),
        fold_for_scan("brl_per_m2"),
        fold_for_scan("custo_por_m2"),
    }
    unit_metrics: dict[str, Any]
    if want_m2 or status == STATUS_COMPARABLE:
        m2_peers = used_peers or [item for item in stratum if str(item.get("contract_id")) != focal]
        unit_metrics = brl_m2_block(focal_mapping, m2_peers)
        if want_m2 and not unit_metrics.get("emitted"):
            status = STATUS_HOLD if status == STATUS_COMPARABLE else status
            unique_reasons = list(dict.fromkeys([*unique_reasons, *unit_metrics.get("reason_codes", [])]))
        if status != STATUS_COMPARABLE:
            withheld_codes = list(
                dict.fromkeys([*(unit_metrics.get("reason_codes") or []), REASON_PHYSICAL_UNIT])
            )
            unit_metrics = {
                "emitted": False,
                "reason_codes": withheld_codes,
                "note": "BRL/m2 withheld unless COMPARABLE and every used peer has documented area.",
            }
    else:
        unit_metrics = {
            "emitted": False,
            "reason_codes": [],
            "note": "Primary metric is valor_integral_nominal. BRL/m2 is not emitted.",
        }

    late_ids = sorted({str(item.get("contract_id")) for item in stratum if item.get("contract_id")})
    late: dict[str, Any]
    if len(late_ids) >= 2:
        requests = (
            PeerRequest(
                focal_contract_id=late_ids[0],
                as_of=as_of,
                catalog_mode=CATALOG_LIVE_CANDIDATE,
                source=source_kind,
                live_semantic_columns_present=live_semantic,
                require_known_regime=False,
                producer_sha=producer_sha,
            ),
            PeerRequest(
                focal_contract_id=late_ids[-1],
                as_of=as_of,
                catalog_mode=CATALOG_LIVE_CANDIDATE,
                source=source_kind,
                live_semantic_columns_present=live_semantic,
                require_known_regime=False,
                producer_sha=producer_sha,
            ),
        )
        event = RectificationEvent(
            rectification_id="live-paving-late-arrival",
            contract_id=late_ids[0],
            as_of=as_of,
            fields={"uf": "RS", "revision": 2},
            note="in-memory late arrival; no production write",
        )
        typed = records_from_mappings(stratum)
        changed = groups_changed_by_rectification(typed, requests, event)
        after_event = RectificationEvent(
            rectification_id="live-paving-target-edit",
            contract_id=focal,
            as_of=as_of,
            fields={"valor": "1.00", "revision": 9},
            note="in-memory target rectification",
        )
        stale = groups_changed_by_rectification(typed, (request,), after_event)
        late = {
            "note": "A late arrival or rectification invalidates only groups that include the affected contract_id.",
            "affected_groups": list(changed),
            "unaffected_groups": [item.focal_contract_id for item in requests if item.focal_contract_id not in changed],
            "target_rectification_invalidates": list(stale),
            "old_hash_remains_valid": False,
            "reason_codes": [REASON_STALE_HASH] if stale else [],
        }
    else:
        late = {
            "note": "Need at least two official paving rows to isolate late-arrival invalidation.",
            "affected_groups": [],
            "unaffected_groups": [],
        }

    metrics_produced = []
    if status == STATUS_COMPARABLE and document.get("metrics"):
        metrics_produced = ["valor_integral_nominal", "median", "p25", "p75", "iqr", "mad", "focal_percentile"]
        if unit_metrics.get("emitted"):
            metrics_produced.append("BRL/m2")
    document["inclusion_rules"] = [
        "typology=pavimentacao AND typology_confidence>=0.80",
        f"paving_family={family} (documented keyword family; not embeddings)",
        "unit=BRL_TOTAL derived from official valorGlobal/valor_contratado field identity",
        "value_semantic=valor_integral_nominal via export_comparables/valor_global_or_contratado_to_valor_integral_nominal/1.1",
        "regime identical when published; unpublished regime stays UNKNOWN and is not an inclusion key",
        "geography=same UF",
        "period=|year_delta|<=1",
        "UNKNOWN valor excluded from denominator",
        "highest revision only",
    ]
    availability = {
        "class": (
            "consulta_cnpj_orgao_bounded"
            if cnpj_orgao and consulta_found
            else ("dsn_absent" if not dsn_available else "live_candidate")
        ),
        "dsn": {"configured": dsn_available, "class": "present" if dsn_available else "dsn_absent"},
        "schema": {"probed": dsn_available, "reason": None if dsn_available else "dsn_absent"},
        "query": {
            "endpoint": "/api/consulta/v1/contratos",
            "official_param": "cnpjOrgao",
            "cnpj_orgao": cnpj_orgao,
            "note": "Swagger /v1/contratos accepts cnpjOrgao. uf and cnpj are ignored.",
        },
        "api_window": {"start": window_start, "end": window_end, "timeout_s": CONSULTA_TIMEOUT_S},
        "semantic": {
            "valor_global": "FACT_OFFICIAL",
            "valor_integral_nominal": "OBSERVATION_DERIVED",
            "unit_brl_total": "OBSERVATION_DERIVED" if live_semantic else "UNKNOWN",
            "unit_derivation": DERIVATION_UNIT_FROM_OFFICIAL_TOTAL if live_semantic else None,
            "regime": "UNKNOWN_unpublished_on_contract_locator",
            "modalidade": "FACT_OFFICIAL_from_linked_compra" if compra_fetch.get("ok") else "UNKNOWN",
        },
        "focal_pairs": {
            "consulta_paving_found": consulta_found,
            "family": family,
            "family_eligible": total_eligible,
            "family_exclusions": len(family_exclusions),
        },
        "public_source": "available" if official_live else "unavailable",
    }
    payload: dict[str, Any] = {
        "schema": LIVE_PAVING_ENVELOPE_SCHEMA,
        "canary_id": LIVE_PAVING_CANARY_ID,
        "peer_group_id": document.get("peer_group_id"),
        "status": status,
        "reason_codes": unique_reasons,
        "catalog_mode": CATALOG_LIVE_CANDIDATE,
        "official_live": official_live,
        "source_kind": source_kind,
        "as_of": as_of,
        "question": QUESTION,
        "question_id": QUESTION_ID,
        "metric": METRIC_NOMINAL_TOTAL,
        "focal_contract_id": focal,
        "target_contract_id": focal,
        "consumer": CONSUMER_WEB_CFG,
        "producer": PRODUCER_EXTRA_CLI,
        "publication_authorization": False,
        "index_authorization": False,
        "no_cross_repo_write": True,
        "national_claim_authorized": False,
        "claim_scope": CLAIM_SCOPE_PI_PAVING,
        "document": document,
        "peers": used_peers,
        "match_quality": document.get("match_quality") or [],
        "suppression": document.get("suppression") or {},
        "missingness": document.get("missingness") or {},
        "method": document.get("method") or {},
        "method_version": document.get("method_version"),
        "policy_version": document.get("policy_version"),
        "typology": document.get("typology"),
        "inclusion_rules": document.get("inclusion_rules"),
        "exclusion_rules": document.get("exclusion_rules"),
        "grain": "contrato",
        "value_semantic": "valor_integral_nominal",
        "unit": document.get("unit"),
        "regime": document.get("regime"),
        "modality": document.get("modality"),
        "geography": document.get("geography"),
        "period": document.get("period"),
        "porte": document.get("porte"),
        "universe": {
            "consulted": source_kind,
            "window": {"start": window_start, "end": window_end},
            "consulta_paving_found": consulta_found,
            "dsn_available": dsn_available,
            "cnpj_orgao": cnpj_orgao,
            "paving_family": family,
        },
        "availability": availability,
        "paving_family": family,
        "family_exclusions": family_exclusions,
        "total_found": total_found,
        "total_eligible": total_eligible,
        "total_used": int(document.get("usable_n") or 0),
        "coverage": document.get("coverage"),
        "outlier_treatment": document.get("outlier_treatment"),
        "monetary_normalization": document.get("monetary_normalization"),
        "unit_metrics": unit_metrics,
        "metrics_produced": metrics_produced,
        "missing_semantic_columns": list(LIVE_MISSING_SEMANTIC_COLUMNS),
        "evidence_refs": evidence_refs,
        "invalidation_keys": ["contract_id", "source_document_sha256", "as_of", "policy_version", "focal_contract_id"],
        "limitations": list(
            dict.fromkeys(
                [
                    *(document.get("limitations") or []),
                    "Engine document catalog_mode is never official_live until semantic columns exist on official locators.",
                    "Envelope official_live is true only when official PNCP bytes were retrieved.",
                    "BRL/m2 is withheld unless COMPARABLE and every used peer documents area/unit/scope.",
                    "Physical-unit cost metrics are refused without verified quantity and scope.",
                    "UNKNOWN is never coerced to zero and never stored as inapplicable.",
                    "Difference is statistical only. Legal accusation language is out of scope.",
                    "national_claim_authorized is false. The Extra 1.093 slice is not a national denominator.",
                    f"MIN_USABLE_N_COMPARABLE={MIN_USABLE_N_COMPARABLE} is not lowered.",
                ]
            )
        ),
        "live": {
            "dsn_available": dsn_available,
            "official_live": official_live,
            "source_kind": source_kind,
            "window": {"start": window_start, "end": window_end},
            "cutoff": as_of,
            "consulta_paving_found": consulta_found,
            "cnpj_orgao": cnpj_orgao,
            "consulta_param": "cnpjOrgao",
            "paving_family": family,
            "focal_fetch_ok": bool(focal_fetch.get("ok")),
            "focal_sha256": focal_fetch.get("sha256"),
            "focal_url": focal_fetch.get("url"),
            "compra_fetch_ok": bool(compra_fetch.get("ok")),
            "production_write": False,
            "backfill": False,
            "publication": False,
            "index": False,
            "unavailabilities": unavailabilities,
            "cache_used": cache_dir is not None,
        },
        "replay_command": replay_command(
            focal_id=focal, as_of=as_of, start=window_start, end=window_end, limit=limit, output=None
        ),
        "observability": {
            "refresh_latency_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "late_arrivals": late,
            "status_counts": {
                STATUS_COMPARABLE: int(status == STATUS_COMPARABLE),
                STATUS_HOLD: int(status == STATUS_HOLD),
                STATUS_NOT: int(status == STATUS_NOT),
                STATUS_BLOCKED: 0,
            },
        },
    }
    if payload["catalog_mode"] == OFFICIAL_LIVE:
        raise ValueError("envelope catalog_mode must not be official_live")
    if payload["official_live"] is True and "fixture" in fold_for_scan(source_kind):
        raise ValueError("fixture source cannot be official_live")
    payload["observability"]["refresh_latency_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
    return attach_live_hash(payload)
