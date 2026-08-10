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
    cnpj_raiz_from_cnpj14,
    company_key_from_raiz,
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


def load_published_index(
    conn: Any,
    *,
    cnpj14s: list[str] | None = None,
    company_keys: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Batch-load confenge_company_target_fit_current keyed by company_key and cnpj_raiz.

    Returns a dict with both ``cnpj_root:XXXXXXXX`` and bare 8-digit raiz keys
    pointing at the same published row, so joiners can use either form.
    """
    keys: set[str] = set(company_keys or [])
    raizes: set[str] = set()
    for c in cnpj14s or []:
        raiz = cnpj_raiz_from_cnpj14(c)
        if raiz and len(raiz) == 8:
            raizes.add(raiz)
            try:
                keys.add(company_key_from_raiz(raiz))
            except ValueError:
                pass
    if not keys and not raizes:
        return {}
    with conn.cursor() as cur:
        if keys and raizes:
            cur.execute(
                """
                SELECT * FROM confenge_company_target_fit_current
                WHERE company_key = ANY(%s) OR cnpj_raiz = ANY(%s)
                """,
                (list(keys), list(raizes)),
            )
        elif keys:
            cur.execute(
                """
                SELECT * FROM confenge_company_target_fit_current
                WHERE company_key = ANY(%s)
                """,
                (list(keys),),
            )
        else:
            cur.execute(
                """
                SELECT * FROM confenge_company_target_fit_current
                WHERE cnpj_raiz = ANY(%s)
                """,
                (list(raizes),),
            )
        rows = cur.fetchall() or []
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        d = dict(row) if not isinstance(row, dict) else dict(row)
        ck = str(d.get("company_key") or "")
        raiz = digits_only(d.get("cnpj_raiz"))[:8]
        if ck:
            out[ck] = d
        if raiz and len(raiz) == 8:
            out[raiz] = d
            out[f"cnpj_root:{raiz}"] = d
    return out


def enrich_row_with_published(
    row: dict[str, Any],
    published: dict[str, Any] | None,
    *,
    suppressed: bool = False,
    datalake_watermark: str = "",
) -> dict[str, Any]:
    """Stamp published materialization + suppression onto a universe/company row."""
    out = dict(row)
    if not published:
        return out
    out["published_target_fit"] = published
    out["target_fit_class"] = published.get("target_fit_class")
    out["target_fit_confidence"] = published.get("target_fit_confidence")
    out["target_fit_version"] = published.get("target_fit_version")
    out["target_fit_computed_at"] = published.get("computed_at")
    out["target_fit_source_watermark"] = published.get("source_watermark")
    out["target_fit_evidence"] = published.get("target_fit_evidence")
    out["target_fit_reason_codes"] = published.get("target_fit_reason_codes")
    out["target_fit_operational_status"] = published.get("operational_status")
    out["company_key"] = published.get("company_key") or out.get("company_key")
    if suppressed:
        out["target_fit_send_suppressed"] = True
        out["target_fit_suppressed"] = True
        reasons = list(out.get("suppression_reasons") or [])
        if "TARGET_FIT_DOWNGRADE" not in reasons:
            reasons.append("TARGET_FIT_DOWNGRADE")
        out["suppression_reasons"] = reasons
    if datalake_watermark:
        out["datalake_watermark"] = datalake_watermark
    return out


def _lookup_live(
    row: dict[str, Any] | None,
    *,
    conn: Any | None,
    published_index: dict[str, dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Resolve from store/index only. Live hit is sole commercial authority."""
    ck = company_key_from_row(row) if row else None
    raiz: str | None = None
    if row:
        cnpj = row.get("cnpj14") or row.get("cnpj") or row.get("cnpj_root")
        raiz = cnpj_raiz_from_cnpj14(cnpj) if cnpj else None
        if not raiz and row.get("cnpj_raiz"):
            raiz = digits_only(row.get("cnpj_raiz"))[:8]

    if published_index:
        if ck and ck in published_index:
            return dict(published_index[ck])
        if raiz and raiz in published_index:
            return dict(published_index[raiz])
        if raiz:
            alt = f"cnpj_root:{raiz}"
            if alt in published_index:
                return dict(published_index[alt])

    if conn is not None and ck:
        live = get_current(conn, ck)
        if live:
            return dict(live)
    return None


def _embed_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Offline/fixture path only — never used when a live store hit exists."""
    pub = row.get("published_target_fit") or row.get("target_fit_materialization")
    if isinstance(pub, dict) and pub.get("target_fit_class"):
        return dict(pub)
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
    return None


def published_from_row_or_db(
    row: dict[str, Any] | None,
    *,
    conn: Any | None = None,
    published_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Resolve published target-fit with explicit authority.

    Authority order (when live path is open — ``conn`` and/or ``published_index``):
      1. ``confenge_company_target_fit_current`` / batch index  (authoritative)
      2. Only if no live hit: embedded row stamps (offline fixtures)

    When live path is **not** open (conn is None and index is None):
      embedded fields only (unit tests / SHADOW-without-DSN).

    Never returns an embed when a live hit exists — stale JSONL CONFIRMED
    cannot authorize outreach while the store says OUT.
    """
    live_open = conn is not None or published_index is not None
    if live_open:
        live = _lookup_live(row, conn=conn, published_index=published_index)
        if live is not None:
            return live
        # Live path open but no row in store — do NOT fall back to embed.
        # Caller treats None as TARGET_FIT_MISSING / fail-closed for send.
        return None

    if row:
        return _embed_from_row(row)
    return None


def resolve_suppressed(
    conn: Any | None,
    *,
    company_key: str | None,
    row: dict[str, Any] | None = None,
) -> bool:
    """Suppression: live ledger wins when conn is open; row flags are additive offline."""
    if conn is not None and company_key:
        try:
            if bool(is_send_suppressed(conn, company_key)):
                return True
        except Exception:  # noqa: BLE001, S110 — ledger optional mid-migration
            pass
        # Live store class OUT after CONFIRMED is also a commercial block even
        # without an invalidation row (class is authority).
        try:
            cur = get_current(conn, company_key)
            if cur and str(cur.get("target_fit_class") or "") != TARGET_CONFIRMED:
                # Not automatically "suppressed" for research queues — class gate
                # already blocks send. Keep explicit ledger OR row flags only.
                pass
        except Exception:  # noqa: BLE001, S110 — current projection optional
            pass
    if row and (
        row.get("target_fit_suppressed")
        or row.get("target_fit_send_suppressed")
        or row.get("target_fit_downgrade")
        or "TARGET_FIT_DOWNGRADE" in (row.get("suppression_reasons") or [])
    ):
        return True
    return False


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
