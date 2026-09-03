"""LI-W2 §A — bundle estatico do contrato ``CONFENGE_LIVE_INTELLIGENCE/1.0``.

``manifest.json`` + ``opportunities/<opportunity_id>.json`` +
``companies/<company_digest>.json``, gerados **deterministicamente a partir de um
snapshot ja selado**.

Tres invariantes que governam o modulo inteiro:

1. **Funcao pura do snapshot (AC2).** Todo dado vem das tabelas
   ``confenge_live_intelligence_*``. Nenhuma view outbound
   (``v_contracts_canonical_v2``, ``v_open_opportunities_canonical``) e lida
   durante o export. Calcular estabelecimento/digest em tempo de export a partir
   da view foi **rejeitado explicitamente** pela arquitetura: tornaria o export
   funcao da view (matando o replay) e criaria uma segunda fonte de identidade.
2. **Nenhum relogio de parede (AC3).** ``export.py`` nao chama
   ``datetime.now()``. ``generated_at`` e ``snapshots.cutoff_at``; ``source_as_of``
   e o ``min`` dos watermarks dos payloads emitidos.
3. **Fail-closed (AC1).** Estado nao exportavel, invariante de ``freshness``
   violada ou company ``ROW_COMPLETE`` sem digest → **nada e escrito**, nem o
   manifest. O bundle e montado inteiro em memoria antes do primeiro ``write``.

Nao-reprodutibilidade DECLARADA (AC4): ``generated_at``, ``freshness`` e
``manifest_hash`` variam entre duas execucoes se houver **re-persist** do mesmo
``snapshot_id`` entre elas — ``cutoff_at`` e reescrito no persist
(``producer.py``, ``_persist``). Dois exports **sem** re-persist leem o mesmo
``cutoff_at`` e produzem ``content_hash`` identico por arquivo. Nenhum teste pode
afirmar ``manifest_hash`` estavel atraves de re-persist.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts.confenge_live_intelligence import public_policy as policy
from scripts.confenge_live_intelligence.fit import ordering_key
from scripts.confenge_live_intelligence.identity import cnpj_digest
from scripts.confenge_live_intelligence.schema import (
    FIT_OBSERVED,
    NO_MATCH,
    ROW_COMPLETE,
    SNAPSHOT_BLOCKED,
    UNKNOWN,
    LiveCompany,
    LiveCompanyOpportunityFit,
    LiveOpportunity,
    canonical_json,
    live_hash,
)

# Reuso deliberado dos rebuilds do verifier: uma SEGUNDA reconstrucao das
# dataclasses a partir das mesmas linhas seria uma segunda fonte de verdade —
# a classe de defeito que a story rejeita em identidade e em allowlist.
from scripts.confenge_live_intelligence.verifier import (
    _rebuild_company,
    _rebuild_fit,
    _rebuild_opportunity,
)

OPPORTUNITIES_DIR = "opportunities"
COMPANIES_DIR = "companies"
MANIFEST_FILE = "manifest.json"

# Dimensoes de OPPORTUNITY expostas em `coverage.dimensoes_desconhecidas`. O
# nome publico e o do campo do payload, nao o da coluna interna.
_OPPORTUNITY_DIMENSIONS: tuple[tuple[str, str], ...] = (
    ("objeto", "objeto_state"),
    ("valor", "valor_state"),
    ("modalidade", "modalidade_state"),
    ("local", "geo_state"),
    ("orgao", "orgao_state"),
    ("prazo", "deadline_state"),
)


class LiveIntelligenceExportError(RuntimeError):
    """Falha de export. Sempre fail-closed: nenhum arquivo e escrito."""


# --- leitura do snapshot selado --------------------------------------------


def _rows(cur: Any) -> list[dict[str, Any]]:
    if cur.description is None:
        return []
    cols = [d[0] for d in cur.description]
    return [dict(r) if isinstance(r, dict) else dict(zip(cols, r, strict=True)) for r in (cur.fetchall() or [])]


def _load_snapshot(conn: Any, snapshot_id: str) -> tuple[dict[str, Any], list[dict], list[dict], list[dict]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM public.confenge_live_intelligence_snapshots WHERE snapshot_id = %s",
            (snapshot_id,),
        )
        headers = _rows(cur)
        if not headers:
            raise LiveIntelligenceExportError(f"snapshot inexistente: {snapshot_id!r}")
        cur.execute(
            "SELECT * FROM public.confenge_live_intelligence_opportunities "
            "WHERE snapshot_id = %s ORDER BY opportunity_id",
            (snapshot_id,),
        )
        opportunity_rows = _rows(cur)
        cur.execute(
            "SELECT * FROM public.confenge_live_intelligence_companies WHERE snapshot_id = %s ORDER BY company_root8",
            (snapshot_id,),
        )
        company_rows = _rows(cur)
        cur.execute(
            "SELECT * FROM public.confenge_live_intelligence_fit "
            "WHERE snapshot_id = %s ORDER BY company_root8, opportunity_id",
            (snapshot_id,),
        )
        fit_rows = _rows(cur)
    return headers[0], opportunity_rows, company_rows, fit_rows


# --- serializacao ----------------------------------------------------------


def _decimal_str(value: Decimal | None) -> str | None:
    """Decimal como STRING decimal normalizada — nunca float.

    Mesma disciplina de ``schema._json_default``: um float no JSON publico
    reintroduziria erro de representacao num campo que o consumidor compara
    contra o documento de origem.
    """
    if value is None:
        return None
    return format(Decimal(str(value)).normalize(), "f")


def _iso_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _content_hash(payload: Mapping[str, Any]) -> str:
    """``live_hash`` do payload publico SEM ``content_hash``.

    Distinto de ``LiveOpportunity.content_hash()``/``LiveCompany.portfolio_hash()``,
    que sao hashes do payload INTERNO e incluem ``source_as_of``.
    """
    return live_hash({k: v for k, v in payload.items() if k != "content_hash"})


# --- projecao publica: opportunity -----------------------------------------


def _opportunity_unknown_dimensions(opportunity: LiveOpportunity) -> list[str]:
    return [name for name, attr in _OPPORTUNITY_DIMENSIONS if getattr(opportunity, attr) == UNKNOWN]


def _opportunity_epistemic_classes(opportunity: LiveOpportunity) -> dict[str, str]:
    """§A.3 — ``INFERENCE`` nunca e emitido: o motor nao infere."""
    unknown = policy.EPISTEMIC_UNKNOWN
    return {
        "objeto": policy.FACT if opportunity.objeto_state != UNKNOWN else unknown,
        # `value_band()` e classificacao deterministica sobre o valor declarado.
        "valor.faixa": policy.CALCULATION if opportunity.valor_state != UNKNOWN else unknown,
        "valor.estimado_brl": policy.FACT if opportunity.valor_state != UNKNOWN else unknown,
        "orgao": policy.FACT if opportunity.orgao_state != UNKNOWN else unknown,
        "local": policy.FACT if opportunity.geo_state != UNKNOWN else unknown,
        # Comparacao deterministica de `data_encerramento` com `as_of`.
        "prazo.status": policy.CALCULATION if opportunity.deadline_state != UNKNOWN else unknown,
        "prazo.data_encerramento": policy.FACT if opportunity.data_encerramento is not None else unknown,
        "prazo.data_publicacao": policy.FACT if opportunity.data_publicacao is not None else unknown,
    }


def _opportunity_payload(
    opportunity: LiveOpportunity,
    *,
    as_of: date,
    freshness: dict[str, Any],
    data_state: str,
    limitations: Sequence[str],
) -> dict[str, Any]:
    orgao_cnpj = None if policy.SUPPRESS_ORGAO_CNPJ else opportunity.orgao_cnpj
    payload: dict[str, Any] = {
        "schema": policy.OPPORTUNITY_SCHEMA,
        "opportunity_id": opportunity.opportunity_id,
        "objeto": opportunity.objeto if opportunity.objeto_state != UNKNOWN else None,
        "valor": {
            "faixa": opportunity.valor_band,
            "estimado_brl": _decimal_str(opportunity.valor_estimado_brl),
            "estado": opportunity.valor_state,
        },
        # `orgao.cnpj` permanece CRU por decisao do contrato: `live_opportunity`
        # nao tem bloco `identity` e CNPJ de orgao publico licitante e dado
        # oficial publicado na fonte (AC6).
        "orgao": {
            "nome": opportunity.orgao_nome,
            "cnpj": orgao_cnpj,
            "estado": opportunity.orgao_state,
        },
        "local": {
            "uf": opportunity.uf,
            "municipio": opportunity.municipio,
            "codigo_ibge": opportunity.codigo_ibge,
            "estado": opportunity.geo_state,
        },
        "prazo": {
            "status": policy.prazo_status_for(opportunity.deadline_state),
            "data_encerramento": _iso_date(opportunity.data_encerramento),
            "data_publicacao": _iso_date(opportunity.data_publicacao),
        },
        "fonte": {
            "sistema": opportunity.source,
            "source_id": opportunity.source_id,
            "link_edital": opportunity.link_edital,
        },
        "as_of": as_of.isoformat(),
        "freshness": freshness,
        "coverage": {
            "row_completeness_state": opportunity.row_completeness_state,
            "dimensoes_desconhecidas": _opportunity_unknown_dimensions(opportunity),
        },
        "limitations": list(limitations),
        "epistemic_classes": _opportunity_epistemic_classes(opportunity),
        "data_state": data_state,
        "reason_codes": sorted(set(opportunity.reason_codes) | set(opportunity.exclusion_reason_codes)),
    }
    payload["content_hash"] = _content_hash(payload)
    return payload


# --- projecao publica: company ---------------------------------------------


def _company_buyers(company: LiveCompany) -> tuple[list[dict[str, str]], int]:
    """``compradores = [{buyer_digest}]`` — NUNCA CNPJ cru (AC6).

    Comprador cujo CNPJ nao reduz a 14 digitos e **omitido** e contado. Emitir
    ``buyer_digest: ""`` seria descarte silencioso; ``producer.py`` extrai
    ``buyer_cnpj`` sem validar comprimento, logo o caminho e real.
    """
    digests: list[str] = []
    unhashable = 0
    for raw in company.observed_buyer_cnpjs:
        digest = cnpj_digest(raw)
        if digest is None:
            unhashable += 1
            continue
        digests.append(digest)
    return [{"buyer_digest": d} for d in sorted(set(digests))], unhashable


def _company_payload(
    company: LiveCompany,
    *,
    company_digest: str,
    fits: Sequence[LiveCompanyOpportunityFit],
    as_of: date,
    freshness: dict[str, Any],
    data_state: str,
    limitations: Sequence[str],
    extra_reason_codes: Sequence[str],
) -> dict[str, Any]:
    ordered = sorted(fits, key=ordering_key)
    aderentes = [
        {
            "opportunity_id": f.opportunity_id,
            "matched_dimensions": list(f.matched_dimensions),
            "unknown_dimensions": list(f.unknown_dimensions),
            "reason_codes": list(f.reason_codes),
        }
        for f in ordered
        if f.fit_state == FIT_OBSERVED
    ]
    gaps = [
        {
            "opportunity_id": f.opportunity_id,
            "dimensoes_sem_correspondencia": [
                name
                for name in (
                    "dim_object",
                    "dim_value_band",
                    "dim_geography",
                    "dim_comparable_buyer",
                    "dim_recency",
                )
                if getattr(f, name) == NO_MATCH
            ],
        }
        for f in ordered
    ]
    gaps = [g for g in gaps if g["dimensoes_sem_correspondencia"]]

    unknowns = sorted(
        {d for f in ordered for d in f.unknown_dimensions} | set(company.reason_codes),
    )
    compradores, _unhashable = _company_buyers(company)

    payload: dict[str, Any] = {
        "schema": policy.COMPANY_SCHEMA,
        "company_digest": company_digest,
        # SEM `company_root8`, SEM `company_ref` (AC6/AC8).
        "perfil": {
            "razao_social": company.razao_social,
            "contratos_observados": len(company.portfolio_contract_ids),
            "contratacao_mais_recente": _iso_date(company.most_recent_contracting_date),
        },
        "categorias": list(company.observed_objects),
        "faixas": list(company.observed_value_bands),
        "geografias": list(company.observed_ufs),
        "compradores": compradores,
        "oportunidades_aderentes": aderentes,
        "gaps": gaps,
        "unknowns": unknowns,
        "as_of": as_of.isoformat(),
        "freshness": freshness,
        "coverage": {
            "row_completeness_state": company.row_completeness_state,
            "dimensoes_desconhecidas": sorted({d for f in ordered for d in f.unknown_dimensions}),
        },
        "limitations": list(limitations),
        "epistemic_classes": {
            # Digest de uma observacao continua sendo a observacao.
            "perfil": policy.FACT,
            "categorias": policy.FACT,
            "faixas": policy.FACT,
            "geografias": policy.FACT,
            "compradores": policy.FACT,
            # Comparacao deterministica de 5 dimensoes (`fit.py`).
            "oportunidades_aderentes": policy.CALCULATION,
            "gaps": policy.CALCULATION,
            "unknowns": policy.EPISTEMIC_UNKNOWN,
        },
        "data_state": data_state,
        "reason_codes": sorted(
            set(company.reason_codes) | set(company.exclusion_reason_codes) | set(extra_reason_codes)
        ),
    }
    payload["content_hash"] = _content_hash(payload)
    return payload


# --- montagem do bundle ----------------------------------------------------


def build_bundle(
    conn: Any,
    snapshot_id: str,
    *,
    catalog_mode: str = policy.DEFAULT_CATALOG_MODE,
) -> dict[str, Any]:
    """Monta o bundle INTEIRO em memoria. Nao escreve nada.

    Devolve ``{"manifest": {...}, "files": {caminho_relativo: payload}}``.
    Separado de :func:`export_bundle` para que o fail-closed seja estrutural: se
    qualquer invariante quebrar aqui, nenhum ``write`` chegou a acontecer.

    ``catalog_mode`` (REQ-001, adjudicacao do @architect) e a PROVENIENCIA
    reivindicada pelo invocador, e o default e ``"fixture"``. O contrato so
    autoriza ``official_live`` *"when producers are live official artifacts and
    claimed_live is true"* — reivindicacao explicita, nunca default. Quem exporta
    de um banco de teste/seed e nao passa nada recebe um bundle **rotulado
    fixture**, que o consumidor recusa por ``producer_status_not_official_live``.

    `catalog_mode` NAO e funcao do ``state`` do snapshot: proveniencia e
    completude sao eixos independentes (mesma doutrina do ``freshness.state`` vs
    ``data_state`` na emenda do AC3). ``official_live: true`` com
    ``data_state: DATA_REJECT`` e coerente — produtor real, nada publicavel.
    """
    if catalog_mode not in policy.CATALOG_MODES:
        raise LiveIntelligenceExportError(
            f"catalog_mode invalido: {catalog_mode!r} — aceitos: {list(policy.CATALOG_MODES)}"
        )
    official_live = catalog_mode == policy.CATALOG_MODE_OFFICIAL_LIVE

    header, opportunity_rows, company_rows, fit_rows = _load_snapshot(conn, snapshot_id)

    state = str(header["state"])
    try:
        data_state = policy.data_state_for(state)
    except KeyError as exc:
        raise LiveIntelligenceExportError(
            f"snapshot {snapshot_id!r} em estado nao exportavel ({state!r}) — nenhum arquivo escrito (AC1)"
        ) from exc

    as_of = header["as_of_date"]
    if isinstance(as_of, datetime):
        as_of = as_of.date()
    if not isinstance(as_of, date):
        raise LiveIntelligenceExportError("as_of_date ausente ou nao e data civil")

    generated_at_dt = header.get("cutoff_at")

    opportunities = [_rebuild_opportunity(r) for r in opportunity_rows]
    companies = [_rebuild_company(r) for r in company_rows]
    fits = [_rebuild_fit(r) for r in fit_rows]

    emitted_opportunities = [o for o in opportunities if o.row_completeness_state == ROW_COMPLETE]
    emitted_companies = [c for c in companies if c.row_completeness_state == ROW_COMPLETE]

    if state == SNAPSHOT_BLOCKED:
        # AC1 — BLOCKED emite APENAS o manifest. Nenhum payload, logo nenhum
        # diretorio `opportunities/`/`companies/`.
        emitted_opportunities = []
        emitted_companies = []

    # --- freshness (emenda do AC3): min sobre TODOS os payloads emitidos ----
    watermarks = [o.source_as_of for o in emitted_opportunities] + [c.source_as_of for c in emitted_companies]
    no_payload_emitted = not watermarks
    if no_payload_emitted:
        # UM unico tratamento para TODO snapshot exportavel sem payload emitido —
        # `BLOCKED` (que por AC1 nunca emite payload) e tambem o universo
        # legitimamente VAZIO em `READY`/`PARTIAL`.
        #
        # Por que NAO abortar aqui. O ramo (1) da emenda do AC3 nomeia tres
        # condicoes de aborto — `generated_at` ausente, `source_as_of` ausente,
        # `tzinfo` ausente — e o racional e explicito: `source_as_of` e
        # `TIMESTAMPTZ NOT NULL` e nao-Optional na dataclass, logo ausencia e
        # **corrupcao de snapshot**. Universo vazio nao e corrupcao: e um
        # snapshot selado valido. E o AC1 nao abre excecao para catalogo vazio —
        # `manifest.index` com zero arquivo satisfaz "nem mais, nem menos".
        # Recusar o export aqui seria substituir a formula pinada por juizo
        # proprio, a mesma classe de desvio que a emenda ja proibiu no ramo de
        # delta negativo.
        #
        # Sem payload nao existe `min(source_as_of)`. O bloco passa a refletir o
        # corte do proprio snapshot, e a substituicao e DECLARADA em
        # `limitations` (`LIMITATION_NO_PAYLOAD_EMITTED`) — nenhum reason code
        # novo e inventado.
        source_as_of_dt = generated_at_dt
    else:
        source_as_of_dt = min(watermarks)

    try:
        freshness = policy.build_freshness(generated_at_dt, source_as_of_dt)
    except policy.FreshnessInvariantError as exc:
        raise LiveIntelligenceExportError(
            f"invariante de freshness violada em {snapshot_id!r}: {exc} — nenhum arquivo escrito (AC3)"
        ) from exc

    # --- limitations comuns -------------------------------------------------
    base_limitations: list[str] = [
        policy.DISCLAIMER_PT,
        policy.LIMITATION_SUSPENSA_ABSENT,
        policy.LIMITATION_SOURCE_SCOPE,
        policy.LIMITATION_UNKNOWN_IS_NOT_ZERO,
    ]
    base_limitations.extend(policy.freshness_limitations(freshness))
    opportunity_limitations = [*base_limitations, policy.LIMITATION_VALUE_SEMANTICS]
    manifest_limitations = list(base_limitations)
    if no_payload_emitted:
        manifest_limitations.append(policy.LIMITATION_NO_PAYLOAD_EMITTED)
    if state != "READY_CANONICAL":
        manifest_limitations.append(
            f"O snapshot fechou em {state}: parte das linhas observadas não foi emitida como arquivo."
        )

    # --- arquivos -----------------------------------------------------------
    files: dict[str, dict[str, Any]] = {}
    index_opportunities: list[dict[str, Any]] = []
    for opportunity in sorted(emitted_opportunities, key=lambda o: o.opportunity_id):
        payload = _opportunity_payload(
            opportunity,
            as_of=as_of,
            freshness=freshness,
            data_state=data_state,
            limitations=opportunity_limitations,
        )
        rel = f"{OPPORTUNITIES_DIR}/{opportunity.opportunity_id}.json"
        files[rel] = payload
        index_opportunities.append(
            {
                "opportunity_id": opportunity.opportunity_id,
                "file": rel,
                "schema": policy.OPPORTUNITY_SCHEMA,
                "content_hash": payload["content_hash"],
            }
        )

    fits_by_root: dict[str, list[LiveCompanyOpportunityFit]] = {}
    for fit in fits:
        fits_by_root.setdefault(fit.company_root8, []).append(fit)

    index_companies: list[dict[str, Any]] = []
    buyers_unhashable = 0
    establishment_digests = 0
    manifest_extra_codes: set[str] = set()

    for company in sorted(emitted_companies, key=lambda c: c.company_root8):
        digests = sorted({d for d in (cnpj_digest(c) for c in company.observed_establishment_cnpjs) if d})
        if not digests:
            # AC8 — invisibilidade silenciosa proibida: a company seria contada
            # como observada e nao teria arquivo nenhum no bundle.
            raise LiveIntelligenceExportError(
                f"company ROW_COMPLETE sem nenhum company_digest de estabelecimento "
                f"(root8={company.company_root8!r}) — nenhum arquivo escrito (AC8/§B.3)"
            )
        _compradores, unhashable = _company_buyers(company)
        buyers_unhashable += unhashable
        company_codes: list[str] = []
        if unhashable:
            company_codes.append(policy.REASON_BUYER_CNPJ_NOT_HASHABLE)
            manifest_extra_codes.add(policy.REASON_BUYER_CNPJ_NOT_HASHABLE)
        establishment_digests += len(digests)
        for digest in digests:
            payload = _company_payload(
                company,
                company_digest=digest,
                fits=fits_by_root.get(company.company_root8, []),
                as_of=as_of,
                freshness=freshness,
                data_state=data_state,
                limitations=base_limitations,
                extra_reason_codes=company_codes,
            )
            rel = f"{COMPANIES_DIR}/{digest}.json"
            files[rel] = payload
            index_companies.append(
                {
                    "company_digest": digest,
                    "file": rel,
                    "schema": policy.COMPANY_SCHEMA,
                    "content_hash": payload["content_hash"],
                }
            )

    # `establishment_cnpj_not_observed` — company observada (nao emitida por
    # exclusao de linha) para a qual nenhum CNPJ14 de estabelecimento apareceu.
    for company in companies:
        if company.row_completeness_state != ROW_COMPLETE and not company.observed_establishment_cnpjs:
            manifest_extra_codes.add(policy.REASON_ESTABLISHMENT_CNPJ_NOT_OBSERVED)

    excluded_opportunities = [o for o in opportunities if o.row_completeness_state != ROW_COMPLETE]
    excluded_companies = [c for c in companies if c.row_completeness_state != ROW_COMPLETE]

    aggregated_codes: set[str] = set(manifest_extra_codes)
    aggregated_codes |= set(policy.freshness_reason_codes(freshness))
    for opportunity in opportunities:
        aggregated_codes |= set(opportunity.reason_codes) | set(opportunity.exclusion_reason_codes)
    for company in companies:
        aggregated_codes |= set(company.reason_codes) | set(company.exclusion_reason_codes)
    blockers = header.get("blockers") or []
    aggregated_codes |= {str(b) for b in blockers}

    manifest: dict[str, Any] = {
        # AC1 — a chave de envelope chama-se `schema`. `contract` NAO e emitido,
        # sem alias: alias e um segundo lugar para divergir, e `schema_absent`
        # esta em `reject_reason_codes` do contrato.
        "schema": policy.CONTRACT_SCHEMA,
        "contract_version": policy.CONTRACT_VERSION,
        # REQ-001 — proveniencia REIVINDICADA, nunca literal. Os tres campos sao
        # derivados do mesmo `catalog_mode` para que nao exista um segundo lugar
        # onde a proposicao "este bundle e oficial ao vivo" possa divergir.
        "catalog_mode": catalog_mode,
        "official_live": official_live,
        "producer_status": policy.producer_status_for(catalog_mode),
        "as_of": as_of.isoformat(),
        "generated_at": freshness["generated_at"],
        "source_as_of": freshness["source_as_of"],
        "freshness": freshness,
        "data_state": data_state,
        "coverage": {
            "opportunities_observed": len(emitted_opportunities),
            "opportunities_excluded": len(excluded_opportunities),
            "companies_observed": len(emitted_companies),
            "companies_excluded": len(excluded_companies),
            "establishment_digests": establishment_digests,
            "buyers_unhashable": buyers_unhashable,
        },
        "limitations": manifest_limitations,
        "epistemic_classes": {
            "coverage": policy.FACT,
            "data_state": policy.CALCULATION,
            "freshness": policy.CALCULATION,
            "reason_codes": policy.FACT,
        },
        "reason_codes": sorted(aggregated_codes),
        "sources": [{"nome": policy.SOURCE_NAME, "as_of": freshness["source_as_of"]}],
        "index": {
            "opportunities": index_opportunities,
            "companies": index_companies,
        },
    }
    manifest["manifest_hash"] = live_hash({k: v for k, v in manifest.items() if k != "manifest_hash"})

    return {"manifest": manifest, "files": files}


def export_bundle(
    conn: Any,
    *,
    snapshot_id: str,
    out_dir: str | Path,
    catalog_mode: str = policy.DEFAULT_CATALOG_MODE,
) -> dict[str, Any]:
    """Monta e ESCREVE o bundle. Devolve o manifest emitido.

    A montagem inteira acontece antes do primeiro ``write`` — se qualquer
    invariante quebrar, nenhum arquivo existe no disco (AC1/AC3/AC8).

    ``catalog_mode`` propaga a proveniencia reivindicada (REQ-001). Default
    fail-closed: ``"fixture"``.
    """
    bundle = build_bundle(conn, snapshot_id, catalog_mode=catalog_mode)
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)

    for rel, payload in sorted(bundle["files"].items()):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(canonical_json(payload) + "\n", encoding="utf-8")

    manifest: dict[str, Any] = bundle["manifest"]
    (root / MANIFEST_FILE).write_text(canonical_json(manifest) + "\n", encoding="utf-8")
    return manifest


def load_bundle(out_dir: str | Path) -> dict[str, Any]:
    """Le o bundle DE DISCO (JSON serializado), para o verifier provar sobre ele."""
    root = Path(out_dir)
    manifest = json.loads((root / MANIFEST_FILE).read_text(encoding="utf-8"))
    files: dict[str, Any] = {}
    for sub in (OPPORTUNITIES_DIR, COMPANIES_DIR):
        directory = root / sub
        if not directory.is_dir():
            continue
        # rglob, nao glob: opportunity_id pode conter "/" (ex.: PNCP
        # "<cnpj>-<seq>/<ano>"), e o writer (linha ~475) cria subdiretorios
        # reais para esses IDs. glob("*.json") nao-recursivo os ignorava
        # silenciosamente, fazendo o verifier acusar AC1 falso-negativo contra
        # qualquer bundle com opportunity_id real (achado provando P0 com
        # dados de producao reais, nunca reproduzido pelos fixtures de teste).
        for path in sorted(directory.rglob("*.json")):
            rel_name = path.relative_to(directory).as_posix()
            files[f"{sub}/{rel_name}"] = json.loads(path.read_text(encoding="utf-8"))
    return {"manifest": manifest, "files": files}
