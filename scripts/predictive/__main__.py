"""Canonical predictive facade CLI.

Usage:
  python -m scripts.predictive claims
  python -m scripts.predictive corpus-stats
  python -m scripts.predictive build-dataset --target demand_30d
  python -m scripts.predictive backtest --target demand_30d
  python -m scripts.predictive train --target demand_30d
  python -m scripts.predictive predict --target demand_30d --entity CNPJ
  python -m scripts.predictive resolve-outcomes
  python -m scripts.predictive monitor
  python -m scripts.predictive data-quality
  python -m scripts.predictive run-pipeline --limit 50000
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.predictive.backtest import (
    run_classification_backtest,
    run_regression_backtest,
    train_production_candidate,
)
from scripts.predictive.claims import load_registry
from scripts.predictive.data_access import (
    corpus_stats,
    fetch_aec_contracts,
    fetch_discount_pairs_from_opportunities,
    get_dsn,
)
from scripts.predictive.dataset import (
    build_competitive_winner_dataset,
    build_demand_dataset,
    build_discount_dataset,
)
from scripts.predictive.predict_service import blocked_prediction, emit_prediction
from scripts.predictive.profile_calibration import personalization_blockers


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _out_dir() -> Path:
    d = _root() / "artifacts" / "predictive"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save(name: str, payload: Any) -> Path:
    path = _out_dir() / name
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def _append_prediction_ledger(prediction: dict[str, Any]) -> Path:
    """Append-only ledger for outcome reconciliation (never rewrites past rows)."""
    path = _out_dir() / "predictions_ledger.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(prediction, ensure_ascii=False, default=str) + "\n")
    return path


def cmd_claims(_: argparse.Namespace) -> int:
    reg = load_registry()
    payload = reg.to_public_dict()
    path = _save("claim_states.json", payload)
    reg.save()
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    print(f"# wrote {path}", file=sys.stderr)
    return 0


def cmd_corpus_stats(args: argparse.Namespace) -> int:
    stats = corpus_stats(args.dsn)
    _save("corpus_stats.json", stats)
    print(json.dumps(stats, indent=2, ensure_ascii=False, default=str))
    return 0


def cmd_data_quality(args: argparse.Namespace) -> int:
    stats = corpus_stats(args.dsn)
    # sample contracts for label coverage estimate
    limit = args.limit or 20000
    try:
        rows = fetch_aec_contracts(args.dsn, limit=limit, uf=args.uf)
    except Exception as exc:
        rows = []
        stats["fetch_error"] = str(exc)
    from scripts.predictive.labels import is_aec_object

    n_aec = sum(
        1
        for r in rows
        if is_aec_object(str(r.get("objeto_contrato") or ""))
    )
    pairs = []
    try:
        pairs = fetch_discount_pairs_from_opportunities(args.dsn)
    except Exception as exc:
        stats["discount_fetch_error"] = str(exc)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corpus": stats,
        "sample_limit": limit,
        "sample_aec_rows": len(rows),
        "sample_aec_confirmed": n_aec,
        "discount_valid_pairs": len(pairs),
        "p2b_participation": {
            "status": "DATA_BLOCKED",
            "reason": "No complete participant-list tables in production schema",
        },
        "p3_discount": {
            "status": "DATA_BLOCKED" if len(pairs) < 1000 else "IMPLEMENTED",
            "n_pairs": len(pairs),
            "reason": (
                "Need auditável estimated→adjudicated joins; "
                f"found {len(pairs)} opportunity_intel pairs"
            ),
        },
        "selection_bias_notes": [
            "Contracts are winners only — not full bidder sets",
            "Absence in incomplete crawl windows is not a demand negative",
            "AEC filter is keyword-based; not CNAE-perfect",
        ],
    }
    path = _save("data_quality_report.json", report)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    print(f"# wrote {path}", file=sys.stderr)
    return 0


def _build_for_target(args: argparse.Namespace) -> Any:
    target = args.target
    if target.startswith("demand_"):
        days = int(target.split("_")[1].replace("d", ""))
        rows = fetch_aec_contracts(
            args.dsn, limit=args.limit, uf=args.uf, min_year=args.min_year
        )
        return build_demand_dataset(
            rows,
            horizon_days=days,
            max_entes=args.max_entes,
        )
    if target == "competitive_winner_p2a":
        rows = fetch_aec_contracts(
            args.dsn, limit=args.limit, uf=args.uf, min_year=args.min_year
        )
        return build_competitive_winner_dataset(
            rows, max_outcomes=args.max_outcomes
        )
    if target == "competitive_participation_p2b":
        from scripts.predictive.dataset import DatasetBuildResult
        import uuid

        return DatasetBuildResult(
            run_id=f"ds_p2b_{uuid.uuid4().hex[:8]}",
            target_name=target,
            dataset_version="p2b_v1",
            examples=[],
            blockers=[
                "P2B DATA_BLOCKED: participant lists not available in schema "
                "(contracts show winners only)"
            ],
            status="data_blocked",
        )
    if target == "winning_discount_p3":
        pairs = fetch_discount_pairs_from_opportunities(args.dsn)
        return build_discount_dataset(pairs)
    if target in {"extra_win_probability_p4", "optimal_bid_p5"}:
        from scripts.predictive.dataset import DatasetBuildResult
        import uuid

        blockers = personalization_blockers()
        return DatasetBuildResult(
            run_id=f"ds_{target}_{uuid.uuid4().hex[:8]}",
            target_name=target,
            dataset_version="p4p5_v1",
            examples=[],
            blockers=[
                "Requires participant×opportunity labels (not winner-only contracts)",
                * [m["field"] + ": " + m["reason"] for m in blockers["missing_critical"]],
            ],
            status="data_blocked",
            coverage=blockers,
        )
    raise SystemExit(f"Unknown target: {target}")


def cmd_build_dataset(args: argparse.Namespace) -> int:
    result = _build_for_target(args)
    summary = result.to_summary()
    # persist examples lightly (cap)
    examples_path = _out_dir() / f"examples_{args.target}.jsonl"
    with examples_path.open("w", encoding="utf-8") as fh:
        for ex in result.examples[:50000]:
            fh.write(json.dumps(ex, ensure_ascii=False, default=str) + "\n")
    summary["examples_path"] = str(examples_path)
    summary["examples_written"] = min(len(result.examples), 50000)
    path = _save(f"dataset_{args.target}.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    print(f"# wrote {path}", file=sys.stderr)
    return 0


def cmd_backtest(args: argparse.Namespace) -> int:
    result = _build_for_target(args)
    if result.status == "data_blocked" or not result.examples:
        payload = {
            "target": args.target,
            "claim_recommendation": "DATA_BLOCKED",
            "blockers": result.blockers,
            "dataset": result.to_summary(),
        }
        _save(f"backtest_{args.target}.json", payload)
        # update registry
        reg = load_registry()
        claim_map = {
            "demand_30d": "PREDICTIVE_DEMAND_FORECAST_AVAILABLE",
            "demand_60d": "PREDICTIVE_DEMAND_FORECAST_AVAILABLE",
            "demand_90d": "PREDICTIVE_DEMAND_FORECAST_AVAILABLE",
            "competitive_winner_p2a": "PREDICTIVE_COMPETITIVE_INTELLIGENCE_AVAILABLE",
            "competitive_participation_p2b": "PREDICTIVE_COMPETITIVE_INTELLIGENCE_AVAILABLE",
            "winning_discount_p3": "PREDICTIVE_WINNING_DISCOUNT_AVAILABLE",
            "extra_win_probability_p4": "EXTRA_WIN_PROBABILITY_AVAILABLE",
            "optimal_bid_p5": "OPTIMAL_BID_RECOMMENDATION_AVAILABLE",
        }
        cid = claim_map.get(args.target)
        if cid:
            try:
                reg.set_state(
                    cid,
                    "DATA_BLOCKED",
                    blockers=result.blockers,
                    evidence={"dataset": result.to_summary()},
                    force=True,
                )
            except ValueError:
                reg.set_state(
                    cid,
                    "IMPLEMENTED",
                    force=True,
                )
                reg.set_state(
                    cid,
                    "DATA_BLOCKED",
                    blockers=result.blockers,
                    evidence={"dataset": result.to_summary()},
                    force=True,
                )
            reg.save()
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0

    if args.target.startswith("winning_discount"):
        bt = run_regression_backtest(result.examples, target_name=args.target)
    else:
        bt = run_classification_backtest(result.examples, target_name=args.target)

    payload = bt.to_dict()
    payload["dataset"] = result.to_summary()
    _save(f"backtest_{args.target}.json", payload)

    # update claims honestly
    reg = load_registry()
    claim_map = {
        "demand_30d": "PREDICTIVE_DEMAND_FORECAST_AVAILABLE",
        "demand_60d": "PREDICTIVE_DEMAND_FORECAST_AVAILABLE",
        "demand_90d": "PREDICTIVE_DEMAND_FORECAST_AVAILABLE",
        "competitive_winner_p2a": "PREDICTIVE_COMPETITIVE_INTELLIGENCE_AVAILABLE",
        "winning_discount_p3": "PREDICTIVE_WINNING_DISCOUNT_AVAILABLE",
    }
    cid = claim_map.get(args.target)
    if cid:
        state = bt.claim_recommendation
        # mark implemented first if needed
        if reg.get(cid).state == "NOT_IMPLEMENTED":
            reg.set_state(cid, "IMPLEMENTED", force=True)
        try:
            reg.set_state(
                cid,
                state,
                evidence={"backtest": payload.get("gate"), "best_model": bt.best_model},
                blockers=bt.blockers,
                force=True,
            )
        except ValueError as exc:
            payload["claim_update_error"] = str(exc)
        # Do NOT auto-promote HISTORICAL_BACKTEST_PROVEN → SHADOW_OPERATIONAL.
        # SHADOW_OPERATIONAL requires actual scheduled emission + persistence of
        # pre-outcome predictions (systemd timer running), not local readiness alone.
        if state == "HISTORICAL_BACKTEST_PROVEN":
            payload["shadow_note"] = (
                "Historical gates passed. Claim remains HISTORICAL_BACKTEST_PROVEN "
                "until shadow path emits/persists predictions on a live schedule "
                "(enable extra-predictive-shadow.timer and verify prediction ledger)."
            )
        reg.save()
        payload["claim_state"] = reg.get(cid).state

    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    return 0


def cmd_train(args: argparse.Namespace) -> int:
    result = _build_for_target(args)
    if not result.examples:
        print(json.dumps({"error": "no examples", "blockers": result.blockers}, indent=2))
        return 2
    task = "regression" if args.target.startswith("winning_discount") else "classification"
    model, feature_names, meta = train_production_candidate(result.examples, task=task)
    artifact = {
        "target": args.target,
        "model_name": model.name,
        "family": model.family,
        "calibrated": model.calibrated,
        "calibration_method": model.calibration_method,
        "feature_names": feature_names,
        "artifact_sha256": model.artifact_sha256(),
        "meta": meta,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "approval_status": "candidate",
        "limitations": [
            "Candidate only — not PRODUCTION_AVAILABLE without prospective gates",
        ],
    }
    # save artifact metadata (not full sklearn blob with sensitive recovery)
    path = _save(f"model_{args.target}.json", artifact)
    # also store feature template
    _save(
        f"model_{args.target}_artifact_meta.json",
        json.loads(model.artifact_blob().decode()),
    )
    print(json.dumps({"path": str(path), **artifact}, indent=2, ensure_ascii=False))
    return 0


def cmd_predict(args: argparse.Namespace) -> int:
    reg = load_registry()
    # Without a live model object, emit blocked/honest envelope using claim state
    model_meta_path = _out_dir() / f"model_{args.target}.json"
    model = None
    model_id = None
    model_version = None
    feature_names: list[str] = []
    if model_meta_path.exists():
        meta = json.loads(model_meta_path.read_text(encoding="utf-8"))
        model_id = meta.get("model_name")
        model_version = meta.get("trained_at")
        feature_names = meta.get("feature_names") or []
    features = {}
    if args.features_json:
        features = json.loads(Path(args.features_json).read_text(encoding="utf-8"))

    if model is None:
        # still emit honest record
        rec = blocked_prediction(
            target_name=args.target,
            reason=(
                "Model object not loaded in-process; use train + in-process predict "
                "or shadow job. Claim gate still applied."
                if not model_meta_path.exists()
                else "Artifact metadata present but estimator not rehydrated for safety"
            ),
            registry=reg,
        )
        # attach meta
        d = rec.to_dict()
        d["model_meta_present"] = model_meta_path.exists()
        d["entity_id"] = args.entity
        _append_prediction_ledger(d)
        print(json.dumps(d, indent=2, ensure_ascii=False, default=str))
        _save(f"prediction_last_{args.target}.json", d)
        return 0

    rec = emit_prediction(
        target_name=args.target,
        features=features,
        feature_names=feature_names,
        model=model,
        model_id=model_id,
        model_version=model_version,
        registry=reg,
        entity_id=args.entity,
        horizon=args.horizon,
        mode="shadow",
    )
    d = rec.to_dict()
    _append_prediction_ledger(d)
    print(json.dumps(d, indent=2, ensure_ascii=False, default=str))
    _save(f"prediction_last_{args.target}.json", d)
    return 0


def cmd_resolve_outcomes(args: argparse.Namespace) -> int:
    """Join immutable predictions to post-window observed events; append outcomes ledger."""
    from scripts.predictive.outcomes import (
        default_ledger_path,
        load_predictions_jsonl,
        persist_outcomes,
        resolve_predictions,
    )

    pred_path = _out_dir() / "predictions_ledger.jsonl"
    # Also accept last single prediction files
    predictions = load_predictions_jsonl(pred_path)
    for p in _out_dir().glob("prediction_last_*.json"):
        try:
            predictions.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass

    contracts: list[dict] = []
    fetch_error = None
    try:
        contracts = fetch_aec_contracts(
            args.dsn, limit=args.limit or 50000, uf=args.uf, min_year=args.min_year
        )
    except Exception as exc:
        fetch_error = str(exc)

    resolved = resolve_predictions(predictions, contracts=contracts)
    persist = persist_outcomes(resolved, dsn=args.dsn or get_dsn())
    pending = max(0, len(predictions) - len(resolved) - int(persist.get("skipped_existing") or 0))
    payload = {
        "status": "ok" if fetch_error is None else "degraded",
        "predictions_loaded": len(predictions),
        "resolved": len(resolved),
        "pending_or_immature": pending,
        "persist": persist,
        "fetch_error": fetch_error,
        "note": (
            "Predictions are never rewritten. Outcomes append-only. "
            "Demand labels resolve only after horizon window fully elapses."
        ),
        "outcomes_sample": [r.to_dict() for r in resolved[:5]],
    }
    _save("outcomes_resolve_last.json", payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    return 0 if fetch_error is None else 1


def cmd_monitor(args: argparse.Namespace) -> int:
    """Drift/calibration monitor over outcome ledger; may suspend claims."""
    from scripts.predictive.drift import (
        apply_drift_to_claims,
        default_drift_path,
        evaluate_outcomes_drift,
    )
    from scripts.predictive.outcomes import default_ledger_path, load_predictions_jsonl

    reg = load_registry()
    outcomes_path = default_ledger_path()
    outcomes: list[dict] = []
    if outcomes_path.exists():
        for line in outcomes_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    outcomes.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    pred_path = _out_dir() / "predictions_ledger.jsonl"
    predictions = load_predictions_jsonl(pred_path)
    for p in _out_dir().glob("prediction_last_*.json"):
        try:
            predictions.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass

    # Evaluate per known target present in predictions
    targets = sorted(
        {
            str(p.get("target_name"))
            for p in predictions
            if p.get("target_name")
        }
        | {"demand_30d", "competitive_winner_p2a"}
    )
    drift_reports = []
    suspend_actions = []
    for t in targets:
        report = evaluate_outcomes_drift(
            outcomes, predictions, target_name=t, min_outcomes=30
        )
        drift_reports.append(report.to_dict())
        action = apply_drift_to_claims(report, registry=reg)
        suspend_actions.append(action)

    payload = {
        "status": "ok",
        "claims": reg.to_public_dict(),
        "n_outcomes": len(outcomes),
        "n_predictions": len(predictions),
        "drift_reports": drift_reports,
        "suspend_actions": suspend_actions,
        "outcomes_ledger": str(outcomes_path),
        "note": (
            "insufficient_data is expected until prospective predictions mature; "
            "suspend_drift / suspend_data_quality actively update claim registry"
        ),
    }
    path = default_drift_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n")
    _save("monitor_last.json", payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    return 0


def cmd_run_pipeline(args: argparse.Namespace) -> int:
    """End-to-end: data-quality + build/backtest key targets + claims snapshot."""
    results: dict[str, Any] = {"steps": []}
    for target in [
        "demand_30d",
        "demand_60d",
        "demand_90d",
        "competitive_winner_p2a",
        "winning_discount_p3",
        "competitive_participation_p2b",
        "extra_win_probability_p4",
    ]:
        args.target = target
        try:
            rc = cmd_backtest(args)
            results["steps"].append({"target": target, "rc": rc})
        except Exception as exc:
            results["steps"].append({"target": target, "error": str(exc)})
    reg = load_registry()
    results["claims"] = reg.to_public_dict()
    results["extra_profile"] = personalization_blockers()
    _save("pipeline_last.json", results)
    print(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m scripts.predictive")
    p.add_argument("--dsn", default=None)
    p.add_argument("--uf", default=None)
    p.add_argument("--limit", type=int, default=50000)
    p.add_argument("--max-entes", type=int, default=None)
    p.add_argument("--max-outcomes", type=int, default=5000)
    p.add_argument("--min-year", type=int, default=2020)
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("claims")
    sub.add_parser("corpus-stats")
    sub.add_parser("data-quality")
    sub.add_parser("resolve-outcomes")
    sub.add_parser("monitor")
    sub.add_parser("run-pipeline")

    b = sub.add_parser("build-dataset")
    b.add_argument("--target", required=True)

    bt = sub.add_parser("backtest")
    bt.add_argument("--target", required=True)

    tr = sub.add_parser("train")
    tr.add_argument("--target", required=True)

    pr = sub.add_parser("predict")
    pr.add_argument("--target", required=True)
    pr.add_argument("--entity", default=None)
    pr.add_argument("--horizon", default=None)
    pr.add_argument("--features-json", default=None)

    # approve is explicit no-op without evidence
    ap = sub.add_parser("approve")
    ap.add_argument("--target", required=True)
    ap.add_argument("--force", action="store_true")

    return p


def cmd_approve(args: argparse.Namespace) -> int:
    """Refuse production approval without prospective evidence."""
    reg = load_registry()
    claim_map = {
        "demand_30d": "PREDICTIVE_DEMAND_FORECAST_AVAILABLE",
        "demand_60d": "PREDICTIVE_DEMAND_FORECAST_AVAILABLE",
        "demand_90d": "PREDICTIVE_DEMAND_FORECAST_AVAILABLE",
        "competitive_winner_p2a": "PREDICTIVE_COMPETITIVE_INTELLIGENCE_AVAILABLE",
        "winning_discount_p3": "PREDICTIVE_WINNING_DISCOUNT_AVAILABLE",
    }
    cid = claim_map.get(args.target)
    if not cid:
        print(json.dumps({"error": "no claim mapping", "target": args.target}))
        return 2
    rec = reg.get(cid)
    if rec.state != "PROSPECTIVE_CALIBRATED" and not args.force:
        print(
            json.dumps(
                {
                    "approved": False,
                    "claim_id": cid,
                    "state": rec.state,
                    "reason": (
                        "PRODUCTION_AVAILABLE requires PROSPECTIVE_CALIBRATED "
                        "with soak evidence; refuse convenience approval"
                    ),
                },
                indent=2,
            )
        )
        return 3
    print(json.dumps({"approved": False, "reason": "use set_state with evidence pack"}))
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.dsn:
        import os

        os.environ["LOCAL_DATALAKE_DSN"] = args.dsn
    dispatch = {
        "claims": cmd_claims,
        "corpus-stats": cmd_corpus_stats,
        "data-quality": cmd_data_quality,
        "build-dataset": cmd_build_dataset,
        "backtest": cmd_backtest,
        "train": cmd_train,
        "predict": cmd_predict,
        "resolve-outcomes": cmd_resolve_outcomes,
        "monitor": cmd_monitor,
        "run-pipeline": cmd_run_pipeline,
        "approve": cmd_approve,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
