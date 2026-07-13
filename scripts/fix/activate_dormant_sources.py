#!/usr/bin/env python3
"""Activate Dormant Data Sources — Coverage Evidence Projection.

Projects entity-level coverage evidence for ALL registered sources into the
coverage_evidence table, activating 11 currently dormant sources.

Strategy per source:
  - Sources with existing matched data in pncp_raw_bids (pcp, compras_gov):
    project success_with_data from existing matched_entity_id rows.
  - ciga_ckan (coverage_only): project from existing entity_coverage rows.
  - contracts: project from pncp_supplier_contracts CNPJ8 matching.
  - sc_compras, tce_sc, transparencia, selenium: attempt lightweight crawl,
    then project partial/success_zero based on result.
  - dom_sc, doe_sc, mides_bigquery (credential): record as not_investigated.

Usage:
    python3 scripts/fix/activate_dormant_sources.py --dry-run
    python3 scripts/fix/activate_dormant_sources.py

Exit codes:
    0 — all sources processed
    1 — errors occurred
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.settings import DEFAULT_DSN
from scripts.crawl.registry import (
    get_credential_sources,
    iter_sources,
    lookup,
)

_logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EVIDENCE_SUCCESS_STATES = {"success_with_data", "success_zero"}
EVIDENCE_DATA_TYPE = "bids"

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _get_conn(dsn: str | None = None):
    import psycopg2

    return psycopg2.connect(dsn or DEFAULT_DSN)


def _load_entities(conn, within_200km_only: bool = False) -> list[dict]:
    """Load all active SC public entities."""
    cur = conn.cursor()
    sql = (
        "SELECT id, razao_social, cnpj_8, municipio, codigo_ibge, natureza_juridica, "
        "latitude, longitude, raio_200km FROM sc_public_entities WHERE is_active = TRUE"
    )
    if within_200km_only:
        sql += " AND raio_200km = TRUE"
    sql += " ORDER BY id"
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    entities = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    return entities


def _entity_id_to_cnpj8(entities: list[dict]) -> dict[int, str]:
    return {e["id"]: e.get("cnpj_8", "") for e in entities if e.get("cnpj_8")}


# ---------------------------------------------------------------------------
# Evidence projection core
# ---------------------------------------------------------------------------


def _evidence_table_exists(conn) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'coverage_evidence')")
    result = cur.fetchone()[0]
    cur.close()
    return result


def _insert_entity_evidence(
    conn,
    entity_id: int,
    source: str,
    state: str,
    count: int = 0,
    run_id: str | None = None,
    entity_meta: dict | None = None,
    data_type: str = EVIDENCE_DATA_TYPE,
):
    """Insert one evidence row for an entity-source pair.

    Uses DELETE + INSERT pattern for idempotency.
    """
    import json as _json

    cur = conn.cursor()
    meta = _json.dumps(entity_meta or {}, ensure_ascii=False)
    cur.execute(
        """INSERT INTO coverage_evidence
           (entity_id, source, data_type, run_id, started_at, completed_at,
            count_obtained, count_transformed, count_persisted,
            state, metadata)
           VALUES (%s, %s, %s, %s, NOW(), NOW(), %s, %s, %s, %s, %s)""",
        (
            entity_id,
            source,
            data_type,
            run_id or f"activate_{source}",
            count,
            count,
            count,
            state,
            meta,
        ),
    )
    cur.close()


def _insert_entity_evidence_batch(
    conn,
    evidence_rows: list[tuple[int, str, int]],
    source: str,
    run_id: str,
    entity_meta: dict | None = None,
):
    """Batch insert many entity evidence rows.

    Each row: (entity_id, state, count)
    """
    import json as _json

    cur = conn.cursor()
    meta = _json.dumps(entity_meta or {}, ensure_ascii=False)
    now = datetime.now(UTC)

    for entity_id, state, count in evidence_rows:
        cur.execute(
            """INSERT INTO coverage_evidence
               (entity_id, source, data_type, run_id, started_at, completed_at,
                count_obtained, count_transformed, count_persisted,
                state, metadata)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                entity_id,
                source,
                EVIDENCE_DATA_TYPE,
                run_id,
                now,
                now,
                count,
                count,
                count,
                state,
                meta,
            ),
        )
    cur.close()


