"""CTO decision validation and DeepSeek decide/review orchestration."""
from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
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
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_review_payload(
    *,
    decision: dict[str, Any],
    verification: dict[str, Any],
    execution: dict[str, Any],
    work_item: dict[str, Any] | None = None,
    prior_attempts: list[dict[str, Any]] | None = None,
    transcript_excerpt: str | None = None,
) -> dict[str, Any]:
    """Assemble full CTO review context — not criterion counts alone."""
    matrix = list(verification.get("criterion_matrix") or [])
    return {
        "original_decision": decision,
        "work_item": work_item
        or {
            "work_id": decision.get("work_id"),
            "issue_number": decision.get("issue_number"),
            "objective": decision.get("objective"),
            "acceptance_criteria": decision.get("acceptance_criteria"),
            "allowed_paths": decision.get("allowed_paths"),
            "test_commands": decision.get("test_commands"),
            "required_evidence": decision.get("required_evidence"),
            "priority": decision.get("priority"),
            "risk": decision.get("estimated_risk"),
            "blockers": decision.get("blockers"),
            "dependencies": decision.get("dependencies"),
        },
        "diff": {
            "sha256": (verification.get("diff") or {}).get("sha256"),
            "truncated": (verification.get("diff") or {}).get("truncated"),
            "char_len": (verification.get("diff") or {}).get("char_len"),
            "text": (verification.get("diff") or {}).get("text"),
        },
        "criterion_matrix": matrix,
        "modified_files": (verification.get("files") or {}).get("modified")
        or (verification.get("checks") or [{}])[0].get("modified"),
        "files": verification.get("files"),
        "execution": {
            "status": execution.get("status"),
            "exit_code": execution.get("exit_code"),
            "worktree": execution.get("worktree"),
            "branch": execution.get("branch"),
            "session_id": execution.get("session_id"),
            "reason": execution.get("reason"),
            "mock": execution.get("mock"),
            "dry_run": execution.get("dry_run"),
        },
        "transcript_excerpt_redacted": transcript_excerpt
        or execution.get("transcript_excerpt")
        or None,
        "tests": next(
            (
                c.get("results")
                for c in (verification.get("checks") or [])
                if c.get("name") == "tests"
            ),
            [],
        ),
        "evidence": decision.get("required_evidence") or [],
        "verification_result": verification.get("result"),
        "failed_criteria": verification.get("failed_criteria"),
        "prior_attempts": list(prior_attempts or []),
        # Counts alone are insufficient — included only as secondary signal
        "matrix_counts": {
            "pass": sum(1 for m in matrix if m.get("status") == "PASS"),
            "fail": sum(1 for m in matrix if m.get("status") == "FAIL"),
            "unproven": sum(1 for m in matrix if m.get("status") == "UNPROVEN"),
            "note": "Do not review by counts alone; inspect criterion_matrix and diff",
        },
    }


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


_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$")


def validate_safe_id(value: str, *, field: str = "id") -> str:
    """Strict identifier for cycle_id / decision_id / branch segments (no path traversal)."""
    s = str(value or "").strip()
    if not s or not _SAFE_ID_RE.match(s):
        raise DecisionValidationError(
            f"invalid {field}: must match ^[a-zA-Z0-9][a-zA-Z0-9._-]{{0,79}}$ got {value!r}"
        )
    if ".." in s or "/" in s or "\\" in s or " " in s:
        raise DecisionValidationError(f"invalid {field}: path-like or whitespace: {value!r}")
    # Reject control / ambiguous unicode
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in s):
        raise DecisionValidationError(f"invalid {field}: control characters")
    if any(ord(ch) > 127 for ch in s):
        raise DecisionValidationError(f"invalid {field}: non-ASCII not allowed")
    return s


