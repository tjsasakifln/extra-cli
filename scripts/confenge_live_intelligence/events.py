"""LI-W2 §C — eventos idempotentes por diff entre snapshots selados.

A tabela ``confenge_live_intelligence_events`` nasce vazia na migration 104
(*"LI-7 popula"*). Este modulo e o LI-7.

**A identidade e a TRANSICAO, nao o estado de destino.**

    event_id = live_hash({event_type, subject_key, prev_semantic_hash, semantic_hash})

Exatamente a tupla de ``uq_live_intel_event_transition`` (``104:471-472``).
``snapshot_id``/``prev_snapshot_id``/``source_as_of``/``created_at`` ficam **fora**
do material do hash: sao linhagem, e inclui-los faria todo replay gerar eventos
novos.

**Projecao semantica, nao ``content_hash()``.** ``source_as_of`` esta em
``OPPORTUNITY_PAYLOAD_KEYS``, logo ``LiveOpportunity.content_hash()`` muda a cada
tick do watermark. Reusa-lo regeneraria eventos exatamente no churn que esta
story proibe. Cada tipo tem projecao explicita (``OPPORTUNITY_CORE``,
``DEADLINE_CORE``, ``FIT_CORE``), e ``semantic_hash = live_hash(projecao)``.

Fora de ``OPPORTUNITY_CORE``, deliberadamente: ``source_as_of`` (churn puro),
``valor_estimado_brl`` (centavos oscilam — a **faixa** e o fato material),
``link_edital``, ``reason_codes`` e todos os hashes.

``COMPANY_PORTFOLIO_CHANGED`` existe no CHECK da 104 e **nao e emitido nesta
story**: o criterio de materialidade depende do ciclo de crawl outbound, fora de
escopo. Downgrade de fit (``OBSERVED_FIT`` → outro estado) tambem nao emite —
declarado, nao esquecido.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from scripts.confenge_live_intelligence.identity import company_ref_from_root8
from scripts.confenge_live_intelligence.schema import (
    FIT_OBSERVED,
    ROW_COMPLETE,
    SNAPSHOT_PARTIAL,
    SNAPSHOT_READY,
    WRITE_TARGET_ORDER,
    LiveCompanyOpportunityFit,
    LiveOpportunity,
    assert_write_target,
    live_hash,
)

EVENT_NEW_OPPORTUNITY: Final[str] = "NEW_OPPORTUNITY"
EVENT_OPPORTUNITY_CHANGED: Final[str] = "OPPORTUNITY_CHANGED"
EVENT_DEADLINE_CHANGED: Final[str] = "DEADLINE_CHANGED"
EVENT_FIT_BECAME_RELEVANT: Final[str] = "FIT_BECAME_RELEVANT"
# Existe no CHECK da 104; NAO emitido nesta story (ver docstring do modulo).
EVENT_COMPANY_PORTFOLIO_CHANGED: Final[str] = "COMPANY_PORTFOLIO_CHANGED"

EMITTED_EVENT_TYPES: Final[tuple[str, ...]] = (
    EVENT_NEW_OPPORTUNITY,
    EVENT_OPPORTUNITY_CHANGED,
    EVENT_DEADLINE_CHANGED,
    EVENT_FIT_BECAME_RELEVANT,
)

# AR-2/ADR-040 — o nome da tabela e DERIVADO de `WRITE_TARGET_ORDER`, a unica
# enumeracao literal de alvos de escrita do pacote. Um literal proprio aqui seria
# uma segunda allowlist, exatamente o defeito que `schema.py:40-46` rejeitou.
# `.index()` falha ruidosamente se o alvo sair da allowlist.
EVENTS_TABLE: Final[str] = WRITE_TARGET_ORDER[WRITE_TARGET_ORDER.index("confenge_live_intelligence_events")]

BOOTSTRAP_PREV_HASH: Final[str] = ""

# Campos de `OPPORTUNITY_CORE` (§C.2), como lista literal UNICA. `orgao_cnpj` e
# usado CRU aqui porque esta e projecao INTERNA: alimenta `semantic_hash` e nunca
# e serializada em payload publico.
OPPORTUNITY_CORE_FIELDS: Final[tuple[str, ...]] = (
    "opportunity_id",
    "objeto",
    "objeto_state",
    "valor_band",
    "valor_state",
    "modalidade_id",
    "modalidade_state",
    "uf",
    "municipio",
    "codigo_ibge",
    "geo_state",
    "orgao_cnpj",
    "orgao_state",
    "row_completeness_state",
)
DEADLINE_CORE_FIELDS: Final[tuple[str, ...]] = (
    "opportunity_id",
    "data_encerramento",
    "deadline_state",
)


class LiveIntelligenceEventsError(RuntimeError):
    """Falha na geracao/persistencia de eventos. Fail-closed."""


@dataclass(frozen=True)
class LiveEvent:
    event_type: str
    subject_key: str
    prev_semantic_hash: str
    semantic_hash: str
    source_as_of: datetime
    reason_codes: tuple[str, ...] = ()

    @property
    def event_id(self) -> str:
        """``live_hash`` da TUPLA DE TRANSICAO — nada mais entra."""
        return live_hash(
            {
                "event_type": self.event_type,
                "subject_key": self.subject_key,
                "prev_semantic_hash": self.prev_semantic_hash,
                "semantic_hash": self.semantic_hash,
            }
        )

    @property
    def is_bootstrap(self) -> bool:
        return self.prev_semantic_hash == BOOTSTRAP_PREV_HASH


# --- projecoes semanticas ---------------------------------------------------


def opportunity_core(opportunity: LiveOpportunity) -> dict[str, Any]:
    return {field: getattr(opportunity, field) for field in OPPORTUNITY_CORE_FIELDS}


def deadline_core(opportunity: LiveOpportunity) -> dict[str, Any]:
    return {field: getattr(opportunity, field) for field in DEADLINE_CORE_FIELDS}


def fit_core(fit: LiveCompanyOpportunityFit) -> dict[str, Any]:
    """§C.2 — ``company_ref``, nao ``company_digest``.

    ``company_digest`` e 1:N por empresa (um por estabelecimento) e fragmentaria
    um evento logico em N linhas. ``company_ref`` e 1:1 com a empresa e a tabela
    de eventos ja tem ``REVOKE`` para leitores publicos (``104:475-476``).
    """
    return {
        "company_ref": company_ref_from_root8(fit.company_root8),
        "opportunity_id": fit.opportunity_id,
        "fit_state": fit.fit_state,
        "matched_dimensions": list(fit.matched_dimensions),
    }


def semantic_hash(projection: Mapping[str, Any]) -> str:
    return live_hash(dict(projection))


def opportunity_subject_key(opportunity_id: str) -> str:
    return f"opportunity:{opportunity_id}"


def company_subject_key(company_root8: str) -> str:
    return f"company:{company_ref_from_root8(company_root8)}"


# --- diff -------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotUniverse:
    """Universo selado de um snapshot, reduzido ao que o diff precisa."""

    opportunities: tuple[LiveOpportunity, ...] = ()
    fits: tuple[LiveCompanyOpportunityFit, ...] = ()


def diff_events(base: SnapshotUniverse | None, current: SnapshotUniverse) -> list[LiveEvent]:
    """Eventos da transicao ``base → current``. Deterministico e ordenado.

    ``base is None`` (nao existe snapshot selado anterior) equivale a base vazio:
    toda oportunidade e nova e emite ``NEW_OPPORTUNITY`` em bootstrap.
    """
    base_universe = base or SnapshotUniverse()
    base_opportunities = {o.opportunity_id: o for o in base_universe.opportunities}
    base_fits = {(f.company_root8, f.opportunity_id): f for f in base_universe.fits}

    events: list[LiveEvent] = []

    for opportunity in sorted(current.opportunities, key=lambda o: o.opportunity_id):
        subject = opportunity_subject_key(opportunity.opportunity_id)
        current_core = semantic_hash(opportunity_core(opportunity))
        previous = base_opportunities.get(opportunity.opportunity_id)

        if previous is None:
            # Bootstrap: satisfaz `chk_live_intel_event_bootstrap` (104:466-469).
            events.append(
                LiveEvent(
                    event_type=EVENT_NEW_OPPORTUNITY,
                    subject_key=subject,
                    prev_semantic_hash=BOOTSTRAP_PREV_HASH,
                    semantic_hash=current_core,
                    source_as_of=opportunity.source_as_of,
                )
            )
        else:
            previous_core = semantic_hash(opportunity_core(previous))
            if previous_core != current_core:
                events.append(
                    LiveEvent(
                        event_type=EVENT_OPPORTUNITY_CHANGED,
                        subject_key=subject,
                        prev_semantic_hash=previous_core,
                        semantic_hash=current_core,
                        source_as_of=opportunity.source_as_of,
                    )
                )
            # `DEADLINE_CORE` e SEPARADO de `OPPORTUNITY_CORE`: OPEN→CLOSED por
            # avanco do `as_of` e material e nao deve poluir o outro tipo.
            previous_deadline = semantic_hash(deadline_core(previous))
            current_deadline = semantic_hash(deadline_core(opportunity))
            if previous_deadline != current_deadline:
                events.append(
                    LiveEvent(
                        event_type=EVENT_DEADLINE_CHANGED,
                        subject_key=subject,
                        prev_semantic_hash=previous_deadline,
                        semantic_hash=current_deadline,
                        source_as_of=opportunity.source_as_of,
                    )
                )

    for fit in sorted(current.fits, key=lambda f: (f.company_root8, f.opportunity_id)):
        # Somente a transicao PARA `OBSERVED_FIT`. Comparado contra a CONSTANTE
        # `schema.FIT_OBSERVED`, nunca contra o literal "FIT_OBSERVED" (que nao
        # existe como valor em lugar nenhum).
        if fit.fit_state != FIT_OBSERVED:
            continue
        previous_fit = base_fits.get((fit.company_root8, fit.opportunity_id))
        if previous_fit is not None and previous_fit.fit_state == FIT_OBSERVED:
            continue  # ja era relevante: nao houve transicao
        current_core = semantic_hash(fit_core(fit))
        previous_core = BOOTSTRAP_PREV_HASH if previous_fit is None else semantic_hash(fit_core(previous_fit))
        if previous_core == current_core:
            continue  # `chk_live_intel_event_is_transition` — nunca emitir no-op
        events.append(
            LiveEvent(
                event_type=EVENT_FIT_BECAME_RELEVANT,
                subject_key=company_subject_key(fit.company_root8),
                prev_semantic_hash=previous_core,
                semantic_hash=current_core,
                source_as_of=_fit_source_as_of(fit, current),
            )
        )

    return events


def _fit_source_as_of(fit: LiveCompanyOpportunityFit, universe: SnapshotUniverse) -> datetime:
    """``source_as_of`` do evento de fit — coluna NOT NULL, fora do hash.

    Usa o watermark da propria oportunidade do fit; o universo do snapshot e
    selado com um unico watermark, entao qualquer payload serve. Fail-closed se
    nao houver nenhum: um evento sem watermark violaria a 104.
    """
    for opportunity in universe.opportunities:
        if opportunity.opportunity_id == fit.opportunity_id:
            return opportunity.source_as_of
    raise LiveIntelligenceEventsError(
        f"fit sem oportunidade correspondente no snapshot corrente: {fit.opportunity_id!r}"
    )


# --- IO ---------------------------------------------------------------------


def _rows(cur: Any) -> list[dict[str, Any]]:
    if cur.description is None:
        return []
    cols = [d[0] for d in cur.description]
    return [dict(r) if isinstance(r, dict) else dict(zip(cols, r, strict=True)) for r in (cur.fetchall() or [])]


def load_universe(conn: Any, snapshot_id: str) -> SnapshotUniverse:
    """Le o universo selado. Somente tabelas do motor — nenhuma view outbound."""
    from scripts.confenge_live_intelligence.verifier import _rebuild_fit, _rebuild_opportunity

    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM public.confenge_live_intelligence_opportunities "
            "WHERE snapshot_id = %s ORDER BY opportunity_id",
            (snapshot_id,),
        )
        opportunity_rows = _rows(cur)
        cur.execute(
            "SELECT * FROM public.confenge_live_intelligence_fit "
            "WHERE snapshot_id = %s ORDER BY company_root8, opportunity_id",
            (snapshot_id,),
        )
        fit_rows = _rows(cur)
    opportunities = tuple(
        o for o in (_rebuild_opportunity(r) for r in opportunity_rows) if o.row_completeness_state == ROW_COMPLETE
    )
    return SnapshotUniverse(opportunities=opportunities, fits=tuple(_rebuild_fit(r) for r in fit_rows))


def resolve_previous_snapshot_id(conn: Any, snapshot_id: str) -> str | None:
    """Snapshot selado imediatamente anterior (``READY_CANONICAL`` ou ``PARTIAL``).

    ``BLOCKED`` nunca e base: nao tem universo selado.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT closed_at FROM public.confenge_live_intelligence_snapshots WHERE snapshot_id = %s",
            (snapshot_id,),
        )
        current = _rows(cur)
        if not current or current[0].get("closed_at") is None:
            return None
        cur.execute(
            """
            SELECT snapshot_id FROM public.confenge_live_intelligence_snapshots
            WHERE state = ANY(%s) AND closed_at IS NOT NULL
              AND closed_at < %s AND snapshot_id <> %s
            ORDER BY closed_at DESC, snapshot_id DESC
            LIMIT 1
            """,
            ([SNAPSHOT_READY, SNAPSHOT_PARTIAL], current[0]["closed_at"], snapshot_id),
        )
        previous = _rows(cur)
    return str(previous[0]["snapshot_id"]) if previous else None


