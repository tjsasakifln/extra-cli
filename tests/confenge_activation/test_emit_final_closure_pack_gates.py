"""Fail-closed gates for national reservoir final pack emitter.

Drives shipped pure functions — no reimplementation of terminal rules.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.confenge_activation.emit_final_closure_pack import (
    assert_pack_postconditions,
    build_sha_binding,
    emit_pack,
    ladder_complete_from_source_yield,
    main,
    warmbly_behavioral_pass,
)
from scripts.confenge_activation.pilot_go_policy import build_universe_manifest


def _universe(n: int) -> dict:
    return build_universe_manifest(
        supplier_roots_observed=n,
        sector_classes={
            "CONSTRUCTION_CONFIRMED": n,
            "CONSTRUCTION_PROBABLE": 0,
            "NON_CONSTRUCTION": 0,
            "SECTOR_INSUFFICIENT_EVIDENCE": 0,
        },
        target_fit_population=n,
        materialized_roots=n,
        target_classes={
            "TARGET_CONFIRMED": n,
            "TARGET_PROBABLE_RESEARCH": 0,
            "TARGET_OUT_OF_SCOPE": 0,
            "TARGET_INSUFFICIENT_EVIDENCE": 0,
        },
        source_contract_rows=n * 4,
        datalake_watermark="2026-08-10T12:00:00Z",
        source_cdc_watermark="2026-08-10T11:59:59Z",
        database_snapshot="123:123:",
        transaction_timestamp="2026-08-10T12:00:00Z",
        construction_universe_derivation="sector_class IN construction classes",
        construction_evidence_version="confenge-sector-v1",
        query_sha256="a" * 64,
        construction_classifier_sha256="b" * 64,
        target_fit_classifier_sha256="c" * 64,
        target_fit_version="confenge-target-fit-v2",
    )


def test_cli_fails_closed_without_atomic_universe_manifest(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="valid --universe-manifest is required"):
        main(
            [
                "--universe-manifest",
                str(tmp_path / "missing.json"),
                "--origin-main-sha",
                "a" * 40,
                "--host-deployed-sha",
                "a" * 40,
                "--evaluated-code-sha",
                "a" * 40,
            ]
        )


def test_evidence_publication_after_evaluation_does_not_invalidate_binding() -> None:
    tip = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    stale = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    binding = build_sha_binding(
        origin_main=tip,
        host_deployed=stale,
        runtime=stale,
        evaluated_code_sha=stale,
        expected_origin_tip=tip,
    )
    assert binding["triple_sha_equal"] is True
    assert binding["sha_bound"] is True
    assert binding["tip_matches_origin_main"] is True
    assert binding["evaluated_code_sha"] == stale
    assert binding["evidence_publication_sha"] == tip


def test_sha_bound_requires_evaluated_deployment_runtime_equality() -> None:
    tip = "cccccccccccccccccccccccccccccccccccccccc"
    binding = build_sha_binding(
        origin_main=tip,
        host_deployed=tip,
        runtime=tip,
        evaluated_code_sha=tip,
        expected_origin_tip=tip,
    )
    assert binding["triple_sha_equal"] is True
    assert binding["sha_bound"] is True


def test_ladder_incomplete_when_transparency_partial_public_probe() -> None:
    """Current measured shape: transparency_compras 20/8382 pages_fetched=0."""
    yield_doc = {
        "sources": {
            "process_administrative_docs": {"companies_attempted": 8382},
            "pncp_annexes": {"companies_attempted": 8382},
            "official_registry": {"companies_attempted": 8381},
            "official_site": {"companies_attempted": 8381},
            "public_docs_datalake": {"companies_attempted": 8381},
            "company_public_pages": {"companies_attempted": 8381},
            "transparency_compras": {
                "companies_attempted": 20,
                "resolved_or_http_ok": 0,
                "pages_fetched": 0,
                "class": "PUBLIC_NO_AUTH",
            },
        }
    }
    ev = ladder_complete_from_source_yield(yield_doc, target_confirmed=8382)
    assert ev["full_source_ladder_complete"] is False
    assert "pncp_transparency_compras" in ev["missing"]
    assert "professional_councils_associations" in ev["missing"]


def test_ladder_complete_when_all_steps_at_target() -> None:
    steps = (
        "public_docs_datalake",
        "process_administrative_docs",
        "pncp_annexes",
        "official_site",
        "transparency_compras",
        "official_registry",
        "company_public_pages",
    )
    sources = {s: {"companies_attempted": 100} for s in steps}
    ev = ladder_complete_from_source_yield({"sources": sources}, target_confirmed=100, ladder_steps=steps)
    assert ev["full_source_ladder_complete"] is True
    assert ev["missing"] == []


def test_warmbly_pass_false_when_critical_pass_config() -> None:
    warmbly = {
        "PASS": True,
        "email_only": True,
        "whatsapp_enabled": False,
        "auto_send_enabled": False,
        "emails_per_hour": 10,
        "dispatch": {"state": "PAUSED_MANUAL_START"},
        "checks": {
            "reservoir_feed_import": "PASS",
            "smtp_imap_reply_stop": "PASS_CONFIG",
            "dnc_preserved": "PASS",
            "rolling_hot_set": "PASS",
            "outcomes_webhook": "PASS",
        },
    }
    ok, feed, config_only = warmbly_behavioral_pass(warmbly)
    assert feed is True
    assert config_only is True
    assert ok is False


def test_emit_pack_forbids_external_on_partial_ladder(
    tmp_path: Path,
) -> None:
    tip = "d" * 40
    out = tmp_path / "pack"
    out.mkdir()
    # Durable ESR rows so ESR>0 postcondition holds
    rows = [
        {
            "cnpj_raiz": f"{i:08d}",
            "email": f"a{i}@co.example",
            "email_send_ready": True,
            "ownership_status": "COMPANY_OWNED",
            "why_this_account": f"why account {i}",
            "why_now": f"why now {i}",
            "micro_offer": "offer",
            "service_code": "gestao_monitoramento_contratual",
            "mailbox_send_blocked": False,
        }
        for i in range(60)
    ]
    (out / "EMAIL-SEND-READY-ROWS.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    esr = {
        "EMAIL_SEND_READY_DISTINCT_COMPANIES": 60,
        "TARGET_CONFIRMED": 8382,
        "email_roots_upper_bound": 100,
        "funnel": {
            "DISTINCT_COMPANIES_WITH_EMAIL": 100,
            "COMPANY_OWNED": 80,
            "SERVICE_FIT_VALID": 60,
            "COPY_CONTEXT_VALID": 60,
            "EMAIL_SEND_READY_DISTINCT_COMPANIES": 60,
        },
        "service_fit_unsupported_count": 0,
        "service_fit_ontology_ok": True,
        "esr_rows": rows,
        "not_ready_sample": [
            {
                "cnpj_raiz": f"n{i:07d}",
                "email": f"n{i}@x.example",
                "email_send_ready": False,
            }
            for i in range(40)
        ],
        "process_terminal_counts": {
            "CONTACT_EXHAUSTED": 8111,
            "CONTACT_FOUND_NOT_SENDABLE": 47,
            "CONTACT_READY": 224,
            "CONTACT_NEVER_ATTEMPTED": 0,
            "CONTACT_EXTERNAL_BLOCKER": 0,
            "CONTACT_RETRY_PENDING": 0,
        },
    }
    yield_doc = {
        "sources": {
            "process_administrative_docs": {"companies_attempted": 8382},
            "pncp_annexes": {"companies_attempted": 8382},
            "official_registry": {"companies_attempted": 8381},
            "official_site": {"companies_attempted": 8381},
            "public_docs_datalake": {"companies_attempted": 8381},
            "company_public_pages": {"companies_attempted": 8381},
            "transparency_compras": {
                "companies_attempted": 20,
                "pages_fetched": 0,
                "resolved_or_http_ok": 0,
                "class": "PUBLIC_NO_AUTH",
            },
        }
    }
    warmbly = {
        "PASS": True,
        "email_only": True,
        "whatsapp_enabled": False,
        "auto_send_enabled": False,
        "emails_per_hour": 10,
        "dispatch": {"state": "PAUSED_MANUAL_START"},
        "checks": {
            "reservoir_feed_import": "PASS",
            "smtp_imap_reply_stop": "PASS",
            "dnc_preserved": "PASS",
            "rolling_hot_set": "PASS",
            "outcomes_webhook": "PASS",
        },
    }
    sha = build_sha_binding(
        origin_main=tip,
        host_deployed=tip,
        runtime=tip,
        expected_origin_tip=tip,
        warmbly_origin_main="w" * 40,
        warmbly_host_deployed="w" * 40,
        warmbly_runtime="w" * 40,
    )
    terms = esr["process_terminal_counts"]
    man = emit_pack(
        out_dir=out,
        esr_report=esr,
        target_classes={"TARGET_CONFIRMED": 8382},
        contact_terminals=terms,
        runtime_health={
            "FULLY_RECONCILED": True,
            "coverage_ratio": 1.0,
            "dirty_pending": 0,
            "processing_stuck": 0,
            "process_harvest": "COMPLETE",
            "contact_enrichment_initial_full_sweep": "COMPLETE",
            "continuous_workers": "HEALTHY",
            # Flag lies — yield must win
            "full_source_ladder_complete": True,
        },
        universe_manifest=_universe(8382),
        sha_binding=sha,
        warmbly_e2e=warmbly,
        source_yield=yield_doc,
        expected_origin_tip=tip,
        enforce_postconditions=True,
    )
    go = json.loads((out / "GO-NO-GO.json").read_text(encoding="utf-8"))
    assert go["terminal_state"] == "ENGINEERING_IN_PROGRESS"
    assert go["gates"]["full_source_ladder_complete"] is False
    assert "pncp_transparency_compras" in go["gates"]["ladder_yield_missing"]
    assert man["terminal_state"] == go["terminal_state"]
    assert man["extra_cli_sha"] == tip
    violations = assert_pack_postconditions(out, expected_origin_tip=tip)
    assert violations == []


def test_emit_pack_stale_sha_cannot_leave_engineering(tmp_path: Path) -> None:
    tip = "e" * 40
    stale = "f" * 40
    out = tmp_path / "pack2"
    out.mkdir()
    rows = [
        {
            "cnpj_raiz": f"{i:08d}",
            "email": f"b{i}@co.example",
            "email_send_ready": True,
            "ownership_status": "COMPANY_OWNED",
            "why_this_account": f"wa {i}",
            "why_now": f"wn {i}",
            "micro_offer": "o",
            "service_code": "gestao_monitoramento_contratual",
            "mailbox_send_blocked": False,
        }
        for i in range(55)
    ]
    esr = {
        "EMAIL_SEND_READY_DISTINCT_COMPANIES": 55,
        "TARGET_CONFIRMED": 100,
        "funnel": {},
        "service_fit_unsupported_count": 0,
        "service_fit_ontology_ok": True,
        "esr_rows": rows,
        "process_terminal_counts": {
            "CONTACT_EXHAUSTED": 50,
            "CONTACT_READY": 50,
            "CONTACT_RETRY_PENDING": 0,
            "CONTACT_NEVER_ATTEMPTED": 0,
            "CONTACT_FOUND_NOT_SENDABLE": 0,
            "CONTACT_EXTERNAL_BLOCKER": 0,
        },
    }
    sources = {
        s: {"companies_attempted": 100}
        for s in (
            "public_docs_datalake",
            "process_administrative_docs",
            "pncp_annexes",
            "official_site",
            "transparency_compras",
            "official_registry",
            "company_public_pages",
        )
    }
    warmbly = {
        "PASS": True,
        "email_only": True,
        "whatsapp_enabled": False,
        "auto_send_enabled": False,
        "emails_per_hour": 10,
        "dispatch": {"state": "PAUSED_MANUAL_START"},
        "checks": {
            "reservoir_feed_import": "PASS",
            "smtp_imap_reply_stop": "PASS",
            "dnc_preserved": "PASS",
            "rolling_hot_set": "PASS",
            "outcomes_webhook": "PASS",
        },
    }
    sha = build_sha_binding(
        origin_main=stale,
        host_deployed=stale,
        runtime=tip,
        evaluated_code_sha=stale,
        expected_origin_tip=tip,
    )
    man = emit_pack(
        out_dir=out,
        esr_report=esr,
        target_classes={"TARGET_CONFIRMED": 100},
        contact_terminals=esr["process_terminal_counts"],
        runtime_health={"FULLY_RECONCILED": True, "dirty_pending": 0, "processing_stuck": 0},
        universe_manifest=_universe(100),
        sha_binding=sha,
        warmbly_e2e=warmbly,
        source_yield={"sources": sources},
        expected_origin_tip=tip,
        enforce_postconditions=True,
    )
    go = json.loads((out / "GO-NO-GO.json").read_text(encoding="utf-8"))
    assert go["gates"]["sha_bound"] is False
    assert go["terminal_state"] == "ENGINEERING_IN_PROGRESS"
    assert man["terminal_state"] == "ENGINEERING_IN_PROGRESS"


def test_emit_pack_go_below_900_after_top20_and_10_approvals(tmp_path: Path) -> None:
    tip = "1" * 40
    out = tmp_path / "go-pack"
    out.mkdir()
    rows = [
        {
            "cnpj_raiz": f"{i:08d}",
            "email": f"pilot{i}@co.example",
            "email_send_ready": True,
            "ownership_status": "COMPANY_OWNED",
            "why_this_account": f"account evidence {i}",
            "why_now": f"timing evidence {i}",
            "micro_offer": "diagnostic",
            "service_code": "gestao_monitoramento_contratual",
            "mailbox_send_blocked": False,
        }
        for i in range(60)
    ]
    not_ready = [{"cnpj_raiz": f"9{i:07d}", "email_send_ready": False} for i in range(40)]
    decisions = out / "HUMAN-REVIEW-DECISIONS.jsonl"
    decisions.write_text(
        "\n".join(
            json.dumps(
                {
                    "cnpj_raiz": row["cnpj_raiz"],
                    "email": row["email"],
                    "review_status": ("HUMAN_REVIEW_APPROVED" if i < 10 else "HUMAN_REVIEW_REJECTED"),
                    "reviewer": "tiago",
                    "reviewed_at": "2026-08-10T13:00:00Z",
                    "evidence_inspected": ["company", "email", "copy"],
                }
            )
            for i, row in enumerate(rows[:20])
        )
        + "\n",
        encoding="utf-8",
    )
    esr = {
        "EMAIL_SEND_READY_DISTINCT_COMPANIES": 60,
        "TARGET_CONFIRMED": 100,
        "funnel": {},
        "service_fit_unsupported_count": 0,
        "service_fit_ontology_ok": True,
        "esr_rows": rows,
        "not_ready_sample": not_ready,
        "process_terminal_counts": {
            "CONTACT_READY": 100,
            "CONTACT_RETRY_PENDING": 0,
            "CONTACT_NEVER_ATTEMPTED": 0,
        },
    }
    sources = {
        step: {"companies_attempted": 100}
        for step in (
            "official_site",
            "process_administrative_docs",
            "pncp_transparency_compras",
            "professional_councils_associations",
            "company_public_pages",
            "official_registry_corroboration",
        )
    }
    warmbly = {
        "PASS": True,
        "email_only": True,
        "whatsapp_enabled": False,
        "auto_send_enabled": False,
        "emails_per_hour": 10,
        "dispatch": {"state": "PAUSED_MANUAL_START"},
        "checks": {
            "reservoir_feed_import": "PASS",
            "smtp_imap_reply_stop": "PASS",
            "dnc_preserved": "PASS",
            "rolling_hot_set": "PASS",
            "outcomes_webhook": "PASS",
        },
    }
    sha = build_sha_binding(
        origin_main=tip,
        host_deployed=tip,
        runtime=tip,
        expected_origin_tip=tip,
    )
    manifest = emit_pack(
        out_dir=out,
        esr_report=esr,
        target_classes={"TARGET_CONFIRMED": 100},
        contact_terminals=esr["process_terminal_counts"],
        runtime_health={
            "FULLY_RECONCILED": True,
            "coverage_ratio": 1.0,
            "database_watermark": "2026-08-10T12:00:00Z",
        },
        universe_manifest=_universe(100),
        sha_binding=sha,
        warmbly_e2e=warmbly,
        source_yield={"sources": sources},
        expected_origin_tip=tip,
        human_review_decisions=decisions,
    )
    go = json.loads((out / "GO-NO-GO.json").read_text(encoding="utf-8"))
    assert go["PILOT_GO"] is True
    assert go["terminal_state"] == "GO_FOR_REAL_CONFENGE_EMAIL_PILOT"
    assert go["NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY"] is False
    assert go["dispatch"]["state"] == "PAUSED_MANUAL_START"
    assert manifest["PILOT_GO"] is True
