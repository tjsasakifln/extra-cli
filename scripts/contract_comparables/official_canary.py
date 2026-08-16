"""Official paving canary: live SELECT-only or an auditable BLOCKED refusal.

This is the EXTRA-010 delta on top of the inbound #418 producer. It does not
open a second engine. Fixture COMPARABLE is not official proof.
"""

from __future__ import annotations

import time
from collections import Counter
from typing import Any

from scripts.contract_comparables.constants import (
    CANARY_STATUS_ENUM,
    CATALOG_BLOCKED,
    CATALOG_LIVE_CANDIDATE,
    LIVE_MISSING_SEMANTIC_COLUMNS,
    METRIC_NOMINAL_TOTAL,
    MIN_TYPOLOGY_CONFIDENCE,
    OFFICIAL_CANARY_SCHEMA,
    OFFICIAL_LIVE,
    PAVING_KEYWORDS,
    PHYSICAL_UNIT_METRICS,
    QUESTION,
    QUESTION_ID,
    REASON_DATASET_EMPTY,
    REASON_DSN_UNAVAILABLE,
    REASON_HOST_UNAVAILABLE,
    REASON_LIVE_COLUMNS,
    REASON_LIVE_PROBE_FAILED,
    REASON_PAVING_SAMPLE_EMPTY,
    REASON_PHYSICAL_UNIT,
    REASON_TABLE_MISSING,
    STATUS_BLOCKED,
    STATUS_COMPARABLE,
    STATUS_HOLD,
    STATUS_NOT,
)
from scripts.contract_comparables.engine import build_peer_group, groups_changed_by_rectification
from scripts.contract_comparables.live import inspect_columns, resolve_dsn, rows_to_records
from scripts.contract_comparables.models import PeerRequest, RectificationEvent
from scripts.contract_comparables.normalize import classify_typology, records_from_mappings, recorte_from_record
from scripts.contract_comparables.serialize import content_hash_for, fold_for_scan

DEFAULT_AS_OF = "2026-08-01"
DEFAULT_LIMIT = 200
MAX_FOCALS_FOR_RATE = 12
NEXT_COMMAND = (
    'export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}" && '
    "python3 -m scripts.contract_comparables official-canary --as-of 2026-08-01 --metric valor_integral_nominal"
)

PAVING_SELECT = """
SELECT contrato_id, orgao_cnpj, orgao_nome, fornecedor_cnpj, fornecedor_nome,
       objeto_contrato, valor_total, data_inicio, data_fim, data_publicacao,
       uf, municipio, source, source_id, ingested_at, is_active,
       codigo_municipio_ibge
FROM pncp_supplier_contracts
WHERE is_active IS TRUE
  AND objeto_contrato IS NOT NULL
  AND (
       objeto_contrato ILIKE %s
    OR objeto_contrato ILIKE %s
    OR objeto_contrato ILIKE %s
    OR objeto_contrato ILIKE %s
    OR objeto_contrato ILIKE %s
    OR objeto_contrato ILIKE %s
  )
ORDER BY contrato_id
LIMIT %s
"""

PAVING_ILIKE = (
    "%paviment%",
    "%recapeamento%",
    "%cbuq%",
    "%asfalt%",
    "%microrevestimento%",
    "%concreto betuminoso%",
)

COUNT_ACTIVE_SQL = """
SELECT COUNT(*) AS n
FROM pncp_supplier_contracts
WHERE is_active IS TRUE
"""

TABLE_EXISTS_SQL = """
SELECT 1
FROM information_schema.tables
WHERE table_schema = 'public' AND table_name = 'pncp_supplier_contracts'
LIMIT 1
"""

DEPENDENCY_RESIDUAL = {
    "EXTRA-003": "absent_locally",
    "EXTRA-004": "not_in_origin_main",
    "EXTRA-008": "not_in_origin_main",
}

LIMITATIONS_OFFICIAL = (
    "Canary answers only the nominal total-value position of paving contracts.",
    "This is not cost/km, a unit price, a legal accusation, or a national ranking.",
    "UNKNOWN is never coerced to zero and never enters the denominator.",
    "catalog_mode is never official_live unless semantic columns and coverage are proven.",
    "Keyword typology is the documented method; it is not an official regime/unit column.",
    "valor_total has no currency column; BRL is a PNCP instrument convention, not a proven field.",
)


