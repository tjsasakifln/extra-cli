"""AC9 — ``event_id`` deterministico, replay idempotente e ausencia de churn.

O que este arquivo prova, em ordem de importancia:

1. ``event_id`` e funcao EXCLUSIVA da tupla de transicao — a mesma de
   ``uq_live_intel_event_transition`` (``104:471-472``). ``snapshot_id``,
   ``source_as_of`` e ``created_at`` fora.
2. Replay produz o MESMO conjunto de ``event_id`` byte a byte.
3. Churn de watermark/centavos/link/reason codes **nao** emite evento.
4. Bootstrap: ``prev_semantic_hash == ""`` e ``prev_snapshot_id IS NULL``.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from scripts.confenge_live_intelligence import events as li_events
from scripts.confenge_live_intelligence import schema as li_schema
from scripts.confenge_live_intelligence.fit import evaluate_fit

UTC_NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
AS_OF = date(2026, 9, 2)


def _opportunity(**overrides) -> li_schema.LiveOpportunity:
    base = dict(
        opportunity_id="LI-TEST-EV-1",
        source="pncp",
        source_as_of=UTC_NOW,
        objeto="Reforma de escola municipal com estrutura metalica",
        objeto_state=li_schema.OBSERVED,
        valor_estimado_brl=Decimal("250000.00"),
        valor_state=li_schema.OBSERVED,
        valor_band="100K_1M",
        modalidade="Pregao",
        modalidade_id="6",
        modalidade_state=li_schema.OBSERVED,
        uf="SC",
        municipio="Florianopolis",
        geo_state=li_schema.OBSERVED,
        orgao_cnpj="12345678000195",
        orgao_nome="Prefeitura",
        orgao_state=li_schema.OBSERVED,
        data_publicacao=date(2026, 8, 1),
        data_encerramento=date(2026, 10, 1),
        deadline_state=li_schema.DEADLINE_OPEN,
    )
    base.update(overrides)
    return li_schema.LiveOpportunity(**base)


def _company(**overrides) -> li_schema.LiveCompany:
    base = dict(
        company_root8="11222333",
        source_as_of=UTC_NOW,
        date_resolver_version="ca-v2-precedence/1.0",
        observed_objects=("Reforma de escola municipal com estrutura metalica",),
        observed_value_bands=("100K_1M",),
        observed_ufs=("SC",),
        observed_buyer_cnpjs=("12345678000195",),
        observed_establishment_cnpjs=("11222333000181",),
        most_recent_contracting_date=date(2026, 5, 1),
        contracting_date_state=li_schema.OBSERVED,
    )
    base.update(overrides)
    return li_schema.LiveCompany(**base)


def _universe(opportunities, companies=()) -> li_events.SnapshotUniverse:
    fits = tuple(evaluate_fit(c, o, as_of=AS_OF) for c in companies for o in opportunities)
    return li_events.SnapshotUniverse(opportunities=tuple(opportunities), fits=fits)


# --- event_id ---------------------------------------------------------------


def test_event_id_is_exactly_the_transition_tuple() -> None:
    """AC9 — sem ``snapshot_id``, sem ``source_as_of``, sem ``created_at``."""
    event = li_events.LiveEvent(
        event_type=li_events.EVENT_OPPORTUNITY_CHANGED,
        subject_key="opportunity:X",
        prev_semantic_hash="a" * 64,
        semantic_hash="b" * 64,
        source_as_of=UTC_NOW,
    )
    expected = li_schema.live_hash(
        {
            "event_type": li_events.EVENT_OPPORTUNITY_CHANGED,
            "subject_key": "opportunity:X",
            "prev_semantic_hash": "a" * 64,
            "semantic_hash": "b" * 64,
        }
    )
    assert event.event_id == expected
    # Trocar apenas a linhagem NAO muda o event_id.
    other_lineage = replace(event, source_as_of=UTC_NOW + timedelta(days=7))
    assert other_lineage.event_id == event.event_id


def test_event_id_satisfies_the_primary_key_check_of_migration_104() -> None:
    event = li_events.LiveEvent(
        event_type=li_events.EVENT_NEW_OPPORTUNITY,
        subject_key="opportunity:X",
        prev_semantic_hash="",
        semantic_hash="c" * 64,
        source_as_of=UTC_NOW,
    )
    assert re.fullmatch(r"^[0-9a-f]{64}$", event.event_id)


def test_semantic_hash_projection_excludes_churn_fields() -> None:
    """§C.2 — ``source_as_of``, ``valor_estimado_brl``, ``link_edital``, hashes."""
    core = li_events.OPPORTUNITY_CORE_FIELDS
    for excluded in ("source_as_of", "valor_estimado_brl", "link_edital", "reason_codes"):
        assert excluded not in core


# --- criterios de emissao ---------------------------------------------------


def test_new_opportunity_is_bootstrap() -> None:
    events = li_events.diff_events(None, _universe([_opportunity()]))
    assert [e.event_type for e in events] == [li_events.EVENT_NEW_OPPORTUNITY]
    assert events[0].prev_semantic_hash == ""
    assert events[0].is_bootstrap
    assert events[0].subject_key == "opportunity:LI-TEST-EV-1"


def test_no_event_when_nothing_material_changed() -> None:
    base = _universe([_opportunity()])
    current = _universe([_opportunity()])
    assert li_events.diff_events(base, current) == []


@pytest.mark.parametrize(
    "churn",
    [
        {"source_as_of": UTC_NOW + timedelta(hours=6)},
        {"valor_estimado_brl": Decimal("250000.37")},
        {"link_edital": "https://exemplo.gov.br/edital/1"},
    ],
    ids=["watermark", "centavos", "link_edital"],
)
def test_churn_does_not_emit_any_event(churn: dict) -> None:
    """AC9 — churn de watermark/centavos/link nao e mudanca material."""
    base = _universe([_opportunity()])
    current = _universe([_opportunity(**churn)])
    assert li_events.diff_events(base, current) == []


def test_value_band_change_is_material_even_though_cents_are_not() -> None:
    base = _universe([_opportunity()])
    current = _universe([_opportunity(valor_estimado_brl=Decimal("5000000.00"), valor_band="1M_10M")])
    events = li_events.diff_events(base, current)
    assert [e.event_type for e in events] == [li_events.EVENT_OPPORTUNITY_CHANGED]
    assert events[0].prev_semantic_hash != events[0].semantic_hash


def test_deadline_change_is_a_separate_event_type() -> None:
    """§C.2 — OPEN→CLOSED nao deve poluir ``OPPORTUNITY_CHANGED``."""
    base = _universe([_opportunity()])
    current = _universe([_opportunity(data_encerramento=date(2026, 8, 20), deadline_state=li_schema.DEADLINE_CLOSED)])
    events = li_events.diff_events(base, current)
    assert [e.event_type for e in events] == [li_events.EVENT_DEADLINE_CHANGED]


def test_fit_became_relevant_uses_company_ref_as_subject() -> None:
    """AC9 — ``company:<company_ref>``, nunca ``company_digest`` (1:N fragmentaria)."""
    company = _company()
    current = _universe([_opportunity()], [company])
    events = li_events.diff_events(None, current)
    fit_events = [e for e in events if e.event_type == li_events.EVENT_FIT_BECAME_RELEVANT]
    assert len(fit_events) == 1
    assert fit_events[0].subject_key == f"company:{company.company_ref()}"
    assert "11222333000181" not in fit_events[0].subject_key


def test_fit_downgrade_emits_nothing_in_this_story() -> None:
    """Declarado, nao esquecido (AC9)."""
    relevant = _universe([_opportunity()], [_company()])
    irrelevant = _universe([_opportunity()], [_company(observed_ufs=("RS",), observed_objects=("Pavimentacao",))])
    downgrade = li_events.diff_events(relevant, irrelevant)
    assert [e.event_type for e in downgrade if e.event_type == li_events.EVENT_FIT_BECAME_RELEVANT] == []


def test_company_portfolio_changed_is_never_emitted() -> None:
    assert li_events.EVENT_COMPANY_PORTFOLIO_CHANGED not in li_events.EMITTED_EVENT_TYPES
    base = _universe([_opportunity()], [_company()])
    current = _universe([_opportunity()], [_company(portfolio_contract_ids=("c1", "c2"))])
    assert all(e.event_type != li_events.EVENT_COMPANY_PORTFOLIO_CHANGED for e in li_events.diff_events(base, current))


def test_transition_never_violates_the_is_transition_check() -> None:
    """``chk_live_intel_event_is_transition`` (104:464) — prev <> novo, sempre."""
    base = _universe([_opportunity()], [_company()])
    current = _universe(
        [_opportunity(valor_band="1M_10M", valor_estimado_brl=Decimal("5000000.00"))],
        [_company()],
    )
    for event in li_events.diff_events(base, current):
        assert event.prev_semantic_hash != event.semantic_hash


def test_replay_is_byte_for_byte_deterministic() -> None:
    """AC9 — duas rodadas do MESMO par base→corrente dao os MESMOS event_id."""
    base = _universe([_opportunity()], [_company()])
    current = _universe(
        [_opportunity(data_encerramento=date(2026, 11, 1)), _opportunity(opportunity_id="LI-TEST-EV-2")],
        [_company()],
    )
    first = [e.event_id for e in li_events.diff_events(base, current)]
    second = [e.event_id for e in li_events.diff_events(base, current)]
    assert first == second
    assert len(set(first)) == len(first), "event_id duplicado na mesma rodada"


# --- persistencia real ------------------------------------------------------

pytest_real_db = pytest.mark.real_db


@pytest_real_db
def test_persist_is_idempotent_on_replay(live_conn) -> None:
    """``ON CONFLICT (event_id) DO NOTHING`` — replay nao duplica (AC9)."""
    from scripts.confenge_live_intelligence.producer import build_snapshot

    created_by = "LI-TEST-events-idempotent"
    result = build_snapshot(
        live_conn,
        as_of=AS_OF,
        created_by=created_by,
        opportunities=[_opportunity()],
        companies=[_company()],
    )
    with live_conn.cursor() as cur:
        cur.execute(
            "SELECT event_id, event_type, prev_semantic_hash, prev_snapshot_id "
            "FROM public.confenge_live_intelligence_events WHERE snapshot_id = %s ORDER BY event_id",
            (result.snapshot_id,),
        )
        first = [dict(r) for r in cur.fetchall()]
    assert first, "o snapshot selado nao gerou nenhum evento — prova vacua"
    assert all(re.fullmatch(r"^[0-9a-f]{64}$", r["event_id"]) for r in first)
    # Bootstrap: prev vazio ⇔ prev_snapshot_id NULL (chk_live_intel_event_bootstrap).
    for row in first:
        if row["prev_semantic_hash"] == "":
            assert row["prev_snapshot_id"] is None

    # Replay do MESMO snapshot: mesmo conjunto, sem duplicata.
    replayed = li_events.generate_events(live_conn, snapshot_id=result.snapshot_id)
    with live_conn.cursor() as cur:
        cur.execute(
            "SELECT event_id FROM public.confenge_live_intelligence_events WHERE snapshot_id = %s ORDER BY event_id",
            (result.snapshot_id,),
        )
        second = [r["event_id"] for r in cur.fetchall()]
    assert second == [r["event_id"] for r in first]
    assert sorted(e.event_id for e in replayed) == sorted(second)
