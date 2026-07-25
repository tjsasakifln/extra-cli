"""CLI: python -m scripts.commercial_leads <command>"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from scripts.commercial_leads import CAMPAIGN_ID
from scripts.commercial_leads.dbutil import connect, fetch_all
from scripts.commercial_leads.isolation import assert_isolation, mask_dsn
from scripts.commercial_leads.pipeline import (
    git_sha,
    run_pipeline,
    verify_migration_idempotence,
)
from scripts.commercial_leads.review import (
    apply_review,
    explain_lead,
    export_reviews_csv,
    import_reviews_csv,
    list_leads,
)


def _print_json(data: dict[str, Any], output: str | None) -> int:
    text = json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n"
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(text, encoding="utf-8")
        print(f"wrote {output} status={data.get('status') or data.get('ok')}")
    else:
        sys.stdout.write(text)
    return 0 if data.get("status") in (None, "PASS") or data.get("ok") is True else 1


def cmd_run(args: argparse.Namespace) -> int:
    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    result = run_pipeline(
        dsn=args.dsn,
        profile_path=args.profile,
        snapshot_manifest=args.snapshot_manifest,
        out_dir=args.out,
        max_contracts=args.max_contracts,
        as_of=as_of,
        skip_migrations=args.skip_migrations,
        skip_persist=args.skip_persist,
        verify_snapshot_hash=not args.skip_hash_verify,
    )
    status = result.get("status")
    print(
        f"[{CAMPAIGN_ID}] status={status} leads={len(result.get('leads') or [])} "
        f"run_id={result.get('run_id')} dsn={mask_dsn(args.dsn)}"
    )
    code = 0 if status == "PASS" else (2 if str(status).startswith("BLOCKED") else 1)
    if args.result_json:
        Path(args.result_json).write_text(
            json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
    return code


def cmd_gate(args: argparse.Namespace) -> int:
    out = Path(args.out)
    run_path = Path(args.run_result) if args.run_result else out.parent / "run-result.json"
    if args.run_result is None and out.suffix == ".json":
        # if out is gate.json, look for sibling run-result
        run_path = out.parent / "run-result.json"
    if not run_path.is_file():
        # try out dir
        cand = Path(args.out).parent / "run" / "run-result.json"
        if cand.is_file():
            run_path = cand
    if not run_path.is_file():
        data = {"ok": False, "status": "FAIL", "reasons": [f"missing_run_result:{run_path}"]}
        return _print_json(data, str(out))

    run = json.loads(run_path.read_text(encoding="utf-8"))
    reasons: list[str] = []
    checks: dict[str, Any] = {}

    iso = run.get("isolation") or {}
    checks["isolation"] = bool(iso.get("ok"))
    checks["production_touched_false"] = run.get("production_touched") is False
    checks["soak_touched_false"] = run.get("soak_touched") is False
    checks["migrations_idempotent"] = bool((run.get("migrations") or {}).get("idempotent"))
    checks["snapshot_real"] = bool((run.get("snapshot") or {}).get("ok"))
    checks["snapshot_hash_present"] = bool(run.get("snapshot_hash"))

    leads = run.get("leads") or []
    top10 = leads[:10]
    checks["top10_cnpj_defensible"] = all(
        isinstance(L.get("cnpj14"), str) and len(L["cnpj14"]) == 14 and L["cnpj14"].isdigit()
        for L in top10
    ) and (len(top10) > 0 or run.get("status", "").startswith("BLOCKED"))
    checks["top10_has_signal"] = all(len(L.get("signals_fired") or []) >= 1 for L in top10) if top10 else False
    checks["top10_has_provenance"] = all(len(L.get("evidence") or []) >= 1 for L in top10) if top10 else False
    checks["score_decomposable"] = all(
        isinstance(L.get("score_decomposition"), dict) and L.get("score_decomposition") for L in top10
    ) if top10 else False
    checks["export_reconciled"] = bool((run.get("export_reconciliation") or {}).get("ok"))

    # forbidden language in outputs
    blob = json.dumps(leads, ensure_ascii=False).lower()
    forbidden = [
        "propensão",
        "probabilidade de compra",
        "intenção de compra",
        "empresa interessada",
        "lead quente",
        "chance de conversão",
    ]
    checks["no_forbidden_language"] = not any(f in blob for f in forbidden)

    for k, v in checks.items():
        if not v:
            reasons.append(k)

    # empty queue with BLOCKED is acceptable for some gates
    if not top10 and str(run.get("status", "")).startswith("BLOCKED"):
        reasons = [r for r in reasons if r not in {
            "top10_has_signal",
            "top10_has_provenance",
            "score_decomposable",
            "top10_cnpj_defensible",
        }]

    ok = len(reasons) == 0 and run.get("status") in ("PASS", "BLOCKED", "BLOCKED_MISSING_AUTHENTICATED_REAL_SNAPSHOT")
    if run.get("status") == "FAIL":
        ok = False
        reasons.append("run_status_fail")

    data = {
        "ok": ok,
        "status": "PASS" if ok else "FAIL",
        "campaign_id": CAMPAIGN_ID,
        "run_id": run.get("run_id"),
        "run_status": run.get("status"),
        "checks": checks,
        "reasons": reasons,
        "git_sha": git_sha(),
    }
    return _print_json(data, str(out))


def cmd_verify(args: argparse.Namespace) -> int:
    iso = assert_isolation(args.dsn)
    if not iso.ok:
        return _print_json(
            {"ok": False, "status": "FAIL", "isolation": iso.as_dict()},
            args.out,
        )
    mig = verify_migration_idempotence(args.dsn) if not args.skip_migrations else {"idempotent": True}
    conn = connect(args.dsn)
    try:
        tables = fetch_all(
            conn,
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema='public'
              AND table_name IN (
                'commercial_lead_runs','commercial_leads',
                'commercial_lead_state_overrides','commercial_feedback_ledger',
                'commercial_exclusions','pncp_supplier_contracts'
              )
            ORDER BY table_name
            """,
        )
        n_contracts = fetch_all(conn, "SELECT COUNT(*)::bigint AS n FROM pncp_supplier_contracts")[0]["n"]
        has_062 = fetch_all(
            conn,
            "SELECT 1 AS ok FROM public._migrations WHERE version LIKE '062%' LIMIT 1",
        )
    finally:
        conn.close()

    expected = {
        "commercial_lead_runs",
        "commercial_leads",
        "commercial_lead_state_overrides",
        "commercial_feedback_ledger",
        "commercial_exclusions",
        "pncp_supplier_contracts",
    }
    present = {r["table_name"] for r in tables}
    missing = sorted(expected - present)
    ok = mig.get("idempotent") is True and not missing and iso.ok
    data = {
        "ok": ok,
        "status": "PASS" if ok else "FAIL",
        "isolation": iso.as_dict(),
        "migrations_idempotent": mig.get("idempotent"),
        "tables_present": sorted(present),
        "tables_missing": missing,
        "contract_count": int(n_contracts),
        "migration_062_applied": bool(has_062),
        "dsn_masked": mask_dsn(args.dsn),
    }
    return _print_json(data, args.out)


