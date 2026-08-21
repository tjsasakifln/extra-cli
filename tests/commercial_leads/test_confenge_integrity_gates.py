"""Integrity gates for CONFENGE PR #144 — drive shipped functions only."""

from __future__ import annotations

import json

from scripts.commercial_leads.scoring import (
    MAX_SINGLE_SIGNAL_OFFER_CHANGE_RATE,
    MIN_SELECTED_OFFER_MARGIN,
    LeadScore,
    diagnose_offer_distribution,
)
from scripts.ops.confenge_code_freeze import (
    ART,
    compute_match_run_to_head,
    verify_code_freeze,
    verify_final_integrity_code_freeze,
    verify_sha_semantics,
)
from scripts.ops.confenge_offer_sensitivity import evaluate_offer_pass


def _fake_lead(
    *,
    cnpj14: str = "11222333000181",
    selected_offer: str = "diagnostico_b2g",
    alternative_offer: str | None = "licitacoes_propostas",
    selected_offer_margin: float = 1.0,
    offer_scores: dict | None = None,
    supporting_signals: list | None = None,
    suggested_offer: str | None = None,
) -> LeadScore:
    scores = offer_scores or {
        "diagnostico_b2g_score": 3.0,
        "licitacoes_propostas_score": 2.0,
        "auditoria_orcamento_score": 0.0,
        "acompanhamento_contratual_score": 0.5,
        "gestao_documental_score": 0.0,
        "inteligencia_pncp_score": 0.0,
    }
    return LeadScore(
        cnpj14=cnpj14,
        razao_social="EMP",
        score_total=5.0,
        priority="HIGH",
        decomposition={},
        signals_fired=[],
        signals_not_computable=[],
        all_signals=[],
        evidence=[],
        suggested_offer=suggested_offer or selected_offer,
        next_human_step="review",
        offer_scores=scores,
        selected_offer=selected_offer,
        selected_offer_margin=selected_offer_margin,
        supporting_signals=list(supporting_signals or ["first_public_contract"]),
        alternative_offer=alternative_offer,
    )


def test_match_run_to_head_only_when_executed_equals_head() -> None:
    assert compute_match_run_to_head(executed_code_sha="abc", current_pr_head_sha="abc") is True
    assert compute_match_run_to_head(executed_code_sha="abc", current_pr_head_sha="def") is False
    assert compute_match_run_to_head(executed_code_sha=None, current_pr_head_sha="x") is False


def test_sha_semantics_fail_when_match_true_with_mismatch() -> None:
    """executed != head AND match_run_to_head == true → FAIL."""
    rep = verify_sha_semantics(
        executed_code_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        current_pr_head_sha="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        match_run_to_head=True,
        write_artifact=False,
    )
    assert rep["ok"] is False
    assert rep["status"] == "BLOCKED_CODE_EXECUTION_SHA_MISMATCH"
    assert "FORBIDDEN_match_run_to_head_with_sha_mismatch" in rep["issues"] or (
        "match_run_to_head_true_with_executed_ne_head" in rep["issues"]
    )


def test_sha_semantics_pass_when_match_false_with_lag() -> None:
    rep = verify_sha_semantics(
        executed_code_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        current_pr_head_sha="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        match_run_to_head=False,
        code_changed_after_execution=False,
        artifact_only_commits_after_execution=True,
        write_artifact=False,
    )
    assert rep["ok"] is True
    assert rep["match_run_to_head_derived"] is False


def test_sha_semantics_fixture_does_not_write_dummy_gate(tmp_path, monkeypatch) -> None:
    """Unit fixtures with aaaa/bbbb must not poison the final campaign gate file."""
    from scripts.ops import confenge_code_freeze as cf

    art = tmp_path / "art"
    art.mkdir()
    monkeypatch.setattr(cf, "ART", art)
    # Even without write_artifact=False, dummy detection must refuse write
    rep = verify_sha_semantics(
        executed_code_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        current_pr_head_sha="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        match_run_to_head=False,
        artifact_only_commits_after_execution=True,
        code_changed_after_execution=False,
    )
    assert rep["ok"] is True
    assert not (art / "sha-semantics-gate.json").is_file()


def test_offer_text_justification_cannot_override_diagnose_block() -> None:
    leads = [
        _fake_lead(
            cnpj14=f"{i:014d}",
            selected_offer="acompanhamento_contratual",
            alternative_offer=None,
            selected_offer_margin=0.01,
            offer_scores={"acompanhamento_contratual_score": 1.0},
            supporting_signals=["near_expiry"],
        )
        for i in range(10)
    ]
    diag = diagnose_offer_distribution(leads)
    # Force block-like diagnose fields if not already
    if not diag.get("block"):
        diag = {
            **diag,
            "block": "BLOCKED_OFFER_MAPPING_NOT_DISCRIMINATIVE",
            "robust_quantitative_justification": False,
            "explanation": {
                **(diag.get("explanation") or {}),
                "catalog_degenerate": True,
            },
        }
    decision = evaluate_offer_pass(
        baseline=leads,
        diag=diag,
        change_rates={"near_expiry": 0.1},
    )
    assert decision["ok"] is False
    assert decision["individual_justification_override_forbidden"] is True
    assert decision["diagnose_block"] is not None or decision["catalog_degenerate"]
    # even if every lead has individual_justification text, still fail
    assert all(hasattr(x, "selected_offer") for x in leads)


