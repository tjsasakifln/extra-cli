"""Authoritative full-snapshot and revocation semantics for confenge.outreach.v1."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

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
                    "verification_status": "OBSERVED",
                    "email_explicitly_published": True,
                    "name_explicitly_published": True,
                    "role_explicitly_published": True,
                    "human_identity_evidence_valid": True,
                    "identity_evidence_urls": [f"https://{domains[index]}/equipe"],
                    "evidence_sha256": f"{index + 1:064x}",
                    "provenance": {
                        "source_type": "site",
                        "source_url": f"https://{domains[index]}/equipe",
                        "observed_at": NOW,
                        "evidence_sha256": f"{index + 1:064x}",
                    },
                },
                {
                    "name": "Joao de Lima",
                    "role": "Responsavel Tecnico",
                    "email": f"joao.lima@{domains[index]}",
                    "ownership_status": "COMPANY_OWNED",
                    "verification_status": "OBSERVED",
                    "confidence": "0.8",
                    "email_explicitly_published": True,
                    "name_explicitly_published": True,
                    "role_explicitly_published": True,
                    "human_identity_evidence_valid": True,
                    "identity_evidence_urls": [f"https://{domains[index]}/equipe-tecnica"],
                    "evidence_sha256": f"{index + 100:064x}",
                    "provenance": {
                        "source_type": "site",
                        "source_url": f"https://{domains[index]}/equipe-tecnica",
                        "observed_at": NOW,
                        "evidence_sha256": f"{index + 100:064x}",
                    },
                },
            ],
        }
        for index, row in enumerate(universe)
    ]
    intel_path = _write_jsonl(source / "intelligence.jsonl", intelligence)
    contacts_path = _write_jsonl(source / "contacts.jsonl", contacts)
    out = source / "feed"
    result = export_outreach(
        ExportConfig(
            universe=universe_path,
            account_intelligence=intel_path,
            contacts=contacts_path,
            target_fit_snapshot=target_fit_path,
            expected_universe_count=len(universe),
            out_dir=out,
            generated_at=NOW,
            datalake_watermark=datalake_watermark,
            repo_sha="authoritative-test",
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
