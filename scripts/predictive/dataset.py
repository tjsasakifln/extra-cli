"""Point-in-time dataset builders for demand, competitive (P2A), discount (P3)."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Sequence

from scripts.predictive.features import (
    FEATURE_SCHEMA_VERSION,
    build_competitor_features,
    build_demand_features,
    build_discount_features,
    validate_feature_cutoff,
)
from scripts.predictive.labels import (
    aec_category,
    demand_label,
    is_aec_object,
    winning_discount,
    winner_label,
)
from scripts.predictive.leakage import assert_no_leakage, audit_examples


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _example_id(*parts: str) -> str:
    h = hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]
    return f"ex_{h}"


@dataclass
class DatasetBuildResult:
    run_id: str
    target_name: str
    dataset_version: str
    examples: list[dict[str, Any]]
    n_rejected_invalid_neg: int = 0
    coverage: dict[str, Any] = field(default_factory=dict)
    leakage: dict[str, Any] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)
    status: str = "built"

    def to_summary(self) -> dict[str, Any]:
        n_pos = sum(1 for e in self.examples if e.get("label_value") == 1)
        n_neg = sum(1 for e in self.examples if e.get("label_value") == 0)
        return {
            "run_id": self.run_id,
            "target_name": self.target_name,
            "dataset_version": self.dataset_version,
            "n_examples": len(self.examples),
            "n_positives": n_pos,
            "n_negatives": n_neg,
            "n_rejected_invalid_neg": self.n_rejected_invalid_neg,
            "coverage": self.coverage,
            "leakage": self.leakage,
            "blockers": self.blockers,
            "status": self.status,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
        }


def _contract_event_at(row: dict[str, Any]) -> datetime | None:
    for key in (
        "source_event_date",
        "data_assinatura",
        "data_publicacao",
        "data_publicacao_fonte",
        "data_inicio",
    ):
        v = row.get(key)
        if v is None:
            continue
        if isinstance(v, datetime):
            dt = _utc(v)
            # filter garbage future dates
            if dt.year > 2100 or dt.year < 1990:
                continue
            return dt
        if isinstance(v, str):
            try:
                dt = _utc(datetime.fromisoformat(v.replace("Z", "+00:00")))
                if dt.year > 2100 or dt.year < 1990:
                    continue
                return dt
            except ValueError:
                continue
    return None


def build_demand_dataset(
    contracts: Sequence[dict[str, Any]],
    *,
    horizon_days: int = 30,
    as_of_dates: Sequence[datetime] | None = None,
    require_coverage: bool = True,
    coverage_by_ente: dict[str, set[str]] | None = None,
    dataset_version: str = "demand_v1",
    category_filter: str | None = None,
    max_entes: int | None = None,
) -> DatasetBuildResult:
    """Build demand examples: ente × category × as_of × horizon.

    contracts: rows with orgao_cnpj, objeto_contrato/objeto, event dates, valor_total.
    coverage_by_ente: optional map ente_id -> set of YYYY-MM months with confirmed crawl coverage.
    If require_coverage and coverage missing, negatives are rejected.
    When coverage_by_ente is None and require_coverage=True, we treat presence of ANY
    contract for the ente in a ±90d window around as_of as weak coverage evidence
    (source was producing data for that ente nearby) — still not inventing absence
    for completely unobserved entes.
    """
    target = f"demand_{horizon_days}d"
    run_id = f"ds_{target}_{uuid.uuid4().hex[:12]}"

    # Index events by ente
    by_ente: dict[str, list[tuple[datetime, str, float | None]]] = {}
    for row in contracts:
        ente = str(row.get("orgao_cnpj") or row.get("entity_id") or "").strip()
        if not ente:
            continue
        obj = row.get("objeto_contrato") or row.get("objeto") or ""
        if not is_aec_object(str(obj)):
            continue
        cat = aec_category(str(obj))
        if category_filter and cat != category_filter:
            continue
        evt = _contract_event_at(row)
        if evt is None:
            continue
        val = row.get("valor_total") or row.get("valor")
        try:
            val_f = float(val) if val is not None else None
        except (TypeError, ValueError):
            val_f = None
        by_ente.setdefault(ente, []).append((evt, cat, val_f))

    for ente in by_ente:
        by_ente[ente].sort(key=lambda x: x[0])

    entes = sorted(by_ente.keys())
    if max_entes is not None:
        entes = entes[:max_entes]

    if as_of_dates is None:
        # Monthly as_of from first event+90d to last-horizon
        all_dates = [e[0] for evs in by_ente.values() for e in evs]
        if not all_dates:
            return DatasetBuildResult(
                run_id=run_id,
                target_name=target,
                dataset_version=dataset_version,
                examples=[],
                blockers=["No AEC contracts with valid event dates"],
                status="empty",
            )
        start = min(all_dates) + timedelta(days=90)
        end = max(all_dates) - timedelta(days=horizon_days)
        as_of_dates = []
        cur = datetime(start.year, start.month, 1, tzinfo=timezone.utc)
        end = _utc(end)
        while cur <= end:
            as_of_dates.append(cur)
            if cur.month == 12:
                cur = datetime(cur.year + 1, 1, 1, tzinfo=timezone.utc)
            else:
                cur = datetime(cur.year, cur.month + 1, 1, tzinfo=timezone.utc)

    examples: list[dict[str, Any]] = []
    rejected = 0
    categories_seen: set[str] = set()

    for ente in entes:
        events = by_ente[ente]
        cats = sorted({c for _, c, _ in events})
        for cat in cats:
            categories_seen.add(cat)
            cat_events = [(d, v) for d, c, v in events if c == cat]
            all_evt_dates = [d for d, _, _ in events]
            for as_of in as_of_dates:
                as_of = _utc(as_of)
                past = [d for d, _ in cat_events if d <= as_of]
                past_vals = [v for d, v in cat_events if d <= as_of]
                future = [d for d, _ in cat_events if d > as_of]

                # Coverage: explicit map OR weak signal that ente has nearby data
                if coverage_by_ente is not None:
                    months = coverage_by_ente.get(ente, set())
                    month_key = f"{as_of.year:04d}-{as_of.month:02d}"
                    cov_ok = month_key in months
                else:
                    near = [
                        d
                        for d in all_evt_dates
                        if abs((d - as_of).days) <= 180
                    ]
                    cov_ok = len(near) > 0

                lab = demand_label(
                    as_of=as_of,
                    horizon_days=horizon_days,
                    future_aec_events=future,
                    coverage_ok=cov_ok if require_coverage else True,
                )
                if lab.label_value is None:
                    rejected += 1
                    continue

                fv = build_demand_features(
                    as_of=as_of,
                    past_events=past,
                    past_values=[v for v in past_vals if v is not None],
                )
                leaks = validate_feature_cutoff(fv, as_of)
                if leaks:
                    rejected += 1
                    continue

                window_end = as_of + timedelta(days=horizon_days)
                eid = _example_id(target, ente, cat, as_of.isoformat(), str(horizon_days))
                examples.append(
                    {
                        "example_id": eid,
                        "target_name": target,
                        "entity_id": ente,
                        "procurement_id": None,
                        "supplier_id": None,
                        "as_of_at": as_of.isoformat(),
                        "prediction_horizon": f"{horizon_days}d",
                        "label_window_start": as_of.isoformat(),
                        "label_window_end": window_end.isoformat(),
                        "label_value": lab.label_value,
                        "label_source": lab.label_source,
                        "label_quality": lab.label_quality,
                        "features_json": fv.to_json(),
                        "feature_events": {
                            k: v.isoformat() for k, v in fv.events.items()
                        },
                        "feature_schema_version": FEATURE_SCHEMA_VERSION,
                        "source_run_ids": [],
                        "source_max_event_at": (
                            fv.source_max_event_at.isoformat()
                            if fv.source_max_event_at
                            else None
                        ),
                        "dataset_version": dataset_version,
                        "cohort": cat,
                    }
                )

    leak_report = audit_examples(examples)
    if not leak_report.ok:
        assert_no_leakage(examples)

    status = "built" if examples else "empty"
    blockers: list[str] = []
    if len(examples) < 1000:
        blockers.append(
            f"n_examples={len(examples)} < 1000 — gate DATA_BLOCKED for production claim"
        )

    return DatasetBuildResult(
        run_id=run_id,
        target_name=target,
        dataset_version=dataset_version,
        examples=examples,
        n_rejected_invalid_neg=rejected,
        coverage={
            "n_entes": len(entes),
            "categories": sorted(categories_seen),
            "n_as_of": len(as_of_dates),
            "require_coverage": require_coverage,
        },
        leakage=leak_report.to_dict(),
        blockers=blockers,
        status=status,
    )


def build_competitive_winner_dataset(
    contracts: Sequence[dict[str, Any]],
    *,
    dataset_version: str = "p2a_v1",
    max_outcomes: int | None = None,
    min_history_days: int = 180,
) -> DatasetBuildResult:
    """P2A: for each AEC contract outcome, candidates = prior winners at ente/category.

    as_of = day before outcome event. Label 1 for actual winner, 0 for other candidates.
    Streaming O(n) scan with running counts (point-in-time safe).
    """
    target = "competitive_winner_p2a"
    run_id = f"ds_{target}_{uuid.uuid4().hex[:12]}"

    rows: list[dict[str, Any]] = []
    for row in contracts:
        obj = row.get("objeto_contrato") or row.get("objeto") or ""
        if not is_aec_object(str(obj)):
            continue
        evt = _contract_event_at(row)
        if evt is None:
            continue
        ente = str(row.get("orgao_cnpj") or "").strip()
        supplier = str(row.get("fornecedor_cnpj") or "").strip()
        if not ente or not supplier:
            continue
        rows.append(
            {
                "event_at": evt,
                "ente": ente,
                "supplier": supplier,
                "category": aec_category(str(obj)),
                "valor": float(row["valor_total"])
                if row.get("valor_total") not in (None, "")
                else None,
                "contrato_id": str(
                    row.get("contrato_id") or row.get("id") or uuid.uuid4().hex[:12]
                ),
            }
        )
    rows.sort(key=lambda r: r["event_at"])

    # Optionally subsample outcomes (keep last N) but scan full history for counts
    outcome_indices: set[int] | None = None
    if max_outcomes is not None and len(rows) > max_outcomes:
        outcome_indices = set(range(len(rows) - max_outcomes, len(rows)))

    examples: list[dict[str, Any]] = []
    rejected = 0

    # Running aggregates (strictly past only — update AFTER emitting examples)
    # supplier totals
    supplier_total: dict[str, int] = {}
    supplier_last: dict[str, datetime] = {}
    # (ente, supplier) wins
    ente_supplier: dict[tuple[str, str], int] = {}
    # (cat, supplier) wins
    cat_supplier: dict[tuple[str, str], int] = {}
    # ente / cat totals
    ente_total: dict[str, int] = {}
    cat_total: dict[str, int] = {}
    # suppliers per ente / cat for candidate listing
    suppliers_at_ente: dict[str, set[str]] = {}
    suppliers_in_cat: dict[str, set[str]] = {}
    first_event: datetime | None = None

    for i, outcome in enumerate(rows):
        if first_event is None:
            first_event = outcome["event_at"]
        emit = outcome_indices is None or i in outcome_indices
        as_of = outcome["event_at"] - timedelta(days=1)
        ente = outcome["ente"]
        cat = outcome["category"]
        winner = outcome["supplier"]

        if emit:
            if first_event is None or (
                outcome["event_at"] - first_event
            ).days < min_history_days:
                rejected += 1
            else:
                candidates = set(suppliers_at_ente.get(ente, set())) | set(
                    suppliers_in_cat.get(cat, set())
                )
                candidates.add(winner)

                def score_sid(sid: str) -> tuple[int, int]:
                    return (
                        ente_supplier.get((ente, sid), 0)
                        + cat_supplier.get((cat, sid), 0),
                        supplier_total.get(sid, 0),
                    )

                ranked = sorted(candidates, key=score_sid, reverse=True)[:20]
                if winner not in ranked:
                    ranked = ranked[:19] + [winner]

                e_tot = max(ente_total.get(ente, 0), 1)
                c_tot = max(cat_total.get(cat, 0), 1)

                for sid in ranked:
                    lab = winner_label(
                        supplier_id=sid, winner_id=winner, in_candidate_set=True
                    )
                    if lab.label_value is None:
                        rejected += 1
                        continue
                    last = supplier_last.get(sid, as_of)
                    days_since = (as_of - last).days if last else 9999
                    fv = build_competitor_features(
                        as_of=as_of,
                        supplier_wins_at_ente=ente_supplier.get((ente, sid), 0),
                        supplier_wins_in_category=cat_supplier.get((cat, sid), 0),
                        supplier_wins_total=supplier_total.get(sid, 0),
                        ente_contracts_total=e_tot,
                        category_contracts_total=c_tot,
                        days_since_supplier_win=float(days_since),
                        value_band_wins=0,
                        last_event_at=last if last <= as_of else as_of,
                    )
                    if validate_feature_cutoff(fv, as_of):
                        rejected += 1
                        continue
                    eid = _example_id(
                        target, outcome["contrato_id"], sid, as_of.isoformat()
                    )
                    examples.append(
                        {
                            "example_id": eid,
                            "target_name": target,
                            "entity_id": ente,
                            "procurement_id": outcome["contrato_id"],
                            "supplier_id": sid,
                            "as_of_at": as_of.isoformat(),
                            "prediction_horizon": "outcome",
                            "label_window_start": as_of.isoformat(),
                            "label_window_end": outcome["event_at"].isoformat(),
                            "label_value": lab.label_value,
                            "label_source": lab.label_source,
                            "label_quality": lab.label_quality,
                            "features_json": fv.to_json(),
                            "feature_events": {
                                k: v.isoformat() for k, v in fv.events.items()
                            },
                            "feature_schema_version": FEATURE_SCHEMA_VERSION,
                            "source_run_ids": [],
                            "source_max_event_at": (
                                fv.source_max_event_at.isoformat()
                                if fv.source_max_event_at
                                else None
                            ),
                            "dataset_version": dataset_version,
                            "cohort": cat,
                        }
                    )

        # Update running history with this outcome (becomes available after event)
        sid = winner
        supplier_total[sid] = supplier_total.get(sid, 0) + 1
        supplier_last[sid] = outcome["event_at"]
        ente_supplier[(ente, sid)] = ente_supplier.get((ente, sid), 0) + 1
        cat_supplier[(cat, sid)] = cat_supplier.get((cat, sid), 0) + 1
        ente_total[ente] = ente_total.get(ente, 0) + 1
        cat_total[cat] = cat_total.get(cat, 0) + 1
        suppliers_at_ente.setdefault(ente, set()).add(sid)
        suppliers_in_cat.setdefault(cat, set()).add(sid)

    leak_report = audit_examples(examples)
    if not leak_report.ok:
        assert_no_leakage(examples)

    blockers: list[str] = []
    if len(examples) < 1000:
        blockers.append(f"n_examples={len(examples)} < 1000")
    n_pos = sum(1 for e in examples if e["label_value"] == 1)
    if n_pos < 100:
        blockers.append(f"n_positives={n_pos} < 100")

    return DatasetBuildResult(
        run_id=run_id,
        target_name=target,
        dataset_version=dataset_version,
        examples=examples,
        n_rejected_invalid_neg=rejected,
        coverage={"n_outcome_contracts": len(rows), "n_examples": len(examples)},
        leakage=leak_report.to_dict(),
        blockers=blockers,
        status="built" if examples else "empty",
    )


def build_discount_dataset(
    pairs: Sequence[dict[str, Any]],
    *,
    dataset_version: str = "p3_v1",
) -> DatasetBuildResult:
    """P3: pairs must include estimated+outcome with semantics.

    Each pair: {
      estimated_value, outcome_value, estimated_value_semantics,
      outcome_value_semantics, same_process, event_at, entity_id,
      modality_code?, hist_discounts?
    }
    """
    target = "winning_discount_p3"
    run_id = f"ds_{target}_{uuid.uuid4().hex[:12]}"
    examples: list[dict[str, Any]] = []
    rejected = 0
    blocks: dict[str, int] = {}

    for i, pair in enumerate(pairs):
        disc, meta = winning_discount(
            estimated_value=pair.get("estimated_value"),
            outcome_value=pair.get("outcome_value"),
            estimated_value_semantics=pair.get("estimated_value_semantics"),
            outcome_value_semantics=pair.get("outcome_value_semantics"),
            same_process=bool(pair.get("same_process", True)),
        )
        if disc is None:
            rejected += 1
            blocks[meta.get("block", "unknown")] = (
                blocks.get(meta.get("block", "unknown"), 0) + 1
            )
            continue
        event_at = pair.get("event_at")
        if isinstance(event_at, str):
            event_at = datetime.fromisoformat(event_at.replace("Z", "+00:00"))
        if not isinstance(event_at, datetime):
            rejected += 1
            continue
        as_of = _utc(event_at) - timedelta(days=1)
        hist = pair.get("hist_discounts") or []
        # hist list of (dt, discount)
        hist_t: list[tuple[datetime, float]] = []
        for h in hist:
            if isinstance(h, (list, tuple)) and len(h) == 2:
                d0, v0 = h
                if isinstance(d0, str):
                    d0 = datetime.fromisoformat(d0.replace("Z", "+00:00"))
                hist_t.append((_utc(d0), float(v0)))
        import math

        est = float(pair["estimated_value"])
        fv = build_discount_features(
            as_of=as_of,
            hist_discounts=hist_t,
            modality_code=float(pair.get("modality_code") or 0),
            log_estimated_value=math.log1p(est),
        )
        if validate_feature_cutoff(fv, as_of):
            rejected += 1
            continue
        eid = _example_id(target, str(pair.get("procurement_id") or i), as_of.isoformat())
        examples.append(
            {
                "example_id": eid,
                "target_name": target,
                "entity_id": pair.get("entity_id"),
                "procurement_id": pair.get("procurement_id"),
                "supplier_id": pair.get("supplier_id"),
                "as_of_at": as_of.isoformat(),
                "prediction_horizon": "outcome",
                "label_window_start": as_of.isoformat(),
                "label_window_end": _utc(event_at).isoformat(),
                "label_value": float(disc),
                "label_source": "estimated_outcome_join",
                "label_quality": "ok",
                "features_json": fv.to_json(),
                "feature_events": {k: v.isoformat() for k, v in fv.events.items()},
                "feature_schema_version": FEATURE_SCHEMA_VERSION,
                "source_run_ids": [],
                "source_max_event_at": (
                    fv.source_max_event_at.isoformat()
                    if fv.source_max_event_at
                    else None
                ),
                "dataset_version": dataset_version,
                "estimated_value_semantics": meta["estimated_value_semantics"],
                "outcome_value_semantics": meta["outcome_value_semantics"],
            }
        )

    leak_report = audit_examples(examples)
    if examples and not leak_report.ok:
        assert_no_leakage(examples)

    blockers: list[str] = []
    if len(examples) < 1000:
        blockers.append(
            f"n_valid_discount_pairs={len(examples)} < 1000 — DATA_BLOCKED for P3"
        )
    if rejected and not examples:
        blockers.append(f"All pairs rejected: {blocks}")

    return DatasetBuildResult(
        run_id=run_id,
        target_name=target,
        dataset_version=dataset_version,
        examples=examples,
        n_rejected_invalid_neg=rejected,
        coverage={"reject_reasons": blocks, "n_input_pairs": len(pairs)},
        leakage=leak_report.to_dict(),
        blockers=blockers,
        status="built" if examples else "data_blocked",
    )


def examples_to_matrix(
    examples: Sequence[dict[str, Any]],
) -> tuple[list[str], list[list[float]], list[float], list[datetime]]:
    """Convert examples to feature matrix with stable column order."""
    keys: list[str] = sorted(
        {
            k
            for ex in examples
            for k in (ex.get("features_json") or {})
            if not str(k).startswith("_")
        }
    )
    X: list[list[float]] = []
    y: list[float] = []
    as_ofs: list[datetime] = []
    for ex in examples:
        feats = ex.get("features_json") or {}
        X.append([float(feats.get(k, 0.0) or 0.0) for k in keys])
        y.append(float(ex["label_value"]))
        as_ofs.append(
            datetime.fromisoformat(str(ex["as_of_at"]).replace("Z", "+00:00"))
        )
    return keys, X, y, as_ofs