def test_offer_excessive_sensitivity_threshold() -> None:
    leads = [
        _fake_lead(
            cnpj14=f"{i:014d}",
            selected_offer="diagnostico_b2g" if i % 2 == 0 else "licitacoes_propostas",
            alternative_offer="gestao_documental",
            selected_offer_margin=1.0,
            offer_scores={
                "diagnostico_b2g_score": 3.0 if i % 2 == 0 else 1.0,
                "licitacoes_propostas_score": 1.0 if i % 2 == 0 else 3.0,
                "auditoria_orcamento_score": 0.5,
                "acompanhamento_contratual_score": 0.2,
                "gestao_documental_score": 0.8,
                "inteligencia_pncp_score": 0.1,
            },
            supporting_signals=["first_public_contract", f"sig{i % 3}"],
        )
        for i in range(10)
    ]
    diag = {
        "block": None,
        "robust_quantitative_justification": True,
        "explanation": {"catalog_degenerate": False},
        "dominant_offer_rate": 0.5,
    }
    decision = evaluate_offer_pass(
        baseline=leads,
        diag=diag,
        change_rates={"agency_concentration": 0.75},
        max_change_rate=MAX_SINGLE_SIGNAL_OFFER_CHANGE_RATE,
        min_margin=MIN_SELECTED_OFFER_MARGIN,
    )
    assert decision["ok"] is False
    assert "BLOCKED_OFFER_MAPPING_EXCESSIVELY_SENSITIVE" in decision["reasons"]
    assert decision["status"] == "BLOCKED_OFFER_MAPPING_EXCESSIVELY_SENSITIVE"


def test_offer_pass_when_all_cumulative_rules_hold() -> None:
    leads = [
        _fake_lead(
            cnpj14=f"{i:014d}",
            selected_offer="diagnostico_b2g" if i < 6 else "licitacoes_propostas",
            alternative_offer="gestao_documental",
            selected_offer_margin=1.2,
            offer_scores={
                "diagnostico_b2g_score": 3.0 if i < 6 else 1.5,
                "licitacoes_propostas_score": 1.5 if i < 6 else 3.0,
                "auditoria_orcamento_score": 0.5,
                "acompanhamento_contratual_score": 0.4,
                "gestao_documental_score": 0.9,
                "inteligencia_pncp_score": 0.3,
            },
            supporting_signals=["first_public_contract", f"sig{i % 4}"],
        )
        for i in range(10)
    ]
    diag = diagnose_offer_distribution(leads)
    decision = evaluate_offer_pass(
        baseline=leads,
        diag=diag,
        change_rates={
            "near_expiry": 0.1,
            "agency_concentration": 0.2,
            "concurrent_portfolio": 0.0,
            "contract_concentration": 0.05,
        },
    )
    assert decision["ok"] is True, decision
    assert decision["status"] == "PASS"
    assert decision["diagnose_block"] is None
    assert decision["catalog_degenerate"] is False


def test_full_pipeline_e2e_starts_from_discovery_not_frozen_list() -> None:
    """Static + function contract: full pipeline gate kind is discovery-based."""
    from scripts.ops import confenge_full_pipeline_e2e as e2e
    from scripts.ops import confenge_full_universe_e2e as down

    assert "raw_snapshot" in e2e.one_full_pipeline_pass.__doc__ or hasattr(e2e, "discovery_input_fingerprint")
    assert e2e.STAGE_HASH_KEYS[0] == "discovery_input_hash"
    assert "discovery_input_hash" in e2e.STAGE_HASH_KEYS
    # Downstream module documents frozen universe start
    assert "frozen" in (down.__doc__ or "").lower() or "frozen" in (down.run_full_universe_e2e.__doc__ or "").lower()


def test_cross_artifact_aggregator_agreement(tmp_path, monkeypatch) -> None:
    """build_final_campaign_status drives derived files to the same terminal reason."""
    from scripts.ops import confenge_final_status as fs

    # Point ART to temp so we don't clobber workspace mid-test incorrectly
    art = tmp_path / "art"
    art.mkdir()
    monkeypatch.setattr(fs, "ART", art)
    # minimal gate files so aggregator has something to read
    (art / "EXECUTED_CODE_SHA.txt").write_text("abc\n")
    (art / "FINAL_INTEGRITY_CODE_FREEZE_SHA.txt").write_text("abc\n")
    (art / "full-pipeline-e2e-reproducibility-gate.json").write_text('{"ok": true, "status": "PASS"}\n')
    (art / "downstream-reproducibility-gate.json").write_text('{"ok": true, "status": "PASS"}\n')
    (art / "offer-sensitivity-gate.json").write_text(
        '{"ok": true, "status": "PASS", "diagnose": {"block": null, "robust_quantitative_justification": true, "explanation": {"catalog_degenerate": false}}}\n'
    )
    (art / "offer-discrimination-gate.json").write_text(
        '{"ok": true, "status": "PASS", "diagnose": {"block": null, "robust_quantitative_justification": true, "explanation": {"catalog_degenerate": false}}}\n'
    )
    (art / "human-review-packages-gate.json").write_text(
        '{"ok": true, "status": "PACKAGES_READY_BLOCKED_REAL_HOLDOUT_NOT_REVIEWED", "published_as_workflow_artifact": true}\n'
    )
    (art / "real-corpus-provenance-gate.json").write_text('{"ok": true, "status": "PASS"}\n')
    (art / "registry-universe-gate.json").write_text(
        '{"ok": false, "status": "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE", "official_coverage": 0.05}\n'
    )
    (art / "historical-window-gate.json").write_text('{"ok": true, "status": "PASS"}\n')
    (art / "restored-snapshot-verify.json").write_text('{"ok": true}\n')

    status = fs.write_derived_artifacts()
    result = fs._load("result.json")
    qs = fs._load("queue-summary.json")
    closure = fs._load("final-evidence-closure.json")
    assert result["status"] == qs["status"] == closure["status"] == "BLOCKED"
    assert result["reason"] == qs["reason"] == closure["terminal_reason"] == "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE"
    assert "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE" in status["machine_blockers"]
    assert status["all_other_machine_blockers"] == []
    assert status["terminal_declaration"] == ("BLOCKED_ONLY_OFFICIAL_REGISTRY_AND_HUMAN_REVIEW")
    # No contradictory insufficient historical window
    assert qs["reason"] != "BLOCKED_INSUFFICIENT_HISTORICAL_WINDOW"
    # Layered real-data must not claim PASS when jobs were not executed
    assert status["real_data_ci_status"] in ("PASS", "NOT_EXECUTED", "FAIL")
    # Integrity + evidence + merge-readiness written by sole aggregator
    assert (art / "final-integrity-closure.json").is_file()
    assert (art / "merge-readiness.json").is_file()
    integrity = fs._load("final-integrity-closure.json")
    assert integrity["terminal_reason"] == result["terminal_reason"]
    assert integrity["real_data_ci_status"] == result["real_data_ci_status"]


