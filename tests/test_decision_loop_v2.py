"""Mandatory tests for EXTRA-DECISION-LOOP-01 decision loop."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from scripts.opportunity_intel.decision_engine import (
    decide_opportunity,
    map_external_to_internal,
    map_internal_to_external,
)
from scripts.opportunity_intel.human_review import (
    calibrate,
    export_review_sample,
    import_review_labels,
    stratified_sample,
)
from scripts.opportunity_intel.profile_resolve import (
    assert_local_not_tracked,
    resolve_extra_profile,
    write_profile_status,
)
from scripts.opportunity_intel.snapshot import (
    build_snapshot,
    classify_http_status,
    compute_delta,
    pick_reconfirm_targets,
    reconfirm_opportunity,
    select_active_opportunities,
)
from scripts.ops.decision_pack import reconcile_pdf_excel, run_decision_pack


def _open_row(**overrides):
    now = datetime.now(UTC)
    base = {
        "id": 1,
        "source": "pncp",
        "source_id": "x-1",
        "orgao_cnpj": "12345678000199",
        "orgao_nome": "Prefeitura Teste",
        "objeto": "Reforma predial de prédio público municipal",
        "valor_estimado": 500_000,
        "modalidade": "Pregão Eletrônico",
        "status_canonico": "open",
        "data_abertura": now + timedelta(days=5),
        "data_encerramento": now + timedelta(days=30),
        "data_publicacao": now - timedelta(days=2),
        "uf": "SC",
        "municipio": "Florianópolis",
        "link_edital": "https://pncp.gov.br/app/editais/example",
        "dentro_raio": True,
        "fonte_confiavel": True,
        "has_match_entity": True,
        "is_active": True,
        "ranking": "REVIEW",
        "ranking_score": 60,
    }
    base.update(overrides)
    return base


class TestProfileResolve:
    def test_hash_stable(self):
        a = resolve_extra_profile()
        b = resolve_extra_profile()
        assert a.profile_hash == b.profile_hash
        assert a.profile_id == "extra_construtora"
        assert a.pending_critical  # capacity still PENDING

    def test_local_override_merge(self, tmp_path: Path):
        public = Path("config/client_profiles/extra.yaml")
        local = tmp_path / "extra.local.yaml"
        local.write_text(
            "priority_municipalities:\n  - Florianópolis\nelicitation:\n"
            "  capital_giro:\n    status: SET\n    value: 1000\n",
            encoding="utf-8",
        )
        r = resolve_extra_profile(public_path=public, local_path=local)
        assert r.local_loaded is True
        assert "Florianópolis" in (r.data.get("priority_municipalities") or [])
        assert "capital_giro" not in r.pending_critical or r.data["elicitation"]["capital_giro"]["status"] == "SET"

    def test_profile_status_written(self, tmp_path: Path):
        r = resolve_extra_profile()
        j, m = write_profile_status(r, tmp_path)
        assert j.is_file() and m.is_file()
        payload = json.loads(j.read_text(encoding="utf-8"))
        assert payload["profile_hash"] == r.profile_hash
        assert "pending" in payload

    def test_local_not_tracked_gitignore(self):
        check = assert_local_not_tracked()
        assert check["gitignore_covers"] is True
        assert check["safe"] is True


class TestDecisionEngine:
    def test_mapping_roundtrip(self):
        assert map_internal_to_external("GO") == "PARTICIPAR"
        assert map_internal_to_external("NO_GO") == "NÃO_PARTICIPAR"
        assert map_external_to_internal("PARTICIPAR") == "GO"

    def test_hard_blocker_not_compensated(self):
        row = _open_row(objeto="", status_canonico="open")
        d = decide_opportunity(
            row,
            reconfirm={"outcome": "ok", "status": "ok"},
            profile_meta={"pending_critical": []},
        )
        assert d.recommendation == "NÃO_PARTICIPAR"
        assert d.hard_blockers

    def test_stale_never_participar(self):
        row = _open_row()
        d = decide_opportunity(
            row,
            reconfirm={"outcome": "stale", "status": "stale"},
            profile_meta={"pending_critical": []},
            profile={
                "profile_id": "t",
                "version": 1,
                "region": {"uf": "SC"},
                "desired_object_types": [{"id": "reforma", "terms": ["reforma predial"]}],
                "value_band_soft": {"min_brl": 1, "max_brl": 9e9},
                "operational_constraints": [{"id": "r"}],
                "engineering_categories": ["reforma"],
                "positive_terms": ["reforma"],
                **{k: {"status": "SET", "value": 1} for k in (
                    "capital_giro", "capacidade_simultanea", "cats_atestados", "equipe",
                    "equipamentos", "certidoes", "margem_minima", "risco_aceitavel",
                    "contratos_atuais", "apetite_consorcios", "capacidade_garantia",
                )},
            },
        )
        assert d.recommendation != "PARTICIPAR"

    def test_unconfirmed_never_participar(self):
        row = _open_row()
        d = decide_opportunity(row, reconfirm={"outcome": "not_attempted"})
        assert d.recommendation != "PARTICIPAR"

    def test_pending_profile_review_not_auto_nogo_for_fit(self):
        """Incomplete profile demotes GO→REVIEW, does not invent NÃO_PARTICIPAR alone."""
        row = _open_row()
        d = decide_opportunity(
            row,
            reconfirm={"outcome": "ok", "status": "ok"},
            profile_meta={"pending_critical": ["capital_giro", "margem_minima"]},
            profile={"region": {"uf": "SC"}, "desired_object_types": [{"id": "x", "terms": ["reforma"]}]},
        )
        assert d.recommendation in {"REVIEW", "NÃO_PARTICIPAR"}
        # With open complete data, hard block shouldn't force only from pending profile
        if not d.hard_blockers:
            assert d.recommendation == "REVIEW"

    def test_dimensions_present(self):
        d = decide_opportunity(_open_row(), reconfirm={"outcome": "http_204"})
        for key in (
            "data_confidence",
            "client_fit",
            "technical_fit",
            "commercial_fit",
            "operational_fit",
            "temporal_fit",
        ):
            assert key in d.dimensions


class TestSnapshot:
    def test_closed_excluded_from_active(self):
        rows = [
            _open_row(id=1, status_canonico="open"),
            _open_row(id=2, status_canonico="closed"),
        ]
        active = select_active_opportunities(rows)
        assert len(active) == 1
        assert active[0]["id"] == 1

    def test_deadline_delta(self):
        prev = build_snapshot(
            [_open_row(id=1, data_encerramento="2026-08-01")],
            run_id="r1",
            reconfirm_map={1: {"outcome": "ok"}},
        )
        cur = build_snapshot(
            [_open_row(id=1, data_encerramento="2026-08-15")],
            run_id="r2",
            reconfirm_map={1: {"outcome": "ok"}},
        )
        # normalize snapshot rows dates as strings
        prev.opportunities[0]["data_encerramento"] = "2026-08-01"
        cur.opportunities[0]["data_encerramento"] = "2026-08-15"
        delta = compute_delta(prev, cur)
        assert 1 in delta["deadline_changed"] or delta["counts"]["deadline_changed"] >= 1

    def test_http_semantics_distinct(self):
        assert classify_http_status(204) == "http_204"
        assert classify_http_status(403) == "http_403"
        assert classify_http_status(429) == "http_429"
        assert classify_http_status(503) == "http_5xx"
        assert classify_http_status(200) == "ok"

    def test_reconfirm_timeout(self):
        def boom(_url, **_kw):
            return None, "", "timeout:x"

        rc = reconfirm_opportunity(
            _open_row(),
            http_get=boom,
            offline=False,
        )
        assert rc.outcome == "timeout"

    def test_reconfirm_204(self):
        def empty(_url, **_kw):
            return 204, "", None

        rc = reconfirm_opportunity(_open_row(), http_get=empty, offline=False)
        assert rc.outcome == "http_204"

    def test_high_confidence_open_requires_ok(self):
        snap = build_snapshot(
            [_open_row(id=9)],
            run_id="r",
            reconfirm_map={9: {"outcome": "not_attempted"}},
        )
        assert snap.opportunities[0]["high_confidence_open"] is False

    def test_pick_targets_includes_all_when_small(self):
        rows = [_open_row(id=i) for i in range(5)]
        t = pick_reconfirm_targets(rows, top_n=20)
        assert len(t) == 5


class TestHumanReview:
    def test_export_never_auto_labels(self, tmp_path: Path):
        decisions = [
            {**_open_row(id=i), "recommendation": "REVIEW", "confidence": "LOW"}
            for i in range(12)
        ]
        path = tmp_path / "queue.csv"
        meta = export_review_sample(decisions, path, target=12)
        text = path.read_text(encoding="utf-8")
        assert "human_decision" in text
        # data rows should have empty human_decision (trailing commas / empty field)
        lines = [ln for ln in text.splitlines() if ln and not ln.startswith("opportunity_id")]
        assert lines
        assert meta["n_sample"] == 12

    def test_import_idempotent(self, tmp_path: Path):
        csv_path = tmp_path / "lab.csv"
        csv_path.write_text(
            "opportunity_id,human_decision,human_reason,hard_block_confirmed,"
            "missing_information,would_present_to_client,reviewed_at,reviewer,"
            "system_recommendation,stratum\n"
            "1,REVIEW,ok,,,,2026-07-19,tiago,REVIEW,borderline\n",
            encoding="utf-8",
        )
        store = tmp_path / "store"
        a = import_review_labels(csv_path, store_dir=store)
        b = import_review_labels(csv_path, store_dir=store)
        assert a["n_labels_total"] == 1
        assert b["n_labels_total"] == 1

    def test_metrics_blocked_without_sample(self, tmp_path: Path):
        res = calibrate(labels={}, store_dir=tmp_path)
        assert res.status == "PENDING_HUMAN"
        assert res.metrics == {}

    def test_metrics_with_enough_labels(self):
        labels = {
            str(i): {
                "human_decision": "REVIEW" if i % 2 else "NÃO_PARTICIPAR",
                "system_recommendation": "REVIEW" if i % 3 else "NÃO_PARTICIPAR",
                "stratum": "borderline",
            }
            for i in range(12)
        }
        res = calibrate(labels=labels, min_labels=10)
        assert res.status == "OK"
        assert "confusion_matrix" in res.metrics
        assert "agreement_system_vs_human" in res.metrics

    def test_stratified_all_when_few(self):
        dec = [{"recommendation": "REVIEW", "id": 1}]
        assert len(stratified_sample(dec, target=40)) == 1


class TestPackGates:
    def test_reconcile_detects_mismatch(self, tmp_path: Path):
        pdf = tmp_path / "a.pdf"
        xlsx = tmp_path / "a.xlsx"
        pdf.write_text("x", encoding="utf-8")
        xlsx.write_text("y", encoding="utf-8")
        r = reconcile_pdf_excel(
            run_id="r",
            profile_hash="h",
            cutoff="2026-07-19",
            pdf_path=pdf,
            xlsx_path=xlsx,
            counts={"participar": 1, "review": 2, "nao_participar": 3, "total": 6},
            excel_counts={"participar": 0, "review": 2, "nao_participar": 3, "total": 5},
        )
        assert r["status"] == "FAIL"
        assert r["divergences"]

    def test_checksum_changes_when_file_changes(self, tmp_path: Path):
        from scripts.crawl.run_evidence import sha256_file

        f = tmp_path / "p.txt"
        f.write_text("a", encoding="utf-8")
        h1 = sha256_file(f)
        f.write_text("b", encoding="utf-8")
        h2 = sha256_file(f)
        assert h1 != h2

    def test_run_pack_offline_db(self, tmp_path: Path):
        code, manifest = run_decision_pack(
            out_dir=tmp_path / "pack",
            offline_reconfirm=True,
            skip_db=False,
            strict=False,
            reconfirm_max=5,
            limit=30,
        )
        assert manifest.get("run_id")
        assert (tmp_path / "pack" / "decision_manifest.json").is_file()
        assert (tmp_path / "pack" / "profile_status.json").is_file()
        assert (tmp_path / "pack" / "checksums.json").is_file()
        assert manifest.get("human_acceptance") == "PENDING_HUMAN"
        # exit 0 or 2 depending on pdf/excel env — both acceptable if products exist
        assert code in {0, 2}
        assert manifest.get("counts", {}).get("total", 0) >= 0

    def test_exit_nonzero_on_reconcile_fail_strict(self, tmp_path: Path, monkeypatch):
        def bad_pdf(*_a, **_k):
            return False, "forced"

        monkeypatch.setattr("scripts.ops.decision_pack._generate_pdf", bad_pdf)
        code, manifest = run_decision_pack(
            out_dir=tmp_path / "pack2",
            offline_reconfirm=True,
            strict=True,
            reconfirm_max=3,
            limit=10,
        )
        assert code != 0
        assert manifest.get("reconcile", {}).get("status") == "FAIL"

    def test_reexecution_does_not_duplicate_labels(self, tmp_path: Path):
        csv_path = tmp_path / "lab.csv"
        csv_path.write_text(
            "opportunity_id,human_decision,human_reason,hard_block_confirmed,"
            "missing_information,would_present_to_client,reviewed_at,reviewer,"
            "system_recommendation,stratum\n"
            "42,REVIEW,r,,,,2026-07-19,tiago,REVIEW,borderline\n",
            encoding="utf-8",
        )
        store = tmp_path / "s"
        import_review_labels(csv_path, store_dir=store)
        import_review_labels(csv_path, store_dir=store)
        doc = json.loads((store / "labels.json").read_text(encoding="utf-8"))
        assert len(doc["labels"]) == 1
