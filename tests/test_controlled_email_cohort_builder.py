"""Bounded controlled-email cohort producer keeps PII private and gates hard.

Drives the shipped producer against a synthetic `confenge.outreach.v1` export.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

from scripts.ops.build_controlled_email_cohort import build, select_cohort
from scripts.warmbly_bridge import SCHEMA_OUTREACH


def _contact(
    email: str,
    *,
    route_class: str = "GENERIC_COMPANY",
    eligible: bool = True,
    preferred: bool = True,
    **overrides: Any,
) -> dict[str, Any]:
    contact = {
        "email": email,
        "route_class": route_class,
        "controlled_email_eligible": eligible,
        "preferred_initial": preferred,
        "recommended": preferred,
        "mailbox_company_evidence": "OBSERVED",
        "route_suppression": "NONE",
        "source_url": f"https://{email.split('@', 1)[1]}/contato",
        "provenance": {"source_type": "contact_page"},
    }
    contact.update(overrides)
    return contact


def _lead(cnpj14: str, contacts: list[dict[str, Any]], *, website: str | None = None) -> dict[str, Any]:
    """A lead whose registered name matches its own domain, as a real one does.

    The cohort refuses a route whose evidence domain is not credible for the
    company name, so a fixture with mismatched name and domain is not a neutral
    default — it is the wrong-company case.
    """
    first = next((c.get("email", "") for c in contacts if c.get("email")), "")
    label = (first.split("@", 1)[1].split(".", 1)[0] if "@" in first else "exemplar").upper()
    return {
        "source_lead_id": f"lead-{cnpj14}",
        "company": {
            "cnpj14": cnpj14,
            "razao_social": f"{label} CONSTRUCOES LTDA",
            "website": website,
        },
        "contacts": contacts,
    }


def _write_export(tmp_path: Path, leads: list[dict[str, Any]]) -> Path:
    feed_dir = tmp_path / "06_warmbly_feed"
    feed_dir.mkdir(parents=True)
    (feed_dir / "chunk_0000.json").write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_OUTREACH,
                "generated_at": "2026-08-22T00:00:00Z",
                "pagination": {"has_more": False},
                "source": {"system": "extra-cli", "repo_sha": "0" * 40, "run_id": "run-test"},
                "leads": leads,
            }
        ),
        encoding="utf-8",
    )
    (feed_dir / "manifest.json").write_text(
        json.dumps(
            {
                "lead_count": len(leads),
                "source": {"repo_sha": "0" * 40, "run_id": "run-test"},
                "authoritative_source_freshness": {
                    "contract_version": "PNCP_CONTRACT_FRESHNESS/1.0",
                    "status": "FRESH",
                    "reason_codes": [],
                    "as_of": "2026-08-22T00:00:00Z",
                    "expires_at": "2999-01-01T00:00:00Z",
                    "run_id": "contracts-test",
                },
            }
        ),
        encoding="utf-8",
    )
    return feed_dir


def test_stale_source_feed_is_refused_before_private_cohort_write(tmp_path: Path):
    feed_dir = _write_export(
        tmp_path,
        [_lead("11111111000191", [_contact("contato@alphaengenharia.com.br")])],
    )
    manifest_path = feed_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["authoritative_source_freshness"]["status"] = "STALE"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with __import__("pytest").raises(ValueError, match="STALE, not FRESH"):
        build(
            feed_dir=feed_dir,
            private_root=tmp_path / "private",
            limit=10,
            as_of="2026-08-22",
            run_stamp="stale",
        )
    assert not (tmp_path / "private" / "stale").exists()


def test_expired_freshness_attestation_is_refused(tmp_path: Path):
    feed_dir = _write_export(
        tmp_path,
        [_lead("11111111000191", [_contact("contato@alphaengenharia.com.br")])],
    )
    manifest_path = feed_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["authoritative_source_freshness"]["expires_at"] = "2000-01-01T00:00:00Z"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with __import__("pytest").raises(ValueError, match="expired"):
        build(
            feed_dir=feed_dir,
            private_root=tmp_path / "private",
            limit=10,
            as_of="2026-08-22",
            run_stamp="expired",
        )
    assert not (tmp_path / "private" / "expired").exists()


def test_risky_and_suppressed_never_enter_the_cohort():
    leads = [
        _lead("11111111000191", [_contact("contato@alphaengenharia.com.br")]),
        _lead(
            "22222222000172",
            [_contact("chute@betaengenharia.com.br", route_class="PROBABILISTIC_OR_RISKY", eligible=False)],
        ),
        _lead("33333333000153", [_contact("contato@gamaengenharia.com.br", route_suppression="OPT_OUT")]),
        _lead("44444444000134", [_contact("contato@deltaengenharia.com.br", eligible=False)]),
        _lead("55555555000115", [_contact("contato@epsilon.com.br", mailbox_purpose_send_blocked=True)]),
    ]
    members, stats = select_cohort(leads, limit=50)
    assert [m["company"]["cnpj14"] for m in members] == ["11111111000191"]
    assert stats["route_class_distribution"]["GENERIC_COMPANY"] == 1
    assert stats["funnel"]["RISKY"] == 1
    assert stats["funnel"]["suppressed"] == 1


def test_exactly_one_preferred_route_per_account():
    leads = [
        _lead(
            "11111111000191",
            [
                _contact("contato@alphaengenharia.com.br"),
                _contact("licitacoes@alphaengenharia.com.br", route_class="ROLE_OR_DEPARTMENT"),
            ],
        ),
        _lead("22222222000172", [_contact("contato@betaengenharia.com.br", preferred=False)]),
    ]
    members, stats = select_cohort(leads, limit=50)
    assert members == []
    assert stats["funnel"]["double_preferred"] == 1


def test_the_same_ambiguous_mailbox_blocks_both_accounts():
    shared = "contato@grupocompartilhado.com.br"
    leads = [
        _lead("11111111000191", [_contact(shared)]),
        _lead("22222222000172", [_contact(shared)]),
    ]
    members, _ = select_cohort(leads, limit=50)
    assert members == []


def test_cohort_is_capped_without_padding():
    leads = [_lead(f"{n:011d}191"[:14], [_contact(f"contato@empresa{n}.com.br")]) for n in range(1, 8)]
    members, stats = select_cohort(leads, limit=3)
    assert len(members) == 3
    assert stats["funnel"]["preferred_initial"] == 7


def test_private_feed_is_0600_and_the_manifest_carries_no_pii(tmp_path):
    feed_dir = _write_export(
        tmp_path,
        [
            _lead(
                "11111111000191", [_contact("contato@alphaengenharia.com.br")], website="https://alphaengenharia.com.br"
            ),
            _lead(
                "22222222000172",
                [_contact("licitacoes@betaengenharia.com.br", route_class="ROLE_OR_DEPARTMENT")],
                website="https://betaengenharia.com.br",
            ),
        ],
    )
    private_root = tmp_path / "private"
    manifest = build(
        feed_dir=feed_dir,
        private_root=private_root,
        limit=50,
        as_of="2026-08-22",
        run_stamp="20260822T000000Z",
    )

    assert manifest["member_count"] == 2
    assert manifest["auto_send"] is False
    assert manifest["REAL_EMAIL_SENT"] is False
    assert manifest["smtp"] == "none"
    assert manifest["route_class_distribution"] == {
        "DIRECT_PERSON": 0,
        "ROLE_OR_DEPARTMENT": 1,
        "GENERIC_COMPANY": 1,
        "PUBLIC_COMPANY_FREEMAIL": 0,
        "PROBABILISTIC_OR_RISKY": 0,
    }
    assert sum(manifest["route_class_distribution"].values()) == manifest["member_count"]

    feed_path = Path(manifest["private_feed_path"])
    assert stat.S_IMODE(os.stat(feed_path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(feed_path.parent).st_mode) == 0o700

    feed = json.loads(feed_path.read_text(encoding="utf-8"))
    assert feed["schema_version"] == SCHEMA_OUTREACH
    assert feed["auto_send"] is False
    assert all(len(lead["contacts"]) == 1 for lead in feed["leads"])

    redacted = Path(manifest["manifest_path"]).read_text(encoding="utf-8")
    assert "@" not in redacted
    assert "11111111000191" not in redacted
    assert "alphaengenharia.com.br" in redacted  # public host is evidence, not PII


def test_feed_hash_matches_the_bytes_on_disk(tmp_path):
    import hashlib

    feed_dir = _write_export(tmp_path, [_lead("11111111000191", [_contact("contato@alphaengenharia.com.br")])])
    manifest = build(
        feed_dir=feed_dir,
        private_root=tmp_path / "private",
        limit=50,
        as_of="2026-08-22",
        run_stamp="20260822T000000Z",
    )
    body = Path(manifest["private_feed_path"]).read_bytes()
    assert hashlib.sha256(body).hexdigest() == manifest["feed_sha256"]


def test_a_stale_stamp_cannot_smuggle_an_untrustworthy_route():
    """An export from an older classifier is re-judged under the shipped policy."""
    smuggled = _contact(
        "contato@sustainconsulting.llc",
        source_url="https://multisend-unsubscribe.gmail.com/x",
        provenance={"source_type": "web_search"},
    )
    members, stats = select_cohort(
        [_lead("11111111000191", [smuggled])],
        limit=50,
    )
    assert members == []
    assert stats["funnel"]["blocked_stamp_disagrees_with_shipped_policy"] == 1


def test_a_route_the_shipped_policy_confirms_still_passes():
    honest = _contact(
        "contato@alphaengenharia.com.br",
        source_url="https://alphaengenharia.com.br/contato",
        provenance={"source_type": "contact_page"},
    )
    members, _ = select_cohort(
        [_lead("11111111000191", [honest], website="https://alphaengenharia.com.br")],
        limit=50,
    )
    assert len(members) == 1


def test_official_domain_ladder_matches_the_exporter():
    from scripts.ops.build_controlled_email_cohort import resolve_official_domain

    lead = _lead("11111111000191", [], website="https://www.AlphaEngenharia.com.br/quem-somos")
    assert resolve_official_domain(lead, {}) == "alphaengenharia.com.br"
    assert resolve_official_domain(lead, {"official_domain": "betaengenharia.com.br"}) == "betaengenharia.com.br"
    assert resolve_official_domain(_lead("11111111000191", []), {}) is None


def test_a_route_on_its_own_official_domain_survives_the_recheck():
    """The exporter's official domain must not be lost, or good routes die."""
    contact = _contact(
        "contato@alphaengenharia.com.br",
        source_url="https://alphaengenharia.com.br/contato",
        official_domain="alphaengenharia.com.br",
    )
    members, _ = select_cohort([_lead("11111111000191", [contact])], limit=50)
    assert len(members) == 1


