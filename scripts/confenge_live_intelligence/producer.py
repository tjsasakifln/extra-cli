"""LI-6 — producer e barreira de snapshot (Decisao 7).

Maquina de estados: ``BUILDING → READY_CANONICAL | PARTIAL | BLOCKED``.

Criterio de completude e POR LINHA com exclusao contada (§7.2):

* ``READY_CANONICAL`` — zero linha excluida. ``UNKNOWN`` em dimensao OPCIONAL
  (``dim_value_band``, ``dim_comparable_buyer``) NAO exclui e NAO impede READY.
* ``PARTIAL`` — pelo menos uma linha excluida por ``UNKNOWN`` em dimensao
  REQUERIDA (``dim_object``, ``dim_geography``) ou por ``dim_recency`` nao
  resolvida. Terminal, selado e consumivel: ``closed_at`` e ``content_hash``
  presentes, ``blockers`` vazio.
* ``BLOCKED`` — condicao da lista fechada de §7.2. ``blockers`` nao vazio,
  nenhum consumo permitido.

Escrita: EXCLUSIVAMENTE nas tabelas ``confenge_live_intelligence_*`` criadas
pela migration 104. Nenhum INSERT/UPDATE/DELETE sobre tabela outbound — o
portfolio e as oportunidades sao lidos por SELECT (ver ``sources.py``).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from scripts.confenge_activation.commercial_authority_v2 import cnpj_root8
from scripts.confenge_contract_identity import public_contract_id
from scripts.confenge_live_intelligence import sources
from scripts.confenge_live_intelligence.contract_date_resolver import (
    DATE_RESOLVER_VERSION,
    TRUST_OBSERVED,
    most_recent_contracting_date,
)
from scripts.confenge_live_intelligence.fit import (
    evaluate_fit,
    required_dimension_unknown,
    sort_fits,
)
from scripts.confenge_live_intelligence.schema import (
    BLOCKER_AS_OF_MISSING,
    BLOCKER_EMPTY_CONTRACT_ID,
    BLOCKER_WATERMARK_MISSING,
    CUTOFF_TIMEZONE,
    DEADLINE_CLOSED,
    DEADLINE_OPEN,
    ENGINE_ID,
    ENGINE_VERSION,
    OBSERVED,
    REASON_CONTRACTING_DATE_UNRESOLVED,
    REASON_DEADLINE_MISSING,
    REASON_GEO_MISSING,
    REASON_MODALIDADE_MISSING,
    REASON_OBJECT_MISSING,
    REASON_ORGAO_MISSING,
    REASON_ROW_EXCLUDED_REQUIRED_UNKNOWN,
    REASON_VALUE_MISSING,
    ROW_COMPLETE,
    ROW_EXCLUDED_INCOMPLETE,
    ROW_EXCLUDED_UNRESOLVED_DATE,
    SCHEMA_VERSION,
    SNAPSHOT_BLOCKED,
    SNAPSHOT_PARTIAL,
    SNAPSHOT_READY,
    UNKNOWN,
    WRITE_TARGET_ORDER,
    LiveCompany,
    LiveCompanyOpportunityFit,
    LiveOpportunity,
    assert_write_target,
    live_hash,
    policy_hash,
    schema_hash,
    value_band,
)

DEFAULT_SOURCE = "pncp"


class LiveIntelligenceProducerError(RuntimeError):
    """Falha do producer. Fail-closed: nunca deixa snapshot meio-fechado."""


@dataclass(frozen=True)
class SnapshotResult:
    snapshot_id: str
    state: str
    as_of_date: date
    universe_hash: str
    policy_hash: str
    schema_hash: str
    data_hash: str
    fit_hash: str
    content_hash: str | None
    observed_opportunity_count: int
    excluded_opportunity_count: int
    observed_company_count: int
    excluded_company_count: int
    blockers: tuple[str, ...] = ()
    handoff_marker: str = "NO"

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "snapshot_id": self.snapshot_id,
            "state": self.state,
            "as_of_date": self.as_of_date.isoformat(),
            "universe_hash": self.universe_hash,
            "content_hash": self.content_hash,
            "observed_opportunity_count": self.observed_opportunity_count,
            "excluded_opportunity_count": self.excluded_opportunity_count,
            "observed_company_count": self.observed_company_count,
            "excluded_company_count": self.excluded_company_count,
            "blockers": list(self.blockers),
            "LIVE_INTELLIGENCE_HANDOFF_READY": self.handoff_marker,
        }
        return payload


@dataclass
class _Universe:
    opportunities: list[LiveOpportunity] = field(default_factory=list)
    companies: list[LiveCompany] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


# --- projecao --------------------------------------------------------------


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def today_in_cutoff_timezone() -> date:
    """Data civil de hoje no fuso que o motor sela (``CUTOFF_TIMEZONE``).

    Por que NAO ``date.today()`` (REL-002). ``date.today()`` resolve no fuso do
    SO — em UTC, na maioria dos hosts. O motor fixa ``CUTOFF_TIMEZONE`` em
    ``sources.pin_session_timezone()`` e ``policy_hash()`` sela esse mesmo nome,
    logo entre ~21:00 e 00:00 UTC o SO e o motor discordam da data civil. Como
    essa data entra em ``as_of_date`` e no ``snapshot_id`` do snapshot BLOCKED,
    a divergencia produzia dois ids para o mesmo bloqueio. Mesma classe de
    defeito de TD-LI-7, agora no codigo de producao.

    Fonte de fuso UNICA: o nome e importado de ``schema.CUTOFF_TIMEZONE``.
    Nenhum segundo literal de fuso neste modulo.
    """
    return datetime.now(tz=ZoneInfo(CUTOFF_TIMEZONE)).date()


def normalize_source_as_of(value: datetime) -> datetime:
    """Normaliza o watermark para UTC — instante estavel, representacao unica.

    ``live_hash`` serializa ``datetime`` por ``isoformat()``, logo o MESMO
    instante com ``tzinfo`` diferente produz strings diferentes e hashes
    diferentes. Como o watermark e lido de uma coluna ``TIMESTAMPTZ``, o driver
    devolve o offset da sessao — que o motor muda ao fixar ``CUTOFF_TIMEZONE``.
    Normalizar para UTC torna o hash funcao do INSTANTE, nao do fuso da sessao
    (mesma propriedade que AC5 exige de ``universe_hash``).
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def project_opportunity(row: Mapping[str, Any], *, as_of: date, source_as_of: datetime) -> LiveOpportunity:
    """Projeta uma linha as-of em OPPORTUNITY, com UNKNOWN explicito e tipado.

    ``source_as_of`` e OBRIGATORIO e vem do watermark observado da fonte
    (``sources.fetch_source_watermark``). Nao existe default de relogio de
    parede: ``source_as_of`` entra em ``content_hash()`` -> ``data_hash_of()``
    -> ``content_hash_of()`` -> ``snapshot_id``, logo qualquer valor derivado de
    ``datetime.now()`` faria dois builds do MESMO snapshot de entrada gerarem
    ids distintos e o ``DELETE ... WHERE snapshot_id`` de ``_persist`` nunca
    encontraria o snapshot anterior — as tabelas do motor ACUMULARIAM linhas em
    vez de reconstruir (REL-001). Ausencia de watermark ja tem ramo BLOCKED em
    ``build_snapshot``; nao ha fallback silencioso aqui.
    """
    reason_codes: list[str] = []

    objeto = (row.get("objeto") or "").strip() or None
    objeto_state = OBSERVED if objeto else UNKNOWN
    if objeto_state == UNKNOWN:
        reason_codes.append(REASON_OBJECT_MISSING)

    valor_raw = row.get("valor_estimado")
    valor = Decimal(str(valor_raw)) if valor_raw is not None else None
    valor_state = OBSERVED if valor is not None else UNKNOWN
    if valor_state == UNKNOWN:
        reason_codes.append(REASON_VALUE_MISSING)

    modalidade = (row.get("modalidade") or "").strip() or None
    modalidade_id = row.get("modalidade_id")
    modalidade_state = OBSERVED if modalidade else UNKNOWN
    if modalidade_state == UNKNOWN:
        reason_codes.append(REASON_MODALIDADE_MISSING)

    uf = (row.get("uf") or "").strip().upper() or None
    geo_state = OBSERVED if uf else UNKNOWN
    if geo_state == UNKNOWN:
        reason_codes.append(REASON_GEO_MISSING)

    orgao_cnpj_raw = "".join(ch for ch in str(row.get("orgao_cnpj") or "") if ch.isdigit())
    orgao_cnpj = orgao_cnpj_raw if len(orgao_cnpj_raw) == 14 else None
    orgao_state = OBSERVED if orgao_cnpj else UNKNOWN
    if orgao_state == UNKNOWN:
        reason_codes.append(REASON_ORGAO_MISSING)

    encerramento = _as_date(row.get("data_encerramento"))
    if encerramento is None:
        deadline_state = UNKNOWN
        reason_codes.append(REASON_DEADLINE_MISSING)
    elif encerramento >= as_of:
        deadline_state = DEADLINE_OPEN
    else:
        deadline_state = DEADLINE_CLOSED

    return LiveOpportunity(
        opportunity_id=str(row.get("bid_id") or row.get("pncp_id") or "").strip(),
        source=str(row.get("source") or DEFAULT_SOURCE),
        source_as_of=normalize_source_as_of(source_as_of),
        objeto=objeto,
        objeto_state=objeto_state,
        valor_estimado_brl=valor,
        valor_state=valor_state,
        valor_band=value_band(valor),
        modalidade_id=str(modalidade_id) if modalidade_id is not None else None,
        modalidade=modalidade,
        modalidade_state=modalidade_state,
        uf=uf,
        municipio=(row.get("municipio") or None),
        codigo_ibge=(row.get("codigo_ibge") or None),
        geo_state=geo_state,
        orgao_cnpj=orgao_cnpj,
        orgao_nome=(row.get("orgao_nome") or None),
        orgao_state=orgao_state,
        data_publicacao=_as_date(row.get("data_publicacao")),
        data_encerramento=encerramento,
        deadline_state=deadline_state,
        link_edital=(row.get("link_edital") or None),
        source_id=(row.get("source_id") or None),
        reason_codes=tuple(sorted(set(reason_codes))),
    )


