"""Batch platform detection - PASS 2 with expanded URL patterns.

Detects transparency portal platforms for SC municipalities that were
NOT FOUND in pass 1. Uses additional URL patterns:
  - {slug}.sc.gov.br (dominio proprio SC)
  - transparencia.{slug}.sc.gov.br
  - www.{slug}.sc.gov.br
  - portaltransparencia.{slug}.sc.gov.br

Also re-checks a few key cities that might have been rate-limited in pass 1.
"""

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

logging.basicConfig(level=logging.WARNING)

from scripts.crawl.transparencia_crawler import _GENERIC_KEYWORDS, _fetch_url, _slugify

MAX_WORKERS = 30
OUTPUT_DIR = _PROJECT_ROOT / "data"
OUTPUT_FILE = OUTPUT_DIR / "platform_detection_results_pass2.json"

# Additional URL patterns for SC municipalities
# Each entry: (name, url_pattern, body_check_keywords)
ADDITIONAL_PATTERNS = [
    # 1. SC state domain (most common for proprietary portals)
    ("sc_gov_main", "https://{slug}.sc.gov.br", None),
    # 2. Transparencia subdomain on SC domain
    ("sc_gov_transparencia", "https://transparencia.{slug}.sc.gov.br", None),
    # 3. WWW subdomain
    ("sc_gov_www", "https://www.{slug}.sc.gov.br", None),
    # 4. Portal transparencia subdomain
    ("sc_gov_portal", "https://portaltransparencia.{slug}.sc.gov.br", None),
]


def check_pattern(slug: str, pattern_name: str, url_template: str) -> dict:
    """Try a specific URL pattern and return result."""
    url = url_template.format(slug=slug)
    try:
        status, body = _fetch_url(url, timeout=8)  # Slightly longer timeout for .sc.gov.br
    except Exception as e:
        return {"status": "error", "error": str(e), "url": url, "body": ""}

    if status == 200:
        # Check for transparency keywords
        body_lower = body.lower()[:5000]
        found_keywords = [kw for kw in _GENERIC_KEYWORDS if kw in body_lower]
        return {
            "status": "detected",
            "url": url,
            "body_size": len(body),
            "found_keywords": found_keywords,
        }

    return {"status": "not_found", "url": url, "body": ""}


def detect_pass2(args: tuple) -> dict:
    """Run detection with expanded patterns for one municipio."""
    mun, index, total = args
    nome = mun["nome"]
    slug = mun["slug"]
    ibge = mun.get("ibge", "")

    print(f"[{index}/{total}] {nome}...", end=" ", flush=True)

    result = {
        "municipio": nome,
        "slug": slug,
        "ibge": ibge,
        "platform": None,
        "url": None,
        "status": "not_found",
        "error": None,
        "detected_at": date.today().isoformat(),
        "pass2_patterns_tried": [],
    }

    # Try additional patterns in order
    for pattern_name, url_template, _ in ADDITIONAL_PATTERNS:
        check = check_pattern(slug, pattern_name, url_template)
        result["pass2_patterns_tried"].append(
            {
                "pattern": pattern_name,
                "url": check["url"],
                "status": check["status"],
            }
        )

        if check["status"] == "detected":
            result["platform"] = "proprio"
            result["url"] = check["url"]
            result["status"] = "detected"
            result["body_size"] = check.get("body_size", 0)
            result["keywords_found"] = check.get("found_keywords", [])

            if check.get("found_keywords"):
                print(f"proprio (transparencia keywords) @ {check['url']}")
            else:
                print(f"proprio (SC domain) @ {check['url']}")
            return result

    print("NOT FOUND (all patterns)")
    return result


def get_not_found_list() -> list[dict]:
    """Read pass1 results and extract the not-found municipios."""
    json_path = OUTPUT_DIR / "platform_detection_results.json"
    if not json_path.exists():
        raise FileNotFoundError(f"Pass1 results not found at {json_path}")

    with open(json_path) as f:
        report = json.load(f)

    # We need the IBGE codes - get from database
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
    all_muns = {
        row[0].strip().upper(): {"ibge": row[1].strip() if row[1] else None, "slug": _slugify(row[0].strip())}
        for row in cur.fetchall()
    }
    conn.close()

    not_found_names = set(report["not_found_list"])
    municipios = []
    for nome in sorted(not_found_names):
        m = all_muns.get(nome.upper(), {})
        municipios.append(
            {
                "nome": nome,
                "slug": m.get("slug", _slugify(nome)),
                "ibge": m.get("ibge", ""),
            }
        )

    return municipios


def merge_results(pass1_path, pass2_results):
    """Merge pass2 results into pass1 results and generate final report."""
    with open(pass1_path) as f:
        report = json.load(f)

    # Create lookup of pass2 results by municipio name
    pass2_by_name = {}
    for r in pass2_results:
        name = r["municipio"].strip().upper()
        pass2_by_name[name] = r

    newly_detected = []
    still_not_found = []
    still_errors = []
    platform_counts = Counter(report["platforms"])

    # Check each not_found from pass1
    for nome in report["not_found_list"]:
        name_key = nome.strip().upper()
        r2 = pass2_by_name.get(name_key)
        if r2 and r2["status"] == "detected":
            newly_detected.append(r2)
            platform_counts[r2["platform"]] += 1
        elif r2 and r2["status"] == "error":
            still_errors.append(nome)
        else:
            still_not_found.append(nome)

    final = {
        "total": report["total"],
        "pass1_detected": report["detected"],
        "pass2_newly_detected": len(newly_detected),
        "total_detected": report["detected"] + len(newly_detected),
        "not_found": len(still_not_found),
        "errors": len(still_errors),
        "platforms": dict(platform_counts.most_common()),
        "detected_list_pass1": report["detected_list"],
        "detected_list_pass2": [
            {
                "municipio": r["municipio"],
                "slug": r["slug"],
                "ibge": r["ibge"],
                "platform": r["platform"],
                "url": r["url"],
                "body_size": r.get("body_size", 0),
            }
            for r in sorted(newly_detected, key=lambda x: x["municipio"])
        ],
        "not_found_list": sorted(still_not_found),
        "error_list": sorted(still_errors),
        "generated_at": date.today().isoformat(),
    }

    return final


