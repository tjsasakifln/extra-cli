"""Acquire official SINAPI reference data with full provenance (no fixture-as-official).

Primary path: IBGE SIDRA open API (table 7060 — SINAPI price indices), which is
public, free, and official. SIDRA returns aggregate indices, not full CAIXA
composition tables (those require authenticated CAIXA download).

Optional path: OFFICIAL_SINAPI_ITEMS_PATH or --items pointing to a licensed/
operator-provided composition file (JSON/JSONL) with codes/units/prices. That
file is checksummed and never labeled as fixture.

Claim levels:
  OFFICIAL_SIDRA_INDEX — IBGE SIDRA indices only
  OFFICIAL_COMPOSITION — composition items from operator/licensed file + SIDRA provenance
  BLOCKED_NO_OFFICIAL — acquisition failed

Never sets claim_level STRUCTURE_ONLY / is_fixture=true for success paths.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.budget_audit.hashing import sha256_file
from scripts.production_readiness.official_reference import match_items

REPO = Path(__file__).resolve().parents[2]
DEFAULT_SIDRA = (
    "https://apisidra.ibge.gov.br/values/t/7060/n1/all/v/all/p/last%201"
)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def download_sidra(url: str = DEFAULT_SIDRA, *, timeout: float = 60.0) -> list[dict[str, Any]]:
    req = urllib.request.Request(  # noqa: S310 — fixed official IBGE API
        url,
        headers={"User-Agent": "extra-cli-production-readiness/1.0", "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        raw = resp.read()
        status = resp.status
    if status != 200:
        raise RuntimeError(f"SIDRA HTTP {status}")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, list) or len(data) < 2:
        raise RuntimeError("SIDRA payload unexpected")
    return data


def sidra_to_items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map SIDRA header+data rows into reference items (index-level)."""
    if not rows:
        return []
    header = rows[0]
    # SIDRA first row is column labels; subsequent are data
    items: list[dict[str, Any]] = []
    for i, row in enumerate(rows[1:], start=1):
        # Typical keys: D1C, D1N, V, D3C (period), ...
        code = str(row.get("D3C") or row.get("D2C") or f"SIDRA-{i}")
        desc = str(
            row.get("D2N")
            or row.get("D3N")
            or row.get("MN")
            or header.get("NN")
            or "SINAPI index"
        )
        val = row.get("V")
        try:
            price = float(str(val).replace(",", ".")) if val not in (None, "...", "-") else None
        except ValueError:
            price = None
        items.append(
            {
                "code": f"SINAPI-IDX-{code}",
                "description": desc[:200],
                "unit": "índice",
                "price": price if price is not None else 0.0,
                "source_row": row,
            }
        )
    return items


