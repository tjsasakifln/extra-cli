"""End-to-end commercial leads pipeline."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from scripts.commercial_leads import (
    CAMPAIGN_ID,
    MODULE_VERSION,
    POPULATION_FULL,
    POPULATION_SAMPLE,
    SOURCE_STATE_RESTORED,
)
from scripts.commercial_leads.baseline import compare_to_baselines
from scripts.commercial_leads.commercial_validity import evaluate_supplier_validity
from scripts.commercial_leads.contract_relevance import (
    classify_contract_relevance,
    filter_relevant_contracts,
)
from scripts.commercial_leads.dbutil import connect, fetch_all
from scripts.commercial_leads.exports import export_all, reconcile_exports
from scripts.commercial_leads.identity import ExclusionRecord, resolve_supplier
from scripts.commercial_leads.isolation import (
    assert_isolation,
    assert_source_state_isolation,
    mask_dsn,
    open_source_connection,
)
from scripts.commercial_leads.profile import CommercialProfile, load_profile
from scripts.commercial_leads.review import load_state_map
from scripts.commercial_leads.scoring import rank_leads, score_supplier
from scripts.commercial_leads.sector_fit import PUBLISHABLE, sector_fit_histogram
from scripts.commercial_leads.signals import compute_signals_for_supplier, rows_from_dicts
from scripts.commercial_leads.snapshot import bind_snapshot_to_database, validate_snapshot_manifest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def git_sha(root: Path | None = None) -> str:
    r = root or _PROJECT_ROOT
    try:
        out = subprocess.check_output(  # noqa: S603,S607
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=str(r),
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return out.strip()
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return "unknown"


def apply_migrations(dsn: str) -> dict[str, Any]:
    cmd = [
        "python3",
        "-m",
        "scripts.ops.apply_migrations",
        "--dsn",
        dsn,
    ]
    proc = subprocess.run(  # noqa: S603
        cmd,
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "exit_code": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
        "ok": proc.returncode == 0,
    }


def verify_migration_idempotence(dsn: str) -> dict[str, Any]:
    first = apply_migrations(dsn)
    second = apply_migrations(dsn)
    return {
        "first_ok": first["ok"],
        "second_ok": second["ok"],
        "idempotent": first["ok"] and second["ok"],
        "first": first,
        "second": second,
    }


def _segment_sql_prefilter(profile: CommercialProfile) -> tuple[str, list[Any]]:
    """Broad SQL prefilter (recall). Final relevance is hierarchical in Python.

    Uses only strong-ish profile keywords plus layer-A tokens so we do not
    scan the entire 4M table blindly, but weak tokens alone never qualify
    after Python classification.
    """
    from scripts.commercial_leads.contract_relevance import STRONG_PHRASES, STRONG_TOKENS

    kws: list[str] = []
    for seg in profile.data.get("segments") or []:
        if isinstance(seg, dict):
            kws.extend(str(x) for x in (seg.get("object_keywords") or []))
    # Prefer strong engineering terms for SQL prefilter
    strongish = [
        k for k in kws
        if k.strip() and k.lower() not in {
            "projeto", "consultoria", "servico", "serviço", "manutencao", "manutenção",
        }
    ]
    strongish.extend(STRONG_PHRASES[:12])
    strongish.extend(STRONG_TOKENS[:10])
    # de-dupe
    seen: set[str] = set()
    ordered: list[str] = []
    for k in strongish:
        kl = k.lower().strip()
        if kl and kl not in seen:
            seen.add(kl)
            ordered.append(k.strip())
    ordered = ordered[:30]
    if not ordered:
        return "TRUE", []
    clauses = []
    params: list[Any] = []
    for kw in ordered:
        clauses.append("objeto_contrato ILIKE %s")
        params.append(f"%{kw}%")
    return "(" + " OR ".join(clauses) + ")", params


def load_contract_universe(
    conn: Any,
    profile: CommercialProfile,
    *,
    max_contracts: int | None = None,
    as_of: date | None = None,
    population_mode: str = POPULATION_SAMPLE,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load active contracts; apply hierarchical relevance; never silent full claim.

    Returns (relevant_rows, load_meta).
    """
    filt, params = _segment_sql_prefilter(profile)
    uf_list = list((profile.data.get("region") or {}).get("primary_ufs") or [])
    uf_list += list((profile.data.get("region") or {}).get("secondary_ufs") or [])
    uf_list = [u.upper() for u in uf_list if u]

    sql = (
        "SELECT contrato_id, orgao_cnpj, orgao_nome, "
        "fornecedor_cnpj, fornecedor_nome, objeto_contrato, valor_total, "
        "data_inicio, data_fim, data_publicacao, uf, source, source_id "
        "FROM public.pncp_supplier_contracts "
        "WHERE is_active = TRUE "
        "AND fornecedor_cnpj IS NOT NULL "
        "AND btrim(fornecedor_cnpj) <> '' "
        "AND (" + filt + ")"  # nosec B608
    )
    # Geography: do NOT auto-include uf IS NULL when filter active
    if uf_list:
        sql += " AND uf IS NOT NULL AND upper(btrim(uf)) = ANY(%s)"
        params.append(uf_list)

    sql += " ORDER BY data_publicacao DESC NULLS LAST, valor_total DESC NULLS LAST"

    limit_applied = None
    if population_mode == POPULATION_FULL:
        # No LIMIT — full eligible population for this prefilter
        pass
    elif max_contracts is not None:
        sql += " LIMIT %s"
        params.append(int(max_contracts))
        limit_applied = int(max_contracts)
    else:
        # Explicit default sample bound (must be recorded, never silent full claim)
        limit_applied = 250_000
        sql += " LIMIT %s"
        params.append(limit_applied)

    raw = fetch_all(conn, sql, tuple(params))
    kept, excluded = filter_relevant_contracts(raw)
    meta = {
        "population_mode": population_mode,
        "limit_applied": limit_applied,
        "sql_prefilter_rows": len(raw),
        "relevance_pass_rows": len(kept),
        "relevance_fail_rows": len(excluded),
        "ufs_filter": uf_list,
        "uf_null_excluded_when_geo_filter": bool(uf_list),
    }
    return kept, meta