def persist_events(
    conn: Any,
    events: Sequence[LiveEvent],
    *,
    snapshot_id: str,
    prev_snapshot_id: str | None,
) -> int:
    """``ON CONFLICT (event_id) DO NOTHING`` — replay idempotente (AC9).

    Bootstrap (``prev_semantic_hash == ""``) grava ``prev_snapshot_id = NULL``,
    como exige ``chk_live_intel_event_bootstrap``, mesmo quando existe snapshot
    base: a oportunidade e nova, logo nao ha estado anterior a referenciar.
    """
    if not events:
        return 0
    inserted = 0
    with conn.cursor() as cur:
        for event in events:
            # AR-2: o nome da tabela e revalidado contra `ALLOWED_WRITE_TARGETS`
            # INLINE, no proprio slot de execucao — nao existe caminho em que a
            # allowlist deixe de ser consultada antes do DML.
            cur.execute(
                f"""
                INSERT INTO public.{assert_write_target(EVENTS_TABLE)} (
                    event_id, event_type, subject_key,
                    prev_semantic_hash, semantic_hash, reason_codes,
                    source_as_of, snapshot_id, prev_snapshot_id
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (event_id) DO NOTHING
                """,  # noqa: S608
                (
                    event.event_id,
                    event.event_type,
                    event.subject_key,
                    event.prev_semantic_hash,
                    event.semantic_hash,
                    list(event.reason_codes),
                    event.source_as_of,
                    snapshot_id,
                    None if event.is_bootstrap else prev_snapshot_id,
                ),
            )
            inserted += cur.rowcount or 0
    conn.commit()
    return inserted


def generate_events(
    conn: Any,
    *,
    snapshot_id: str,
    prev_snapshot_id: str | None = None,
    persist: bool = True,
) -> list[LiveEvent]:
    """Diff ``base → snapshot_id`` e (opcionalmente) persiste. Idempotente."""
    base_id = prev_snapshot_id if prev_snapshot_id is not None else resolve_previous_snapshot_id(conn, snapshot_id)
    base = load_universe(conn, base_id) if base_id else None
    current = load_universe(conn, snapshot_id)
    events = diff_events(base, current)
    if persist:
        persist_events(conn, events, snapshot_id=snapshot_id, prev_snapshot_id=base_id)
    return events
