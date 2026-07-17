#!/usr/bin/env python3
"""CLI — list DOM-related packages on CIGA Dados (public CKAN).

Uses the same public Action API as ``ciga_ckan_crawler`` (no token).

Examples:
    python -m scripts.crawl.discover_ciga_packages
    python -m scripts.crawl.discover_ciga_packages --q domsc --rows 20
    python -m scripts.crawl.discover_ciga_packages --list-domsc-months
    python -m scripts.crawl.discover_ciga_packages --package domsc-publicacoes-de-07-2026
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.crawl import ciga_ckan_crawler as ciga  # noqa: E402

_logger = logging.getLogger(__name__)


def search_packages(q: str = "domsc", rows: int = 20) -> dict | None:
    """package_search on CIGA; returns full CKAN result dict or None."""
    url = f"{ciga.CKAN_API}/package_search?q={q}&rows={rows}"
    # _ckan_request already returns result only; re-fetch via that + wrap
    result = ciga._ckan_request(url)  # noqa: SLF001 — shared client
    if result is None:
        return None
    return result


def list_dom_related_packages(*, prefix_only: bool = False) -> list[str]:
    """List package names related to DOM-SC / autopublicações.

    Prefer ``list_domsc_months`` from the crawler; this helper also includes
    older ``autopublicacoes-*`` naming if present in package_list.
    """
    all_pkgs = ciga.list_datasets()
    if not all_pkgs:
        return []
    prefixes = (
        "domsc-publicacoes-de-",
        "dom-sc-publicacoes-de-",
        "domsc-autopublicacoes-de-",
        "domsc-edicoes-de-",
        "autopublicacoes-de-",
    )
    if prefix_only:
        # Only packages already used by ciga list_domsc_months
        return ciga.list_domsc_months()
    matched = sorted(
        d for d in all_pkgs if d.startswith(prefixes) or "domsc" in d or "dom-sc" in d
    )
    return matched


def show_package_summary(package_id: str) -> dict | None:
    """Return package name, title, resource count and first resources."""
    pkg = ciga.get_package(package_id)
    if not pkg:
        return None
    resources = ciga.get_package_resources(pkg)
    return {
        "id": pkg.get("id"),
        "name": pkg.get("name"),
        "title": pkg.get("title"),
        "metadata_modified": pkg.get("metadata_modified"),
        "resource_count": len(resources),
        "resources": [
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "format": r.get("format"),
                "url": r.get("url"),
                "last_modified": r.get("last_modified"),
            }
            for r in resources[:10]
        ],
        "resources_truncated": len(resources) > 10,
    }


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    p = argparse.ArgumentParser(description="Discover DOM packages on CIGA Dados CKAN")
    p.add_argument("--q", default="domsc", help="package_search query (default: domsc)")
    p.add_argument("--rows", type=int, default=10, help="rows for package_search")
    p.add_argument(
        "--list-domsc-months",
        action="store_true",
        help="List monthly packages via ciga.list_domsc_months()",
    )
    p.add_argument(
        "--list-all-dom",
        action="store_true",
        help="List all DOM-related package names from package_list",
    )
    p.add_argument("--package", help="package_show summary for one package id/name")
    p.add_argument("--json", action="store_true", help="JSON output")
    args = p.parse_args(argv)

    payload: dict = {"portal": ciga.CKAN_BASE, "auth_required": False}

    if args.package:
        summary = show_package_summary(args.package)
        if not summary:
            print(f"package not found or request failed: {args.package}", file=sys.stderr)
            return 1
        payload["package"] = summary
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"{summary['name']} | resources={summary['resource_count']}")
            for r in summary["resources"]:
                print(f"  - {r.get('name')} | {r.get('format')} | {r.get('id')}")
            if summary.get("resources_truncated"):
                print("  ... (truncated)")
        return 0

    if args.list_domsc_months or args.list_all_dom:
        pkgs = (
            ciga.list_domsc_months()
            if args.list_domsc_months
            else list_dom_related_packages(prefix_only=False)
        )
        payload["packages"] = pkgs
        payload["count"] = len(pkgs)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"DOM-related packages: {len(pkgs)}")
            for name in pkgs[-30:]:
                print(f"  {name}")
            if len(pkgs) > 30:
                print(f"  ... showing last 30 of {len(pkgs)}")
        return 0 if pkgs else 1

    # Default: package_search
    result = search_packages(q=args.q, rows=args.rows)
    time.sleep(ciga.REQUEST_DELAY)
    if result is None:
        print("package_search failed", file=sys.stderr)
        return 1

    results = result.get("results") if isinstance(result, dict) else None
    # ciga._ckan_request returns result only — for package_search that is the
    # dict with count/results. If API shape differs, handle list.
    if isinstance(result, list):
        packages = result
        count = len(result)
    else:
        packages = results or []
        count = result.get("count", len(packages))

    payload["q"] = args.q
    payload["count"] = count
    payload["packages"] = [
        {
            "name": pkg.get("name"),
            "title": pkg.get("title"),
            "num_resources": pkg.get("num_resources") or len(pkg.get("resources") or []),
        }
        for pkg in packages
    ]

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"CIGA package_search q={args.q!r} count={count}")
        for item in payload["packages"]:
            print(
                f"  {item['name']} | resources={item['num_resources']} | {item['title']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
