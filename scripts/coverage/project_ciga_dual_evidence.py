#!/usr/bin/env python3
"""Project CIGA CKAN dual coverage_evidence for open_tenders (municipal).

Dual coverage (ADR-030) reads ``coverage_evidence``, not ``entity_coverage``.
Municipal open_tenders requires ``pncp + ciga_ckan``. This projector:

1. Loads the canonical universe (spreadsheet authority).
2. Selects entities whose required combination includes ``ciga_ckan``.
3. Crawls recent DOM-SC monthly packages from dados.ciga.sc.gov.br.
4. Matches publications to universe entities by normalized name + município.
5. Writes one ``coverage_evidence`` row per municipal entity:
   - ``success_with_data`` when matched with publication count > 0
   - ``success_zero`` when catalog crawl is complete and entity has no match

Fail-closed: incomplete crawl does not project success_zero for missing entities.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_logger = logging.getLogger(__name__)

SOURCE = "ciga_ckan"
DATA_TYPE = "bids"
CAPABILITY = "open_tenders"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime | None = None) -> str:
    d = dt or _utc_now()
    return d.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _connect(dsn: str) -> Any:
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    conn.autocommit = True
    return conn


def municipal_entities_needing_ciga(universe: Any, policy: Any) -> list[Any]:
    """Return universe entities whose open_tenders combination includes ciga_ckan."""
    from scripts.coverage.source_policy import (
        entity_attributes_from_canonical,
        select_required_combination,
    )

    out: list[Any] = []
    for ent in universe.conservative_monitoring_population:
        attrs = entity_attributes_from_canonical(ent)
        sel = select_required_combination(
            policy,
            CAPABILITY,
            attrs,
            validated_at=getattr(policy, "validated_at", None) or "",
        )
        comb = list(sel.get("selected_combination") or [])
        if SOURCE in comb:
            out.append(ent)
    return out


def _match_counts(
    universe_entities: list[Any],
    ciga_entities: dict[str, dict[str, Any]],
) -> dict[str, int]:
    """Map universe entity_id → publication count from CIGA extract."""
    from scripts.lib.name_normalizer import normalize_name

    # Index CIGA by (norm_name, municipio_upper) and by norm_name alone
    by_name_muni: dict[tuple[str, str], int] = {}
    by_name: dict[str, list[int]] = {}
    for entry in ciga_entities.values():
        norm = entry.get("norm_name") or normalize_name(entry.get("raw_name") or "")
        mun = (entry.get("municipio") or "").upper().strip()
        cnt = int(entry.get("count") or 0)
        if not norm:
            continue
        if mun:
            key = (norm, mun)
            by_name_muni[key] = by_name_muni.get(key, 0) + cnt
        by_name.setdefault(norm, []).append(cnt)

    counts: dict[str, int] = {}
    for ent in universe_entities:
        norm = normalize_name(ent.razao_social or "")
        mun = (ent.municipio or "").upper().strip()
        n = 0
        if norm and mun and (norm, mun) in by_name_muni:
            n = by_name_muni[(norm, mun)]
        elif norm and norm in by_name and len(by_name[norm]) == 1:
            n = by_name[norm][0]
        counts[ent.entity_id] = n
    return counts


def crawl_recent_ciga_months(*, max_months: int = 3) -> tuple[list[str], dict[str, dict], bool, str]:
    """Download up to ``max_months`` most recent DOM-SC packages.

    Returns (months, entities_dict, scope_complete, error_message).
    """
    from scripts.crawl.ciga_ckan_crawler import (
        download_month,
        extract_entities,
        list_domsc_months,
    )

    months = list_domsc_months()
    if not months:
        return [], {}, False, "no_domsc_months_listed"
    # Package ids like domsc-publicacoes-de-MM-YYYY (or bare MM-YYYY / YYYY-MM)
    def _sort_key(m: str) -> tuple[int, int]:
        import re

        s = m.replace("_", "-")
        found = re.findall(r"(\d{1,4})", s)
        if len(found) >= 2:
            a, b = found[-2], found[-1]
            # last two numeric groups: prefer (year, month)
            if len(b) == 4 and len(a) <= 2:
                return int(b), int(a)
            if len(a) == 4 and len(b) <= 2:
                return int(a), int(b)
            if len(a) == 4 and len(b) == 4:
                return int(a), int(b)
        return (0, 0)

    months_sorted = sorted(months, key=_sort_key, reverse=True)
    target = months_sorted[: max(1, max_months)]
    all_pubs: list[dict] = []
    errors: list[str] = []
    months_ok: list[str] = []
    for m in target:
        try:
            pubs = download_month(m)
            if pubs is None:
                errors.append(f"{m}:null")
                continue
            all_pubs.extend(pubs)
            months_ok.append(m)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{m}:{exc}")
            _logger.exception("CIGA month %s failed", m)
    entities = extract_entities(all_pubs) if all_pubs else {}
    # Scope complete only if every targeted month downloaded without error
    scope_complete = len(months_ok) == len(target) and not errors
    err = "; ".join(errors[:5]) if errors else ""
    return months_ok, entities, scope_complete, err


def project_ciga_coverage_evidence(
    *,
    dsn: str,
    max_months: int = 3,
    external_run_id: str | None = None,
    seed_path: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Crawl CIGA and project dual coverage_evidence for municipal entities."""
    from scripts.coverage.source_policy import load_source_policy
    from scripts.lib.universe import load_canonical_universe, resolve_default_seed_path

    policy = load_source_policy(
        _PROJECT_ROOT / "config" / "source_applicability.yaml",
        require_active=True,
    )
    seed = seed_path or resolve_default_seed_path(_PROJECT_ROOT)
    universe = load_canonical_universe(seed_path=seed)
    targets = municipal_entities_needing_ciga(universe, policy)
    run_id = external_run_id or f"ciga-dual-{_utc_now().strftime('%Y%m%dT%H%M%SZ')}"

    months_ok, ciga_entities, scope_complete, crawl_err = crawl_recent_ciga_months(
        max_months=max_months
    )
    match_counts = _match_counts(targets, ciga_entities)
    matched_with_data = sum(1 for v in match_counts.values() if v > 0)

    summary: dict[str, Any] = {
        "source": SOURCE,
        "capability": CAPABILITY,
        "run_id": run_id,
        "generated_at": _iso(),
        "municipal_targets": len(targets),
        "months_ok": months_ok,
        "scope_complete": scope_complete,
        "crawl_error": crawl_err or None,
        "ciga_unique_entities": len(ciga_entities),
        "matched_with_data": matched_with_data,
        "projected": 0,
        "success_with_data": 0,
        "success_zero": 0,
        "skipped": 0,
        "dry_run": dry_run,
    }

    if not scope_complete:
        summary["status"] = "FAIL"
        summary["note"] = (
            "Incomplete CIGA crawl — refuse success_zero projection "
            "(fail-closed; dual coverage must not invent completeness)"
        )
        return summary

    if dry_run:
        summary["status"] = "DRY_RUN"
        summary["would_project"] = len(targets)
        return summary

    conn = _connect(dsn)
    try:
        projected = _upsert_rows(
            conn,
            entities=targets,
            match_counts=match_counts,
            run_id=run_id,
            months_ok=months_ok,
        )
    finally:
        conn.close()

    summary.update(projected)
    summary["status"] = "OK"
    return summary