def project_companies(
    portfolio_rows: Sequence[Mapping[str, Any]],
    *,
    source_as_of: datetime,
    allow_legacy_surrogate: bool = False,
) -> tuple[list[LiveCompany], list[str]]:
    """Agrupa contratos observados por raiz de CNPJ. Retorna (companies, blockers).

    ``source_as_of`` e OBRIGATORIO e e o MESMO watermark da fonte usado pela
    projecao de OPPORTUNITY (REL-001). Entra em ``portfolio_hash()``, logo
    relogio de parede aqui quebraria a idempotencia de replay do mesmo modo.
    """
    blockers: list[str] = []
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in portfolio_rows:
        root = cnpj_root8(row.get("supplier_cnpj"))
        if len(root) != 8:
            continue
        contract_id = public_contract_id(dict(row), allow_legacy_surrogate=allow_legacy_surrogate)
        if not contract_id:
            if BLOCKER_EMPTY_CONTRACT_ID not in blockers:
                blockers.append(BLOCKER_EMPTY_CONTRACT_ID)
            continue
        grouped.setdefault(root, []).append(row)

    companies: list[LiveCompany] = []
    for root in sorted(grouped):
        rows = grouped[root]
        resolved, trust, _fields = most_recent_contracting_date(list(rows))
        observed_date = trust == TRUST_OBSERVED and resolved is not None
        reason_codes: list[str] = []
        exclusion: tuple[str, ...] = ()
        completeness = ROW_COMPLETE
        if not observed_date:
            reason_codes.append(REASON_CONTRACTING_DATE_UNRESOLVED)
            exclusion = (REASON_CONTRACTING_DATE_UNRESOLVED,)
            completeness = ROW_EXCLUDED_UNRESOLVED_DATE

        contract_ids = tuple(
            sorted({public_contract_id(dict(r), allow_legacy_surrogate=allow_legacy_surrogate) for r in rows} - {""})
        )
        bands = tuple(sorted({b for b in (value_band(r.get("valor")) for r in rows) if b}))
        ufs = tuple(sorted({str(r.get("uf")).upper() for r in rows if r.get("uf")}))
        buyers = tuple(
            sorted({"".join(ch for ch in str(r.get("buyer_cnpj") or "") if ch.isdigit()) for r in rows} - {""})
        )
        objects = tuple(sorted({str(r.get("objeto")) for r in rows if r.get("objeto")}))
        razao = next((str(r.get("supplier_nome")) for r in rows if r.get("supplier_nome")), None)

        companies.append(
            LiveCompany(
                company_root8=root,
                source_as_of=normalize_source_as_of(source_as_of),
                date_resolver_version=DATE_RESOLVER_VERSION,
                razao_social=razao,
                portfolio_contract_ids=contract_ids,
                observed_objects=objects,
                observed_value_bands=bands,
                observed_ufs=ufs,
                observed_buyer_cnpjs=buyers,
                most_recent_contracting_date=resolved if observed_date else None,
                contracting_date_state=OBSERVED if observed_date else UNKNOWN,
                row_completeness_state=completeness,
                exclusion_reason_codes=exclusion,
                reason_codes=tuple(sorted(set(reason_codes))),
            )
        )
    return companies, blockers


