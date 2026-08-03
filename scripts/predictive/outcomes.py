"""Outcome reconciliation: join immutable predictions to post-window observed events.

Never rewrites predictions. Writes predictive_outcomes rows (or JSON ledger offline).

Demand negatives require coverage evidence — absence alone is never label 0.
P2A joins predictions to observed winners by procurement_id after as_of.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


@dataclass
class ResolvedOutcome:
    outcome_id: str
    prediction_id: str
    observed_at: str
    label_value: float | None
    outcome_source: str
    outcome_quality: str
    error_abs: float | None
    brier_component: float | None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def is_scorable(self) -> bool:
        """Only quality=ok with finite label contributes to Brier/drift."""
        return self.outcome_quality == "ok" and self.label_value is not None and self.brier_component is not None


def default_ledger_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / "artifacts" / "predictive" / "outcomes_ledger.jsonl"


def load_predictions_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def _score_components(prediction: dict[str, Any], label: float | None) -> tuple[float | None, float | None]:
    if label is None:
        return None, None
    score = prediction.get("probability")
    if score is None:
        score = prediction.get("score")
    if score is None:
        return None, None
    try:
        p = float(score)
        return abs(p - label), (p - label) ** 2
    except (TypeError, ValueError):
        return None, None


def coverage_ok_for_entity(
    *,
    entity_id: str,
    as_of: datetime,
    window_end: datetime,
    events: list[datetime],
    coverage_by_entity: dict[str, set[str]] | None = None,
    coverage_flag: bool | None = None,
) -> bool:
    """Evidence that the source was consulted for this ente in the label window.

    Explicit coverage map (YYYY-MM) wins. Else prediction-level flag. Else weak
    signal: any observed event for the ente within ±180d of as_of/window
    (source producing data nearby) — same weak rule as demand dataset builder.
    """
    if coverage_flag is True:
        return True
    if coverage_flag is False:
        return False
    if coverage_by_entity is not None:
        months = coverage_by_entity.get(entity_id, set())
        # Require coverage for as_of month or window-end month
        keys = {
            f"{as_of.year:04d}-{as_of.month:02d}",
            f"{window_end.year:04d}-{window_end.month:02d}",
        }
        return bool(months & keys)
    # Weak nearby activity signal (not inventing absence for never-seen entes)
    near = [e for e in events if abs((e - as_of).days) <= 180 or abs((e - window_end).days) <= 180]
    return len(near) > 0


def resolve_demand_prediction(
    prediction: dict[str, Any],
    events_by_entity: dict[str, list[datetime]],
    *,
    coverage_by_entity: dict[str, set[str]] | None = None,
) -> ResolvedOutcome | None:
    """Resolve a demand prediction against observed AEC events after as_of.

    - Positive: ≥1 AEC event in (as_of, as_of+horizon]
    - Negative: no event AND coverage evidence only
    - Without coverage and no event: refuse scoring (quality=rejected_invalid_negative,
      label_value=None) so absence is never turned into a silent 0 for metrics.
    """
    pred_id = prediction.get("prediction_id")
    if not pred_id:
        return None
    as_of = _parse_dt(prediction.get("as_of_at") or prediction.get("prediction_as_of"))
    if as_of is None:
        return None
    horizon = str(prediction.get("horizon") or prediction.get("prediction_horizon") or "30d")
    try:
        days = int(horizon.replace("d", "").split("_")[-1]) if "d" in horizon else 30
    except ValueError:
        days = 30

    window_end = as_of + timedelta(days=days)
    entity = str(prediction.get("entity_id") or "")
    all_events = events_by_entity.get(entity) or []
    positives = [e for e in all_events if as_of < e <= window_end]
    now = _utc_now()
    if now < window_end:
        return None  # not mature

    coverage_flag = prediction.get("coverage_ok")
    if coverage_flag is None:
        coverage_flag = (prediction.get("metadata") or {}).get("coverage_ok")
    if coverage_flag is not None:
        coverage_flag = bool(coverage_flag)

    cov = coverage_ok_for_entity(
        entity_id=entity,
        as_of=as_of,
        window_end=window_end,
        events=all_events,
        coverage_by_entity=coverage_by_entity,
        coverage_flag=coverage_flag,
    )

    if positives:
        label: float | None = 1.0
        quality = "ok"
        source = "observed_aec_event"
    elif cov:
        label = 0.0
        quality = "ok"
        source = "coverage_confirmed_absence"
    else:
        # Fail-closed: do not invent negative labels without coverage
        label = None
        quality = "rejected_invalid_negative"
        source = "insufficient_coverage"

    err, brier = _score_components(prediction, label)
    return ResolvedOutcome(
        outcome_id=f"out_{uuid.uuid4().hex[:16]}",
        prediction_id=str(pred_id),
        observed_at=now.isoformat(),
        label_value=label,
        outcome_source=source,
        outcome_quality=quality,
        error_abs=err,
        brier_component=brier,
        metadata={
            "n_events_in_window": len(positives),
            "window_end": window_end.isoformat(),
            "entity_id": entity,
            "horizon_days": days,
            "coverage_ok": cov,
            "scorable": quality == "ok" and label is not None,
        },
    )


def resolve_competitive_winner_prediction(
    prediction: dict[str, Any],
    winners_by_procurement: dict[str, dict[str, Any]],
) -> ResolvedOutcome | None:
    """Resolve P2A: supplier predicted vs observed winner for procurement_id.

    Requires observed outcome after as_of. Label:
    - 1 if predicted supplier_id is the observed winner
    - 0 if different observed winner (supplier was in pre-result candidate set
      by construction of the prediction)
    - None / not mature if procurement outcome not yet observed
    """
    pred_id = prediction.get("prediction_id")
    if not pred_id:
        return None
    target = str(prediction.get("target_name") or "")
    if target != "competitive_winner_p2a":
        return None
    procurement_id = str(prediction.get("procurement_id") or "").strip()
    supplier_id = str(prediction.get("supplier_id") or "").strip()
    if not procurement_id or not supplier_id:
        return ResolvedOutcome(
            outcome_id=f"out_{uuid.uuid4().hex[:16]}",
            prediction_id=str(pred_id),
            observed_at=_utc_now().isoformat(),
            label_value=None,
            outcome_source="missing_procurement_or_supplier",
            outcome_quality="rejected_invalid",
            error_abs=None,
            brier_component=None,
            metadata={"procurement_id": procurement_id, "supplier_id": supplier_id},
        )

    as_of = _parse_dt(prediction.get("as_of_at") or prediction.get("prediction_as_of"))
    outcome = winners_by_procurement.get(procurement_id)
    if outcome is None:
        return None  # not observed yet — immature

    winner_id = str(outcome.get("winner_id") or outcome.get("supplier_id") or "").strip()
    event_at = _parse_dt(outcome.get("event_at") or outcome.get("observed_at"))
    if as_of is not None and event_at is not None and event_at <= as_of:
        # Outcome timestamp not after as_of — invalid / leakage risk
        return ResolvedOutcome(
            outcome_id=f"out_{uuid.uuid4().hex[:16]}",
            prediction_id=str(pred_id),
            observed_at=_utc_now().isoformat(),
            label_value=None,
            outcome_source="outcome_not_after_as_of",
            outcome_quality="rejected_invalid",
            error_abs=None,
            brier_component=None,
            metadata={
                "procurement_id": procurement_id,
                "as_of_at": as_of.isoformat(),
                "event_at": event_at.isoformat() if event_at else None,
            },
        )

    if not winner_id:
        return None

    label = 1.0 if supplier_id == winner_id else 0.0
    err, brier = _score_components(prediction, label)
    return ResolvedOutcome(
        outcome_id=f"out_{uuid.uuid4().hex[:16]}",
        prediction_id=str(pred_id),
        observed_at=_utc_now().isoformat(),
        label_value=label,
        outcome_source="observed_winner",
        outcome_quality="ok",
        error_abs=err,
        brier_component=brier,
        metadata={
            "procurement_id": procurement_id,
            "supplier_id": supplier_id,
            "winner_id": winner_id,
            "event_at": event_at.isoformat() if event_at else None,
            "scorable": True,
        },
    )


def build_winners_index(
    contracts: Sequence[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Map procurement/contrato_id → observed winner (latest event wins)."""
    from scripts.predictive.dataset import _contract_event_at
    from scripts.predictive.labels import is_aec_object

    index: dict[str, dict[str, Any]] = {}
    for row in contracts:
        obj = row.get("objeto_contrato") or row.get("objeto") or ""
        if obj and not is_aec_object(str(obj)):
            # still allow explicit non-filter if already AEC sample
            pass
        pid = str(row.get("contrato_id") or row.get("procurement_id") or row.get("id") or "").strip()
        supplier = str(row.get("fornecedor_cnpj") or row.get("supplier_id") or "").strip()
        if not pid or not supplier:
            continue
        evt = _contract_event_at(row)
        if evt is None:
            continue
        prev = index.get(pid)
        if prev is None or (prev.get("event_at") and evt > prev["event_at"]):
            index[pid] = {
                "winner_id": supplier,
                "supplier_id": supplier,
                "event_at": evt,
                "entity_id": str(row.get("orgao_cnpj") or row.get("entity_id") or ""),
            }
    return index


