"""#261 #331 #332 #333 — consume #346 ranking; promote or defer, no adapters.

Reads the existing AlertaLicitação ranking snapshot and records one
decision per VALIDATE source. Does not start adapter, coverage or live ops.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from scripts.coverage.alerta_miss_ranking import (
    HISTORICAL_SEEDS,
    AdapterRank,
    ReconciliationReport,
    classify_historical_seeds,
    run_measurement,
)

Decision = Literal["PROMOTE", "DEFER"]

# P1 requires measured material unique recall. A single seed row is not enough.
MATERIAL_UNIQUE_RECALL = 3.0

ISSUE_SOURCES: dict[int, dict[str, Any]] = {
    261: {"adapter_keys": ("bll",), "label": "BLL", "seed_identity": "BLL-261"},
    331: {"adapter_keys": ("bnc",), "label": "BNC", "seed_identity": "BNC-331"},
    332: {"adapter_keys": ("dou", "diario_oficial"), "label": "DOU", "seed_identity": "DOU-332"},
    333: {
        "adapter_keys": ("portal_proprio", "portais_municipais", "transparencia"),
        "label": "portais_municipais",
        "seed_identity": "MUN-333",
    },
}

DEFAULT_WINDOW_START = "2026-08-01"
DEFAULT_WINDOW_END = "2026-08-12"
DEFAULT_REGISTERED = frozenset({"pncp", "ciga"})


@dataclass(frozen=True)
class SourceDecision:
    issue: int
    source: str
    decision: Decision
    reason: str
    adapter_key: str | None
    unique_recall: float
    implementation_effort: float
    score: float
    n_misses: int
    seed_identity: str
    seed_evidence: str
    snapshot_ref: str | None
    ranking_hash: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_ranking(
    alerta_path: Path,
    extra_path: Path,
    *,
    window_start: str = DEFAULT_WINDOW_START,
    window_end: str = DEFAULT_WINDOW_END,
    registered_sources: frozenset[str] | None = None,
) -> ReconciliationReport:
    """Consume the shipped #346 measurement. Does not implement adapters."""
    return run_measurement(
        alerta_path.read_bytes(),
        extra_path.read_bytes(),
        alerta_filename=alerta_path.name,
        extra_filename=extra_path.name,
        window_start=window_start,
        window_end=window_end,
        registered_sources=registered_sources or DEFAULT_REGISTERED,
    )


def _rank_for_issue(report: ReconciliationReport, issue: int) -> AdapterRank | None:
    keys = set(ISSUE_SOURCES[issue]["adapter_keys"])
    matches = [rank for rank in report.ranking if rank.adapter_key in keys]
    if not matches:
        return None
    return sorted(matches, key=lambda rank: (-rank.score, -rank.n_misses, rank.adapter_key))[0]


def _seed_record(report: ReconciliationReport, issue: int) -> dict[str, Any]:
    identity = str(ISSUE_SOURCES[issue]["seed_identity"])
    for record in classify_historical_seeds(report):
        if str(record.get("identity")) == identity or int(record.get("issue") or 0) == issue:
            return record
    for seed in HISTORICAL_SEEDS:
        if int(seed["issue"]) == issue:
            return {**seed, "evidence": "seed preserved; not present in this ranking window"}
    raise KeyError(issue)