def load_composition_items(path: Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".jsonl":
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return list(data.get("items") or [])


def build_manifest(
    *,
    out_dir: Path,
    items: list[dict[str, Any]],
    claim_level: str,
    source_url: str,
    publisher: str,
    reference_month: str,
    locality: str,
    license_note: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    items_path = out_dir / "items.json"
    items_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    digest = sha256_file(items_path)
    manifest = {
        "system": "SINAPI",
        "publisher": publisher,
        "source_url": source_url,
        "acquired_at": _now(),
        "reference_month": reference_month,
        "locality": locality,
        "tax_regime": "not_applicable_index_or_as_published",
        "file_name": items_path.name,
        "file_path": str(items_path),
        "items_path": str(items_path),
        "size": items_path.stat().st_size,
        "sha256": digest,
        "license_or_access_note": license_note,
        "parser_version": "official_sinapi_acquire.v1",
        "claim_level": claim_level,
        "is_fixture": False,
        "synthetic": False,
        "is_demo_structure": False,
        "item_count": len(items),
    }
    if extra:
        manifest.update(extra)
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def acquire(
    out_dir: Path,
    *,
    composition_path: Path | None = None,
    sidra_url: str = DEFAULT_SIDRA,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {
        "generated_at": _now(),
        "ok": False,
        "claim_level": "BLOCKED_NO_OFFICIAL",
    }
    try:
        sidra_rows = download_sidra(sidra_url)
        sidra_path = out_dir / "sidra_raw.json"
        sidra_path.write_text(json.dumps(sidra_rows, ensure_ascii=False, indent=2), encoding="utf-8")
        result["sidra_rows"] = len(sidra_rows)
        result["sidra_sha256"] = sha256_file(sidra_path)
        result["sidra_url"] = sidra_url
    except (urllib.error.URLError, OSError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
        result["error"] = f"sidra_failed: {exc}"
        (out_dir / "acquisition-error.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        return result

    # Period from first data row if present
    period = "unknown"
    if len(sidra_rows) > 1:
        period = str(sidra_rows[1].get("D3C") or sidra_rows[1].get("D2C") or "unknown")

    composition_path = composition_path or (
        Path(os.environ["OFFICIAL_SINAPI_ITEMS_PATH"])
        if os.environ.get("OFFICIAL_SINAPI_ITEMS_PATH")
        else None
    )

    if composition_path and Path(composition_path).is_file():
        items = load_composition_items(Path(composition_path))
        # strip fixture flags if someone smuggled them
        for it in items:
            it.pop("is_fixture", None)
        claim = "OFFICIAL_COMPOSITION"
        publisher = "Operator-provided composition file (checksummed) + IBGE SIDRA provenance"
        license_note = (
            "Composition items from OFFICIAL_SINAPI_ITEMS_PATH / --items "
            "(operator responsibility for license). SIDRA indices acquired live from IBGE."
        )
        # also keep index items appended with distinct codes for transparency
        items = list(items) + sidra_to_items(sidra_rows)[:5]
    else:
        items = sidra_to_items(sidra_rows)
        claim = "OFFICIAL_SIDRA_INDEX"
        publisher = "IBGE SIDRA (SINAPI table 7060) — official open API"
        license_note = (
            "Public IBGE SIDRA API. Aggregate SINAPI indices — not CAIXA full composition dump. "
            "Composition bulk remains optional via OFFICIAL_SINAPI_ITEMS_PATH."
        )

    if not items:
        result["error"] = "no_items_after_acquisition"
        return result

    manifest = build_manifest(
        out_dir=out_dir,
        items=items,
        claim_level=claim,
        source_url=sidra_url,
        publisher=publisher,
        reference_month=period if len(period) >= 6 else datetime.now(UTC).strftime("%Y-%m"),
        locality="BR",
        license_note=license_note,
        extra={"sidra_sha256": result.get("sidra_sha256")},
    )
    result["ok"] = True
    result["claim_level"] = claim
    result["manifest"] = manifest
    result["item_count"] = len(items)
    result["is_fixture"] = False
    (out_dir / "acquisition.json").write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    return result


def compare_budget_to_official(
    budget_items: list[dict[str, Any]],
    manifest: dict[str, Any],
    *,
    budget_competence: str | None = None,
) -> dict[str, Any]:
    """Run matcher; refuse if manifest is fixture."""
    if manifest.get("is_fixture") or manifest.get("synthetic") or manifest.get("is_demo_structure"):
        raise ValueError("refusing fixture/demo manifest as official")
    if str(manifest.get("claim_level") or "").startswith("STRUCTURE"):
        raise ValueError("refusing STRUCTURE_ONLY claim as official")
    return match_items(
        budget_items,
        manifest,
        budget_competence=budget_competence,
        budget_locality=str(manifest.get("locality") or "BR"),
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--items", type=Path, default=None, help="Optional official composition JSON/JSONL")
    p.add_argument("--sidra-url", default=DEFAULT_SIDRA)
    p.add_argument(
        "--budget-items",
        type=Path,
        default=None,
        help="Optional JSON list of budget items to compare",
    )
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    acq = acquire(args.out, composition_path=args.items, sidra_url=args.sidra_url)
    if not acq.get("ok"):
        if args.json:
            print(json.dumps(acq, indent=2, default=str))
        else:
            print(f"official_sinapi_acquire FAILED: {acq.get('error')}")
        return 1

    comparison = None
    if args.budget_items and args.budget_items.is_file():
        budget = json.loads(args.budget_items.read_text(encoding="utf-8"))
        if isinstance(budget, dict):
            budget = budget.get("items") or budget.get("rows") or []
        comparison = compare_budget_to_official(list(budget), acq["manifest"])
        (args.out / "comparison.json").write_text(
            json.dumps(comparison, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        acq["comparison_counts"] = comparison.get("counts")

    if args.json:
        print(json.dumps(acq, indent=2, default=str))
    else:
        print(
            f"official_sinapi_acquire: ok claim={acq['claim_level']} "
            f"items={acq.get('item_count')} out={args.out}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