# --- hashes ----------------------------------------------------------------


def universe_hash_of(
    opportunities: Iterable[LiveOpportunity],
    companies: Iterable[LiveCompany],
    *,
    as_of: date,
) -> str:
    """Hash do universo observado. Independente de fuso e de ordem fisica."""
    return live_hash(
        {
            "as_of_date": as_of.isoformat(),
            "cutoff_timezone": CUTOFF_TIMEZONE,
            "schema_version": SCHEMA_VERSION,
            "opportunity_ids": sorted(o.opportunity_id for o in opportunities),
            "company_roots": sorted(c.company_root8 for c in companies),
        }
    )


def data_hash_of(opportunities: Sequence[LiveOpportunity], companies: Sequence[LiveCompany]) -> str:
    return live_hash(
        {
            "opportunities": [o.content_hash() for o in sorted(opportunities, key=lambda x: x.opportunity_id)],
            "companies": [c.portfolio_hash() for c in sorted(companies, key=lambda x: x.company_root8)],
        }
    )


def fit_hash_of(fits: Sequence[LiveCompanyOpportunityFit]) -> str:
    return live_hash({"fits": [f.fit_hash() for f in sort_fits(list(fits))]})


def content_hash_of(*, universe: str, policy: str, schema: str, data: str, fits: str) -> str:
    return live_hash(
        {
            "engine_id": ENGINE_ID,
            "engine_version": ENGINE_VERSION,
            "universe_hash": universe,
            "policy_hash": policy,
            "schema_hash": schema,
            "data_hash": data,
            "fit_hash": fits,
        }
    )


