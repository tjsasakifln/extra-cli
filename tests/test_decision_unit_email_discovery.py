"""Golden/adversarial fixtures drive the shipped extract/associate/classify/pattern path."""

from __future__ import annotations

from scripts.decision_unit_intelligence.email_discovery import (
    EmailDiscoveryClass,
    associate_person_to_email,
    classify_email_discovery,
    derive_versioned_patterns,
    inferred_candidates_from_supported_patterns,
)
from scripts.decision_unit_intelligence.email_resolution import ObservedOrgEmail as ResolutionObserved
from scripts.decision_unit_intelligence.models import (
    ChannelObservation,
    ChannelType,
    EpistemicClass,
    PersonObservation,
    PersonRelation,
    ReachabilityClass,
    RouteRelation,
)
from scripts.decision_unit_intelligence.orchestrator import investigate_account
from scripts.decision_unit_intelligence.projection import is_email_safe_for_warmbly, project_warmbly_outreach
from scripts.decision_unit_intelligence.providers.base import InvestigationContext
from scripts.decision_unit_intelligence.web_discovery import (
    CrawlDocument,
    SearchHit,
    build_query_plan,
    extract_public_evidence,
    rank_crawl_urls,
)


def _person(name: str, role: str = "Diretor") -> PersonObservation:
    return PersonObservation(
        observation_id=f"p-{name}",
        company_entity_id="12345678000190",
        person_name=name,
        observed_role=role,
        relation=PersonRelation.COMPANY_MEMBER,
        source_type="company_website",
        source_url="https://empresaexemplo.com.br/equipe",
        epistemic_class=EpistemicClass.OBSERVED,
    )


def _doc(html: str = "", text: str = "", url: str = "https://empresaexemplo.com.br/equipe") -> CrawlDocument:
    return CrawlDocument(
        url=url,
        text=text or " ",
        content_type="text/html",
        retrieved_at="2026-08-14T12:00:00Z",
        html=html,
        bytes_touched=len((html or text).encode()),
    )


def _context() -> InvestigationContext:
    return InvestigationContext(
        cnpj="12345678000190",
        legal_name="EMPRESA EXEMPLO ENGENHARIA LTDA",
        service="reajuste_14133",
    )


def test_equipe_page_with_mailto_associates_with_field_evidence():
    html = """
    <html><body>
      <article class="card">
        <h3>João da Silva</h3>
        <p>Diretor de Engenharia</p>
        <a href="mailto:joao.silva@empresaexemplo.com.br">escrever</a>
      </article>
    </body></html>
    """
    extracted = extract_public_evidence(_context(), _doc(html=html, text="João da Silva Diretor de Engenharia"))
    email = next(ch for ch in extracted.channels if ch.channel_value == "joao.silva@empresaexemplo.com.br")
    assert email.person_name == "João da Silva"
    assert email.extra["identity_explicitly_associated"] is True
    assert email.extra["email_discovery_class"] == EmailDiscoveryClass.OBSERVED_DIRECT_EMAIL_IDENTITY_ASSOCIATED.value
    assert "MAILTO_IN_PERSON_BLOCK" in email.extra["association_reason_codes"]
    evidence = next(item for item in extracted.evidence if item.field == "email")
    assert evidence.source_url == "https://empresaexemplo.com.br/equipe"
    assert evidence.evidence_snippet
    assert evidence.extraction_method
    assert "CONTEXTUAL_IDENTITY_ASSOCIATED" in evidence.extra["reason_codes"]


def test_split_cards_do_not_associate():
    html = """
    <html><body>
      <article class="card"><h3>João da Silva</h3><p>Diretor de Engenharia</p></article>
      <article class="card"><a href="mailto:contato@empresaexemplo.com.br">contato</a></article>
    </body></html>
    """
    extracted = extract_public_evidence(
        _context(),
        _doc(html=html, text="João da Silva Diretor de Engenharia contato@empresaexemplo.com.br"),
    )
    email = next(ch for ch in extracted.channels if ch.channel_value == "contato@empresaexemplo.com.br")
    assert email.extra["identity_explicitly_associated"] is False
    assert email.person_name is None
    association = associate_person_to_email(
        "contato@empresaexemplo.com.br",
        people=[_person("João da Silva")],
        html=html,
        text="João da Silva Diretor de Engenharia",
        source_url="https://empresaexemplo.com.br/equipe",
    )
    assert association.associated is False


