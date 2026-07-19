"""Policy enforcement for CTO decisions and human gates."""
from __future__ import annotations

from typing import Any

from scripts.cto.config import load_policies

HUMAN_ONLY_DEFAULT = [
    "merge",
    "deploy",
    "force_push",
    "paid_provision",
    "destructive_migration",
    "irreversible_delete",
    "change_dod_meaning",
    "reduce_dod",
    "architecture_material_change",
    "contractual_scope_change",
    "client_claim",
    "external_publication",
    "confidential_out_of_scope_access",
    "third_repair_attempt",
    "product_decision_without_prd",
]

FORBIDDEN_CLAIMS_DEFAULT = [
    "LOCAL_READY",
    "PRE_VPS_FINAL_READY",
    "VPS_OPERATIONAL",
    "PROJECT_DONE",
    "95% coverage",
    "cobertura operacional 95%",
    "recall 100%",
]


def human_only_actions(policies: dict[str, Any] | None = None) -> set[str]:
    pol = policies if policies is not None else load_policies()
    return set(pol.get("human_only_actions") or HUMAN_ONLY_DEFAULT)


def forbidden_claims(policies: dict[str, Any] | None = None) -> list[str]:
    pol = policies if policies is not None else load_policies()
    return list(pol.get("forbidden_claims") or FORBIDDEN_CLAIMS_DEFAULT)


def is_human_only_action(action: str, policies: dict[str, Any] | None = None) -> bool:
    key = action.strip().lower().replace("-", "_").replace(" ", "_")
    return key in {a.lower() for a in human_only_actions(policies)}


def decision_authorizes_human_only(
    decision: dict[str, Any],
    policies: dict[str, Any] | None = None,
) -> list[str]:
    """Return list of human-only actions the decision improperly tries to authorize."""
    violations: list[str] = []
    forbidden = set(decision.get("forbidden_actions") or [])
    # If decision is EXECUTE/REPAIR but allowed_claims include forbidden seals
    for claim in decision.get("allowed_claims") or []:
        for fc in forbidden_claims(policies):
            if fc.lower() in str(claim).lower():
                violations.append(f"allowed_claims includes forbidden seal: {fc}")
    # Detect objective/reason trying to merge/deploy
    blob = " ".join(
        [
            str(decision.get("objective") or ""),
            str(decision.get("strategic_reason") or ""),
            " ".join(decision.get("test_commands") or []),
        ]
    ).lower()
    for action in human_only_actions(policies):
        token = action.replace("_", " ")
        if token in blob or action in blob:
            # only violation if not listed in forbidden_actions (should be forbidden)
            if action not in forbidden and action.replace("_", "-") not in forbidden:
                # soft: escalate flags handled elsewhere; hard fail if decision says EXECUTE merge
                if decision.get("decision") in {"EXECUTE", "REPAIR", "ACCEPT"}:
                    if any(
                        w in blob
                        for w in (
                            f"{action}",
                            f"git {action}" if action in {"merge"} else action,
                        )
                    ) and action in {
                        "merge",
                        "deploy",
                        "force_push",
                        "destructive_migration",
                    }:
                        violations.append(f"decision references human-only action: {action}")
    return violations


def path_allowed(path: str, allowed: list[str], forbidden: list[str]) -> bool:
    """Simple prefix/glob-ish check (no shell)."""
    norm = path.replace("\\", "/").lstrip("./")
    for f in forbidden:
        f_norm = f.replace("\\", "/").lstrip("./").rstrip("*")
        if f_norm and (norm == f_norm or norm.startswith(f_norm.rstrip("/"))):
            return False
        if f.endswith("**") and norm.startswith(f[:-2].rstrip("/")):
            return False
    if not allowed:
        return False
    for a in allowed:
        a_norm = a.replace("\\", "/").lstrip("./")
        if a_norm.endswith("/**"):
            prefix = a_norm[:-3]
            if norm == prefix or norm.startswith(prefix + "/"):
                return True
        elif a_norm.endswith("/*"):
            prefix = a_norm[:-2]
            if norm.startswith(prefix + "/") and "/" not in norm[len(prefix) + 1 :]:
                return True
        elif a_norm.endswith("*"):
            if norm.startswith(a_norm[:-1]):
                return True
        else:
            if norm == a_norm or norm.startswith(a_norm.rstrip("/") + "/"):
                return True
    return False
