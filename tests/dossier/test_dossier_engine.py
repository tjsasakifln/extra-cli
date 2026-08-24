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
    """Every focal consumer calls the same classifier used by the panel view."""
    assert CATEGORY_SQL == "public.contract_category_v1({col})"


def test_default_scope_is_both_and_national_hold_blocks_unqualified_position(built):
    result, document = built
    panel = document["sections"]["price_panel"]
    assert document["parameters"]["reference_scope"] == "BOTH"
    assert panel["payload"]["requested_scope"] == "BOTH"
    assert [item["scope_kind"] for item in panel["payload"]["panels"]] == ["REGIONAL", "NATIONAL"]
    assert panel["payload"]["panels"][1]["state"] == DATA_HOLD
    assert panel["payload"]["panels"][1]["categories"] == []
    required_metadata = {
        "scope_id",
        "reference_state",
        "geography",
        "denominator",
        "as_of",
        "source",
        "sample_count",
        "coverage",
        "missingness",
        "method",
        "hash",
        "limitations",
    }
    assert all(required_metadata <= item.keys() for item in panel["payload"]["panels"])
    assert panel["state"] == DATA_HOLD
    assert not [f for f in result.findings if f.finding_id.startswith("value_position_in_category")]


def test_explicit_regional_scope_preserves_scoped_comparison():
    result, document = build_dossier(FixtureSource(FIXTURE), _request(reference_scope="REGIONAL"))
    panel = document["sections"]["price_panel"]
    assert panel["payload"]["requested_scope"] == "REGIONAL"
    assert [item["scope_kind"] for item in panel["payload"]["panels"]] == ["REGIONAL"]
    assert panel["payload"]["panels"][0]["scope_id"] == "regional_200km:fixture"
    assert panel["payload"]["panels"][0]["source"]["id"] == "fixture"
    assert result.request.reference_scope == "REGIONAL"


def test_regional_authority_hold_cannot_be_promoted_by_comparable_values():
    read = SourceRead(
        source="v_contract_intel_reference_scopes_v1",
        observed_at="t",
        rows=(
            {
                "scope_kind": "REGIONAL",
                "scope_id": "regional:test",
                "reference_state": DATA_HOLD,
                "categoria": "OBRAS",
                "p25_valor": "100",
                "p50_valor": "200",
                "p75_valor": "300",
                "focal_median": "200",
                "qtd_contratos": 10,
                "focal_count": 1,
                "focal_valued_count": 1,
            },
        ),
    )
    section = build_price_panel(read, reference_scope="REGIONAL")
    panel = section.payload["panels"][0]
    assert panel["reference_state"] == DATA_HOLD
    assert panel["state"] == DATA_HOLD
    assert section.state == DATA_HOLD


def test_missing_official_regional_authority_is_unknown_not_fixture():
    read = SourceRead(
        source="v_contract_intel_reference_scopes_v1",
        observed_at="t",
        rows=(
            {
                "scope_kind": "NATIONAL",
                "scope_id": "national:unavailable",
                "reference_state": DATA_HOLD,
            },
        ),
    )
    panel = build_price_panel(read, reference_scope="BOTH").payload["panels"][0]
    assert panel["scope_id"] == "regional:unavailable"
    assert panel["reference_state"] == DATA_HOLD
    assert panel["source"] == {"id": "UNKNOWN", "version": "UNKNOWN"}
    assert panel["method"] == {"status": "UNAVAILABLE"}


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
    # BOTH is the safe default and the fixture has no national authority.
    assert code == 4


def test_handoff_is_ready_only_for_official_live(tmp_path):
    from scripts.dossier.handoff import (
        DECISION_BLOCKED,
        REASON_NOT_OFFICIAL_LIVE,
        REASON_NOT_PUBLISHABLE,
        decide,
        verify_handoff,
        write_handoff,
    )

    fixture_public = {
        "catalog_mode": CATALOG_FIXTURE,
        "data_state": DATA_READY,
        "publication_readiness": DATA_HOLD,
        "content_hash": "sha256:abc",
        "reason_codes": [],
    }
    decision, reasons = decide(fixture_public)
    assert decision == DECISION_BLOCKED
    assert REASON_NOT_OFFICIAL_LIVE in reasons
    assert REASON_NOT_PUBLISHABLE in reasons

    root = tmp_path / "rendezvous"
    result = write_handoff(fixture_public, {"dossier_id": "d", "producer_sha": "s"}, root)
    assert result["decision"] == DECISION_BLOCKED
    assert (root / "BLOCKED.json").exists()
    assert not (root / "READY.json").exists()
    assert verify_handoff(root) == []