def decide_promotion(
    *,
    issue: int,
    rank: AdapterRank | None,
    top: AdapterRank | None,
    seed: dict[str, Any],
    ranking_hash: str,
) -> SourceDecision:
    """Promote only the highest material recall-per-effort source."""
    meta = ISSUE_SOURCES[issue]
    seed_evidence = str(seed.get("evidence") or seed.get("identity") or "")
    if rank is None:
        return SourceDecision(
            issue=issue,
            source=str(meta["label"]),
            decision="DEFER",
            reason="no commercially ranked row for this source on the #346 snapshot",
            adapter_key=None,
            unique_recall=0.0,
            implementation_effort=0.0,
            score=0.0,
            n_misses=0,
            seed_identity=str(meta["seed_identity"]),
            seed_evidence=seed_evidence,
            snapshot_ref=None,
            ranking_hash=ranking_hash,
        )
    if rank.expected_unique_recall_gain < MATERIAL_UNIQUE_RECALL:
        return SourceDecision(
            issue=issue,
            source=str(meta["label"]),
            decision="DEFER",
            reason=(
                "unique recall "
                f"{rank.expected_unique_recall_gain} < material threshold "
                f"{MATERIAL_UNIQUE_RECALL}; seed evidence preserved"
            ),
            adapter_key=rank.adapter_key,
            unique_recall=rank.expected_unique_recall_gain,
            implementation_effort=rank.implementation_effort,
            score=rank.score,
            n_misses=rank.n_misses,
            seed_identity=str(meta["seed_identity"]),
            seed_evidence=seed_evidence,
            snapshot_ref=rank.snapshot_ref,
            ranking_hash=ranking_hash,
        )
    if top is None or rank.adapter_key != top.adapter_key:
        return SourceDecision(
            issue=issue,
            source=str(meta["label"]),
            decision="DEFER",
            reason="not the highest expected commercially relevant recall per unit of effort",
            adapter_key=rank.adapter_key,
            unique_recall=rank.expected_unique_recall_gain,
            implementation_effort=rank.implementation_effort,
            score=rank.score,
            n_misses=rank.n_misses,
            seed_identity=str(meta["seed_identity"]),
            seed_evidence=seed_evidence,
            snapshot_ref=rank.snapshot_ref,
            ranking_hash=ranking_hash,
        )
    return SourceDecision(
        issue=issue,
        source=str(meta["label"]),
        decision="PROMOTE",
        reason="highest measured commercially relevant recall per unit of effort and material gain",
        adapter_key=rank.adapter_key,
        unique_recall=rank.expected_unique_recall_gain,
        implementation_effort=rank.implementation_effort,
        score=rank.score,
        n_misses=rank.n_misses,
        seed_identity=str(meta["seed_identity"]),
        seed_evidence=seed_evidence,
        snapshot_ref=rank.snapshot_ref,
        ranking_hash=ranking_hash,
    )


def decide_all(report: ReconciliationReport, issues: tuple[int, ...] = (261, 331, 332, 333)) -> tuple[SourceDecision, ...]:
    top = report.ranking[0] if report.ranking else None
    out: list[SourceDecision] = []
    for issue in issues:
        out.append(
            decide_promotion(
                issue=issue,
                rank=_rank_for_issue(report, issue),
                top=top,
                seed=_seed_record(report, issue),
                ranking_hash=report.report_hash,
            )
        )
    return tuple(out)


def decisions_payload(report: ReconciliationReport, decisions: tuple[SourceDecision, ...]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "consumes": "#346",
        "adapter_code_started": False,
        "coverage_engineering_started": False,
        "live_ops_started": False,
        "ranking_hash": report.report_hash,
        "import_id": report.import_id,
        "snapshot_window": [report.window_start, report.window_end],
        "decisions": [item.as_dict() for item in decisions],
        "historical_seeds": classify_historical_seeds(report),
        "ranking": [rank.as_dict() for rank in report.ranking],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Promote or defer VALIDATE sources from the #346 ranking")
    parser.add_argument("--alerta", required=True)
    parser.add_argument("--extra", required=True)
    parser.add_argument("--window-start", default=DEFAULT_WINDOW_START)
    parser.add_argument("--window-end", default=DEFAULT_WINDOW_END)
    parser.add_argument("--issues", default="261,331,332,333")
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)
    issues = tuple(int(part) for part in args.issues.split(",") if part.strip())
    report = load_ranking(
        Path(args.alerta),
        Path(args.extra),
        window_start=args.window_start,
        window_end=args.window_end,
    )
    decisions = decide_all(report, issues)
    payload = decisions_payload(report, decisions)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