# --- construcao do snapshot ------------------------------------------------


def _apply_row_exclusions(
    opportunities: list[LiveOpportunity],
    fits: list[LiveCompanyOpportunityFit],
) -> list[LiveOpportunity]:
    """Exclui, por linha, oportunidades cujo FIT tem UNKNOWN em dimensao REQUERIDA."""
    excluded_ids: set[str] = set()
    for fit in fits:
        if required_dimension_unknown(fit):
            excluded_ids.add(fit.opportunity_id)
    if not excluded_ids:
        return opportunities
    rebuilt: list[LiveOpportunity] = []
    for opportunity in opportunities:
        if opportunity.opportunity_id not in excluded_ids:
            rebuilt.append(opportunity)
            continue
        reasons = tuple(sorted(set(opportunity.reason_codes) | {REASON_ROW_EXCLUDED_REQUIRED_UNKNOWN}))
        rebuilt.append(
            LiveOpportunity(
                **{
                    **{f: getattr(opportunity, f) for f in opportunity.__dataclass_fields__},
                    "row_completeness_state": ROW_EXCLUDED_INCOMPLETE,
                    "exclusion_reason_codes": (REASON_ROW_EXCLUDED_REQUIRED_UNKNOWN,),
                    "reason_codes": reasons,
                }
            )
        )
    return rebuilt


