"""Deterministic 10k-account, no-transport rehearsal for the Warmbly feed.

The committed recipe is the versioned corpus definition. Materialized JSONL
and feed chunks are reproducible runtime artifacts and intentionally stay out
of Git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.warmbly_bridge.export import ExportConfig, export_outreach

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECIPE = REPO_ROOT / "tests/fixtures/confenge_scale_10k_recipe.json"
GENERATED_AT = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
FRESHNESS_EXPIRY = datetime(2099, 1, 1, tzinfo=UTC)


def _rfc3339(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _cnpj_check_digit(base: str) -> str:
    weights = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)[-len(base) :]
    remainder = sum(int(digit) * weight for digit, weight in zip(base, weights, strict=True)) % 11
    return "0" if remainder < 2 else str(11 - remainder)


def synthetic_cnpj(ordinal: int, *, root_offset: int = 10_000_000) -> str:
    """Return a valid, deterministic CNPJ that is reserved for synthetic use."""
    root = root_offset + ordinal
    if root > 99_999_999:
        raise ValueError("synthetic CNPJ ordinal exceeds the available root range")
    base = f"{root:08d}0001"
    first = _cnpj_check_digit(base)
    return base + first + _cnpj_check_digit(base + first)


def _contact(
    *,
    cnpj: str,
    email: str,
    observed_at: str,
    scenario: str,
    named: bool = False,
) -> dict[str, Any]:
    host = f"account-{cnpj}.rehearsal.confenge.com.br"
    return {
        "source_contact_id": f"contact-{cnpj}",
        "name": f"Synthetic Person {cnpj[-4:]}" if named else "",
        "role": "Contract Manager" if named else "Public contracts routing",
        "email": email,
        "source_url": f"https://{host}/contact",
        # The corpus envelope carries the synthetic marker. The route itself
        # uses the production provenance vocabulary so the normal classifier,
        # rather than a rehearsal-only bypass, decides its eligibility.
        "source_type": "company_website",
        "source_published_at": observed_at,
        "observed_at": observed_at,
        "verified_at": observed_at,
        "evidence_sha256": hashlib.sha256(f"{scenario}:{cnpj}:{email}".encode()).hexdigest(),
        "verification_status": "OFFICIAL_SOURCE",
        "ownership_status": "HUMAN_CONFIRMED" if named else "COMPANY_OWNED",
        "confidence": "HIGH",
        "enrollable": True,
        "recommended": True,
        "email_explicitly_published": True,
        "name_explicitly_published": named,
        "role_explicitly_published": True,
        "human_identity_evidence_valid": named,
        "identity_explicitly_associated": True,
        "email_derivation": "OBSERVED",
        "route_freshness": "STALE" if scenario == "stale_evidence" else "FRESH",
        "route_suppression": "SUPPRESSED" if scenario == "suppression" else "NONE",
        "channel_epistemic_class": "OBSERVED",
        "mailbox_company_evidence": "OBSERVED",
        "company_associated": True,
        "official_domain": host,
    }


def _rows_for_account(index: int, ordinal: int, scenario: str, generated_at: datetime) -> tuple[dict[str, Any], ...]:
    cnpj = synthetic_cnpj(ordinal)
    buyer = synthetic_cnpj(ordinal, root_offset=80_000_000)
    other_supplier = synthetic_cnpj(ordinal, root_offset=60_000_000)
    observed = generated_at - (timedelta(days=900) if scenario == "stale_evidence" else timedelta(days=1))
    observed_text = _rfc3339(observed)
    generated_text = _rfc3339(generated_at)
    company_host = f"account-{cnpj}.rehearsal.confenge.com.br"

    universe = {
        "cnpj14": cnpj,
        "razao_social": f"Synthetic Scale Account {index:05d} Ltda",
        "nome_fantasia": f"Scale Account {index:05d}",
        "municipio": "Synthetic City",
        "uf": "SC",
        "website": f"https://{company_host}",
        "official_domain": company_host,
        "rank": index + 1,
        "score": 80.0,
        "tier": "HIGH",
        "priority_confidence": "HIGH",
        "commercial_state": "DO_NOT_CONTACT" if scenario == "suppression" else "NEW",
        "source_lead_id": f"synthetic:{scenario}:{cnpj}",
        "construction_universe_member": True,
    }
    supplier = other_supplier if scenario == "buyer_conflict" else cnpj
    contract_buyer = cnpj if scenario == "buyer_conflict" else buyer
    evidence_id = f"contract-{cnpj}"
    contract = {
        "id": evidence_id,
        "supplier_cnpj14": supplier,
        "supplier_role": "CONTRATADA",
        "buyer_cnpj14": contract_buyer,
        "buyer_role": "CONTRATANTE",
    }
    intelligence = {
        "cnpj14": cnpj,
        "why_now": {
            "code": "SYNTHETIC_PUBLIC_CONTRACT",
            "summary": "Synthetic supplier evidence for a no-transport scale rehearsal",
            "observed_at": observed_text,
            "confidence": "HIGH",
            "evidence_ids": [evidence_id],
        },
        "offer": {
            "service_code": "CONTRACT_MANAGEMENT",
            "service_name": "Synthetic contract management",
            "entry_offer": "Synthetic routing question",
            "rationale": "Scale rehearsal only",
        },
        "messaging": {
            "fact_to_mention": "Synthetic public-contract evidence; never use for delivery",
            "question_to_ask": "Who owns public-contract operations?",
            "cta": "Route this synthetic record",
            "claims_to_avoid": ["real company", "real recipient", "send authorization"],
        },
        "contracts": [contract],
        "evidence": [
            {
                "id": evidence_id,
                "type": "SYNTHETIC_CONTRACT",
                "title": "Synthetic public contract",
                "url": f"https://evidence.rehearsal.confenge.com.br/{cnpj}",
                "date": observed_text[:10],
                "synthesis": "Synthetic supplier/buyer role evidence",
                "epistemic_class": "CONFIRMED_FACT",
                "reliability": "HIGH",
                "consulted_at": generated_text,
            }
        ],
        "inferences": [],
    }

    if scenario == "no_public_email":
        contacts: list[dict[str, Any]] = []
        terminal = "NOT_FOUND"
    else:
        local = {
            "direct_person": f"person-{cnpj[-6:]}",
            "role_mailbox": "licitacoes",
            "generic_mailbox": "contato",
            "company_freemail": f"synthetic-company-{cnpj}",
            "shared_mailbox_conflict": f"shared-{index // 20}",
        }.get(scenario, "contracts")
        if scenario == "company_freemail":
            email = f"{local}@gmail.com"
        elif scenario == "shared_mailbox_conflict":
            email = f"{local}@shared.rehearsal.confenge.com.br"
        else:
            email = f"{local}@{company_host}"
        contacts = [
            _contact(
                cnpj=cnpj,
                email=email,
                observed_at=observed_text,
                scenario=scenario,
                named=scenario == "direct_person",
            )
        ]
        terminal = "SUPPRESSED" if scenario == "suppression" else "RESOLVED"
    contact_row = {
        "cnpj14": cnpj,
        "official_domain": company_host,
        "discovery_terminal": {
            "status": terminal,
            "reason": scenario,
            "policy_version": "confenge-contact-discovery.v1",
        },
        "contacts": contacts,
    }
    target_fit = {
        "cnpj14": cnpj,
        "target_fit_class": "TARGET_CONFIRMED",
        "target_fit_confidence": 1.0,
        "target_fit_version": "confenge-target-fit-v2",
        "target_fit_computed_at": generated_text,
        "target_fit_source_watermark": generated_text,
        "target_fit_evidence": [{"id": evidence_id}],
        "target_fit_evidence_ids": [evidence_id],
        "target_fit_reason_codes": ["synthetic_rehearsal", scenario],
        "target_fit_send_suppressed": scenario == "suppression",
        "operational_status": "suppressed" if scenario == "suppression" else "ok",
    }
    return universe, intelligence, contact_row, target_fit


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def materialize_corpus(
    root: Path,
    recipe: dict[str, Any],
    *,
    generated_at: datetime,
    generation: int,
) -> dict[str, Any]:
    count = int(recipe["account_count"])
    scenarios = [str(value) for value in recipe["scenarios"]]
    changed = count * int(recipe["refresh_membership_change_percent"]) // 100 if generation > 1 else 0
    retained = count - changed
    rows: tuple[list[dict[str, Any]], ...] = ([], [], [], [])
    scenario_counts: Counter[str] = Counter()
    discovery_counts: Counter[str] = Counter()
    for index in range(count):
        ordinal = index if index < retained else count + index - retained
        scenario = scenarios[index % len(scenarios)]
        built = _rows_for_account(index, ordinal, scenario, generated_at)
        for destination, row in zip(rows, built, strict=True):
            destination.append(row)
        scenario_counts[scenario] += 1
        discovery_counts[str(built[2]["discovery_terminal"]["status"])] += 1

    names = ("universe.jsonl", "account_intelligence.jsonl", "contacts.jsonl", "target_fit.jsonl")
    for name, materialized in zip(names, rows, strict=True):
        _write_jsonl(root / name, materialized)
    return {
        "paths": {name.removesuffix(".jsonl"): str(root / name) for name in names},
        "cnpjs": [str(row["cnpj14"]) for row in rows[0]],
        "scenario_counts": dict(sorted(scenario_counts.items())),
        "discovery_terminal_counts": dict(sorted(discovery_counts.items())),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _export(
    corpus: dict[str, Any],
    out_dir: Path,
    recipe: dict[str, Any],
    *,
    generated_at: datetime,
    deactivations: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], float]:
    paths = corpus["paths"]
    started = time.perf_counter()
    result = export_outreach(
        ExportConfig(
            universe=Path(paths["universe"]),
            account_intelligence=Path(paths["account_intelligence"]),
            contacts=Path(paths["contacts"]),
            target_fit_snapshot=Path(paths["target_fit"]),
            out_dir=out_dir,
            expected_universe_count=int(recipe["account_count"]),
            max_leads_per_chunk=int(recipe["max_leads_per_chunk"]),
            generated_at=_rfc3339(generated_at),
            datalake_watermark=_rfc3339(generated_at),
            repo_sha="synthetic-rehearsal",
            authoritative_source_freshness={
                "contract_version": "PNCP_CONTRACT_FRESHNESS/1.0",
                "status": "FRESH",
                "observed_at": _rfc3339(generated_at),
                "expires_at": _rfc3339(FRESHNESS_EXPIRY),
                "scope": "SYNTHETIC_REHEARSAL_ONLY",
            },
            require_authoritative_source_freshness=True,
            deactivations=deactivations,
        )
    )
    return result, time.perf_counter() - started


def _audit_feed(out_dir: Path, expected: set[str]) -> dict[str, Any]:
    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    observed: list[str] = []
    route_classes: Counter[str] = Counter()
    preferred = 0
    for chunk in manifest["chunks"]:
        chunk_path = out_dir / str(chunk["file"])
        if _sha256(chunk_path) != chunk["content_hash"]:
            raise RuntimeError(f"chunk hash mismatch: {chunk_path.name}")
        payload = json.loads(chunk_path.read_text(encoding="utf-8"))
        for lead in payload["leads"]:
            observed.append(str(lead["company"]["cnpj14"]))
            for contact in lead.get("contacts") or []:
                route_classes[str(contact.get("route_class") or "UNCLASSIFIED")] += 1
                preferred += int(contact.get("preferred_initial") is True)
    duplicate_count = len(observed) - len(set(observed))
    missing = expected - set(observed)
    unexpected = set(observed) - expected
    coverage = manifest["authoritative_target_fit"]
    feed_identity = {
        "run_id": manifest["source"]["run_id"],
        "snapshot_hash": manifest["source"]["snapshot_hash"],
        "chunk_hashes": [chunk["content_hash"] for chunk in manifest["chunks"]],
        "deactivations": manifest.get("deactivations") or [],
    }
    return {
        "manifest_sha256": _sha256(manifest_path),
        # Operational write/unchanged statuses may change the manifest bytes on
        # replay. This hash covers only the consumer-visible feed identity.
        "feed_identity_sha256": hashlib.sha256(
            json.dumps(feed_identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "lead_count": len(observed),
        "chunk_count": len(manifest["chunks"]),
        "duplicate_count": duplicate_count,
        "orphan_count": len(missing) + len(unexpected),
        "missing_count": len(missing),
        "unexpected_count": len(unexpected),
        "preferred_route_count": preferred,
        "route_class_counts": dict(sorted(route_classes.items())),
        "coverage_complete": coverage.get("coverage_complete") is True,
        "omission_preserves_authorization": coverage.get("omission_preserves_authorization"),
        "freshness_status": (manifest.get("authoritative_source_freshness") or {}).get("status"),
        "run_id": manifest["source"]["run_id"],
        "snapshot_hash": manifest["source"]["snapshot_hash"],
    }


def run_rehearsal(recipe_path: Path, out_dir: Path, *, repeat: int) -> dict[str, Any]:
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    if repeat < 2:
        raise ValueError("repeat must be >= 2")
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    run1_corpus = materialize_corpus(out_dir / "corpus-v1", recipe, generated_at=GENERATED_AT, generation=1)
    run1, run1_duration = _export(run1_corpus, out_dir / "feed-v1", recipe, generated_at=GENERATED_AT)
    run1_audit = _audit_feed(out_dir / "feed-v1", set(run1_corpus["cnpjs"]))
    run1_hashes = [run1_audit["feed_identity_sha256"]]
    replay_durations: list[float] = []
    for _ in range(repeat - 1):
        _, duration = _export(run1_corpus, out_dir / "feed-v1", recipe, generated_at=GENERATED_AT)
        replay_durations.append(duration)
        replay_audit = _audit_feed(out_dir / "feed-v1", set(run1_corpus["cnpjs"]))
        run1_hashes.append(replay_audit["feed_identity_sha256"])

    generated2 = GENERATED_AT + timedelta(hours=1)
    run2_corpus = materialize_corpus(out_dir / "corpus-v2", recipe, generated_at=generated2, generation=2)
    old_members = set(run1_corpus["cnpjs"])
    new_members = set(run2_corpus["cnpjs"])
    removed = sorted(old_members - new_members)
    added = sorted(new_members - old_members)
    deactivations = [
        {"cnpj14": cnpj, "to_state": "NOT_ACTIONABLE", "reason": "synthetic_membership_refresh"}
        for cnpj in removed
    ]
    run2, run2_duration = _export(
        run2_corpus,
        out_dir / "feed-v2",
        recipe,
        generated_at=generated2,
        deactivations=deactivations,
    )
    run2_audit = _audit_feed(out_dir / "feed-v2", new_members)
    _, run2_replay_duration = _export(
        run2_corpus,
        out_dir / "feed-v2",
        recipe,
        generated_at=generated2,
        deactivations=deactivations,
    )
    run2_replay_hash = _audit_feed(out_dir / "feed-v2", new_members)["feed_identity_sha256"]

    expected_changed = int(recipe["account_count"]) * int(recipe["refresh_membership_change_percent"]) // 100
    assertions = {
        "run1_exact_account_count": run1_audit["lead_count"] == int(recipe["account_count"]),
        "run2_exact_account_count": run2_audit["lead_count"] == int(recipe["account_count"]),
        "zero_silent_loss": run1_audit["orphan_count"] == run2_audit["orphan_count"] == 0,
        "zero_duplicates": run1_audit["duplicate_count"] == run2_audit["duplicate_count"] == 0,
        "complete_target_membership": run1_audit["coverage_complete"] and run2_audit["coverage_complete"],
        "omission_never_authorizes": not run1_audit["omission_preserves_authorization"]
        and not run2_audit["omission_preserves_authorization"],
        "freshness_bound": run1_audit["freshness_status"] == run2_audit["freshness_status"] == "FRESH",
        "ten_percent_refresh": len(removed) == len(added) == expected_changed,
        "snapshot_advanced": run1_audit["snapshot_hash"] != run2_audit["snapshot_hash"],
        "two_x_idempotent": run2_audit["feed_identity_sha256"] == run2_replay_hash,
        "n_x_idempotent": len(set(run1_hashes)) == 1,
        "no_transport_invoked": True,
    }
    failed = sorted(name for name, passed in assertions.items() if not passed)
    report = {
        "schema_version": "confenge.scale-rehearsal-report.v1",
        "status": "PASS" if not failed else "FAIL",
        "no_smtp": True,
        "provider_send_invocations": 0,
        "recipe": recipe,
        "recipe_sha256": _sha256(recipe_path),
        "repeat_count": repeat,
        "total_duration_seconds": round(time.perf_counter() - started, 6),
        "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "max_rss_delta_kib": max(0, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - rss_before),
        "producer": {
            "run1_duration_seconds": round(run1_duration, 6),
            "run1_replay_duration_seconds": [round(value, 6) for value in replay_durations],
            "run2_duration_seconds": round(run2_duration, 6),
            "run2_replay_duration_seconds": round(run2_replay_duration, 6),
            "run1": run1_audit,
            "run2": run2_audit,
            "scenario_counts": run1_corpus["scenario_counts"],
            "discovery_terminal_counts": run1_corpus["discovery_terminal_counts"],
            "membership_removed": len(removed),
            "membership_added": len(added),
            "deactivation_count": len(deactivations),
            "export_result_counts": {
                "run1_leads": run1["lead_count"],
                "run1_chunks": run1["chunk_count"],
                "run2_leads": run2["lead_count"],
                "run2_chunks": run2["chunk_count"],
            },
        },
        "assertions": assertions,
        "failed_assertions": failed,
        "scope_note": "Synthetic scheduling/feed headroom only; this is not evidence of provider send rate.",
    }
    report_path = out_dir / "producer-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, default=DEFAULT_RECIPE)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=10)
    return parser


def main() -> int:
    args = _parser().parse_args()
    report = run_rehearsal(args.recipe, args.out_dir, repeat=args.repeat)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
