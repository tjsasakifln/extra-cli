"""Read published target-fit materialization for downstream gates (send-readiness / feed).

Warmbly and EMAIL_SEND_READY must consume the published decision — never re-score.
"""

from __future__ import annotations

from typing import Any

from scripts.confenge_target_fit import (
    TARGET_CONFIRMED,
    TARGET_OUT_OF_SCOPE,
    TARGET_PROBABLE_RESEARCH,
)
from scripts.confenge_target_fit.company_key import (
    company_key_from_raiz,
    cnpj_raiz_from_cnpj14,
    digits_only,
)
from scripts.confenge_target_fit.freshness import evaluate_freshness
from scripts.confenge_target_fit.models import FreshnessDecision
from scripts.confenge_target_fit.store import get_control, get_current, is_send_suppressed


def company_key_from_row(row: dict[str, Any] | None) -> str | None:
    if not row:
        return None
    if row.get("company_key"):
        return str(row["company_key"])
    cnpj: Any = row.get("cnpj14") or row.get("cnpj") or row.get("cnpj_root") or row.get(
        "cnpj_raiz"
    )
    company = row.get("company")
    if isinstance(company, dict):
        cnpj = cnpj or company.get("cnpj14") or company.get("cnpj_root")
    raiz = cnpj_raiz_from_cnpj14(cnpj) if cnpj else None
    if not raiz and row.get("cnpj_raiz"):
        raiz = digits_only(row.get("cnpj_raiz"))[:8]
    if not raiz or len(raiz) != 8:
        return None
    try:
        return company_key_from_raiz(raiz)
    except ValueError:
        return None


def load_published_target_fit(
    conn: Any,
    *,
    company_key: str | None = None,
    cnpj: str | None = None,
) -> dict[str, Any] | None:
    if not company_key and cnpj:
        raiz = cnpj_raiz_from_cnpj14(cnpj)
        if raiz:
            company_key = company_key_from_raiz(raiz)
    if not company_key:
        return None
    return get_current(conn, company_key)


def published_from_row_or_db(
    row: dict[str, Any] | None,
    *,
    conn: Any | None = None,
) -> dict[str, Any] | None:
    """Prefer embedded published fields on the row; else load from DB when conn given."""
    if row:
        # Explicit materialization blob
        pub = row.get("published_target_fit") or row.get("target_fit_materialization")
        if isinstance(pub, dict) and pub.get("target_fit_class"):
            return pub
        # Flattened fields (feed / universe enrichment)
        if row.get("target_fit_class"):
            return {
                "company_key": company_key_from_row(row),
                "target_fit_class": row.get("target_fit_class"),
                "target_fit_confidence": row.get("target_fit_confidence"),
                "target_fit_version": row.get("target_fit_version"),
                "target_fit_reason_codes": row.get("target_fit_reason_codes") or [],
                "target_fit_evidence": row.get("target_fit_evidence") or [],
                "computed_at": row.get("target_fit_computed_at") or row.get("computed_at"),
                "source_watermark": row.get("target_fit_source_watermark")
                or row.get("source_watermark"),
                "operational_status": row.get("target_fit_operational_status")
                or row.get("operational_status")
                or "ok",
                "input_fingerprint": row.get("input_fingerprint"),
            }
    if conn is not None:
        ck = company_key_from_row(row) if row else None
        if ck:
            return get_current(conn, ck)
    return None


def map_class_to_send_tier(target_fit_class: str | None) -> str:
    """Map published ICP class → legacy send tier used by EMAIL_SEND_READY."""
    cls = (target_fit_class or "").strip().upper()
    if cls == TARGET_CONFIRMED:
        return "A_AUTOMATIC"
    if cls == TARGET_PROBABLE_RESEARCH:
        return "RESEARCH_ONLY"
    if cls in {TARGET_OUT_OF_SCOPE, "REFRESH_FAILED", "RECOMPUTE_REQUIRED"}:
        return "OUT_OF_SCOPE"
    return "OUT_OF_SCOPE"


