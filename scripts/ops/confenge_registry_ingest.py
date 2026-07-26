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
MINHARECEITA = "https://minhareceita.org"
CNPJWS = "https://publica.cnpj.ws/cnpj"
UA = "extra-cli-confenge-registry/2.1"

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


def _http_json(url: str, *, timeout: float = 12.0) -> tuple[str, dict[str, Any] | None]:
    """GET JSON. Returns (STATUS_*, payload). Distinguishes 404 from transient."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return STATUS_NOT_FOUND, None
        if exc.code in {429, 502, 503, 504}:
            return STATUS_TRANSIENT, None
        return STATUS_TRANSIENT, None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return STATUS_TRANSIENT, None
    if not isinstance(raw, dict):
        return STATUS_CORRUPT, None
    return STATUS_RESOLVED, raw


def _normalize_brasilapi_like(cnpj14: str, raw: dict[str, Any], *, source: str, url: str, version: str) -> dict[str, Any] | None:
    cnae = raw.get("cnae_fiscal") or raw.get("cnae") or raw.get("cnae_principal")
    cnae_desc = raw.get("cnae_fiscal_descricao") or raw.get("cnae_descricao")
    # cnpj.ws shape
    if cnae is None and isinstance(raw.get("estabelecimento"), dict):
        est = raw["estabelecimento"]
        at = est.get("atividade_principal") or {}
        if isinstance(at, dict):
            cnae = at.get("id") or at.get("codigo")
            cnae_desc = at.get("descricao") or cnae_desc
        raw = {
            **raw,
            "razao_social": raw.get("razao_social"),
            "nome_fantasia": est.get("nome_fantasia") or raw.get("nome_fantasia"),
            "descricao_situacao_cadastral": (est.get("situacao_cadastral") or {}).get("descricao")
            if isinstance(est.get("situacao_cadastral"), dict)
            else est.get("situacao_cadastral"),
            "municipio": (est.get("cidade") or {}).get("nome")
            if isinstance(est.get("cidade"), dict)
            else est.get("municipio"),
            "uf": (est.get("estado") or {}).get("sigla")
            if isinstance(est.get("estado"), dict)
            else est.get("uf"),
            "cnaes_secundarios": est.get("atividades_secundarias") or [],
        }
    cnae_principal = None
    if cnae is not None:
        cnae_principal = f"{cnae}"
        if cnae_desc:
            cnae_principal = f"{cnae} - {cnae_desc}"
    secs: list[str] = []
    for s in raw.get("cnaes_secundarios") or raw.get("atividades_secundarias") or []:
        if isinstance(s, dict):
            code = s.get("codigo") or s.get("id") or s.get("code")
            desc = s.get("descricao") or s.get("text")
            if code is not None:
                secs.append(f"{code}" + (f" - {desc}" if desc else ""))
        elif s:
            secs.append(str(s))
    row = {
        "cnpj14": cnpj14,
        "razao_social": raw.get("razao_social") or raw.get("nome_fantasia") or raw.get("nome"),
        "nome_fantasia": raw.get("nome_fantasia"),
        "cnae_principal": cnae_principal,
        "cnaes_secundarios": secs,
        "situacao_cadastral": raw.get("descricao_situacao_cadastral")
        or raw.get("situacao_cadastral")
        or raw.get("situacao"),
        "data_situacao": raw.get("data_situacao_cadastral") or raw.get("data_situacao"),
        "municipio": raw.get("municipio") or raw.get("cidade"),
        "uf": raw.get("uf"),
        "natureza_juridica": raw.get("natureza_juridica")
        or raw.get("codigo_natureza_juridica")
        or raw.get("natureza_juridica_codigo"),
        "source": source,
        "source_file": url,
        "source_version": version,
        "source_date": date.today().isoformat(),
        "source_hash": hashlib.sha256(
            json.dumps(raw, sort_keys=True, default=str).encode()
        ).hexdigest()[:16],
        "ingested_at": utc_now(),
    }
    if not row.get("cnae_principal") and not row.get("razao_social"):
        return None
    return row


def fetch_brasilapi(cnpj14: str, *, timeout: float = 12.0) -> tuple[str, dict[str, Any] | None]:
    """Multi-source cadastral lookup. Prefer BrasilAPI → MinhaReceita → cnpj.ws."""
    sources = [
        ("brasilapi_fallback", f"{BRASILAPI}/{cnpj14}", "cnpj/v1"),
        ("minhareceita_fallback", f"{MINHARECEITA}/{cnpj14}", "minhareceita/v1"),
        ("cnpjws_fallback", f"{CNPJWS}/{cnpj14}", "publica.cnpj.ws/v1"),
    ]
    saw_not_found = 0
    last_transient = False
    for source, url, version in sources:
        st, raw = _http_json(url, timeout=timeout)
        if st == STATUS_RESOLVED and raw:
            row = _normalize_brasilapi_like(cnpj14, raw, source=source, url=url, version=version)
            if row:
                return STATUS_RESOLVED, row
            return STATUS_CORRUPT, None
        if st == STATUS_NOT_FOUND:
            saw_not_found += 1
            continue
        if st == STATUS_TRANSIENT:
            last_transient = True
            continue
        if st == STATUS_CORRUPT:
            return STATUS_CORRUPT, None
    # Definitive not found only if at least one source returned 404 and none resolved
    if saw_not_found >= 1 and not last_transient:
        return STATUS_NOT_FOUND, None
    if saw_not_found >= 2:
        # majority 404 across sources
        return STATUS_NOT_FOUND, None
    return STATUS_TRANSIENT, None


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


def _seed_from_db(conn: Any, cnpjs: list[str], statuses: dict[str, str], done: set[str]) -> int:
    """Mark already-ingested registry rows as RESOLVED (idempotent)."""
    from scripts.commercial_leads.dbutil import fetch_all

    n = 0
    for i in range(0, len(cnpjs), 500):
        batch = cnpjs[i : i + 500]
        rows = fetch_all(
            conn,
            "SELECT cnpj14 FROM public.supplier_registry WHERE cnpj14 = ANY(%s)",
            (batch,),
        )
        for r in rows:
            c = str(r["cnpj14"])
            statuses[c] = STATUS_RESOLVED
            done.add(c)
            n += 1
    return n


def _fetch_with_retries(cnpj: str, max_retries: int, rate_limit_s: float) -> tuple[str, dict[str, Any] | None]:
    status, row = STATUS_TRANSIENT, None
    delay = max(rate_limit_s, 0.05)
    for _ in range(max_retries):
        status, row = fetch_brasilapi(cnpj, timeout=15.0)
        if status != STATUS_TRANSIENT:
            return status, row
        time.sleep(delay)
        delay = min(delay * 2, 20.0)
    return status, row


def run_ingest(
    *,
    dsn: str,
    cnpjs: list[str],
    official_jsonl: Path | None,
    resume: bool,
    rate_limit_s: float,
    max_retries: int,
    failures_only: bool,
    workers: int = 8,
    export_official_path: Path | None = None,
) -> dict[str, Any]:
    """Ingest full candidate universe with resume + parallel API fallback.

    Prefer versioned official JSONL. BrasilAPI is fallback only.
    HTTP timeout → LOOKUP_TRANSIENT_FAILURE (never NOT_FOUND).
    HTTP 404 → NOT_FOUND_IN_OFFICIAL_DATASET (definitive).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    conn = connect(dsn)
    ensure_registry_table(conn)

    ck = _load_json(CHECKPOINT) if resume else {}
    statuses: dict[str, str] = dict(ck.get("statuses") or {})
    done: set[str] = set(ck.get("done") or [])
    error_counts: dict[str, int] = dict(ck.get("error_counts") or {})

    # Seed from existing DB rows (idempotent)
    seeded = _seed_from_db(conn, cnpjs, statuses, done)

    official = load_official_jsonl(official_jsonl) if official_jsonl and official_jsonl.is_file() else {}
    to_process: list[str] = []
    for c in cnpjs:
        if not re_cnpj14(c):
            statuses[c] = STATUS_INVALID
            done.add(c)
            error_counts[STATUS_INVALID] = error_counts.get(STATUS_INVALID, 0) + 1
            continue
        if failures_only:
            if statuses.get(c) not in {None, STATUS_TRANSIENT, STATUS_NOT_COMPUTABLE}:
                if c in done and statuses.get(c) != STATUS_TRANSIENT:
                    continue
        if resume and c in done and statuses.get(c) not in {STATUS_TRANSIENT, None}:
            continue
        if c in official:
            continue  # handled below as batch
        if c in done and statuses.get(c) == STATUS_RESOLVED:
            continue
        to_process.append(c)

    # Official JSONL rows first (preferred release anchor)
    official_rows: list[dict[str, Any]] = []
    for c in cnpjs:
        if c in official and statuses.get(c) != STATUS_RESOLVED:
            official_rows.append(official[c])
            statuses[c] = STATUS_RESOLVED
            done.add(c)
    upserted = 0
    if official_rows:
        upserted += upsert_registry_rows(conn, official_rows)

    # Parallel BrasilAPI for remainder
    api_rows: list[dict[str, Any]] = []
    processed = 0
    workers = max(1, min(int(workers), 16))

    def _one(cnpj: str) -> tuple[str, str, dict[str, Any] | None]:
        time.sleep(rate_limit_s * (0.3 + 0.1 * (hash(cnpj) % 5)))  # jitter
        st, row = _fetch_with_retries(cnpj, max_retries, rate_limit_s)
        return cnpj, st, row

    if to_process:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_one, c): c for c in to_process}
            for fut in as_completed(futs):
                cnpj, st, row = fut.result()
                processed += 1
                if row and st == STATUS_RESOLVED:
                    api_rows.append(row)
                    statuses[cnpj] = STATUS_RESOLVED
                    done.add(cnpj)
                else:
                    statuses[cnpj] = st
                    if st != STATUS_TRANSIENT:
                        done.add(cnpj)
                    error_counts[st] = error_counts.get(st, 0) + 1
                if len(api_rows) >= 40:
                    upserted += upsert_registry_rows(conn, api_rows)
                    api_rows = []
                    _save_json(
                        CHECKPOINT,
                        {
                            "updated_at": utc_now(),
                            "done": sorted(done),
                            "statuses": statuses,
                            "error_counts": error_counts,
                            "inputs": len(cnpjs),
                            "progress": processed,
                            "to_process": len(to_process),
                        },
                    )
                if processed % 200 == 0:
                    _save_json(
                        CHECKPOINT,
                        {
                            "updated_at": utc_now(),
                            "done": sorted(done),
                            "statuses": statuses,
                            "error_counts": error_counts,
                            "inputs": len(cnpjs),
                            "progress": processed,
                            "to_process": len(to_process),
                        },
                    )

    if api_rows:
        upserted += upsert_registry_rows(conn, api_rows)

    # Export versioned snapshot of resolved registry for the candidate universe
    export_path = export_official_path or (ART / "official-cnpj-registry-snapshot.jsonl")
    from scripts.commercial_leads.dbutil import fetch_all

    export_n = 0
    with export_path.open("w", encoding="utf-8") as ef:
        for i in range(0, len(cnpjs), 500):
            batch = cnpjs[i : i + 500]
            rows = fetch_all(
                conn,
                """
                SELECT cnpj14, razao_social, nome_fantasia, cnae_principal,
                       cnaes_secundarios, situacao_cadastral, data_situacao,
                       municipio, uf, source, source_version, source_date, ingested_at
                FROM public.supplier_registry WHERE cnpj14 = ANY(%s)
                """,
                (batch,),
            )
            for r in rows:
                out = dict(r)
                for k, v in list(out.items()):
                    if hasattr(v, "isoformat"):
                        out[k] = v.isoformat()
                out["source_file"] = str(export_path.name)
                out["source_hash"] = hashlib.sha256(
                    json.dumps(out, sort_keys=True, default=str).encode()
                ).hexdigest()[:16]
                ef.write(json.dumps(out, ensure_ascii=False, default=str) + "\n")
                export_n += 1

    # Status map for every candidate (reconciliation)
    for c in cnpjs:
        if c not in statuses:
            statuses[c] = STATUS_TRANSIENT
            error_counts[STATUS_TRANSIENT] = error_counts.get(STATUS_TRANSIENT, 0) + 1

    conn.close()

    resolved = sum(1 for c in cnpjs if statuses.get(c) == STATUS_RESOLVED)
    definitive = sum(
        1
        for c in cnpjs
        if statuses.get(c)
        in {
            STATUS_RESOLVED,
            STATUS_NOT_FOUND,
            STATUS_INVALID,
            STATUS_CORRUPT,
            STATUS_NOT_COMPUTABLE,
        }
    )
    unresolved_by_reason: dict[str, int] = {}
    for c in cnpjs:
        st = statuses.get(c) or STATUS_TRANSIENT
        if st != STATUS_RESOLVED:
            unresolved_by_reason[st] = unresolved_by_reason.get(st, 0) + 1

    report = {
        "ok": definitive == len(cnpjs) and len(cnpjs) > 0,
        "generated_at": utc_now(),
        "inputs": len(cnpjs),
        "processed_this_run": processed,
        "seeded_from_db": seeded,
        "upserted": upserted,
        "resolved": resolved,
        "definitive_resolution_count": definitive,
        "registry_resolved_or_definitively_not_found": (
            round(definitive / len(cnpjs), 4) if cnpjs else None
        ),
        "unresolved_by_reason": unresolved_by_reason,
        "error_counts": error_counts,
        "status_counts": {
            s: sum(1 for c in cnpjs if statuses.get(c) == s)
            for s in sorted({statuses.get(c) for c in cnpjs})
        },
        "official_dataset_rows": len(official),
        "exported_registry_jsonl": str(export_path),
        "exported_registry_n": export_n,
        "workers": workers,
        "fallback_api": "brasilapi" if not official else "official_jsonl_preferred+brasilapi_gapfill",
        "checkpoint": str(CHECKPOINT),
        "note": (
            "Release requires registry_resolved_or_definitively_not_found == 100% "
            "BEFORE top20 selection. HTTP timeouts are LOOKUP_TRANSIENT_FAILURE, "
            "never NOT_FOUND. Official JSONL is preferred; BrasilAPI is fallback."
        ),
    }
    _save_json(
        CHECKPOINT,
        {
            "updated_at": utc_now(),
            "done": sorted(done),
            "statuses": statuses,
            "error_counts": error_counts,
            "inputs": len(cnpjs),
            "candidate_cnpjs": cnpjs,
        },
    )
    _save_json(REPORT, report)
    audit = ART / "registry-ingest.jsonl"
    with audit.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": utc_now(), "report": report}, ensure_ascii=False) + "\n")
    # Persist resolution status side-car for coverage_report
    _save_json(ART / "registry-resolution-status.json", {
        "generated_at": utc_now(),
        "statuses": statuses,
        "n": len(cnpjs),
        "definitive_rate": report["registry_resolved_or_definitively_not_found"],
    })
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
    ap.add_argument("--rate-limit", type=float, default=0.08)
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument("--workers", type=int, default=10)
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
        official_jsonl=args.official_jsonl
        or (
            Path(os.environ["CONFENGE_OFFICIAL_CNPJ_JSONL"])
            if os.environ.get("CONFENGE_OFFICIAL_CNPJ_JSONL")
            else None
        ),
        resume=args.resume or args.failures_only,
        rate_limit_s=args.rate_limit,
        max_retries=args.max_retries,
        failures_only=args.failures_only,
        workers=args.workers,
    )
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