def test_every_funnel_and_route_class_key_ships_even_at_zero():
    """A zero is a finding. Consumers must never have to guess an absent key."""
    from scripts.ops.build_controlled_email_cohort import FUNNEL_KEYS

    _, stats = select_cohort([], limit=50)
    for key in FUNNEL_KEYS:
        assert stats["funnel"][key] == 0, key
    for key in ("DIRECT_PERSON", "ROLE_OR_DEPARTMENT", "GENERIC_COMPANY", "PUBLIC_COMPANY_FREEMAIL"):
        assert key in stats["funnel"], key
    assert stats["route_class_distribution"]["PROBABILISTIC_OR_RISKY"] == 0
    assert stats["route_class_distribution"]["DIRECT_PERSON"] == 0


def test_the_published_official_domain_feeds_the_recheck():
    """The exporter publishes the domain it judged against; the recheck reuses it."""
    from scripts.ops.build_controlled_email_cohort import resolve_official_domain

    lead = _lead("11111111000191", [])
    lead["company"]["official_domain"] = "alphaengenharia.com.br"
    assert resolve_official_domain(lead, {}) == "alphaengenharia.com.br"

    contact = _contact(
        "contato@alphaengenharia.com.br",
        source_url="https://alphaengenharia.com.br/fale-conosco",
    )
    lead_with_contact = _lead("11111111000191", [contact])
    lead_with_contact["company"]["official_domain"] = "alphaengenharia.com.br"
    members, stats = select_cohort([lead_with_contact], limit=50)
    assert len(members) == 1
    assert stats["funnel"]["official_domain"] == 1
    assert stats["funnel"]["no_domain"] == 0