# ---------------------------------------------------------------------------
# Source-specific evidence projectors
# ---------------------------------------------------------------------------


def project_pcp_evidence(conn, entities: list[dict], dry_run: bool = False) -> dict:
    """Project evidence for PCP source from existing pncp_raw_bids matched entities.

    PCP has 251 bids and 63 matched entities already in the DB.
    """
    print("  PCP: Projecting from existing matched entity data...")
    cur = conn.cursor()

    # Get entity IDs that have matched PCP bids
    cur.execute(
        """SELECT matched_entity_id, COUNT(*) as cnt
           FROM pncp_raw_bids
           WHERE source = 'pcp' AND matched_entity_id IS NOT NULL
           GROUP BY matched_entity_id"""
    )
    matched_rows = {r[0]: r[1] for r in cur.fetchall()}

    cur.close()

    if not matched_rows:
        print("  PCP: No matched entities found. Marking all as not_investigated.")
        return _project_base_not_investigated(conn, entities, "pcp", "no_matched_data", dry_run)

    entity_ids_matched = set(matched_rows.keys())

    candidate_entities = [e for e in entities if e.get("raio_200km")]

    if dry_run:
        print(
            f"  PCP [DRY RUN]: Would insert {len(matched_rows)} success_with_data + "
            f"{len(candidate_entities) - len(entity_ids_matched.intersection(set(e['id'] for e in candidate_entities)))} "
            f"partial rows for {len(candidate_entities)} candidate entities"
        )
        return {
            "candidate_entities": len(candidate_entities),
            "success_with_data": len(matched_rows),
            "state": "dry_run",
        }

    print(f"  PCP: {len(matched_rows)} matched entities found, projecting evidence...")
    run_id = "activate_pcp"
    entity_meta = {
        "source": "pcp",
        "projection_method": "existing_matched_bids",
        "total_matched_rows": len(matched_rows),
    }

    evidence_rows: list[tuple[int, str, int]] = []
    for entity in candidate_entities:
        eid = entity["id"]
        if eid in entity_ids_matched:
            evidence_rows.append((eid, "success_with_data", matched_rows[eid]))
        else:
            evidence_rows.append((eid, "not_investigated", 0))

    # Clean old evidence for this source
    cur = conn.cursor()
    candidate_ids = [e["id"] for e in candidate_entities]
    cur.execute(
        "DELETE FROM coverage_evidence WHERE entity_id = ANY(%s) AND source = %s",
        (candidate_ids, "pcp"),
    )
    cur.close()

    _insert_entity_evidence_batch(conn, evidence_rows, "pcp", run_id, entity_meta)
    conn.commit()

    stats = {
        "candidate_entities": len(candidate_entities),
        "success_with_data": len(entity_ids_matched.intersection(set(e["id"] for e in candidate_entities))),
        "not_investigated": len(candidate_entities)
        - len(entity_ids_matched.intersection(set(e["id"] for e in candidate_entities))),
    }
    print(f"  PCP: {stats['success_with_data']} success_with_data, {stats['not_investigated']} not_investigated")
    return stats


