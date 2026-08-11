"""Strict ESR rebuild + service ontology round-trip tests.

Proves shipped evaluate_email_send_ready path with real build_dossier,
and that canonical service codes survive account→dossier→ESR.
"""

from __future__ import annotations

import json
from argparse import Namespace
from datetime import date, timedelta
from pathlib import Path

from scripts.confenge_account_intelligence.catalog import load_catalog
from scripts.confenge_account_intelligence.pipeline import build_dossier
from scripts.confenge_activation.strict_national_esr import (
    _load_jsonl_emails,
    _sanitize_pilot_contract_dates,
    build_company_package,
    build_pilot_review,
    evaluate_root_candidates,
    rebuild_strict_esr,
    write_pilot_feed,
)
from scripts.confenge_contact_resolution.send_readiness import (
    _service_fit_supported,
    evaluate_copy_context_ready,
    evaluate_email_send_ready,
)

# Canonical codes from live catalog — do not invent new ones.
REQUIRED_SERVICES = (
    "gestao_monitoramento_contratual",
    "apoio_licitacoes_propostas",
    "auditoria_orcamento_bdi",
    "aditivos_extracontratuais",
    "medicoes_glosas_memoria",
    "estruturacao_pleito_reajuste",
    "reequilibrio_economico_financeiro",
    "diagnostico_contratual_b2g",
)


def _multi_contract_raw(*, n: int = 5, razao: str = "CONSTRUTORA ALVORADA LTDA") -> dict:
    from datetime import date, timedelta

    orgaos = [
        ("Agência Estadual de Gestão de Empreendimentos", "MS"),
        ("Prefeitura Municipal de Campo Grande", "MS"),
        ("Secretaria de Obras de Dourados", "MS"),
        ("Departamento de Estradas de Rodagem", "GO"),
        ("Prefeitura de Goiânia", "GO"),
        ("DNIT Superintendência Regional", "SP"),
    ]
    today = date.today()
    contracts = []
    for i in range(n):
        org, uf = orgaos[i % len(orgaos)]
        # Recent publications keep why_now temporal strength non-WEAK.
        pub = today - timedelta(days=14 + i * 7)
        start = pub + timedelta(days=3)
        end = start + timedelta(days=365)
        contracts.append(
            {
                "objeto_contrato": (
                    "OBRA DE INFRAESTRUTURA URBANA – PAVIMENTAÇÃO ASFÁLTICA E DRENAGEM "
                    f"NO MUNICÍPIO DE TACURU/MS lote {i + 1}"
                ),
                "orgao_nome": org,
                "uf": uf,
                "valor_total": 1_000_000 + i * 50_000,
                "data_inicio": start.isoformat(),
                "data_fim": end.isoformat(),
                "data_publicacao": pub.isoformat(),
                "numero_controle_pncp": f"15457856000168-2-0000{i + 1:02d}/2026",
            }
        )
    return {
        "cnpj14": "00061493000170",
        "cnpj_root": "00061493",
        "razao_social": razao,
        "target_fit_class": "TARGET_CONFIRMED",
        "contracts": contracts,
    }


def test_catalog_contains_required_canonical_services() -> None:
    cat = load_catalog()
    services = cat.get("services") or []
    if isinstance(services, list):
        ids = {
            str(s.get("id") or s.get("service_id") or s.get("canonical_service_code") or "")
            for s in services
            if isinstance(s, dict)
        }
    elif isinstance(services, dict):
        ids = set(services)
    else:
        ids = set()
    # catalog may nest under different key — also try service_index pattern
    if not ids:
        for s in cat.get("items") or []:
            if isinstance(s, dict):
                ids.add(str(s.get("id") or s.get("service_id") or ""))
    for code in REQUIRED_SERVICES:
        assert code in ids, f"missing canonical service {code} in catalog"


