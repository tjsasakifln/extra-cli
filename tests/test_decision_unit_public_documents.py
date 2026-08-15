"""Adversarial fixtures drive the shipped public-document miner.

Expected verdicts live in the fixture manifest. Tests do not reimplement
association and do not start after the unit under test.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.decision_unit_intelligence.contact_discovery.public_documents import (
    DOC_EPISTEMIC_CURRENT,
    DOC_EPISTEMIC_OBSERVED,
    REASON_DOC_IDENTITY_ASSOCIATED,
    DocumentBudget,
    NamedPersonHint,
    PublicDocumentQuery,
    fetched_document_from_text,
    mine_document_text,
    mine_public_documents,
    prefer_document_hit,
    query_from_context,
)
from scripts.decision_unit_intelligence.email_discovery import EmailDiscoveryClass, classify_email_discovery
from scripts.decision_unit_intelligence.models import EpistemicClass
from scripts.decision_unit_intelligence.projection import is_email_safe_for_warmbly
from scripts.decision_unit_intelligence.providers.base import InvestigationContext
from scripts.decision_unit_intelligence.providers.official_documents import OfficialDocumentsProvider
from scripts.decision_unit_intelligence.reachability import classify_channel_observation, draft_to_route

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "public_documents"
EXPECTED = json.loads((FIXTURE_DIR / "expected.json").read_text(encoding="utf-8"))


def _query() -> PublicDocumentQuery:
    spec = EXPECTED["query"]
    return PublicDocumentQuery(
        cnpj=spec["cnpj"],
        legal_name=spec["legal_name"],
        aliases=tuple(spec.get("aliases") or ()),
        domain=spec.get("domain"),
        named_people=tuple(
            NamedPersonHint(name=item["name"], role=item.get("role")) for item in spec.get("named_people") or []
        ),
        contract_refs=tuple(spec.get("contract_refs") or ()),
        budget=DocumentBudget(),
        reference_date=spec.get("reference_date"),
    )


def _document(case_id: str):
    case = EXPECTED["cases"][case_id]
    text = (FIXTURE_DIR / f"{case_id}.txt").read_text(encoding="utf-8")
    readable = case.get("readable")
    return fetched_document_from_text(
        text,
        url=case["url"],
        source_class=case.get("source_class"),
        published_at=case.get("published_at"),
        readable=False if readable is False else None,
        fetched_at="2026-08-15T12:00:00Z",
    )


def _mine_case(case_id: str):
    return mine_document_text(_query(), _document(case_id))


def _codes(result) -> set[str]:
    codes = set(result.reason_codes)
    for item in result.associations:
        codes.update(item.reason_codes)
    return codes


def test_fixtures_cover_required_adversarial_cases():
    required = {
        "signature_name_role_email",
        "ambiguous_table",
        "accountant_email",
        "stale_document",
        "consortium",
        "holding",
        "homonym",
        "generic_no_contact",
        "unreadable",
        "company_mismatch",
        "header_blesses_foreign_signature",
        "foreign_corporate_mailbox",
        "header_same_domain_other_person",
    }
    assert required <= set(EXPECTED["cases"])
    for case_id in required:
        assert (FIXTURE_DIR / f"{case_id}.txt").exists()


def test_each_fixture_drives_shipped_miner_to_manifest_verdict():
    for case_id, spec in EXPECTED["cases"].items():
        result = _mine_case(case_id)
        codes = _codes(result)
        missing = set(spec["must_contain"]) - codes
        leaked = set(spec.get("must_not_contain") or []) & codes
        assert not missing, f"{case_id} missing {missing}; got {sorted(codes)}"
        assert not leaked, f"{case_id} leaked {leaked}; got {sorted(codes)}"
        associated = [item for item in result.associations if item.associated]
        assert bool(associated) is bool(spec["associated"]), f"{case_id} associated={associated}"
        if spec.get("email"):
            emails = {item.email for item in result.associations}
            assert (
                spec["email"] in emails
                or any(spec["email"] == (ch.channel_value or "") for ch in result.channels)
                or spec["email"] in {ev.value for ev in result.evidence}
            )
        if spec.get("person_name") and spec["associated"]:
            assert any(item.person_name == spec["person_name"] for item in associated)
        if spec.get("stale"):
            assert any(item.stale for item in result.associations)
        if spec.get("discarded"):
            assert any(item.discarded for item in result.associations)
        for item in result.associations:
            assert item.current_identity_proven is False
            assert item.document_epistemic_class == DOC_EPISTEMIC_OBSERVED
            assert item.document_epistemic_class != DOC_EPISTEMIC_CURRENT
        for ev in result.evidence:
            assert ev.extra.get("email_discovery_class") != EmailDiscoveryClass.EMAIL_VALIDATED.value
            assert ev.extra.get("current_identity_proven") is False
            assert ev.source_url
            assert ev.document_sha256
            assert ev.observed_at
            assert ev.extraction_method
            assert ev.extra.get("source_class")


def test_document_header_does_not_bless_another_firm_signature():
    result = _mine_case("header_blesses_foreign_signature")
    pedro = [item for item in result.associations if item.email == "pedro.santos@outrapavimentacao.com.br"]
    assert pedro
    assert all(item.associated is False for item in pedro)
    assert all(item.company_matched is False for item in pedro)
    assert "DOC_IDENTITY_ASSOCIATED" not in _codes(result)
    assert "DOC_THIRD_PARTY_DOMAIN" in _codes(result)


def test_foreign_corporate_mailbox_is_not_identity_even_in_our_signature():
    result = _mine_case("foreign_corporate_mailbox")
    hits = [item for item in result.associations if item.email == "joao.silva@outrapavimentacao.com.br"]
    assert hits
    assert all(item.associated is False for item in hits)
    assert all(item.discarded for item in hits)
    assert "DOC_IDENTITY_ASSOCIATED" not in _codes(result)
    assert "DOC_THIRD_PARTY_DOMAIN" in _codes(result)


def test_header_mention_does_not_associate_same_domain_signature_without_unit_company():
    result = _mine_case("header_same_domain_other_person")
    hits = [item for item in result.associations if item.email == "pedro.santos@empresaexemplo.com.br"]
    assert hits
    assert all(item.associated is False for item in hits)
    assert all(item.company_matched is False for item in hits)
    assert "DOC_IDENTITY_ASSOCIATED" not in _codes(result)


def test_signature_fixture_is_strong_association_without_email_validated():
    result = _mine_case("signature_name_role_email")
    hit = next(item for item in result.associations if item.associated)
    assert hit.email == "joao.silva@empresaexemplo.com.br"
    assert hit.person_name == "João da Silva"
    assert hit.role
    assert REASON_DOC_IDENTITY_ASSOCIATED in hit.reason_codes
    channel = next(ch for ch in result.channels if ch.channel_value == hit.email)
    assert channel.extra["email_discovery_class"] != EmailDiscoveryClass.EMAIL_VALIDATED.value
    assert channel.extra["identity_explicitly_associated"] is False
    assert channel.extra["document_identity_associated"] is True
    assert channel.extra["document_epistemic_class"] == DOC_EPISTEMIC_OBSERVED


def test_loose_proximity_is_not_proof():
    document = fetched_document_from_text(
        "João da Silva trabalha em obras no Sul. No rodapé: suporte@provedor.net",
        url="https://blog.exemplo.net/nota",
        fetched_at="2026-08-15T12:00:00Z",
        source_class="indexed_public_file",
    )
    result = mine_document_text(_query(), document)
    assert not any(item.associated for item in result.associations)
    assert REASON_DOC_IDENTITY_ASSOCIATED not in _codes(result)


def test_miner_launch_is_deterministic_on_same_document():
    document = _document("signature_name_role_email")
    query = _query()
    first = mine_public_documents(query, documents=[document], enrich_campaign=False)
    second = mine_public_documents(query, documents=[document], enrich_campaign=False)
    assert [item.email for item in first.associations] == [item.email for item in second.associations]
    assert [item.reason_codes for item in first.associations] == [item.reason_codes for item in second.associations]
    assert [doc.sha256 for doc in first.documents] == [doc.sha256 for doc in second.documents]
    assert first.reason_codes == second.reason_codes
    for ev in first.evidence + second.evidence:
        assert ev.source_url
        assert ev.document_sha256
        assert ev.evidence_snippet
        assert ev.extraction_method
        assert ev.extra.get("source_class")
        assert ev.extra.get("document_epistemic_class") == DOC_EPISTEMIC_OBSERVED
        assert ev.extra.get("email_discovery_class") != EmailDiscoveryClass.EMAIL_VALIDATED.value


def test_official_documents_provider_is_additive_entry_point():
    document = _document("signature_name_role_email")
    provider = OfficialDocumentsProvider(documents=[document], enrich_campaign=False)
    context = InvestigationContext(
        cnpj=EXPECTED["query"]["cnpj"],
        legal_name=EXPECTED["query"]["legal_name"],
        extra={"domain": EXPECTED["query"]["domain"], "named_people": EXPECTED["query"]["named_people"]},
    )
    first = provider.collect(context)
    second = provider.collect(context)
    assert first.attempts[0].extra["document_hashes"] == second.attempts[0].extra["document_hashes"]
    assert first.attempts[0].extra["reason_codes"] == second.attempts[0].extra["reason_codes"]
    assert any(ch.channel_value == "joao.silva@empresaexemplo.com.br" for ch in first.channels)
    assert all(
        ev.extra.get("email_discovery_class") != EmailDiscoveryClass.EMAIL_VALIDATED.value for ev in first.evidence
    )
    rebuilt = query_from_context(context)
    assert rebuilt.cnpj == EXPECTED["query"]["cnpj"]
    assert rebuilt.domain == EXPECTED["query"]["domain"]


def test_canonical_promoter_does_not_email_validate_document_observation():
    mined = _mine_case("signature_name_role_email")
    for ev in mined.evidence:
        assert ev.epistemic_class == EpistemicClass.OBSERVED
        assert ev.extra.get("document_epistemic_class") == DOC_EPISTEMIC_OBSERVED
        assert ev.extra.get("email_discovery_class") != EmailDiscoveryClass.EMAIL_VALIDATED.value
    channel = next(item for item in mined.channels if item.channel_value and "@" in item.channel_value)
    draft = classify_channel_observation(channel, candidate=None, suitable_person=bool(channel.person_name))
    route = draft_to_route(draft, company_entity_id=EXPECTED["query"]["cnpj"])
    email_safe = is_email_safe_for_warmbly(route)
    klass = classify_email_discovery(
        route.channel_value,
        epistemic=route.epistemic_class,
        identity_associated=bool((channel.extra or {}).get("document_identity_associated")),
        email_safe_policy=email_safe,
    )
    assert email_safe is False
    assert klass != EmailDiscoveryClass.EMAIL_VALIDATED
    assert (channel.extra or {}).get("document_epistemic_class") == DOC_EPISTEMIC_OBSERVED
    assert (channel.extra or {}).get("current_identity_proven") is False


def test_template_and_echo_hits_are_not_seeded():
    assert prefer_document_hit("https://pncp.gov.br/app/contratos/82951344000140/2024/6")
    assert prefer_document_hit("https://doe.sc.gov.br/2024/ata-empresa.pdf")
    assert not prefer_document_hit(
        "https://www.jucespsorocaba.com.br/wp-content/uploads/2020/10/Ltda/MODELO-DE-ALTERACAO-CONTRATUAL.pdf"
    )
    assert not prefer_document_hit("https://casadosdados.com.br/solucao/cnpj/exemplo")
    assert not prefer_document_hit("https://pastebin.com/raw/leaked")


def test_runner_wires_official_documents_additively():
    from scripts.decision_unit_intelligence.runner import default_providers

    source = Path("scripts/decision_unit_intelligence/runner.py").read_text(encoding="utf-8")
    assert "OfficialDocumentsProvider(backend=backend, budget=budget)" in source
    official = next(
        item for item in default_providers(search_backend="off") if item.provider_id == "official_documents"
    )
    assert official.backend is None
    result = official.collect(InvestigationContext(cnpj="12345678000190"))
    assert result.attempts
    assert result.attempts[0].status == "skipped"
    assert result.attempts[0].reason != "no_contact"
    assert "EMAIL_VALIDATED" not in json.dumps(result.extra)


def test_isolated_cli_entry_point_is_wired():
    from scripts.decision_unit_intelligence.contact_discovery.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["--out", "/tmp/docs-out", "--limit", "30", "--search-backend", "off"])
    assert args.func.__name__ == "cmd_mine_docs"
    assert args.limit == 30


def test_mx_is_not_consulted_and_does_not_become_identity():
    mined = _mine_case("signature_name_role_email")
    dumped = json.dumps(mined.to_dict(), ensure_ascii=False)
    assert "MX_PRESENT" not in dumped
    assert "dns" not in dumped.lower() or "dns" not in json.dumps(
        [item.to_dict() for item in mined.associations], ensure_ascii=False
    )
    assert all(item.current_identity_proven is False for item in mined.associations)