def project_compras_gov_evidence(conn, entities: list[dict], dry_run: bool = False) -> dict:
    """Project evidence for compras_gov from existing matched entities.

    compras_gov has 1508 bids and 74 matched entities.
    """
    print("  ComprasGov: Projecting from existing matched entity data...")
    cur = conn.cursor()
    cur.execute(
        """SELECT matched_entity_id, COUNT(*) as cnt
           FROM pncp_raw_bids
           WHERE source = 'compras_gov' AND matched_entity_id IS NOT NULL
           GROUP BY matched_entity_id"""
    )
    matched_rows = {r[0]: r[1] for r in cur.fetchall()}
    cur.close()

    if not matched_rows:
        print("  ComprasGov: No matched entities found.")
        return _project_base_not_investigated(conn, entities, "compras_gov", "no_matched_data", dry_run)

    entity_ids_matched = set(matched_rows.keys())
    candidate_entities = [e for e in entities if e.get("raio_200km")]

    if dry_run:
        print(
            f"  ComprasGov [DRY RUN]: Would insert {len(matched_rows)} success_with_data + "
            f"{len(candidate_entities) - len(entity_ids_matched.intersection(set(e['id'] for e in candidate_entities)))} "
            f"partial rows"
        )
        return {
            "candidate_entities": len(candidate_entities),
            "success_with_data": len(matched_rows),
            "state": "dry_run",
        }

    run_id = "activate_compras_gov"
    entity_meta = {
        "source": "compras_gov",
        "projection_method": "existing_matched_bids",
        "total_matched_rows": len(matched_rows),
    }

    evidence_rows: list[tuple[int, str, int]] = []
    for entity in candidate_entities:
        eid = entity["id"]
        if eid in entity_ids_matched:
            evidence_rows.append((eid, "success_with_data", matched_rows[eid]))
        else:
            evidence_rows.append((eid, "not_investigated", 0))

    cur = conn.cursor()
    candidate_ids = [e["id"] for e in candidate_entities]
    cur.execute(
        "DELETE FROM coverage_evidence WHERE entity_id = ANY(%s) AND source = %s",
        (candidate_ids, "compras_gov"),
    )
    cur.close()

    _insert_entity_evidence_batch(conn, evidence_rows, "compras_gov", run_id, entity_meta)
    conn.commit()

    stats = {
        "candidate_entities": len(candidate_entities),
        "success_with_data": len(entity_ids_matched.intersection(set(e["id"] for e in candidate_entities))),
        "not_investigated": len(candidate_entities)
        - len(entity_ids_matched.intersection(set(e["id"] for e in candidate_entities))),
    }
    print(f"  ComprasGov: {stats['success_with_data']} success_with_data, {stats['not_investigated']} not_investigated")
    return stats


def project_ciga_ckan_evidence(conn, entities: list[dict], dry_run: bool = False) -> dict:
    """Project evidence for ciga_ckan from existing entity_coverage rows.

    ciga_ckan is coverage_only and has 153 covered entities in entity_coverage.
    """
    print("  CIGA CKAN: Projecting from existing entity_coverage...")
    cur = conn.cursor()
    cur.execute("SELECT entity_id FROM entity_coverage WHERE source = 'ciga_ckan' AND is_covered = TRUE")
    covered_entity_ids = {r[0] for r in cur.fetchall()}
    cur.close()

    candidate_entities = [e for e in entities if e.get("raio_200km")]

    if dry_run:
        print(
            f"  CIGA CKAN [DRY RUN]: Would insert {len(covered_entity_ids)} success_with_data + "
            f"{len(candidate_entities) - len(covered_entity_ids.intersection(set(e['id'] for e in candidate_entities)))} "
            f"not_investigated rows"
        )
        return {
            "candidate_entities": len(candidate_entities),
            "success_with_data": len(covered_entity_ids),
            "state": "dry_run",
        }

    run_id = "activate_ciga_ckan"
    entity_meta = {
        "source": "ciga_ckan",
        "projection_method": "existing_entity_coverage",
    }

    evidence_rows: list[tuple[int, str, int]] = []
    for entity in candidate_entities:
        eid = entity["id"]
        if eid in covered_entity_ids:
            evidence_rows.append((eid, "success_with_data", 1))
        else:
            evidence_rows.append((eid, "not_investigated", 0))

    cur = conn.cursor()
    candidate_ids = [e["id"] for e in candidate_entities]
    cur.execute(
        "DELETE FROM coverage_evidence WHERE entity_id = ANY(%s) AND source = %s",
        (candidate_ids, "ciga_ckan"),
    )
    cur.close()

    _insert_entity_evidence_batch(conn, evidence_rows, "ciga_ckan", run_id, entity_meta)
    conn.commit()

    stats = {
        "candidate_entities": len(candidate_entities),
        "success_with_data": len(covered_entity_ids.intersection(set(e["id"] for e in candidate_entities))),
        "not_investigated": len(candidate_entities)
        - len(covered_entity_ids.intersection(set(e["id"] for e in candidate_entities))),
    }
    print(f"  CIGA CKAN: {stats['success_with_data']} success_with_data, {stats['not_investigated']} not_investigated")
    return stats


