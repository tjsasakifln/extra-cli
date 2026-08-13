"""Literal human-recipient evidence and date-semantics regressions."""

from __future__ import annotations

from scripts.confenge_contact_resolution.adapters.site import _obs_from_page
from scripts.confenge_contact_resolution.discovery.datalake_docs import _normalize_doc_row
from scripts.confenge_contact_resolution.discovery.extract import extract_contacts_from_html
from scripts.confenge_contact_resolution.discovery.public_document_fetch import (
    PublicDocumentResult,
    _contains_exact_cnpj,
    _public_http_url,
)
from scripts.confenge_contact_resolution.enrichment_batch import is_publishable_human_contact
from scripts.confenge_contact_resolution.merge import observations_to_candidates
from scripts.confenge_contact_resolution.models import OwnershipStatus
from scripts.confenge_contact_resolution.send_readiness import evaluate_email_send_ready


def test_site_observation_does_not_fabricate_source_publication_date() -> None:
    observations = _obs_from_page(
        "12345678000199",
        {
            "url": "https://example.com/equipe",
            "contacts": [
                {
                    "name": "Maria de Souza",
                    "cargo": "Diretora Comercial",
                    "email": "maria.souza@example.com",
                }
            ],
        },
    )
    assert len(observations) == 1
    source = observations[0].source
    assert source.source_published_at is None
    assert source.source_date is None
    assert source.observed_at is None


def test_single_public_observation_proves_name_role_and_email_without_inference() -> None:
    observations = _obs_from_page(
        "12345678000199",
        {
            "url": "https://example.com/equipe",
            "observed_at": "2026-08-13T12:00:00Z",
            "contacts": [
                {
                    "name": "Maria de Souza",
                    "cargo": "Diretora Comercial",
                    "email": "maria.souza@example.com",
                }
            ],
        },
    )
    candidate = observations_to_candidates(
        observations,
        cnpj14="12345678000199",
    )[0]
    assert candidate.email_explicitly_published is True
    assert candidate.name_explicitly_published is True
    assert candidate.role_explicitly_published is True
    assert candidate.human_identity_evidence_valid is True
    assert candidate.identity_evidence_urls == ["https://example.com/equipe"]
    assert len(candidate.evidence_sha256) == 64
    assert candidate.freshness_days is None
    assert candidate.freshness == 0.7


def test_name_or_role_from_email_is_never_inferred_as_human_evidence() -> None:
    observations = _obs_from_page(
        "12345678000199",
        {
            "url": "https://example.com/contato",
            "contacts": [{"email": "maria.souza@example.com"}],
        },
    )
    candidate = observations_to_candidates(
        observations,
        cnpj14="12345678000199",
    )[0]
    assert candidate.name is None
    assert candidate.cargo is None
    assert candidate.human_identity_evidence_valid is False


def test_merge_does_not_create_observation_date_for_undated_artifact() -> None:
    observations = _obs_from_page(
        "12345678000199",
        {
            "url": "https://example.com/equipe",
            "contacts": [
                {
                    "name": "Maria de Souza",
                    "cargo": "Diretora Comercial",
                    "email": "maria.souza@example.com",
                }
            ],
        },
    )
    candidate = observations_to_candidates(observations, cnpj14="12345678000199")[0]
    assert candidate.source.observed_at is None
    assert candidate.source.source_published_at is None
    assert candidate.human_identity_evidence_valid is False


def test_html_extractor_associates_only_explicit_named_person_context() -> None:
    contacts = extract_contacts_from_html(
        """
        <section class="team-card">
          <h3>Maria de Souza</h3>
          <p>Diretora Comercial</p>
          <a href="mailto:maria.souza@empresa.com.br">E-mail</a>
        </section>
        <footer>contato@empresa.com.br</footer>
        """,
        source_url="https://empresa.com.br/equipe",
    )
    nominal = next(c for c in contacts if c.get("email") == "maria.souza@empresa.com.br")
    generic = next(c for c in contacts if c.get("email") == "contato@empresa.com.br")
    assert nominal["name"] == "Maria de Souza"
    assert nominal["cargo"] == "Diretora Comercial"
    assert generic.get("name") is None
    assert generic.get("cargo") is None


def test_pre_feed_gate_requires_mx_checked_named_human() -> None:
    observations = _obs_from_page(
        "12345678000199",
        {
            "url": "https://empresa.com.br/equipe",
            "observed_at": "2026-08-13T12:00:00Z",
            "contacts": [
                {
                    "name": "Maria de Souza",
                    "cargo": "Diretora Comercial",
                    "email": "maria.souza@empresa.com.br",
                }
            ],
        },
    )
    candidate = observations_to_candidates(
        observations,
        cnpj14="12345678000199",
        check_mx=True,
        mx_resolver=lambda _domain: True,
    )[0]
    candidate.ownership_status = OwnershipStatus.COMPANY_OWNED.value
    candidate.enrollable = True
    assert is_publishable_human_contact(candidate) is True

    candidate.email = "comercial@empresa.com.br"
    assert is_publishable_human_contact(candidate) is False


def test_document_ingestion_time_is_observation_not_publication() -> None:
    rows = _normalize_doc_row(
        {
            "email": "maria.souza@empresa.com.br",
            "name": "Maria de Souza",
            "cargo": "Diretora Comercial",
            "url": "https://gov.br/documento/1",
            "observed_at": "2026-08-13T12:00:00Z",
        },
        "12345678000199",
    )
    assert rows[0]["source_published_at"] is None
    assert rows[0]["observed_at"] == "2026-08-13T12:00:00Z"


def test_exact_cnpj_match_does_not_cross_boundaries_or_match_longer_number() -> None:
    target = "12345678000199"
    assert _contains_exact_cnpj("CNPJ 12.345.678/0001-99", target)
    assert _contains_exact_cnpj("/documentos/12345678000199/proposta.pdf", target)
    assert not _contains_exact_cnpj("/12 fim 345678000199", target)
    assert not _contains_exact_cnpj("991234567800019988", target)


def test_public_document_strength_is_not_upgraded_by_cnpj_presence_alone() -> None:
    result = PublicDocumentResult(url="https://example.net/documento", cnpj_linked=True)
    result.contacts = [{"email": "pessoa@example.net"}]
    assert result.as_public_docs()[0]["evidence_strength"] == "document_contact"
    result.evidence_strength = "official_cnpj_linked_document"
    assert result.as_public_docs()[0]["evidence_strength"] == "official_cnpj_linked_document"


def test_public_url_guard_rejects_private_dns_answers(monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.confenge_contact_resolution.discovery.public_document_fetch.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))],
    )
    assert _public_http_url("https://public.example/documento") == (False, "non_public_address")


def test_human_gate_rejects_empty_reference_and_invalid_semantic_date() -> None:
    contact = {
        "name": "Maria de Souza",
        "cargo": "Diretora Comercial",
        "email_explicitly_published": True,
        "name_explicitly_published": True,
        "role_explicitly_published": True,
        "human_identity_evidence_valid": True,
        "identity_evidence_urls": [""],
        "evidence_sha256": "a" * 64,
        "source": {
            "source_type": "site",
            "source_url": "https://empresa.example/equipe",
            "observed_at": "not-a-date",
            "evidence_sha256": "a" * 64,
        },
    }
    result = evaluate_email_send_ready(
        company=None,
        email="maria@empresa.example",
        ownership_status="COMPANY_OWNED",
        verification_status="VERIFIED",
        contact=contact,
    )
    assert result.human_recipient_evidence_valid is False
    assert "recipient_evidence_reference_missing" in result.reasons
    assert "recipient_evidence_date_semantics_missing" in result.reasons
