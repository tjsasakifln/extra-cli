import pytest

from scripts.cto.decision import DecisionValidationError, validate_decision
from scripts.cto.paths import repo_root


def test_valid_execute(sample_decision):
    out = validate_decision(sample_decision, root=repo_root())
    assert out["decision"] == "EXECUTE"


def test_execute_requires_criteria(sample_decision):
    sample_decision["acceptance_criteria"] = []
    with pytest.raises(DecisionValidationError):
        validate_decision(sample_decision, root=repo_root())


def test_execute_requires_paths(sample_decision):
    sample_decision["allowed_paths"] = []
    with pytest.raises(DecisionValidationError):
        validate_decision(sample_decision, root=repo_root())


def test_execute_requires_traceability(sample_decision):
    sample_decision["issue_number"] = None
    sample_decision["work_id"] = None
    with pytest.raises(DecisionValidationError):
        validate_decision(sample_decision, root=repo_root())


def test_invalid_decision_enum(sample_decision):
    sample_decision["decision"] = "HACK"
    with pytest.raises(DecisionValidationError):
        validate_decision(sample_decision, root=repo_root())


def test_dangerous_merge_in_objective(sample_decision):
    sample_decision["objective"] = "Please merge to main and deploy production"
    sample_decision["forbidden_actions"] = []  # empty so detector fires
    with pytest.raises(DecisionValidationError):
        validate_decision(sample_decision, root=repo_root())


def test_human_gate_requires_escalate(sample_decision):
    sample_decision["human_gate"] = {"required": True, "reason": "need Tiago"}
    with pytest.raises(DecisionValidationError):
        validate_decision(sample_decision, root=repo_root())


def test_noop_ok():
    d = {
        "schema_version": "1.0",
        "decision_id": "d1",
        "cycle_id": "c1",
        "decision": "NOOP",
        "objective": "nothing",
        "issue_number": None,
        "work_id": None,
        "candidate_id": None,
        "strategic_reason": "no unblocked work",
        "acceptance_criteria": [],
        "required_evidence": [],
        "allowed_paths": [],
        "forbidden_paths": [],
        "test_commands": [],
        "forbidden_actions": ["merge"],
        "allowed_claims": [],
        "forbidden_claims": ["LOCAL_READY"],
        "max_repair_attempts": 0,
        "estimated_risk": "LOW",
        "confidence": 1.0,
        "human_gate": {"required": False, "reason": None},
    }
    assert validate_decision(d, root=repo_root())["decision"] == "NOOP"