def build_snapshot(
    conn: Any,
    *,
    as_of: date | None,
    created_by: str,
    opportunities: Sequence[LiveOpportunity] | None = None,
    companies: Sequence[LiveCompany] | None = None,
    extra_blockers: Sequence[str] = (),
    persist: bool = True,
) -> SnapshotResult:
    """Constroi e sela um snapshot. Nunca falha silenciosamente.

    ``opportunities``/``companies`` permitem injetar universo sintetico nos
    testes de criterio de estado (AC8) sem tocar nenhuma tabela outbound.

    O watermark da fonte e PRE-CONDICAO do caminho de projecao: ele e a
    proveniencia de ``source_as_of`` dos dois objetos projetados (§3 do
    impact-analysis, "proveniencia obrigatoria por campo derivado"). Ausencia de
    watermark curto-circuita em BLOCKED ANTES de qualquer projecao — nao existe
    mais o antigo ``require_watermark``, que permitia projetar sem watermark e
    obrigava um relogio de parede como origem de ``source_as_of`` (REL-001).
    """
    blockers: list[str] = list(extra_blockers)
    if as_of is None:
        return _blocked_result(
            conn,
            as_of=today_in_cutoff_timezone(),
            created_by=created_by,
            blockers=[BLOCKER_AS_OF_MISSING],
            persist=persist,
        )

    universe = _Universe()
    if opportunities is None or companies is None:
        watermark = sources.fetch_source_watermark(conn, DEFAULT_SOURCE)
        source_as_of = watermark.get("watermark_at") if watermark else None
        if not isinstance(source_as_of, datetime):
            blockers.append(BLOCKER_WATERMARK_MISSING)
            return _blocked_result(conn, as_of=as_of, created_by=created_by, blockers=blockers, persist=persist)
        rows = sources.fetch_open_opportunities_as_of(conn, as_of)
        universe.opportunities = [
            project_opportunity(row, as_of=as_of, source_as_of=source_as_of)
            for row in rows
            if (row.get("bid_id") or row.get("pncp_id"))
        ]
        portfolio = sources.fetch_observed_portfolio(conn)
        built_companies, company_blockers = project_companies(portfolio, source_as_of=source_as_of)
        universe.companies = built_companies
        blockers.extend(b for b in company_blockers if b not in blockers)
    else:
        universe.opportunities = list(opportunities)
        universe.companies = list(companies)

    if blockers:
        return _blocked_result(conn, as_of=as_of, created_by=created_by, blockers=blockers, persist=persist)

    active_companies = [c for c in universe.companies if c.row_completeness_state == ROW_COMPLETE]
    fits = [
        evaluate_fit(company, opportunity, as_of=as_of)
        for company in active_companies
        for opportunity in universe.opportunities
        if opportunity.row_completeness_state == ROW_COMPLETE
    ]
    opportunities_final = _apply_row_exclusions(universe.opportunities, fits)
    kept_ids = {o.opportunity_id for o in opportunities_final if o.row_completeness_state == ROW_COMPLETE}
    fits = [f for f in fits if f.opportunity_id in kept_ids]

    excluded_opportunities = sum(1 for o in opportunities_final if o.row_completeness_state != ROW_COMPLETE)
    excluded_companies = sum(1 for c in universe.companies if c.row_completeness_state != ROW_COMPLETE)
    observed_opportunities = len(opportunities_final) - excluded_opportunities
    observed_companies = len(universe.companies) - excluded_companies

    u_hash = universe_hash_of(opportunities_final, universe.companies, as_of=as_of)
    p_hash = policy_hash(date_resolver_version=DATE_RESOLVER_VERSION)
    s_hash = schema_hash()
    d_hash = data_hash_of(opportunities_final, universe.companies)
    f_hash = fit_hash_of(fits)
    c_hash = content_hash_of(universe=u_hash, policy=p_hash, schema=s_hash, data=d_hash, fits=f_hash)

    state = SNAPSHOT_READY if (excluded_opportunities == 0 and excluded_companies == 0) else SNAPSHOT_PARTIAL
    snapshot_id = _snapshot_id(as_of=as_of, content=c_hash)

    result = SnapshotResult(
        snapshot_id=snapshot_id,
        state=state,
        as_of_date=as_of,
        universe_hash=u_hash,
        policy_hash=p_hash,
        schema_hash=s_hash,
        data_hash=d_hash,
        fit_hash=f_hash,
        content_hash=c_hash,
        observed_opportunity_count=observed_opportunities,
        excluded_opportunity_count=excluded_opportunities,
        observed_company_count=observed_companies,
        excluded_company_count=excluded_companies,
        blockers=(),
        handoff_marker="YES" if state == SNAPSHOT_READY else "PARTIAL",
    )
    if persist:
        _persist(conn, result, opportunities_final, universe.companies, fits, created_by=created_by)
    return result