def test_handoff_never_grants_index_authorization(tmp_path):
    from scripts.dossier.handoff import verify_handoff, write_handoff

    public = {
        "catalog_mode": CATALOG_OFFICIAL_LIVE,
        "data_state": DATA_READY,
        "publication_readiness": DATA_READY,
        "content_hash": "sha256:abc",
        "source_dossier_hash": "sha256:def",
        "reason_codes": [],
    }
    root = tmp_path / "rendezvous"
    result = write_handoff(public, {"dossier_id": "d", "producer_sha": "s"}, root)
    assert result["decision"] == "READY"
    assert verify_handoff(root) == []
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["index_authorization"] is False
    assert manifest["publication_authorization"] is False
    assert manifest["carries_prospect_identity"] is False


def test_handoff_verify_detects_tampering(tmp_path):
    from scripts.dossier.handoff import verify_handoff, write_handoff

    public = {
        "catalog_mode": CATALOG_OFFICIAL_LIVE,
        "data_state": DATA_READY,
        "publication_readiness": DATA_READY,
        "content_hash": "sha256:abc",
        "reason_codes": [],
    }
    root = tmp_path / "rendezvous"
    write_handoff(public, {"dossier_id": "d", "producer_sha": "s"}, root)
    (root / "payload.json").write_text('{"tampered": true}\n', encoding="utf-8")
    errors = verify_handoff(root)
    assert any(e.startswith("digest:payload.json") for e in errors)


def test_cli_handoff_publishes_only_the_public_projection(tmp_path, capsys):
    out = tmp_path / "acme"
    cli.main(["build", "--cnpj", CNPJ, "--as-of", "2026-08-22", "--fixture", str(FIXTURE), "--out", str(out)])
    capsys.readouterr()
    root = tmp_path / "rendezvous"
    # A fixture build is BLOCKED, which is exit code 1, not a crash.
    assert cli.main(["handoff", "--dir", str(out), "--to", str(root)]) == 1
    capsys.readouterr()
    body = (root / "payload.json").read_text(encoding="utf-8")
    assert CNPJ not in body
    assert "ACME PAVIMENTACAO" not in body
    assert not (root / "dossier.json").exists()


# --- Regressions pinned from the adversarial review -------------------------


def test_public_projection_publishes_no_join_key(built):
    """An exact competitor valor_sum resolves a redacted supplier in one query."""
    _result, document = built
    public = public_projection(document)
    competitors = public["sections"][SECTION_COMPETITORS]["payload"]
    body = json.dumps(public, ensure_ascii=False)
    assert "competitors" not in competitors, "individual competitor rows must not be published"
    assert "3000000.00" not in body, "exact competitor money is a join key"
    assert competitors["value_bands"] == ["<10.000.000"]
    assert competitors["contract_count_band"] == "7-7"


def test_public_subject_profile_is_banded_not_exact(built):
    """uf + cnae + exact counts identify one supplier nationwide."""
    _result, document = built
    profile = public_projection(document)["subject_profile"]
    assert profile["cnae_division"] == "42"
    assert profile["buyer_count_band"] == "1-5"
    assert profile["contract_count_band"] == "1-10"
    assert "buyer_count" not in profile
    assert "cnae_principal" not in profile


def test_portfolio_totals_are_not_computed_over_the_display_list():
    """A capped buyer list must not set the total, the share or the HHI."""
    from scripts.dossier.compose import build_buyer_map

    displayed = SourceRead(
        source="v_contracts_canonical_v2",
        observed_at="t",
        rows=tuple(
            {
                "buyer_cnpj": f"b{i}",
                "buyer_nome": f"B{i}",
                "uf": "SC",
                "contract_count": 1,
                "valued_count": 1,
                "valor_sum": "100.00",
                "last_data_fim": "2027-01-01",
            }
            for i in range(3)
        ),
    )
    totals = SourceRead(
        source="v_contracts_canonical_v2",
        observed_at="t",
        rows=({"buyer_count": 900, "contract_count": 4951, "valor_sum_valued": "228158552.72", "hhi": 0.1583},),
    )
    section = build_buyer_map(displayed, SourceRead(source="c", observed_at="t"), totals)
    assert section.payload["buyer_count"] == 900
    assert section.payload["contract_count"] == 4951
    assert section.payload["displayed_buyer_count"] == 3
    assert section.payload["valor_sum_valued"] == "228158552.72"
    assert section.payload["hhi"] == 0.1583
    assert "buyer_list_truncated_for_display" in section.reason_codes
    # Truncation alone is disclosure, not a defect: the section stays READY.
    assert section.state == DATA_READY


