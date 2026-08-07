"""Ranking, DNC dominance, conflicts, stale freshness."""

from __future__ import annotations

from datetime import date

from scripts.confenge_contact_resolution.freshness import freshness_score
from scripts.confenge_contact_resolution.merge import observations_to_candidates
from scripts.confenge_contact_resolution.models import (
    RawObservation,
    RoleClass,
    ServiceContext,
    SourceProvenance,
    VerificationStatus,
)
from scripts.confenge_contact_resolution.ranking import select_recommended
from scripts.confenge_contact_resolution.role_map import map_role_class


def _obs(**kwargs) -> RawObservation:
    defaults = {
        "adapter": "site",
        "cnpj14": "12345678000199",
        "source": SourceProvenance(source_type="site", source_date="2026-06-01"),
    }
    defaults.update(kwargs)
    return RawObservation(**defaults)


def test_role_map() -> None:
    assert map_role_class("Diretor de Contratos") == RoleClass.CONTRATOS.value
    assert map_role_class("Gerente de Licitações") == RoleClass.LICITACOES.value
    assert map_role_class("Engenheiro de orçamento") == RoleClass.ENGENHARIA.value
    assert map_role_class(None) == RoleClass.GENERIC.value


def test_service_aware_ranking_claims_prefers_contratos() -> None:
    obs = [
        _obs(
            name="Ana Contratos",
            cargo="Gerente de Contratos",
            email="ana.contratos@obra.com.br",
            phone_raw="48999991111",
        ),
        _obs(
            name="Bob Vendas",
            cargo="Comercial",
            email="comercial@obra.com.br",
            phone_raw="48999992222",
            adapter="contact_page",
            source=SourceProvenance(source_type="contact_page", source_date="2026-06-01"),
        ),
    ]
    cands = observations_to_candidates(obs, cnpj14="12345678000199")
    ranked, rec = select_recommended(cands, service_context=ServiceContext.CLAIMS_REAJUSTE.value)
    assert rec is not None
    winner = next(c for c in ranked if c.recommended)
    assert winner.role_class == RoleClass.CONTRATOS.value
    assert winner.recommendation_reason


def test_licitacoes_prefers_licitacoes_role() -> None:
    obs = [
        _obs(name="Li", cargo="Analista de Licitações", email="licitacao@x.com.br", phone_raw="1133334444"),
        _obs(name="Fi", cargo="Financeiro", email="financeiro@x.com.br", phone_raw="1133335555"),
    ]
    cands = observations_to_candidates(obs, cnpj14="12345678000199")
    ranked, _ = select_recommended(cands, service_context=ServiceContext.LICITACOES.value)
    assert next(c for c in ranked if c.recommended).role_class == RoleClass.LICITACOES.value


def test_dnc_blocks_recommendation() -> None:
    obs = [
        _obs(
            name="Blocked",
            cargo="Diretor",
            email="diretor@x.com.br",
            phone_raw="48988887777",
            dnc=True,
            dnc_reason="DO_NOT_CONTACT",
            adapter="human_outcome",
            source=SourceProvenance(source_type="human_outcome", source_date="2026-07-01"),
        ),
        _obs(
            name="Alt",
            cargo="Comercial",
            email="contato@x.com.br",
            phone_raw="48988886666",
        ),
    ]
    cands = observations_to_candidates(obs, cnpj14="12345678000199")
    ranked, rec = select_recommended(cands, service_context=ServiceContext.GENERIC.value)
    dnc_ones = [c for c in ranked if c.dnc]
    assert dnc_ones
    assert all(not c.recommended for c in dnc_ones)
    assert rec is not None
    winner = next(c for c in ranked if c.recommended)
    assert not winner.dnc


def test_pattern_guess_not_recommended_primary() -> None:
    obs = [
        _obs(
            name="Guessed",
            cargo="Diretor",
            email="joao.silva@empresa.com.br",
            pattern_guessed_email=True,
        ),
        _obs(
            name=None,
            cargo=None,
            email="contato@empresa.com.br",
        ),
    ]
    cands = observations_to_candidates(obs, cnpj14="12345678000199")
    ranked, rec = select_recommended(cands)
    guessed = [c for c in ranked if c.verification_status == VerificationStatus.CANDIDATE_UNVERIFIED.value]
    assert guessed
    assert all(not c.recommended for c in guessed)
    assert all(not c.enrollable for c in guessed)
    winner = next(c for c in ranked if c.candidate_id == rec)
    assert winner.email == "contato@empresa.com.br"


def test_conflicting_sources_dedupe_by_email() -> None:
    obs = [
        _obs(
            email="contato@empresa.com.br",
            phone_raw="4833331111",
            adapter="registry",
            source=SourceProvenance(source_type="registry", source_date="2025-01-01"),
        ),
        _obs(
            email="contato@empresa.com.br",
            phone_raw="4833332222",
            adapter="site",
            source=SourceProvenance(source_type="site", source_date="2026-05-01"),
        ),
    ]
    cands = observations_to_candidates(obs, cnpj14="12345678000199")
    # same email → one candidate
    emails = [c.email for c in cands if c.email]
    assert emails.count("contato@empresa.com.br") == 1
    assert len([c for c in cands if c.email == "contato@empresa.com.br"]) == 1


def test_stale_contact_loses_confidence() -> None:
    fresh_f, _ = freshness_score("2026-06-01", as_of=date(2026, 8, 1))
    stale_f, age = freshness_score("2018-01-01", as_of=date(2026, 8, 1))
    assert age is not None and age > 1000
    assert stale_f < fresh_f

    obs_stale = [
        _obs(
            email="velho@empresa.com.br",
            phone_raw="48999990000",
            cargo="Diretor",
            name="Velho",
            source=SourceProvenance(source_type="public_docs", source_date="2018-01-01"),
        )
    ]
    obs_fresh = [
        _obs(
            email="novo@empresa.com.br",
            phone_raw="48999991111",
            cargo="Comercial",
            name="Novo",
            source=SourceProvenance(source_type="site", source_date="2026-07-01"),
        )
    ]
    stale_c = observations_to_candidates(obs_stale, cnpj14="12345678000199")[0]
    fresh_c = observations_to_candidates(obs_fresh, cnpj14="12345678000199")[0]
    assert stale_c.freshness < fresh_c.freshness
    assert stale_c.confidence < fresh_c.confidence


def test_total_absence() -> None:
    cands = observations_to_candidates([], cnpj14="12345678000199")
    ranked, rec = select_recommended(cands)
    assert ranked == []
    assert rec is None