def resolve_predictions(
    predictions: Sequence[dict[str, Any]],
    *,
    contracts: Sequence[dict[str, Any]] | None = None,
    events_by_entity: dict[str, list[datetime]] | None = None,
    coverage_by_entity: dict[str, set[str]] | None = None,
    winners_by_procurement: dict[str, dict[str, Any]] | None = None,
) -> list[ResolvedOutcome]:
    """Resolve mature predictions for demand and competitive_winner_p2a."""
    from scripts.predictive.dataset import _contract_event_at
    from scripts.predictive.labels import is_aec_object

    if events_by_entity is None:
        events_by_entity = {}
        for row in contracts or []:
            ente = str(row.get("orgao_cnpj") or row.get("entity_id") or "").strip()
            if not ente:
                continue
            obj = row.get("objeto_contrato") or row.get("objeto") or ""
            if obj and not is_aec_object(str(obj)):
                continue
            evt = _contract_event_at(row)
            if evt is None:
                continue
            events_by_entity.setdefault(ente, []).append(evt)

    if winners_by_procurement is None and contracts is not None:
        winners_by_procurement = build_winners_index(contracts)
    elif winners_by_procurement is None:
        winners_by_procurement = {}

    resolved: list[ResolvedOutcome] = []
    for pred in predictions:
        target = str(pred.get("target_name") or "")
        if target.startswith("demand_"):
            out = resolve_demand_prediction(
                pred,
                events_by_entity,
                coverage_by_entity=coverage_by_entity,
            )
            if out is not None:
                resolved.append(out)
        elif target == "competitive_winner_p2a":
            out = resolve_competitive_winner_prediction(pred, winners_by_procurement)
            if out is not None:
                resolved.append(out)
        # P3 remains DATA_BLOCKED at claim level until estimated↔outcome pairs exist
    return resolved


