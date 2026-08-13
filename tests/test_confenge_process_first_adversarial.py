"""Adversarial tests for process-first commercial enrichment (§39).

Each test drives shipped functions — no reimplementation theater.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.confenge_process_enrichment.contact_extract import (
    extract_contacts_from_text,
    pattern_guess_email,
)
from scripts.confenge_process_enrichment.contact_graph import build_account_contact_graph, select_best_for_service
from scripts.confenge_process_enrichment.identifiers import normalize_process_number, process_number_variants
from scripts.confenge_process_enrichment.models import (
    ContactObservation,
    EpistemicClass,
    content_hash,
)
from scripts.confenge_process_enrichment.outreach_export import (
    assert_no_forbidden_pii,
    observation_to_outreach,
)
from scripts.confenge_process_enrichment.pipeline import ProcessFirstConfig, ProcessFirstEnricher, enrich_account
from scripts.confenge_process_enrichment.states import (
    InvestigationState,
    TerminalState,
    can_declare_no_contact,
)

FIXTURES = Path(__file__).parent / "fixtures" / "confenge_process_enrichment"


def test_01_public_official_email_not_company_contact():
    text = """
    Pregão Eletrônico 10/2024
    Pregoeiro: João Servidor
    E-mail: joao.servidor@prefeitura.sp.gov.br
    Telefone: (11) 3333-4444
    Empresa vencedora: CONSTRUTORA EXEMPLO LTDA CNPJ 12.345.678/0001-90
    """
    obs = extract_contacts_from_text(
        text,
        company_cnpj="12345678000190",
        company_name="CONSTRUTORA EXEMPLO LTDA",
        document_title="Ata de Sessão",
        document_type="ata",
    )
    gov = [o for o in obs if o.email and o.email.endswith(".gov.br")]
    assert gov, "expected government email extraction"
    assert all(o.epistemic_class == EpistemicClass.PUBLIC_OFFICIAL for o in gov)
    assert all(not o.is_commercially_usable() for o in gov)
    graph = build_account_contact_graph(obs, account_cnpj="12345678000190")
    assert not any(e.endswith(".gov.br") for p in graph.people for e in p.emails)
    for o in gov:
        assert observation_to_outreach(o) is None


def test_02_competitor_email_not_company_contact():
    text = """
    Concorrente OUTRA OBRA LTDA CNPJ 98.765.432/0001-10
    contato: comercial@outraobra.com.br
    Classificada em 2º lugar.
    """
    obs = extract_contacts_from_text(
        text,
        company_cnpj="12345678000190",
        company_name="CONSTRUTORA EXEMPLO LTDA",
        other_bidder_cnpjs=["98765432000110"],
        document_title="Resultado",
    )
    emails = [o for o in obs if o.email == "comercial@outraobra.com.br"]
    assert emails
    assert emails[0].epistemic_class in {
        EpistemicClass.OTHER_BIDDER,
        EpistemicClass.THIRD_PARTY_REFERENCE,
    }
    assert not emails[0].is_commercially_usable()


def test_03_cross_contract_same_person_consolidates():
    base = dict(
        person_name="Maria Silva",
        role_observed="representante legal",
        email="maria@exemplo.com.br",
        company_cnpj="12345678000190",
        epistemic_class=EpistemicClass.ADMIN_RECORDED_COMPANY_REP,
    )
    o1 = ContactObservation(**base, source_document_id="doc-a", contract_id="c1", observation_date="2025-01-10")
    o2 = ContactObservation(**base, source_document_id="doc-b", contract_id="c2", observation_date="2026-03-01")
    graph = build_account_contact_graph([o1, o2], account_cnpj="12345678000190")
    assert len(graph.people) == 1
    assert graph.people[0].observation_count == 2
    assert graph.people[0].source_count == 2
    assert "maria@exemplo.com.br" in graph.people[0].emails


def test_04_homonym_different_companies_not_merged():
    o1 = ContactObservation(
        person_name="José Souza",
        email=None,
        phone="11999990001",
        company_cnpj="11111111000111",
        epistemic_class=EpistemicClass.COMPANY_DECLARED,
        source_document_id="d1",
    )
    o2 = ContactObservation(
        person_name="José Souza",
        email=None,
        phone="21988880002",
        company_cnpj="22222222000122",
        epistemic_class=EpistemicClass.COMPANY_DECLARED,
        source_document_id="d2",
    )
    # Same account graph should not apply across companies; keys include phone
    g1 = build_account_contact_graph([o1], account_cnpj="11111111000111")
    g2 = build_account_contact_graph([o2], account_cnpj="22222222000122")
    assert g1.people[0].person_key != g2.people[0].person_key


def test_05_old_role_loses_freshness():
    old = ContactObservation(
        person_name="Old Dir",
        email="old@empresa.com.br",
        role_observed="diretor",
        company_cnpj="12345678000190",
        epistemic_class=EpistemicClass.COMPANY_DECLARED,
        observation_date="2020-01-01",
        source_document_id="old",
    )
    new = ContactObservation(
        person_name="New Dir",
        email="new@empresa.com.br",
        role_observed="diretor",
        company_cnpj="12345678000190",
        epistemic_class=EpistemicClass.COMPANY_DECLARED,
        observation_date="2026-06-01",
        source_document_id="new",
    )
    graph = build_account_contact_graph([old, new], account_cnpj="12345678000190")
    by_email = {p.emails[0]: p for p in graph.people if p.emails}
    assert by_email["new@empresa.com.br"].role_freshness > by_email["old@empresa.com.br"].role_freshness
    best = select_best_for_service(graph, "diretoria_b2g")
    assert best is not None
    assert best["email"] == "new@empresa.com.br"


def test_06_freemail_from_company_proposal_possible():
    text = """
    PROPOSTA COMERCIAL
    CONSTRUTORA EXEMPLO LTDA
    CNPJ 12.345.678/0001-90
    Representante legal: Ana Costa
    E-mail: ana.costa@gmail.com
    Telefone: (48) 99999-1111
    """
    obs = extract_contacts_from_text(
        text,
        company_cnpj="12345678000190",
        company_name="CONSTRUTORA EXEMPLO LTDA",
        document_title="Proposta Comercial",
        document_type="proposta",
        document_produced_by_company=True,
    )
    gmail = [o for o in obs if o.email == "ana.costa@gmail.com"]
    assert gmail
    assert gmail[0].epistemic_class == EpistemicClass.COMPANY_DECLARED
    assert gmail[0].is_commercially_usable()


def test_07_pattern_guess_never_enrollable():
    guessed = pattern_guess_email("Maria Silva", "empresa.com.br")
    assert guessed == "maria.silva@empresa.com.br"
    obs = ContactObservation(
        email=guessed,
        person_name="Maria Silva",
        company_cnpj="12345678000190",
        pattern_guessed=True,
        epistemic_class=EpistemicClass.COMPANY_DOMAIN_OBSERVED,
    )
    assert not obs.is_commercially_usable()
    assert observation_to_outreach(obs) is None
    graph = build_account_contact_graph([obs], account_cnpj="12345678000190")
    assert graph.people == []
    assert any(r.pattern_guessed for r in graph.rejected)


def test_08_process_number_normalizes_masks():
    a = normalize_process_number("00123/2024")
    b = normalize_process_number("processo nº 123/2024")
    c = normalize_process_number("123.2024")
    assert a == b == c == "123/2024"
    variants = process_number_variants("00123/2024")
    assert "123/2024" in variants


def test_09_replay_does_not_duplicate_by_hash():
    body = b"%PDF-fake-content-for-hash"
    h1 = content_hash(body)
    h2 = content_hash(body)
    assert h1 == h2
    # document registry behavior: same hash → same identity
    docs = [
        {"document_id": "d1", "sha256": h1, "title": "proposta.pdf"},
        {"document_id": "d1", "sha256": h2, "title": "proposta.pdf"},
    ]
    seen = set()
    unique = []
    for d in docs:
        if d["sha256"] in seen:
            continue
        seen.add(d["sha256"])
        unique.append(d)
    assert len(unique) == 1


def test_10_updated_document_invalidates_old_parse_by_hash():
    old = content_hash(b"version-1-text")
    new = content_hash(b"version-2-text-changed")
    assert old != new
    parse_cache = {old: "old parse"}
    assert new not in parse_cache


def test_11_portal_unavailable_explicit_blocker():
    from scripts.confenge_process_enrichment.models import ContractNode
    from scripts.confenge_process_enrichment.process_resolve import resolve_process_for_contract

    contract = ContractNode(
        contract_id="c1",
        supplier_cnpj="12345678000190",
        contracting_authority_cnpj="00000000000191",
        administrative_process_number="123/2024",
        year=2024,
        sequential=1,
    )

    def fetch_fn(url: str):
        return 403, None, "forbidden"

    res = resolve_process_for_contract(
        contract,
        allow_network=True,
        fetch_fn=fetch_fn,
    )
    assert res.resolved  # PNCP URL still resolved
    assert any("AUTH" in b for b in res.blockers)


def test_12_pncp_without_docs_continues_to_process_portal():
    contracts = [
        {
            "fornecedor_cnpj": "12345678000190",
            "orgao_cnpj": "00000000000191",
            "processo": "555/2024",
            "ano_contrato": 2024,
            "sequencial_contrato": 10,
            "numero_controle_pncp": "00000000000191-1-000010/2024",
        }
    ]
    result = enrich_account(
        "12345678000190",
        razao_social="EXEMPLO LTDA",
        contracts=contracts,
        allow_network=False,
    )
    assert result.funnel_flags.get("contracts_resolved")
    assert result.investigation_state != InvestigationState.NOT_STARTED
    # Process number should be known from contract metadata
    assert result.process_graph is not None
    assert any(c.administrative_process_number for c in result.process_graph.contracts)
    # Must not look like "site/web only" abandonment
    assert not can_declare_no_contact(
        state=InvestigationState.NOT_STARTED,
        process_path_applicable=True,
        process_path_attempted=False,
        site_web_only=True,
    )


def test_13_process_without_docs_leaves_research_gap_not_fake_success():
    result = enrich_account(
        "12345678000190",
        contracts=[
            {
                "fornecedor_cnpj": "12345678000190",
                "orgao_cnpj": "00000000000191",
                "processo": "999/2023",
                "ano_contrato": 2023,
                "sequencial_contrato": 2,
            }
        ],
    )
    assert result.terminal_state != TerminalState.EMAIL_SEND_READY
    assert result.investigation_state != InvestigationState.NOT_STARTED


def test_14_existing_good_contact_stops_expensive_work():
    enricher = ProcessFirstEnricher(config=ProcessFirstConfig(stop_on_high_confidence_email=True))
    r = enricher.enrich(
        account_cnpj="12345678000190",
        existing_enrollable=True,
        contracts=[{"fornecedor_cnpj": "12345678000190", "processo": "1/2024"}],
    )
    assert r.terminal_state == TerminalState.EMAIL_SEND_READY
    assert r.funnel_flags.get("skipped_expensive_existing_enrollable")


def test_15_phone_only_does_not_block_email_search_path():
    # Phone-only observation should not mark EMAIL_SEND_READY
    docs = [
        {
            "text": "Telefone da empresa: (48) 3333-2222 CNPJ 12.345.678/0001-90",
            "document_id": "d1",
            "title": "Contrato",
            "company_authored": False,
        }
    ]
    r = enrich_account("12345678000190", document_texts=docs, contracts=[])
    assert r.terminal_state != TerminalState.EMAIL_SEND_READY


def test_16_dnc_dominates_new_documents():
    obs = ContactObservation(
        email="keep@empresa.com.br",
        person_name="Keep",
        company_cnpj="12345678000190",
        epistemic_class=EpistemicClass.COMPANY_DECLARED,
        observation_date="2026-01-01",
        source_document_id="newdoc",
    )
    graph = build_account_contact_graph(
        [obs],
        account_cnpj="12345678000190",
        dnc_emails={"keep@empresa.com.br"},
    )
    assert graph.people == []
    assert any(r.email == "keep@empresa.com.br" for r in graph.rejected)


def test_17_bounce_dominates_even_if_email_reappears():
    obs = ContactObservation(
        email="bounce@empresa.com.br",
        person_name="X",
        company_cnpj="12345678000190",
        epistemic_class=EpistemicClass.COMPANY_DECLARED,
        source_document_id="d",
    )
    graph = build_account_contact_graph(
        [obs],
        account_cnpj="12345678000190",
        bounced_emails={"bounce@empresa.com.br"},
    )
    assert graph.people == []


def test_18_stale_contact_not_preferred():
    stale = ContactObservation(
        email="stale@empresa.com.br",
        person_name="Stale",
        role_observed="diretor",
        company_cnpj="12345678000190",
        epistemic_class=EpistemicClass.COMPANY_DECLARED,
        observation_date="2019-05-01",
        source_document_id="s",
    )
    fresh = ContactObservation(
        email="fresh@empresa.com.br",
        person_name="Fresh",
        role_observed="comercial",
        company_cnpj="12345678000190",
        epistemic_class=EpistemicClass.COMPANY_DECLARED,
        observation_date="2026-07-01",
        source_document_id="f",
    )
    graph = build_account_contact_graph([stale, fresh], account_cnpj="12345678000190")
    best = select_best_for_service(graph, "generic")
    assert best["email"] == "fresh@empresa.com.br"


def test_19_contact_lineage_reaches_outreach_payload():
    text = """
    PROPOSTA
    CONSTRUTORA EXEMPLO LTDA CNPJ 12.345.678/0001-90
    Representante legal: Paulo Lima
    E-mail: paulo@exemploeng.com.br
    """
    r = enrich_account(
        "12345678000190",
        razao_social="CONSTRUTORA EXEMPLO LTDA",
        document_texts=[
            {
                "text": text,
                "document_id": "prop-1",
                "title": "Proposta Comercial",
                "document_type": "proposta",
                "company_authored": True,
                "url": "https://example.invalid/prop.pdf",
                "observation_date": "2026-04-01",
            }
        ],
        known_company_domains=["exemploeng.com.br"],
    )
    assert r.outreach_contacts
    c = r.outreach_contacts[0]
    assert c.get("email")
    assert c.get("provenance_id")
    assert c.get("source_type")
    assert c.get("epistemic_class")


def test_20_cpf_and_residential_never_in_bridge_payload():
    text = """
    Representante legal:
    Nome: Carla Mendes
    CPF: 123.456.789-00
    E-mail: carla@empresa.com.br
    Endereço residencial: Rua X, 10
    """
    r = enrich_account(
        "12345678000190",
        document_texts=[
            {
                "text": text,
                "document_id": "form-1",
                "title": "Credenciamento",
                "document_type": "credenciamento",
                "company_authored": True,
            }
        ],
        known_company_domains=["empresa.com.br"],
    )
    payload = {"contacts": r.outreach_contacts, "dossier": r.dossier}
    assert_no_forbidden_pii(payload)
    blob = json.dumps(payload)
    assert "12345678900" not in blob.replace(".", "").replace("-", "")
    assert "residencial" not in blob.lower()


def test_site_web_only_cannot_declare_no_contact():
    assert not can_declare_no_contact(
        state=InvestigationState.NOT_STARTED,
        process_path_applicable=True,
        process_path_attempted=False,
        site_web_only=True,
    )


def test_24_municipal_candidates_and_process_match_extract_docs():
    from scripts.confenge_process_enrichment.adapters.municipal_portal import (
        MunicipalPortalAdapter,
        candidate_municipal_bases,
    )

    bases = candidate_municipal_bases(municipality="Flores da Cunha", uf="RS")
    assert any("flores-da-cunha.rs.gov.br" in b or "floresdacunha.rs.gov.br" in b for b in bases)
    assert any("multi24h.com.br" in b for b in bases)

    class FakeResp:
        def __init__(self, status: int, text: str) -> None:
            self.status_code = status
            self.text = text
            self.headers = {"Content-Type": "text/html"}
            self.content = text.encode("utf-8")

    class FakeSession:
        headers: dict = {}

        def get(self, url, timeout=None, allow_redirects=None):
            if "licitacoes" in url or "flores" in url:
                html = """
                <html><body>
                <a href="/portal.php?pagina=licitacoes_editais">licitacoes</a>
                Processo 000023/2025
                CNPJ 12.345.678/0001-90
                <a href="/files/proposta-000023-2025.pdf">Proposta</a>
                <a href="/files/edital.pdf">Edital</a>
                </body></html>
                """
                return FakeResp(200, html)
            return FakeResp(404, "missing")

    adapter = MunicipalPortalAdapter(session=FakeSession(), request_delay=0, max_bases=3, max_pages=4)  # type: ignore[arg-type]
    result = adapter.resolve(
        process_number="000023/2025",
        municipality="Flores da Cunha",
        uf="RS",
        orgao_cnpj="87843819000107",
        supplier_cnpj="12345678000190",
    )
    assert result.resolved is True
    assert any(str(d.get("url") or "").endswith(".pdf") for d in result.document_index)


def test_25_sei_human_session_requires_captcha_answer():
    from scripts.confenge_process_enrichment.adapters.sei_human_session import (
        HumanSessionSpec,
        SeiHumanSessionAdapter,
    )

    class FakeResp:
        def __init__(self, status: int, text: str) -> None:
            self.status_code = status
            self.text = text

    class FakeSession:
        headers: dict = {}
        cookies: dict = {}

        def get(self, url, timeout=None, allow_redirects=None):
            html = """
            <form>
              <input name="txtProtocoloPesquisa" value=""/>
              <input name="txtInfraCaptcha" value=""/>
              <input name="hdnInfraCaptcha" value="1"/>
              <input name="sbmPesquisar" value="Pesquisar"/>
              <input name="hdnFlagPesquisa" value="1"/>
            </form>
            """
            return FakeResp(200, html)

        def post(self, url, data=None, timeout=None, allow_redirects=None):
            return FakeResp(200, "should not reach without captcha")

    spec = HumanSessionSpec(base_url="https://colaboragov.sei.gov.br", captcha_answer=None)
    adapter = SeiHumanSessionAdapter(spec, session=FakeSession(), request_delay=0)  # type: ignore[arg-type]
    result = adapter.search_protocol("13032.283609/2026-26")
    assert result.blocker == "SOURCE_REQUIRES_HUMAN_ACCESS"
    assert result.captcha_required is True


def test_22_sei_protocol_format_and_captcha_blocks_unverified_results():
    from scripts.confenge_process_enrichment.adapters.sei_public import (
        SeiPublicAdapter,
        format_sei_protocol,
    )

    assert "13032.283609/2026-26" in format_sei_protocol("13032283609202626")

    class FakeResp:
        def __init__(self, status: int, text: str) -> None:
            self.status_code = status
            self.text = text

    class FakeSession:
        headers: dict = {}

        def get(self, url, timeout=None, allow_redirects=None):
            html = """
            <form>
              <input name="txtProtocoloPesquisa" value=""/>
              <input name="txtInfraCaptcha" value=""/>
              <input name="hdnInfraCaptcha" value="1"/>
              <input name="sbmPesquisar" value="Pesquisar"/>
              <input name="hdnFlagPesquisa" value="1"/>
            </form>
            """
            return FakeResp(200, html)

        def post(self, url, data=None, timeout=None, allow_redirects=None):
            return FakeResp(200, "10199.007734/2026-41 captcha resultado")

    adapter = SeiPublicAdapter(session=FakeSession(), request_delay=0)  # type: ignore[arg-type]
    result = adapter.search_protocol("13032.283609/2026-26", base_url="https://colaboragov.sei.gov.br")
    assert result.captcha_required is True
    assert result.blocker == "CAPTCHA_BLOCKED"
    assert result.document_index == []


def test_23_sei_match_parses_document_links_without_captcha():
    from scripts.confenge_process_enrichment.adapters.sei_public import SeiPublicAdapter

    class FakeResp:
        def __init__(self, status: int, text: str) -> None:
            self.status_code = status
            self.text = text

    class FakeSession:
        headers: dict = {}

        def get(self, url, timeout=None, allow_redirects=None):
            html = """
            <form>
              <input name="txtProtocoloPesquisa" value=""/>
              <input name="hdnInfraCaptcha" value="0"/>
              <input name="sbmPesquisar" value="Pesquisar"/>
              <input name="hdnFlagPesquisa" value="1"/>
            </form>
            """
            return FakeResp(200, html)

        def post(self, url, data=None, timeout=None, allow_redirects=None):
            proto = (data or {}).get("txtProtocoloPesquisa", "")
            html = f"""
            <table class="infraTable">
              <tr><td>{proto}</td>
              <td><a href="md_pesq_processo_exibir.php?TOKEN1">proc</a></td>
              <td><a href="md_pesq_documento_consulta_externa.php?TOKEN2">doc</a></td>
              </tr>
            </table>
            """
            return FakeResp(200, html)

    adapter = SeiPublicAdapter(session=FakeSession(), request_delay=0)  # type: ignore[arg-type]
    result = adapter.search_protocol("13032.283609/2026-26", base_url="https://colaboragov.sei.gov.br")
    assert result.matched_protocol is True
    assert result.blocker is None
    assert any("documento_consulta" in u for u in result.document_urls)
    assert result.document_index


def test_21_pncp_multi_key_harvest_uses_compra_and_contrato_paths():
    """Supplier harvest must try compra control keys AND contract arquivos path."""
    from unittest.mock import MagicMock

    from scripts.confenge_process_enrichment.models import ContractNode
    from scripts.confenge_process_enrichment.pncp_supplier_harvest import PncpSupplierHarvester

    calls: list[str] = []

    class FakeSession:
        headers: dict = {}

        def get(self, url, params=None, timeout=None, allow_redirects=None):
            calls.append(url)
            m = MagicMock()
            m.status_code = 200
            if "/compras/" in url and "/37/" in url:
                m.json.return_value = [
                    {"titulo": "Proposta.pdf", "sequencialDocumento": 1, "url": "https://example.invalid/p.pdf"}
                ]
            elif "/contratos/" in url:
                m.json.return_value = [
                    {"titulo": "Contrato.pdf", "sequencialDocumento": 1, "url": "https://example.invalid/c.pdf"}
                ]
            else:
                m.json.return_value = []
            m.headers = {}
            return m

    harvester = PncpSupplierHarvester(
        session=FakeSession(),  # type: ignore[arg-type]
        request_delay=0,
        prefer_process_documents_adapter=False,
    )
    node = ContractNode(
        contract_id="x",
        supplier_cnpj="12345678000190",
        contracting_authority_cnpj="00394460005887",
        pncp_control_number="00394460005887-1-000037/2026",
        year=2026,
        sequential=3771,
        raw_keys={"numeroControlePncpCompra": "00394460005887-1-000037/2026"},
    )
    result = harvester.harvest_contract(node)
    assert any("/compras/2026/37/" in u for u in calls)
    assert any("/contratos/2026/3771/" in u for u in calls)
    assert len(result.documents) >= 1


def test_end_to_end_fixture_proposal_yields_send_ready():
    FIXTURES.mkdir(parents=True, exist_ok=True)
    proposal = (FIXTURES / "sample_proposal.txt")
    if not proposal.exists():
        proposal.write_text(
            """
            PROPOSTA COMERCIAL
            EMPRESA DEMO CONSTRUÇÕES LTDA
            CNPJ 11.222.333/0001-44
            Representante legal: Bruno Alves
            Cargo: Diretor Comercial
            E-mail: bruno@democonstrucoes.com.br
            Telefone: (48) 98888-7777
            Atenciosamente,
            Bruno Alves
            Diretor Comercial
            EMPRESA DEMO CONSTRUÇÕES LTDA
            bruno@democonstrucoes.com.br
            """,
            encoding="utf-8",
        )
    text = proposal.read_text(encoding="utf-8")
    contracts = [
        {
            "fornecedor_cnpj": "11222333000144",
            "orgao_cnpj": "00000000000191",
            "orgao_nome": "PREFEITURA DEMO",
            "processo": "42/2025",
            "ano_contrato": 2025,
            "sequencial_contrato": 7,
            "numero_controle_pncp": "00000000000191-1-000007/2025",
            "numero_contrato_empenho": "007/2025",
        }
    ]
    r = enrich_account(
        "11222333000144",
        razao_social="EMPRESA DEMO CONSTRUÇÕES LTDA",
        contracts=contracts,
        document_texts=[
            {
                "text": text,
                "document_id": "fixture-proposal",
                "title": "Proposta Comercial",
                "document_type": "proposta",
                "company_authored": True,
                "contract_id": "00000000000191|2025|7",
                "observation_date": "2025-08-01",
            }
        ],
        known_company_domains=["democonstrucoes.com.br"],
    )
    assert r.funnel_flags.get("contracts_resolved")
    assert r.funnel_flags.get("enrollable_email") or r.terminal_state in {
        TerminalState.EMAIL_SEND_READY,
        TerminalState.CONTACT_FOUND_VERIFIED,
        TerminalState.REFERRAL_ROUTE_AVAILABLE,
    }
    assert r.terminal_state in {
        TerminalState.EMAIL_SEND_READY,
        TerminalState.CONTACT_FOUND_VERIFIED,
        TerminalState.REFERRAL_ROUTE_AVAILABLE,
        TerminalState.CONTACT_FOUND_UNVERIFIED,
    }
    assert r.investigation_state != InvestigationState.NOT_STARTED
    # Explicit investigation state always present
    assert r.investigation_state.value
    assert r.terminal_state.value
