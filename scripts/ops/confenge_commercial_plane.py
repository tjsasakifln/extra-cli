"""Pure evaluators for CONFENGE commercial-plane authority.

I/O (filesystem, ssh, systemd) stays at the CLI edges so tests can feed
fixtures and in-memory unit text. This is not a second control plane: it
reuses ``CHAIN_TIMERS``, ``CHAIN_DISABLED_TIMERS`` and ``DECOUPLED_ON_SUCCESS``.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONTRACT_RELATIVE = Path("docs/contracts/confenge-commercial-plane/v1/operating-authority.json")
ADR_RELATIVE = Path("docs/architecture/adr/ADR-039-confenge-pncp-outbound-decoupling.md")
ADR_INDEX_RELATIVE = Path("docs/architecture/adr/INDEX.md")
DOD_RELATIVE = Path("DOD.md")
RUNBOOK_RELATIVE = Path("docs/ops/confenge-commercial-plane-authority.md")

CONTRACT_ID = "CONFENGE_COMMERCIAL_PLANE_OPERATING_AUTHORITY"
REQUIRED_CONTRACT_FIELDS = (
    "contract_id",
    "version",
    "status",
    "pncp_live_role",
    "commercial_operational_source",
    "current_population_authority",
    "commercial_cycle_stages",
    "source_health_statuses",
    "datalake_fail_closed_gates",
    "prohibited_dependency_edges",
    "prohibited_terminal_states",
    "terminology",
    "superseded_artifacts",
    "owner_boundaries",
    "rollback_semantics",
)

CHAIN_UNITS = (
    "pncp-contracts.service",
    "extra-confenge-source-freshness-gate.service",
    "extra-confenge-target-fit-refresh.service",
    "extra-confenge-target-fit-reconcile.service",
    "extra-confenge-contact-cycle.service",
    "extra-confenge-feed-cycle.service",
)

COMMERCIAL_TIMERS = (
    "extra-confenge-target-fit-refresh.timer",
    "extra-confenge-target-fit-reconcile.timer",
    "extra-confenge-contact-cycle.timer",
    "extra-confenge-feed-cycle.timer",
)

COMMERCIAL_CODE_PATHS = (
    Path("scripts/confenge_outreach_pipeline/cli.py"),
    Path("scripts/confenge_outreach_pipeline/pipeline.py"),
    Path("scripts/confenge_activation/publish.py"),
    Path("scripts/warmbly_bridge/export.py"),
    Path("scripts/ops/build_controlled_email_cohort.py"),
)

# Live PNCP FRESH used as a commercial abort. Watermark restamp under FRESH is
# allowed; aborting the commercial path because status != FRESH is not.
_FRESH_ABORT = re.compile(
    r"""(?ix)
    (raise\s+ValueError|sys\.exit|EXIT_FAIL)
    .{0,220}
    (status\s*!=\s*['\"]FRESH['\"]|not\s+.*FRESH|freshness.*abort|abort.*fresh)
    |
    if\s+.{0,80}status.{0,40}!=.{0,20}['\"]FRESH['\"].{0,120}(raise|return\s+False|sys\.exit)
    """
)

_DOD_REQUIRED = (
    "PNCP live **não** é autoridade comercial",
    "commercial refresh",
    "PNCP ingestion run",
    "source run canônico",
    "PENDING_ONSUCCESS",
)

_HISTORICAL_LABEL = re.compile(
    r"(?im)^\s{0,3}(\*\*)?(Status|status)\s*:\s*(HISTORICAL|SUPERSEDED)\b"
    r"|^\s{0,3}<!--\s*(HISTORICAL|SUPERSEDED)\s*-->"
    r"|^\s{0,3}#.*\b(HISTORICAL|SUPERSEDED)\b"
)


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class PlaneEvaluation:
    checks: list[Check] = field(default_factory=list)
    tokens: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks) and not self.errors


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _unit_section(text: str, header: str) -> str:
    marker = f"[{header}]"
    if marker not in text:
        return ""
    rest = text.split(marker, 1)[1]
    nxt = re.search(r"\n\[", rest)
    return rest[: nxt.start()] if nxt else rest


def on_success_targets(unit_text: str) -> list[str]:
    values: list[str] = []
    section = _unit_section(unit_text, "Unit")
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("OnSuccess="):
            values.extend(part for part in stripped.split("=", 1)[1].split() if part)
    return values


def load_contract(root: Path) -> dict[str, Any]:
    path = root / CONTRACT_RELATIVE
    data = json.loads(_read(path))
    if not isinstance(data, dict):
        raise ValueError("operating-authority.json must be an object")
    return data


def evaluate_contract(root: Path) -> list[Check]:
    checks: list[Check] = []
    path = root / CONTRACT_RELATIVE
    if not path.is_file():
        return [Check("contract_present", False, str(path))]
    try:
        data = load_contract(root)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return [Check("contract_parse", False, str(exc))]
    missing = [key for key in REQUIRED_CONTRACT_FIELDS if key not in data]
    checks.append(Check("contract_fields", not missing, ",".join(missing)))
    checks.append(
        Check(
            "contract_identity",
            data.get("contract_id") == CONTRACT_ID and str(data.get("status", "")).upper() == "ACTIVE",
            f"id={data.get('contract_id')} status={data.get('status')}",
        )
    )
    checks.append(
        Check(
            "pncp_live_role",
            data.get("pncp_live_role") == "ASYNC_INGESTION_AND_TELEMETRY_ONLY",
            str(data.get("pncp_live_role")),
        )
    )
    checks.append(
        Check(
            "commercial_operational_source",
            data.get("commercial_operational_source") == "PERSISTED_CANONICAL_DATALAKE",
            str(data.get("commercial_operational_source")),
        )
    )
    checks.append(
        Check(
            "population_not_v2",
            data.get("current_population_authority") == "TARGET_FIT_PERSISTED_PROJECTION"
            and "COMMERCIAL_AUTHORITY/2.0" in (data.get("not_adopted") or []),
            str(data.get("current_population_authority")),
        )
    )
    checks.append(
        Check(
            "pending_onsuccess_prohibited",
            "PENDING_ONSUCCESS" in (data.get("prohibited_terminal_states") or []),
            "",
        )
    )
    statuses = set(data.get("source_health_statuses") or [])
    checks.append(
        Check(
            "source_health_statuses",
            {"FRESH", "DEGRADED", "STALE", "UNKNOWN"} <= statuses,
            ",".join(sorted(statuses)),
        )
    )
    rules = data.get("source_health_rules") or {}
    checks.append(
        Check(
            "source_health_not_a_gate",
            rules.get("authorizes_publication") is False and rules.get("blocks_publication") is False,
            json.dumps(rules, sort_keys=True),
        )
    )
    required_gates = {
        "datalake_availability",
        "coverage_ratio",
        "unexplained_missing",
        "pagination_exhausted_normally",
        "terminal_queue",
        "membership_binding",
        "source_health_envelope_present",
    }
    gates = {str(item) for item in (data.get("datalake_fail_closed_gates") or [])}
    missing_gates = sorted(required_gates - gates)
    checks.append(Check("datalake_gates_present", not missing_gates, ",".join(missing_gates)))
    return checks


def evaluate_adr(root: Path) -> list[Check]:
    adr = _read(root / ADR_RELATIVE)
    index = _read(root / ADR_INDEX_RELATIVE)
    accepted = bool(
        re.search(r"\*\*Status:\*\*\s*Accepted/Effective", adr, re.I)
        or re.search(r"^-\s+\*\*Status:\*\*\s*Accepted/Effective", adr, re.M)
    )
    has_pr = "#535" in adr and "ad4d18f8" in adr
    has_qa = "d99dc92c" in adr and "PASS" in adr
    not_v2 = "COMMERCIAL_AUTHORITY/2.0" in adr and "não" in adr.lower()
    index_ok = bool(
        re.search(
            r"ADR-039.*Accepted/Effective",
            index,
            re.I | re.S,
        )
    )
    proposed_left = bool(re.search(r"ADR-039.*\*\*Proposed\*\*", index, re.I))
    return [
        Check("adr_accepted_effective", accepted, adr.splitlines()[2] if adr.splitlines() else ""),
        Check("adr_acceptance_evidence", has_pr and has_qa, "pr535/merge/qa"),
        Check("adr_not_adopting_v2", not_v2, ""),
        Check("adr_index_coherent", index_ok and not proposed_left, "INDEX"),
    ]


def evaluate_dod(root: Path) -> list[Check]:
    dod = _read(root / DOD_RELATIVE)
    missing = [token for token in _DOD_REQUIRED if token not in dod]
    p0 = "P0 — Autoridade do plano comercial CONFENGE" in dod
    return [
        Check("dod_p0_section", p0, ""),
        Check("dod_invariants", not missing, ",".join(missing)),
    ]


def evaluate_units(root: Path) -> list[Check]:
    unit_dir = root / "deploy" / "systemd"
    coupled: list[str] = []
    missing: list[str] = []
    for name in CHAIN_UNITS:
        path = unit_dir / name
        if not path.is_file():
            missing.append(name)
            continue
        targets = on_success_targets(_read(path))
        if targets:
            coupled.append(f"{name}->{','.join(targets)}")
    return [
        Check("versioned_units_present", not missing, ",".join(missing)),
        Check("versioned_onsuccess_zero", not coupled, ";".join(coupled)),
    ]


def _assign_tuple(source: str, name: str) -> tuple[str, ...]:
    tree = ast.parse(source)
    for node in tree.body:
        target = None
        value = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target, value = node.target.id, node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target, value = node.targets[0].id, node.value
        if target != name or value is None:
            continue
        if isinstance(value, ast.Tuple):
            out: list[str] = []
            for elt in value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    out.append(elt.value)
            return tuple(out)
    return ()


def evaluate_pin_timers(root: Path) -> list[Check]:
    pin = root / "deploy/confenge/pin_release.py"
    if not pin.is_file():
        return [Check("pin_release_present", False, str(pin))]
    source = _read(pin)
    timers = _assign_tuple(source, "CHAIN_TIMERS")
    disabled = _assign_tuple(source, "CHAIN_DISABLED_TIMERS")
    missing = [name for name in COMMERCIAL_TIMERS if name not in timers]
    orphaned = [name for name in COMMERCIAL_TIMERS if name in disabled]
    return [
        Check("pin_release_present", True, ""),
        Check("chain_timers_cover_commercial", not missing, ",".join(missing)),
        Check("chain_disabled_does_not_orphan", not orphaned, ",".join(orphaned)),
        Check("disabled_timers_empty_or_non_commercial", not orphaned, ",".join(disabled)),
    ]


def evaluate_commercial_code(root: Path) -> list[Check]:
    hits: list[str] = []
    envelope_ok = False
    for rel in COMMERCIAL_CODE_PATHS:
        path = root / rel
        if not path.is_file():
            hits.append(f"missing:{rel}")
            continue
        text = _read(path)
        if "source_health_attestation_present" in text or "source_operational_health" in text:
            envelope_ok = True
        if _FRESH_ABORT.search(text):
            hits.append(str(rel))
    # pipeline.py restamps watermark only when status == FRESH; that is allowed.
    pipeline = root / "scripts/confenge_outreach_pipeline/pipeline.py"
    if pipeline.is_file():
        text = _read(pipeline)
        if "if freshness.get(\"status\") == \"FRESH\"" not in text:
            hits.append("pipeline_missing_fresh_restamp_guard")
        abort_on_non_fresh = re.search(
            r'if freshness\.get\("status"\) != "FRESH"',
            text,
        )
        if abort_on_non_fresh:
            hits.append("pipeline_aborts_on_non_fresh")
    return [
        Check("pncp_fresh_not_commercial_gate", not hits, ",".join(hits)),
        Check("source_health_envelope_required", envelope_ok, ""),
    ]


def evaluate_pr528_not_current(root: Path) -> list[Check]:
    current_docs = [
        root / RUNBOOK_RELATIVE,
        root / ADR_RELATIVE,
        root / DOD_RELATIVE,
        root / CONTRACT_RELATIVE,
    ]
    instructing: list[str] = []
    for path in current_docs:
        if not path.is_file():
            continue
        text = _read(path)
        if re.search(r"(?i)merge(?:ar)?\s+(?:o\s+)?PR\s*#?528", text):
            instructing.append(path.name)
        if re.search(r"(?i)retomar a branch do PR #528", text) and "PROIBIDO" not in text and "não" not in text.lower():
            instructing.append(path.name)
    return [Check("pr528_not_current_implementation", not instructing, ",".join(instructing))]


def evaluate_runbook(root: Path) -> list[Check]:
    path = root / RUNBOOK_RELATIVE
    if not path.is_file():
        return [Check("runbook_present", False, str(path))]
    text = _read(path)
    needed = (
        "Dois planos",
        "PENDING_ONSUCCESS",
        "Pode bloquear",
        "Não reutilizar resultado parcial",
        "python3 -m scripts.ops.check_confenge_commercial_plane",
    )
    missing = [item for item in needed if item not in text]
    return [
        Check("runbook_present", True, ""),
        Check("runbook_complete", not missing, ",".join(missing)),
    ]


def evaluate_repo(root: Path) -> PlaneEvaluation:
    ev = PlaneEvaluation()
    ev.checks.extend(evaluate_contract(root))
    ev.checks.extend(evaluate_adr(root))
    ev.checks.extend(evaluate_dod(root))
    ev.checks.extend(evaluate_units(root))
    ev.checks.extend(evaluate_pin_timers(root))
    ev.checks.extend(evaluate_commercial_code(root))
    ev.checks.extend(evaluate_pr528_not_current(root))
    ev.checks.extend(evaluate_runbook(root))
    architecture_ok = all(c.ok for c in ev.checks)
    ev.tokens = {
        "PNCP_LIVE_ROLE": "ASYNC_INGESTION_AND_TELEMETRY_ONLY",
        "COMMERCIAL_OPERATIONAL_SOURCE": "PERSISTED_CANONICAL_DATALAKE",
        "PNCP_FRESH_IS_COMMERCIAL_GATE": "NO",
        "HOST_ONSUCCESS_COUPLING": "NOT_TESTED",
        "COMMERCIAL_STAGE_ORPHANS": "ZERO" if architecture_ok else "FAIL",
        "DATALAKE_FAIL_CLOSED_GATES": "PASS" if architecture_ok else "FAIL",
        "ARCHITECTURE_AUTHORITY": "PASS" if architecture_ok else "FAIL",
    }
    if not architecture_ok:
        ev.errors.extend(f"{c.name}: {c.detail}" for c in ev.checks if not c.ok)
    return ev


def evaluate_host_onsuccess(unit_onsuccess: Mapping[str, str]) -> tuple[int, list[str]]:
    """Count live OnSuccess couplings. Backup files are not live units."""
    coupled: list[str] = []
    for unit in CHAIN_UNITS:
        raw = str(unit_onsuccess.get(unit, "") or "").strip()
        if raw:
            coupled.append(f"{unit}={raw}")
    return len(coupled), coupled


def apply_host_readback(ev: PlaneEvaluation, unit_onsuccess: Mapping[str, str]) -> None:
    n, coupled = evaluate_host_onsuccess(unit_onsuccess)
    ev.tokens["HOST_ONSUCCESS_COUPLING"] = "ZERO" if n == 0 else str(n)
    ev.checks.append(Check("host_onsuccess_zero", n == 0, ";".join(coupled)))
    if n:
        ev.errors.append("host OnSuccess coupled: " + ";".join(coupled))
        ev.tokens["ARCHITECTURE_AUTHORITY"] = "FAIL"


# ---------------------------------------------------------------------------
# Campaign-plan linter
# ---------------------------------------------------------------------------

PROHIBITIVE = re.compile(
    r"(?i)\b(proibido|não\s+se\s+espera|nao\s+se\s+espera|must\s+not|do\s+not|"
    r"never|inválido|invalido|forbidden|não\s+aguardar|nao\s+aguardar|"
    r"não\s+tratar|nao\s+tratar|não\s+retomar|nao\s+retomar|"
    r"não\s+reutilizar|nao\s+reutilizar|incorreto)\b"
)

RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "wait_pncp_before_feed",
        re.compile(
            r"(?is)(aguardar|wait(?:\s+for)?|depois\s+que|após|apos).{0,80}"
            r"(pncp-contracts|pncp\s+(live|ficar|concluir|fresh)|fonte\s+ficar\s+FRESH)"
            r".{0,80}(feed|publicar|contact)"
        ),
    ),
    (
        "contact_pending_onsuccess",
        re.compile(r"(?i)CONTACT_DISCOVERY\s*=\s*PENDING_ONSUCCESS"),
    ),
    (
        "pending_onsuccess_state",
        re.compile(r"(?i)=\s*PENDING_ONSUCCESS\b"),
    ),
    (
        "seven_pncp_windows_gate",
        re.compile(
            r"(?is)(sete|7)\s+janelas?\s+PNCP.{0,80}(publicar|feed|contact|gate|então|entao)"
        ),
    ),
    (
        "pncp_feed_cascade",
        re.compile(
            r"(?i)PNCP\s*(→|->)\s*(gate\s*(→|->)\s*)?(reconcile\s*(→|->)\s*)?"
            r"(contact\s*(→|->)\s*)?feed"
        ),
    ),
    (
        "unqualified_source_run",
        re.compile(r"(?i)source run can[oô]nico(?!\s+(contemporâneo sobre o Data Lake|de ingestão PNCP|comercial))"),
    ),
    (
        "pncp_live_required_for_feed",
        re.compile(r"(?i)PNCP_LIVE_REQUIRED_FOR_FEED\s*=\s*YES"),
    ),
    (
        "resume_pr_528",
        re.compile(r"(?i)(retomar|reuse|reusar|rebasear)\s+(a\s+)?(branch\s+do\s+)?PR\s*#?528"),
    ),
    (
        "canary_satisfies_official",
        re.compile(
            r"(?is)can[aá]rio.{0,60}(satisfaz|satisfies|equivale|é o evento oficial|is the official)"
        ),
    ),
    (
        "queued_as_smtp",
        re.compile(r"(?i)QUEUED.{0,40}(SMTP|enviado|sent)|\bSMTP_SENT\s*=\s*QUEUED\b"),
    ),
    (
        "reuse_after_divergent_membership",
        re.compile(
            r"(?is)(reutilizar|reuse)\s+(snapshot|contact projection|proje[cç][aã]o).{0,80}"
            r"(membership\s+diverg|divergente)"
        ),
    ),
    (
        "pncp_fresh_required_for_contact",
        re.compile(
            r"(?i)(PNCP\s+FRESH|status\s*=\s*FRESH).{0,80}(contact discovery|CONTACT_DISCOVERY)"
        ),
    ),
)


ACTIVE_SCAN_GLOBS = (
    "docs/ops/confenge-commercial-plane-authority.md",
    "docs/contracts/confenge-commercial-plane/v1/**",
    "docs/architecture/confenge-commercial-plane-authority-matrix.md",
    "tests/fixtures/confenge_campaign_plans/**",
)


@dataclass
class PlanVerdict:
    path: str
    accepted: bool
    violations: list[str]
    historical: bool


def is_historical(text: str) -> bool:
    head = "\n".join(text.splitlines()[:40])
    return bool(_HISTORICAL_LABEL.search(head))


def classify_plan(text: str, *, path: str = "") -> PlanVerdict:
    historical = is_historical(text)
    if historical:
        return PlanVerdict(path=path, accepted=True, violations=[], historical=True)
    violations: list[str] = []
    for name, pattern in RULES:
        for match in pattern.finditer(text):
            start = max(0, match.start() - 500)
            snippet = text[start : match.end() + 80]
            if PROHIBITIVE.search(snippet):
                continue
            if re.search(
                r"(?i)(incorreto|o linter rejeita|terminologia proibida|"
                r"estado inválido|não significa|nao significa|"
                r"historical|superseded|supersedida)",
                snippet,
            ):
                continue
            violations.append(name)
            break
    return PlanVerdict(path=path, accepted=not violations, violations=violations, historical=False)


def iter_active_plan_files(root: Path, extra: Sequence[Path] = ()) -> list[Path]:
    files: list[Path] = []
    for pattern in ACTIVE_SCAN_GLOBS:
        files.extend(root.glob(pattern))
    files.extend(Path(p) if not isinstance(p, Path) else p for p in extra)
    out: list[Path] = []
    seen: set[Path] = set()
    for path in files:
        resolved = path.resolve() if path.exists() else path
        if resolved in seen or not path.is_file():
            continue
        seen.add(resolved)
        out.append(path)
    return out
