#!/usr/bin/env python3
"""
Geocodifica entes sem coordenadas na tabela sc_public_entities.

3 niveis de geocoding:
  1. Cache local (data/geocode_cache.json)
  2. IBGE API (nome oficial do municipio)
  3. Nominatim/OSM (coordenadas por nome do municipio)

Usage:
    python scripts/fix/geocode_missing_entities.py --dry-run        # Simular sem alterar banco
    python scripts/fix/geocode_missing_entities.py --commit         # Executar e persistir
    python scripts/fix/geocode_missing_entities.py --report-only    # Apenas relatorio
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import psycopg2  # noqa: E402
import psycopg2.extras  # noqa: E402

from config.logging_config import get_logger  # noqa: E402
from config.settings import DEFAULT_DSN  # noqa: E402
from scripts.lib.geocode import FLORIANOPOLIS, Geocoder, haversine, validate_coords  # noqa: E402

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _get_conn():
    """Create database connection from DEFAULT_DSN."""
    return psycopg2.connect(DEFAULT_DSN)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

SQL_FETCH_MISSING = """
    SELECT id, razao_social, codigo_ibge, municipio, natureza_juridica,
           latitude, longitude, distancia_fk, raio_200km
    FROM sc_public_entities
    WHERE latitude IS NULL AND is_active = TRUE
    ORDER BY codigo_ibge NULLS LAST
"""

SQL_UPDATE_COORDS = """
    UPDATE sc_public_entities
    SET latitude = %s, longitude = %s,
        distancia_fk = %s, raio_200km = %s
    WHERE id = %s AND latitude IS NULL
"""

SQL_UPDATE_WITH_METHOD = """
    UPDATE sc_public_entities
    SET latitude = %s, longitude = %s,
        distancia_fk = %s, raio_200km = %s,
        geocode_method = %s
    WHERE id = %s AND latitude IS NULL
"""

SQL_ADD_GEOCODE_METHOD = """
    ALTER TABLE sc_public_entities
    ADD COLUMN IF NOT EXISTS geocode_method TEXT
"""

SQL_COUNT_MISSING = """
    SELECT COUNT(*) FROM sc_public_entities WHERE latitude IS NULL
"""

SQL_COUNT_WITH_COORDS = """
    SELECT COUNT(*) FROM sc_public_entities WHERE latitude IS NOT NULL
"""

SQL_REMAINING_DETAIL = """
    SELECT id, razao_social, codigo_ibge, municipio, natureza_juridica
    FROM sc_public_entities
    WHERE latitude IS NULL AND is_active = TRUE
    ORDER BY codigo_ibge NULLS LAST, razao_social
"""


# ---------------------------------------------------------------------------
# Ensure geocode_method column exists
# ---------------------------------------------------------------------------


def _ensure_geocode_method_column(conn) -> bool:
    """Add geocode_method column if it does not exist.

    Returns:
        True if the column was added, False if it already existed.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(SQL_ADD_GEOCODE_METHOD)
            conn.commit()
            log.info("Coluna 'geocode_method' garantida na tabela sc_public_entities")
            return True
    except Exception as e:
        log.warning("Nao foi possivel adicionar coluna geocode_method: %s", e)
        conn.rollback()
        return False


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report() -> dict:
    """Gera relatorio dos entes sem coordenadas e estatisticas.

    Returns:
        Dict com estatisticas de cobertura de coordenadas.
    """
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            # Total sem coordenadas
            cur.execute(SQL_COUNT_MISSING)
            total_missing = cur.fetchone()[0]

            # Total com coordenadas
            cur.execute(SQL_COUNT_WITH_COORDS)
            total_with = cur.fetchone()[0]

            total = total_missing + total_with

            # Detalhes dos que continuam sem coordenadas
            cur.execute(SQL_REMAINING_DETAIL)
            remaining = [
                {
                    "id": r[0],
                    "razao_social": r[1],
                    "codigo_ibge": r[2],
                    "municipio": r[3],
                    "natureza_juridica": r[4],
                    "motivo": _motivo_falta_coordenada(r[2], r[3]),
                }
                for r in cur.fetchall()
            ]

        report = {
            "total_entes": total,
            "total_com_coordenadas": total_with,
            "total_sem_coordenadas": total_missing,
            "pct_cobertura": round(100.0 * total_with / total, 1) if total > 0 else 0,
            "entes_sem_coordenadas": remaining,
        }
        return report

    finally:
        conn.close()


def _motivo_falta_coordenada(codigo_ibge: str | None, municipio: str | None) -> str:
    """Determina o motivo pelo qual um ente continua sem coordenadas."""
    if not codigo_ibge and not municipio:
        return "Sem codigo_ibge e sem municipio — impossivel geocodificar"
    if not codigo_ibge and municipio:
        return f"Geocodificacao por nome falhou para municipio '{municipio}'"
    if codigo_ibge and not municipio:
        return f"Codigo IBGE {codigo_ibge} presente mas municipio vazio — Nominatim sem nome"
    return f"Geocodificacao falhou para IBGE {codigo_ibge} / '{municipio}'"


# ---------------------------------------------------------------------------
# Main geocoding execution
# ---------------------------------------------------------------------------


