"""Email verification must never collapse technical plausibility into identity."""

from pathlib import Path

from scripts.decision_unit_intelligence.email_verification import (
    DnsLookupError,
    PassiveEmailVerifier,
    verify_email_routes,
)
from scripts.decision_unit_intelligence.models import (
    ChannelObservation,
    ChannelType,
    EpistemicClass,
    PersonObservation,
    PersonRelation,
)
from scripts.decision_unit_intelligence.operator_pack import build_card
from scripts.decision_unit_intelligence.orchestrator import investigate_account
from scripts.decision_unit_intelligence.web_discovery import JsonDiscoveryCache


class FakeDns:
    def __init__(self, records: dict[tuple[str, str], list[str]] | None = None) -> None:
        self.records = records or {}
        self.calls: list[tuple[str, str]] = []

    def query(self, domain: str, record_type: str) -> list[str]:
        self.calls.append((domain, record_type))
        key = (domain, record_type)
        if key not in self.records:
            raise DnsLookupError("NXDOMAIN")
        return self.records[key]


def test_mx_present_is_not_mailbox_or_identity_proof():
    verifier = PassiveEmailVerifier(FakeDns({("empresa.com.br", "MX"): ["10 mx.empresa.com.br."]}))
    report = verifier.verify("joao.silva@empresa.com.br")
    assert report.syntax == "VALID"
    assert report.mx == "MX_PRESENT"
    assert report.smtp == "SKIPPED_POLICY"
    assert report.catch_all == "UNKNOWN_NOT_PROBED"
    assert report.final_classification == "UNVERIFIED_DIRECT_CANDIDATE"
    assert "MX_PRESENT_NOT_MAILBOX_PROOF" in report.reason_codes


def test_null_mx_and_generic_role_mailbox_remain_unsuitable_for_named_identity():
    verifier = PassiveEmailVerifier(FakeDns({("empresa.example", "MX"): ["0 ."]}))
    report = verifier.verify("licitacoes@empresa.example")
    assert report.mx == "NULL_MX"
    assert report.final_classification == "GENERIC_ROLE_MAILBOX"
    assert "NULL_MX_DECLINES_EMAIL" in report.reason_codes


def test_domain_cache_avoids_repeating_dns_and_keeps_each_email_classification(tmp_path: Path):
    dns = FakeDns({("empresa.com.br", "MX"): ["10 mx.empresa.com.br."]})
    verifier = PassiveEmailVerifier(dns, cache=JsonDiscoveryCache(tmp_path, ttl_days=7))
    first = verifier.verify("joao.silva@empresa.com.br")
    second = verifier.verify("contato@empresa.com.br")
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert len(dns.calls) == 1
    assert second.final_classification == "GENERIC_MAILBOX"
    assert "CACHE_HIT" in second.reason_codes


def test_invalid_syntax_never_touches_dns():
    dns = FakeDns()
    report = PassiveEmailVerifier(dns).verify("not-an-email")
    assert report.syntax == "INVALID"
    assert report.dns == "NOT_CHECKED"
    assert not dns.calls


def test_operator_projection_exposes_verification_without_promoting_identity():
    account = investigate_account(
        cnpj="12345678000190",
        legal_name="EMPRESA LTDA",
        service="reajuste_14133",
        why_now="contrato ativo",
        people=[
            PersonObservation(
                observation_id="person-1",
                company_entity_id="12345678000190",
                person_name="JOAO SILVA",
                observed_role="Diretor de Engenharia",
                relation=PersonRelation.COMPANY_MEMBER,
                source_type="company_website",
                source_url="https://empresa.com.br/diretoria",
                epistemic_class=EpistemicClass.OBSERVED,
            )
        ],
        channels=[
            ChannelObservation(
                observation_id="email-1",
                company_entity_id="12345678000190",
                channel_type=ChannelType.DIRECT_EMAIL,
                channel_value="joao.silva@empresa.com.br",
                person_name="JOAO SILVA",
                source_type="company_website",
                source_url="https://empresa.com.br/diretoria",
                epistemic_class=EpistemicClass.OBSERVED,
            )
        ],
        infer_email=False,
        discovery_extra={
            "domain_resolution": {
                "canonical_domain": "empresa.com.br",
                "confidence": "HIGH",
                "alternatives": [],
                "reason_codes": ["KNOWN_SITE_OBSERVED"],
            }
        },
    )
    reports = verify_email_routes(
        account.routes,
        PassiveEmailVerifier(FakeDns({("empresa.com.br", "MX"): ["10 mx.empresa.com.br."]})),
    )
    account.extra["email_verification"] = [report.to_dict() for report in reports]
    card = build_card(account)
    assert card["domain_resolution"]["canonical_domain"] == "empresa.com.br"
    assert card["email_verification"]["mx"] == "MX_PRESENT"
    assert card["email_verification"]["final_classification"] == "UNVERIFIED_DIRECT_CANDIDATE"
    assert card["email_verification"].get("identity_proven") is None
