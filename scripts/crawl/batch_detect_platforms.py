"""Batch platform detection for ALL SC municipalities.

Detects transparency portal platforms for all 295 SC municipalities
using concurrent HTTP requests for speed. Writes results to JSON and
generates YAML config entries for transparencia_config.yaml.

Usage:
    python scripts/crawl/batch_detect_platforms.py
"""

import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path

# Add project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Silence the logger from transparencia_crawler
logging.basicConfig(level=logging.WARNING)
logging.getLogger("scripts.crawl.transparencia_crawler").setLevel(logging.WARNING)

from scripts.crawl.transparencia_crawler import _slugify, detect_platform

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Number of concurrent workers (adjust based on network capacity)
MAX_WORKERS = 30

# Delay between requests per platform template (from transparencia_crawler)
REQUEST_DELAY = float(os.getenv("TRANSPARENCIA_REQUEST_DELAY", "0.5"))

OUTPUT_DIR = _PROJECT_ROOT / "data"
OUTPUT_FILE = OUTPUT_DIR / "platform_detection_results.json"

# ---------------------------------------------------------------------------
# Get municipios from database
# ---------------------------------------------------------------------------


def get_municipios_from_db() -> list[dict]:
    """Fetch all SC municipios with IBGE codes from the database."""
    import psycopg2

    conn = psycopg2.connect(os.getenv("LOCAL_DATALAKE_DSN", "postgresql://postgres@127.0.0.1:5433/pncp_datalake"))
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
    conn.close()

    municipios = []
    for nome, ibge in rows:
        municipios.append(
            {
                "nome": nome.strip().upper(),
                "ibge": ibge.strip() if ibge else None,
                "slug": _slugify(nome),
            }
        )
    return municipios


def get_municipios_from_file() -> list[dict]:
    """Fallback: use hardcoded list from municipios_sc.json if DB unavailable."""
    # This is populated as a fallback if DB is down
    raise FileNotFoundError("No file-based fallback available")


# ---------------------------------------------------------------------------
# Batch detection with concurrency
# ---------------------------------------------------------------------------


def detect_single(args: tuple) -> dict:
    """Run detect_platform for one municipio. Wrapped for ThreadPoolExecutor."""
    mun, index, total = args
    nome = mun["nome"]
    slug = mun["slug"]
    ibge = mun.get("ibge", "")

    # Print progress indicator
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
    print(f"Concurrency: {MAX_WORKERS} workers")
    print(f"Started at: {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'=' * 70}\n")

    # Prepare args with index for progress tracking
    args_list = [(mun, i + 1, total) for i, mun in enumerate(municipios)]

    results = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(detect_single, args): args[0] for args in args_list}

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

    # Platform distribution
    from collections import Counter

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


def generate_yaml_entries(report: dict) -> str:
    """Generate YAML config entries for transparencia_config.yaml."""
    lines = []
    lines.append("# Platform Detection Results (auto-generated)")
    lines.append(f"# Generated at: {report['generated_at']}")
    lines.append(
        f"# Total: {report['total']} | Detected: {report['detected']} | Not found: {report['not_found']} | Errors: {report['errors']}"
    )
    lines.append(f"# Platform distribution: {json.dumps(report['platforms'])}")
    lines.append("")

    # Group by platform for organized config
    by_platform: dict[str, list] = {}
    for d in report["detected_list"]:
        by_platform.setdefault(d["platform"], []).append(d)

    for platform, items in sorted(by_platform.items()):
        lines.append(f"  # --- {platform.upper()} ({len(items)} municipios) ---")
        for item in items:
            slug = item["slug"]
            nome = item["municipio"].title()
            url = item["url"]

            # Determine template based on platform
            template_map = {
                "betha": "portal_transparencia_net",
                "ipam": "portal_transparencia_net",
                "egov": "e_gov_net",
                "proprio": "custom",
            }
            template = template_map.get(platform, "custom")

            lines.append(f"  {slug}:")
            lines.append(f'    nome: "{nome}"')
            lines.append(f'    ibge: "{item["ibge"]}"')
            lines.append(f'    portal_url: "{url}"')
            lines.append(f'    template: "{template}"')
            lines.append("    requires_js: false")
            lines.append("    ativo: true")
            lines.append("")

    # Not found municipios as comments
    if report["not_found_list"]:
        lines.append("  # --- NOT FOUND ({}) ---".format(len(report["not_found_list"])))
        for nome in report["not_found_list"]:
            lines.append(f"  # {_slugify(nome)}:")
            lines.append(f'  #   nome: "{nome.title()}"')
            lines.append('  #   ibge: ""  # TODO: lookup IBGE code')
            lines.append('  #   portal_url: ""  # TODO: manual discovery')
            lines.append('  #   template: "custom"')
            lines.append("  #   requires_js: false")
            lines.append("  #   ativo: false")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    # Step 1: Get municipios
    print("Fetching municipios from database...")
    try:
        municipios = get_municipios_from_db()
    except Exception as e:
        print(f"Database error: {e}")
        print("Trying fallback...")
        municipios = get_municipios_from_file()

    print(f"Found {len(municipios)} municipios to detect")

    # Step 2: Run batch detection
    results = run_batch_detection(municipios)

    # Step 3: Generate report
    report = generate_report(results)

    # Step 4: Save JSON results
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Results saved to: {OUTPUT_FILE}")

    # Step 5: Print summary
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Total municipios:  {report['total']}")
    print(f"  Detected:          {report['detected']} ({report['detected'] / report['total'] * 100:.1f}%)")
    print(f"  Not found:         {report['not_found']} ({report['not_found'] / report['total'] * 100:.1f}%)")
    print(f"  Errors:            {report['errors']}")
    print("\nPlatform distribution:")
    for plat, count in report["platforms"].items():
        print(f"  {plat}: {count} ({count / report['total'] * 100:.1f}%)")

    # Step 6: Generate YAML
    yaml_entries = generate_yaml_entries(report)

    output_yaml = OUTPUT_DIR / "platform_detection_config_entries.yaml"
    with open(output_yaml, "w", encoding="utf-8") as f:
        f.write(yaml_entries)
    print(f"\nYAML config entries saved to: {output_yaml}")
    print("\nPreview (first 30 lines of YAML):")
    print("-" * 60)
    for line in yaml_entries.split("\n")[:30]:
        print(line)
    if len(yaml_entries.split("\n")) > 30:
        print(f"... ({len(yaml_entries.split('\\n'))} total lines)")


if __name__ == "__main__":
    main()