def persist_outcomes(
    outcomes: Sequence[ResolvedOutcome],
    *,
    ledger_path: Path | None = None,
    dsn: str | None = None,
) -> dict[str, Any]:
    """Append to JSONL ledger; optionally insert into PG if DSN and table exist.

    Scorable outcomes (quality=ok + label) and rejected records are both
    persisted for audit; drift metrics should filter is_scorable.
    """
    path = ledger_path or default_ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids: set[str] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                existing_ids.add(json.loads(line).get("prediction_id", ""))
            except json.JSONDecodeError:
                continue

    written = 0
    skipped = 0
    n_scorable = 0
    n_rejected = 0
    with path.open("a", encoding="utf-8") as fh:
        for o in outcomes:
            if o.prediction_id in existing_ids:
                skipped += 1
                continue
            fh.write(json.dumps(o.to_dict(), ensure_ascii=False, default=str) + "\n")
            written += 1
            existing_ids.add(o.prediction_id)
            if o.is_scorable:
                n_scorable += 1
            elif o.outcome_quality.startswith("rejected"):
                n_rejected += 1

    pg_written = 0
    if dsn:
        try:
            import psycopg2

            conn = psycopg2.connect(dsn)
            try:
                with conn.cursor() as cur:
                    for o in outcomes:
                        cur.execute(
                            """
                            INSERT INTO predictive_outcomes (
                              outcome_id, prediction_id, observed_at, label_value,
                              outcome_source, outcome_quality, error_abs, brier_component,
                              metadata_json
                            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                            ON CONFLICT (prediction_id) DO NOTHING
                            """,
                            (
                                o.outcome_id,
                                o.prediction_id,
                                o.observed_at,
                                o.label_value,
                                o.outcome_source,
                                o.outcome_quality,
                                o.error_abs,
                                o.brier_component,
                                json.dumps(o.metadata),
                            ),
                        )
                        pg_written += cur.rowcount
                conn.commit()
            finally:
                conn.close()
        except Exception as exc:
            return {
                "ledger_path": str(path),
                "written": written,
                "skipped_existing": skipped,
                "n_scorable": n_scorable,
                "n_rejected_invalid_negative": n_rejected,
                "pg_written": 0,
                "pg_error": str(exc),
            }

    return {
        "ledger_path": str(path),
        "written": written,
        "skipped_existing": skipped,
        "n_scorable": n_scorable,
        "n_rejected_invalid_negative": n_rejected,
        "pg_written": pg_written,
        "total_resolved_this_run": len(outcomes),
    }
