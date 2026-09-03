"""Verifier (nucleo) — re-derivacao fail-closed de hashes e whitelist de PII.

Duas garantias:

1. **AC9 — fail-closed.** Todo hash persistido (``universe``, ``policy``,
   ``schema``, ``data``, ``fit``, ``content``, alem dos hashes por linha) e
   RE-DERIVADO a partir do conteudo gravado. Qualquer divergencia levanta
   ``LiveIntelligenceVerificationError``. Nao existe retorno de sucesso parcial
   nem degradacao silenciosa.
2. **AC10 — zero PII por WHITELIST.** O key-set de cada payload emitido precisa
   ser SUBCONJUNTO do schema declarado em ``schema.py``. Whitelist, nao
   blacklist: uma chave nova como ``responsavel_nome`` e rejeitada por nao estar
   declarada, mesmo sem bater em nenhum termo de regex proibido.

O verifier NUNCA escreve. Ele apenas le ``confenge_live_intelligence_*``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from scripts.confenge_live_intelligence.contract_date_resolver import DATE_RESOLVER_VERSION
from scripts.confenge_live_intelligence.fit import derive_fit_state
from scripts.confenge_live_intelligence.producer import (
    content_hash_of,
    data_hash_of,
    fit_hash_of,
    normalize_source_as_of,
    universe_hash_of,
)
from scripts.confenge_live_intelligence.schema import (
    COMPANY_PAYLOAD_KEYS,
    FIT_PAYLOAD_KEYS,
    FORBIDDEN_PII_KEY_TERMS,
    OPPORTUNITY_PAYLOAD_KEYS,
    SNAPSHOT_BLOCKED,
    SNAPSHOT_PARTIAL,
    SNAPSHOT_READY,
    LiveCompany,
    LiveCompanyOpportunityFit,
    LiveIntelligenceSchemaError,
    LiveOpportunity,
    assert_payload_within_schema,
    policy_hash,
    schema_hash,
)


class LiveIntelligenceVerificationError(RuntimeError):
    """Divergencia de verificacao. Sempre fatal — nunca sucesso parcial."""


@dataclass(frozen=True)
class VerificationReport:
    snapshot_id: str
    state: str
    checks: tuple[str, ...]
    verified_opportunities: int
    verified_companies: int
    verified_fits: int

    @property
    def ok(self) -> bool:
        return True  # a instancia so existe quando tudo passou (fail-closed)


def _rows(cur: Any) -> list[dict[str, Any]]:
    if cur.description is None:
        return []
    cols = [d[0] for d in cur.description]
    return [dict(r) if isinstance(r, dict) else dict(zip(cols, r, strict=True)) for r in (cur.fetchall() or [])]


def _fail(message: str) -> None:
    raise LiveIntelligenceVerificationError(message)


def assert_no_undeclared_keys(payload: Mapping[str, Any], *, kind: str) -> None:
    """AC10 — whitelist de key-set por tipo de objeto emitido."""
    allowed = {
        "opportunity": OPPORTUNITY_PAYLOAD_KEYS,
        "company": COMPANY_PAYLOAD_KEYS,
        "fit": FIT_PAYLOAD_KEYS,
    }.get(kind)
    if allowed is None:
        _fail(f"tipo de payload desconhecido: {kind!r}")
        return
    try:
        assert_payload_within_schema(dict(payload), allowed, label=f"payload {kind}")
    except LiveIntelligenceSchemaError as exc:
        raise LiveIntelligenceVerificationError(str(exc)) from exc
    # Trava redundante de revisao: nenhum termo de contato pode existir como
    # chave, ainda que alguem o declarasse no schema por engano.
    offending = sorted(key for key in payload if any(term in str(key).lower() for term in FORBIDDEN_PII_KEY_TERMS))
    if offending:
        _fail(f"payload {kind} contem chave de contato/PII: {offending}")


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(str(v) for v in value)


def _rebuild_opportunity(row: Mapping[str, Any]) -> LiveOpportunity:
    """Reconstroi a OPPORTUNITY persistida para re-derivar o hash de linha.

    ``source_as_of`` passa por ``normalize_source_as_of`` (→ UTC) porque a coluna
    e ``TIMESTAMPTZ`` e o driver devolve o INSTANTE no fuso da SESSAO corrente.
    ``live_hash`` serializa ``datetime`` por ``isoformat()``, logo o mesmo
    instante lido sob ``CUTOFF_TIMEZONE`` e sob UTC dava hashes diferentes e o
    verifier falhava fechado sobre um snapshot intacto — bastava verificar na
    MESMA conexao que acabou de fazer o build (que pina o fuso). Mesma classe de
    REL-001, latente no caminho de verify; a normalizacao dos dois lados torna o
    hash funcao do instante, nao do fuso da sessao.
    """
    valor = row.get("valor_estimado_brl")
    return LiveOpportunity(
        opportunity_id=str(row["opportunity_id"]),
        source=str(row["source"]),
        source_as_of=normalize_source_as_of(row["source_as_of"]),
        objeto=row.get("objeto"),
        objeto_state=str(row["objeto_state"]),
        valor_estimado_brl=Decimal(str(valor)) if valor is not None else None,
        valor_state=str(row["valor_state"]),
        valor_band=row.get("valor_band"),
        modalidade_id=row.get("modalidade_id"),
        modalidade=row.get("modalidade"),
        modalidade_state=str(row["modalidade_state"]),
        uf=row.get("uf"),
        municipio=row.get("municipio"),
        codigo_ibge=row.get("codigo_ibge"),
        geo_state=str(row["geo_state"]),
        orgao_cnpj=row.get("orgao_cnpj"),
        orgao_nome=row.get("orgao_nome"),
        orgao_state=str(row["orgao_state"]),
        data_publicacao=row.get("data_publicacao"),
        data_encerramento=row.get("data_encerramento"),
        deadline_state=str(row["deadline_state"]),
        link_edital=row.get("link_edital"),
        source_id=row.get("source_id"),
        row_completeness_state=str(row["row_completeness_state"]),
        exclusion_reason_codes=_as_tuple(row.get("exclusion_reason_codes")),
        reason_codes=_as_tuple(row.get("reason_codes")),
    )


def _rebuild_company(row: Mapping[str, Any]) -> LiveCompany:
    return LiveCompany(
        company_root8=str(row["company_root8"]),
        # Mesma normalizacao de `_rebuild_opportunity` — ver docstring de la.
        source_as_of=normalize_source_as_of(row["source_as_of"]),
        date_resolver_version=str(row["date_resolver_version"]),
        razao_social=row.get("razao_social"),
        portfolio_contract_ids=_as_tuple(row.get("portfolio_contract_ids")),
        observed_objects=_as_tuple(row.get("observed_objects")),
        observed_value_bands=_as_tuple(row.get("observed_value_bands")),
        observed_ufs=_as_tuple(row.get("observed_ufs")),
        observed_buyer_cnpjs=_as_tuple(row.get("observed_buyer_cnpjs")),
        most_recent_contracting_date=row.get("most_recent_contracting_date"),
        contracting_date_state=str(row["contracting_date_state"]),
        row_completeness_state=str(row["row_completeness_state"]),
        exclusion_reason_codes=_as_tuple(row.get("exclusion_reason_codes")),
        reason_codes=_as_tuple(row.get("reason_codes")),
    )


def _rebuild_fit(row: Mapping[str, Any]) -> LiveCompanyOpportunityFit:
    return LiveCompanyOpportunityFit(
        company_root8=str(row["company_root8"]),
        opportunity_id=str(row["opportunity_id"]),
        dim_object=str(row["dim_object"]),
        dim_value_band=str(row["dim_value_band"]),
        dim_geography=str(row["dim_geography"]),
        dim_comparable_buyer=str(row["dim_comparable_buyer"]),
        dim_recency=str(row["dim_recency"]),
        fit_state=str(row["fit_state"]),
        matched_dimensions=_as_tuple(row.get("matched_dimensions")),
        unknown_dimensions=_as_tuple(row.get("unknown_dimensions")),
        reason_codes=_as_tuple(row.get("reason_codes")),
        evidence_refs=dict(row.get("evidence_refs") or {}),
    )


def verify_snapshot(conn: Any, snapshot_id: str) -> VerificationReport:
    """Re-deriva todos os hashes do snapshot persistido. Falha fechado."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM public.confenge_live_intelligence_snapshots WHERE snapshot_id = %s",
            (snapshot_id,),
        )
        headers = _rows(cur)
        if not headers:
            _fail(f"snapshot inexistente: {snapshot_id!r}")
        header = headers[0]

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

    state = str(header["state"])
    checks: list[str] = []

    if state == SNAPSHOT_BLOCKED:
        if not header.get("blockers"):
            _fail("snapshot BLOCKED sem blockers declarados")
        return VerificationReport(snapshot_id, state, ("blocked_has_blockers",), 0, 0, 0)

    if state not in (SNAPSHOT_READY, SNAPSHOT_PARTIAL):
        _fail(f"estado nao verificavel: {state!r} (esperado READY_CANONICAL ou PARTIAL)")

    if header.get("closed_at") is None or header.get("content_hash") is None:
        _fail(f"estado terminal {state} sem closed_at/content_hash: snapshot nao selado")
    if header.get("blockers"):
        _fail(f"{state} com blockers e contradicao estrutural: {header.get('blockers')!r}")
    checks.append("terminal_state_sealed")

    opportunities = [_rebuild_opportunity(r) for r in opportunity_rows]
    companies = [_rebuild_company(r) for r in company_rows]
    fits = [_rebuild_fit(r) for r in fit_rows]

    for obj, row, kind, column in (
        *[(o, r, "opportunity", "opportunity_hash") for o, r in zip(opportunities, opportunity_rows, strict=True)],
        *[(c, r, "company", "portfolio_hash") for c, r in zip(companies, company_rows, strict=True)],
        *[(f, r, "fit", "fit_hash") for f, r in zip(fits, fit_rows, strict=True)],
    ):
        payload = obj.as_payload()
        assert_no_undeclared_keys(payload, kind=kind)
        recomputed = {
            "opportunity": lambda: obj.content_hash(),
            "company": lambda: obj.portfolio_hash(),
            "fit": lambda: obj.fit_hash(),
        }[kind]()
        if recomputed != str(row[column]):
            _fail(f"hash de linha divergente ({kind}, {column}): persistido={row[column]} rederivado={recomputed}")
    checks.append("row_hashes_rederived")
    checks.append("payload_keyset_whitelisted")

    for fit in fits:
        derived = derive_fit_state(
            {
                "dim_object": fit.dim_object,
                "dim_value_band": fit.dim_value_band,
                "dim_geography": fit.dim_geography,
                "dim_comparable_buyer": fit.dim_comparable_buyer,
                "dim_recency": fit.dim_recency,
            }
        )
        if derived != fit.fit_state:
            _fail(
                f"fit_state persistido ({fit.fit_state}) diverge da derivacao ({derived}) "
                f"para {fit.company_root8}/{fit.opportunity_id}"
            )
    checks.append("fit_state_derivation")

    as_of = header["as_of_date"]
    if isinstance(as_of, datetime):
        as_of = as_of.date()
    if not isinstance(as_of, date):
        _fail("as_of_date ausente ou nao e data civil")

    expected = {
        "universe_hash": universe_hash_of(opportunities, companies, as_of=as_of),
        "policy_hash": policy_hash(
            date_resolver_version=str(header.get("date_resolver_version") or DATE_RESOLVER_VERSION)
        ),
        "schema_hash": schema_hash(),
        "data_hash": data_hash_of(opportunities, companies),
        "fit_hash": fit_hash_of(fits),
    }
    for column, value in expected.items():
        if str(header[column]) != value:
            _fail(f"{column} divergente: persistido={header[column]} rederivado={value}")
    checks.append("aggregate_hashes_rederived")

    content = content_hash_of(
        universe=expected["universe_hash"],
        policy=expected["policy_hash"],
        schema=expected["schema_hash"],
        data=expected["data_hash"],
        fits=expected["fit_hash"],
    )
    if content != str(header["content_hash"]):
        _fail(f"content_hash divergente: persistido={header['content_hash']} rederivado={content}")
    checks.append("content_hash_rederived")

    excluded_opportunities = sum(1 for o in opportunities if o.row_completeness_state != "COMPLETE")
    excluded_companies = sum(1 for c in companies if c.row_completeness_state != "COMPLETE")
    if excluded_opportunities != int(header["excluded_opportunity_count"]):
        _fail("excluded_opportunity_count nao bate com as linhas excluidas persistidas")
    if excluded_companies != int(header["excluded_company_count"]):
        _fail("excluded_company_count nao bate com as linhas excluidas persistidas")
    if state == SNAPSHOT_READY and (excluded_opportunities or excluded_companies):
        _fail("READY_CANONICAL com linha excluida e contradicao estrutural")
    if state == SNAPSHOT_PARTIAL and not (excluded_opportunities or excluded_companies):
        _fail("PARTIAL sem nenhuma linha excluida e contradicao estrutural")
    checks.append("exclusion_counts_reconciled")

    return VerificationReport(
        snapshot_id=snapshot_id,
        state=state,
        checks=tuple(checks),
        verified_opportunities=len(opportunities),
        verified_companies=len(companies),
        verified_fits=len(fits),
    )


def verify_payload_keysets(payloads: Sequence[tuple[str, Mapping[str, Any]]]) -> None:
    """Helper de gate: valida uma sequencia de ``(kind, payload)``."""
    for kind, payload in payloads:
        assert_no_undeclared_keys(payload, kind=kind)
