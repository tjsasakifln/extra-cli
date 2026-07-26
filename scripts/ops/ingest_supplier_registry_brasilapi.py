#!/usr/bin/env python3
"""Ingest supplier_registry rows from BrasilAPI for candidate CNPJs.

Never invents data. Failed lookups are skipped (NOT_COMPUTABLE remains).
Source provenance: brasilapi /cnpj/v1, versioned by API path + fetch date.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.commercial_leads.dbutil import connect  # noqa: E402
from scripts.commercial_leads.supplier_registry import (  # noqa: E402
    ensure_registry_table,
    upsert_registry_rows,
)

BRASILAPI = "https://brasilapi.com.br/api/cnpj/v1"
UA = "extra-cli-confenge-registry/1.0"


def fetch_one(cnpj14: str, timeout: float = 12.0) -> dict[str, Any] | None:
    url = f"{BRASILAPI}/{cnpj14}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
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
    return {
        "cnpj14": cnpj14,
        "razao_social": raw.get("razao_social") or raw.get("nome_fantasia"),
        "nome_fantasia": raw.get("nome_fantasia"),
        "cnae_principal": cnae_principal,
        "cnaes_secundarios": secs,
        "situacao_cadastral": raw.get("descricao_situacao_cadastral") or raw.get("situacao_cadastral"),
        "data_situacao": raw.get("data_situacao_cadastral"),
        "municipio": raw.get("municipio"),
        "uf": raw.get("uf"),
        "source": "brasilapi",
        "source_version": "cnpj/v1",
        "source_date": date.today().isoformat(),
    }


def load_cnpjs_from_run(run_result: Path, limit: int | None) -> list[str]:
    d = json.loads(run_result.read_text(encoding="utf-8"))
    cnpjs: list[str] = []
    lm = d.get("load_meta") or {}
    cnpjs.extend(lm.get("candidate_supplier_cnpjs") or [])
    for r in d.get("review_queue_sample") or []:
        if r.get("cnpj14"):
            cnpjs.append(str(r["cnpj14"]))
    for r in d.get("leads") or []:
        if r.get("cnpj14"):
            cnpjs.append(str(r["cnpj14"]))
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for c in cnpjs:
        c = "".join(ch for ch in c if ch.isdigit())[-14:]
        if len(c) == 14 and c not in seen:
            seen.add(c)
            out.append(c)
    # Prefer multi-contract candidates from review queue JSON if present
    rq_path = run_result.parent / "review-queue.json"
    if rq_path.is_file():
        rq = json.loads(rq_path.read_text(encoding="utf-8"))
        ranked = sorted(
            rq,
            key=lambda r: (
                int(r.get("relevant_contract_count") or 0),
                float(r.get("relevant_contract_ratio_full_history") or 0),
                float(r.get("total_value") or 0),
            ),
            reverse=True,
        )
        preferred = []
        for r in ranked:
            c = "".join(ch for ch in str(r.get("cnpj14") or "") if ch.isdigit())[-14:]
            if len(c) == 14:
                preferred.append(c)
        # put preferred first
        rest = [c for c in out if c not in set(preferred)]
        out = preferred + rest
    if limit:
        out = out[: int(limit)]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN"))
    ap.add_argument(
        "--run-result",
        default="artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/run/run-result.json",
    )
    ap.add_argument("--limit", type=int, default=400, help="Max CNPJs to fetch")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default="artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/registry-ingest.json")
    args = ap.parse_args(argv)
    if not args.dsn:
        print("FAIL: --dsn or CONFENGE_COMMERCIAL_STATE_DSN required", file=sys.stderr)
        return 1

    cnpjs = load_cnpjs_from_run(Path(args.run_result), args.limit)
    print(f"fetching {len(cnpjs)} CNPJs from BrasilAPI…")
    rows: list[dict[str, Any]] = []
    failed = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_one, c): c for c in cnpjs}
        for i, fut in enumerate(as_completed(futs), 1):
            rec = fut.result()
            if rec and rec.get("cnae_principal"):
                rows.append(rec)
            else:
                failed += 1
            if i % 50 == 0:
                print(f"  progress {i}/{len(cnpjs)} ok={len(rows)} fail={failed}")

    conn = connect(args.dsn)
    try:
        ensure_registry_table(conn)
        n = upsert_registry_rows(conn, rows)
    finally:
        conn.close()

    report = {
        "requested": len(cnpjs),
        "fetched_with_cnae": len(rows),
        "failed_or_empty": failed,
        "upserted": n,
        "source": "brasilapi",
        "source_version": "cnpj/v1",
        "source_date": date.today().isoformat(),
        "elapsed_s": round(time.time() - t0, 2),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    # also dump jsonl for make ingest-supplier-registry reproducibility
    jsonl = out.with_suffix(".jsonl")
    with jsonl.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2))
    print(f"jsonl: {jsonl}")
    return 0 if n > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