def validate_decision(
    decision: dict[str, Any],
    *,
    root: Path | None = None,
    policies: dict[str, Any] | None = None,
    min_confidence: float = 0.0,
    allow_legacy_test_commands: bool = False,
) -> dict[str, Any]:
    """Validate decision schema + business fail-closed rules.

    Model-authored decisions must use ``test_ids`` only
    (``allow_legacy_test_commands=False``). Legacy imports/seeds may map aliases
    once, then strip free-form commands from the stored decision.
    """
    schema = load_schema(decision_schema_path(root))
    validate_against_schema(decision, schema)

    # Canonicalize identifiers (fail closed on traversal / spaces)
    decision = {
        **decision,
        "cycle_id": validate_safe_id(str(decision.get("cycle_id") or ""), field="cycle_id"),
        "decision_id": validate_safe_id(
            str(decision.get("decision_id") or ""), field="decision_id"
        ),
    }

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
        # test_ids only — resolve + require non-empty; never keep free shell for model path
        from scripts.cto.test_registry import (
            AuthorizedTestError,
            normalize_test_ids,
        )

        try:
            tids = normalize_test_ids(
                decision,
                root=root,
                allow_legacy_commands=allow_legacy_test_commands,
            )
        except AuthorizedTestError as exc:
            raise DecisionValidationError(str(exc)) from exc
        if not tids:
            raise DecisionValidationError(
                "EXECUTE/REPAIR requires non-empty authorized test_ids "
                "(free-form test_commands are not accepted from the model)"
            )
        # Canonical stored form: test_ids only; strip free-form commands
        decision = {**decision, "test_ids": tids, "test_commands": []}

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


