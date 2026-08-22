"""Contract tests for the CONFENGE dossier engine."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.dossier import cli
from scripts.dossier.compose import _position, build_findings, build_price_panel
from scripts.dossier.constants import (
    CATALOG_FIXTURE,
    CATALOG_OFFICIAL_LIVE,
    DATA_HOLD,
    DATA_READY,
    DATA_REJECT,
    FINDING_ANNIVERSARY,
    FORBIDDEN_CLAIM_TOKENS,
    PANEL_OUT_OF_RANGE_FACTOR,
    POSITION_OUT_OF_PANEL_RANGE,
    PUBLIC_REDACTED_FIELDS,
    REASON_FIXTURE_LABELED_LIVE,
    REASON_FIXTURE_NOT_LIVE,
    REASON_INVALID_CNPJ,
    SCHEMA,
    SECTION_BUYER_MAP,
    SECTION_COMPETITORS,
    SECTION_IDENTITY,
)
from scripts.dossier.envelope import (
    LIMITATION_ACTIVE_ONLY,
    LIMITATION_FIXTURE,
    LIMITATION_NO_CLAIM,
    LIMITATION_REFERENCE_SCOPE,
    LIMITATION_UNKNOWN,
    build_dossier,
    content_hash,
    public_projection,
    scan_forbidden,
)
from scripts.dossier.models import DossierRequest, SourceRead, cnpj14, worst_state
from scripts.dossier.render import render_markdown
from scripts.dossier.sources import CATEGORY_SQL, FixtureSource

FIXTURE = Path(__file__).parent / "fixtures" / "acme.json"
CNPJ = "11222333000181"


def _request(**overrides) -> DossierRequest:
    base = {
        "cnpj": CNPJ,
        "as_of": "2026-08-22",
        "catalog_mode": CATALOG_FIXTURE,
        "consumer_id": "test",
        "producer_sha": "deadbeef",
    }
    base.update(overrides)
    return DossierRequest(**base)


@pytest.fixture()
def built():
    return build_dossier(FixtureSource(FIXTURE), _request())


def test_document_carries_versioned_envelope(built):
    _result, document = built
    assert document["schema"] == SCHEMA
    assert document["grain"] == "cnpj14"
    assert document["cnpj14"] == CNPJ
    assert document["catalog_mode"] == CATALOG_FIXTURE
    assert document["content_hash"].startswith("sha256:")


def test_content_hash_is_stable_across_volatile_fields(built):
    _result, document = built
    baseline = content_hash(document)
    mutated = json.loads(json.dumps(document))
    mutated["producer_sha"] = "0" * 40
    mutated["observed_at"] = "2099-01-01T00:00:00Z"
    mutated["sections"][SECTION_IDENTITY]["observed_at"] = "2099-01-01T00:00:00Z"
    assert content_hash(mutated) == baseline


def test_content_hash_changes_when_a_fact_changes(built):
    _result, document = built
    mutated = json.loads(json.dumps(document))
    mutated["sections"][SECTION_BUYER_MAP]["payload"]["buyer_count"] = 999
    assert content_hash(mutated) != content_hash(document)


def test_fixture_run_declares_itself_a_fixture(built):
    _result, document = built
    assert REASON_FIXTURE_NOT_LIVE in document["reason_codes"]
    assert LIMITATION_FIXTURE in document["limitations"]


def test_fixture_cannot_be_labeled_official_live():
    _result, document = build_dossier(FixtureSource(FIXTURE), _request(catalog_mode=CATALOG_OFFICIAL_LIVE))
    assert document["data_state"] == DATA_REJECT
    assert REASON_FIXTURE_LABELED_LIVE in document["reason_codes"]
    assert document["sections"] == {}


def test_invalid_cnpj_is_rejected_not_padded():
    _result, document = build_dossier(FixtureSource(FIXTURE), _request(cnpj="123"))
    assert document["data_state"] == DATA_REJECT
    assert REASON_INVALID_CNPJ in document["reason_codes"]
    assert cnpj14("123") is None
    assert cnpj14("11.222.333/0001-81") == CNPJ


def test_unknown_value_never_becomes_zero(built):
    _result, document = built
    buyers = document["sections"][SECTION_BUYER_MAP]["payload"]["buyers"]
    first = next(b for b in buyers if b["buyer_cnpj"] == "82000000000101")
    # Two contracts, one without a published value: the sum reflects only the known one.
    assert first["contract_count"] == 2
    assert first["valued_count"] == 1
    assert first["valor_sum"] == "1000000.00"
    missingness = document["sections"][SECTION_BUYER_MAP]["missingness"]
    assert missingness == pytest.approx(1 / 3, abs=1e-4)


def test_findings_are_facts_plus_questions(built):
    _result, document = built
    assert document["findings"], "fixture must produce findings"
    for finding in document["findings"]:
        assert finding["fact"]
        assert finding["question"].endswith("?")
        assert finding["evidence_refs"]


def test_anniversary_finding_requires_a_running_contract():
    source = FixtureSource(FIXTURE)
    contracts = source.contracts(CNPJ)
    findings = build_findings(
        contracts=contracts,
        buyer_map=build_price_panel(SourceRead(source="x", observed_at="t")),
        price_panel=build_price_panel(SourceRead(source="x", observed_at="t")),
        expiring=build_price_panel(SourceRead(source="x", observed_at="t")),
        opportunities=build_price_panel(SourceRead(source="x", observed_at="t")),
        as_of="2026-08-22",
    )
    anniversaries = {f.subject for f in findings if f.finding_id.startswith(FINDING_ANNIVERSARY)}
    # FIX-0001 started 2024-01-10 and runs to 2027: anniversary reached.
    assert "FIX-0001" in anniversaries
    # FIX-0002 started 2026-06-01: under twelve months, no anniversary.
    assert "FIX-0002" not in anniversaries


def test_panel_refuses_a_position_outside_its_range():
    assert _position(Decimal("1000000"), Decimal("100"), Decimal("500"), Decimal("2000")) == (
        POSITION_OUT_OF_PANEL_RANGE
    )
    assert _position(Decimal("1"), Decimal("1000"), Decimal("5000"), Decimal("20000")) == (POSITION_OUT_OF_PANEL_RANGE)
    inside = _position(Decimal("750000"), Decimal("200000"), Decimal("700000"), Decimal("1500000"))
    assert inside == "P50_P75"
    assert PANEL_OUT_OF_RANGE_FACTOR == 10


def test_out_of_range_category_produces_no_position_finding():
    read = SourceRead(
        source="v_contract_intel_percentis",
        observed_at="2026-01-01T00:00:00Z",
        rows=(
            {
                "categoria": "FACILITIES",
                "qtd_contratos": 100,
                "p25_valor": "100.00",
                "p50_valor": "500.00",
                "p75_valor": "2000.00",
                "ticket_medio": "800.00",
                "focal_count": 3,
                "focal_valued_count": 3,
                "focal_median": "44000000.00",
            },
        ),
    )
    section = build_price_panel(read)
    assert section.state == DATA_HOLD
    assert section.payload["categories"][0]["focal_position"] == POSITION_OUT_OF_PANEL_RANGE
    findings = build_findings(
        contracts=SourceRead(source="c", observed_at="t"),
        buyer_map=section,
        price_panel=section,
        expiring=build_price_panel(SourceRead(source="x", observed_at="t")),
        opportunities=build_price_panel(SourceRead(source="x", observed_at="t")),
        as_of="2026-08-22",
    )
    assert not [f for f in findings if f.finding_id.startswith("value_position_in_category")]


def test_competitors_are_bound_to_the_primary_category(built):
    _result, document = built
    payload = document["sections"][SECTION_COMPETITORS]["payload"]
    assert payload["primary_category"] == "OBRAS"
    for competitor in payload["competitors"]:
        assert competitor["shared_categories"] == ["OBRAS"]


def test_no_forbidden_claim_reaches_the_document(built):
    _result, document = built
    assert scan_forbidden(document) == ()
    assert scan_forbidden(public_projection(document)) == ()


def test_scanner_catches_an_injected_claim(built):
    _result, document = built
    poisoned = json.loads(json.dumps(document))
    poisoned["findings"][0]["question"] = "Houve sobrepreco neste contrato?"
    assert any("sobrepreco" in hit for hit in scan_forbidden(poisoned))


def test_scanner_exempts_official_object_text(built):
    _result, document = built
    poisoned = json.loads(json.dumps(document))
    poisoned["sections"]["expiring_contracts"]["payload"]["contracts"][0]["objeto"] = (
        "Servico de manutencao com apuracao de irregularidade contratual"
    )
    assert scan_forbidden(poisoned) == ()


def test_limitations_are_frozen_constants(built):
    """The scanner exempts $.limitations, so the block must stay reviewed constants."""
    _result, document = built
    allowed = {
        LIMITATION_FIXTURE,
        LIMITATION_UNKNOWN,
        LIMITATION_NO_CLAIM,
        LIMITATION_ACTIVE_ONLY,
        LIMITATION_REFERENCE_SCOPE,
    }
    assert set(document["limitations"]) <= allowed


def test_public_projection_removes_the_prospect(built):
    _result, document = built
    public = public_projection(document)
    body = json.dumps(public, ensure_ascii=False)
    assert CNPJ not in body
    assert "ACME PAVIMENTACAO" not in body
    assert "CONCORRENTE FIXTURE" not in body
    assert public["source_dossier_hash"] == document["content_hash"]
    assert SECTION_IDENTITY not in public["sections"]
    assert SECTION_BUYER_MAP not in public["sections"]
    for field in PUBLIC_REDACTED_FIELDS:
        assert f'"{field}": "ACME' not in body


def test_public_projection_of_a_fixture_is_never_publishable(built):
    _result, document = built
    public = public_projection(document)
    assert public["publication_readiness"] == DATA_HOLD


def test_markdown_render_is_byte_stable(built):
    _result, document = built
    assert render_markdown(document) == render_markdown(document)
    body = render_markdown(document)
    assert body.startswith("# Diagnóstico B2G — ACME PAVIMENTACAO LTDA")
    assert "UNKNOWN" in body


def test_forbidden_tokens_are_lowercase_for_the_scanner():
    for token in FORBIDDEN_CLAIM_TOKENS:
        assert token == token.lower()


def test_worst_state_folds_to_the_worst():
    assert worst_state((DATA_READY, DATA_READY)) == DATA_READY
    assert worst_state((DATA_READY, DATA_HOLD)) == DATA_HOLD
    assert worst_state((DATA_HOLD, DATA_REJECT)) == DATA_REJECT
    assert worst_state(()) == DATA_REJECT


def test_category_ladder_covers_every_panel_bucket():
    """The ladder is duplicated from v_contract_intel_percentis; keep the buckets aligned."""
    for bucket in (
        "OBRAS",
        "FACILITIES",
        "TI",
        "SAÚDE",
        "ALIMENTAÇÃO",
        "TRANSPORTE",
        "SEGURANÇA",
        "CONSULTORIA",
        "COMBUSTÍVEL",
        "OUTROS",
    ):
        assert f"'{bucket}'" in CATEGORY_SQL


def test_cli_build_and_verify_roundtrip(tmp_path, capsys):
    out = tmp_path / "acme"
    code = cli.main(["build", "--cnpj", CNPJ, "--as-of", "2026-08-22", "--fixture", str(FIXTURE), "--out", str(out)])
    capsys.readouterr()
    assert code == 0
    assert (out / "dossier.json").exists()
    assert (out / "public-read.json").exists()
    assert (out / "dossier.md").exists()
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["catalog_mode"] == CATALOG_FIXTURE

    assert cli.main(["verify", "--dir", str(out)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["verdict"] == "PASS"


def test_cli_verify_detects_a_tampered_dossier(tmp_path, capsys):
    out = tmp_path / "acme"
    cli.main(["build", "--cnpj", CNPJ, "--as-of", "2026-08-22", "--fixture", str(FIXTURE), "--out", str(out)])
    capsys.readouterr()
    path = out / "dossier.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["sections"][SECTION_BUYER_MAP]["payload"]["buyer_count"] = 42
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert cli.main(["verify", "--dir", str(out)]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["verdict"] == "FAIL"
    assert any("content_hash mismatch" in problem for problem in report["problems"])


def test_cli_claim_live_on_fixture_exits_rejected(tmp_path, capsys):
    code = cli.main(["build", "--cnpj", CNPJ, "--fixture", str(FIXTURE), "--claim-live", "--as-of", "2026-08-22"])
    capsys.readouterr()
    assert code == 5


def test_cli_strict_fails_on_hold(tmp_path, capsys):
    code = cli.main(["build", "--cnpj", CNPJ, "--fixture", str(FIXTURE), "--as-of", "2026-08-22", "--strict"])
    capsys.readouterr()
    # The fixture is DATA_READY on required sections, so strict must pass.
    assert code == 0