def assert_select_only(sql: str) -> None:
    head = sql.lstrip().split(None, 1)[0].upper() if sql.strip() else ""
    if head != "SELECT":
        raise ValueError(f"official canary accepts SELECT-only SQL, got {head or 'empty'}")


def requested_physical_unit_metric(metric: str) -> bool:
    folded = fold_for_scan(metric)
    return folded in {fold_for_scan(item) for item in PHYSICAL_UNIT_METRICS}


_HASH_SKIP = frozenset({"content_hash", "refresh_latency_ms", "per_group_ms"})


def _hashable_copy(payload: dict[str, Any]) -> dict[str, Any]:
    copy: dict[str, Any] = {}
    for key, value in payload.items():
        if key in _HASH_SKIP:
            continue
        if key == "observability" and isinstance(value, dict):
            copy[key] = {obs_key: obs_value for obs_key, obs_value in value.items() if obs_key not in _HASH_SKIP}
            continue
        copy[key] = value
    return copy


def attach_envelope_hash(payload: dict[str, Any]) -> dict[str, Any]:
    payload["content_hash"] = content_hash_for(_hashable_copy(payload))
    return payload


def dependency_residual() -> dict[str, str]:
    return dict(DEPENDENCY_RESIDUAL)


def blocked_envelope(
    *,
    reason_codes: tuple[str, ...],
    prerequisite: str,
    next_command: str,
    as_of: str,
    metric: str,
    reviewable_sample: dict[str, Any] | None = None,
    missing_semantic_columns: tuple[str, ...] = LIVE_MISSING_SEMANTIC_COLUMNS,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": OFFICIAL_CANARY_SCHEMA,
        "status": STATUS_BLOCKED,
        "reason_codes": list(reason_codes),
        "catalog_mode": CATALOG_BLOCKED,
        "as_of": as_of,
        "question": QUESTION,
        "question_id": QUESTION_ID,
        "metric": metric,
        "document": None,
        "peers": [],
        "match_quality": [],
        "suppression": {"peer_ids_emitted": False, "aggregate_only": True},
        "missingness": {"ratio": 1.0, "unknown_excluded": True},
        "method": {
            "id": "comparable-contracts-peer-group/1.0",
            "question_id": QUESTION_ID,
            "no_llm": True,
            "select_only": True,
        },
        "reviewable_sample": reviewable_sample or empty_reviewable_sample(),
        "missing_semantic_columns": list(missing_semantic_columns),
        "prerequisite": prerequisite,
        "next_command": next_command,
        "residual": dependency_residual(),
        "limitations": list(LIMITATIONS_OFFICIAL),
        "observability": {
            "not_comparable_rate": None,
            "status_counts": {
                STATUS_COMPARABLE: 0,
                STATUS_HOLD: 0,
                STATUS_NOT: 0,
                STATUS_BLOCKED: 1,
            },
            "refresh_latency_ms": None,
            "late_arrivals": {
                "note": "No official peer group was built; late-arrival isolation was not exercised on live rows.",
                "affected_groups": [],
                "unaffected_groups": [],
            },
        },
    }
    if extra:
        payload.update(extra)
    if payload["catalog_mode"] == OFFICIAL_LIVE:
        raise ValueError("blocked envelope must not claim official_live")
    return attach_envelope_hash(payload)


def empty_reviewable_sample() -> dict[str, Any]:
    return {
        "n_rows_fetched": 0,
        "n_paving": 0,
        "typology": {
            "label": "pavimentacao",
            "method": "documented_keyword_classifier",
            "keywords": list(PAVING_KEYWORDS),
            "min_confidence": MIN_TYPOLOGY_CONFIDENCE,
            "sample_precision_reviewed": False,
        },
        "regime": {"status": "UNKNOWN", "column": None, "note": "no official regime column"},
        "porte": {"status": "UNKNOWN", "column": None, "note": "no official porte column"},
        "geography": {"ufs": [], "municipios": [], "note": "no official paving rows"},
        "period": {"years": [], "as_of": None},
        "currency": {
            "code": "UNKNOWN",
            "column": None,
            "note": "valor_total has no currency column; BRL is a PNCP convention, not a proven field",
        },
        "value_basis": {"status": "UNKNOWN", "column": None},
        "coverage": {"usable_over_total": 0.0, "missingness": 1.0, "eligible_n": 0},
        "unknown_fields": list(LIVE_MISSING_SEMANTIC_COLUMNS),
    }