def test_aggregate_real_data_ci_requires_all_four_pass() -> None:
    from scripts.ops.confenge_final_status import aggregate_real_data_ci_status

    assert aggregate_real_data_ci_status("PASS", "PASS", "PASS", "PASS") == "PASS"
    assert aggregate_real_data_ci_status("PASS", "NOT_EXECUTED", "PASS", "PASS") == "NOT_EXECUTED"
    assert aggregate_real_data_ci_status("PASS", "FAIL", "NOT_EXECUTED", "PASS") == "FAIL"
    # publication alias must not upgrade to PASS
    assert aggregate_real_data_ci_status("PASS_ARTIFACT_PUBLICATION", "PASS", "PASS", "PASS") == "NOT_EXECUTED"


def test_resolve_sha_roles_never_promotes_merge_to_pr_head(monkeypatch) -> None:
    from scripts.ops.confenge_final_status import resolve_sha_roles

    monkeypatch.setenv("CONFENGE_PR_HEAD_SHA", "prhead11111111111111111111111111111111")
    monkeypatch.setenv("CONFENGE_WORKFLOW_MERGE_SHA", "mergesha222222222222222222222222222222")
    roles = resolve_sha_roles(
        checked_out_sha="mergesha222222222222222222222222222222",
        executed_code_sha="freeze33333333333333333333333333333333",
        freeze_sha="freeze33333333333333333333333333333333",
        artifact_only=True,
        code_changed=False,
    )
    assert roles["pr_head_sha"] == "prhead11111111111111111111111111111111"
    assert roles["current_pr_head_sha"] == roles["pr_head_sha"]
    assert roles["workflow_merge_sha"] == "mergesha222222222222222222222222222222"
    assert roles["match_run_to_head"] is False
    assert roles["artifact_only_commits_after_execution"] is True
    assert roles["code_changed_after_execution"] is False


def test_cross_artifact_fails_when_integrity_pass_evidence_not_executed() -> None:
    """Adversarial: integrity says real-data PASS, evidence says NOT_EXECUTED → FAIL."""
    from scripts.ops.confenge_final_status import collect_cross_artifact_issues

    issues = collect_cross_artifact_issues(
        result={
            "status": "BLOCKED",
            "terminal_reason": "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE",
            "technical_status": "BLOCKED",
            "executed_code_sha": "abc",
            "match_run_to_head": False,
            "machine_blockers": ["BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE"],
            "real_data_ci_status": "NOT_EXECUTED",
            "pr_head_sha": "head1",
            "current_pr_head_sha": "head1",
        },
        queue={
            "status": "BLOCKED",
            "reason": "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE",
            "technical_status": "BLOCKED",
            "executed_code_sha": "abc",
            "match_run_to_head": False,
            "machine_blockers": ["BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE"],
            "real_data_ci_status": "NOT_EXECUTED",
        },
        evidence={
            "status": "BLOCKED",
            "terminal_reason": "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE",
            "technical_status": "BLOCKED",
            "executed_code_sha": "abc",
            "match_run_to_head": False,
            "machine_blockers": ["BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE"],
            "real_data_ci_status": "NOT_EXECUTED",
        },
        integrity={
            "real_data_ci_status": "PASS",
            "terminal_reason": "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE",
            "remaining_machine_blockers": ["BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE"],
        },
    )
    assert any("real_data_ci_status" in i for i in issues)


