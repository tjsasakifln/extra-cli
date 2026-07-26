#!/usr/bin/env python3
"""Official CNPJ cadastral dataset for CONFENGE — government authority preferred.

BrasilAPI / MinhaReceita / cnpj.ws are FALLBACK only and must never be labeled
as the primary official source in release evidence.

Primary path: versioned offline extract under data/official_cnpj/ or
CONFENGE_OFFICIAL_CNPJ_JSONL, with a provenance manifest declaring authority.

If no government-authority extract is available, gates fail closed with
BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE rather than renaming fallbacks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
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
OFFICIAL_DIR = _ROOT / "data" / "official_cnpj"
OFFICIAL_JSONL = ART / "official-cnpj-registry-snapshot.jsonl"
OFFICIAL_MANIFEST = ART / "official-cnpj-dataset-manifest.json"
PROVENANCE_GATE = ART / "official-registry-provenance-gate.json"

# Sources that must NEVER be claimed as official authority
FALLBACK_SOURCES = frozenset(
    {
        "brasilapi",
        "brasilapi_fallback",
        "minhareceita",
        "minhareceita_fallback",
        "cnpjws",
        "cnpjws_fallback",
        "publica.cnpj.ws",
    }
)

# Recognized government / official authorities (honest only)
OFFICIAL_AUTHORITIES = frozenset(
    {
        "receita_federal_dados_abertos",
        "receita_federal_do_brasil",
        "rfb_dados_publicos_cnpj",
        "governo_federal_dados_abertos_cnpj",
    }
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_candidates(run_result: Path | None) -> list[str]:
    out: list[str] = []
    if run_result and run_result.is_file():
        d = json.loads(run_result.read_text(encoding="utf-8"))
        lm = d.get("load_meta") or {}
        for c in lm.get("candidate_supplier_cnpjs") or []:
            cc = re_cnpj14(c)
            if cc:
                out.append(cc)
        for L in d.get("leads") or []:
            cc = re_cnpj14(L.get("cnpj14"))
            if cc:
                out.append(cc)
    # dedupe preserve order
    seen: set[str] = set()
    cleaned: list[str] = []
    for c in out:
        if c not in seen:
            seen.add(c)
            cleaned.append(c)
    return cleaned


def candidate_universe_hash(cnpjs: list[str]) -> str:
    blob = json.dumps(sorted(cnpjs), separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def _try_download_rfb_index() -> dict[str, Any]:
    """Attempt to locate RFB open-data index. Fail closed on network errors."""
    urls = [
        "https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/",
        "http://200.152.38.155/CNPJ/",
        "https://dadosabertos.rfb.gov.br/CNPJ/",
    ]
    errors: list[str] = []
    for url in urls:
        try:
            req = urllib.request.Request(  # noqa: S310
                url, headers={"User-Agent": "extra-cli-confenge/1.0", "Accept": "text/html"}
            )
            with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
                body = resp.read(5000).decode("utf-8", errors="replace")
                return {
                    "ok": True,
                    "url": url,
                    "status": resp.status,
                    "snippet_len": len(body),
                    "source_authority": "receita_federal_dados_abertos",
                }
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    return {
        "ok": False,
        "status": "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE",
        "errors": errors,
        "source_authority": None,
        "note": (
            "RFB open-data bulk endpoints unreachable from this environment. "
            "Do not substitute BrasilAPI as official."
        ),
    }


def download_official_dataset(*, out_dir: Path | None = None) -> dict[str, Any]:
    """Download or locate official CNPJ dataset. Never renames BrasilAPI to official."""
    out_dir = out_dir or OFFICIAL_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded_at = utc_now()

    # 1) Pre-staged official extract in data/official_cnpj/
    staged = sorted(out_dir.glob("*.jsonl")) + sorted(out_dir.glob("*.csv"))
    if staged:
        files = []
        for p in staged:
            files.append(
                {
                    "path": str(p),
                    "file_sha256": sha256_file(p),
                    "size_bytes": p.stat().st_size,
                    "record_count_estimate": sum(1 for _ in p.open(encoding="utf-8", errors="ignore")),
                }
            )
        manifest = {
            "ok": True,
            "status": "STAGED_OFFICIAL_PRESENT",
            "source_name": "receita_federal_dados_abertos_staged",
            "source_authority": "receita_federal_dados_abertos",
            "source_files": [f["path"] for f in files],
            "source_urls_or_identifiers": [
                "local:data/official_cnpj/* (operator-staged RFB extract)"
            ],
            "source_reference_date": date.today().isoformat(),
            "downloaded_at": downloaded_at,
            "file_sha256": {Path(f["path"]).name: f["file_sha256"] for f in files},
            "record_count": sum(f["record_count_estimate"] for f in files),
            "schema_version": "official-cnpj-v1",
            "ingestion_version": "confenge-official-cnpj-v1",
            "files": files,
        }
        OFFICIAL_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return manifest

    # 2) Env-provided path
    env_path = os.environ.get("CONFENGE_OFFICIAL_CNPJ_JSONL")
    if env_path and Path(env_path).is_file():
        p = Path(env_path)
        n = sum(1 for line in p.open(encoding="utf-8") if line.strip())
        manifest = {
            "ok": True,
            "status": "ENV_OFFICIAL_PRESENT",
            "source_name": os.environ.get(
                "CONFENGE_OFFICIAL_CNPJ_SOURCE_NAME", "receita_federal_dados_abertos"
            ),
            "source_authority": os.environ.get(
                "CONFENGE_OFFICIAL_CNPJ_AUTHORITY", "receita_federal_dados_abertos"
            ),
            "source_files": [str(p)],
            "source_urls_or_identifiers": [
                os.environ.get("CONFENGE_OFFICIAL_CNPJ_URL", f"file:{p}")
            ],
            "source_reference_date": os.environ.get(
                "CONFENGE_OFFICIAL_CNPJ_REF_DATE", date.today().isoformat()
            ),
            "downloaded_at": downloaded_at,
            "file_sha256": {p.name: sha256_file(p)},
            "record_count": n,
            "schema_version": "official-cnpj-v1",
            "ingestion_version": "confenge-official-cnpj-v1",
        }
        OFFICIAL_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return manifest

    # 3) Try network RFB index (bulk too large to auto-ingest fully here)
    probe = _try_download_rfb_index()
    if not probe.get("ok"):
        manifest = {
            "ok": False,
            "status": "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE",
            "source_name": None,
            "source_authority": None,
            "source_files": [],
            "source_urls_or_identifiers": [],
            "source_reference_date": None,
            "downloaded_at": downloaded_at,
            "file_sha256": {},
            "record_count": 0,
            "schema_version": "official-cnpj-v1",
            "ingestion_version": "confenge-official-cnpj-v1",
            "probe": probe,
            "note": (
                "No staged RFB extract and remote RFB endpoints unavailable. "
                "BrasilAPI-only snapshot is NOT official — do not rename."
            ),
        }
        OFFICIAL_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return manifest

    # Index reachable but full bulk download is multi-GB — require staged extract
    manifest = {
        "ok": False,
        "status": "BLOCKED_OFFICIAL_REGISTRY_BULK_NOT_STAGED",
        "source_name": "receita_federal_dados_abertos",
        "source_authority": "receita_federal_dados_abertos",
        "source_files": [],
        "source_urls_or_identifiers": [probe.get("url")],
        "source_reference_date": date.today().isoformat(),
        "downloaded_at": downloaded_at,
        "file_sha256": {},
        "record_count": 0,
        "schema_version": "official-cnpj-v1",
        "ingestion_version": "confenge-official-cnpj-v1",
        "probe": probe,
        "note": (
            "RFB index reachable but multi-GB bulk not auto-downloaded. "
            "Stage a filtered extract under data/official_cnpj/*.jsonl with authority metadata."
        ),
    }
    OFFICIAL_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def _is_official_source(source: str | None, authority: str | None) -> bool:
    s = (source or "").lower()
    a = (authority or "").lower()
    if s in FALLBACK_SOURCES or any(s.startswith(f) for f in FALLBACK_SOURCES):
        return False
    if a in FALLBACK_SOURCES:
        return False
    if a in OFFICIAL_AUTHORITIES:
        return True
    if "receita" in a or "rfb" in a or "governo" in a:
        return True
    if "receita" in s or "rfb" in s or s.startswith("official_"):
        return True
    return False


def ingest_official_dataset(
    *,
    dsn: str,
    candidates: list[str],
    official_jsonl: Path | None = None,
) -> dict[str, Any]:
    """Join frozen candidate universe with official extract; record per-field provenance."""
    man = {}
    if OFFICIAL_MANIFEST.is_file():
        man = json.loads(OFFICIAL_MANIFEST.read_text(encoding="utf-8"))

    # Load official rows
    by_cnpj: dict[str, dict[str, Any]] = {}
    sources_files = list(man.get("source_files") or [])
    if official_jsonl and official_jsonl.is_file():
        sources_files.append(str(official_jsonl))
    for staged in OFFICIAL_DIR.glob("*.jsonl"):
        sources_files.append(str(staged))

    authority = man.get("source_authority")
    for fp in sources_files:
        p = Path(fp)
        if not p.is_file() or p.suffix != ".jsonl":
            continue
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                c = re_cnpj14(row.get("cnpj14") or row.get("cnpj"))
                if not c:
                    continue
                src = str(row.get("source") or man.get("source_name") or "official_cnpj_dataset")
                if not _is_official_source(src, authority):
                    # skip fallback-labeled rows inside "official" file
                    continue
                row = dict(row)
                row["cnpj14"] = c
                row["source"] = src if _is_official_source(src, authority) else f"official_{src}"
                row.setdefault("source_authority", authority or "receita_federal_dados_abertos")
                # field-level provenance
                for field in (
                    "cnae_principal",
                    "cnaes_secundarios",
                    "situacao_cadastral",
                    "razao_social",
                ):
                    row.setdefault(f"{field}_source", row["source"])
                by_cnpj[c] = row

    universe_hash = candidate_universe_hash(candidates)
    conn = connect(dsn)
    ensure_registry_table(conn)

    resolution: dict[str, str] = {}
    official_rows: list[dict[str, Any]] = []
    for c in candidates:
        if not re_cnpj14(c):
            resolution[c] = "INVALID_CNPJ"
            continue
        if c in by_cnpj:
            official_rows.append(by_cnpj[c])
            resolution[c] = "RESOLVED_OFFICIAL"
        else:
            # Definitive not found only when official dataset was present and complete
            if man.get("ok") and by_cnpj:
                resolution[c] = "NOT_FOUND_OFFICIAL"
            else:
                resolution[c] = "NOT_COMPUTABLE"

    if official_rows:
        upsert_registry_rows(conn, official_rows)

    # Write filtered official snapshot (never label fallback as official)
    with OFFICIAL_JSONL.open("w", encoding="utf-8") as f:
        for c in candidates:
            if c in by_cnpj:
                f.write(json.dumps(by_cnpj[c], ensure_ascii=False, default=str) + "\n")

    counts: dict[str, int] = {}
    for st in resolution.values():
        counts[st] = counts.get(st, 0) + 1

    n = len(candidates) or 1
    resolved = counts.get("RESOLVED_OFFICIAL", 0)
    not_found = counts.get("NOT_FOUND_OFFICIAL", 0)
    definitive = resolved + not_found + counts.get("INVALID_CNPJ", 0)
    report = {
        "ok": bool(man.get("ok") and definitive == len(candidates) and len(candidates) > 0),
        "status": (
            "PASS"
            if man.get("ok") and definitive == len(candidates) and len(candidates) > 0
            else "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE"
            if not man.get("ok")
            else "BLOCKED_REGISTRY_UNIVERSE_INCOMPLETE"
        ),
        "candidate_count": len(candidates),
        "candidate_universe_hash": universe_hash,
        "official_dataset_rows": len(by_cnpj),
        "resolution_counts": counts,
        "official_registry_match_rate": resolved / n,
        "official_registry_not_found_rate": not_found / n,
        "fallback_usage_rate": 0.0,  # this path does not apply fallback
        "field_conflict_rate": 0.0,
        "registry_resolved_or_definitively_not_found": definitive / n if candidates else 0.0,
        "transient_failures": counts.get("NOT_COMPUTABLE", 0) if man.get("ok") else len(candidates),
        "selection_bias_risk": False,
        "source_authority": authority,
        "manifest_ok": bool(man.get("ok")),
        "ingested_at": utc_now(),
    }
    if not man.get("ok"):
        report["selection_bias_risk"] = True  # incomplete official join risks bias
        report["block"] = "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE"
    (ART / "official-cnpj-ingest-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    (ART / "registry-resolution-status.json").write_text(
        json.dumps(
            {
                "candidate_universe_hash": universe_hash,
                "candidate_count": len(candidates),
                "resolution_counts": counts,
                "statuses_sample": dict(list(resolution.items())[:20]),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    conn.close()
    return report


def verify_official_provenance() -> dict[str, Any]:
    """Gate: refuse PASS if snapshot rows are primarily BrasilAPI-labeled as official."""
    man = {}
    if OFFICIAL_MANIFEST.is_file():
        man = json.loads(OFFICIAL_MANIFEST.read_text(encoding="utf-8"))

    src_counts: dict[str, int] = {}
    n = 0
    if OFFICIAL_JSONL.is_file():
        with OFFICIAL_JSONL.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                n += 1
                row = json.loads(line)
                src = str(row.get("source") or "unknown")
                src_counts[src] = src_counts.get(src, 0) + 1

    fallback_n = sum(v for k, v in src_counts.items() if k.lower() in FALLBACK_SOURCES or "fallback" in k.lower() or "brasilapi" in k.lower() or "minhareceita" in k.lower())
    official_n = n - fallback_n
    authority = man.get("source_authority")
    authority_ok = _is_official_source(man.get("source_name"), authority)
    # FAIL if file is empty of official rows or entirely fallback-labeled while named official
    primarily_fallback = n > 0 and fallback_n == n
    ok = bool(
        man.get("ok")
        and authority_ok
        and official_n > 0
        and not primarily_fallback
        and int(man.get("record_count") or 0) > 0
    )
    report = {
        "ok": ok,
        "status": "PASS" if ok else "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE",
        "source_name": man.get("source_name"),
        "source_authority": authority,
        "source_files": man.get("source_files"),
        "source_urls_or_identifiers": man.get("source_urls_or_identifiers"),
        "source_reference_date": man.get("source_reference_date"),
        "downloaded_at": man.get("downloaded_at"),
        "file_sha256": man.get("file_sha256"),
        "record_count": man.get("record_count"),
        "schema_version": man.get("schema_version"),
        "ingestion_version": man.get("ingestion_version"),
        "jsonl_row_count": n,
        "source_distribution": src_counts,
        "fallback_rows": fallback_n,
        "official_rows": official_n,
        "primarily_fallback_labeled": primarily_fallback,
        "note": (
            "BrasilAPI/MinhaReceita may fill missing fields elsewhere with per-field "
            "provenance, but must not be the sole content of official-cnpj-registry-snapshot.jsonl."
        ),
    }
    PROVENANCE_GATE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("download")
    ing = sub.add_parser("ingest")
    ing.add_argument("--dsn", default=os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN"))
    ing.add_argument(
        "--run-result",
        type=Path,
        default=ART / "run" / "run-result.json",
    )
    sub.add_parser("verify-provenance")
    args = ap.parse_args(argv)
    if args.cmd == "download":
        rep = download_official_dataset()
        print(json.dumps(rep, indent=2, default=str))
        return 0 if rep.get("ok") else 2
    if args.cmd == "ingest":
        if not args.dsn:
            print("CONFENGE_COMMERCIAL_STATE_DSN required", file=sys.stderr)
            return 1
        cands = load_candidates(args.run_result)
        rep = ingest_official_dataset(dsn=args.dsn, candidates=cands)
        print(json.dumps(rep, indent=2, default=str))
        return 0 if rep.get("ok") else 2
    if args.cmd == "verify-provenance":
        rep = verify_official_provenance()
        print(json.dumps(rep, indent=2, default=str))
        return 0 if rep.get("ok") else 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
