"""Bridge: official local registry → existing supplier_registry (no second pipeline)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Iterable

from scripts.company_registry.lookup import batch_lookup, lookup_cnpj, read_active_pointer
from scripts.company_registry.models import OfficialMatchStatus, SITUACAO_BLOCK_PROMOTION
from scripts.company_registry.normalization import is_valid_cnpj14, normalize_cnpj14
from scripts.commercial_leads.supplier_registry import (
    ensure_registry_table,
    is_official_registry_source,
    upsert_registry_rows,
)

DEFAULT_OFFICIAL_SOURCE = "rfb_public_cadastral"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def require_active_release() -> dict[str, Any]:
    ptr = read_active_pointer()
    if not ptr or ptr.get("status") != "ACTIVE":
        return {
            "ok": False,
            "status": "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE",
            "pointer": ptr,
        }
    return {"ok": True, "pointer": ptr, "release_id": ptr.get("release_id")}


def publish_matches_to_supplier_registry(
    conn: Any,
    cnpjs: Iterable[str],
    *,
    source: str | None = None,
    source_date: str | None = None,
) -> dict[str, Any]:
    """Upsert MATCHED official rows into supplier_registry with RFB-authority labels."""
    active = require_active_release()
    if not active["ok"]:
        return active

    release_id = str(active["release_id"])
    src = source or DEFAULT_OFFICIAL_SOURCE
    if not is_official_registry_source(src):
        raise ValueError(
            f"source_not_official:{src} — use rfb_public_cadastral or rfb_* label"
        )
    ensure_registry_table(conn)
    rows: list[dict[str, Any]] = []
    resolution: dict[str, str] = {}
    stats = {
        "matched": 0,
        "not_found": 0,
        "invalid": 0,
        "missing": 0,
        "unavailable": 0,
        "blocked_situacao": 0,
    }
    for raw in cnpjs:
        rec = lookup_cnpj(raw)
        st = rec.official_match_status
        if st == OfficialMatchStatus.MISSING_CNPJ.value:
            stats["missing"] += 1
            resolution[str(raw)] = st
            continue
        if st == OfficialMatchStatus.INVALID_CNPJ.value:
            stats["invalid"] += 1
            resolution[rec.cnpj or str(raw)] = st
            continue
        if st == OfficialMatchStatus.OFFICIAL_REGISTRY_UNAVAILABLE.value:
            stats["unavailable"] += 1
            resolution[rec.cnpj] = st
            continue
        if st == OfficialMatchStatus.NOT_FOUND_IN_OFFICIAL_RELEASE.value:
            stats["not_found"] += 1
            resolution[rec.cnpj] = "NOT_FOUND_IN_OFFICIAL_DATASET"
            continue
        if st != OfficialMatchStatus.MATCHED.value:
            resolution[rec.cnpj] = st
            continue
        sit = (rec.registration_status or "").upper()
        if sit in SITUACAO_BLOCK_PROMOTION:
            stats["blocked_situacao"] += 1
            # still publish row for transparency, commercial gates exclude
        rows.append(
            {
                "cnpj14": rec.cnpj,
                "razao_social": rec.legal_name,
                "nome_fantasia": rec.trade_name,
                "cnae_principal": rec.primary_cnae,
                "cnaes_secundarios": rec.secondary_cnaes,
                "situacao_cadastral": rec.registration_status,
                "data_situacao": rec.registration_status_date,
                "municipio": rec.city,
                "uf": rec.state,
                "source": src,
                "source_version": release_id,
                "source_date": source_date or date.today().isoformat(),
            }
        )
        resolution[rec.cnpj] = "RESOLVED_OFFICIAL"
        stats["matched"] += 1

    n = upsert_registry_rows(conn, rows) if rows else 0
    return {
        "ok": True,
        "upserted": n,
        "stats": stats,
        "resolution_status": resolution,
        "active_official_registry_release": release_id,
        "source": src,
        "published_at": utc_now(),
    }


def fail_closed_commercial_precheck() -> dict[str, Any]:
    """Gate used by commercial cycle: ACTIVE release required."""
    active = require_active_release()
    if not active["ok"]:
        return {
            "ok": False,
            "gate": "FAIL_CLOSED",
            "reason": "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE",
            "detail": active,
        }
    return {
        "ok": True,
        "gate": "PASS",
        "active_official_registry_release": active["release_id"],
        "pointer": active["pointer"],
    }


def enrich_lead_from_official(lead: dict[str, Any]) -> dict[str, Any]:
    """Attach official fields + provenance onto a lead dict (non-destructive)."""
    cnpj = normalize_cnpj14(lead.get("cnpj14") or lead.get("cnpj"))
    out = dict(lead)
    if not cnpj or not is_valid_cnpj14(cnpj):
        out["official_match_status"] = (
            OfficialMatchStatus.INVALID_CNPJ.value
            if cnpj
            else OfficialMatchStatus.MISSING_CNPJ.value
        )
        return out
    rec = lookup_cnpj(cnpj)
    out["official"] = rec.as_dict()
    out["official_match_status"] = rec.official_match_status
    out["official_release_id"] = rec.official_release_id
    if rec.official_match_status == OfficialMatchStatus.MATCHED.value:
        # RFB is authority for cadastral fields — do not overwrite contract facts
        out["razao_social_oficial"] = rec.legal_name
        out["nome_fantasia_oficial"] = rec.trade_name
        out["situacao_cadastral"] = rec.registration_status
        out["cnae_principal"] = rec.primary_cnae
        out["cnaes_secundarios"] = rec.secondary_cnaes
        out["porte"] = rec.company_size
        out["municipio_oficial"] = rec.city
        out["uf_oficial"] = rec.state
        out["registry_source"] = (rec.source_provenance or {}).get(
            "source_label", DEFAULT_OFFICIAL_SOURCE
        )
        out["registry_is_official"] = True
        out["registry_resolution_status"] = "RESOLVED_OFFICIAL"
    return out