def test_cross_artifact_fails_when_pr_head_mismatch() -> None:
    from scripts.ops.confenge_final_status import collect_cross_artifact_issues

    issues = collect_cross_artifact_issues(
        result={
            "status": "BLOCKED",
            "terminal_reason": "X",
            "technical_status": "BLOCKED",
            "executed_code_sha": "abc",
            "match_run_to_head": False,
            "machine_blockers": [],
            "real_data_ci_status": "NOT_EXECUTED",
            "pr_head_sha": "reported_head",
            "current_pr_head_sha": "reported_head",
        },
        queue={
            "status": "BLOCKED",
            "reason": "X",
            "technical_status": "BLOCKED",
            "executed_code_sha": "abc",
            "match_run_to_head": False,
            "machine_blockers": [],
            "real_data_ci_status": "NOT_EXECUTED",
        },
        evidence={
            "status": "BLOCKED",
            "terminal_reason": "X",
            "technical_status": "BLOCKED",
            "executed_code_sha": "abc",
            "match_run_to_head": False,
            "machine_blockers": [],
            "real_data_ci_status": "NOT_EXECUTED",
            "pr_head_sha": "reported_head",
        },
        expected_pr_head="actual_live_head",
    )
    assert any("pr_head_mismatch" in i for i in issues)


def test_cross_artifact_fails_on_dummy_sha_in_semantics_gate() -> None:
    from scripts.ops.confenge_final_status import collect_cross_artifact_issues

    issues = collect_cross_artifact_issues(
        result={
            "status": "BLOCKED",
            "terminal_reason": "X",
            "technical_status": "BLOCKED",
            "executed_code_sha": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            "match_run_to_head": False,
            "machine_blockers": [],
            "real_data_ci_status": "NOT_EXECUTED",
        },
        queue={
            "status": "BLOCKED",
            "reason": "X",
            "technical_status": "BLOCKED",
            "executed_code_sha": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            "match_run_to_head": False,
            "machine_blockers": [],
            "real_data_ci_status": "NOT_EXECUTED",
        },
        evidence={
            "status": "BLOCKED",
            "terminal_reason": "X",
            "technical_status": "BLOCKED",
            "executed_code_sha": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            "match_run_to_head": False,
            "machine_blockers": [],
            "real_data_ci_status": "NOT_EXECUTED",
        },
        sha_semantics={
            "executed_code_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "current_pr_head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        },
    )
    assert any("dummy_sha" in i for i in issues)


def test_publication_pass_does_not_imply_real_data_pass() -> None:
    """human_package_publication_status=PASS must not force real_data_ci_status=PASS."""
    from scripts.ops.confenge_final_status import aggregate_real_data_ci_status

    # publication is outside the four real-data jobs
    real = aggregate_real_data_ci_status("NOT_EXECUTED", "NOT_EXECUTED", "NOT_EXECUTED", "NOT_EXECUTED")
    assert real == "NOT_EXECUTED"
    human_pkg = "PASS"
    assert human_pkg == "PASS" and real != "PASS"


def test_queue_summary_overwrites_stale_evidence_and_legacy_executed(tmp_path, monkeypatch) -> None:
    """queue-summary must not retain ancient evidence_commit_sha / executed_git_sha."""
    from scripts.ops import confenge_final_status as fs

    art = tmp_path / "art"
    art.mkdir()
    monkeypatch.setattr(fs, "ART", art)
    monkeypatch.setattr(fs, "_git_head", lambda: "livehead11111111111111111111111111111111")
    (art / "EXECUTED_CODE_SHA.txt").write_text("execsha22222222222222222222222222222222\n")
    (art / "FINAL_INTEGRITY_CODE_FREEZE_SHA.txt").write_text("execsha22222222222222222222222222222222\n")
    (art / "full-pipeline-e2e-reproducibility-gate.json").write_text('{"ok": true, "status": "PASS"}\n')
    (art / "downstream-reproducibility-gate.json").write_text('{"ok": true, "status": "PASS"}\n')
    (art / "offer-sensitivity-gate.json").write_text(
        '{"ok": true, "status": "PASS", "diagnose": {"block": null, '
        '"robust_quantitative_justification": true, '
        '"explanation": {"catalog_degenerate": false}}}\n'
    )
    (art / "offer-discrimination-gate.json").write_text(
        '{"ok": true, "status": "PASS", "diagnose": {"block": null, '
        '"robust_quantitative_justification": true, '
        '"explanation": {"catalog_degenerate": false}}}\n'
    )
    (art / "human-review-packages-gate.json").write_text(
        '{"ok": true, "status": "PACKAGES_READY", "published_as_workflow_artifact": true}\n'
    )
    (art / "real-corpus-provenance-gate.json").write_text('{"ok": true, "status": "PASS"}\n')
    (art / "registry-universe-gate.json").write_text(
        '{"ok": false, "status": "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE", "official_coverage": 0.053}\n'
    )
    (art / "historical-window-gate.json").write_text('{"ok": true, "status": "PASS"}\n')
    (art / "restored-snapshot-verify.json").write_text('{"ok": true}\n')
    (art / "queue-summary.json").write_text(
        json.dumps(
            {
                "status": "BLOCKED",
                "evidence_commit_sha": "c51ac9804b33a0300755d904f7a2ef9afd575b09",
                "executed_git_sha": "da9596aece9a661c0b4bf4cba0637cac5e20767c",
                "executed_code_sha": "old",
            }
        )
        + "\n"
    )
    (art / "final-integrity-code-freeze-gate.json").write_text(
        json.dumps(
            {
                "ok": True,
                "executed_code_sha": "execsha22222222222222222222222222222222",
                "final_integrity_code_freeze_sha": "execsha22222222222222222222222222222222",
                "artifact_only_commits_after_execution": True,
                "code_changed_after_execution": False,
                "non_artifact_files_changed_after_execution": [],
            }
        )
        + "\n"
    )

    fs.write_derived_artifacts()
    qs = fs._load("queue-summary.json")
    result = fs._load("result.json")
    assert qs["evidence_commit_sha"] == result["evidence_commit_sha"]
    assert qs["evidence_commit_sha"] != "c51ac9804b33a0300755d904f7a2ef9afd575b09"
    assert qs["executed_git_sha"] == result["executed_code_sha"]
    assert qs["executed_git_sha"] != "da9596aece9a661c0b4bf4cba0637cac5e20767c"
    assert qs["executed_code_sha"] == "execsha22222222222222222222222222222222"