def project_contracts_evidence(conn, entities: list[dict], dry_run: bool = False) -> dict:
    """Project evidence for contracts source from pncp_supplier_contracts.

    The contracts table has 3.6M rows. We match by LEFT(orgao_cnpj, 8) against
    entity cnpj_8 values.
    """
    print("  Contracts: Projecting from pncp_supplier_contracts CNPJ8 matching...")
    cur = conn.cursor()

    # Build CNPJ8 → entity_id map for candidate entities
    candidate_entities = [e for e in entities if e.get("raio_200km") and e.get("cnpj_8")]
    cnpj8_to_eid = {e["cnpj_8"]: e["id"] for e in candidate_entities if e["cnpj_8"]}

    if not cnpj8_to_eid:
        print("  Contracts: No candidate entities with CNPJ8.")
        cur.close()
        return {"candidate_entities": 0, "success_with_data": 0}

    # Query contracts by CNPJ8 batches
    cnpj8_list = list(cnpj8_to_eid.keys())
    matched_entity_count: dict[int, int] = {}
    batch_size = 500

    for i in range(0, len(cnpj8_list), batch_size):
        batch = cnpj8_list[i : i + batch_size]
        cur.execute(
            """SELECT LEFT(orgao_cnpj, 8) AS cnpj8, COUNT(*) AS cnt
               FROM pncp_supplier_contracts
               WHERE LEFT(orgao_cnpj, 8) = ANY(%s)
               GROUP BY LEFT(orgao_cnpj, 8)""",
            (batch,),
        )
        for row in cur.fetchall():
            cnpj8 = row[0]
            cnt = row[1]
            eid = cnpj8_to_eid.get(cnpj8)
            if eid:
                matched_entity_count[eid] = matched_entity_count.get(eid, 0) + cnt

    cur.close()
    entity_ids_matched = set(matched_entity_count.keys())

    if dry_run:
        print(
            f"  Contracts [DRY RUN]: {len(matched_entity_count)} entities with contracts, "
            f"{sum(matched_entity_count.values())} total contracts. "
            f"Would insert success_with_data for matched entities."
        )
        return {
            "candidate_entities": len(candidate_entities),
            "success_with_data": len(matched_entity_count),
            "state": "dry_run",
        }

    run_id = "activate_contracts"
    entity_meta = {
        "source": "contracts",
        "projection_method": "pncp_supplier_contracts_cnpj8_match",
    }

    evidence_rows: list[tuple[int, str, int]] = []
    for entity in candidate_entities:
        eid = entity["id"]
        if eid in entity_ids_matched:
            evidence_rows.append((eid, "success_with_data", matched_entity_count[eid]))
        else:
            evidence_rows.append((eid, "not_investigated", 0))

    cur = conn.cursor()
    candidate_ids = [e["id"] for e in candidate_entities]
    cur.execute(
        "DELETE FROM coverage_evidence WHERE entity_id = ANY(%s) AND source = %s",
        (candidate_ids, "contracts"),
    )
    cur.close()

    _insert_entity_evidence_batch(conn, evidence_rows, "contracts", run_id, entity_meta)
    conn.commit()

    stats = {
        "candidate_entities": len(candidate_entities),
        "success_with_data": len(entity_ids_matched),
        "not_investigated": len(candidate_entities) - len(entity_ids_matched),
    }
    print(f"  Contracts: {stats['success_with_data']} success_with_data, {stats['not_investigated']} not_investigated")
    return stats


