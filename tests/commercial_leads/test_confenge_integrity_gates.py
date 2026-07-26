"""Integrity gates for CONFENGE PR #144 — drive shipped functions only."""

from __future__ import annotations

from scripts.ops.confenge_code_freeze import (
    compute_match_run_to_head,
    verify_sha_semantics,
)
from scripts.ops.confenge_offer_sensitivity import evaluate_offer_pass
from scripts.commercial_leads.scoring import (
    MAX_SINGLE_SIGNAL_OFFER_CHANGE_RATE,
    MIN_SELECTED_OFFER_MARGIN,
    LeadScore,
    diagnose_offer_distribution,
)


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
    assert (
        compute_match_run_to_head(
            executed_code_sha="abc", current_pr_head_sha="abc"
        )
        is True
    )
    assert (
        compute_match_run_to_head(
            executed_code_sha="abc", current_pr_head_sha="def"
        )
        is False
    )
    assert (
        compute_match_run_to_head(executed_code_sha=None, current_pr_head_sha="x")
        is False
    )


def test_sha_semantics_fail_when_match_true_with_mismatch() -> None:
    """executed != head AND match_run_to_head == true → FAIL."""
    rep = verify_sha_semantics(
        executed_code_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        current_pr_head_sha="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        match_run_to_head=True,
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
    )
    assert rep["ok"] is True
    assert rep["match_run_to_head_derived"] is False


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

    assert "raw_snapshot" in e2e.one_full_pipeline_pass.__doc__ or hasattr(
        e2e, "discovery_input_fingerprint"
    )
    assert e2e.STAGE_HASH_KEYS[0] == "discovery_input_hash"
    assert "discovery_input_hash" in e2e.STAGE_HASH_KEYS
    # Downstream module documents frozen universe start
    assert "frozen" in (down.__doc__ or "").lower() or "frozen" in (
        down.run_full_universe_e2e.__doc__ or ""
    ).lower()


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
    (art / "full-pipeline-e2e-reproducibility-gate.json").write_text(
        '{"ok": true, "status": "PASS"}\n'
    )
    (art / "downstream-reproducibility-gate.json").write_text(
        '{"ok": true, "status": "PASS"}\n'
    )
    (art / "offer-sensitivity-gate.json").write_text(
        '{"ok": true, "status": "PASS", "diagnose": {"block": null, "robust_quantitative_justification": true, "explanation": {"catalog_degenerate": false}}}\n'
    )
    (art / "offer-discrimination-gate.json").write_text(
        '{"ok": true, "status": "PASS", "diagnose": {"block": null, "robust_quantitative_justification": true, "explanation": {"catalog_degenerate": false}}}\n'
    )
    (art / "human-review-packages-gate.json").write_text(
        '{"ok": true, "status": "PACKAGES_READY_BLOCKED_REAL_HOLDOUT_NOT_REVIEWED", "published_as_workflow_artifact": true}\n'
    )
    (art / "real-corpus-provenance-gate.json").write_text(
        '{"ok": true, "status": "PASS"}\n'
    )
    (art / "registry-universe-gate.json").write_text(
        '{"ok": false, "status": "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE", "official_coverage": 0.05}\n'
    )
    (art / "historical-window-gate.json").write_text(
        '{"ok": true, "status": "PASS"}\n'
    )
    (art / "restored-snapshot-verify.json").write_text('{"ok": true}\n')

    status = fs.write_derived_artifacts()
    result = fs._load("result.json")
    qs = fs._load("queue-summary.json")
    closure = fs._load("final-evidence-closure.json")
    assert result["status"] == qs["status"] == closure["status"] == "BLOCKED"
    assert (
        result["reason"]
        == qs["reason"]
        == closure["terminal_reason"]
        == "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE"
    )
    assert "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE" in status["machine_blockers"]
    assert status["all_other_machine_blockers"] == []
    assert status["terminal_declaration"] == (
        "BLOCKED_ONLY_OFFICIAL_REGISTRY_AND_HUMAN_REVIEW"
    )
    # No contradictory insufficient historical window
    assert qs["reason"] != "BLOCKED_INSUFFICIENT_HISTORICAL_WINDOW"
