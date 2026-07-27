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
      --corpus evals/edital_relevance/pilot_36.jsonl \\
      --manifest evals/edital_relevance/pilot_36-manifest.json

    python -m scripts.coverage.edital_relevance_recall evaluate-final \\
      --corpus evals/edital_relevance/pilot_36.jsonl \\
      --manifest evals/edital_relevance/pilot_36-manifest.json \\
      --development evals/edital_relevance/development_candidate_pool.jsonl \\
      --development-manifest evals/edital_relevance/development_candidate_pool-manifest.json
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
EVALUATOR_VERSION = "edital-relevance-recall/1.2.0"
RECALL_THRESHOLD = 0.95
MIN_RELEVANT_HOLDOUT = 100
MIN_PER_REQUIRED_STRATUM = 10
# Fail-closed blocker taxonomy (primary blocker selected by precedence, never mask technical as human).
FAILED_DEVELOPMENT_INTEGRITY = "FAILED_DEVELOPMENT_INTEGRITY"
BLOCKED_HUMAN_DUAL_LABELING = "BLOCKED_HUMAN_DUAL_LABELING"
FAILED_FINAL_GATE = "FAILED_FINAL_GATE"
DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"
# Deterministic precedence: lower rank wins as primary ``blocker``.
# 1) technical development integrity
# 2) human dual-labeling / seal / pilot absence (operational blocker of this foundation)
# 3) pure metric/final residual (recall threshold etc.) — never masks (1) or (2)
BLOCKER_PRECEDENCE: dict[str, int] = {
    FAILED_DEVELOPMENT_INTEGRITY: 1,
    BLOCKED_HUMAN_DUAL_LABELING: 2,
    FAILED_FINAL_GATE: 3,
}
# Development selection provenance (must match real selection process).
DEV_SELECTION_RULE = "public_inventory_stratified_content_sample"
DEV_SELECTION_BASIS = "public_inventory_only"

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
        "pilot_candidate",
        "locked_holdout",  # legacy name from contaminated PR — never accept
    }
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_reviewer_id(value: str) -> str:
    """Case- and whitespace-insensitive identity key (same rule as human importer)."""
    return " ".join((value or "").strip().split()).casefold()


def parse_timezone_aware_iso(value: str) -> datetime:
    """Parse ISO-8601 requiring explicit timezone; reject naive/placeholders.

    Accepts Z, +00:00, -03:00. Rejects date-only, time-only, naive, tbd/pending/null.
    """
    v = (value or "").strip()
    if not v:
        raise ValueError("missing timestamp")
    if v.lower() in {"tbd", "pending", "null", "none", "n/a", "na"}:
        raise ValueError(f"placeholder timestamp {v!r}")
    if "T" not in v and " " not in v:
        raise ValueError(f"date-only timestamp rejected {v!r}")
    try:
        parsed = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid ISO-8601 timestamp {v!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"timezone-naive timestamp rejected {v!r}")
    return parsed


def resolve_manifest_corpus_path(manifest_corpus_path: str) -> Path:
    """Resolve manifest corpus_path: absolute as-is, relative against PROJECT_ROOT."""
    p = Path(manifest_corpus_path)
    if p.is_absolute():
        return p.resolve()
    return (PROJECT_ROOT / p).resolve()


def paths_refer_to_same_file(manifest_corpus_path: str, provided: Path) -> bool:
    """Exact path identity only — same basename in another directory must fail."""
    try:
        return resolve_manifest_corpus_path(manifest_corpus_path) == provided.resolve()
    except OSError:
        return False


def primary_blocker(blockers: Iterable[str | None]) -> str | None:
    """Select primary blocker by deterministic precedence (lowest rank wins)."""
    present = [b for b in blockers if b]
    if not present:
        return None
    # Deduplicate preserving first-seen order for stable listing
    ordered: list[str] = []
    seen: set[str] = set()
    for b in present:
        if b not in seen:
            seen.add(b)
            ordered.append(b)
    return min(ordered, key=lambda b: BLOCKER_PRECEDENCE.get(b, 99))


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


