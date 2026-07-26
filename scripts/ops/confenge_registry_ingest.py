#!/usr/bin/env python3
"""Official CNPJ registry ingestion with resume, checkpoint, and status taxonomy.

Prefer a versioned official dataset (Receita Federal open data or equivalent JSONL).
BrasilAPI is operational fallback only — never the sole release anchor.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.commercial_leads.dbutil import connect  # noqa: E402
from scripts.commercial_leads.supplier_registry import (  # noqa: E402
    ensure_registry_table,
    re_cnpj14,
    upsert_registry_rows,
)

ART = _ROOT / "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01"
CHECKPOINT = ART / "registry-ingest-checkpoint.json"
REPORT = ART / "registry-ingest-report.json"
BRASILAPI = "https://brasilapi.com.br/api/cnpj/v1"
UA = "extra-cli-confenge-registry/2.0"

STATUS_RESOLVED = "RESOLVED"
STATUS_NOT_FOUND = "NOT_FOUND_IN_OFFICIAL_DATASET"
STATUS_INVALID = "INVALID_CNPJ"
STATUS_CORRUPT = "REGISTRY_DATA_CORRUPT"
STATUS_TRANSIENT = "LOOKUP_TRANSIENT_FAILURE"
STATUS_NOT_COMPUTABLE = "NOT_COMPUTABLE"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_candidate_cnpjs(run_result: Path | None, explicit: list[str] | None) -> list[str]:
    out: list[str] = []
    if explicit:
        out.extend(explicit)
    if run_result and run_result.is_file():
        d = json.loads(run_result.read_text(encoding="utf-8"))
        lm = d.get("load_meta") or {}
        for c in lm.get("candidate_supplier_cnpjs") or []:
            out.append(str(c))
        for L in d.get("leads") or []:
            if L.get("cnpj14"):
                out.append(str(L["cnpj14"]))
    cleaned = []
    seen = set()
    for raw in out:
        c = re_cnpj14(raw)
        if not c:
            continue
        if c not in seen:
            seen.add(c)
            cleaned.append(c)
    return cleaned


def fetch_brasilapi(cnpj14: str, *, timeout: float = 12.0) -> tuple[str, dict[str, Any] | None]:
    """Return (status, row_or_none). Distinguishes NOT_FOUND from TRANSIENT."""
    url = f"{BRASILAPI}/{cnpj14}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return STATUS_NOT_FOUND, None
        return STATUS_TRANSIENT, None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return STATUS_TRANSIENT, None
    if not isinstance(raw, dict):
        return STATUS_CORRUPT, None
    cnae = raw.get("cnae_fiscal")
    cnae_desc = raw.get("cnae_fiscal_descricao")
    cnae_principal = None
    if cnae is not None:
        cnae_principal = f"{cnae}"
        if cnae_desc:
            cnae_principal = f"{cnae} - {cnae_desc}"
    secs = []
    for s in raw.get("cnaes_secundarios") or []:
        if isinstance(s, dict):
            code = s.get("codigo")
            desc = s.get("descricao")
            if code is not None:
                secs.append(f"{code}" + (f" - {desc}" if desc else ""))
        elif s:
            secs.append(str(s))
    row = {
        "cnpj14": cnpj14,
        "razao_social": raw.get("razao_social") or raw.get("nome_fantasia"),
        "nome_fantasia": raw.get("nome_fantasia"),
        "cnae_principal": cnae_principal,
        "cnaes_secundarios": secs,
        "situacao_cadastral": raw.get("descricao_situacao_cadastral")
        or raw.get("situacao_cadastral"),
        "data_situacao": raw.get("data_situacao_cadastral"),
        "municipio": raw.get("municipio"),
        "uf": raw.get("uf"),
        "natureza_juridica": raw.get("natureza_juridica") or raw.get("codigo_natureza_juridica"),
        "source": "brasilapi_fallback",
        "source_file": url,
        "source_version": "cnpj/v1",
        "source_date": date.today().isoformat(),
        "source_hash": hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()[:16],
        "ingested_at": utc_now(),
    }
    if not cnae_principal and not row.get("razao_social"):
        return STATUS_CORRUPT, None
    return STATUS_RESOLVED, row


def load_official_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    """Load versioned official CNPJ extract (preferred release anchor)."""
    by: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            c = re_cnpj14(row.get("cnpj14") or row.get("cnpj"))
            if not c:
                continue
            row = dict(row)
            row["cnpj14"] = c
            row.setdefault("source", "official_cnpj_dataset")
            row.setdefault("source_version", path.name)
            row.setdefault("source_date", date.today().isoformat())
            row.setdefault("source_file", str(path))
            by[c] = row
    return by


def run_ingest(
    *,
    dsn: str,
    cnpjs: list[str],
    official_jsonl: Path | None,
    resume: bool,
    rate_limit_s: float,
    max_retries: int,
    failures_only: bool,
) -> dict[str, Any]:
    conn = connect(dsn)
    ensure_registry_table(conn)

    ck = _load_json(CHECKPOINT) if resume else {}
    statuses: dict[str, str] = dict(ck.get("statuses") or {})
    done = set(ck.get("done") or [])
    error_counts: dict[str, int] = dict(ck.get("error_counts") or {})

    official = load_official_jsonl(official_jsonl) if official_jsonl and official_jsonl.is_file() else {}
    to_process = []
    for c in cnpjs:
        if failures_only and statuses.get(c) not in {
            None,
            STATUS_TRANSIENT,
            STATUS_NOT_COMPUTABLE,
        }:
            if c in done and statuses.get(c) not in {STATUS_TRANSIENT}:
                continue
        if resume and c in done and statuses.get(c) not in {STATUS_TRANSIENT}:
            continue
        to_process.append(c)

    upserted = 0
    rows_batch: list[dict[str, Any]] = []

    for cnpj in to_process:
        if not re_cnpj14(cnpj):
            statuses[cnpj] = STATUS_INVALID
            done.add(cnpj)
            error_counts[STATUS_INVALID] = error_counts.get(STATUS_INVALID, 0) + 1
            continue

        if cnpj in official:
            row = official[cnpj]
            rows_batch.append(row)
            statuses[cnpj] = STATUS_RESOLVED
            done.add(cnpj)
            continue

        # Fallback: BrasilAPI with exponential backoff
        status, row = STATUS_TRANSIENT, None
        delay = rate_limit_s
        for attempt in range(max_retries):
            status, row = fetch_brasilapi(cnpj)
            if status != STATUS_TRANSIENT:
                break
            time.sleep(delay)
            delay = min(delay * 2, 30.0)
        if row:
            rows_batch.append(row)
            statuses[cnpj] = STATUS_RESOLVED
            done.add(cnpj)
            upserted += 0  # counted after upsert
        else:
            statuses[cnpj] = status
            if status != STATUS_TRANSIENT:
                done.add(cnpj)
            error_counts[status] = error_counts.get(status, 0) + 1
        time.sleep(rate_limit_s)

        if len(rows_batch) >= 25:
            upserted += upsert_registry_rows(conn, rows_batch)
            rows_batch = []
            _save_json(
                CHECKPOINT,
                {
                    "updated_at": utc_now(),
                    "done": sorted(done),
                    "statuses": statuses,
                    "error_counts": error_counts,
                    "inputs": len(cnpjs),
                },
            )

    if rows_batch:
        upserted += upsert_registry_rows(conn, rows_batch)

    conn.close()

    resolved = sum(1 for s in statuses.values() if s == STATUS_RESOLVED)
    definitive = sum(
        1
        for s in statuses.values()
        if s
        in {
            STATUS_RESOLVED,
            STATUS_NOT_FOUND,
            STATUS_INVALID,
            STATUS_CORRUPT,
            STATUS_NOT_COMPUTABLE,
        }
    )
    report = {
        "ok": definitive == len(cnpjs) and len(cnpjs) > 0,
        "generated_at": utc_now(),
        "inputs": len(cnpjs),
        "processed_this_run": len(to_process),
        "upserted": upserted,
        "resolved": resolved,
        "definitive_resolution_count": definitive,
        "registry_resolved_or_definitively_not_found": (
            round(definitive / len(cnpjs), 4) if cnpjs else None
        ),
        "error_counts": error_counts,
        "status_counts": {
            s: sum(1 for v in statuses.values() if v == s) for s in sorted(set(statuses.values()))
        },
        "official_dataset_rows": len(official),
        "fallback_api": "brasilapi" if not official else "official_jsonl_preferred",
        "checkpoint": str(CHECKPOINT),
        "note": (
            "Release requires registry_resolved_or_definitively_not_found == 100% "
            "BEFORE top20 selection. HTTP timeouts are LOOKUP_TRANSIENT_FAILURE, "
            "never NOT_FOUND."
        ),
    }
    _save_json(CHECKPOINT, {
        "updated_at": utc_now(),
        "done": sorted(done),
        "statuses": statuses,
        "error_counts": error_counts,
        "inputs": len(cnpjs),
    })
    _save_json(REPORT, report)
    # Also append jsonl audit trail
    audit = ART / "registry-ingest.jsonl"
    with audit.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": utc_now(), "report": report}, ensure_ascii=False) + "\n")
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN"))
    ap.add_argument(
        "--run-result",
        type=Path,
        default=ART / "run" / "run-result.json",
    )
    ap.add_argument("--official-jsonl", type=Path, default=None)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--failures-only", action="store_true")
    ap.add_argument("--rate-limit", type=float, default=0.35)
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument("--cnpj", action="append", default=[])
    args = ap.parse_args(argv)
    if not args.dsn:
        print(json.dumps({"ok": False, "reason": "CONFENGE_COMMERCIAL_STATE_DSN required"}))
        return 2
    cnpjs = load_candidate_cnpjs(args.run_result, args.cnpj)
    if not cnpjs:
        print(json.dumps({"ok": False, "reason": "no_candidate_cnpjs"}))
        return 1
    report = run_ingest(
        dsn=args.dsn,
        cnpjs=cnpjs,
        official_jsonl=args.official_jsonl or (
            Path(os.environ["CONFENGE_OFFICIAL_CNPJ_JSONL"])
            if os.environ.get("CONFENGE_OFFICIAL_CNPJ_JSONL")
            else None
        ),
        resume=args.resume or args.failures_only,
        rate_limit_s=args.rate_limit,
        max_retries=args.max_retries,
        failures_only=args.failures_only,
    )
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
