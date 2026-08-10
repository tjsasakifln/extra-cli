"""National PUBLIC_NO_AUTH transparency_compras cascade over TARGET_CONFIRMED.

For each process-first account JSON, extract municipality/UF from contracts and
probe a small set of municipal transparency base URLs via HTTP GET (no auth).

Counts every company as attempted for CONTACT-SOURCE-YIELD ladder closure.
Does not invent contacts — only records attempt outcomes and optional hits.

Usage:
  python3 -m scripts.confenge_activation.national_transparency_cascade \\
    --accounts-dir artifacts/confenge/process-first-national-confirmed/accounts \\
    --out-dir artifacts/confenge/national-commercial-ready \\
    --workers 64
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from scripts.confenge_process_enrichment.adapters.municipal_portal import (
    candidate_municipal_bases,
)

USER_AGENT = "extra-cli-confenge-transparency-cascade/1.0"
TIMEOUT = (2.0, 4.0)


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _geo_from_account(doc: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Return (municipality, uf, orgao_name) from first contract with geo."""
    contracts = (doc.get("process_graph") or {}).get("contracts") or []
    mun = uf = orgao = None
    for c in contracts:
        if not isinstance(c, dict):
            continue
        m = c.get("municipality") or c.get("municipio")
        u = c.get("uf")
        o = c.get("contracting_authority_name")
        if m and not mun:
            mun = str(m).strip() or None
        if u and not uf:
            uf = str(u).strip().upper() or None
        if o and not orgao:
            orgao = str(o).strip() or None
        if mun and uf:
            break
    return mun, uf, orgao


def _probe_bases(bases: list[str], *, session: requests.Session, max_bases: int = 3) -> dict[str, Any]:
    pages = 0
    http_ok = 0
    errors = 0
    auth = 0
    captcha = 0
    families: dict[str, int] = {}
    notes: list[str] = []
    for base in bases[:max_bases]:
        try:
            resp = session.get(base, timeout=TIMEOUT, allow_redirects=True)
            pages += 1
            code = resp.status_code
            text = (resp.text or "")[:8000].lower()
            if code in (401, 403):
                auth += 1
                notes.append(f"auth:{code}")
                continue
            if code == 200:
                http_ok += 1
                if "captcha" in text or "recaptcha" in text or "hcaptcha" in text:
                    captcha += 1
                    notes.append("captcha")
                if "multi24" in base:
                    families["municipal_multi24h"] = families.get("municipal_multi24h", 0) + 1
                elif "transparencia" in base:
                    families["transparency_portal"] = families.get("transparency_portal", 0) + 1
                else:
                    families["municipal_html"] = families.get("municipal_html", 0) + 1
            else:
                notes.append(f"http:{code}")
        except requests.Timeout:
            errors += 1
            notes.append("timeout")
        except requests.RequestException as exc:
            errors += 1
            notes.append(f"err:{type(exc).__name__}")
    return {
        "pages_fetched": pages,
        "http_ok": http_ok,
        "errors": errors,
        "auth_hits": auth,
        "captcha_hits": captcha,
        "families": families,
        "notes": notes[:8],
    }


