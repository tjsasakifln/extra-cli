#!/usr/bin/env python3
"""Multi-source coverage & freshness metrics (file-artifact based).

Recalculates coverage with **defensible, explicit denominators**. Does NOT
overwrite or rebrand the historical 4.76% editais metric — that value is
preserved as ``historical_editais_raw_coverage`` with its original methodology.

This module reads local session artifacts (JSON/JSONL/CSV) under ``output/``
and ``data/``. It does not require a live database connection.

Usage::

    python3 -m scripts.coverage.multi_source_coverage
    python3 -m scripts.coverage.multi_source_coverage --window-days 30 --output-dir output/coverage

Outputs::

    output/coverage/multi_source-{run_id}.json
    output/coverage/multi_source-{run_id}.md
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
import uuid
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output" / "coverage"
IBGE_CACHE_PATH = PROJECT_ROOT / "data" / "ibge_cache.json"

# Canonical SC municipality universe size (IBGE). Used as denominator when
# ibge_cache is available; otherwise falls back to this constant with low confidence.
SC_MUNICIPALITY_UNIVERSE = 295

# Historical crude editais metric (entities with bids / target universe 200 km).
# Source: output/coverage/next30d-metrics-final.json + coverage_truth bid_presence.
HISTORICAL_EDITAIS_RAW = {
    "name": "historical_editais_raw_coverage",
    "numerator": 52,
    "denominator": 1093,
    "result_pct": 4.76,
    "period": "snapshot as of 2026-07-17 (entity_coverage, radius 200 km FLN)",
    "sources": [
        "output/coverage/next30d-metrics-final.json",
        "output/sc_compras/coverage-truth/coverage-truth-2026-07-16.json",
    ],
    "formula": "entities_with_bids / total_entities_within_200km * 100",
    "note": (
        "PRESERVED historical metric. Denominator = target_universe entities within "
        "200 km of Florianópolis (1093). Numerator = entities with ≥1 persisted bid "
        "in entity_coverage (52). This is NOT municipal publication coverage and must "
        "not be conflated with municipalities_with_publication_30d or multi-source "
        "artifact metrics produced by this module."
    ),
    "methodology_change_warning": (
        "New multi-source metrics use different denominators (295 IBGE municipios, "
        "artifact-local org sets, API totals). Comparing them to 4.76% is invalid."
    ),
}

# Procurement-related act categories (shared taxonomy with act_classifier).
PROCUREMENT_ACT_CATEGORIES = frozenset(
    {
        "aviso_licitacao",
        "edital",
        "dispensa",
        "inexigibilidade",
        "homologacao",
        "resultado",
        "extrato_contrato",
        "termo_aditivo",
        "ata_registro_precos",
        "chamamento_publico",
        "credenciamento",
        "anulacao",
        "revogacao",
        "suspensao",
        "rescisao",
        "apostilamento",
        "errata",
        "retificacao",
        "outros_atos_contratacao",
    }
)

# Core fields expected for completeness scoring per source family.
FIELD_SETS: dict[str, list[str]] = {
    "ciga_dom": ["municipio", "orgao", "data", "titulo", "url", "act_category", "texto"],
    "sc_compras": [
        "objeto_compra",
        "orgao_razao_social",
        "data_publicacao",
        "modalidade_nome",
        "link_pncp",
        "municipio",
        "orgao_cnpj",
        "valor_total_estimado",
        "documentos",
    ],
    "dados_abertos_sc": [
        "orgao",
        "titulo",
        "data_publicacao",
        "tipo_ato",
        "act_category",
        "texto_ou_extrato",
        "link_edicao",
        "link_extrato",
    ],
    "pncp": ["objeto_compra", "orgao_razao_social", "data_publicacao", "municipio", "uf"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_utc() -> datetime:
    return datetime.now(UTC)


def make_run_id(now: datetime | None = None) -> str:
    ts = (now or _now_utc()).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{uuid.uuid4().hex[:10]}"


def normalize_muni_key(name: str | None) -> str:
    """Accent-insensitive, case-folded municipality key for set membership."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", str(name).strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    # ISO date or datetime
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19].replace("Z", ""), fmt.replace("Z", "")).date()
        except ValueError:
            continue
    # BR format
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    # Prefix ISO
    m = re.match(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        try:
            return date.fromisoformat(m.group(1))
        except ValueError:
            return None
    return None


def parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except ValueError:
        d = parse_date(text)
        if d:
            return datetime(d.year, d.month, d.day, tzinfo=UTC)
    return None


def safe_pct(num: float | int | None, den: float | int | None, digits: int = 2) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return round(float(num) / float(den) * 100.0, digits)


def is_nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, dict, str)) and len(value) == 0:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def hours_since(ts: datetime | None, now: datetime) -> float | None:
    if ts is None:
        return None
    return round((now - ts).total_seconds() / 3600.0, 2)


# ---------------------------------------------------------------------------
# Artifact discovery
# ---------------------------------------------------------------------------


@dataclass
class SourceArtifacts:
    source: str
    summary: dict[str, Any] | None = None
    summary_path: Path | None = None
    records: list[dict[str, Any]] = field(default_factory=list)
    records_path: Path | None = None
    freshness_manifest: dict[str, Any] | None = None
    freshness_path: Path | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _latest_dir(parent: Path, prefix: str | None = None) -> Path | None:
    if not parent.is_dir():
        return None
    dirs = [p for p in parent.iterdir() if p.is_dir()]
    if prefix:
        dirs = [p for p in dirs if p.name.startswith(prefix)]
    if not dirs:
        return None
    return max(dirs, key=lambda p: p.stat().st_mtime)