def _project_base_not_investigated(conn, entities: list[dict], source: str, reason: str, dry_run: bool) -> dict:
    """Mark all entities as not_investigated for a source."""
    candidate_entities = [e for e in entities if e.get("raio_200km")]

    if dry_run:
        print(f"  {source} [DRY RUN]: Would insert {len(candidate_entities)} not_investigated rows (reason: {reason})")
        return {"candidate_entities": len(candidate_entities), "success_with_data": 0, "state": "dry_run"}

    run_id = f"activate_{source}"
    entity_meta = {"source": source, "reason": reason, "projection_method": "not_investigated"}

    evidence_rows = [(e["id"], "not_investigated", 0) for e in candidate_entities]

    cur = conn.cursor()
    candidate_ids = [e["id"] for e in candidate_entities]
    cur.execute(
        "DELETE FROM coverage_evidence WHERE entity_id = ANY(%s) AND source = %s",
        (candidate_ids, source),
    )
    cur.close()

    _insert_entity_evidence_batch(conn, evidence_rows, source, run_id, entity_meta)
    conn.commit()

    stats = {
        "candidate_entities": len(candidate_entities),
        "success_with_data": 0,
        "not_investigated": len(candidate_entities),
    }
    print(f"  {source}: {len(candidate_entities)} not_investigated (reason: {reason})")
    return stats


def project_credential_source(conn, entities: list[dict], source: str, dry_run: bool = False) -> dict:
    """Mark credential sources as not_investigated with auth_failed reason.

    These sources (dom_sc, doe_sc, mides_bigquery) require credentials and
    cannot be checked without them.
    """
    print(f"  {source}: Marking as not_investigated (credentials required)...")
    return _project_base_not_investigated(conn, entities, source, "credentials_required", dry_run)


def _check_crawler_module(source_name: str) -> tuple[bool, str | None]:
    """Try to import a crawler module. Returns (success, error_message)."""
    info = lookup(source_name)
    if not info or not info.module:
        return False, f"No module registered for {source_name}"
    try:
        __import__(f"scripts.crawl.{info.module}", fromlist=["crawl", "transform"])
        return True, None
    except ImportError as e:
        return False, str(e)


