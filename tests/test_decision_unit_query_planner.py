"""Drive the shipped query planner: families, yield, cache, early-stop, backends."""

from __future__ import annotations

from pathlib import Path

from scripts.decision_unit_intelligence.providers.base import InvestigationContext
from scripts.decision_unit_intelligence.query_planner import (
    QueryFamily,
    QuerySearchCache,
    execute_plan,
    load_policy,
    plan_queries,
    rank_queries,
    should_early_stop,
)
from scripts.decision_unit_intelligence.query_planner.benchmark import ObservationReplayBackend
from scripts.decision_unit_intelligence.query_planner.spec import QueryPolicy, QuerySpec, emit_query_specs
from scripts.decision_unit_intelligence.web_discovery import JsonDiscoveryCache, SearchHit


class ScriptedBackend:
    backend_id = "searxng"

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.hits_for: dict[str, list[SearchHit]] = {}
        self.errors: dict[str, Exception] = {}

    def search(self, query: str, *, limit: int) -> list[SearchHit]:
        self.calls.append(query)
        if query in self.errors:
            raise self.errors[query]
        return list(self.hits_for.get(query, []))[:limit]


def _ctx(**kwargs) -> InvestigationContext:
    payload = {
        "cnpj": "12345678000190",
        "legal_name": "EMPRESA EXEMPLO ENGENHARIA LTDA",
        "service": "reajuste_14133",
    }
    payload.update(kwargs)
    return InvestigationContext(**payload)


def test_emit_includes_required_family_shapes() -> None:
    specs = emit_query_specs(
        _ctx(),
        known_domain="empresaexemplo.com.br",
        known_people=["João da Silva"],
        trade_name="Exemplo",
    )
    queries = [spec.query for spec in specs]
    families = {spec.family for spec in specs}
    assert families == set(QueryFamily)
    assert '"EMPRESA EXEMPLO ENGENHARIA LTDA" email' in queries
    assert '"Exemplo" contato' in queries
    assert '"12345678000190" email' in queries
    assert 'site:empresaexemplo.com.br "@empresaexemplo.com.br"' in queries
    assert '"João da Silva" "EMPRESA EXEMPLO ENGENHARIA LTDA"' in queries
    assert '"João da Silva" "@empresaexemplo.com.br"' in queries
    assert '"João da Silva" email' in queries
    assert 'site:empresaexemplo.com.br "João da Silva"' in queries
    assert '"EMPRESA EXEMPLO ENGENHARIA LTDA" diretor engenharia email' in queries
    assert '"EMPRESA EXEMPLO ENGENHARIA LTDA" gerente contratos email' in queries
    assert '"EMPRESA EXEMPLO ENGENHARIA LTDA" licitações email' in queries
    assert '"12345678000190" filetype:pdf' in queries
    assert '"EMPRESA EXEMPLO ENGENHARIA LTDA" ata email' in queries
    assert "site:empresaexemplo.com.br equipe" in queries
    assert "site:empresaexemplo.com.br diretoria" in queries
    assert "site:empresaexemplo.com.br contato" in queries
    assert "site:empresaexemplo.com.br engenharia" in queries


def test_duplicate_query_emitted_once() -> None:
    specs = emit_query_specs(_ctx(), known_domain="empresaexemplo.com.br", known_people=["João da Silva"])
    normalized = [spec.query.casefold() for spec in specs]
    assert len(normalized) == len(set(normalized))


def test_same_policy_and_input_reproduces_the_same_plan() -> None:
    policy = load_policy("query-policy.v2")
    first = plan_queries(
        _ctx(),
        policy=policy,
        known_domain="empresaexemplo.com.br",
        known_people=["João da Silva"],
    )
    second = plan_queries(
        _ctx(),
        policy=policy,
        known_domain="empresaexemplo.com.br",
        known_people=["João da Silva"],
    )
    assert first.to_dict() == second.to_dict()
    assert [spec.query for spec in first.specs] == [spec.query for spec in second.specs]


