#!/usr/bin/env python3
"""Fail-closed evaluator for DOD §8.4 relevance recall foundation.

Two explicit modes — no flag can promote machine labels to DOD accept:

1. ``diagnose`` (foundation/diagnostic)
   - May use ``machine_criteria_draft`` corpora.
   - Always returns ``status=DIAGNOSTIC_ONLY``.
   - Never sets ``pass=true``, ``ACCEPTED``, or ``dod_item_accepted=true``.

2. ``evaluate-final`` (final acceptance)
   - Rejects any ``machine_criteria_draft`` authority.
   - Requires two distinct human reviewers, adjudication, pilot approval,
     a new sealed holdout, ≥100 human RELEVANT, stratification, recall ≥95%.
   - Exits non-zero while any condition is missing (blocker string
     ``BLOCKED_HUMAN_DUAL_LABELING`` when human dual labeling is absent).

Canonical commands::

    python -m scripts.coverage.edital_relevance_recall diagnose \\
      --corpus evals/edital_relevance/machine_draft_candidate_pool.jsonl \\
      --manifest evals/edital_relevance/machine_draft_candidate_pool-manifest.json

    python -m scripts.coverage.edital_relevance_recall evaluate-final \\
      --corpus evals/edital_relevance/machine_draft_candidate_pool.jsonl \\
      --manifest evals/edital_relevance/machine_draft_candidate_pool-manifest.json
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

SCHEMA_VERSION = "edital-relevance-corpus/1.1.0"
EVALUATOR_VERSION = "edital-relevance-recall/1.1.0"
RECALL_THRESHOLD = 0.95
MIN_RELEVANT_HOLDOUT = 100
MIN_PER_REQUIRED_STRATUM = 10
BLOCKED_HUMAN_DUAL_LABELING = "BLOCKED_HUMAN_DUAL_LABELING"
DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"

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
# Roles that must never be treated as sealed final holdout
NON_SEAL_ROLES = frozenset(
    {
        "diagnostic_machine_draft",
        "machine_draft_candidate_pool",
        "development",
        "pilot",
        "locked_holdout",  # legacy name from contaminated PR — never accept
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


def is_machine_authority(auth: str) -> bool:
    a = (auth or "").strip().lower()
    if a in MACHINE_LABEL_AUTHORITIES:
        return True
    if a.startswith("machine") or a.startswith("criteria"):
        return True
    if not a:
        return True
    return False


@dataclass
class IntegrityReport:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blocker: str | None = None

    def fail(self, msg: str, *, blocker: str | None = None) -> None:
        self.ok = False
        self.errors.append(msg)
        if blocker and not self.blocker:
            self.blocker = blocker

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def check_corpus_integrity(
    records: list[dict[str, Any]],
    *,
    manifest: dict[str, Any] | None = None,
    development_ids: set[str] | None = None,
    mode: str = "diagnostic",
    corpus_path: Path | None = None,
) -> IntegrityReport:
    """Integrity checks.

    ``mode`` is ``diagnostic`` or ``final``. Final never accepts machine labels
    and has no promote-to-accept switch.
    """
    rep = IntegrityReport()
    final_mode = mode == "final"

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
        la = rec.get("label_reviewer_a")
        lb = rec.get("label_reviewer_b")
        if la is not None and str(la) not in FINAL_LABELS:
            rep.fail(f"{oid}: invalid label_reviewer_a={la!r}")
        if lb is not None and str(lb) not in FINAL_LABELS:
            rep.fail(f"{oid}: invalid label_reviewer_b={lb!r}")
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
        if final_mode and is_synthetic_record(rec):
            rep.fail(f"{oid}: synthetic record cannot satisfy final gate")
        sel = str(rec.get("selection_method") or rec.get("selection_provenance") or "")
        for proxy in FORBIDDEN_SELECTION_PROXIES:
            if proxy in sel.lower().replace("-", "_"):
                rep.fail(f"{oid}: forbidden selection proxy {proxy}")
        if rec.get("selected_by_db_presence") or rec.get("selected_by_success_zero"):
            rep.fail(f"{oid}: selected via forbidden DB/success_zero proxy")
        if rec.get("selected_by_classifier") is True:
            rep.fail(f"{oid}: selected by classifier output")

        auth = str(rec.get("label_authority") or "").strip().lower()
        human_a = str(rec.get("human_reviewer_a_id") or rec.get("human_reviewer_a") or "").strip()
        human_b = str(rec.get("human_reviewer_b_id") or rec.get("human_reviewer_b") or "").strip()
        machine = is_machine_authority(auth)
        if machine:
            machine_label_n += 1
        if final_mode:
            if machine or auth not in HUMAN_LABEL_AUTHORITIES:
                rep.fail(
                    f"{oid}: final gate requires human dual-independent labels (label_authority={auth!r})",
                    blocker=BLOCKED_HUMAN_DUAL_LABELING,
                )
            if not human_a or not human_b or human_a == human_b:
                rep.fail(
                    f"{oid}: final gate requires two distinct human reviewer ids",
                    blocker=BLOCKED_HUMAN_DUAL_LABELING,
                )
            if la != lb and not str(rec.get("adjudication_reason") or "").strip():
                rep.fail(
                    f"{oid}: divergence between reviewers requires explicit adjudication",
                    blocker=BLOCKED_HUMAN_DUAL_LABELING,
                )

    seen: set[str] = set()
    dups: set[str] = set()
    for oid in ids:
        if oid in seen:
            dups.add(oid)
        seen.add(oid)
    if dups:
        rep.fail(f"duplicate official_id: {sorted(dups)[:20]}")

    if development_ids:
        leak = sorted(seen & development_ids)
        if leak:
            rep.fail(f"development leakage into holdout: {leak[:20]}")

    relevant = [r for r in records if r.get("label_final") == "RELEVANT"]
    if final_mode and len(relevant) < MIN_RELEVANT_HOLDOUT:
        rep.fail(f"RELEVANT floor not met: {len(relevant)} < {MIN_RELEVANT_HOLDOUT}")

    if final_mode:
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

    if manifest is not None and corpus_path is not None:
        expected = manifest.get("corpus_sha256")
        if expected:
            actual = sha256_file(corpus_path)
            if actual != expected:
                rep.fail(f"manifest corpus_sha256 mismatch: expected={expected} actual={actual}")

    if final_mode:
        if manifest is None:
            rep.fail("final gate requires manifest", blocker=BLOCKED_HUMAN_DUAL_LABELING)
        else:
            role = str(manifest.get("role") or "")
            if role in NON_SEAL_ROLES or role != "human_sealed_holdout":
                rep.fail(
                    f"final gate requires role=human_sealed_holdout (got {role!r}); "
                    "machine-draft / contaminated / legacy locked_holdout roles are rejected",
                    blocker=BLOCKED_HUMAN_DUAL_LABELING,
                )
            if manifest.get("acceptance_eligible") is True and is_machine_authority(
                str(manifest.get("label_authority") or "")
            ):
                rep.fail("manifest claims acceptance_eligible with machine label authority")
            if (
                manifest.get("sealed_holdout") is not True
                and manifest.get("sealed_before_classifier_edits") is not True
            ):
                rep.fail(
                    "final gate requires sealed_holdout=true (new sample sealed before classifier edits)",
                    blocker=BLOCKED_HUMAN_DUAL_LABELING,
                )
            if not manifest.get("frozen_at"):
                rep.fail("manifest missing frozen_at")
            if not manifest.get("pilot_human_approved_at"):
                rep.fail(
                    "manifest missing pilot_human_approved_at",
                    blocker=BLOCKED_HUMAN_DUAL_LABELING,
                )
            man_auth = str(manifest.get("label_authority") or "")
            if man_auth not in HUMAN_LABEL_AUTHORITIES:
                rep.fail(
                    f"manifest label_authority must be human (got {man_auth!r})",
                    blocker=BLOCKED_HUMAN_DUAL_LABELING,
                )
            if machine_label_n:
                rep.fail(
                    f"{machine_label_n} records use machine/criteria draft labels",
                    blocker=BLOCKED_HUMAN_DUAL_LABELING,
                )
            clf_edit = manifest.get("classifier_first_edit_at")
            freeze_ts = manifest.get("frozen_at")
            if clf_edit and freeze_ts and str(clf_edit) < str(freeze_ts):
                rep.fail(f"classifier_first_edit_at {clf_edit} is before frozen_at {freeze_ts}")

    if not final_mode and machine_label_n:
        rep.warn(f"{machine_label_n} records use machine_criteria_draft — diagnostic only; not eligible for DOD accept")

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
    nat = str(rec.get("natureza_juridica") or "").lower()
    if nat:
        # normalize common aliases
        if nat in {"admin_direta", "direta", "administracao_direta"}:
            keys.append("natureza:admin_direta")
        elif nat in {"admin_indireta", "indireta", "administracao_indireta"}:
            keys.append("natureza:admin_indireta")
        else:
            keys.append(f"natureza:{nat}")
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
    mode: str = "diagnostic",
    output_path: Path | None = None,
) -> tuple[int, dict[str, Any]]:
    """Evaluate corpus.

    mode=diagnostic → always non-accept (DIAGNOSTIC_ONLY), exit 0 if integrity
    for diagnostic holds (machine labels allowed).
    mode=final → accept only when all human gates + recall ≥95%; otherwise
    non-zero exit with blocker.
    """
    if mode not in {"diagnostic", "final"}:
        raise ValueError(f"unknown mode {mode!r}")

    profile_path = profile_path or (PROJECT_ROOT / "config" / "client_profiles" / "extra.yaml")
    records = load_jsonl(corpus_path)
    manifest: dict[str, Any] | None = None
    if manifest_path and manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    elif mode == "final":
        # missing manifest handled in integrity
        pass

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
        mode=mode,
        corpus_path=corpus_path,
    )

    prof = load_profile(profile_path)
    metrics = score_records(records, profile=prof, profile_path=profile_path)
    recall = float(metrics["relevance_recall"])
    relevant_n = int(metrics["relevant_denominator"])
    errors = list(integrity.errors)

    if mode == "final":
        if relevant_n == 0:
            errors.append("relevant denominator is zero (only IRRELEVANT/UNDECIDABLE)")
        if relevant_n > 0 and recall + 1e-15 < RECALL_THRESHOLD:
            errors.append(f"relevance_recall {recall:.6f} < threshold {RECALL_THRESHOLD}")

    blocker = integrity.blocker
    if mode == "final" and not blocker:
        # human dual labeling is the primary structural blocker when machine present
        man_auth = str((manifest or {}).get("label_authority") or "")
        if is_machine_authority(man_auth) or any(
            is_machine_authority(str(r.get("label_authority") or "")) for r in records
        ):
            blocker = BLOCKED_HUMAN_DUAL_LABELING
        elif not integrity.ok or errors:
            # still blocked, prefer human dual labeling string when pilot/seal missing
            joined = " ".join(errors).lower()
            if any(
                k in joined
                for k in (
                    "human",
                    "pilot",
                    "seal",
                    "machine",
                    "reviewer",
                    "adjudicat",
                    "role=",
                )
            ):
                blocker = BLOCKED_HUMAN_DUAL_LABELING

    if mode == "diagnostic":
        # Diagnostic never accepts, even if metrics look good against machine labels.
        status = DIAGNOSTIC_ONLY
        acceptance_eligible = False
        dod_item_accepted = False
        passed = False
        # Foundation integrity: structural errors (empty, dups, missing fields) still fail exit
        structural_fail = (
            not integrity.ok
            and any(
                not (
                    "machine" in e.lower()
                    or "human dual" in e.lower()
                    or "sealed" in e.lower()
                    or "pilot_human" in e.lower()
                )
                for e in integrity.errors
            )
            or not records
        )
        # For diagnostic, integrity.ok may be True with only warnings for machine labels
        exit_code = 1 if (not records or (not integrity.ok and structural_fail)) else 0
        # Prefer exit 0 for diagnostic when only expected machine-draft warnings
        if integrity.ok or (
            not integrity.ok
            and all(
                "machine" in e.lower()
                or "human dual" in e.lower()
                or "final gate" in e.lower()
                or "sealed" in e.lower()
                or "pilot" in e.lower()
                or "role=" in e.lower()
                for e in integrity.errors
            )
        ):
            # pure machine-draft corpus should run diagnostic successfully
            if records and not any(
                "missing" in e.lower()
                or "duplicate" in e.lower()
                or "empty" in e.lower()
                or "invalid" in e.lower()
                or "forbidden" in e.lower()
                or "synthetic" in e.lower()
                or "mismatch" in e.lower()
                for e in integrity.errors
            ):
                exit_code = 0
                # recompute: if real structural issues exist, fail
                structural_keys = (
                    "missing",
                    "duplicate",
                    "empty",
                    "invalid",
                    "forbidden",
                    "selected by",
                    "selected via",
                    "silently",
                )
                if any(any(k in e.lower() for k in structural_keys) for e in integrity.errors):
                    exit_code = 1
        result: dict[str, Any] = {
            "pass": False,
            "status": status,
            "mode": mode,
            "acceptance_eligible": acceptance_eligible,
            "dod_item_accepted": dod_item_accepted,
            "sealed_holdout": False,
            "label_authority": (manifest or {}).get("label_authority") or "machine_criteria_draft",
            "role": (manifest or {}).get("role") or "diagnostic_machine_draft",
            "blocker": None,
            "exit_code": exit_code,
            "metric": "relevance_recall",
            "not_capture_recall": True,
            "diagnostic_only": True,
            "threshold": RECALL_THRESHOLD,
            "relevance_recall": recall,
            "relevance_recall_note": (
                "Diagnostic comparison against machine_criteria_draft labels only. "
                "NOT gold, NOT sealed holdout, NOT DOD accept evidence."
            ),
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
                "ok": integrity.ok,
                "errors": integrity.errors,
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
            "non_claims": [
                "Not DOD §8.4 accept",
                "Not human gold",
                "Not sealed final holdout",
                "Machine draft labels are circular-risk diagnostic only",
            ],
        }
    else:
        passed = integrity.ok and not errors and recall >= RECALL_THRESHOLD - 1e-15
        exit_code = 0 if passed else 1
        status = "ACCEPTED" if passed else (blocker or "FAILED_FINAL_GATE")
        result = {
            "pass": passed,
            "status": status,
            "mode": mode,
            "acceptance_eligible": passed,
            "dod_item_accepted": False,  # only main merge + human process can set DOD [x]
            "sealed_holdout": bool(
                (manifest or {}).get("sealed_holdout") or (manifest or {}).get("sealed_before_classifier_edits")
            ),
            "blocker": None if passed else (blocker or "FAILED_FINAL_GATE"),
            "exit_code": exit_code,
            "metric": "relevance_recall",
            "not_capture_recall": True,
            "diagnostic_only": False,
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
                "ok": integrity.ok and not errors,
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

    return exit_code, result


def cmd_diagnose(args: argparse.Namespace) -> int:
    code, result = evaluate(
        Path(args.corpus),
        manifest_path=Path(args.manifest) if args.manifest else None,
        profile_path=Path(args.profile) if args.profile else None,
        development_path=Path(args.development) if args.development else None,
        mode="diagnostic",
        output_path=Path(args.output) if args.output else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


def cmd_evaluate_final(args: argparse.Namespace) -> int:
    code, result = evaluate(
        Path(args.corpus),
        manifest_path=Path(args.manifest) if args.manifest else None,
        profile_path=Path(args.profile) if args.profile else None,
        development_path=Path(args.development) if args.development else None,
        mode="final",
        output_path=Path(args.output) if args.output else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    # Always non-zero while blocked on human dual labeling
    if result.get("blocker") == BLOCKED_HUMAN_DUAL_LABELING:
        print(BLOCKED_HUMAN_DUAL_LABELING, file=sys.stderr)
        return 1 if code == 0 else code
    return code


def cmd_validate_corpus(args: argparse.Namespace) -> int:
    records = load_jsonl(Path(args.corpus))
    mode = "final" if args.final else "diagnostic"
    manifest = None
    if args.manifest:
        mp = Path(args.manifest)
        if mp.is_file():
            manifest = json.loads(mp.read_text(encoding="utf-8"))
    rep = check_corpus_integrity(
        records,
        manifest=manifest,
        mode=mode,
        corpus_path=Path(args.corpus),
    )
    out = {
        "ok": rep.ok,
        "mode": mode,
        "blocker": rep.blocker,
        "errors": rep.errors,
        "warnings": rep.warnings,
        "n": len(records),
        "relevant": sum(1 for r in records if r.get("label_final") == "RELEVANT"),
        "irrelevant": sum(1 for r in records if r.get("label_final") == "IRRELEVANT"),
        "undecidable": sum(1 for r in records if r.get("label_final") == "UNDECIDABLE"),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if mode == "final" and not rep.ok:
        if rep.blocker:
            print(rep.blocker, file=sys.stderr)
        return 1
    return 0 if rep.ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="edital_relevance_recall",
        description="Fail-closed edital relevance recall evaluator (foundation + final).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--corpus", required=True, help="Path to corpus JSONL")
    common.add_argument("--manifest", default=None, help="Path to corpus manifest JSON")
    common.add_argument(
        "--profile",
        default=str(PROJECT_ROOT / "config" / "client_profiles" / "extra.yaml"),
    )
    common.add_argument("--development", default=None, help="Development split for leakage check")
    common.add_argument("--output", default=None, help="Write result JSON")

    d = sub.add_parser(
        "diagnose",
        parents=[common],
        help="Diagnostic mode: machine drafts allowed; never accept (DIAGNOSTIC_ONLY).",
    )
    d.set_defaults(func=cmd_diagnose)

    f = sub.add_parser(
        "evaluate-final",
        parents=[common],
        help="Final accept mode: human dual labels required; fail-closed.",
    )
    f.set_defaults(func=cmd_evaluate_final)

    v = sub.add_parser("validate-corpus", help="Validate corpus integrity only")
    v.add_argument("--corpus", required=True)
    v.add_argument("--manifest", default=None)
    v.add_argument(
        "--final",
        action="store_true",
        help="Apply final-gate integrity (rejects machine labels)",
    )
    v.set_defaults(func=cmd_validate_corpus)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