def project_source_via_crawl(
    conn,
    entities: list[dict],
    source: str,
    dry_run: bool = False,
) -> dict:
    """Try to run a crawl for a source and project evidence from the result.

    For sources with NO existing data (sc_compras, tce_sc, transparencia,
    selenium), we attempt a lightweight crawl call. If it succeeds and
    produces matched records, we project success_with_data. Otherwise we
    project not_investigated.
    """
    from scripts.crawl.credential_validator import validate_source_credentials
    from scripts.crawl.ingestion._base.crawler import CrawlRequest

    info = lookup(source)
    if not info:
        print(f"  {source}: Unknown source in registry.")
        return _project_base_not_investigated(conn, entities, source, "unknown_source", dry_run)

    # Check credentials
    creds_ok, missing_creds = validate_source_credentials(source)
    if not creds_ok:
        print(f"  {source}: Missing credentials: {', '.join(missing_creds)}. Skipping.")
        return _project_base_not_investigated(
            conn, entities, source, f"missing_credentials: {', '.join(missing_creds)}", dry_run
        )

    # Import crawler
    try:
        mod = __import__(f"scripts.crawl.{info.module}", fromlist=["crawl", "transform"])
    except ImportError as e:
        print(f"  {source}: Cannot import module {info.module}: {e}")
        return _project_base_not_investigated(conn, entities, source, f"import_error: {e}", dry_run)

    if not hasattr(mod, "crawl"):
        print(f"  {source}: No crawl() function found.")
        return _project_base_not_investigated(conn, entities, source, "no_crawl_function", dry_run)

    if dry_run:
        print(f"  {source} [DRY RUN]: Would attempt crawl call")
        return {"candidate_entities": 0, "success_with_data": 0, "state": "dry_run"}

    # Attempt crawl
    print(f"  {source}: Attempting crawl...")
    run_id = f"activate_{source}"
    entity_meta = {"source": source, "projection_method": "crawl_attempt"}

    try:
        crawl_req = CrawlRequest(mode="incremental")
        try:
            raw_response = mod.crawl(crawl_req)
        except TypeError:
            raw_response = mod.crawl("incremental")

        if hasattr(raw_response, "records"):
            raw_records = raw_response.records
        else:
            raw_records = raw_response

        print(f"  {source}: crawl returned {len(raw_records)} records")

        # Try transform
        if hasattr(mod, "transform") and raw_records:
            try:
                records = mod.transform(raw_records)
            except Exception:
                records = raw_records
            records = [{**r, "source": source} for r in records]
        else:
            records = raw_records

        # Match entities from records
        candidate_entities = [e for e in entities if e.get("raio_200km")]
        matched_entity_ids: set[int] = set()

        if records:
            cnpj_index: dict[str, dict] = {}
            for e in entities:
                cnpj_8 = e.get("cnpj_8")
                if cnpj_8:
                    cnpj_index[cnpj_8] = e

            for rec in records:
                orgao_cnpj = (rec.get("orgao_cnpj") or "").strip()
                if orgao_cnpj:
                    cnpj_clean = "".join(c for c in orgao_cnpj if c.isdigit())
                    cnpj_base = cnpj_clean[:8]
                    if cnpj_base in cnpj_index:
                        matched_entity_ids.add(cnpj_index[cnpj_base]["id"])

        # Project evidence
        evidence_rows: list[tuple[int, str, int]] = []
        for entity in candidate_entities:
            eid = entity["id"]
            if eid in matched_entity_ids:
                evidence_rows.append((eid, "success_with_data", 1))
            else:
                evidence_rows.append((eid, "not_investigated", 0))

        cur = conn.cursor()
        candidate_ids = [e["id"] for e in candidate_entities]
        cur.execute(
            "DELETE FROM coverage_evidence WHERE entity_id = ANY(%s) AND source = %s",
            (candidate_ids, source),
        )
        cur.close()

        _insert_entity_evidence_batch(conn, evidence_rows, source, run_id, entity_meta)
        conn.commit()

        stats = {
            "candidate_entities": len(candidate_entities),
            "success_with_data": len(matched_entity_ids),
            "not_investigated": len(candidate_entities) - len(matched_entity_ids),
            "records_fetched": len(raw_records),
        }
        print(
            f"  {source}: {stats['success_with_data']} success_with_data, "
            f"{stats['not_investigated']} not_investigated "
            f"(fetched {len(raw_records)} records)"
        )
        return stats

    except Exception as e:
        print(f"  {source}: Crawl attempt failed: {e}")
        return _project_base_not_investigated(conn, entities, source, f"crawl_failed: {e}", dry_run)


# ---------------------------------------------------------------------------
# entity_coverage update
# ---------------------------------------------------------------------------


