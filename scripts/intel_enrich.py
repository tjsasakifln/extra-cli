#!/usr/bin/env python3
"""
Enriquecimento de dados para o comando /intel-busca.

Adiciona ao JSON gerado pelo intel_collect.py:
  - Verificação SICAF (CRC + restrição)
  - Verificação de sanções (CEIS/CNEP/CEPIM/CEAF)
  - Distância sede→edital (OSRM)
  - Dados IBGE (população/PIB) do município do edital
  - Custo estimativo de proposta (presencial vs eletrônico)

Usage:
    python scripts/intel_enrich.py --input docs/intel/intel-CNPJ-slug-YYYY-MM-DD.json
    python scripts/intel_enrich.py --input data.json --skip-sicaf
    python scripts/intel_enrich.py --input data.json --output enriched.json

Requires:
    pip install httpx pyyaml
    playwright install chromium  (para SICAF)
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Fix Windows console encoding
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "buffer") and not isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "buffer") and not isinstance(sys.stderr, io.TextIOWrapper):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except (ValueError, AttributeError):
        pass

# ============================================================
# IMPORT from collect_report_data.py (same pattern as intel_collect.py)
# ============================================================

_scripts_dir = str(Path(__file__).resolve().parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from lib.intel_logging import setup_intel_logging

logger = setup_intel_logging("intel_enrich")

_crd_path = str(Path(__file__).resolve().parent / "collect_report_data.py")
_spec = importlib.util.spec_from_file_location("collect_report_data", _crd_path)
if _spec is None or _spec.loader is None:
    print(f"ERROR: Cannot load {_crd_path}")
    sys.exit(1)
_crd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_crd)

# Pull out the functions we need
ApiClient = _crd.ApiClient
_clean_cnpj = _crd._clean_cnpj
_format_cnpj = _crd._format_cnpj
_safe_float = _crd._safe_float
_source_tag = _crd._source_tag
_fmt_brl = _crd._fmt_brl
_strip_accents = _crd._strip_accents

# Collection functions
collect_portal_transparencia = _crd.collect_portal_transparencia
collect_sicaf = _crd.collect_sicaf
collect_ibge_batch = _crd.collect_ibge_batch
_geocode = _crd._geocode
_geocode_disk_save = _crd._geocode_disk_save
_calculate_distances_table = _crd._calculate_distances_table

# Cost estimator (local module)
_lib_dir = str(Path(__file__).resolve().parent / "lib")
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)
from cost_estimator import estimate_proposal_cost, estimate_roi_simple

# Bid simulator (v4)
try:
    from bid_simulator import simulate_bid
except ImportError:
    simulate_bid = None  # type: ignore[assignment]

# Victory profile (v4)
try:
    from victory_profile import build_victory_profile, format_fit_label, score_edital_fit
except ImportError:
    build_victory_profile = None  # type: ignore[assignment]
    score_edital_fit = None  # type: ignore[assignment]
    format_fit_label = None  # type: ignore[assignment]

# ============================================================
# CONSTANTS
# ============================================================

VERSION = "1.0.0"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Capitais brasileiras (para majorar custo de hospedagem)
CAPITAIS = {
    "AC": "RIO BRANCO",
    "AL": "MACEIO",
    "AP": "MACAPA",
    "AM": "MANAUS",
    "BA": "SALVADOR",
    "CE": "FORTALEZA",
    "DF": "BRASILIA",
    "ES": "VITORIA",
    "GO": "GOIANIA",
    "MA": "SAO LUIS",
    "MT": "CUIABA",
    "MS": "CAMPO GRANDE",
    "MG": "BELO HORIZONTE",
    "PA": "BELEM",
    "PB": "JOAO PESSOA",
    "PR": "CURITIBA",
    "PE": "RECIFE",
    "PI": "TERESINA",
    "RJ": "RIO DE JANEIRO",
    "RN": "NATAL",
    "RS": "PORTO ALEGRE",
    "RO": "PORTO VELHO",
    "RR": "BOA VISTA",
    "SC": "FLORIANOPOLIS",
    "SP": "SAO PAULO",
    "SE": "ARACAJU",
    "TO": "PALMAS",
}

# Modalidades eletrônicas (não exigem deslocamento presencial)
MODALIDADES_ELETRONICAS = {"eletrônico", "eletronica", "eletrônica", "eletronico"}


# ============================================================
# HTTP RETRY UTILITY
# ============================================================


def _request_with_retry(
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
    max_retries: int = 3,
    timeout: int = 30,
) -> Any:
    """HTTP GET with exponential backoff retry.

    Used as a resilient wrapper for direct httpx.get() calls that bypass
    ApiClient (e.g., one-off lookups, health checks).

    ApiClient.get() already has its own retry logic — this utility is for
    any future direct HTTP calls added to this module.
    """
    import httpx as _httpx

    resp = None
    for attempt in range(max_retries + 1):
        try:
            resp = _httpx.get(url, params=params, headers=headers, timeout=timeout)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                delay = min(1.0 * (2**attempt), 30.0)
                logger.info("[retry] HTTP %d from %s, retrying in %.0fs...", resp.status_code, url, delay)
                time.sleep(delay)
                continue
            return resp
        except (_httpx.TimeoutException, _httpx.ConnectError, _httpx.ReadError) as e:
            if attempt < max_retries:
                delay = min(1.0 * (2**attempt), 30.0)
                logger.info("[retry] %s from %s, retrying in %.0fs...", type(e).__name__, url, delay)
                time.sleep(delay)
            else:
                raise
    return resp


# ============================================================
# HELPERS
# ============================================================


def _is_eletronico(modalidade: str) -> bool:
    """Determina se a modalidade é eletrônica (sem deslocamento presencial)."""
    if not modalidade:
        return False
    lower = _strip_accents(modalidade.lower())
    return "eletron" in lower


def _is_capital(municipio: str, uf: str) -> bool:
    """Verifica se o município é capital do estado."""
    if not municipio or not uf:
        return False
    mun_norm = _strip_accents(municipio.upper().strip())
    cap = CAPITAIS.get(uf.upper().strip(), "")
    return mun_norm == cap


def _today() -> datetime:
    return datetime.now(UTC)


# ============================================================
# STEP 1: SICAF + SANCTIONS (empresa-level — run once)
# ============================================================


def enrich_empresa(
    api: ApiClient,
    cnpj14: str,
    skip_sicaf: bool = False,
) -> dict:
    """Enrich company data with SICAF status and sanctions check.

    Returns dict with keys: sicaf, sancoes, sancoes_source, sancionada, restricao
    """
    result: dict[str, Any] = {}

    # Portal da Transparência — Sanções
    pt_key = os.environ.get("PORTAL_TRANSPARENCIA_API_KEY", "")
    pt_data = collect_portal_transparencia(api, cnpj14, pt_key)
    result["sancoes"] = pt_data.get("sancoes", {})
    result["sancoes_source"] = pt_data.get("sancoes_source", {})
    result["historico_contratos_federais"] = pt_data.get("historico_contratos", [])
    result["historico_contratos_source"] = pt_data.get("historico_source", {})

    sancionada = result["sancoes"].get("sancionada", False)
    result["sancionada"] = sancionada
    if sancionada:
        sancoes_ativas = [k for k, v in result["sancoes"].items() if v and k not in ("sancionada", "inconclusive")]
        logger.warning("ALERTA: Empresa SANCIONADA (%s)", ", ".join(s.upper() for s in sancoes_ativas))
        logger.warning("Empresa IMPEDIDA de licitar — recomendação: regularizar antes de prosseguir")

    # SICAF
    if skip_sicaf:
        result["sicaf"] = {
            "status": "PULADO",
            "_source": _source_tag("UNAVAILABLE", "Coleta SICAF pulada (--skip-sicaf)"),
        }
        result["restricao_sicaf"] = None
        logger.info("SICAF: pulado (--skip-sicaf)")
    else:
        sicaf_data = collect_sicaf(cnpj14, verbose=True)
        result["sicaf"] = sicaf_data
        # Check restriction
        restricao = sicaf_data.get("restricao", {})
        if isinstance(restricao, dict):
            result["restricao_sicaf"] = restricao.get("possui_restricao", None)
        elif isinstance(restricao, bool):
            result["restricao_sicaf"] = restricao
        else:
            result["restricao_sicaf"] = None

        if result["restricao_sicaf"]:
            logger.warning("ALERTA: SICAF com RESTRIÇÃO ativa")
            logger.warning("Empresa pode participar mas com risco de inabilitação")

    return result


# ============================================================
# STEP 2: DISTANCE + IBGE + COST (per-edital — batch)
# ============================================================


def enrich_editais(
    api: ApiClient,
    editais: list[dict],
    cidade_sede: str,
    uf_sede: str,
    max_editais: int = 80,
    capital_social: float | None = None,
) -> dict[str, Any]:
    """Enrich editais with distance, IBGE data, and cost estimates.

    Selects the top N compatible editais prioritising those within capacity
    (valor_estimado <= capital_social * 10), rather than raw value ranking.

    Returns summary stats dict.
    """
    # Filter compatible editais
    compatible = [ed for ed in editais if ed.get("cnae_compatible")]

    # Capacity filter: keep editais within 10× capital_social (or with no value info)
    if capital_social and capital_social > 0:
        capacity_limit = capital_social * 10
        within_capacity = [
            ed
            for ed in compatible
            if not (ed.get("valor_estimado") or 0) or (ed.get("valor_estimado") or 0) <= capacity_limit
        ]
        skipped = len(compatible) - len(within_capacity)
        if skipped:
            logger.info(
                "[FILTRO] %d editais acima da capacidade (R$%s = 10x capital social R$%s) — ignorados",
                skipped,
                f"{capacity_limit:,.0f}",
                f"{capital_social:,.0f}",
            )
        compatible_filtered = within_capacity
    else:
        compatible_filtered = compatible

    compatible_sorted = sorted(
        compatible_filtered,
        key=lambda e: e.get("valor_estimado") or 0.0,
        reverse=True,
    )
    target_editais = compatible_sorted[:max_editais]
    target_ids = {ed["_id"] for ed in target_editais}

    capacity_note = (
        f" dentro da capacidade (≤R${capital_social * 10:,.0f})" if capital_social and capital_social > 0 else ""
    )
    logger.info(
        "Enriquecendo %d editais compatíveis%s (top %d por valor)...", len(target_editais), capacity_note, max_editais
    )

    # --- 2a. Geocode sede ---
    logger.info("[GEO] Geocodificando sede: %s/%s", cidade_sede, uf_sede)
    origin = _geocode(api, cidade_sede, uf_sede)
    if not origin:
        logger.warning("Não foi possível geocodificar a sede (%s/%s)", cidade_sede, uf_sede)
        logger.warning("Distâncias não serão calculadas")

    # --- 2b. Geocode destinos (editais) + collect unique municipalities ---
    destinations: dict[str, tuple[float, float]] = {}
    mun_set: set[tuple[str, str]] = set()

    for ed in target_editais:
        mun = ed.get("municipio", "")
        uf = ed.get("uf", "")
        if mun and uf:
            mun_set.add((mun, uf))
            dest_key = f"{mun}|{uf}"
            if dest_key not in destinations:
                coords = _geocode(api, mun, uf)
                if coords:
                    destinations[dest_key] = coords

    # Save geocode cache
    _geocode_disk_save()

    logger.info("[GEO] %d municípios geocodificados de %d únicos", len(destinations), len(mun_set))

    # --- 2c. Calculate distances (batch OSRM) ---
    distance_results: dict[str, dict] = {}
    if origin and destinations:
        logger.info("[DIST] Calculando distâncias via OSRM Table API...")
        distance_results = _calculate_distances_table(api, origin, destinations)
        ok_count = sum(1 for d in distance_results.values() if d.get("km") is not None)
        logger.info("[DIST] %d/%d distâncias calculadas", ok_count, len(distance_results))

    # --- 2d. IBGE batch ---
    logger.info("[IBGE] Coletando dados municipais (população/PIB)...")
    ibge_results = collect_ibge_batch(api, list(mun_set)) if mun_set else {}
    ibge_ok = sum(1 for v in ibge_results.values() if v.get("populacao"))
    logger.info("[IBGE] %d/%d municípios com dados IBGE", ibge_ok, len(mun_set))

    # --- 2e. Attach to editais + compute costs ---
    costs_computed = 0
    for ed in editais:
        if ed["_id"] not in target_ids:
            continue

        mun = ed.get("municipio", "")
        uf = ed.get("uf", "")
        dest_key = f"{mun}|{uf}"
        modalidade = ed.get("modalidade_nome", "")

        # Distance
        dist = distance_results.get(dest_key, {})
        ed["distancia"] = (
            dist
            if dist
            else {
                "km": None,
                "duracao_horas": None,
                "_source": _source_tag("UNAVAILABLE", "Sede ou destino não geocodificado"),
            }
        )

        # IBGE
        ibge = ibge_results.get(dest_key, {})
        ed["ibge"] = {
            "populacao": ibge.get("populacao"),
            "pib_mil_reais": ibge.get("pib_mil_reais"),
            "pib_per_capita": ibge.get("pib_per_capita"),
        }

        # Cost estimate
        km = dist.get("km") if dist else None
        dur = dist.get("duracao_horas") if dist else None
        eletronico = _is_eletronico(modalidade)
        capital = _is_capital(mun, uf)

        cost = estimate_proposal_cost(
            distancia_km=km,
            duracao_horas=dur,
            is_capital=capital,
            is_eletronico=eletronico,
        )
        ed["custo_proposta"] = cost

        # ROI
        valor = _safe_float(ed.get("valor_estimado"))
        custo_total = cost.get("total")
        roi = estimate_roi_simple(valor, custo_total)
        ed["roi_proposta"] = roi

        if cost.get("total") is not None:
            costs_computed += 1

    logger.info("[CUSTO] %d estimativas de custo calculadas", costs_computed)

    # --- 2f. Bid simulation (v4) ---
    bids_computed = 0
    if simulate_bid is not None:
        cnae_principal = None
        # Try to get CNAE from empresa context (passed via capital_social's caller)
        # We use a simple approach: get first compatible edital's competitive_intel
        for ed in editais:
            if ed["_id"] not in target_ids:
                continue
            ci = ed.get("competitive_intel") or {}
            bm = ed.get("price_benchmark") or {}
            if ci or bm:
                bid_result = simulate_bid(
                    edital=ed,
                    competitive_intel=ci,
                    benchmark=bm,
                    cnae_principal=cnae_principal,
                )
                ed["_bid_simulation"] = {
                    "lance_sugerido": bid_result.lance_sugerido,
                    "desconto_sugerido_pct": bid_result.desconto_sugerido_pct,
                    "p_vitoria_pct": bid_result.p_vitoria_pct,
                    "margem_liquida_pct": bid_result.margem_liquida_pct,
                    "valor_esperado": bid_result.valor_esperado,
                    "lance_agressivo": bid_result.lance_agressivo,
                    "lance_conservador": bid_result.lance_conservador,
                    "desconto_agressivo_pct": bid_result.desconto_agressivo_pct,
                    "desconto_conservador_pct": bid_result.desconto_conservador_pct,
                    "competidores_esperados": bid_result.competidores_esperados,
                    "historico_contratos": bid_result.historico_contratos,
                    "confianca": bid_result.confianca,
                    "racional": bid_result.racional,
                    "has_data": bid_result.has_data,
                }
                if bid_result.has_data:
                    bids_computed += 1
        logger.info("[LANCE] %d simulações de lance calculadas", bids_computed)
    else:
        logger.info("[LANCE] Módulo bid_simulator não disponível — pulando")

    # --- 2g. Victory profile fit scoring (v4) ---
    fits_computed = 0
    if build_victory_profile is not None and score_edital_fit is not None:
        # Build profile from all competitive_intel contracts
        all_contracts: list[dict] = []
        for ed in editais:
            ci = ed.get("competitive_intel") or {}
            contracts = ci.get("contracts", [])
            if contracts:
                all_contracts.extend(contracts)

        if len(all_contracts) >= 3:
            profile = build_victory_profile(
                all_contracts,
                company_capital=capital_social or 0.0,
            )
            if profile.has_data:
                for ed in editais:
                    if ed["_id"] not in target_ids:
                        continue
                    fit = score_edital_fit(ed, profile)
                    ed["_victory_fit"] = fit
                    ed["_victory_fit_label"] = format_fit_label(fit)
                    fits_computed += 1
                logger.info(
                    "[PERFIL] %d editais com score de aderência (perfil de %d contratos)",
                    fits_computed,
                    profile.total_contracts,
                )
            else:
                logger.info(
                    "[PERFIL] Dados insuficientes para perfil de vitória (%d contratos < 3 mínimo)", len(all_contracts)
                )
        else:
            logger.info("[PERFIL] Sem contratos históricos para perfil de vitória")
    else:
        logger.info("[PERFIL] Módulo victory_profile não disponível — pulando")

    return {
        "editais_enriquecidos": len(target_editais),
        "distancias_ok": sum(1 for d in distance_results.values() if d.get("km") is not None),
        "ibge_ok": ibge_ok,
        "custos_ok": costs_computed,
        "sede_geocodificada": origin is not None,
        "bids_computed": bids_computed,
        "fits_computed": fits_computed,
    }


# ============================================================
# MAIN
# ============================================================


def main():
    """Entry point for intel_enrich CLI."""
    from lib.cli_validation import validate_input_file
    from lib.constants import INTEL_VERSION

    parser = argparse.ArgumentParser(
        description="Intel Enrich — Enriquecimento SICAF/Sancoes/Distancia/Custo para /intel-busca.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Exemplos:
  python scripts/intel_enrich.py --input docs/intel/intel-CNPJ-slug-YYYY-MM-DD.json
  python scripts/intel_enrich.py --input data.json --skip-sicaf
  python scripts/intel_enrich.py --input data.json --output enriched.json --max-editais 40""",
    )
    parser.add_argument(
        "--input", "-i", required=True, help="JSON de entrada (output do intel_collect.py). Deve existir."
    )
    parser.add_argument("--output", "-o", default=None, help="JSON de saida (default: sobrescreve input)")
    parser.add_argument("--skip-sicaf", action="store_true", help="Pular coleta SICAF (evita captcha do navegador)")
    parser.add_argument(
        "--max-editais",
        type=int,
        default=80,
        help="Max editais para enriquecer dentro da capacidade financeira (default: 80)",
    )
    parser.add_argument("--quiet", action="store_true", help="Reduzir output (somente erros e resumo final)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {INTEL_VERSION}")
    args = parser.parse_args()

    # ── Validate arguments ──
    validate_input_file(args.input)

    t0 = time.time()

    # Load input
    input_path = Path(args.input)

    logger.info("=" * 60)
    logger.info("INTEL-ENRICH v%s", VERSION)
    logger.info("Input: %s", input_path)
    logger.info("=" * 60)

    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    empresa = data.get("empresa", {})
    editais = data.get("editais", [])
    cnpj = empresa.get("cnpj", "")
    cnpj14 = _clean_cnpj(cnpj) if cnpj else ""
    razao = empresa.get("razao_social", "N/A")
    capital_social = _safe_float(empresa.get("capital_social"))

    logger.info("Empresa: %s", razao)
    logger.info("CNPJ: %s", _format_cnpj(cnpj14))
    logger.info("Editais: %d", len(editais))

    api = ApiClient(verbose=not args.quiet)

    # ── Step 1: Empresa enrichment (SICAF + Sanções) ──
    # Skip if already collected by intel_collect.py (Step 1b)
    sicaf_already = (
        empresa.get("sicaf") and empresa["sicaf"].get("status") != "PULADO" and empresa["sicaf"].get("crc_status")
    )
    if sicaf_already:
        logger.info("[1/2] Verificação cadastral da empresa...")
        logger.info("SICAF já coletado no intel_collect.py — pulando")
        empresa_enrich = {
            "sicaf": empresa.get("sicaf", {}),
            "sancoes": empresa.get("sancoes", {}),
            "sancionada": empresa.get("sancionada", False),
            "restricao_sicaf": empresa.get("restricao_sicaf"),
        }
    else:
        logger.info("[1/2] Verificação cadastral da empresa...")
        empresa_enrich = enrich_empresa(api, cnpj14, skip_sicaf=args.skip_sicaf)

        # Merge into empresa
        data["empresa"]["sicaf"] = empresa_enrich.get("sicaf", {})
        data["empresa"]["sancoes"] = empresa_enrich.get("sancoes", {})
        data["empresa"]["sancoes_source"] = empresa_enrich.get("sancoes_source", {})
        data["empresa"]["sancionada"] = empresa_enrich.get("sancionada", False)
        data["empresa"]["restricao_sicaf"] = empresa_enrich.get("restricao_sicaf")
        data["empresa"]["historico_contratos_federais"] = empresa_enrich.get("historico_contratos_federais", [])

    # Check abort conditions
    if empresa_enrich.get("sancionada"):
        logger.warning("EMPRESA SANCIONADA — recomendação: NÃO prosseguir com participação")
        logger.warning("O relatório será gerado com alerta de impedimento.")

    # ── Step 2: Edital enrichment (Distance + IBGE + Cost) ──
    cidade_sede = empresa.get("cidade_sede") or empresa.get("municipio", "")
    uf_sede = empresa.get("uf_sede") or empresa.get("uf", "")

    if not cidade_sede or not uf_sede:
        logger.warning("Sede da empresa não disponível — distâncias não serão calculadas")
        enrich_stats = {"editais_enriquecidos": 0, "distancias_ok": 0, "ibge_ok": 0, "custos_ok": 0}
    else:
        logger.info("[2/2] Enriquecendo editais (distância, IBGE, custo)...")
        enrich_stats = enrich_editais(
            api,
            editais,
            cidade_sede,
            uf_sede,
            max_editais=args.max_editais,
            capital_social=capital_social,
        )

    # ── Save output ──
    data["_metadata"]["enrichment"] = {
        "version": VERSION,
        "enriched_at": _today().isoformat(),
        "sicaf_collected": not args.skip_sicaf,
        "sancionada": empresa_enrich.get("sancionada", False),
        "restricao_sicaf": empresa_enrich.get("restricao_sicaf"),
        **enrich_stats,
    }

    out_path = args.output or str(input_path)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    elapsed = time.time() - t0

    logger.info("=" * 60)
    logger.info("RESULTADO ENRIQUECIMENTO")
    logger.info("=" * 60)
    logger.info("SICAF:                %s", "coletado" if not args.skip_sicaf else "pulado")
    logger.info("Sancionada:           %s", "SIM" if empresa_enrich.get("sancionada") else "NÃO")
    logger.info(
        "Restrição SICAF:      %s",
        "SIM"
        if empresa_enrich.get("restricao_sicaf")
        else "NÃO"
        if empresa_enrich.get("restricao_sicaf") is not None
        else "N/D",
    )
    logger.info("Editais enriquecidos: %d", enrich_stats.get("editais_enriquecidos", 0))
    logger.info("Distâncias OK:        %d", enrich_stats.get("distancias_ok", 0))
    logger.info("IBGE OK:              %d", enrich_stats.get("ibge_ok", 0))
    logger.info("Custos calculados:    %d", enrich_stats.get("custos_ok", 0))
    logger.info("Tempo total:          %.1fs", elapsed)
    logger.info("Salvo em:             %s", out_path)
    logger.info("=" * 60)

    api.print_stats()
    api.close()


if __name__ == "__main__":
    main()
