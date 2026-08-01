"""Load multi-source observations from PostgreSQL lake + optional file artifacts.

Bridges the operational lake (opportunity_intel, official_acts) into the
EXTRA-MS-OPEN observation model without requiring pre-exported CSVs.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Any

from scripts.ops.multi_source_open_pack.events import classify_event
from scripts.ops.multi_source_open_pack.loaders import (
    load_ciga_observations,
    load_sc_compras_observations,
)
from scripts.ops.multi_source_open_pack.models import SourceObservation
from scripts.ops.multi_source_open_pack.textutil import optional_float

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _obs_from_row(
    *,
    fonte: str,
    fonte_papel: str,
    id_externo: str,
    orgao: str,
    orgao_cnpj: str,
    municipio: str,
    uf: str,
    objeto: str,
    modalidade: str,
    valor_estimado: Any,
    data_publicacao: str,
    data_abertura: str,
    data_encerramento: str,
    url: str,
    status_fonte: str,
    categoria_ato: str,
    raw: dict[str, Any] | None = None,
) -> SourceObservation:
    oid = f"{fonte}:{id_externo or hash((orgao, (objeto or '')[:80], data_publicacao))}"
    event_type, is_active, excl = classify_event(
        categoria_ato=categoria_ato,
        objeto=objeto or "",
        status_fonte=status_fonte,
        fonte=fonte,
    )
    return SourceObservation(
        observation_id=oid,
        fonte=fonte,
        fonte_papel=fonte_papel,
        id_externo=str(id_externo or ""),
        orgao=orgao or "",
        orgao_cnpj=orgao_cnpj or "",
        municipio=municipio or "",
        uf=uf or "SC",
        objeto=(objeto or "")[:2000],
        modalidade=modalidade or "",
        valor_estimado=optional_float(valor_estimado),
        data_publicacao=str(data_publicacao or ""),
        data_abertura=str(data_abertura or ""),
        data_encerramento=str(data_encerramento or ""),
        url=str(url or ""),
        status_fonte=status_fonte or "",
        categoria_ato=categoria_ato or "",
        raw=raw or {},
        event_type=event_type,
        is_active_dispute=is_active,
        exclusion_reason=excl,
    )


def _q(conn: Any, sql: str, params: tuple | list | None = None) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        return [dict(r) for r in rows]


def _table_exists(conn: Any, name: str) -> bool:
    rows = _q(
        conn,
        """
        SELECT 1 AS ok
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (name,),
    )
    return bool(rows)


def _fonte_papel(source: str) -> str:
    s = (source or "").lower()
    if s in {"pncp", "pncp_opportunities", "test_batch"}:
        return "required"
    if s in {"ciga_ckan", "ciga", "dom_sc", "ciga_dom"}:
        return "required_municipal"
    if s in {"sc_compras"}:
        return "complementary_estadual"
    if s in {"pcp", "compras_gov", "doe_sc", "tce_sc"}:
        return "complementary"
    return "gap_fill"


def _normalize_source_key(source: str) -> str:
    s = (source or "").strip().lower()
    if s in {"pncp", "pncp_opportunities", "test_batch"}:
        return "pncp"
    if s in {"ciga", "ciga_dom", "dom_sc"}:
        return "ciga_ckan"
    return s or "unknown"


