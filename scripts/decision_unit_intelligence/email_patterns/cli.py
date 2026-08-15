"""CLI for the isolated email_patterns engine."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from scripts.decision_unit_intelligence.email_patterns.engine import (
    InjectedTechnicalAdapter,
    run_email_patterns,
)
from scripts.decision_unit_intelligence.email_patterns.fixtures import (
    all_fixtures,
    audit_corpus_30,
)
from scripts.decision_unit_intelligence.email_patterns.types import (
    EmailPatternPolicy,
    EmailPatternResult,
    KnownPerson,
    ObservedPersonEmail,
)
from scripts.decision_unit_intelligence.models import EpistemicClass, dumps_stable, normalize_email
from scripts.decision_unit_intelligence.reachability import (
    email_domain,
    is_brand_mailbox,
    is_generic_mailbox,
    is_role_mailbox,
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _observed_from_payload(rows: Sequence[dict[str, Any]]) -> list[ObservedPersonEmail]:
    out: list[ObservedPersonEmail] = []
    for row in rows:
        epistemic_raw = str(row.get("epistemic_class") or EpistemicClass.OBSERVED.value)
        try:
            epistemic = EpistemicClass(epistemic_raw)
        except ValueError:
            epistemic = EpistemicClass.UNKNOWN
        out.append(
            ObservedPersonEmail(
                email=str(row.get("email") or ""),
                person_name=str(row.get("person_name") or ""),
                domain=str(row.get("domain") or email_domain(row.get("email")) or ""),
                source_url=row.get("source_url"),
                observed_at=row.get("observed_at"),
                epistemic_class=epistemic,
                person_id=row.get("person_id"),
                account_id=row.get("account_id"),
                source_type=str(row.get("source_type") or "public_page"),
            )
        )
    return out


def _people_from_payload(rows: Sequence[dict[str, Any]]) -> list[KnownPerson]:
    return [
        KnownPerson(
            person_name=str(row.get("person_name") or row.get("name") or ""),
            corroborated=bool(row.get("corroborated", True)),
            person_id=row.get("person_id"),
            account_id=row.get("account_id"),
            already_has_observed_email=bool(row.get("already_has_observed_email", False)),
        )
        for row in rows
        if row.get("person_name") or row.get("name")
    ]


def run_fixture_case(case: dict[str, Any]) -> EmailPatternResult:
    domain = case.get("domain")
    observed: list[ObservedPersonEmail] = list(case["observed"])
    people: list[KnownPerson] = list(case["known_people"])
    if domain:
        return run_email_patterns(
            observed=observed,
            known_people=people,
            domain=domain,
            technical=case.get("technical"),
        )
    # Multi-domain audit corpus: run per domain and merge.
    by_domain: dict[str, list[ObservedPersonEmail]] = {}
    for item in observed:
        by_domain.setdefault(item.domain, []).append(item)
    merged = EmailPatternResult(domain=None)
    patterns = []
    candidates = []
    ingested = []
    exclusions: list[str] = []
    for item_domain, rows in sorted(by_domain.items()):
        people_here = [person for person in people if (person.account_id or "") in {row.account_id for row in rows}]
        if not people_here:
            people_here = people
        result = run_email_patterns(
            observed=rows,
            known_people=people_here,
            domain=item_domain,
            technical=case.get("technical"),
        )
        ingested.extend(result.ingested)
        exclusions.extend(result.exclusions)
        patterns.extend(result.patterns)
        candidates.extend(result.candidates)
    merged.ingested = tuple(ingested)
    merged.exclusions = tuple(exclusions)
    merged.patterns = tuple(patterns)
    merged.candidates = tuple(candidates)
    merged.reason_codes = ("MULTI_DOMAIN_RUN",)
    return merged


def cmd_run(args: argparse.Namespace) -> int:
    payload = _load_json(Path(args.input))
    observed = _observed_from_payload(payload.get("observed") or [])
    people = _people_from_payload(payload.get("known_people") or [])
    policy_raw = payload.get("policy") or {}
    policy = EmailPatternPolicy(
        candidate_budget=int(policy_raw.get("candidate_budget") or 2),
        smtp_authorized=bool(policy_raw.get("smtp_authorized") or False),
    )
    technical = None
    tech_raw = payload.get("technical") or {}
    if tech_raw:
        technical = InjectedTechnicalAdapter(
            mx_by_domain=dict(tech_raw.get("mx_by_domain") or {}),
            catch_all_by_domain=dict(tech_raw.get("catch_all_by_domain") or {}),
            smtp_by_email=dict(tech_raw.get("smtp_by_email") or {}),
        )
    result = run_email_patterns(
        observed=observed,
        known_people=people,
        domain=payload.get("domain"),
        policy=policy,
        technical=technical,
    )
    text = dumps_stable(result.to_dict())
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def cmd_fixtures(args: argparse.Namespace) -> int:
    reports = []
    for case in all_fixtures():
        result = run_fixture_case(case)
        reports.append({"name": case["name"], "result": result.to_dict()})
    text = dumps_stable({"schema_id": "confenge.email_patterns.fixtures.v1", "cases": reports})
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def _parse_qsa_names(blob: str | None) -> list[str]:
    if not blob:
        return []
    names: list[str] = []
    for part in blob.split(";"):
        name = part.split("(", 1)[0].strip()
        if name and "ltda" not in name.lower() and "participac" not in name.lower():
            names.append(name)
    return names


def load_track_a_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = []
    for account in payload.get("accounts") or []:
        cnpj = str(account.get("cnpj") or "")
        email = normalize_email(account.get("email"))
        site = account.get("site") or account.get("fonte")
        domain = email_domain(email) if email else None
        if not domain and site:
            from urllib.parse import urlsplit

            host = (urlsplit(str(site)).hostname or "").lower().removeprefix("www.")
            domain = host or None
        names = _parse_qsa_names(account.get("qsa")) + _parse_qsa_names(account.get("qsa2"))
        observed: list[ObservedPersonEmail] = []
        if email and not (is_generic_mailbox(email) or is_role_mailbox(email) or is_brand_mailbox(email)):
            # Track A almost never binds a named person to the published mailbox.
            # Keep it only when a unique QSA name is encoded in the local-part.
            local = email.split("@", 1)[0]
            for name in names:
                folded = "".join(ch for ch in name.lower() if ch.isalpha())
                if folded and folded[:4] in local.replace(".", ""):
                    observed.append(
                        ObservedPersonEmail(
                            email=email,
                            person_name=name,
                            domain=domain or "",
                            source_url=account.get("fonte") or account.get("site"),
                            observed_at="2026-08-05T00:00:00Z",
                            account_id=cnpj,
                        )
                    )
                    break
        people = [
            KnownPerson(name, corroborated=True, account_id=cnpj, person_id=f"{cnpj}:{index}")
            for index, name in enumerate(names)
        ]
        cases.append(
            {
                "cnpj": cnpj,
                "legal_name": account.get("legal_name"),
                "domain": domain,
                "observed": observed,
                "known_people": people,
                "published_email": email,
            }
        )
    return cases


def summarize_results(results: Sequence[EmailPatternResult], *, persons_eligible: int) -> dict[str, Any]:
    patterns_strong = sum(
        1 for result in results for pattern in result.patterns if pattern.state.value == "PATTERN_STRONG"
    )
    patterns_ambiguous = sum(
        1 for result in results for pattern in result.patterns if pattern.state.value == "PATTERN_AMBIGUOUS"
    )
    candidates = [candidate for result in results for candidate in result.candidates]
    mx_ok = sum(1 for candidate in candidates if candidate.candidate_state.value == "INFERRED_PATTERN_MX_OK")
    catch_all = sum(1 for candidate in candidates if candidate.candidate_state.value == "INFERRED_PATTERN_CATCH_ALL")
    persons_with_candidate = len({(c.account_id, c.person_name) for c in candidates})
    incremental = round(persons_with_candidate / persons_eligible, 4) if persons_eligible else 0.0
    return {
        "persons_eligible": persons_eligible,
        "patterns_strong": patterns_strong,
        "patterns_ambiguous": patterns_ambiguous,
        "candidates": len(candidates),
        "mx_ok": mx_ok,
        "catch_all": catch_all,
        "false_positive": None,
        "false_positive_note": "human audit pending; no fabricated verdicts",
        "incremental_reachable_rate": incremental,
        "persons_with_candidate": persons_with_candidate,
    }


def cmd_canary(args: argparse.Namespace) -> int:
    observations = Path(args.observations)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    track_cases = load_track_a_cases(observations)
    track_results: list[EmailPatternResult] = []
    for case in track_cases:
        if not case["domain"]:
            track_results.append(
                EmailPatternResult(domain=None, reason_codes=("NO_DOMAIN",), exclusions=("NO_DOMAIN",))
            )
            continue
        track_results.append(
            run_email_patterns(
                observed=case["observed"],
                known_people=case["known_people"],
                domain=case["domain"],
                technical=InjectedTechnicalAdapter(
                    mx_by_domain={case["domain"]: "MX_PRESENT"},
                    catch_all_by_domain={case["domain"]: "UNKNOWN_NOT_PROBED"},
                ),
            )
        )
    track_eligible = sum(len(case["known_people"]) for case in track_cases)
    track_metrics = summarize_results(track_results, persons_eligible=track_eligible)

    audit = audit_corpus_30()
    audit_result = run_fixture_case(audit)
    fixture_metrics = summarize_results([audit_result], persons_eligible=len(audit["known_people"]))

    live_mx: dict[str, Any] = {"attempted": False, "error": None}
    if args.live_mx:
        try:
            from scripts.decision_unit_intelligence.email_patterns.engine import PassiveVerifierAdapter
            from scripts.decision_unit_intelligence.email_verification import DnspythonResolver, PassiveEmailVerifier

            adapter = PassiveVerifierAdapter(PassiveEmailVerifier(DnspythonResolver()))
            sample = next((c for c in audit_result.candidates if c.email), None)
            if sample:
                check = adapter.check(sample.email, smtp_authorized=False)
                live_mx = {"attempted": True, "error": None, "sample": check.to_dict()}
            else:
                live_mx = {"attempted": True, "error": "no_candidate_to_probe"}
        except Exception as exc:  # noqa: BLE001 — canary must record the failure, not invent MX
            live_mx = {"attempted": True, "error": f"{type(exc).__name__}: {exc}"}

    metrics = {
        "schema_id": "confenge.email_patterns.canary.v1",
        "cohort": "track_a_30",
        "track_a_30": track_metrics,
        "fixture_injected": fixture_metrics,
        "persons_eligible": track_metrics["persons_eligible"] + fixture_metrics["persons_eligible"],
        "patterns_strong": track_metrics["patterns_strong"] + fixture_metrics["patterns_strong"],
        "patterns_ambiguous": track_metrics["patterns_ambiguous"] + fixture_metrics["patterns_ambiguous"],
        "candidates": track_metrics["candidates"] + fixture_metrics["candidates"],
        "mx_ok": track_metrics["mx_ok"] + fixture_metrics["mx_ok"],
        "catch_all": track_metrics["catch_all"] + fixture_metrics["catch_all"],
        "false_positive": None,
        "incremental_reachable_rate": track_metrics["incremental_reachable_rate"],
        "live_mx": live_mx,
        "note": (
            "Track A 30 is the real 30/100 canary. Fixture-injected rows exist so MX/catch-all "
            "counters are produced by the shipped engine, not hand-typed."
        ),
    }
    (out_dir / "email-patterns-canary-metrics.json").write_text(dumps_stable(metrics) + "\n", encoding="utf-8")
    (out_dir / "email-patterns-canary-track-a.json").write_text(
        dumps_stable({"accounts": [result.to_dict() for result in track_results]}) + "\n",
        encoding="utf-8",
    )
    (out_dir / "email-patterns-canary-audit-candidates.json").write_text(
        dumps_stable(audit_result.to_dict()) + "\n", encoding="utf-8"
    )
    print(dumps_stable(metrics))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="email-patterns")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--input", required=True)
    run.add_argument("--out")
    run.set_defaults(func=cmd_run)
    fixtures = sub.add_parser("fixtures")
    fixtures.add_argument("--out")
    fixtures.set_defaults(func=cmd_fixtures)
    canary = sub.add_parser("canary")
    canary.add_argument(
        "--observations",
        default="scripts/decision_unit_intelligence/data/track_a_30.observations.json",
    )
    canary.add_argument("--out", required=True)
    canary.add_argument("--live-mx", action="store_true")
    canary.set_defaults(func=cmd_canary)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
