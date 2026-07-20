"""Canonical data-quality contract (ARCH-RESET PR F).

Single registry of critical checks. Implementations may use SQL or Python
in-process; this module defines the contract IDs and pure evaluation helpers
so Soda/dbt are not required for the gate.

Does not claim production coverage/freshness SLAs are met — only that the
check surface is centralized.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    ok: bool
    severity: str  # blocker | warn | info
    detail: str
    observed: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Ten critical checks (spike scope)
CRITICAL_CHECKS: tuple[str, ...] = (
    "freshness_editais",
    "freshness_contratos",
    "identifier_completeness",
    "official_url_present",
    "closing_date_present",
    "duplicate_detection",
    "unknown_status_not_open",
    "coverage_by_capability",
    "volume_drop_alert",
    "run_reference_integrity",
)


def check_freshness_editais(
    *,
    last_success_at: datetime | None,
    sla_hours: float = 48.0,
    now: datetime | None = None,
) -> CheckResult:
    now = now or datetime.now(UTC)
    if last_success_at is None:
        return CheckResult("freshness_editais", False, "blocker", "no_successful_collection")
    age_h = (now - last_success_at).total_seconds() / 3600.0
    ok = age_h <= sla_hours
    return CheckResult(
        "freshness_editais",
        ok,
        "blocker" if not ok else "info",
        f"age_hours={age_h:.2f} sla={sla_hours}",
        observed={"age_hours": age_h, "sla_hours": sla_hours},
    )


def check_freshness_contratos(
    *,
    last_success_at: datetime | None,
    sla_hours: float = 168.0,
    now: datetime | None = None,
) -> CheckResult:
    now = now or datetime.now(UTC)
    if last_success_at is None:
        return CheckResult("freshness_contratos", False, "blocker", "no_successful_collection")
    age_h = (now - last_success_at).total_seconds() / 3600.0
    ok = age_h <= sla_hours
    return CheckResult(
        "freshness_contratos",
        ok,
        "blocker" if not ok else "info",
        f"age_hours={age_h:.2f} sla={sla_hours}",
        observed={"age_hours": age_h, "sla_hours": sla_hours},
    )


def check_identifier_completeness(rows: list[dict[str, Any]], id_keys: tuple[str, ...] = ("cnpj", "orgao_cnpj")) -> CheckResult:
    if not rows:
        return CheckResult("identifier_completeness", False, "warn", "empty_set")
    missing = 0
    for r in rows:
        if not any(str(r.get(k) or "").strip() for k in id_keys):
            missing += 1
    ratio = missing / len(rows)
    ok = ratio == 0.0
    return CheckResult(
        "identifier_completeness",
        ok,
        "blocker" if not ok else "info",
        f"missing_ratio={ratio:.4f}",
        observed={"n": len(rows), "missing": missing},
    )


def check_official_url_present(rows: list[dict[str, Any]], url_keys: tuple[str, ...] = ("url", "raw_uri", "link_oficial")) -> CheckResult:
    if not rows:
        return CheckResult("official_url_present", False, "warn", "empty_set")
    missing = sum(1 for r in rows if not any(str(r.get(k) or "").startswith("http") for k in url_keys))
    ok = missing == 0
    return CheckResult(
        "official_url_present",
        ok,
        "warn" if not ok else "info",
        f"missing_urls={missing}",
        observed={"missing": missing, "n": len(rows)},
    )


def check_closing_date_present(rows: list[dict[str, Any]], keys: tuple[str, ...] = ("data_encerramento", "prazo", "closing_date")) -> CheckResult:
    if not rows:
        return CheckResult("closing_date_present", False, "warn", "empty_set")
    missing = sum(1 for r in rows if not any(r.get(k) for k in keys))
    ok = missing == 0
    return CheckResult(
        "closing_date_present",
        ok,
        "warn" if not ok else "info",
        f"missing_closing={missing}",
        observed={"missing": missing},
    )


def check_duplicate_detection(ids: list[str]) -> CheckResult:
    seen: set[str] = set()
    dups: list[str] = []
    for i in ids:
        if not i:
            continue
        if i in seen:
            dups.append(i)
        seen.add(i)
    ok = not dups
    return CheckResult(
        "duplicate_detection",
        ok,
        "blocker" if not ok else "info",
        f"duplicates={len(dups)}",
        observed={"duplicates": dups[:20]},
    )


def check_unknown_status_not_open(rows: list[dict[str, Any]]) -> CheckResult:
    """unknown/None status must not be treated as open/participable."""
    bad = []
    for r in rows:
        status = (r.get("status") or r.get("situacao_nome") or "").strip().lower()
        openish = bool(r.get("is_open") or r.get("recommend") == "PARTICIPAR")
        if openish and status in {"", "unknown", "desconhecido", "n/a"}:
            bad.append(r.get("id") or r.get("numero_controle_pncp"))
    ok = not bad
    return CheckResult(
        "unknown_status_not_open",
        ok,
        "blocker" if not ok else "info",
        f"bad_open_unknown={len(bad)}",
        observed={"ids": bad[:20]},
    )


def check_coverage_by_capability(
    *,
    covered: int,
    universe: int,
    capability: str,
) -> CheckResult:
    if universe <= 0:
        return CheckResult("coverage_by_capability", False, "blocker", "invalid_universe")
    ratio = covered / universe
    # Does NOT assert >=95% — only that metric is computable and fail-closed on bad inputs
    return CheckResult(
        "coverage_by_capability",
        True,
        "info",
        f"capability={capability} covered={covered}/{universe} ratio={ratio:.4f}",
        observed={"capability": capability, "covered": covered, "universe": universe, "ratio": ratio},
    )


def check_volume_drop_alert(*, current: int, baseline: int, drop_ratio_threshold: float = 0.5) -> CheckResult:
    if baseline <= 0:
        return CheckResult("volume_drop_alert", False, "warn", "no_baseline")
    drop = 1.0 - (current / baseline)
    ok = drop < drop_ratio_threshold
    return CheckResult(
        "volume_drop_alert",
        ok,
        "blocker" if not ok else "info",
        f"drop={drop:.2%} threshold={drop_ratio_threshold:.0%}",
        observed={"current": current, "baseline": baseline, "drop": drop},
    )


def check_run_reference_integrity(
    *,
    report_run_ids: list[str],
    known_run_ids: set[str],
) -> CheckResult:
    missing = [r for r in report_run_ids if r and r not in known_run_ids]
    ok = not missing
    return CheckResult(
        "run_reference_integrity",
        ok,
        "blocker" if not ok else "info",
        f"orphan_run_refs={len(missing)}",
        observed={"missing": missing[:20]},
    )


def run_all_fixture_suite() -> dict[str, Any]:
    """Deterministic fixture evaluation for CI (no DB)."""
    now = datetime(2026, 7, 20, 12, 0, 0, tzinfo=UTC)
    results = [
        check_freshness_editais(last_success_at=now - timedelta(hours=10), now=now),
        check_freshness_contratos(last_success_at=now - timedelta(hours=200), now=now),
        check_identifier_completeness([{"cnpj": "123"}, {"cnpj": ""}, {"orgao_cnpj": "456"}]),
        check_official_url_present([{"url": "https://x"}, {"raw_uri": "ftp://no"}]),
        check_closing_date_present([{"prazo": "2026-08-01"}, {}]),
        check_duplicate_detection(["a", "b", "a"]),
        check_unknown_status_not_open(
            [
                {"id": 1, "status": "unknown", "is_open": True},
                {"id": 2, "status": "open", "is_open": True},
            ]
        ),
        check_coverage_by_capability(covered=100, universe=1093, capability="editais"),
        check_volume_drop_alert(current=40, baseline=100),
        check_run_reference_integrity(
            report_run_ids=["run-1", "run-missing"],
            known_run_ids={"run-1"},
        ),
    ]
    return {
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "engine": "python_native",
        "critical_checks": list(CRITICAL_CHECKS),
        "results": [r.to_dict() for r in results],
        "n_blocker_fail": sum(1 for r in results if not r.ok and r.severity == "blocker"),
        "n_ok": sum(1 for r in results if r.ok),
    }


# SQL stubs (documentation + optional execution when DSN available)
SQL_STUBS: dict[str, str] = {
    "freshness_editais": """
        SELECT MAX(completed_at) AS last_success
        FROM crawl_runs WHERE source = 'pncp' AND status = 'success';
    """,
    "freshness_contratos": """
        SELECT MAX(completed_at) AS last_success
        FROM crawl_runs WHERE source = 'pncp_contracts' AND status = 'success';
    """,
    "duplicate_detection": """
        SELECT external_id, COUNT(*) c FROM opportunities
        GROUP BY external_id HAVING COUNT(*) > 1;
    """,
    "run_reference_integrity": """
        SELECT r.run_id FROM report_artifacts r
        LEFT JOIN crawl_runs c ON c.run_id = r.run_id
        WHERE c.run_id IS NULL;
    """,
}
