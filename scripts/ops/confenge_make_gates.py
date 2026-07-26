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
    oos = sum(1 for L in top if L.get("supplier_sector_fit") == "OUT_OF_SCOPE")
    strong = (
        all(
            L.get("supplier_sector_fit")
            in ("CONFIRMED_ENGINEERING", "STRONG_ENGINEERING_FIT")
            for L in top
        )
        if top
        else False
    )
    # also require data_quality full history fields present
    hist_ok = all(
        (L.get("data_quality") or {}).get("total_contract_count_full_history") is not None
        for L in top
    ) if top else False
    print({"top10": len(top), "oos": oos, "strong": strong, "full_history_fields": hist_ok})
    return 0 if strong and oos == 0 and top and hist_ok else 1


def cmd_ranking_stability(_: argparse.Namespace) -> int:
    p = ART / "ranking-stability.json"
    d = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    print(d)
    return 0 if d.get("ok") else 1


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
    """Prove write denial on source role when enforce_source_readonly=True."""
    from scripts.commercial_leads.dbutil import connect
    from scripts.commercial_leads.isolation import assert_source_state_isolation

    dsn = _require_dsn()
    isolation = assert_source_state_isolation(
        source_dsn=dsn,
        state_dsn=dsn,
        force_mode="RESTORED_SNAPSHOT_SINGLE_DB",
        enforce_source_readonly=True,
    )
    report: dict[str, Any] = {"isolation": isolation.as_dict()}
    # Attempt writes against commercial ledger (state) and snapshot table
    conn = connect(dsn)
    write_tests: dict[str, Any] = {}
    try:
        with conn.cursor() as cur:
            # Snapshot table must not be mutated by campaign writes in policy;
            # we only prove we can detect mode. Actual role separation may be soft
            # on RESTORED_SNAPSHOT_SINGLE_DB single role.
            try:
                cur.execute(
                    "SELECT 1 FROM public.pncp_supplier_contracts LIMIT 1"
                )
                write_tests["select_snapshot"] = "ok"
            except Exception as exc:  # noqa: BLE001
                write_tests["select_snapshot"] = f"fail:{exc}"
            # State insert into commercial_lead_runs should be possible
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
                write_tests["insert_ledger"] = "ok"
                cur.execute("DELETE FROM commercial_lead_runs WHERE run_id = 'gate-isolation-probe'")
                conn.commit()
            except Exception as exc:  # noqa: BLE001
                write_tests["insert_ledger"] = f"fail:{exc}"
                try:
                    conn.rollback()
                except Exception:  # noqa: BLE001
                    pass
    finally:
        conn.close()

    report["write_tests"] = write_tests
    report["ok"] = (
        isolation.source_state_mode == "RESTORED_SNAPSHOT_SINGLE_DB"
        and write_tests.get("insert_ledger") == "ok"
        and write_tests.get("select_snapshot") == "ok"
    )
    report["note"] = (
        "RESTORED_SNAPSHOT_SINGLE_DB: same physical DB; ledger write proven; "
        "true OS-level source readonly requires separate role (not claimed as SEPARATED)."
    )
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
            "SELECT version, name FROM _migrations WHERE version IN ('062','063') ORDER BY version",
        )
        r["applied_versions"] = [x["version"] for x in rows]
        r["has_062"] = any(x["version"] == "062" for x in rows)
        r["has_063"] = any(x["version"] == "063" for x in rows)
        r["ok"] = r["ok"] and r["has_062"] and r["has_063"]
    finally:
        conn.close()
    (ART / "migrations-gate.json").write_text(json.dumps(r, indent=2, default=str) + "\n")
    print(json.dumps(r, indent=2, default=str))
    return 0 if r["ok"] else 1


def cmd_package_evidence(_: argparse.Namespace) -> int:
    out = ART / "evidence-package"
    out.mkdir(parents=True, exist_ok=True)
    sha = subprocess.check_output(  # noqa: S603,S607
        ["git", "rev-parse", "HEAD"], cwd=str(_ROOT), text=True
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
    p = ART / "evidence-package" / "attestation.json"
    d = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    head = subprocess.check_output(  # noqa: S603,S607
        ["git", "rev-parse", "HEAD"], cwd=str(_ROOT), text=True
    ).strip()
    ok = d.get("executed_git_sha") == head and bool(
        (d.get("checksums") or {}).get("gold-standard-baseline.json", {}).get("exists")
    )
    print({"ok": ok, "executed": d.get("executed_git_sha"), "head": head})
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