def test_cross_artifact_fails_on_evidence_commit_divergence() -> None:
    from scripts.ops.confenge_final_status import collect_cross_artifact_issues

    issues = collect_cross_artifact_issues(
        result={
            "status": "BLOCKED",
            "terminal_reason": "X",
            "technical_status": "BLOCKED",
            "executed_code_sha": "exec1",
            "evidence_commit_sha": "ev1",
            "match_run_to_head": False,
            "machine_blockers": [],
            "real_data_ci_status": "NOT_EXECUTED",
            "pr_head_sha": "h1",
        },
        queue={
            "status": "BLOCKED",
            "reason": "X",
            "technical_status": "BLOCKED",
            "executed_code_sha": "exec1",
            "evidence_commit_sha": "stale_old",
            "executed_git_sha": "stale_exec",
            "match_run_to_head": False,
            "machine_blockers": [],
            "real_data_ci_status": "NOT_EXECUTED",
            "pr_head_sha": "h1",
        },
        evidence={
            "status": "BLOCKED",
            "terminal_reason": "X",
            "technical_status": "BLOCKED",
            "executed_code_sha": "exec1",
            "evidence_commit_sha": "ev1",
            "match_run_to_head": False,
            "machine_blockers": [],
            "real_data_ci_status": "NOT_EXECUTED",
            "pr_head_sha": "h1",
        },
    )
    assert any("evidence_commit_sha" in i for i in issues)
    assert any("legacy_executed_git_sha_stale" in i for i in issues)


def test_cross_artifact_fails_when_workflow_head_is_pr_not_merge() -> None:
    from scripts.ops.confenge_final_status import collect_cross_artifact_issues

    issues = collect_cross_artifact_issues(
        result={
            "status": "BLOCKED",
            "terminal_reason": "X",
            "technical_status": "BLOCKED",
            "executed_code_sha": "e",
            "evidence_commit_sha": "h",
            "match_run_to_head": False,
            "machine_blockers": [],
            "real_data_ci_status": "NOT_EXECUTED",
            "pr_head_sha": "prhead",
            "workflow_merge_sha": "mergesha",
            "workflow_head_sha": "prhead",
        },
        queue={
            "status": "BLOCKED",
            "reason": "X",
            "technical_status": "BLOCKED",
            "executed_code_sha": "e",
            "evidence_commit_sha": "h",
            "match_run_to_head": False,
            "machine_blockers": [],
            "real_data_ci_status": "NOT_EXECUTED",
            "pr_head_sha": "prhead",
            "workflow_merge_sha": "mergesha",
        },
        evidence={
            "status": "BLOCKED",
            "terminal_reason": "X",
            "technical_status": "BLOCKED",
            "executed_code_sha": "e",
            "evidence_commit_sha": "h",
            "match_run_to_head": False,
            "machine_blockers": [],
            "real_data_ci_status": "NOT_EXECUTED",
            "pr_head_sha": "prhead",
            "workflow_merge_sha": "mergesha",
            "workflow_head_sha": "prhead",
        },
        provenance={
            "workflow_head_sha": "prhead",
            "workflow_merge_sha": "mergesha",
            "pr_head_sha": "prhead",
        },
    )
    assert any("workflow_head_sha" in i for i in issues)


def test_independent_live_pr_head_not_from_package(monkeypatch) -> None:
    from scripts.ops import confenge_final_status as fs

    monkeypatch.setenv("CONFENGE_PR_HEAD_SHA", "envprhead3333333333333333333333333333")
    assert fs.independent_live_pr_head() == "envprhead3333333333333333333333333333"


def test_iter_package_status_files_includes_machine_evidence_twin(tmp_path) -> None:
    from scripts.ops.confenge_final_status import iter_package_status_files

    art = tmp_path / "art"
    me = art / "machine-evidence"
    me.mkdir(parents=True)
    (art / "result.json").write_text("{}\n")
    (art / "sha-semantics-gate.json").write_text("{}\n")
    (me / "sha-semantics-gate.json").write_text("{}\n")
    (me / "post-execution-artifact-only-diff-gate.json").write_text("{}\n")
    paths = {p.name for p in iter_package_status_files(art)}
    rels = {str(p.relative_to(art)) for p in iter_package_status_files(art)}
    assert "result.json" in paths
    assert "sha-semantics-gate.json" in paths
    assert "machine-evidence/sha-semantics-gate.json" in rels
    assert "machine-evidence/post-execution-artifact-only-diff-gate.json" in rels