def test_adaptive_budget_person_and_domain_vs_unknown_domain() -> None:
    policy = load_policy("query-policy.v2")
    specific = plan_queries(
        _ctx(),
        policy=policy,
        known_domain="empresaexemplo.com.br",
        known_people=["João da Silva"],
    )
    discovery = plan_queries(_ctx(), policy=policy, known_domain=None, known_people=[])
    assert specific.adaptive_mode == "known_person_and_domain"
    assert discovery.adaptive_mode == "unknown_domain"
    assert specific.specs[0].family in {QueryFamily.PERSON, QueryFamily.SITE_PATH}
    assert any(spec.family == QueryFamily.PERSON for spec in specific.specs)
    assert any(spec.family == QueryFamily.SITE_PATH for spec in specific.specs)
    assert discovery.specs[0].family == QueryFamily.COMPANY
    assert all(spec.family != QueryFamily.SITE_PATH for spec in discovery.specs)
    assert all(spec.family != QueryFamily.PERSON for spec in discovery.specs)


def test_unsupported_operator_is_marked_and_not_executed_as_success() -> None:
    payload = load_policy("query-policy.v1").to_dict()
    payload["family_order"] = ["DOCUMENT", "COMPANY", "PERSON", "ROLE", "SITE_PATH"]
    payload["early_stop"] = {
        "min_identity_associated": 99,
        "min_observed_email": 99,
        "max_zero_yield_streak": 99,
    }
    policy = QueryPolicy.from_dict(payload)
    plan = plan_queries(_ctx(), policy=policy, known_domain="empresaexemplo.com.br")
    backend = ScriptedBackend()
    backend.backend_id = "replay-ddgs"
    pdf_queries = [spec.query for spec in plan.specs if "filetype:pdf" in spec.query]
    assert pdf_queries
    run = execute_plan(plan, backend, policy=policy, legal_name="EMPRESA EXEMPLO ENGENHARIA LTDA")
    skipped = [row for row in run.executions if row.skip_reason == "unsupported_operator"]
    assert skipped
    assert all("filetype" in (row.failure or "") for row in skipped)
    assert all(row.spec.query not in backend.calls for row in skipped)
    assert all(not row.executed or row.failure for row in skipped)


def test_backend_failure_is_visible_not_empty_miss() -> None:
    policy = load_policy("query-policy.v2")
    plan = plan_queries(_ctx(), policy=policy, known_domain=None, known_people=[])
    backend = ScriptedBackend()
    target = plan.specs[0].query

    class RateLimitedError(Exception):
        status_code = 429

    backend.errors[target] = RateLimitedError("too many requests")
    run = execute_plan(plan, backend, policy=policy, legal_name="EMPRESA EXEMPLO ENGENHARIA LTDA")
    failed = next(row for row in run.executions if row.spec.query == target)
    assert failed.executed
    assert failed.failure
    assert failed.http_status == 429
    assert failed.result_count == 0
    assert failed.observed_email_count == 0
    assert "RateLimitedError" in failed.failure


def test_cache_hits_second_normalized_query_same_backend_and_policy(tmp_path: Path) -> None:
    policy = load_policy("query-policy.v2")
    plan = plan_queries(_ctx(), policy=policy, known_domain=None, known_people=[])
    backend = ScriptedBackend()
    first_query = plan.specs[0].query
    backend.hits_for[first_query] = [
        SearchHit("https://empresaexemplo.com.br/contato", "contato", "email contato@empresaexemplo.com.br")
    ]
    cache = QuerySearchCache(JsonDiscoveryCache(tmp_path, ttl_days=7), policy_version=policy.version)
    first = execute_plan(plan, backend, policy=policy, cache=cache, legal_name="EMPRESA EXEMPLO ENGENHARIA LTDA")
    second = execute_plan(plan, backend, policy=policy, cache=cache, legal_name="EMPRESA EXEMPLO ENGENHARIA LTDA")
    executed_first = [row.spec.query for row in first.executions if row.executed and not row.failure]
    assert executed_first
    assert backend.calls == executed_first
    assert all(row.cache_hit for row in second.executions if row.spec.query in executed_first)
    other_policy = QuerySearchCache(JsonDiscoveryCache(tmp_path, ttl_days=7), policy_version="query-policy.v1")
    third = execute_plan(plan, backend, policy=policy, cache=other_policy, legal_name="EMPRESA EXEMPLO ENGENHARIA LTDA")
    assert any(not row.cache_hit for row in third.executions if row.executed)