def test_two_names_near_one_email_are_ambiguous():
    html = """
    <html><body>
      <article>
        João da Silva e Maria Souza — e-mail: comercial.time@empresaexemplo.com.br
      </article>
    </body></html>
    """
    association = associate_person_to_email(
        "comercial.time@empresaexemplo.com.br",
        people=[_person("João da Silva"), _person("Maria Souza", "Gerente")],
        html=html,
        text="João da Silva e Maria Souza comercial.time@empresaexemplo.com.br",
        source_url="https://empresaexemplo.com.br/equipe",
    )
    assert association.associated is False
    assert association.ambiguous is True
    assert "AMBIGUOUS_PERSON_EMAIL_CONTEXT" in association.reason_codes


def test_brand_mailbox_on_contact_page_is_not_identity():
    html = """
    <section>
      <h3>José Roberto</h3>
      <p>Diretor</p>
      <a href="mailto:setep@setep.com.br">setep@setep.com.br</a>
    </section>
    """
    extracted = extract_public_evidence(
        _context(),
        _doc(html=html, text="José Roberto Diretor setep@setep.com.br", url="https://setep.com.br/institucional"),
        canonical_domain="setep.com.br",
    )
    email = next(ch for ch in extracted.channels if ch.channel_value == "setep@setep.com.br")
    assert email.extra["identity_explicitly_associated"] is False
    assert email.person_name is None
    assert email.channel_type.value == "GENERIC_CORPORATE_EMAIL"
    assert "GENERIC_OR_BRAND_MAILBOX_NOT_PERSON" in email.extra["association_reason_codes"]


def test_lawyer_mailbox_on_company_page_is_not_identity():
    html = """
    <article>
      <h3>Chief Compliance Officer</h3>
      <p>Canal de denúncias operado por escritório terceiro.</p>
      <a href="mailto:ricardocoelho@ricardocoelho.adv.br">e-mail</a>
    </article>
    """
    extracted = extract_public_evidence(
        _context(),
        _doc(
            html=html,
            text="Chief Compliance Officer ricardocoelho@ricardocoelho.adv.br",
            url="https://planaterra.com.br/2026/03/04/programa-de-compliance-planaterra/",
        ),
        canonical_domain="planaterra.com.br",
    )
    email = next(ch for ch in extracted.channels if "ricardocoelho" in (ch.channel_value or ""))
    assert email.extra["identity_explicitly_associated"] is False
    assert email.person_name is None
    assert email.extra["email_discovery_class"] != EmailDiscoveryClass.EMAIL_VALIDATED.value
    assert {
        "FOREIGN_OR_THIRD_PARTY_DOMAIN",
        "GENERIC_OR_BRAND_MAILBOX_NOT_PERSON",
        "THIRD_PARTY_PROFESSIONAL_DOMAIN",
    } & set(email.extra["association_reason_codes"])
    assert not any((person.person_name or "").lower().startswith("chief") for person in extracted.people)


def test_holding_or_third_party_domain_is_not_silently_promoted():
    html = """
    <html><body>
      <article>
        <h3>João da Silva</h3>
        <a href="mailto:joao.silva@fiscallcontabilidade.com.br">email</a>
      </article>
    </body></html>
    """
    extracted = extract_public_evidence(
        InvestigationContext(cnpj="12345678000190", legal_name="EMPRESA EXEMPLO ENGENHARIA LTDA"),
        _doc(
            html=html,
            text="João da Silva Diretor joao.silva@fiscallcontabilidade.com.br",
            url="https://casadosdados.com.br/empresa/exemplo",
        ),
        canonical_domain="empresaexemplo.com.br",
    )
    email = next(ch for ch in extracted.channels if "fiscall" in (ch.channel_value or ""))
    assert email.extra["identity_explicitly_associated"] is False
    assert email.extra["third_party_echo"] is True
    assert email.extra["email_discovery_class"] != EmailDiscoveryClass.EMAIL_VALIDATED.value