def group_by_supplier(
    rows: list[dict[str, Any]],
    profile: CommercialProfile,
) -> tuple[dict[str, list[dict[str, Any]]], list[ExclusionRecord], dict[str, str]]:
    """Resolve identity and group contracts by canonical CNPJ14."""
    excl = profile.data.get("exclusions") or {}
    markers = list(excl.get("organ_name_markers") or [])
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    names: dict[str, str] = {}
    exclusions: list[ExclusionRecord] = []
    seen_excluded: set[str] = set()

    for row in rows:
        resolved = resolve_supplier(
            row.get("fornecedor_cnpj"),
            row.get("fornecedor_nome"),
            organ_markers=markers,
            drop_organs=bool(excl.get("drop_public_organs", True)),
            drop_persons=bool(excl.get("drop_natural_persons", True)),
            drop_invalid=bool(excl.get("drop_invalid_cnpj", True)),
        )
        if not resolved.eligible or not resolved.cnpj14:
            key = f"{resolved.exclusion_reason}:{resolved.raw_tax_id}:{resolved.razao_social}"
            if key not in seen_excluded:
                seen_excluded.add(key)
                exclusions.append(
                    ExclusionRecord(
                        raw_tax_id=resolved.raw_tax_id,
                        raw_name=resolved.razao_social,
                        reason_code=resolved.exclusion_reason or "ineligible",
                    )
                )
            continue
        groups[resolved.cnpj14].append(row)
        names[resolved.cnpj14] = resolved.razao_social
    return groups, exclusions, names


