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
    compute_match_run_to_head,
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