def refuse_physical_unit_metric(*, metric: str, as_of: str) -> dict[str, Any]:
    sample = empty_reviewable_sample()
    sample["typology"]["sample_precision_reviewed"] = True
    payload = {
        "schema": OFFICIAL_CANARY_SCHEMA,
        "status": STATUS_HOLD,
        "reason_codes": [REASON_PHYSICAL_UNIT],
        "catalog_mode": CATALOG_LIVE_CANDIDATE,
        "as_of": as_of,
        "question": QUESTION,
        "question_id": QUESTION_ID,
        "metric": metric,
        "document": None,
        "peers": [],
        "match_quality": [],
        "suppression": {"peer_ids_emitted": False, "aggregate_only": True},
        "missingness": {"ratio": 1.0, "unknown_excluded": True},
        "method": {
            "id": "comparable-contracts-peer-group/1.0",
            "question_id": QUESTION_ID,
            "no_llm": True,
            "select_only": True,
        },
        "reviewable_sample": sample,
        "missing_semantic_columns": list(LIVE_MISSING_SEMANTIC_COLUMNS),
        "prerequisite": (
            "Documentary quantity, physical unit, scope, normalization and usable sample "
            "on official columns before any cost/km or unit price is computed."
        ),
        "next_command": NEXT_COMMAND,
        "residual": dependency_residual(),
        "limitations": list(LIMITATIONS_OFFICIAL),
        "observability": {
            "not_comparable_rate": None,
            "status_counts": {
                STATUS_COMPARABLE: 0,
                STATUS_HOLD: 1,
                STATUS_NOT: 0,
                STATUS_BLOCKED: 0,
            },
            "refresh_latency_ms": None,
            "late_arrivals": {
                "note": "Physical-unit request is refused before peer construction.",
                "affected_groups": [],
                "unaffected_groups": [],
            },
        },
    }
    return attach_envelope_hash(payload)


def is_paving_record(mapping: dict[str, Any]) -> bool:
    typology, confidence, _scope = classify_typology(str(mapping.get("objeto") or ""))
    return typology == "pavimentacao" and confidence >= MIN_TYPOLOGY_CONFIDENCE


def filter_paving_mappings(mappings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in mappings if is_paving_record(item)]


