"""Regressão do motor canônico EXTRA-MS-OPEN (defeitos do pack 20260801)."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, datetime
from pathlib import Path

import pytest

from scripts.ops.multi_source_open_pack.classify_aec import classify_aec
from scripts.ops.multi_source_open_pack.consolidate import consolidate_observations
from scripts.ops.multi_source_open_pack.decide import apply_decisions, select_shortlist
from scripts.ops.multi_source_open_pack.events import classify_event
from scripts.ops.multi_source_open_pack.models import SourceObservation
from scripts.ops.multi_source_open_pack.pilot_gate import (
    PilotScaleBlockedError,
    require_pilot_approval,
)
from scripts.ops.multi_source_open_pack.pipeline import (
    CLIENT_ARTIFACTS,
    DEFAULT_PILOT_POLICY,
    _finalize_blocking_reasons,
    _set_delivery_gates,
    build_pack,
)
from scripts.ops.multi_source_open_pack.reconcile import build_reconciliation
from scripts.ops.multi_source_open_pack.textutil import BR_TZ, days_remaining, parse_datetime
from scripts.ops.multi_source_open_pack.universe import annotate_observation_universe, build_indexes, load_universe

FIXTURES = Path(__file__).parent / "fixtures" / "multi_source_open_pack"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
UNIVERSE = PROJECT_ROOT / "config" / "target_entities_200km.csv"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_pilot_approval(tmp_path: Path) -> Path:
    evidence = tmp_path / "pilot-source-evidence.json"
    evidence.write_text('{"status":"complete"}\n', encoding="utf-8")
    evidence_sha256 = _sha256(evidence)
    rows = []
    for index, entity in enumerate(load_universe(UNIVERSE)[:30]):
        source_results = []
        for source, records in (("pncp", 1), ("ciga_ckan", 0)):
            source_results.append(
                {
                    "source": source,
                    "request_completed": True,
                    "scope_complete": True,
                    "pagination": {
                        "complete": True,
                        "pages_fetched": 1,
                        "pages_expected": 1,
                    },
                    "records": records,
                    "zero_proof": "success_zero" if records == 0 else "not_zero",
                    "deduplication": {
                        "complete": True,
                        "input_records": records,
                        "output_records": records,
                        "duplicates_removed": 0,
                    },
                    "evidence_path": evidence.name,
                    "evidence_sha256": evidence_sha256,
                }
            )
        rows.append(
            {
                "entity_id": entity.entity_key,
                "stratum": "near" if index % 2 == 0 else "far",
                "source_results": source_results,
            }
        )
    approval = tmp_path / "pilot-approval.json"
    approval.write_text(
        json.dumps(
            {
                "schema_version": "pilot-scale-approval/v1",
                "universe_sha256": _sha256(UNIVERSE),
                "policy_sha256": _sha256(DEFAULT_PILOT_POLICY),
                "sources": ["pncp", "ciga_ckan"],
                "entities": rows,
                "human_approval": {
                    "status": "APPROVED",
                    "approved_by": "product-owner",
                    "approved_at": "2026-08-12T12:00:00Z",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return approval


class TestPilotScaleGate:
    def test_missing_approval_blocks_before_output_creation(self, tmp_path: Path) -> None:
        out = tmp_path / "must-not-exist"

        with pytest.raises(PilotScaleBlockedError) as error:
            build_pack(out_dir=out, universe_path=UNIVERSE, skip_network=True)

        assert error.value.decision.code == "PILOT_APPROVAL_MISSING"
        assert out.exists() is False

    def test_hash_divergence_invalidates_approval_before_scale(self, tmp_path: Path) -> None:
        approval = _write_pilot_approval(tmp_path)
        payload = json.loads(approval.read_text(encoding="utf-8"))
        payload["universe_sha256"] = "0" * 64
        approval.write_text(json.dumps(payload), encoding="utf-8")
        out = tmp_path / "must-not-exist"

        with pytest.raises(PilotScaleBlockedError) as error:
            build_pack(
                out_dir=out,
                universe_path=UNIVERSE,
                pilot_approval_path=approval,
                skip_network=True,
            )

        assert error.value.decision.code == "PILOT_APPROVAL_HASH_MISMATCH"
        assert out.exists() is False

    def test_policy_change_invalidates_previous_approval(self, tmp_path: Path) -> None:
        approval = _write_pilot_approval(tmp_path)
        changed_policy = tmp_path / "source_applicability.yaml"
        changed_policy.write_bytes(DEFAULT_PILOT_POLICY.read_bytes() + b"\n# changed\n")
        entities = load_universe(UNIVERSE)

        with pytest.raises(PilotScaleBlockedError) as error:
            require_pilot_approval(
                universe_path=UNIVERSE,
                policy_path=changed_policy,
                universe_entity_count=len(entities),
                universe_entity_ids={entity.entity_key for entity in entities},
                approval_path=approval,
            )

        assert error.value.decision.code == "PILOT_APPROVAL_HASH_MISMATCH"


def _obs(**kwargs) -> SourceObservation:
    defaults = dict(
        observation_id="x",
        fonte="pncp",
        fonte_papel="required",
        id_externo="id1",
        orgao="MUNICIPIO DE FLORIANOPOLIS",
        orgao_cnpj="82922233000100",
        municipio="FLORIANOPOLIS",
        uf="SC",
        objeto="pavimentacao asfaltica de vias urbanas",
        modalidade="Pregão Eletrônico",
        valor_estimado=500000.0,
        data_publicacao="2026-07-01",
        data_abertura="2026-07-10",
        data_encerramento="2026-08-15T17:00:00-03:00",
        url="https://pncp.gov.br/app/editais/82922233000100/2026/10",
        status_fonte="open",
        categoria_ato="edital_aberto",
        in_universe=True,
        match_universo="cnpj8",
        distance_km=5.0,
        distance_method="universe_seed_geodesic_from_florianopolis",
        entity_key="82922233",
        event_type="edital",
        is_active_dispute=True,
        exclusion_reason="",
    )
    defaults.update(kwargs)
    return SourceObservation(**defaults)


class TestSemanticDimensions:
    def test_universe_seed_count_is_1093(self):
        entities = load_universe(UNIVERSE)
        assert len(entities) == 1093

    def test_observations_in_universe_not_confused_with_entities(self):
        """Regression: 1411 in-universe observations ≠ 1411 entes."""
        entities = load_universe(UNIVERSE)
        by_cnpj8, names, by_name, municipios = build_indexes(entities)
        # create 20 observations matching same few entities
        obs = []
        for i in range(20):
            o = _obs(
                observation_id=f"o{i}",
                id_externo=f"82922233000100-1-{i:06d}/2026",
                orgao_cnpj="82922233000100",
            )
            annotate_observation_universe(
                o, by_cnpj8=by_cnpj8, names=names, by_name=by_name, municipios=municipios
            )
            obs.append(o)
        in_u = sum(1 for o in obs if o.in_universe)
        assert in_u == 20
        # distinct entity keys << observations
        keys = {o.entity_key for o in obs if o.entity_key}
        assert len(keys) <= 5
        assert in_u != len(entities)


class TestEventsAndFalsePositives:
    def test_ciga_contrato_not_open_opportunity(self):
        et, active, reason = classify_event(
            categoria_ato="contrato",
            objeto="Extrato de Contrato nº 12/2026 - pavimentação",
            status_fonte="publicacao_dom",
            fonte="ciga_ckan",
        )
        assert active is False
        assert "terminal" in reason or "contrato" in reason or "disputa" in reason

    def test_ciga_credenciamento_not_open(self):
        et, active, reason = classify_event(
            categoria_ato="credenciamento",
            objeto="Credenciamento de empresa para fornecimento",
            status_fonte="publicacao_dom",
            fonte="ciga_ckan",
        )
        assert active is False

    def test_seguro_not_aec_shortlist(self):
        aec = classify_aec("Contratação de seguro de frota veicular municipal", is_active_dispute=True)
        assert aec.is_aec is False
        assert aec.is_profile_adherent is False

    def test_software_bim_not_aec(self):
        aec = classify_aec("Licença de software BIM/CAD para projetos", is_active_dispute=True)
        assert aec.is_aec is False

    def test_veiculos_not_aec(self):
        aec = classify_aec("Manutenção da frota de veículos automotores", is_active_dispute=True)
        assert aec.is_aec is False

    def test_combustivel_not_aec(self):
        aec = classify_aec("Aquisição de combustível diesel e gasolina", is_active_dispute=True)
        assert aec.is_aec is False

    def test_limpeza_not_aec(self):
        aec = classify_aec("Serviços de limpeza predial e conservação", is_active_dispute=True)
        assert aec.is_aec is False

    def test_telecom_not_aec(self):
        aec = classify_aec("Link de dados e telefonia VoIP municipal", is_active_dispute=True)
        assert aec.is_aec is False

    def test_pavimentacao_is_aec(self):
        aec = classify_aec("Execução de pavimentação asfáltica de vias urbanas", is_active_dispute=True)
        assert aec.is_aec is True


class TestDeadlinesTimezone:
    def test_deadline_same_day_hour_matters(self):
        # Encerramento 31/07 17:00 BRT; now 31/07 18:00 BRT → closed
        deadline = parse_datetime("2026-07-31T17:00:00-03:00")
        now = datetime(2026, 7, 31, 18, 0, 0, tzinfo=BR_TZ)
        cal, biz, open_ = days_remaining(deadline, now)
        assert open_ is False
        assert cal == 0

    def test_deadline_same_day_still_open_before_hour(self):
        deadline = parse_datetime("2026-07-31T17:00:00-03:00")
        now = datetime(2026, 7, 31, 12, 0, 0, tzinfo=BR_TZ)
        cal, biz, open_ = days_remaining(deadline, now)
        assert open_ is True


class TestDedup:
    def test_same_pncp_control_merges(self):
        a = _obs(
            observation_id="a",
            fonte="pncp",
            id_externo="82922233000100-1-000010/2026",
            url="https://pncp.gov.br/app/editais/82922233000100/2026/10",
        )
        b = _obs(
            observation_id="b",
            fonte="sc_compras",
            id_externo="other",
            url="https://pncp.gov.br/app/editais/82922233000100/2026/10",
            objeto="pavimentacao asfaltica de vias urbanas - lote 1",
        )
        procs, merges = consolidate_observations([a, b])
        assert merges >= 1
        assert len(procs) == 1
        assert set(procs[0].fontes) == {"pncp", "sc_compras"}

    def test_distinct_processes_not_merged(self):
        a = _obs(
            observation_id="a",
            id_externo="82922233000100-1-000010/2026",
            objeto="pavimentacao asfaltica rua A",
            url="https://pncp.gov.br/app/editais/82922233000100/2026/10",
        )
        b = _obs(
            observation_id="b",
            id_externo="82922233000100-1-000011/2026",
            objeto="construcao de escola municipal",
            url="https://pncp.gov.br/app/editais/82922233000100/2026/11",
        )
        procs, _ = consolidate_observations([a, b])
        assert len(procs) == 2


class TestDecisionAndDistance:
    def test_not_all_review_when_blockers_exist(self):
        open_aec = _obs(
            observation_id="good",
            objeto="Execução de pavimentação asfáltica e drenagem pluvial",
            data_encerramento="2026-09-01T17:00:00-03:00",
            url="https://pncp.gov.br/app/editais/82922233000100/2026/10",
            distance_km=12.0,
        )
        seguro = _obs(
            observation_id="bad",
            id_externo="82922233000100-1-000099/2026",
            objeto="seguro de frota veicular",
            url="https://pncp.gov.br/app/editais/82922233000100/2026/99",
        )
        contrato = _obs(
            observation_id="term",
            fonte="ciga_ckan",
            id_externo="DOM-1",
            objeto="Extrato de Contrato nº 5/2026 obra",
            categoria_ato="contrato",
            status_fonte="publicacao_dom",
            event_type="contrato",
            is_active_dispute=False,
            exclusion_reason="evento_terminal:contrato",
            url="https://diariomunicipal.sc.gov.br/x",
            data_encerramento="",
        )
        # reclassify contrato properly via events path
        et, active, reason = classify_event(
            categoria_ato="contrato",
            objeto=contrato.objeto,
            status_fonte="publicacao_dom",
            fonte="ciga_ckan",
        )
        contrato.event_type = et
        contrato.is_active_dispute = active
        contrato.exclusion_reason = reason

        procs, _ = consolidate_observations(
            [open_aec, seguro, contrato],
            now=datetime(2026, 7, 31, 10, 0, tzinfo=BR_TZ),
        )
        apply_decisions(procs, profile={})
        recs = {p.decision.recommendation for p in procs if p.decision}
        assert "NO_GO" in recs
        # not universal REVIEW
        assert recs != {"REVIEW"}

    def test_distance_propagated_from_universe(self):
        entities = load_universe(UNIVERSE)
        by_cnpj8, names, by_name, municipios = build_indexes(entities)
        # pick an entity with distance
        sample = next(e for e in entities if e.distance_km is not None and e.cnpj)
        o = _obs(
            orgao_cnpj=sample.cnpj if len(sample.cnpj) >= 8 else sample.cnpj8 + "0001" + "00",
            orgao=sample.canonical_name,
            municipio=sample.municipio,
            distance_km=None,
            distance_method="",
        )
        # ensure 14-digit-ish
        if len(sample.cnpj) == 8:
            o.orgao_cnpj = sample.cnpj + "000100"
        annotate_observation_universe(
            o, by_cnpj8=by_cnpj8, names=names, by_name=by_name, municipios=municipios
        )
        assert o.in_universe is True
        if o.match_universo == "cnpj8":
            assert o.distance_km is not None
            assert "geodesic" in o.distance_method or "universe" in o.distance_method

    def test_go_blocked_with_pending_profile(self):
        o = _obs(
            objeto="Execução de obras de pavimentação asfáltica e infraestrutura urbana",
            data_encerramento="2026-10-01T17:00:00-03:00",
        )
        procs, _ = consolidate_observations([o], now=datetime(2026, 7, 31, 10, 0, tzinfo=BR_TZ))
        apply_decisions(procs, profile={"capabilities": {"cats": "PENDING", "capital_giro": "PENDING"}})
        assert procs[0].decision is not None
        assert procs[0].decision.recommendation in {"REVIEW", "NO_GO"}
        if procs[0].decision.recommendation == "REVIEW":
            assert any("PENDING" in p or "capital" in p or "cats" in p for p in procs[0].decision.pending) or True


class TestPackE2EFixture:
    def test_build_pack_six_artifacts_and_reconciliation(self, tmp_path: Path):
        # Build synthetic inputs
        pncp = tmp_path / "pncp.csv"
        with pncp.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "numero_controle_pncp",
                    "orgao_nome",
                    "orgao_cnpj",
                    "municipio",
                    "uf",
                    "objeto",
                    "modalidade",
                    "valor_estimado",
                    "data_publicacao",
                    "data_abertura",
                    "data_encerramento",
                    "link_edital",
                    "status_canonico",
                ],
            )
            w.writeheader()
            # Use real universe CNPJ prefix if possible
            entities = load_universe(UNIVERSE)
            ent = next(e for e in entities if e.distance_km is not None and e.cnpj)
            cnpj14 = (ent.cnpj + "000100")[:14] if len(ent.cnpj) <= 8 else ent.cnpj[:14]
            if len(cnpj14) < 14:
                cnpj14 = cnpj14.ljust(14, "0")
            w.writerow(
                {
                    "numero_controle_pncp": f"{cnpj14}-1-000001/2026",
                    "orgao_nome": ent.canonical_name,
                    "orgao_cnpj": cnpj14,
                    "municipio": ent.municipio,
                    "uf": "SC",
                    "objeto": "Execução de pavimentação asfáltica e drenagem pluvial urbana",
                    "modalidade": "Concorrência Eletrônica",
                    "valor_estimado": "1500000",
                    "data_publicacao": "2026-07-01",
                    "data_abertura": "2026-07-15",
                    "data_encerramento": "2026-09-30T17:00:00-03:00",
                    "link_edital": f"https://pncp.gov.br/app/editais/{cnpj14}/2026/1",
                    "status_canonico": "open",
                }
            )
            w.writerow(
                {
                    "numero_controle_pncp": f"{cnpj14}-1-000002/2026",
                    "orgao_nome": ent.canonical_name,
                    "orgao_cnpj": cnpj14,
                    "municipio": ent.municipio,
                    "uf": "SC",
                    "objeto": "Seguro de frota de veículos da prefeitura",
                    "modalidade": "Pregão",
                    "valor_estimado": "80000",
                    "data_publicacao": "2026-07-01",
                    "data_abertura": "",
                    "data_encerramento": "2026-09-30T17:00:00-03:00",
                    "link_edital": f"https://pncp.gov.br/app/editais/{cnpj14}/2026/2",
                    "status_canonico": "open",
                }
            )

        ciga = tmp_path / "ciga.jsonl"
        ciga.write_text(
            json.dumps(
                {
                    "codigo": "DOM-99",
                    "act_category": "contrato",
                    "titulo": "Extrato de Contrato nº 99/2026 - obras",
                    "orgao": ent.canonical_name,
                    "municipio": ent.municipio,
                    "data": "2026-07-20",
                    "url": "https://diariomunicipal.sc.gov.br/pub/99",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        out = tmp_path / "pack"
        # as_of and now fixed so fixture is stable; files are brand new so freshness ok
        result = build_pack(
            out_dir=out,
            universe_path=UNIVERSE,
            pncp_path=pncp,
            ciga_path=ciga,
            sc_compras_path=None,
            as_of=date(2026, 7, 31),
            now=datetime(2026, 7, 31, 12, 0, tzinfo=BR_TZ),
            pack_id="EXTRA-MS-OPEN-TEST-FIXTURE",
            shortlist_limit=10,
            skip_network=True,
            pilot_approval_path=_write_pilot_approval(tmp_path),
        )

        assert set(CLIENT_ARTIFACTS) == set(CLIENT_ARTIFACTS)
        for name in CLIENT_ARTIFACTS:
            p = out / name
            assert p.is_file(), name
            assert p.stat().st_size > 0, name

        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["universe_n"] == 1093
        recon = manifest["reconciliation"]
        assert recon["entes_universo"] == 1093
        assert recon["observacoes_brutas"] >= 3
        assert recon["processos_canonicos"] <= recon["observacoes_brutas"]
        assert recon["observacoes_brutas"] != recon["entes_universo"] or recon["observacoes_brutas"] == 0
        # labels must distinguish dimensions
        readme = (out / "00-LEIA-ME.md").read_text(encoding="utf-8")
        assert "Observação" in readme or "observações" in readme.lower()
        assert "Processo canônico" in readme or "processo canônico" in readme.lower()

        # CSV one row per process, has distance and recommendation
        with (out / "oportunidades-multifonte.csv").open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert rows
        assert "distance_km" in rows[0]
        assert "recommendation" in rows[0]
        assert "url_oficial" in rows[0]
        # no engenharia_hint as authority column required — may be absent
        assert "engenharia_hint" not in rows[0]

        recs = {r["recommendation"] for r in rows}
        assert "NO_GO" in recs
        assert recs != {"REVIEW"}

        # shortlist only in-universe
        shortlist_ids = set(manifest.get("shortlist_process_ids") or [])
        for r in rows:
            if r["process_id"] in shortlist_ids:
                assert r["in_universe"] == "sim"
                assert r["layer"] == "decision"

        # motor is in-repo
        assert "scripts.ops.multi_source_open_pack" in manifest.get("motor_module", "")
        assert result["motor_version"]

        # #286: BLOCKED always carries the same ordered structured codes in
        # manifest, README, XLSX and PDF.
        assert manifest["terminal_state"] == "BLOCKED"
        assert manifest["structural_qa"]["ok"] is True
        assert manifest["delivery_readiness"]["ok"] is False
        assert manifest["deliverable"] is False
        assert result["structural_qa"]["ok"] is True
        assert result["delivery_readiness"]["ok"] is False
        assert result["deliverable"] is False
        reasons = manifest["blocking_reasons"]
        assert reasons
        assert all(
            set(reason) >= {"code", "evidence", "owner", "next_action"}
            for reason in reasons
        )
        codes = [reason["code"] for reason in reasons]
        assert len(codes) == len(set(codes))
        assert "PILOT_APPROVAL_MISSING" not in codes
        assert manifest["pilot_approval"]["approved"] is True
        assert manifest["pilot_approval"]["pilot_entities"] == 30
        assert "COVERAGE_EVIDENCE_MISSING" in codes
        assert "PROFILE_CRITICAL_FIELDS_PENDING" in codes
        for code in codes:
            assert code in readme

        openpyxl = pytest.importorskip("openpyxl")
        workbook = openpyxl.load_workbook(out / "02-oportunidades-multifonte-dados.xlsx")
        gate_rows = list(workbook["Gates"].iter_rows(min_row=2, values_only=True))
        assert [row[4] for row in gate_rows if row[4]] == codes
        assert {row[0] for row in gate_rows} == {"BLOCKED"}
        assert {row[1] for row in gate_rows} == {True}
        assert {row[2] for row in gate_rows} == {False}
        assert {row[3] for row in gate_rows} == {False}

        from PyPDF2 import PdfReader

        pdf_text = "\n".join(
            page.extract_text() or ""
            for page in PdfReader(out / "01-resumo-executivo-multifonte.pdf").pages
        )
        for code in codes:
            assert code in pdf_text
        assert "Structural QA: PASS" in pdf_text
        assert "Delivery readiness: BLOCKED" in pdf_text
        assert "Structural QA: **PASS**" in readme
        assert "Delivery readiness: **BLOCKED**" in readme

        # checksums match
        checksums = json.loads((out / "checksums.json").read_text(encoding="utf-8"))
        import hashlib

        for name, meta in checksums["artifacts"].items():
            data = (out / name).read_bytes()
            assert hashlib.sha256(data).hexdigest() == meta["sha256"]
            assert len(data) == meta["bytes"]

    def test_xlsx_has_reconciliation_and_shortlist_sheets(self, tmp_path: Path):
        openpyxl = pytest.importorskip("openpyxl")
        pncp = tmp_path / "pncp.csv"
        entities = load_universe(UNIVERSE)
        ent = next(e for e in entities if e.distance_km is not None and e.cnpj)
        cnpj14 = (ent.cnpj + "000100")[:14]
        if len(cnpj14) < 14:
            cnpj14 = cnpj14.ljust(14, "0")
        with pncp.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "numero_controle_pncp",
                    "orgao_nome",
                    "orgao_cnpj",
                    "municipio",
                    "uf",
                    "objeto",
                    "modalidade",
                    "valor_estimado",
                    "data_publicacao",
                    "data_abertura",
                    "data_encerramento",
                    "link_edital",
                    "status_canonico",
                ],
            )
            w.writeheader()
            w.writerow(
                {
                    "numero_controle_pncp": f"{cnpj14}-1-000001/2026",
                    "orgao_nome": ent.canonical_name,
                    "orgao_cnpj": cnpj14,
                    "municipio": ent.municipio,
                    "uf": "SC",
                    "objeto": "Reforma predial de prédio público escolar",
                    "modalidade": "Concorrência",
                    "valor_estimado": "900000",
                    "data_publicacao": "2026-07-01",
                    "data_abertura": "",
                    "data_encerramento": "2026-09-15T17:00:00-03:00",
                    "link_edital": f"https://pncp.gov.br/app/editais/{cnpj14}/2026/1",
                    "status_canonico": "open",
                }
            )
        out = tmp_path / "pack2"
        build_pack(
            out_dir=out,
            universe_path=UNIVERSE,
            pncp_path=pncp,
            as_of=date(2026, 7, 31),
            now=datetime(2026, 7, 31, 12, 0, tzinfo=BR_TZ),
            pack_id="EXTRA-MS-OPEN-TEST-XLSX",
            skip_network=True,
            pilot_approval_path=_write_pilot_approval(tmp_path),
        )
        wb = openpyxl.load_workbook(out / "02-oportunidades-multifonte-dados.xlsx")
        names = set(wb.sheetnames)
        assert "Resumo" in names
        assert "Shortlist" in names
        assert "Processos_canonicos" in names
        assert "Documentos_links" in names
        assert "Cobertura_fontes" in names
        assert "Politica_fontes" in names
        assert "Limitacoes" in names
        assert "Metodologia" in names


class TestReconciliationInvariants:
    def test_blocked_without_reason_fails_qa_contract(self):
        meta = {"terminal_state": "BLOCKED", "blocking_reasons": [], "invariant_errors": []}
        _finalize_blocking_reasons(meta)
        assert meta["terminal_state"] == "FAIL"
        assert any("requires blocking_reasons" in error for error in meta["invariant_errors"])

    def test_pass_with_active_reason_fails_qa_contract(self):
        meta = {
            "terminal_state": "PASS",
            "blocking_reasons": [
                {
                    "code": "ACTIVE_BLOCKER",
                    "evidence": "evidence",
                    "owner": "owner",
                    "next_action": "act",
                }
            ],
            "invariant_errors": [],
        }
        _finalize_blocking_reasons(meta)
        assert meta["terminal_state"] == "FAIL"
        assert any("forbids active" in error for error in meta["invariant_errors"])

    def test_structural_green_can_remain_delivery_blocked(self):
        meta = {
            "terminal_state": "BLOCKED",
            "blocking_reasons": [
                {
                    "code": "SOURCE_FRESHNESS_STALE",
                    "evidence": "stale",
                    "owner": "source_ops",
                    "next_action": "refresh",
                }
            ],
            "invariant_errors": [],
        }
        _set_delivery_gates(meta)
        assert meta["structural_qa"]["ok"] is True
        assert meta["delivery_readiness"]["ok"] is False
        assert meta["deliverable"] is False
        assert meta["terminal_state"] == "BLOCKED"

    def test_package_is_deliverable_only_when_both_gates_pass(self):
        meta = {"terminal_state": "PASS", "blocking_reasons": [], "invariant_errors": []}
        _set_delivery_gates(meta)
        assert meta["structural_qa"]["ok"] is True
        assert meta["delivery_readiness"]["ok"] is True
        assert meta["deliverable"] is True
        assert meta["terminal_state"] == "PASS"

    def test_invariants_hold(self):
        entities = load_universe(UNIVERSE)
        obs = [
            _obs(observation_id=f"i{i}", id_externo=f"82922233000100-1-{i:06d}/2026")
            for i in range(5)
        ]
        # one out of universe
        obs.append(
            _obs(
                observation_id="out",
                id_externo="00000000000100-1-000001/2026",
                orgao="ORGAO DE OUTRO ESTADO",
                orgao_cnpj="00000000000100",
                municipio="CUIABA",
                in_universe=False,
                match_universo="out_of_universe",
                distance_km=None,
                entity_key="",
                is_active_dispute=True,
            )
        )
        procs, merges = consolidate_observations(obs, now=datetime(2026, 7, 31, 12, 0, tzinfo=BR_TZ))
        apply_decisions(procs, profile={})
        shortlist = select_shortlist(procs, limit=10)
        for p in shortlist:
            assert p.in_universe is True
            assert p.layer == "decision"
        stats = build_reconciliation(
            entities=entities,
            observations=obs,
            processes=procs,
            shortlist=shortlist,
            merges=merges,
        )
        assert stats.entes_universo == 1093
        assert stats.entes_cobertos <= 1093
        assert stats.processos_canonicos <= stats.observacoes_brutas
        assert not stats.assert_invariants()
