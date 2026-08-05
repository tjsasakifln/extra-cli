"""End-to-end reajuste 14.133 commercial pipeline (read-only source).

v2: keyset streaming, supplier portfolios, outreach gates, value quality,
document pipeline states, no silent 25k cap, fail-closed documentary proof.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from scripts.commercial.reajuste_14133 import (
    CALCULABLE_ADJUSTMENT_CLAIM,
    CAMPAIGN_SLUG,
    DATA_BASE_CONFIRMED,
    DEFAULT_AS_OF,
    DIAGNOSTIC_OUTREACH_READY,
    DOCUMENT_REQUEST_CANDIDATE,
    DOCUMENT_REQUEST_READY,
    LIKELY_ADJUSTMENT_OPPORTUNITY,
    MODULE_VERSION,
    NOT_READY_FOR_OUTREACH,
    OUTREACH_READY,
    OUTREACH_READY_WITHOUT_VALUE_ESTIMATE,
    POTENTIAL_ADJUSTMENT_SIGNAL,
    REGIME_14133,
    REGIME_CONFLICT,
    STATUS_ALREADY_ADJUSTED,
    STATUS_CLOSED,
    STATUS_HOT_VERIFIED,
    STATUS_LEGAL_REGIME_CONFLICT,
    STATUS_LEGAL_REGIME_UNKNOWN,
    STATUS_NOT_ELIGIBLE,
    STATUS_RESEARCH_REQUIRED,
    STATUS_REVIEW_REQUIRED,
    STATUS_STRONG_CANDIDATE,
    TEMPORAL_CANDIDATE_BY_PROXY,
    TEMPORAL_ELIGIBILITY_CONFIRMED,
    TEMPORAL_INCOMPLETE,
    TEMPORAL_UNKNOWN,
    TERMINAL_BLOCKED_INSUFFICIENT,
    TERMINAL_SUCCESS_OUTREACH,
    VERIFIED_ADJUSTMENT_OPPORTUNITY,
)
from scripts.commercial.reajuste_14133.checkpoint import (
    append_classified,
    classified_keys,
    clear_classified,
    load_classified,
    mark_stage,
    save_params,
)
from scripts.commercial.reajuste_14133.domain.adjustment_history import (
    classify_adjustment_history,
)
from scripts.commercial.reajuste_14133.domain.commercial_stages import (
    co_status_document_request,
    diagnostic_message,
    evaluate_commercial_stage,
)
from scripts.commercial.reajuste_14133.domain.contradictions import (
    detect_material_contradictions,
)
from scripts.commercial.reajuste_14133.domain.dates import consolidate_dates
from scripts.commercial.reajuste_14133.domain.eligibility import evaluate_eligibility
from scripts.commercial.reajuste_14133.domain.execution_status import (
    classify_execution_status,
)
from scripts.commercial.reajuste_14133.domain.finance import estimate_reajuste
from scripts.commercial.reajuste_14133.domain.freshness import compute_source_freshness
from scripts.commercial.reajuste_14133.domain.giants import is_giant_low_consulting_fit
from scripts.commercial.reajuste_14133.domain.obra_classifier import classify_construction
from scripts.commercial.reajuste_14133.domain.outreach import evaluate_outreach
from scripts.commercial.reajuste_14133.domain.regime import classify_legal_regime
from scripts.commercial.reajuste_14133.domain.scoring import rank_leads, score_lead
from scripts.commercial.reajuste_14133.domain.supplier_portfolio import (
    consolidate_suppliers,
)
from scripts.commercial.reajuste_14133.domain.value_quality import (
    may_use_for_financial_attractiveness,
    validate_contract_value,
)
from scripts.commercial.reajuste_14133.io.contacts import (
    contact_readiness_level,
    enrich_from_brasilapi,
    enrich_from_registry_row,
    is_contact_verifiable_for_diagnostic,
    merge_contacts,
)
from scripts.commercial.reajuste_14133.io.documents import (
    pncp_contract_url,
    verify_contract_documents,
)
from scripts.commercial.reajuste_14133.io.source import (
    count_prefilter,
    digits_cnpj,
    fetch_official_acts_mentions,
    fetch_supplier_registry,
    iter_contracts_keyset,
    mask_dsn,
    resolve_source,
    value_band,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]

PUBLIC_ORG_MARKERS = (
    "prefeitura", "municipio", "município", "governo", "secretaria", "ministerio",
    "ministério", "autarquia", "fundacao", "fundação", "instituto federal",
    "universidade federal", "camara municipal", "câmara municipal", "tribunal",
    "companhia de agua", "companhia de água", "companhia de saneamento",
    "departamento municipal de agua", "empresa publica", "empresa pública",
)

# Concessionárias de utilidade (água/energia) — not CONFENGE construction ICP
UTILITY_CONCESSIONAIRE_MARKERS = (
    "aguas de ", "águas de ", "agua e esgoto", "água e esgoto",
    "saneamento de ", "companhia catarinense de aguas", "casan",
    "copasa", "sabesp", "cedae", "embasa", "cagece", "compesa",
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def git_sha() -> str:
    try:
        out = subprocess.check_output(  # noqa: S603,S607
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=str(_PROJECT_ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return out.strip()
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return "unknown"


def _parse_as_of(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def is_private_supplier(cnpj: str | None, nome: str | None) -> bool:
    c = digits_cnpj(cnpj)
    if len(c) != 14:
        return False
    name = (nome or "").lower()
    # Utility concessionaires are private SPEs but outside construction ICP ranking
    if any(m in name for m in UTILITY_CONCESSIONAIRE_MARKERS):
        return False
    if any(m in name for m in PUBLIC_ORG_MARKERS):
        if re.search(r"\b(s\.?a\.?|s/a|ltda|eireli|spe)\b", name, re.I):
            if any(
                x in name
                for x in ("prefeitura", "municipio", "secretaria", "governo do", "uniao", "união")
            ):
                return False
        else:
            return False
    return True


def dedupe_key(row: dict[str, Any]) -> str:
    cid = (row.get("contrato_id") or "").strip()
    if cid:
        return f"cid:{cid}"
    raw = "|".join(
        [
            digits_cnpj(row.get("fornecedor_cnpj")),
            digits_cnpj(row.get("orgao_cnpj")),
            str(row.get("valor_total") or ""),
            str(row.get("data_assinatura") or row.get("data_inicio") or ""),
            (row.get("objeto_contrato") or "")[:80],
        ]
    )
    return "h:" + hashlib.sha256(raw.encode()).hexdigest()[:20]


def temporal_layer(dates: Any) -> str:
    if dates.data_base_status == DATA_BASE_CONFIRMED and dates.interregno_completo:
        return TEMPORAL_ELIGIBILITY_CONFIRMED
    if dates.data_base_status == "PROXY_PROSPECTION_ONLY" and dates.interregno_completo:
        return TEMPORAL_CANDIDATE_BY_PROXY
    if dates.data_base_effective.value is not None and not dates.interregno_completo:
        return TEMPORAL_INCOMPLETE
    return TEMPORAL_UNKNOWN


def _parse_date_field(v: Any) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v).strip()[:10])
    except ValueError:
        return None


def classify_row(
    row: dict[str, Any],
    *,
    as_of: date,
    doc_scan: Any | None = None,
    registry: dict[str, Any] | None = None,
    contacts: dict[str, Any] | None = None,
    structured_regime: str | None = None,
    human_review_done: bool = False,
    official_acts: list[dict[str, Any]] | None = None,
    human_review_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify a single contract row into a lead record."""
    objeto = row.get("objeto_contrato")
    cnpj = digits_cnpj(row.get("fornecedor_cnpj"))
    nome = (row.get("fornecedor_nome") or "").strip()
    cnae_hint = None
    if registry:
        cnae_hint = registry.get("cnae_principal") or registry.get("cnae")
    obra = classify_construction(
        objeto,
        razao_social=nome,
        cnae=cnae_hint,
        document_text=(
            " ".join(
                getattr(e, "excerpt", "") or ""
                for e in (getattr(doc_scan, "evidences", None) or [])
            )[:3000]
            if doc_scan
            else None
        ),
    )
    private = is_private_supplier(cnpj, nome)

    assin = row.get("data_assinatura")
    sig_year = None
    if assin:
        try:
            sig_year = int(str(assin)[:4])
        except ValueError:
            sig_year = None

    doc_texts: list[str] = []
    index_found = False
    index_in_clause = False
    docs_accessible = False
    text_extracted = False
    official_text = False
    already_adjusted = False
    index_name = None
    clause_located = False
    regime_conflict = False
    document_link_status = None
    document_link_validated = False
    data_base_exact_from_docs = False
    exact_data_base_payload = None
    signals_usable = True
    if doc_scan is not None:
        signals_usable = bool(getattr(doc_scan, "signals_usable", True))
        document_link_status = getattr(doc_scan, "document_link_status", None)
        document_link_validated = document_link_status in {
            "DOCUMENT_LINK_VERIFIED",
            "DOCUMENT_LINK_PARTIAL",
        }
        # Official PDF/edital text only — portal HTML / object never count
        # CONFLICT documents cannot prove regime/clause/index/data-base
        official_text = bool(getattr(doc_scan, "official_text_extracted", False)) and signals_usable
        text_extracted = official_text
        docs_accessible = bool(doc_scan.docs_accessible) and official_text and signals_usable
        if getattr(doc_scan, "pdf_binary_located", False) and not official_text:
            docs_accessible = False
        clause_located = bool(doc_scan.reajuste_clause_mention) and official_text and signals_usable
        regime_conflict = bool(getattr(doc_scan, "regime_conflict", False)) and signals_usable
        if doc_scan.regime_14133_mention and official_text:
            doc_texts.append("lei 14.133/2021 (documento oficial extraído)")
        for e in doc_scan.evidences:
            method = getattr(e, "extraction_method", "") or ""
            # Only official PDF/DOCX/sheet extract methods prove regime/clause
            if method not in {
                "pncp_pdf_pypdf2",
                "pncp_pdf_pypdf",
                "process_documents_pdf",
                "http_get_pdf_text",
                "pncp_docx",
                "pncp_xlsx",
                "pncp_ods",
                "pncp_zip_pdf",
                "pncp_zip_docx",
                "pncp_zip_xlsx",
                "pncp_zip_ods",
            }:
                continue
            if e.field_found == "regime_legal_14133" and e.excerpt:
                doc_texts.append(e.excerpt)
            if e.field_found == "clausula_reajuste" and e.excerpt:
                doc_texts.append(e.excerpt)
        in_clause = list(getattr(doc_scan, "index_in_clause", None) or []) if signals_usable else []
        index_found = bool(in_clause) and official_text
        index_in_clause = bool(in_clause) and official_text
        if in_clause and official_text:
            index_name = in_clause[0]
        already_adjusted = bool(doc_scan.already_adjusted_hint) and official_text
        data_base_exact_from_docs = bool(
            getattr(doc_scan, "data_base_exata_localizada", False)
        ) and signals_usable
        exact_data_base_payload = getattr(doc_scan, "exact_data_base", None)

    if official_acts:
        for act in official_acts[:5]:
            blob = str(act)[:500]
            if blob:
                doc_texts.append(blob)

    # Origin process / edital — may prove legacy regime over signature year
    origin_edital_year = None
    origin_process_year = None
    for key in (
        "ano_edital",
        "edital_year",
        "origin_edital_year",
        "ano_compra",
        "ano_licitacao",
    ):
        raw_y = row.get(key)
        if raw_y is not None and str(raw_y).strip():
            try:
                origin_edital_year = int(str(raw_y).strip()[:4])
                break
            except ValueError:
                pass
    for key in (
        "ano_processo",
        "origin_process_year",
        "process_year",
        "ano_contratacao_originaria",
    ):
        raw_y = row.get(key)
        if raw_y is not None and str(raw_y).strip():
            try:
                origin_process_year = int(str(raw_y).strip()[:4])
                break
            except ValueError:
                pass
    origin_doc_texts: list[str] = []
    for key in (
        "edital_fundamento_legal",
        "fundamento_legal",
        "origin_regime_text",
        "processo_fundamento",
    ):
        val = row.get(key)
        if val:
            origin_doc_texts.append(str(val))
    initiation_act = (
        row.get("data_edital")
        or row.get("data_abertura_licitacao")
        or row.get("initiation_act_date")
        or row.get("data_publicacao_edital")
    )

    regime = classify_legal_regime(
        structured_regime=structured_regime or row.get("regime_juridico") or row.get("lei"),
        document_texts=doc_texts or None,
        objeto=objeto if "14.133" in (objeto or "") or "14133" in (objeto or "") else None,
        signature_year=sig_year,
        published_on_pncp=True,
        origin_process_year=origin_process_year,
        origin_edital_year=origin_edital_year,
        origin_document_texts=origin_doc_texts or None,
        initiation_act_date=initiation_act,
        document_link_validated=document_link_validated,
        has_official_linked_document=bool(doc_texts) and text_extracted,
    )
    if regime_conflict and regime.regime in {REGIME_14133, "LIKELY_14133"}:
        regime = classify_legal_regime(
            document_texts=(doc_texts or []) + ["lei 8.666 e lei 14.133"],
            signature_year=sig_year,
            published_on_pncp=True,
            origin_process_year=origin_process_year,
            origin_edital_year=origin_edital_year,
            origin_document_texts=origin_doc_texts or None,
        )

    # Prefer exact data-base extracted from official docs (never signature/publication)
    orc_date = None
    orc_source = "missing"
    orc_conf = "none"
    if data_base_exact_from_docs and exact_data_base_payload:
        primary = (exact_data_base_payload or {}).get("primary") or {}
        orc_date = primary.get("value_date") or primary.get("value")
        orc_source = f"document:{primary.get('document') or 'official'}:{primary.get('state')}"
        orc_conf = "high" if primary.get("confidence") in {"high", "medium"} else "high"
    dates = consolidate_dates(
        as_of=as_of,
        orcamento_estimado=orc_date,
        orcamento_source=orc_source,
        orcamento_confidence=orc_conf,
        data_assinatura=row.get("data_assinatura"),
        data_publicacao=row.get("data_publicacao_fonte") or row.get("data_publicacao"),
        inicio_vigencia=row.get("data_inicio"),
        fim_vigencia=row.get("data_fim"),
        allow_proxy_for_prospection=True,
    )
    t_layer = temporal_layer(dates)

    exec_st = classify_execution_status(
        as_of=as_of,
        is_active=row.get("is_active"),
        data_fim=row.get("data_fim"),
        valor_total=float(row.get("valor_total") or 0) or None,
        valor_medido=None,
        valor_pago=None,
    )
    is_closed = exec_st.status in {"CONTRACT_CLOSED", "CONTRACT_FULLY_MEASURED"}

    value_q = validate_contract_value(
        valor_total=row.get("valor_total"),
        valor_atualizado=row.get("valor_total"),
        objeto=objeto,
        confirmed_by_document=False,
    )

    # Index series values only when confirmed — never invent
    finance = estimate_reajuste(
        valor_original=row.get("valor_total") if value_q.may_drive_financial_score else None,
        valor_atualizado=row.get("valor_total") if value_q.may_drive_financial_score else None,
        indice_contratual=index_name if index_in_clause else None,
        indice_base_value=None,
        indice_final_value=None,
    )

    adj = classify_adjustment_history(
        apostila_mentions=1 if (doc_scan and doc_scan.apostila_mention) else 0,
        reajuste_concedido_mentions=1 if already_adjusted else 0,
        searched_sources=bool(doc_scan and (doc_scan.evidences or doc_scan.network_error is False)),
        document_texts=doc_texts,
    )
    if already_adjusted:
        already_adjusted = adj.status in {
            "PRIOR_ADJUSTMENT_CONFIRMED",
            "PARTIAL_ADJUSTMENT_CONFIRMED",
        }

    outside_idx = bool(getattr(doc_scan, "index_outside_clause_only", None)) and not index_in_clause
    contrad = detect_material_contradictions(
        regime_labels=[regime.regime] if regime.regime else [],
        is_construction=obra.is_construction,
        object_text=objeto,
        value_status=value_q.status,
        already_adjusted=already_adjusted,
        index_in_clause=index_in_clause,
        index_outside_clause_only=outside_idx,
        legal_regime_conflict=regime.regime == REGIME_CONFLICT,
    )

    only_table = not docs_accessible
    elig = evaluate_eligibility(
        obra=obra,
        regime=regime,
        dates=dates,
        finance=finance,
        is_closed=is_closed,
        already_adjusted=already_adjusted and adj.status == "PRIOR_ADJUSTMENT_CONFIRMED",
        docs_accessible=docs_accessible,
        index_found=index_found and index_in_clause,
        material_contradiction=contrad.material_contradiction,
        has_private_supplier=private,
        only_table_dates=only_table,
    )

    contacts = contacts or {}
    contact_score = float(contacts.get("contact_score") or 0.0)
    uf = (
        (contacts.get("uf_sede") or row.get("uf") or "").upper()
        if contacts
        else (row.get("uf") or "").upper()
    )

    giant = is_giant_low_consulting_fit(
        nome, valor_contrato=float(row.get("valor_total") or 0) or None
    )
    too_small = bool(re.search(r"\bmei\b|microempresa individual", nome, re.I)) and float(
        row.get("valor_total") or 0
    ) > 20_000_000

    freshness = compute_source_freshness(
        as_of=as_of,
        data_publicacao=row.get("data_publicacao") or row.get("data_publicacao_fonte"),
        data_assinatura=row.get("data_assinatura"),
        data_atualizacao_fonte=row.get("data_atualizacao_fonte"),
        last_seen_at=row.get("last_seen_at"),
        source_event_date=row.get("source_event_date"),
    )

    portfolio_for_score = (
        float(row.get("valor_total") or 0)
        if may_use_for_financial_attractiveness(value_q.status)
        else 0.0
    )

    # Freemail alone is NOT diagnostic-verifiable (low confidence + requires review)
    contact_verifiable = is_contact_verifiable_for_diagnostic(contacts)
    contact_ready_lvl = contact_readiness_level(contacts)
    open_obl = exec_st.open_obligation_possible and not is_closed

    # Exact data-base: only structured extraction states (not mere "data-base" mention)
    data_base_exact = bool(data_base_exact_from_docs) or (
        dates.data_base_status == DATA_BASE_CONFIRMED
        and dates.data_base_effective.confidence == "high"
        and not str(dates.data_base_effective.source).startswith("proxy")
    )
    exact_budget_dt = _parse_date_field(orc_date) if data_base_exact else None
    if data_base_exact and exact_budget_dt is None and dates.data_base_effective.value:
        if not str(dates.data_base_effective.source).startswith("proxy"):
            exact_budget_dt = dates.data_base_effective.value

    # Human review: only from explicit complete import — never auto-forged
    hr_record = human_review_record or {}
    if hr_record:
        from scripts.commercial.reajuste_14133.io.human_review import (
            assess_human_review_completeness,
        )

        hr_assessment = assess_human_review_completeness(hr_record)
        human_review_done = bool(hr_assessment.get("can_mark_completed"))
        if human_review_done:
            human_review_status = "human_review_completed"
        elif hr_record.get("reviewer") or hr_record.get("decision"):
            human_review_status = "human_review_incomplete"
            human_review_done = False
        else:
            human_review_status = "human_review_pending"
            human_review_done = False
    else:
        # Explicit flag only if caller already validated completeness
        human_review_status = (
            "human_review_completed" if human_review_done else "human_review_pending"
        )

    obj_text = (objeto or "")
    object_mentions_14133 = bool(
        re.search(r"14[\./]?133|lei\s*14", obj_text, re.I)
    )

    commercial = evaluate_commercial_stage(
        as_of=as_of,
        is_construction=obra.is_construction,
        obra_confidence=float(obra.confidence or 0),
        private_supplier=private,
        regime=regime.regime,
        regime_proven=regime.proven,
        signature_year=sig_year,
        object_mentions_14133=object_mentions_14133,
        legal_confidence=getattr(regime, "legal_confidence", None),
        exact_budget_date=exact_budget_dt,
        data_assinatura=_parse_date_field(row.get("data_assinatura")),
        data_publicacao=_parse_date_field(
            row.get("data_publicacao_fonte") or row.get("data_publicacao")
        ),
        inicio_vigencia=_parse_date_field(row.get("data_inicio")),
        is_closed=is_closed,
        open_obligation=open_obl,
        fully_liquidated=exec_st.status == "CONTRACT_FULLY_MEASURED",
        adjustment_history=adj.status,
        clause_located=clause_located,
        index_or_formula=index_in_clause,
        docs_text_extracted=text_extracted,
        document_link_validated=document_link_validated,
        material_contradiction=contrad.material_contradiction,
        legal_regime_conflict=regime.regime == REGIME_CONFLICT,
        contact_verifiable=contact_verifiable,
        contact_confidence=contact_ready_lvl,
        human_review_done=human_review_done,
        has_calculable_base=(
            finance.base_label in {"SALDO_CONTRATUAL", "SALDO_DERIVADO"}
            and finance.base_reajustavel is not None
            and finance.base_reajustavel > 0
        ),
        has_index_series=(
            finance.indice_contratual is not None
            and finance.indice_base_value is not None
            and finance.indice_final_value is not None
        ),
        value_plausible=value_q.status in {"VALUE_CONFIRMED", "VALUE_PLAUSIBLE"},
        icp_compatible=not giant,
    )

    sc = score_lead(
        eligibility=elig,
        obra=obra,
        regime=regime,
        dates=dates,
        finance=finance,
        uf=uf,
        municipio=row.get("municipio"),
        portfolio_hint_brl=portfolio_for_score,
        contact_score=contact_score,
        source_freshness=freshness,
        is_giant_low_consulting_fit=giant,
        is_too_small_for_ticket=too_small,
        has_personal_only_contact=bool(contacts.get("has_personal_only_contact")),
        material_contradiction=contrad.material_contradiction,
        commercial_stage=commercial.commercial_stage,
        minimum_interregnum_elapsed=commercial.temporal.minimum_elapsed_confirmed,
        regime_probable=commercial.regime_probable_14133,
    )

    # Legacy claim-path outreach (fail-closed) — preserved for HOT/VERIFIED gates
    outreach = evaluate_outreach(
        eligibility_status=elig.status,
        regime=regime.regime,
        regime_proven=regime.proven,
        is_construction=obra.is_construction,
        private_supplier=private,
        clause_located=clause_located,
        data_base_status=dates.data_base_status,
        data_base_exact=data_base_exact,
        index_in_clause=index_in_clause,
        interregno_completo=bool(
            dates.interregno_completo or commercial.temporal.interregno_complete_exact
        ),
        open_obligation=open_obl,
        adjustment_history=adj.status,
        value_quality=value_q.status,
        contact_verifiable=contact_verifiable,
        human_review_done=human_review_done,
        has_valor_potencial=(
            finance.valor_potencial is not None and commercial.valor_potencial_allowed
        ),
        argument_cites_unproven_value=False,
        docs_text_extracted=text_extracted,
        legal_regime_conflict=regime.regime == REGIME_CONFLICT,
        document_link_validated=document_link_validated,
        document_link_status=document_link_status,
    )

    # Map commercial stage to primary operational outreach label when not claim-ready
    commercial_stage = commercial.commercial_stage
    document_request_co = co_status_document_request(
        commercial_stage, commercial.dimensions.documentary_confidence
    )
    if commercial_stage == DIAGNOSTIC_OUTREACH_READY:
        operational_outreach = DOCUMENT_REQUEST_CANDIDATE  # legacy export bucket
    elif commercial_stage == LIKELY_ADJUSTMENT_OPPORTUNITY:
        operational_outreach = DOCUMENT_REQUEST_CANDIDATE
    elif commercial_stage == CALCULABLE_ADJUSTMENT_CLAIM and human_review_done:
        operational_outreach = OUTREACH_READY
    elif commercial_stage == VERIFIED_ADJUSTMENT_OPPORTUNITY and human_review_done:
        operational_outreach = OUTREACH_READY_WITHOUT_VALUE_ESTIMATE
    else:
        operational_outreach = outreach.status
        if commercial_stage in {
            POTENTIAL_ADJUSTMENT_SIGNAL,
            LIKELY_ADJUSTMENT_OPPORTUNITY,
            DIAGNOSTIC_OUTREACH_READY,
            DOCUMENT_REQUEST_READY,
        } and operational_outreach == NOT_READY_FOR_OUTREACH:
            operational_outreach = commercial.outreach_status_legacy

    url = pncp_contract_url(row.get("contrato_id"), row.get("orgao_cnpj"))
    evidences_fav = list(commercial.favorable_signals)
    if obra.is_construction:
        evidences_fav.append(
            f"Objeto classificado como {obra.category} (conf={obra.confidence:.2f})"
        )
    if commercial.temporal.minimum_elapsed_confirmed:
        evidences_fav.append(
            f"Interregno mínimo conservador confirmado "
            f"(level={commercial.temporal.level}; "
            f"proxy={commercial.temporal.proxy_type})"
        )
    if dates.interregno_completo:
        evidences_fav.append(
            f"Interregno ≥12m na data-base efetiva ({dates.data_base_effective.source}) "
            f"[{t_layer}]"
        )
    if regime.proven:
        evidences_fav.append(f"Regime comprovado: {regime.regime}")
    if doc_scan and doc_scan.evidences:
        evidences_fav.append(
            f"{len(doc_scan.evidences)} evidências documentais "
            f"(pipeline={getattr(doc_scan, 'pipeline_state', '?')})"
        )
    evidences_fav = list(dict.fromkeys(evidences_fav))

    # Diagnostic language only — never claim due credit without verification
    if commercial_stage == DIAGNOSTIC_OUTREACH_READY:
        commercial_arg = diagnostic_message()
    elif commercial_stage in {LIKELY_ADJUSTMENT_OPPORTUNITY, DOCUMENT_REQUEST_READY}:
        commercial_arg = commercial.language_allowed
    elif commercial_stage == POTENTIAL_ADJUSTMENT_SIGNAL:
        commercial_arg = (
            f"Sinal comercial de possível maturidade anual em obra "
            f"({obra.category.replace('_', ' ')}). "
            f"Não constitui afirmação de crédito. "
            f"Temporal={commercial.temporal.level}."
        )
    elif operational_outreach == DOCUMENT_REQUEST_CANDIDATE:
        commercial_arg = diagnostic_message()
    else:
        commercial_arg = commercial.language_allowed or (
            f"Identificamos indícios de contrato de {obra.category.replace('_', ' ')} "
            f"com interregno anual potencialmente superado. "
            f"Confirmação depende de análise documental — sem valor devido afirmado."
        )

    # valor_potencial ONLY on CALCULABLE stage
    valor_potencial_out = None
    if commercial.valor_potencial_allowed and commercial_stage == CALCULABLE_ADJUSTMENT_CLAIM:
        valor_potencial_out = (
            float(finance.valor_potencial) if finance.valor_potencial is not None else None
        )

    lead: dict[str, Any] = {
        "classificacao": elig.status,
        "commercial_stage": commercial_stage,
        "commercial_dimensions": commercial.dimensions.as_dict(),
        "temporal_evidence": commercial.temporal.as_dict(),
        "exact_budget_date": (
            commercial.temporal.exact_budget_date.isoformat()
            if commercial.temporal.exact_budget_date
            else None
        ),
        "proxy_date": (
            commercial.temporal.proxy_date.isoformat()
            if commercial.temporal.proxy_date
            else None
        ),
        "proxy_type": commercial.temporal.proxy_type,
        "minimum_elapsed_confirmed": commercial.temporal.minimum_elapsed_confirmed,
        "temporal_reasoning": commercial.temporal.temporal_reasoning,
        "calculation_blocked": commercial.temporal.calculation_blocked,
        "document_request_ready": document_request_co
        or commercial_stage == DOCUMENT_REQUEST_READY,
        "regime_probable_14133": commercial.regime_probable_14133,
        "outreach_status": operational_outreach,
        "outreach_status_claim_path": outreach.status,
        "outreach_gates": outreach.gates,
        "outreach_gates_passed": outreach.gates_passed,
        "outreach_language": commercial.language_allowed
        if commercial_stage
        in {
            DIAGNOSTIC_OUTREACH_READY,
            LIKELY_ADJUSTMENT_OPPORTUNITY,
            DOCUMENT_REQUEST_READY,
        }
        else outreach.language_allowed,
        "outreach_next_action": commercial.next_action,
        "language_prohibited": commercial.prohibited_language,
        "missing_documents": commercial.missing_documents,
        "uncertainties": commercial.uncertainties,
        "score_total": sc.score_total,
        "opportunity_score": sc.opportunity_score,
        "verification_score": sc.verification_score,
        "commercial_fit_score": sc.commercial_fit_score,
        "priority_score": sc.priority_score,
        "score_decomposition": sc.components,
        "score_penalties": sc.penalties,
        "ranking_bucket": sc.ranking_bucket,
        "cnpj": cnpj,
        "razao_social": nome,
        "nome_fantasia": (contacts or {}).get("nome_fantasia")
        or (registry or {}).get("nome_fantasia"),
        "municipio_empresa": (contacts or {}).get("municipio_sede") or row.get("municipio"),
        "uf": uf,
        "cnae": (registry or {}).get("cnae_principal"),
        "situacao_cadastral": (registry or {}).get("situacao_cadastral"),
        "porte_cadastral": (registry or {}).get("porte") or (contacts or {}).get("porte"),
        "orgao_contratante": row.get("orgao_nome"),
        "orgao_cnpj": digits_cnpj(row.get("orgao_cnpj")),
        "contrato_id": row.get("contrato_id"),
        "objeto": (objeto or "")[:2000],
        "classificacao_obra": obra.category,
        "obra_confidence": obra.confidence,
        "obra_reasons": obra.reason_codes,
        "valor_original": float(row.get("valor_total") or 0),
        "valor_atualizado": float(row.get("valor_total") or 0),
        "value_quality": value_q.as_dict(),
        "value_quality_status": value_q.status,
        "saldo_conhecido": float(finance.saldo_contratual)
        if finance.saldo_contratual is not None
        else None,
        "regime_legal": regime.regime,
        "regime_proven": regime.proven,
        "regime_notes": regime.notes,
        "regime_evidence_level": getattr(regime, "evidence_level", None),
        "regime_legal_confidence": getattr(regime, "legal_confidence", None),
        "regime_chronological_context": getattr(regime, "chronological_context", None) or [],
        "regime_priority_documents": getattr(regime, "priority_documents", None) or [],
        "regime_probable_14133": commercial.regime_probable_14133,
        "message_template": getattr(commercial, "message_template", None),
        "origin_edital_year": origin_edital_year,
        "origin_process_year": origin_process_year,
        # Legal data-base only when exact; proxy lives solely in proxy_date/proxy_type
        "data_base": (
            exact_budget_dt.isoformat()
            if exact_budget_dt is not None
            else (
                dates.data_base_effective.value.isoformat()
                if (
                    data_base_exact
                    and dates.data_base_effective.value
                    and not str(dates.data_base_effective.source).startswith("proxy")
                )
                else None
            )
        ),
        "data_base_status": dates.data_base_status,
        "data_base_source": (
            dates.data_base_effective.source
            if data_base_exact
            and not str(dates.data_base_effective.source).startswith("proxy")
            else (
                "missing"
                if not data_base_exact
                else dates.data_base_effective.source
            )
        ),
        "data_base_confidence": (
            dates.data_base_effective.confidence
            if data_base_exact
            else "none"
        ),
        "data_base_exata_localizada": data_base_exact,
        "exact_data_base": exact_data_base_payload,
        "document_link_status": document_link_status,
        "document_link_validated": document_link_validated,
        "document_link": getattr(doc_scan, "document_link", None) if doc_scan else None,
        "doc_type_inventory": getattr(doc_scan, "doc_type_inventory", None) if doc_scan else None,
        "index_formula": getattr(doc_scan, "index_formula", None) if doc_scan else None,
        "signals_usable": signals_usable,
        "temporal_layer": t_layer,
        "indice": finance.indice_contratual,
        "indice_in_clause": index_in_clause,
        "data_proximo_reajuste": (
            dates.proxima_data_aniversario.isoformat() if dates.proxima_data_aniversario else None
        ),
        "dias_atraso_potencial": dates.dias_desde_reajuste_aplicavel,
        "vigencia_final": dates.fim_vigencia.value.isoformat() if dates.fim_vigencia.value else None,
        "dias_restantes_vigencia": dates.dias_restantes_vigencia,
        "percentual_reajuste": float(finance.percentual_acumulado)
        if finance.percentual_acumulado is not None
        else None,
        "base_potencialmente_reajustavel": float(finance.base_reajustavel)
        if finance.base_reajustavel is not None
        else None,
        "base_label": finance.base_label,
        "valor_potencial": valor_potencial_out,
        "teto_teorico": float(finance.teto_teorico) if finance.teto_teorico is not None else None,
        "teto_label": finance.teto_label,
        "status_reajustes_anteriores": adj.status,
        "adjustment_history": adj.status,
        "execution_status": exec_st.status,
        "evidencias_favoraveis": evidences_fav,
        "lacunas": list(dict.fromkeys(list(elig.gaps) + list(commercial.missing_documents))),
        "riscos": elig.risks + finance.limitations + contrad.items + value_q.notes,
        "proxima_acao_investigativa": commercial.next_action or elig.next_investigative_action,
        "argumento_comercial": commercial_arg,
        "canais_contato": {
            "email": (contacts or {}).get("email_comercial"),
            "email_low_confidence": (contacts or {}).get("email_comercial_low_confidence"),
            "email_confidence": (contacts or {}).get("email_confidence") or contact_ready_lvl,
            "telefone": (contacts or {}).get("telefone_empresarial"),
            "site": (contacts or {}).get("site_oficial"),
            "linkedin": (contacts or {}).get("linkedin_institucional"),
            "requires_review": bool((contacts or {}).get("contact_requires_review")),
        },
        "contact_sources": (contacts or {}).get("contact_sources") or [],
        "urls_oficiais": [u for u in [url] if u],
        "hot_gates": elig.hot_gates,
        "hot_gates_passed": elig.hot_gates_passed,
        "dates": dates.as_dict(),
        "finance": finance.as_dict(),
        "obra": obra.as_dict(),
        "regime": regime.as_dict(),
        "doc_scan": doc_scan.as_dict() if doc_scan else None,
        "document_pipeline_state": getattr(doc_scan, "pipeline_state", None) if doc_scan else None,
        "material_contradiction": contrad.material_contradiction,
        "contradictions": contrad.items,
        "source_freshness": freshness,
        "timestamp_analise": utc_now(),
        "module_version": MODULE_VERSION,
        "dedupe_key": dedupe_key(row),
        "data_assinatura": str(row.get("data_assinatura") or "")[:10] or None,
        "data_inicio": str(row.get("data_inicio") or "")[:10] or None,
        "data_publicacao": str(row.get("data_publicacao") or "")[:10] or None,
        "human_review_done": human_review_done,
        "human_review_status": human_review_status,
        "human_review_completed": bool(human_review_done),  # only true via import
        "human_review_record": hr_record or None,
        "automated_review_queue": not human_review_done,
        "is_giant_low_fit": giant,
        "value_band": value_band(float(row.get("valor_total") or 0) or None),
        "claim_readiness": commercial.dimensions.claim_readiness,
        "contact_readiness": commercial.dimensions.contact_readiness,
        "commercial_action": commercial.dimensions.commercial_action,
    }
    return lead


