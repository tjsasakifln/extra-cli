"""Fail-closed cores for issues #300 #307 #251 #267 #293 #308 #310 #316 #318 #345.

Each test drives the shipped entry point from a real start state.
No hardcoded dump of the unit under test, no mocked SUT, no reimplemented oracle.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from scripts.crawl import compras_gov_crawler as cgc
from scripts.national_contract_truth.canonical_orchestration import (
    CanonicalJob,
    advance_fact,
    invalidate_derivatives,
    resume_job,
)
from scripts.national_contract_truth.compras_gov_feeder import (
    SCOPE_LEGADO,
    ComprasGovIngestError,
    PaginationVerdict,
    classify_fetch,
    default_open_window,
    ingest_scope,
)
from scripts.national_contract_truth.contract_corrections import (
    IncomingCorrection,
    apply_correction,
    decide_correction,
    material_hash,
    snapshot_as_of,
)
from scripts.national_contract_truth.contract_events import (
    ContractEvent,
    append_event,
    empty_ledger,
)
from scripts.national_contract_truth.freshness_slo import (
    LayerObservation,
    evaluate_layer,
    freshness_claim_allowed,
    overlay_entity_sla,
)
from scripts.national_contract_truth.late_arrivals import (
    due_for_revalidation,
    is_sealed_forever,
    late_arrival_is_in_scope,
    may_advance_checkpoint,
    stamp_complete,
)
from scripts.national_contract_truth.platform_discovery import (
    SurfaceEvidence,
    classify_discovery,
    quarantine_source_id,
)
from scripts.national_contract_truth.relation_health import (
    RelationMetrics,
    analyze_after_bulk_load,
    evaluate_relation,
)
from scripts.national_contract_truth.tender_dossier import (
    DossierClaim,
    DossierInputs,
    build_dossier,
    client_profile_change_schedules_work,
    contains_client_column,
    inputs_hash,
)
from scripts.national_contract_truth.universe_linkage import (
    FORBIDDEN_COLLAPSE_ROOT,
    LakeRow,
    UniverseRow,
    evaluate_readiness,
)
from scripts.universe_tools import link_included_to_datalake

NOW = datetime(2026, 8, 14, 12, 0, 0)


def _cnpj14(root8: str, branch: str = "0001") -> str:
    body = (root8 + branch)[:12].ljust(12, "0")
    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    def dv(nums: str, weights: list[int]) -> int:
        total = sum(int(n) * w for n, w in zip(nums, weights, strict=True))
        rem = total % 11
        return 0 if rem < 2 else 11 - rem

    d13 = body + str(dv(body, weights1))
    return d13 + str(dv(d13, weights2))


class TestIssue300UniverseLinkage:
    def test_readiness_requires_full_resolution_via_universe_tools(self):
        cnpj_a = _cnpj14("11222333")
        cnpj_b = _cnpj14("44555666")
        rows = (
            UniverseRow("ent-a", cnpj_a, cnpj_a[:8], "PREFEITURA A", "BLUMENAU", True),
            UniverseRow("ent-b", cnpj_b, cnpj_b[:8], "PREFEITURA B", "JOINVILLE", True),
        )
        lake = (LakeRow("db-a", cnpj_a, cnpj_a[:8], "PREFEITURA A", "BLUMENAU"),)
        ledger = link_included_to_datalake(rows, lake, active_run_keys=["ent-a", "ent-b"])
        readiness = evaluate_readiness(ledger)
        assert readiness.ready is False
        assert readiness.denominator == 2
        assert readiness.resolved == 1
        assert any("ent-b" in item for item in readiness.blockers)

    def test_forbidden_root_is_not_collapsed(self):
        left = _cnpj14(FORBIDDEN_COLLAPSE_ROOT, "0001")
        right = _cnpj14(FORBIDDEN_COLLAPSE_ROOT, "0002")
        rows = (
            UniverseRow("dup-1", None, FORBIDDEN_COLLAPSE_ROOT, None, None, True),
            UniverseRow("dup-2", None, FORBIDDEN_COLLAPSE_ROOT, None, None, True),
        )
        lake = (
            LakeRow("db-1", left, FORBIDDEN_COLLAPSE_ROOT, "ORGAO UM", "A"),
            LakeRow("db-2", right, FORBIDDEN_COLLAPSE_ROOT, "ORGAO DOIS", "B"),
        )
        ledger = link_included_to_datalake(rows, lake, active_run_keys=["dup-1", "dup-2"])
        assert {d.status for d in ledger.decisions} == {"ambiguous"}
        assert all(d.db_entity_id is None for d in ledger.decisions)
        assert all(d.blocker == "refuse_collapse_00394494" for d in ledger.decisions)

    def test_duplicate_root_with_full_cnpj_stays_two_links(self):
        left = _cnpj14(FORBIDDEN_COLLAPSE_ROOT, "0001")
        right = _cnpj14(FORBIDDEN_COLLAPSE_ROOT, "0002")
        rows = (
            UniverseRow("dup-1", left, FORBIDDEN_COLLAPSE_ROOT, "ORGAO UM", "A", True),
            UniverseRow("dup-2", right, FORBIDDEN_COLLAPSE_ROOT, "ORGAO DOIS", "B", True),
        )
        lake = (
            LakeRow("db-1", left, FORBIDDEN_COLLAPSE_ROOT, "ORGAO UM", "A"),
            LakeRow("db-2", right, FORBIDDEN_COLLAPSE_ROOT, "ORGAO DOIS", "B"),
        )
        ledger = link_included_to_datalake(rows, lake, active_run_keys=["dup-1", "dup-2"])
        assert {d.db_entity_id for d in ledger.decisions} == {"db-1", "db-2"}
        assert evaluate_readiness(ledger).ready is True

    def test_outside_active_run_is_excluded_from_denominator(self):
        cnpj_a = _cnpj14("11222333")
        rows = (
            UniverseRow("in-run", cnpj_a, cnpj_a[:8], "A", "X", True),
            UniverseRow("out-run", cnpj_a, cnpj_a[:8], "A", "X", True),
        )
        lake = (LakeRow("db-a", cnpj_a, cnpj_a[:8], "A", "X"),)
        ledger = link_included_to_datalake(rows, lake, active_run_keys=["in-run"])
        assert ledger.denominator_keys == frozenset({"in-run"})
        assert any(d.status == "excluded" and d.canonical_entity_key == "out-run" for d in ledger.decisions)
        assert evaluate_readiness(ledger).ready is True

    def test_replay_is_idempotent(self):
        cnpj_a = _cnpj14("11222333")
        rows = (UniverseRow("ent-a", cnpj_a, cnpj_a[:8], "A", "X", True),)
        lake = (LakeRow("db-a", cnpj_a, cnpj_a[:8], "A", "X"),)
        first = link_included_to_datalake(rows, lake, active_run_keys=["ent-a"])
        second = link_included_to_datalake(rows, lake, active_run_keys=["ent-a"])
        assert first == second


class TestIssue307ContractCorrections:
    def _incoming(self, valor: float, when: datetime, raw: str = "raw-1") -> IncomingCorrection:
        return IncomingCorrection(
            payload={
                "valor": valor,
                "objeto": "obra",
                "fornecedor": "ACME",
                "vigencia_inicio": "2026-01-01",
                "vigencia_fim": "2026-12-31",
                "data_assinatura": "2025-12-15",
                "status": "vigente",
            },
            source_updated_at=when,
            observed_at=when,
            raw_hash=raw,
            run_id="run-1",
            attempt_id="att-1",
        )

    def test_identical_payload_only_touches_last_seen(self):
        incoming = self._incoming(10.0, NOW)
        versions, first = apply_correction([], incoming)
        assert first.action == "CREATE"
        versions, second = apply_correction(versions, incoming)
        assert second.action == "TOUCH_LAST_SEEN"
        assert second.next_version is None
        assert len(versions) == 1

    def test_newer_rectification_creates_immutable_version(self):
        versions, _ = apply_correction([], self._incoming(10.0, NOW))
        later = self._incoming(12.5, NOW + timedelta(days=1), raw="raw-2")
        later_payload = dict(later.payload)
        later_payload["valor"] = 12.5
        later = IncomingCorrection(
            payload=later_payload,
            source_updated_at=NOW + timedelta(days=1),
            observed_at=NOW + timedelta(days=1),
            raw_hash="raw-2",
            run_id="run-2",
            attempt_id="att-2",
        )
        versions, decision = apply_correction(versions, later)
        assert decision.action == "NEW_VERSION"
        assert decision.next_version == 2
        assert versions[0].payload["valor"] == 10.0
        assert versions[0].valid_to == NOW + timedelta(days=1)
        assert versions[1].payload["valor"] == 12.5
        assert versions[1].valid_to is None

    def test_late_older_payload_does_not_overwrite(self):
        versions, _ = apply_correction([], self._incoming(10.0, NOW))
        newer_payload = dict(self._incoming(20.0, NOW + timedelta(days=2)).payload)
        newer_payload["valor"] = 20.0
        versions, _ = apply_correction(
            versions,
            IncomingCorrection(newer_payload, NOW + timedelta(days=2), NOW + timedelta(days=2), "raw-n", "r", "a"),
        )
        stale = IncomingCorrection(
            self._incoming(11.0, NOW - timedelta(days=5)).payload,
            NOW - timedelta(days=5),
            NOW + timedelta(days=3),
            "raw-old",
            "r",
            "a",
        )
        after, decision = apply_correction(versions, stale)
        assert decision.action == "REJECT_STALE"
        assert after[-1].payload["valor"] == 20.0
        assert snapshot_as_of(after, NOW + timedelta(days=2)).payload["valor"] == 20.0

    def test_material_hash_ignores_observation_metadata(self):
        left = {
            "valor": 1,
            "objeto": "x",
            "fornecedor": "y",
            "vigencia_inicio": "a",
            "vigencia_fim": "b",
            "data_assinatura": "c",
            "status": "s",
            "run": "1",
        }
        right = {**left, "run": "2", "attempt": "9"}
        assert material_hash(left) == material_hash(right)
        assert decide_correction(None, self._incoming(1.0, NOW)).next_version == 1


class TestIssue251ComprasGov:
    def test_fetch_error_is_failed_not_zero(self):
        outcome = classify_fetch(http_status=None, records=[], error="timeout")
        assert outcome.status == "FAILED"
        empty_ok = classify_fetch(http_status=200, records=[], error=None)
        assert empty_ok.status == "ZERO"

    def test_malformed_200_body_is_failed_not_zero(self):
        monkey = pytest.MonkeyPatch()
        monkey.setattr(cgc, "_make_request", lambda _url: {"erro": "indisponivel"})
        monkey.setattr(cgc, "REQUEST_DELAY", 0)
        try:
            with pytest.raises(ComprasGovIngestError) as exc:
                cgc._paginate("/modulo-contratacoes/x", {"tamanhoPagina": 1}, max_pages=2)
            assert exc.value.status == "FAILED"
        finally:
            monkey.undo()

    def test_missing_pagination_metadata_at_cap_is_truncated(self):
        payload = {"resultado": [{"numeroControlePNCP": "1", "objetoCompra": "x"}]}

        def fake_request(_url: str):
            return payload

        monkey = pytest.MonkeyPatch()
        monkey.setattr(cgc, "_make_request", fake_request)
        monkey.setattr(cgc, "REQUEST_DELAY", 0)
        try:
            with pytest.raises(ComprasGovIngestError) as exc:
                cgc._paginate("/modulo-contratacoes/x", {"tamanhoPagina": 1}, max_pages=1)
            assert exc.value.status == "PAGINATION_TRUNCATED"
        finally:
            monkey.undo()

    def test_max_pages_truncation_fails_closed_through_crawler(self):
        payload = {
            "resultado": [{"numeroControlePNCP": "1", "objetoCompra": "x"}],
            "paginasRestantes": 3,
            "totalPaginas": 4,
        }

        def fake_request(_url: str):
            return payload

        monkey = pytest.MonkeyPatch()
        monkey.setattr(cgc, "_make_request", fake_request)
        monkey.setattr(cgc, "REQUEST_DELAY", 0)
        try:
            with pytest.raises(ComprasGovIngestError) as exc:
                cgc._paginate("/modulo-contratacoes/x", {"tamanhoPagina": 1}, max_pages=1)
            assert exc.value.status == "PAGINATION_TRUNCATED"
        finally:
            monkey.undo()

    def test_full_mode_uses_2025_open_window(self):
        window = default_open_window(date(2026, 8, 14), has_native_open_status=False)
        assert window == (date(2025, 1, 1), date(2026, 8, 14))
        assert default_open_window(date(2026, 8, 14), has_native_open_status=True) is None

    def test_legacy_without_cnpj_is_review_via_crawler(self):
        record = cgc.transform(
            [
                {
                    "id_compra": "20230001",
                    "objeto": "servico",
                    "valor_estimado": 1,
                    "modalidade": 1,
                    "nome_modalidade": "Pregao",
                    "data_publicacao": "2023-06-15T10:00:00",
                }
            ]
        )[0]
        assert record["orgao_cnpj"] == ""
        assert cgc.identity_disposition(record) == "REVIEW"
        verdict = PaginationVerdict("COMPLETE", 1, 1, "exhausted")
        ingest = ingest_scope(SCOPE_LEGADO, verdict, [record])
        assert ingest.dispositions == ("REVIEW",)


class TestIssue267Discovery:
    def test_new_domain_is_quarantined_not_merged(self):
        source_id = quarantine_source_id("https://www.editais.exemplo.gov.br/licitacoes")
        assert source_id == "unknown:editais.exemplo.gov.br"
        decision = classify_discovery(
            SurfaceEvidence(
                domain="https://editais.exemplo.gov.br",
                terms_or_robots="allow",
                public_surface="https://editais.exemplo.gov.br/licitacoes",
                technology="wordpress",
                login_required=False,
                captcha=False,
                contract_test_pass=False,
            )
        )
        assert decision.source_id.startswith("unknown:")
        assert decision.terminal == "BLOCKED"
        assert decision.merged_into is None

    def test_found_or_zero_are_illegal_before_promotion(self):
        exhausted = classify_discovery(SurfaceEvidence("portal.novo.br", "robots", None, "custom", False, False, False))
        assert exhausted.terminal == "DISCOVERY_EXHAUSTED_NO_SURFACE"
        promoted = classify_discovery(
            SurfaceEvidence("portal.novo.br", "robots", "/editais", "custom", False, False, True)
        )
        assert promoted.terminal == "PROMOTED"
        assert not promoted.source_id.startswith("unknown:")


class TestIssue293Orchestration:
    def test_every_input_reaches_ready_or_blocked(self):
        job = CanonicalJob("j1", "hash-a", "PENDING", 0)
        ready = advance_fact(job, now=NOW, success=True)
        assert ready.job.state == "CANONICAL_READY"
        blocked = advance_fact(job, now=NOW, success=False, reason="MISSING_DOC")
        assert blocked.job.state == "BLOCKED"
        assert blocked.served_revision is None

    def test_restart_does_not_duplicate_and_poison_goes_to_dlq(self):
        job = CanonicalJob("j1", "hash-a", "PENDING", 0, last_valid_revision="rev-0", last_valid_at=NOW)
        first = resume_job(job)
        assert first.http_or_ocr_scheduled is True
        second = resume_job(first.job)
        assert second.http_or_ocr_scheduled is False
        poison = advance_fact(
            CanonicalJob("j2", "hash-b", "BUILDING", 1, poison=True, last_valid_revision="rev-old"),
            now=NOW,
            success=False,
        )
        assert poison.job.state == "DLQ"
        assert poison.served_revision == "rev-old"

    def test_invalidation_is_selective(self):
        jobs = [
            CanonicalJob("keep", "hash-keep", "CANONICAL_READY", 1, last_valid_revision="r1"),
            CanonicalJob("drop", "hash-drop", "CANONICAL_READY", 1, last_valid_revision="r2"),
        ]
        updated = invalidate_derivatives("hash-drop", jobs)
        assert updated[0].state == "CANONICAL_READY"
        assert updated[1].state == "PENDING"
        assert updated[1].last_valid_revision == "r2"


class TestIssue308LateArrivals:
    def test_completed_window_is_never_sealed(self):
        state = stamp_complete("2024-01", "cold", NOW)
        assert state.revalidate_after is not None
        assert is_sealed_forever(state) is False
        assert due_for_revalidation(state, NOW + timedelta(days=31)) is True

    def test_published_today_with_old_event_date_is_in_scope(self):
        assert late_arrival_is_in_scope(
            event_date=NOW - timedelta(days=120),
            published_at=NOW - timedelta(hours=2),
            now=NOW,
            incremental_lookback=timedelta(days=7),
        )
        assert not late_arrival_is_in_scope(
            event_date=NOW - timedelta(days=1),
            published_at=NOW - timedelta(hours=2),
            now=NOW,
            incremental_lookback=timedelta(days=7),
        )

    def test_checkpoint_waits_for_raw_persist_and_reconcile(self):
        assert may_advance_checkpoint(raw_ok=True, persist_ok=True, reconcile_ok=True)
        assert not may_advance_checkpoint(raw_ok=True, persist_ok=True, reconcile_ok=False)


class TestIssue310ContractEvents:
    def _event(self, family: str, eid: str, days: int = 0, source: str = "pncp") -> ContractEvent:
        when = NOW + timedelta(days=days)
        return ContractEvent(source, eid, family, when, when, None, None, f"raw-{eid}", "run", "c-1")

    def test_no_signal_is_unknown_not_inactive(self):
        ledger = empty_ledger()
        assert ledger.current_state == "UNKNOWN"
        assert ledger.events == ()

    def test_out_of_order_and_idempotent_dedup(self):
        ledger = empty_ledger()
        rescisao = self._event("rescisao", "e2", days=2)
        aditivo = self._event("aditivo", "e1", days=0)
        ledger = append_event(ledger, rescisao)
        ledger = append_event(ledger, aditivo)
        replay = append_event(ledger, rescisao)
        assert replay.events == ledger.events
        assert ledger.current_state == "RESCINDED"
        other_source = self._event("aditivo", "e1", days=0, source="dou")
        both = append_event(ledger, other_source)
        assert len(both.events) == 3


class TestIssue316RelationHealth:
    def test_bloat_and_stale_stats_alert(self):
        health = evaluate_relation(
            RelationMetrics(
                "pncp_supplier_contracts",
                dead_ratio=0.45,
                last_analyze_age=timedelta(days=3),
                last_vacuum_age=timedelta(days=10),
                freeze_age=10,
                heap_bytes=1,
                index_bytes=1,
            )
        )
        assert health.level == "ALERT"
        assert "dead_ratio_high" in health.reasons
        assert health.should_analyze is True

    def test_wraparound_blocks_and_analyze_waits_for_commit(self):
        health = evaluate_relation(
            RelationMetrics(
                "pncp_supplier_contracts",
                0.01,
                timedelta(hours=1),
                timedelta(hours=1),
                freeze_age=1_600_000_000,
                heap_bytes=1,
                index_bytes=1,
            )
        )
        assert health.level == "BLOCK"
        assert "wraparound_imminent" in health.reasons
        assert analyze_after_bulk_load(committed=True, reconciled=True)
        assert not analyze_after_bulk_load(committed=True, reconciled=False)


class TestIssue318FreshnessSlo:
    def test_breach_blocks_claim_without_masking_entity_sla(self):
        obs = LayerObservation(
            "publication",
            age_since_complete_run=timedelta(days=4),
            lag_p50=timedelta(hours=1),
            lag_p95=timedelta(hours=2),
            lag_p99=timedelta(hours=3),
        )
        evaluation = evaluate_layer(obs)
        assert evaluation.status == "BREACH"
        assert freshness_claim_allowed([evaluation], entity_sla_ok=True) is False
        assert overlay_entity_sla(evaluation.status, "entity-ok-36h") == "entity-ok-36h"

    def test_within_slo_still_requires_entity_sla(self):
        obs = LayerObservation(
            "publication",
            age_since_complete_run=timedelta(hours=3),
            lag_p50=timedelta(minutes=10),
            lag_p95=timedelta(minutes=20),
            lag_p99=timedelta(minutes=30),
        )
        evaluation = evaluate_layer(obs)
        assert evaluation.status == "OK"
        assert freshness_claim_allowed([evaluation], entity_sla_ok=False) is False


class TestIssue345TenderDossier:
    def _inputs(self, **overrides: object) -> DossierInputs:
        claims = (DossierClaim("objeto", "reforma", "pncp", "doc-edital", "p.3", "ext-1", "pol-1", "observed"),)
        base = dict(
            tender_id="proc-1",
            snapshot_id="snap-1",
            schema_version="1",
            policy_version="pol-1",
            extractor_version="ext-1",
            document_hashes=("doc-edital",),
            required_document_hashes=("doc-edital",),
            claims=claims,
        )
        base.update(overrides)
        return DossierInputs(**base)  # type: ignore[arg-type]

    def test_missing_required_document_is_blocked(self):
        dossier = build_dossier(self._inputs(document_hashes=(), required_document_hashes=("doc-edital",)))
        assert dossier.state == "BLOCKED"
        assert dossier.reason_code == "MISSING_REQUIRED_DOCUMENT"

    def test_claim_without_observed_evidence_cannot_complete(self):
        claims = (DossierClaim("objeto", "reforma", "pncp", "doc-edital", "p.3", "ext-1", "pol-1", "missing"),)
        dossier = build_dossier(self._inputs(claims=claims))
        assert dossier.state == "BLOCKED"
        assert dossier.reason_code == "CLAIM_WITHOUT_EVIDENCE"

    def test_claim_without_locator_cannot_complete(self):
        claims = (DossierClaim("valor", 10, "pncp", "doc-edital", None, "ext-1", "pol-1", "observed"),)
        dossier = build_dossier(self._inputs(claims=claims))
        assert dossier.state == "BLOCKED"
        assert dossier.reason_code == "CLAIM_WITHOUT_LOCATOR"

    def test_same_inputs_are_idempotent_and_client_profile_is_inert(self):
        first = build_dossier(self._inputs())
        second = build_dossier(self._inputs(), previous=first)
        assert first.state == "COMPLETE"
        assert second is first
        assert inputs_hash(self._inputs()) == inputs_hash(self._inputs())
        assert client_profile_change_schedules_work(first, "profile-b") is False
        assert contains_client_column({"tender_id": "x", "score": 9}) is True
        assert contains_client_column({"tender_id": "x", "objeto": "y"}) is False