def cmd_reproduce(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    r1_dir = out / "run1"
    r2_dir = out / "run2"
    common = dict(
        dsn=args.dsn,
        profile_path=args.profile,
        snapshot_manifest=args.snapshot_manifest,
        max_contracts=args.max_contracts,
        skip_migrations=True,
        skip_persist=True,
        verify_snapshot_hash=not args.skip_hash_verify,
    )
    a = run_pipeline(out_dir=r1_dir, **common)
    b = run_pipeline(out_dir=r2_dir, **common)
    ha, hb = a.get("ranking_hash"), b.get("ranking_hash")
    same = ha is not None and ha == hb
    # also compare lead cnpj lists
    la = [L.get("cnpj14") for L in (a.get("leads") or [])]
    lb = [L.get("cnpj14") for L in (b.get("leads") or [])]
    data = {
        "ok": same and la == lb,
        "status": "PASS" if same and la == lb else "FAIL",
        "ranking_hash_run1": ha,
        "ranking_hash_run2": hb,
        "leads_run1": la,
        "leads_run2": lb,
        "status_run1": a.get("status"),
        "status_run2": b.get("status"),
    }
    return _print_json(data, str(out / "reproduce.json"))


def cmd_explain(args: argparse.Namespace) -> int:
    run_path = Path(args.run_result)
    run = json.loads(run_path.read_text(encoding="utf-8"))
    cnpj = "".join(ch for ch in args.cnpj if ch.isdigit())
    for lead in run.get("leads") or []:
        if lead.get("cnpj14") == cnpj:
            return _print_json(lead, args.out)
    return _print_json({"ok": False, "error": "cnpj_not_in_queue", "cnpj14": cnpj}, args.out)



def cmd_review(args: argparse.Namespace) -> int:
    try:
        data = apply_review(
            args.dsn,
            cnpj=args.cnpj,
            status=args.status,
            reason=args.reason,
            author=args.author,
            run_id=args.run_id,
            force_override=args.force_override,
        )
        return _print_json(data, args.out)
    except Exception as exc:  # noqa: BLE001
        return _print_json({"ok": False, "status": "FAIL", "error": str(exc)}, args.out)


def cmd_list(args: argparse.Namespace) -> int:
    try:
        data = list_leads(
            args.dsn,
            limit=args.limit,
            changed_since_last_run=args.changed_since_last_run,
        )
        return _print_json(data, args.out)
    except Exception as exc:  # noqa: BLE001
        return _print_json({"ok": False, "error": str(exc)}, args.out)


def cmd_explain_db(args: argparse.Namespace) -> int:
    try:
        data = explain_lead(args.dsn, args.cnpj)
        return _print_json(data, args.out)
    except Exception as exc:  # noqa: BLE001
        return _print_json({"ok": False, "error": str(exc)}, args.out)


def cmd_export_reviews(args: argparse.Namespace) -> int:
    try:
        data = export_reviews_csv(args.dsn, args.out)
        return _print_json(data, None if args.out.endswith(".csv") else args.out)
    except Exception as exc:  # noqa: BLE001
        return _print_json({"ok": False, "error": str(exc)}, None)


def cmd_import_reviews(args: argparse.Namespace) -> int:
    try:
        data = import_reviews_csv(
            args.dsn,
            args.path,
            author=args.author,
            default_run_id=args.run_id,
        )
        code = 0 if data.get("ok") else 1
        text = json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n"
        sys.stdout.write(text)
        return code
    except Exception as exc:  # noqa: BLE001
        return _print_json({"ok": False, "error": str(exc)}, None)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m scripts.commercial_leads",
        description=(
            "CONFENGE commercial queue — sinais observados de necessidade/aderência. "
            "Não calcula probabilidade de compra nem claim de conversão."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="Generate commercial queue from snapshot + DB")
    r.add_argument("--dsn", required=True)
    r.add_argument("--profile", required=True)
    r.add_argument("--snapshot-manifest", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--max-contracts", type=int, default=250_000)
    r.add_argument("--as-of", default=None, help="YYYY-MM-DD")
    r.add_argument("--skip-migrations", action="store_true")
    r.add_argument("--skip-persist", action="store_true")
    r.add_argument("--skip-hash-verify", action="store_true")
    r.add_argument("--result-json", default=None)
    r.set_defaults(func=cmd_run)

    g = sub.add_parser("gate", help="Deterministic quality gate on run outputs")
    g.add_argument("--out", required=True)
    g.add_argument("--run-result", default=None)
    g.set_defaults(func=cmd_gate)

    v = sub.add_parser("verify", help="Verify isolation + schema + migrations")
    v.add_argument("--dsn", required=True)
    v.add_argument("--out", required=True)
    v.add_argument("--skip-migrations", action="store_true")
    v.set_defaults(func=cmd_verify)

    rep = sub.add_parser("reproduce", help="Two runs → compare ranking hashes")
    rep.add_argument("--dsn", required=True)
    rep.add_argument("--profile", required=True)
    rep.add_argument("--snapshot-manifest", required=True)
    rep.add_argument("--out", required=True)
    rep.add_argument("--max-contracts", type=int, default=250_000)
    rep.add_argument("--skip-hash-verify", action="store_true")
    rep.set_defaults(func=cmd_reproduce)

    ex = sub.add_parser("explain", help="Explain one CNPJ from a run-result.json")
    ex.add_argument("--run-result", required=True)
    ex.add_argument("--cnpj", required=True)
    ex.add_argument("--out", default=None)
    ex.set_defaults(func=cmd_explain)


    rev = sub.add_parser("review", help="Register human review / state change")
    rev.add_argument("--dsn", required=True)
    rev.add_argument("--cnpj", required=True)
    rev.add_argument("--status", required=True)
    rev.add_argument("--reason", required=True)
    rev.add_argument("--author", default="tiago")
    rev.add_argument("--run-id", default=None)
    rev.add_argument("--force-override", action="store_true")
    rev.add_argument("--out", default=None)
    rev.set_defaults(func=cmd_review)

    ls = sub.add_parser("list", help="List latest commercial leads")
    ls.add_argument("--dsn", required=True)
    ls.add_argument("--limit", type=int, default=20)
    ls.add_argument("--changed-since-last-run", action="store_true")
    ls.add_argument("--out", default=None)
    ls.set_defaults(func=cmd_list)

    exdb = sub.add_parser("explain-db", help="Explain lead from state DB")
    exdb.add_argument("--dsn", required=True)
    exdb.add_argument("--cnpj", required=True)
    exdb.add_argument("--out", default=None)
    exdb.set_defaults(func=cmd_explain_db)

    er = sub.add_parser("export-reviews", help="Export open review CSV")
    er.add_argument("--dsn", required=True)
    er.add_argument("--out", required=True)
    er.set_defaults(func=cmd_export_reviews)

    ir = sub.add_parser("import-reviews", help="Import human review CSV")
    ir.add_argument("--dsn", required=True)
    ir.add_argument("--path", required=True)
    ir.add_argument("--author", default="tiago")
    ir.add_argument("--run-id", default=None)
    ir.set_defaults(func=cmd_import_reviews)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