def load_opportunity_intel_observations(
    conn: Any,
    *,
    limit: int = 5000,
    statuses: tuple[str, ...] = ("open", "upcoming"),
) -> list[SourceObservation]:
    """Load active opportunities from opportunity_intel as observations."""
    if not _table_exists(conn, "opportunity_intel"):
        return []
    placeholders = ",".join(["%s"] * len(statuses))
    rows = _q(
        conn,
        f"""
        SELECT id, source, source_id, numero_controle_pncp, orgao_cnpj, orgao_nome,
               municipio, uf, objeto, modalidade, valor_estimado,
               status_canonico, data_publicacao, data_abertura, data_encerramento,
               link_edital, source_url, run_id, crawl_batch_id, proveniencia
        FROM opportunity_intel
        WHERE COALESCE(is_active, TRUE)
          AND status_canonico IN ({placeholders})
        ORDER BY
          CASE status_canonico WHEN 'open' THEN 0 WHEN 'upcoming' THEN 1 ELSE 2 END,
          data_encerramento NULLS LAST,
          updated_at DESC NULLS LAST
        LIMIT %s
        """,  # noqa: S608 — placeholders only
        (*statuses, limit),
    )
    out: list[SourceObservation] = []
    for r in rows:
        fonte = _normalize_source_key(str(r.get("source") or "pncp"))
        ext = r.get("numero_controle_pncp") or r.get("source_id") or str(r.get("id") or "")
        url = r.get("link_edital") or r.get("source_url") or ""
        if not url and r.get("numero_controle_pncp"):
            # PNCP public portal pattern when only control number is known
            url = f"https://pncp.gov.br/app/editais/{r['numero_controle_pncp']}"
        out.append(
            _obs_from_row(
                fonte=fonte,
                fonte_papel=_fonte_papel(fonte),
                id_externo=str(ext),
                orgao=str(r.get("orgao_nome") or ""),
                orgao_cnpj=str(r.get("orgao_cnpj") or ""),
                municipio=str(r.get("municipio") or ""),
                uf=str(r.get("uf") or "SC"),
                objeto=str(r.get("objeto") or ""),
                modalidade=str(r.get("modalidade") or ""),
                valor_estimado=r.get("valor_estimado"),
                data_publicacao=str(r.get("data_publicacao") or ""),
                data_abertura=str(r.get("data_abertura") or ""),
                data_encerramento=str(r.get("data_encerramento") or ""),
                url=str(url or ""),
                status_fonte=str(r.get("status_canonico") or "open"),
                categoria_ato="edital_aberto",
                raw=dict(r),
            )
        )
    return out


def load_official_acts_observations(
    conn: Any,
    *,
    limit: int = 5000,
    lookback_days: int = 45,
) -> list[SourceObservation]:
    """Load recent official_acts (CIGA/DOM etc.) when table has data."""
    if not _table_exists(conn, "official_acts"):
        return []
    rows = _q(
        conn,
        """
        SELECT id, source, external_id, source_url, title, category,
               publication_date, orgao_nome, municipio, raw_json, run_id
        FROM official_acts
        WHERE COALESCE(publication_date, ingested_at::date)
              >= CURRENT_DATE - (%s || ' days')::interval
        ORDER BY publication_date DESC NULLS LAST
        LIMIT %s
        """,
        (lookback_days, limit),
    )
    out: list[SourceObservation] = []
    for r in rows:
        fonte = _normalize_source_key(str(r.get("source") or "ciga_ckan"))
        if fonte == "pncp":
            fonte = "ciga_ckan"  # acts table is not PNCP open tenders
        cat = str(r.get("category") or "publicacao_dom")
        out.append(
            _obs_from_row(
                fonte=fonte if fonte != "unknown" else "ciga_ckan",
                fonte_papel="required_municipal",
                id_externo=str(r.get("external_id") or r.get("id") or ""),
                orgao=str(r.get("orgao_nome") or ""),
                orgao_cnpj="",
                municipio=str(r.get("municipio") or ""),
                uf="SC",
                objeto=str(r.get("title") or ""),
                modalidade=cat,
                valor_estimado="",
                data_publicacao=str(r.get("publication_date") or ""),
                data_abertura="",
                data_encerramento="",
                url=str(r.get("source_url") or ""),
                status_fonte="publicacao_dom",
                categoria_ato=cat,
                raw=dict(r),
            )
        )
    return out


