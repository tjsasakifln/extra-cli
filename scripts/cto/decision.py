"""CTO decision validation and DeepSeek decide/review orchestration."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.cto.config import CTOConfig, load_config
from scripts.cto.deepseek_client import (
    DeepSeekClient,
    DeepSeekInvalidResponse,
    DeepSeekUnavailable,
)
from scripts.cto.paths import (
    cto_dir,
    decision_path,
    decision_schema_path,
    review_schema_path,
)
from scripts.cto.policies import (
    decision_authorizes_human_only,
    forbidden_claims,
)
from scripts.cto.redaction import redact_obj


class DecisionValidationError(ValueError):
    """Decision failed closed validation."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _check_required(data: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in schema.get("required") or []:
        if key not in data:
            errors.append(f"missing required field: {key}")
    return errors


def _check_enum(data: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    props = schema.get("properties") or {}
    for key, prop in props.items():
        if key not in data or data[key] is None:
            continue
        if "enum" in prop and data[key] not in prop["enum"]:
            errors.append(f"{key}={data[key]!r} not in {prop['enum']}")
        if prop.get("type") == "string" and prop.get("const") is not None:
            if data[key] != prop["const"]:
                errors.append(f"{key} must be {prop['const']!r}")
        if prop.get("type") == "number":
            try:
                v = float(data[key])
            except (TypeError, ValueError):
                errors.append(f"{key} must be number")
                continue
            if "minimum" in prop and v < prop["minimum"]:
                errors.append(f"{key} below minimum")
            if "maximum" in prop and v > prop["maximum"]:
                errors.append(f"{key} above maximum")
        if prop.get("type") == "integer":
            if not isinstance(data[key], int) or isinstance(data[key], bool):
                errors.append(f"{key} must be integer")
            else:
                if "minimum" in prop and data[key] < prop["minimum"]:
                    errors.append(f"{key} below minimum")
                if "maximum" in prop and data[key] > prop["maximum"]:
                    errors.append(f"{key} above maximum")
        if prop.get("type") == "array" and not isinstance(data[key], list):
            errors.append(f"{key} must be array")
    return errors


def validate_against_schema(data: dict[str, Any], schema: dict[str, Any]) -> None:
    errors = _check_required(data, schema) + _check_enum(data, schema)
    if schema.get("additionalProperties") is False:
        allowed = set((schema.get("properties") or {}).keys())
        extra = set(data.keys()) - allowed
        if extra:
            errors.append(f"additional properties not allowed: {sorted(extra)}")
    if errors:
        raise DecisionValidationError("; ".join(errors))


def validate_decision(
    decision: dict[str, Any],
    *,
    root: Path | None = None,
    policies: dict[str, Any] | None = None,
    min_confidence: float = 0.0,
) -> dict[str, Any]:
    """Validate decision schema + business fail-closed rules."""
    schema = load_schema(decision_schema_path(root))
    validate_against_schema(decision, schema)

    action = decision["decision"]
    if action in {"EXECUTE", "REPAIR"}:
        if not decision.get("acceptance_criteria"):
            raise DecisionValidationError("EXECUTE/REPAIR requires acceptance_criteria")
        if not decision.get("allowed_paths"):
            raise DecisionValidationError("EXECUTE/REPAIR requires non-empty allowed_paths")
        if not decision.get("issue_number") and not decision.get("work_id"):
            raise DecisionValidationError(
                "EXECUTE/REPAIR requires issue_number or work_id for traceability"
            )

    if action == "ACCEPT" and not (
        decision.get("issue_number") or decision.get("work_id") or decision.get("candidate_id")
    ):
        raise DecisionValidationError("ACCEPT requires trackable issue/work/candidate")

    # Always inject policy forbidden claims if empty
    if not decision.get("forbidden_claims"):
        decision = {**decision, "forbidden_claims": forbidden_claims(policies)}

    violations = decision_authorizes_human_only(decision, policies)
    if violations:
        raise DecisionValidationError("policy violation: " + "; ".join(violations))

    if float(decision.get("confidence") or 0) < min_confidence and action in {
        "EXECUTE",
        "REPAIR",
        "ACCEPT",
    }:
        raise DecisionValidationError(
            f"confidence {decision.get('confidence')} below min {min_confidence}"
        )

    hg = decision.get("human_gate") or {}
    if hg.get("required") and action not in {"ESCALATE", "BLOCK", "NOOP"}:
        # Force escalate path
        raise DecisionValidationError(
            "human_gate.required=true requires decision ESCALATE/BLOCK/NOOP"
        )

    return decision


def validate_review(review: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    schema = load_schema(review_schema_path(root))
    validate_against_schema(review, schema)
    if review["verdict"] not in {"ACCEPT", "REPAIR", "ROLLBACK", "BLOCK", "ESCALATE"}:
        raise DecisionValidationError("invalid review verdict")
    return review


def _read_prompt(name: str, root: Path | None = None) -> str:
    path = cto_dir(root) / "prompts" / name
    return path.read_text(encoding="utf-8")


def build_fallback_blocked_decision(
    *,
    cycle_id: str,
    reason: str,
    observation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """When DeepSeek unavailable — do not invent work."""
    return {
        "schema_version": "1.0",
        "decision_id": f"dec-blocked-{uuid.uuid4().hex[:12]}",
        "cycle_id": cycle_id,
        "decision": "BLOCK",
        "objective": "Preserve state; CTO unavailable",
        "issue_number": None,
        "work_id": None,
        "candidate_id": None,
        "strategic_reason": f"BLOCKED_CTO_UNAVAILABLE: {reason}",
        "acceptance_criteria": [],
        "required_evidence": [],
        "allowed_paths": [],
        "forbidden_paths": [".env", "**/.ssh/**"],
        "test_commands": [],
        "forbidden_actions": [
            "merge",
            "deploy",
            "force_push",
            "git push",
        ],
        "allowed_claims": [],
        "forbidden_claims": forbidden_claims(),
        "max_repair_attempts": 0,
        "estimated_risk": "HIGH",
        "confidence": 1.0,
        "human_gate": {
            "required": True,
            "reason": "DeepSeek CTO unavailable — deterministic checks only",
        },
        "ranking_veto": None,
        "_meta": {
            "created_at": _utc_now(),
            "fallback": True,
            "observation_keys": sorted((observation or {}).keys())[:20],
        },
    }


def decide_from_observation(
    observation: dict[str, Any],
    *,
    config: CTOConfig | None = None,
    client: DeepSeekClient | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Produce a validated CTO decision from observation JSON."""
    cfg = config or load_config()
    cycle_id = (
        (observation.get("cycle") or {}).get("cycle_id")
        or f"cyc-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )

    if dry_run and client is None:
        # Deterministic dry-run: prefer ready Issues, then work registry, then ranker
        ranking = observation.get("ranking") or {}
        top = (ranking.get("top") or [None])[0]
        issues = observation.get("issues") or {}
        ready = (issues.get("by_state") or {}).get("state:ready") or []
        issue_number = None
        work_id = None
        if ready:
            issue_number = ready[0].get("number")
            work_id = ready[0].get("work_id")
        if not work_id:
            reg = observation.get("work_registry") or {}
            ids = reg.get("ids") or []
            if ids:
                work_id = ids[0]
        if not work_id and top:
            work_id = (top or {}).get("id")
        has_work = bool(work_id or issue_number)
        decision = {
            "schema_version": "1.0",
            "decision_id": f"dec-dry-{uuid.uuid4().hex[:12]}",
            "cycle_id": cycle_id,
            "decision": "EXECUTE" if has_work else "NOOP",
            "objective": (
                f"Dry-run candidate: {work_id or issue_number or 'none'}"
            ),
            "issue_number": issue_number,
            "work_id": work_id,
            "candidate_id": (top or {}).get("id"),
            "strategic_reason": "Dry-run deterministic decision without DeepSeek call",
            "acceptance_criteria": [
                "No remote mutations",
                "Decision schema valid",
            ],
            "required_evidence": ["decision.json", "observation.json"],
            "allowed_paths": ["scripts/cto/**", "docs/ops/cto-autopilot/**", "tests/cto/**"],
            "forbidden_paths": [".env", "**/.ssh/**"],
            "test_commands": ["python -m pytest tests/cto -q"],
            "forbidden_actions": ["merge", "deploy", "git push", "force_push"],
            "allowed_claims": [],
            "forbidden_claims": forbidden_claims(cfg.policies),
            "max_repair_attempts": cfg.budgets.max_repair_attempts,
            "estimated_risk": "LOW",
            "confidence": 0.9,
            "human_gate": {"required": False, "reason": None},
            "ranking_veto": None,
        }
        if decision["decision"] == "NOOP":
            decision["acceptance_criteria"] = []
            decision["allowed_paths"] = []
            decision["work_id"] = None
            decision["candidate_id"] = None
        validated = validate_decision(
            decision,
            root=cfg.root,
            policies=cfg.policies,
            min_confidence=0.0 if decision["decision"] == "NOOP" else 0.0,
        )
        return redact_obj(validated)

    ds_client = client or DeepSeekClient(cfg.deepseek)
    system = _read_prompt("decide.md", cfg.root)
    user_payload = {
        "instruction": "Produce a single CTO decision JSON object matching the schema.",
        "observation": observation,
        "charter_priorities": list(range(1, 11)),
        "cycle_id": cycle_id,
    }
    try:
        result = ds_client.chat_json(
            system=system,
            user=json.dumps(user_payload, ensure_ascii=False, default=str),
        )
    except DeepSeekUnavailable as exc:
        return build_fallback_blocked_decision(
            cycle_id=cycle_id, reason=str(exc), observation=observation
        )
    except DeepSeekInvalidResponse as exc:
        return build_fallback_blocked_decision(
            cycle_id=cycle_id, reason=f"invalid response: {exc}", observation=observation
        )

    content = dict(result.content)
    content.setdefault("cycle_id", cycle_id)
    content.setdefault("decision_id", f"dec-{uuid.uuid4().hex[:12]}")
    content.setdefault("schema_version", "1.0")
    try:
        validated = validate_decision(
            content,
            root=cfg.root,
            policies=cfg.policies,
            min_confidence=cfg.budgets.min_confidence
            if content.get("decision") in {"EXECUTE", "REPAIR", "ACCEPT"}
            else 0.0,
        )
    except DecisionValidationError as exc:
        blocked = build_fallback_blocked_decision(
            cycle_id=cycle_id, reason=f"schema/policy: {exc}", observation=observation
        )
        blocked["_meta"] = {
            **(blocked.get("_meta") or {}),
            "raw_rejected": redact_obj(content),
            "usage": {
                "model": result.usage.model,
                "total_tokens": result.usage.total_tokens,
                "attempts": result.usage.attempts,
            },
        }
        return blocked

    validated["_meta"] = {
        "created_at": _utc_now(),
        "usage": {
            "model": result.usage.model,
            "prompt_tokens": result.usage.prompt_tokens,
            "completion_tokens": result.usage.completion_tokens,
            "total_tokens": result.usage.total_tokens,
            "duration_ms": result.usage.duration_ms,
            "attempts": result.usage.attempts,
            "estimated_cost_usd": result.usage.estimated_cost_usd,
        },
        "finish_reason": result.finish_reason,
    }
    return redact_obj(validated)


def review_execution(
    *,
    decision: dict[str, Any],
    verification: dict[str, Any],
    execution: dict[str, Any],
    config: CTOConfig | None = None,
    client: DeepSeekClient | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Independent CTO review after verifier."""
    cfg = config or load_config()
    cycle_id = decision.get("cycle_id") or "unknown"
    decision_id = decision.get("decision_id") or "unknown"

    if dry_run and client is None:
        verdict = "ACCEPT" if verification.get("result") == "PASS" else "REPAIR"
        if verification.get("result") == "UNSAFE":
            verdict = "BLOCK"
        review = {
            "schema_version": "1.0",
            "review_id": f"rev-dry-{uuid.uuid4().hex[:12]}",
            "cycle_id": cycle_id,
            "decision_id": decision_id,
            "verdict": verdict,
            "summary": f"Dry-run review based on verifier={verification.get('result')}",
            "failed_criteria": list(verification.get("failed_criteria") or []),
            "repair_instructions": list(verification.get("repair_hints") or []),
            "confidence": 0.85,
            "human_gate": {"required": verdict in {"BLOCK", "ESCALATE"}, "reason": None},
        }
        return validate_review(review, root=cfg.root)

    ds_client = client or DeepSeekClient(cfg.deepseek)
    system = _read_prompt("review.md", cfg.root)
    user_payload = {
        "decision": decision,
        "verification": verification,
        "execution": execution,
    }
    try:
        result = ds_client.chat_json(
            system=system,
            user=json.dumps(user_payload, ensure_ascii=False, default=str),
        )
        content = dict(result.content)
        content.setdefault("schema_version", "1.0")
        content.setdefault("review_id", f"rev-{uuid.uuid4().hex[:12]}")
        content.setdefault("cycle_id", cycle_id)
        content.setdefault("decision_id", decision_id)
        return validate_review(content, root=cfg.root)
    except (DeepSeekUnavailable, DeepSeekInvalidResponse, DecisionValidationError) as exc:
        # Fail closed: if verifier PASS keep as REPAIR? No — escalate
        return {
            "schema_version": "1.0",
            "review_id": f"rev-fallback-{uuid.uuid4().hex[:12]}",
            "cycle_id": cycle_id,
            "decision_id": decision_id,
            "verdict": "ESCALATE" if verification.get("result") != "PASS" else "ACCEPT",
            "summary": f"Review fallback (CTO error: {exc})",
            "failed_criteria": list(verification.get("failed_criteria") or []),
            "repair_instructions": [],
            "confidence": 0.5,
            "human_gate": {
                "required": verification.get("result") != "PASS",
                "reason": str(exc),
            },
        }


def save_decision(decision: dict[str, Any], root: Path | None = None) -> Path:
    path = decision_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(redact_obj(decision), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path
