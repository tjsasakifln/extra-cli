#!/usr/bin/env python3
"""Session pipeline: load acts → resolve entities → classify → recalc coverage 200km.

Operational script for epic/coverage-200km-operational. Produces:
  - output/session-YYYY-MM-DD/coverage_canonical.json
  - output/session-YYYY-MM-DD/entities_covered.jsonl
  - output/session-YYYY-MM-DD/entities_uncovered.jsonl
  - output/session-YYYY-MM-DD/entity_crosswalk.jsonl
  - output/session-YYYY-MM-DD/radar_opportunities.jsonl
  - updates entity_coverage for resolved opportunity-relevant acts

Does NOT modify DOD.md or executive HTML.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.coverage.commercial_status import (  # noqa: E402
    OPPORTUNITY_ACT_CATEGORIES,
    STRICT_OPPORTUNITY_STATUSES,
    classify_commercial,
)
from scripts.coverage.sector_engineering import classify_sector  # noqa: E402
from scripts.lib.name_normalizer import normalize_name  # noqa: E402
from scripts.matching.entity_matcher import generate_name_aliases  # noqa: E402

SESSION_DATE = date.today().isoformat()
OUT_DIR = _PROJECT_ROOT / "output" / f"session-{SESSION_DATE}"
DENOMINATOR = 1093

# Categories that count as commercial opportunity evidence for coverage
COVERAGE_ACT_CATEGORIES = OPPORTUNITY_ACT_CATEGORIES | {
    "retificacao",  # only with parent opportunity context — still procurement notice
}


def _load_dotenv() -> None:
    env_path = _PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def _norm_muni(s: str | None) -> str:
    if not s:
        return ""
    t = _strip_accents(s).upper().strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"^(MUNICIPIO DE |MUNICÍPIO DE |PREFEITURA MUNICIPAL DE |PREFEITURA DE )", "", t)
    return t.strip()


def connect():
    import psycopg2

    _load_dotenv()
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg2.connect(dsn, connect_timeout=15)


def load_universe(conn) -> list[dict[str, Any]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, razao_social, cnpj_8, municipio, codigo_ibge, natureza_juridica
        FROM sc_public_entities
        WHERE is_active = TRUE AND raio_200km = TRUE
        ORDER BY id
        """
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def build_entity_indexes(entities: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {e["id"]: e for e in entities}
    name_index: dict[str, list[dict]] = defaultdict(list)
    name_muni: dict[tuple[str, str], list[dict]] = defaultdict(list)
    muni_prefeitura: dict[str, list[dict]] = defaultdict(list)
    cnpj8: dict[str, dict] = {}

    for e in entities:
        nn = normalize_name(e.get("razao_social") or "")
        muni = _norm_muni(e.get("municipio"))
        if nn:
            name_index[nn].append(e)
            for alias in generate_name_aliases(nn):
                name_index[alias].append(e)
            if muni:
                name_muni[(nn, muni)].append(e)
                for alias in generate_name_aliases(nn):
                    name_muni[(alias, muni)].append(e)
        if e.get("cnpj_8"):
            cnpj8[e["cnpj_8"]] = e
        # Prefer prefeitura / município as municipal executive match
        nat = (e.get("natureza_juridica") or "").lower()
        rs = (e.get("razao_social") or "").upper()
        if muni and (
            "prefeitura" in rs
            or "municipio" in rs
            or "município" in (e.get("razao_social") or "").lower()
            or "executivo municipal" in nat
            or nat.strip() == "município"
            or "municipio" in nat
        ):
            muni_prefeitura[muni].append(e)

    return {
        "by_id": by_id,
        "name_index": name_index,
        "name_muni": name_muni,
        "muni_prefeitura": muni_prefeitura,
        "cnpj8": cnpj8,
    }


def resolve_entity(
    *,
    orgao_nome: str | None,
    municipio: str | None,
    orgao_cnpj: str | None,
    indexes: dict[str, Any],
) -> dict[str, Any]:
    """Conservative entity resolution. Returns match metadata."""
    cnpj_digits = re.sub(r"\D", "", orgao_cnpj or "")
    if len(cnpj_digits) >= 8:
        base = cnpj_digits[:8]
        ent = indexes["cnpj8"].get(base)
        if ent:
            return {
                "status": "matched_exact",
                "rule": "cnpj_base8",
                "score": 1.0,
                "canonical_entity_id": ent["id"],
                "canonical_name": ent["razao_social"],
                "municipio": ent.get("municipio"),
                "reversible": True,
            }

    nn = normalize_name(orgao_nome or "")
    muni = _norm_muni(municipio)
    if not nn and not muni:
        return {
            "status": "unresolved",
            "rule": "empty_identity",
            "score": 0.0,
            "canonical_entity_id": None,
            "canonical_name": None,
            "municipio": None,
            "reversible": True,
        }

    # name + municipio exact
    if nn and muni:
        hits = indexes["name_muni"].get((nn, muni), [])
        if len(hits) == 1:
            ent = hits[0]
            return {
                "status": "matched_exact",
                "rule": "name_normalized+municipio",
                "score": 0.95,
                "canonical_entity_id": ent["id"],
                "canonical_name": ent["razao_social"],
                "municipio": ent.get("municipio"),
                "reversible": True,
            }
        if len(hits) > 1:
            return {
                "status": "ambiguous",
                "rule": "name_normalized+municipio",
                "score": 0.5,
                "canonical_entity_id": None,
                "canonical_name": None,
                "municipio": muni,
                "candidates": [h["id"] for h in hits[:5]],
                "reversible": True,
            }

        # alias forms
        for alias in generate_name_aliases(nn):
            hits = indexes["name_muni"].get((alias, muni), [])
            if len(hits) == 1:
                ent = hits[0]
                return {
                    "status": "matched_alias",
                    "rule": "alias+municipio",
                    "score": 0.9,
                    "canonical_entity_id": ent["id"],
                    "canonical_name": ent["razao_social"],
                    "municipio": ent.get("municipio"),
                    "reversible": True,
                }

    # name only (state organs often have municipio SANTA CATARINA)
    if nn:
        hits = indexes["name_index"].get(nn, [])
        if len(hits) == 1:
            ent = hits[0]
            return {
                "status": "matched_exact",
                "rule": "name_normalized_unique",
                "score": 0.88,
                "canonical_entity_id": ent["id"],
                "canonical_name": ent["razao_social"],
                "municipio": ent.get("municipio"),
                "reversible": True,
            }
        for alias in generate_name_aliases(nn):
            hits = indexes["name_index"].get(alias, [])
            if len(hits) == 1:
                ent = hits[0]
                return {
                    "status": "matched_alias",
                    "rule": "alias_unique",
                    "score": 0.85,
                    "canonical_entity_id": ent["id"],
                    "canonical_name": ent["razao_social"],
                    "municipio": ent.get("municipio"),
                    "reversible": True,
                }

    # Municipal executive fallback: "Prefeitura municipal de X" → prefeitura in universe
    if muni and re.search(r"PREFEITURA|MUNICIPIO DE", nn):
        prefs = indexes["muni_prefeitura"].get(muni, [])
        # Also try extracting city from org name
        m = re.search(
            r"(?:PREFEITURA(?: MUNICIPAL)? DE |MUNICIPIO DE )(.+)$",
            nn,
        )
        if m:
            city = _norm_muni(m.group(1))
            prefs = indexes["muni_prefeitura"].get(city, []) or prefs
            muni = city or muni
        if len(prefs) == 1:
            ent = prefs[0]
            return {
                "status": "matched_alias",
                "rule": "municipio_prefeitura_executive",
                "score": 0.82,
                "canonical_entity_id": ent["id"],
                "canonical_name": ent["razao_social"],
                "municipio": ent.get("municipio"),
                "reversible": True,
            }
        if len(prefs) > 1:
            # Prefer exact "PREFEITURA" in razao_social
            pref_only = [p for p in prefs if "PREFEITURA" in (p.get("razao_social") or "").upper()]
            if len(pref_only) == 1:
                ent = pref_only[0]
                return {
                    "status": "matched_alias",
                    "rule": "municipio_prefeitura_prefer",
                    "score": 0.8,
                    "canonical_entity_id": ent["id"],
                    "canonical_name": ent["razao_social"],
                    "municipio": ent.get("municipio"),
                    "reversible": True,
                }
            return {
                "status": "ambiguous",
                "rule": "municipio_prefeitura_multiple",
                "score": 0.4,
                "canonical_entity_id": None,
                "canonical_name": None,
                "municipio": muni,
                "candidates": [p["id"] for p in prefs[:5]],
                "reversible": True,
            }

    return {
        "status": "unresolved",
        "rule": "no_conservative_match",
        "score": 0.0,
        "canonical_entity_id": None,
        "canonical_name": None,
        "municipio": muni or None,
        "reversible": True,
    }


def iter_jsonl(path: Path):
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _best_jsonl(candidates: list[Path], *, min_bytes: int = 100) -> Path | None:
    """Prefer non-empty artifact with most records (size proxy), then newest mtime."""
    usable = [p for p in candidates if p.is_file() and p.stat().st_size >= min_bytes]
    if not usable:
        return None
    usable.sort(key=lambda p: (p.stat().st_size, p.stat().st_mtime), reverse=True)
    return usable[0]


def latest_ciga_jsonl() -> Path | None:
    root = _PROJECT_ROOT / "output" / "ciga_dom"
    return _best_jsonl(list(root.glob("ciga-dom-*/publications.jsonl")))


def latest_sc_compras_jsonl() -> Path | None:
    root = _PROJECT_ROOT / "output" / "sc_compras"
    return _best_jsonl(list(root.glob("sc_compras-*/licitacoes.jsonl")))


def latest_pncp_sc_jsonl() -> Path | None:
    root = _PROJECT_ROOT / "output" / "pncp_sc"
    return _best_jsonl(list(root.glob("*/contratacoes.jsonl")))


def process_sources(indexes: dict[str, Any], as_of: date) -> dict[str, Any]:
    """Process file artifacts: classify + resolve. Return evidence bundles."""
    records: list[dict[str, Any]] = []
    crosswalk: list[dict[str, Any]] = []
    source_stats: dict[str, Counter] = defaultdict(Counter)

    # --- CIGA DOM ---
    ciga_path = latest_ciga_jsonl()
    if ciga_path:
        for rec in iter_jsonl(ciga_path):
            cat = rec.get("act_category")
            comm = classify_commercial(
                act_category=cat,
                title=rec.get("titulo"),
                text=rec.get("texto"),
                data_publicacao=rec.get("data"),
                as_of=as_of,
            )
            sector = classify_sector(rec.get("texto") or rec.get("titulo"), titulo=rec.get("titulo"))
            match = resolve_entity(
                orgao_nome=rec.get("orgao") or rec.get("entidade"),
                municipio=rec.get("municipio"),
                orgao_cnpj=None,
                indexes=indexes,
            )
            is_opp_act = (cat or "") in COVERAGE_ACT_CATEGORIES
            counts_for_coverage = is_opp_act and match.get("canonical_entity_id") and comm.status in (
                STRICT_OPPORTUNITY_STATUSES | {"OTHER_PROCUREMENT_ACT", "RECENT_NOTICE"}
            )
            # For CIGA without deadline, opportunity acts count as RECENT_NOTICE/OTHER
            if is_opp_act and match.get("canonical_entity_id"):
                counts_for_coverage = True

            row = {
                "source": "ciga_dom",
                "source_id": rec.get("codigo"),
                "title": rec.get("titulo"),
                "orgao_nome": rec.get("orgao"),
                "municipio": rec.get("municipio"),
                "publication_date": rec.get("data"),
                "act_category": cat,
                "url": rec.get("url"),
                "commercial": comm.to_dict(),
                "sector": sector.to_dict(),
                "entity_match": match,
                "counts_for_coverage": bool(counts_for_coverage),
                "artifact": str(ciga_path),
            }
            records.append(row)
            source_stats["ciga_dom"]["records"] += 1
            if counts_for_coverage:
                source_stats["ciga_dom"]["coverage_eligible"] += 1
            if match.get("canonical_entity_id"):
                source_stats["ciga_dom"]["matched"] += 1
            crosswalk.append(
                {
                    "source": "ciga_dom",
                    "source_entity_id": rec.get("orgao"),
                    "source_name": rec.get("orgao"),
                    "source_cnpj": None,
                    "source_municipio": rec.get("municipio"),
                    "canonical_entity_id": match.get("canonical_entity_id"),
                    "canonical_name": match.get("canonical_name"),
                    "municipio": match.get("municipio"),
                    "rule": match.get("rule"),
                    "score": match.get("score"),
                    "status": match.get("status"),
                    "review": match.get("status") == "ambiguous",
                    "reversible": True,
                }
            )

    # --- SC Compras ---
    sc_path = latest_sc_compras_jsonl()
    if sc_path:
        for rec in iter_jsonl(sc_path):
            comm = classify_commercial(
                act_category=None,
                title=rec.get("objeto_compra"),
                text=rec.get("objeto_compra"),
                official_status=rec.get("status"),
                data_abertura=rec.get("data_abertura"),
                data_encerramento=rec.get("data_encerramento"),
                data_publicacao=rec.get("data_publicacao"),
                as_of=as_of,
            )
            sector = classify_sector(
                rec.get("objeto_compra"),
                modalidade=rec.get("modalidade_nome"),
            )
            match = resolve_entity(
                orgao_nome=rec.get("orgao_razao_social"),
                municipio=rec.get("municipio"),
                orgao_cnpj=rec.get("orgao_cnpj"),
                indexes=indexes,
            )
            counts = bool(
                match.get("canonical_entity_id")
                and comm.status
                in STRICT_OPPORTUNITY_STATUSES
                | {"OTHER_PROCUREMENT_ACT", "RESULT", "CLOSED", "RECENT_NOTICE"}
            )
            # For historical-style bid coverage, any procurement row matched counts
            # Commercial metric uses STRICT + RECENT only
            row = {
                "source": "sc_compras",
                "source_id": rec.get("source_id") or rec.get("api_id") or rec.get("pncp_id"),
                "title": (rec.get("objeto_compra") or "")[:500],
                "orgao_nome": rec.get("orgao_razao_social"),
                "municipio": rec.get("municipio"),
                "publication_date": rec.get("data_publicacao"),
                "status_official": rec.get("status"),
                "modalidade": rec.get("modalidade_nome"),
                "url": rec.get("link_pncp"),
                "commercial": comm.to_dict(),
                "sector": sector.to_dict(),
                "entity_match": match,
                "counts_for_coverage": counts,
                "counts_for_historical_bid": bool(match.get("canonical_entity_id")),
                "artifact": str(sc_path),
            }
            records.append(row)
            source_stats["sc_compras"]["records"] += 1
            if counts:
                source_stats["sc_compras"]["coverage_eligible"] += 1
            if match.get("canonical_entity_id"):
                source_stats["sc_compras"]["matched"] += 1
            crosswalk.append(
                {
                    "source": "sc_compras",
                    "source_entity_id": rec.get("orgao_razao_social"),
                    "source_name": rec.get("orgao_razao_social"),
                    "source_cnpj": rec.get("orgao_cnpj"),
                    "source_municipio": rec.get("municipio"),
                    "canonical_entity_id": match.get("canonical_entity_id"),
                    "canonical_name": match.get("canonical_name"),
                    "municipio": match.get("municipio"),
                    "rule": match.get("rule"),
                    "score": match.get("score"),
                    "status": match.get("status"),
                    "review": match.get("status") == "ambiguous",
                    "reversible": True,
                }
            )

    # --- PNCP SC focused artifact if present ---
    pncp_path = latest_pncp_sc_jsonl()
    if pncp_path:
        for rec in iter_jsonl(pncp_path):
            orgao = rec.get("orgaoEntidade") or {}
            unidade = rec.get("unidadeOrgao") or {}
            orgao_nome = orgao.get("razaoSocial") or orgao.get("nome")
            cnpj = orgao.get("cnpj") or orgao.get("cnpjCpf")
            muni = unidade.get("municipioNome")
            comm = classify_commercial(
                title=rec.get("objetoCompra"),
                text=rec.get("objetoCompra"),
                official_status=str(rec.get("situacaoCompraId") or rec.get("situacaoCompraNome") or ""),
                data_abertura=rec.get("dataAberturaProposta"),
                data_encerramento=rec.get("dataEncerramentoProposta"),
                data_publicacao=rec.get("dataPublicacaoPncp") or rec.get("dataInclusao"),
                as_of=as_of,
            )
            sector = classify_sector(rec.get("objetoCompra"))
            match = resolve_entity(
                orgao_nome=orgao_nome,
                municipio=muni,
                orgao_cnpj=cnpj,
                indexes=indexes,
            )
            counts = bool(match.get("canonical_entity_id"))
            row = {
                "source": "pncp_sc",
                "source_id": rec.get("numeroControlePNCP"),
                "title": (rec.get("objetoCompra") or "")[:500],
                "orgao_nome": orgao_nome,
                "orgao_cnpj": cnpj,
                "municipio": muni,
                "publication_date": rec.get("dataPublicacaoPncp"),
                "numero_controle_pncp": rec.get("numeroControlePNCP"),
                "url": rec.get("linkSistemaOrigem"),
                "commercial": comm.to_dict(),
                "sector": sector.to_dict(),
                "entity_match": match,
                "counts_for_coverage": counts
                and comm.status in STRICT_OPPORTUNITY_STATUSES | {"RECENT_NOTICE", "OTHER_PROCUREMENT_ACT", "CLOSED", "RESULT"},
                "counts_for_historical_bid": counts,
                "artifact": str(pncp_path),
            }
            records.append(row)
            source_stats["pncp_sc"]["records"] += 1
            if row["counts_for_coverage"]:
                source_stats["pncp_sc"]["coverage_eligible"] += 1
            if match.get("canonical_entity_id"):
                source_stats["pncp_sc"]["matched"] += 1

    return {
        "records": records,
        "crosswalk": crosswalk,
        "source_stats": {k: dict(v) for k, v in source_stats.items()},
        "artifacts": {
            "ciga_dom": str(ciga_path) if ciga_path else None,
            "sc_compras": str(sc_path) if sc_path else None,
            "pncp_sc": str(pncp_path) if pncp_path else None,
        },
    }


def update_entity_coverage(
    conn,
    records: list[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    """Upsert entity_coverage for matched opportunity-relevant records."""
    # Aggregate per (entity_id, source)
    agg: dict[tuple[int, str], dict[str, Any]] = {}
    for r in records:
        mid = r.get("entity_match", {}).get("canonical_entity_id")
        if not mid:
            continue
        # Historical bid presence: any matched procurement record
        hist = r.get("counts_for_historical_bid")
        cov = r.get("counts_for_coverage")
        if not hist and not cov:
            # still allow opportunity acts from ciga
            if not r.get("counts_for_coverage"):
                continue
        source = r["source"]
        # Map sources onto entity_coverage source keys used historically
        src_key = {
            "ciga_dom": "dom_sc",
            "sc_compras": "sc_compras",
            "pncp_sc": "pncp",
        }.get(source, source)
        key = (int(mid), src_key)
        slot = agg.setdefault(
            key,
            {"bids": 0, "last_seen": None, "methods": Counter(), "eligible": 0},
        )
        slot["bids"] += 1
        if cov:
            slot["eligible"] += 1
        pub = r.get("publication_date")
        if pub and (slot["last_seen"] is None or str(pub) > str(slot["last_seen"])):
            slot["last_seen"] = pub
        rule = r.get("entity_match", {}).get("rule")
        if rule:
            slot["methods"][rule] += 1

    cur = conn.cursor()
    updated = 0
    inserted = 0
    for (entity_id, source), slot in agg.items():
        method = slot["methods"].most_common(1)[0][0] if slot["methods"] else "session_resolve"
        last_seen = slot["last_seen"]
        # is_covered true if any bid-like evidence
        is_covered = slot["bids"] > 0
        if dry_run:
            updated += 1
            continue
        cur.execute(
            """
            INSERT INTO entity_coverage
                (entity_id, source, last_seen_at, total_bids, is_covered, within_200km, match_method)
            VALUES (%s, %s, COALESCE(%s::timestamptz, NOW()), %s, %s, TRUE, %s)
            ON CONFLICT (entity_id, source) DO UPDATE SET
                last_seen_at = GREATEST(
                    COALESCE(entity_coverage.last_seen_at, '-infinity'::timestamptz),
                    COALESCE(EXCLUDED.last_seen_at, '-infinity'::timestamptz)
                ),
                total_bids = GREATEST(entity_coverage.total_bids, EXCLUDED.total_bids),
                is_covered = entity_coverage.is_covered OR EXCLUDED.is_covered,
                within_200km = TRUE,
                match_method = COALESCE(EXCLUDED.match_method, entity_coverage.match_method)
            """,
            (entity_id, source, last_seen, slot["bids"], is_covered, method),
        )
        if cur.rowcount:
            updated += 1
    if not dry_run:
        conn.commit()
    cur.close()
    return {"upserts": updated, "entities_sources": len(agg), "inserted_hint": inserted}


def compute_coverage(
    conn,
    universe: list[dict[str, Any]],
    records: list[dict[str, Any]],
    as_of: date,
) -> dict[str, Any]:
    """Compute multi-metric coverage against fixed denominator 1093."""
    denom = len(universe)
    if denom <= 0:
        raise RuntimeError("Universe empty — cannot compute coverage")
    # Prefer live count but report if mismatch
    denom_live = denom
    denom_canonical = DENOMINATOR

    # Baseline from DB (any is_covered)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(DISTINCT e.id)
        FROM sc_public_entities e
        JOIN entity_coverage ec ON e.id = ec.entity_id
        WHERE e.is_active AND e.raio_200km AND ec.is_covered
        """
    )
    covered_db = cur.fetchone()[0]

    cur.execute(
        """
        SELECT e.id, e.razao_social, e.municipio, e.cnpj_8, e.natureza_juridica,
               BOOL_OR(ec.is_covered) AS is_covered,
               COALESCE(SUM(ec.total_bids),0) AS total_bids,
               MAX(ec.last_seen_at) AS last_seen,
               ARRAY_AGG(DISTINCT ec.source) FILTER (WHERE ec.is_covered) AS sources
        FROM sc_public_entities e
        LEFT JOIN entity_coverage ec ON e.id = ec.entity_id
        WHERE e.is_active AND e.raio_200km
        GROUP BY e.id, e.razao_social, e.municipio, e.cnpj_8, e.natureza_juridica
        ORDER BY e.municipio, e.razao_social
        """
    )
    cols = [d[0] for d in cur.description]
    entity_rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()

    # From session records — commercial metrics
    window_30 = as_of - timedelta(days=30)
    window_90 = as_of - timedelta(days=90)

    def _pub_date(r):
        d = r.get("publication_date")
        if not d:
            return None
        try:
            return date.fromisoformat(str(d)[:10])
        except ValueError:
            return None

    entities_any_hist: set[int] = set()
    entities_any_commercial: set[int] = set()
    entities_30d: set[int] = set()
    entities_90d: set[int] = set()
    entities_open: set[int] = set()
    entities_eng: set[int] = set()
    entities_open_eng: set[int] = set()
    entities_with_doc: set[int] = set()
    source_contribution: dict[int, set[str]] = defaultdict(set)

    for r in records:
        mid = r.get("entity_match", {}).get("canonical_entity_id")
        if not mid:
            continue
        mid = int(mid)
        if r.get("counts_for_historical_bid") or r.get("counts_for_coverage"):
            entities_any_hist.add(mid)
            source_contribution[mid].add(r["source"])
        st = r.get("commercial", {}).get("status")
        pub = _pub_date(r)
        if r.get("counts_for_coverage") or (
            st in STRICT_OPPORTUNITY_STATUSES and mid
        ):
            entities_any_commercial.add(mid)
        if st in STRICT_OPPORTUNITY_STATUSES:
            entities_any_commercial.add(mid)
            if pub and pub >= window_30:
                entities_30d.add(mid)
            if pub and pub >= window_90:
                entities_90d.add(mid)
        if st == "OPEN_OPPORTUNITY":
            entities_open.add(mid)
        if r.get("sector", {}).get("sector_match"):
            entities_eng.add(mid)
            if st == "OPEN_OPPORTUNITY":
                entities_open_eng.add(mid)
        if r.get("url"):
            entities_with_doc.add(mid)

    # DB-covered set
    db_covered_ids = {int(e["id"]) for e in entity_rows if e.get("is_covered")}

    # Combined numerator: DB covered OR session historical match
    combined_hist = db_covered_ids | entities_any_hist

    def metric(name: str, num_set: set[int], formula: str) -> dict[str, Any]:
        num = len(num_set)
        return {
            "name": name,
            "numerator": num,
            "denominator": denom_canonical,
            "denominator_live": denom_live,
            "result_pct": round(num / denom_canonical * 100, 2) if denom_canonical else 0.0,
            "formula": formula,
            "as_of": as_of.isoformat(),
            "entity_ids_sample": sorted(list(num_set))[:50],
        }

    metrics = [
        metric(
            "historical_editais_raw_coverage_baseline",
            set(),  # filled below with static 52 reference
            "baseline preserved 52/1093",
        ),
        {
            "name": "historical_editais_raw_coverage_baseline",
            "numerator": 52,
            "denominator": 1093,
            "result_pct": 4.76,
            "formula": "entities_with_bids / total_entities_within_200km * 100 (pre-session)",
            "as_of": as_of.isoformat(),
            "preserved": True,
        },
        metric(
            "entity_coverage_db_is_covered",
            db_covered_ids,
            "COUNT DISTINCT entity_id WHERE is_covered on raio_200km / 1093",
        ),
        metric(
            "session_matched_any_procurement",
            entities_any_hist,
            "entities matched from session artifacts with procurement evidence / 1093",
        ),
        metric(
            "canonical_combined_post_session",
            combined_hist,
            "union(db is_covered, session matched procurement) / 1093",
        ),
        metric(
            "commercial_opportunity_any",
            entities_any_commercial,
            "entities with commercial opportunity status / 1093",
        ),
        metric(
            "opportunity_published_30d",
            entities_30d,
            "entities with opportunity published last 30d / 1093",
        ),
        metric(
            "opportunity_published_90d",
            entities_90d,
            "entities with opportunity published last 90d / 1093",
        ),
        metric(
            "open_opportunity",
            entities_open,
            "entities with OPEN_OPPORTUNITY / 1093",
        ),
        metric(
            "engineering_relevant",
            entities_eng,
            "entities with sector_match engineering / 1093",
        ),
        metric(
            "open_engineering",
            entities_open_eng,
            "entities with open engineering opportunity / 1093",
        ),
        metric(
            "with_document_url",
            entities_with_doc & combined_hist,
            "covered entities that have at least one source URL / 1093",
        ),
    ]

    covered_list = []
    uncovered_list = []
    for e in entity_rows:
        eid = int(e["id"])
        is_cov = eid in combined_hist
        entry = {
            "entity_id": eid,
            "razao_social": e["razao_social"],
            "municipio": e["municipio"],
            "cnpj_8": e["cnpj_8"],
            "natureza_juridica": e["natureza_juridica"],
            "is_covered": is_cov,
            "db_covered": eid in db_covered_ids,
            "total_bids": int(e["total_bids"] or 0),
            "last_seen": str(e["last_seen"]) if e["last_seen"] else None,
            "sources_db": list(e["sources"] or []) if e["sources"] else [],
            "sources_session": sorted(source_contribution.get(eid, [])),
            "coverage_status": "covered" if is_cov else "uncovered",
            "absence_reason": None
            if is_cov
            else "no_matched_procurement_opportunity_in_db_or_session_artifacts",
        }
        if is_cov:
            covered_list.append(entry)
        else:
            uncovered_list.append(entry)

    # Source attribution for NEW entities vs baseline 52
    new_ids = combined_hist - db_covered_ids
    new_by_source: Counter = Counter()
    for eid in new_ids:
        for s in source_contribution.get(eid, []):
            new_by_source[s] += 1

    return {
        "metrics": metrics,
        "covered_entities": covered_list,
        "uncovered_entities": uncovered_list,
        "new_entities_vs_db": {
            "count": len(new_ids),
            "entity_ids": sorted(new_ids),
            "by_source": dict(new_by_source),
        },
        "db_covered_before_or_after_update": covered_db,
        "combined_numerator": len(combined_hist),
        "denominator": denom_canonical,
        "denominator_live": denom_live,
    }


def write_outputs(
    *,
    coverage: dict[str, Any],
    processed: dict[str, Any],
    coverage_update: dict[str, int],
    as_of: date,
) -> dict[str, str]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = {}

    cov_path = OUT_DIR / "coverage_canonical.json"
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "as_of": as_of.isoformat(),
        "git_branch": "epic/coverage-200km-operational",
        "methodology": {
            "denominator": 1093,
            "denominator_definition": "sc_public_entities is_active AND raio_200km",
            "do_not_change_denominator": True,
            "baseline_numerator": 52,
            "baseline_pct": 4.76,
        },
        "coverage_update": coverage_update,
        "source_stats": processed["source_stats"],
        "artifacts": processed["artifacts"],
        "metrics": coverage["metrics"],
        "new_entities_vs_db": coverage["new_entities_vs_db"],
        "combined_numerator": coverage["combined_numerator"],
        "denominator": coverage["denominator"],
        "result_pct": round(coverage["combined_numerator"] / coverage["denominator"] * 100, 2),
        "covered_count": len(coverage["covered_entities"]),
        "uncovered_count": len(coverage["uncovered_entities"]),
    }
    cov_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    paths["coverage_canonical"] = str(cov_path)

    # entity lists
    cov_list = OUT_DIR / "entities_covered.jsonl"
    with cov_list.open("w", encoding="utf-8") as fh:
        for e in coverage["covered_entities"]:
            fh.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
    paths["entities_covered"] = str(cov_list)

    unc_list = OUT_DIR / "entities_uncovered.jsonl"
    with unc_list.open("w", encoding="utf-8") as fh:
        for e in coverage["uncovered_entities"]:
            fh.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
    paths["entities_uncovered"] = str(unc_list)

    # crosswalk unique by source_name
    cw_path = OUT_DIR / "entity_crosswalk.jsonl"
    seen = set()
    with cw_path.open("w", encoding="utf-8") as fh:
        for row in processed["crosswalk"]:
            key = (row.get("source"), row.get("source_name"), row.get("canonical_entity_id"))
            if key in seen:
                continue
            seen.add(key)
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    paths["entity_crosswalk"] = str(cw_path)

    # radar
    radar_path = OUT_DIR / "radar_opportunities.jsonl"
    n_radar = 0
    with radar_path.open("w", encoding="utf-8") as fh:
        for r in processed["records"]:
            st = r.get("commercial", {}).get("status")
            if st not in STRICT_OPPORTUNITY_STATUSES and not (
                r.get("sector", {}).get("sector_match") and st in {"RECENT_NOTICE", "OTHER_PROCUREMENT_ACT", "OPEN_OPPORTUNITY"}
            ):
                if st not in {"OPEN_OPPORTUNITY", "UPCOMING_OPPORTUNITY", "RECENT_NOTICE"}:
                    continue
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
            n_radar += 1
    paths["radar_opportunities"] = str(radar_path)
    paths["radar_count"] = str(n_radar)

    # summary md
    md = OUT_DIR / "COVERAGE_REPORT.md"
    m = payload
    lines = [
        f"# Cobertura canônica 200 km — {as_of.isoformat()}",
        "",
        "- **Baseline:** 52 / 1093 (4,76%)",
        f"- **Pós-sessão (combined):** {m['combined_numerator']} / 1093 ({m['result_pct']}%)",
        f"- **Delta absoluto:** {m['combined_numerator'] - 52}",
        f"- **Entidades novas vs DB:** {m['new_entities_vs_db']['count']}",
        f"- **Cobertas listadas:** {m['covered_count']}",
        f"- **Descobertas listadas:** {m['uncovered_count']}",
        "",
        "## Métricas",
        "",
    ]
    for met in m["metrics"]:
        if met.get("name") == "historical_editais_raw_coverage_baseline" and met.get("numerator") == 0:
            continue
        lines.append(
            f"- `{met['name']}`: **{met.get('numerator')}** / {met.get('denominator')} "
            f"= {met.get('result_pct')}%"
        )
    lines += ["", "## Fontes (artefatos)", ""]
    for k, v in (m.get("artifacts") or {}).items():
        lines.append(f"- {k}: `{v}`")
    lines += ["", "## Stats por fonte", ""]
    for k, v in (m.get("source_stats") or {}).items():
        lines.append(f"- {k}: {v}")
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    paths["report_md"] = str(md)
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Session coverage pipeline 200km")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-db-update", action="store_true")
    parser.add_argument("--as-of", default=None, help="YYYY-MM-DD")
    args = parser.parse_args(argv)

    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    _load_dotenv()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    conn = connect()
    try:
        universe = load_universe(conn)
        print(f"Universe loaded: {len(universe)} (expected {DENOMINATOR})")
        indexes = build_entity_indexes(universe)
        processed = process_sources(indexes, as_of)
        print(f"Records processed: {len(processed['records'])}")
        print(f"Source stats: {processed['source_stats']}")

        if args.skip_db_update or args.dry_run:
            cov_upd = update_entity_coverage(conn, processed["records"], dry_run=True)
            print(f"Coverage update dry-run: {cov_upd}")
        else:
            cov_upd = update_entity_coverage(conn, processed["records"], dry_run=False)
            print(f"Coverage update applied: {cov_upd}")

        coverage = compute_coverage(conn, universe, processed["records"], as_of)
        paths = write_outputs(
            coverage=coverage,
            processed=processed,
            coverage_update=cov_upd,
            as_of=as_of,
        )
        print(json.dumps({
            "combined_numerator": coverage["combined_numerator"],
            "denominator": coverage["denominator"],
            "pct": round(coverage["combined_numerator"] / coverage["denominator"] * 100, 2),
            "new_vs_db": coverage["new_entities_vs_db"]["count"],
            "paths": paths,
        }, indent=2, ensure_ascii=False))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
