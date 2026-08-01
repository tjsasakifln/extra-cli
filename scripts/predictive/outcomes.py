"""Outcome reconciliation: join immutable predictions to post-window observed events.

Never rewrites predictions. Writes predictive_outcomes rows (or JSON ledger offline).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
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


def resolve_demand_prediction(
    prediction: dict[str, Any],
    events_by_entity: dict[str, list[datetime]],
) -> ResolvedOutcome | None:
    """Resolve a demand prediction against observed AEC events after as_of."""
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
    from datetime import timedelta

    window_end = as_of + timedelta(days=days)
    entity = str(prediction.get("entity_id") or "")
    events = events_by_entity.get(entity) or []
    positives = [e for e in events if as_of < e <= window_end]
    # Only resolve after window has fully elapsed
    now = _utc_now()
    if now < window_end:
        return None  # not mature
    label = 1.0 if positives else 0.0
    score = prediction.get("probability")
    if score is None:
        score = prediction.get("score")
    brier = None
    err = None
    if score is not None:
        try:
            p = float(score)
            brier = (p - label) ** 2
            err = abs(p - label)
        except (TypeError, ValueError):
            pass
    return ResolvedOutcome(
        outcome_id=f"out_{uuid.uuid4().hex[:16]}",
        prediction_id=str(pred_id),
        observed_at=now.isoformat(),
        label_value=label,
        outcome_source="observed_aec_event" if positives else "coverage_window_elapsed",
        outcome_quality="ok",
        error_abs=err,
        brier_component=brier,
        metadata={
            "n_events_in_window": len(positives),
            "window_end": window_end.isoformat(),
            "entity_id": entity,
            "horizon_days": days,
        },
    )


def resolve_predictions(
    predictions: Sequence[dict[str, Any]],
    *,
    contracts: Sequence[dict[str, Any]] | None = None,
    events_by_entity: dict[str, list[datetime]] | None = None,
) -> list[ResolvedOutcome]:
    """Resolve mature predictions. Demand uses events; other targets need specific joins."""
    from scripts.predictive.dataset import _contract_event_at
    from scripts.predictive.labels import is_aec_object

    if events_by_entity is None:
        events_by_entity = {}
        for row in contracts or []:
            ente = str(row.get("orgao_cnpj") or row.get("entity_id") or "").strip()
            if not ente:
                continue
            obj = row.get("objeto_contrato") or row.get("objeto") or ""
            if not is_aec_object(str(obj)):
                continue
            evt = _contract_event_at(row)
            if evt is None:
                continue
            events_by_entity.setdefault(ente, []).append(evt)

    resolved: list[ResolvedOutcome] = []
    for pred in predictions:
        target = str(pred.get("target_name") or "")
        if target.startswith("demand_"):
            out = resolve_demand_prediction(pred, events_by_entity)
            if out is not None:
                resolved.append(out)
        # P2A/P3 resolution requires procurement outcome joins — skip if incomplete
    return resolved


def persist_outcomes(
    outcomes: Sequence[ResolvedOutcome],
    *,
    ledger_path: Path | None = None,
    dsn: str | None = None,
) -> dict[str, Any]:
    """Append to JSONL ledger; optionally insert into PG if DSN and table exist."""
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
    with path.open("a", encoding="utf-8") as fh:
        for o in outcomes:
            if o.prediction_id in existing_ids:
                skipped += 1
                continue
            fh.write(json.dumps(o.to_dict(), ensure_ascii=False, default=str) + "\n")
            written += 1
            existing_ids.add(o.prediction_id)

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
                "pg_written": 0,
                "pg_error": str(exc),
            }

    return {
        "ledger_path": str(path),
        "written": written,
        "skipped_existing": skipped,
        "pg_written": pg_written,
        "total_resolved_this_run": len(outcomes),
    }
