#!/usr/bin/env python3
"""
SC 200km Radius Analysis — Foco total em Santa Catarina.

1. Fetch all SC municipalities with lat/lon from IBGE API
2. Calculate Haversine distance from Florianópolis (-27.5969, -48.5495)
3. Filter municipalities within 200km radius
4. Cross-reference with datalake: bids, contracts, suppliers
5. Output comprehensive report

Usage:
    python scripts/datalake-sc-200km.py
    python scripts/datalake-sc-200km.py --radius 150
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import UTC, datetime
from typing import Any

import httpx
import psycopg2
import psycopg2.extras

# ── Config ──
_LOCAL_DSN = os.environ.get("LOCAL_DATALAKE_DSN", "")

FLORIPA_LAT = -27.5969
FLORIPA_LON = -48.5495
FLORIPA_NAME = "Florianópolis"
FLORIPA_UF = "SC"

IBGE_API = "https://servicodados.ibge.gov.br/api/v1"


def _today() -> str:
    return datetime.now(UTC).isoformat()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two points using Haversine formula."""
    R = 6371.0  # noqa: N806  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def get_conn():
    return psycopg2.connect(_LOCAL_DSN)


# ============================================================
# Step 1: Fetch SC municipalities with coordinates
# ============================================================


def fetch_sc_municipalities() -> dict[str, dict]:
    """Fetch all SC municipalities from IBGE API with lat/lon."""
    url = f"{IBGE_API}/localidades/estados/SC/municipios"
    print(f"[IBGE] Fetching SC municipalities: {url}")

    with httpx.Client(timeout=30) as session:
        resp = session.get(url)
        resp.raise_for_status()
        data = resp.json()

    result: dict[str, dict] = {}
    for mun in data:
        nome = mun.get("nome", "").strip()
        mun_id = mun.get("id")
        # IBGE API v1 doesn't include coordinates in the list endpoint.
        # Need to fetch each municipality detail for coordinates.
        result[nome.upper()] = {
            "ibge_id": mun_id,
            "nome": nome,
            "uf": "SC",
            "lat": None,
            "lon": None,
        }

    print(f"[IBGE] {len(result)} municipalities found in SC catalog")
    return result


def enrich_coordinates(municipalities: dict[str, dict], delay: float = 0.1):
    """Fetch coordinates for each SC municipality from IBGE detail endpoint."""
    total = len(municipalities)
    fetched = 0

    with httpx.Client(timeout=30) as session:
        for nome_upper, info in municipalities.items():
            mun_id = info["ibge_id"]
            if not mun_id:
                continue

            try:
                resp = session.get(f"{IBGE_API}/localidades/municipios/{mun_id}")
                if resp.status_code == 200:
                    detail = resp.json()
                    # Coordinates in IBGE response
                    centro = detail.get("centro", detail.get("coordenadas", {}))
                    if centro:
                        info["lat"] = centro.get("latitude") or centro.get("lat")
                        info["lon"] = centro.get("longitude") or centro.get("lon")

                    # Also try microrregiao > mesorregiao > UF > regiao nesting
                    if info["lat"] is None:
                        # Try to find coordinates in nested structure
                        pass

                    fetched += 1
            except Exception:
                pass

            time.sleep(delay)
            if fetched % 50 == 0:
                pct = fetched / total * 100
                print(f"\r[COORDS] {fetched}/{total} ({pct:.1f}%)", end="")
                sys.stdout.flush()

    print(f"\r[COORDS] {fetched}/{total} coordinates fetched")
    return municipalities


# ============================================================
# Step 2: Filter to 200km radius
# ============================================================


def filter_radius(
    municipalities: dict[str, dict], center_lat: float, center_lon: float, radius_km: float = 200
) -> dict[str, dict]:
    """Filter municipalities within radius_km of center point."""
    within: dict[str, dict] = {}
    outside: dict[str, dict] = {}

    for nome_upper, info in municipalities.items():
        lat = info.get("lat")
        lon = info.get("lon")
        if lat is None or lon is None:
            continue

        dist = haversine_km(center_lat, center_lon, float(lat), float(lon))
        info["distancia_km"] = round(dist, 1)

        if dist <= radius_km:
            within[nome_upper] = info
        else:
            outside[nome_upper] = info

    return within