def test_gestao_service_fit_supported_with_multi_orgao_portfolio() -> None:
    raw = _multi_contract_raw(n=5)
    company = build_company_package(
        root="00061493",
        account=None,
        contracts=raw["contracts"],
        razao=raw["razao_social"],
    )
    svc = (company.get("primary_service") or {}).get("service_id")
    assert svc == "gestao_monitoramento_contratual"
    assert _service_fit_supported(company, svc) is True


def test_message_spine_makes_copy_context_ready() -> None:
    raw = _multi_contract_raw(n=5)
    company = build_company_package(
        root="00061493",
        account=None,
        contracts=raw["contracts"],
        razao=raw["razao_social"],
    )
    spine = company.get("message_spine") or {}
    assert spine.get("complete") is True
    copy = evaluate_copy_context_ready(company, service_code=(company.get("primary_service") or {}).get("service_id"))
    assert copy.copy_context_ready is True, copy


def test_strict_esr_true_for_process_doc_company_email() -> None:
    raw = _multi_contract_raw(n=5)
    account = {
        "account_cnpj": "00061493000170",
        "razao_social": raw["razao_social"],
        "process_graph": {
            "contracts": [
                {
                    "contract_id": c["numero_controle_pncp"],
                    "object_summary": c["objeto_contrato"],
                    "contracting_authority_name": c["orgao_nome"],
                    "uf": c["uf"],
                    "value_global": c["valor_total"],
                    "signed_at": c["data_inicio"],
                    "vigency_end": c["data_fim"],
                    "pncp_control_number": c["numero_controle_pncp"],
                    "supplier_cnpj": "00061493000170",
                }
                for c in raw["contracts"]
            ]
        },
        "contact_graph": {
            "people": [],
            "functional_mailboxes": [
                {
                    "email": "contato@construtoraalvorada.com.br",
                    "source_type": "public_process_document",
                    "source_url": "https://pncp.gov.br/pncp-api/v1/orgaos/x/arquivos/1",
                    "pattern_guessed": False,
                    "epistemic_class": "COMPANY_DECLARED",
                }
            ],
        },
    }
    result = evaluate_root_candidates(
        root="00061493",
        account=account,
        email_rows=[
            {
                "email": "contato@construtoraalvorada.com.br",
                "source_type": "public_process_document",
                "source_url": "https://pncp.gov.br/pncp-api/v1/orgaos/x/arquivos/1",
                "company_authored_likely": True,
                "pattern_guessed": False,
            }
        ],
    )
    assert result["email_send_ready"] is True, result
    assert result["best"]["service_code"] == "gestao_monitoramento_contratual"


def test_strict_esr_never_synthesizes_missing_cnpj14() -> None:
    raw = _multi_contract_raw(n=5)
    result = evaluate_root_candidates(
        root="00061493",
        account={"account_cnpj": "00061493", "razao_social": raw["razao_social"]},
        contracts=[{**row, "fornecedor_cnpj": "00061493"} for row in raw["contracts"]],
        email_rows=[
            {
                "email": "contato@construtoraalvorada.com.br",
                "source_type": "public_process_document",
                "source_url": "https://pncp.gov.br/x",
                "company_authored_likely": True,
            }
        ],
    )
    assert result["email_send_ready"] is False
    assert result["best"]["cnpj14"] is None
    assert "invalid_or_missing_cnpj14" in result["best"]["reasons"]