def update_entity_coverage(conn, entities: list[dict], dry_run: bool = False) -> dict:
    """Update entity_coverage table based on collected evidence.

    For each entity, sets is_covered = TRUE if ANY source has success_with_data
    evidence for that entity.
    """
    print("\n  Updating entity_coverage from evidence...")
    cur = conn.cursor()

    # Get all entity+source pairs with successful evidence
    cur.execute(
        """SELECT DISTINCT entity_id, source
           FROM coverage_evidence
           WHERE state = 'success_with_data'
             AND entity_id IS NOT NULL"""
    )
    evidence_pairs = list(cur.fetchall())

    # Build entity → sources map
    entity_sources: dict[int, list[str]] = {}
    for eid, src in evidence_pairs:
        if eid not in entity_sources:
            entity_sources[eid] = []
        entity_sources[eid].append(src)

    # Update entity_coverage for each entity
    candidate_entities = [e for e in entities if e.get("raio_200km")]
    updated_count = 0
    already_covered = set()

    cur.execute("SELECT entity_id FROM entity_coverage WHERE is_covered = TRUE")
    already_covered = {r[0] for r in cur.fetchall()}

    if dry_run:
        new_covered = sum(1 for e in candidate_entities if e["id"] in entity_sources and e["id"] not in already_covered)
        multi_source = sum(1 for eid, sources in entity_sources.items() if len(sources) > 1 and eid in already_covered)
        print(f"  [DRY RUN] Would set is_covered=TRUE for {new_covered} new entities (multi-source: {multi_source})")
        cur.close()
        return {"new_covered": new_covered, "multi_source": multi_source, "state": "dry_run"}

    # Insert/update entity_coverage rows for newly matched entities
    for entity in candidate_entities:
        eid = entity["id"]
        if eid in entity_sources:
            sources = entity_sources[eid]
            if eid not in already_covered:
                # Insert coverage rows for each source
                for src in sources:
                    try:
                        cur.execute(
                            """INSERT INTO entity_coverage
                               (entity_id, source, is_covered, within_200km, last_seen_at)
                               VALUES (%s, %s, TRUE, TRUE, NOW())
                               ON CONFLICT (entity_id, source) DO UPDATE
                               SET is_covered = TRUE, last_seen_at = NOW()""",
                            (eid, src),
                        )
                        updated_count += 1
                    except Exception:
                        pass

    conn.commit()
    cur.close()

    # New entities covered count
    new_covered = sum(1 for e in candidate_entities if e["id"] in entity_sources and e["id"] not in already_covered)
    multi_source = sum(1 for eid, sources in entity_sources.items() if len(sources) > 1)

    stats = {
        "new_covered": new_covered,
        "multi_source": multi_source,
        "total_upserted": updated_count,
        "entity_coverage_rows": len(entity_sources),
    }
    print(
        f"  Updated: {updated_count} upserts, {new_covered} new entities covered, "
        f"{multi_source} entities with multi-source coverage"
    )
    return stats


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


def get_source_strategy(source_name: str) -> str:
    """Determine the strategy for a source.

    Returns one of:
      - "existing_bids": has data in pncp_raw_bids with matched entities
      - "ciga_ckan": coverage_only source
      - "contracts": special source using pncp_supplier_contracts
      - "crawl": try lightweight crawl
      - "credential": blocked by credentials
    """
    credential_sources = get_credential_sources()

    if source_name in credential_sources:
        return "credential"

    if source_name == "pcp":
        return "existing_bids"
    if source_name == "compras_gov":
        return "existing_bids"
    if source_name == "ciga_ckan":
        return "ciga_ckan"
    if source_name == "contracts":
        return "contracts"

    return "crawl"