def test_the_sample_publishes_the_name_credibility_verdict(tmp_path):
    """Host-vs-host fields all agree when a domain was guessed from the name."""
    lead = _lead(
        "11111111000191",
        [_contact("contato@eletronelevadores.com.br", source_url="https://eletronelevadores.com.br/x")],
        website="https://eletronelevadores.com.br",
    )
    lead["company"]["razao_social"] = "ELETRON ELEVADORES LTDA"
    feed_dir = _write_export(tmp_path, [lead])
    manifest = build(
        feed_dir=feed_dir,
        private_root=tmp_path / "private",
        limit=50,
        as_of="2026-08-22",
        run_stamp="20260822T000000Z",
    )
    sample = manifest["sample_qa"][0]
    assert sample["mailbox_domain_matches_official"] is True
    assert sample["source_host_matches_official"] is True
    assert sample["mailbox_domain_fits_company_name"] is True


def test_the_sample_never_carries_the_company_name(tmp_path):
    """A Brazilian MEI's razao social is a natural person's name, often with a CPF."""
    lead = _lead(
        "11111111000191",
        [_contact("contato@silvaconstrucoes.com.br", source_url="https://silvaconstrucoes.com.br/x")],
        website="https://silvaconstrucoes.com.br",
    )
    lead["company"]["razao_social"] = "JOAO DA SILVA CONSTRUCOES"
    feed_dir = _write_export(tmp_path, [lead])
    manifest = build(
        feed_dir=feed_dir,
        private_root=tmp_path / "private",
        limit=50,
        as_of="2026-08-22",
        run_stamp="20260822T000000Z",
    )
    assert manifest["member_count"] == 1
    redacted = Path(manifest["manifest_path"]).read_text(encoding="utf-8")
    assert "JOAO DA SILVA" not in redacted
    assert "mailbox_domain_fits_company_name" in redacted


