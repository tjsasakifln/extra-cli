"""Pipeline canônico EXTRA-MS-OPEN: observação → processo → decisão → 6 arquivos."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Any

from scripts.ops.multi_source_open_pack.analysis import apply_minimum_analysis
from scripts.ops.multi_source_open_pack.classify_aec import TAXONOMY_VERSION
from scripts.ops.multi_source_open_pack.consolidate import consolidate_observations
from scripts.ops.multi_source_open_pack.decide import SCORING_VERSION, apply_decisions, select_shortlist
from scripts.ops.multi_source_open_pack.documents import inventariar_shortlist
from scripts.ops.multi_source_open_pack.loaders import load_all_observations, load_csv_dicts
from scripts.ops.multi_source_open_pack.models import CanonicalProcess, ReconciliationStats
from scripts.ops.multi_source_open_pack.reconcile import build_reconciliation
from scripts.ops.multi_source_open_pack.render_pack import (
    CLIENT_ARTIFACTS,
    write_checksums_and_manifest,
    write_csv,
    write_excel,
    write_pdf,
    write_readme,
)
from scripts.ops.multi_source_open_pack.textutil import BR_TZ, iso_z, utc_now
from scripts.ops.multi_source_open_pack.universe import annotate_observation_universe, build_indexes, load_universe

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MOTOR_VERSION = "extra-ms-open-pack/2.0.0"
DEFAULT_UNIVERSE = PROJECT_ROOT / "config" / "target_entities_200km.csv"
DEFAULT_PROFILE = PROJECT_ROOT / "config" / "client_profiles" / "extra.yaml"


def _git_sha(root: Path) -> str:
    try:
        out = subprocess.check_output(  # noqa: S603
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=str(root),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except Exception:
        return "unknown"


def _load_profile(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _profile_hash(path: Path) -> str:
    import hashlib

    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def default_limitations(
    *,
    stats: ReconciliationStats,
    inputs: dict[str, str],
    freshness_notes: list[str],
) -> list[str]:
    lim = [
        "Não declara LOCAL_READY, VPS_OPERATIONAL, cobertura operacional 95% nem recall estratificado sem prova.",
        "Score e ranking não são probabilidade de vitória; GO bloqueado com elicitation PENDING do perfil Extra.",
        "CIGA/DOM inclui publicações de atos; contratos/credenciamentos/homologações não viram oportunidade aberta.",
        "CSV exporta 1 linha por processo canônico (não por publicação bruta).",
        "Fora do universo 200 km fica em layer=secondary_reference e não contamina a shortlist principal.",
        "Distância exibida é geodésica do seed (origem Florianópolis/SC configurável); não é distância rodoviária.",
        "Inventário documental nesta versão linka URLs oficiais; download/OCR completo pode estar pendente "
        f"({stats.processos_com_docs} com docs complete).",
        "Análise de órgãos e concorrentes não inventa vencedores sem base histórica no recorte.",
        "valor_estimado ≠ valor homologado ≠ valor contratado ≠ valor pago.",
        "Aceite humano: PENDING_HUMAN — ausência de manifestação não é aceite.",
    ]
    lim.extend(freshness_notes)
    return lim


def default_source_policy(stats: ReconciliationStats) -> list[dict[str, str]]:
    src = stats.observacoes_por_fonte
    return [
        {
            "fonte": "pncp",
            "papel_open_tenders": "required",
            "esferas": "municipal + estadual + federal",
            "status_no_pack": "incluido" if src.get("pncp") else "sem_dados",
            "notas": f"{src.get('pncp', 0)} observações brutas (não processos)",
        },
        {
            "fonte": "ciga_ckan",
            "papel_open_tenders": "required (municipal)",
            "esferas": "municipal SC (DOM)",
            "status_no_pack": "incluido" if src.get("ciga_ckan") else "sem_dados",
            "notas": f"{src.get('ciga_ckan', 0)} publicações DOM classificadas por evento",
        },
        {
            "fonte": "sc_compras",
            "papel_open_tenders": "complementary / required-alt estadual",
            "esferas": "estadual SC",
            "status_no_pack": "incluido" if src.get("sc_compras") else "sem_dados",
            "notas": f"{src.get('sc_compras', 0)} observações",
        },
        {
            "fonte": "pcp",
            "papel_open_tenders": "complementary",
            "esferas": "multi",
            "status_no_pack": "sem_dados_no_lake",
            "notas": "adapter existe; não operacional no pack",
        },
        {
            "fonte": "compras_gov",
            "papel_open_tenders": "complementary",
            "esferas": "federal",
            "status_no_pack": "sem_dados_no_lake",
            "notas": "adapter existe; não operacional no pack",
        },
        {
            "fonte": "doe_sc",
            "papel_open_tenders": "complementary",
            "esferas": "estadual",
            "status_no_pack": "sem_dados_no_lake",
            "notas": "requer credenciais DOE_SC_*",
        },
        {
            "fonte": "tce_sc",
            "papel_open_tenders": "complementary",
            "esferas": "estadual",
            "status_no_pack": "sem_dados_no_lake",
            "notas": "não proven live no recorte",
        },
        {
            "fonte": "transparencia",
            "papel_open_tenders": "gap_fill",
            "esferas": "municipal",
            "status_no_pack": "sem_dados_no_lake",
            "notas": "portais heterogêneos",
        },
        {
            "fonte": "mides_bigquery",
            "papel_open_tenders": "gap_fill",
            "esferas": "estadual",
            "status_no_pack": "sem_dados_no_lake",
            "notas": "requer GOOGLE_APPLICATION_CREDENTIALS",
        },
        {
            "fonte": "dom_sc",
            "papel_open_tenders": "gap_fill (legado)",
            "esferas": "municipal",
            "status_no_pack": "substituido_por_ciga_ckan",
            "notas": "preferir CIGA Dados público",
        },
    ]


def build_pack(
    *,
    out_dir: Path,
    universe_path: Path = DEFAULT_UNIVERSE,
    profile_path: Path = DEFAULT_PROFILE,
    pncp_path: Path | None = None,
    ciga_path: Path | None = None,
    sc_compras_path: Path | None = None,
    coverage_path: Path | None = None,
    brand_dir: Path | None = None,
    as_of: date | None = None,
    now: datetime | None = None,
    pack_id: str | None = None,
    shortlist_limit: int = 25,
    ciga_lookback_days: int = 45,
    inventory_docs: bool = True,
    skip_network: bool = False,
) -> dict[str, Any]:
    """Build the 6 client artifacts. Returns pack result dict with terminal_state."""
    now = now or utc_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=BR_TZ)
    as_of = as_of or now.astimezone(BR_TZ).date()
    pack_id = pack_id or f"EXTRA-MS-OPEN-{now.astimezone(BR_TZ).strftime('%Y%m%dT%H%M%SZ')}"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    entities = load_universe(universe_path)
    by_cnpj8, names, by_name, municipios = build_indexes(entities)
    profile = _load_profile(profile_path)

    observations = load_all_observations(
        pncp_path=pncp_path,
        ciga_path=ciga_path,
        sc_path=sc_compras_path,
        as_of=as_of,
        ciga_lookback_days=ciga_lookback_days,
    )
    for obs in observations:
        annotate_observation_universe(
            obs,
            by_cnpj8=by_cnpj8,
            names=names,
            by_name=by_name,
            municipios=municipios,
        )

    processes, merges = consolidate_observations(observations, now=now)
    processes = apply_decisions(processes, profile=profile)
    shortlist = select_shortlist(processes, limit=shortlist_limit)

    # Document inventory + minimum analysis on shortlist (network optional).
    # Over-fetch candidates so we can keep only complete* inventories on the
    # executive shortlist (incomplete stay REVIEW blocked outside shortlist).
    doc_cache = out_dir / "_internal_doc_cache"
    inventory_pool = select_shortlist(processes, limit=max(shortlist_limit * 3, 30))
    inventory_summary = inventariar_shortlist(
        inventory_pool,
        cache_dir=doc_cache if inventory_docs and not skip_network else None,
        enabled=inventory_docs and not skip_network,
        max_processes=max(shortlist_limit * 3, 30),
    )
    analysis_summary = apply_minimum_analysis(
        inventory_pool,
        all_processes=processes,
        fetch_contracts=inventory_docs and not skip_network,
    )

    def _shortlist_doc_ok(p: CanonicalProcess) -> bool:
        st = str(p.docs_inventory_status)
        # HTML-only page hash is NOT enough (partial_page_only / complete_page_inventory banned)
        if st in {"complete", "complete_pncp_arquivos", "complete_with_attachments"}:
            return p.official_page_validated and bool(
                getattr(p, "_combined_doc_text", "") or getattr(p, "_page_text_sample", "")
            )
        return False

    complete_pool = [
        p
        for p in inventory_pool
        if _shortlist_doc_ok(p)
        and p.decision
        and p.decision.recommendation in {"GO", "REVIEW"}
        and p.in_universe
        and p.is_active_dispute
    ]
    complete_pool.sort(
        key=lambda p: (
            0 if p.decision and p.decision.recommendation == "GO" else 1,
            -(p.decision.score if p.decision else 0),
            p.calendar_days_remaining if p.calendar_days_remaining is not None else 999,
            p.distance_km if p.distance_km is not None else 9999,
        )
    )
    shortlist = complete_pool[:shortlist_limit]
    inventory_summary["shortlist_complete_only"] = True
    inventory_summary["complete_pool"] = len(complete_pool)
    inventory_summary["shortlist_after_filter"] = len(shortlist)
    inventory_summary["excluded_incomplete"] = [
        {
            "process_id": p.process_id,
            "docs_inventory_status": p.docs_inventory_status,
            "official_page_validated": p.official_page_validated,
        }
        for p in inventory_pool
        if p not in shortlist and not str(p.docs_inventory_status).startswith("complete")
    ][:50]

    # Incomplete inventory items: explicit REVIEW blocked (not in executive shortlist)
    for p in inventory_pool:
        if p in shortlist:
            continue
        if p.decision and not str(p.docs_inventory_status).startswith("complete"):
            p.decision.recommendation = "REVIEW"
            p.decision.inclusion_reason = (
                f"review_bloqueado_fora_shortlist:{p.docs_inventory_status}"
            )
            p.decision.blockers = sorted(
                set(p.decision.blockers + ["inventario_documental_incompleto"])
            )

    cov_rows = load_csv_dicts(coverage_path) if coverage_path else []
    stats = build_reconciliation(
        entities=entities,
        observations=observations,
        processes=processes,
        shortlist=shortlist,
        merges=merges,
        coverage_rows=cov_rows,
    )
    # docs complete count after inventory
    stats.processos_com_docs = sum(
        1 for p in processes if str(p.docs_inventory_status).startswith("complete")
    )
    inv_errors = stats.assert_invariants()

    freshness_notes: list[str] = []
    freshness_by_source: dict[str, Any] = {}
    for label, p in (
        ("PNCP", pncp_path),
        ("CIGA", ciga_path),
        ("SC Compras", sc_compras_path),
    ):
        if p and p.is_file():
            mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=BR_TZ)
            age_h = (now - mtime).total_seconds() / 3600
            freshness_by_source[label] = {
                "path": str(p),
                "mtime": mtime.isoformat(),
                "age_hours": round(age_h, 1),
                "fresh_24h": age_h <= 24,
            }
            if age_h > 24:
                freshness_notes.append(
                    f"Artefato {label} ({p.name}) com ~{age_h:.0f}h de idade — "
                    "não fundamenta claim de cobertura live completa sem revalidação."
                )

    # Live revalidation of executive shortlist pages (post complete* filter)
    live_pages_ok = sum(1 for p in shortlist if p.official_page_validated)
    live_complete = sum(
        1 for p in shortlist if str(p.docs_inventory_status).startswith("complete")
    )
    if shortlist:
        freshness_by_source["shortlist_official_pages"] = {
            "validated": live_pages_ok,
            "complete_inventory": live_complete,
            "total": len(shortlist),
            "fresh_live_http": live_pages_ok == len(shortlist)
            and live_complete == len(shortlist),
            "as_of": iso_z(now),
            "pool_attempted": inventory_summary.get("attempted"),
            "pool_complete": inventory_summary.get("complete"),
        }

    limitations = default_limitations(stats=stats, inputs={}, freshness_notes=freshness_notes)
    source_policy = default_source_policy(stats)
    logo = None
    if brand_dir:
        cand = Path(brand_dir) / "logo-confenge.png"
        if cand.is_file():
            logo = cand

    # Decision layer processes for CSV (canonical); include secondary with layer flag
    decision_procs = [p for p in processes if p.layer == "decision"]
    secondary = [p for p in processes if p.layer != "decision"]
    # CSV: all processes but decision first; still 1 line each
    csv_procs = sorted(
        processes,
        key=lambda p: (0 if p.layer == "decision" else 1, -(p.decision.score if p.decision else 0)),
    )

    inputs = {
        "pncp_open_csv": str(pncp_path) if pncp_path else "",
        "ciga_publications": str(ciga_path) if ciga_path else "",
        "sc_compras_open": str(sc_compras_path) if sc_compras_path else "",
        "coverage_entity_source": str(coverage_path) if coverage_path else "",
        "universe_seed": str(universe_path),
        "profile": str(profile_path),
        "brand": str(brand_dir) if brand_dir else "",
    }

    pack_meta: dict[str, Any] = {
        "pack_id": pack_id,
        "generated_at": iso_z(now),
        "as_of": as_of.isoformat(),
        "motor_version": MOTOR_VERSION,
        "motor_module": "scripts.ops.multi_source_open_pack",
        "git_sha": _git_sha(PROJECT_ROOT),
        "universe_n": stats.entes_universo,
        "universe_seed": str(universe_path),
        "profile_version": str(profile.get("version") or profile.get("profile_id") or ""),
        "profile_hash": _profile_hash(profile_path),
        "taxonomy_version": TAXONOMY_VERSION,
        "scoring_version": SCORING_VERSION,
        "stats": stats.to_dict(),
        "reconciliation": stats.to_dict(),
        "inputs": inputs,
        "document_inventory": inventory_summary,
        "analysis_minimum": {
            "edital_n": len(analysis_summary.get("edital") or []),
            "orgao_n": len(analysis_summary.get("orgao") or []),
            "concorrentes_n": len(analysis_summary.get("concorrentes") or []),
            "market_intel": analysis_summary.get("market_intel") or {},
            "note": (
                "Edital: trechos extraídos de PDFs/HTML oficiais baixados. "
                "Órgão: estatísticas do pack multi-fonte + PNCP contratos API quando filtrável. "
                "Concorrentes: apenas vencedores históricos do mesmo órgão com CNPJ-8 filtrado; "
                "sem lista genérica inventada."
            ),
        },
        "freshness_by_source": freshness_by_source,
        "brand": {
            "source": "CONFENGE",
            "tokens": {
                "navy_900": "#061a33",
                "lime": "#ced62a",
                "green_700": "#2d6f2d",
                "ink": "#071a31",
            },
            "logo": str(logo) if logo else "",
        },
        "human_accept": "PENDING_HUMAN",
        "terminal_state": "FAIL" if inv_errors else "PASS",
        "invariant_errors": inv_errors,
        "claims_allowed": [
            "contagens_dimensionalmente_rotuladas",
            "processo_canonic_deduplicado",
            "engenharia_hint_nao_autoridade",
            "shortlist_somente_universo",
            "distancia_geodesica_do_universo_quando_match",
        ],
        "claims_forbidden": [
            "LOCAL_READY",
            "VPS_OPERATIONAL",
            "cobertura_95",
            "probabilidade_de_vitoria",
            "GO_com_campos_PENDING",
            "concorrentes_inventados",
        ],
        "shortlist_process_ids": [p.process_id for p in shortlist],
        "decision_layer_process_count": len(decision_procs),
        "secondary_reference_process_count": len(secondary),
    }

    if freshness_notes:
        pack_meta["terminal_state"] = "BLOCKED" if not inv_errors else "FAIL"
        pack_meta["claims_forbidden"] = list(
            set(pack_meta["claims_forbidden"]) | {"cobertura_live_completa", "freshness_24h"}
        )
        pack_meta["blockers_external"] = freshness_notes
        # partial claim if shortlist pages revalidated live
        if live_pages_ok and shortlist and live_pages_ok == len(shortlist):
            pack_meta["claims_allowed"].append("shortlist_paginas_oficiais_revalidadas_http_live")
            pack_meta["partial_quality"] = (
                "Cobertura multi-fonte stale, mas 100% das páginas oficiais da shortlist "
                "foram revalidadas por HTTP no momento da geração."
            )

    # Client-ready gates for shortlist (docs + parse + analysis substance)
    if shortlist and inventory_docs and not skip_network:
        incomplete = [p for p in shortlist if not _shortlist_doc_ok(p)]
        weak_edital = [
            p
            for p in shortlist
            if len(getattr(p, "_combined_doc_text", "") or getattr(p, "_page_text_sample", "") or "")
            < 200
        ]
        no_buyer = [
            p
            for p in shortlist
            if not p.buyer_analysis
            or "não invent" in (p.buyer_analysis or "").lower()
            and "No pack multi-fonte" not in (p.buyer_analysis or "")
        ]
        # buyer must have pack-based analysis sentence
        no_buyer = [
            p
            for p in shortlist
            if "No pack multi-fonte" not in (p.buyer_analysis or "")
            and "processo(s)" not in (p.buyer_analysis or "")
        ]
        gate_issues: list[str] = []
        if incomplete:
            gate_issues.append(
                f"{len(incomplete)}/{len(shortlist)} shortlist sem docs complete (edital/anexo parseado)"
            )
        if weak_edital:
            gate_issues.append(
                f"{len(weak_edital)}/{len(shortlist)} shortlist sem texto documental suficiente para análise"
            )
        if no_buyer:
            gate_issues.append(
                f"{len(no_buyer)}/{len(shortlist)} shortlist sem análise de órgão baseada em evidência"
            )
        if not shortlist:
            gate_issues.append(
                "shortlist vazia após filtro de inventário completo — sem base decisória executiva"
            )
        if gate_issues and pack_meta["terminal_state"] == "PASS":
            pack_meta["terminal_state"] = "BLOCKED"
            pack_meta["blockers_external"] = pack_meta.get("blockers_external", []) + gate_issues
            pack_meta["claims_forbidden"] = list(
                set(pack_meta["claims_forbidden"])
                | {
                    "shortlist_docs_100_percent_complete",
                    "analise_edital_completa_100",
                    "client_ready_sem_ressalva",
                }
            )
        elif not gate_issues and pack_meta["terminal_state"] == "PASS":
            pack_meta["claims_allowed"] = list(
                set(pack_meta["claims_allowed"])
                | {
                    "shortlist_docs_complete_with_parse",
                    "shortlist_analise_edital_parcial_extraida",
                    "shortlist_analise_orgao_baseada_em_evidencia",
                }
            )

    # If no input data at all
    if not observations:
        pack_meta["terminal_state"] = "BLOCKED"
        pack_meta["blockers_external"] = pack_meta.get("blockers_external", []) + [
            "Nenhuma observação carregada — forneça --pncp/--ciga/--sc-compras"
        ]

    # Do not ship internal cache as client artifact — remove from client listing later
    pack_meta["internal_doc_cache"] = str(doc_cache) if doc_cache.exists() else ""

    readme = out_dir / "00-LEIA-ME.md"
    pdf_path = out_dir / "01-resumo-executivo-multifonte.pdf"
    xlsx_path = out_dir / "02-oportunidades-multifonte-dados.xlsx"
    csv_path = out_dir / "oportunidades-multifonte.csv"

    write_readme(
        readme,
        pack_id=pack_id,
        stats=stats,
        generated_at=pack_meta["generated_at"],
        as_of=pack_meta["as_of"],
        limitations=limitations,
        motor_version=MOTOR_VERSION,
    )
    write_csv(csv_path, csv_procs)

    obs_sample = [
        {
            "observation_id": o.observation_id,
            "fonte": o.fonte,
            "id_externo": o.id_externo,
            "orgao": o.orgao,
            "objeto": o.objeto[:200],
            "event_type": o.event_type,
            "is_active_dispute": "sim" if o.is_active_dispute else "nao",
            "in_universe": "sim" if o.in_universe else "nao",
            "url": o.url,
        }
        for o in observations
    ]

    write_excel(
        xlsx_path,
        pack_meta=pack_meta,
        processes=processes,
        shortlist=shortlist,
        stats=stats,
        source_policy=source_policy,
        limitations=limitations,
        observations_sample=obs_sample,
        logo_path=logo,
    )
    write_pdf(
        pdf_path,
        pack_meta=pack_meta,
        shortlist=shortlist,
        stats=stats,
        limitations=limitations,
        logo_path=logo,
    )

    pack_meta["limitations"] = limitations
    pack_meta["source_policy"] = source_policy
    pack_meta["coverage_summary"] = [
        {
            "fonte": k,
            "observacoes_brutas": v,
            "nota": "contagem de observações, não de entes nem de processos",
        }
        for k, v in sorted(stats.observacoes_por_fonte.items())
    ]

    artifacts = {
        "00-LEIA-ME.md": readme,
        "01-resumo-executivo-multifonte.pdf": pdf_path,
        "02-oportunidades-multifonte-dados.xlsx": xlsx_path,
        "oportunidades-multifonte.csv": csv_path,
    }
    write_checksums_and_manifest(out_dir, pack_meta=pack_meta, artifact_paths=artifacts)

    # Verify exactly 6 client files (ignore internal dirs like _internal_doc_cache)
    present = sorted(p.name for p in out_dir.iterdir() if p.is_file())
    client = [n for n in present if n in CLIENT_ARTIFACTS]
    extra = [n for n in present if n not in CLIENT_ARTIFACTS]
    if set(client) != set(CLIENT_ARTIFACTS):
        pack_meta["terminal_state"] = "FAIL"
        pack_meta["invariant_errors"] = pack_meta.get("invariant_errors", []) + [
            f"client artifacts mismatch: {client}"
        ]
    if extra:
        # allow only nothing extra ideally; fail if unexpected client-facing
        pack_meta["extra_files_in_out_dir"] = extra

    result = {
        "pack_id": pack_id,
        "out_dir": str(out_dir),
        "terminal_state": pack_meta["terminal_state"],
        "stats": stats.to_dict(),
        "shortlist_n": len(shortlist),
        "processes_n": len(processes),
        "observations_n": len(observations),
        "client_artifacts": list(CLIENT_ARTIFACTS),
        "invariant_errors": pack_meta.get("invariant_errors", []),
        "git_sha": pack_meta["git_sha"],
        "motor_version": MOTOR_VERSION,
    }
    # rewrite manifest with final terminal state
    (out_dir / "manifest.json").write_text(
        json.dumps(pack_meta, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    return result


def run_pack_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m scripts.ops.multi_source_open_pack",
        description="Motor canônico EXTRA-MS-OPEN — pack multi-fonte decisório (6 arquivos).",
    )
    parser.add_argument("--out-dir", type=Path, required=True, help="Diretório de saída do pack")
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--pncp", type=Path, default=None, help="CSV open PNCP")
    parser.add_argument("--ciga", type=Path, default=None, help="JSONL publicações CIGA/DOM")
    parser.add_argument("--sc-compras", type=Path, default=None, help="JSONL SC Compras open")
    parser.add_argument("--coverage", type=Path, default=None, help="CSV coverage entity×source")
    parser.add_argument("--brand-dir", type=Path, default=None)
    parser.add_argument("--as-of", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--pack-id", type=str, default=None)
    parser.add_argument("--shortlist-limit", type=int, default=25)
    parser.add_argument("--ciga-lookback-days", type=int, default=45)
    parser.add_argument(
        "--skip-network",
        action="store_true",
        help="Não baixar páginas/docs (testes offline); shortlist fica REVIEW bloqueado documental",
    )
    parser.add_argument(
        "--no-inventory",
        action="store_true",
        help="Desliga inventário documental da shortlist",
    )
    args = parser.parse_args(argv)

    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    result = build_pack(
        out_dir=args.out_dir,
        universe_path=args.universe,
        profile_path=args.profile,
        pncp_path=args.pncp,
        ciga_path=args.ciga,
        sc_compras_path=args.sc_compras,
        coverage_path=args.coverage,
        brand_dir=args.brand_dir,
        as_of=as_of,
        pack_id=args.pack_id,
        shortlist_limit=args.shortlist_limit,
        ciga_lookback_days=args.ciga_lookback_days,
        inventory_docs=not args.no_inventory,
        skip_network=args.skip_network,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    state = result.get("terminal_state")
    if state == "FAIL":
        return 2
    if state == "BLOCKED":
        return 1
    return 0


# re-export
__all__ = ["CLIENT_ARTIFACTS", "build_pack", "run_pack_cli", "MOTOR_VERSION"]