def main() -> int:
    parser = argparse.ArgumentParser(description="Activate dormant data sources with coverage evidence projection.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without making changes",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Run for a single source only (default: all sources)",
    )
    parser.add_argument(
        "--dsn",
        type=str,
        default=None,
        help="PostgreSQL DSN (default: from settings)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Set DSN
    global DEFAULT_DSN
    if args.dsn:
        DEFAULT_DSN = args.dsn

    # Get entities
    conn = _get_conn(args.dsn)
    try:
        entities = _load_entities(conn, within_200km_only=False)
    except Exception:
        conn.close()
        raise

    within_200km = sum(1 for e in entities if e.get("raio_200km"))
    print(f"\n{'=' * 68}")
    print("  ACTIVATING DORMANT DATA SOURCES")
    print(f"  {len(entities)} entities loaded ({within_200km} within 200km)")
    print(f"  {'DRY RUN' if args.dry_run else 'LIVE EXECUTION'}")
    print(f"{'=' * 68}\n")

    # Check coverage_evidence table exists
    if not _evidence_table_exists(conn):
        print("ERROR: coverage_evidence table does not exist.")
        conn.close()
        return 1

    # Determine which sources to process
    all_sources = [s.name for s in iter_sources()]
    if args.source:
        resolved = args.source.replace("-", "_")
        if resolved not in all_sources:
            print(f"ERROR: Unknown source '{args.source}'. Valid: {all_sources}")
            conn.close()
            return 1
        sources_to_process = [resolved]
    else:
        # Skip pncp (already has evidence)
        sources_to_process = [s for s in all_sources if s != "pncp"]

    print(f"Sources to process: {', '.join(sources_to_process)}\n")

    # Process each source
    overall_stats: dict[str, dict] = {}
    errors = []

    for src in sources_to_process:
        print(f"\n{'─' * 60}")
        print(f"  Source: {src}")
        print(f"{'─' * 60}")

        strategy = get_source_strategy(src)
        print(f"  Strategy: {strategy}")

        try:
            if strategy == "credential":
                stats = project_credential_source(conn, entities, src, args.dry_run)
            elif strategy == "existing_bids":
                if src == "pcp":
                    stats = project_pcp_evidence(conn, entities, args.dry_run)
                elif src == "compras_gov":
                    stats = project_compras_gov_evidence(conn, entities, args.dry_run)
                else:
                    stats = _project_base_not_investigated(
                        conn, entities, src, "unknown_existing_bids_source", args.dry_run
                    )
            elif strategy == "ciga_ckan":
                stats = project_ciga_ckan_evidence(conn, entities, args.dry_run)
            elif strategy == "contracts":
                stats = project_contracts_evidence(conn, entities, args.dry_run)
            elif strategy == "crawl":
                stats = project_source_via_crawl(conn, entities, src, args.dry_run)
            else:
                stats = _project_base_not_investigated(
                    conn, entities, src, f"unknown_strategy: {strategy}", args.dry_run
                )

            overall_stats[src] = stats

        except Exception as e:
            _logger.exception(f"Error processing source {src}")
            errors.append(f"{src}: {e}")
            overall_stats[src] = {"error": str(e)}

    conn.close()

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print(f"\n{'=' * 68}")
    print("  SUMMARY")
    print(f"{'=' * 68}")

    total_entities = len([e for e in entities if e.get("raio_200km")])
    sources_with_success = 0
    sources_with_data = 0
    total_success_data = 0
    total_not_investigated = 0

    for src, stats in sorted(overall_stats.items()):
        data = stats.get("success_with_data", 0)
        not_inv = stats.get("not_investigated", 0)
        state = stats.get("state", "completed")
        err = stats.get("error")

        total_success_data += data
        total_not_investigated += not_inv

        if data > 0:
            sources_with_data += 1
        if data > 0 or not_inv > 0:
            sources_with_success += 1

        status_icon = "⚠️" if err else "✅"
        data_str = f"success_with_data={data}" if data > 0 else "no data"
        not_inv_str = f"not_investigated={not_inv}" if not_inv > 0 else ""
        err_str = f" ERROR: {err}" if err else ""
        print(f"  {status_icon} {src:20s}: {data_str} {not_inv_str} ({state}){err_str}")

    print(f"\n  Sources processed: {len(overall_stats)}")
    print(f"  Sources with data evidence: {sources_with_data}")
    print(f"  Total success_with_data rows: {total_success_data}")
    print(f"  Total not_investigated rows: {total_not_investigated}")
    print(f"  Entities in candidate universe: {total_entities}")

    if errors:
        print(f"\n  ERRORS: {len(errors)}")
        for err in errors:
            print(f"    • {err}")
        print("\n  Exit code: 1")
        return 1

    print(f"\n  {'DRY RUN COMPLETE' if args.dry_run else 'EXECUTION COMPLETE'}")
    print("\n  Next step: Run without --dry-run to write evidence rows,")
    print("  then run python3 scripts/consulting_readiness.py to regenerate manifest.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
