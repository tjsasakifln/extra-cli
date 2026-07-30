"""Public-agency commercial pipeline — buyer-side prospecting."""

from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml

from scripts.public_agency import (
    CAMPAIGN_ID,
    MODE_PROACTIVE,
    MODE_REACTIVE,
    MODULE_VERSION,
    OBJECT_HUMAN,
)
from scripts.public_agency.catalog import catalog_hash, get_service, services_list
from scripts.public_agency.conflict import assess_conflict
from scripts.public_agency.conflict import config_hash as conflict_hash
from scripts.public_agency.contacts import default_institutional_research_contact, validate_contacts
from scripts.public_agency.dossier import write_dossier
from scripts.public_agency.entities import build_prospect_from_contract_rows, normalize_cnpj14
from scripts.public_agency.exports import export_public_agency_run
from scripts.public_agency.fragmentation import assess_fragmentation
from scripts.public_agency.kit import generate_commercial_kit
from scripts.public_agency.legal_thresholds import (
    catalog_hash as thresholds_hash,
)
from scripts.public_agency.legal_thresholds import (
    evaluate_potential_eligibility,
    get_threshold,
)
from scripts.public_agency.object_classification import classify_object, may_allege_dispensa_ceiling
from scripts.public_agency.population import load_population_map, match_population_by_name
from scripts.public_agency.proposal import generate_proposal, write_proposal
from scripts.public_agency.publishability import evaluate_publishability
from scripts.public_agency.scoring import score_agency, service_fit_for_agency
from scripts.public_agency.signals import compute_agency_signals, material_need_signals

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PROFILE = _ROOT / "config/commercial/public_agency_profile.yaml"

