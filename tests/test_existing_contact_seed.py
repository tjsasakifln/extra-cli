"""Historical contact reconciliation is the first durable waterfall tier."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.company_registry.models import OfficialCompanyRecord, OfficialMatchStatus
from scripts.decision_unit_intelligence.controlled_email import (
    EmailRouteClass,
    classify_account_email_routes,
)
from scripts.decision_unit_intelligence.projection import project_warmbly_outreach
from scripts.decision_unit_intelligence.providers.base import InvestigationContext
from scripts.decision_unit_intelligence.providers.existing_contacts import (
    ExistingContactsProvider,
    bind_contact_seeds_to_input_version,
    manifest_contact_seed_inputs,
)
from scripts.decision_unit_intelligence.providers.official_company_registry import (
    OfficialCompanyRegistryProvider,
)
from scripts.decision_unit_intelligence.runner import run_account


def _write_seed(path: Path) -> None:
    rows = [
        {
            "cnpj14": "11222333000181",
            "official_domain": "acme.example.com",
            "contacts": [
                {
                    "source_contact_id": "historical-role-route",
                    "email": "licitacoes@acme.example.com",
                    "source": "contact_page",
                    "source_url": "https://acme.example.com/contato",
                    "source_date": "2026-08-24",
                    "observed_at": "2026-08-24T10:00:00Z",
                    "ownership_status": "COMPANY_OWNED",
                    "verification_status": "OFFICIAL_SOURCE",
                    "email_explicitly_published": True,
                }
            ],
        },
        {
            "cnpj14": "44555666000177",
            "contacts": [],
        },
    ]
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_seed_manifest_is_content_bound_and_deduplicated(tmp_path: Path) -> None:
    seed = tmp_path / "contacts.jsonl"
    _write_seed(seed)

    manifested = manifest_contact_seed_inputs([str(seed), str(seed)])

    assert len(manifested) == 1
    assert manifested[0]["path"] == str(seed.resolve())
    assert len(manifested[0]["sha256"]) == 64
    bound = bind_contact_seeds_to_input_version("target-fit.abc", manifested)
    assert bound.startswith("target-fit.abc.contacts-")
    assert bind_contact_seeds_to_input_version("target-fit.abc", []) == "target-fit.abc"


def test_seed_provider_preserves_public_source_and_unknown_person(tmp_path: Path) -> None:
    seed = tmp_path / "contacts.jsonl"
    _write_seed(seed)
    inputs = manifest_contact_seed_inputs([str(seed)])

    result = ExistingContactsProvider(inputs).collect(
        InvestigationContext(cnpj="11222333000181")
    )

    assert result.terminal == "hit"
    assert len(result.channels) == 1
    assert result.channels[0].person_name is None
    assert result.channels[0].source_url == "https://acme.example.com/contato"
    assert result.channels[0].evidence_id == result.evidence[0].evidence_id
    assert result.extra["domain_resolution"]["canonical_domain"] == "acme.example.com"


def test_seed_hash_change_is_a_factual_provider_failure(tmp_path: Path) -> None:
    seed = tmp_path / "contacts.jsonl"
    _write_seed(seed)
    inputs = manifest_contact_seed_inputs([str(seed)])
    seed.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="CONTACT_SEED_HASH_MISMATCH"):
        ExistingContactsProvider(inputs).collect(
            InvestigationContext(cnpj="11222333000181")
        )


def test_run_account_uses_seed_before_public_search_without_minting_person(tmp_path: Path) -> None:
    seed = tmp_path / "contacts.jsonl"
    _write_seed(seed)
    inputs = manifest_contact_seed_inputs([str(seed)])

    account = run_account(
        "11222333000181",
        search_backend="off",
        contact_seed_inputs=inputs,
        account_meta={"razao_social": "ACME ENGENHARIA LTDA"},
    )
    ranking = classify_account_email_routes(account)

    assert account.legal_name == "ACME ENGENHARIA LTDA"
    assert ranking.preferred_initial_route is not None
    assert ranking.preferred_initial_route.route_class == EmailRouteClass.ROLE_OR_DEPARTMENT
    assert ranking.preferred_initial_route.email_validated is False
    assert ranking.preferred_initial_route.person_name is None
    assert account.ledger.search_queries == []


def test_official_registry_exact_cnpj_accepts_public_company_mailbox_without_person() -> None:
    cnpj = "11222333000181"
    provider = OfficialCompanyRegistryProvider(
        lookup=lambda _cnpj: OfficialCompanyRecord(
            cnpj=cnpj,
            official_match_status=OfficialMatchStatus.MATCHED.value,
            official_authority="RECEITA_FEDERAL",
            official_release_id="rfb-2026-07",
            legal_name="Construtora Cadastro Ltda",
            email="contato@construtoracadastro.com.br",
            fetched_from_local_registry_at="2026-08-24T12:00:00Z",
            source_provenance={
                "release_id": "rfb-2026-07",
                "source_label": "rfb_public_cadastral",
            },
        )
    )

    account = run_account(cnpj, providers=[provider], infer_email=False)
    projected = project_warmbly_outreach(account)

    assert projected["preferred_initial_route"]["route_class"] == "GENERIC_COMPANY"
    assert projected["preferred_initial_route"]["person_name"] is None
    route = next(item for item in account.routes if item.channel_value == "contato@construtoracadastro.com.br")
    assert route.source_type == "company_registry"
    assert route.extra["official_domain"] == "construtoracadastro.com.br"


def test_official_registry_exact_cnpj_accepts_public_freemail_without_person() -> None:
    cnpj = "11222333000181"
    provider = OfficialCompanyRegistryProvider(
        lookup=lambda _cnpj: OfficialCompanyRecord(
            cnpj=cnpj,
            official_match_status=OfficialMatchStatus.MATCHED.value,
            official_authority="RECEITA_FEDERAL",
            official_release_id="rfb-2026-07",
            legal_name="Construtora Cadastro Ltda",
            email="construtoracadastro@gmail.com",
            fetched_from_local_registry_at="2026-08-24T12:00:00Z",
            source_provenance={
                "release_id": "rfb-2026-07",
                "source_label": "rfb_public_cadastral",
            },
        )
    )

    projected = project_warmbly_outreach(run_account(cnpj, providers=[provider], infer_email=False))
    preferred = projected["preferred_initial_route"]

    assert preferred["route_class"] == "PUBLIC_COMPANY_FREEMAIL"
    assert preferred["mailbox_person_evidence"] == "UNKNOWN"
    assert preferred["person_name"] is None
    assert preferred["email_validated"] is False


def test_unavailable_official_registry_is_recorded_without_stopping_later_sources() -> None:
    cnpj = "11222333000181"
    provider = OfficialCompanyRegistryProvider(
        lookup=lambda _cnpj: OfficialCompanyRecord(
            cnpj=cnpj,
            official_match_status=OfficialMatchStatus.OFFICIAL_REGISTRY_UNAVAILABLE.value,
            official_authority="RECEITA_FEDERAL",
            source_provenance={"reason": "no_active_release"},
        )
    )
    result = provider.collect(InvestigationContext(cnpj=cnpj))

    assert result.attempts[0].reason == "OFFICIAL_REGISTRY_UNAVAILABLE"
    assert result.attempts[0].blocked is False
    assert result.attempts[0].extra["failures"] == ["OFFICIAL_REGISTRY_UNAVAILABLE"]
