"""Named fixtures for the eight required email-pattern cases."""

from __future__ import annotations

from typing import Any

from scripts.decision_unit_intelligence.email_patterns.engine import InjectedTechnicalAdapter
from scripts.decision_unit_intelligence.email_patterns.types import (
    KnownPerson,
    ObservedPersonEmail,
)
from scripts.decision_unit_intelligence.models import EpistemicClass

DOMAIN = "empresaexemplo.com.br"
OBSERVED_AT = "2026-06-01T12:00:00Z"
SOURCE = "https://empresaexemplo.com.br/equipe"


def _obs(
    email: str,
    person: str,
    *,
    domain: str = DOMAIN,
    url: str = SOURCE,
    epistemic: EpistemicClass = EpistemicClass.OBSERVED,
    account_id: str = "acc-exemplo",
) -> ObservedPersonEmail:
    return ObservedPersonEmail(
        email=email,
        person_name=person,
        domain=domain,
        source_url=url,
        observed_at=OBSERVED_AT,
        epistemic_class=epistemic,
        account_id=account_id,
    )


def fixture_three_first_last() -> dict[str, Any]:
    return {
        "name": "three_first_last_strong",
        "domain": DOMAIN,
        "observed": [
            _obs("ana.souza@empresaexemplo.com.br", "Ana Souza"),
            _obs("bruno.alves@empresaexemplo.com.br", "Bruno Alves"),
            _obs("carla.mendes@empresaexemplo.com.br", "Carla Mendes"),
        ],
        "known_people": [
            KnownPerson("João da Silva", corroborated=True, account_id="acc-exemplo"),
        ],
        "technical": InjectedTechnicalAdapter(
            mx_by_domain={DOMAIN: "MX_PRESENT"},
            catch_all_by_domain={DOMAIN: "UNKNOWN_NOT_PROBED"},
        ),
    }


def fixture_single_example() -> dict[str, Any]:
    return {
        "name": "single_example_not_high",
        "domain": DOMAIN,
        "observed": [_obs("ana.souza@empresaexemplo.com.br", "Ana Souza")],
        "known_people": [KnownPerson("João da Silva", corroborated=True, account_id="acc-exemplo")],
        "technical": InjectedTechnicalAdapter(
            mx_by_domain={DOMAIN: "MX_PRESENT"},
            catch_all_by_domain={DOMAIN: "UNKNOWN_NOT_PROBED"},
        ),
    }


def fixture_two_competing_patterns() -> dict[str, Any]:
    return {
        "name": "two_patterns_ambiguous",
        "domain": DOMAIN,
        "observed": [
            _obs("ana.souza@empresaexemplo.com.br", "Ana Souza"),
            _obs("brunoalves@empresaexemplo.com.br", "Bruno Alves"),
        ],
        "known_people": [KnownPerson("João da Silva", corroborated=True, account_id="acc-exemplo")],
        "technical": InjectedTechnicalAdapter(
            mx_by_domain={DOMAIN: "MX_PRESENT"},
            catch_all_by_domain={DOMAIN: "UNKNOWN_NOT_PROBED"},
        ),
    }


def fixture_particles() -> dict[str, Any]:
    return {
        "name": "brazilian_particles",
        "domain": DOMAIN,
        "observed": [
            _obs("ana.souza@empresaexemplo.com.br", "Ana de Souza"),
            _obs("bruno.alves@empresaexemplo.com.br", "Bruno dos Alves"),
            _obs("carla.mendes@empresaexemplo.com.br", "Carla Mendes"),
        ],
        "known_people": [
            KnownPerson("José Antônio da Costa Lima", corroborated=True, account_id="acc-exemplo"),
        ],
        "technical": InjectedTechnicalAdapter(
            mx_by_domain={DOMAIN: "MX_PRESENT"},
            catch_all_by_domain={DOMAIN: "UNKNOWN_NOT_PROBED"},
        ),
    }


def fixture_observed_alias() -> dict[str, Any]:
    return {
        "name": "observed_alias",
        "domain": DOMAIN,
        "observed": [
            _obs("ana.souza@empresaexemplo.com.br", "Ana Souza"),
            _obs("bruno.alves@empresaexemplo.com.br", "Bruno Alves"),
            _obs("ze.silva@empresaexemplo.com.br", "José da Silva"),
        ],
        "known_people": [
            KnownPerson("Maria de Oliveira", corroborated=True, account_id="acc-exemplo"),
            KnownPerson("José Ferreira", corroborated=True, account_id="acc-exemplo"),
        ],
        "technical": InjectedTechnicalAdapter(
            mx_by_domain={DOMAIN: "MX_PRESENT"},
            catch_all_by_domain={DOMAIN: "UNKNOWN_NOT_PROBED"},
        ),
    }