def reviewable_sample_from_records(
    mappings: list[dict[str, Any]],
    *,
    as_of: str,
    coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    recortes = sorted(
        (recorte_from_record(record) for record in records_from_mappings(mappings)),
        key=lambda item: item.contract.contract_id,
    )
    ufs = sorted({item.uf for item in recortes if item.uf})
    municipios = sorted({item.contract.municipio for item in recortes if item.contract.municipio})
    years = sorted({item.year for item in recortes if item.year is not None})
    regimes = sorted({item.regime for item in recortes})
    portes = sorted({item.porte for item in recortes})
    unknown = sorted({field for item in recortes for field in item.unknown_fields})
    return {
        "n_rows_fetched": len(mappings),
        "n_paving": len(recortes),
        "typology": {
            "label": "pavimentacao",
            "method": "documented_keyword_classifier",
            "keywords": list(PAVING_KEYWORDS),
            "min_confidence": MIN_TYPOLOGY_CONFIDENCE,
            "sample_precision_reviewed": True,
            "confidences": [round(item.typology_confidence, 4) for item in recortes[:20]],
        },
        "regime": {
            "status": "UNKNOWN" if regimes == ["unknown"] or not regimes else "mixed_or_heuristic",
            "observed": regimes,
            "column": None,
            "note": "no official regime column; unknown remains unknown",
        },
        "porte": {
            "status": "UNKNOWN" if portes == ["unknown"] or not portes else "value_band_heuristic",
            "observed": portes,
            "column": None,
            "note": "no official porte column; value-band heuristic is not an official field",
        },
        "geography": {"ufs": ufs, "municipios": municipios[:20], "municipio_count": len(municipios)},
        "period": {"years": years, "as_of": as_of},
        "currency": {
            "code": "UNKNOWN",
            "column": None,
            "note": "valor_total has no currency column; BRL is a PNCP convention, not a proven field",
        },
        "value_basis": {"status": "UNKNOWN", "column": None},
        "coverage": coverage or {"usable_over_total": 0.0, "missingness": 1.0, "eligible_n": 0},
        "unknown_fields": unknown or list(LIVE_MISSING_SEMANTIC_COLUMNS),
        "contracts": [
            {
                "contract_id": item.contract.contract_id,
                "typology": item.typology,
                "typology_confidence": item.typology_confidence,
                "regime": item.regime,
                "porte": item.porte,
                "uf": item.uf,
                "year": item.year,
                "unit": item.unit,
                "value_semantic": item.value_semantic,
                "unknown_fields": list(item.unknown_fields),
            }
            for item in recortes[:20]
        ],
    }


def observe_late_arrivals(
    mappings: list[dict[str, Any]],
    *,
    as_of: str,
    live_semantic_columns_present: bool,
) -> dict[str, Any]:
    records = records_from_mappings(mappings)
    ids = sorted({record.contract_id for record in records})
    if len(ids) < 3:
        return {
            "note": "Need at least three official paving rows to isolate late-arrival invalidation.",
            "affected_groups": [],
            "unaffected_groups": [],
        }
    requests = (
        PeerRequest(
            focal_contract_id=ids[0],
            as_of=as_of,
            catalog_mode=CATALOG_LIVE_CANDIDATE,
            source="pncp_supplier_contracts",
            live_semantic_columns_present=live_semantic_columns_present,
        ),
        PeerRequest(
            focal_contract_id=ids[-1],
            as_of=as_of,
            catalog_mode=CATALOG_LIVE_CANDIDATE,
            source="pncp_supplier_contracts",
            live_semantic_columns_present=live_semantic_columns_present,
        ),
    )
    # Official live rows lack semantic columns, so peers are exclusions and a
    # valor edit would not change the HOLD document. Changing the focal UF is a
    # material identity edit that appears only on groups that contain that focal.
    event = RectificationEvent(
        rectification_id="official-canary-late-arrival",
        contract_id=ids[0],
        as_of=as_of,
        fields={"uf": "RS", "revision": 2},
        note="in-memory late arrival; no write to the official table",
    )
    changed = groups_changed_by_rectification(records, requests, event)
    unaffected = tuple(item.focal_contract_id for item in requests if item.focal_contract_id not in changed)
    return {
        "note": "A late arrival or rectification invalidates only groups that include the affected contract_id.",
        "rectified_contract_id": ids[0],
        "affected_groups": list(changed),
        "unaffected_groups": list(unaffected),
    }


def measure_status_rates(
    mappings: list[dict[str, Any]],
    *,
    as_of: str,
    live_semantic_columns_present: bool,
) -> dict[str, Any]:
    ids = sorted({str(item["contract_id"]) for item in mappings if item.get("contract_id")})
    statuses: Counter[str] = Counter()
    latencies_ms: list[float] = []
    hashes: list[str] = []
    records = records_from_mappings(mappings)
    for focal_id in ids[:MAX_FOCALS_FOR_RATE]:
        started = time.perf_counter()
        request = PeerRequest(
            focal_contract_id=focal_id,
            as_of=as_of,
            catalog_mode=CATALOG_LIVE_CANDIDATE,
            source="pncp_supplier_contracts",
            live_semantic_columns_present=live_semantic_columns_present,
        )
        _result, document = build_peer_group(records, request)
        latencies_ms.append((time.perf_counter() - started) * 1000.0)
        statuses[document["status"]] += 1
        hashes.append(document["content_hash"])
    evaluated = sum(statuses.values())
    refused = statuses[STATUS_NOT]
    return {
        "groups_evaluated": evaluated,
        "status_counts": {
            STATUS_COMPARABLE: statuses[STATUS_COMPARABLE],
            STATUS_HOLD: statuses[STATUS_HOLD],
            STATUS_NOT: statuses[STATUS_NOT],
            STATUS_BLOCKED: 0,
        },
        "not_comparable_rate": round(refused / evaluated, 4) if evaluated else None,
        "per_group_ms": [round(item, 3) for item in latencies_ms],
        "document_hashes": hashes,
    }


def build_official_envelope(
    mappings: list[dict[str, Any]],
    *,
    as_of: str,
    focal_id: str | None,
    missing_semantic_columns: tuple[str, ...],
    official_columns: tuple[str, ...],
    active_row_count: int | None = None,
) -> dict[str, Any]:
    paving = filter_paving_mappings(mappings)
    if not paving:
        sample = empty_reviewable_sample()
        sample["n_rows_fetched"] = len(mappings)
        reason = (
            REASON_DATASET_EMPTY if not mappings and (active_row_count in {0, None}) else REASON_PAVING_SAMPLE_EMPTY
        )
        prerequisite = (
            "Populate public.pncp_supplier_contracts with official active rows, then re-run the canary."
            if reason == REASON_DATASET_EMPTY
            else "Official snapshot has no paving rows under the documented keyword typology."
        )
        return blocked_envelope(
            reason_codes=(reason, REASON_LIVE_COLUMNS),
            prerequisite=prerequisite,
            next_command=NEXT_COMMAND,
            as_of=as_of,
            metric=METRIC_NOMINAL_TOTAL,
            reviewable_sample=sample,
            missing_semantic_columns=missing_semantic_columns,
            extra={"official_columns_present": list(official_columns), "active_row_count": active_row_count},
        )
    focal = focal_id or str(paving[0]["contract_id"])
    live_semantic = not missing_semantic_columns
    request = PeerRequest(
        focal_contract_id=focal,
        as_of=as_of,
        catalog_mode=CATALOG_LIVE_CANDIDATE,
        source="pncp_supplier_contracts",
        live_semantic_columns_present=live_semantic,
    )
    _result, document = build_peer_group(records_from_mappings(paving), request)
    if document.get("catalog_mode") == OFFICIAL_LIVE:
        raise RuntimeError("official canary must not self-label official_live")
    if missing_semantic_columns and REASON_LIVE_COLUMNS not in document["reason_codes"]:
        document["reason_codes"] = [*document["reason_codes"], REASON_LIVE_COLUMNS]
    rates = measure_status_rates(
        paving,
        as_of=as_of,
        live_semantic_columns_present=live_semantic,
    )
    late = observe_late_arrivals(
        paving,
        as_of=as_of,
        live_semantic_columns_present=live_semantic,
    )
    sample = reviewable_sample_from_records(paving, as_of=as_of, coverage=document.get("coverage"))
    payload = {
        "schema": OFFICIAL_CANARY_SCHEMA,
        "status": document["status"],
        "reason_codes": list(document["reason_codes"]),
        "catalog_mode": CATALOG_LIVE_CANDIDATE,
        "as_of": as_of,
        "question": QUESTION,
        "question_id": QUESTION_ID,
        "metric": METRIC_NOMINAL_TOTAL,
        "focal_contract_id": focal,
        "document": document,
        "peers": document.get("peers") or [],
        "match_quality": document.get("match_quality") or [],
        "suppression": document.get("suppression") or {},
        "missingness": document.get("missingness") or {},
        "method": document.get("method") or {},
        "reviewable_sample": sample,
        "missing_semantic_columns": list(missing_semantic_columns),
        "official_columns_present": list(official_columns),
        "active_row_count": active_row_count,
        "prerequisite": (
            None
            if document["status"] == STATUS_COMPARABLE
            else "Official semantic columns (unidade, quantidade, regime, modalidade, valor_semantic) plus a usable paving sample."
        ),
        "next_command": NEXT_COMMAND,
        "residual": dependency_residual(),
        "limitations": list(dict.fromkeys([*(document.get("limitations") or []), *LIMITATIONS_OFFICIAL])),
        "observability": {
            "not_comparable_rate": rates["not_comparable_rate"],
            "status_counts": rates["status_counts"],
            "groups_evaluated": rates["groups_evaluated"],
            "per_group_ms": rates["per_group_ms"],
            "refresh_latency_ms": None,
            "late_arrivals": late,
        },
    }
    if payload["status"] not in CANARY_STATUS_ENUM:
        raise ValueError(f"illegal canary status: {payload['status']}")
    if payload["catalog_mode"] == OFFICIAL_LIVE:
        raise ValueError("official_live is forbidden until semantics and coverage are proven")
    return attach_envelope_hash(payload)


def _probe_live(
    *,
    dsn: str,
    limit: int,
) -> dict[str, Any]:
    assert_select_only(PAVING_SELECT)
    assert_select_only(COUNT_ACTIVE_SQL)
    assert_select_only(TABLE_EXISTS_SQL)
    try:
        from scripts.national_intel.db import connect, fetch_all
    except ImportError as exc:
        return {
            "blocked": True,
            "reason_codes": (REASON_LIVE_PROBE_FAILED,),
            "prerequisite": "scripts.national_intel.db must be importable for SELECT-only live access.",
            "detail": str(exc),
        }
    try:
        with connect(dsn) as conn:
            exists = fetch_all(conn, TABLE_EXISTS_SQL)
            if not exists:
                return {
                    "blocked": True,
                    "reason_codes": (REASON_TABLE_MISSING,),
                    "prerequisite": "Create public.pncp_supplier_contracts via the official migration path.",
                    "detail": "table_missing",
                }
            official, missing = inspect_columns(conn)
            counts = fetch_all(conn, COUNT_ACTIVE_SQL)
            active_n = int(counts[0]["n"]) if counts else 0
            rows = fetch_all(conn, PAVING_SELECT, (*PAVING_ILIKE, limit))
    except Exception as exc:  # noqa: BLE001 — live probe must fail closed
        text = str(exc)
        reason = REASON_HOST_UNAVAILABLE
        if "does not exist" in text and "pncp_supplier_contracts" in text:
            reason = REASON_TABLE_MISSING
        return {
            "blocked": True,
            "reason_codes": (reason, REASON_LIVE_PROBE_FAILED),
            "prerequisite": "Reachable SELECT-only DSN with public.pncp_supplier_contracts.",
            "detail": text,
        }
    mappings = [item for item in rows_to_records(rows) if item.get("contract_id")]
    return {
        "blocked": False,
        "official": official,
        "missing": missing,
        "active_n": active_n,
        "mappings": mappings,
    }


def run_official_canary(
    *,
    dsn: str | None = None,
    focal_id: str | None = None,
    as_of: str = DEFAULT_AS_OF,
    limit: int = DEFAULT_LIMIT,
    metric: str = METRIC_NOMINAL_TOTAL,
) -> dict[str, Any]:
    started = time.perf_counter()
    if requested_physical_unit_metric(metric):
        payload = refuse_physical_unit_metric(metric=metric, as_of=as_of)
        payload["observability"]["refresh_latency_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
        return attach_envelope_hash(payload)
    if fold_for_scan(metric) not in {fold_for_scan(METRIC_NOMINAL_TOTAL), "valor", "ticket"}:
        payload = refuse_physical_unit_metric(metric=metric, as_of=as_of)
        payload["reason_codes"] = [REASON_PHYSICAL_UNIT, "metric_not_in_whitelist"]
        payload["status"] = STATUS_NOT
        payload["observability"]["status_counts"] = {
            STATUS_COMPARABLE: 0,
            STATUS_HOLD: 0,
            STATUS_NOT: 1,
            STATUS_BLOCKED: 0,
        }
        payload["observability"]["refresh_latency_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
        return attach_envelope_hash(payload)

    resolved = resolve_dsn(dsn)
    if not resolved:
        payload = blocked_envelope(
            reason_codes=(REASON_DSN_UNAVAILABLE,),
            prerequisite="Set LOCAL_DATALAKE_DSN (or NATIONAL_INTEL_DSN) to a SELECT-only snapshot that contains public.pncp_supplier_contracts.",
            next_command=NEXT_COMMAND,
            as_of=as_of,
            metric=METRIC_NOMINAL_TOTAL,
        )
        payload["observability"]["refresh_latency_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
        return attach_envelope_hash(payload)

    probe = _probe_live(dsn=resolved, limit=limit)
    if probe.get("blocked"):
        payload = blocked_envelope(
            reason_codes=tuple(probe["reason_codes"]),
            prerequisite=str(probe["prerequisite"]),
            next_command=NEXT_COMMAND,
            as_of=as_of,
            metric=METRIC_NOMINAL_TOTAL,
            extra={"detail": probe.get("detail")},
        )
        payload["observability"]["refresh_latency_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
        return attach_envelope_hash(payload)

    payload = build_official_envelope(
        probe["mappings"],
        as_of=as_of,
        focal_id=focal_id,
        missing_semantic_columns=tuple(probe["missing"]),
        official_columns=tuple(probe["official"]),
        active_row_count=probe["active_n"],
    )
    payload["observability"]["refresh_latency_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
    return attach_envelope_hash(payload)