def persist_run(
    conn: Any,
    *,
    run_id: str,
    profile: CommercialProfile,
    snapshot_hash: str,
    snapshot_manifest: dict[str, Any],
    status: str,
    leads: list[dict[str, Any]],
    exclusions: list[ExclusionRecord],
    metrics: dict[str, Any],
    git: str,
) -> None:
    from psycopg2.extras import Json

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO commercial_lead_runs (
                run_id, profile_id, profile_version, profile_hash,
                snapshot_hash, snapshot_manifest, git_sha, status,
                queue_limit, eligible_companies, ranked_companies,
                metrics, non_claims, finished_at
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now()
            )
            ON CONFLICT (run_id) DO UPDATE SET
                status = EXCLUDED.status,
                metrics = EXCLUDED.metrics,
                ranked_companies = EXCLUDED.ranked_companies,
                finished_at = now()
            """,
            (
                run_id,
                profile.profile_id,
                profile.version,
                profile.profile_hash,
                snapshot_hash,
                Json(snapshot_manifest),
                git,
                status,
                profile.queue_limit,
                int(metrics.get("eligible_companies") or 0),
                len(leads),
                Json(metrics),
                Json(profile.data.get("non_claims") or []),
            ),
        )
        for i, lead in enumerate(leads, start=1):
            cur.execute(
                """
                INSERT INTO commercial_leads (
                    run_id, cnpj14, cnpj8, razao_social, score_total, priority,
                    score_decomposition, signals_fired, signals_not_computable,
                    evidence, suggested_offer, next_human_step, limitations,
                    commercial_state, rank_position
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
                ON CONFLICT (run_id, cnpj14) DO UPDATE SET
                    score_total = EXCLUDED.score_total,
                    priority = EXCLUDED.priority,
                    score_decomposition = EXCLUDED.score_decomposition,
                    signals_fired = EXCLUDED.signals_fired,
                    commercial_state = EXCLUDED.commercial_state,
                    rank_position = EXCLUDED.rank_position
                """,
                (
                    run_id,
                    lead["cnpj14"],
                    lead["cnpj14"][:8],
                    lead["razao_social"],
                    lead["score_total"],
                    lead["priority"],
                    Json(lead.get("score_decomposition") or {}),
                    Json(lead.get("signals_fired") or []),
                    Json(lead.get("signals_not_computable") or []),
                    Json(lead.get("evidence") or []),
                    lead.get("suggested_offer"),
                    lead.get("next_human_step"),
                    Json(lead.get("limitations") or []),
                    lead.get("commercial_state") or "NEW",
                    lead.get("rank_position") or i,
                ),
            )
            cur.execute(
                """
                INSERT INTO commercial_feedback_ledger (run_id, cnpj14, event_type, payload, author)
                VALUES (%s,%s,'EXPORT',%s,'system')
                """,
                (run_id, lead["cnpj14"], Json({"rank": i, "score": lead["score_total"]})),
            )
        for ex in exclusions[:5000]:
            cur.execute(
                """
                INSERT INTO commercial_exclusions (run_id, raw_tax_id, raw_name, reason_code, detail)
                VALUES (%s,%s,%s,%s,%s)
                """,
                (run_id, ex.raw_tax_id, ex.raw_name, ex.reason_code, ex.detail),
            )
    conn.commit()


def run_pipeline(
    *,
    dsn: str,
    profile_path: str | Path,
    snapshot_manifest: str | Path,
    out_dir: str | Path,
    max_contracts: int | None = None,
    as_of: date | None = None,
    skip_migrations: bool = False,
    skip_persist: bool = False,
    verify_snapshot_hash: bool = True,
    source_dsn: str | None = None,
    state_dsn: str | None = None,
    population_mode: str | None = None,
    source_state_mode: str | None = None,
    persistence_required: bool | None = None,
    run_mode: str = "RC",
) -> dict[str, Any]:
    """Run commercial queue with sector validity gates.

    population_mode: FULL_POPULATION | BOUNDED_SAMPLE
    run_mode: RC | TEST | DRY_RUN | EXPERIMENTAL_SAMPLE
    """
    t0 = time.time()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    run_id = f"cl-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    as_of_d = as_of or date.today()
    git = git_sha()

    state = state_dsn or dsn
    source = source_dsn or dsn
    # Honest dual-DSN mode
    if source_state_mode is None:
        source_state_mode = SOURCE_STATE_RESTORED if source == state else None
    isolation = assert_source_state_isolation(
        source_dsn=source,
        state_dsn=state,
        out_dir=out,
        force_mode=source_state_mode or SOURCE_STATE_RESTORED,
        enforce_source_readonly=False,  # probe optional; session set readonly on open
    )
    if not isolation.ok or isolation.production_touched or isolation.soak_touched:
        result = {
            "run_id": run_id,
            "status": "FAIL",
            "reason": "isolation_violation",
            "isolation": isolation.as_dict(),
            "campaign_id": CAMPAIGN_ID,
            "production_touched": isolation.production_touched,
            "soak_touched": isolation.soak_touched,
            "artifact_git_sha": git,
            "run_git_sha": git,
        }
        (out / "run-result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return result

    # Population mode defaults: sample unless explicitly FULL
    pop_mode = (population_mode or POPULATION_SAMPLE).upper()
    if pop_mode not in (POPULATION_FULL, POPULATION_SAMPLE):
        pop_mode = POPULATION_SAMPLE
    if run_mode == "RC" and pop_mode != POPULATION_FULL:
        # RC may still run sample but cannot claim final ranking
        run_mode_effective = "EXPERIMENTAL_SAMPLE"
    else:
        run_mode_effective = run_mode

    persist_required = persistence_required
    if persist_required is None:
        persist_required = run_mode_effective == "RC" and pop_mode == POPULATION_FULL
    if skip_persist and run_mode_effective == "RC" and pop_mode == POPULATION_FULL:
        result = {
            "run_id": run_id,
            "status": "FAIL",
            "reason": "skip_persist_not_allowed_for_rc",
            "campaign_id": CAMPAIGN_ID,
            "artifact_git_sha": git,
            "run_git_sha": git,
        }
        (out / "run-result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return result
    if skip_persist and run_mode_effective not in ("TEST", "DRY_RUN", "EXPERIMENTAL_SAMPLE"):
        result = {
            "run_id": run_id,
            "status": "FAIL",
            "reason": "skip_persist_only_for_test_dry_run_sample",
            "campaign_id": CAMPAIGN_ID,
            "artifact_git_sha": git,
            "run_git_sha": git,
        }
        (out / "run-result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return result

    snap = validate_snapshot_manifest(
        snapshot_manifest,
        verify_file_hash=verify_snapshot_hash,
        allow_missing_dump=True,  # bind to DB is the real gate
    )
    if not snap.ok and snap.status.startswith("BLOCKED"):
        # Allow DB-bound path when dump absent but hash declared
        if "dump_file_missing" not in (snap.reasons or []) and "dump_file_absent" not in str(snap.reasons):
            result = {
                "run_id": run_id,
                "status": snap.status if snap.status.startswith("BLOCKED") else "FAIL",
                "reason": "snapshot_validation_failed",
                "snapshot": snap.as_dict(),
                "isolation": isolation.as_dict(),
                "campaign_id": CAMPAIGN_ID,
                "artifact_git_sha": git,
                "run_git_sha": git,
            }
            (out / "run-result.json").write_text(
                json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n",
                encoding="utf-8",
            )
            return result

    profile = load_profile(profile_path)
    mig: dict[str, Any]
    if skip_migrations:
        mig = {"idempotent": False, "skipped": True, "first_ok": False, "second_ok": False}
        if run_mode_effective == "RC" and pop_mode == POPULATION_FULL:
            result = {
                "run_id": run_id,
                "status": "FAIL",
                "reason": "migrations_skipped_not_allowed_for_rc",
                "migrations": mig,
                "isolation": isolation.as_dict(),
                "artifact_git_sha": git,
                "run_git_sha": git,
            }
            (out / "run-result.json").write_text(
                json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8"
            )
            return result
    else:
        mig = verify_migration_idempotence(state)
        mig["skipped"] = False
        if not mig.get("idempotent"):
            result = {
                "run_id": run_id,
                "status": "FAIL",
                "reason": "migration_not_idempotent",
                "migrations": mig,
                "isolation": isolation.as_dict(),
                "artifact_git_sha": git,
                "run_git_sha": git,
            }
            (out / "run-result.json").write_text(
                json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8"
            )
            return result

    source_conn = open_source_connection(source)
    state_conn = connect(state)
    try:
        # Snapshot ↔ DB binding on source
        binding = bind_snapshot_to_database(source_conn, snap)
        if not binding.get("ok"):
            result = {
                "run_id": run_id,
                "status": "FAIL",
                "reason": "snapshot_database_binding_failed",
                "snapshot_binding": binding,
                "snapshot": snap.as_dict(),
                "isolation": isolation.as_dict(),
                "artifact_git_sha": git,
                "run_git_sha": git,
            }
            (out / "run-result.json").write_text(
                json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8"
            )
            return result

        db_count = int(binding["database_row_count"])
        if db_count == 0:
            result = {
                "run_id": run_id,
                "status": "BLOCKED",
                "reason": "BLOCKED_MISSING_AUTHENTICATED_REAL_SNAPSHOT",
                "snapshot": snap.as_dict(),
                "snapshot_binding": binding,
                "isolation": isolation.as_dict(),
                "db_contract_count": 0,
                "artifact_git_sha": git,
                "run_git_sha": git,
            }
            (out / "run-result.json").write_text(
                json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8"
            )
            return result

        raw_rows, load_meta = load_contract_universe(
            source_conn,
            profile,
            max_contracts=max_contracts,
            as_of=as_of_d,
            population_mode=pop_mode,
        )
        groups, exclusions, names = group_by_supplier(raw_rows, profile)

        uf_list = list((profile.data.get("region") or {}).get("primary_ufs") or [])
        uf_list += list((profile.data.get("region") or {}).get("secondary_ufs") or [])
        uf_list = [u.upper() for u in uf_list if u]

        candidates_meta: list[dict[str, Any]] = []
        scored = []
        sector_decisions = []
        review_queue: list[dict[str, Any]] = []
        validity_excluded = 0

        state_map: dict[str, str] = {}
        try:
            state_map = load_state_map(state_conn)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if "commercial_lead_state_overrides" in msg or "does not exist" in msg:
                state_map = {}
            else:
                raise
        dnc_set = {c for c, st in state_map.items() if str(st).upper() == "DO_NOT_CONTACT"}

        for cnpj14, crow in groups.items():
            contracts = rows_from_dicts(crow)
            # convert contracts back to dicts for sector/geo
            crow_dicts = list(crow)
            sigs = compute_signals_for_supplier(contracts, profile, as_of=as_of_d, official_acts=None)
            total_value = sum(float(c.valor_total or 0) for c in contracts if c.valor_total is not None)
            last_pub = None
            pubs = [c.data_publicacao for c in contracts if c.data_publicacao]
            if pubs:
                last_pub = max(pubs).isoformat()
            razao = names.get(cnpj14, crow[0].get("fornecedor_nome") or cnpj14)
            lead = score_supplier(
                cnpj14=cnpj14,
                razao_social=razao,
                signal_results=sigs,
                profile=profile,
                total_value=total_value,
                contract_count=len(contracts),
                last_publication=last_pub,
            )
            # provisional signal dict for validity
            lead_d = lead.as_dict()
            validity, sector, geo = evaluate_supplier_validity(
                razao_social=razao,
                contracts=crow_dicts,
                signals_fired=lead_d.get("signals_fired") or [],
                score_total=lead.score_total,
                allowed_ufs=uf_list,
                min_signals=int((profile.data.get("queue") or {}).get("min_signals_fired") or 1),
                min_score=float((profile.data.get("queue") or {}).get("min_score") or 1.0),
                exclusion_flags={
                    "do_not_contact": cnpj14 in dnc_set,
                },
                run_id=run_id,
            )
            sector_decisions.append(sector)
            meta_row = {
                "cnpj14": cnpj14,
                "razao_social": razao,
                "total_value": total_value,
                "contract_count": len(contracts),
                "last_publication": last_pub,
                "supplier_sector_fit": sector.classification,
                "contract_relevance": validity.contract_relevance,
                "commercial_signal_fit": validity.commercial_signal_fit,
                "geography_fit": validity.geography_fit,
                "publishable": validity.publishable,
            }
            candidates_meta.append(meta_row)
            # Attach validity fields onto lead object via as_dict later
            lead_d_extra = {
                "supplier_sector_fit": sector.classification,
                "supplier_sector_confidence": sector.confidence,
                "supplier_sector_evidence": sector.as_dict(),
                "contract_relevance": validity.contract_relevance,
                "contract_relevance_evidence": (validity.evidence or {}).get("contract_relevance_sample"),
                "commercial_signal_fit": validity.commercial_signal_fit,
                "geography_fit": validity.geography_fit,
                "exclusion_checks": validity.exclusion_checks,
                "commercial_validity": validity.as_dict(),
                "data_quality": {
                    "relevant_contract_ratio": sector.relevant_contract_ratio,
                    "relevant_contract_count": sector.relevant_contract_count,
                    "total_contract_count": sector.total_contract_count,
                },
                "manual_review_status": "PENDING",
            }
            if validity.publishable and cnpj14 not in dnc_set:
                scored.append((lead, lead_d_extra))
            else:
                validity_excluded += 1
                if validity.review_queue:
                    review_queue.append({**meta_row, **lead_d_extra})

        pure_scored = [s[0] for s in scored]
        extras_by_cnpj = {s[0].cnpj14: s[1] for s in scored}
        suppressed_from_score = [s for s in pure_scored if s.cnpj14 in dnc_set]
        ranked = rank_leads(
            pure_scored,
            profile,
            suppressed_cnpjs=dnc_set,
            state_by_cnpj=state_map,
        )
        lead_dicts: list[dict[str, Any]] = []
        for i, lead in enumerate(ranked, start=1):
            d = lead.as_dict()
            d["rank_position"] = i
            d["commercial_state"] = state_map.get(lead.cnpj14, "NEW")
            d.update(extras_by_cnpj.get(lead.cnpj14, {}))
            lead_dicts.append(d)

        # Human-label-aware baseline comparison (labels optional)
        baseline_cmp = compare_to_baselines(ranked, candidates_meta, limit=profile.queue_limit)
        sector_dist = sector_fit_histogram(sector_decisions)

        ledger = [
            {
                "cnpj14": lead["cnpj14"],
                "event_type": "EXPORT",
                "author": "system",
                "payload": {
                    "rank": lead["rank_position"],
                    "score": lead["score_total"],
                    "commercial_state": lead.get("commercial_state"),
                    "supplier_sector_fit": lead.get("supplier_sector_fit"),
                    "profile_version": profile.version,
                    "catalog_version": profile.catalog_hash,
                    "dataset_snapshot_id": snap.snapshot_hash,
                    "source_run_id": run_id,
                    "rule_version": "commercial-validity-v1",
                },
                "created_at": utc_now(),
            }
            for lead in lead_dicts
        ]

        metrics = {
            "eligible_companies": len(groups),
            "raw_contracts_loaded": load_meta.get("sql_prefilter_rows"),
            "relevance_pass_contracts": load_meta.get("relevance_pass_rows"),
            "db_contract_count": db_count,
            "exclusions": len(exclusions),
            "scored_companies": len(pure_scored),
            "validity_excluded": validity_excluded,
            "review_queue_size": len(review_queue),
            "ranked_leads": len(lead_dicts),
            "do_not_contact_suppressed": len(suppressed_from_score),
            "human_state_overrides": len(state_map),
            "queue_limit": profile.queue_limit,
            "insufficient_queue": len(lead_dicts) < profile.queue_limit,
            "elapsed_seconds": round(time.time() - t0, 3),
            "module_version": MODULE_VERSION,
            "population_mode": pop_mode,
            "limit_applied": load_meta.get("limit_applied"),
            "sector_fit_distribution": sector_dist,
        }

        # Commercial top-10 gate
        top10: list[dict[str, Any]] = lead_dicts[:10]
        top10_ok = True
        top10_issues: list[str] = []
        out_of_scope_top10 = 0
        for item in top10:
            if not item.get("cnpj14") or len(str(item["cnpj14"])) != 14:
                top10_ok = False
                top10_issues.append("invalid_cnpj_in_top10")
            if str(item.get("commercial_state") or "").upper() == "DO_NOT_CONTACT":
                top10_ok = False
                top10_issues.append("do_not_contact_in_top10")
            if not (item.get("signals_fired") or []):
                top10_ok = False
                top10_issues.append("top10_without_fired_signal")
            if not (item.get("evidence") or []):
                top10_ok = False
                top10_issues.append("top10_without_evidence")
            sfit = str(item.get("supplier_sector_fit") or "")
            if sfit not in PUBLISHABLE:
                top10_ok = False
                top10_issues.append(f"top10_sector_not_strong:{sfit}")
                if sfit == "OUT_OF_SCOPE":
                    out_of_scope_top10 += 1
            if item.get("contract_relevance") != "PASS":
                top10_ok = False
                top10_issues.append("top10_contract_relevance_fail")
            if item.get("commercial_signal_fit") != "PASS":
                top10_ok = False
                top10_issues.append("top10_commercial_signal_fail")
            if item.get("geography_fit") != "PASS":
                top10_ok = False
                top10_issues.append("top10_geography_fail")
        if out_of_scope_top10:
            top10_ok = False
            top10_issues.append("out_of_scope_in_top10")
        if any(str(L.get("commercial_state") or "").upper() == "DO_NOT_CONTACT" for L in lead_dicts):
            top10_ok = False
            top10_issues.append("do_not_contact_in_published_queue")

        # Terminal status — never RC_TECHNICAL_PASS
        if not lead_dicts:
            status = "BLOCKED"
            reason = "BLOCKED_COMMERCIAL_RELEVANCE_NOT_PROVEN"
            top10_issues.append("empty_queue")
        elif pop_mode != POPULATION_FULL:
            status = "BLOCKED"
            reason = "BLOCKED_FULL_POPULATION_NOT_AVAILABLE"
        elif not top10_ok:
            status = "FAIL"
            reason = "FAIL_COMMERCIAL_QUALITY_GATE"
        else:
            status = "PASS"
            reason = None

        # Sample mode cannot claim final ranking
        claims = [
            "explainable_signals",
            "reproducible_ranking_inputs",
            "sector_fit_layer_v1",
            "hierarchical_contract_relevance_v1",
        ]
        if pop_mode == POPULATION_FULL and status == "PASS":
            claims.append("full_population_ranking")
        else:
            claims.append("EXPERIMENTAL_SAMPLE" if pop_mode == POPULATION_SAMPLE else "partial_queue")

        run_payload: dict[str, Any] = {
            "run_id": run_id,
            "campaign_id": CAMPAIGN_ID,
            "status": status,
            "reason": reason,
            "as_of": as_of_d.isoformat(),
            "git_sha": git,
            "artifact_git_sha": git,
            "run_git_sha": git,
            "profile_id": profile.profile_id,
            "profile_version": profile.version,
            "profile_hash": profile.profile_hash,
            "catalog_hash": profile.catalog_hash,
            "snapshot_hash": snap.snapshot_hash,
            "snapshot": snap.as_dict(),
            "snapshot_binding": binding,
            "isolation": isolation.as_dict(),
            "source_state_mode": isolation.source_state_mode,
            "population_mode": pop_mode,
            "run_mode": run_mode_effective,
            "load_meta": load_meta,
            "migrations": {
                "idempotent": mig.get("idempotent"),
                "skipped": mig.get("skipped", False),
                "first_ok": mig.get("first_ok", mig.get("idempotent")),
                "second_ok": mig.get("second_ok", mig.get("idempotent")),
            },
            "persistence_required": persist_required,
            "dsn_masked": mask_dsn(state),
            "production_touched": False,
            "soak_touched": False,
            "eligible_companies": len(groups),
            "queue_limit": profile.queue_limit,
            "leads": lead_dicts,
            "review_queue_sample": review_queue[:50],
            "exclusions_sample": [e.as_dict() for e in exclusions[:200]],
            "exclusion_counts": _count_reasons(exclusions),
            "baseline_comparison": baseline_cmp,
            "signal_catalog": profile.catalog,
            "profile_public": profile.as_public_dict(),
            "ledger": ledger,
            "metrics": metrics,
            "sector_fit_distribution": sector_dist,
            "top10_validation": {
                "ok": top10_ok,
                "issues": sorted(set(top10_issues)),
                "out_of_scope_in_top10": out_of_scope_top10,
            },
            "non_claims": profile.data.get("non_claims")
            or [
                "CONFENGE_COMMERCIAL_READY",
                "purchase_propensity",
                "conversion_probability",
                "tiago_acceptance",
                "contact_authorization",
                "PROJECT_DONE",
                "VPS_OPERATIONAL",
                "RC_TECHNICAL_PASS",
            ],
            "claims": claims,
            "language_note": (
                "Fila de priorização por aderência setorial + sinais observados; "
                "não afirma claim estatístico de conversão comercial."
            ),
            "suppressed_do_not_contact": sorted(dnc_set)[:100],
        }

        if not skip_persist:
            try:
                persist_run(
                    state_conn,
                    run_id=run_id,
                    profile=profile,
                    snapshot_hash=str(snap.snapshot_hash),
                    snapshot_manifest=snap.as_dict(),
                    status=status,
                    leads=lead_dicts,
                    exclusions=exclusions,
                    metrics=metrics,
                    git=git,
                )
                run_payload["persist_ok"] = True
            except Exception as exc:  # noqa: BLE001
                run_payload["persist_error"] = str(exc)
                run_payload["persist_ok"] = False
                if persist_required:
                    run_payload["status"] = "FAIL"
                    run_payload["reason"] = "persistence_failed"
                    run_payload["artifact_invalid"] = True
                    try:
                        state_conn.rollback()
                    except Exception:  # noqa: BLE001
                        pass
        else:
            run_payload["persist_ok"] = None
            run_payload["persist_skipped"] = True

        paths = export_all(out, run_payload)
        recon = reconcile_exports(out, run_payload)
        run_payload["export_paths"] = paths
        run_payload["export_reconciliation"] = recon
        if not recon.get("ok") and run_payload["status"] == "PASS":
            run_payload["status"] = "FAIL"
            run_payload["reason"] = "export_reconciliation_failed"

        rank_blob = json.dumps(
            [
                (
                    lead["cnpj14"],
                    lead["score_total"],
                    lead["priority"],
                    lead.get("supplier_sector_fit"),
                )
                for lead in lead_dicts
            ],
            sort_keys=True,
        )
        run_payload["ranking_hash"] = hashlib.sha256(rank_blob.encode()).hexdigest()

        (out / "run-result.json").write_text(
            json.dumps(run_payload, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        # review queue separate
        (out / "review-queue.json").write_text(
            json.dumps(review_queue[:200], indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        return run_payload
    finally:
        source_conn.close()
        state_conn.close()



def _count_reasons(exclusions: list[ExclusionRecord]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for e in exclusions:
        counts[e.reason_code] += 1
    return dict(counts)
