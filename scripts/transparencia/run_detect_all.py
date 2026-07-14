"""Batch platform detection for ALL SC municipalities (COVERAGE-1.3).

Detects transparency portal platforms for all SC municipalities (295+)
using the updated _PLATFORM_TEMPLATES (includes 5 new platforms:
Fiorilli, Iplan, IRI, Prima, Tecnospeed).

Saves results to data/transparencia_platforms.json in the format
expected by transparencia_crawler.crawl() — compatible with
_load_existing_results() / _save_results().

Usage:
    python scripts/transparencia/run_detect_all.py          # Batch detect all
    python scripts/transparencia/run_detect_all.py --slug chapeco  # Single test
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path

# Add project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("scripts.crawl.transparencia_crawler").setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MAX_WORKERS = 30  # Concurrent HTTP workers
REQUEST_DELAY = float(os.getenv("TRANSPARENCIA_REQUEST_DELAY", "0.5"))

OUTPUT_FILE = _PROJECT_ROOT / "data" / "transparencia_platforms.json"
RESIDUAL_FILE = _PROJECT_ROOT / "data" / "transparencia_residual_municipios.json"


# ---------------------------------------------------------------------------
# Municipio loading
# ---------------------------------------------------------------------------


def get_municipios_from_db() -> list[dict]:
    """Fetch all SC municipios with IBGE codes from the database."""
    import psycopg2

    from scripts.crawl.transparencia_crawler import _slugify

    conn = psycopg2.connect(os.getenv("DATABASE_URL", "postgresql://postgres@127.0.0.1:5433/pncp_datalake"))
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT municipio, codigo_ibge
        FROM sc_public_entities
        WHERE municipio IS NOT NULL
          AND municipio != 'SANTA CATARINA'
        ORDER BY municipio
    """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    municipios = []
    seen = set()
    for nome, ibge in rows:
        nome_clean = nome.strip().upper()
        if nome_clean in seen:
            continue
        seen.add(nome_clean)
        municipios.append(
            {
                "nome": nome_clean,
                "ibge": ibge.strip() if ibge else None,
                "slug": _slugify(nome_clean),
            }
        )
    return municipios


# ---------------------------------------------------------------------------
# Batch detection with concurrency
# ---------------------------------------------------------------------------


def _detect_single(args: tuple) -> dict:
    """Run detect_platform for one municipio. Wrapped for ThreadPoolExecutor."""
    from scripts.crawl.transparencia_crawler import detect_platform

    mun, index, total = args
    nome = mun["nome"]
    slug = mun["slug"]
    ibge = mun.get("ibge", "")

    print(f"[{index}/{total}] {nome} (slug={slug})...", end=" ", flush=True)

    try:
        result = detect_platform(slug, municipio=nome)
        result["ibge"] = ibge
        if result["status"] == "detected":
            print(f"\r[{index}/{total}] {nome} -> {result['platform']} @ {result['url']}")
        elif result["status"] == "not_found":
            print(f"\r[{index}/{total}] {nome} -> NOT FOUND")
        else:
            print(f"\r[{index}/{total}] {nome} -> {result['status']}: {result.get('error', '')}")
    except Exception as e:
        result = {
            "municipio": nome,
            "slug": slug,
            "ibge": ibge,
            "platform": None,
            "url": None,
            "status": "error",
            "error": str(e),
            "detected_at": date.today().isoformat(),
        }
        print(f"\r[{index}/{total}] {nome} -> ERROR: {e}")

    return result


def run_batch_detection(municipios: list[dict]) -> list[dict]:
    """Run detection for all municipios using thread pool concurrency."""
    total = len(municipios)
    print(f"\n{'=' * 70}")
    print(f"Batch platform detection for {total} SC municipalities")
    print("Platforms: betha, ipam, egov, fiorilli, iplan, iri, prima, tecnospeed + proprio")
    print(f"Concurrency: {MAX_WORKERS} workers")
    print(f"Started at: {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'=' * 70}\n")

    args_list = [(mun, i + 1, total) for i, mun in enumerate(municipios)]

    results: list[dict] = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_detect_single, args): args[0] for args in args_list}

        for future in as_completed(futures):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                mun = futures[future]
                results.append(
                    {
                        "municipio": mun["nome"],
                        "slug": mun["slug"],
                        "ibge": mun.get("ibge", ""),
                        "platform": None,
                        "url": None,
                        "status": "error",
                        "error": str(e),
                        "detected_at": date.today().isoformat(),
                    }
                )

    elapsed = time.time() - start_time
    print(f"\n{'=' * 70}")
    print(f"Completed in {elapsed:.1f}s ({elapsed / 60:.1f}min)")
    print(f"{'=' * 70}\n")

    return results


# ---------------------------------------------------------------------------
# Report & Export
# ---------------------------------------------------------------------------


def generate_report(results: list[dict]) -> dict:
    """Generate summary report from detection results."""
    total = len(results)
    detected = [r for r in results if r["status"] == "detected"]
    not_found = [r for r in results if r["status"] == "not_found"]
    errors = [r for r in results if r["status"] == "error"]

    platform_counts = Counter(r["platform"] for r in detected)

    return {
        "total": total,
        "detected": len(detected),
        "not_found": len(not_found),
        "errors": len(errors),
        "platforms": dict(platform_counts.most_common()),
        "detected_list": [
            {
                "municipio": r["municipio"],
                "slug": r["slug"],
                "ibge": r["ibge"],
                "platform": r["platform"],
                "url": r["url"],
            }
            for r in sorted(detected, key=lambda x: x["municipio"])
        ],
        "not_found_list": sorted([r["municipio"] for r in not_found]),
        "error_list": sorted(
            [(r["municipio"], r.get("error", "")) for r in errors],
            key=lambda x: x[0],
        ),
        "generated_at": date.today().isoformat(),
    }


