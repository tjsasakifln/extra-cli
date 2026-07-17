#!/usr/bin/env python3
"""Public DOE-SC acquisition through the official Dados Abertos CKAN.

This read path requires no credentials. It is intentionally separate from the
authenticated publishing/portal API adapter. Annual resources may lag the
current day, so a successful download is never presented as fresh unless the
resource contains publications inside the configured SLA.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.crawl.act_classifier import classify_act
from scripts.crawl.security import USER_AGENT

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CKAN_ACTION = "https://dados.sc.gov.br/api/3/action"
PACKAGE_ID = "984555cc-7637-4d5b-8b84-775817e253da"
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "doe_sc_public"
OUTPUT_DIR = PROJECT_ROOT / "output" / "doe_sc"
SOURCE = "doe_sc_public_ckan"
PROCUREMENT_TERMS = (
    "LICITA",
    "CONTRAT",
    "PREGÃO",
    "PREGAO",
    "CONCORRÊNCIA",
    "CONCORRENCIA",
    "DISPENSA",
    "INEXIGIBIL",
    "TERMO ADITIVO",
    "ATA DE REGISTRO",
    "HOMOLOGA",
)


def _request_bytes(url: str, *, retries: int = 3, timeout: int = 90) -> bytes:
    """Fetch HTTPS bytes with bounded exponential backoff and jitter."""
    if not url.startswith("https://"):
        raise ValueError("DOE-SC public adapter only accepts HTTPS URLs")
    last: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310
                return response.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            if isinstance(exc, urllib.error.HTTPError) and exc.code not in {429, 500, 502, 503, 504}:
                break
            if attempt + 1 < retries:
                time.sleep((2**attempt) + random.uniform(0.0, 0.25))  # noqa: S311
    raise RuntimeError(f"DOE-SC public fetch failed after {retries} attempts: {last}")


def discover_package() -> dict[str, Any]:
    url = f"{CKAN_ACTION}/package_show?{urllib.parse.urlencode({'id': PACKAGE_ID})}"
    payload = json.loads(_request_bytes(url).decode("utf-8"))
    if payload.get("success") is not True or not isinstance(payload.get("result"), dict):
        raise RuntimeError("DOE-SC CKAN package_show returned no result")
    return payload["result"]


def select_csv_resource(package: dict[str, Any], year: int | None = None) -> dict[str, Any]:
    resources = [
        r
        for r in package.get("resources") or []
        if str(r.get("format") or "").upper() == "CSV"
        and str(r.get("name") or "").startswith("publicacoes_")
    ]
    if year is not None:
        resources = [r for r in resources if str(year) in str(r.get("name") or "")]
    if not resources:
        raise RuntimeError(f"No DOE-SC public CSV resource found for year={year or 'latest'}")
    return sorted(resources, key=lambda r: str(r.get("name") or ""))[-1]


def parse_publications(raw: bytes) -> list[dict[str, str]]:
    text = raw.decode("utf-8-sig", errors="replace")
    return [dict(row) for row in csv.DictReader(io.StringIO(text), delimiter=";")]


def normalize_publication(row: dict[str, str], *, resource: dict[str, Any]) -> dict[str, Any] | None:
    title = (row.get("TITULO_PUBLICACAO") or "").strip()
    subject = (row.get("ASSUNTO") or "").strip()
    category = (row.get("CATEGORIA") or "").strip()
    searchable = f"{subject} {title}".upper()
    if not any(term in searchable for term in PROCUREMENT_TERMS):
        return None
    raw_date = (row.get("DATA_PUBLICACAO") or "").strip()
    published_at: str | None = None
    try:
        published_at = datetime.strptime(raw_date, "%d/%m/%Y").date().isoformat()
    except ValueError:
        pass
    external_id = (row.get("PUBLICACAO") or "").strip() or None
    # The public CSV does not document a stable per-matter URL. Keep the
    # official resource URL and the native id separately instead of inventing
    # a deep link.
    official_url = resource.get("url")
    classification = classify_act(title, subject=subject, category=category)
    fingerprint = json.dumps(row, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return {
        "source": SOURCE,
        "external_id": external_id,
        "publication_date": published_at,
        "edition_number": (row.get("EDICAO") or "").strip() or None,
        "orgao_nome": category or None,
        "source_category": subject or None,
        "title": title or None,
        "source_url": official_url,
        "resource_id": resource.get("id"),
        "resource_url": resource.get("url"),
        "record_hash": hashlib.sha256(fingerprint).hexdigest(),
        "act_category": classification.get("category"),
        "act_confidence": classification.get("confidence"),
        "raw_json": row,
    }


def run(*, year: int | None = None, sla_hours: int = 24) -> dict[str, Any]:
    started = datetime.now(UTC)
    package = discover_package()
    resource = select_csv_resource(package, year=year)
    raw = _request_bytes(str(resource["url"]))
    digest = hashlib.sha256(raw).hexdigest()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / f"{resource['id']}-{digest[:12]}.csv"
    if not raw_path.exists():
        raw_path.write_bytes(raw)
    normalized = [
        item
        for row in parse_publications(raw)
        if (item := normalize_publication(row, resource=resource)) is not None
    ]
    latest_date = max((x["publication_date"] for x in normalized if x.get("publication_date")), default=None)
    fresh = False
    if latest_date:
        fresh = datetime.fromisoformat(latest_date).replace(tzinfo=UTC) >= started - timedelta(hours=sla_hours)
    run_id = f"doe-public-{started.strftime('%Y%m%dT%H%M%SZ')}-{digest[:10]}"
    run_dir = OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    records_path = run_dir / "publications.jsonl"
    records_path.write_text(
        "".join(json.dumps(x, ensure_ascii=False, default=str) + "\n" for x in normalized),
        encoding="utf-8",
    )
    summary = {
        "run_id": run_id,
        "source": SOURCE,
        "status": "success" if normalized else "empty",
        "credentials_required": False,
        "package_id": package.get("id"),
        "resource_id": resource.get("id"),
        "resource_url": resource.get("url"),
        "raw_uri": str(raw_path),
        "raw_sha256": digest,
        "records_read": len(parse_publications(raw)),
        "records_normalized": len(normalized),
        "latest_publication_date": latest_date,
        "sla_hours": sla_hours,
        "fresh_within_sla": fresh,
        "freshness_status": "fresh" if fresh else "stale",
        "started_at": started.isoformat(),
        "completed_at": datetime.now(UTC).isoformat(),
        "records_path": str(records_path),
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect public DOE-SC CKAN publications without credentials")
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--sla-hours", type=int, default=24)
    args = parser.parse_args(argv)
    summary = run(year=args.year, sla_hours=args.sla_hours)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