def _snapshot_id(*, as_of: date, content: str) -> str:
    return f"LI-{as_of.isoformat()}-{content[:32]}"


def _blocked_result(
    conn: Any,
    *,
    as_of: date,
    created_by: str,
    blockers: Sequence[str],
    persist: bool,
) -> SnapshotResult:
    p_hash = policy_hash(date_resolver_version=DATE_RESOLVER_VERSION)
    s_hash = schema_hash()
    u_hash = live_hash({"blocked": sorted(set(blockers)), "as_of": as_of.isoformat()})
    result = SnapshotResult(
        snapshot_id=f"LI-{as_of.isoformat()}-BLOCKED-{u_hash[:20]}",
        state=SNAPSHOT_BLOCKED,
        as_of_date=as_of,
        universe_hash=u_hash,
        policy_hash=p_hash,
        schema_hash=s_hash,
        data_hash=live_hash({"data": []}),
        fit_hash=live_hash({"fits": []}),
        content_hash=None,
        observed_opportunity_count=0,
        excluded_opportunity_count=0,
        observed_company_count=0,
        excluded_company_count=0,
        blockers=tuple(sorted(set(blockers))),
        handoff_marker="NO",
    )
    if persist:
        _persist(conn, result, [], [], [], created_by=created_by)
    return result


# --- persistencia (somente tabelas confenge_live_intelligence_*) -----------