SOURCE_FAILURE = "SOURCE_FAILURE"
EMPTY_VALID_RESULT = "EMPTY_VALID_RESULT"
NO_PUBLISHABLE_LEADS = "NO_PUBLISHABLE_LEADS"
FILTER_REMOVED_ALL = "FILTER_REMOVED_ALL"
COVERAGE_INSUFFICIENT = "COVERAGE_INSUFFICIENT"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def git_sha(root: Path | None = None) -> str:
    r = root or _ROOT
    try:
        out = subprocess.check_output(  # noqa: S603
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=str(r),
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return out.strip()
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return "unknown"


def load_profile(path: Path | None = None) -> dict[str, Any]:
    p = path or _DEFAULT_PROFILE
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def profile_hash(path: Path | None = None) -> str:
    p = path or _DEFAULT_PROFILE
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _connect(dsn: str) -> Any:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    conn = psycopg2.connect(dsn)
    conn.cursor_factory = RealDictCursor
    return conn


def fetch_agency_contracts(
    dsn: str,
    *,
    ufs: list[str],
    max_contracts: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load buyer-side rows from pncp_supplier_contracts."""
    meta: dict[str, Any] = {"source": "pncp_supplier_contracts", "ok": False}
    try:
        conn = _connect(dsn)
    except Exception as exc:  # noqa: BLE001
        meta["error"] = str(exc)
        meta["failure_class"] = SOURCE_FAILURE
        return [], meta

    try:
        cur = conn.cursor()
        # Discover optional columns (schemas differ: commercial snapshot may have is_active)
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'pncp_supplier_contracts'
            """
        )
        cols = {str(r["column_name"] if isinstance(r, dict) else r[0]) for r in cur.fetchall()}
        base = [
            "contrato_id",
            "orgao_cnpj",
            "orgao_nome",
            "fornecedor_cnpj",
            "fornecedor_nome",
            "objeto_contrato",
            "valor_total",
            "data_inicio",
            "data_fim",
            "data_publicacao",
            "uf",
            "source",
            "source_id",
        ]
        optional = [c for c in ("is_active", "municipio") if c in cols]
        select_list = ", ".join(base + optional)
        sql = (
            f"SELECT {select_list} FROM public.pncp_supplier_contracts "  # noqa: S608
            "WHERE orgao_nome IS NOT NULL AND btrim(orgao_nome) <> ''"
        )
        params: list[Any] = []
        if ufs:
            sql += " AND uf IS NOT NULL AND upper(btrim(uf)) = ANY(%s)"
            params.append([u.upper() for u in ufs])
        sql += " ORDER BY data_publicacao DESC NULLS LAST"
        if max_contracts:
            sql += " LIMIT %s"
            params.append(int(max_contracts))
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        # Normalize missing is_active
        for row in rows:
            row.setdefault("is_active", None)
        meta["ok"] = True
        meta["row_count"] = len(rows)
        meta["ufs"] = ufs
        meta["columns"] = base + optional
        return rows, meta
    except Exception as exc:  # noqa: BLE001
        meta["error"] = str(exc)
        meta["failure_class"] = SOURCE_FAILURE
        return [], meta
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001,S110
            pass


def group_by_agency(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        cnpj = normalize_cnpj14(row.get("orgao_cnpj"))
        nome = str(row.get("orgao_nome") or "").strip().upper()
        uf = str(row.get("uf") or "").strip().upper()
        key = cnpj or f"NAME::{nome}::{uf}"
        groups[key].append(row)
    return dict(groups)


def _is_public_agency_name(nome: str) -> bool:
    n = nome.upper()
    markers = (
        "PREFEITURA",
        "MUNICIPIO",
        "MUNICÍPIO",
        "SECRETARIA",
        "AUTARQUIA",
        "FUNDACAO",
        "FUNDAÇÃO",
        "CONSORCIO",
        "CONSÓRCIO",
        "ESTADO DE",
        "GOVERNO",
        "CAMARA MUNICIPAL",
        "CÂMARA MUNICIPAL",
        "INSTITUTO",
        "UNIVERSIDADE",
        "COMPANHIA",
        "EMPRESA PUBLICA",
        "EMPRESA PÚBLICA",
    )
    return any(m in n for m in markers)


def _has_geographic_identity(nome: str) -> bool:
    """Reject bare 'SECRETARIA DE ADMINISTRAÇÃO' without municipality/UF context."""
    n = nome.upper()
    # Strong geo anchors
    if any(x in n for x in ("PREFEITURA", "MUNICÍPIO", "MUNICIPIO", " - SC", "/SC", " DE SC")):
        return True
    if "FUNDAÇÃO" in n or "FUNDACAO" in n:
        # Fundação X de <município>
        return " DE " in n or " DO " in n
    if "SECRETARIA" in n:
        # Require explicit municipality/state in the name
        return any(x in n for x in ("MUNICIPAL", "ESTADUAL", "DE SC", "SANTA CATARINA")) and (
            " DE " in n or " DO " in n
        )
    return True


def run_public_agency_pipeline(
    *,
    dsn: str | None,
    out_dir: str | Path,
    profile_path: str | Path | None = None,
    as_of: date | None = None,
    ufs: list[str] | None = None,
    max_contracts: int | None = 100_000,
    max_leads: int = 20,
    priority_population_max: int | None = None,
    focus_population_max: int | None = None,
    mode_filter: str | None = None,
    require_conflict_check: bool = True,
    fixture_rows: list[dict[str, Any]] | None = None,
    skip_kit: bool = False,
) -> dict[str, Any]:
    """Execute public-agency commercial cycle modality."""
    as_of = as_of or date.today()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    profile_p = Path(profile_path) if profile_path else _DEFAULT_PROFILE
    profile = load_profile(profile_p)
    region = profile.get("region") or {}
    ufs = ufs or list(region.get("primary_ufs") or ["SC"])
    priority_population_max = priority_population_max or int(region.get("priority_population_max") or 50000)
    focus_population_max = focus_population_max or int(region.get("focus_population_max") or 100000)
    weights = profile.get("scoring_weights") or {}
    eng_kws = list(profile.get("engineering_object_keywords") or [])

    run_id = str(uuid.uuid4())
    sha = git_sha()
    config_hashes = {
        "profile": profile_hash(profile_p),
        "thresholds": thresholds_hash(),
        "catalog": catalog_hash(),
        "conflict": conflict_hash(),
    }

    source_meta: dict[str, Any]
    if fixture_rows is not None:
        rows = list(fixture_rows)
        source_meta = {"ok": True, "row_count": len(rows), "source": "fixture", "ufs": ufs}
    else:
        if not dsn:
            return {
                "run_id": run_id,
                "campaign_id": CAMPAIGN_ID,
                "status": "FAIL",
                "reason": SOURCE_FAILURE,
                "git_sha": sha,
                "as_of": as_of.isoformat(),
                "metrics": {},
                "leads": [],
                "error": "missing DSN and no fixture_rows",
                "config_hashes": config_hashes,
            }
        rows, source_meta = fetch_agency_contracts(dsn, ufs=ufs, max_contracts=max_contracts)

    if not source_meta.get("ok"):
        fail_result: dict[str, Any] = {
            "run_id": run_id,
            "campaign_id": CAMPAIGN_ID,
            "status": "FAIL",
            "reason": source_meta.get("failure_class") or SOURCE_FAILURE,
            "git_sha": sha,
            "as_of": as_of.isoformat(),
            "metrics": {"source": source_meta},
            "leads": [],
            "error": source_meta.get("error"),
            "config_hashes": config_hashes,
            "module_version": MODULE_VERSION,
        }
        export_public_agency_run(out, fail_result)
        return fail_result

    if not rows:
        empty_result: dict[str, Any] = {
            "run_id": run_id,
            "campaign_id": CAMPAIGN_ID,
            "status": "PASS",
            "reason": EMPTY_VALID_RESULT,
            "git_sha": sha,
            "as_of": as_of.isoformat(),
            "metrics": {
                "source": source_meta,
                "agency_universe": 0,
                "evaluated_agencies": 0,
                "publishable_agencies": 0,
            },
            "leads": [],
            "config_hashes": config_hashes,
            "module_version": MODULE_VERSION,
        }
        export_public_agency_run(out, empty_result)
        return empty_result

    pop_map = load_population_map()
    groups = group_by_agency(rows)
    catalog_services = services_list()

    evaluated = 0
    publishable_leads: list[dict[str, Any]] = []
    all_scored: list[dict[str, Any]] = []
    blocked = 0
    reasons_counter: dict[str, int] = defaultdict(int)

    for _key, contracts in groups.items():
        nome = str(contracts[0].get("orgao_nome") or "")
        if not _is_public_agency_name(nome):
            # Skip private entities appearing as orgao (data noise)
            continue
        if not _has_geographic_identity(nome):
            reasons_counter["missing_geographic_identity"] += 1
            continue

        pop_info = match_population_by_name(nome, pop_map)
        # Prefer municipio column from contracts when name match failed
        if not pop_info.get("municipio"):
            mun = str(contracts[0].get("municipio") or "").strip()
            if mun:
                pop_info = match_population_by_name(f"PREFEITURA MUNICIPAL DE {mun}", pop_map)
                if not pop_info.get("municipio"):
                    pop_info = {
                        **pop_info,
                        "municipio": mun,
                        "match": "contract_municipio_field",
                    }
        # Priority filter: prefer ≤ priority max; allow ≤ focus max
        pop = pop_info.get("population")
        if pop is not None and pop > focus_population_max:
            reasons_counter["above_focus_population"] += 1
            continue
        # Prefer priority band but still evaluate up to focus for ranking
        prospect = build_prospect_from_contract_rows(contracts, population_info=pop_info)
        evaluated += 1

        # Representative object = most recent engineering-ish or first
        objects = [str(c.get("objeto_contrato") or "") for c in contracts]
        joined = " | ".join(objects[:5])
        classification = classify_object(joined)
        cls_dict = classification.as_dict()

        # Fragmentation / annual sum
        same_nature = []
        for c in contracts:
            amt = c.get("valor_total")
            try:
                same_nature.append(
                    {
                        "amount": float(amt) if amt is not None else 0.0,
                        "object": str(c.get("objeto_contrato") or ""),
                        "id": c.get("contrato_id"),
                    }
                )
            except (TypeError, ValueError):
                continue
        thr = None
        if classification.suggested_class != OBJECT_HUMAN:
            thr = get_threshold(classification.suggested_class, as_of=as_of)
        ceiling = thr.amount if thr else None
        # Observed same-nature history can drive fragmentation *indicators*, but the
        # full annual UG ledger is not available → DIRECT_CONTRACTING_SUM_UNKNOWN
        # for eligibility adherence claims (never claim annual limit adherence).
        annual_ledger_complete = False
        frag = assess_fragmentation(
            proposed_amount=None,
            ceiling=ceiling,
            same_nature_contracts=same_nature,
            complete_annual_ledger=False,
        )
        observed_sum = sum(float(x.get("amount") or 0) for x in same_nature)
        frag_dict = frag.as_dict()
        frag_dict["observed_contract_sum_in_sample"] = observed_sum
        frag_dict["annual_sum_state"] = "DIRECT_CONTRACTING_SUM_UNKNOWN"
        frag_dict["annual_sum_known"] = False
        frag_dict["annual_ledger_complete"] = annual_ledger_complete
        frag_dict["notes"] = (
            frag_dict.get("notes")
            or ""
        ) + " Somatório observado no sample de contratos não equivale a ledger anual completo da UG."

        sample_amount = None
        if same_nature:
            sample_amount = max(float(x.get("amount") or 0) for x in same_nature) or None

        # Hard publishability blocks only for HIGH fragmentation / package-split.
        # Mild indicators penalize score via signals, not COMPLIANCE_BLOCKED.
        compliance_blocks: list[str] = []
        if frag.severity == "HIGH" or "packages_sum_above_ceiling_each_below" in frag.indicators:
            compliance_blocks.append("possible_expense_fragmentation")
            compliance_blocks.append("fragmentation_severity_high")
        compliance_flags: list[str] = list(frag.indicators)
        if classification.suggested_class == OBJECT_HUMAN:
            compliance_flags.append("legal_classification_ambiguous")
        if frag.fragmentation_suspected and "possible_expense_fragmentation" not in compliance_blocks:
            compliance_flags.append("possible_expense_fragmentation_soft")

        eligibility = evaluate_potential_eligibility(
            sample_amount,
            classification.suggested_class,
            as_of=as_of,
            annual_sum_same_nature=None,
            annual_sum_known=False,  # never claim full UG annual adherence without ledger
            fragmentation_flag=frag.severity == "HIGH"
            or "packages_sum_above_ceiling_each_below" in frag.indicators,
        )
        if not may_allege_dispensa_ceiling(classification):
            eligibility = dict(eligibility)
            eligibility["commercial_ceiling_allegation_allowed"] = False
            if eligibility.get("potentially_eligible"):
                eligibility["eligibility_state"] = "NOT_ASSESSED_AMBIGUOUS_OBJECT"
                eligibility["potentially_eligible"] = False
                eligibility["reason_codes"] = list(eligibility.get("reason_codes") or []) + [
                    "CEILING_ALLEGATION_BLOCKED_AMBIGUOUS_CLASS"
                ]
        else:
            eligibility["commercial_ceiling_allegation_allowed"] = True

        conflict = assess_conflict(
            agency_id=prospect.agency_id,
            cnpj14=prospect.cnpj,
            official_name=prospect.nome_oficial,
        )

        # No invented institutional contacts. Research action is a *next step*,
        # not a channel already available (does not fire institutional_contact_available).
        contact_validation = validate_contacts([])
        research = default_institutional_research_contact(prospect.uf, prospect.municipio)
        research_only = {
            "accepted": [],
            "rejected": [],
            "has_institutional": False,
            "research_actions": [research.as_dict()],
            "note": (
                "Nenhum e-mail/telefone institucional capturado nesta rodada; "
                "há apenas justificativa de pesquisa adicional em portal oficial."
            ),
        }
        has_real_institutional_contact = False

        signals = compute_agency_signals(
            contracts=contracts,
            population=prospect.populacao,
            as_of=as_of,
            eng_keywords=eng_kws,
            has_institutional_contact=has_real_institutional_contact,
            object_class_ambiguous=classification.suggested_class == OBJECT_HUMAN,
            fragmentation_indicators=frag.indicators,
            conflict_state=conflict.state,
            annual_sum_state="DIRECT_CONTRACTING_SUM_UNKNOWN",
        )

        # count engineering contracts more directly
        eng_contract_count = 0
        for c in contracts:
            blob = str(c.get("objeto_contrato") or "").upper()
            if any(t in blob for t in ("OBRA", "ENGENHAR", "PAVIMENT", "REFORMA", "SANEAMENTO", "INFRAESTRUTURA")):
                eng_contract_count += 1

        distress = any(s.signal_id == "contract_execution_distress" and s.status == "FIRED" for s in signals)
        recent_hist = any(
            s.signal_id == "recent_publication_of_engineering_demand" and s.status == "FIRED" for s in signals
        )
        # Reactive mode requires an open published opportunity (edital/aviso/contratação
        # direta em curso). Historical buyer-side contracts alone are PROACTIVE only.
        open_opportunity = any(
            s.signal_id == "active_direct_contracting_notice" and s.status == "FIRED" for s in signals
        )
        fit, sid = service_fit_for_agency(
            eng_contract_count=eng_contract_count,
            distress=distress,
            recent_eng=recent_hist,
            object_class=classification.suggested_class,
            catalog_services=catalog_services,
        )
        service = get_service(sid or "") or {}

        mode = MODE_REACTIVE if open_opportunity else MODE_PROACTIVE
        if mode_filter and mode != mode_filter:
            reasons_counter["mode_filter"] += 1
            continue

        score = score_agency(
            agency_id=prospect.agency_id,
            signals=signals,
            service_fit=fit,
            selected_service_id=sid,
            has_institutional_contact=has_real_institutional_contact,
            evidence_count=len(contracts),
            mode=mode,
            conflict_state=conflict.state,
            compliance_blocks=compliance_blocks,
            weights=weights,
        )

        # Priority boost for ≤50k
        if prospect.populacao is not None and prospect.populacao <= priority_population_max:
            score.priority_score = round(min(1.0, score.priority_score + 0.05), 4)

        evidence = []
        for c in contracts[:15]:
            evidence.append(
                {
                    "source": c.get("source") or "pncp_supplier_contracts",
                    "identifier": c.get("contrato_id") or c.get("source_id"),
                    "url_or_ref": f"pncp_supplier_contracts:{c.get('contrato_id')}",
                    "publication_date": str(c.get("data_publicacao") or "")[:10] or None,
                    "capture_date": as_of.isoformat(),
                    "hash": hashlib.sha256(
                        json.dumps(
                            {
                                "id": c.get("contrato_id"),
                                "obj": c.get("objeto_contrato"),
                                "val": str(c.get("valor_total")),
                            },
                            sort_keys=True,
                            default=str,
                        ).encode()
                    ).hexdigest()[:16],
                    "parser": "public_agency.pipeline",
                    "version": MODULE_VERSION,
                    "quality": "official_table_row",
                    "limitations": [
                        "Buyer-side row from supplier contracts table; not full process file."
                    ],
                    "objeto": c.get("objeto_contrato"),
                    "valor_total": c.get("valor_total"),
                }
            )

        pub = evaluate_publishability(
            has_official_identity=bool(prospect.cnpj or prospect.nome_oficial),
            signals=signals,
            has_official_evidence=bool(contracts),
            service_fit_score=score.service_fit_score,
            explanation=score.explanation,
            conflict=conflict,
            compliance_blocks=compliance_blocks,
            has_institutional_contact=has_real_institutional_contact,
            contact_research_justified=True,  # research step justified; not a real channel
        )

        if pub.category in {"CONFLICT_BLOCKED", "COMPLIANCE_BLOCKED"}:
            blocked += 1

        total_value = sum(float(c.get("valor_total") or 0) for c in contracts)
        last_pub = None
        for c in contracts:
            d = str(c.get("data_publicacao") or "")[:10]
            if d and (last_pub is None or d > last_pub):
                last_pub = d

        material = material_need_signals(signals)
        probable = (
            "Sinais de possível necessidade técnica (histórico de contratações de engenharia / "
            "execução longa) — prospecção proativa institucional; não afirma que o órgão está "
            "contratando no momento."
            if material
            else "Sinais fracos; necessita pesquisa adicional."
        )

        lead = {
            "entity_type": "PUBLIC_AGENCY_PROSPECT",
            "agency": prospect.as_dict(),
            "mode": mode,
            "mode_note": (
                "REACTIVE only when open published opportunity is observed; "
                "historical buyer-side contracts alone yield PROACTIVE_INSTITUTIONAL_PROSPECT."
            ),
            "score": score.as_dict(),
            "signals": [s.as_dict() for s in signals],
            "object_classification": cls_dict,
            "eligibility": eligibility,
            "fragmentation": frag_dict,
            "conflict": conflict.as_dict(),
            "contacts": research_only,
            "publishability": pub.as_dict(),
            "selected_service": {
                "service_id": service.get("service_id"),
                "nome": service.get("nome"),
                "escopo": service.get("escopo"),
                "entregaveis": service.get("entregaveis"),
                "exclusoes": service.get("exclusoes"),
                "faixa_preco_por_escopo": service.get("faixa_preco_por_escopo"),
                "duracao_estimada": service.get("duracao_estimada"),
            },
            "evidence": evidence,
            "contract_count": len(contracts),
            "total_value": total_value,
            "last_publication": last_pub,
            "limitations": [
                "Somatório anual completo da UG não disponível (DIRECT_CONTRACTING_SUM_UNKNOWN).",
                "População IBGE Censo 2022 (API oficial) é contexto, não prova de baixa capacidade.",
                "Sem contato institucional capturado — apenas research action.",
                "Modo proativo: não há edital/aviso aberto observado nesta fonte.",
                "Sem outreach automático.",
            ],
            "probable_problem": probable,
            "recommended_approach": (
                "Apresentar capacidade técnica e redução de risco; não vender dispensa de licitação. "
                "Pesquisar canal institucional oficial antes de qualquer contato."
            ),
            "next_human_step": (
                "Revisar conflito de interesses, classificação do objeto, dossier; "
                "localizar contato institucional público; autorizar ou rejeitar outreach."
            ),
            "outreach_message": (
                f"Prezados(as) de {prospect.nome_oficial},\n\n"
                "A CONFENGE presta apoio técnico especializado a órgãos públicos em "
                "planejamento de contratações de obras e serviços de engenharia, orçamentação "
                "e apoio técnico à fiscalização e à gestão contratual (sem substituir o fiscal público).\n\n"
                "Com base em dados públicos de contratações, identificamos sinais de possível "
                "necessidade técnica. Gostaríamos de apresentar nosso catálogo, se houver interesse institucional.\n\n"
                "Atenciosamente,\nCONFENGE"
            ),
            "compliance_blocks": compliance_blocks,
            "compliance_flags": compliance_flags,
            "require_conflict_check": require_conflict_check,
        }
        all_scored.append(lead)
        if pub.publishable:
            # Extra priority preference for ≤50k when building top list
            publishable_leads.append(lead)
        reasons_counter[pub.category] += 1

    # Rank publishable first by priority; if fewer than max_leads, do not pad with weak leads
    publishable_leads.sort(
        key=lambda lead: float((lead.get("score") or {}).get("priority_score") or 0),
        reverse=True,
    )
    # Prefer priority population when scores close
    def _rank_key(lead: dict[str, Any]) -> tuple[float, int]:
        pop = (lead.get("agency") or {}).get("populacao")
        prefer = 1 if pop is not None and pop <= priority_population_max else 0
        return (float((lead.get("score") or {}).get("priority_score") or 0), prefer)

    publishable_leads.sort(key=_rank_key, reverse=True)
    top = publishable_leads[:max_leads]
    for i, lead in enumerate(top, start=1):
        lead["rank_position"] = i

    # Dossiers + proposals for top
    dossiers_dir = out / "dossiers"
    proposals_dir = out / "proposals"
    for lead in top:
        write_dossier(dossiers_dir, lead)
        raw_svc = lead.get("selected_service")
        svc: dict[str, Any] = raw_svc if isinstance(raw_svc, dict) else {}
        try:
            raw_agency = lead.get("agency")
            agency_obj: dict[str, Any] = raw_agency if isinstance(raw_agency, dict) else {}
            raw_cls = lead.get("object_classification")
            raw_elig = lead.get("eligibility")
            prop = generate_proposal(
                agency_name=str(agency_obj.get("nome_oficial") or ""),
                problem=str(lead.get("probable_problem") or ""),
                object_text="Serviços técnicos de engenharia / apoio à contratação",
                service=svc,
                deliverables=list(svc.get("entregaveis") or [])[:8],
                effort_hours=80.0,
                object_classification=raw_cls if isinstance(raw_cls, dict) else None,
                eligibility=raw_elig if isinstance(raw_elig, dict) else None,
            )
            aid = str(agency_obj.get("agency_id") or "x")
            write_proposal(proposals_dir, prop, aid)
        except Exception:  # noqa: BLE001,S110
            pass

    kit_paths = {}
    if not skip_kit:
        kit_paths = generate_commercial_kit(out / "commercial-kit")

    reason = "PASS"
    status = "PASS"
    if not top:
        reason = NO_PUBLISHABLE_LEADS
        status = "PASS"  # honest empty publishable set is valid
    if evaluated == 0 and rows:
        reason = FILTER_REMOVED_ALL
        status = "PASS"

    result: dict[str, Any] = {
        "run_id": run_id,
        "campaign_id": CAMPAIGN_ID,
        "status": status,
        "reason": reason,
        "git_sha": sha,
        "artifact_git_sha": sha,
        "as_of": as_of.isoformat(),
        "started_at": utc_now(),
        "finished_at": utc_now(),
        "target": "public-agencies",
        "module_version": MODULE_VERSION,
        "config_hashes": config_hashes,
        "metrics": {
            "source": source_meta,
            "agency_universe": len(groups),
            "evaluated_agencies": evaluated,
            "publishable_agencies": len(publishable_leads),
            "blocked_agencies": blocked,
            "top_n": len(top),
            "reasons": dict(reasons_counter),
            "ufs": ufs,
            "priority_population_max": priority_population_max,
            "focus_population_max": focus_population_max,
            "kit_artifacts": len(kit_paths),
        },
        "leads": top,
        "outreach_sent": False,
        "non_claims": [
            "No guaranteed direct contracting",
            "No automatic outreach",
            "No substitution of public fiscal",
            "No invented credentials",
        ],
        "ready_state": "READY_FOR_TIAGO_REVIEW_PUBLIC_AGENCY_VERTICAL"
        if status == "PASS" and (top or reason == NO_PUBLISHABLE_LEADS)
        else "NOT_READY",
    }

    paths = export_public_agency_run(out, result)
    result["artifact_paths"] = paths
    # Also write cycle-manifest compatible file
    (out / "cycle-manifest.json").write_text(
        json.dumps(
            {
                "campaign_id": CAMPAIGN_ID,
                "status": status,
                "run_id": run_id,
                "git_sha": sha,
                "target": "public-agencies",
                "metrics": result["metrics"],
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    return result
