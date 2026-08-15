"""Fresh consumer of the versioned query planner (not the planner unit tests)."""

from __future__ import annotations

from scripts.decision_unit_intelligence.providers.base import InvestigationContext
from scripts.decision_unit_intelligence.query_planner import QueryFamily, load_policy, plan_queries


def test_consumer_known_person_and_domain_gets_specific_queries() -> None:
    policy = load_policy("query-policy.v2")
    context = InvestigationContext(
        cnpj="52639513000140",
        legal_name="INFRAPAV CONSTRUCOES LTDA",
        service="reajuste_14133",
    )
    plan = plan_queries(
        context,
        policy=policy,
        known_domain="infrapav.com.br",
        known_people=["KELLY NUNES"],
    )
    families = {spec.family for spec in plan.specs}
    assert QueryFamily.PERSON in families
    assert QueryFamily.SITE_PATH in families
    assert QueryFamily.COMPANY in families
    assert plan.specs[0].family in {QueryFamily.COMPANY, QueryFamily.PERSON, QueryFamily.SITE_PATH}
    assert any('"KELLY NUNES"' in spec.query for spec in plan.specs)
    assert any(spec.query.startswith("site:infrapav.com.br") for spec in plan.specs)


def test_consumer_unknown_domain_starts_with_company_discovery() -> None:
    policy = load_policy("query-policy.v2")
    context = InvestigationContext(
        cnpj="29095199000160",
        legal_name="PAVIMENTAR ENGENHARIA E CONSTRUÇÕES LTDA",
        service="reajuste_14133",
    )
    plan = plan_queries(context, policy=policy, known_domain=None, known_people=[])
    assert plan.adaptive_mode == "unknown_domain"
    assert plan.specs[0].family == QueryFamily.COMPANY
    assert plan.specs[0].shape_id in {"company_legal_email", "cnpj_email", "trade_name_contact"}
    assert all(spec.family != QueryFamily.PERSON for spec in plan.specs)
    assert all(spec.family != QueryFamily.SITE_PATH for spec in plan.specs)
    assert any('"PAVIMENTAR ENGENHARIA E CONSTRUÇÕES LTDA" email' == spec.query for spec in plan.specs)
    assert any('"29095199000160" email' == spec.query for spec in plan.specs)