def _record_has_forbidden_proxy(rec: dict[str, Any]) -> str | None:
    """Return proxy name if record was selected via a forbidden proxy; else None."""
    if rec.get("selected_by_classifier") is True:
        return "selected_by_classifier"
    if rec.get("selected_by_db_presence") is True:
        return "selected_by_db_presence"
    if rec.get("selected_by_success_zero") is True:
        return "selected_by_success_zero"
    sel = str(rec.get("selection_method") or rec.get("selection_provenance") or "")
    sel_norm = sel.lower().replace("-", "_")
    for proxy in FORBIDDEN_SELECTION_PROXIES:
        if proxy in sel_norm:
            return proxy
    return None


def check_development_integrity(
    *,
    development_path: Path | None,
    development_manifest_path: Path | None,
    holdout_ids: list[str],
    required: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    """Fail-closed development corpus integrity for final mode.

    Validates presence, non-empty JSONL, unique official_ids, no holdout overlap,
    mandatory development-manifest hash/path/n_records/role/flags, and rejects
    synthetic or forbidden-proxy selection. Decision uses the full ID set.
    """
    errors: list[str] = []
    integrity: dict[str, Any] = {
        "path": str(development_path) if development_path else None,
        "manifest_path": str(development_manifest_path) if development_manifest_path else None,
        "sha256": None,
        "n_records": 0,
        "duplicate_ids": [],
        "holdout_overlap_count": 0,
        "holdout_overlap_ids": [],
        "pass": False,
    }

    if not required and development_path is None and development_manifest_path is None:
        integrity["pass"] = True
        return integrity, errors

    if development_path is None:
        errors.append(
            "final gate requires development corpus for leak check "
            "(--development is mandatory; empty/omitted is not allowed)"
        )
        return integrity, errors
    if development_manifest_path is None:
        errors.append(
            "final gate requires --development-manifest "
            "(development hash/role/flags cannot be omitted)"
        )
        return integrity, errors

    integrity["path"] = str(development_path)
    integrity["manifest_path"] = str(development_manifest_path)

    if not development_path.is_file():
        errors.append(f"development corpus missing: {development_path}")
        return integrity, errors
    if not development_manifest_path.is_file():
        errors.append(f"development manifest missing: {development_manifest_path}")
        return integrity, errors

    try:
        records = load_jsonl(development_path)
    except ValueError as exc:
        errors.append(f"development corpus invalid JSONL: {exc}")
        return integrity, errors

    if not records:
        errors.append("development corpus empty (non-empty development required for final gate)")
        return integrity, errors

    try:
        dev_manifest = json.loads(development_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"development manifest unreadable/invalid JSON: {exc}")
        return integrity, errors
    if not isinstance(dev_manifest, dict):
        errors.append("development manifest must be a JSON object")
        return integrity, errors

    actual_sha = sha256_file(development_path)
    integrity["sha256"] = actual_sha
    expected_sha = dev_manifest.get("corpus_sha256")
    if expected_sha is None or str(expected_sha).strip() == "":
        errors.append(
            "development manifest requires corpus_sha256 "
            "(missing/empty hash is not optional)"
        )
    elif str(expected_sha) != actual_sha:
        errors.append(
            f"development corpus_sha256 mismatch: expected={expected_sha} actual={actual_sha}"
        )

    man_path = str(dev_manifest.get("corpus_path") or "").strip()
    if not man_path:
        errors.append("development manifest requires corpus_path")
    else:
        # Exact path identity only (absolute resolve or PROJECT_ROOT-relative).
        # Same basename in another directory is NOT sufficient.
        if not paths_refer_to_same_file(man_path, development_path):
            errors.append(
                f"development corpus_path mismatch: manifest={man_path!r} file={development_path} "
                f"(resolved manifest={resolve_manifest_corpus_path(man_path)} "
                f"resolved file={development_path.resolve()})"
            )

    role = str(dev_manifest.get("role") or "")
    if role != "development":
        errors.append(f"development manifest role must be 'development' (got {role!r})")
    if dev_manifest.get("acceptance_eligible") is True:
        errors.append("development manifest must not set acceptance_eligible=true")
    if dev_manifest.get("acceptance_eligible") is not False:
        errors.append("development manifest requires acceptance_eligible=false")
    if dev_manifest.get("sealed_holdout") is True:
        errors.append("development manifest must not set sealed_holdout=true")
    if dev_manifest.get("sealed_holdout") is not False:
        errors.append("development manifest requires sealed_holdout=false")

    # Provenance must describe the real selection process (not a coarser alias alone).
    sel_rule = str(dev_manifest.get("selection_rule") or "").strip()
    if sel_rule != DEV_SELECTION_RULE:
        errors.append(
            f"development manifest selection_rule must be {DEV_SELECTION_RULE!r} "
            f"(got {sel_rule!r})"
        )
    sel_basis = str(dev_manifest.get("selection_basis") or "").strip()
    if sel_basis != DEV_SELECTION_BASIS:
        errors.append(
            f"development manifest selection_basis must be {DEV_SELECTION_BASIS!r} "
            f"(got {sel_basis!r})"
        )
    if dev_manifest.get("selection_independent_of_classifier") is not True:
        errors.append(
            "development manifest requires selection_independent_of_classifier=true"
        )

    expected_n = dev_manifest.get("n_records")
    if expected_n is None:
        errors.append("development manifest requires n_records")
    else:
        try:
            expected_n_int = int(expected_n)
        except (TypeError, ValueError):
            errors.append(f"development manifest n_records invalid: {expected_n!r}")
            expected_n_int = -1
        if expected_n_int != len(records):
            errors.append(
                f"development n_records mismatch: manifest={expected_n_int} actual={len(records)}"
            )

    development_id_list: list[str] = []
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            errors.append(f"development record[{i}] is not an object")
            continue
        oid = str(rec.get("official_id") or "").strip()
        if not oid:
            errors.append(f"development record[{i}] missing official_id")
            continue
        development_id_list.append(oid)
        if is_synthetic_record(rec):
            errors.append(f"development {oid}: synthetic record not allowed")
        proxy = _record_has_forbidden_proxy(rec)
        if proxy:
            errors.append(f"development {oid}: forbidden selection proxy {proxy}")

    integrity["n_records"] = len(records)
    # Full-set duplicate detection (no truncated decision).
    seen: set[str] = set()
    dups: list[str] = []
    for oid in development_id_list:
        if oid in seen:
            if oid not in dups:
                dups.append(oid)
        else:
            seen.add(oid)
    integrity["duplicate_ids"] = dups
    if dups:
        errors.append(f"development corpus has duplicate official_id: {dups}")
    if len(development_id_list) != len(set(development_id_list)):
        # already recorded above; ensure fail even if list formatting differs
        if not dups:
            errors.append("development corpus has duplicate official_id values")

    holdout_set = {str(x).strip() for x in holdout_ids if str(x).strip()}
    # Detect internal holdout dups separately is done by holdout integrity;
    # here compute full intersection.
    overlap = sorted(holdout_set & set(development_id_list))
    integrity["holdout_overlap_ids"] = overlap
    integrity["holdout_overlap_count"] = len(overlap)
    if overlap:
        errors.append(
            f"development leakage into holdout: count={len(overlap)} ids={overlap[:20]}"
        )

    integrity["pass"] = len(errors) == 0
    return integrity, errors


@dataclass
class IntegrityReport:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blocker: str | None = None
    blockers: list[str] = field(default_factory=list)

    def fail(self, msg: str, *, blocker: str | None = None) -> None:
        self.ok = False
        self.errors.append(msg)
        if blocker:
            if blocker not in self.blockers:
                self.blockers.append(blocker)
            # Precedence: technical development integrity always outranks human dual labeling.
            self.blocker = primary_blocker(self.blockers)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def check_corpus_integrity(
    records: list[dict[str, Any]],
    *,
    manifest: dict[str, Any] | None = None,
    development_ids: set[str] | None = None,
    development_path: Path | None = None,
    development_required: bool = False,
    mode: str = "diagnostic",
    corpus_path: Path | None = None,
) -> IntegrityReport:
    """Integrity checks.

    ``mode`` is ``diagnostic`` or ``final``. Final never accepts machine labels
    and has no promote-to-accept switch. Final requires both seal flags (AND),
    mandatory ``corpus_sha256``, and a non-omissible development leak check.
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
        final_raw = rec.get("label_final")
        final = str(final_raw).strip() if final_raw is not None else ""
        if not final:
            rep.fail(f"{oid}: missing label_final")
            final = ""
        elif final not in FINAL_LABELS:
            rep.fail(f"{oid}: invalid label_final={final_raw!r}")
            final = ""

        la_raw = rec.get("label_reviewer_a")
        lb_raw = rec.get("label_reviewer_b")
        la = str(la_raw).strip() if la_raw is not None else ""
        lb = str(lb_raw).strip() if lb_raw is not None else ""
        # Diagnostic may omit dual labels; final never may.
        if la and la not in FINAL_LABELS:
            rep.fail(f"{oid}: invalid label_reviewer_a={la_raw!r}")
        if lb and lb not in FINAL_LABELS:
            rep.fail(f"{oid}: invalid label_reviewer_b={lb_raw!r}")
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
            # Direct reviewer identity validation (do not rely solely on importer).
            # Normalize with the same rule as the human importer.
            norm_a = normalize_reviewer_id(human_a)
            norm_b = normalize_reviewer_id(human_b)
            if not norm_a or not norm_b:
                rep.fail(
                    f"{oid}: final gate requires two distinct human reviewer ids "
                    f"(human_reviewer_a_id / human_reviewer_b_id)",
                    blocker=BLOCKED_HUMAN_DUAL_LABELING,
                )
            elif norm_a == norm_b:
                rep.fail(
                    f"{oid}: final gate requires two distinct human reviewer identities "
                    f"after case/whitespace normalize "
                    f"(a={human_a!r} b={human_b!r} → {norm_a!r})",
                    blocker=BLOCKED_HUMAN_DUAL_LABELING,
                )
            # Timestamps: timezone-aware ISO-8601 required on every record.
            for ts_field in ("reviewed_at_a", "reviewed_at_b"):
                raw_ts = rec.get(ts_field)
                if raw_ts is None or str(raw_ts).strip() == "":
                    rep.fail(
                        f"{oid}: final gate requires {ts_field} (timezone-aware ISO-8601)",
                        blocker=BLOCKED_HUMAN_DUAL_LABELING,
                    )
                else:
                    try:
                        parse_timezone_aware_iso(str(raw_ts))
                    except ValueError as exc:
                        rep.fail(
                            f"{oid}: invalid {ts_field}={raw_ts!r}: {exc}",
                            blocker=BLOCKED_HUMAN_DUAL_LABELING,
                        )
            # Individual human reasons (importer fields); adjudication_reason is not a substitute.
            reason_a = str(
                rec.get("label_reviewer_a_reason")
                or rec.get("reason_reviewer_a")
                or rec.get("reviewer_a_reason")
                or ""
            ).strip()
            reason_b = str(
                rec.get("label_reviewer_b_reason")
                or rec.get("reason_reviewer_b")
                or rec.get("reviewer_b_reason")
                or ""
            ).strip()
            if not reason_a:
                rep.fail(
                    f"{oid}: final gate requires non-empty label_reviewer_a_reason",
                    blocker=BLOCKED_HUMAN_DUAL_LABELING,
                )
            if not reason_b:
                rep.fail(
                    f"{oid}: final gate requires non-empty label_reviewer_b_reason",
                    blocker=BLOCKED_HUMAN_DUAL_LABELING,
                )
            # Dual labels are mandatory for final accept (forged/missing duals cannot pass).
            if not la or la not in FINAL_LABELS:
                rep.fail(
                    f"{oid}: final gate requires label_reviewer_a in {sorted(FINAL_LABELS)}",
                    blocker=BLOCKED_HUMAN_DUAL_LABELING,
                )
            if not lb or lb not in FINAL_LABELS:
                rep.fail(
                    f"{oid}: final gate requires label_reviewer_b in {sorted(FINAL_LABELS)}",
                    blocker=BLOCKED_HUMAN_DUAL_LABELING,
                )
            adj = str(rec.get("adjudication_reason") or "").strip()
            if la and lb and la in FINAL_LABELS and lb in FINAL_LABELS:
                if la != lb:
                    if not adj or adj.lower() in {"silent_undecidable", "auto"}:
                        rep.fail(
                            f"{oid}: divergence between reviewers requires explicit adjudication",
                            blocker=BLOCKED_HUMAN_DUAL_LABELING,
                        )
                    # Adjudicated final must be one of the two reviewer labels or explicit UNDECIDABLE.
                    if final and final not in {la, lb, "UNDECIDABLE"} and final in FINAL_LABELS:
                        # Allow adjudicator to pick any valid label only with non-empty reason already required.
                        # Still require final itself valid (already checked) and reason present.
                        if not adj:
                            rep.fail(
                                f"{oid}: adjudicated label_final={final!r} without adjudication_reason",
                                blocker=BLOCKED_HUMAN_DUAL_LABELING,
                            )
                else:
                    # Agreement: label_final must match both dual labels (no silent override).
                    if final and final != la:
                        rep.fail(
                            f"{oid}: label_final={final!r} contradicts agreed dual labels {la!r}",
                            blocker=BLOCKED_HUMAN_DUAL_LABELING,
                        )
                    if not adj:
                        # agreement reason should be recorded (import path writes agreement:LABEL)
                        rep.fail(
                            f"{oid}: missing adjudication_reason for agreed dual labels",
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

    # Lightweight development leak check for diagnostic / callers that only pass IDs.
    # Final-mode mandatory development+manifest validation lives in
    # ``check_development_integrity`` (hash/role/empty/dups/full overlap).
    if development_ids is not None:
        leak = sorted(seen & development_ids)
        if leak:
            rep.fail(f"development leakage into holdout: {leak[:20]}")
    elif final_mode or development_required:
        if development_path is None:
            rep.fail(
                "final gate requires development corpus for leak check "
                "(--development is mandatory)",
                blocker=FAILED_DEVELOPMENT_INTEGRITY,
            )
        elif not development_path.is_file():
            rep.fail(
                f"development corpus missing: {development_path}",
                blocker=FAILED_DEVELOPMENT_INTEGRITY,
            )

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

    if final_mode:
        # corpus_sha256 is mandatory in final mode (missing hash fails).
        if corpus_path is None or not corpus_path.is_file():
            rep.fail("final gate requires corpus_path for sha256 check")
        if manifest is None:
            rep.fail("final gate requires manifest", blocker=BLOCKED_HUMAN_DUAL_LABELING)
        else:
            expected = manifest.get("corpus_sha256")
            if not expected:
                rep.fail(
                    "final gate requires manifest corpus_sha256 (missing hash is not optional)",
                    blocker=BLOCKED_HUMAN_DUAL_LABELING,
                )
            elif corpus_path is not None and corpus_path.is_file():
                actual = sha256_file(corpus_path)
                if actual != expected:
                    rep.fail(f"manifest corpus_sha256 mismatch: expected={expected} actual={actual}")
            role = str(manifest.get("role") or "")
            if role in NON_SEAL_ROLES or role != "human_sealed_holdout":
                rep.fail(
                    f"final gate requires role=human_sealed_holdout (got {role!r}); "
                    "machine-draft / contaminated / legacy locked_holdout roles are rejected",
                    blocker=BLOCKED_HUMAN_DUAL_LABELING,
                )
            if manifest.get("acceptance_eligible") is not True:
                rep.fail(
                    "final gate requires acceptance_eligible=true",
                    blocker=BLOCKED_HUMAN_DUAL_LABELING,
                )
            if manifest.get("acceptance_eligible") is True and is_machine_authority(
                str(manifest.get("label_authority") or "")
            ):
                rep.fail("manifest claims acceptance_eligible with machine label authority")
            # BOTH seal flags required (AND — no OR).
            if manifest.get("sealed_holdout") is not True:
                rep.fail(
                    "final gate requires sealed_holdout=true",
                    blocker=BLOCKED_HUMAN_DUAL_LABELING,
                )
            if manifest.get("sealed_before_classifier_edits") is not True:
                rep.fail(
                    "final gate requires sealed_before_classifier_edits=true",
                    blocker=BLOCKED_HUMAN_DUAL_LABELING,
                )
            if not manifest.get("frozen_at"):
                rep.fail("manifest missing frozen_at", blocker=BLOCKED_HUMAN_DUAL_LABELING)
            if not manifest.get("pilot_human_approved_at"):
                rep.fail(
                    "manifest missing pilot_human_approved_at",
                    blocker=BLOCKED_HUMAN_DUAL_LABELING,
                )
            if not manifest.get("pilot_human_approved_by"):
                rep.fail(
                    "manifest missing pilot_human_approved_by",
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
    elif manifest is not None and corpus_path is not None:
        # Diagnostic: hash check only when provided.
        expected = manifest.get("corpus_sha256")
        if expected:
            actual = sha256_file(corpus_path)
            if actual != expected:
                rep.fail(f"manifest corpus_sha256 mismatch: expected={expected} actual={actual}")

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
    development_manifest_path: Path | None = None,
    mode: str = "diagnostic",
    output_path: Path | None = None,
) -> tuple[int, dict[str, Any]]:
    """Evaluate corpus.

    mode=diagnostic → always non-accept (DIAGNOSTIC_ONLY), exit 0 if integrity
    for diagnostic holds (machine labels allowed).
    mode=final → accept only when all human gates + recall ≥95%; otherwise
    non-zero exit with blocker. Final mode requires real non-empty development
    corpus + development-manifest with mandatory hash/role/flags.
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

    # Final mode: --development and --development-manifest are mandatory
    # (no silent inference from holdout manifest alone).
    resolved_dev_path: Path | None = development_path
    resolved_dev_manifest: Path | None = development_manifest_path

    holdout_ids: list[str] = [
        str(r.get("official_id") or "").strip()
        for r in records
        if str(r.get("official_id") or "").strip()
    ]
    # Detect holdout internal duplicate IDs (full set).
    if len(holdout_ids) != len(set(holdout_ids)):
        # check_corpus_integrity also reports dups; keep list for development block
        pass

    development_ids: set[str] = set()
    development_id_list: list[str] = []
    if resolved_dev_path is not None and resolved_dev_path.is_file():
        try:
            for rec in load_jsonl(resolved_dev_path):
                oid = str(rec.get("official_id") or "").strip()
                if oid:
                    development_id_list.append(oid)
                    development_ids.add(oid)
        except ValueError:
            # invalid JSONL handled by check_development_integrity
            pass

    integrity = check_corpus_integrity(
        records,
        manifest=manifest,
        development_ids=development_ids if resolved_dev_path is not None else None,
        development_path=resolved_dev_path,
        development_required=(mode == "final"),
        mode=mode,
        corpus_path=corpus_path,
    )

    development_integrity: dict[str, Any] | None = None
    if mode == "final":
        development_integrity, dev_errors = check_development_integrity(
            development_path=resolved_dev_path,
            development_manifest_path=resolved_dev_manifest,
            holdout_ids=holdout_ids,
            required=True,
        )
        # Technical development failures MUST NOT be classified as human dual-labeling.
        for msg in dev_errors:
            integrity.fail(msg, blocker=FAILED_DEVELOPMENT_INTEGRITY)
        # Also fail closed on holdout internal dups explicitly for final reporting
        if len(holdout_ids) != len(set(holdout_ids)):
            integrity.fail(
                "holdout corpus has duplicate official_id values",
                blocker=FAILED_FINAL_GATE,
            )

    prof = load_profile(profile_path)
    metrics = score_records(records, profile=prof, profile_path=profile_path)
    recall = float(metrics["relevance_recall"])
    relevant_n = int(metrics["relevant_denominator"])

    if mode == "final":
        # Metric residual errors: message always recorded; blocker only if no
        # higher-precedence development/human blockers are already present.
        metric_msgs: list[str] = []
        if relevant_n == 0:
            metric_msgs.append(
                "relevant denominator is zero (only IRRELEVANT/UNDECIDABLE)"
            )
        if relevant_n > 0 and recall + 1e-15 < RECALL_THRESHOLD:
            metric_msgs.append(
                f"relevance_recall {recall:.6f} < threshold {RECALL_THRESHOLD}"
            )
        higher = {
            b
            for b in integrity.blockers
            if b in {FAILED_DEVELOPMENT_INTEGRITY, BLOCKED_HUMAN_DUAL_LABELING}
        }
        for msg in metric_msgs:
            if higher:
                integrity.fail(msg)  # keep error, do not promote FAILED_FINAL_GATE over human/dev
            else:
                integrity.fail(msg, blocker=FAILED_FINAL_GATE)

    errors = list(integrity.errors)

    # Precedence: FAILED_DEVELOPMENT_INTEGRITY > BLOCKED_HUMAN_DUAL_LABELING > FAILED_FINAL_GATE
    blocker = integrity.blocker
    if mode == "final":
        candidate_blockers: list[str] = list(integrity.blockers)
        if development_integrity is not None and development_integrity.get("pass") is not True:
            if FAILED_DEVELOPMENT_INTEGRITY not in candidate_blockers:
                candidate_blockers.append(FAILED_DEVELOPMENT_INTEGRITY)
        man_auth = str((manifest or {}).get("label_authority") or "")
        human_pending = is_machine_authority(man_auth) or any(
            is_machine_authority(str(r.get("label_authority") or "")) for r in records
        )
        joined = " ".join(errors).lower()
        if human_pending or any(
            k in joined
            for k in (
                "human",
                "pilot",
                "seal",
                "machine",
                "reviewer",
                "adjudicat",
                "role=",
                "reviewed_at",
                "label_reviewer_a_reason",
                "label_reviewer_b_reason",
            )
        ):
            if BLOCKED_HUMAN_DUAL_LABELING not in candidate_blockers:
                candidate_blockers.append(BLOCKED_HUMAN_DUAL_LABELING)
        if (not integrity.ok or errors) and not candidate_blockers:
            candidate_blockers.append(FAILED_FINAL_GATE)
        blocker = primary_blocker(candidate_blockers)
        integrity.blockers = [b for b in candidate_blockers if b]
        integrity.blocker = blocker

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
            "development_integrity": development_integrity,
            "non_claims": [
                "Not DOD §8.4 accept",
                "Not human gold",
                "Not sealed final holdout",
                "Machine draft labels are circular-risk diagnostic only",
            ],
        }
    else:
        # Final accept only when integrity ok, no residual errors, recall met,
        # AND development integrity explicitly passes (never mask technical fail as human).
        dev_ok = bool(development_integrity and development_integrity.get("pass") is True)
        passed = (
            integrity.ok
            and not errors
            and recall >= RECALL_THRESHOLD - 1e-15
            and dev_ok
        )
        exit_code = 0 if passed else 1
        if passed:
            status = "ACCEPTED"
            result_blocker = None
            result_blockers: list[str] = []
        else:
            result_blocker = blocker or FAILED_FINAL_GATE
            result_blockers = list(integrity.blockers) if integrity.blockers else [result_blocker]
            # Hard rule: if development failed, primary cannot be human dual labeling.
            if development_integrity is not None and development_integrity.get("pass") is not True:
                if FAILED_DEVELOPMENT_INTEGRITY not in result_blockers:
                    result_blockers.insert(0, FAILED_DEVELOPMENT_INTEGRITY)
                result_blocker = primary_blocker(result_blockers) or FAILED_DEVELOPMENT_INTEGRITY
            status = result_blocker or FAILED_FINAL_GATE
        result = {
            "pass": passed,
            "status": status,
            "mode": mode,
            "acceptance_eligible": passed,
            "dod_item_accepted": False,  # only main merge + human process can set DOD [x]
            "sealed_holdout": bool(
                (manifest or {}).get("sealed_holdout") is True
                and (manifest or {}).get("sealed_before_classifier_edits") is True
            ),
            "blocker": result_blocker,
            "blockers": result_blockers,
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
            "development_integrity": development_integrity
            or {
                "path": str(resolved_dev_path) if resolved_dev_path else None,
                "manifest_path": str(resolved_dev_manifest) if resolved_dev_manifest else None,
                "sha256": None,
                "n_records": 0,
                "duplicate_ids": [],
                "holdout_overlap_count": 0,
                "holdout_overlap_ids": [],
                "pass": False,
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
        development_manifest_path=(
            Path(args.development_manifest) if getattr(args, "development_manifest", None) else None
        ),
        mode="diagnostic",
        output_path=Path(args.output) if args.output else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


def cmd_evaluate_final(args: argparse.Namespace) -> int:
    # --development and --development-manifest are required for final mode
    # (leak/hash check cannot be omitted; argparse enforces presence).
    code, result = evaluate(
        Path(args.corpus),
        manifest_path=Path(args.manifest) if args.manifest else None,
        profile_path=Path(args.profile) if args.profile else None,
        development_path=Path(args.development) if args.development else None,
        development_manifest_path=(
            Path(args.development_manifest) if args.development_manifest else None
        ),
        mode="final",
        output_path=Path(args.output) if args.output else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    # Always non-zero while blocked; emit primary blocker to stderr for meta-tests/CI.
    primary = result.get("blocker")
    if primary:
        print(str(primary), file=sys.stderr)
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
    common.add_argument("--output", default=None, help="Write result JSON")

    d = sub.add_parser(
        "diagnose",
        parents=[common],
        help="Diagnostic mode: machine drafts allowed; never accept (DIAGNOSTIC_ONLY).",
    )
    d.add_argument(
        "--development",
        default=None,
        help="Optional development split for leakage check (diagnose may omit).",
    )
    d.set_defaults(func=cmd_diagnose)

    f = sub.add_parser(
        "evaluate-final",
        parents=[common],
        help="Final accept mode: human dual labels required; fail-closed.",
    )
    f.add_argument(
        "--development",
        required=True,
        help="Development split for leak check (required non-empty; cannot be omitted).",
    )
    f.add_argument(
        "--development-manifest",
        required=True,
        help=(
            "Development corpus manifest JSON (required; corpus_sha256, role=development, "
            "acceptance_eligible=false, sealed_holdout=false, n_records)."
        ),
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