# ============================================================
# Step 3: Fetch SC municipalities from IBGE with coordinates via aggregate endpoint
# ============================================================


def fetch_sc_with_coords_via_malha() -> dict[str, dict]:
    """
    Alternative: use IBGE malha territorial or localidades with direct coordinate fetch.
    This approach fetches the list then batches detail requests.
    """
    municipalities = fetch_sc_municipalities()

    # Use geolocalidades endpoint for batch coordinate data
    print("[IBGE] Fetching coordinates via localidades/municipios...")

    # Actually, let's use a different approach. The IBGE API localidades endpoint
    # returns coordinates in the municipality detail. But we can also use the
    # aggregates API or a CSV-based approach.

    # Fastest approach: use hardcoded SC municipality coordinates
    # (295 municipalities — fetching one-by-one takes ~30s with 0.1s delay)

    return enrich_coordinates(municipalities)


# ============================================================
# Step 4: Cross with datalake
# ============================================================


def cross_datalake(within: dict[str, dict], conn) -> dict[str, Any]:
    """Cross-reference radius municipalities with datalake data."""
    cur = conn.cursor()

    mun_names = list(within.keys())
    # Normalize: upper, strip, accents
    report: dict[str, Any] = {
        "centro": {"nome": FLORIPA_NAME, "uf": FLORIPA_UF, "lat": FLORIPA_LAT, "lon": FLORIPA_LON},
        "raio_km": 200,
        "municipios_dentro": len(mun_names),
        "fornecedores": {},
        "bids": {},
        "contratos": {},
    }

    # ── Suppliers within radius ──
    # Match by municipality name (case-insensitive, accent-insensitive)
    # Use ILIKE with unaccent if available, otherwise simple matching
    print(f"\n[CROSS] Cross-referencing {len(mun_names)} municipalities...")

    # Build municipality filter for SQL
    # Since we have municipality names with accents, use ILIKE ANY
    mun_list = list(within.values())
    mun_sql_list = [m["nome"].upper() for m in mun_list]

    # ── Bids ──
    placeholders = ",".join(["%s"] * len(mun_sql_list))
    cur.execute(
        f"""
        SELECT COUNT(*) as total_bids,
               COUNT(DISTINCT municipio) as muns_com_bids,
               SUM(valor_estimado) as valor_total_estimado
        FROM pncp_raw_bids
        WHERE uf = 'SC' AND UPPER(municipio) IN ({placeholders})
    """,
        mun_sql_list,
    )
    row = cur.fetchone()
    report["bids"] = {
        "total": row[0] or 0,
        "municipios_com_bids": row[1] or 0,
        "valor_total_estimado": float(row[2] or 0),
    }

    # Bids by municipality
    cur.execute(
        f"""
        SELECT UPPER(municipio), COUNT(*), SUM(valor_estimado)
        FROM pncp_raw_bids
        WHERE uf = 'SC' AND UPPER(municipio) IN ({placeholders})
        GROUP BY UPPER(municipio)
        ORDER BY COUNT(*) DESC
        LIMIT 20
    """,
        mun_sql_list,
    )
    report["bids"]["por_municipio"] = [
        {"municipio": r[0], "total": r[1], "valor_total": float(r[2] or 0)} for r in cur.fetchall()
    ]

    # ── Contracts ──
    cur.execute(
        f"""
        SELECT COUNT(*) as total_contracts,
               COUNT(DISTINCT municipio) as muns_com_contracts,
               COUNT(DISTINCT ni_fornecedor) as fornecedores_unicos,
               SUM(valor_global) as valor_total
        FROM pncp_supplier_contracts
        WHERE uf = 'SC' AND UPPER(municipio) IN ({placeholders})
    """,
        mun_sql_list,
    )
    row = cur.fetchone()
    report["contratos"] = {
        "total": row[0] or 0,
        "municipios_com_contratos": row[1] or 0,
        "fornecedores_unicos": row[2] or 0,
        "valor_total": float(row[3] or 0),
    }

    # ── Engineering/Construction Suppliers in radius ──
    eng_keywords = [
        "engenh",
        "constru",
        "obra",
        "edific",
        "paviment",
        "saneamento",
        "infraestrutura",
        "incorporadora",
        "empreiteira",
        "construtora",
        "terraplenagem",
        "fundacao",
        "estrutura",
        "predial",
        "rodovi",
        "drenagem",
        "asfalto",
        "concreto",
        "reforma",
        "arquitet",
    ]
    eng_conditions = " OR ".join(
        [f"(LOWER(nome_fornecedor) LIKE '%{k}%' OR LOWER(objeto_contrato) LIKE '%{k}%')" for k in eng_keywords]
    )

    cur.execute(
        f"""
        SELECT ni_fornecedor, nome_fornecedor,
               COUNT(*) as contratos,
               SUM(valor_global) as valor_total,
               COUNT(DISTINCT municipio) as municipios
        FROM pncp_supplier_contracts
        WHERE uf = 'SC'
          AND UPPER(municipio) IN ({placeholders})
          AND ({eng_conditions})
          AND ni_fornecedor IS NOT NULL
          AND LENGTH(ni_fornecedor) = 14
        GROUP BY ni_fornecedor, nome_fornecedor
        ORDER BY contratos DESC
    """,
        mun_sql_list,
    )

    report["fornecedores_engenharia"] = {
        "total": cur.rowcount if hasattr(cur, "rowcount") else 0,
        "top": [
            {"cnpj": r[0], "nome": r[1], "contratos": r[2], "valor_total": float(r[3] or 0), "municipios": r[4]}
            for r in cur.fetchall()
        ],
    }

    report["fornecedores_engenharia"]["total"] = len(report["fornecedores_engenharia"]["top"])

    cur.close()
    return report