def discover_ciga_jsonl(search_roots: list[Path] | None = None) -> Path | None:
    """Return newest CIGA publications.jsonl under known output paths."""
    roots = search_roots or [
        PROJECT_ROOT / "output" / "ciga_dom",
        PROJECT_ROOT / "output" / "ciga-ckan",
    ]
    candidates: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        candidates.extend(root.glob("**/publications.jsonl"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def discover_sc_compras_jsonl(search_roots: list[Path] | None = None) -> Path | None:
    roots = search_roots or [
        PROJECT_ROOT / "output" / "sc_compras",
        PROJECT_ROOT / "output" / "resilience",
    ]
    candidates: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        candidates.extend(root.glob("**/*sc_compras*.jsonl"))
        candidates.extend(root.glob("**/open*.jsonl"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def export_pncp_csv(observations: list[SourceObservation], path: Path) -> Path:
    """Write PNCP-shaped CSV for multi_source pack loaders (interop)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "numero_controle_pncp",
        "source_id",
        "orgao_nome",
        "orgao_cnpj",
        "municipio",
        "uf",
        "objeto",
        "modalidade",
        "valor_estimado",
        "data_publicacao",
        "data_abertura",
        "data_encerramento",
        "link_edital",
        "source_url",
        "status_canonico",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for o in observations:
            if o.fonte != "pncp":
                continue
            w.writerow(
                {
                    "numero_controle_pncp": o.id_externo,
                    "source_id": o.id_externo,
                    "orgao_nome": o.orgao,
                    "orgao_cnpj": o.orgao_cnpj,
                    "municipio": o.municipio,
                    "uf": o.uf,
                    "objeto": o.objeto,
                    "modalidade": o.modalidade,
                    "valor_estimado": o.valor_estimado if o.valor_estimado is not None else "",
                    "data_publicacao": o.data_publicacao,
                    "data_abertura": o.data_abertura,
                    "data_encerramento": o.data_encerramento,
                    "link_edital": o.url,
                    "source_url": o.url,
                    "status_canonico": o.status_fonte or "open",
                }
            )
    return path


def load_all_lake_observations(
    conn: Any,
    *,
    as_of: date | None = None,
    ciga_path: Path | None = None,
    sc_path: Path | None = None,
    ciga_lookback_days: int = 45,
    opp_limit: int = 5000,
    auto_discover_files: bool = True,
) -> tuple[list[SourceObservation], dict[str, Any]]:
    """Combine lake + optional file artifacts into one observation list."""
    as_of = as_of or date.today()
    meta: dict[str, Any] = {
        "as_of": as_of.isoformat(),
        "sources_loaded": {},
        "file_artifacts": {},
    }
    rows: list[SourceObservation] = []

    opp = load_opportunity_intel_observations(conn, limit=opp_limit)
    rows.extend(opp)
    meta["sources_loaded"]["opportunity_intel"] = len(opp)

    acts = load_official_acts_observations(conn, lookback_days=ciga_lookback_days)
    rows.extend(acts)
    meta["sources_loaded"]["official_acts"] = len(acts)

    if ciga_path is None and auto_discover_files:
        ciga_path = discover_ciga_jsonl()
    if ciga_path and ciga_path.is_file():
        ciga_rows = load_ciga_observations(ciga_path, as_of, ciga_lookback_days)
        rows.extend(ciga_rows)
        meta["sources_loaded"]["ciga_file"] = len(ciga_rows)
        meta["file_artifacts"]["ciga"] = str(ciga_path)
    else:
        meta["file_artifacts"]["ciga"] = None

    if sc_path is None and auto_discover_files:
        sc_path = discover_sc_compras_jsonl()
    if sc_path and sc_path.is_file():
        sc_rows = load_sc_compras_observations(sc_path, as_of)
        rows.extend(sc_rows)
        meta["sources_loaded"]["sc_compras_file"] = len(sc_rows)
        meta["file_artifacts"]["sc_compras"] = str(sc_path)
    else:
        meta["file_artifacts"]["sc_compras"] = None

    meta["total_observations"] = len(rows)
    by_fonte: dict[str, int] = {}
    for o in rows:
        by_fonte[o.fonte] = by_fonte.get(o.fonte, 0) + 1
    meta["by_fonte"] = by_fonte
    return rows, meta


__all__ = [
    "discover_ciga_jsonl",
    "discover_sc_compras_jsonl",
    "export_pncp_csv",
    "load_all_lake_observations",
    "load_official_acts_observations",
    "load_opportunity_intel_observations",
]
