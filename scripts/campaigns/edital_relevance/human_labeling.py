#!/usr/bin/env python3
"""Human dual-label workflow for edital relevance (blind packages + import).

This module NEVER auto-fills labels and NEVER acts as a human reviewer.
It only:

1. Generates blind labeling packages (no system class/score/machine labels).
2. Imports human responses.
3. Validates distinct identities, timestamps, completeness, duplicates.
4. Detects divergences and requires explicit adjudication.
5. Never silently converts UNDECIDABLE.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ALLOWED_LABELS = frozenset({"RELEVANT", "IRRELEVANT", "UNDECIDABLE"})
# Immutable content fields: humans may only edit label/reason.
IMMUTABLE_FIELDS = (
    "official_id",
    "source",
    "url",
    "titulo",
    "objeto",
    "observed_at",
)
BLIND_COLUMNS = (
    *IMMUTABLE_FIELDS,
    "label",
    "reason",
)
# Fields that must never appear in a blind package (inducement risk)
FORBIDDEN_BLIND_FIELDS = frozenset(
    {
        "label_final",
        "label_reviewer_a",
        "label_reviewer_b",
        "label_authority",
        "system_class",
        "predicted_label",
        "score",
        "confidence",
        "selected_by_classifier",
        "adjudication_reason",
        "labels_agreed",
        "human_reviewer_a_id",
        "human_reviewer_b_id",
        "reviewers",
        "rule_version",
        "classifier_label",
        "machine_label",
        "error_hint",
        "false_negative",
        "false_positive",
    }
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if not isinstance(obj, dict):
            raise ValueError(f"{path}:{i} not an object")
        rows.append(obj)
    return rows


def record_to_blind_row(rec: dict[str, Any]) -> dict[str, str]:
    """Project a candidate record to blind package columns only."""
    return {
        "official_id": str(rec.get("official_id") or "").strip(),
        "source": str(rec.get("source") or "").strip(),
        "url": str(rec.get("url") or "").strip(),
        "titulo": str(rec.get("titulo") or "").strip(),
        "objeto": str(rec.get("objeto") or "").strip(),
        "observed_at": str(rec.get("observed_at") or "").strip(),
        "label": "",
        "reason": "",
    }


def generate_blind_packages(
    records: list[dict[str, Any]],
    *,
    out_a: Path,
    out_b: Path,
    seed_a: int = 42,
    seed_b: int = 97,
) -> dict[str, Any]:
    """Write two blind CSVs for the same ID set with independent row order."""
    if not records:
        raise ValueError("no records for blind packages")

    base_rows = [record_to_blind_row(r) for r in records]
    for row in base_rows:
        if not row["official_id"]:
            raise ValueError("record missing official_id")
        if not row["url"]:
            raise ValueError(f"{row['official_id']}: missing url for blind package")

    ids = sorted(r["official_id"] for r in base_rows)
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate official_id in source records")

    by_id = {r["official_id"]: r for r in base_rows}

    def _write(path: Path, order: list[str]) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(BLIND_COLUMNS))
            w.writeheader()
            for oid in order:
                w.writerow(by_id[oid])
        return hashlib.sha256(path.read_bytes()).hexdigest()

    # Deterministic shuffle for blind package order only (not cryptographic).
    order_a = ids[:]
    rng_a = random.Random(seed_a)  # noqa: S311
    rng_a.shuffle(order_a)
    order_b = ids[:]
    rng_b = random.Random(seed_b)  # noqa: S311
    rng_b.shuffle(order_b)

    sha_a = _write(out_a, order_a)
    sha_b = _write(out_b, order_b)

    return {
        "n": len(ids),
        "ids_sha256": hashlib.sha256("\n".join(ids).encode()).hexdigest(),
        "package_a": str(out_a),
        "package_b": str(out_b),
        "package_a_sha256": sha_a,
        "package_b_sha256": sha_b,
        "columns": list(BLIND_COLUMNS),
        "label_cells_empty": True,
        "forbidden_fields_excluded": sorted(FORBIDDEN_BLIND_FIELDS),
    }


def read_blind_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"{path}: empty CSV")
        cols = [c.strip() for c in reader.fieldnames]
        if cols != list(BLIND_COLUMNS):
            raise ValueError(f"{path}: columns must be exactly {list(BLIND_COLUMNS)}; got {cols}")
        # inducement check
        for c in cols:
            if c in FORBIDDEN_BLIND_FIELDS:
                raise ValueError(f"{path}: forbidden inducement column {c}")
        rows: list[dict[str, str]] = []
        for row in reader:
            rows.append({k: (row.get(k) or "").strip() for k in BLIND_COLUMNS})
        return rows


@dataclass
class ImportReport:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    divergences: list[dict[str, Any]] = field(default_factory=list)
    records: list[dict[str, Any]] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.ok = False
        self.errors.append(msg)


def _parse_ts(value: str, *, field_name: str, rep: ImportReport) -> str | None:
    v = (value or "").strip()
    if not v:
        rep.fail(f"missing {field_name}")
        return None
    # Accept ISO-8601; reject obvious placeholders
    if v.lower() in {"tbd", "pending", "null", "none"}:
        rep.fail(f"invalid {field_name}={v!r}")
        return None
    try:
        # fromisoformat handles offset or Z after normalize
        normalized = v.replace("Z", "+00:00")
        datetime.fromisoformat(normalized)
    except ValueError:
        rep.fail(f"invalid timestamp {field_name}={v!r}")
        return None
    return v


def _immutable_snapshot(row: dict[str, Any]) -> dict[str, str]:
    return {f: str(row.get(f) or "").strip() for f in IMMUTABLE_FIELDS}


def import_human_labels(
    *,
    package_a: Path,
    package_b: Path,
    reviewer_a_id: str,
    reviewer_b_id: str,
    reviewed_at_a: str,
    reviewed_at_b: str,
    expected_corpus: Path | None = None,
    expected_ids: set[str] | None = None,
    expected_records: dict[str, dict[str, Any]] | None = None,
    adjudication: dict[str, dict[str, str]] | None = None,
) -> ImportReport:
    """Import two filled human packages and validate dual-label integrity.

    ``adjudication`` maps official_id → {label, reason} for every divergence.
    Labels are never auto-filled. UNDECIDABLE is never silently converted.
    Immutable content fields must match the expected corpus and A↔B packages.
    Only ``label`` and ``reason`` may be edited by humans.
    """
    rep = ImportReport()
    ra = (reviewer_a_id or "").strip()
    rb = (reviewer_b_id or "").strip()
    if not ra or not rb:
        rep.fail("reviewer_id required for both reviewers")
        return rep
    if ra == rb:
        rep.fail("reviewer_a and reviewer_b must be distinct human identities")
        return rep
    if ra.lower().startswith("criteria_") or rb.lower().startswith("criteria_"):
        rep.fail("machine criteria engines are not human reviewers")
        return rep
    if "machine" in ra.lower() or "machine" in rb.lower():
        rep.fail("machine identities are not human reviewers")
        return rep

    ts_a = _parse_ts(reviewed_at_a, field_name="reviewed_at_a", rep=rep)
    ts_b = _parse_ts(reviewed_at_b, field_name="reviewed_at_b", rep=rep)
    if not rep.ok:
        return rep

    # Load expected corpus (required at CLI; optional only for pure unit helpers
    # that already supply expected_records / expected_ids).
    exp_by_id: dict[str, dict[str, Any]] = dict(expected_records or {})
    if expected_corpus is not None:
        if not expected_corpus.is_file():
            rep.fail(f"expected corpus missing: {expected_corpus}")
            return rep
        for rec in load_jsonl(expected_corpus):
            oid = str(rec.get("official_id") or "").strip()
            if not oid:
                continue
            if oid in exp_by_id:
                rep.fail(f"expected corpus duplicate official_id {oid}")
                continue
            exp_by_id[oid] = rec
    if expected_ids is None and exp_by_id:
        expected_ids = set(exp_by_id)

    rows_a = read_blind_csv(package_a)
    rows_b = read_blind_csv(package_b)

    def _index(rows: list[dict[str, str]], which: str) -> dict[str, dict[str, str]]:
        out: dict[str, dict[str, str]] = {}
        for r in rows:
            oid = r["official_id"]
            if not oid:
                rep.fail(f"{which}: row missing official_id")
                continue
            if oid in out:
                rep.fail(f"{which}: duplicate official_id {oid}")
                continue
            out[oid] = r
        return out

    idx_a = _index(rows_a, "package_a")
    idx_b = _index(rows_b, "package_b")
    if not rep.ok:
        return rep

    ids_a = set(idx_a)
    ids_b = set(idx_b)
    if ids_a != ids_b:
        only_a = sorted(ids_a - ids_b)[:10]
        only_b = sorted(ids_b - ids_a)[:10]
        rep.fail(f"ID set mismatch between packages (only_a={only_a} only_b={only_b})")
        return rep

    if expected_ids is not None and ids_a != expected_ids:
        missing = sorted(expected_ids - ids_a)[:10]
        extra = sorted(ids_a - expected_ids)[:10]
        rep.fail(f"ID set mismatch vs expected (missing={missing} extra={extra})")
        return rep

    adjudication = adjudication or {}
    merged: list[dict[str, Any]] = []

    for oid in sorted(ids_a):
        a = idx_a[oid]
        b = idx_b[oid]
        snap_a = _immutable_snapshot(a)
        snap_b = _immutable_snapshot(b)
        if snap_a != snap_b:
            for field in IMMUTABLE_FIELDS:
                if snap_a[field] != snap_b[field]:
                    rep.fail(
                        f"{oid}: immutable field {field} differs between packages A/B "
                        f"(a={snap_a[field]!r} b={snap_b[field]!r})"
                    )
            continue
        if exp_by_id:
            exp = exp_by_id.get(oid)
            if exp is None:
                rep.fail(f"{oid}: not present in expected corpus")
                continue
            snap_exp = _immutable_snapshot(exp)
            if snap_a != snap_exp:
                for field in IMMUTABLE_FIELDS:
                    if snap_a[field] != snap_exp[field]:
                        rep.fail(
                            f"{oid}: immutable field {field} was edited "
                            f"(package={snap_a[field]!r} expected={snap_exp[field]!r})"
                        )
                continue

        la = (a.get("label") or "").strip().upper()
        lb = (b.get("label") or "").strip().upper()
        ra_reason = str(a.get("reason") or "").strip()
        rb_reason = str(b.get("reason") or "").strip()
        if not la or not lb:
            rep.fail(f"{oid}: empty label (auto-fill forbidden)")
            continue
        if la not in ALLOWED_LABELS:
            rep.fail(f"{oid}: invalid label from reviewer_a={la!r}")
            continue
        if lb not in ALLOWED_LABELS:
            rep.fail(f"{oid}: invalid label from reviewer_b={lb!r}")
            continue
        if not ra_reason:
            rep.fail(f"{oid}: empty reason from reviewer_a (required)")
            continue
        if not rb_reason:
            rep.fail(f"{oid}: empty reason from reviewer_b (required)")
            continue

        agreed = la == lb
        final_label = la if agreed else ""
        adj_reason = ""
        if not agreed:
            adj = adjudication.get(oid) or adjudication.get(str(oid))
            if not adj or not str(adj.get("label") or "").strip():
                rep.fail(f"{oid}: divergence {la} vs {lb} requires explicit adjudication")
                rep.divergences.append(
                    {
                        "official_id": oid,
                        "label_a": la,
                        "label_b": lb,
                        "adjudicated": False,
                    }
                )
                continue
            final_label = str(adj["label"]).strip().upper()
            adj_reason = str(adj.get("reason") or "").strip()
            if final_label not in ALLOWED_LABELS:
                rep.fail(f"{oid}: invalid adjudication label={final_label!r}")
                continue
            if not adj_reason:
                rep.fail(f"{oid}: adjudication requires non-empty reason")
                continue
            # forbid silent UNDECIDABLE → IRRELEVANT without explicit reason content
            if (
                final_label == "IRRELEVANT"
                and (la == "UNDECIDABLE" or lb == "UNDECIDABLE")
                and adj_reason.lower() in {"", "silent_undecidable", "auto"}
            ):
                rep.fail(f"{oid}: UNDECIDABLE must not be silently converted to IRRELEVANT")
                continue
            rep.divergences.append(
                {
                    "official_id": oid,
                    "label_a": la,
                    "label_b": lb,
                    "label_final": final_label,
                    "adjudicated": True,
                    "reason": adj_reason,
                }
            )
        else:
            adj_reason = f"agreement:{la}"

        merged.append(
            {
                "official_id": oid,
                "source": snap_a["source"],
                "url": snap_a["url"],
                "titulo": snap_a["titulo"],
                "objeto": snap_a["objeto"],
                "observed_at": snap_a["observed_at"],
                "label_reviewer_a": la,
                "label_reviewer_b": lb,
                "label_reviewer_a_reason": ra_reason,
                "label_reviewer_b_reason": rb_reason,
                "label_final": final_label,
                "labels_agreed": agreed,
                "adjudication_reason": adj_reason,
                "human_reviewer_a_id": ra,
                "human_reviewer_b_id": rb,
                "reviewed_at_a": ts_a,
                "reviewed_at_b": ts_b,
                "label_authority": "human_dual_independent",
                "pilot_human_approval": False,
            }
        )

    rep.records = merged
    return rep


def cmd_generate_blind(args: argparse.Namespace) -> int:
    records = load_jsonl(Path(args.corpus))
    if args.limit:
        records = records[: int(args.limit)]
    meta = generate_blind_packages(
        records,
        out_a=Path(args.out_a),
        out_b=Path(args.out_b),
        seed_a=int(args.seed_a),
        seed_b=int(args.seed_b),
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    adjudication: dict[str, dict[str, str]] = {}
    if args.adjudication:
        raw = json.loads(Path(args.adjudication).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            print(json.dumps({"ok": False, "errors": ["adjudication file must be object"]}))
            return 1
        adjudication = {str(k): dict(v) for k, v in raw.items()}

    rep = import_human_labels(
        package_a=Path(args.package_a),
        package_b=Path(args.package_b),
        reviewer_a_id=args.reviewer_a_id,
        reviewer_b_id=args.reviewer_b_id,
        reviewed_at_a=args.reviewed_at_a,
        reviewed_at_b=args.reviewed_at_b,
        expected_corpus=Path(args.expected_corpus),
        adjudication=adjudication,
    )
    out = {
        "ok": rep.ok,
        "errors": rep.errors,
        "warnings": rep.warnings,
        "n_records": len(rep.records),
        "divergences": rep.divergences,
        "label_authority": "human_dual_independent" if rep.ok else None,
        "auto_filled": False,
    }
    if args.output and rep.ok:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as fh:
            for rec in rep.records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        out["output"] = str(out_path)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if rep.ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Blind human labeling packages + import validation")
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate-blind", help="Generate two blind CSV packages")
    g.add_argument("--corpus", required=True, help="Source JSONL (candidate pool / pilot)")
    g.add_argument("--out-a", required=True)
    g.add_argument("--out-b", required=True)
    g.add_argument("--limit", type=int, default=None)
    g.add_argument("--seed-a", type=int, default=42)
    g.add_argument("--seed-b", type=int, default=97)
    g.set_defaults(func=cmd_generate_blind)

    i = sub.add_parser("import", help="Import and validate two human-filled packages")
    i.add_argument("--package-a", required=True)
    i.add_argument("--package-b", required=True)
    i.add_argument("--reviewer-a-id", required=True)
    i.add_argument("--reviewer-b-id", required=True)
    i.add_argument("--reviewed-at-a", required=True)
    i.add_argument("--reviewed-at-b", required=True)
    i.add_argument("--adjudication", default=None, help="JSON map of divergences → label/reason")
    i.add_argument(
        "--expected-corpus",
        required=True,
        help="Expected source corpus JSONL (IDs + immutable fields must match A/B packages).",
    )
    i.add_argument("--output", default=None, help="Write merged human-labeled JSONL")
    i.set_defaults(func=cmd_import)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