# ============================================================
# Step 5: Enrich engineering suppliers into enriched_entities
# ============================================================


def enrich_suppliers_radius(report: dict, within: dict[str, dict], conn):
    """Store engineering suppliers within radius into enriched_entities."""
    suppliers = report.get("fornecedores_engenharia", {}).get("top", [])
    if not suppliers:
        print("[ENRICH] No suppliers to enrich")
        return 0

    cur = conn.cursor()
    enriched = 0

    # Batch insert
    batch_data = []
    for s in suppliers:
        cnpj = s["cnpj"]
        within.values()
        # Find which municipalities this supplier operates in
        data = {
            "cnpj": cnpj,
            "nome": s["nome"],
            "stats": {
                "contratos_no_raio": s["contratos"],
                "valor_total_no_raio": s["valor_total"],
                "municipios_no_raio": s["municipios"],
            },
            "tipo": "engenharia_construcao",
            "uf": "SC",
            "raio_200km_florianopolis": True,
            "enriched_at": _today(),
        }

        batch_data.append(
            (
                "fornecedor",
                cnpj,
                psycopg2.extras.Json(data),
                _today(),
            )
        )

    if batch_data:
        psycopg2.extras.execute_values(
            cur,
            """INSERT INTO enriched_entities (entity_type, entity_id, data, enriched_at)
            VALUES %s ON CONFLICT (entity_type, entity_id) DO UPDATE
            SET data = EXCLUDED.data, enriched_at = EXCLUDED.enriched_at""",
            batch_data,
            template="(%s, %s, %s, %s)",
        )
        conn.commit()
        enriched = len(batch_data)

    cur.close()
    return enriched


# ============================================================
# Main
# ============================================================


