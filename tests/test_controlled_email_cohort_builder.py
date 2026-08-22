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
    return {
        "source_lead_id": f"lead-{cnpj14}",
        "company": {"cnpj14": cnpj14, "razao_social": f"EMPRESA {cnpj14}", "website": website},
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
        json.dumps({"lead_count": len(leads), "source": {"repo_sha": "0" * 40, "run_id": "run-test"}}),
        encoding="utf-8",
    )
    return feed_dir


def test_risky_and_suppressed_never_enter_the_cohort():
    leads = [
        _lead("11111111000191", [_contact("contato@alpha.com.br")]),
        _lead(
            "22222222000172",
            [_contact("chute@beta.com.br", route_class="PROBABILISTIC_OR_RISKY", eligible=False)],
        ),
        _lead("33333333000153", [_contact("contato@gama.com.br", route_suppression="OPT_OUT")]),
        _lead("44444444000134", [_contact("contato@delta.com.br", eligible=False)]),
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
            [_contact("contato@alpha.com.br"), _contact("licitacoes@alpha.com.br", route_class="ROLE_OR_DEPARTMENT")],
        ),
        _lead("22222222000172", [_contact("contato@beta.com.br", preferred=False)]),
    ]
    members, stats = select_cohort(leads, limit=50)
    assert members == []
    assert stats["funnel"]["double_preferred"] == 1


def test_the_same_mailbox_cannot_be_claimed_by_two_accounts():
    shared = "contato@grupo.com.br"
    leads = [
        _lead("11111111000191", [_contact(shared)]),
        _lead("22222222000172", [_contact(shared)]),
    ]
    members, _ = select_cohort(leads, limit=50)
    assert len(members) == 1


def test_cohort_is_capped_without_padding():
    leads = [_lead(f"{n:011d}191"[:14], [_contact(f"contato@empresa{n}.com.br")]) for n in range(1, 8)]
    members, stats = select_cohort(leads, limit=3)
    assert len(members) == 3
    assert stats["funnel"]["preferred_initial"] == 7


def test_private_feed_is_0600_and_the_manifest_carries_no_pii(tmp_path):
    feed_dir = _write_export(
        tmp_path,
        [
            _lead("11111111000191", [_contact("contato@alpha.com.br")], website="https://alpha.com.br"),
            _lead(
                "22222222000172",
                [_contact("licitacoes@beta.com.br", route_class="ROLE_OR_DEPARTMENT")],
                website="https://beta.com.br",
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
    assert "alpha.com.br" in redacted  # public host is evidence, not PII


def test_feed_hash_matches_the_bytes_on_disk(tmp_path):
    import hashlib

    feed_dir = _write_export(tmp_path, [_lead("11111111000191", [_contact("contato@alpha.com.br")])])
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
        "contato@alpha.com.br",
        source_url="https://alpha.com.br/contato",
        provenance={"source_type": "contact_page"},
    )
    members, _ = select_cohort(
        [_lead("11111111000191", [honest], website="https://alpha.com.br")],
        limit=50,
    )
    assert len(members) == 1


def test_official_domain_ladder_matches_the_exporter():
    from scripts.ops.build_controlled_email_cohort import resolve_official_domain

    lead = _lead("11111111000191", [], website="https://www.Alpha.com.br/quem-somos")
    assert resolve_official_domain(lead, {}) == "alpha.com.br"
    assert resolve_official_domain(lead, {"official_domain": "beta.com.br"}) == "beta.com.br"
    assert resolve_official_domain(_lead("11111111000191", []), {}) is None


def test_a_route_on_its_own_official_domain_survives_the_recheck():
    """The exporter's official domain must not be lost, or good routes die."""
    contact = _contact(
        "contato@alpha.com.br",
        source_url="https://alpha.com.br/contato",
        official_domain="alpha.com.br",
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
    lead["company"]["official_domain"] = "alpha.com.br"
    assert resolve_official_domain(lead, {}) == "alpha.com.br"

    contact = _contact(
        "contato@alpha.com.br",
        source_url="https://alpha.com.br/fale-conosco",
    )
    lead_with_contact = _lead("11111111000191", [contact])
    lead_with_contact["company"]["official_domain"] = "alpha.com.br"
    members, stats = select_cohort([lead_with_contact], limit=50)
    assert len(members) == 1
    assert stats["funnel"]["official_domain"] == 1
    assert stats["funnel"]["no_domain"] == 0