def test_pattern_from_several_observed_stays_inferred_even_with_mx():
    observed = [
        ResolutionObserved("ana.souza@empresaexemplo.com.br", "company_website", person_name="ANA SOUZA"),
        ResolutionObserved("bruno.alves@empresaexemplo.com.br", "company_website", person_name="BRUNO ALVES"),
    ]
    records = derive_versioned_patterns(observed)
    first_last = next(record for record in records if record.pattern_id == "first.last")
    assert first_last.version == "org-email-pattern.v1"
    assert first_last.epistemic_class == EpistemicClass.CORROBORATED
    assert "PATTERN_NOT_A_PERSON_FACT" in first_last.reason_codes
    inferences = inferred_candidates_from_supported_patterns(
        person_name="João da Silva",
        domain="empresaexemplo.com.br",
        observed=observed,
        mx_valid=True,
    )
    assert inferences
    assert all(item.epistemic_class == EpistemicClass.INFERRED for item in inferences)
    klass = classify_email_discovery(
        inferences[0].email,
        epistemic=EpistemicClass.INFERRED,
        inferred_pattern=True,
        mx_present=True,
    )
    assert klass == EmailDiscoveryClass.INFERRED_PATTERN_EMAIL
    assert klass != EmailDiscoveryClass.EMAIL_VALIDATED


def test_generic_and_role_mailboxes_never_become_a_person():
    for address, expected in (
        ("contato@empresaexemplo.com.br", EmailDiscoveryClass.GENERIC_MAILBOX),
        ("conduta@empresaexemplo.com.br", EmailDiscoveryClass.GENERIC_MAILBOX),
        ("empresaexemplo@empresaexemplo.com.br", EmailDiscoveryClass.GENERIC_MAILBOX),
        ("vitoria@empresaexemplo.com.br", EmailDiscoveryClass.GENERIC_MAILBOX),
        ("brasilia@empresaexemplo.com.br", EmailDiscoveryClass.GENERIC_MAILBOX),
        ("comercial@empresaexemplo.com.br", EmailDiscoveryClass.ROLE_MAILBOX),
        ("licitacoes@empresaexemplo.com.br", EmailDiscoveryClass.ROLE_MAILBOX),
    ):
        klass = classify_email_discovery(address, epistemic=EpistemicClass.OBSERVED, identity_associated=True)
        assert klass == expected
        extracted = extract_public_evidence(
            _context(),
            _doc(
                html=f"<p>Fale conosco <a href='mailto:{address}'>{address}</a></p>",
                text=f"Fale conosco {address}",
                url="https://empresaexemplo.com.br/contato",
            ),
        )
        channel = next(ch for ch in extracted.channels if ch.channel_value == address)
        assert channel.person_name is None
        assert channel.extra["identity_explicitly_associated"] is False


def test_stale_person_is_not_current_identity():
    html = """
    <article>
      Ex-diretor João da Silva saiu da empresa. e-mail antigo: joao.silva@empresaexemplo.com.br
    </article>
    """
    association = associate_person_to_email(
        "joao.silva@empresaexemplo.com.br",
        people=[_person("João da Silva")],
        html=html,
        text="Ex-diretor João da Silva saiu da empresa joao.silva@empresaexemplo.com.br",
        source_url="https://empresaexemplo.com.br/equipe",
    )
    assert association.associated is False
    assert association.stale is True
    assert "PERSON_MAY_HAVE_LEFT" in association.reason_codes


def test_third_party_index_echo_is_not_identity():
    association = associate_person_to_email(
        "joao.silva@empresaexemplo.com.br",
        people=[_person("João da Silva")],
        html="<article><h3>João da Silva</h3><a href='mailto:joao.silva@empresaexemplo.com.br'>x</a></article>",
        text="João da Silva joao.silva@empresaexemplo.com.br",
        source_url="https://econodata.com.br/consulta/empresa-exemplo",
    )
    assert association.third_party_echo is True
    assert association.associated is False
    assert "THIRD_PARTY_ECHO_NOT_IDENTITY" in association.reason_codes


def test_public_professional_document_with_unequivocal_association():
    html = """
    <section>
      <h2>João da Silva</h2>
      <p>Diretor de Engenharia — EMPRESA EXEMPLO ENGENHARIA LTDA</p>
      <p>E-mail de João da Silva: joao.silva@empresaexemplo.com.br</p>
    </section>
    """
    association = associate_person_to_email(
        "joao.silva@empresaexemplo.com.br",
        people=[_person("João da Silva", "Diretor de Engenharia")],
        html=html,
        text="João da Silva Diretor de Engenharia E-mail de João da Silva: joao.silva@empresaexemplo.com.br",
        source_url="https://empresaexemplo.com.br/institucional/diretoria",
        canonical_domain="empresaexemplo.com.br",
    )
    assert association.associated is True
    assert association.person_name == "João da Silva"
    assert "EXPLICIT_EMAIL_DE_NOME" in association.reason_codes
    assert association.extraction_method
    assert association.snippet