def main():
    parser = argparse.ArgumentParser(description="SC 200km radius analysis")
    parser.add_argument("--radius", type=float, default=200, help="Radius in km (default: 200)")
    parser.add_argument("--output", "-o", default=None, help="Save report JSON (default: stdout)")
    parser.add_argument(
        "--enrich", action="store_true", default=True, help="Store results in enriched_entities (default: True)"
    )
    parser.add_argument("--no-enrich", action="store_false", dest="enrich", help="Skip storing in enriched_entities")
    args = parser.parse_args()

    t0 = time.time()

    print("=" * 60)
    print("SC 200km RADIUS ANALYSIS — Florianópolis")
    print(f"Raio: {args.radius}km")
    print("=" * 60)

    # Step 1: Fetch SC municipalities with coordinates
    print("\n[1/3] Fetching SC municipalities with coordinates...")
    municipalities = fetch_sc_with_coords_via_malha()

    # Step 2: Filter to radius
    print(f"\n[2/3] Filtering to {args.radius}km radius from Florianópolis...")
    within = filter_radius(municipalities, FLORIPA_LAT, FLORIPA_LON, args.radius)
    print(f"[FILTER] {len(within)} municipalities within {args.radius}km")

    # Show distance bands
    bands = {"0-50km": 0, "50-100km": 0, "100-150km": 0, "150-200km": 0}
    for info in within.values():
        d = info.get("distancia_km", 999)
        if d <= 50:
            bands["0-50km"] += 1
        elif d <= 100:
            bands["50-100km"] += 1
        elif d <= 150:
            bands["100-150km"] += 1
        else:
            bands["150-200km"] += 1
    for band, count in bands.items():
        print(f"  {band}: {count} municípios")

    # Closest and farthest
    sorted_within = sorted(within.items(), key=lambda x: x[1].get("distancia_km", 999))
    print(f"  Mais próximo: {sorted_within[0][1]['nome']} ({sorted_within[0][1]['distancia_km']} km)")
    print(f"  Mais distante: {sorted_within[-1][1]['nome']} ({sorted_within[-1][1]['distancia_km']} km)")

    # Step 3: Cross with datalake
    print("\n[3/3] Cross-referencing with datalake...")
    conn = get_conn()
    report = cross_datalake(within, conn)

    # Enrich
    if args.enrich:
        enriched = enrich_suppliers_radius(report, within, conn)
        print(f"\n[ENRICH] {enriched} engineering suppliers stored in enriched_entities")

    conn.close()

    # ── Print report ──
    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    print("RESULTADO — SC Raio 200km de Florianópolis")
    print("=" * 60)
    print(f"Municípios dentro do raio: {report['municipios_dentro']}")
    print("\nBIDS:")
    print(f"  Total: {report['bids']['total']:,}")
    print(f"  Valor estimado total: R$ {report['bids']['valor_total_estimado']:,.0f}")
    print(f"  Municípios com bids: {report['bids']['municipios_com_bids']}")
    print("\nCONTRATOS:")
    print(f"  Total: {report['contratos']['total']:,}")
    print(f"  Valor total: R$ {report['contratos']['valor_total']:,.0f}")
    print(f"  Fornecedores únicos: {report['contratos']['fornecedores_unicos']:,}")
    print("\nFORNECEDORES ENGENHARIA/CONSTRUÇÃO:")
    print(f"  Total: {report['fornecedores_engenharia']['total']:,}")
    top_suppliers = report["fornecedores_engenharia"]["top"][:15]
    print(f"\n  {'CNPJ':<18} {'Nome':<45} {'Contratos':>10} {'Valor Total':>20}")
    print(f"  {'-' * 18} {'-' * 45} {'-' * 10} {'-' * 20}")
    for s in top_suppliers:
        print(f"  {s['cnpj']:<18} {s['nome'][:43]:<45} {s['contratos']:>10,} R$ {s['valor_total']:>18,.0f}")

    print(f"\nTempo: {elapsed:.1f}s")

    # Save output
    out_path = args.output or f"docs/intel/sc-200km-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"Relatório salvo: {out_path}")


if __name__ == "__main__":
    main()