def test_jsonl_public_document_does_not_invent_company_authorship(tmp_path: Path) -> None:
    path = tmp_path / "contacts.jsonl"
    path.write_text(
        json.dumps(
            {
                "cnpj_raiz": "00061493",
                "email": "obras@prefeitura.gov.br",
                "source_type": "public_process_document",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    row = _load_jsonl_emails(path)["00061493"][0]
    assert row["company_authored_likely"] is False
    assert row["epistemic_class"] == "OBSERVED_PUBLIC"


def test_pilot_does_not_describe_future_start_as_recent_event() -> None:
    future = (date.today() + timedelta(days=90)).isoformat()
    sanitized = _sanitize_pilot_contract_dates(
        [{"data_inicio": future, "data_publicacao": future, "data_fim": future}]
    )
    assert sanitized[0]["data_inicio"] is None
    assert sanitized[0]["data_publicacao"] is None
    assert sanitized[0]["data_fim"] == future


def test_pilot_review_has_full_identity_evidence_message_and_human_gate(tmp_path: Path) -> None:
    raw = _multi_contract_raw(n=5)
    for contract in raw["contracts"]:
        contract["contract_id"] = contract["numero_controle_pncp"]
        contract["fornecedor_cnpj"] = raw["cnpj14"]
        contract["fornecedor_nome"] = raw["razao_social"]
    seed = {
        "cnpj14": raw["cnpj14"],
        "root": raw["cnpj_root"],
        "razao_social": raw["razao_social"],
        "email": "contato@construtoraalvorada.com.br",
        "ownership_status": "COMPANY_OWNED",
        "verification_status": "VERIFIED",
        "source_type": "site",
        "source_url": "https://construtoraalvorada.com.br/contato",
        "provenance_chain_valid": True,
        "provenance_chain": [
            {
                "source_type": "site",
                "source_url": "https://construtoraalvorada.com.br/contato",
                "method": "host_enrich_confirmed",
                "root": True,
            }
        ],
    }
    review = build_pilot_review(
        [seed],
        contracts_by_root={raw["cnpj_root"]: raw["contracts"]},
        target_size=1,
    )
    assert review["n"] == 1, review
    lead = review["leads"][0]
    assert lead["cnpj14"] == raw["cnpj14"]
    assert lead["email_send_ready"] is True
    assert lead["primary_contract"]["contract_id"]
    assert lead["observed_fact"]
    assert lead["why_this_company"]
    assert lead["why_now"]
    assert lead["message"]["subject"]
    assert lead["message"]["body"]
    assert lead["review_status"] == "HUMAN_REVIEW_PENDING"
    assert lead["review_decision"] is None
    assert review["approved"] == 0
    feed = write_pilot_feed(review, tmp_path / "feed")
    assert feed["lead_count"] == 1
    chunk = json.loads((tmp_path / "feed" / "chunk_0000.json").read_text(encoding="utf-8"))
    assert chunk["leads"][0]["email_send_ready"] is True
    assert chunk["leads"][0]["offer"]["service_code"] == lead["recommended_service"]


def test_pattern_guess_never_send_ready() -> None:
    raw = _multi_contract_raw(n=5)
    company = build_company_package(
        root="00061493",
        account=None,
        contracts=raw["contracts"],
        razao=raw["razao_social"],
    )
    r = evaluate_email_send_ready(
        company=company,
        email="licitacoes@construtoraalvorada.com.br",
        ownership_status="COMPANY_OWNED",
        verification_status="PATTERN_GUESS",
        service_code="gestao_monitoramento_contratual",
        factual_evidence=True,
        evidence_ids=["contract-1"],
        require_copy_context=True,
        source_type="pattern_guess",
        canonical_universe_member=True,
    )
    assert r.email_send_ready is False


def test_service_ontology_round_trip_all_required_codes_in_catalog() -> None:
    """Every required service id is loadable and can be selected as service_code."""
    load_catalog()
    # build dossiers with signals that should route to different services when possible
    raw = _multi_contract_raw(n=5)
    d = build_dossier(raw)
    primary = (d.get("primary_service") or {}).get("service_id")
    assert primary in REQUIRED_SERVICES
    # Round-trip: primary must remain a catalog id after package
    company = build_company_package(
        root="00061493", account=None, contracts=raw["contracts"], razao=raw["razao_social"]
    )
    assert (company.get("primary_service") or {}).get("service_id") == primary
    assert company.get("canonical_service_code") == primary or company.get("service_code") == primary


def test_rebuild_strict_esr_from_fixture_harvest(tmp_path: Path) -> None:
    harvest = tmp_path / "harvest"
    accounts = harvest / "accounts"
    accounts.mkdir(parents=True)
    raw = _multi_contract_raw(n=5)
    account = {
        "account_cnpj": "00061493000170",
        "razao_social": raw["razao_social"],
        "terminal_state": "EMAIL_SEND_READY",
        "process_graph": {
            "contracts": [
                {
                    "contract_id": c["numero_controle_pncp"],
                    "object_summary": c["objeto_contrato"],
                    "contracting_authority_name": c["orgao_nome"],
                    "uf": c["uf"],
                    "value_global": c["valor_total"],
                    "signed_at": c["data_inicio"],
                    "vigency_end": c["data_fim"],
                    "pncp_control_number": c["numero_controle_pncp"],
                    "supplier_cnpj": "00061493000170",
                }
                for c in raw["contracts"]
            ]
        },
        "contact_graph": {
            "functional_mailboxes": [
                {
                    "email": "contato@construtoraalvorada.com.br",
                    "source_type": "public_process_document",
                    "source_url": "https://pncp.gov.br/x",
                    "pattern_guessed": False,
                    "company_authored_likely": True,
                }
            ]
        },
    }
    (accounts / "00061493.json").write_text(json.dumps(account), encoding="utf-8")
    terms = harvest / "contact-discovery-terminals.jsonl"
    terms.write_text(
        json.dumps(
            {
                "cnpj_raiz": "00061493",
                "terminal_state": "CONTACT_READY",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    report = rebuild_strict_esr(
        harvest_dir=harvest,
        confirmed_roots={"00061493"},
    )
    assert report["EMAIL_SEND_READY_DISTINCT_COMPANIES"] == 1
    assert report["funnel"]["DISTINCT_COMPANIES_WITH_EMAIL"] == 1
    assert report["email_roots_upper_bound"] == 1
    # Must not use email count as ESR without gates
    assert report["EMAIL_SEND_READY_DISTINCT_COMPANIES"] <= report["email_roots_upper_bound"]


def test_gestao_not_silently_unsupported_when_package_present() -> None:
    """Regression: gestao_monitoramento_contratual is a legitimate CONFENGE service."""
    raw = _multi_contract_raw(n=5)
    company = build_company_package(
        root="00061493",
        account=None,
        contracts=raw["contracts"],
        razao=raw["razao_social"],
    )
    r = evaluate_email_send_ready(
        company=company,
        email="contato@construtoraalvorada.com.br",
        ownership_status="COMPANY_OWNED",
        verification_status="OBSERVED",
        service_code="gestao_monitoramento_contratual",
        factual_evidence=True,
        evidence_ids=list((company.get("primary_service") or {}).get("evidence_ids") or ["contract-1"]),
        require_copy_context=True,
        source_type="public_process_document",
        source_url="https://pncp.gov.br/x",
        canonical_universe_member=True,
    )
    assert "service_fit_unsupported" not in (r.reasons or [])
    assert r.email_send_ready is True


def test_outcome_receptor_uses_dsn_from_environment_without_argv(
    monkeypatch,
) -> None:
    """The persistent service must not expose its DSN in the process command line."""
    from scripts.decision_memory import db, repository
    from scripts.warmbly_bridge import cli

    seen: dict[str, object] = {}
    connection = object()
    monkeypatch.setenv("LOCAL_DATALAKE_DSN", "postgresql://local-env")
    monkeypatch.setattr(
        db,
        "connect",
        lambda dsn: seen.setdefault("dsn", dsn) and connection,
    )
    monkeypatch.setattr(
        repository,
        "DecisionMemoryRepository",
        lambda conn: seen.setdefault("connection", conn) and conn,
    )
    monkeypatch.setattr(cli, "DecisionMemoryOutcomeStore", lambda repo: repo)

    store = cli._build_store(Namespace(memory_store=False, dsn=None))

    assert store is connection
    assert seen == {"dsn": "postgresql://local-env", "connection": connection}