def _persist(
    conn: Any,
    result: SnapshotResult,
    opportunities: Sequence[LiveOpportunity],
    companies: Sequence[LiveCompany],
    fits: Sequence[LiveCompanyOpportunityFit],
    *,
    created_by: str,
) -> None:
    import json

    # `now` alimenta APENAS `cutoff_at`/`closed_at`/`recorded_at`, que sao
    # colunas de AUDITORIA: nenhuma delas entra em `universe_hash_of`,
    # `data_hash_of`, `fit_hash_of`, `content_hash_of` nem nos hashes de linha
    # (ver as whitelists `*_PAYLOAD_KEYS` em schema.py). Logo o replay reescreve
    # esses timestamps sob o MESMO `snapshot_id`, por desenho — este relogio de
    # parede NAO e insumo de hash e nao afeta a idempotencia corrigida em
    # REL-001.
    now = datetime.now(tz=UTC)
    with conn.cursor() as cur:
        # Replay idempotente: reconstroi o mesmo snapshot_id do zero.
        # AR-2: `table` vem EXCLUSIVAMENTE de `WRITE_TARGET_ORDER` (schema.py) e
        # e revalidado por `assert_write_target()` antes de cada execucao. Nao
        # existe tupla local de nomes de tabela neste modulo — e isso que o
        # teste do AC11 amarra estaticamente.
        for table in WRITE_TARGET_ORDER:
            cur.execute(
                f"DELETE FROM public.{assert_write_target(table)} WHERE snapshot_id = %s",  # noqa: S608
                (result.snapshot_id,),
            )
        cur.execute(
            """
            INSERT INTO public.confenge_live_intelligence_snapshots (
                snapshot_id, engine_id, engine_version, schema_version,
                as_of_date, cutoff_at, cutoff_timezone, date_resolver_version,
                universe_hash, policy_hash, schema_hash, data_hash, fit_hash, content_hash,
                state, observed_opportunity_count, excluded_opportunity_count,
                observed_company_count, excluded_company_count,
                blockers, closed_at, created_by
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s::jsonb, %s, %s
            )
            """,
            (
                result.snapshot_id,
                ENGINE_ID,
                ENGINE_VERSION,
                SCHEMA_VERSION,
                result.as_of_date,
                now,
                CUTOFF_TIMEZONE,
                DATE_RESOLVER_VERSION,
                result.universe_hash,
                result.policy_hash,
                result.schema_hash,
                result.data_hash,
                result.fit_hash,
                result.content_hash,
                result.state,
                result.observed_opportunity_count,
                result.excluded_opportunity_count,
                result.observed_company_count,
                result.excluded_company_count,
                json.dumps(list(result.blockers)),
                None if result.state == SNAPSHOT_BLOCKED else now,
                created_by,
            ),
        )
        for opportunity in opportunities:
            cur.execute(
                """
                INSERT INTO public.confenge_live_intelligence_opportunities (
                    snapshot_id, opportunity_id, objeto, objeto_state,
                    valor_estimado_brl, valor_state, valor_band,
                    modalidade_id, modalidade, modalidade_state,
                    uf, municipio, codigo_ibge, geo_state,
                    orgao_cnpj, orgao_nome, orgao_state,
                    data_publicacao, data_encerramento, deadline_state,
                    link_edital, source, source_id, source_as_of,
                    row_completeness_state, exclusion_reason_codes, reason_codes,
                    opportunity_hash
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
                """,
                (
                    result.snapshot_id,
                    opportunity.opportunity_id,
                    opportunity.objeto,
                    opportunity.objeto_state,
                    opportunity.valor_estimado_brl,
                    opportunity.valor_state,
                    opportunity.valor_band,
                    opportunity.modalidade_id,
                    opportunity.modalidade,
                    opportunity.modalidade_state,
                    opportunity.uf,
                    opportunity.municipio,
                    opportunity.codigo_ibge,
                    opportunity.geo_state,
                    opportunity.orgao_cnpj,
                    opportunity.orgao_nome,
                    opportunity.orgao_state,
                    opportunity.data_publicacao,
                    opportunity.data_encerramento,
                    opportunity.deadline_state,
                    opportunity.link_edital,
                    opportunity.source,
                    opportunity.source_id,
                    opportunity.source_as_of,
                    opportunity.row_completeness_state,
                    list(opportunity.exclusion_reason_codes),
                    list(opportunity.reason_codes),
                    opportunity.content_hash(),
                ),
            )
        for company in companies:
            cur.execute(
                """
                INSERT INTO public.confenge_live_intelligence_companies (
                    snapshot_id, company_root8, razao_social,
                    portfolio_contract_ids, observed_objects, observed_value_bands,
                    observed_ufs, observed_buyer_cnpjs,
                    most_recent_contracting_date, contracting_date_state, date_resolver_version,
                    row_completeness_state, exclusion_reason_codes, reason_codes,
                    portfolio_hash, source_as_of
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    result.snapshot_id,
                    company.company_root8,
                    company.razao_social,
                    list(company.portfolio_contract_ids),
                    list(company.observed_objects),
                    list(company.observed_value_bands),
                    list(company.observed_ufs),
                    list(company.observed_buyer_cnpjs),
                    company.most_recent_contracting_date,
                    company.contracting_date_state,
                    company.date_resolver_version,
                    company.row_completeness_state,
                    list(company.exclusion_reason_codes),
                    list(company.reason_codes),
                    company.portfolio_hash(),
                    company.source_as_of,
                ),
            )
        for fit in sort_fits(list(fits)):
            cur.execute(
                """
                INSERT INTO public.confenge_live_intelligence_fit (
                    snapshot_id, company_root8, opportunity_id,
                    dim_object, dim_value_band, dim_geography,
                    dim_comparable_buyer, dim_recency,
                    matched_dimensions, unknown_dimensions, reason_codes, evidence_refs,
                    fit_state, fit_hash
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
                """,
                (
                    result.snapshot_id,
                    fit.company_root8,
                    fit.opportunity_id,
                    fit.dim_object,
                    fit.dim_value_band,
                    fit.dim_geography,
                    fit.dim_comparable_buyer,
                    fit.dim_recency,
                    list(fit.matched_dimensions),
                    list(fit.unknown_dimensions),
                    list(fit.reason_codes),
                    json.dumps(fit.evidence_refs, sort_keys=True),
                    fit.fit_state,
                    fit.fit_hash(),
                ),
            )
    conn.commit()