def validate_review(
    review: dict[str, Any],
    *,
    root: Path | None = None,
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    schema = load_schema(review_schema_path(root))
    validate_against_schema(review, schema)
    if review["verdict"] not in {"ACCEPT", "REPAIR", "ROLLBACK", "BLOCK", "ESCALATE"}:
        raise DecisionValidationError("invalid review verdict")
    # Absolute veto is applied after schema validate when verification is supplied
    if verification is not None:
        from scripts.cto.review_veto import apply_absolute_veto

        review = apply_absolute_veto(review, verification)
        # Drop internal veto metadata before re-validate optional fields
        if review["verdict"] not in {"ACCEPT", "REPAIR", "ROLLBACK", "BLOCK", "ESCALATE"}:
            raise DecisionValidationError("invalid review verdict after veto")
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
        "test_ids": [],
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
    root: Path | None = None,
) -> dict[str, Any]:
    """Produce a validated CTO decision from observation JSON.

    Ranking is refreshed or explicitly marked stale before decision — never
    silently treat old latest.json as current.
    """
    cfg = config or load_config()
    root = root or cfg.root
    cycle_id = (
        (observation.get("cycle") or {}).get("cycle_id")
        or f"cyc-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    )

    from scripts.cto.observer import ensure_ranking_current

    rank_meta = ensure_ranking_current(root, try_refresh=not dry_run)
    ranking_obs = dict(observation.get("ranking") or {})
    ranking_obs["freshness"] = rank_meta
    ranking_obs["stale"] = bool(rank_meta.get("stale") or rank_meta.get("explicitly_stale"))
    if ranking_obs["stale"]:
        ranking_obs["stale_warning"] = (
            "RANKING_STALE: latest.json is not current; do not treat as live state"
        )
    observation = {**observation, "ranking": ranking_obs}

    if dry_run and client is None:
        # Deterministic dry-run: only truly-ready work (readiness gates + not PR#48-implemented)
        from scripts.cto.work_registry import (
            IMPLEMENTED_IN_PR48,
            ISSUE_NUMBERS_IMPLEMENTED_IN_PR48,
            get_by_work_id,
            load_registry,
            readiness_for_item,
        )

        ranking = observation.get("ranking") or {}
        top = (ranking.get("top") or [None])[0]
        issues = observation.get("issues") or {}
        registry = load_registry(root)
        issue_number = None
        work_id = None

        def _is_executable_ready(item: dict[str, Any] | None, issue_meta: dict[str, Any] | None = None) -> bool:
            if not item and not issue_meta:
                return False
            wid = (item or {}).get("work_id") or (issue_meta or {}).get("work_id")
            inum = (item or {}).get("issue_number") or (issue_meta or {}).get("number")
            if wid in IMPLEMENTED_IN_PR48 or inum in ISSUE_NUMBERS_IMPLEMENTED_IN_PR48:
                return False
            if item is not None:
                info = readiness_for_item(item, registry)
                return bool(info.get("ready"))
            # issue-only: require effective state ready and no dual labels with non-ready
            eff = (issue_meta or {}).get("effective_state") or ""
            state_labels = (issue_meta or {}).get("state_labels") or []
            if any(
                s in state_labels
                for s in ("state:review", "state:human", "state:blocked", "state:in-progress")
            ):
                return False
            return eff == "state:ready" or (
                not eff and "state:ready" in state_labels and len(state_labels) == 1
            )

        # 1) Prefer registry items that are truly ready
        ready_items = [
            i
            for i in (registry.get("work_items") or [])
            if _is_executable_ready(i, None)
        ]
        # priority order p0,p1,p2,p3
        prio = {"p0": 0, "p1": 1, "p2": 2, "p3": 3}
        ready_items.sort(key=lambda x: prio.get(str(x.get("priority")), 9))
        if ready_items:
            work_id = ready_items[0].get("work_id")
            if ready_items[0].get("issue_number"):
                issue_number = int(ready_items[0]["issue_number"])

        # 2) Fallback: observation state:ready filtered by readiness
        if not work_id:
            for cand in (issues.get("by_state") or {}).get("state:ready") or []:
                wid = cand.get("work_id")
                item = get_by_work_id(registry, str(wid)) if wid else None
                if _is_executable_ready(item, cand):
                    work_id = wid or work_id
                    if cand.get("number"):
                        issue_number = int(cand["number"])
                    break

        # 3) Ranker advisory only if not already-implemented and maps to ready work
        if not work_id and top and (top or {}).get("id"):
            cand_id = (top or {}).get("id")
            # do not execute ranker research items that are blocked
            for i in registry.get("work_items") or []:
                if i.get("candidate_id") == cand_id and _is_executable_ready(i, None):
                    work_id = i.get("work_id")
                    if i.get("issue_number"):
                        issue_number = int(i["issue_number"])
                    break

        # Link issue_number from registry when only work_id known
        if work_id and not issue_number:
            try:
                item = get_by_work_id(registry, str(work_id))
                if item and item.get("issue_number"):
                    issue_number = int(item["issue_number"])
            except Exception:  # noqa: BLE001
                issue_number = issue_number
        if work_id and not issue_number:
            for it in issues.get("items") or []:
                if it.get("work_id") == work_id and it.get("number"):
                    issue_number = int(it["number"])
                    break

        # Final hard reject if still points at implemented PR#48 work
        if work_id in IMPLEMENTED_IN_PR48 or issue_number in ISSUE_NUMBERS_IMPLEMENTED_IN_PR48:
            work_id = None
            issue_number = None
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
            "test_ids": ["cto.pytest.suite"],
            "test_commands": [],
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
            decision["test_ids"] = []
            decision["work_id"] = None
            decision["candidate_id"] = None
        validated = validate_decision(
            decision,
            root=cfg.root,
            policies=cfg.policies,
            min_confidence=0.0 if decision["decision"] == "NOOP" else 0.0,
            allow_legacy_test_commands=False,
        )
        # Second hard gate even after selection
        validated = enforce_executable_readiness(validated, root=root)
        if validated.get("decision") == "NOOP":
            try:
                validated = validate_decision(
                    validated,
                    root=cfg.root,
                    policies=cfg.policies,
                    min_confidence=0.0,
                )
            except DecisionValidationError:
                pass
        validated["_meta"] = {
            **(validated.get("_meta") or {}),
            "created_at": _utc_now(),
            "dry_run": True,
            "ranking_freshness": rank_meta,
            "ranking_stale": bool(ranking_obs.get("stale")),
        }
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
    # cycle_id is orchestrator authority — never accept model-supplied value
    content["cycle_id"] = validate_safe_id(cycle_id, field="cycle_id")
    # decision_id: generate if missing/invalid; never trust path-like model values
    raw_dec_id = str(content.get("decision_id") or "").strip()
    try:
        content["decision_id"] = validate_safe_id(raw_dec_id, field="decision_id")
    except DecisionValidationError:
        content["decision_id"] = f"dec-{uuid.uuid4().hex[:12]}"
    content["schema_version"] = "1.0"
    # Model must not introduce free-form test_commands as authoritative
    if content.get("decision") in {"EXECUTE", "REPAIR"}:
        # Prefer test_ids; drop unmapped free shell (legacy aliases only via explicit flag)
        content.pop("test_commands", None)
    try:
        validated = validate_decision(
            content,
            root=cfg.root,
            policies=cfg.policies,
            min_confidence=cfg.budgets.min_confidence
            if content.get("decision") in {"EXECUTE", "REPAIR", "ACCEPT"}
            else 0.0,
            allow_legacy_test_commands=False,
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

    # Hard readiness gate on live CTO output (never re-execute PR#48-delivered work)
    validated = enforce_executable_readiness(validated, root=root)

    validated["_meta"] = {
        **(validated.get("_meta") or {}),
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
        "ranking_freshness": rank_meta,
        "ranking_stale": bool(ranking_obs.get("stale")),
    }
    return redact_obj(validated)


def enforce_executable_readiness(
    decision: dict[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Reject EXECUTE/REPAIR targeting non-ready or already-implemented work.

    Converts to NOOP (or keeps BLOCK/ESCALATE) rather than re-picking silently.
    """
    from scripts.cto.work_registry import (
        IMPLEMENTED_IN_PR48,
        ISSUE_NUMBERS_IMPLEMENTED_IN_PR48,
        get_by_work_id,
        load_registry,
        readiness_for_item,
    )

    action = decision.get("decision")
    if action not in {"EXECUTE", "REPAIR", "ACCEPT"}:
        return decision

    wid = decision.get("work_id")
    inum = decision.get("issue_number")
    reasons: list[str] = []
    if wid in IMPLEMENTED_IN_PR48 or inum in ISSUE_NUMBERS_IMPLEMENTED_IN_PR48:
        reasons.append(
            f"work already implemented in PR #48 (work_id={wid} issue={inum}) — not new ready work"
        )
    registry = load_registry(root)
    item = get_by_work_id(registry, str(wid)) if wid else None
    if item is not None:
        info = readiness_for_item(item, registry)
        if not info.get("ready"):
            reasons.extend(list(info.get("reasons") or ["not ready"]))
    elif wid or inum:
        # Unknown registry item with EXECUTE is fail-closed unless issue-only NOOP
        if action in {"EXECUTE", "REPAIR"}:
            reasons.append("work item not found in registry or not ready")

    if not reasons:
        return decision

    # Do not invent alternate work — escalate/noop closed
    return {
        **decision,
        "decision": "NOOP",
        "objective": "No executable ready work after readiness gate",
        "work_id": None,
        "issue_number": None,
        "candidate_id": None,
        "acceptance_criteria": [],
        "allowed_paths": [],
        "test_ids": [],
        "test_commands": [],
        "strategic_reason": (
            "READINESS_GATE: " + "; ".join(reasons[:5])
        ),
        "human_gate": {
            "required": False,
            "reason": None,
        },
        "_meta": {
            **(decision.get("_meta") or {}),
            "readiness_rejected": True,
            "readiness_reasons": reasons,
            "original_decision": action,
            "original_work_id": wid,
            "original_issue_number": inum,
        },
    }


def normalize_review_content(content: dict[str, Any]) -> dict[str, Any]:
    """Coerce common DeepSeek drift into review.schema.json before validate.

    Does not invent ACCEPT — only renames/fills required structural fields.
    """
    out = dict(content)
    # summary: required non-empty string
    summary = out.get("summary")
    if summary is None or (isinstance(summary, str) and not summary.strip()):
        for alt in ("reason", "rationale", "explanation", "message", "notes"):
            val = out.get(alt)
            if val is not None and str(val).strip():
                out["summary"] = str(val).strip()
                break
        else:
            # last resort structural placeholder (verdict still decided by model)
            out["summary"] = str(out.get("verdict") or "review completed")
    else:
        out["summary"] = str(summary).strip()
    for alt in ("reason", "rationale", "explanation", "message", "notes"):
        if alt in out and alt != "summary":
            out.pop(alt, None)
    if "failed_criteria" not in out or out["failed_criteria"] is None:
        out["failed_criteria"] = []
    elif not isinstance(out["failed_criteria"], list):
        out["failed_criteria"] = [str(out["failed_criteria"])]
    if "repair_instructions" not in out or out["repair_instructions"] is None:
        out["repair_instructions"] = []
    elif not isinstance(out["repair_instructions"], list):
        out["repair_instructions"] = [str(out["repair_instructions"])]
    if "confidence" not in out or out["confidence"] is None:
        out["confidence"] = 0.5
    try:
        out["confidence"] = float(out["confidence"])
    except (TypeError, ValueError):
        out["confidence"] = 0.5
    hg = out.get("human_gate")
    if not isinstance(hg, dict):
        out["human_gate"] = {"required": False, "reason": None}
    else:
        out["human_gate"] = {
            "required": bool(hg.get("required")),
            "reason": hg.get("reason"),
        }
    allowed = {
        "schema_version",
        "review_id",
        "cycle_id",
        "decision_id",
        "verdict",
        "summary",
        "failed_criteria",
        "repair_instructions",
        "confidence",
        "human_gate",
    }
    return {k: v for k, v in out.items() if k in allowed}


def review_execution(
    *,
    decision: dict[str, Any],
    verification: dict[str, Any],
    execution: dict[str, Any],
    config: CTOConfig | None = None,
    client: DeepSeekClient | None = None,
    dry_run: bool = False,
    work_item: dict[str, Any] | None = None,
    prior_attempts: list[dict[str, Any]] | None = None,
    transcript_excerpt: str | None = None,
) -> dict[str, Any]:
    """Independent CTO review after verifier.

    DeepSeek unavailability/timeout/invalid schema/error NEVER yields ACCEPT.
    Use ESCALATE or BLOCK with BLOCKED_CTO_UNAVAILABLE.
    """
    cfg = config or load_config()
    cycle_id = decision.get("cycle_id") or "unknown"
    decision_id = decision.get("decision_id") or "unknown"

    review_payload = build_review_payload(
        decision=decision,
        verification=verification,
        execution=execution,
        work_item=work_item,
        prior_attempts=prior_attempts,
        transcript_excerpt=transcript_excerpt,
    )

    if dry_run and client is None:
        # Deterministic dry-run does not call DeepSeek — local verifier only
        verdict = "ACCEPT" if verification.get("result") == "PASS" else "REPAIR"
        if verification.get("result") == "UNSAFE":
            verdict = "BLOCK"
        if any(
            m.get("status") == "UNPROVEN"
            for m in (verification.get("criterion_matrix") or [])
        ):
            verdict = "REPAIR"
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
            "_meta": {
                "review_payload_keys": sorted(review_payload.keys()),
                "matrix_counts": review_payload.get("matrix_counts"),
                "dry_run": True,
            },
        }
        validated = validate_review(
            {k: v for k, v in review.items() if k != "_meta"},
            root=cfg.root,
            verification=verification,
        )
        return validated | {"_meta": review["_meta"], "review_context": review_payload}

    ds_client = client or DeepSeekClient(cfg.deepseek)
    system = _read_prompt("review.md", cfg.root)
    user_payload = {
        "instruction": (
            "Review using full context. Do not decide from criterion counts alone. "
            "Inspect original decision, work item, diff+hashes, criterion matrix, "
            "execution exit code, tests, evidence, and prior attempts. "
            "ABSOLUTE RULE: if verification.result is not PASS you MUST NOT return ACCEPT."
        ),
        **review_payload,
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
        content = normalize_review_content(content)
        validated = validate_review(content, root=cfg.root, verification=verification)
        # Re-apply veto on the full object (preserves _veto for audit)
        from scripts.cto.review_veto import apply_absolute_veto

        validated = apply_absolute_veto(validated, verification)
        validated["review_context"] = {
            "matrix_counts": review_payload.get("matrix_counts"),
            "diff_sha256": (review_payload.get("diff") or {}).get("sha256"),
            "execution_status": (review_payload.get("execution") or {}).get("status"),
            "verification_result": verification.get("result"),
            "commit_sha": verification.get("commit_sha"),
            "tree_hash": verification.get("tree_hash"),
        }
        return validated
    except (DeepSeekUnavailable, DeepSeekInvalidResponse, DecisionValidationError) as exc:
        # NEVER ACCEPT when CTO unavailable — even if verifier PASS
        return {
            "schema_version": "1.0",
            "review_id": f"rev-fallback-{uuid.uuid4().hex[:12]}",
            "cycle_id": cycle_id,
            "decision_id": decision_id,
            "verdict": "ESCALATE",
            "summary": (
                f"BLOCKED_CTO_UNAVAILABLE: DeepSeek review failed ({exc}). "
                f"Verifier result was {verification.get('result')}; "
                "cannot ACCEPT without CTO review."
            ),
            "failed_criteria": list(verification.get("failed_criteria") or [])
            + ["BLOCKED_CTO_UNAVAILABLE"],
            "repair_instructions": [],
            "confidence": 0.0,
            "human_gate": {
                "required": True,
                "reason": f"BLOCKED_CTO_UNAVAILABLE: {exc}",
            },
            "blocked_code": "BLOCKED_CTO_UNAVAILABLE",
            "review_context": {
                "matrix_counts": review_payload.get("matrix_counts"),
                "diff_sha256": (review_payload.get("diff") or {}).get("sha256"),
                "verifier_result": verification.get("result"),
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