def generate_final_yaml(final: dict) -> str:
    """Generate the complete YAML config entries."""
    lines = []
    lines.append("# Platform Detection Results (Pass 1 + 2)")
    lines.append(f"# Generated at: {final['generated_at']}")
    lines.append(
        f"# Total: {final['total']} | Detected: {final['total_detected']} | Not found: {final['not_found']} | Errors: {final['errors']}"
    )
    lines.append(f"# Platform distribution: {json.dumps(final['platforms'])}")
    lines.append("")

    # Combine pass1 + pass2 detected
    all_detected = list(final["detected_list_pass1"]) + list(final["detected_list_pass2"])

    by_platform: dict[str, list] = {}
    for d in all_detected:
        by_platform.setdefault(d["platform"], []).append(d)

    for platform, items in sorted(by_platform.items()):
        lines.append(
            f"  # --- {platform.upper()} ({len(items)} municipios, {len(items) / final['total'] * 100:.1f}%) ---"
        )
        for item in items:
            slug = item["slug"]
            nome = item["municipio"].title()
            url = item["url"]

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

    # Not found as comments
    if final["not_found_list"]:
        lines.append(f"  # --- NAO ENCONTRADOS ({len(final['not_found_list'])}) ---")
        for nome in final["not_found_list"]:
            slug_val = _slugify(nome)
            lines.append(f"  # {slug_val}:")
            lines.append(f'  #   nome: "{nome.title()}"')
            lines.append('  #   ibge: ""  # TODO: lookup manual')
            lines.append('  #   portal_url: ""  # TODO: descobrir manualmente')
            lines.append('  #   template: "custom"')
            lines.append("  #   requires_js: false")
            lines.append("  #   ativo: false")
            lines.append("")

    return "\n".join(lines)


def main():
    # Step 1: Load not-found municipios
    print("Loading NOT FOUND municipios from pass 1...")
    municipios = get_not_found_list()
    print(f"Loaded {len(municipios)} municipios for pass 2 detection\n")

    # Step 2: Run batch detection with expanded patterns
    total = len(municipios)
    print(f"{'=' * 70}")
    print(f"Pass 2 - Expanded pattern detection for {total} SC municipalities")
    print(f"Patterns: {len(ADDITIONAL_PATTERNS)} per municipio")
    print(f"Concurrency: {MAX_WORKERS} workers")
    print(f"Started at: {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'=' * 70}\n")

    args_list = [(mun, i + 1, total) for i, mun in enumerate(municipios)]
    results = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(detect_pass2, args): args[0] for args in args_list}
        for future in as_completed(futures):
            try:
                results.append(future.result())
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
    print(f"Pass 2 completed in {elapsed:.1f}s ({elapsed / 60:.1f}min)")
    print(f"{'=' * 70}\n")

    # Step 3: Save pass2 results
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Pass2 results saved to: {OUTPUT_FILE}")

    # Step 4: Merge with pass1
    pass1_path = OUTPUT_DIR / "platform_detection_results.json"
    final = merge_results(pass1_path, results)

    # Step 5: Save final merged report
    final_report_path = OUTPUT_DIR / "platform_detection_results_final.json"
    with open(final_report_path, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    print(f"Final merged results saved to: {final_report_path}")

    # Step 6: Print summary
    print(f"\n{'=' * 70}")
    print("FINAL SUMMARY (Pass 1 + Pass 2)")
    print(f"{'=' * 70}")
    print(f"  Total municipios:         {final['total']}")
    print(f"  Pass 1 detected (Betha):  {final['pass1_detected']}")
    print(f"  Pass 2 detected (Proprio): {final['pass2_newly_detected']}")
    print(
        f"  Total detected:           {final['total_detected']} ({final['total_detected'] / final['total'] * 100:.1f}%)"
    )
    print(f"  Still not found:          {final['not_found']} ({final['not_found'] / final['total'] * 100:.1f}%)")
    print(f"  Errors:                   {final['errors']}")
    print("\nPlatform distribution:")
    for plat, count in final["platforms"].items():
        print(f"  {plat}: {count} ({count / final['total'] * 100:.1f}%)")

    # Step 7: Generate YAML
    yaml_entries = generate_final_yaml(final)
    output_yaml = OUTPUT_DIR / "platform_detection_final_config.yaml"
    with open(output_yaml, "w", encoding="utf-8") as f:
        f.write(yaml_entries)
    print(f"\nFinal YAML config saved to: {output_yaml}")

    # Show how many config lines were generated
    yaml_lines = yaml_entries.split("\n")
    len(
        [
            ln
            for ln in yaml_lines
            if not ln.strip().startswith("-") and ln.strip().endswith(":") and ln[0] != "#" and ln[0] != " "
        ]
    )
    print(
        f"YAML entries: ~{len([ln for ln in yaml_lines if ln.strip().endswith(':') and not ln.startswith('#') and not ln.startswith(' ')])} config blocks generated"
    )

    # Step 8: Print pass2 detected cities
    print("\nNewly detected cities (Pass 2):")
    for d in sorted(final["detected_list_pass2"], key=lambda x: x["municipio"]):
        print(f"  {d['municipio']:40s} -> {d['url']}")


if __name__ == "__main__":
    main()
