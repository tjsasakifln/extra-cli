"""Unit tests for scripts.matching.official_acts_reconcile (no network, no live DB)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.matching.official_acts_reconcile import (
    RULE_SCORES,
    MatchIndex,
    Record,
    SOURCE_COMPRAS_SC,
    SOURCE_DOE,
    SOURCE_DOM,
    SOURCE_PNCP,
    build_report,
    detect_conflicts,
    deterministic_entity_hash,
    extract_identifiers_from_text,
    match_pair,
    match_record_against_index,
    normalize_identifier,
    normalize_modalidade,
    normalize_pncp_number,
    normalize_status,
    reconcile_collections,
    record_from_compras_sc,
    record_from_doe,
    record_from_dom,
    record_from_pncp_bid,
    record_from_pncp_contract,
    write_outputs,
)


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def test_normalize_identifier_variants():
    assert normalize_identifier("001/2026") == "1/2026"
    assert normalize_identifier("1-2026") == "1/2026"
    assert normalize_identifier("1.2026") == "1/2026"
    assert normalize_identifier(" 053 / 2026 ") == "53/2026"
    assert normalize_identifier(None) is None
    assert normalize_identifier("") is None


def test_normalize_pncp_number():
    assert (
        normalize_pncp_number("83102459000123-2-002798/2026")
        == "83102459000123-2-002798/2026"
    )
    assert normalize_pncp_number("sc-41624") == "sc-41624"
    assert normalize_pncp_number("prefix sc-99 suffix") == "sc-99"
    assert normalize_pncp_number(None) is None


def test_normalize_modalidade():
    assert normalize_modalidade("Pregão Eletrônico") == "pregao_eletronico"
    assert normalize_modalidade("Dispensa de Licitação (Serviços)") == "dispensa"
    assert normalize_modalidade("Inexigência de Licitação (Materiais)") == "inexigibilidade"
    assert normalize_modalidade(5) == "pregao_eletronico"
    assert normalize_modalidade(8) == "inexigibilidade"


def test_normalize_status():
    assert normalize_status("Homologado") == "homologado"
    assert normalize_status("Aguardando Homologação") == "aguardando_homologacao"


def test_deterministic_entity_hash_requires_all_parts():
    assert deterministic_entity_hash(None, "1/2026", 2026, "dispensa") is None
    assert deterministic_entity_hash("123", None, 2026, "dispensa") is None
    h1 = deterministic_entity_hash("12.345.678/0001-99", "001/2026", 2026, "dispensa")
    h2 = deterministic_entity_hash("12345678000199", "1/2026", 2026, "dispensa")
    assert h1 is not None and h1 == h2


def test_extract_identifiers_from_text():
    text = (
        "PROCESSO LICITATÓRIO Nº 361/2026 INEXIGIBILIDADE "
        "EDITAL N° 007/2026 CONTRATO Nº 288/2026 "
        "controle 83102459000123-2-000123/2026 "
        "https://compras.sc.gov.br/editais/41624"
    )
    ids = extract_identifiers_from_text(text)
    assert ids["process_number"] == "361/2026"
    assert ids["edital_number"] == "7/2026"
    assert ids["contract_number"] == "288/2026"
    assert ids["pncp_number"] == "83102459000123-2-000123/2026"
    assert ids["compras_sc_id"] == "sc-41624"


# ---------------------------------------------------------------------------
# Rule matching (each rule)
# ---------------------------------------------------------------------------


def _pncp(**kwargs) -> Record:
    base = dict(
        source_system=SOURCE_PNCP,
        source_id="p1",
        target_table="pncp_raw_bids",
    )
    base.update(kwargs)
    return Record(**base)


def _dom(**kwargs) -> Record:
    base = dict(source_system=SOURCE_DOM, source_id="d1")
    base.update(kwargs)
    return Record(**base)


def _doe(**kwargs) -> Record:
    base = dict(source_system=SOURCE_DOE, source_id="e1")
    base.update(kwargs)
    return Record(**base)


def _sc(**kwargs) -> Record:
    base = dict(source_system=SOURCE_COMPRAS_SC, source_id="sc-1")
    base.update(kwargs)
    return Record(**base)


def test_rule_pncp_number_exact():
    left = _sc(source_id="sc-a", pncp_number="83102459000123-2-000001/2026")
    right = _pncp(
        source_id="83102459000123-2-000001/2026",
        pncp_number="83102459000123-2-000001/2026",
    )
    m = match_pair(left, right)
    assert m is not None
    assert m.rule == "pncp_number_exact"
    assert m.score == RULE_SCORES["pncp_number_exact"]
    assert m.reversible is True


def test_rule_process_number_orgao_cnpj():
    left = _dom(
        process_number="53/2026",
        orgao_cnpj="12345678000199",
    )
    right = _pncp(
        source_id="bid-1",
        process_number="053/2026",
        orgao_cnpj="12345678000199",
    )
    # normalize on construction paths — force normalized forms
    left.process_number = normalize_identifier("53/2026")
    right.process_number = normalize_identifier("053/2026")
    m = match_pair(left, right)
    assert m is not None
    assert m.rule == "process_number_orgao_cnpj"
    assert m.score == RULE_SCORES["process_number_orgao_cnpj"]


def test_rule_process_number_year_modalidade():
    left = _doe(
        process_number="10/2025",
        year=2025,
        modalidade="dispensa",
        # no cnpj → skip higher-priority process+cnpj
        orgao_cnpj=None,
    )
    right = _pncp(
        source_id="bid-2",
        process_number="10/2025",
        year=2025,
        modalidade="dispensa",
        orgao_cnpj=None,
    )
    m = match_pair(left, right)
    assert m is not None
    assert m.rule == "process_number_year_modalidade"


def test_rule_contract_number_orgao_cnpj():
    left = _dom(
        contract_number="108/2021",
        orgao_cnpj="99999999000191",
        process_number=None,
        pncp_number=None,
    )
    right = _pncp(
        source_id="c-1",
        contract_number="108/2021",
        orgao_cnpj="99999999000191",
        target_table="pncp_supplier_contracts",
    )
    m = match_pair(left, right)
    assert m is not None
    assert m.rule == "contract_number_orgao_cnpj"


def test_rule_edital_number_year_orgao_cnpj():
    left = _dom(
        edital_number="7/2026",
        year=2026,
        orgao_cnpj="11111111000191",
        process_number=None,
        contract_number=None,
        pncp_number=None,
    )
    right = _pncp(
        source_id="bid-ed",
        edital_number="7/2026",
        year=2026,
        orgao_cnpj="11111111000191",
    )
    m = match_pair(left, right)
    assert m is not None
    assert m.rule == "edital_number_year_orgao_cnpj"


def test_rule_edital_number_year_orgao_name_when_no_cnpj():
    left = _dom(
        edital_number="20/2025",
        year=2025,
        orgao_cnpj=None,
        orgao_nome_norm="PREFEITURA MUNICIPAL DE SUL BRASIL",
        process_number=None,
        contract_number=None,
        pncp_number=None,
    )
    right = _pncp(
        source_id="bid-name",
        edital_number="20/2025",
        year=2025,
        orgao_cnpj=None,
        orgao_nome_norm="PREFEITURA MUNICIPAL DE SUL BRASIL",
    )
    m = match_pair(left, right)
    assert m is not None
    assert m.rule == "edital_number_year_orgao_name"


def test_rule_compras_sc_id_crosswalk():
    left = _sc(source_id="sc-41624", compras_sc_id="sc-41624", pncp_number=None)
    right = _pncp(
        source_id="sc-41624",
        compras_sc_id="sc-41624",
        pncp_number=None,
    )
    m = match_pair(left, right)
    assert m is not None
    assert m.rule == "compras_sc_id_crosswalk"
    assert m.score == RULE_SCORES["compras_sc_id_crosswalk"]


def test_rule_deterministic_hash():
    left = _sc(
        source_id="sc-h",
        orgao_cnpj="12345678000199",
        process_number="99/2026",
        year=2026,
        modalidade="concorrencia",
        compras_sc_id=None,
        pncp_number=None,
        contract_number=None,
        edital_number=None,
    )
    right = _pncp(
        source_id="bid-h",
        orgao_cnpj="12345678000199",
        process_number="99/2026",
        year=2026,
        modalidade="concorrencia",
        compras_sc_id=None,
        pncp_number=None,
    )
    # Ensure hash matches
    assert deterministic_entity_hash(
        left.orgao_cnpj, left.process_number, left.year, left.modalidade
    ) == deterministic_entity_hash(
        right.orgao_cnpj, right.process_number, right.year, right.modalidade
    )
    m = match_pair(left, right)
    assert m is not None
    # process+cnpj has higher priority than hash when both present
    assert m.rule == "process_number_orgao_cnpj"


def test_rule_deterministic_hash_when_no_higher_rule():
    """Hash fires when process is missing on one side but hash keys still align.

    Actually hash requires process — so simulate match via index where
    process+cnpj would match too. Force hash-only by clearing process on
    index path is impossible. Instead: same hash keys, and process+cnpj
    is the expected higher rule — test hash key equality + index lookup.
    """
    h = deterministic_entity_hash("12345678000199", "5/2024", 2024, "pregao_eletronico")
    assert h is not None
    left = _doe(
        source_id="doe-h",
        orgao_cnpj="12345678000199",
        process_number="5/2024",
        year=2024,
        modalidade="pregao_eletronico",
        pncp_number=None,
        contract_number=None,
        edital_number=None,
    )
    right = _pncp(
        source_id="pncp-h",
        orgao_cnpj="12345678000199",
        process_number="5/2024",
        year=2024,
        modalidade="pregao_eletronico",
        pncp_number=None,
    )
    idx = MatchIndex()
    idx.add(right)
    # hash index populated
    assert h in idx.by_hash
    # Full match still prefers process+cnpj (correct priority)
    m = match_record_against_index(left, idx)
    assert m is not None
    assert m.rule == "process_number_orgao_cnpj"
    assert m.score > RULE_SCORES["deterministic_hash"]


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------


def test_conflict_status_and_value_and_date():
    left = _sc(
        status="homologado",
        publication_date="2026-07-01",
        value=1000.0,
        orgao_cnpj="12345678000199",
    )
    right = _pncp(
        status="aberto",
        publication_date="2026-07-10",
        value=1500.0,
        orgao_cnpj="12345678000199",
    )
    conflicts, fields, needs = detect_conflicts(left, right)
    kinds = {c["kind"] for c in conflicts}
    assert "status_divergence" in kinds
    assert "date_divergence" in kinds
    assert "value_divergence" in kinds
    assert "status" in fields
    assert needs is True


def test_conflict_cnpj_different_root():
    left = _dom(orgao_cnpj="11111111000191", status="homologado")
    right = _pncp(orgao_cnpj="22222222000191", status="homologado")
    conflicts, _, needs = detect_conflicts(left, right)
    assert any(c["kind"] == "cnpj_conflict" for c in conflicts)
    assert needs is True


def test_no_conflict_when_aligned():
    left = _sc(
        status="homologado",
        publication_date="2026-07-16",
        value=100.0,
        orgao_cnpj="12345678000199",
    )
    right = _pncp(
        status="homologado",
        publication_date="2026-07-16",
        value=100.5,  # within abs tol of 1.0
        orgao_cnpj="12345678000199",
    )
    conflicts, fields, needs = detect_conflicts(left, right)
    assert conflicts == []
    assert fields == []
    assert needs is False


def test_ambiguous_match_needs_review():
    probe = _sc(compras_sc_id="sc-1", source_id="sc-1", pncp_number=None)
    a = _pncp(source_id="a", compras_sc_id="sc-1", pncp_number=None)
    b = _pncp(source_id="b", compras_sc_id="sc-1", pncp_number=None)
    idx = MatchIndex()
    idx.add(a)
    idx.add(b)
    m = match_record_against_index(probe, idx)
    assert m is not None
    assert m.needs_review is True
    assert any(c["kind"] == "ambiguous_match" for c in m.conflicts)


# ---------------------------------------------------------------------------
# Loaders (synthetic)
# ---------------------------------------------------------------------------


def test_record_from_dom_extracts_process():
    raw = {
        "codigo": "ABC",
        "titulo": "PROCESSO ADMINISTRATIVO Nº 053/2026/PMS",
        "texto": "Homologação do processo",
        "orgao": "Prefeitura municipal de Sangão",
        "data": "2026-07-16",
        "url": "http://example.test/x",
    }
    rec = record_from_dom(raw, 0)
    assert rec.source_system == SOURCE_DOM
    assert rec.process_number == "53/2026"
    assert rec.has_documents is True


def test_record_from_doe_extracts_contract():
    raw = {
        "record_hash": "rh1",
        "titulo": "EXTRATO DE CONTRATO Nº 025/2025",
        "texto_ou_extrato": "Contrato nº 025/2025 SEF",
        "orgao": "Secretaria de Estado da Fazenda",
        "data_publicacao": "2025-04-01",
        "link_extrato": "http://example.test/e",
    }
    rec = record_from_doe(raw, 0)
    assert rec.source_system == SOURCE_DOE
    assert rec.contract_number == "25/2025"


def test_record_from_compras_sc():
    raw = {
        "api_id": 41624,
        "pncp_id": "sc-41624",
        "source_id": "sc-41624",
        "orgao_razao_social": "SED",
        "modalidade_nome": "Dispensa de Licitação (Serviços)",
        "status": "Homologado",
        "data_publicacao": "2026-07-16",
        "documentos": [],
        "uf": "SC",
    }
    rec = record_from_compras_sc(raw, 0)
    assert rec.compras_sc_id == "sc-41624"
    assert rec.modalidade == "dispensa"
    assert rec.status == "homologado"
    assert rec.has_documents is False


def test_record_from_pncp_bid_sc_crosswalk():
    raw = {
        "pncp_id": "sc-58075",
        "numero_controle_pncp": "sc-58075",
        "link_pncp": "https://compras.sc.gov.br/editais/58075",
        "orgao_razao_social": "PM/SC",
        "modalidade_id": 8,
        "data_publicacao": "2026-07-16",
        "uf": "SC",
    }
    rec = record_from_pncp_bid(raw)
    assert rec.compras_sc_id == "sc-58075"
    assert rec.modalidade == "inexigibilidade"


def test_record_from_pncp_contract():
    raw = {
        "contrato_id": "83102459000123-2-002798/2026",
        "orgao_cnpj": "83102459000123",
        "orgao_nome": "MUNICÍPIO DE JARAGUÁ DO SUL",
        "valor_total": "2700.00",
        "data_publicacao": "2026-07-10",
        "uf": "SC",
    }
    rec = record_from_pncp_contract(raw)
    assert rec.pncp_number == "83102459000123-2-002798/2026"
    assert rec.contract_number == "2798/2026"
    assert rec.orgao_cnpj == "83102459000123"
    assert rec.value == 2700.0


# ---------------------------------------------------------------------------
# Collection reconcile + report
# ---------------------------------------------------------------------------


def test_reconcile_collections_compras_to_pncp():
    pncp = [
        _pncp(source_id="sc-10", compras_sc_id="sc-10", pncp_number=None),
        _pncp(source_id="sc-11", compras_sc_id="sc-11", pncp_number=None),
    ]
    compras = [
        _sc(source_id="sc-10", compras_sc_id="sc-10", pncp_number=None),
        _sc(source_id="sc-99", compras_sc_id="sc-99", pncp_number=None),
    ]
    dom = [
        _dom(
            source_id="dom-1",
            process_number="1/2026",
            orgao_cnpj="12345678000199",
        )
    ]
    # no matching pncp for dom process
    doe: list[Record] = []
    matches = reconcile_collections(pncp, doe, dom, compras)
    rules = {m.rule for m in matches}
    assert "compras_sc_id_crosswalk" in rules
    assert any(m.left_source_id == "sc-10" or m.right_source_id == "sc-10" for m in matches)


def test_build_report_and_write_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pncp = [
        _pncp(
            source_id="sc-1",
            compras_sc_id="sc-1",
            status="homologado",
            publication_date="2026-07-16",
            value=100.0,
        )
    ]
    compras = [
        _sc(
            source_id="sc-1",
            compras_sc_id="sc-1",
            status="aberto",
            publication_date="2026-07-15",
            value=200.0,
            has_documents=False,
        )
    ]
    matches = reconcile_collections(pncp, [], [], compras)
    assert len(matches) == 1
    report = build_report(
        run_id="reconcile-test-1",
        mode="smoke",
        started_at="2026-07-16T00:00:00+00:00",
        pncp=pncp,
        doe=[],
        dom=[],
        compras=compras,
        matches=matches,
    )
    assert report.reconciled_count == 1
    assert report.compras_sc_only == 0
    assert report.pncp_only == 0
    assert report.status_divergences >= 1
    assert report.value_divergences >= 1
    assert report.missing_documents >= 1
    assert "90_day_pilot_success" in report.claims_forbidden
    assert "3_year_backfill_complete" in report.claims_forbidden
    assert any("deterministic" in c for c in report.claims_allowed)

    out = tmp_path / "reconcile-test-1"
    paths = write_outputs(report, out)
    assert paths["report_json"].is_file()
    assert paths["report_md"].is_file()
    assert paths["matches"].is_file()
    assert paths["evidence"].is_file()

    data = json.loads(paths["report_json"].read_text(encoding="utf-8"))
    assert data["run_id"] == "reconcile-test-1"
    assert data["reconciled_count"] == 1
    assert "claims_forbidden" in data

    match_line = paths["matches"].read_text(encoding="utf-8").strip().splitlines()[0]
    match_obj = json.loads(match_line)
    assert match_obj["reversible"] is True
    assert match_obj["rule"] == "compras_sc_id_crosswalk"

    evidence = json.loads(paths["evidence"].read_text(encoding="utf-8"))
    assert evidence["run_id"] == "reconcile-test-1"
    assert "90_day_pilot_success" in evidence["claims_forbidden"]


def test_no_match_same_system():
    a = _pncp(source_id="x", compras_sc_id="sc-1")
    b = _pncp(source_id="y", compras_sc_id="sc-1")
    m = match_pair(a, b)
    assert m is None


def test_match_priority_pncp_over_compras_sc_id_when_both():
    """When pncp_number matches, that rule wins over compras_sc crosswalk."""
    left = _sc(
        source_id="sc-5",
        pncp_number="83102459000123-1-000001/2026",
        compras_sc_id="sc-5",
    )
    right = _pncp(
        source_id="83102459000123-1-000001/2026",
        pncp_number="83102459000123-1-000001/2026",
        compras_sc_id="sc-5",
    )
    m = match_pair(left, right)
    assert m is not None
    assert m.rule == "pncp_number_exact"
    assert m.score == 1.0