def test_early_stop_skips_remaining_after_identity_or_low_marginal_gain() -> None:
    policy = load_policy("query-policy.v2")
    plan = plan_queries(
        _ctx(),
        policy=policy,
        known_domain="empresaexemplo.com.br",
        known_people=["João da Silva"],
    )
    backend = ScriptedBackend()
    first = plan.specs[0].query
    backend.hits_for[first] = [
        SearchHit(
            "https://empresaexemplo.com.br/equipe",
            "João da Silva",
            "E-mail de João da Silva: joao.silva@empresaexemplo.com.br",
        )
    ]
    run = execute_plan(
        plan,
        backend,
        policy=policy,
        legal_name="EMPRESA EXEMPLO ENGENHARIA LTDA",
        known_people=["João da Silva"],
    )
    assert run.executions[0].executed
    assert run.executions[0].identity_associated_count >= 1
    assert should_early_stop(run.executions[:1], policy)
    assert any(row.skip_reason == "early_stop" for row in run.executions[1:])
    assert backend.calls == [first]


def test_early_stop_on_zero_yield_streak() -> None:
    policy = load_policy("query-policy.v2")
    plan = plan_queries(_ctx(), policy=policy, known_domain=None, known_people=[])
    backend = ScriptedBackend()
    run = execute_plan(plan, backend, policy=policy, legal_name="EMPRESA EXEMPLO ENGENHARIA LTDA")
    executed = [row for row in run.executions if row.executed]
    assert len(executed) <= policy.max_zero_yield_streak
    assert any(row.skip_reason == "early_stop" for row in run.executions)


def test_ranking_uses_downstream_yield_not_serp_count() -> None:
    policy = load_policy("query-policy.v2")
    noisy = QuerySpec(QueryFamily.ROLE, "noisy", '"EMPRESA" diretor', "12345678000190")
    precise = QuerySpec(QueryFamily.PERSON, "precise", '"João" email', "12345678000190")
    from scripts.decision_unit_intelligence.query_planner.spec import QueryExecution

    high_serp = QueryExecution(
        spec=noisy,
        backend="searxng",
        executed=True,
        result_count=40,
        useful_url_count=0,
        observed_email_count=0,
        identity_associated_count=0,
    )
    low_serp = QueryExecution(
        spec=precise,
        backend="searxng",
        executed=True,
        result_count=2,
        useful_url_count=1,
        observed_email_count=1,
        identity_associated_count=1,
    )
    ranked = rank_queries([high_serp, low_serp])
    assert ranked[0]["shape_id"] == "precise"
    assert ranked[0]["result_count_total"] < ranked[1]["result_count_total"]
    assert policy.ranking_metric != "result_count"


def test_replay_backend_does_not_invent_identity_email() -> None:
    from scripts.decision_unit_intelligence.query_planner.benchmark import BenchmarkAccount

    account = BenchmarkAccount(
        cnpj="00820854000114",
        legal_name="QUALIDADE MINERACAO LTDA",
        site="https://qualidademineracao.com.br/",
        email="contato@qualidademineracao.com.br",
        fonte="https://qualidademineracao.com.br/",
        people=["EDUARDO SCHMITT ESPINDOLA"],
        trade_name="qualidade",
    )
    backend = ObservationReplayBackend([account], simulate_backend="searxng")
    hits = backend.search('"EDUARDO SCHMITT ESPINDOLA" email', limit=5)
    joined = " ".join(f"{hit.title} {hit.snippet}" for hit in hits)
    assert "eduardo" not in joined.lower() or "contato@qualidademineracao.com.br" in joined
    assert "eduardo.schmitt@" not in joined.lower()


def test_cli_query_yield_replay_30(tmp_path: Path) -> None:
    from scripts.decision_unit_intelligence.query_planner.__main__ import main

    out = tmp_path / "yield-30"
    rc = main(
        [
            "--out",
            str(out),
            "--limit",
            "30",
            "--primary",
            "replay-searxng",
            "--compare",
            "replay-ddgs",
            "--query-policy-version",
            "query-policy.v2",
            "--search-cache-dir",
            str(tmp_path / "cache"),
        ]
    )
    assert rc == 0
    report = (out / "query-yield-report.json").read_text(encoding="utf-8")
    assert "identity_associated_per_search" in report
    assert "COMPANY" in report
    assert "PERSON" in report
    assert "ROLE" in report
    assert "DOCUMENT" in report
    assert "SITE_PATH" in report
    assert "weak_sources" in report
    assert "replay-searxng" in report
    assert "replay-ddgs" in report
    assert (out / "query-yield-report.md").exists()
    assert (out / "query-policy.v2.json").exists()
