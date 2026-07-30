"""Canonical supplier registry (CNAE / cadastro) for commercial sector fit.

Never invents cadastral data. Missing → NOT_COMPUTABLE.
CNPJ is the join key. Source and date are mandatory for each row.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.commercial_leads.dbutil import fetch_all

RULE_VERSION = "supplier-registry-v1"
NOT_COMPUTABLE = "NOT_COMPUTABLE"

# Sources that may be counted as RFB-authority / official cadastral for
# ``official_registry_coverage``. Redistributors (BrasilAPI, MinhaReceita, etc.)
# are operational fallback only and MUST NOT inflate official coverage to 1.0.
OFFICIAL_REGISTRY_SOURCE_MARKERS: tuple[str, ...] = (
    "receita_federal",
    "rfb_",
    "rfb-",
    "dados_abertos_cnpj",
    "cnpj_rfb",
    "public_cadastral_via_opencnpj",  # OpenCNPJ serving RFB public dataset
    "rfb_public_cadastral",
)


def is_official_registry_source(source: str | None) -> bool:
    """True only for RFB-authority / official open-data lineage labels."""
    if not source:
        return False
    s = str(source).strip().lower()
    if not s:
        return False
    if "fallback" in s:
        return False
    if s in {"brasilapi", "minhareceita", "cnpjws", "opencnpj"}:
        return False
    return any(marker in s for marker in OFFICIAL_REGISTRY_SOURCE_MARKERS)


@dataclass
class SupplierRegistryRecord:
    cnpj14: str
    razao_social: str | None = None
    nome_fantasia: str | None = None
    cnae_principal: str | None = None
    cnaes_secundarios: list[str] = field(default_factory=list)
    situacao_cadastral: str | None = None
    data_situacao: str | None = None
    municipio: str | None = None
    uf: str | None = None
    source: str | None = None
    source_version: str | None = None
    source_date: str | None = None
    ingested_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def has_cnae_principal(self) -> bool:
        return bool(self.cnae_principal and str(self.cnae_principal).strip())

    @property
    def is_official_source(self) -> bool:
        return is_official_registry_source(self.source)

    @property
    def is_inactive(self) -> bool:
        sit = (self.situacao_cadastral or "").upper()
        return sit in {"BAIXADA", "INAPTA", "SUSPENSA", "NULA", "INATIVA"}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_registry_table(conn: Any) -> None:
    """Create supplier_registry if missing (additive; also covered by migration 063)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS public.supplier_registry (
                cnpj14              TEXT PRIMARY KEY,
                razao_social        TEXT,
                nome_fantasia       TEXT,
                cnae_principal      TEXT,
                cnaes_secundarios   JSONB NOT NULL DEFAULT '[]'::jsonb,
                situacao_cadastral  TEXT,
                data_situacao       DATE,
                municipio           TEXT,
                uf                  TEXT,
                source              TEXT NOT NULL,
                source_version      TEXT NOT NULL,
                source_date         DATE NOT NULL,
                ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_supplier_registry_cnae
            ON public.supplier_registry (cnae_principal)
            """
        )
    conn.commit()


def upsert_registry_rows(conn: Any, rows: list[dict[str, Any]]) -> int:
    """Upsert registry rows. Requires source, source_version, source_date, cnpj14."""
    if not rows:
        return 0
    from psycopg2.extras import Json

    n = 0
    with conn.cursor() as cur:
        for row in rows:
            cnpj = re_cnpj14(row.get("cnpj14"))
            if not cnpj:
                continue
            source = row.get("source")
            source_version = row.get("source_version") or "unknown"
            source_date = row.get("source_date")
            if not source or not source_date:
                raise ValueError(f"registry row missing source provenance for {cnpj}")
            # Sanitize data_situacao — APIs sometimes return "0" / garbage
            data_sit = row.get("data_situacao")
            if data_sit is not None:
                s = str(data_sit).strip()
                if len(s) < 8 or s in {"0", "00", "0000-00-00", "None", "null"}:
                    data_sit = None
                else:
                    data_sit = s[:10]
            cur.execute(
                """
                INSERT INTO public.supplier_registry (
                    cnpj14, razao_social, nome_fantasia, cnae_principal,
                    cnaes_secundarios, situacao_cadastral, data_situacao,
                    municipio, uf, source, source_version, source_date, ingested_at
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now()
                )
                ON CONFLICT (cnpj14) DO UPDATE SET
                    razao_social = EXCLUDED.razao_social,
                    nome_fantasia = EXCLUDED.nome_fantasia,
                    cnae_principal = EXCLUDED.cnae_principal,
                    cnaes_secundarios = EXCLUDED.cnaes_secundarios,
                    situacao_cadastral = EXCLUDED.situacao_cadastral,
                    data_situacao = EXCLUDED.data_situacao,
                    municipio = EXCLUDED.municipio,
                    uf = EXCLUDED.uf,
                    source = EXCLUDED.source,
                    source_version = EXCLUDED.source_version,
                    source_date = EXCLUDED.source_date,
                    ingested_at = now()
                """,
                (
                    cnpj,
                    row.get("razao_social"),
                    row.get("nome_fantasia"),
                    row.get("cnae_principal"),
                    Json(list(row.get("cnaes_secundarios") or [])),
                    row.get("situacao_cadastral"),
                    data_sit,
                    row.get("municipio"),
                    row.get("uf"),
                    source,
                    source_version,
                    source_date,
                ),
            )
            n += 1
    conn.commit()
    return n


def re_cnpj14(raw: Any) -> str | None:
    import re

    digits = re.sub(r"\D", "", str(raw or ""))
    if len(digits) == 14:
        return digits
    if len(digits) == 11:
        return None  # CPF not accepted
    if len(digits) > 14:
        return digits[-14:]
    return None


def load_registry_map(conn: Any, cnpjs: list[str]) -> dict[str, SupplierRegistryRecord]:
    """Load registry records for CNPJs. Missing keys → absent (NOT_COMPUTABLE)."""
    cleaned = [c for c in (re_cnpj14(x) for x in cnpjs) if c]
    if not cleaned:
        return {}
    # batch
    out: dict[str, SupplierRegistryRecord] = {}
    batch_size = 500
    for i in range(0, len(cleaned), batch_size):
        batch = cleaned[i : i + batch_size]
        rows = fetch_all(
            conn,
            """
            SELECT cnpj14, razao_social, nome_fantasia, cnae_principal,
                   cnaes_secundarios, situacao_cadastral, data_situacao,
                   municipio, uf, source, source_version, source_date, ingested_at
            FROM public.supplier_registry
            WHERE cnpj14 = ANY(%s)
            """,
            (batch,),
        )
        for r in rows:
            secs = r.get("cnaes_secundarios") or []
            if isinstance(secs, str):
                try:
                    secs = json.loads(secs)
                except json.JSONDecodeError:
                    secs = []
            out[str(r["cnpj14"])] = SupplierRegistryRecord(
                cnpj14=str(r["cnpj14"]),
                razao_social=r.get("razao_social"),
                nome_fantasia=r.get("nome_fantasia"),
                cnae_principal=r.get("cnae_principal"),
                cnaes_secundarios=list(secs) if isinstance(secs, list) else [],
                situacao_cadastral=r.get("situacao_cadastral"),
                data_situacao=str(r["data_situacao"]) if r.get("data_situacao") else None,
                municipio=r.get("municipio"),
                uf=r.get("uf"),
                source=r.get("source"),
                source_version=r.get("source_version"),
                source_date=str(r["source_date"]) if r.get("source_date") else None,
                ingested_at=str(r["ingested_at"]) if r.get("ingested_at") else None,
            )
    return out


def coverage_report(
    registry: dict[str, SupplierRegistryRecord],
    *,
    all_candidates: list[str],
    top100: list[str] | None = None,
    top20: list[str] | None = None,
    resolution_status: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Coverage BEFORE publication.

    Top-20-only coverage is never sufficient. Require either:
      registry_coverage_all_candidates == 100%, or
      registry_resolved_or_definitively_not_found == 100%
    with explicit non-transient status per missing CNPJ.
    """
    definitive = {
        "NOT_FOUND_IN_OFFICIAL_DATASET",
        "INVALID_CNPJ",
        "REGISTRY_DATA_CORRUPT",
        "NOT_COMPUTABLE",
    }
    transient = {"LOOKUP_TRANSIENT_FAILURE"}
    resolution_status = resolution_status or {}

    def _cov(cnpjs: list[str]) -> dict[str, Any]:
        if not cnpjs:
            return {
                "n": 0,
                "with_registry": 0,
                "coverage": None,
                "cnae_primary_coverage": None,
                "cnae_secondary_coverage": None,
                "status": NOT_COMPUTABLE,
            }
        with_reg = [c for c in cnpjs if c in registry]
        with_cnae = [c for c in with_reg if registry[c].has_cnae_principal]
        with_sec = [c for c in with_reg if registry[c].cnaes_secundarios]
        n = len(cnpjs)
        return {
            "n": n,
            "with_registry": len(with_reg),
            "coverage": round(len(with_reg) / n, 4) if n else None,
            "cnae_primary_coverage": round(len(with_cnae) / n, 4) if n else None,
            "cnae_secondary_coverage": round(len(with_sec) / n, 4) if n else None,
            "status": "OK" if with_reg else NOT_COMPUTABLE,
        }

    top100 = top100 or []
    top20 = top20 or []
    all_cov = _cov(all_candidates)
    missing = [c for c in all_candidates if c not in registry]
    resolved_or_definitive = 0
    official_resolved = 0
    status_counts: dict[str, int] = {}
    source_distribution: dict[str, int] = {}
    for c in all_candidates:
        if c in registry:
            resolved_or_definitive += 1
            rec = registry[c]
            src = (rec.source or "unknown").strip() or "unknown"
            source_distribution[src] = source_distribution.get(src, 0) + 1
            if rec.is_official_source:
                official_resolved += 1
                status_counts["RESOLVED_OFFICIAL"] = status_counts.get("RESOLVED_OFFICIAL", 0) + 1
            else:
                status_counts["RESOLVED_FALLBACK"] = status_counts.get("RESOLVED_FALLBACK", 0) + 1
            # Legacy aggregate for operational gates (any row present)
            status_counts["RESOLVED"] = status_counts.get("RESOLVED", 0) + 1
            continue
        st = resolution_status.get(c) or "LOOKUP_TRANSIENT_FAILURE"
        status_counts[st] = status_counts.get(st, 0) + 1
        if st in definitive and st not in transient:
            resolved_or_definitive += 1
    n_all = len(all_candidates) or 1
    resolved_rate = round(resolved_or_definitive / n_all, 4) if all_candidates else None
    official_rate = (
        round(official_resolved / len(all_candidates), 4) if all_candidates else None
    )

    report = {
        "rule_version": RULE_VERSION,
        "generated_at": utc_now(),
        "registry_coverage_all_candidates": all_cov,
        "registry_coverage_top100": _cov(top100),
        "registry_coverage_top20": _cov(top20),
        "cnae_primary_coverage": all_cov.get("cnae_primary_coverage"),
        "cnae_secondary_coverage": all_cov.get("cnae_secondary_coverage"),
        "registry_freshness": None,
        "top20_coverage_100pct": False,
        "registry_universe_resolved": all_cov.get("coverage") == 1.0,
        "registry_resolved_or_definitively_not_found": resolved_rate,
        "registry_resolution_status_counts": status_counts,
        "source_distribution": source_distribution,
        # RFB-authority share only — never equal to operational row presence when
        # redistributor fallbacks fill the universe.
        "official_registry_coverage": official_rate,
        "official_resolved_n": official_resolved,
        "fallback_resolved_n": max(0, resolved_or_definitive - official_resolved)
        if all_candidates
        else 0,
        "missing_candidates_sample": missing[:50],
        "missing_candidates_n": len(missing),
        "block_reason": None,
        "selection_bias_risk": False,
    }
    t20 = report["registry_coverage_top20"]
    if t20.get("n") and t20.get("coverage") == 1.0 and t20.get("cnae_primary_coverage") == 1.0:
        report["top20_coverage_100pct"] = True
    else:
        report["block_reason"] = "BLOCKED_MISSING_SUPPLIER_SECTOR_DATA"
        report["top20_coverage_100pct"] = False

    # Endogenous coverage: top20 complete while universe incomplete → selection bias
    all_rate = all_cov.get("coverage") or 0.0
    if report["top20_coverage_100pct"] and all_rate < 1.0 and (resolved_rate or 0) < 1.0:
        report["selection_bias_risk"] = True
        report["block_reason"] = "BLOCKED_REGISTRY_SELECTION_BIAS"
    elif all_rate < 1.0 and (resolved_rate or 0) < 1.0:
        report["block_reason"] = "BLOCKED_REGISTRY_SELECTION_BIAS"
        report["selection_bias_risk"] = True
    elif all_rate == 1.0 or resolved_rate == 1.0:
        # Universe resolved; keep top20 data-quality block if any
        if report["block_reason"] == "BLOCKED_REGISTRY_SELECTION_BIAS":
            report["block_reason"] = None
        report["selection_bias_risk"] = False

    # freshness from loaded records
    dates = [r.source_date for r in registry.values() if r.source_date]
    if dates:
        report["registry_freshness"] = {"min_source_date": min(dates), "max_source_date": max(dates)}
    else:
        report["registry_freshness"] = NOT_COMPUTABLE
    return report


def ingest_from_jsonl(conn: Any, path: str | Path) -> dict[str, Any]:
    """Ingest versioned cadastral dataset from JSONL."""
    ensure_registry_table(conn)
    p = Path(path)
    rows: list[dict[str, Any]] = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    n = upsert_registry_rows(conn, rows)
    return {"ingested": n, "path": str(p), "source": "jsonl"}
