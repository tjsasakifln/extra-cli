"""Fail-closed deploy and soak gate for VPS operation.

Test/crawl failures abort the deploy. The implanted SHA must equal the SHA
approved in CI. No automation may declare VPS_OPERATIONAL; the state remains
PENDING_HUMAN.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

PENDING_HUMAN = "PENDING_HUMAN"
FORBIDDEN_CLAIMS = frozenset({"VPS_OPERATIONAL", "LOCAL_READY", "95%"})
PILOT_REQUIRED = ("pagination", "dedup", "raw", "documents", "replay")
SoakVerdict = Literal["PENDING_HUMAN", "ABORT"]


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    detail: str


@dataclass
class DeployDecision:
    state: str
    abort: bool
    reasons: list[str] = field(default_factory=list)
    implanted_sha: str | None = None
    approved_sha: str | None = None
    claims: list[str] = field(default_factory=list)
    gates: list[GateResult] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "abort": self.abort,
            "reasons": list(self.reasons),
            "implanted_sha": self.implanted_sha,
            "approved_sha": self.approved_sha,
            "claims": list(self.claims),
            "gates": [asdict(g) for g in self.gates],
            "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }


def command_is_masked(command: str) -> bool:
    """Scripts that swallow pytest/crawl failures with `|| true` are illegal."""
    compact = " ".join(command.split())
    return "|| true" in compact or "||true" in compact


def sha_matches(implanted_sha: str, approved_sha: str) -> bool:
    if not implanted_sha or not approved_sha:
        return False
    return implanted_sha.lower() == approved_sha.lower()


def evaluate_preflight(
    *,
    test_exit: int,
    crawl_exit: int,
    commands: list[str],
) -> GateResult:
    masked = [cmd for cmd in commands if command_is_masked(cmd)]
    if masked:
        return GateResult("preflight", False, f"masked_failure:{masked[0]}")
    if test_exit != 0:
        return GateResult("preflight", False, f"test_exit={test_exit}")
    if crawl_exit != 0:
        return GateResult("preflight", False, f"crawl_exit={crawl_exit}")
    return GateResult("preflight", True, "tests_and_crawls_passed")


def evaluate_sha(implanted_sha: str, approved_sha: str) -> GateResult:
    if sha_matches(implanted_sha, approved_sha):
        return GateResult("sha", True, implanted_sha)
    return GateResult("sha", False, f"{implanted_sha}!={approved_sha}")


def evaluate_pilot(proven: set[str]) -> GateResult:
    missing = [item for item in PILOT_REQUIRED if item not in proven]
    if missing:
        return GateResult("pilot", False, f"missing:{','.join(missing)}")
    return GateResult("pilot", True, "pagination,dedup,raw,documents,replay")


def evaluate_reboot(leases_recovered: bool, jobs_recovered: bool) -> GateResult:
    if leases_recovered and jobs_recovered:
        return GateResult("reboot", True, "leases_and_jobs_recovered")
    return GateResult("reboot", False, "recovery_incomplete")


def evaluate_soak(*, backup_restore: bool, freshness_ok: bool, days: int) -> GateResult:
    if days < 7:
        return GateResult("soak", False, f"days={days}<7")
    if not backup_restore:
        return GateResult("soak", False, "backup_restore_unproven")
    if not freshness_ok:
        return GateResult("soak", False, "freshness_unproven")
    return GateResult("soak", True, "7d_backup_freshness")


def decide_deploy(
    *,
    test_exit: int,
    crawl_exit: int,
    commands: list[str],
    implanted_sha: str,
    approved_sha: str,
    pilot_proven: set[str],
    leases_recovered: bool,
    jobs_recovered: bool,
    backup_restore: bool,
    freshness_ok: bool,
    soak_days: int,
    requested_claims: list[str] | None = None,
) -> DeployDecision:
    decision = DeployDecision(
        state=PENDING_HUMAN,
        abort=False,
        implanted_sha=implanted_sha,
        approved_sha=approved_sha,
        claims=[],
    )
    gates = [
        evaluate_preflight(test_exit=test_exit, crawl_exit=crawl_exit, commands=commands),
        evaluate_sha(implanted_sha, approved_sha),
        evaluate_pilot(pilot_proven),
        evaluate_reboot(leases_recovered, jobs_recovered),
        evaluate_soak(backup_restore=backup_restore, freshness_ok=freshness_ok, days=soak_days),
    ]
    decision.gates = gates
    failed = [g for g in gates if not g.passed]
    if failed:
        decision.abort = True
        decision.reasons = [f"{g.name}:{g.detail}" for g in failed]
    illegal = [c for c in (requested_claims or []) if c in FORBIDDEN_CLAIMS]
    if illegal:
        decision.abort = True
        decision.reasons.append(f"forbidden_claim:{illegal[0]}")
    # State never auto-promotes.
    decision.state = PENDING_HUMAN
    decision.claims = []
    return decision