def fixture_catchall() -> dict[str, Any]:
    return {
        "name": "catch_all_domain",
        "domain": DOMAIN,
        "observed": [
            _obs("ana.souza@empresaexemplo.com.br", "Ana Souza"),
            _obs("bruno.alves@empresaexemplo.com.br", "Bruno Alves"),
            _obs("carla.mendes@empresaexemplo.com.br", "Carla Mendes"),
        ],
        "known_people": [KnownPerson("João da Silva", corroborated=True, account_id="acc-exemplo")],
        "technical": InjectedTechnicalAdapter(
            mx_by_domain={DOMAIN: "MX_PRESENT"},
            catch_all_by_domain={DOMAIN: "CATCH_ALL"},
        ),
    }


def fixture_wrong_domain() -> dict[str, Any]:
    return {
        "name": "wrong_domain_excluded",
        "domain": DOMAIN,
        "observed": [
            _obs("ana.souza@empresaexemplo.com.br", "Ana Souza"),
            _obs("bruno.alves@empresaexemplo.com.br", "Bruno Alves"),
            _obs("carla.mendes@empresaexemplo.com.br", "Carla Mendes"),
            _obs(
                "pedro.lima@outrodominio.com.br",
                "Pedro Lima",
                domain="outrodominio.com.br",
                url="https://outrodominio.com.br/equipe",
                account_id="acc-other",
            ),
        ],
        "known_people": [KnownPerson("João da Silva", corroborated=True, account_id="acc-exemplo")],
        "technical": InjectedTechnicalAdapter(
            mx_by_domain={DOMAIN: "MX_PRESENT"},
            catch_all_by_domain={DOMAIN: "UNKNOWN_NOT_PROBED"},
        ),
    }


def fixture_homonym() -> dict[str, Any]:
    return {
        "name": "homonym_not_auto_assigned",
        "domain": "empresa-b.com.br",
        "observed": [
            _obs(
                "joao.silva@empresa-a.com.br",
                "João Silva",
                domain="empresa-a.com.br",
                url="https://empresa-a.com.br/equipe",
                account_id="acc-a",
            ),
        ],
        "known_people": [
            KnownPerson("João Silva", corroborated=True, account_id="acc-b", person_id="person-b"),
        ],
        "technical": InjectedTechnicalAdapter(
            mx_by_domain={"empresa-b.com.br": "MX_PRESENT"},
            catch_all_by_domain={"empresa-b.com.br": "UNKNOWN_NOT_PROBED"},
        ),
    }


def all_fixtures() -> list[dict[str, Any]]:
    return [
        fixture_three_first_last(),
        fixture_single_example(),
        fixture_two_competing_patterns(),
        fixture_particles(),
        fixture_observed_alias(),
        fixture_catchall(),
        fixture_wrong_domain(),
        fixture_homonym(),
    ]


def audit_corpus_30() -> dict[str, Any]:
    """30 known people across domains with 3× first.last OBSERVED support each."""
    observed: list[ObservedPersonEmail] = []
    known: list[KnownPerson] = []
    mx: dict[str, str] = {}
    catch_all: dict[str, str] = {}
    first_names = [
        "Paulo",
        "Marina",
        "Ricardo",
        "Helena",
        "Felipe",
        "Camila",
        "Diego",
        "Larissa",
        "Rodrigo",
        "Patricia",
    ]
    last_names = [
        "Moreira",
        "Barbosa",
        "Teixeira",
        "Cardoso",
        "Nogueira",
        "Azevedo",
        "Pacheco",
        "Farias",
        "Rezende",
        "Siqueira",
    ]
    supporters = [
        ("Ana Souza", "ana.souza"),
        ("Bruno Alves", "bruno.alves"),
        ("Carla Mendes", "carla.mendes"),
    ]
    for index in range(10):
        domain = f"canario{index:02d}.eng.br"
        mx[domain] = "MX_PRESENT"
        catch_all[domain] = "CATCH_ALL" if index == 9 else "UNKNOWN_NOT_PROBED"
        account = f"canary-{index:02d}"
        for person_name, local in supporters:
            observed.append(
                _obs(
                    f"{local}@{domain}",
                    person_name,
                    domain=domain,
                    url=f"https://{domain}/equipe",
                    account_id=account,
                )
            )
        for offset in range(3):
            person_index = index * 3 + offset
            if person_index >= 30:
                break
            person = f"{first_names[person_index % 10]} {last_names[person_index % 10]}"
            known.append(
                KnownPerson(
                    person,
                    corroborated=True,
                    account_id=account,
                    person_id=f"canary-person-{person_index:02d}",
                )
            )
    return {
        "name": "audit_corpus_30",
        "domain": None,
        "observed": observed,
        "known_people": known,
        "technical": InjectedTechnicalAdapter(mx_by_domain=mx, catch_all_by_domain=catch_all),
        "domains": list(mx),
    }
