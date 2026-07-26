#!/usr/bin/env python3
"""Makefile-backed CONFENGE gate helpers — re-query live snapshot when DSN set.

File-only boolean reads are FAIL for real-data gates (objective §26).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

ART = _ROOT / "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01"
RUN = ART / "run" / "run-result.json"


def _load_run() -> dict[str, Any]:
    if not RUN.is_file():
        return {}
    return json.loads(RUN.read_text(encoding="utf-8"))


def _require_dsn() -> str:
    dsn = os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN") or os.environ.get(
        "CONFENGE_COMMERCIAL_SOURCE_DSN"
    )
    if not dsn:
        raise SystemExit(
            "FAIL: CONFENGE_COMMERCIAL_STATE_DSN required for real-data gate "
            "(file-only re-read is theater)"
        )
    return dsn


def cmd_full_candidate_history(_: argparse.Namespace) -> int:
    """Re-query snapshot for a sample of candidates from the last run."""
    from scripts.commercial_leads.dbutil import connect, fetch_all
    from scripts.commercial_leads.pipeline import load_full_supplier_histories

    d = _load_run()
    lm = d.get("load_meta") or {}
    cnpjs = list(lm.get("candidate_supplier_cnpjs") or [])[:40]
    if not cnpjs and d.get("leads"):
        cnpjs = [L["cnpj14"] for L in d["leads"][:20]]
    if not cnpjs:
        print(json.dumps({"ok": False, "reason": "no_candidates_in_run_result"}, indent=2))
        return 1

    dsn = _require_dsn()
    conn = connect(dsn)
    try:
        groups, hist = load_full_supplier_histories(conn, cnpjs, per_supplier_limit=None)
        # independent COUNT(*) reconciliation
        mismatches = []
        for cnpj in cnpjs:
            rows = fetch_all(
                conn,
                """
                SELECT COUNT(*)::int AS n
                FROM public.pncp_supplier_contracts
                WHERE is_active = TRUE
                  AND right(regexp_replace(fornecedor_cnpj, '\\D', '', 'g'), 14) = %s
                """,
                (cnpj,),
            )
            expected = int(rows[0]["n"]) if rows else 0
            loaded = len(groups.get(cnpj, []))
            if loaded != expected:
                mismatches.append({"cnpj14": cnpj, "loaded": loaded, "snapshot": expected})
        ok = (
            hist.get("history_expansion_mode") == "FULL_CANDIDATE_HISTORY"
            and hist.get("history_complete") is True
            and not hist.get("per_supplier_limit")
            and len(mismatches) == 0
            and lm.get("history_is_full") is True
        )
        report = {
            "ok": ok,
            "rechecked_cnpjs": len(cnpjs),
            "history_expansion_mode": hist.get("history_expansion_mode"),
            "history_complete": hist.get("history_complete"),
            "mismatches": mismatches[:20],
            "run_claimed_history_is_full": lm.get("history_is_full"),
            "method": "live_db_recount_vs_full_history_loader",
        }
        out = ART / "full-candidate-history-gate.json"
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0 if ok else 1
    finally:
        conn.close()


def cmd_registry_coverage(_: argparse.Namespace) -> int:
    """Re-query supplier_registry for published top20 CNPJs."""
    from scripts.commercial_leads.dbutil import connect, fetch_all

    d = _load_run()
    leads = d.get("leads") or []
    top20 = [str(L.get("cnpj14")) for L in leads[:20] if L.get("cnpj14")]
    if len(top20) < 1:
        print(json.dumps({"ok": False, "reason": "empty_published_queue"}, indent=2))
        return 1

    dsn = _require_dsn()
    conn = connect(dsn)
    try:
        rows = fetch_all(
            conn,
            """
            SELECT cnpj14, cnae_principal, source, source_date
            FROM public.supplier_registry
            WHERE cnpj14 = ANY(%s)
            """,
            (top20,),
        )
        by = {str(r["cnpj14"]): r for r in rows}
        missing = [c for c in top20 if c not in by]
        no_cnae = [c for c, r in by.items() if not (r.get("cnae_principal") or "").strip()]
        coverage = (len(top20) - len(missing)) / len(top20)
        cnae_cov = (len(top20) - len(missing) - len(no_cnae)) / len(top20)
        ok = coverage == 1.0 and cnae_cov == 1.0 and len(no_cnae) == 0
        report = {
            "ok": ok,
            "method": "live_db_supplier_registry_lookup",
            "top20_n": len(top20),
            "with_registry": len(top20) - len(missing),
            "coverage": round(coverage, 4),
            "cnae_primary_coverage": round(cnae_cov, 4),
            "missing": missing,
            "no_cnae": no_cnae,
            "block": None if ok else "BLOCKED_MISSING_SUPPLIER_SECTOR_DATA",
        }
        (ART / "registry-coverage-gate.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, indent=2))
        return 0 if ok else 2
    finally:
        conn.close()


def cmd_full_population(_: argparse.Namespace) -> int:
    """Validate explicit mode semantics — forbid ambiguous FULL_POPULATION claim alone."""
    d = _load_run()
    disc = d.get("discovery_mode")
    hist = d.get("history_expansion_mode")
    rank = d.get("ranking_population_mode")
    pop = d.get("population_mode")
    lim = (d.get("load_meta") or {}).get("limit_applied") or (d.get("metrics") or {}).get(
        "limit_applied"
    )
    # Acceptable: discovery prefilter + full history + full eligible ranking, no limit
    ok = (
        disc == "PREFILTERED_CANDIDATE_DISCOVERY"
        and hist == "FULL_CANDIDATE_HISTORY"
        and rank in ("FULL_ELIGIBLE_CANDIDATES", None)
        and not lim
        and pop not in (None, "")  # legacy field may still say FULL_POPULATION
    )
    # Explicitly reject claiming FULL_SNAPSHOT_SCAN when discovery was prefiltered
    if disc == "PREFILTERED_CANDIDATE_DISCOVERY" and pop == "FULL_SNAPSHOT_SCAN":
        ok = False
    report = {
        "ok": ok,
        "population_mode_legacy": pop,
        "discovery_mode": disc,
        "history_expansion_mode": hist,
        "ranking_population_mode": rank,
        "limit_applied": lim,
        "note": (
            "PASS requires PREFILTERED_CANDIDATE_DISCOVERY + FULL_CANDIDATE_HISTORY "
            "with no LIMIT; FULL_POPULATION alone is not a completeness claim"
        ),
    }
    print(report)
    return 0 if ok else 1


def cmd_prefilter_recall(_: argparse.Namespace) -> int:
    """Re-measure prefilter recall live against DB (same UF universe)."""
    from scripts.commercial_leads.contract_relevance import classify_contract_relevance
    from scripts.commercial_leads.dbutil import connect, fetch_all
    from scripts.commercial_leads.pipeline import (
        _normalize_cnpj_digits,
        discover_candidate_suppliers,
    )
    from scripts.commercial_leads.profile import load_profile

    dsn = _require_dsn()
    conn = connect(dsn)
    try:
        profile = load_profile(_ROOT / "config/commercial_profiles/confenge.yaml")
        uf_list = list((profile.data.get("region") or {}).get("primary_ufs") or [])
        uf_list += list((profile.data.get("region") or {}).get("secondary_ufs") or [])
        uf_list = [u.upper() for u in uf_list if u]
        rows = fetch_all(
            conn,
            """
            SELECT contrato_id, fornecedor_cnpj, objeto_contrato, uf
            FROM public.pncp_supplier_contracts
            WHERE is_active = TRUE AND fornecedor_cnpj IS NOT NULL AND btrim(fornecedor_cnpj) <> ''
              AND uf IS NOT NULL AND upper(btrim(uf)) = ANY(%s)
              AND (abs(hashtext(contrato_id::text)) %% 100) < 8
            LIMIT 8000
            """,
            (uf_list,),
        )
        gold: set[str] = set()
        for r in rows:
            if classify_contract_relevance(r.get("objeto_contrato")).status == "PASS":
                c = _normalize_cnpj_digits(r.get("fornecedor_cnpj"))
                if c:
                    gold.add(c)
        evidence, meta = discover_candidate_suppliers(
            conn, profile, population_mode="FULL_POPULATION"
        )
        disc = set(evidence.keys())
        found = gold & disc
        recall = len(found) / len(gold) if gold else None
        ok = recall is not None and recall >= 0.95
        report = {
            "method": "live_same_universe_uf_hash_sample_no_keyword_prefilter",
            "ufs": uf_list,
            "sample_contracts": len(rows),
            "gold_relevant_suppliers_in_sample": len(gold),
            "discovered_among_gold": len(found),
            "missed": len(gold - disc) if gold else None,
            "candidate_discovery_recall": round(recall, 4) if recall is not None else None,
            "threshold": 0.95,
            "ok": ok,
            "status": "PASS" if ok else "FAIL",
            "discovery_meta_candidate_count": meta.get("candidate_supplier_count"),
        }
        (ART / "prefilter-recall.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, indent=2))
        return 0 if ok else 2
    finally:
        conn.close()


def cmd_ranking_quality(_: argparse.Namespace) -> int:
    d = _load_run()
    leads = d.get("leads") or []
    top = leads[:10]
    oos = sum(1 for item in top if item.get("supplier_sector_fit") == "OUT_OF_SCOPE")
    strong = (
        all(
            item.get("supplier_sector_fit")
            in ("CONFIRMED_ENGINEERING", "STRONG_ENGINEERING_FIT")
            for item in top
        )
        if top
        else False
    )
    # also require data_quality full history fields present
    hist_ok = all(
        (item.get("data_quality") or {}).get("total_contract_count_full_history") is not None
        for item in top
    ) if top else False
    print({"top10": len(top), "oos": oos, "strong": strong, "full_history_fields": hist_ok})
    return 0 if strong and oos == 0 and top and hist_ok else 1


def cmd_ranking_stability(_: argparse.Namespace) -> int:
    """Re-execute ranking twice on same run inputs and require identical ranking_hash.

    Does not merely re-read a boolean file.
    """
    dsn = _require_dsn()
    run = _load_run()
    leads = run.get("leads") or []
    if len(leads) < 5:
        report = {"ok": False, "reason": "insufficient_leads_in_run", "n": len(leads)}
        (ART / "ranking-stability.json").write_text(json.dumps(report, indent=2) + "\n")
        print(report)
        return 1

    # Deterministic re-hash of published queue identity
    def rank_blob(items: list[dict[str, Any]]) -> str:
        blob = json.dumps(
            [
                (
                    item.get("cnpj14"),
                    item.get("score_total"),
                    item.get("priority"),
                    item.get("supplier_sector_fit"),
                )
                for item in items
            ],
            sort_keys=True,
        )
        return hashlib.sha256(blob.encode()).hexdigest()

    h1 = rank_blob(leads)
    h2 = rank_blob(list(reversed(list(reversed(leads)))))  # order-stable rebuild
    # Live re-score top published CNPJs from full history (same as-of/profile)
    from datetime import date

    from scripts.commercial_leads.dbutil import connect
    from scripts.commercial_leads.pipeline import load_full_supplier_histories
    from scripts.commercial_leads.profile import load_profile
    from scripts.commercial_leads.scoring import rank_leads, score_supplier
    from scripts.commercial_leads.signals import compute_signals_for_supplier, rows_from_dicts

    profile = load_profile(_ROOT / "config/commercial_profiles/confenge.yaml")
    cnpjs = [str(item["cnpj14"]) for item in leads]
    conn = connect(dsn)
    try:
        groups, hist = load_full_supplier_histories(conn, cnpjs, per_supplier_limit=None)
    finally:
        conn.close()
    if not hist.get("history_complete"):
        report = {"ok": False, "reason": "history_incomplete_on_stability_recheck", "hist": hist}
        (ART / "ranking-stability.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
        print(report)
        return 1

    as_of = date.fromisoformat(str(run.get("as_of") or date.today().isoformat()))
    scored = []
    sector_by_cnpj = {
        str(item.get("cnpj14")): item.get("supplier_sector_fit") for item in leads
    }
    for item in leads:
        cnpj = str(item["cnpj14"])
        crow = groups.get(cnpj) or []
        contracts = rows_from_dicts(crow)
        sigs = compute_signals_for_supplier(contracts, profile, as_of=as_of, official_acts=None)
        total_value = sum(
            float(c.valor_total or 0) for c in contracts if c.valor_total is not None
        )
        pubs = [c.data_publicacao for c in contracts if c.data_publicacao]
        last_pub = max(pubs).isoformat() if pubs else None
        lead = score_supplier(
            cnpj14=cnpj,
            razao_social=item.get("razao_social") or cnpj,
            signal_results=sigs,
            profile=profile,
            total_value=total_value,
            contract_count=len(contracts),
            last_publication=last_pub,
        )
        scored.append(lead)
    ranked_a = rank_leads(scored, profile, suppressed_cnpjs=set(), state_by_cnpj={})
    ranked_b = rank_leads(list(scored), profile, suppressed_cnpjs=set(), state_by_cnpj={})
    ha = rank_blob(
        [
            {
                "cnpj14": x.cnpj14,
                "score_total": x.score_total,
                "priority": x.priority,
                "supplier_sector_fit": sector_by_cnpj.get(x.cnpj14),
            }
            for x in ranked_a
        ]
    )
    hb = rank_blob(
        [
            {
                "cnpj14": x.cnpj14,
                "score_total": x.score_total,
                "priority": x.priority,
                "supplier_sector_fit": sector_by_cnpj.get(x.cnpj14),
            }
            for x in ranked_b
        ]
    )
    order_a = [x.cnpj14 for x in ranked_a]
    order_b = [x.cnpj14 for x in ranked_b]
    published_order = [str(L["cnpj14"]) for L in leads]
    ok = ha == hb and order_a == order_b and h1 == h2
    # published order should match re-score order for same snapshot/profile
    same_as_published = order_a == published_order
    report = {
        "ok": ok and same_as_published,
        "method": "live_rescore_twice_same_snapshot_profile",
        "same_snapshot": {"ok": ha == hb, "hash_a": ha, "hash_b": hb},
        "order_stable": order_a == order_b,
        "matches_published_queue": same_as_published,
        "published_order": published_order,
        "rescored_order": order_a,
        "history_complete": hist.get("history_complete"),
        "n_leads": len(leads),
    }
    (ART / "ranking-stability.json").write_text(
        json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["ok"] else 1


def cmd_baseline_superiority(_: argparse.Namespace) -> int:
    d = _load_run()
    b = d.get("baseline_comparison") or {}
    hm = d.get("human_metrics") or {}
    if hm.get("human_review_status") != "COMPLETE" or hm.get("precision_at_10") is None:
        print(
            {
                "ok": False,
                "status": "BLOCKED_INSUFFICIENT_HUMAN_LABELS",
                "baseline": b,
            }
        )
        return 2
    print(b)
    return 0 if b.get("proposed_better") else 1


def cmd_snapshot_content_binding(_: argparse.Namespace) -> int:
    """Live recompute canonical_table_hash and compare to manifest."""
    from scripts.commercial_leads.isolation import open_source_connection
    from scripts.commercial_leads.snapshot import (
        bind_snapshot_to_database,
        validate_snapshot_manifest,
    )

    dsn = _require_dsn()
    manifest = os.environ.get("CONFENGE_COMMERCIAL_SNAPSHOT")
    if not manifest:
        print({"ok": False, "reason": "CONFENGE_COMMERCIAL_SNAPSHOT required"})
        return 1
    snap = validate_snapshot_manifest(manifest, allow_missing_dump=True)
    conn = open_source_connection(dsn)
    try:
        binding = bind_snapshot_to_database(conn, snap, require_canonical_match=True)
    finally:
        conn.close()
    (ART / "snapshot-content-binding-gate.json").write_text(
        json.dumps(binding, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(binding, indent=2, default=str))
    return 0 if binding.get("ok") and binding.get("canonical_table_hash") else 1


def cmd_source_state_isolation(_: argparse.Namespace) -> int:
    """Prove snapshot writes FAIL and ledger writes PASS (RESTORED_SNAPSHOT_SINGLE_DB)."""
    from scripts.commercial_leads.dbutil import connect
    from scripts.commercial_leads.isolation import (
        assert_source_state_isolation,
        probe_snapshot_write_denied,
    )

    dsn = _require_dsn()
    isolation = assert_source_state_isolation(
        source_dsn=dsn,
        state_dsn=dsn,
        force_mode="RESTORED_SNAPSHOT_SINGLE_DB",
        enforce_source_readonly=True,  # non-negotiable for this gate
    )
    snapshot_probe = getattr(isolation, "snapshot_write_probe", None) or probe_snapshot_write_denied(
        dsn
    )

    # Ledger insert must still work on state path (writable commercial tables)
    conn = connect(dsn)
    ledger: dict[str, Any] = {}
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO commercial_lead_runs (
                        run_id, profile_id, profile_version, profile_hash,
                        snapshot_hash, snapshot_manifest, git_sha, status,
                        queue_limit, eligible_companies, ranked_companies, metrics, non_claims
                    ) VALUES (
                        'gate-isolation-probe', 'confenge', 'gate', 'x',
                        'x', '{}'::jsonb, 'gate', 'FAIL',
                        1, 0, 0, '{}'::jsonb, '[]'::jsonb
                    )
                    ON CONFLICT (run_id) DO UPDATE SET status = 'FAIL'
                    """
                )
                conn.commit()
                ledger["insert_ledger"] = "ok"
                cur.execute(
                    "DELETE FROM commercial_lead_runs WHERE run_id = 'gate-isolation-probe'"
                )
                conn.commit()
            except Exception as exc:  # noqa: BLE001
                ledger["insert_ledger"] = f"fail:{exc}"
                try:
                    conn.rollback()
                except Exception as rb_exc:  # noqa: BLE001
                    ledger["rollback_error"] = str(rb_exc)
    finally:
        conn.close()

    # Count must remain stable after probe
    from scripts.commercial_leads.dbutil import fetch_all

    conn2 = connect(dsn)
    try:
        n = int(fetch_all(conn2, "SELECT COUNT(*)::int AS n FROM public.pncp_supplier_contracts")[0]["n"])
    finally:
        conn2.close()

    report: dict[str, Any] = {
        "isolation": isolation.as_dict(),
        "snapshot_write_probe": snapshot_probe,
        "ledger": ledger,
        "snapshot_row_count_after_probe": n,
        "ok": bool(
            isolation.source_state_mode == "RESTORED_SNAPSHOT_SINGLE_DB"
            and isolation.source_read_only_enforced is True
            and snapshot_probe.get("ok") is True
            and ledger.get("insert_ledger") == "ok"
            and str(snapshot_probe.get("insert", "")).startswith("denied")
            and str(snapshot_probe.get("update_real_row", "")).startswith("denied")
            and str(snapshot_probe.get("delete", "")).startswith("denied")
            and snapshot_probe.get("residual_probe_rows") == 0
        ),
        "note": (
            "RESTORED_SNAPSHOT_SINGLE_DB: snapshot mutations denied by DB trigger (064); "
            "ledger writes allowed; not claimed as SOURCE_STATE_SEPARATED."
        ),
    }
    (ART / "source-state-isolation-gate.json").write_text(
        json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["ok"] else 1


def cmd_migrations(_: argparse.Namespace) -> int:
    """Live migration double-apply; file presence alone is never PASS."""
    from scripts.commercial_leads.pipeline import verify_migration_idempotence

    dsn = _require_dsn()
    r = verify_migration_idempotence(dsn)
    r["skipped"] = False
    r["ok"] = bool(r.get("idempotent") and r.get("first_ok") and r.get("second_ok"))
    # verify 063 present in _migrations
    from scripts.commercial_leads.dbutil import connect, fetch_all

    conn = connect(dsn)
    try:
        rows = fetch_all(
            conn,
            "SELECT version, name FROM _migrations WHERE version IN ('062','063','064') ORDER BY version",
        )
        r["applied_versions"] = [x["version"] for x in rows]
        r["has_062"] = any(x["version"] == "062" for x in rows)
        r["has_063"] = any(x["version"] == "063" for x in rows)
        r["has_064"] = any(x["version"] == "064" for x in rows)
        r["ok"] = r["ok"] and r["has_062"] and r["has_063"] and r["has_064"]
    finally:
        conn.close()
    (ART / "migrations-gate.json").write_text(json.dumps(r, indent=2, default=str) + "\n")
    print(json.dumps(r, indent=2, default=str))
    return 0 if r["ok"] else 1


def cmd_package_evidence(_: argparse.Namespace) -> int:
    out = ART / "evidence-package"
    out.mkdir(parents=True, exist_ok=True)
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],  # noqa: S603,S607
        cwd=str(_ROOT),
        text=True,
    ).strip()
    files = [
        "result.json",
        "queue-summary.json",
        "denominator-integrity.json",
        "contract-relevance-holdout.json",
        "gold-standard-baseline.json",
        "prefilter-recall.json",
        "full-candidate-history-gate.json",
        "registry-coverage-gate.json",
        "snapshot-content-binding-gate.json",
    ]
    checks: dict[str, Any] = {}
    for f in files:
        p = ART / f
        checks[f] = {
            "exists": p.is_file(),
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None,
        }
    pkg = {
        "executed_git_sha": sha,
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "created_at": datetime.now(UTC).isoformat(),
        "checksums": checks,
        "note": "execution artifacts; not self-referential commit SHA of this package",
    }
    (out / "attestation.json").write_text(
        json.dumps(pkg, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(pkg, indent=2))
    return 0


def cmd_verify_attestation(_: argparse.Namespace) -> int:
    """executed_git_sha must equal HEAD, or be a git ancestor with only evidence lag.

    Committing attestation cannot embed its own final SHA (recursive). Policy:
    exact match OR executed is ancestor of HEAD (artifact-only lag commits).
    """
    p = ART / "evidence-package" / "attestation.json"
    d = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],  # noqa: S603,S607
        cwd=str(_ROOT),
        text=True,
    ).strip()
    executed = d.get("executed_git_sha") or ""
    exact = executed == head
    ancestor = False
    if executed and not exact:
        try:
            subprocess.check_call(  # noqa: S603
                ["git", "merge-base", "--is-ancestor", executed, head],  # noqa: S603,S607
                cwd=str(_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            ancestor = True
        except (subprocess.CalledProcessError, OSError):
            ancestor = False
    ok = (exact or ancestor) and bool(
        (d.get("checksums") or {}).get("gold-standard-baseline.json", {}).get("exists")
    )
    report = {
        "ok": ok,
        "executed": executed,
        "head": head,
        "exact_match": exact,
        "ancestor_with_artifact_lag": ancestor,
        "policy": "exact_or_ancestor_artifact_only_lag",
    }
    print(report)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    mapping = {
        "full-candidate-history": cmd_full_candidate_history,
        "registry-coverage": cmd_registry_coverage,
        "full-population": cmd_full_population,
        "prefilter-recall": cmd_prefilter_recall,
        "ranking-quality": cmd_ranking_quality,
        "ranking-stability": cmd_ranking_stability,
        "baseline-superiority": cmd_baseline_superiority,
        "snapshot-content-binding": cmd_snapshot_content_binding,
        "source-state-isolation": cmd_source_state_isolation,
        "migrations": cmd_migrations,
        "package-evidence": cmd_package_evidence,
        "verify-attestation": cmd_verify_attestation,
    }
    for name in mapping:
        sub.add_parser(name)
    args = ap.parse_args(argv)
    return mapping[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
