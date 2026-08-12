#!/usr/bin/env python3
"""Bulk-fetch cadastral rows via OpenCNPJ API (RFB public data redistributor).

Produces a versioned JSONL under data/official_cnpj/ with explicit provenance:
  source_authority = receita_federal_dados_abertos
  source_distributor = opencnpj.org
  source_name = rfb_public_cadastral_via_opencnpj

This is NOT BrasilAPI. OpenCNPJ redistributes RFB open cadastral data.
If the operator has a direct RFB zip extract, prefer that path instead.
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.commercial_leads.supplier_registry import re_cnpj14  # noqa: E402
from scripts.ops.confenge_official_cnpj import (  # noqa: E402
    OFFICIAL_DIR,
    OFFICIAL_MANIFEST,
    load_candidates,
    sha256_file,
)

ART = _ROOT / "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01"
API = "https://api.opencnpj.org"
UA = "extra-cli-confenge-official/1.0 (+rfb-public-data-via-opencnpj)"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fetch_one(cnpj14: str, timeout: float = 20.0) -> tuple[str, dict[str, Any] | None, str]:
    url = f"{API}/{cnpj14}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return "NOT_FOUND_OFFICIAL", None, url
        return "TRANSIENT", None, url
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return "TRANSIENT", None, url
    if not isinstance(raw, dict):
        return "CORRUPT", None, url

    cnae = raw.get("cnae_principal") or raw.get("cnae_fiscal") or raw.get("cnae")
    cnae_desc = raw.get("cnae_principal_descricao") or raw.get("cnae_fiscal_descricao")
    cnae_principal = None
    if cnae is not None:
        cnae_principal = str(cnae)
        if cnae_desc:
            cnae_principal = f"{cnae} - {cnae_desc}"
    secs: list[str] = []
    for s in raw.get("cnaes_secundarios") or raw.get("cnaes_secundarias") or []:
        if isinstance(s, dict):
            code = s.get("codigo") or s.get("code") or s.get("id")
            desc = s.get("descricao")
            if code is not None:
                secs.append(f"{code}" + (f" - {desc}" if desc else ""))
        elif s:
            secs.append(str(s))
    row = {
        "cnpj14": cnpj14,
        "razao_social": raw.get("razao_social") or raw.get("nome"),
        "nome_fantasia": raw.get("nome_fantasia"),
        "cnae_principal": cnae_principal,
        "cnaes_secundarios": secs,
        "situacao_cadastral": raw.get("situacao_cadastral") or raw.get("descricao_situacao_cadastral"),
        "data_situacao": raw.get("data_situacao_cadastral") or raw.get("data_situacao"),
        "municipio": raw.get("municipio") or raw.get("cidade"),
        "uf": raw.get("uf"),
        "natureza_juridica": raw.get("natureza_juridica"),
        "source": "rfb_public_cadastral_via_opencnpj",
        "source_authority": "receita_federal_dados_abertos",
        "source_distributor": "opencnpj.org",
        "source_version": "opencnpj-api/v1",
        "source_date": date.today().isoformat(),
        "source_file": url,
        "source_url": url,
        "source_hash": hashlib.sha256(
            json.dumps(raw, sort_keys=True, default=str).encode()
        ).hexdigest()[:16],
        "ingested_at": utc_now(),
        "cnae_principal_source": "rfb_public_cadastral_via_opencnpj",
        "cnaes_secundarios_source": "rfb_public_cadastral_via_opencnpj",
        "situacao_cadastral_source": "rfb_public_cadastral_via_opencnpj",
        "razao_social_source": "rfb_public_cadastral_via_opencnpj",
        "raw_keys": sorted(raw.keys())[:40],
    }
    if not row.get("razao_social") and not row.get("cnae_principal"):
        return "CORRUPT", None, url
    return "RESOLVED_OFFICIAL", row, url


def bulk_fetch(
    cnpjs: list[str],
    *,
    workers: int = 12,
    rate_limit_s: float = 0.05,
    out_jsonl: Path | None = None,
    resume: bool = True,
) -> dict[str, Any]:
    OFFICIAL_DIR.mkdir(parents=True, exist_ok=True)
    out_jsonl = out_jsonl or (OFFICIAL_DIR / "rfb_via_opencnpj_universe.jsonl")
    ck_path = OFFICIAL_DIR / "opencnpj-bulk-checkpoint.json"

    done: dict[str, str] = {}
    if resume and ck_path.is_file():
        done = dict(json.loads(ck_path.read_text(encoding="utf-8")).get("statuses") or {})

    # Load existing rows
    existing: dict[str, dict[str, Any]] = {}
    if out_jsonl.is_file() and resume:
        with out_jsonl.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                c = re_cnpj14(row.get("cnpj14"))
                if c:
                    existing[c] = row
                    done.setdefault(c, "RESOLVED_OFFICIAL")

    pending = [c for c in cnpjs if c not in done or done.get(c) == "TRANSIENT"]
    statuses = dict(done)
    rows_out = dict(existing)
    started = utc_now()

    def one(c: str) -> tuple[str, str, dict[str, Any] | None]:
        time.sleep(rate_limit_s)
        st, row, _url = _fetch_one(c)
        return c, st, row

    processed = 0
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 20))) as ex:
        futs = {ex.submit(one, c): c for c in pending}
        for fut in as_completed(futs):
            c, st, row = fut.result()
            processed += 1
            statuses[c] = st
            if row and st == "RESOLVED_OFFICIAL":
                rows_out[c] = row
            if processed % 100 == 0:
                # checkpoint
                with out_jsonl.open("w", encoding="utf-8") as f:
                    for cnpj in sorted(rows_out):
                        f.write(json.dumps(rows_out[cnpj], ensure_ascii=False, default=str) + "\n")
                ck_path.write_text(
                    json.dumps({"statuses": statuses, "n_rows": len(rows_out)}, indent=2) + "\n",
                    encoding="utf-8",
                )
                print(f"... {processed}/{len(pending)} fetched, rows={len(rows_out)}", flush=True)

    # final write
    with out_jsonl.open("w", encoding="utf-8") as f:
        for cnpj in sorted(rows_out):
            f.write(json.dumps(rows_out[cnpj], ensure_ascii=False, default=str) + "\n")
    ck_path.write_text(
        json.dumps({"statuses": statuses, "n_rows": len(rows_out)}, indent=2) + "\n",
        encoding="utf-8",
    )

    counts: dict[str, int] = {}
    for st in statuses.values():
        counts[st] = counts.get(st, 0) + 1

    finished = utc_now()
    file_sha = sha256_file(out_jsonl) if out_jsonl.is_file() else None
    manifest = {
        "ok": True,
        "status": "DOWNLOADED_RFB_VIA_OPENCNPJ",
        "source_name": "rfb_public_cadastral_via_opencnpj",
        "source_authority": "receita_federal_dados_abertos",
        "source_distributor": "opencnpj.org",
        "source_files": [str(out_jsonl)],
        "source_urls_or_identifiers": [
            "https://api.opencnpj.org/{cnpj14}",
            "Receita Federal — Dados Abertos CNPJ (public cadastral base redistributed by OpenCNPJ)",
            "https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/cadastros/consultas/dados-publicos-cnpj",
        ],
        "source_reference_date": date.today().isoformat(),
        "downloaded_at": finished,
        "download_started_at": started,
        "file_sha256": {out_jsonl.name: file_sha},
        "record_count": len(rows_out),
        "schema_version": "official-cnpj-v1",
        "ingestion_version": "confenge-opencnpj-bulk-v1",
        "universe_requested": len(cnpjs),
        "status_counts": counts,
        "note": (
            "Cadastral fields originate from RFB public CNPJ open data as served by "
            "OpenCNPJ API redistributor. Direct multi-GB RFB zip was not staged; "
            "this is the operational official-equivalent extract for the frozen universe."
        ),
    }
    OFFICIAL_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (ART / "opencnpj-bulk-report.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-result", type=Path, default=ART / "run" / "run-result.json")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--rate-limit", type=float, default=0.05)
    ap.add_argument("--cnpj", action="append", default=[])
    ap.add_argument("--limit", type=int, default=0, help="0 = full universe")
    args = ap.parse_args(argv)
    cands = list(args.cnpj) if args.cnpj else load_candidates(args.run_result)
    if not cands:
        # fallback: distinct suppliers from commercial DB
        dsn = os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN")
        if dsn:
            from scripts.commercial_leads.dbutil import connect, fetch_all

            conn = connect(dsn)
            rows = fetch_all(
                conn,
                """
                SELECT DISTINCT fornecedor_cnpj AS c
                FROM public.pncp_supplier_contracts
                WHERE supplier_id_type = 'CNPJ'
                  AND fornecedor_cnpj IS NOT NULL
                """,
            )
            conn.close()
            cands = [r["c"] for r in rows if re_cnpj14(r["c"])]
    # prefer frozen candidate list from prior run when larger
    if args.limit and args.limit > 0:
        cands = cands[: args.limit]
    print(f"fetching {len(cands)} cnpjs via OpenCNPJ...", flush=True)
    rep = bulk_fetch(cands, workers=args.workers, rate_limit_s=args.rate_limit)
    print(json.dumps({k: rep[k] for k in ("ok", "status", "record_count", "status_counts", "source_authority")}, indent=2))
    return 0 if rep.get("ok") and int(rep.get("record_count") or 0) > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
