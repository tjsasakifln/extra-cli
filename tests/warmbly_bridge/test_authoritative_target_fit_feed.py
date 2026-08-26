"""Authoritative full-snapshot and revocation semantics for confenge.outreach.v1."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from scripts.confenge_target_fit.company_key import canonical_cnpj14, canonical_target_membership
from scripts.warmbly_bridge.export import ExportConfig, export_outreach
from scripts.warmbly_bridge.io_jsonl import InputError

NOW = "2026-08-12T12:00:00Z"


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def _decision(
    cnpj14: str,
    target_class: str,
    *,
    watermark: str = NOW,
    evidence_ids: list[str] | None = None,
    operational_status: str = "ok",
) -> dict[str, Any]:
    return {
        "cnpj14": cnpj14,
        "target_fit_class": target_class,
        "target_fit_confidence": 0.95,
        "target_fit_version": "confenge-target-fit-v2",
        "target_fit_computed_at": watermark,
        "target_fit_source_watermark": watermark,
        "target_fit_evidence": [
            {"id": evidence_id, "type": "CONTRACT_EXECUTION"} for evidence_id in (evidence_ids or [])
        ],
        "target_fit_reason_codes": [target_class.lower()],
        "target_fit_operational_status": operational_status,
    }


def _read_leads(out: Path) -> list[dict[str, Any]]:
    leads: list[dict[str, Any]] = []
    for path in sorted(out.glob("chunk_*.json")):
        leads.extend(json.loads(path.read_text(encoding="utf-8"))["leads"])
    return leads


def _export(
    tmp_path: Path,
    *,
    universe: list[dict[str, Any]],
    target_fit: list[dict[str, Any]],
    suffix: str,
    datalake_watermark: str | None = None,
    authoritative_contact_report: bool = False,
    contact_membership_hash: str | None = None,
    contact_coverage_complete: bool = True,
    no_public_email_cnpjs: set[str] | None = None,
) -> tuple[Path, list[dict[str, Any]]]:
    source = tmp_path / suffix
    source.mkdir()
    domains = [f"{str(row['razao_social']).split()[0].lower()}.com.br" for row in universe]
    feed_universe = [
        {
            **row,
            "official_domain": domains[index],
            "construction_universe_member": row.get(
                "construction_universe_member",
                True,
            ),
        }
        for index, row in enumerate(universe)
    ]
    universe_path = _write_jsonl(source / "universe.jsonl", feed_universe)
    target_fit_path = _write_jsonl(source / "target-fit.jsonl", target_fit)
    intelligence = [
        {
            "cnpj14": row["cnpj14"],
            "offer": {"service_code": "REAJUSTE"},
            "primary_service": {
                "service_id": "REAJUSTE",
                "service_code": "REAJUSTE",
                "supporting_signal_ids": [f"signal-{row['cnpj14']}"],
                "evidence_ids": [f"contract-{row['cnpj14']}"],
            },
            "messaging": {
                "fact_to_mention": (
                    f"{row['razao_social']} consta no objeto: pavimentacao asfaltica "
                    "de vias urbanas; orgao: Prefeitura de Coxilha."
                ),
                "question_to_ask": "Quem acompanha os contratos publicos?",
                "cta": "Posso enviar o recorte publico?",
                "claims_to_avoid": [],
            },
            "why_this_account": (
                f"{row['razao_social']} executa objeto: pavimentacao asfaltica "
                "de vias urbanas; orgao: Prefeitura de Coxilha."
            ),
            "why_now": (
                f"Aditivo recente de {row['razao_social']} no objeto: pavimentacao "
                "asfaltica; orgao: Prefeitura de Coxilha."
            ),
            "observed_fact": (f"{row['razao_social']}; objeto: pavimentacao asfaltica; orgao: Prefeitura de Coxilha."),
            "micro_offer_code": "REAJUSTE_CHECK",
            "evidence": [
                {
                    "id": f"contract-{row['cnpj14']}",
                    "type": "PNCP_CONTRACT",
                    "epistemic_class": "CONFIRMED_FACT",
                }
            ],
        }
        for row in universe
    ]
    contacts = [
        {
            "cnpj14": row["cnpj14"],
            "contacts": [
                {
                    "name": "Maria de Souza",
                    "role": "Diretora Comercial",
                    "email": f"maria.souza@{domains[index]}",
                    "ownership_status": "COMPANY_OWNED",
                    "company_associated": True,
                    "mailbox_company_evidence": "OBSERVED",
                    "channel_epistemic_class": "OBSERVED",
                    "route_freshness": "FRESH",
                    "route_suppression": "NONE",
                    "verification_status": "OBSERVED",
                    "email_explicitly_published": True,
                    "name_explicitly_published": True,
                    "role_explicitly_published": True,
                    "human_identity_evidence_valid": True,
                    "identity_evidence_urls": [f"https://{domains[index]}/equipe"],
                    "evidence_sha256": f"{index + 1:064x}",
                    "source_type": "company_registry",
                    "source_reference": f"registry-contact:{row['cnpj14']}:maria",
                    "evidence_ids": [f"registry-evidence:{row['cnpj14']}:maria"],
                    "registry_cnpj14": row["cnpj14"],
                    "official_match_status": "MATCHED",
                    "official_authority": "RECEITA_FEDERAL",
                    "official_release_id": "registry-release-1",
                    "source_provenance": {
                        "authority": "RECEITA_FEDERAL",
                        "release_id": "registry-release-1",
                        "source_label": "rfb_public_cadastral",
                    },
                    "provenance": {
                        "source_type": "company_registry",
                        "observed_at": NOW,
                        "evidence_sha256": f"{index + 1:064x}",
                    },
                },
                {
                    "name": "Joao de Lima",
                    "role": "Responsavel Tecnico",
                    "email": f"joao.lima@{domains[index]}",
                    "ownership_status": "COMPANY_OWNED",
                    "company_associated": True,
                    "mailbox_company_evidence": "OBSERVED",
                    "channel_epistemic_class": "OBSERVED",
                    "route_freshness": "FRESH",
                    "route_suppression": "NONE",
                    "verification_status": "OBSERVED",
                    "confidence": "0.8",
                    "email_explicitly_published": True,
                    "name_explicitly_published": True,
                    "role_explicitly_published": True,
                    "human_identity_evidence_valid": True,
                    "identity_evidence_urls": [f"https://{domains[index]}/equipe-tecnica"],
                    "evidence_sha256": f"{index + 100:064x}",
                    "source_type": "company_registry",
                    "source_reference": f"registry-contact:{row['cnpj14']}:joao",
                    "evidence_ids": [f"registry-evidence:{row['cnpj14']}:joao"],
                    "registry_cnpj14": row["cnpj14"],
                    "official_match_status": "MATCHED",
                    "official_authority": "RECEITA_FEDERAL",
                    "official_release_id": "registry-release-1",
                    "source_provenance": {
                        "authority": "RECEITA_FEDERAL",
                        "release_id": "registry-release-1",
                        "source_label": "rfb_public_cadastral",
                    },
                    "provenance": {
                        "source_type": "company_registry",
                        "observed_at": NOW,
                        "evidence_sha256": f"{index + 100:064x}",
                    },
                },
            ],
        }
        for index, row in enumerate(universe)
    ]
    intel_path = _write_jsonl(source / "intelligence.jsonl", intelligence)
    if authoritative_contact_report:
        confirmed_cnpjs = {
            canonical_cnpj14(row["cnpj14"]) for row in target_fit if row.get("target_fit_class") == "TARGET_CONFIRMED"
        }
        for row in contacts:
            if canonical_cnpj14(row["cnpj14"]) in confirmed_cnpjs:
                if canonical_cnpj14(row["cnpj14"]) in (no_public_email_cnpjs or set()):
                    row["contacts"] = []
                    row["enrichment_state"] = "NO_PUBLIC_EMAIL_FOUND"
                    row["preferred_email_route"] = None
                else:
                    row["enrichment_state"] = "EMAIL_ROUTE_READY"
                    row["contacts"][1]["preferred_initial"] = True
                    row["contacts"][1]["recommended"] = True
                    row["contacts"][1]["controlled_email_eligible"] = True
                    row["preferred_email_route"] = {
                        "email": row["contacts"][1]["email"],
                        "route_class": "DIRECT_PERSON",
                    }
    contacts_path = _write_jsonl(source / "contacts.jsonl", contacts)
    contact_report_path: Path | None = None
    if authoritative_contact_report:
        confirmed = [
            canonical_cnpj14(row["cnpj14"]) for row in target_fit if row.get("target_fit_class") == "TARGET_CONFIRMED"
        ]
        membership = canonical_target_membership(confirmed)
        terminal_states = Counter(str(row.get("enrichment_state")) for row in contacts if row.get("enrichment_state"))
        contact_report_path = source / "contact-projection-report.json"
        contact_report_path.write_text(
            json.dumps(
                {
                    "schema_id": "confenge.contact_discovery.projection_report.v1",
                    "generated_at": NOW,
                    "cohort_id": "test-contact-cohort",
                    "population_count": membership["population_count"],
                    "population_hash": "f" * 64,
                    "population_as_of": NOW,
                    "membership_schema_version": membership["schema_version"],
                    "membership_identity_key": membership["identity_key"],
                    "membership_count": membership["population_count"],
                    "membership_hash": contact_membership_hash or membership["membership_hash"],
                    "membership_hash_algorithm": membership["hash_algorithm"],
                    "membership_contract_matches_population": True,
                    "terminal_coverage_complete": contact_coverage_complete,
                    "terminal_equation": {"holds": contact_coverage_complete},
                    "enrichment_states": dict(terminal_states),
                    "integrity_failures": {},
                    "blockers": {},
                    "accounts_with_any_email": sum(
                        bool(row["contacts"]) for row in contacts if canonical_cnpj14(row["cnpj14"]) in confirmed_cnpjs
                    ),
                    "accounts_with_preferred_route": sum(
                        bool(row.get("preferred_email_route"))
                        for row in contacts
                        if canonical_cnpj14(row["cnpj14"]) in confirmed_cnpjs
                    ),
                    "route_class_distribution": {"DIRECT_PERSON": membership["population_count"]},
                    "preferred_route_class_distribution": {"DIRECT_PERSON": membership["population_count"]},
                    "provenance_source_distribution": {"site": membership["population_count"]},
                    "projection_hash": "e" * 64,
                    "controlled_email_policy_version": "controlled-email-policy.v3",
                    "policy_version": "dui.policy.v1",
                    "input_evidence_version": "target-fit.test",
                    "code_sha": "authoritative-test",
                }
            ),
            encoding="utf-8",
        )
    out = source / "feed"
    result = export_outreach(
        ExportConfig(
            universe=universe_path,
            account_intelligence=intel_path,
            contacts=contacts_path,
            contact_projection_report=contact_report_path,
            target_fit_snapshot=target_fit_path,
            expected_universe_count=len(universe),
            out_dir=out,
            generated_at=NOW,
            datalake_watermark=datalake_watermark,
            repo_sha="authoritative-test",
            require_authoritative_contact_projection_metadata=authoritative_contact_report,
            max_leads_per_chunk=3,
        )
    )
    assert result["lead_count"] == len(universe)
    return out, _read_leads(out)


def test_full_snapshot_publishes_negative_decisions_and_temporal_order(tmp_path: Path) -> None:
    universe = [
        {"cnpj14": "01489370000105", "razao_social": "PREVENCAO LABORATORIO", "commercial_state": "NEW"},
        {"cnpj14": "01607033000167", "razao_social": "BEBA MAIS", "commercial_state": "NEW"},
        {"cnpj14": "01942594000112", "razao_social": "SULPEL PAPEIS", "commercial_state": "NEW"},
        {"cnpj14": "11222333000181", "razao_social": "ALFA ENGENHARIA", "commercial_state": "NEW"},
        {"cnpj14": "22333444000155", "razao_social": "ENGENHARIA DNC", "commercial_state": "DO_NOT_CONTACT"},
        {"cnpj14": "33444555000166", "razao_social": "ENGENHARIA STALE", "commercial_state": "NEW"},
        {"cnpj14": "44555666000177", "razao_social": "SEM ICP PUBLICADO", "commercial_state": "NEW"},
    ]
    snapshot = [
        _decision("01489370000105", "TARGET_OUT_OF_SCOPE"),
        _decision("01607033000167", "TARGET_OUT_OF_SCOPE"),
        _decision("01942594000112", "TARGET_INSUFFICIENT_EVIDENCE"),
        _decision("11222333000181", "TARGET_CONFIRMED", evidence_ids=["eng-contract"]),
        _decision("22333444000155", "TARGET_CONFIRMED", evidence_ids=["dnc-contract"]),
        _decision(
            "33444555000166",
            "TARGET_CONFIRMED",
            evidence_ids=["stale-contract"],
            operational_status="stale",
        ),
        # Deliberately omit 44555666: exporter must emit a revocation tombstone.
    ]
    out, leads = _export(tmp_path, universe=universe, target_fit=snapshot, suffix="full")
    by_cnpj = {lead["company"]["cnpj14"]: lead for lead in leads}

    assert "14893700000105" in by_cnpj
    assert "01489370000105" not in by_cnpj
    for cnpj in ("14893700000105", "01607033000167", "01942594000112"):
        assert by_cnpj[cnpj]["email_send_ready"] is False
    assert by_cnpj["11222333000181"]["target_fit_class"] == "TARGET_CONFIRMED"
    assert by_cnpj["11222333000181"]["construction_universe_member"] is True
    assert by_cnpj["11222333000181"]["target_fit_fresh"] is True
    assert by_cnpj["11222333000181"]["email_send_ready"] is True
    all_contacts = by_cnpj["11222333000181"]["contacts"]
    ready_contacts = [c for c in all_contacts if c.get("email_send_ready")]
    assert len(ready_contacts) == 2
    preferred_contacts = [c for c in all_contacts if c.get("preferred_initial")]
    recommended_contacts = [c for c in all_contacts if c.get("recommended")]
    assert len(preferred_contacts) == 1
    assert sum(1 for c in all_contacts if c.get("preferred_initial")) == 1
    assert recommended_contacts == preferred_contacts
    assert sum(bool(c.get("recommended")) for c in ready_contacts) == 1
    assert preferred_contacts[0].get("email_send_ready") is True
    assert all(c["source_date"] == "2026-08-12" for c in ready_contacts)
    assert all(c["source_date_semantics"] == "observed_at" for c in ready_contacts)
    assert all(not c.get("source_published_at") for c in ready_contacts)
    assert by_cnpj["22333444000155"]["email_send_ready"] is False
    assert by_cnpj["33444555000166"]["target_fit_fresh"] is False
    assert by_cnpj["33444555000166"]["email_send_ready"] is False
    missing = by_cnpj["44555666000177"]
    assert missing["target_fit_class"] == "TARGET_FIT_MISSING"
    assert missing["target_fit_tombstone"] is True
    assert missing["email_send_ready"] is False

    required = {
        "construction_universe_member",
        "target_fit_class",
        "target_fit_fresh",
        "target_fit_version",
        "target_fit_computed_at",
        "target_fit_source_watermark",
        "target_fit_evidence_ids",
        "target_fit_send_tier",
        "email_send_ready",
    }
    assert all(required <= set(lead) for lead in leads)
    watermarks = [lead["target_fit_source_watermark"] for lead in leads]
    assert watermarks == sorted(watermarks)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    authority = manifest["authoritative_target_fit"]
    assert authority["coverage_complete"] is True
    assert authority["full_decision_count"] == len(universe)
    assert authority["ordering"]["watermarks_monotonic"] is True
    assert authority["omission_preserves_authorization"] is False


def test_authoritative_contact_membership_is_bound_into_manifest(tmp_path: Path) -> None:
    cnpj = "11222333000181"
    out, _ = _export(
        tmp_path,
        universe=[{"cnpj14": cnpj, "razao_social": "ALFA ENGENHARIA", "commercial_state": "NEW"}],
        target_fit=[_decision(cnpj, "TARGET_CONFIRMED", evidence_ids=["contract-1"])],
        suffix="contact-membership",
        authoritative_contact_report=True,
    )

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    membership = manifest["authoritative_target_membership"]
    contact = manifest["authoritative_contact_projection"]
    expected = canonical_target_membership([cnpj])
    assert membership["population_count"] == 1
    assert membership["membership_hash"] == expected["membership_hash"]
    assert contact["terminal_coverage_complete"] is True
    assert contact["membership_hash"] == membership["membership_hash"]
    assert contact["recipient_states"] == {
        "RECIPIENT_ATTRIBUTED": 1,
        "READY": 1,
        "NO_PUBLIC_EMAIL_FOUND": 0,
        "BLOCKED_WITH_REASON": 0,
    }


def test_missing_contact_remains_in_target_denominator(tmp_path: Path) -> None:
    ready = "11222333000181"
    no_public = "22333444000172"
    out, leads = _export(
        tmp_path,
        universe=[
            {"cnpj14": ready, "razao_social": "ALFA ENGENHARIA", "commercial_state": "NEW"},
            {"cnpj14": no_public, "razao_social": "BETA ENGENHARIA", "commercial_state": "NEW"},
        ],
        target_fit=[
            _decision(ready, "TARGET_CONFIRMED", evidence_ids=["contract-1"]),
            _decision(no_public, "TARGET_CONFIRMED", evidence_ids=["contract-2"]),
        ],
        suffix="missing-contact-denominator",
        authoritative_contact_report=True,
        no_public_email_cnpjs={no_public},
    )

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["authoritative_target_membership"]["population_count"] == 2
    assert manifest["authoritative_contact_projection"]["recipient_states"] == {
        "RECIPIENT_ATTRIBUTED": 1,
        "READY": 1,
        "NO_PUBLIC_EMAIL_FOUND": 1,
        "BLOCKED_WITH_REASON": 0,
    }
    missing = next(lead for lead in leads if lead["company"]["cnpj14"] == no_public)
    assert missing["target_fit_class"] == "TARGET_CONFIRMED"
    assert missing["contacts"] == []


def test_non_target_contact_does_not_inflate_recipient_denominator(tmp_path: Path) -> None:
    target = "11222333000181"
    out_of_scope = "22333444000172"
    out, _leads = _export(
        tmp_path,
        universe=[
            {"cnpj14": target, "razao_social": "ALFA ENGENHARIA", "commercial_state": "NEW"},
            {"cnpj14": out_of_scope, "razao_social": "BETA VAREJO", "commercial_state": "NEW"},
        ],
        target_fit=[
            _decision(target, "TARGET_CONFIRMED", evidence_ids=["contract-1"]),
            _decision(out_of_scope, "TARGET_OUT_OF_SCOPE", evidence_ids=["contract-2"]),
        ],
        suffix="non-target-contact",
        authoritative_contact_report=True,
    )

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["authoritative_target_membership"]["population_count"] == 1
    assert manifest["authoritative_contact_projection"]["recipient_states"]["RECIPIENT_ATTRIBUTED"] == 1


def test_contact_report_clock_only_change_keeps_snapshot_and_generated_at(tmp_path: Path) -> None:
    cnpj = "11222333000181"
    out, _ = _export(
        tmp_path,
        universe=[{"cnpj14": cnpj, "razao_social": "ALFA ENGENHARIA", "commercial_state": "NEW"}],
        target_fit=[_decision(cnpj, "TARGET_CONFIRMED", evidence_ids=["contract-1"])],
        suffix="contact-report-clock",
        authoritative_contact_report=True,
    )
    first = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    report_path = out.parent / "contact-projection-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["generated_at"] = "2026-08-13T12:00:00Z"
    report["cohort_id"] = "retry-with-identical-facts"
    report["code_sha"] = "new-runtime-only"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    second_result = export_outreach(
        ExportConfig(
            universe=out.parent / "universe.jsonl",
            account_intelligence=out.parent / "intelligence.jsonl",
            contacts=out.parent / "contacts.jsonl",
            contact_projection_report=report_path,
            target_fit_snapshot=out.parent / "target-fit.jsonl",
            expected_universe_count=1,
            out_dir=out,
            generated_at=None,
            datalake_watermark=NOW,
            repo_sha=None,
            require_authoritative_contact_projection_metadata=True,
        )
    )
    second = json.loads((out / "manifest.json").read_text(encoding="utf-8"))

    assert second_result["snapshot_hash"] == first["source"]["snapshot_hash"]
    assert second["generated_at"] == first["generated_at"]
    assert (
        second["authoritative_contact_projection"]["report_sha256"]
        != first["authoritative_contact_projection"]["report_sha256"]
    )


@pytest.mark.parametrize(
    ("membership_hash", "coverage_complete", "message"),
    [
        ("0" * 64, True, "membership_hash"),
        (None, False, "terminal coverage"),
    ],
)
def test_authoritative_contact_report_must_match_closed_membership(
    tmp_path: Path,
    membership_hash: str | None,
    coverage_complete: bool,
    message: str,
) -> None:
    cnpj = "11222333000181"
    with pytest.raises(InputError, match=message):
        _export(
            tmp_path,
            universe=[{"cnpj14": cnpj, "razao_social": "ALFA ENGENHARIA", "commercial_state": "NEW"}],
            target_fit=[_decision(cnpj, "TARGET_CONFIRMED", evidence_ids=["contract-1"])],
            suffix=f"contact-report-{coverage_complete}-{membership_hash is not None}",
            authoritative_contact_report=True,
            contact_membership_hash=membership_hash,
            contact_coverage_complete=coverage_complete,
        )


def test_duplicate_target_roots_fail_before_export(tmp_path: Path) -> None:
    universe = [
        {"cnpj14": "11222333000181", "razao_social": "ALFA MATRIZ", "commercial_state": "NEW"},
        {"cnpj14": "11222333000262", "razao_social": "ALFA FILIAL", "commercial_state": "NEW"},
    ]
    target_fit = [_decision(row["cnpj14"], "TARGET_CONFIRMED", evidence_ids=[row["cnpj14"]]) for row in universe]

    with pytest.raises(InputError, match="duplicate CNPJ roots"):
        _export(tmp_path, universe=universe, target_fit=target_fit, suffix="duplicate-roots")


def test_buyer_supplier_conflict_removes_all_route_authorization(tmp_path: Path) -> None:
    cnpj = "11222333000181"
    out, leads = _export(
        tmp_path,
        universe=[
            {
                "cnpj14": cnpj,
                "razao_social": "ORGAO CONFLITANTE",
                "commercial_state": "NEW",
                "contracts": [
                    {
                        "id": "contract-conflict",
                        "supplier_cnpj14": cnpj,
                        "buyer_cnpj14": cnpj,
                        "supplier_role": "CONTRATADA",
                        "buyer_role": "CONTRATANTE",
                    }
                ],
            }
        ],
        target_fit=[_decision(cnpj, "TARGET_CONFIRMED", evidence_ids=["contract-conflict"])],
        suffix="buyer-conflict",
    )

    lead = leads[0]
    assert lead["contractor_role"]["target_party_role"] == "BUYER_CONFLICT"
    assert lead["email_send_ready"] is False
    assert not any(contact.get("preferred_initial") for contact in lead["contacts"])
    assert not any(contact.get("controlled_email_eligible") for contact in lead["contacts"])
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["authoritative_party_roles"]["buyer_supplier_conflict_fails_closed"] is True


def test_target_confirmed_does_not_override_explicit_non_construction(
    tmp_path: Path,
) -> None:
    universe = [
        {
            "cnpj14": "11222333000181",
            "razao_social": "ALFA ENGENHARIA",
            "commercial_state": "NEW",
            "construction_universe_member": False,
        }
    ]

    _, leads = _export(
        tmp_path,
        universe=universe,
        target_fit=[
            _decision(
                "11222333000181",
                "TARGET_CONFIRMED",
                evidence_ids=["eng-contract"],
            )
        ],
        suffix="non-construction",
    )

    assert leads[0]["target_fit_class"] == "TARGET_CONFIRMED"
    assert leads[0]["construction_universe_member"] is False
    assert leads[0]["email_send_ready"] is False


def test_independently_attributed_shared_mailbox_reconciles_without_route_loss(tmp_path: Path) -> None:
    accounts = ("11222333000181", "22333444000172")
    universe = [
        {"cnpj14": account, "razao_social": f"CONSTRUTORA {index}", "commercial_state": "NEW"}
        for index, account in enumerate(accounts, start=1)
    ]
    source = tmp_path / "shared-attributed"
    source.mkdir()
    universe_path = _write_jsonl(source / "universe.jsonl", universe)
    target_fit_path = _write_jsonl(
        source / "target-fit.jsonl",
        [_decision(account, "TARGET_CONFIRMED", evidence_ids=[f"contract-{account}"]) for account in accounts],
    )
    contacts = []
    for account in accounts:
        contacts.append(
            {
                "cnpj14": account,
                "contacts": [
                    {
                        "email": "licitacoes@grupo.example.com",
                        "preferred_initial": True,
                        "recommended": True,
                        "ownership_status": "COMPANY_OWNED",
                        "company_associated": True,
                        "mailbox_company_evidence": "OBSERVED",
                        "channel_epistemic_class": "OBSERVED",
                        "route_freshness": "FRESH",
                        "route_suppression": "NONE",
                        "source_type": "company_registry",
                        "source_reference": f"registry-contact:{account}",
                        "evidence_ids": [f"registry-evidence:{account}"],
                        "registry_cnpj14": account,
                        "official_match_status": "MATCHED",
                        "official_authority": "RECEITA_FEDERAL",
                        "official_release_id": "registry-release-1",
                        "official_domain": "grupo.example.com",
                        "provenance": {
                            "source_type": "company_registry",
                            "observed_at": NOW,
                            "evidence_ids": [f"registry-evidence:{account}"],
                        },
                        "source_provenance": {
                            "authority": "RECEITA_FEDERAL",
                            "release_id": "registry-release-1",
                            "source_label": "rfb_public_cadastral",
                        },
                        "observed_at": NOW,
                    }
                ],
            }
        )
    contacts_path = _write_jsonl(source / "contacts.jsonl", contacts)
    intel_path = _write_jsonl(source / "intelligence.jsonl", [])

    result = export_outreach(
        ExportConfig(
            universe=universe_path,
            account_intelligence=intel_path,
            contacts=contacts_path,
            target_fit_snapshot=target_fit_path,
            expected_universe_count=len(universe),
            out_dir=source / "feed",
            generated_at=NOW,
            datalake_watermark=NOW,
            repo_sha="authoritative-test",
        )
    )

    projection = result["authoritative_contact_projection"]
    assert projection["input_preferred_route_count"] == 2
    assert projection["output_preferred_route_count"] == 2
    assert projection["preferred_routes_reconciled"] is True
    assert projection["input_preferred_routes_hash"] == projection["output_preferred_routes_hash"]


def test_declared_ambiguous_shared_mailbox_is_policy_excluded_and_reconciles(tmp_path: Path) -> None:
    accounts = ("11222333000181", "22333444000172")
    universe = [
        {"cnpj14": account, "razao_social": f"CONSTRUTORA {index}", "commercial_state": "NEW"}
        for index, account in enumerate(accounts, start=1)
    ]
    source = tmp_path / "shared-ambiguous"
    source.mkdir()
    universe_path = _write_jsonl(source / "universe.jsonl", universe)
    target_fit_path = _write_jsonl(
        source / "target-fit.jsonl",
        [_decision(account, "TARGET_CONFIRMED", evidence_ids=[f"contract-{account}"]) for account in accounts],
    )
    contacts_path = _write_jsonl(
        source / "contacts.jsonl",
        [
            {
                "cnpj14": account,
                "official_domain": "grupo.example.com",
                "contacts": [
                    {
                        "email": "licitacoes@grupo.example.com",
                        "preferred_initial": True,
                        "recommended": True,
                        "ownership_status": "COMPANY_OWNED",
                        "source_type": "site",
                        "source_url": "https://grupo.example.com/contato",
                        "observed_at": NOW,
                    }
                ],
            }
            for account in accounts
        ],
    )
    intel_path = _write_jsonl(source / "intelligence.jsonl", [])

    result = export_outreach(
        ExportConfig(
            universe=universe_path,
            account_intelligence=intel_path,
            contacts=contacts_path,
            target_fit_snapshot=target_fit_path,
            expected_universe_count=len(universe),
            out_dir=source / "feed",
            generated_at=NOW,
            datalake_watermark=NOW,
            repo_sha="authoritative-test",
        )
    )

    projection = result["authoritative_contact_projection"]
    assert projection["projection_policy_version"] == "controlled-email-policy.v4"
    assert projection["raw_input_preferred_route_count"] == 2
    assert projection["policy_excluded_preferred_route_count"] == 2
    assert projection["input_preferred_route_count"] == 0
    assert projection["output_preferred_route_count"] == 0
    assert projection["preferred_routes_reconciled"] is True
    chunk = json.loads((source / "feed" / "chunk_0000.json").read_text())
    contacts = [contact for lead in chunk["leads"] for contact in lead["contacts"]]
    assert not any(contact.get("preferred_initial") for contact in contacts)


def test_unique_website_mailbox_without_cnpj_attestation_is_policy_excluded(tmp_path: Path) -> None:
    account = "20368709000151"
    source = tmp_path / "unique-unattributed"
    source.mkdir()
    universe_path = _write_jsonl(
        source / "universe.jsonl",
        [{"cnpj14": account, "razao_social": "PIMENTA E SANTOS LTDA", "commercial_state": "NEW"}],
    )
    target_fit_path = _write_jsonl(
        source / "target-fit.jsonl",
        [_decision(account, "TARGET_CONFIRMED", evidence_ids=["contract-pimenta"])],
    )
    contacts_path = _write_jsonl(
        source / "contacts.jsonl",
        [
            {
                "cnpj14": account,
                "official_domain": "pimenta.com.br",
                "contacts": [
                    {
                        "email": "escritorio@pimenta.com.br",
                        "preferred_initial": True,
                        "recommended": True,
                        "ownership_status": "COMPANY_OWNED",
                        "company_associated": True,
                        "mailbox_company_evidence": "OBSERVED",
                        "channel_epistemic_class": "OBSERVED",
                        "route_freshness": "FRESH",
                        "route_suppression": "NONE",
                        "source_type": "contact_page",
                        "source_reference": "https://pimenta.com.br/contato",
                        "source_url": "https://pimenta.com.br/contato",
                        "evidence_ids": ["website-contact-evidence"],
                        "observed_at": NOW,
                    }
                ],
            }
        ],
    )

    result = export_outreach(
        ExportConfig(
            universe=universe_path,
            account_intelligence=_write_jsonl(source / "intelligence.jsonl", []),
            contacts=contacts_path,
            target_fit_snapshot=target_fit_path,
            expected_universe_count=1,
            out_dir=source / "feed",
            generated_at=NOW,
            datalake_watermark=NOW,
            repo_sha="authoritative-test",
        )
    )

    projection = result["authoritative_contact_projection"]
    assert projection["raw_input_preferred_route_count"] == 1
    assert projection["policy_excluded_preferred_route_count"] == 1
    assert projection["input_preferred_route_count"] == 0
    assert projection["output_preferred_route_count"] == 0
    assert projection["preferred_routes_reconciled"] is True
    chunk = json.loads((source / "feed" / "chunk_0000.json").read_text())
    contact = chunk["leads"][0]["contacts"][0]
    assert chunk["leads"][0]["email_send_ready"] is False
    assert contact["preferred_initial"] is False
    assert contact["controlled_email_eligible"] is False
    assert contact["email_send_ready"] is False
    assert "recipient_without_account_identity_evidence" in contact["reason_codes"]


def test_null_new_membership_field_falls_back_to_explicit_canonical_value(
    tmp_path: Path,
) -> None:
    universe = [
        {
            "cnpj14": "11222333000181",
            "razao_social": "ALFA ENGENHARIA",
            "commercial_state": "NEW",
            "construction_universe_member": None,
            "canonical_universe_member": True,
        }
    ]

    _, leads = _export(
        tmp_path,
        universe=universe,
        target_fit=[
            _decision(
                "11222333000181",
                "TARGET_CONFIRMED",
                evidence_ids=["eng-contract"],
            )
        ],
        suffix="canonical-fallback",
    )

    assert leads[0]["construction_universe_member"] is True


def test_downgrade_and_missing_snapshot_cannot_resurrect_prior_authorization(
    tmp_path: Path,
) -> None:
    universe = [{"cnpj14": "11222333000181", "razao_social": "ALFA ENGENHARIA", "commercial_state": "NEW"}]
    _, initial = _export(
        tmp_path,
        universe=universe,
        target_fit=[_decision("11222333000181", "TARGET_CONFIRMED", evidence_ids=["e1"])],
        suffix="initial",
    )
    assert initial[0]["email_send_ready"] is True

    _, downgraded = _export(
        tmp_path,
        universe=universe,
        target_fit=[_decision("11222333000181", "TARGET_OUT_OF_SCOPE")],
        suffix="downgraded",
    )
    assert downgraded[0]["target_fit_class"] == "TARGET_OUT_OF_SCOPE"
    assert downgraded[0]["email_send_ready"] is False

    _, tombstoned = _export(
        tmp_path,
        universe=universe,
        target_fit=[],
        suffix="tombstoned",
    )
    assert tombstoned[0]["target_fit_class"] == "TARGET_FIT_MISSING"
    assert tombstoned[0]["target_fit_tombstone"] is True
    assert tombstoned[0]["email_send_ready"] is False


def test_explicit_decision_without_source_watermark_fails_closed(tmp_path: Path) -> None:
    universe = [{"cnpj14": "11222333000181", "razao_social": "ALFA ENGENHARIA", "commercial_state": "NEW"}]
    incomplete = _decision("11222333000181", "TARGET_CONFIRMED", evidence_ids=["e1"])
    incomplete.pop("target_fit_source_watermark")

    with pytest.raises(InputError, match="source_watermark"):
        _export(tmp_path, universe=universe, target_fit=[incomplete], suffix="incomplete")


def test_freshness_uses_canonical_datalake_watermark_not_export_clock(tmp_path: Path) -> None:
    source_watermark = "2026-08-12T08:00:00Z"
    universe = [{"cnpj14": "11222333000181", "razao_social": "ALFA ENGENHARIA", "commercial_state": "NEW"}]
    decision = _decision(
        "11222333000181",
        "TARGET_CONFIRMED",
        watermark=source_watermark,
        evidence_ids=["e1"],
    )

    out, leads = _export(
        tmp_path,
        universe=universe,
        target_fit=[decision],
        suffix="canonical-watermark",
        datalake_watermark=source_watermark,
    )

    assert leads[0]["target_fit_fresh"] is True
    assert leads[0]["email_send_ready"] is True
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"]["datalake_watermark"] == source_watermark


def test_database_datetime_strings_are_serialized_as_rfc3339(tmp_path: Path) -> None:
    database_timestamp = "2026-08-12 12:00:00.123456+00:00"
    universe = [{"cnpj14": "11222333000181", "razao_social": "ALFA ENGENHARIA", "commercial_state": "NEW"}]
    decision = _decision(
        "11222333000181",
        "TARGET_CONFIRMED",
        watermark=database_timestamp,
        evidence_ids=["e1"],
    )
    decision["target_fit_evidence_watermark"] = "2026-08-10T09:00:00Z"
    decision["target_fit_observation_run_id"] = "contracts-live-1"

    _, leads = _export(
        tmp_path,
        universe=universe,
        target_fit=[decision],
        suffix="rfc3339-database-timestamp",
        datalake_watermark=database_timestamp,
    )

    assert leads[0]["target_fit_computed_at"] == "2026-08-12T12:00:00.123456Z"
    assert leads[0]["target_fit_source_watermark"] == "2026-08-12T12:00:00.123456Z"
    assert leads[0]["target_fit_evidence_watermark"] == "2026-08-10T09:00:00Z"
    assert leads[0]["target_fit_observation_run_id"] == "contracts-live-1"


def test_cli_exposes_canonical_datalake_watermark() -> None:
    from scripts.warmbly_bridge.cli import build_parser

    args = build_parser().parse_args(
        [
            "export-outreach",
            "--universe",
            "universe.jsonl",
            "--account-intelligence",
            "intelligence.jsonl",
            "--contacts",
            "contacts.jsonl",
            "--out",
            "feed",
            "--datalake-watermark",
            "2026-08-12T08:00:00Z",
        ]
    )

    assert args.datalake_watermark == "2026-08-12T08:00:00Z"