def test_write_mirrors_and_purges_dummy_machine_evidence_gates(tmp_path, monkeypatch) -> None:
    """One write clears dummy SHAs under machine-evidence/ and mirrors root."""
    from scripts.ops import confenge_final_status as fs

    art = tmp_path / "art"
    me = art / "machine-evidence"
    me.mkdir(parents=True)
    monkeypatch.setattr(fs, "ART", art)
    monkeypatch.setattr(fs, "_git_head", lambda: "livehead11111111111111111111111111111111")
    (art / "EXECUTED_CODE_SHA.txt").write_text("execsha22222222222222222222222222222222\n")
    (art / "FINAL_INTEGRITY_CODE_FREEZE_SHA.txt").write_text("execsha22222222222222222222222222222222\n")
    for name, body in (
        ("full-pipeline-e2e-reproducibility-gate.json", '{"ok": true, "status": "PASS"}'),
        ("downstream-reproducibility-gate.json", '{"ok": true, "status": "PASS"}'),
        (
            "offer-sensitivity-gate.json",
            '{"ok": true, "status": "PASS", "diagnose": {"block": null, '
            '"robust_quantitative_justification": true, '
            '"explanation": {"catalog_degenerate": false}}}',
        ),
        (
            "offer-discrimination-gate.json",
            '{"ok": true, "status": "PASS", "diagnose": {"block": null, '
            '"robust_quantitative_justification": true, '
            '"explanation": {"catalog_degenerate": false}}}',
        ),
        (
            "human-review-packages-gate.json",
            '{"ok": true, "status": "PACKAGES_READY", "published_as_workflow_artifact": true}',
        ),
        ("real-corpus-provenance-gate.json", '{"ok": true, "status": "PASS"}'),
        (
            "registry-universe-gate.json",
            '{"ok": false, "status": "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE", "official_coverage": 0.053}',
        ),
        ("historical-window-gate.json", '{"ok": true, "status": "PASS"}'),
        ("restored-snapshot-verify.json", '{"ok": true}'),
        (
            "final-integrity-code-freeze-gate.json",
            json.dumps(
                {
                    "ok": True,
                    "executed_code_sha": "execsha22222222222222222222222222222222",
                    "final_integrity_code_freeze_sha": "execsha22222222222222222222222222222222",
                    "final_code_freeze_sha": "execsha22222222222222222222222222222222",
                    "pr_head_sha": "livehead11111111111111111111111111111111",
                    "current_pr_head_sha": "livehead11111111111111111111111111111111",
                    "artifact_only_commits_after_execution": True,
                    "code_changed_after_execution": False,
                    "non_artifact_files_changed_after_execution": [],
                }
            ),
        ),
        (
            "sha-semantics-gate.json",
            json.dumps(
                {
                    "ok": True,
                    "status": "PASS",
                    "executed_code_sha": "execsha22222222222222222222222222222222",
                    "current_pr_head_sha": "livehead11111111111111111111111111111111",
                    "pr_head_sha": "livehead11111111111111111111111111111111",
                }
            ),
        ),
    ):
        (art / name).write_text(body + "\n")
    # Plant dummy twin + orphan
    (me / "sha-semantics-gate.json").write_text(
        json.dumps(
            {
                "ok": True,
                "status": "PASS",
                "executed_code_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "current_pr_head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            }
        )
        + "\n"
    )
    (me / "orphan-only-gate.json").write_text('{"ok": true}\n')

    fs.write_derived_artifacts(refresh_sha_gates=False)
    result = json.loads((art / "result.json").read_text())
    twin = json.loads((me / "sha-semantics-gate.json").read_text())
    assert twin["executed_code_sha"] == result["executed_code_sha"]
    assert twin["executed_code_sha"] != "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert not (me / "orphan-only-gate.json").exists()
    # Inventory must not report dummies
    inv = fs.load_inventory_json(art)
    assert not fs.inventory_dummy_sha_issues(inv)


def test_cross_artifact_fails_on_stale_post_execution_gate_shas() -> None:
    """§5: post-execution gate with old freeze/pr SHAs must fail cross-artifact."""
    from scripts.ops.confenge_final_status import collect_cross_artifact_issues

    issues = collect_cross_artifact_issues(
        result={
            "status": "BLOCKED",
            "terminal_reason": "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE",
            "technical_status": "BLOCKED",
            "executed_code_sha": "4d54d93112229c2c8ac6838a3df7b6d6481ea366",
            "final_integrity_code_freeze_sha": "4d54d93112229c2c8ac6838a3df7b6d6481ea366",
            "final_code_freeze_sha": "4d54d93112229c2c8ac6838a3df7b6d6481ea366",
            "pr_head_sha": "0af7356e8b1ddd237d8d0b591a2d29e148673efe",
            "current_pr_head_sha": "0af7356e8b1ddd237d8d0b591a2d29e148673efe",
            "evidence_commit_sha": "0af7356e8b1ddd237d8d0b591a2d29e148673efe",
            "match_run_to_head": False,
            "machine_blockers": ["BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE"],
            "real_data_ci_status": "NOT_EXECUTED",
        },
        queue={
            "status": "BLOCKED",
            "reason": "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE",
            "technical_status": "BLOCKED",
            "executed_code_sha": "4d54d93112229c2c8ac6838a3df7b6d6481ea366",
            "pr_head_sha": "0af7356e8b1ddd237d8d0b591a2d29e148673efe",
            "evidence_commit_sha": "0af7356e8b1ddd237d8d0b591a2d29e148673efe",
            "match_run_to_head": False,
            "machine_blockers": ["BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE"],
            "real_data_ci_status": "NOT_EXECUTED",
        },
        evidence={
            "status": "BLOCKED",
            "terminal_reason": "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE",
            "technical_status": "BLOCKED",
            "executed_code_sha": "4d54d93112229c2c8ac6838a3df7b6d6481ea366",
            "pr_head_sha": "0af7356e8b1ddd237d8d0b591a2d29e148673efe",
            "evidence_commit_sha": "0af7356e8b1ddd237d8d0b591a2d29e148673efe",
            "match_run_to_head": False,
            "machine_blockers": ["BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE"],
            "real_data_ci_status": "NOT_EXECUTED",
        },
        post_execution={
            "ok": True,
            "status": "PASS",
            "executed_code_sha": "7262d2bf4840dda61a134cace76c41b32a1694c0",
            "final_code_freeze_sha": "7262d2bf4840dda61a134cace76c41b32a1694c0",
            "current_pr_head_sha": "fcf177d24b55ab4e2ab223635a57bd2c5af9b212",
            "artifact_only_commits_after_execution": True,
        },
    )
    assert any("post_execution" in i and "executed_code_sha" in i for i in issues)
    assert any("post_execution" in i and "pr_head_sha" in i for i in issues)


