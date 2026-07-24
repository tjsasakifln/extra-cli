#!/usr/bin/env python3
"""Stratified opportunity recall benchmark (fail-closed).

Compares system capture against an independent sample of official portal items.
Database row counts are NEVER a valid proxy for recall.

Usage:
  python -m scripts.coverage.recall_benchmark scaffold
  python -m scripts.coverage.recall_benchmark run --sample PATH
  python -m scripts.coverage.recall_benchmark evaluate --sample PATH
  python -m scripts.coverage.recall_benchmark validate-sample --sample PATH
  python -m scripts.coverage.recall_benchmark freeze-lock --sample PATH --out PATH
  python -m scripts.coverage.recall_benchmark gate --sample PATH --result PATH
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SAMPLE = PROJECT_ROOT / "output" / "coverage" / "recall_sample.json"
DEFAULT_RESULT = PROJECT_ROOT / "output" / "coverage" / "recall_benchmark.json"

# Stratified strata required by mandate / DOD §8.4
REQUIRED_STRATA = [
    "municipio_grande",
    "municipio_medio",
    "municipio_pequeno",
    "admin_direta",
    "admin_indireta",
    "autarquia",
    "fundacao",
    "camara",
    "consorcio",
    "source_api",
    "source_html",
    "source_pdf",
    "source_js",
    "platform_pncp",
    "platform_sc_compras",
    "platform_ciga",
]

MIN_UNIQUE_ITEMS = 50
MIN_PER_STRATUM = 5
GLOBAL_TARGET_PCT = 95.0
STRATUM_FLOOR_PCT = 90.0
CRITICAL_STRATA = list(REQUIRED_STRATA)  # all required are critical floors
VALID_MISS_REASONS = frozenset(
    {
        "source_gap",
        "match_gap",
        "window_gap",
        "external_unavailable",
        "other",
    }
)
FORBIDDEN_DENOMINATOR_MARKERS = (
    "count(*)",
    "count (*)",
    "operational_table_count",
    "db_row_count",
    "from opportunity_intel count",
)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def denominator_payload(sample: dict[str, Any]) -> list[dict[str, Any]]:
    """Stable identity payload for the frozen gold denominator (no capture labels)."""
    rows: list[dict[str, Any]] = []
    for item in sample.get("portal_items") or []:
        sid = str(item.get("sample_id") or "")
        if sid.startswith("EXAMPLE"):
            continue
        rows.append(
            {
                "sample_id": sid,
                "external_id": item.get("external_id"),
                "portal_url": item.get("portal_url"),
                "content_hash": item.get("content_hash"),
                "source_platform": item.get("source_platform"),
                "published_at": item.get("published_at"),
                "strata": sorted(item.get("strata") or []),
            }
        )
    rows.sort(key=lambda r: r["sample_id"])
    return rows


def denominator_hash(sample: dict[str, Any]) -> str:
    payload = denominator_payload(sample)
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def real_items(sample: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        i
        for i in (sample.get("portal_items") or [])
        if not str(i.get("sample_id", "")).startswith("EXAMPLE")
    ]


def scaffold_sample(path: Path) -> dict[str, Any]:
    """Create empty stratified sample template for manual/portal verification."""
    sample = {
        "schema_version": 2,
        "purpose": "Independent stratified recall sample — fill portal_items then run evaluate",
        "window": {
            "start": "2026-07-01",
            "end": "2026-07-17",
            "notes": "Fill with items observed on official portals during window",
        },
        "methodology": {
            "rule": "For each portal_item, check if system captured it (by official id/url/hash)",
            "forbidden": "Do not use COUNT(*) from database as recall proxy",
            "required_strata": REQUIRED_STRATA,
            "min_unique_items": MIN_UNIQUE_ITEMS,
            "min_per_stratum": MIN_PER_STRATUM,
            "global_target_pct": GLOBAL_TARGET_PCT,
            "stratum_floor_pct": STRATUM_FLOOR_PCT,
            "independence": "Sample must be selected before system matching; never from operational COUNT",
        },
        "portal_items": [
            {
                "sample_id": "EXAMPLE-001",
                "strata": ["municipio_medio", "admin_direta", "source_api", "platform_pncp"],
                "orgao_nome": "MUNICIPIO EXEMPLO",
                "cnpj": None,
                "objeto": "Reforma de prédio público — PREENCHER",
                "portal_url": "https://example.invalid/edital/1",
                "published_at": "2026-07-10",
                "source_platform": "pncp",
                "external_id": None,
                "captured_by_system": None,
                "capture_evidence": None,
                "notes": "Replace with real portal observation",
            }
        ],
        "status": "SCAFFOLD",
        "forbidden_proxy_used": False,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sample, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return sample


def validate_sample_schema(sample: dict[str, Any]) -> dict[str, Any]:
    """Structural readiness of a gold sample (before or after labeling)."""
    errors: list[str] = []
    warnings: list[str] = []
    items = real_items(sample)
    all_items = sample.get("portal_items") or []
    example_count = sum(1 for i in all_items if str(i.get("sample_id", "")).startswith("EXAMPLE"))

    if sample.get("forbidden_proxy_used") is True:
        errors.append("forbidden_proxy_used=true")
    meth = sample.get("methodology") or {}
    meth_blob = _canonical_json(meth).lower()
    for marker in FORBIDDEN_DENOMINATOR_MARKERS:
        if marker in meth_blob and "not" not in meth_blob and "forbidden" not in meth_blob:
            # only flag if methodology claims count as denominator without forbid
            pass
    if any(
        marker in str(sample.get("denominator_source", "")).lower()
        for marker in ("count(*)", "operational_table", "db_row_count")
    ):
        errors.append("denominator_source uses operational DB count proxy")

    if sample.get("status") == "SCAFFOLD" or (example_count and not items):
        errors.append("scaffold_only")

    if example_count and items:
        warnings.append(f"scaffold_examples_present={example_count}")

    ids = [str(i.get("sample_id") or "") for i in items]
    if len(ids) != len(set(ids)):
        errors.append("duplicate_sample_id")
    if any(not sid for sid in ids):
        errors.append("empty_sample_id")

    for i in items:
        if not i.get("portal_url") and not i.get("external_id") and not i.get("content_hash"):
            errors.append(f"item_{i.get('sample_id')}_missing_identity")
        if not (i.get("strata") or []):
            errors.append(f"item_{i.get('sample_id')}_missing_strata")
        if "example.invalid" in str(i.get("portal_url") or ""):
            errors.append(f"item_{i.get('sample_id')}_example_url")

    unique_n = len(items)
    if unique_n < MIN_UNIQUE_ITEMS:
        errors.append(f"insufficient_unique_items={unique_n}<{MIN_UNIQUE_ITEMS}")

    strata_counts: dict[str, int] = {s: 0 for s in REQUIRED_STRATA}
    for i in items:
        for s in i.get("strata") or []:
            if s in strata_counts:
                strata_counts[s] += 1
    missing_strata = [s for s, n in strata_counts.items() if n == 0]
    thin_strata = [s for s, n in strata_counts.items() if 0 < n < MIN_PER_STRATUM]
    if missing_strata:
        errors.append(f"missing_strata={missing_strata}")
    if thin_strata:
        errors.append(f"thin_strata={thin_strata}")

    independence = sample.get("independence") or meth.get("independence") or {}
    if isinstance(independence, str):
        independence = {"note": independence}
    if not sample.get("window"):
        errors.append("missing_window")
    if not (independence or sample.get("sample_plan_hash") or meth.get("selected_before_match")):
        warnings.append("independence_metadata_weak")

    denom_h = denominator_hash(sample) if items else None
    ready = not errors
    return {
        "ok": ready,
        "status": "READY" if ready else "NOT_READY",
        "unique_items": unique_n,
        "example_count": example_count,
        "strata_counts": strata_counts,
        "missing_strata": missing_strata,
        "thin_strata": thin_strata,
        "errors": errors,
        "warnings": warnings,
        "denominator_hash": denom_h,
        "min_unique_items": MIN_UNIQUE_ITEMS,
        "min_per_stratum": MIN_PER_STRATUM,
        "as_of": _utc_now(),
    }


def evaluate_sample(sample: dict[str, Any]) -> dict[str, Any]:
    """Evaluate labeled sample. Never returns success for PARTIAL/NOT_READY/below floor."""
    validation = validate_sample_schema(sample)
    items = real_items(sample)
    if not items:
        return {
            "status": "NOT_READY",
            "captured": None,
            "published_in_sample": None,
            "pct": None,
            "as_of": date.today().isoformat(),
            "generated_at": _utc_now(),
            "formula": "captured / published_in_sample",
            "notes": (
                "Sample still scaffold-only (EXAMPLE items). "
                "Populate portal_items from independent portal observation, "
                "set captured_by_system true/false with evidence, re-run evaluate."
            ),
            "strata_coverage": {},
            "stratum_pct": {},
            "forbidden_proxy_used": False,
            "target_pct": GLOBAL_TARGET_PCT,
            "stratum_floor_pct": STRATUM_FLOOR_PCT,
            "denominator_hash": None,
            "validation": validation,
            "gate_exit": 2,
        }

    labeled = [i for i in items if i.get("captured_by_system") is not None]
    unlabeled = len(items) - len(labeled)
    invalid_captured = [
        i for i in labeled if i.get("captured_by_system") is True and not i.get("capture_evidence")
    ]
    invalid_misses = [
        i
        for i in labeled
        if i.get("captured_by_system") is False
        and str(i.get("miss_reason") or "") not in VALID_MISS_REASONS
    ]

    published = len(items)
    captured = sum(1 for i in labeled if i.get("captured_by_system") is True)
    strata_cov: dict[str, dict[str, int]] = {}
    for i in labeled:
        for s in i.get("strata") or []:
            strata_cov.setdefault(s, {"published": 0, "captured": 0})
            strata_cov[s]["published"] += 1
            if i.get("captured_by_system") is True:
                strata_cov[s]["captured"] += 1

    # Include unlabeled in stratum published counts for denominator integrity
    for i in items:
        if i.get("captured_by_system") is not None:
            continue
        for s in i.get("strata") or []:
            strata_cov.setdefault(s, {"published": 0, "captured": 0})
            strata_cov[s]["published"] += 1

    stratum_pct: dict[str, float | None] = {}
    for s, counts in strata_cov.items():
        pub = counts["published"]
        stratum_pct[s] = (counts["captured"] / pub * 100.0) if pub else None

    missing_strata = [s for s in REQUIRED_STRATA if s not in strata_cov or strata_cov[s]["published"] == 0]
    thin_strata = [
        s
        for s in REQUIRED_STRATA
        if strata_cov.get(s, {}).get("published", 0) < MIN_PER_STRATUM
    ]

    notes_parts: list[str] = []
    if unlabeled:
        notes_parts.append(f"{unlabeled} items missing captured_by_system label")
    else:
        notes_parts.append("All real items labeled")
    if missing_strata:
        notes_parts.append(f"missing_strata={missing_strata}")
    if thin_strata:
        notes_parts.append(f"thin_strata={thin_strata}")
    if invalid_captured:
        notes_parts.append(f"captured_without_evidence={len(invalid_captured)}")
    if invalid_misses:
        notes_parts.append(f"misses_without_reason={len(invalid_misses)}")
    if published < MIN_UNIQUE_ITEMS:
        notes_parts.append(f"insufficient_unique_items={published}<{MIN_UNIQUE_ITEMS}")
    notes_parts.append(f"target recall {GLOBAL_TARGET_PCT}% global / floor {STRATUM_FLOOR_PCT}% per critical stratum")

    pct = (captured / published * 100.0) if published and not unlabeled else None

    floors_failed: list[str] = []
    if pct is not None:
        for s in CRITICAL_STRATA:
            sp = stratum_pct.get(s)
            if sp is None:
                floors_failed.append(s)
            elif sp < STRATUM_FLOOR_PCT:
                floors_failed.append(f"{s}={sp:.1f}")

    structural_ok = (
        published >= MIN_UNIQUE_ITEMS
        and not missing_strata
        and not thin_strata
        and not unlabeled
        and not invalid_captured
        and not invalid_misses
        and not validation["errors"]
        and sample.get("forbidden_proxy_used") is not True
    )

    if not structural_ok:
        if published == 0 or validation["status"] == "NOT_READY" and not labeled:
            status = "NOT_READY"
        else:
            status = "PARTIAL"
    else:
        # Fully labeled, strata ready — check recall targets
        if pct is None:
            status = "PARTIAL"
        elif pct >= GLOBAL_TARGET_PCT and not floors_failed:
            status = "PASS"
        else:
            status = "FAIL"
            if pct < GLOBAL_TARGET_PCT:
                notes_parts.append(f"global_below_target={pct:.2f}<{GLOBAL_TARGET_PCT}")
            if floors_failed:
                notes_parts.append(f"stratum_floors_failed={floors_failed}")

    # Map status → process exit (fail-closed)
    if status == "PASS":
        gate_exit = 0
    elif status in {"NOT_READY", "PARTIAL"}:
        gate_exit = 2
    else:  # FAIL
        gate_exit = 1

    return {
        "status": status,
        "captured": captured if published else None,
        "published_in_sample": published if published else None,
        "pct": pct,
        "as_of": date.today().isoformat(),
        "generated_at": _utc_now(),
        "formula": "captured / published_in_sample (independent stratified portal sample)",
        "notes": "; ".join(notes_parts),
        "strata_coverage": strata_cov,
        "stratum_pct": stratum_pct,
        "forbidden_proxy_used": bool(sample.get("forbidden_proxy_used", False)),
        "target_pct": GLOBAL_TARGET_PCT,
        "stratum_floor_pct": STRATUM_FLOOR_PCT,
        "floors_failed": floors_failed,
        "denominator_hash": denominator_hash(sample),
        "validation": {
            "unique_items": published,
            "missing_strata": missing_strata,
            "thin_strata": thin_strata,
            "unlabeled": unlabeled,
            "invalid_captured": len(invalid_captured),
            "invalid_misses": len(invalid_misses),
            "schema_errors": validation.get("errors") or [],
        },
        "gate_exit": gate_exit,
    }


def try_match_against_system(
    sample: dict[str, Any],
    dsn: str | None = None,
    *,
    fail_closed: bool = True,
) -> dict[str, Any]:
    """Auto-label from opportunity_intel by official id/url/hash.

    When fail_closed=True (default), connection/import errors raise and do not
    silently leave items unlabeled or invent misses.
    """
    import os

    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        if fail_closed:
            raise RuntimeError("psycopg2 required for auto-match (fail-closed)") from None
        sample["_match_error"] = "psycopg2_missing"
        return sample

    dsn = dsn or os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("RECALL_ISOLATED_DSN")
    if not dsn:
        if fail_closed:
            raise RuntimeError("DSN required for auto-match (LOCAL_DATALAKE_DSN / --dsn)")
        sample["_match_error"] = "dsn_missing"
        return sample

    try:
        # Short timeout so broken hosts fail closed quickly in gates/tests.
        conn = psycopg2.connect(dsn, connect_timeout=3)
    except Exception as exc:
        if fail_closed:
            raise RuntimeError(f"auto-match connection failed (fail-closed): {exc}") from exc
        sample["_match_error"] = f"connection_failed:{exc}"
        return sample

    def _row_id(row: Any) -> Any:
        if row is None:
            return None
        if isinstance(row, dict):
            return row.get("id")
        try:
            return row[0]
        except Exception:
            return None

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            for item in sample.get("portal_items") or []:
                if str(item.get("sample_id", "")).startswith("EXAMPLE"):
                    continue
                if item.get("captured_by_system") is not None:
                    continue
                ext = item.get("external_id")
                url = item.get("portal_url")
                content_hash = item.get("content_hash")
                found = False
                evidence = None
                if ext:
                    try:
                        cur.execute(
                            """
                            SELECT id, source, source_url FROM opportunity_intel
                            WHERE numero_controle_pncp = %s OR source_id = %s
                            LIMIT 1
                            """,
                            (str(ext), str(ext)),
                        )
                        row = cur.fetchone()
                    except Exception as exc:
                        if fail_closed:
                            raise RuntimeError(
                                f"auto-match query failed (fail-closed): {exc}"
                            ) from exc
                        sample["_match_error"] = f"query_failed:{exc}"
                        return sample
                    if row:
                        found = True
                        evidence = f"opportunity_intel.id={_row_id(row)}"
                if not found and url and "example.invalid" not in str(url):
                    # Exact URL match only — no substring / host-only false positives
                    try:
                        cur.execute(
                            """
                            SELECT id, source FROM opportunity_intel
                            WHERE source_url = %s OR link_edital = %s
                            LIMIT 1
                            """,
                            (url, url),
                        )
                        row = cur.fetchone()
                    except Exception as exc:
                        if fail_closed:
                            raise RuntimeError(
                                f"auto-match query failed (fail-closed): {exc}"
                            ) from exc
                        sample["_match_error"] = f"query_failed:{exc}"
                        return sample
                    if row:
                        found = True
                        evidence = f"opportunity_intel.id={_row_id(row)} exact_url"
                if not found and content_hash:
                    try:
                        cur.execute(
                            """
                            SELECT id, source FROM opportunity_intel
                            WHERE content_hash = %s
                            LIMIT 1
                            """,
                            (str(content_hash),),
                        )
                        row = cur.fetchone()
                    except Exception as exc:
                        if fail_closed:
                            raise RuntimeError(
                                f"auto-match query failed (fail-closed): {exc}"
                            ) from exc
                        sample["_match_error"] = f"query_failed:{exc}"
                        return sample
                    if row:
                        found = True
                        evidence = f"opportunity_intel.id={_row_id(row)} content_hash"
                item["captured_by_system"] = found
                if found:
                    item["capture_evidence"] = evidence
                else:
                    item["capture_evidence"] = "not_found_in_opportunity_intel"
                    if not item.get("miss_reason"):
                        item["miss_reason"] = "source_gap"
    finally:
        conn.close()
    return sample


def freeze_sample_lock(sample: dict[str, Any], meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Freeze denominator identity + methodology before matching writes."""
    validation = validate_sample_schema(sample)
    lock = {
        "schema_version": 1,
        "frozen_at": _utc_now(),
        "denominator_hash": denominator_hash(sample),
        "unique_items": validation["unique_items"],
        "strata_counts": validation["strata_counts"],
        "window": sample.get("window"),
        "sample_plan_hash": sample.get("sample_plan_hash"),
        "independence": sample.get("independence") or (sample.get("methodology") or {}).get("independence"),
        "validation_ok": validation["ok"],
        "validation_errors": validation["errors"],
        "required_strata": REQUIRED_STRATA,
        "min_unique_items": MIN_UNIQUE_ITEMS,
        "min_per_stratum": MIN_PER_STRATUM,
        "global_target_pct": GLOBAL_TARGET_PCT,
        "stratum_floor_pct": STRATUM_FLOOR_PCT,
        "item_ids": sorted(str(i.get("sample_id")) for i in real_items(sample)),
        "meta": meta or {},
    }
    return lock


