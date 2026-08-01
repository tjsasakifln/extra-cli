"""Fail-closed leakage detection for point-in-time predictive examples."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


LEAKY_FEATURE_NAMES = frozenset(
    {
        "winner_id",
        "winner_cnpj",
        "fornecedor_vencedor",
        "valor_adjudicado",
        "valor_homologado",
        "outcome_value",
        "label",
        "y_true",
        "is_winner",
        "participou",
        "n_propostas_final",  # known only after session if not pre-published
    }
)


@dataclass
class LeakageFinding:
    code: str
    severity: str  # critical | high
    message: str
    example_id: str | None = None
    feature: str | None = None


@dataclass
class LeakageReport:
    ok: bool
    findings: list[LeakageFinding] = field(default_factory=list)
    n_examples_checked: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "n_examples_checked": self.n_examples_checked,
            "findings": [asdict(f) for f in self.findings],
        }


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def check_example(example: dict[str, Any]) -> list[LeakageFinding]:
    """Check a single PIT example dict for leakage."""
    findings: list[LeakageFinding] = []
    eid = example.get("example_id")
    as_of = _parse_dt(example.get("as_of_at"))
    if as_of is None:
        findings.append(
            LeakageFinding(
                code="missing_as_of",
                severity="critical",
                message="as_of_at missing or unparseable",
                example_id=eid,
            )
        )
        return findings

    source_max = _parse_dt(example.get("source_max_event_at"))
    if source_max is not None and source_max > as_of:
        findings.append(
            LeakageFinding(
                code="source_max_after_as_of",
                severity="critical",
                message=f"source_max_event_at {source_max} > as_of_at {as_of}",
                example_id=eid,
            )
        )

    features = example.get("features_json") or example.get("features") or {}
    if not isinstance(features, dict):
        findings.append(
            LeakageFinding(
                code="features_not_dict",
                severity="critical",
                message="features_json must be a dict",
                example_id=eid,
            )
        )
        return findings

    for fname in features:
        base = str(fname).split(".")[0]
        if base in LEAKY_FEATURE_NAMES or str(fname) in LEAKY_FEATURE_NAMES:
            findings.append(
                LeakageFinding(
                    code="leaky_feature_name",
                    severity="critical",
                    message=f"Feature name indicates post-outcome knowledge: {fname}",
                    example_id=eid,
                    feature=str(fname),
                )
            )

    # Feature event timestamps nested under features_meta
    meta = example.get("feature_events") or features.get("_feature_events") or {}
    if isinstance(meta, dict):
        for fname, event_at in meta.items():
            if str(fname).startswith("_"):
                continue
            edt = _parse_dt(event_at)
            if edt is not None and edt > as_of:
                findings.append(
                    LeakageFinding(
                        code="feature_event_after_as_of",
                        severity="critical",
                        message=f"Feature {fname} event_at {edt} > as_of {as_of}",
                        example_id=eid,
                        feature=str(fname),
                    )
                )

    # Label window must start after as_of for demand-style targets
    label_start = _parse_dt(example.get("label_window_start"))
    if label_start is not None and label_start < as_of:
        # equal is ok for some designs; strict before is leak if label includes past
        if label_start < as_of:
            # only flag if label uses pre-as_of events as positives incorrectly —
            # allow label_window_start == as_of
            pass
    if label_start is not None and label_start < as_of:
        findings.append(
            LeakageFinding(
                code="label_window_starts_before_as_of",
                severity="high",
                message=f"label_window_start {label_start} < as_of {as_of}",
                example_id=eid,
            )
        )

    # Target encoding fold leakage marker
    if features.get("_target_encoding_uses_future_folds"):
        findings.append(
            LeakageFinding(
                code="target_encoding_future_folds",
                severity="critical",
                message="Target encoding computed with future folds",
                example_id=eid,
            )
        )

    # Ingestion timestamp confused with event date
    if features.get("_used_ingested_at_as_event"):
        findings.append(
            LeakageFinding(
                code="ingestion_as_event",
                severity="critical",
                message="ingested_at used as event_at",
                example_id=eid,
            )
        )

    return findings


def audit_examples(examples: list[dict[str, Any]]) -> LeakageReport:
    findings: list[LeakageFinding] = []
    for ex in examples:
        findings.extend(check_example(ex))
    critical = [f for f in findings if f.severity == "critical"]
    return LeakageReport(
        ok=len(critical) == 0,
        findings=findings,
        n_examples_checked=len(examples),
    )


def assert_no_leakage(examples: list[dict[str, Any]]) -> LeakageReport:
    """Fail-closed: raise RuntimeError if critical leakage found."""
    report = audit_examples(examples)
    if not report.ok:
        crit = [f for f in report.findings if f.severity == "critical"]
        msgs = "; ".join(f"{f.code}:{f.message}" for f in crit[:5])
        raise RuntimeError(f"LEAKAGE_DETECTED ({len(crit)} critical): {msgs}")
    return report