def test_the_producer_never_holds_the_whole_feed(tmp_path):
    """The authoritative export covers the decision universe, not the hot set.

    Materializing hundreds of thousands of leads is how the producer would run
    the host out of memory, so it must stream chunk by chunk.
    """
    from scripts.ops.build_controlled_email_cohort import iter_feed_leads

    feed_dir = tmp_path / "06_warmbly_feed"
    feed_dir.mkdir(parents=True)
    for idx in range(4):
        (feed_dir / f"chunk_{idx:04d}.json").write_text(
            json.dumps(
                {
                    "schema_version": SCHEMA_OUTREACH,
                    "leads": [
                        _lead(f"{idx}{n:010d}9"[:14], [_contact(f"contato@empresa{idx}x{n}.com.br")]) for n in range(3)
                    ],
                }
            ),
            encoding="utf-8",
        )
    (feed_dir / "manifest.json").write_text(
        json.dumps(
            {
                "lead_count": 12,
                "authoritative_source_freshness": {
                    "contract_version": "PNCP_CONTRACT_FRESHNESS/1.0",
                    "status": "FRESH",
                    "expires_at": "2999-01-01T00:00:00Z",
                },
            }
        ),
        encoding="utf-8",
    )

    stream = iter_feed_leads(feed_dir)
    assert next(stream)["company"]["cnpj14"].startswith("0")
    assert sum(1 for _ in iter_feed_leads(feed_dir)) == 12

    manifest = build(
        feed_dir=feed_dir,
        private_root=tmp_path / "private",
        limit=50,
        as_of="2026-08-22",
        run_stamp="20260822T000000Z",
    )
    assert manifest["member_count"] == 12
    assert manifest["funnel"]["accounts_considered"] == 12


