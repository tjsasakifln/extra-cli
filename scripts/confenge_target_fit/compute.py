"""Pure compute path: company input → materialization + transition event.

Idempotent for same fingerprint + version. Fail-closed on classification errors.
"""

from __future__ import annotations

import hashlib
import inspect
from datetime import UTC, datetime
from typing import Any

from scripts.confenge_target_fit import (
    EVT_FAILED,
    MODE_ACTIVE,
    MODE_CANARY,
    MODE_SHADOW,
    REFRESH_FAILED,
    STORE_SCHEMA_VERSION,
    TARGET_FIT_VERSION,
)
from scripts.confenge_target_fit.fingerprint import (
    changed_evidence_ids,
    compute_input_fingerprint,
)
from scripts.confenge_target_fit.models import (
    CompanyInput,
    MaterializedTargetFit,
    TransitionEvent,
)
from scripts.confenge_target_fit.transitions import (
    classify_event_type,
    is_downgrade,
    is_upgrade,
    transition_key,
)
from scripts.confenge_universe.target_fit import classify_target_fit


def classifier_sha() -> str:
    """Stable hash of classifier source for materialization provenance."""
    try:
        src = inspect.getsource(classify_target_fit)
    except (OSError, TypeError):
        src = TARGET_FIT_VERSION
    return "sha256:" + hashlib.sha256(src.encode("utf-8")).hexdigest()[:16]


