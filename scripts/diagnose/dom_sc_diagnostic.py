"""DOM-SC Crawler Diagnostic — Extra Consultoria.

Diagnostico completo do crawler DOM-SC para identificar falhas de cobertura:
conectividade, autenticacao, parser, paginacao, e gaps por municipio.

Usage:
    python scripts/diagnose/dom_sc_diagnostic.py
    python scripts/diagnose/dom_sc_diagnostic.py --sample 50
    python scripts/diagnose/dom_sc_diagnostic.py --days 365
    python scripts/diagnose/dom_sc_diagnostic.py --output docs/research/dom-sc-diagnostic-2026-07-11.md
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

# Add project root to path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (mirrors dom_sc_crawler for independent diagnostic)
# ---------------------------------------------------------------------------

BASE_URL = "https://diariomunicipal.sc.gov.br"
CATEGORIAS = [6, 7, 28]
CATEGORIA_NOMES: dict[int, str] = {
    6: "Contrato",
    7: "Convenio",
    28: "Empenho",
}
HTTP_TIMEOUT = 60

# ---------------------------------------------------------------------------
# HTTP Client (independent of dom_sc_crawler's internal helpers)
# ---------------------------------------------------------------------------


def _api_request(url: str, params: dict[str, Any]) -> dict | None:
    """Make a sync HTTP GET request to the DOM-SC API.

    Mirrors dom_sc_crawler._api_request for independent diagnostic.
    """
    import base64
    import urllib.error
    import urllib.request

    dom_sc_cpf = os.getenv("DOM_SC_CPF", "")
    dom_sc_cnpj = os.getenv("DOM_SC_CNPJ", "")
    dom_sc_api_key = os.getenv("DOM_SC_API_KEY", "")

    from scripts.crawl.security import USER_AGENT, sanitize_url_param

    query = "&".join(f"{k}={sanitize_url_param(v)}" for k, v in params.items())
    full_url = f"{url}?{query}"

    credentials = f"{dom_sc_cpf}:{dom_sc_cnpj}"
    encoded_creds = base64.b64encode(credentials.encode("utf-8")).decode("ascii")

    req = urllib.request.Request(full_url)
    req.add_header("Authorization", f"Basic {encoded_creds}")
    req.add_header("X-API-Key", dom_sc_api_key)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        return {"_error": f"HTTP {exc.code}", "_detail": exc.read().decode("utf-8", errors="replace")[:500]}
    except urllib.error.URLError as exc:
        return {"_error": "URLError", "_detail": str(exc.reason)}
    except Exception as exc:
        return {"_error": type(exc).__name__, "_detail": str(exc)}


def _test_site_accessibility() -> dict:
    """Test basic site accessibility via various endpoint patterns."""
    results: dict[str, Any] = {}
    import urllib.error
    import urllib.request

    # Test 1: Homepage
    for label, test_url in [
        ("homepage", BASE_URL),
        ("api_docs", f"{BASE_URL}/?r=site/page&view=integracao"),
        ("site_login", f"{BASE_URL}/?r=site/login"),
    ]:
        try:
            req = urllib.request.Request(test_url)
            from scripts.crawl.security import USER_AGENT

            req.add_header("User-Agent", USER_AGENT)
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read()
                results[label] = {
                    "status": resp.status,
                    "bytes": len(body),
                    "content_type": resp.headers.get("Content-Type", ""),
                }
        except urllib.error.HTTPError as exc:
            results[label] = {"status": exc.code, "error": str(exc)[:200]}
        except Exception as exc:
            results[label] = {"status": "ERROR", "error": str(exc)[:200]}
    return results


def _test_all_categorias(date_from: date, date_to: date) -> dict[str, Any]:
    """Test API authentication and data retrieval for all categorias."""
    results: dict[str, Any] = {}
    for cat in CATEGORIAS:
        url = f"{BASE_URL}/?r=remote/search"
        params: dict[str, Any] = {
            "categoria": cat,
            "data_inicio": date_from.strftime("%d/%m/%Y"),
            "data_fim": date_to.strftime("%d/%m/%Y"),
            "com_metadados": 1,
        }
        data = _api_request(url, params)
        if data is None:
            results[f"categoria_{cat}"] = {"status": "ERROR", "erro": "No response (None)"}
        elif "_error" in data:
            results[f"categoria_{cat}"] = {"status": "FAIL", "erro": f"{data['_error']}: {data.get('_detail', '')}"}
        else:
            publicacoes = data.get("publicacoes", [])
            if not isinstance(publicacoes, list):
                publicacoes = []
            municipios = Counter()
            orgaos = Counter()
            for p in publicacoes:
                muni = (p.get("municipio") or "").strip()
                if muni:
                    municipios[muni] += 1
                orgao = (p.get("orgao_cnpj") or "")[:8]
                if orgao:
                    orgaos[orgao] += 1

            results[f"categoria_{cat}"] = {
                "status": "OK",
                "nome": CATEGORIA_NOMES.get(cat, f"Categoria {cat}"),
                "total_publicacoes": len(publicacoes),
                "total_municipios": len(municipios),
                "total_orgaos_8": len(orgaos),
                "top5_municipios": municipios.most_common(5),
                "has_metadados": any(p.get("metadados") for p in publicacoes[:50]),
                "sample_municipios": sorted(municipios.keys())[:10],
            }
    return results


def _check_pagination_api(date_from: date, date_to: date) -> dict[str, Any]:
    """Check if the API supports pagination via pagina/offset parameter."""
    results: dict[str, Any] = {}
    url = f"{BASE_URL}/?r=remote/search"
    params: dict[str, Any] = {
        "categoria": 6,
        "data_inicio": date_from.strftime("%d/%m/%Y"),
        "data_fim": date_to.strftime("%d/%m/%Y"),
        "com_metadados": 1,
    }

    # Test without pagination first
    data = _api_request(url, params)
    if data is None or "_error" in (data or {}):
        results["pagination_supported"] = "UNKNOWN"
        results["error"] = "API not available for pagination test"
        return results

    total_sem_pagina = len(data.get("publicacoes", []))

    # Try with pagina=1
    params["pagina"] = 1
    data_p1 = _api_request(url, params)
    total_p1 = len(data_p1.get("publicacoes", [])) if data_p1 and "_error" not in data_p1 else 0

    # Try with pagina=2
    params["pagina"] = 2
    data_p2 = _api_request(url, params)
    total_p2 = len(data_p2.get("publicacoes", [])) if data_p2 and "_error" not in data_p2 else 0

    # Try with offset=0 and offset=100
    del params["pagina"]

    params["offset"] = 0
    data_o0 = _api_request(url, params)
    total_o0 = len(data_o0.get("publicacoes", [])) if data_o0 and "_error" not in data_o0 else 0

    params["offset"] = 100
    data_o100 = _api_request(url, params)
    total_o100 = len(data_o100.get("publicacoes", [])) if data_o100 and "_error" not in data_o100 else 0

    results.update(
        {
            "total_sem_paginacao": total_sem_pagina,
            "total_com_pagina_1": total_p1,
            "total_com_pagina_2": total_p2,
            "total_com_offset_0": total_o0,
            "total_com_offset_100": total_o100,
            "pagination_supported": (
                "YES"
                if total_p1 > 0 and total_p2 >= 0 and total_p1 != total_p2
                else "PARTIAL"
                if total_p1 > 0
                else "NO"
            ),
            "offset_supported": ("YES" if total_o0 > 0 and total_o100 >= 0 and total_o0 != total_o100 else "NO"),
            "observations": [],
        }
    )

    # Build observations
    obs = results["observations"]
    if total_sem_pagina > 1000 and not results["pagination_supported"]:
        obs.append("WARN: Response contains >1000 records without pagination — possible truncation")
    if results["pagination_supported"] == "YES":
        obs.append("Pagination via 'pagina' parameter IS supported by the API")
    if results["offset_supported"] == "YES":
        obs.append("Offset via 'offset' parameter IS supported by the API")
    if results["pagination_supported"] == "NO" and results["offset_supported"] == "NO":
        obs.append("Neither 'pagina' nor 'offset' parameters appear to be supported")

    return results


def _test_html_scraping_fallback() -> dict[str, Any]:
    """Test if the DOM-SC site is reachable for HTML scraping fallback.

    Checks the public search page and validates that basic HTML content
    can be retrieved (no anti-bot, no JS challenge).
    """
    results: dict[str, Any] = {}
    import urllib.error
    import urllib.request

    from scripts.crawl.security import USER_AGENT

    test_urls = [
        ("public_search", f"{BASE_URL}/?r=site/publication/search"),
        ("advanced_search", f"{BASE_URL}/?r=site/advancedSearch"),
    ]

    for label, url in test_urls:
        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", USER_AGENT)
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                results[label] = {
                    "status": resp.status,
                    "bytes": len(body),
                    "has_html": "<html" in body.lower() or "<!doctype" in body.lower(),
                    "has_captcha": "captcha" in body.lower() or "recaptcha" in body.lower(),
                    "has_form": "<form" in body.lower(),
                    "sample": body[:500],
                }
        except urllib.error.HTTPError as exc:
            results[label] = {"status": exc.code, "error": str(exc)[:200]}
        except Exception as exc:
            results[label] = {"status": "ERROR", "error": str(exc)[:200]}

    return results


def _load_uncovered_entities():
    """Load sample of uncovered entities for targeted testing."""
    from config.settings import DEFAULT_DSN

    try:
        import psycopg2

        conn = psycopg2.connect(DEFAULT_DSN)
        cur = conn.cursor()
        cur.execute(
            """SELECT e.id, e.razao_social, e.cnpj_8, e.municipio, e.codigo_ibge
               FROM sc_public_entities e
               WHERE e.is_active = TRUE
                 AND e.id NOT IN (
                     SELECT entity_id FROM entity_coverage WHERE is_covered = TRUE
                 )
               ORDER BY e.municipio, e.razao_social"""
        )
        cols = [d[0] for d in cur.description]
        entities = [dict(zip(cols, row)) for row in cur.fetchall()]
        cur.close()
        conn.close()
        return entities
    except Exception as exc:
        _logger.warning("Could not load uncovered entities: %s", exc)
        return []


def _check_credential_status() -> dict:
    """Check if required env vars are set."""
    required = ["DOM_SC_CPF", "DOM_SC_CNPJ", "DOM_SC_API_KEY"]
    status: dict[str, str] = {}
    for var in required:
        val = os.getenv(var, "")
        if val:
            status[var] = f"OK ({len(val)} chars)"
        else:
            status[var] = "MISSING"
    return status


def run_diagnostic(sample_size: int = 0, days: int = 90) -> dict:
    """Run full diagnostic of DOM-SC crawler.

    Args:
        sample_size: Number of uncovered entities to sample for targeted testing (0 = skip).
        days: Lookback window for API tests.

    Returns:
        Dict with all diagnostic results.
    """
    date_to = date.today()
    date_from = date_to - timedelta(days=days)

    results: dict[str, Any] = {
        "diagnostic_date": date_to.isoformat(),
        "lookback_days": days,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
    }

    # Check 1: Credentials
    results["credentials"] = _check_credential_status()

    # Check 2: Site accessibility
    results["site_accessibility"] = _test_site_accessibility()

    # Check 3: API per categoria
    results["api_categorias"] = _test_all_categorias(date_from, date_to)

    # Check 4: Pagination
    results["pagination"] = _check_pagination_api(date_from, date_to)

    # Check 5: HTML scraping fallback
    results["html_scraping"] = _test_html_scraping_fallback()

    # Check 6: Uncovered entities sample
    if sample_size > 0:
        uncovered = _load_uncovered_entities()
        results["uncovered_entities"] = {
            "total": len(uncovered),
            "sample": [e for e in uncovered[:sample_size]],
            "municipios": sorted(set(e["municipio"] for e in uncovered if e.get("municipio"))),
        }
    else:
        results["uncovered_entities"] = {"total": "N/A (skipped)", "sample": []}

    # Summary
    api_ok = sum(
        1 for v in results.get("api_categorias", {}).values() if isinstance(v, dict) and v.get("status") == "OK"
    )
    api_fail = sum(
        1 for v in results.get("api_categorias", {}).values() if isinstance(v, dict) and v.get("status") != "OK"
    )
    results["summary"] = {
        "categorias_ok": api_ok,
        "categorias_fail": api_fail,
        "total_categorias": len(CATEGORIAS),
        "site_acessivel": any(v.get("status") == 200 for v in results.get("site_accessibility", {}).values()),
        "pagination_supported": results.get("pagination", {}).get("pagination_supported", "UNKNOWN"),
        "credentials_ok": all(v.startswith("OK") for v in results.get("credentials", {}).values()),
    }

    return results


def print_diagnostic_report(results: dict) -> None:
    """Pretty-print diagnostic results to terminal."""
    print("\n" + "=" * 72)
    print("  DOM-SC CRAWLER DIAGNOSTIC REPORT")
    print(f"  Date: {results['diagnostic_date']}")
    print(f"  Lookback: {results['lookback_days']} days ({results['date_from']} to {results['date_to']})")
    print("=" * 72)

    # Credentials
    print("\n  1. CREDENTIALS")
    creds = results.get("credentials", {})
    all_ok = True
    for var, status in creds.items():
        flag = "OK" if status.startswith("OK") else "MISSING"
        print(f"     {var:20s}: {flag}")
        if not status.startswith("OK"):
            all_ok = False
    if all_ok:
        print("     -> All credentials present")
    else:
        print("     -> WARNING: Missing credentials will cause API failures")

    # Site accessibility
    print("\n  2. SITE ACCESSIBILITY")
    for label, info in results.get("site_accessibility", {}).items():
        if isinstance(info, dict):
            status = info.get("status", "?")
            if status == 200:
                print(f"     {label:20s}: OK ({info.get('bytes', 0)} bytes)")
            else:
                print(f"     {label:20s}: FAIL (status={status}, error={info.get('error', 'N/A')})")

    # API per categoria
    print("\n  3. API PER CATEGORIA")
    api = results.get("api_categorias", {})
    for cat_key, info in api.items():
        if isinstance(info, dict):
            status = info.get("status", "?")
            if status == "OK":
                print(
                    f"     {cat_key:15s}: OK | {info.get('total_publicacoes', 0):6d} pubs | "
                    f"{info.get('total_municipios', 0):3d} municipios | "
                    f"{info.get('total_orgaos_8', 0):3d} orgaos"
                )
                top5 = info.get("top5_municipios", [])
                if top5:
                    print(f"                  Top5: {top5[:3]}")
            else:
                print(f"     {cat_key:15s}: FAIL | {info.get('erro', 'N/A')}")

    # Pagination
    print("\n  4. PAGINATION")
    pag = results.get("pagination", {})
    print(f"     Supported (pagina): {pag.get('pagination_supported', '?')}")
    print(f"     Supported (offset): {pag.get('offset_supported', '?')}")
    print(f"     Records without page param: {pag.get('total_sem_paginacao', '?')}")
    print(f"     Records with pagina=1:      {pag.get('total_com_pagina_1', '?')}")
    print(f"     Records with pagina=2:      {pag.get('total_com_pagina_2', '?')}")
    for obs in pag.get("observations", []):
        print(f"     -> {obs}")

    # HTML scraping
    print("\n  5. HTML SCRAPING FALLBACK")
    html = results.get("html_scraping", {})
    for label, info in html.items():
        if isinstance(info, dict):
            st = info.get("status", "?")
            if st == 200:
                print(
                    f"     {label:20s}: OK ({info.get('bytes', 0)} bytes, "
                    f"captcha={info.get('has_captcha', '?')}, "
                    f"form={info.get('has_form', '?')})"
                )
            else:
                print(f"     {label:20s}: FAIL (status={st})")

    # Uncovered entities
    ue = results.get("uncovered_entities", {})
    total = ue.get("total", 0)
    if isinstance(total, int) and total > 0:
        print(f"\n  6. UNCOVERED ENTITIES: {total}")
        munis = ue.get("municipios", [])
        print(f"     Municipios: {len(munis)}")
        if munis:
            print(f"     Sample: {munis[:15]}")
    else:
        print(f"\n  6. UNCOVERED ENTITIES: {total}")

    # Summary
    print("\n" + "=" * 72)
    print("  SUMMARY")
    print("=" * 72)
    s = results.get("summary", {})
    for key, val in s.items():
        icon = "OK" if val in (True, "YES", 3, 3.0) else "WARN" if val == "PARTIAL" else "FAIL"
        if isinstance(val, bool):
            icon = "OK" if val else "FAIL"
        print(f"     {key:25s}: {icon} ({val})")


def generate_markdown_report(results: dict) -> str:
    """Generate a markdown diagnostic report for docs/research/."""
    lines = []
    lines.append("# DOM-SC Crawler Diagnostic Report")
    lines.append("")
    lines.append(f"> **Date:** {results['diagnostic_date']}")
    lines.append(f"> **Lookback:** {results['lookback_days']} days ({results['date_from']} to {results['date_to']})")
    lines.append("> **Context:** Story COVERAGE-1.5 — DOM-SC Crawler Expansion")
    lines.append("")
    lines.append("## 1. Credentials Status")
    lines.append("")
    lines.append("| Variable | Status |")
    lines.append("|----------|--------|")
    creds = results.get("credentials", {})
    for var, status in creds.items():
        flag = "OK" if status.startswith("OK") else "MISSING"
        lines.append(f"| `{var}` | {flag} |")
    lines.append("")
    lines.append(
        f"**Verdict:** {'All credentials present' if all(s.startswith('OK') for s in creds.values()) else 'WARNING: Missing credentials will cause API failures'}"
    )
    lines.append("")

    lines.append("## 2. Site Accessibility")
    lines.append("")
    lines.append("| Endpoint | Status | Details |")
    lines.append("|----------|--------|---------|")
    for label, info in results.get("site_accessibility", {}).items():
        if isinstance(info, dict):
            st = info.get("status", "?")
            detail = f"{info.get('bytes', 0)} bytes" if st == 200 else info.get("error", "N/A")
            icon = "OK" if st == 200 else "FAIL"
            lines.append(f"| {label} | {icon} | st={st}, {detail} |")
    lines.append("")

    lines.append("## 3. API per Categoria")
    lines.append("")
    lines.append("| Categoria | Status | Publicacoes | Municipios | Orgaos(8) |")
    lines.append("|-----------|--------|-------------|------------|-----------|")
    api = results.get("api_categorias", {})
    for cat_key in sorted(api.keys()):
        info = api[cat_key]
        if isinstance(info, dict):
            status = info.get("status", "?")
            icon = "OK" if status == "OK" else "FAIL"
            pubs = info.get("total_publicacoes", "?")
            munis = info.get("total_municipios", "?")
            orgaos = info.get("total_orgaos_8", "?")
            lines.append(f"| {cat_key} | {icon} | {pubs} | {munis} | {orgaos} |")
    lines.append("")

    lines.append("## 4. Pagination Support")
    lines.append("")
    pag = results.get("pagination", {})
    lines.append(f"- **pagina param:** {pag.get('pagination_supported', '?')}")
    lines.append(f"- **offset param:** {pag.get('offset_supported', '?')}")
    lines.append(f"- Records without page param: {pag.get('total_sem_paginacao', '?')}")
    lines.append(f"- Records with pagina=1: {pag.get('total_com_pagina_1', '?')}")
    lines.append(f"- Records with pagina=2: {pag.get('total_com_pagina_2', '?')}")
    lines.append(f"- Records with offset=0: {pag.get('total_com_offset_0', '?')}")
    lines.append(f"- Records with offset=100: {pag.get('total_com_offset_100', '?')}")
    for obs in pag.get("observations", []):
        lines.append(f"- **Observation:** {obs}")
    lines.append("")

    lines.append("## 5. HTML Scraping Fallback Viability")
    lines.append("")
    lines.append("| Endpoint | Status | Size | Captcha | Form |")
    lines.append("|----------|--------|------|---------|------|")
    html = results.get("html_scraping", {})
    for label, info in html.items():
        if isinstance(info, dict):
            st = info.get("status", "?")
            icon = "OK" if st == 200 else "FAIL"
            sz = info.get("bytes", "?")
            captcha = info.get("has_captcha", "?")
            form = info.get("has_form", "?")
            lines.append(f"| {label} | {icon} | {sz} | {captcha} | {form} |")
    lines.append("")

    lines.append("## 6. Uncovered Entities Analysis")
    lines.append("")
    ue = results.get("uncovered_entities", {})
    total = ue.get("total", 0)
    if isinstance(total, int) and total > 0:
        lines.append(f"- Total uncovered entities in database: **{total}**")
        munis = ue.get("municipios", [])
        lines.append(f"- Municipios represented: **{len(munis)}**")
        if munis:
            lines.append(f"- Sample municipios: `{', '.join(munis[:20])}`")
    else:
        lines.append(f"- Uncovered entities: {total}")
    lines.append("")

    lines.append("## 7. Summary")
    lines.append("")
    s = results.get("summary", {})
    for key, val in s.items():
        lines.append(f"- **{key}:** {val}")
    lines.append("")

    # Recommendations
    lines.append("## 8. Recommendations")
    lines.append("")
    if not all(s.startswith("OK") for s in creds.values()):
        lines.append("- [HIGH] Set missing DOM-SC credential env vars before crawl")
    api_ok = sum(1 for v in api.values() if isinstance(v, dict) and v.get("status") == "OK")
    if api_ok > 0:
        lines.append(f"- [DONE] API REST funcional para {api_ok}/{len(CATEGORIAS)} categorias")
        lines.append("- [ACTION] Expandir janela temporal de 90 para 180 dias")
        if pag.get("pagination_supported") in ("YES", "PARTIAL"):
            lines.append("- [ACTION] Implementar pagination via parametro 'pagina' no crawler")
        if pag.get("total_sem_paginacao", 0) > 500:
            lines.append(f"- [ACTION] Possivel truncamento: {pag['total_sem_paginacao']} records sem paginacao")
    else:
        lines.append("- [HIGH] API REST nao funcional — implementar fallback HTML scraping")
    lines.append("- [ACTION] Melhorar logging por municipio no crawler")
    if isinstance(total, int) and total > 0:
        lines.append(f"- [ACTION] Testar com amostra de municipios nao cobertos ({total} disponiveis)")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DOM-SC Crawler Diagnostic")
    parser.add_argument("--sample", type=int, default=0, help="Sample size of uncovered entities to load")
    parser.add_argument("--days", type=int, default=90, help="Lookback window in days")
    parser.add_argument("--output", type=str, default="", help="Output path for markdown report")
    parser.add_argument("--json", action="store_true", help="Output raw JSON results")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

    print("Running DOM-SC crawler diagnostic...")
    print(f"  Lookback: {args.days} days")
    print(f"  Sample size: {args.sample}")
    print()

    results = run_diagnostic(
        sample_size=args.sample,
        days=args.days,
    )

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    else:
        print_diagnostic_report(results)

    # Generate markdown report
    md = generate_markdown_report(results)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(md, encoding="utf-8")
        print(f"\nReport saved to: {output_path}")

    # Return exit code
    s = results.get("summary", {})
    if s.get("credentials_ok") and s.get("categorias_ok", 0) > 0:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