def test_a_precomputed_owner_map_matches_the_whole_feed_gate():
    """Streaming must not weaken the cross-account rule."""
    from scripts.decision_unit_intelligence.controlled_email import shared_preferred_mailbox_owner

    shared = "contato@grupocompartilhado.com.br"
    leads = [_lead("22222222000172", [_contact(shared)]), _lead("11111111000191", [_contact(shared)])]

    whole, _ = select_cohort(list(leads), limit=50)
    streamed, _ = select_cohort(
        iter(list(leads)),
        limit=50,
        shared_mailbox_owner=shared_preferred_mailbox_owner(leads),
    )
    assert [m["company"]["cnpj14"] for m in whole] == [m["company"]["cnpj14"] for m in streamed] == []


def test_a_wrongly_resolved_domain_is_blocked_by_the_company_name():
    """Observed in a real run: premium.com.br for a Braga, balboa.com for an ML.

    When resolution picks the wrong company, mailbox host, page host and
    official host all agree with each other, so nothing internal to the route
    looks wrong. The registered name is the only independent check.
    """
    wrong = _lead(
        "11111111000191",
        [_contact("contato@premium.com.br", source_url="https://premium.com.br/contato")],
        website="https://premium.com.br",
    )
    wrong["company"]["razao_social"] = "C M L BRAGA CONSTRUCAO DE EDIFICIOS"
    members, stats = select_cohort([wrong], limit=50)
    assert members == []
    assert stats["funnel"]["blocked_domain_not_credible_for_company_name"] == 1


def test_a_company_on_its_own_named_domain_still_passes():
    right = _lead(
        "22222222000172",
        [_contact("contato@eletronelevadores.com.br", source_url="https://eletronelevadores.com.br/contato")],
        website="https://eletronelevadores.com.br",
    )
    right["company"]["razao_social"] = "ELETRON ELEVADORES LTDA"
    members, _ = select_cohort([right], limit=50)
    assert len(members) == 1


def test_a_generic_word_in_the_name_is_not_a_brand_match():
    """CONSTRUTORA CAPITAL matched capital.com, a real and unrelated business."""
    from scripts.confenge_contact_resolution.discovery.official_domain import is_credible_company_domain

    for domain, name in (
        ("capital.com", "CONSTRUTORA CAPITAL JP LTDA"),
        ("premium.com.br", "C M L BRAGA CONSTRUCAO DE EDIFICIOS"),
        ("balboa.com", "ML ENGENHARIA LTDA"),
        ("cepam.com.br", "F A CONSTRUCOES E SERVICOS EIRELI"),
        ("central.com.br", "CONSTRUTORA CENTRAL LTDA"),
        ("horizonte.com.br", "CONSTRUTORA HORIZONTE LTDA"),
    ):
        assert is_credible_company_domain(domain, name) is False, (domain, name)

    for domain, name in (
        ("eletronelevadores.com.br", "ELETRON ELEVADORES LTDA"),
        ("engelec.com.br", "ENGELEC - ENGENHARIA ELETRICA E CIVIL LTDA"),
        ("andradegutierrez.com.br", "ANDRADE GUTIERREZ ENGENHARIA SA"),
    ):
        assert is_credible_company_domain(domain, name) is True, (domain, name)


def test_a_lead_without_a_company_name_cannot_be_verified():
    unnamed = _lead(
        "33333333000153", [_contact("contato@alphaengenharia.com.br")], website="https://alphaengenharia.com.br"
    )
    unnamed["company"]["razao_social"] = ""
    unnamed["company"]["nome_fantasia"] = ""
    members, stats = select_cohort([unnamed], limit=50)
    assert members == []
    assert stats["funnel"]["blocked_company_name_unavailable_for_domain_check"] == 1