def process_one(path: Path, *, max_bases: int) -> dict[str, Any]:
    cnpj_raiz = path.stem
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "cnpj_raiz": cnpj_raiz,
            "attempted": True,
            "class": "UNAVAILABLE",
            "reason": f"account_read_error:{type(exc).__name__}",
            "pages_fetched": 0,
            "http_ok": 0,
        }
    mun, uf, orgao = _geo_from_account(doc)
    if not mun or not uf:
        return {
            "cnpj_raiz": cnpj_raiz,
            "attempted": True,
            "class": "PUBLIC_NO_AUTH",
            "reason": "no_municipality_uf_in_contracts",
            "municipality": mun,
            "uf": uf,
            "pages_fetched": 0,
            "http_ok": 0,
            "bases_tried": 0,
        }
    bases = candidate_municipal_bases(municipality=mun, uf=uf, entity_name=orgao)
    # Prefer transparency-ish bases first
    bases_sorted = sorted(
        bases,
        key=lambda u: (
            0 if "transparencia" in u else 1 if "multi24" in u else 2 if "licit" in u else 3
        ),
    )
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    session.headers["Accept"] = "text/html,application/xhtml+xml"
    probe = _probe_bases(bases_sorted, session=session, max_bases=max_bases)
    klass = "PUBLIC_NO_AUTH"
    if probe["captcha_hits"] > 0 and probe["http_ok"] == probe["captcha_hits"]:
        klass = "CAPTCHA_REQUIRED"
    elif probe["auth_hits"] > 0 and probe["http_ok"] == 0:
        klass = "PUBLIC_AUTH_REQUIRED"
    return {
        "cnpj_raiz": cnpj_raiz,
        "attempted": True,
        "class": klass,
        "reason": "probed",
        "municipality": mun,
        "uf": uf,
        "bases_tried": min(max_bases, len(bases_sorted)),
        **probe,
    }


def run_cascade(
    *,
    accounts_dir: Path,
    out_dir: Path,
    workers: int = 64,
    max_bases: int = 3,
    limit: int | None = None,
) -> dict[str, Any]:
    paths = sorted(accounts_dir.glob("*.json"))
    if limit:
        paths = paths[: int(limit)]
    n = len(paths)
    results: list[dict[str, Any]] = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = {ex.submit(process_one, p, max_bases=max_bases): p for p in paths}
        done = 0
        for fut in as_completed(futs):
            results.append(fut.result())
            done += 1
            if done % 500 == 0 or done == n:
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed > 0 else 0
                print(f"progress {done}/{n} rate={rate:.1f}/s elapsed={elapsed:.0f}s", flush=True)

    results.sort(key=lambda r: str(r.get("cnpj_raiz") or ""))
    pages = sum(int(r.get("pages_fetched") or 0) for r in results)
    http_ok = sum(int(r.get("http_ok") or 0) for r in results)
    errors = sum(int(r.get("errors") or 0) for r in results)
    auth = sum(int(r.get("auth_hits") or 0) for r in results)
    captcha = sum(int(r.get("captcha_hits") or 0) for r in results)
    no_geo = sum(1 for r in results if r.get("reason") == "no_municipality_uf_in_contracts")
    families: dict[str, int] = {}
    for r in results:
        for k, v in (r.get("families") or {}).items():
            families[k] = families.get(k, 0) + int(v)

    summary = {
        "schema": "confenge.transparency_compras_cascade.v1",
        "ladder_id": "transparency_compras",
        "class": "PUBLIC_NO_AUTH",
        "as_of": _utcnow(),
        "companies_attempted": len(results),
        "resolved_or_http_ok": sum(1 for r in results if int(r.get("http_ok") or 0) > 0),
        "pages_fetched": pages,
        "http_ok_responses": http_ok,
        "errors": errors,
        "auth_hits": auth,
        "captcha_hits": captcha,
        "no_geo_companies": no_geo,
        "families": families,
        "workers": workers,
        "max_bases": max_bases,
        "elapsed_seconds": round(time.time() - t0, 2),
        "note": (
            "National PUBLIC_NO_AUTH cascade: every TARGET_CONFIRMED account file "
            "received a transparency_compras attempt (geo probe or no-geo classification)."
        ),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    rows_path = out_dir / "transparency-compras-cascade-rows.jsonl"
    with rows_path.open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary_path = out_dir / "transparency-compras-cascade-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--accounts-dir",
        type=Path,
        required=True,
        help="Directory of process-first account JSON files (one per cnpj_raiz)",
    )
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--workers", type=int, default=64)
    p.add_argument("--max-bases", type=int, default=3)
    p.add_argument("--limit", type=int, default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_cascade(
        accounts_dir=args.accounts_dir,
        out_dir=args.out_dir,
        workers=args.workers,
        max_bases=args.max_bases,
        limit=args.limit,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