def run_geocode(dry_run: bool = True) -> dict:
    """Executa a geocodificacao dos entes sem coordenadas.

    Args:
        dry_run: Se True, simula sem alterar o banco.

    Returns:
        Dict com resultados da operacao.
    """
    conn = _get_conn()
    geocoder = Geocoder()

    try:
        # Garantir coluna geocode_method
        has_method_column = _ensure_geocode_method_column(conn)

        # Buscar entes sem coordenadas
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(SQL_FETCH_MISSING)
            rows = cur.fetchall()

        log.info("Encontrados %d entes sem coordenadas", len(rows))

        if not rows:
            conn.close()
            return {"total": 0, "message": "Nenhum ente sem coordenadas"}

        # Geocodificar (agrupado por municipio)
        resultados = geocoder.geocode_batch(rows)
        log.info(
            "Geocoding: %d municipios OK, %d falhas (entidades: %d totais, %d IDs atualizaveis)",
            resultados["geocoded"],
            resultados["failed"],
            resultados["total_entities"],
            len(resultados["updated_ids"]),
        )

        if not dry_run:
            updated = 0
            entity_map = {r["id"]: r for r in rows}

            for entity_id in resultados["updated_ids"]:
                entity = entity_map.get(entity_id)
                if not entity:
                    continue

                cache_key = entity.get("codigo_ibge") or entity.get("municipio")
                cache_entry = geocoder.cache.get(cache_key, {})
                if not isinstance(cache_entry, dict):
                    continue

                lat = cache_entry.get("lat")
                lon = cache_entry.get("lon")
                method = cache_entry.get("method", "unknown")

                if lat is not None and lon is not None and validate_coords(lat, lon):
                    # Calcular distancia ate Florianopolis
                    distancia = haversine(lat, lon, *FLORIANOPOLIS)
                    raio_200 = distancia <= 200

                    with conn.cursor() as cur:
                        if has_method_column:
                            cur.execute(
                                SQL_UPDATE_WITH_METHOD,
                                [
                                    lat,
                                    lon,
                                    round(distancia, 2),
                                    raio_200,
                                    method,
                                    entity_id,
                                ],
                            )
                        else:
                            cur.execute(
                                SQL_UPDATE_COORDS,
                                [
                                    lat,
                                    lon,
                                    round(distancia, 2),
                                    raio_200,
                                    entity_id,
                                ],
                            )
                    updated += 1

            conn.commit()
            log.info("Commitado: %d entes atualizados com coordenadas", updated)
            resultados["updated"] = updated

            # Log do cache salvo
            cache_entries = len(geocoder.cache)
            log.info("Cache salvo em %s com %d entradas", geocoder.cache_file, cache_entries)
        else:
            log.info("DRY-RUN: nenhum UPDATE persistido")
            estimativa = len(resultados["updated_ids"])
            log.info("Estimativa: %d entes seriam atualizados", estimativa)
            resultados["updated"] = 0

        resultados["total"] = len(rows)
        resultados["geocoder_stats"] = dict(geocoder.stats)
        return resultados

    except Exception as e:
        log.error("Erro fatal: %s", e)
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Geocodifica entes sem coordenadas na tabela sc_public_entities",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Simular sem alterar o banco (padrao)",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        default=False,
        help="Executar e persistir alteracoes no banco",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        default=False,
        help="Apenas gerar relatorio dos entes sem coordenadas",
    )
    return parser.parse_args(argv)


def main() -> None:
    """Entry point."""
    args = parse_args()

    if args.report_only:
        report = generate_report()
        print("\n=== RELATORIO DE COBERTURA DE COORDENADAS ===\n")
        print(f"Total de entes:        {report['total_entes']}")
        print(f"Com coordenadas:       {report['total_com_coordenadas']}")
        print(f"Sem coordenadas:       {report['total_sem_coordenadas']}")
        print(f"Cobertura:             {report['pct_cobertura']}%")
        print()

        if report["entes_sem_coordenadas"]:
            print("Entes sem coordenadas:")
            print(f"{'ID':>6} {'Razao Social':<50} {'IBGE':<8} {'Municipio':<25} {'Motivo'}")
            print("-" * 120)
            for ente in report["entes_sem_coordenadas"]:
                print(
                    f"{ente['id']:>6} "
                    f"{ente['razao_social'][:48]:<50} "
                    f"{ente['codigo_ibge'] or '-':<8} "
                    f"{ente['municipio'] or '-':<25} "
                    f"{ente['motivo']}"
                )
        else:
            print("Nenhum ente sem coordenadas encontrado.")
        return

    # Determinar modo dry_run
    dry_run = not args.commit
    if args.dry_run:
        dry_run = True

    if dry_run:
        log.info("Modo DRY-RUN: nenhuma alteracao sera persistida")
    else:
        log.info("Modo COMMIT: alteracoes serao persistidas no banco")

    resultados = run_geocode(dry_run=dry_run)

    if "error" in resultados:
        log.error("Falha na execucao: %s", resultados["error"])
        sys.exit(1)

    if "message" in resultados:
        log.info(resultados["message"])
        return

    print("\n=== RESULTADO DA GEOCODIFICACAO ===\n")
    print(f"Total de entes processados: {resultados.get('total', 0)}")
    print(f"Municipios geocodificados:  {resultados.get('geocoded', 0)}")
    print(f"Falhas:                     {resultados.get('failed', 0)}")
    print(f"Entes atualizados:          {resultados.get('updated', 0)}")
    print(f"Total municipios unicos:    {resultados.get('total_municipios', 0)}")

    cache_hits = resultados.get("geocoder_stats", {}).get("cache_hit", 0)
    nominatim_calls = resultados.get("geocoder_stats", {}).get("nominatim", 0)
    print(f"Cache hits:                 {cache_hits}")
    print(f"Chamadas Nominatim:         {nominatim_calls}")


if __name__ == "__main__":
    main()