def _upsert_rows(
    conn: Any,
    *,
    entities: list[Any],
    match_counts: dict[str, int],
    run_id: str,
    months_ok: list[str],
) -> dict[str, int]:
    """Insert/update coverage_evidence rows using canonical unique index."""
    now = _utc_now()
    period_end = date.today()
    # approximate window from oldest month string if possible
    period_start = period_end
    sql = """
        INSERT INTO coverage_evidence (
            entity_id, canonical_entity_key, source, data_type, capability,
            applicability, scope_key, queried_start, queried_end, run_id,
            started_at, completed_at, checked_at,
            count_obtained, count_transformed, count_persisted,
            state, pages_expected, pages_processed, records_fetched, open_records,
            freshness_status, error_code, error_message, metadata, evidence_metadata
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s::evidence_state, %s, %s, %s, %s,
            %s, %s, %s, %s::jsonb, %s::jsonb
        )
        ON CONFLICT (canonical_entity_key, source, data_type, run_id)
            WHERE canonical_entity_key IS NOT NULL
        DO UPDATE SET
            capability = EXCLUDED.capability,
            applicability = EXCLUDED.applicability,
            checked_at = EXCLUDED.checked_at,
            completed_at = EXCLUDED.completed_at,
            state = EXCLUDED.state,
            pages_expected = EXCLUDED.pages_expected,
            pages_processed = EXCLUDED.pages_processed,
            records_fetched = EXCLUDED.records_fetched,
            count_obtained = EXCLUDED.count_obtained,
            count_persisted = EXCLUDED.count_persisted,
            open_records = EXCLUDED.open_records,
            freshness_status = EXCLUDED.freshness_status,
            error_code = EXCLUDED.error_code,
            error_message = EXCLUDED.error_message,
            metadata = EXCLUDED.metadata,
            evidence_metadata = EXCLUDED.evidence_metadata
    """
    scope_key = f"ciga_domsc_months={','.join(months_ok)}"
    success_data = 0
    success_zero = 0
    with conn.cursor() as cur:
        for ent in entities:
            n = int(match_counts.get(ent.entity_id) or 0)
            if n > 0:
                state = "success_with_data"
                success_data += 1
            else:
                state = "success_zero"
                success_zero += 1
            meta = {
                "completion_rule": "complete",
                "pagination_complete": True,
                "provenance": "ciga_ckan_domsc_catalog",
                "evidence_persisted": True,
                "source_strategy": "ciga_domsc_monthly_packages",
                "months": months_ok,
                "scope_complete": True,
                "matched_publications": n,
                "universe_entity_id": ent.entity_id,
                "municipio": ent.municipio,
            }
            meta_json = json.dumps(meta, ensure_ascii=False, default=str)
            # pages: one logical page per month package completed
            pages = max(1, len(months_ok))
            cur.execute(
                sql,
                (
                    ent.db_entity_id,  # may be None
                    ent.entity_id,
                    SOURCE,
                    DATA_TYPE,
                    CAPABILITY,
                    "applicable",
                    scope_key,
                    period_start,
                    period_end,
                    run_id,
                    now,
                    now,
                    now,
                    n,  # count_obtained
                    n,  # count_transformed
                    n,  # count_persisted
                    state,
                    pages,  # pages_expected
                    pages,  # pages_processed
                    n,  # records_fetched
                    n,  # open_records
                    "fresh",
                    None,
                    None,
                    meta_json,
                    meta_json,
                ),
            )
    return {
        "projected": len(entities),
        "success_with_data": success_data,
        "success_zero": success_zero,
        "skipped": 0,
    }


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Project CIGA dual coverage_evidence")
    p.add_argument("--dsn", default=None)
    p.add_argument("--max-months", type=int, default=3)
    p.add_argument("--run-id", default=None)
    p.add_argument("--seed", type=Path, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)
    dsn = (
        args.dsn
        or os.environ.get("LOCAL_DATALAKE_DSN")
        or os.environ.get("DATABASE_URL")
    )
    if not dsn and not args.dry_run:
        print(json.dumps({"error": "DSN required"}, ensure_ascii=False))
        return 1
    report = project_ciga_coverage_evidence(
        dsn=dsn or "postgresql://invalid",
        max_months=args.max_months,
        external_run_id=args.run_id,
        seed_path=args.seed,
        dry_run=args.dry_run or not dsn,
    )
    text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0 if report.get("status") in {"OK", "DRY_RUN"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