def save_results_as_transparencia_format(results: list[dict], output_path: str | Path) -> None:
    """Save results in the format expected by transparencia_crawler._load_existing_results().

    The format is:
    {
        "detected": [list of detection result dicts],
        "metadata": { ... }
    }
    """
    detected_count = sum(1 for r in results if r.get("status") == "detected")
    not_found_count = sum(1 for r in results if r.get("status") == "not_found")
    error_count = sum(1 for r in results if r.get("status") == "error")

    data = {
        "detected": results,
        "metadata": {
            "version": 2,
            "total_entities": len(results),
            "total_detected": detected_count,
            "total_not_found": not_found_count,
            "total_errors": error_count,
            "mode": "batch_detect_all",
            "updated_at": date.today().isoformat(),
            "platforms": sorted(set(r.get("platform") for r in results if r.get("platform"))),
        },
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to: {output_path}")


def save_residual_municipios(detected_list: list[dict], not_found_list: list[str], output_path: str | Path) -> None:
    """Save list of municipios WITHOUT detected platform for Fase 3 follow-up.

    Format: JSON with per-municipio info, suggested next steps for manual discovery.
    """
    from scripts.crawl.transparencia_crawler import _slugify

    # Build comprehensive list with suggested follow-ups
    residual: list[dict] = []
    for nome in sorted(not_found_list):
        slug = _slugify(nome)
        residual.append(
            {
                "municipio": nome,
                "slug": slug,
                "suggested_urls": [
                    f"https://{slug}.sc.gov.br",
                    f"https://www.{slug}.sc.gov.br",
                    f"https://transparencia.{slug}.sc.gov.br",
                ],
                "coverage_source_alternatives": [
                    "pncp",
                    "dom_sc",
                    "ciga_ckan",
                    "sc_compras",
                ],
                "status": "pending_fase3",
            }
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at": date.today().isoformat(),
                "total_residual": len(residual),
                "source": "COVERAGE-1.3 batch detect",
                "note": "Municipios sem plataforma detectada. Encaminhar para COVERAGE-3.2 (Fase 3).",
                "residual": residual,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"Residual municipios saved to: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Batch detect transparency platforms for all SC municipios")
    parser.add_argument(
        "--slug",
        default=None,
        help="Detectar plataforma para um unico slug (modo teste)",
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT_FILE),
        help=f"Caminho para arquivo de resultados (default: {OUTPUT_FILE})",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=MAX_WORKERS,
        help=f"Numero de workers concorrentes (default: {MAX_WORKERS})",
    )
    args = parser.parse_args()

    # Step 1: Get municipios
    print("Fetching municipios from database...")
    try:
        municipios = get_municipios_from_db()
    except Exception as e:
        print(f"Database error: {e}")
        print("Cannot proceed without database connection.")
        sys.exit(1)

    print(f"Found {len(municipios)} municipios to detect")

    # Single slug mode
    if args.slug:
        from scripts.crawl.transparencia_crawler import detect_platform

        result = detect_platform(args.slug, municipio=args.slug)
        result["ibge"] = ""
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0)

    # Step 2: Run batch detection
    results = run_batch_detection(municipios)

    # Step 3: Generate report
    report = generate_report(results)

    # Step 4: Print summary
    print(f"\n{'=' * 70}")
    print("SUMMARY — COVERAGE-1.3 Platform Detection")
    print(f"{'=' * 70}")
    print(f"  Total municipios:  {report['total']}")
    print(f"  Detected:          {report['detected']} ({report['detected'] / report['total'] * 100:.1f}%)")
    print(f"  Not found:         {report['not_found']} ({report['not_found'] / report['total'] * 100:.1f}%)")
    print(f"  Errors:            {report['errors']}")
    print("\n  Platform distribution:")
    for plat, count in report["platforms"].items():
        print(f"    {plat}: {count} ({count / report['total'] * 100:.1f}%)")

    # Step 5: Save results in transparencia_crawler format
    save_results_as_transparencia_format(results, args.output)

    # Step 6: Save residual municipios for Fase 3
    if report["not_found_list"]:
        save_residual_municipios(
            report["detected_list"],
            report["not_found_list"],
            RESIDUAL_FILE,
        )

    # Step 7: Generate YAML config entries for transparencia_config.yaml
    print("\n  YAML config entries:")
    by_platform: dict[str, list] = {}
    for d in report["detected_list"]:
        by_platform.setdefault(d["platform"], []).append(d)

    for platform, items in sorted(by_platform.items()):
        print(f"\n    # --- {platform.upper()} ({len(items)} municipios) ---")
        for item in items:
            slug = item["slug"]
            nome = item["municipio"].title()
            url = item["url"]
            ibge = item.get("ibge", "")
            template_map = {
                "betha": "portal_transparencia_net",
                "ipam": "portal_transparencia_net",
                "egov": "e_gov_net",
                "proprio": "custom",
            }
            template = template_map.get(platform, "custom")
            print(f"    {slug}:")
            print(f'      nome: "{nome}"')
            print(f'      ibge: "{ibge}"')
            print(f'      portal_url: "{url}"')
            print(f'      template: "{template}"')
            print("      requires_js: false")
            print("      ativo: true")


if __name__ == "__main__":
    main()