def test_query_plan_emits_email_job_shapes_and_internal_rank_includes_equipe():
    ctx = _context()
    ctx.extra["known_people"] = ["João da Silva"]
    queries = build_query_plan(ctx, known_domain="empresaexemplo.com.br", known_people=["João da Silva"])
    assert '"João da Silva" "EMPRESA EXEMPLO ENGENHARIA LTDA"' in queries
    assert '"João da Silva" "@empresaexemplo.com.br"' in queries
    assert '"João da Silva" email' in queries
    assert 'site:empresaexemplo.com.br "João da Silva"' in queries
    assert 'site:empresaexemplo.com.br "@empresaexemplo.com.br"' in queries
    assert "site:empresaexemplo.com.br equipe" in queries
    assert '"12345678000190" "João da Silva" email' in queries
    ranked = rank_crawl_urls(
        [SearchHit("https://empresaexemplo.com.br/", "Home", "site oficial")],
        "empresaexemplo.com.br",
        limit=4,
        extra_urls=["https://empresaexemplo.com.br/equipe", "https://empresaexemplo.com.br/blog/foto"],
    )
    assert "https://empresaexemplo.com.br/equipe" in ranked
    assert ranked.index("https://empresaexemplo.com.br/equipe") < ranked.index("https://empresaexemplo.com.br/")


def test_warmbly_never_promotes_inferred_or_generic_to_validated():
    account = investigate_account(
        cnpj="12345678000190",
        legal_name="EMPRESA EXEMPLO ENGENHARIA LTDA",
        service="reajuste_14133",
        why_now="contrato ativo",
        people=[_person("JOAO SILVA"), _person("ANA SOUZA", "Gerente")],
        channels=[
            ChannelObservation(
                observation_id="obs-ana",
                company_entity_id="12345678000190",
                channel_type=ChannelType.DIRECT_EMAIL,
                channel_value="ana.souza@empresaexemplo.com.br",
                person_name="ANA SOUZA",
                source_type="company_website",
                source_url="https://empresaexemplo.com.br/equipe",
                epistemic_class=EpistemicClass.OBSERVED,
                extra={"identity_explicitly_associated": True},
            ),
            ChannelObservation(
                observation_id="obs-gen",
                company_entity_id="12345678000190",
                channel_type=ChannelType.GENERIC_CORPORATE_EMAIL,
                channel_value="contato@empresaexemplo.com.br",
                source_type="company_website",
                source_url="https://empresaexemplo.com.br/contato",
                epistemic_class=EpistemicClass.OBSERVED,
            ),
        ],
        company_site="https://empresaexemplo.com.br",
        infer_email=True,
    )
    inferred = [route for route in account.routes if route.channel_type == ChannelType.INFERRED_DIRECT_EMAIL]
    assert inferred
    assert all(route.epistemic_class == EpistemicClass.INFERRED for route in inferred)
    assert all(route.extra["email_discovery_class"] == EmailDiscoveryClass.INFERRED_PATTERN_EMAIL.value for route in inferred)
    assert all(not is_email_safe_for_warmbly(route) for route in inferred)
    payload = project_warmbly_outreach(account)
    assert payload["auto_send"] is False
    assert all(item["contact_tier"] == "DIRECT_EMAIL_VALIDATED" for item in payload["recipient_candidates"])
    for item in payload["email_discovery_routes"]:
        if item["email_discovery_class"] in {
            EmailDiscoveryClass.INFERRED_PATTERN_EMAIL.value,
            EmailDiscoveryClass.GENERIC_MAILBOX.value,
            EmailDiscoveryClass.ROLE_MAILBOX.value,
        }:
            assert item["contact_tier"] != "DIRECT_EMAIL_VALIDATED"
            assert item["contact_tier"] != "EMAIL_VALIDATED"
    ana = next(route for route in account.routes if route.channel_value == "ana.souza@empresaexemplo.com.br")
    assert ana.route_relation == RouteRelation.PERSON_OWNS_CHANNEL
    assert ana.reachability_class == ReachabilityClass.R1_DIRECT
    assert is_email_safe_for_warmbly(ana)
    assert ana.extra["email_discovery_class"] == EmailDiscoveryClass.EMAIL_VALIDATED.value
    first = project_warmbly_outreach(account)
    second = project_warmbly_outreach(account)
    assert first["email_safe_count"] == second["email_safe_count"]
    assert first["recipient_candidates"] == second["recipient_candidates"]
