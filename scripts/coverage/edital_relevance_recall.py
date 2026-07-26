#!/usr/bin/env python3
"""Fail-closed evaluator for DOD §8.4 relevance recall on gold corpus.

Canonical command::

    python -m scripts.coverage.edital_relevance_recall evaluate \\
      --corpus evals/edital_relevance/locked_holdout.jsonl \\
      --manifest evals/edital_relevance/locked_holdout-manifest.json \\
      --profile config/client_profiles/extra.yaml \\
      --output /tmp/edital-relevance-recall-result.json

Exit 0 only when integrity gates + global relevance recall ≥ 95% all hold.
UNDECIDABLE is excluded from the recall denominator and must never be
silently converted to IRRELEVANT.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ops.sector_classifier import (  # noqa: E402
    RULE_VERSION,
    classify_object,
    is_engineering_for_e,
    load_profile,
)

SCHEMA_VERSION = "edital-relevance-corpus/1.0.0"
EVALUATOR_VERSION = "edital-relevance-recall/1.0.0"
RECALL_THRESHOLD = 0.95
MIN_RELEVANT_HOLDOUT = 100
MIN_PER_REQUIRED_STRATUM = 10
REQUIRED_STRATA_KEYS = (
    "source:pncp",
    "source:sc_compras",
    "source:ciga",
    "municipio_bucket:grande",
    "municipio_bucket:medio",
    "municipio_bucket:pequeno",
    "natureza:admin_direta",
    "natureza:admin_indireta",
)
FINAL_LABELS = frozenset({"RELEVANT", "IRRELEVANT", "UNDECIDABLE"})
FORBIDDEN_SELECTION_PROXIES = frozenset(
    {
        "system_class",
        "classifier_output",
        "db_count",
        "success_zero",
        "operational_queue",
        "presence_in_db",
        "score_existing",
    }
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def profile_hash(path: Path) -> str:
    return sha256_file(path) if path.is_file() else "missing-profile"


def git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=PROJECT_ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
        return out.strip()
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return "unknown"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: line {i} invalid JSON: {exc}") from exc
        if not isinstance(obj, dict):
            raise ValueError(f"{path}: line {i} is not an object")
        rows.append(obj)
    return rows


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n <= 0:
        return (0.0, 0.0)
    phat = successes / n
    denom = 1.0 + z * z / n
    centre = phat + z * z / (2.0 * n)
    margin = z * math.sqrt((phat * (1.0 - phat) + z * z / (4.0 * n)) / n)
    low = max(0.0, (centre - margin) / denom)
    high = min(1.0, (centre + margin) / denom)
    return (low, high)


def predicted_relevant(label: str) -> bool:
    """Map classifier labels to binary relevance for Extra engineering."""
    return label in {"ENGINEERING_HIGH_CONFIDENCE", "ENGINEERING_REVIEW"}


def is_synthetic_record(rec: dict[str, Any]) -> bool:
    if rec.get("synthetic") is True:
        return True
    prov = str(rec.get("selection_provenance") or "").lower()
    if "synthetic" in prov or "fabricated" in prov:
        return True
    url = str(rec.get("url") or "")
    if "example.invalid" in url or "example.com" in url:
        return True
    return False


@dataclass
class IntegrityReport:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.ok = False
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


MACHINE_LABEL_AUTHORITIES = frozenset(
    {
        "machine_criteria_draft",
        "criteria_engine",
        "dual_engine",
        "synthetic_labeler",
        "",
    }
)
HUMAN_LABEL_AUTHORITIES = frozenset(
    {
        "human_dual_independent",
        "human_adjudicated",
    }
)


def check_corpus_integrity(
    records: list[dict[str, Any]],
    *,
    manifest: dict[str, Any] | None = None,
    development_ids: set[str] | None = None,
    require_holdout_floor: bool = False,
    allow_synthetic: bool = False,
    allow_machine_labels: bool = False,
    corpus_path: Path | None = None,
) -> IntegrityReport:
    """Integrity checks. Final accept (require_holdout_floor) demands human dual labels."""
    rep = IntegrityReport()
    if not records:
        rep.fail("corpus empty")
        return rep

    ids: list[str] = []
    machine_label_n = 0
    for i, rec in enumerate(records):
        oid = str(rec.get("official_id") or "").strip()
        if not oid:
            rep.fail(f"record[{i}] missing official_id")
            continue
        ids.append(oid)
        final = rec.get("label_final")
        if final is None or str(final).strip() == "":
            rep.fail(f"{oid}: missing label_final")
        elif str(final) not in FINAL_LABELS:
            rep.fail(f"{oid}: invalid label_final={final!r}")
        # Dual labels required when present fields expected
        la = rec.get("label_reviewer_a")
        lb = rec.get("label_reviewer_b")
        if la is not None and str(la) not in FINAL_LABELS:
            rep.fail(f"{oid}: invalid label_reviewer_a={la!r}")
        if lb is not None and str(lb) not in FINAL_LABELS:
            rep.fail(f"{oid}: invalid label_reviewer_b={lb!r}")
        # Silent UNDECIDABLE → IRRELEVANT conversion is forbidden
        if (
            final == "IRRELEVANT"
            and (la == "UNDECIDABLE" or lb == "UNDECIDABLE")
            and rec.get("adjudication_reason") in (None, "", "silent_undecidable")
        ):
            rep.fail(f"{oid}: UNDECIDABLE silently converted to IRRELEVANT")
        if not rec.get("url"):
            rep.fail(f"{oid}: missing official url")
        if not rec.get("source"):
            rep.fail(f"{oid}: missing source")
        if not rec.get("content_hash"):
            rep.fail(f"{oid}: missing content_hash")
        if not rec.get("observed_at"):
            rep.fail(f"{oid}: missing observed_at")
        if not allow_synthetic and is_synthetic_record(rec):
            rep.fail(f"{oid}: synthetic record cannot satisfy final gate")
        sel = str(rec.get("selection_method") or rec.get("selection_provenance") or "")
        for proxy in FORBIDDEN_SELECTION_PROXIES:
            if proxy in sel.lower().replace("-", "_"):
                rep.fail(f"{oid}: forbidden selection proxy {proxy}")
        # DB presence / success_zero must not influence selection
        if rec.get("selected_by_db_presence") or rec.get("selected_by_success_zero"):
            rep.fail(f"{oid}: selected via forbidden DB/success_zero proxy")
        if rec.get("selected_by_classifier") is True:
            rep.fail(f"{oid}: selected by classifier output")

        # Label authority (human dual independent required for final accept)
        auth = str(rec.get("label_authority") or "").strip().lower()
        human_a = str(rec.get("human_reviewer_a_id") or rec.get("human_reviewer_a") or "").strip()
        human_b = str(rec.get("human_reviewer_b_id") or rec.get("human_reviewer_b") or "").strip()
        is_machine = (
            auth in MACHINE_LABEL_AUTHORITIES or auth.startswith("machine") or auth.startswith("criteria") or not auth
        )
        if is_machine:
            machine_label_n += 1
        if require_holdout_floor and not allow_machine_labels:
            if is_machine or auth not in HUMAN_LABEL_AUTHORITIES:
                rep.fail(
                    f"{oid}: final gate requires human dual-independent labels "
                    f"(label_authority={auth!r}; got machine/criteria draft)"
                )
            if not human_a or not human_b or human_a == human_b:
                rep.fail(
                    f"{oid}: final gate requires two distinct human reviewer ids "
                    f"(human_reviewer_a_id / human_reviewer_b_id)"
                )
            if not rec.get("pilot_human_approval") and manifest and manifest.get("role") == "locked_holdout":
                # pilot approval is manifest-level; checked below
                pass

    # Duplicates
    seen: set[str] = set()
    dups: set[str] = set()
    for oid in ids:
        if oid in seen:
            dups.add(oid)
        seen.add(oid)
    if dups:
        rep.fail(f"duplicate official_id: {sorted(dups)[:20]}")

    # Development leakage
    if development_ids:
        leak = sorted(seen & development_ids)
        if leak:
            rep.fail(f"development leakage into holdout: {leak[:20]}")

    relevant = [r for r in records if r.get("label_final") == "RELEVANT"]
    if require_holdout_floor and len(relevant) < MIN_RELEVANT_HOLDOUT:
        rep.fail(f"RELEVANT floor not met: {len(relevant)} < {MIN_RELEVANT_HOLDOUT}")

    # Strata
    if require_holdout_floor:
        stratum_counts = count_strata(records)
        blockers = (manifest or {}).get("stratum_blockers") or {}
        for key in REQUIRED_STRATA_KEYS:
            n = stratum_counts.get(key, 0)
            if n < MIN_PER_REQUIRED_STRATUM:
                if key in blockers and blockers[key]:
                    rep.warn(
                        f"stratum {key} has {n} < {MIN_PER_REQUIRED_STRATUM} with documented blocker: {blockers[key]}"
                    )
                else:
                    rep.fail(
                        f"stratum {key} missing floor ({n} < {MIN_PER_REQUIRED_STRATUM}) "
                        "without explicit population blocker"
                    )

    # Manifest hash + freeze-before-repair (strict for final holdout)
    if manifest is not None and corpus_path is not None:
        expected = manifest.get("corpus_sha256")
        if expected:
            actual = sha256_file(corpus_path)
            if actual != expected:
                rep.fail(f"manifest corpus_sha256 mismatch: expected={expected} actual={actual}")
        freeze_ts = manifest.get("frozen_at")
        if not freeze_ts:
            rep.fail("manifest missing frozen_at")
        role = manifest.get("role")
        sealed = manifest.get("sealed_before_classifier_edits")
        if role == "locked_holdout" and require_holdout_floor and not allow_machine_labels:
            # Final accept: seal must be explicit True (missing/false fail)
            if sealed is not True:
                rep.fail(f"locked_holdout sealed_before_classifier_edits must be true for final gate (got {sealed!r})")
            clf_edit = manifest.get("classifier_first_edit_at")
            if clf_edit and freeze_ts and str(clf_edit) < str(freeze_ts):
                rep.fail(f"classifier_first_edit_at {clf_edit} is before frozen_at {freeze_ts}")
            if not manifest.get("pilot_human_approved_at"):
                rep.fail(
                    "manifest missing pilot_human_approved_at "
                    "(Tiago/authorized reviewer must approve pilot before scale-up)"
                )
            if manifest.get("label_authority") not in HUMAN_LABEL_AUTHORITIES and not allow_machine_labels:
                rep.fail(
                    "manifest label_authority must be human_dual_independent for final gate "
                    f"(got {manifest.get('label_authority')!r})"
                )
        elif role == "locked_holdout" and sealed is False and require_holdout_floor and not allow_machine_labels:
            rep.fail("holdout not sealed before classifier edits")

    if require_holdout_floor and not allow_machine_labels and machine_label_n:
        rep.fail(
            f"{machine_label_n} records use machine/criteria draft labels; "
            "human dual-independent labeling required for DOD accept"
        )

    return rep


def count_strata(records: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for rec in records:
        for key in record_stratum_keys(rec):
            counts[key] = counts.get(key, 0) + 1
    return counts


def record_stratum_keys(rec: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    src = str(rec.get("source") or "").lower()
    if src:
        keys.append(f"source:{src}")
    bucket = str(rec.get("municipio_bucket") or "").lower()
    if bucket:
        keys.append(f"municipio_bucket:{bucket}")
    natureza = str(rec.get("natureza_juridica") or "").lower()
    if natureza:
        keys.append(f"natureza:{natureza}")
    # explicit strata list support
    for s in rec.get("strata") or []:
        keys.append(str(s))
    return keys


@dataclass
class Confusion:
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return (self.tp / denom) if denom else 0.0

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return (self.tp / denom) if denom else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "tn": self.tn,
            "fn": self.fn,
            "recall": self.recall,
            "precision": self.precision,
        }


def score_records(
    records: list[dict[str, Any]],
    *,
    profile: dict[str, Any] | None = None,
    profile_path: Path | None = None,
) -> dict[str, Any]:
    """Run canonical classifier and compute relevance metrics.

    Denominator for recall = adjudicated RELEVANT only (UNDECIDABLE excluded).
    DB presence / success_zero fields are ignored if present.
    """
    conf = Confusion()
    false_negatives: list[dict[str, Any]] = []
    false_positives: list[dict[str, Any]] = []
    per_record: list[dict[str, Any]] = []
    by_source: dict[str, Confusion] = {}
    by_municipio: dict[str, Confusion] = {}
    by_natureza: dict[str, Confusion] = {}

    for rec in records:
        # Explicitly ignore forbidden proxies even if present on the record
        _ = rec.get("in_database")
        _ = rec.get("success_zero")
        _ = rec.get("db_presence")

        final = rec.get("label_final")
        if final == "UNDECIDABLE":
            per_record.append(
                {
                    "official_id": rec.get("official_id"),
                    "label_final": final,
                    "skipped": True,
                    "reason": "UNDECIDABLE excluded from denominator",
                }
            )
            continue

        gold_rel = final == "RELEVANT"
        clf = classify_object(
            rec.get("objeto"),
            titulo=rec.get("titulo"),
            itens=rec.get("itens"),
            profile=profile,
            profile_path=profile_path,
        )
        pred_rel = predicted_relevant(clf.label) or is_engineering_for_e(clf)

        if gold_rel and pred_rel:
            conf.tp += 1
            bucket = "tp"
        elif gold_rel and not pred_rel:
            conf.fn += 1
            bucket = "fn"
            false_negatives.append(
                {
                    "official_id": rec.get("official_id"),
                    "source": rec.get("source"),
                    "municipio": rec.get("municipio"),
                    "natureza_juridica": rec.get("natureza_juridica"),
                    "objeto": (rec.get("objeto") or "")[:400],
                    "url": rec.get("url"),
                    "predicted_label": clf.label,
                    "reason": clf.reason,
                }
            )
        elif (not gold_rel) and pred_rel:
            conf.fp += 1
            bucket = "fp"
            false_positives.append(
                {
                    "official_id": rec.get("official_id"),
                    "source": rec.get("source"),
                    "objeto": (rec.get("objeto") or "")[:400],
                    "predicted_label": clf.label,
                }
            )
        else:
            conf.tn += 1
            bucket = "tn"

        def _bump(store: dict[str, Confusion], key: str) -> None:
            if not key:
                return
            c = store.setdefault(key, Confusion())
            setattr(c, bucket, getattr(c, bucket) + 1)

        _bump(by_source, str(rec.get("source") or ""))
        _bump(by_municipio, str(rec.get("municipio") or ""))
        _bump(by_natureza, str(rec.get("natureza_juridica") or ""))

        per_record.append(
            {
                "official_id": rec.get("official_id"),
                "label_final": final,
                "predicted_label": clf.label,
                "predicted_relevant": pred_rel,
                "bucket": bucket,
                "rule_version": clf.rule_version,
            }
        )

    relevant_n = conf.tp + conf.fn
    ci_low, ci_high = wilson_ci(conf.tp, relevant_n)
    return {
        "confusion": conf.to_dict(),
        "relevance_recall": conf.recall,
        "informative_precision": conf.precision,
        "relevant_denominator": relevant_n,
        "undecidable_excluded": sum(1 for r in records if r.get("label_final") == "UNDECIDABLE"),
        "confidence_interval_wilson_95": {"low": ci_low, "high": ci_high},
        "false_negatives": false_negatives,
        "false_positives": false_positives,
        "by_source": {k: v.to_dict() for k, v in sorted(by_source.items())},
        "by_municipio": {k: v.to_dict() for k, v in sorted(by_municipio.items())[:50]},
        "by_natureza": {k: v.to_dict() for k, v in sorted(by_natureza.items())},
        "per_record": per_record,
    }


def evaluate(
    corpus_path: Path,
    *,
    manifest_path: Path | None = None,
    profile_path: Path | None = None,
    development_path: Path | None = None,
    require_holdout_floor: bool = True,
    allow_synthetic: bool = False,
    allow_machine_labels: bool = False,
    output_path: Path | None = None,
) -> tuple[int, dict[str, Any]]:
    """Full fail-closed evaluation. Returns (exit_code, result_dict)."""
    profile_path = profile_path or (PROJECT_ROOT / "config/client_profiles/extra.yaml")
    records = load_jsonl(corpus_path)
    manifest: dict[str, Any] | None = None
    if manifest_path is not None:
        if not manifest_path.is_file():
            result = {
                "pass": False,
                "exit_code": 2,
                "errors": [f"manifest missing: {manifest_path}"],
                "evaluator_version": EVALUATOR_VERSION,
            }
            if output_path:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            return 2, result
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    development_ids: set[str] = set()
    if development_path and development_path.is_file():
        for rec in load_jsonl(development_path):
            oid = str(rec.get("official_id") or "").strip()
            if oid:
                development_ids.add(oid)

    integrity = check_corpus_integrity(
        records,
        manifest=manifest,
        development_ids=development_ids or None,
        require_holdout_floor=require_holdout_floor,
        allow_synthetic=allow_synthetic,
        allow_machine_labels=allow_machine_labels,
        corpus_path=corpus_path,
    )

    prof = load_profile(profile_path)
    metrics = score_records(records, profile=prof, profile_path=profile_path)

    recall = float(metrics["relevance_recall"])
    relevant_n = int(metrics["relevant_denominator"])
    errors = list(integrity.errors)
    if relevant_n == 0:
        errors.append("relevant denominator is zero (only IRRELEVANT/UNDECIDABLE)")
    if recall + 1e-15 < RECALL_THRESHOLD:
        errors.append(f"relevance_recall {recall:.6f} < threshold {RECALL_THRESHOLD}")
    if not records:
        errors.append("empty result set")

    # Partial failure: any integrity error means fail
    passed = integrity.ok and not errors and recall >= RECALL_THRESHOLD - 1e-15

    # Freeze-before-repair (final accept only)
    if (
        require_holdout_floor
        and not allow_machine_labels
        and manifest
        and manifest.get("classifier_first_edit_at")
        and manifest.get("frozen_at")
    ):
        if str(manifest["classifier_first_edit_at"]) < str(manifest["frozen_at"]):
            errors.append("classifier edited before holdout freeze")
            passed = False

    result: dict[str, Any] = {
        "pass": passed,
        "exit_code": 0 if passed else 1,
        "metric": "relevance_recall",
        "not_capture_recall": True,
        "threshold": RECALL_THRESHOLD,
        "relevance_recall": recall,
        "informative_precision": metrics["informative_precision"],
        "confusion": metrics["confusion"],
        "confidence_interval_wilson_95": metrics["confidence_interval_wilson_95"],
        "relevant_denominator": relevant_n,
        "undecidable_excluded": metrics["undecidable_excluded"],
        "false_negatives": metrics["false_negatives"],
        "false_positives_count": len(metrics["false_positives"]),
        "false_positives_nominal": metrics["false_positives"][:50],
        "by_source": metrics["by_source"],
        "by_municipio": metrics["by_municipio"],
        "by_natureza": metrics["by_natureza"],
        "stratum_counts": count_strata(records),
        "integrity": {
            "ok": integrity.ok and not any(e.startswith("relevance_recall") or "denominator" in e for e in errors)
            if integrity.ok
            else False,
            "errors": errors,
            "warnings": integrity.warnings,
        },
        "versions": {
            "evaluator_version": EVALUATOR_VERSION,
            "schema_version": SCHEMA_VERSION,
            "rule_version": RULE_VERSION,
            "profile_hash": profile_hash(profile_path),
            "profile_path": str(profile_path),
            "corpus_path": str(corpus_path),
            "corpus_sha256": sha256_file(corpus_path) if corpus_path.is_file() else None,
            "manifest_path": str(manifest_path) if manifest_path else None,
            "git_sha": git_sha(),
            "evaluated_at": utc_now(),
        },
        "forbidden_proxies_used": False,
        "per_record_sample": metrics["per_record"][:20],
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return (0 if passed else 1), result


def cmd_validate_corpus(args: argparse.Namespace) -> int:
    records = load_jsonl(Path(args.corpus))
    rep = check_corpus_integrity(
        records,
        require_holdout_floor=False,
        allow_synthetic=bool(args.allow_synthetic),
    )
    out = {
        "ok": rep.ok,
        "errors": rep.errors,
        "warnings": rep.warnings,
        "n": len(records),
        "relevant": sum(1 for r in records if r.get("label_final") == "RELEVANT"),
        "irrelevant": sum(1 for r in records if r.get("label_final") == "IRRELEVANT"),
        "undecidable": sum(1 for r in records if r.get("label_final") == "UNDECIDABLE"),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if rep.ok else 1


def cmd_evaluate(args: argparse.Namespace) -> int:
    code, result = evaluate(
        Path(args.corpus),
        manifest_path=Path(args.manifest) if args.manifest else None,
        profile_path=Path(args.profile) if args.profile else None,
        development_path=Path(args.development) if args.development else None,
        require_holdout_floor=not args.no_holdout_floor,
        allow_synthetic=bool(args.allow_synthetic),
        allow_machine_labels=bool(args.allow_machine_labels),
        output_path=Path(args.output) if args.output else None,
    )
    # Compact stdout
    summary = {
        "pass": result["pass"],
        "exit_code": code,
        "relevance_recall": result["relevance_recall"],
        "relevant_denominator": result["relevant_denominator"],
        "confusion": result["confusion"],
        "errors": result["integrity"]["errors"],
        "git_sha": result["versions"]["git_sha"],
        "rule_version": result["versions"]["rule_version"],
        "profile_hash": result["versions"]["profile_hash"],
        "false_negatives_n": len(result["false_negatives"]),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return code


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="edital_relevance_recall")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate-corpus", help="Validate corpus schema/labels")
    v.add_argument("--corpus", required=True)
    v.add_argument("--allow-synthetic", action="store_true")
    v.set_defaults(func=cmd_validate_corpus)

    e = sub.add_parser("evaluate", help="Fail-closed relevance recall evaluate")
    e.add_argument("--corpus", required=True)
    e.add_argument("--manifest", default=None)
    e.add_argument(
        "--profile",
        default=str(PROJECT_ROOT / "config/client_profiles/extra.yaml"),
    )
    e.add_argument(
        "--development",
        default=str(PROJECT_ROOT / "evals/edital_relevance/development.jsonl"),
        help="Development corpus path for leakage check",
    )
    e.add_argument("--output", default=None)
    e.add_argument(
        "--no-holdout-floor",
        action="store_true",
        help="Skip ≥100 RELEVANT / stratum floors (pilot/dev only)",
    )
    e.add_argument("--allow-synthetic", action="store_true")
    e.add_argument(
        "--allow-machine-labels",
        action="store_true",
        help="Diagnostic only: permit criteria-engine draft labels (NOT DOD accept)",
    )
    e.set_defaults(func=cmd_evaluate)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
