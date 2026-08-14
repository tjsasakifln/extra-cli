"""Versioned golden-dataset registry for coverage misses and factual corrections.

Public truth-plane cases move candidate → adjudicated → golden. Replay never
requires client, action, or outcome fields. Material regressions block promotion.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Literal

SCHEMA_VERSION = 1
Stage = Literal["candidate", "adjudicated", "golden"]
STAGE_CANDIDATE: Stage = "candidate"
STAGE_ADJUDICATED: Stage = "adjudicated"
STAGE_GOLDEN: Stage = "golden"
FORBIDDEN_AUTHORITY_FIELDS = frozenset({"client", "action", "outcome", "crm", "label_model"})
PII_KEYS = frozenset({"cpf", "email", "telefone", "phone", "nome", "nome_pessoa", "rg", "endereco", "address"})
CRITICAL_STAGES = (
    "source_miss",
    "pagination_miss",
    "freshness_miss",
    "document_ocr",
    "dedup_conflict",
    "identity_conflict",
    "retificacao",
    "factual_extraction",
    "negative_zero",
    "negative_revoked",
)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_payload(obj: Any) -> str:
    return hashlib.sha256(_canonical_json(obj).encode("utf-8")).hexdigest()


def tokenize_pii(value: str) -> str:
    """Deterministic tokenization — never store raw PII in the golden case."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"pii_{digest}"


def _tokenize_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if key.lower() in PII_KEYS and isinstance(value, str) and value:
            out[key] = tokenize_pii(value)
        else:
            out[key] = value
    return out


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    stage: Stage
    public_stage: str
    origin: str
    adjudicator: str | None
    restriction: str
    snapshot_at: str
    published_at: str
    split: Literal["train", "eval", "holdout"]
    payload: dict[str, Any]
    expected: dict[str, Any]
    license: str
    content_hash: str
    version: str
    pii_tokenized: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GoldenRegistry:
    version: str
    cases: dict[str, GoldenCase] = field(default_factory=dict)

    def list_cases(self) -> list[dict[str, Any]]:
        rows = []
        for case in sorted(self.cases.values(), key=lambda c: c.case_id):
            rows.append(
                {
                    "case_id": case.case_id,
                    "version": case.version,
                    "hash": case.content_hash,
                    "origin": case.origin,
                    "adjudicator": case.adjudicator,
                    "restriction": case.restriction,
                    "stage": case.stage,
                    "public_stage": case.public_stage,
                    "split": case.split,
                }
            )
        return rows


def _reject_authority_fields(payload: dict[str, Any]) -> None:
    banned = FORBIDDEN_AUTHORITY_FIELDS.intersection(payload)
    if banned:
        raise ValueError(f"client/action/outcome fields are not authority: {sorted(banned)}")


def assign_split(published_at: str, *, cutoff: str) -> Literal["train", "eval", "holdout"]:
    """Temporal split. Items on/after cutoff never leak into train."""
    pub = date.fromisoformat(published_at[:10])
    cut = date.fromisoformat(cutoff[:10])
    if pub < cut:
        return "train"
    if pub == cut:
        return "eval"
    return "holdout"


def ingest_candidate(
    *,
    case_id: str,
    public_stage: str,
    origin: str,
    snapshot_at: str,
    published_at: str,
    payload: dict[str, Any],
    expected: dict[str, Any],
    restriction: str = "public-authorized",
    license_name: str = "public-domain-or-authorized",
    split_cutoff: str,
    version: str,
) -> GoldenCase:
    if public_stage not in CRITICAL_STAGES:
        raise ValueError(f"unknown public stage: {public_stage}")
    _reject_authority_fields(payload)
    _reject_authority_fields(expected)
    safe_payload = _tokenize_mapping(payload)
    safe_expected = _tokenize_mapping(expected)
    body = {
        "case_id": case_id,
        "public_stage": public_stage,
        "origin": origin,
        "payload": safe_payload,
        "expected": safe_expected,
        "published_at": published_at,
    }
    return GoldenCase(
        case_id=case_id,
        stage=STAGE_CANDIDATE,
        public_stage=public_stage,
        origin=origin,
        adjudicator=None,
        restriction=restriction,
        snapshot_at=snapshot_at,
        published_at=published_at,
        split=assign_split(published_at, cutoff=split_cutoff),
        payload=safe_payload,
        expected=safe_expected,
        license=license_name,
        content_hash=sha256_payload(body),
        version=version,
        pii_tokenized=True,
    )