def run_pipeline(
    *,
    as_of: str | date = DEFAULT_AS_OF,
    scope: str = "national",
    uf: str | None = None,
    municipio: str | None = None,
    supplier_cnpj: str | None = None,
    min_contract_value: float = 1_000_000.0,
    min_potential_value: float | None = None,
    status_filter: str | None = None,
    top: int = 200,
    verify_documents: bool = False,
    max_document_fetches: int = 30,
    enrich_contacts: bool = False,
    max_contact_lookups: int = 40,
    dsn: str | None = None,
    prefer_ssh: bool = False,
    csv_path: str | None = None,
    dry_run: bool = False,
    batch_size: int = 2000,
    max_source_rows: int | None = None,
    resume_from: str | Path | None = None,
    checkpoint_dir: str | Path | None = None,
    require_proxy_interregno: bool = False,
    human_review_map: dict[str, bool] | None = None,
    human_review_records: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute full funnel with keyset streaming and supplier consolidation.

    Two-phase commercial pipeline:
      Phase 1 — cheap national structured triage (no remote docs/contacts).
      Phase 2 — document/contact deepen only for high-priority suppliers
                (Sul/SC, ICP fit, material value, age >12m, multi-contract).

    ``max_source_rows=None`` (default) means full prefiltered universe.
    Any non-None cap is diagnostic sampling and is recorded in the manifest.
    """
    as_of_d = _parse_as_of(as_of)
    cfg = resolve_source(dsn, prefer_ssh=prefer_ssh, csv_path=csv_path)
    started = utc_now()
    run_dir: Path | None = None
    if resume_from:
        run_dir = Path(resume_from)
    elif checkpoint_dir:
        run_dir = Path(checkpoint_dir)
    funnel: dict[str, int] = {
        "examined_raw": 0,
        "after_dedupe": 0,
        "private_supplier": 0,
        "construction": 0,
        "regime_14133_proven": 0,
        "temporally_mature": 0,
        "data_base_confirmed": 0,
        "index_located": 0,
        "already_adjusted": 0,
        "universe_eligible_count": 0,
        "sampled": 0,
        STATUS_HOT_VERIFIED: 0,
        STATUS_STRONG_CANDIDATE: 0,
        STATUS_REVIEW_REQUIRED: 0,
        STATUS_RESEARCH_REQUIRED: 0,
        STATUS_ALREADY_ADJUSTED: 0,
        STATUS_NOT_ELIGIBLE: 0,
        STATUS_LEGAL_REGIME_UNKNOWN: 0,
        STATUS_LEGAL_REGIME_CONFLICT: 0,
        STATUS_CLOSED: 0,
        OUTREACH_READY: 0,
        OUTREACH_READY_WITHOUT_VALUE_ESTIMATE: 0,
        DOCUMENT_REQUEST_CANDIDATE: 0,
        NOT_READY_FOR_OUTREACH: 0,
        POTENTIAL_ADJUSTMENT_SIGNAL: 0,
        LIKELY_ADJUSTMENT_OPPORTUNITY: 0,
        DIAGNOSTIC_OUTREACH_READY: 0,
        DOCUMENT_REQUEST_READY: 0,
        VERIFIED_ADJUSTMENT_OPPORTUNITY: 0,
        CALCULABLE_ADJUSTMENT_CLAIM: 0,
        "commercial_stage_not_commercial": 0,
        "minimum_interregnum_elapsed": 0,
    }
    excluded: list[dict[str, Any]] = []
    uf_dist: Counter[str] = Counter()
    band_dist: Counter[str] = Counter()
    cat_dist: Counter[str] = Counter()
    if dry_run:
        return {
            "run_id": f"dry-{as_of_d.isoformat()}",
            "as_of": as_of_d.isoformat(),
            "module_version": MODULE_VERSION,
            "campaign": CAMPAIGN_SLUG,
            "source_mode": cfg.mode,
            "source_dsn_masked": mask_dsn(cfg.dsn or ""),
            "dry_run": True,
            "started_at": started,
            "funnel": funnel,
            "leads": [],
            "supplier_portfolios": [],
            "excluded": [],
            "message": "dry-run: no source fetch",
        }

    sampling_reason = None
    if max_source_rows is not None:
        sampling_reason = (
            f"DIAGNOSTIC max_source_rows={max_source_rows} — not a full national analysis"
        )

    params = {
        "as_of": as_of_d.isoformat(),
        "scope": scope,
        "uf": uf,
        "municipio": municipio,
        "min_contract_value": min_contract_value,
        "top": top,
        "verify_documents": verify_documents,
        "enrich_contacts": enrich_contacts,
        "max_source_rows": max_source_rows,
        "sampling_reason": sampling_reason,
        "require_proxy_interregno": require_proxy_interregno,
        "pagination": "keyset",
    }
    if run_dir is not None:
        run_dir.mkdir(parents=True, exist_ok=True)
        save_params(run_dir, params)

    # Universe count (best-effort)
    try:
        universe_n = count_prefilter(
            cfg,
            as_of=as_of_d,
            min_contract_value=min_contract_value,
            uf=uf,
            municipio=municipio,
            supplier_cnpj=supplier_cnpj,
            scope=scope,
            require_proxy_interregno=require_proxy_interregno,
        )
    except Exception as exc:
        universe_n = -1
        params["universe_count_error"] = str(exc)[:200]
    funnel["universe_eligible_count"] = universe_n

    leads: list[dict[str, Any]] = []
    already_keys: set[str] = set()
    seen_dedupe: set[str] = set()
    if run_dir is not None and resume_from:
        prior = load_classified(run_dir)
        leads.extend(prior)
        already_keys = classified_keys(run_dir)
        for lead in prior:
            st = lead.get("classificacao") or ""
            if st in funnel:
                funnel[st] = funnel.get(st, 0) + 1
            ost = lead.get("outreach_status") or ""
            if ost in funnel:
                funnel[ost] = funnel.get(ost, 0) + 1
            if (lead.get("obra") or {}).get("is_construction"):
                funnel["construction"] += 1
            funnel["private_supplier"] += 1
            funnel["examined_raw"] += 1
            seen_dedupe.add(str(lead.get("dedupe_key") or lead.get("contrato_id") or ""))
    elif run_dir is not None and not resume_from:
        clear_classified(run_dir)

    doc_fetches = 0
    contact_lookups = 0
    contact_attempts = 0
    docs_processed_deep = 0
    human_map = human_review_map or {}
    human_records = human_review_records or {}
    # raw rows kept for phase-2 reclassify
    raw_by_key: dict[str, dict[str, Any]] = {}

    # Incremental: stream batches — Phase 1 cheap structured triage only
    registry_map: dict[str, dict[str, Any]] = {}
    cnpj_buffer: list[str] = []

    for batch in iter_contracts_keyset(
        cfg,
        as_of=as_of_d,
        min_contract_value=min_contract_value,
        uf=uf,
        municipio=municipio,
        supplier_cnpj=supplier_cnpj,
        scope=scope,
        batch_size=batch_size,
        max_rows=max_source_rows,
        require_proxy_interregno=require_proxy_interregno,
    ):
        # Registry for this batch (structured only — no BrasilAPI yet)
        batch_cnpjs = [digits_cnpj(r.get("fornecedor_cnpj")) for r in batch]
        cnpj_buffer.extend(batch_cnpjs)
        missing = [c for c in batch_cnpjs if c and c not in registry_map]
        if missing:
            registry_map.update(fetch_supplier_registry(cfg, missing[:500]))

        for row in batch:
            funnel["examined_raw"] += 1
            row_key = dedupe_key(row)
            if row_key in already_keys or row_key in seen_dedupe:
                excluded.append(
                    {"contrato_id": row.get("contrato_id"), "reason": "duplicata_instrumento"}
                )
                continue
            seen_dedupe.add(row_key)
            raw_by_key[row_key] = row

            uf_dist[str(row.get("uf") or "?").upper()] += 1
            band_dist[value_band(float(row.get("valor_total") or 0) or None)] += 1

            cnpj = digits_cnpj(row.get("fornecedor_cnpj"))
            nome = row.get("fornecedor_nome")
            if not is_private_supplier(cnpj, nome):
                excluded.append(
                    {
                        "contrato_id": row.get("contrato_id"),
                        "cnpj": cnpj,
                        "reason": "fornecedor_nao_privado_ou_orgao",
                    }
                )
                continue
            funnel["private_supplier"] += 1

            pre_obra = classify_construction(row.get("objeto_contrato"), razao_social=nome)
            cat_dist[pre_obra.category] += 1

            # Phase 1: local/structured docs only — no remote document budget burn
            doc_scan = verify_contract_documents(
                contrato_id=str(row.get("contrato_id") or ""),
                orgao_cnpj=row.get("orgao_cnpj"),
                orgao_nome=row.get("orgao_nome"),
                objeto=row.get("objeto_contrato"),
                fetch_remote=False,
                max_fetches=0,
            )

            contacts = enrich_from_registry_row(registry_map.get(cnpj))

            cid = str(row.get("contrato_id") or "")
            hr_rec = human_records.get(cid) or human_records.get(cnpj) or {}
            hr = bool(
                human_map.get(cid, False)
                or human_map.get(cnpj, False)
                or (
                    hr_rec.get("decision") in {"ACCEPT", "CONFIRMED", "APPROVED"}
                    and hr_rec.get("reviewer")
                )
            )

            lead = classify_row(
                row,
                as_of=as_of_d,
                doc_scan=doc_scan,
                registry=registry_map.get(cnpj),
                contacts=contacts,
                human_review_done=hr,
                human_review_record=hr_rec or None,
            )
            lead["_dedupe_key_internal"] = row_key
            if run_dir is not None and lead.get("obra", {}).get("is_construction"):
                append_classified(run_dir, lead)
                already_keys.add(row_key)

            st = lead["classificacao"]
            funnel[st] = funnel.get(st, 0) + 1
            ost = lead.get("outreach_status") or NOT_READY_FOR_OUTREACH
            funnel[ost] = funnel.get(ost, 0) + 1
            cst = lead.get("commercial_stage") or ""
            if cst in funnel:
                funnel[cst] = funnel.get(cst, 0) + 1
            elif cst == "NOT_COMMERCIAL":
                funnel["commercial_stage_not_commercial"] = (
                    funnel.get("commercial_stage_not_commercial", 0) + 1
                )
            if lead.get("minimum_elapsed_confirmed"):
                funnel["minimum_interregnum_elapsed"] = (
                    funnel.get("minimum_interregnum_elapsed", 0) + 1
                )
            if lead["obra"]["is_construction"]:
                funnel["construction"] += 1
            else:
                excluded.append(
                    {
                        "contrato_id": lead.get("contrato_id"),
                        "cnpj": cnpj,
                        "reason": "objeto_nao_construcao:"
                        + ",".join(lead.get("obra_reasons") or []),
                    }
                )
                continue

            if lead.get("regime_proven") and lead.get("regime_legal") == REGIME_14133:
                funnel["regime_14133_proven"] += 1
            if lead.get("dates", {}).get("interregno_completo") or lead.get(
                "minimum_elapsed_confirmed"
            ):
                funnel["temporally_mature"] += 1
            if lead.get("data_base_status") == "CONFIRMED":
                funnel["data_base_confirmed"] += 1
            if lead.get("indice") and lead.get("indice_in_clause"):
                funnel["index_located"] += 1
            if st == STATUS_ALREADY_ADJUSTED:
                funnel["already_adjusted"] += 1

            if st in {STATUS_NOT_ELIGIBLE, STATUS_CLOSED, STATUS_ALREADY_ADJUSTED}:
                excluded.append(
                    {
                        "contrato_id": lead.get("contrato_id"),
                        "cnpj": cnpj,
                        "reason": st,
                        "detail": (lead.get("lacunas") or lead.get("evidencias_favoraveis") or [""])[
                            :3
                        ],
                    }
                )

            if min_potential_value is not None:
                pot = lead.get("valor_potencial") or 0
                teto = lead.get("teto_teorico") or 0
                if max(pot or 0, teto or 0) < min_potential_value and st not in {
                    STATUS_HOT_VERIFIED,
                    STATUS_STRONG_CANDIDATE,
                } and lead.get("commercial_stage") not in {
                    LIKELY_ADJUSTMENT_OPPORTUNITY,
                    DIAGNOSTIC_OUTREACH_READY,
                }:
                    continue

            if status_filter and st != status_filter and lead.get("commercial_stage") != status_filter:
                continue

            leads.append(lead)

    funnel["after_dedupe"] = len(seen_dedupe)
    if max_source_rows is not None:
        funnel["sampled"] = funnel["examined_raw"]

    # Rank by priority_score (commercial potential) before deepen
    def _priority_key(lead: dict[str, Any]) -> tuple:
        return (
            -float(lead.get("priority_score") or lead.get("score_total") or 0),
            -float(lead.get("opportunity_score") or 0),
            -float(lead.get("valor_atualizado") or lead.get("valor_original") or 0),
            str(lead.get("contrato_id") or ""),
        )

    leads.sort(key=_priority_key)

    # Phase 2 — deepen docs/contacts only for high-priority suppliers
    # Priority order: Sul/SC → ICP fit → material value → age>12m → multi-contract → non-giant
    def _deepen_rank(lead: dict[str, Any]) -> tuple:
        uf_l = (lead.get("uf") or "").upper()
        sul = 2 if uf_l == "SC" else (1 if uf_l in {"PR", "RS"} else 0)
        return (
            -sul,
            -float(lead.get("priority_score") or 0),
            -float(lead.get("opportunity_score") or 0),
            -float(lead.get("valor_atualizado") or 0),
            str(lead.get("contrato_id") or ""),
        )

    deepen_candidates = [
        lead
        for lead in leads
        if lead.get("commercial_stage")
        in {
            POTENTIAL_ADJUSTMENT_SIGNAL,
            LIKELY_ADJUSTMENT_OPPORTUNITY,
            DIAGNOSTIC_OUTREACH_READY,
            DOCUMENT_REQUEST_READY,
            VERIFIED_ADJUSTMENT_OPPORTUNITY,
            CALCULABLE_ADJUSTMENT_CLAIM,
        }
        or lead.get("obra", {}).get("is_construction")
    ]
    deepen_candidates.sort(key=_deepen_rank)

    # Supplier consolidation preview for multi-contract boost in deepen order
    cnpj_counts: Counter[str] = Counter(
        str(lead.get("cnpj") or "") for lead in deepen_candidates if lead.get("cnpj")
    )
    deepen_candidates.sort(
        key=lambda lead: (
            - (2 if (lead.get("uf") or "").upper() == "SC" else (1 if (lead.get("uf") or "").upper() in {"PR", "RS"} else 0)),
            -min(5, cnpj_counts.get(str(lead.get("cnpj") or ""), 0)),
            -float(lead.get("priority_score") or 0),
            -float(lead.get("opportunity_score") or 0),
            str(lead.get("contrato_id") or ""),
        )
    )

    if verify_documents or enrich_contacts:
        deepen_n = max(max_document_fetches, max_contact_lookups, 30)
        deepen_slice = deepen_candidates[:deepen_n]
        lead_by_cid = {str(lead.get("contrato_id") or ""): lead for lead in leads}
        deepened_cnpjs: set[str] = set()

        for lead in deepen_slice:
            cid = str(lead.get("contrato_id") or "")
            cnpj = str(lead.get("cnpj") or "")
            row = raw_by_key.get(str(lead.get("_dedupe_key_internal") or ""))
            if row is None:
                # reconstruct minimal row from lead
                row = {
                    "contrato_id": cid,
                    "fornecedor_cnpj": cnpj,
                    "fornecedor_nome": lead.get("razao_social"),
                    "orgao_cnpj": lead.get("orgao_cnpj"),
                    "orgao_nome": lead.get("orgao_contratante"),
                    "objeto_contrato": lead.get("objeto"),
                    "valor_total": lead.get("valor_original"),
                    "data_assinatura": lead.get("data_assinatura"),
                    "data_inicio": lead.get("data_inicio"),
                    "data_publicacao": lead.get("data_publicacao"),
                    "data_fim": lead.get("vigencia_final"),
                    "uf": lead.get("uf"),
                    "municipio": lead.get("municipio_empresa"),
                    "is_active": lead.get("execution_status") == "CONTRACT_ACTIVE",
                }

            doc_scan = None
            if verify_documents and doc_fetches < max_document_fetches:
                doc_scan = verify_contract_documents(
                    contrato_id=cid,
                    orgao_cnpj=row.get("orgao_cnpj"),
                    orgao_nome=row.get("orgao_nome"),
                    objeto=row.get("objeto_contrato"),
                    fetch_remote=True,
                    max_fetches=3,
                )
                doc_fetches += 1
                if getattr(doc_scan, "deep_document_work", False) or (
                    getattr(doc_scan, "pdfs_downloaded", 0) or 0
                ) > 0:
                    docs_processed_deep += 1
                if getattr(doc_scan, "official_text_extracted", False):
                    funnel["official_pdf_text_extracted"] = (
                        funnel.get("official_pdf_text_extracted", 0) + 1
                    )
                if getattr(doc_scan, "pdfs_downloaded", 0):
                    funnel["pdfs_downloaded"] = funnel.get("pdfs_downloaded", 0) + int(
                        doc_scan.pdfs_downloaded
                    )

            contacts = enrich_from_registry_row(registry_map.get(cnpj))
            if (
                enrich_contacts
                and contact_lookups < max_contact_lookups
                and cnpj
                and cnpj not in deepened_cnpjs
            ):
                contact_attempts += 1
                ba = enrich_from_brasilapi(cnpj)
                contacts = merge_contacts(contacts, ba)
                contact_lookups += 1
                deepened_cnpjs.add(cnpj)

            hr_rec = human_records.get(cid) or human_records.get(cnpj) or {}
            hr = bool(
                human_map.get(cid, False)
                or human_map.get(cnpj, False)
                or (
                    hr_rec.get("decision") in {"ACCEPT", "CONFIRMED", "APPROVED"}
                    and hr_rec.get("reviewer")
                )
            )
            reclass = classify_row(
                row,
                as_of=as_of_d,
                doc_scan=doc_scan,
                registry=registry_map.get(cnpj),
                contacts=contacts,
                human_review_done=hr,
                human_review_record=hr_rec or None,
            )
            reclass["_dedupe_key_internal"] = lead.get("_dedupe_key_internal")
            # Replace in leads list
            for i, existing in enumerate(leads):
                if str(existing.get("contrato_id") or "") == cid and str(
                    existing.get("cnpj") or ""
                ) == cnpj:
                    leads[i] = reclass
                    break
            lead_by_cid[cid] = reclass

        # Rebuild commercial stage funnel counts after deepen
        for key in (
            POTENTIAL_ADJUSTMENT_SIGNAL,
            LIKELY_ADJUSTMENT_OPPORTUNITY,
            DIAGNOSTIC_OUTREACH_READY,
            DOCUMENT_REQUEST_READY,
            VERIFIED_ADJUSTMENT_OPPORTUNITY,
            CALCULABLE_ADJUSTMENT_CLAIM,
            "commercial_stage_not_commercial",
        ):
            funnel[key] = 0
        for lead in leads:
            cst = lead.get("commercial_stage") or ""
            if cst in funnel:
                funnel[cst] = funnel.get(cst, 0) + 1
            elif cst == "NOT_COMMERCIAL":
                funnel["commercial_stage_not_commercial"] = (
                    funnel.get("commercial_stage_not_commercial", 0) + 1
                )

    # Best-effort official acts for top construction leads
    top_for_acts = [
        lead for lead in leads if lead.get("obra", {}).get("is_construction")
    ][:30]
    try:
        acts_map = fetch_official_acts_mentions(
            cfg, [str(lead.get("contrato_id") or "") for lead in top_for_acts]
        )
        for lead in top_for_acts:
            cid = str(lead.get("contrato_id") or "")
            if acts_map.get(cid):
                lead["official_acts_hits"] = len(acts_map[cid])
    except Exception as exc:
        params["official_acts_error"] = str(exc)[:200]

    # Rank contracts then consolidate suppliers (priority_score first)
    leads.sort(key=_priority_key)
    leads_ranked = rank_leads(leads)
    for i, lead in enumerate(leads_ranked, start=1):
        lead["ranking"] = i
        lead.pop("_dedupe_key_internal", None)
    nacional = rank_leads(leads, ranking="NACIONAL")
    sul = rank_leads(leads, ranking="SUL_SC_PRIORITY")

    portfolios = consolidate_suppliers(leads_ranked)

    # Commercial actionable queue: LIKELY / DIAGNOSTIC / VERIFIED / CALCULABLE + legacy strong
    actionable = [
        lead
        for lead in leads_ranked
        if lead.get("commercial_stage")
        in {
            LIKELY_ADJUSTMENT_OPPORTUNITY,
            DIAGNOSTIC_OUTREACH_READY,
            DOCUMENT_REQUEST_READY,
            VERIFIED_ADJUSTMENT_OPPORTUNITY,
            CALCULABLE_ADJUSTMENT_CLAIM,
            POTENTIAL_ADJUSTMENT_SIGNAL,
        }
        or lead.get("classificacao")
        in {
            STATUS_HOT_VERIFIED,
            STATUS_STRONG_CANDIDATE,
            STATUS_REVIEW_REQUIRED,
            STATUS_RESEARCH_REQUIRED,
            STATUS_LEGAL_REGIME_UNKNOWN,
        }
    ]
    top_leads = actionable[:top]

    ready_suppliers = [
        p
        for p in portfolios
        if p.get("commercial_stage")
        in {DIAGNOSTIC_OUTREACH_READY, VERIFIED_ADJUSTMENT_OPPORTUNITY, CALCULABLE_ADJUSTMENT_CLAIM}
        or p.get("outreach_status")
        in {OUTREACH_READY, OUTREACH_READY_WITHOUT_VALUE_ESTIMATE}
    ]
    doc_req_suppliers = [
        p
        for p in portfolios
        if p.get("document_request_ready")
        or p.get("commercial_stage")
        in {DOCUMENT_REQUEST_READY, LIKELY_ADJUSTMENT_OPPORTUNITY, DIAGNOSTIC_OUTREACH_READY}
        or p.get("outreach_status") == DOCUMENT_REQUEST_CANDIDATE
    ]
    not_ready_suppliers = [
        p
        for p in portfolios
        if p.get("commercial_stage") in {None, "NOT_COMMERCIAL", POTENTIAL_ADJUSTMENT_SIGNAL}
        and p.get("outreach_status") == NOT_READY_FOR_OUTREACH
    ]

    pot_sum = sum(float(lead.get("valor_potencial") or 0) for lead in top_leads)
    teto_sum = sum(float(lead.get("teto_teorico") or 0) for lead in top_leads)

    # Commercial success = diagnostic/likely queue non-empty (not only claim-ready OUTREACH)
    commercial_queue_n = sum(
        1
        for p in portfolios
        if p.get("commercial_stage")
        in {
            LIKELY_ADJUSTMENT_OPPORTUNITY,
            DIAGNOSTIC_OUTREACH_READY,
            VERIFIED_ADJUSTMENT_OPPORTUNITY,
            CALCULABLE_ADJUSTMENT_CLAIM,
        }
    )
    if commercial_queue_n >= 1 or len(ready_suppliers) >= 1:
        terminal = TERMINAL_SUCCESS_OUTREACH
    elif docs_processed_deep >= 200 or doc_fetches >= 200:
        terminal = TERMINAL_BLOCKED_INSUFFICIENT
    elif funnel["examined_raw"] > 0 and commercial_queue_n == 0:
        terminal = TERMINAL_BLOCKED_INSUFFICIENT
    else:
        terminal = TERMINAL_BLOCKED_INSUFFICIENT

    if run_dir is not None:
        mark_stage(
            run_dir,
            "classified",
            n_leads=len(leads_ranked),
            n_suppliers=len(portfolios),
            doc_fetches=doc_fetches,
            contact_lookups=contact_lookups,
            docs_processed_deep=docs_processed_deep,
        )

    complete = max_source_rows is None and (
        universe_n < 0 or funnel["examined_raw"] >= universe_n * 0.95
    )

    return {
        "run_id": f"{CAMPAIGN_SLUG}-{as_of_d.isoformat()}-{git_sha()[:8]}",
        "as_of": as_of_d.isoformat(),
        "module_version": MODULE_VERSION,
        "campaign": CAMPAIGN_SLUG,
        "git_sha": git_sha(),
        "source_mode": cfg.mode,
        "source_dsn_masked": mask_dsn(
            cfg.dsn or ("ssh:" + cfg.ssh_host if cfg.mode == "ssh" else "")
        ),
        "started_at": started,
        "finished_at": utc_now(),
        "resumed": bool(resume_from),
        "checkpoint_dir": str(run_dir / ".checkpoint") if run_dir else None,
        "terminal_status": terminal,
        "params": {
            "scope": scope,
            "uf": uf,
            "municipio": municipio,
            "min_contract_value": min_contract_value,
            "min_potential_value": min_potential_value,
            "top": top,
            "verify_documents": verify_documents,
            "max_document_fetches": max_document_fetches,
            "doc_fetches_used": doc_fetches,
            "docs_processed_deep": docs_processed_deep,
            "contact_lookups_used": contact_lookups,
            "contact_attempts": contact_attempts,
            "enrich_contacts": enrich_contacts,
            "max_source_rows": max_source_rows,
            "sampling_reason": sampling_reason,
            "pagination": "keyset",
            "require_proxy_interregno": require_proxy_interregno,
            "universe_eligible_count": universe_n,
            "execution_complete": complete,
        },
        "funnel": funnel,
        "distributions": {
            "uf": dict(uf_dist),
            "value_band": dict(band_dist),
            "obra_category": dict(cat_dist),
        },
        "metrics": {
            "top_leads": len(top_leads),
            "all_classified": len(leads_ranked),
            "supplier_portfolios": len(portfolios),
            "outreach_ready_suppliers": len(ready_suppliers),
            "outreach_ready_without_value_suppliers": len(
                [
                    p
                    for p in portfolios
                    if p.get("outreach_status") == OUTREACH_READY_WITHOUT_VALUE_ESTIMATE
                ]
            ),
            "document_request_suppliers": len(doc_req_suppliers),
            "not_ready_suppliers": len(not_ready_suppliers),
            "valor_potencial_agregado_top": pot_sum,
            "teto_teorico_agregado_top": teto_sum,
            "document_fetch_coverage": doc_fetches,
            "docs_processed_deep": docs_processed_deep,
            "official_pdf_text_extracted": funnel.get("official_pdf_text_extracted", 0),
            "pdfs_downloaded": funnel.get("pdfs_downloaded", 0),
            "arquivos_listed": funnel.get("arquivos_listed", 0),
            "docs_processed_deep_definition": (
                "contracts with PNCP compra PDF download attempted "
                "(not portal HTML alone)"
            ),
            "excluded_count": len(excluded),
            "contact_lookups_used": contact_lookups,
            "contact_attempts": contact_attempts,
            "universe_eligible_count": universe_n,
            "rows_read": funnel["examined_raw"],
            "execution_complete": complete,
            "sampling_reason": sampling_reason,
        },
        "leads": leads_ranked,
        "top_leads": top_leads,
        "nacional": nacional[:top],
        "sul_sc_priority": sul[:top],
        "supplier_portfolios": portfolios,
        "outreach_ready_suppliers": ready_suppliers,
        "document_request_suppliers": doc_req_suppliers,
        "not_ready_suppliers": not_ready_suppliers,
        "excluded": excluded,
        "language_policy": {
            "reajuste_sentido_estrito_only": True,
            "not_reequilibrio": True,
            "not_repactuacao": True,
            "not_atualizacao_por_atraso": True,
            "not_aditivo_quantitativo": True,
            "not_legal_opinion": True,
            "hot_verified_requires_documentary_gates": True,
            "no_hot_from_pncp_supplier_contracts_dates_alone": True,
            "legal_regime_unknown_never_outreach_ready": True,
            "pdf_binary_not_documentary_proof": True,
            "no_prior_adjustment_located_not_proof": True,
            "unit_is_supplier_not_contract": True,
        },
    }