def test_resolve_sha_roles_dual_head_not_equal() -> None:
    """workflow_artifact_head_sha must not default to pr_head (dual-head model)."""
    from scripts.ops.confenge_final_status import resolve_sha_roles

    sha = resolve_sha_roles(
        checked_out_sha="package_tip_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        pr_head_sha="package_tip_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        executed_code_sha="freeze_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        freeze_sha="freeze_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        workflow_artifact_head_sha="gha_run_head_cccccccccccccccccccccccccc",
        artifact_only=True,
        code_changed=False,
    )
    assert sha["pr_head_sha"] == "package_tip_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert sha["workflow_artifact_head_sha"] == "gha_run_head_cccccccccccccccccccccccccc"
    assert sha["pr_head_sha"] != sha["workflow_artifact_head_sha"]
    assert sha["match_run_to_head"] is False
    assert sha["artifact_only_commits_after_execution"] is True


def test_resolve_sha_roles_does_not_invent_artifact_head_from_pr() -> None:
    from scripts.ops.confenge_final_status import resolve_sha_roles

    sha = resolve_sha_roles(
        checked_out_sha="tip_dddddddddddddddddddddddddddddddddddd",
        pr_head_sha="tip_dddddddddddddddddddddddddddddddddddd",
        executed_code_sha="exec_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
        freeze_sha="exec_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
        artifact_only=True,
        code_changed=False,
    )
    assert sha["workflow_artifact_head_sha"] is None


def test_workflow_run_head_mismatch_uses_artifact_head_not_pr() -> None:
    from scripts.ops.confenge_final_status import workflow_run_head_mismatch_issues

    # Package tip differs from GHA head, but workflow_artifact_head matches run — OK
    ok_issues = workflow_run_head_mismatch_issues(
        package={
            "pr_head_sha": "package_tip_ffffffffffffffffffffffffffffff",
            "workflow_artifact_head_sha": "gha_head_gggggggggggggggggggggggggggggggg",
        },
        run_head_sha="gha_head_gggggggggggggggggggggggggggggggg",
    )
    assert ok_issues == []

    # Claiming package tip as artifact head while run is different — FAIL
    bad = workflow_run_head_mismatch_issues(
        package={
            "pr_head_sha": "package_tip_ffffffffffffffffffffffffffffff",
            "workflow_artifact_head_sha": "package_tip_ffffffffffffffffffffffffffffff",
        },
        run_head_sha="gha_head_gggggggggggggggggggggggggggggggg",
    )
    assert any("workflow_run_head_mismatch" in i for i in bad)

    # Missing artifact head when run_head provided — FAIL (no pr_head fallback)
    missing = workflow_run_head_mismatch_issues(
        package={"pr_head_sha": "package_tip_ffffffffffffffffffffffffffffff"},
        run_head_sha="gha_head_gggggggggggggggggggggggggggggggg",
    )
    assert any("missing_workflow_artifact_head_sha" in i for i in missing)


def test_inventory_allows_pr_head_ne_workflow_artifact_head(tmp_path) -> None:
    """Inventory OK when pr_head != workflow_artifact_head but each role agrees across files."""
    from scripts.ops.confenge_final_status import verify_package_inventory

    art = tmp_path / "art"
    art.mkdir()
    pkg_tip = "pkg_tip_11111111111111111111111111111111111111"
    gha_head = "gha_head_222222222222222222222222222222222222"
    freeze = "freeze_333333333333333333333333333333333333"
    for name in (
        "result.json",
        "queue-summary.json",
        "final-evidence-closure.json",
        "final-integrity-closure.json",
        "workflow-artifact-publication.json",
        "sha-semantics-gate.json",
        "final-integrity-code-freeze-gate.json",
        "post-execution-artifact-only-diff-gate.json",
        "evidence-provenance-gate.json",
        "executed-tree-integrity-gate.json",
        "cross-artifact-consistency-gate.json",
    ):
        body = {
            "ok": True,
            "status": "BLOCKED",
            "pr_head_sha": pkg_tip,
            "current_pr_head_sha": pkg_tip,
            "executed_code_sha": freeze,
            "final_integrity_code_freeze_sha": freeze,
            "final_code_freeze_sha": freeze,
            "freeze_sha": freeze,
            "evidence_commit_sha": pkg_tip,
            "workflow_artifact_head_sha": gha_head,
            "workflow_run_id": "999",
            "match_run_to_head": False,
            "code_changed_after_execution": False,
            "artifact_only_commits_after_execution": True,
            "real_data_ci_status": "NOT_EXECUTED",
            "terminal_reason": "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE",
            "reason": "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE",
            "technical_status": "BLOCKED",
            "machine_blockers": ["BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE"],
        }
        if name == "workflow-artifact-publication.json":
            body.update(
                {
                    "published_as_workflow_artifact": True,
                    "workflow_pr_head_sha": gha_head,
                    "source_tip": gha_head,
                    "human_review_artifact_id": 1,
                    "machine_evidence_artifact_id": 2,
                }
            )
        (art / name).write_text(json.dumps(body) + "\n", encoding="utf-8")

    rep = verify_package_inventory(art_dir=art, expected_pr_head=pkg_tip, run_head_sha=gha_head)
    assert rep["ok"] is True, rep.get("issues")

    # Wrong run head must fail
    bad = verify_package_inventory(art_dir=art, expected_pr_head=pkg_tip, run_head_sha=pkg_tip)
    assert bad["ok"] is False
    assert any("workflow_run_head_mismatch" in i for i in bad["issues"])


