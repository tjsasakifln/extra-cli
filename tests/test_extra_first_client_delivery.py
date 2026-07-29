"""Tests for EXTRA-FIRST-CLIENT-DECISION-DELIVERY-01 thin composition layer.

Drive shipped functions — no fixture masquerading as final evidence.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest
import yaml

from scripts.ops import extra_first_client_delivery as efd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROFILE = PROJECT_ROOT / "config" / "client_profiles" / "extra.yaml"


def _write_weekly(tmp: Path, rows: list[dict], *, exit_code: int = 0) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    fields = [
        "id",
        "source",
        "source_id",
        "numero_controle_pncp",
        "orgao_cnpj",
        "orgao_nome",
        "municipio",
        "uf",
        "objeto",
        "modalidade",
        "valor_estimado",
        "valor_semantica",
        "status_canonico",
        "ranking",
        "ranking_score",
        "ranking_confianca",
        "data_publicacao",
        "data_abertura",
        "data_encerramento",
        "link_edital",
        "ingested_at",
    ]
    opp = tmp / "opportunities.csv"
    with opp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    (tmp / "orgaos.csv").write_text("orgao\nX\n", encoding="utf-8")
    (tmp / "source_health.csv").write_text(
        "source,level\npncp_opportunities,fresh\n", encoding="utf-8"
    )
    (tmp / "contracts.csv").write_bytes(b"")
    (tmp / "competitors.csv").write_bytes(b"")
    (tmp / "gaps.csv").write_text("gap\n", encoding="utf-8")
    (tmp / "executive_summary.md").write_text("# exec\n", encoding="utf-8")
    (tmp / "extra_weekly_pack.xlsx").write_bytes(b"PK\x03\x04fake")
    (tmp / "deliverable_e.json").write_text("{}", encoding="utf-8")
    (tmp / "deliverable_e_audit.json").write_text("{}", encoding="utf-8")
    (tmp / "claims_provenance.csv").write_text("c\n", encoding="utf-8")

    artifacts = {}
    for name, key in [
        ("opportunities.csv", "opportunities_csv"),
        ("contracts.csv", "contracts_csv"),
        ("competitors.csv", "competitors_csv"),
        ("orgaos.csv", "orgaos_csv"),
        ("source_health.csv", "source_health_csv"),
        ("gaps.csv", "gaps_csv"),
        ("executive_summary.md", "executive_md"),
        ("extra_weekly_pack.xlsx", "excel"),
        ("deliverable_e.json", "deliverable_e"),
        ("deliverable_e_audit.json", "deliverable_e_audit"),
        ("claims_provenance.csv", "claims_provenance"),
    ]:
        p = tmp / name
        artifacts[key] = {
            "path": f"output/weekly/{tmp.name}/{name}",
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "bytes": p.stat().st_size,
        }
    checksums = {
        "schema": "extra-weekly-checksums/1.0",
        "cycle_id": tmp.name,
        "collection_id": "col-test",
        "artifacts": artifacts,
    }
    (tmp / "checksums.json").write_text(json.dumps(checksums), encoding="utf-8")
    manifest = {
        "cycle_id": tmp.name,
        "collection_id": "col-test",
        "started_at": "2026-07-28T00:00:00Z",
        "finished_at": "2026-07-28T01:00:00Z",
        "exit_code": exit_code,
        "freshness": [{"source": "pncp_opportunities", "level": "fresh"}],
        "source_health": [{"source": "pncp_opportunities", "level": "fresh"}],
        "limitations": ["test limitation"],
        "products": {},
        "intelligence": {"counts": {"opportunities": len(rows)}},
        "human_accept": {"status": "PENDING_HUMAN"},
    }
    (tmp / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp


def _future_eng_row(**over):
    base = {
        "id": "1",
        "source": "pncp",
        "source_id": "83102228000110-1-000077/2026",
        "numero_controle_pncp": "83102228000110-1-000077/2026",
        "orgao_cnpj": "83102228000110",
        "orgao_nome": "MUNICIPIO TESTE",
        "municipio": "Teste",
        "uf": "SC",
        "objeto": "Contratação de empresa para execução de pavimentação asfáltica da Rua X",
        "modalidade": "Concorrencia",
        "valor_estimado": "1351615.97",
        "valor_semantica": "valor_total_estimado_informado_pelo_pncp",
        "status_canonico": "aberta",
        "ranking": "REVIEW",
        "ranking_score": "0.8",
        "ranking_confianca": "media",
        "data_publicacao": "2026-07-01",
        "data_abertura": "2026-07-10",
        "data_encerramento": "2026-08-15",
        "link_edital": "https://pncp.gov.br/app/editais/83102228000110/2026/77",
        "ingested_at": "2026-07-28T00:00:00Z",
    }
    base.update(over)
    return base


def test_validate_weekly_fails_without_manifest(tmp_path: Path) -> None:
    d = tmp_path / "empty"
    d.mkdir()
    v = efd.validate_weekly_pack(d)
    assert v.ok is False
    assert any("manifest" in e for e in v.errors)


def test_validate_weekly_fails_on_checksum_mismatch(tmp_path: Path) -> None:
    weekly = _write_weekly(tmp_path / "w1", [_future_eng_row()])
    # corrupt opportunities after checksum
    (weekly / "opportunities.csv").write_text("broken", encoding="utf-8")
    v = efd.validate_weekly_pack(weekly)
    assert v.ok is False
    assert any("checksum" in e.lower() or "divergente" in e for e in v.errors)


def test_validate_weekly_fails_when_declared_file_missing(tmp_path: Path) -> None:
    weekly = _write_weekly(tmp_path / "w2", [_future_eng_row()])
    (weekly / "opportunities.csv").unlink()
    v = efd.validate_weekly_pack(weekly)
    assert v.ok is False
    assert any("ausente" in e.lower() or "opportunities" in e.lower() for e in v.errors)


def test_validate_weekly_fails_when_declared_file_missing_even_if_empty_hash(
    tmp_path: Path,
) -> None:
    """D2: empty sha256 in checksums must NOT authorize physical absence."""
    weekly = _write_weekly(tmp_path / "w2-empty-hash", [_future_eng_row()])
    empty_hash = hashlib.sha256(b"").hexdigest()
    cs = json.loads((weekly / "checksums.json").read_text(encoding="utf-8"))
    # Force declared hash to empty-content while deleting the file on disk.
    cs["artifacts"]["contracts_csv"]["sha256"] = empty_hash
    cs["artifacts"]["contracts_csv"]["bytes"] = 0
    (weekly / "checksums.json").write_text(json.dumps(cs), encoding="utf-8")
    (weekly / "contracts.csv").unlink()
    v = efd.validate_weekly_pack(weekly)
    assert v.ok is False
    assert any("ausente" in e.lower() for e in v.errors)
    assert any("contracts" in e.lower() for e in v.errors)


def test_validate_weekly_fails_on_zero_byte_critical_csv(tmp_path: Path) -> None:
    """D3: opportunities.csv zero-byte without header is never SUCCESS_ZERO."""
    weekly = _write_weekly(tmp_path / "w-zero", [_future_eng_row()])
    (weekly / "opportunities.csv").write_bytes(b"")
    # Recompute checksum so D3 is tested independently of D2/checksum mismatch.
    cs = json.loads((weekly / "checksums.json").read_text(encoding="utf-8"))
    cs["artifacts"]["opportunities_csv"]["sha256"] = hashlib.sha256(b"").hexdigest()
    cs["artifacts"]["opportunities_csv"]["bytes"] = 0
    (weekly / "checksums.json").write_text(json.dumps(cs), encoding="utf-8")
    v = efd.validate_weekly_pack(weekly)
    assert v.ok is False
    assert any("zero-byte" in e.lower() or "header" in e.lower() for e in v.errors)


def test_validate_weekly_accepts_header_only_opportunities_success_zero_shape(
    tmp_path: Path,
) -> None:
    """Header-only opportunities (row_count=0) is valid shape when file exists."""
    weekly = _write_weekly(tmp_path / "w-header-only", [])
    v = efd.validate_weekly_pack(weekly)
    assert v.ok is True
    assert v.opportunities_path is not None
    rows = efd.load_csv_rows(Path(v.opportunities_path))
    assert rows == []


def test_empty_opportunities_still_emits_insufficiency(tmp_path: Path) -> None:
    weekly = _write_weekly(tmp_path / "w3", [])
    out = tmp_path / "out"
    result = efd.run_delivery(
        weekly_input=weekly,
        delivery_out=out,
        profile_path=PROFILE,
        as_of=date(2026, 7, 28),
    )
    assert result["exit_code"] == 0
    man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert man["counts"]["candidates_total"] == 0
    assert man["counts"]["insufficient"] is True
    assert man["counts"]["go_count"] == 0


def test_critical_pending_blocks_go() -> None:
    profile = efd.load_profile(PROFILE)
    assert efd.go_blocked_by_profile(profile) is True
    crit = efd.critical_pending_fields(profile)
    assert "capital_giro" in crit
    assert "cats_atestados" in crit


def test_past_deadline_not_in_defensible_shortlist() -> None:
    profile = efd.load_profile(PROFILE)
    rows = [
        _future_eng_row(data_encerramento="2026-07-01", numero_controle_pncp="1-1-000001/2026"),
        _future_eng_row(
            data_encerramento="2026-08-20",
            numero_controle_pncp="83102228000110-1-000099/2026",
            source_id="83102228000110-1-000099/2026",
        ),
    ]
    # evaluate via build_shortlist
    result = efd.build_shortlist(
        rows,
        profile=profile,
        as_of=date(2026, 7, 28),
        cycle_id="c",
        collection_id="col",
        cut_date="2026-07-28",
    )
    ids = {e["numero_controle"] for e in result["shortlist"]}
    assert "1-1-000001/2026" not in ids
    assert any("000099" in (i or "") for i in ids)
    assert result["go_count"] == 0


def test_terminal_status_is_no_go() -> None:
    profile = efd.load_profile(PROFILE)
    row = _future_eng_row(status_canonico="revogada")
    ev = efd.evaluate_opportunity(
        row,
        profile=profile,
        as_of=date(2026, 7, 28),
        cycle_id="c",
        collection_id="col",
        cut_date="2026-07-28",
        go_blocked=True,
        critical_pending=["capital_giro"],
    )
    assert ev["recommendation"] == "NO_GO"
    assert "TERMINAL_OR_SUSPENDED" in ev["hard_blocks"]


def test_generic_url_detection() -> None:
    assert efd.is_generic_url("https://pncp.gov.br/app/editais?q=obra") is True
    assert efd.is_generic_url("https://pncp.gov.br/app/editais/83102228000110/2026/77") is False
    assert efd.is_generic_url("") is True


def test_missing_value_stays_null() -> None:
    profile = efd.load_profile(PROFILE)
    row = _future_eng_row(valor_estimado="")
    ev = efd.evaluate_opportunity(
        row,
        profile=profile,
        as_of=date(2026, 7, 28),
        cycle_id="c",
        collection_id="col",
        cut_date="2026-07-28",
        go_blocked=True,
        critical_pending=["capital_giro"],
    )
    assert ev["valor"] is None


def test_intake_has_no_invented_answers() -> None:
    profile = efd.load_profile(PROFILE)
    intake = efd.build_intake(profile)
    assert intake["go_blocked"] is True
    assert len(intake["questions"]) <= 10
    for q in intake["questions"]:
        assert q["answer"] is None
    patch = intake["profile_patch_candidate"]["elicitation"]
    for _k, v in patch.items():
        assert v.get("value") is None
        assert v.get("status") == "PENDING"


def test_human_review_starts_pending_and_cannot_autoaccept() -> None:
    weekly = efd.WeeklyValidation(
        ok=True,
        weekly_dir="/x",
        cycle_id="c1",
        collection_id="col1",
        exit_code=0,
        cut_date="2026-07-28",
        freshness=[{"source": "pncp_opportunities", "level": "fresh", "age_hours": 1}],
        source_health=[{"source": "pncp_opportunities", "level": "fresh"}],
        limitations=["lim-test"],
    )
    shortlist_result = {
        "candidates_total": 2,
        "blocked_total": 0,
        "review_defensible_total": 1,
        "shortlist_count": 1,
        "go_count": 0,
        "critical_pending": ["capital_giro"],
        "shortlist": [
            {
                "numero_controle": "83102228000110-1-000099/2026",
                "recommendation": "REVIEW",
                "client_fit": "ADERENTE",
                "data_limite": "2026-08-20",
                "dias_restantes": 23,
                "valor": 100.0,
                "url_oficial": "https://pncp.gov.br/app/editais/83102228000110/2026/99",
                "orgao": "MUNICIPIO TESTE",
                "termos_positivos": ["pavimentação"],
            }
        ],
    }
    diagnosis = {
        "cause_code": "UNKNOWN",
        "candidate_funnel": {"deadline_buckets": {"FUTURE": 1}},
        "prior_weekly_blocked_delivery": efd.load_prior_blocked_weekly_diagnosis(),
    }
    hr = efd.build_human_review(
        "run-1",
        {"a": "b"},
        weekly=weekly,
        shortlist_result=shortlist_result,
        diagnosis=diagnosis,
        market_baseline={"contracts": {"n_contracts": 0}, "competitors": {"top_suppliers": []}},
    )
    efd.assert_not_auto_accepted(hr)
    assert hr["status"] == "PENDING_HUMAN"
    assert hr["reviewed_by"] is None
    assert hr["decision"] is None
    assert hr["client_feedback"] is None
    # D7: empty feedback template present, never simulated as filled
    tpl = hr.get("client_feedback_template") or {}
    assert tpl.get("schema") == "extra-client-feedback/1.0"
    assert tpl.get("filled") is False
    assert tpl.get("recipient") is None
    assert tpl.get("decisions") == []
    claims = hr["claims_for_review"]
    assert isinstance(claims, list) and len(claims) >= 10
    topics = {c["topic"] for c in claims}
    for required in (
        "fontes_consultadas",
        "freshness",
        "existencia_ou_ausencia_oportunidades",
        "identificacao_oportunidades",
        "prazos",
        "valores",
        "concorrentes",
        "interpretacao_historica",
        "limitacoes",
        "recomendacao_proxima_acao",
    ):
        assert required in topics
    # prior weekly exit 2 documented inside limitations claim evidence
    lim = next(c for c in claims if c["topic"] == "limitacoes")
    assert (lim.get("evidence") or {}).get("prior_weekly_blocked_delivery", {}).get(
        "exit_code"
    ) == 2
    bad = dict(hr)
    bad["status"] = "ACCEPTED"
    bad["reviewed_by"] = "Tiago"
    bad["decision"] = "ACCEPTED"
    with pytest.raises(ValueError):
        efd.assert_not_auto_accepted(bad)
    # simulated filled client feedback template must also be rejected
    bad2 = dict(hr)
    bad2["client_feedback_template"] = {
        **tpl,
        "filled": True,
        "recipient": "Leonardo",
        "decisions": ["GO on item 1"],
    }
    with pytest.raises(ValueError):
        efd.assert_not_auto_accepted(bad2)


def test_indeterminado_without_positive_terms_is_not_review_defensible() -> None:
    profile = efd.load_profile(PROFILE)
    row = _future_eng_row(
        objeto="Aquisição de cubos de acrílico.",
        numero_controle_pncp="83169623000110-1-000358/2026",
        source_id="83169623000110-1-000358/2026",
    )
    ev = efd.evaluate_opportunity(
        row,
        profile=profile,
        as_of=date(2026, 7, 28),
        cycle_id="c",
        collection_id="col",
        cut_date="2026-07-28",
        go_blocked=True,
        critical_pending=["capital_giro"],
    )
    assert ev["client_fit"] == "INDETERMINADO"
    assert ev["termos_positivos"] == []
    assert ev["recommendation"] == "NO_GO"
    assert "sem termos positivos" in (ev.get("recommendation_reason") or "").lower()
    assert "aderência" not in (ev.get("recommendation_reason") or "").lower() or "sem" in (
        ev.get("recommendation_reason") or ""
    ).lower()

    result = efd.build_shortlist(
        [row, _future_eng_row()],
        profile=profile,
        as_of=date(2026, 7, 28),
        cycle_id="c",
        collection_id="col",
        cut_date="2026-07-28",
    )
    ids = {e["numero_controle"] for e in result["shortlist"]}
    assert "83169623000110-1-000358/2026" not in ids
    assert result["review_defensible_total"] >= 1


def test_diagnosis_includes_prior_blocked_weekly() -> None:
    weekly = efd.WeeklyValidation(
        ok=True,
        weekly_dir="/x",
        cycle_id="weekly-new",
        collection_id="col-new",
        exit_code=0,
        cut_date="2026-07-29",
        freshness=[{"source": "pncp_opportunities", "level": "fresh"}],
    )
    diag = efd.diagnose_weekly_source(
        weekly,
        shortlist_result={
            "evaluated_all": [],
            "candidates_total": 0,
            "blocked_total": 0,
            "review_defensible_total": 0,
            "shortlist_count": 0,
            "go_count": 0,
        },
        as_of=date(2026, 7, 29),
    )
    prior = diag.get("prior_weekly_blocked_delivery") or {}
    assert prior.get("cycle_id") == "weekly-20260727T063446Z-0d158e9c60"
    assert prior.get("exit_code") == 2
    assert (prior.get("candidate_funnel") or {}).get("deadline_buckets", {}).get("PASSED") == 50
    md = efd.diagnosis_to_markdown(diag)
    assert "weekly-20260727T063446Z-0d158e9c60" in md
    assert "50" in md
    assert "DEADLINE" in md.upper() or "PASSED" in md


def test_stale_acceptance_rejected_on_checksum_change() -> None:
    prev = {
        "decision": "ACCEPTED",
        "package_checksums": {"00-LEIA-ME.md": "aaa"},
    }
    assert efd.reject_stale_acceptance(prev, {"00-LEIA-ME.md": "bbb"}) is True
    assert efd.reject_stale_acceptance(prev, {"00-LEIA-ME.md": "aaa"}) is False


def test_package_run_produces_required_artifacts(tmp_path: Path) -> None:
    weekly = _write_weekly(
        tmp_path / "w-run",
        [
            _future_eng_row(),
            _future_eng_row(
                numero_controle_pncp="83102228000110-1-000100/2026",
                source_id="83102228000110-1-000100/2026",
                objeto="Obra de drenagem urbana e galeria pluvial",
                data_encerramento="2026-09-01",
                valor_estimado="",
            ),
            _future_eng_row(
                numero_controle_pncp="83102228000110-1-000101/2026",
                source_id="83102228000110-1-000101/2026",
                objeto="Reforma predial de escola municipal",
                data_encerramento="2026-08-30",
            ),
            _future_eng_row(
                numero_controle_pncp="83102228000110-1-000102/2026",
                source_id="83102228000110-1-000102/2026",
                objeto="Construção de edifício público administrativo",
                data_encerramento="2026-10-01",
            ),
            _future_eng_row(
                numero_controle_pncp="83102228000110-1-000103/2026",
                source_id="83102228000110-1-000103/2026",
                objeto="Pavimentação asfáltica e infraestrutura urbana",
                data_encerramento="2026-08-10",
            ),
            _future_eng_row(
                numero_controle_pncp="99999999999999-1-000001/2026",
                source_id="99999999999999-1-000001/2026",
                objeto="Aquisição de lençóis e mantas hospitalares",
                data_encerramento="2026-08-10",
            ),
        ],
    )
    out = tmp_path / "delivery"
    result = efd.run_delivery(
        weekly_input=weekly,
        delivery_out=out,
        profile_path=PROFILE,
        as_of=date(2026, 7, 28),
    )
    assert result["exit_code"] == 0
    assert result["terminal_state"] == "BUNDLE_READY_FOR_HUMAN_MERGE"
    assert result["package_quality"] == "COMPLETE_PENDING_HUMAN"
    required = [
        "00-LEIA-ME.md",
        "01-resumo-executivo.pdf",
        "01-resumo-executivo.md",
        "02-oportunidades-priorizadas.xlsx",
        "03-decision-ledger.csv",
        "03-decision-ledger.json",
        "04-intake-operacional-extra.md",
        "04-intake-operacional-extra.json",
        "05-limitacoes-e-confiabilidade.md",
        "06-baseline-mercado-extra.md",
        "06-baseline-mercado-extra.json",
        "07-plano-30-dias.md",
        "08-roteiro-reuniao.md",
        "09-dossie-edital-NOT_AVAILABLE.md",
        "diagnostico-weekly-source.json",
        "diagnostico-weekly-source.md",
        "manifest.json",
        "checksums.json",
        "human-review.json",
        "shortlist.json",
    ]
    for name in required:
        assert (out / name).is_file(), name
    man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert man["counts"]["go_count"] == 0
    assert man["counts"]["shortlist_count"] >= 5
    assert man["terminal_state"] == result["terminal_state"]
    hr = json.loads((out / "human-review.json").read_text(encoding="utf-8"))
    assert hr["status"] == "PENDING_HUMAN"
    assert hr["reviewed_by"] is None
    assert hr["decision"] is None
    # ledger client_decision empty
    ledger = json.loads((out / "03-decision-ledger.json").read_text(encoding="utf-8"))
    for item in ledger["items"]:
        assert item["client_decision"] == ""
        assert item["recommendation"] != "GO"
    # checksums.json must match on-disk files
    cs = json.loads((out / "checksums.json").read_text(encoding="utf-8"))
    for name, meta in cs["artifacts"].items():
        h = hashlib.sha256((out / name).read_bytes()).hexdigest()
        assert h == meta["sha256"], name
    # shortlist.json must be integrity-covered
    assert "shortlist.json" in cs["artifacts"]
    # human-review.package_checksums must bind to FINAL content digests (post-finalization)
    hr_cs = hr.get("package_checksums") or {}
    assert hr_cs, "human-review must carry package_checksums"
    for name, expected in hr_cs.items():
        actual = hashlib.sha256((out / name).read_bytes()).hexdigest()
        assert actual == expected, f"HR checksum stale for {name}"
        assert cs["artifacts"][name]["sha256"] == expected
    # PDF and MD must show final terminal state (not PENDING_BUILD)
    md = (out / "01-resumo-executivo.md").read_text(encoding="utf-8")
    leia = (out / "00-LEIA-ME.md").read_text(encoding="utf-8")
    assert result["terminal_state"] in md
    assert result["terminal_state"] in leia
    assert "PENDING_BUILD" not in md
    assert "PENDING_BUILD" not in leia
    # PDF body streams may be Flate-compressed; reportlab writes /Subject as plain
    # Info dict (no PyPDF2/pypdf required in CI).
    pdf_bytes = (out / "01-resumo-executivo.pdf").read_bytes()
    assert pdf_bytes.startswith(b"%PDF")
    assert b"PENDING_BUILD" not in pdf_bytes
    assert result["terminal_state"].encode("ascii") in pdf_bytes
    assert result["run_id"].encode("ascii") in pdf_bytes
    # null value preserved for empty valor row
    shortlist = json.loads((out / "shortlist.json").read_text(encoding="utf-8"))["shortlist"]
    null_vals = [s for s in shortlist if s.get("numero_controle", "").endswith("000100/2026")]
    assert null_vals
    assert null_vals[0]["valor"] is None
    # Renumber: entrypoint and resumo must point to 08-roteiro / 09-dossie (not stale 06/07)
    leia_full = (out / "00-LEIA-ME.md").read_text(encoding="utf-8")
    assert "08-roteiro-reuniao.md" in leia_full
    assert "09-dossie" in leia_full
    assert "06-roteiro-reuniao.md" not in leia_full
    assert "07-dossie" not in leia_full
    assert "07-plano-30-dias.md" in leia_full
    assert "06-baseline-mercado-extra" in leia_full
    assert "07-dossie-edital" not in md
    assert "ver 07" not in md.lower() or "09-dossie" in md


def test_production_dsn_rejected(tmp_path: Path) -> None:
    weekly = _write_weekly(tmp_path / "w-dsn", [_future_eng_row()])
    out = tmp_path / "out-dsn"
    with pytest.raises(SystemExit) as ei:
        efd.run_delivery(
            weekly_input=weekly,
            delivery_out=out,
            profile_path=PROFILE,
            as_of=date(2026, 7, 28),
            client_ready_dsn="postgresql://u:p@ec-prod:5432/extra_prod",
        )
    assert int(ei.value.code) == 2


def test_reconcile_detects_divergence() -> None:
    weekly = efd.WeeklyValidation(
        ok=True,
        weekly_dir="/x",
        cycle_id="c1",
        collection_id="col1",
        cut_date="2026-07-28",
    )
    profile = {"version": 3}
    shortlist_result = {
        "shortlist_count": 5,
        "go_count": 0,
        "review_count": 5,
        "candidates_total": 10,
        "go_blocked_by_profile": True,
    }
    excel_meta = {
        "shortlist_count": 4,  # diverge
        "go_count": 0,
        "review_count": 5,
        "candidates_total": 10,
        "cut_date": "2026-07-28",
        "profile_version": 3,
        "collection_id": "col1",
        "cycle_run_id": "c1",
    }
    pdf_meta = dict(excel_meta)
    pdf_meta["shortlist_count"] = 5
    recon = efd.reconcile_package_counts(
        shortlist_result=shortlist_result,
        excel_meta=excel_meta,
        pdf_meta=pdf_meta,
        weekly=weekly,
        profile=profile,
    )
    assert recon["status"] == "FAIL"
    assert recon["divergences"]


def test_cli_validate_exit_codes(tmp_path: Path) -> None:
    weekly = _write_weekly(tmp_path / "w-cli", [_future_eng_row()])
    assert efd.main(["validate-weekly", "--weekly-input", str(weekly)]) == 0
    empty = tmp_path / "nope"
    empty.mkdir()
    assert efd.main(["validate-weekly", "--weekly-input", str(empty)]) == 2


def test_diagnosis_marks_all_passed_deadlines(tmp_path: Path) -> None:
    weekly = _write_weekly(
        tmp_path / "w-diag",
        [
            {
                "id": "1",
                "source": "pncp",
                "source_id": "83102228000110-1-000001/2026",
                "numero_controle_pncp": "83102228000110-1-000001/2026",
                "orgao_cnpj": "83102228000110",
                "orgao_nome": "MUNICIPIO DEMO",
                "municipio": "Demo",
                "uf": "SC",
                "objeto": "Pavimentação asfáltica de vias urbanas",
                "modalidade": "Pregão",
                "valor_estimado": "100000",
                "valor_semantica": "estimado",
                "status_canonico": "open",
                "ranking": "REVIEW",
                "ranking_score": "0",
                "ranking_confianca": "MEDIUM",
                "data_publicacao": "2026-07-01",
                "data_abertura": "2026-07-01",
                "data_encerramento": "2026-07-20",
                "link_edital": "https://pncp.gov.br/app/editais/83102228000110/2026/1",
                "ingested_at": "2026-07-20T00:00:00Z",
            }
        ],
        exit_code=2,
    )
    out = tmp_path / "out-diag"
    result = efd.run_delivery(
        weekly_input=weekly,
        delivery_out=out,
        profile_path=PROFILE,
        as_of=date(2026, 7, 28),
    )
    # D1: weekly exit 2 → BLOCKED_EXTERNAL, process exit 3 (not READY)
    assert result["exit_code"] == 3
    assert result["terminal_state"] == "BLOCKED_EXTERNAL"
    assert result["terminal_state"] != "BUNDLE_READY_FOR_HUMAN_MERGE"
    man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert man["terminal_state"] == "BLOCKED_EXTERNAL"
    # Operator diagnosis + intake still emitted
    assert (out / "diagnostico-weekly-source.json").is_file()
    assert (out / "04-intake-operacional-extra.json").is_file()
    hr = json.loads((out / "human-review.json").read_text(encoding="utf-8"))
    assert hr["status"] == "PENDING_HUMAN"
    assert hr["reviewed_by"] is None
    diag = json.loads((out / "diagnostico-weekly-source.json").read_text(encoding="utf-8"))
    assert diag["exit_code"] == 2
    assert diag.get("reliable_market_absence") is False
    assert diag["candidate_funnel"]["deadline_buckets"]["PASSED"] >= 1
    assert diag["candidate_funnel"]["review_defensible_total"] == 0
    assert "A_records_old_or_closed" in (diag.get("causes") or []) or diag.get("cause_code")
    baseline = (out / "06-baseline-mercado-extra.md").read_text(encoding="utf-8")
    assert "históric" in baseline.lower() or "Referências" in baseline


def test_weekly_exit_code_3_is_blocked_external_not_ready(tmp_path: Path) -> None:
    """D1+D6: exit 3 → BLOCKED_EXTERNAL (never READY); absence not reliable."""
    weekly = _write_weekly(tmp_path / "w-exit3", [_future_eng_row()], exit_code=3)
    out = tmp_path / "out-exit3"
    result = efd.run_delivery(
        weekly_input=weekly,
        delivery_out=out,
        profile_path=PROFILE,
        as_of=date(2026, 7, 28),
    )
    assert result["exit_code"] == 3
    assert result["terminal_state"] == "BLOCKED_EXTERNAL"
    assert "BUNDLE_READY" not in result["terminal_state"]
    leia = (out / "00-LEIA-ME.md").read_text(encoding="utf-8")
    assert "BLOCKED_EXTERNAL" in leia
    man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert man["terminal_state"] == "BLOCKED_EXTERNAL"
    assert man["package_quality"] == "PARTIAL_VISIBLE_LIMITATIONS"
    bad = efd.WeeklyValidation(
        ok=True,
        weekly_dir="/x",
        cycle_id="c",
        collection_id="col",
        exit_code=3,
        freshness=[{"source": "pncp_opportunities", "level": "fresh"}],
        source_health=[{"source": "pncp_opportunities", "level": "fresh"}],
    )
    assert (
        efd.is_reliable_market_absence(bad, {"candidates_total": 0, "shortlist_count": 0})
        is False
    )


def test_pncp_open_proposal_data_final_uses_forward_horizon() -> None:
    from datetime import timedelta

    from scripts.opportunity_intel.crawler_base import CrawlRequest
    from scripts.opportunity_intel.pncp_crawler import (
        PNCP_OPEN_PROPOSAL_HORIZON_DAYS,
        PncpOpportunityCrawler,
    )

    crawler = PncpOpportunityCrawler(dsn=None)
    req = CrawlRequest(
        source="pncp",
        target="modalidade:6",
        date_from=date.today() - timedelta(days=7),
        date_to=date.today(),
        mode="incremental",
    )
    data_final = crawler.resolve_data_final(req)
    assert data_final == date.today() + timedelta(days=PNCP_OPEN_PROPOSAL_HORIZON_DAYS)
    url = crawler.build_url(req, 1)
    assert f"dataFinal={data_final.strftime('%Y%m%d')}" in url
    assert f"dataFinal={date.today().strftime('%Y%m%d')}" not in url


def test_profile_patch_yaml_nulls() -> None:
    profile = efd.load_profile(PROFILE)
    intake = efd.build_intake(profile)
    text = efd.profile_patch_yaml(intake)
    data = yaml.safe_load(text)
    assert data["profile_patch_candidate"]["elicitation"]["capital_giro"]["value"] is None