def adjudicate(case: GoldenCase, *, adjudicator: str, expected: dict[str, Any] | None = None) -> GoldenCase:
    if not adjudicator.strip():
        raise ValueError("adjudicator is required")
    _reject_authority_fields(expected or {})
    new_expected = _tokenize_mapping(expected) if expected is not None else dict(case.expected)
    body = {
        "case_id": case.case_id,
        "public_stage": case.public_stage,
        "origin": case.origin,
        "payload": case.payload,
        "expected": new_expected,
        "published_at": case.published_at,
    }
    return GoldenCase(
        case_id=case.case_id,
        stage=STAGE_ADJUDICATED,
        public_stage=case.public_stage,
        origin=case.origin,
        adjudicator=adjudicator,
        restriction=case.restriction,
        snapshot_at=case.snapshot_at,
        published_at=case.published_at,
        split=case.split,
        payload=dict(case.payload),
        expected=new_expected,
        license=case.license,
        content_hash=sha256_payload(body),
        version=case.version,
        pii_tokenized=case.pii_tokenized,
    )


def promote_to_golden(case: GoldenCase) -> GoldenCase:
    if case.stage != STAGE_ADJUDICATED:
        raise ValueError("only adjudicated cases can become golden")
    if not case.adjudicator:
        raise ValueError("golden case requires an adjudicator")
    return GoldenCase(
        case_id=case.case_id,
        stage=STAGE_GOLDEN,
        public_stage=case.public_stage,
        origin=case.origin,
        adjudicator=case.adjudicator,
        restriction=case.restriction,
        snapshot_at=case.snapshot_at,
        published_at=case.published_at,
        split=case.split,
        payload=dict(case.payload),
        expected=dict(case.expected),
        license=case.license,
        content_hash=case.content_hash,
        version=case.version,
        pii_tokenized=case.pii_tokenized,
    )


def replay(case: GoldenCase, actual: dict[str, Any]) -> dict[str, Any]:
    """Compare actual replay against adjudicated expected. No client fields needed."""
    _reject_authority_fields(actual)
    missing = [k for k in case.expected if actual.get(k) != case.expected[k]]
    return {
        "case_id": case.case_id,
        "ok": not missing,
        "mismatched": missing,
        "stage": case.public_stage,
        "split": case.split,
    }


def evaluate_benchmark(
    cases: list[GoldenCase],
    actual_by_id: dict[str, dict[str, Any]],
    *,
    baseline_rate: float | None = None,
) -> dict[str, Any]:
    """Emit baseline / delta / interval-ready rates per stage and split."""
    by_stage: dict[str, dict[str, int]] = {}
    by_split: dict[str, dict[str, int]] = {}
    regressions: list[str] = []
    for case in cases:
        actual = actual_by_id.get(case.case_id)
        if actual is None:
            passed = False
            mismatches = list(case.expected)
        else:
            result = replay(case, actual)
            passed = bool(result["ok"])
            mismatches = list(result["mismatched"])
        bucket = by_stage.setdefault(case.public_stage, {"pass": 0, "total": 0})
        bucket["total"] += 1
        if passed:
            bucket["pass"] += 1
        else:
            regressions.append(case.case_id)
        split_b = by_split.setdefault(case.split, {"pass": 0, "total": 0})
        split_b["total"] += 1
        if passed:
            split_b["pass"] += 1
        if mismatches:
            continue
    rates = {stage: (vals["pass"] / vals["total"] if vals["total"] else None) for stage, vals in by_stage.items()}
    overall_total = sum(v["total"] for v in by_stage.values())
    overall_pass = sum(v["pass"] for v in by_stage.values())
    overall = (overall_pass / overall_total) if overall_total else None
    delta = None if baseline_rate is None or overall is None else overall - baseline_rate
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "overall_rate": overall,
        "baseline_rate": baseline_rate,
        "delta": delta,
        "by_stage": by_stage,
        "by_split": by_split,
        "rates": rates,
        "regressions": regressions,
        "n": overall_total,
    }


def promotion_blocked(benchmark: dict[str, Any], *, material_drop: float = 0.02) -> bool:
    """Material regression blocks promotion. No silent exception path."""
    if benchmark.get("overall_rate") is None:
        return True
    delta = benchmark.get("delta")
    if delta is not None and delta < -abs(material_drop):
        return True
    if benchmark.get("regressions"):
        return True
    return False


def register_miss(
    registry: GoldenRegistry,
    *,
    case_id: str,
    public_stage: str,
    origin: str,
    snapshot_at: str,
    published_at: str,
    payload: dict[str, Any],
    expected: dict[str, Any],
    split_cutoff: str,
    adjudicator: str,
) -> GoldenCase:
    """Adjudicated miss/correction becomes a traceable golden candidate then case."""
    candidate = ingest_candidate(
        case_id=case_id,
        public_stage=public_stage,
        origin=origin,
        snapshot_at=snapshot_at,
        published_at=published_at,
        payload=payload,
        expected=expected,
        split_cutoff=split_cutoff,
        version=registry.version,
    )
    adjudicated = adjudicate(candidate, adjudicator=adjudicator)
    golden = promote_to_golden(adjudicated)
    registry.cases[golden.case_id] = golden
    return golden
