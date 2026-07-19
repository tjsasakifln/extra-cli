#!/usr/bin/env python3
"""Resolve CNPJ-14 for residual entities via matriz branch 0001 + check digits.

Public entities commonly register headquarters as {cnpj8}0001{DV}.
We compute official check digits (Receita Federal algorithm), then verify via
PNCP GET /api/pncp/v1/orgaos/{cnpj14}. Only 200 responses with matching
cnpj8 prefix are accepted (optional soft name check).

Usage:
  python3 -m scripts.ops.resolve_cnpj14_matriz --limit 200 --write --delay 0.6
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2

UA = "ExtraConsultoria-OPS95/1.0"
REPO = Path(__file__).resolve().parents[2]
CACHE_DEFAULT = REPO / "data/cnpj14_cache/pncp_orgaos_by_name.jsonl"
ORGAO_URL = "https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}"


def digits(s: str | None) -> str:
    return re.sub(r"\D", "", str(s or ""))


def cnpj_check_digits(base12: str) -> str:
    def dv(nums: str, weights: list[int]) -> str:
        total = sum(int(n) * w for n, w in zip(nums, weights, strict=False))
        r = total % 11
        return "0" if r < 2 else str(11 - r)

    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    w2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = dv(base12, w1)
    d2 = dv(base12 + d1, w2)
    return d1 + d2


def cnpj14_matriz(cnpj8: str, branch: str = "0001") -> str:
    c8 = digits(cnpj8)[:8]
    if len(c8) != 8 or len(branch) != 4:
        raise ValueError("cnpj8 must be 8 digits and branch 4 digits")
    base12 = c8 + branch
    return base12 + cnpj_check_digits(base12)


def normalize_name(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Z0-9 ]+", " ", s.upper())
    return re.sub(r"\s+", " ", s).strip()


def soft_name_match(entity_name: str, api_name: str) -> bool:
    """Accept if token overlap is meaningful; never reject solely on empty API name."""
    a = normalize_name(entity_name)
    b = normalize_name(api_name)
    if not b:
        return True  # API returned body without name — still cnpj8-verified
    if a == b:
        return True
    stop = {
        "MUNICIPIO",
        "PREFEITURA",
        "SECRETARIA",
        "FUNDO",
        "FUNDACAO",
        "ESTADO",
        "SANTA",
        "CATARINA",
        "DE",
        "DA",
        "DO",
        "DOS",
        "DAS",
        "E",
        "SOCIAL",
        "PUBLICO",
        "PUBLICA",
        "MUNICIPAL",
    }
    ta = {t for t in a.split() if len(t) > 3 and t not in stop}
    tb = {t for t in b.split() if len(t) > 3 and t not in stop}
    if not ta or not tb:
        # short names: require containment either way
        return a in b or b in a or len(set(a.split()) & set(b.split())) >= 2
    inter = ta & tb
    return len(inter) >= 1 and (len(inter) / max(1, min(len(ta), len(tb)))) >= 0.34


def http_get_json(url: str, timeout: int = 20) -> tuple[int, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return int(resp.status), json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        body = e.read() if e.fp else b""
        try:
            data = json.loads(body.decode("utf-8")) if body else {}
        except json.JSONDecodeError:
            data = {}
        return int(e.code), data


def load_have(path: Path) -> set[str]:
    have: set[str] = set()
    if not path.exists():
        return have
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            have.add(json.loads(line)["cnpj8"])
    return have


def residual_rows(cur, have: set[str], limit: int) -> list[tuple]:
    cur.execute(
        """
        WITH den AS (
          SELECT cnpj_8, razao_social, municipio
          FROM sc_public_entities WHERE is_active AND raio_200km
        ),
        hit AS (
          SELECT DISTINCT LEFT(REGEXP_REPLACE(COALESCE(orgao_cnpj::text,''),'[^0-9]','','g'),8) c8
          FROM pncp_raw_bids
          WHERE LENGTH(REGEXP_REPLACE(COALESCE(orgao_cnpj::text,''),'[^0-9]','','g'))>=8
          UNION
          SELECT DISTINCT LEFT(REGEXP_REPLACE(COALESCE(orgao_cnpj::text,''),'[^0-9]','','g'),8) c8
          FROM pncp_supplier_contracts
          WHERE LENGTH(REGEXP_REPLACE(COALESCE(orgao_cnpj::text,''),'[^0-9]','','g'))>=8
        )
        SELECT d.cnpj_8, d.razao_social, d.municipio
        FROM den d
        LEFT JOIN hit h ON d.cnpj_8 = h.c8
        WHERE h.c8 IS NULL
        ORDER BY d.razao_social
        """
    )
    out = []
    for c8, razao, mun in cur.fetchall():
        if c8 in have:
            continue
        out.append((c8, razao, mun))
        if len(out) >= limit:
            break
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", default=None)
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--delay", type=float, default=0.55)
    p.add_argument("--branch", default="0001", help="Filial branch digits (default 0001 HQ)")
    p.add_argument("--write", action="store_true")
    p.add_argument("--cache", type=Path, default=CACHE_DEFAULT)
    p.add_argument("--require-name-match", action="store_true", help="Stricter: soft name match required")
    p.add_argument("--output-json", type=Path, default=None)
    args = p.parse_args(argv)

    dsn = args.dsn or os.environ.get(
        "LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test"
    )
    cache = args.cache if args.cache.is_absolute() else REPO / args.cache
    cache.parent.mkdir(parents=True, exist_ok=True)
    have = load_have(cache)

    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    rows = residual_rows(cur, have, args.limit)
    conn.close()
    print(
        f"todo={len(rows)} already_cached={len(have)} branch={args.branch} write={args.write}",
        flush=True,
    )

    results: list[dict[str, Any]] = []
    resolved = 0
    rejected_name = 0
    not_found = 0
    errors = 0

    for i, (c8, razao, mun) in enumerate(rows, 1):
        try:
            c14 = cnpj14_matriz(c8, args.branch)
            url = ORGAO_URL.format(cnpj=c14)
            status, body = http_get_json(url)
            time.sleep(args.delay)
            row: dict[str, Any] = {
                "cnpj8": c8,
                "cnpj14": c14,
                "razao": razao,
                "municipio": mun,
                "http_status": status,
                "url": url,
            }
            if status == 200 and isinstance(body, dict):
                api_razao = body.get("razaoSocial") or body.get("nome") or ""
                api_cnpj = digits(body.get("cnpj") or c14)
                row["api_razao"] = api_razao
                if len(api_cnpj) == 14 and api_cnpj[:8] != c8:
                    row["verdict"] = "CNPJ8_MISMATCH"
                    rejected_name += 1
                elif args.require_name_match and not soft_name_match(razao, api_razao):
                    row["verdict"] = "NAME_MISMATCH"
                    rejected_name += 1
                else:
                    # Soft name check when available (non-blocking unless required)
                    if api_razao and not soft_name_match(razao, api_razao):
                        row["name_soft"] = "weak"
                    else:
                        row["name_soft"] = "ok"
                    row["verdict"] = "RESOLVED"
                    row["method"] = f"matriz_{args.branch}_checkdigit"
                    if args.write:
                        with cache.open("a", encoding="utf-8") as fh:
                            fh.write(
                                json.dumps(
                                    {
                                        "cnpj8": c8,
                                        "cnpj14": c14,
                                        "method": row["method"],
                                        "razao": razao,
                                        "api_razao": api_razao,
                                        "name_soft": row["name_soft"],
                                        "resolved_at": datetime.now(timezone.utc).isoformat(),
                                    },
                                    ensure_ascii=False,
                                )
                                + "\n"
                            )
                        have.add(c8)
                    resolved += 1
            elif status == 404:
                row["verdict"] = "NOT_FOUND"
                not_found += 1
            elif status == 429:
                row["verdict"] = "RATE_LIMIT"
                errors += 1
                time.sleep(45)
            else:
                row["verdict"] = f"HTTP_{status}"
                errors += 1
            results.append(row)
        except Exception as e:  # noqa: BLE001
            errors += 1
            results.append(
                {
                    "cnpj8": c8,
                    "razao": razao,
                    "verdict": "ERROR",
                    "error": f"{type(e).__name__}: {e}",
                }
            )
            if "429" in str(e):
                time.sleep(45)
        if i % 25 == 0 or i == len(rows):
            print(
                f"progress {i}/{len(rows)} resolved={resolved} not_found={not_found} "
                f"rejected={rejected_name} errors={errors}",
                flush=True,
            )

    report = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "branch": args.branch,
        "probed": len(results),
        "resolved": resolved,
        "not_found": not_found,
        "rejected_name": rejected_name,
        "errors": errors,
        "cache_total": len(have),
        "write": args.write,
        "results": results,
        "claims_forbidden": [
            "invented CNPJ without verification",
            "operational coverage from resolve alone",
        ],
        "note": "CNPJ-14 = cnpj8+branch+DV verified via PNCP orgaos API HTTP 200",
    }
    out = args.output_json
    if out is None:
        out = (
            REPO
            / "docs/ops/campaigns/EXTRA-OPS-95/evidence/M2-cnpj14"
            / f"matriz-{args.branch}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        )
    out = out if out.is_absolute() else REPO / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in report if k != "results"}, ensure_ascii=False, indent=2))
    print(f"wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