def test_low_precision_category_claims_no_position():
    """Lexical TI is fixed, but the broad `sistema` rung still withholds position."""
    from scripts.dossier.compose import build_price_panel

    read = SourceRead(
        source="v_contract_intel_percentis",
        observed_at="t",
        rows=(
            {
                "categoria": "TI",
                "qtd_contratos": 21017,
                "p25_valor": "335.64",
                "p50_valor": "1870.20",
                "p75_valor": "30867.98",
                "ticket_medio": None,
                "focal_count": 4,
                "focal_valued_count": 4,
                "focal_median": "5000.00",
            },
        ),
    )
    section = build_price_panel(read)
    category = section.payload["categories"][0]
    assert category["focal_position"] == "LOW_PRECISION_BUCKET"
    assert category["bucket_precision"] == "LOW"
    assert "category_bucket_low_precision" in section.reason_codes
    assert section.state == DATA_HOLD
    findings = build_findings(
        contracts=SourceRead(source="c", observed_at="t"),
        buyer_map=section,
        price_panel=section,
        expiring=build_price_panel(SourceRead(source="x", observed_at="t")),
        opportunities=build_price_panel(SourceRead(source="x", observed_at="t")),
        as_of="2026-08-22",
    )
    assert not [f for f in findings if f.finding_id.startswith("value_position_in_category")]


def test_a_missing_offer_section_cannot_fold_to_ready(tmp_path):
    """Competitors, expiring and open bids are offer scope; absence is not READY."""
    partial = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for key in ("competitors", "expiring", "opportunities"):
        partial.pop(key)
    path = tmp_path / "partial.json"
    path.write_text(json.dumps(partial, ensure_ascii=False), encoding="utf-8")
    _result, document = build_dossier(FixtureSource(path), _request())
    assert document["data_state"] == DATA_HOLD
    assert "official_table_missing" in document["reason_codes"]


def test_markdown_is_scanned_and_official_text_is_exempt(built):
    from scripts.dossier.envelope import scan_markdown

    _result, document = built
    markdown = render_markdown(document)
    assert scan_markdown(markdown, document) == ()
    poisoned = markdown + "\n\nHa sobrepreco de R$ 1.000.000,00.\n"
    assert any("sobrepreco" in hit for hit in scan_markdown(poisoned, document))
    # A word carried from an official objeto is that source's word, not a claim.
    official = json.loads(json.dumps(document))
    official["sections"]["expiring_contracts"]["payload"]["contracts"][0]["objeto"] = "Servico irregular declarado"
    assert scan_markdown(markdown + "\nServico irregular declarado\n", official) == ()


def test_manifest_digests_cover_the_bytes_on_disk(tmp_path, capsys):
    out = tmp_path / "acme"
    cli.main(["build", "--cnpj", CNPJ, "--as-of", "2026-08-22", "--fixture", str(FIXTURE), "--out", str(out)])
    capsys.readouterr()
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["files"]) == {"dossier.json", "public-read.json", "dossier.md"}
    for name, digest in manifest["files"].items():
        assert digest == cli.file_digest(out / name)


def test_verify_detects_a_tampered_markdown(tmp_path, capsys):
    out = tmp_path / "acme"
    cli.main(["build", "--cnpj", CNPJ, "--as-of", "2026-08-22", "--fixture", str(FIXTURE), "--out", str(out)])
    capsys.readouterr()
    path = out / "dossier.md"
    path.write_text(
        path.read_text(encoding="utf-8") + "\n\nHa sobrepreco e o reajuste devido e imediato.\n", encoding="utf-8"
    )
    assert cli.main(["verify", "--dir", str(out)]) == 1
    report = json.loads(capsys.readouterr().out)
    assert any("digest mismatch" in p for p in report["problems"])
    assert any("forbidden claim content" in p for p in report["problems"])


def test_competitor_missingness_describes_the_published_rows():
    from scripts.dossier.compose import build_competitors

    rows = tuple(
        {
            "supplier_cnpj": f"c{i}",
            "supplier_nome": f"C{i}",
            "contract_count": 1,
            "valued_count": 1,
            "valor_sum": "10.00" if i < 3 else None,
            "shared_buyer_count": 1,
            "shared_categories": "OBRAS",
        }
        for i in range(20)
    )
    section = build_competitors(SourceRead(source="v", observed_at="t", rows=rows), limit=3)
    assert section.row_count == 3
    assert section.missingness == 0.0