def assert_denominator_unchanged(sample: dict[str, Any], lock: dict[str, Any]) -> None:
    current = denominator_hash(sample)
    expected = lock.get("denominator_hash")
    if current != expected:
        raise RuntimeError(
            f"denominator hash drift: locked={expected} current={current} "
            "(misses must remain in denominator; never shrink sample after miss)"
        )


def cmd_scaffold(args: argparse.Namespace) -> int:
    path = Path(args.output or DEFAULT_SAMPLE)
    scaffold_sample(path)
    print(f"Scaffold written: {path}")
    print("Next: replace EXAMPLE items with real portal observations, then run evaluate.")
    return 0


def cmd_validate_sample(args: argparse.Namespace) -> int:
    sample_path = Path(args.sample or DEFAULT_SAMPLE)
    if not sample_path.exists():
        print(json.dumps({"ok": False, "error": f"missing sample {sample_path}"}, indent=2))
        return 2
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    result = validate_sample_schema(sample)
    out = Path(args.output) if args.output else None
    text = json.dumps(result, indent=2, ensure_ascii=False)
    print(text)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    return 0 if result["ok"] else 2


def cmd_freeze_lock(args: argparse.Namespace) -> int:
    sample_path = Path(args.sample or DEFAULT_SAMPLE)
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    lock = freeze_sample_lock(sample)
    out = Path(args.output or (sample_path.parent / "sample-lock.json"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(lock, indent=2, ensure_ascii=False))
    print(f"Wrote {out}")
    # Freeze may run before labels; still fail if sample is scaffold/too thin when --require-ready
    if args.require_ready and not lock["validation_ok"]:
        return 2
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    sample_path = Path(args.sample or DEFAULT_SAMPLE)
    if not sample_path.exists():
        scaffold_sample(sample_path)
    sample = json.loads(sample_path.read_text(encoding="utf-8"))

    if getattr(args, "lock", None):
        lock = json.loads(Path(args.lock).read_text(encoding="utf-8"))
        assert_denominator_unchanged(sample, lock)

    if args.auto_match:
        fail_closed = not getattr(args, "soft_match", False)
        try:
            sample = try_match_against_system(sample, dsn=args.dsn, fail_closed=fail_closed)
        except RuntimeError as exc:
            err = {
                "status": "NOT_READY",
                "error": str(exc),
                "forbidden_proxy_used": False,
                "gate_exit": 2,
            }
            out = Path(args.output or DEFAULT_RESULT)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(err, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(json.dumps(err, indent=2, ensure_ascii=False))
            return 2
        if not getattr(args, "no_write_sample", False):
            sample_path.write_text(
                json.dumps(sample, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )

    result = evaluate_sample(sample)
    out = Path(args.output or DEFAULT_RESULT)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"Wrote {out}")
    # Fail-closed: non-PASS exits non-zero
    return int(result.get("gate_exit", 1 if result.get("status") != "PASS" else 0))


def cmd_gate(args: argparse.Namespace) -> int:
    """Evaluate and enforce exit codes; optional compare to lock hash."""
    rc = cmd_run(args)
    result_path = Path(args.output or DEFAULT_RESULT)
    if result_path.exists():
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("forbidden_proxy_used"):
            return 2
        if result.get("status") == "PASS" and result.get("pct") is not None:
            if float(result["pct"]) < GLOBAL_TARGET_PCT:
                return 1
    return rc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Stratified opportunity recall benchmark (fail-closed)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scaffold", help="Create empty stratified sample template")
    s.add_argument("--output", "-o", default=str(DEFAULT_SAMPLE))
    s.set_defaults(func=cmd_scaffold)

    v = sub.add_parser("validate-sample", help="Validate gold sample readiness (schema/strata/size)")
    v.add_argument("--sample", default=str(DEFAULT_SAMPLE))
    v.add_argument("--output", "-o", default=None)
    v.set_defaults(func=cmd_validate_sample)

    f = sub.add_parser("freeze-lock", help="Freeze denominator hash before matching")
    f.add_argument("--sample", default=str(DEFAULT_SAMPLE))
    f.add_argument("--output", "-o", default=None)
    f.add_argument("--require-ready", action="store_true")
    f.set_defaults(func=cmd_freeze_lock)

    r = sub.add_parser("run", help="Evaluate sample and write recall_benchmark.json")
    r.add_argument("--sample", default=str(DEFAULT_SAMPLE))
    r.add_argument("--output", "-o", default=str(DEFAULT_RESULT))
    r.add_argument("--auto-match", action="store_true", help="Match portal items against DB")
    r.add_argument("--dsn", default=None)
    r.add_argument("--lock", default=None, help="sample-lock.json to assert denominator stability")
    r.add_argument(
        "--soft-match",
        action="store_true",
        help="DEPRECATED softness: allow match errors (default fail-closed)",
    )
    r.add_argument("--no-write-sample", action="store_true")
    r.set_defaults(func=cmd_run)

    e = sub.add_parser("evaluate", help="Alias for run")
    e.add_argument("--sample", default=str(DEFAULT_SAMPLE))
    e.add_argument("--output", "-o", default=str(DEFAULT_RESULT))
    e.add_argument("--auto-match", action="store_true")
    e.add_argument("--dsn", default=None)
    e.add_argument("--lock", default=None)
    e.add_argument("--soft-match", action="store_true")
    e.add_argument("--no-write-sample", action="store_true")
    e.set_defaults(func=cmd_run)

    g = sub.add_parser("gate", help="Fail-closed gate (exit non-zero unless PASS)")
    g.add_argument("--sample", default=str(DEFAULT_SAMPLE))
    g.add_argument("--output", "-o", default=str(DEFAULT_RESULT))
    g.add_argument("--auto-match", action="store_true")
    g.add_argument("--dsn", default=None)
    g.add_argument("--lock", default=None)
    g.add_argument("--soft-match", action="store_true")
    g.add_argument("--no-write-sample", action="store_true")
    g.set_defaults(func=cmd_gate)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