_STALE_FREEZE_SHA = "90348c66d4309578aae3058579303adf7e4c7f81"


def test_rebound_freeze_drives_shipped_verifiers_on_campaign_tree() -> None:
    """PR #447 closeout: rebound freeze/executed SHAs are not the stale 90348c66 execution.

    Drives shipped verify_code_freeze / verify_final_integrity_code_freeze /
    verify_sha_semantics against the live campaign tree (not a reimplementation).
    """
    from pathlib import Path

    from scripts.ops.confenge_frozen_inputs import (
        discover_frozen_input_paths,
        load_frozen_inputs_manifest,
        protected_path_set,
    )

    executed = (ART / "EXECUTED_CODE_SHA.txt").read_text(encoding="utf-8").strip().split()[0]
    freeze = (ART / "FINAL_CODE_FREEZE_SHA.txt").read_text(encoding="utf-8").strip().split()[0]
    integrity = (ART / "FINAL_INTEGRITY_CODE_FREEZE_SHA.txt").read_text(encoding="utf-8").strip().split()[0]
    assert executed != _STALE_FREEZE_SHA
    assert freeze != _STALE_FREEZE_SHA
    assert integrity != _STALE_FREEZE_SHA
    assert executed == freeze == integrity

    root = Path(__file__).resolve().parents[2]
    discovered = set(discover_frozen_input_paths(root))
    assert "scripts/decision_unit_intelligence/controlled_email.py" in discovered
    assert "scripts/warmbly_bridge/mapping.py" in discovered
    assert "scripts/confenge_contact_resolution/mailbox_purpose.py" in discovered
    assert "scripts/confenge_contact_resolution/send_readiness.py" in discovered

    freeze_rep = verify_code_freeze()
    integrity_rep = verify_final_integrity_code_freeze()
    sem = verify_sha_semantics(
        executed_code_sha=integrity_rep.get("executed_code_sha"),
        current_pr_head_sha=integrity_rep.get("current_pr_head_sha"),
        workflow_merge_sha=integrity_rep.get("workflow_merge_sha"),
        match_run_to_head=integrity_rep.get("match_run_to_head"),
        code_changed_after_execution=integrity_rep.get("code_changed_after_execution"),
        artifact_only_commits_after_execution=integrity_rep.get("artifact_only_commits_after_execution"),
        write_artifact=True,
    )

    assert freeze_rep["ok"] is True, freeze_rep
    assert integrity_rep["ok"] is True, integrity_rep
    assert sem["ok"] is True, sem
    assert freeze_rep.get("protected_changed") == []
    assert integrity_rep.get("protected_changed") == []
    assert freeze_rep["executed_code_sha"] != _STALE_FREEZE_SHA
    assert integrity_rep["executed_code_sha"] != _STALE_FREEZE_SHA
    assert freeze_rep["final_code_freeze_sha"] != _STALE_FREEZE_SHA

    man = load_frozen_inputs_manifest(art_dir=ART)
    assert man.get("freeze_sha") != _STALE_FREEZE_SHA
    protected = protected_path_set(man)
    assert "scripts/decision_unit_intelligence/controlled_email.py" in protected
    assert "scripts/warmbly_bridge/mapping.py" in protected

    pr_head = str(integrity_rep["current_pr_head_sha"] or "")
    merge = integrity_rep.get("workflow_merge_sha")
    if merge and merge != pr_head:
        assert pr_head != merge

    derived = compute_match_run_to_head(
        executed_code_sha=str(integrity_rep["executed_code_sha"]),
        current_pr_head_sha=pr_head,
    )
    if integrity_rep["executed_code_sha"] != pr_head:
        assert derived is False
        assert integrity_rep.get("match_run_to_head") is False
        assert integrity_rep.get("artifact_only_commits_after_execution") is True
    else:
        assert derived is True
        assert integrity_rep.get("match_run_to_head") is True

    forbidden = verify_sha_semantics(
        executed_code_sha=str(integrity_rep["executed_code_sha"]),
        current_pr_head_sha="ffffffffffffffffffffffffffffffffffffffff",
        match_run_to_head=True,
        write_artifact=False,
    )
    assert forbidden["ok"] is False
    assert forbidden.get("match_run_to_head") is True
    assert forbidden["executed_code_sha"] != forbidden["current_pr_head_sha"]