def compute_materialization(
    company: CompanyInput,
    *,
    previous: dict[str, Any] | None = None,
    mode: str = MODE_ACTIVE,
    target_fit_version: str = TARGET_FIT_VERSION,
    now: datetime | None = None,
) -> tuple[MaterializedTargetFit, TransitionEvent | None, dict[str, Any]]:
    """Return (materialization, event|None, meta).

    meta includes: skipped_fingerprint, upgrade, downgrade, transition_key, error
    """
    now = now or datetime.now(UTC)
    meta: dict[str, Any] = {
        "skipped_fingerprint": False,
        "upgrade": False,
        "downgrade": False,
        "transition_key": "UNCHANGED",
        "error": None,
    }
    fp = compute_input_fingerprint(company, target_fit_version=target_fit_version)
    prev_fp = (previous or {}).get("input_fingerprint")
    prev_ver = (previous or {}).get("target_fit_version")
    prev_class = (previous or {}).get("target_fit_class")
    prev_conf = (previous or {}).get("target_fit_confidence")
    prev_watermark = str((previous or {}).get("source_watermark") or "")
    incoming_watermark = str(company.source_watermark or "")

    if (
        previous
        and prev_fp == fp
        and prev_ver == target_fit_version
        and prev_class
        and prev_class not in {REFRESH_FAILED, "RECOMPUTE_REQUIRED"}
        # A newer canonical watermark is provenance work even when semantic
        # inputs are unchanged. Recompute/publish so the durable snapshot can
        # prove which datalake state the decision observed.
        and (not incoming_watermark or incoming_watermark == prev_watermark)
    ):
        meta["skipped_fingerprint"] = True
        mat = MaterializedTargetFit(
            company_key=company.company_key,
            cnpj_raiz=company.cnpj_raiz,
            target_fit_class=str(prev_class),
            target_fit_confidence=float(prev_conf or 0),
            target_fit_version=str(prev_ver),
            target_fit_reason_codes=list(
                previous.get("target_fit_reason_codes") or []
            ),
            target_fit_evidence=list(previous.get("target_fit_evidence") or []),
            computed_at=previous.get("computed_at") or now,
            source_watermark=company.source_watermark
            or str(previous.get("source_watermark") or ""),
            source_max_updated_at=company.source_max_updated_at
            or previous.get("source_max_updated_at"),
            input_fingerprint=fp,
            classifier_sha=str(previous.get("classifier_sha") or classifier_sha()),
            schema_version=STORE_SCHEMA_VERSION,
            operational_status="ok",
            sector_fit=str(previous.get("sector_fit") or ""),
            activity_class=str(previous.get("activity_class") or ""),
            relevant_execution_contract_count=int(
                previous.get("relevant_execution_contract_count") or 0
            ),
            relevant_supply_only_count=int(
                previous.get("relevant_supply_only_count") or 0
            ),
            materialization_mode=mode,
            previous_class=str(prev_class) if prev_class else None,
            previous_confidence=float(prev_conf) if prev_conf is not None else None,
            transition_event="TARGET_FIT_UNCHANGED",
        )
        # normalize json fields that may already be lists from RealDict
        if isinstance(mat.target_fit_reason_codes, str):
            import json

            mat.target_fit_reason_codes = json.loads(mat.target_fit_reason_codes)
        if isinstance(mat.target_fit_evidence, str):
            import json

            mat.target_fit_evidence = json.loads(mat.target_fit_evidence)
        return mat, None, meta

    try:
        decision = classify_target_fit(
            razao_social=company.razao_social,
            nome_fantasia=company.nome_fantasia,
            contracts=company.contracts,
            cnae_principal=company.cnae_principal,
            cnaes_secundarios=company.cnaes_secundarios,
            sector_fit=company.sector_fit,
            activity_class=company.activity_class,
            construction_evidence=company.construction_evidence,
        )
    except Exception as exc:  # noqa: BLE001 — fail-closed, never preserve CONFIRMED blindly
        meta["error"] = f"{type(exc).__name__}: {exc}"
        mat = MaterializedTargetFit(
            company_key=company.company_key,
            cnpj_raiz=company.cnpj_raiz,
            target_fit_class=REFRESH_FAILED,
            target_fit_confidence=0.0,
            target_fit_version=target_fit_version,
            target_fit_reason_codes=["classification_error", meta["error"][:200]],
            target_fit_evidence=[],
            computed_at=now,
            source_watermark=company.source_watermark,
            source_max_updated_at=company.source_max_updated_at,
            input_fingerprint=fp,
            classifier_sha=classifier_sha(),
            schema_version=STORE_SCHEMA_VERSION,
            operational_status="refresh_failed",
            materialization_mode=mode,
            previous_class=str(prev_class) if prev_class else None,
            previous_confidence=float(prev_conf) if prev_conf is not None else None,
            transition_event=EVT_FAILED,
        )
        event = TransitionEvent(
            event_type=EVT_FAILED,
            company_key=company.company_key,
            cnpj_raiz=company.cnpj_raiz,
            old_class=str(prev_class) if prev_class else None,
            new_class=REFRESH_FAILED,
            old_confidence=float(prev_conf) if prev_conf is not None else None,
            new_confidence=0.0,
            reason_codes=mat.target_fit_reason_codes,
            changed_evidence_ids=[],
            source_watermark=company.source_watermark,
            computed_at=now,
            target_fit_version=target_fit_version,
            payload={"error": meta["error"]},
        )
        return mat, event, meta

    reasons = list(decision.target_fit_reason_codes)
    evidence = list(decision.target_fit_evidence)
    if company.is_consortium_member:
        reasons.append("CONSORTIUM_EVIDENCE")
        evidence.append(
            {
                "id": "consortium",
                "type": "CONSORTIUM_EVIDENCE",
                "excerpt": "consortium contracts present; conservative treatment",
            }
        )
        for n in company.consortium_notes:
            reasons.append(n)

    # Never promote solely by absence of information / contract count alone —
    # classifier already enforces triangulation; we only add provenance notes.

    new_class = decision.target_fit_class
    new_conf = float(decision.target_fit_confidence)
    evt_type = classify_event_type(
        old_class=str(prev_class) if prev_class else None,
        new_class=new_class,
        old_version=str(prev_ver) if prev_ver else None,
        new_version=target_fit_version,
        old_evidence=list(previous.get("target_fit_evidence") or []) if previous else [],
        new_evidence=evidence,
    )
    meta["upgrade"] = is_upgrade(
        str(prev_class) if prev_class else None, new_class
    )
    meta["downgrade"] = is_downgrade(
        str(prev_class) if prev_class else None, new_class
    )
    meta["transition_key"] = transition_key(
        str(prev_class) if prev_class else None, new_class
    )

    mat = MaterializedTargetFit(
        company_key=company.company_key,
        cnpj_raiz=company.cnpj_raiz,
        target_fit_class=new_class,
        target_fit_confidence=new_conf,
        target_fit_version=target_fit_version,
        target_fit_reason_codes=reasons,
        target_fit_evidence=evidence,
        computed_at=now,
        source_watermark=company.source_watermark,
        source_max_updated_at=company.source_max_updated_at,
        input_fingerprint=fp,
        classifier_sha=classifier_sha(),
        schema_version=STORE_SCHEMA_VERSION,
        operational_status="shadow_only" if mode == MODE_SHADOW else "ok",
        sector_fit=decision.sector_fit or (company.sector_fit or ""),
        activity_class=decision.activity_class or (company.activity_class or ""),
        relevant_execution_contract_count=decision.relevant_execution_contract_count,
        relevant_supply_only_count=decision.relevant_supply_only_count,
        materialization_mode=mode,
        previous_class=str(prev_class) if prev_class else None,
        previous_confidence=float(prev_conf) if prev_conf is not None else None,
        transition_event=evt_type,
    )

    event = TransitionEvent(
        event_type=evt_type,
        company_key=company.company_key,
        cnpj_raiz=company.cnpj_raiz,
        old_class=str(prev_class) if prev_class else None,
        new_class=new_class,
        old_confidence=float(prev_conf) if prev_conf is not None else None,
        new_confidence=new_conf,
        reason_codes=reasons,
        changed_evidence_ids=changed_evidence_ids(
            list(previous.get("target_fit_evidence") or []) if previous else [],
            evidence,
        ),
        source_watermark=company.source_watermark,
        computed_at=now,
        target_fit_version=target_fit_version,
        payload={
            "mode": mode,
            "transition": meta["transition_key"],
            "fingerprint": fp,
        },
    )
    if evt_type == "TARGET_FIT_UNCHANGED":
        return mat, None, meta
    return mat, event, meta


def should_apply_active(
    *,
    mode: str,
    company_key: str,
    canary_percent: int,
) -> bool:
    """Whether materialization may update canonical current (not just shadow)."""
    if mode == MODE_SHADOW:
        return False
    if mode == MODE_ACTIVE:
        return True
    if mode == MODE_CANARY:
        from scripts.confenge_target_fit.company_key import canary_bucket

        return canary_bucket(company_key) < canary_percent
    return False