def _latest_file(parent: Path, pattern: str) -> Path | None:
    if not parent.is_dir():
        return None
    files = list(parent.glob(pattern))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def load_ibge_universe(path: Path = IBGE_CACHE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {
            "available": False,
            "count": SC_MUNICIPALITY_UNIVERSE,
            "keys": set(),
            "raw": {},
            "path": str(path),
            "note": f"ibge_cache missing; using constant SC_MUNICIPALITY_UNIVERSE={SC_MUNICIPALITY_UNIVERSE}",
        }
    raw = read_json(path)
    keys = {normalize_muni_key(k) for k in raw.keys() if normalize_muni_key(k)}
    return {
        "available": True,
        "count": len(keys),
        "keys": keys,
        "raw": raw,
        "path": str(path),
        "note": "IBGE cache municipality name → code mapping for SC",
    }


def discover_ciga_dom(root: Path = PROJECT_ROOT) -> SourceArtifacts:
    base = root / "output" / "ciga_dom"
    art = SourceArtifacts(source="ciga_dom")
    run_dir = _latest_dir(base, "ciga-dom-")
    latest_summary = base / "latest_summary.json"
    if latest_summary.exists():
        art.summary = read_json(latest_summary)
        art.summary_path = latest_summary
        # Prefer run dir matching summary run_id
        run_id = (art.summary or {}).get("run_id")
        if run_id and (base / run_id).is_dir():
            run_dir = base / run_id
    if run_dir is None:
        return art
    if art.summary is None and (run_dir / "summary.json").exists():
        art.summary = read_json(run_dir / "summary.json")
        art.summary_path = run_dir / "summary.json"
    pubs = run_dir / "publications.jsonl"
    if pubs.exists():
        art.records = read_jsonl(pubs)
        art.records_path = pubs
    fresh = base / "freshness_manifest.json"
    if fresh.exists():
        art.freshness_manifest = read_json(fresh)
        art.freshness_path = fresh
    art.extra["run_dir"] = str(run_dir)
    return art


def discover_sc_compras(root: Path = PROJECT_ROOT) -> SourceArtifacts:
    base = root / "output" / "sc_compras"
    art = SourceArtifacts(source="sc_compras")
    # Prefer incremental over smoke when both exist
    candidates = [
        p
        for p in base.iterdir()
        if p.is_dir() and p.name.startswith("sc_compras-") and (p / "artifact.json").exists()
    ] if base.is_dir() else []
    run_dir: Path | None = None
    if candidates:
        # Prefer incremental mode, then newest mtime
        def _rank(p: Path) -> tuple[int, float]:
            try:
                mode = read_json(p / "artifact.json").get("mode", "")
            except Exception:
                mode = ""
            pref = 1 if mode == "incremental" else 0
            return (pref, p.stat().st_mtime)

        run_dir = max(candidates, key=_rank)
    if run_dir is None:
        return art
    art.summary = read_json(run_dir / "artifact.json")
    art.summary_path = run_dir / "artifact.json"
    lic = run_dir / "licitacoes.jsonl"
    if lic.exists():
        art.records = read_jsonl(lic)
        art.records_path = lic
    art.extra["run_dir"] = str(run_dir)
    return art


def discover_dados_abertos_sc(root: Path = PROJECT_ROOT) -> SourceArtifacts:
    base = root / "output" / "dados_abertos_sc"
    art = SourceArtifacts(source="dados_abertos_sc")
    summary_path = _latest_file(base, "*.json") if base.is_dir() else None
    if summary_path:
        art.summary = read_json(summary_path)
        art.summary_path = summary_path
        # Prefer normalized jsonl referenced by run_id
        run_id = (art.summary or {}).get("run_id")
        if run_id:
            norm_root = root / "data" / "normalized" / "dados_abertos_sc"
            matches = list(norm_root.rglob(f"*{run_id}*.jsonl")) if norm_root.is_dir() else []
            if matches:
                art.records = read_jsonl(matches[0])
                art.records_path = matches[0]
        if not art.records and art.summary:
            samples = art.summary.get("sample_records") or []
            if samples:
                art.records = list(samples)
                art.extra["records_are_samples_only"] = True
    return art


def discover_pncp(root: Path = PROJECT_ROOT) -> SourceArtifacts:
    """PNCP coverage from readiness / historical artifacts (no live crawl required)."""
    art = SourceArtifacts(source="pncp")
    readiness = root / "output" / "readiness" / "opportunity-coverage-manifest.json"
    coverage_manifest = root / "output" / "readiness" / "coverage_manifest.json"
    recon = root / "output" / "readiness" / "target-reconciliation-summary.json"
    next30d = root / "output" / "coverage" / "next30d-metrics-final.json"
    freshness = root / "output" / "readiness" / "freshness-gate.json"
    if readiness.exists():
        art.extra["opportunity_manifest"] = read_json(readiness)
        art.extra["opportunity_manifest_path"] = str(readiness)
    if coverage_manifest.exists():
        art.extra["coverage_manifest"] = read_json(coverage_manifest)
        art.extra["coverage_manifest_path"] = str(coverage_manifest)
    if recon.exists():
        art.extra["target_reconciliation"] = read_json(recon)
        art.extra["target_reconciliation_path"] = str(recon)
    if next30d.exists():
        art.extra["next30d_metrics"] = read_json(next30d)
        art.extra["next30d_metrics_path"] = str(next30d)
    if freshness.exists():
        art.freshness_manifest = read_json(freshness)
        art.freshness_path = freshness
    # Optional reconciliation folder
    recon_dir = root / "output" / "reconciliation"
    if recon_dir.is_dir():
        art.extra["reconciliation_dir"] = str(recon_dir)
        files = list(recon_dir.glob("*.json"))
        if files:
            latest = max(files, key=lambda p: p.stat().st_mtime)
            art.extra["reconciliation_artifact"] = read_json(latest)
            art.extra["reconciliation_artifact_path"] = str(latest)
    return art


# ---------------------------------------------------------------------------
# Metric builder
# ---------------------------------------------------------------------------


def metric(
    *,
    name: str,
    numerator: float | int | None,
    denominator: float | int | None,
    formula: str,
    period: str,
    sources: list[str],
    limitations: list[str],
    calc_date: str,
    run_id: str,
    confidence: str,
    unit: str = "pct",
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = safe_pct(numerator, denominator) if unit == "pct" else numerator
    out: dict[str, Any] = {
        "name": name,
        "numerator": numerator,
        "denominator": denominator,
        "formula": formula,
        "period": period,
        "sources": sources,
        "limitations": limitations,
        "calc_date": calc_date,
        "run_id": run_id,
        "result": result,
        "result_unit": unit,
        "confidence": confidence,  # high | medium | low | none
    }
    if extras:
        out.update(extras)
    return out


# ---------------------------------------------------------------------------
# Per-metric calculations
# ---------------------------------------------------------------------------


def calc_municipalities_with_publication_30d(
    *,
    ciga: SourceArtifacts,
    ibge: dict[str, Any],
    window_days: int,
    as_of: date,
    calc_date: str,
    run_id: str,
) -> dict[str, Any]:
    window_start = as_of - timedelta(days=window_days)
    universe_keys: set[str] = set(ibge["keys"]) if ibge["keys"] else set()
    den = int(ibge["count"]) if ibge["count"] else SC_MUNICIPALITY_UNIVERSE

    observed_in_window: set[str] = set()
    observed_all: set[str] = set()
    matched_in_window: set[str] = set()
    unmatched_samples: list[str] = []

    for rec in ciga.records:
        muni = rec.get("municipio")
        key = normalize_muni_key(muni)
        if not key:
            continue
        observed_all.add(key)
        d = parse_date(rec.get("data") or rec.get("data_publicacao"))
        in_window = d is not None and window_start <= d <= as_of
        if in_window:
            observed_in_window.add(key)
            if not universe_keys or key in universe_keys:
                matched_in_window.add(key)
            elif len(unmatched_samples) < 10:
                unmatched_samples.append(str(muni))

    # If universe empty, numerator = observed_in_window (weaker)
    num = len(matched_in_window) if universe_keys else len(observed_in_window)
    sources = [str(p) for p in [ciga.records_path, ciga.summary_path] if p]
    sources.append(str(ibge.get("path") or IBGE_CACHE_PATH))

    limitations = [
        "Numerator is municipalities with ≥1 collected CIGA DOM publication in the window — "
        "not proof that the municipality published something every day.",
        "Smoke/partial CIGA runs process only selected resources; full package has more ZIPs.",
        "Name matching is accent-insensitive but may miss exotic spelling variants.",
        "Other sources (dados_abertos_sc, sc_compras) are not included in this municipal metric "
        "because they lack reliable IBGE municipality linkage in the current artifacts.",
    ]
    if ciga.summary and ciga.summary.get("mode") == "smoke":
        limitations.append("CIGA DOM run mode=smoke — partial resource selection; underestimates full coverage.")
    confidence = "medium" if ciga.records and ibge["available"] else "low"

    return metric(
        name="municipalities_with_publication_30d",
        numerator=num,
        denominator=den,
        formula=(
            "count(distinct municipio with pub date in [as_of-window, as_of] "
            "matched to IBGE SC universe) / len(ibge_cache SC municipios)"
        ),
        period=f"last {window_days}d ending {as_of.isoformat()} (business date of publication)",
        sources=sources,
        limitations=limitations,
        calc_date=calc_date,
        run_id=run_id,
        confidence=confidence,
        extras={
            "window_start": window_start.isoformat(),
            "window_end": as_of.isoformat(),
            "observed_municipios_all_time_in_artifact": len(observed_all),
            "observed_municipios_in_window": len(observed_in_window),
            "matched_to_ibge_in_window": len(matched_in_window),
            "unmatched_name_samples": unmatched_samples,
            "universe_source": "data/ibge_cache.json" if ibge["available"] else "constant_295",
            "primary_source": "ciga_dom",
        },
    )


def _org_key(rec: dict[str, Any]) -> str:
    for k in ("orgao_razao_social", "orgao", "entidade", "orgao_cnpj", "cnpj"):
        v = rec.get(k)
        if is_nonempty(v):
            return str(v).strip().lower()
    return ""


def calc_orgs_with_recent_licitacao(
    *,
    ciga: SourceArtifacts,
    sc: SourceArtifacts,
    dados: SourceArtifacts,
    window_days: int,
    as_of: date,
    calc_date: str,
    run_id: str,
    root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    """Orgs with ≥1 recent bid/procurement signal vs expected public-org universe.

    Universe source (priority):
      1. coverage_truth / next30d denominator 1093 (target 200 km) if artifact present
      2. readiness opportunity-coverage-manifest universe
      3. unavailable → result null with documented gap
    """
    window_start = as_of - timedelta(days=window_days)
    den: int | None = None
    den_source = "unavailable"
    den_def = ""

    next30d_path = root / "output" / "coverage" / "next30d-metrics-final.json"
    truth_path = root / "output" / "sc_compras" / "coverage-truth" / "coverage-truth-2026-07-16.json"
    opp_path = root / "output" / "readiness" / "opportunity-coverage-manifest.json"

    if next30d_path.exists():
        d = read_json(next30d_path)
        if d.get("editais_denominator"):
            den = int(d["editais_denominator"])
            den_source = str(next30d_path)
            den_def = (
                "target universe entities within 200 km of Florianópolis "
                "(same denominator family as historical 4.76%)"
            )
    if den is None and truth_path.exists():
        d = read_json(truth_path)
        den_val = (d.get("denominator") or {}).get("total_entities_within_radius")
        if den_val:
            den = int(den_val)
            den_source = str(truth_path)
            den_def = "coverage_truth total_entities_within_radius (200 km)"
    if den is None and opp_path.exists():
        d = read_json(opp_path)
        den_val = (d.get("universe") or {}).get("total_entities_within_200km")
        if den_val:
            den = int(den_val)
            den_source = str(opp_path)
            den_def = "opportunity-coverage-manifest total_entities_within_200km"

    orgs: set[str] = set()
    by_source: dict[str, int] = {}

    def _consider(records: Iterable[dict[str, Any]], source: str, date_keys: list[str], require_procurement: bool) -> None:
        local: set[str] = set()
        for rec in records:
            if require_procurement:
                cat = str(rec.get("act_category") or "").strip().lower()
                if cat and cat not in PROCUREMENT_ACT_CATEGORIES:
                    continue
            d = None
            for dk in date_keys:
                d = parse_date(rec.get(dk))
                if d:
                    break
            if d is None or not (window_start <= d <= as_of):
                # sc_compras may have future abertura; accept publicacao within window OR
                # if no date, skip
                continue
            key = _org_key(rec)
            if key:
                local.add(key)
        by_source[source] = len(local)
        orgs.update(local)

    _consider(sc.records, "sc_compras", ["data_publicacao", "data_abertura"], False)
    _consider(ciga.records, "ciga_dom", ["data", "data_publicacao"], True)
    _consider(dados.records, "dados_abertos_sc", ["data_publicacao", "data_edicao"], True)

    num = len(orgs)
    sources = [s for s in [
        str(sc.records_path) if sc.records_path else None,
        str(ciga.records_path) if ciga.records_path else None,
        str(dados.records_path) if dados.records_path else None,
        den_source if den_source != "unavailable" else None,
    ] if s]

    limitations = [
        "Org identity is string-normalized name (or CNPJ when present); no entity resolver applied.",
        "Denominator is the 200 km target-universe entity set, while numerator mixes statewide "
        "artifact orgs (CIGA/DOM SC + sc_compras + DOE sample) — geographic scopes differ.",
        "CIGA/dados contribute only procurement-classified acts; classifier false negatives omit orgs.",
        "sc_compras artifact is incremental/smoke-sized (page-limited), not full portal history.",
        "This metric is intentionally SEPARATE from historical_editais_raw_coverage (4.76%).",
    ]
    confidence = "medium" if den and num > 0 else ("low" if den else "none")

    return metric(
        name="orgs_with_recent_licitacao",
        numerator=num,
        denominator=den,
        formula="count(distinct org with ≥1 recent bid/procurement signal) / expected_public_orgs_universe",
        period=f"last {window_days}d ending {as_of.isoformat()}",
        sources=sources,
        limitations=limitations,
        calc_date=calc_date,
        run_id=run_id,
        confidence=confidence,
        extras={
            "universe_definition": den_def,
            "universe_source": den_source,
            "orgs_by_source": by_source,
            "scope_note": "numerator multi-source artifacts; denominator 200km target universe",
        },
    )


def calc_pncp_sc_reconciled(
    *,
    pncp: SourceArtifacts,
    calc_date: str,
    run_id: str,
) -> dict[str, Any]:
    """PNCP SC records/entities matched to state/municipal sources or target list."""
    limitations: list[str] = []
    sources: list[str] = []
    num: int | None = None
    den: int | None = None
    formula = "pncp_sc_matched / pncp_sc_in_period"
    period = "artifact-dependent"
    confidence = "none"
    extras: dict[str, Any] = {}

    recon_art = pncp.extra.get("reconciliation_artifact")
    if isinstance(recon_art, dict) and (
        recon_art.get("matched") is not None or recon_art.get("pncp_sc_matched") is not None
    ):
        num = recon_art.get("pncp_sc_matched", recon_art.get("matched"))
        den = recon_art.get("pncp_sc_total", recon_art.get("total"))
        sources.append(str(pncp.extra.get("reconciliation_artifact_path")))
        confidence = "medium"
        period = str(recon_art.get("period") or "from reconciliation artifact")
        extras["reconciliation_mode"] = "output/reconciliation artifact"
    else:
        # Fallback: target reconciliation summary (entity-level, not record-level)
        recon = pncp.extra.get("target_reconciliation") or {}
        match_results = recon.get("match_results") or {}
        found = (match_results.get("FOUND_EXACT") or {}).get("count")
        # total targets from spreadsheet universe
        spreadsheet_total = (recon.get("spreadsheet") or {}).get("total_rows")
        universe = recon.get("universe") or {}
        den_candidate = universe.get("confirmed_universe") or universe.get("targets_within_200km")
        if found is not None and den_candidate is not None:
            num = int(found)
            den = int(den_candidate)
            path = pncp.extra.get("target_reconciliation_path")
            if path:
                sources.append(str(path))
            formula = (
                "FOUND_EXACT entities with PNCP opportunity data / confirmed target universe "
                "(entity-level proxy; NOT PNCP-record↔municipal-record join)"
            )
            period = f"snapshot {(recon.get('generated_at') or '')[:10] or 'unknown'}"
            confidence = "low"
            extras["reconciliation_mode"] = "target-reconciliation-summary entity proxy"
            extras["match_results"] = {k: (v or {}).get("count") for k, v in match_results.items()}
            extras["spreadsheet_total_rows"] = spreadsheet_total
            limitations.append(
                "No record-level PNCP↔state/municipal join artifact found under output/reconciliation/."
            )
            limitations.append(
                "Using entity-level FOUND_EXACT vs target universe as a PROXY only."
            )
        else:
            opp = pncp.extra.get("opportunity_manifest") or {}
            universe = opp.get("universe") or {}
            if universe.get("entities_with_opportunity_data") is not None:
                num = int(universe["entities_with_opportunity_data"])
                den = int(universe.get("total_entities_within_200km") or 0) or None
                path = pncp.extra.get("opportunity_manifest_path")
                if path:
                    sources.append(str(path))
                formula = (
                    "entities_with_opportunity_data / total_entities_within_200km "
                    "(opportunity manifest proxy; not formal PNCP reconciliation)"
                )
                period = f"snapshot {(opp.get('meta') or {}).get('generated_at', '')[:10]}"
                confidence = "low"
                extras["reconciliation_mode"] = "opportunity-coverage-manifest proxy"
                limitations.append("Formal PNCP SC reconciliation dataset unavailable this session.")
            else:
                limitations.append(
                    "pncp_sc_reconciled unavailable: no output/reconciliation/** and no usable proxy."
                )
                confidence = "none"

    if not sources:
        sources = ["(none — metric unavailable)"]

    limitations.append(
        "Do not interpret this as municipal publication coverage or as the historical 4.76% metric."
    )

    return metric(
        name="pncp_sc_reconciled",
        numerator=num,
        denominator=den,
        formula=formula,
        period=period,
        sources=sources,
        limitations=limitations,
        calc_date=calc_date,
        run_id=run_id,
        confidence=confidence,
        extras=extras,
    )


def calc_source_coverage(
    *,
    source: str,
    art: SourceArtifacts,
    ibge: dict[str, Any],
    calc_date: str,
    run_id: str,
    as_of: date,
) -> dict[str, Any]:
    """Source-specific coverage with source-appropriate denominator."""
    sources = [str(p) for p in [art.summary_path, art.records_path, art.freshness_path] if p]
    limitations: list[str] = []
    extras: dict[str, Any] = {"source": source}
    num: int | None = None
    den: int | None = None
    formula = ""
    period = "artifact snapshot"
    confidence = "low"

    if source == "ciga_dom":
        den = int(ibge["count"]) if ibge["count"] else SC_MUNICIPALITY_UNIVERSE
        munis = {normalize_muni_key(r.get("municipio")) for r in art.records}
        munis.discard("")
        universe = set(ibge["keys"]) if ibge["keys"] else munis
        matched = {m for m in munis if m in universe} if ibge["keys"] else munis
        num = len(matched)
        formula = "distinct municipios observed in CIGA DOM artifact ∩ IBGE SC / 295"
        period = "publication dates present in current CIGA artifact (may be single-day smoke)"
        confidence = "medium" if art.records else "none"
        extras["records"] = len(art.records)
        extras["observed_municipios"] = len(munis)
        if art.summary:
            extras["run_mode"] = art.summary.get("mode")
            extras["summary_counts"] = art.summary.get("counts")
        limitations.append("Smoke runs process subset of monthly package resources.")
        limitations.append("Observed municipio without IBGE match is excluded from numerator.")

    elif source == "sc_compras":
        summary = art.summary or {}
        metrics = summary.get("metrics") or {}
        num = int(metrics.get("records_normalized") or len(art.records) or 0)
        den = metrics.get("api_total_elementos_reported")
        if den is None:
            list_meta = (metrics.get("list_meta") or {})
            den = list_meta.get("total_elementos")
        den = int(den) if den is not None else None
        formula = "records_normalized_in_run / api_total_elementos_reported (year filter)"
        period = f"API year filter={summary.get('ano')}; mode={summary.get('mode')}"
        confidence = "medium" if den else "low"
        extras["api_total_elementos_reported"] = den
        extras["records_normalized"] = num
        extras["coverage_claim"] = metrics.get("coverage_claim")
        limitations.append(
            "Denominator is live API total for the requested year filter only — not full historical portal."
        )
        limitations.append("Incremental/smoke page limits mean numerator is a sample of denominator.")
        if not sources and summary:
            sources = [str(art.summary_path)] if art.summary_path else []

    elif source == "dados_abertos_sc":
        summary = art.summary or {}
        counts = summary.get("counts") or {}
        num = int(counts.get("rows_normalized") or len(art.records) or 0)
        # Full CSV is much larger; try to read raw size estimate from download path
        den = None
        download_results = summary.get("download_results") or []
        raw_path = None
        if download_results:
            raw_path = download_results[0].get("path")
        if raw_path and Path(raw_path).exists():
            # Count lines in raw CSV (minus header) — may be multi-line fields; approximate
            try:
                with Path(raw_path).open(encoding="utf-8-sig", errors="replace") as fh:
                    # Rough line count; CSV may embed newlines in fields so this is approximate
                    den = max(sum(1 for _ in fh) - 1, 0)
                extras["raw_csv_path"] = raw_path
                extras["denominator_method"] = "approx_line_count_raw_csv"
                limitations.append(
                    "Raw CSV line count is approximate (fields may contain embedded newlines)."
                )
            except OSError:
                den = None
        if den is None:
            den = num  # self-denominator for smoke completeness of processed set
            extras["denominator_method"] = "processed_set_only"
            limitations.append(
                "Full corpus size unknown; denominator falls back to processed rows (coverage=100% of sample)."
            )
        formula = "rows_normalized_in_run / estimated_rows_in_selected_resource_csv"
        period = f"mode={summary.get('mode')}; resource subset of package diario-oficial-sc-publicacoes"
        confidence = "low" if summary.get("mode") == "smoke" else "medium"
        extras["rows_normalized"] = num
        extras["resources_selected"] = counts.get("resources_selected")
        extras["resources_listed"] = counts.get("resources_listed")
        limitations.append("Smoke mode processes only first N rows of one resource (sample, not full DOE).")

    elif source == "pncp":
        next30d = art.extra.get("next30d_metrics") or {}
        opp = art.extra.get("opportunity_manifest") or {}
        if next30d.get("pncp_raw_bids") is not None:
            num = int(next30d["pncp_raw_bids"])
            # Entity-level crude coverage uses covered_200km / editais_denominator
            den_entities = next30d.get("editais_denominator")
            covered = next30d.get("covered_200km")
            extras["pncp_raw_bids"] = num
            extras["covered_200km_entities"] = covered
            extras["editais_denominator"] = den_entities
            # Source coverage for PNCP reported as entity bid presence (documented)
            num = int(covered) if covered is not None else None
            den = int(den_entities) if den_entities is not None else None
            formula = "entities_with_persisted_pncp_bids / target_universe_200km"
            period = f"datalake snapshot {(next30d.get('timestamp') or '')[:10]}"
            confidence = "medium"
            path = art.extra.get("next30d_metrics_path")
            if path:
                sources.append(str(path))
            limitations.append(
                "This is entity bid-presence from next30d metrics — same family as historical 4.76%, "
                "reported here under source=pncp for cross-source comparison, NOT a new methodology."
            )
        elif (opp.get("universe") or {}).get("entities_with_opportunity_data") is not None:
            u = opp["universe"]
            num = int(u["entities_with_opportunity_data"])
            den = int(u.get("total_entities_within_200km") or 0) or None
            formula = "entities_with_opportunity_data / total_entities_within_200km"
            period = f"opportunity manifest {(opp.get('meta') or {}).get('generated_at', '')[:10]}"
            confidence = "low"
            path = art.extra.get("opportunity_manifest_path")
            if path:
                sources.append(str(path))
        else:
            formula = "unavailable"
            confidence = "none"
            limitations.append("No PNCP coverage artifact found for this session.")
            sources = sources or ["(none)"]

    else:
        formula = "unknown source"
        confidence = "none"

    limitations.append(f"Source coverage for '{source}' uses a source-specific denominator; do not average blindly.")

    return metric(
        name=f"source_coverage_{source}",
        numerator=num,
        denominator=den,
        formula=formula,
        period=period,
        sources=sources or ["(none)"],
        limitations=limitations,
        calc_date=calc_date,
        run_id=run_id,
        confidence=confidence,
        extras=extras,
    )


def calc_temporal_coverage(
    *,
    source: str,
    records: list[dict[str, Any]],
    date_keys: list[str],
    window_days: int,
    as_of: date,
    calc_date: str,
    run_id: str,
    source_paths: list[str],
) -> dict[str, Any]:
    window_start = as_of - timedelta(days=window_days)
    dates: list[date] = []
    for rec in records:
        for dk in date_keys:
            d = parse_date(rec.get(dk))
            if d:
                dates.append(d)
                break

    if not dates:
        return metric(
            name=f"temporal_coverage_{source}",
            numerator=0,
            denominator=window_days + 1,
            formula="distinct calendar days with ≥1 record in window / days_in_window",
            period=f"last {window_days}d ending {as_of.isoformat()}",
            sources=source_paths or ["(none)"],
            limitations=["No parseable dates in artifact records."],
            calc_date=calc_date,
            run_id=run_id,
            confidence="none" if not records else "low",
            extras={"min_date": None, "max_date": None, "records_with_date": 0},
        )

    in_window = [d for d in dates if window_start <= d <= as_of]
    distinct_days = {d.isoformat() for d in in_window}
    den = window_days + 1  # inclusive day count
    num = len(distinct_days)
    return metric(
        name=f"temporal_coverage_{source}",
        numerator=num,
        denominator=den,
        formula="distinct calendar days with ≥1 record in window / (window_days+1 inclusive)",
        period=f"last {window_days}d ending {as_of.isoformat()}",
        sources=source_paths or ["(none)"],
        limitations=[
            "Measures day-level presence of collected records, not publication completeness of the source.",
            "Smoke artifacts often cover a single day → low temporal coverage even if source is healthy.",
        ],
        calc_date=calc_date,
        run_id=run_id,
        confidence="medium" if records else "none",
        extras={
            "min_date": min(dates).isoformat(),
            "max_date": max(dates).isoformat(),
            "min_date_in_window": min(in_window).isoformat() if in_window else None,
            "max_date_in_window": max(in_window).isoformat() if in_window else None,
            "records_with_date": len(dates),
            "records_in_window": len(in_window),
            "distinct_days_in_window": sorted(distinct_days),
        },
    )


def calc_act_category_distribution(
    *,
    source: str,
    records: list[dict[str, Any]],
    calc_date: str,
    run_id: str,
    source_paths: list[str],
    summary_categories: dict[str, int] | None = None,
) -> dict[str, Any]:
    counter: Counter[str] = Counter()
    if summary_categories:
        counter.update({str(k): int(v) for k, v in summary_categories.items()})
        total = sum(counter.values())
        origin = "summary.counts.act_categories"
    else:
        for rec in records:
            cat = rec.get("act_category") or rec.get("categoria_dom") or rec.get("tipo_ato") or "unknown"
            counter[str(cat)] += 1
        total = sum(counter.values())
        origin = "records"

    # Coverage of known procurement taxonomy: categories observed / taxonomy size
    observed_proc = {c for c in counter if c in PROCUREMENT_ACT_CATEGORIES}
    num = len(observed_proc)
    den = len(PROCUREMENT_ACT_CATEGORIES)
    distribution = {
        k: {"count": v, "pct": safe_pct(v, total)}
        for k, v in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    }
    return metric(
        name=f"act_category_distribution_{source}",
        numerator=num,
        denominator=den,
        formula="distinct procurement act_category labels observed / |PROCUREMENT_ACT_CATEGORIES|",
        period="artifact snapshot",
        sources=source_paths or ["(none)"],
        limitations=[
            "Distribution reflects classifier output on collected sample, not true publication mix.",
            f"Taxonomy size={den}; residual labels (outros, nao_relacionado, etc.) excluded from numerator.",
            f"Counts origin: {origin}.",
        ],
        calc_date=calc_date,
        run_id=run_id,
        confidence="medium" if total else "none",
        extras={
            "total_records_classified": total,
            "distribution": distribution,
            "procurement_categories_observed": sorted(observed_proc),
            "non_procurement_share_pct": safe_pct(
                sum(v for k, v in counter.items() if k not in PROCUREMENT_ACT_CATEGORIES),
                total,
            ),
        },
    )


def calc_field_completeness(
    *,
    source: str,
    records: list[dict[str, Any]],
    fields: list[str],
    calc_date: str,
    run_id: str,
    source_paths: list[str],
) -> dict[str, Any]:
    n = len(records)
    if n == 0:
        return metric(
            name=f"field_completeness_{source}",
            numerator=0,
            denominator=0,
            formula="mean over fields of (nonempty_count / n_records); reported as overall fill rate",
            period="artifact snapshot",
            sources=source_paths or ["(none)"],
            limitations=["No records available."],
            calc_date=calc_date,
            run_id=run_id,
            confidence="none",
            unit="pct",
            extras={"per_field": {}, "n_records": 0},
        )

    per_field: dict[str, dict[str, Any]] = {}
    fill_rates: list[float] = []
    for f in fields:
        filled = sum(1 for r in records if is_nonempty(r.get(f)))
        rate = filled / n
        fill_rates.append(rate)
        per_field[f] = {"filled": filled, "total": n, "pct": round(rate * 100, 2)}

    overall = sum(fill_rates) / len(fill_rates) if fill_rates else 0.0
    # Represent as numerator/denominator = sum(filled) / (n * n_fields)
    num = sum(per_field[f]["filled"] for f in fields)
    den = n * len(fields)
    return metric(
        name=f"field_completeness_{source}",
        numerator=num,
        denominator=den,
        formula="sum(nonempty field cells) / (n_records * n_core_fields)",
        period="artifact snapshot",
        sources=source_paths or ["(none)"],
        limitations=[
            "Core field set is project-defined, not a legal completeness standard.",
            "Empty string / null / empty list count as missing.",
        ],
        calc_date=calc_date,
        run_id=run_id,
        confidence="high" if n >= 10 else "medium",
        extras={
            "n_records": n,
            "fields": fields,
            "per_field": per_field,
            "mean_field_fill_pct": round(overall * 100, 2),
        },
    )


def calc_document_coverage(
    *,
    source: str,
    records: list[dict[str, Any]],
    link_keys: list[str],
    calc_date: str,
    run_id: str,
    source_paths: list[str],
) -> dict[str, Any]:
    n = len(records)
    with_doc = 0
    for rec in records:
        if any(is_nonempty(rec.get(k)) for k in link_keys):
            with_doc += 1
    return metric(
        name=f"document_coverage_{source}",
        numerator=with_doc,
        denominator=n if n else None,
        formula="records with ≥1 document/link field populated / n_records",
        period="artifact snapshot",
        sources=source_paths or ["(none)"],
        limitations=[
            "Presence of URL/link only — does not verify HTTP reachability or PDF parseability.",
            f"Link fields checked: {link_keys}",
        ],
        calc_date=calc_date,
        run_id=run_id,
        confidence="high" if n >= 10 else ("medium" if n else "none"),
        extras={"link_keys": link_keys, "n_records": n},
    )


def calc_freshness_hours(
    *,
    source: str,
    art: SourceArtifacts,
    now: datetime,
    calc_date: str,
    run_id: str,
) -> dict[str, Any]:
    """Hours since last successful collection / latest business date for a source."""
    sources = [str(p) for p in [art.summary_path, art.freshness_path, art.records_path] if p]
    completed_at: datetime | None = None
    latest_business: date | None = None
    method_parts: list[str] = []

    summary = art.summary or {}
    for key in ("completed_at", "generated_at", "started_at"):
        completed_at = parse_datetime(summary.get(key))
        if completed_at:
            method_parts.append(f"summary.{key}")
            break

    if art.freshness_manifest:
        fm = art.freshness_manifest
        if source == "ciga_dom":
            completed_at = parse_datetime(fm.get("generated_at")) or completed_at
            method_parts.append("freshness_manifest.generated_at")
            lrm = parse_datetime(fm.get("latest_resource_modified"))
            if lrm:
                latest_business = lrm.date()
                method_parts.append("freshness_manifest.latest_resource_modified")
        elif source == "pncp" and isinstance(fm, dict):
            # freshness-gate.json structure
            for cs in fm.get("critical_sources") or []:
                if cs.get("source") == "pncp":
                    completed_at = parse_datetime(cs.get("last_success_at")) or completed_at
                    latest_business = parse_date(cs.get("latest_business_date")) or latest_business
                    method_parts.append("freshness-gate critical_sources[pncp]")
                    sources.append(str(art.freshness_path))
                    break

    # Business date from records
    date_keys = {
        "ciga_dom": ["data", "data_publicacao"],
        "sc_compras": ["data_publicacao", "data_abertura"],
        "dados_abertos_sc": ["data_publicacao", "data_edicao"],
        "pncp": ["data_publicacao"],
    }.get(source, ["data_publicacao", "data"])
    for rec in art.records:
        for dk in date_keys:
            d = parse_date(rec.get(dk))
            if d and (latest_business is None or d > latest_business):
                latest_business = d

    if latest_business and "records" not in "".join(method_parts):
        method_parts.append("max(record business dates)")

    hours_collection = hours_since(completed_at, now)
    hours_business = None
    if latest_business:
        hours_business = hours_since(
            datetime(latest_business.year, latest_business.month, latest_business.day, tzinfo=UTC),
            now,
        )

    # Primary result: collection freshness hours (null if unknown)
    result_hours = hours_collection
    confidence = "high" if completed_at else ("medium" if latest_business else "none")
    limitations = [
        "freshness_hours is wall-clock age of last collection completion (or business date fallback).",
        "Negative business-date age can occur when max data_publicacao is in the future (planned openings).",
        "Does not prove downstream DB persistence — file artifact only.",
    ]
    if result_hours is None and hours_business is not None:
        result_hours = hours_business
        limitations.append("Collection timestamp missing; using latest business date as freshness proxy.")
        confidence = "low"

    return metric(
        name=f"freshness_hours_{source}",
        numerator=result_hours,
        denominator=1,
        formula="(now_utc - last_collection_completed_at).total_seconds()/3600",
        period=f"as of {now.isoformat()}",
        sources=sources or ["(none)"],
        limitations=limitations,
        calc_date=calc_date,
        run_id=run_id,
        confidence=confidence,
        unit="hours",
        extras={
            "last_collection_at": completed_at.isoformat() if completed_at else None,
            "latest_business_date": latest_business.isoformat() if latest_business else None,
            "hours_since_collection": hours_collection,
            "hours_since_latest_business_date": hours_business,
            "method": " + ".join(method_parts) if method_parts else "unavailable",
        },
    )


def calc_historical_editais_raw(calc_date: str, run_id: str, root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """Preserve the historical 4.76% metric without redefining it."""
    path = root / "output" / "coverage" / "next30d-metrics-final.json"
    num = HISTORICAL_EDITAIS_RAW["numerator"]
    den = HISTORICAL_EDITAIS_RAW["denominator"]
    result_pct = HISTORICAL_EDITAIS_RAW["result_pct"]
    sources = list(HISTORICAL_EDITAIS_RAW["sources"])
    if path.exists():
        data = read_json(path)
        if data.get("covered_200km") is not None:
            num = int(data["covered_200km"])
        if data.get("editais_denominator") is not None:
            den = int(data["editais_denominator"])
        if data.get("editais_crude_pct") is not None:
            result_pct = float(data["editais_crude_pct"])
        sources = [str(path)] + [s for s in sources if s != str(path)]

    m = metric(
        name="historical_editais_raw_coverage",
        numerator=num,
        denominator=den,
        formula=str(HISTORICAL_EDITAIS_RAW["formula"]),
        period=str(HISTORICAL_EDITAIS_RAW["period"]),
        sources=sources,
        limitations=[
            str(HISTORICAL_EDITAIS_RAW["note"]),
            str(HISTORICAL_EDITAIS_RAW["methodology_change_warning"]),
            "Evidence ledger was empty at truth generation; bid presence uses entity_coverage only.",
        ],
        calc_date=calc_date,
        run_id=run_id,
        confidence="high",  # high confidence that THIS is the preserved historical number
        extras={
            "preserved": True,
            "canonical_result_pct": result_pct,
            "do_not_overwrite": True,
            "denominator_definition": (
                "1093 = public entities in target universe within 200 km of Florianópolis"
            ),
            "numerator_definition": "52 = entities with ≥1 persisted bid (entity_coverage.total_bids)",
        },
    )
    # Force exact historical display value when math rounds to 4.76
    if m["result"] is not None and abs(m["result"] - result_pct) <= 0.05:
        m["result"] = result_pct
    return m


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def collect_all_metrics(
    *,
    root: Path = PROJECT_ROOT,
    window_days: int = 30,
    now: datetime | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    now = now or _now_utc()
    run_id = run_id or make_run_id(now)
    calc_date = now.date().isoformat()
    as_of = now.date()

    ibge = load_ibge_universe(root / "data" / "ibge_cache.json")
    ciga = discover_ciga_dom(root)
    sc = discover_sc_compras(root)
    dados = discover_dados_abertos_sc(root)
    pncp = discover_pncp(root)

    metrics: list[dict[str, Any]] = []

    # 0) Historical preserved metric
    metrics.append(calc_historical_editais_raw(calc_date, run_id, root))

    # 1) Municipalities with publication 30d
    metrics.append(
        calc_municipalities_with_publication_30d(
            ciga=ciga,
            ibge=ibge,
            window_days=window_days,
            as_of=as_of,
            calc_date=calc_date,
            run_id=run_id,
        )
    )

    # 2) Orgs with recent licitacao
    metrics.append(
        calc_orgs_with_recent_licitacao(
            ciga=ciga,
            sc=sc,
            dados=dados,
            window_days=window_days,
            as_of=as_of,
            calc_date=calc_date,
            run_id=run_id,
            root=root,
        )
    )

    # 3) PNCP SC reconciled
    metrics.append(calc_pncp_sc_reconciled(pncp=pncp, calc_date=calc_date, run_id=run_id))

    # 4) Source coverage (4 sources)
    for src_name, art in (
        ("dados_abertos_sc", dados),
        ("ciga_dom", ciga),
        ("sc_compras", sc),
        ("pncp", pncp),
    ):
        metrics.append(
            calc_source_coverage(
                source=src_name,
                art=art,
                ibge=ibge,
                calc_date=calc_date,
                run_id=run_id,
                as_of=as_of,
            )
        )

    # 5) Temporal coverage per source (artifact-backed)
    for src_name, art, dkeys in (
        ("ciga_dom", ciga, ["data", "data_publicacao"]),
        ("sc_compras", sc, ["data_publicacao", "data_abertura"]),
        ("dados_abertos_sc", dados, ["data_publicacao", "data_edicao"]),
    ):
        paths = [str(p) for p in [art.records_path, art.summary_path] if p]
        metrics.append(
            calc_temporal_coverage(
                source=src_name,
                records=art.records,
                date_keys=dkeys,
                window_days=window_days,
                as_of=as_of,
                calc_date=calc_date,
                run_id=run_id,
                source_paths=paths,
            )
        )

    # 6) Act category distribution
    for src_name, art in (("ciga_dom", ciga), ("dados_abertos_sc", dados)):
        paths = [str(p) for p in [art.records_path, art.summary_path] if p]
        summary_cats = None
        if art.summary and isinstance((art.summary.get("counts") or {}).get("act_categories"), dict):
            # Prefer record-level if we have full records; else summary
            if not art.records:
                summary_cats = art.summary["counts"]["act_categories"]
        metrics.append(
            calc_act_category_distribution(
                source=src_name,
                records=art.records,
                calc_date=calc_date,
                run_id=run_id,
                source_paths=paths,
                summary_categories=summary_cats,
            )
        )

    # 7) Field completeness
    for src_name, art in (
        ("ciga_dom", ciga),
        ("sc_compras", sc),
        ("dados_abertos_sc", dados),
    ):
        paths = [str(p) for p in [art.records_path, art.summary_path] if p]
        metrics.append(
            calc_field_completeness(
                source=src_name,
                records=art.records,
                fields=FIELD_SETS.get(src_name, []),
                calc_date=calc_date,
                run_id=run_id,
                source_paths=paths,
            )
        )

    # 8) Document coverage
    doc_specs = (
        ("ciga_dom", ciga, ["url"]),
        ("sc_compras", sc, ["link_pncp", "documentos"]),
        ("dados_abertos_sc", dados, ["link_edicao", "link_extrato"]),
    )
    for src_name, art, keys in doc_specs:
        paths = [str(p) for p in [art.records_path, art.summary_path] if p]
        metrics.append(
            calc_document_coverage(
                source=src_name,
                records=art.records,
                link_keys=keys,
                calc_date=calc_date,
                run_id=run_id,
                source_paths=paths,
            )
        )

    # 9) Freshness hours per source
    for src_name, art in (
        ("ciga_dom", ciga),
        ("sc_compras", sc),
        ("dados_abertos_sc", dados),
        ("pncp", pncp),
    ):
        metrics.append(
            calc_freshness_hours(
                source=src_name,
                art=art,
                now=now,
                calc_date=calc_date,
                run_id=run_id,
            )
        )

    artifacts_used = {
        "ciga_dom": {
            "summary": str(ciga.summary_path) if ciga.summary_path else None,
            "records": str(ciga.records_path) if ciga.records_path else None,
            "n_records": len(ciga.records),
            "freshness": str(ciga.freshness_path) if ciga.freshness_path else None,
        },
        "sc_compras": {
            "summary": str(sc.summary_path) if sc.summary_path else None,
            "records": str(sc.records_path) if sc.records_path else None,
            "n_records": len(sc.records),
        },
        "dados_abertos_sc": {
            "summary": str(dados.summary_path) if dados.summary_path else None,
            "records": str(dados.records_path) if dados.records_path else None,
            "n_records": len(dados.records),
            "records_are_samples_only": bool(dados.extra.get("records_are_samples_only")),
        },
        "pncp": {
            "opportunity_manifest": pncp.extra.get("opportunity_manifest_path"),
            "next30d_metrics": pncp.extra.get("next30d_metrics_path"),
            "target_reconciliation": pncp.extra.get("target_reconciliation_path"),
            "reconciliation_dir": pncp.extra.get("reconciliation_dir"),
            "freshness_gate": str(pncp.freshness_path) if pncp.freshness_path else None,
        },
        "ibge_cache": {
            "path": ibge.get("path"),
            "available": ibge.get("available"),
            "count": ibge.get("count"),
        },
    }

    global_limitations = [
        "All metrics are file-artifact based for this session; they may under-represent full portal coverage when runs are smoke/incremental.",
        "historical_editais_raw_coverage (4.76%) is preserved with its original 52/1093 methodology and must not be replaced by multi-source percentages.",
        "Denominators differ by metric (295 municipios vs 1093 entities vs API year totals) — never mix without re-basing.",
        "No live DB queries are performed by this module.",
        f"Window used for recency metrics: {window_days} days ending {as_of.isoformat()}.",
    ]

    return {
        "schema_version": 1,
        "run_id": run_id,
        "calc_date": calc_date,
        "generated_at": now.isoformat(),
        "window_days": window_days,
        "as_of": as_of.isoformat(),
        "project_root": str(root),
        "methodology": {
            "approach": "multi_source_file_artifacts_v1",
            "historical_metric_policy": "preserve_separately",
            "historical_metric_name": "historical_editais_raw_coverage",
            "historical_result_pct": 4.76,
            "sc_municipality_universe": ibge.get("count") or SC_MUNICIPALITY_UNIVERSE,
        },
        "artifacts_used": artifacts_used,
        "global_limitations": global_limitations,
        "metrics": metrics,
        "metrics_index": {m["name"]: m.get("result") for m in metrics},
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Multi-Source Coverage Report")
    lines.append("")
    lines.append(f"**run_id:** `{report['run_id']}`")
    lines.append(f"**calc_date:** {report['calc_date']}")
    lines.append(f"**generated_at:** {report['generated_at']}")
    lines.append(f"**window_days:** {report['window_days']}")
    lines.append(f"**as_of:** {report['as_of']}")
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    meth = report.get("methodology") or {}
    lines.append(f"- Approach: `{meth.get('approach')}`")
    lines.append(
        f"- Historical metric policy: **{meth.get('historical_metric_policy')}** "
        f"(`{meth.get('historical_metric_name')}` = {meth.get('historical_result_pct')}%)"
    )
    lines.append(f"- SC municipality universe: {meth.get('sc_municipality_universe')}")
    lines.append("")
    lines.append("> Do **not** compare new multi-source % values to the historical 4.76% without re-basing denominators.")
    lines.append("")
    lines.append("## Global limitations")
    lines.append("")
    for lim in report.get("global_limitations") or []:
        lines.append(f"- {lim}")
    lines.append("")
    lines.append("## Metrics summary")
    lines.append("")
    lines.append("| Metric | Result | Numerator | Denominator | Confidence | Unit |")
    lines.append("|--------|--------|-----------|-------------|------------|------|")
    for m in report.get("metrics") or []:
        res = m.get("result")
        res_s = "n/a" if res is None else str(res)
        lines.append(
            f"| `{m['name']}` | {res_s} | {m.get('numerator')} | {m.get('denominator')} | "
            f"{m.get('confidence')} | {m.get('result_unit')} |"
        )
    lines.append("")
    lines.append("## Metric details")
    lines.append("")
    for m in report.get("metrics") or []:
        lines.append(f"### `{m['name']}`")
        lines.append("")
        lines.append(f"- **result:** {m.get('result')} ({m.get('result_unit')})")
        lines.append(f"- **numerator:** {m.get('numerator')}")
        lines.append(f"- **denominator:** {m.get('denominator')}")
        lines.append(f"- **formula:** {m.get('formula')}")
        lines.append(f"- **period:** {m.get('period')}")
        lines.append(f"- **confidence:** {m.get('confidence')}")
        lines.append(f"- **calc_date:** {m.get('calc_date')}")
        lines.append(f"- **run_id:** `{m.get('run_id')}`")
        lines.append("- **sources:**")
        for s in m.get("sources") or []:
            lines.append(f"  - `{s}`")
        lines.append("- **limitations:**")
        for lim in m.get("limitations") or []:
            lines.append(f"  - {lim}")
        # compact extras
        skip = {
            "name",
            "numerator",
            "denominator",
            "formula",
            "period",
            "sources",
            "limitations",
            "calc_date",
            "run_id",
            "result",
            "result_unit",
            "confidence",
            "distribution",
            "per_field",
            "distinct_days_in_window",
            "match_results",
        }
        extras = {k: v for k, v in m.items() if k not in skip and v is not None}
        if extras:
            lines.append("- **extras:**")
            for k, v in extras.items():
                lines.append(f"  - {k}: `{v}`")
        if "distribution" in m and isinstance(m["distribution"], dict):
            lines.append("- **distribution (top 15):**")
            items = list(m["distribution"].items())[:15]
            for cat, info in items:
                lines.append(f"  - {cat}: {info}")
        if "per_field" in m and isinstance(m["per_field"], dict):
            lines.append("- **per_field:**")
            for fname, info in m["per_field"].items():
                lines.append(f"  - {fname}: {info}")
        lines.append("")

    lines.append("## Artifacts used")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(report.get("artifacts_used"), indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = report["run_id"]
    json_path = output_dir / f"multi_source-{run_id}.json"
    md_path = output_dir / f"multi_source-{run_id}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    # Convenience pointers
    latest_json = output_dir / "multi_source-latest.json"
    latest_md = output_dir / "multi_source-latest.md"
    latest_json.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_md.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    return json_path, md_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Multi-source coverage metrics (file artifacts)")
    parser.add_argument("--window-days", type=int, default=30, help="Recency window in days (default 30)")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for multi_source-{run_id}.json/.md",
    )
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT, help="Project root")
    parser.add_argument("--run-id", type=str, default=None, help="Optional fixed run_id")
    args = parser.parse_args(argv)

    report = collect_all_metrics(
        root=args.root.resolve(),
        window_days=args.window_days,
        run_id=args.run_id,
    )
    json_path, md_path = write_report(report, args.output_dir.resolve())

    # Console summary
    print(f"run_id={report['run_id']}")
    print(f"json={json_path}")
    print(f"md={md_path}")
    print("metrics:")
    for m in report["metrics"]:
        print(f"  - {m['name']}: result={m.get('result')} ({m.get('numerator')}/{m.get('denominator')}) conf={m.get('confidence')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