def evaluate_published_send_gate(
    *,
    published: dict[str, Any] | None,
    datalake_watermark: str = "",
    suppressed: bool = False,
) -> tuple[bool, list[str], FreshnessDecision | None]:
    """Return (blocks_email_send, reasons, freshness).

    Fail-closed: missing/stale/failed/non-confirmed/downgrade-suppressed all block.
    """
    reasons: list[str] = []
    if not published:
        return True, ["TARGET_FIT_MISSING"], None

    cls = str(published.get("target_fit_class") or "")
    ck = str(published.get("company_key") or "unknown")
    fresh = evaluate_freshness(
        company_key=ck,
        current=published,
        datalake_watermark=datalake_watermark,
        suppressed=suppressed,
    )
    if cls != TARGET_CONFIRMED:
        reasons.append(f"target_fit_class:{cls or 'missing'}")
    if fresh.blocks_send:
        reasons.append(fresh.reason)
    if suppressed and "TARGET_FIT_DOWNGRADE" not in reasons:
        reasons.append("TARGET_FIT_DOWNGRADE")
    op = str(published.get("operational_status") or "")
    if op in {"refresh_failed", "recompute_required", "stale"}:
        if op.upper() not in {r.upper() for r in reasons}:
            reasons.append(f"operational_status:{op}")
    blocks = bool(reasons) or cls != TARGET_CONFIRMED or fresh.blocks_send
    return blocks, reasons, fresh


def attach_published_fields(
    lead: dict[str, Any],
    *,
    published: dict[str, Any] | None,
    freshness: FreshnessDecision | None,
) -> dict[str, Any]:
    """Mutate lead with confenge.outreach.v1 target-fit fields."""
    out = dict(lead)
    if not published:
        out.update(
            {
                "target_fit_class": None,
                "target_fit_confidence": None,
                "target_fit_version": None,
                "target_fit_computed_at": None,
                "target_fit_source_watermark": None,
                "target_fit_fresh": False,
                "target_fit_evidence_ids": [],
            }
        )
        return out
    evidence = published.get("target_fit_evidence") or []
    ids: list[str] = []
    if isinstance(evidence, list):
        for e in evidence:
            if isinstance(e, dict) and e.get("id") is not None:
                ids.append(str(e["id"]))
    computed = published.get("computed_at") or published.get("target_fit_computed_at")
    if hasattr(computed, "isoformat"):
        computed = computed.isoformat()
    fresh_ok = bool(freshness and freshness.target_fit_fresh and not freshness.blocks_send)
    out.update(
        {
            "target_fit_class": published.get("target_fit_class"),
            "target_fit_confidence": published.get("target_fit_confidence"),
            "target_fit_version": published.get("target_fit_version"),
            "target_fit_computed_at": computed,
            "target_fit_source_watermark": published.get("source_watermark")
            or published.get("target_fit_source_watermark"),
            "target_fit_fresh": fresh_ok,
            "target_fit_evidence_ids": ids,
            "target_fit_freshness_reason": (freshness.reason if freshness else None),
        }
    )
    return out


def resolve_gate_from_conn(
    conn: Any,
    *,
    company_key: str | None = None,
    cnpj: str | None = None,
    row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Full resolution used by send-readiness / export."""
    published = published_from_row_or_db(row, conn=conn)
    if published is None and (company_key or cnpj):
        published = load_published_target_fit(conn, company_key=company_key, cnpj=cnpj)
    ck = (published or {}).get("company_key") or company_key or company_key_from_row(row)
    suppressed = bool(ck and is_send_suppressed(conn, str(ck)))
    cdc = get_control(conn, "cdc_watermark")
    dl_wm = str(cdc.get("watermark") or "")
    blocks, reasons, fresh = evaluate_published_send_gate(
        published=published,
        datalake_watermark=dl_wm,
        suppressed=suppressed,
    )
    return {
        "published": published,
        "suppressed": suppressed,
        "blocks_send": blocks,
        "reasons": reasons,
        "freshness": fresh,
        "send_tier": map_class_to_send_tier(
            (published or {}).get("target_fit_class") if published else None
        ),
    }
