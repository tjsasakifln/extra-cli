"""Path-based confenge.outreach.v1 exporter with deterministic chunking + manifest."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.confenge_outreach_pipeline.party_role import (
    PARTY_ROLE_CONFLICT,
    PARTY_ROLE_POLICY_V1,
    project_contractor_role,
)
from scripts.confenge_target_fit.company_key import (
    TARGET_MEMBERSHIP_IDENTITY_KEY,
    canonical_target_membership,
)
from scripts.confenge_target_fit.published import build_published_index_from_rows
from scripts.crawl.run_evidence import runtime_release_sha
from scripts.decision_unit_intelligence.controlled_email import (
    CONTROLLED_EMAIL_POLICY_VERSION,
    apply_cross_account_preferred_mailbox_gate,
    canonicalize_mailbox,
)
from scripts.warmbly_bridge import (
    DEFAULT_MAX_BYTES_PER_CHUNK,
    DEFAULT_MAX_LEADS_PER_CHUNK,
    DEFAULT_PROFILE_ID,
    DEFAULT_PROFILE_VERSION,
    DEFAULT_SYSTEM,
    MODULE_VERSION,
    SCHEMA_OUTREACH,
)
from scripts.warmbly_bridge.io_jsonl import InputError, content_hash_obj, read_jsonl, require_readable_file
from scripts.warmbly_bridge.mapping import build_leads, normalize_cnpj14

TARGET_CONFIRMED = "TARGET_CONFIRMED"

# The published feed carries the current TARGET_CONFIRMED outreach population,
# one lead per canonical ``cnpj_root8``. The full decision universe stays the
# authoritative extra-cli record and is accounted for in the manifest, but it is
# not shipped: Warmbly imports the feed as the actionable population itself.
FEED_SCOPE = "TARGET_CONFIRMED_MEMBERSHIP"
FEED_MEMBERSHIP_SCHEMA = "confenge.outreach.feed_membership.v1"
FEED_MEMBERSHIP_FILENAME = "membership.json"

# Consumer import ceilings, mirrored from Warmbly's feed_sync validation. They
# are fail-closed guards, never truncation limits: a feed above them must abort
# the run so a human reconciles the population.
CONSUMER_MAX_LEADS = 100_000
CONSUMER_MAX_CHUNKS = 1_000
CONSUMER_MAX_BYTES_PER_CHUNK = 512_000
CONSUMER_MAX_STAGED_BYTES = 1_073_741_824

# Warmbly rejects a deactivation targeting ACTIONABLE_NOW.
DEACTIVATION_STATES = ("RESEARCH_REQUIRED", "SUPPRESSED", "WATCH")
MEMBERSHIP_DROP_REASON = "TARGET_CONFIRMED_MEMBERSHIP_DROPPED"


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _git_sha() -> str:
    import shutil

    if release_sha := runtime_release_sha():
        return release_sha
    git_bin = shutil.which("git")
    if not git_bin:
        return "unknown"
    try:
        out = subprocess.check_output(  # noqa: S603 — absolute git path, fixed argv
            [git_bin, "-C", str(Path(__file__).resolve().parents[2]), "rev-parse", "--short=12", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return out.strip() or "unknown"
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return "unknown"


def _snapshot_hash(
    universe: Path,
    intel: Path,
    contacts: Path,
    target_fit: Path | None,
    contact_projection_report: Path | None,
) -> str:
    h = hashlib.sha256()
    for p in (universe, intel, contacts, target_fit):
        if p is None:
            continue
        h.update(p.name.encode())
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    if contact_projection_report is not None:
        try:
            report = json.loads(contact_projection_report.read_bytes())
        except (OSError, json.JSONDecodeError) as exc:
            raise InputError(f"invalid authoritative contact projection report: {contact_projection_report}") from exc
        if not isinstance(report, dict):
            raise InputError("authoritative contact projection report must be a JSON object")
        # Operational run labels and clocks are evidence, not new business data.
        # Keep their raw SHA in the manifest, but exclude them from the source
        # snapshot so an identical projection cannot manufacture freshness.
        semantic_report = {
            key: value
            for key, value in report.items()
            if key
            not in {
                "generated_at",
                "cohort_id",
                "code_sha",
                "durable_reconciliation",
            }
        }
        h.update(contact_projection_report.name.encode())
        h.update(b"\0")
        h.update(
            json.dumps(
                semantic_report,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        )
        h.update(b"\0")
    return h.hexdigest()


def _run_id(
    snapshot_hash: str,
    profile_id: str,
    profile_version: str,
    authoritative_freshness_hash: str | None = None,
) -> str:
    raw = (
        f"{snapshot_hash}|{profile_id}|{profile_version}|{MODULE_VERSION}|"
        f"{authoritative_freshness_hash or 'no-source-freshness'}"
    )
    return "run-" + hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class ExportConfig:
    universe: Path
    account_intelligence: Path
    contacts: Path
    out_dir: Path
    target_fit_snapshot: Path | None = None
    contact_projection_report: Path | None = None
    expected_universe_count: int | None = None
    limit: int | None = None
    max_leads_per_chunk: int = DEFAULT_MAX_LEADS_PER_CHUNK
    max_bytes_per_chunk: int = DEFAULT_MAX_BYTES_PER_CHUNK
    profile_id: str = DEFAULT_PROFILE_ID
    profile_version: str = DEFAULT_PROFILE_VERSION
    system: str = DEFAULT_SYSTEM
    generated_at: str | None = None  # inject for deterministic tests
    datalake_watermark: str | None = None
    require_authoritative_target_fit_metadata: bool = True
    require_authoritative_contact_projection_metadata: bool = False
    repo_sha: str | None = None
    authoritative_source_freshness: dict[str, Any] | None = None
    require_authoritative_source_freshness: bool = False
    # Delta deactivations for accounts leaving ACTIONABLE_NOW (manifest section)
    deactivations: list[dict[str, Any]] | None = None
    # Previously published feed release (``<publish_dir>/current``). Accounts that
    # were shipped there and are no longer TARGET_CONFIRMED members become
    # explicit deactivations instead of silently vanishing from the feed.
    previous_feed_dir: Path | None = None


def validate_inputs(cfg: ExportConfig) -> None:
    """Fail-closed: all three required inputs must exist and be readable."""
    require_readable_file(cfg.universe, label="--universe")
    require_readable_file(cfg.account_intelligence, label="--account-intelligence")
    require_readable_file(cfg.contacts, label="--contacts")
    if cfg.target_fit_snapshot is not None:
        require_readable_file(cfg.target_fit_snapshot, label="--target-fit-snapshot")
    if cfg.contact_projection_report is not None:
        require_readable_file(cfg.contact_projection_report, label="--contact-projection-report")
    elif cfg.require_authoritative_contact_projection_metadata:
        raise InputError("--contact-projection-report is required for authoritative publication")
    if cfg.max_leads_per_chunk < 1:
        raise InputError("--max-leads-per-chunk must be >= 1")
    if cfg.max_bytes_per_chunk < 1024:
        raise InputError("--max-bytes-per-chunk must be >= 1024")
    if cfg.max_bytes_per_chunk > CONSUMER_MAX_BYTES_PER_CHUNK:
        raise InputError(
            "--max-bytes-per-chunk exceeds the consumer ceiling: "
            f"configured={cfg.max_bytes_per_chunk} max={CONSUMER_MAX_BYTES_PER_CHUNK}"
        )
    if cfg.expected_universe_count is not None and cfg.expected_universe_count < 1:
        raise InputError("--expected-universe-count must be >= 1")
    # PNCP freshness is acquisition telemetry and never authorises or blocks an
    # export. `require_authoritative_source_freshness` now only demands that the
    # telemetry envelope be present and well-formed, so a shipped manifest still
    # records what the source was doing without ever fabricating FRESH.
    freshness = cfg.authoritative_source_freshness or {}
    if cfg.require_authoritative_source_freshness and freshness.get("contract_version") != (
        "PNCP_CONTRACT_FRESHNESS/1.0"
    ):
        raise InputError("source operational health envelope missing or unsupported")


def _encode_chunk(feed: dict[str, Any]) -> bytes:
    # Canonical serialization for stable content hashes (resume/idempotency).
    text = json.dumps(feed, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
    return text.encode("utf-8")


def _encoded_lead_item_size(lead: dict[str, Any]) -> int:
    """Exact byte contribution of one lead inside an indented ``leads`` array."""
    raw = json.dumps(lead, ensure_ascii=False, indent=2, sort_keys=True, default=str).encode("utf-8")
    # ``leads`` is a top-level value, so every line of each array item is
    # shifted four spaces relative to the standalone representation.
    return len(raw) + 4 * (raw.count(b"\n") + 1)


_CHUNK_HASH_PLACEHOLDER = "0" * 64


def _provisional_chunk_size(
    *,
    lead_item_bytes: int,
    lead_count: int,
    source: dict[str, Any],
    generated_at: str,
    cursor: str,
    chunk_index: int,
    next_cursor: str | None = None,
    snapshot_hash: str | None = None,
) -> int:
    """Measure a provisional chunk in O(1) after each lead is encoded once.

    The estimate must be at least as large as the bytes later written by
    ``_encode_chunk``. Production pagination adds 64-char content hashes after
    packing; omitting them under-counted a live chunk by 51 bytes (512051 >
    512000) and aborted publication.
    """
    digest = (snapshot_hash or _CHUNK_HASH_PLACEHOLDER).ljust(64, "0")[:64]
    envelope = {
        "schema_version": SCHEMA_OUTREACH,
        "generated_at": generated_at,
        "source": source,
        "pagination": {
            "chunk_index": chunk_index,
            "content_hash": _CHUNK_HASH_PLACEHOLDER,
            "cursor": cursor,
            "has_more": next_cursor is not None,
            "hashes": {
                "leads": _CHUNK_HASH_PLACEHOLDER,
                "snapshot": digest,
            },
            "next_cursor": next_cursor,
        },
        "leads": [],
    }
    empty_size = len(_encode_chunk(envelope))
    if lead_count == 0:
        return empty_size
    # Replace the two bytes of ``[]`` with the exact pretty-printed array:
    # "[\n" + indented items joined by ",\n" + "\n  ]".
    array_size = 2 + lead_item_bytes + (2 * (lead_count - 1)) + 4
    return empty_size - 2 + array_size


def _decision_cursor(lead: dict[str, Any]) -> str:
    return "|".join(
        (
            str(lead.get("target_fit_source_watermark") or ""),
            str(lead.get("target_fit_computed_at") or ""),
            str((lead.get("company") or {}).get("cnpj14") or ""),
        )
    )


def _preferred_route_claims(rows: list[dict[str, Any]], *, feed_leads: bool) -> set[tuple[str, str]]:
    """Return identity-bound preferred routes without exposing them in metrics."""

    claims: set[tuple[str, str]] = set()
    for row in rows:
        company = row.get("company") if feed_leads and isinstance(row.get("company"), dict) else row
        cnpj = normalize_cnpj14(str(company.get("cnpj14") or company.get("cnpj") or ""))
        if not cnpj:
            continue
        declared = row.get("preferred_email_route")
        if isinstance(declared, dict):
            mailbox = canonicalize_mailbox(str(declared.get("email") or ""))
            if mailbox:
                claims.add((cnpj, mailbox))
        for contact in row.get("contacts") or []:
            if not isinstance(contact, dict) or contact.get("preferred_initial") is not True:
                continue
            mailbox = canonicalize_mailbox(str(contact.get("email") or ""))
            if mailbox:
                claims.add((cnpj, mailbox))
    return claims


def _reconcile_preferred_route_projection(
    contact_rows: list[dict[str, Any]],
    leads: list[dict[str, Any]],
    *,
    full_snapshot: bool,
) -> dict[str, Any]:
    """Reconcile output against the same identity policy used by the mapper."""

    target_accounts = {
        normalize_cnpj14(str((lead.get("company") or {}).get("cnpj14") or ""))
        for lead in leads
        if str(lead.get("target_fit_class") or "") == "TARGET_CONFIRMED"
    }
    raw_expected = _preferred_route_claims(contact_rows, feed_leads=False)
    policy_input = [
        {
            "source_lead_id": normalize_cnpj14(str(row.get("cnpj14") or row.get("cnpj") or "")),
            "company": {"cnpj14": normalize_cnpj14(str(row.get("cnpj14") or row.get("cnpj") or ""))},
            "contacts": row.get("contacts") or [],
        }
        for row in contact_rows
        if normalize_cnpj14(str(row.get("cnpj14") or row.get("cnpj") or ""))
    ]
    normalized_rows = apply_cross_account_preferred_mailbox_gate(
        policy_input,
        require_account_identity_evidence=True,
    )
    shared_mailbox_expected = _preferred_route_claims(normalized_rows, feed_leads=True)
    party_role_blocked_accounts = {
        normalize_cnpj14(str((lead.get("company") or {}).get("cnpj14") or ""))
        for lead in leads
        if str((lead.get("contractor_role") or {}).get("target_party_role") or "") == "BUYER_CONFLICT"
    }
    expected = {claim for claim in shared_mailbox_expected if claim[0] not in party_role_blocked_accounts}
    observed = _preferred_route_claims(leads, feed_leads=True)
    raw_expected = {claim for claim in raw_expected if claim[0] in target_accounts}
    shared_mailbox_expected = {claim for claim in shared_mailbox_expected if claim[0] in target_accounts}
    expected = {claim for claim in expected if claim[0] in target_accounts}
    observed = {claim for claim in observed if claim[0] in target_accounts}
    if not full_snapshot:
        output_accounts = {normalize_cnpj14(str((lead.get("company") or {}).get("cnpj14") or "")) for lead in leads}
        raw_expected = {claim for claim in raw_expected if claim[0] in output_accounts}
        shared_mailbox_expected = {claim for claim in shared_mailbox_expected if claim[0] in output_accounts}
        expected = {claim for claim in expected if claim[0] in output_accounts}
    raw_expected_hash = content_hash_obj(sorted(raw_expected))
    expected_hash = content_hash_obj(sorted(expected))
    observed_hash = content_hash_obj(sorted(observed))
    if raw_expected and expected != observed:
        raise InputError(
            "preferred route projection does not reconcile with generated feed: "
            f"input={len(expected)} output={len(observed)} "
            f"missing={len(expected - observed)} unexpected={len(observed - expected)} "
            f"input_hash={expected_hash} output_hash={observed_hash}"
        )
    raw_accounts = {account for account, _mailbox in raw_expected}
    shared_mailbox_accounts = {account for account, _mailbox in shared_mailbox_expected}
    expected_accounts = {account for account, _mailbox in expected}
    observed_accounts = {account for account, _mailbox in observed}
    output_route_classes: Counter[str] = Counter()
    for lead in leads:
        company = lead.get("company") if isinstance(lead.get("company"), dict) else {}
        if normalize_cnpj14(str(company.get("cnpj14") or "")) not in target_accounts:
            continue
        for contact in lead.get("contacts") or []:
            if isinstance(contact, dict) and contact.get("preferred_initial") is True:
                output_route_classes[str(contact.get("route_class") or "UNKNOWN")] += 1
    return {
        "input_declared": bool(raw_expected),
        "scope": "FULL_INPUT" if full_snapshot else "OUTPUT_SLICE",
        "projection_policy_version": CONTROLLED_EMAIL_POLICY_VERSION,
        "raw_input_preferred_route_count": len(raw_expected),
        "raw_input_preferred_account_count": len(raw_accounts),
        "raw_input_preferred_routes_hash": raw_expected_hash,
        "shared_mailbox_excluded_preferred_route_count": len(raw_expected - shared_mailbox_expected),
        "shared_mailbox_excluded_account_count": len(raw_accounts - shared_mailbox_accounts),
        "party_role_excluded_preferred_route_count": len(shared_mailbox_expected - expected),
        "party_role_excluded_account_count": len(shared_mailbox_accounts - expected_accounts),
        "policy_excluded_preferred_route_count": len(raw_expected - expected),
        "policy_excluded_account_count": len(raw_accounts - expected_accounts),
        "input_preferred_route_count": len(expected),
        "output_preferred_route_count": len(observed),
        "input_preferred_account_count": len(expected_accounts),
        "output_preferred_account_count": len(observed_accounts),
        "output_preferred_route_class_distribution": dict(sorted(output_route_classes.items())),
        "preferred_routes_reconciled": expected == observed if raw_expected else None,
        "input_preferred_routes_hash": expected_hash,
        "output_preferred_routes_hash": observed_hash,
    }


def _read_contact_projection_report(path: Path | None) -> tuple[dict[str, Any], str | None]:
    if path is None:
        return {}, None
    try:
        raw = path.read_bytes()
        report = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"invalid authoritative contact projection report: {path}") from exc
    if not isinstance(report, dict):
        raise InputError("authoritative contact projection report must be a JSON object")
    return report, hashlib.sha256(raw).hexdigest()


def _authoritative_contact_projection(
    preferred_routes: dict[str, Any],
    report: dict[str, Any],
    *,
    report_hash: str | None,
    target_membership: dict[str, Any],
    contact_rows: list[dict[str, Any]],
    required: bool,
) -> dict[str, Any]:
    if not report:
        if required:
            raise InputError("authoritative contact projection report is required")
        return preferred_routes
    if report.get("schema_id") != "confenge.contact_discovery.projection_report.v1":
        raise InputError("unsupported authoritative contact projection report schema")
    required_metadata = (
        "cohort_id",
        "generated_at",
        "population_hash",
        "population_as_of",
        "projection_hash",
        "controlled_email_policy_version",
        "policy_version",
        "input_evidence_version",
        "code_sha",
    )
    missing_metadata = [field for field in required_metadata if not str(report.get(field) or "").strip()]
    if missing_metadata:
        raise InputError(f"contact projection report is missing versioned source metadata: {missing_metadata}")
    _parse_timestamp(report["generated_at"], field="contact_projection.generated_at", cnpj="authoritative-projection")
    _parse_timestamp(
        report["population_as_of"], field="contact_projection.population_as_of", cnpj="authoritative-projection"
    )
    terminal_equation = report.get("terminal_equation")
    terminal_equation = terminal_equation if isinstance(terminal_equation, dict) else {}
    if report.get("terminal_coverage_complete") is not True or terminal_equation.get("holds") is not True:
        raise InputError("contact projection terminal coverage is incomplete")
    if report.get("membership_contract_matches_population") is not True:
        raise InputError("contact projection membership does not match its population contract")
    raw_population_coverage_ratio = report.get("population_coverage_ratio")
    if isinstance(raw_population_coverage_ratio, bool) or not isinstance(
        raw_population_coverage_ratio, (int, float)
    ):
        raise InputError("contact projection population_coverage_ratio is missing or invalid")
    try:
        population_coverage_ratio = float(raw_population_coverage_ratio)
    except (TypeError, ValueError) as exc:
        raise InputError("contact projection population_coverage_ratio is missing or invalid") from exc
    if (
        report.get("population_publication_ready") is not True
        or not math.isfinite(population_coverage_ratio)
        or abs(population_coverage_ratio - 1.0) > 1e-12
    ):
        raise InputError(
            "contact projection population is not PUBLICATION_READY: "
            f"coverage_ratio={population_coverage_ratio}"
        )
    if report.get("population_as_of_source") != "target_fit_full_reconcile":
        raise InputError("contact projection population freshness is not bound to a full reconcile")
    verified_at = _parse_timestamp(
        report.get("population_verified_at"),
        field="contact_projection.population_verified_at",
        cnpj="authoritative-projection",
    )
    population_as_of = _parse_timestamp(
        report.get("population_as_of"),
        field="contact_projection.population_as_of",
        cnpj="authoritative-projection",
    )
    if verified_at != population_as_of:
        raise InputError("contact projection population_as_of does not equal its full reconcile attestation")
    if int(report.get("population_count") or -1) != int(target_membership["population_count"]):
        raise InputError("contact projection population_count does not match TARGET_CONFIRMED membership")
    if int(report.get("membership_count") or -1) != int(target_membership["population_count"]):
        raise InputError("contact projection membership_count does not match TARGET_CONFIRMED membership")
    if str(report.get("membership_hash") or "") != str(target_membership["membership_hash"]):
        raise InputError("contact projection membership_hash does not match TARGET_CONFIRMED membership")
    if str(report.get("membership_schema_version") or "") != str(target_membership["schema_version"]):
        raise InputError("contact projection membership schema does not match TARGET_CONFIRMED membership")
    if str(report.get("membership_identity_key") or "") != str(target_membership["identity_key"]):
        raise InputError("contact projection identity key does not match TARGET_CONFIRMED membership")
    if str(report.get("membership_hash_algorithm") or "") != str(target_membership["hash_algorithm"]):
        raise InputError("contact projection hash algorithm does not match TARGET_CONFIRMED membership")
    integrity_failures = report.get("integrity_failures")
    if isinstance(integrity_failures, dict) and any(int(value or 0) for value in integrity_failures.values()):
        raise InputError("contact projection contains integrity failures")

    raw_states = report.get("enrichment_states")
    states = raw_states if isinstance(raw_states, dict) else {}
    allowed = {"EMAIL_ROUTE_READY", "NO_PUBLIC_EMAIL_FOUND", "BLOCKED_WITH_REASON"}
    unexpected = sorted(set(states) - allowed)
    if unexpected:
        raise InputError(f"contact projection contains non-terminal states: {unexpected}")
    state_counts = {name: int(states.get(name) or 0) for name in sorted(allowed)}
    if sum(state_counts.values()) != int(target_membership["population_count"]):
        raise InputError("contact projection terminal states do not close the TARGET_CONFIRMED denominator")
    if int(report.get("accounts_with_preferred_route") or 0) != state_counts["EMAIL_ROUTE_READY"]:
        raise InputError("contact projection EMAIL_ROUTE_READY does not match preferred-route accounts")
    if state_counts["EMAIL_ROUTE_READY"] and preferred_routes.get("input_declared") is not True:
        raise InputError("contact projection EMAIL_ROUTE_READY lacks declared preferred routes")
    if int(preferred_routes.get("raw_input_preferred_account_count") or 0) != state_counts["EMAIL_ROUTE_READY"]:
        raise InputError("declared preferred-route accounts do not match contact EMAIL_ROUTE_READY accounts")

    terminal_rows = [row for row in contact_rows if str(row.get("enrichment_state") or "") in allowed]
    try:
        observed_contact_membership = canonical_target_membership(
            [str(row.get("cnpj14") or row.get("canonical_account_id") or "") for row in terminal_rows]
        )
    except ValueError as exc:
        raise InputError(str(exc)) from exc
    if observed_contact_membership["membership_hash"] != target_membership["membership_hash"]:
        raise InputError("contact projection rows do not match TARGET_CONFIRMED membership")
    observed_states = Counter(str(row.get("enrichment_state")) for row in terminal_rows)
    if {name: int(observed_states.get(name) or 0) for name in sorted(allowed)} != state_counts:
        raise InputError("contact projection row states do not match its report")
    if any(
        row.get("preferred_email_route") for row in terminal_rows if row.get("enrichment_state") != "EMAIL_ROUTE_READY"
    ):
        raise InputError("non-ready contact terminal carries a preferred route")

    ready = int(preferred_routes.get("output_preferred_account_count") or 0)
    policy_blocked = state_counts["EMAIL_ROUTE_READY"] - ready
    if policy_blocked < 0:
        raise InputError("published preferred-route accounts exceed contact EMAIL_ROUTE_READY accounts")
    publication_blockers = {
        **(report.get("blockers") or {}),
        "SHARED_MAILBOX_CONFLICT": int(preferred_routes.get("shared_mailbox_excluded_account_count") or 0),
        "PARTY_ROLE_CONFLICT": int(preferred_routes.get("party_role_excluded_account_count") or 0),
    }
    return {
        **preferred_routes,
        "schema_id": report["schema_id"],
        "report_sha256": report_hash,
        "cohort_id": report.get("cohort_id"),
        "generated_at": report.get("generated_at"),
        "coverage_complete": True,
        "terminal_coverage_complete": True,
        "terminal_equation": terminal_equation,
        "population_count": int(report["population_count"]),
        "population_hash": report.get("population_hash"),
        "population_as_of": report.get("population_as_of"),
        "population_as_of_source": report.get("population_as_of_source"),
        "population_verified_at": report.get("population_verified_at"),
        "population_coverage_ratio": population_coverage_ratio,
        "population_publication_ready": True,
        "membership_schema_version": report.get("membership_schema_version"),
        "membership_identity_key": report.get("membership_identity_key"),
        "membership_count": int(report["membership_count"]),
        "membership_hash": report.get("membership_hash"),
        "membership_hash_algorithm": report.get("membership_hash_algorithm"),
        "enrichment_states": state_counts,
        "recipient_states": {
            "RECIPIENT_ATTRIBUTED": ready,
            "READY": ready,
            "NO_PUBLIC_EMAIL_FOUND": state_counts["NO_PUBLIC_EMAIL_FOUND"],
            "BLOCKED_WITH_REASON": state_counts["BLOCKED_WITH_REASON"] + policy_blocked,
        },
        "policy_blocked_from_ready": policy_blocked,
        "blockers": report.get("blockers") or {},
        "publication_blockers": dict(sorted(publication_blockers.items())),
        "accounts_with_any_email": int(report.get("accounts_with_any_email") or 0),
        "accounts_with_preferred_route": int(report.get("accounts_with_preferred_route") or 0),
        "route_class_distribution": report.get("route_class_distribution") or {},
        "preferred_route_class_distribution": report.get("preferred_route_class_distribution") or {},
        "provenance_source_distribution": report.get("provenance_source_distribution") or {},
        "projection_hash": report.get("projection_hash"),
        "controlled_email_policy_version": report.get("controlled_email_policy_version"),
        "discovery_policy_version": report.get("policy_version"),
        "input_evidence_version": report.get("input_evidence_version"),
        "code_sha": report.get("code_sha"),
    }


def _parse_timestamp(value: Any, *, field: str, cnpj: str) -> datetime:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InputError(f"invalid {field} timestamp for {cnpj}: {text!r}") from exc
    if parsed.tzinfo is None:
        raise InputError(f"timezone required in {field} for {cnpj}: {text!r}")
    return parsed.astimezone(UTC)


def _rfc3339_timestamp(value: Any, *, field: str, cnpj: str) -> str:
    """Return the contract timestamp in canonical UTC RFC 3339 form."""
    return _parse_timestamp(value, field=field, cnpj=cnpj).isoformat().replace("+00:00", "Z")


def _normalize_authoritative_timestamps(leads: list[dict[str, Any]]) -> None:
    """Normalize database datetime strings before schema serialization and hashing."""
    for lead in leads:
        cnpj = str((lead.get("company") or {}).get("cnpj14") or "")
        for field in ("target_fit_source_watermark", "target_fit_computed_at"):
            lead[field] = _rfc3339_timestamp(lead.get(field), field=field, cnpj=cnpj)


def _attach_contractor_roles(leads: list[dict[str, Any]], *, run_id: str, observed_at: str) -> None:
    """Bind typed supplier/buyer truth at the canonical publication boundary."""
    for lead in leads:
        company = lead.get("company") if isinstance(lead.get("company"), dict) else {}
        contracts = lead.get("contracts") if isinstance(lead.get("contracts"), list) else []
        lead["contractor_role"] = project_contractor_role(
            company.get("cnpj14"),
            contracts,
            source_run_id=run_id,
            observed_at=observed_at,
        )


def _apply_contractor_role_gate(leads: list[dict[str, Any]]) -> int:
    """Make a buyer/supplier conflict non-authorizing at the producer boundary.

    The gate runs over the whole decision universe: a conflicted account must be
    unauthorized whether or not its decision is shipped in this feed. The
    published distributions are projected separately over the shipped leads by
    :func:`_contractor_role_projection`.
    """

    conflict_authorizations_removed = 0
    for lead in leads:
        role = lead.get("contractor_role")
        if not isinstance(role, dict):
            raise InputError("every lead requires a typed contractor_role")
        if role.get("policy_version") != PARTY_ROLE_POLICY_V1:
            raise InputError("unsupported or missing contractor role policy version")
        target_role = str(role.get("target_party_role") or "UNKNOWN")
        status = str(role.get("status") or "UNKNOWN")
        if status != PARTY_ROLE_CONFLICT and target_role != "BUYER_CONFLICT":
            continue

        lead["contractor_role_eligible"] = False
        lead["outreach_block_reason"] = "PARTY_ROLE_CONFLICT"
        lead["email_send_ready"] = False
        lead["preferred_email_route"] = None
        for contact in lead.get("contacts") or []:
            if not isinstance(contact, dict):
                continue
            if any(
                contact.get(field) is True
                for field in (
                    "controlled_email_eligible",
                    "email_send_ready",
                    "enrollable",
                    "preferred_initial",
                    "recommended",
                )
            ):
                conflict_authorizations_removed += 1
            contact["controlled_email_eligible"] = False
            contact["email_send_ready"] = False
            contact["enrollable"] = False
            contact["preferred_initial"] = False
            contact["recommended"] = False
            contact["outreach_block_reason"] = "PARTY_ROLE_CONFLICT"

    return conflict_authorizations_removed


def _contractor_role_projection(
    feed_leads: list[dict[str, Any]],
    *,
    conflict_authorizations_removed: int,
    decision_universe_count: int,
) -> dict[str, Any]:
    """Project the published party-role distribution over the shipped leads."""

    role_distribution: Counter[str] = Counter()
    status_distribution: Counter[str] = Counter()
    for lead in feed_leads:
        role = lead.get("contractor_role")
        if not isinstance(role, dict):
            raise InputError("every lead requires a typed contractor_role")
        if str(lead.get("target_fit_class") or "") != TARGET_CONFIRMED:
            raise InputError("published feed lead is not TARGET_CONFIRMED")
        role_distribution[str(role.get("target_party_role") or "UNKNOWN")] += 1
        status_distribution[str(role.get("status") or "UNKNOWN")] += 1

    return {
        "policy_version": PARTY_ROLE_POLICY_V1,
        "target_party_role_distribution": dict(sorted(role_distribution.items())),
        "status_distribution": dict(sorted(status_distribution.items())),
        "supplier_confirmed_count": int(role_distribution.get("SUPPLIER") or 0),
        "unknown_role_count": int(role_distribution.get("UNKNOWN") or 0),
        "buyer_conflict_count": int(role_distribution.get("BUYER_CONFLICT") or 0),
        "conflict_authorizations_removed": conflict_authorizations_removed,
        "conflict_authorizations_removed_scope": "FULL_DECISION_UNIVERSE",
        "decision_universe_count": decision_universe_count,
        "distribution_scope": FEED_SCOPE,
        "buyer_supplier_conflict_fails_closed": True,
    }


def _target_membership_contract(
    leads: list[dict[str, Any]],
    *,
    party_roles: dict[str, Any],
    coverage_complete: bool,
) -> dict[str, Any]:
    confirmed = [lead for lead in leads if str(lead.get("target_fit_class") or "") == "TARGET_CONFIRMED"]
    try:
        membership = canonical_target_membership(
            [str((lead.get("company") or {}).get("cnpj14") or "") for lead in confirmed]
        )
    except ValueError as exc:
        raise InputError(str(exc)) from exc
    versions = sorted({str(lead.get("target_fit_version") or "") for lead in confirmed})
    if "" in versions:
        raise InputError("TARGET_CONFIRMED membership contains a missing target_fit_version")
    return {
        **membership,
        "target_fit_class": "TARGET_CONFIRMED",
        "target_confirmed_count": membership["population_count"],
        "supplier_confirmed_count": party_roles["supplier_confirmed_count"],
        "source_member_count": len(confirmed),
        "membership_complete": coverage_complete,
        "target_fit_policy_versions": versions,
        "contractor_role_policy_version": party_roles["policy_version"],
        "target_party_role_distribution": party_roles["target_party_role_distribution"],
        "contractor_role_status_distribution": party_roles["status_distribution"],
        "buyer_supplier_conflict_fails_closed": party_roles["buyer_supplier_conflict_fails_closed"],
    }


def _decision_order_key(lead: dict[str, Any]) -> tuple[datetime, datetime, str, str]:
    cnpj = str((lead.get("company") or {}).get("cnpj14") or "")
    return (
        _parse_timestamp(
            lead.get("target_fit_source_watermark"),
            field="target_fit_source_watermark",
            cnpj=cnpj,
        ),
        _parse_timestamp(
            lead.get("target_fit_computed_at"),
            field="target_fit_computed_at",
            cnpj=cnpj,
        ),
        cnpj,
        str(lead.get("source_lead_id") or ""),
    )


def _assert_authoritative_leads(leads: list[dict[str, Any]]) -> dict[str, Any]:
    required = (
        "target_fit_class",
        "target_fit_fresh",
        "target_fit_version",
        "target_fit_computed_at",
        "target_fit_source_watermark",
        "target_fit_evidence_ids",
        "target_fit_send_tier",
        "email_send_ready",
    )
    cursors: list[str] = []
    order_keys: list[tuple[datetime, datetime, str, str]] = []
    seen: set[str] = set()
    for lead in leads:
        company = lead.get("company") if isinstance(lead.get("company"), dict) else {}
        cnpj = str(company.get("cnpj14") or "")
        canonical = normalize_cnpj14(cnpj)
        if not canonical or canonical != cnpj:
            raise InputError(f"non-canonical company.cnpj14 in authoritative feed: {cnpj!r}")
        declared_root = str(company.get("cnpj_root") or "").strip()
        if declared_root and declared_root != cnpj[:8]:
            raise InputError(f"company.cnpj_root does not match canonical CNPJ14 for {cnpj}: {declared_root!r}")
        company["cnpj_root"] = cnpj[:8]
        missing = [field for field in required if field not in lead or lead[field] is None]
        if missing:
            raise InputError(f"authoritative target-fit decision incomplete for {cnpj}: {missing}")
        if not str(lead["target_fit_class"]):
            raise InputError(f"authoritative target-fit class empty for {cnpj}")
        if not str(lead["target_fit_version"]):
            raise InputError(f"authoritative target-fit version empty for {cnpj}")
        if not str(lead["target_fit_computed_at"]):
            raise InputError(f"authoritative target-fit computed_at empty for {cnpj}")
        if not str(lead["target_fit_source_watermark"]):
            raise InputError(f"authoritative target-fit watermark empty for {cnpj}")
        if cnpj in seen:
            raise InputError(f"duplicate authoritative decision for CNPJ {cnpj}")
        seen.add(cnpj)
        cursors.append(_decision_cursor(lead))
        order_keys.append(_decision_order_key(lead))
    monotonic = all(a <= b for a, b in zip(order_keys, order_keys[1:]))
    if not monotonic:
        raise InputError("target-fit source watermarks are not monotonically ordered")
    return {
        "key": [
            "target_fit_source_watermark",
            "target_fit_computed_at",
            "company.cnpj14",
        ],
        "direction": "ascending",
        "watermarks_monotonic": True,
        "first_cursor": cursors[0] if cursors else None,
        "last_cursor": cursors[-1] if cursors else None,
    }


def _membership_representative_key(lead: dict[str, Any]) -> tuple[Any, ...]:
    """Total order used to elect one lead per canonical root.

    Independent of input ordering: it reads only lead content. The routed
    establishment wins first (that is the one carrying the discovered outreach
    route), then contact depth, then the deterministic decision order.
    """
    contacts = [contact for contact in (lead.get("contacts") or []) if isinstance(contact, dict)]
    routed = 1 if (lead.get("email_send_ready") is True or lead.get("preferred_email_route")) else 0
    watermark, computed_at, cnpj, source_lead_id = _decision_order_key(lead)
    return (-routed, -len(contacts), watermark, computed_at, cnpj, source_lead_id)


def _select_feed_leads(leads: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Scope the published feed to TARGET_CONFIRMED, one lead per cnpj_root8.

    The full decision universe stays intact in ``leads``; this only decides what
    is shipped. Two establishments of the same commercial company collapse into
    the deterministically elected representative — never two Warmbly accounts
    for one company, and never a silently dropped root.
    """
    by_root: dict[str, dict[str, Any]] = {}
    collapsed: list[str] = []
    confirmed_count = 0
    for lead in leads:
        if str(lead.get("target_fit_class") or "") != TARGET_CONFIRMED:
            continue
        confirmed_count += 1
        company = lead.get("company") if isinstance(lead.get("company"), dict) else {}
        cnpj = normalize_cnpj14(str(company.get("cnpj14") or ""))
        if not cnpj:
            raise InputError("TARGET_CONFIRMED decision is missing a canonical CNPJ14")
        root = cnpj[:8]
        incumbent = by_root.get(root)
        if incumbent is None:
            by_root[root] = lead
            continue
        challenger_key = _membership_representative_key(lead)
        incumbent_key = _membership_representative_key(incumbent)
        if challenger_key == incumbent_key:
            raise InputError(f"cnpj_root8 {root} has two indistinguishable TARGET_CONFIRMED representatives")
        keep, drop = (lead, incumbent) if challenger_key < incumbent_key else (incumbent, lead)
        by_root[root] = keep
        collapsed.append(str((drop.get("company") or {}).get("cnpj14") or ""))

    feed_leads = sorted(by_root.values(), key=_decision_order_key)
    class_distribution = Counter(str(lead.get("target_fit_class") or "UNKNOWN") for lead in leads)
    return feed_leads, {
        "scope": FEED_SCOPE,
        "identity_key": TARGET_MEMBERSHIP_IDENTITY_KEY,
        "decision_universe_count": len(leads),
        "target_confirmed_decision_count": confirmed_count,
        "shipped_lead_count": len(feed_leads),
        "withheld_decision_count": len(leads) - len(feed_leads),
        "branch_duplicates_collapsed": len(collapsed),
        "collapsed_branch_cnpj14s": sorted(collapsed),
        "decision_class_distribution": dict(sorted(class_distribution.items())),
        "consumer_max_leads": CONSUMER_MAX_LEADS,
        "consumer_max_chunks": CONSUMER_MAX_CHUNKS,
    }


def _reproduce_membership_hash(cnpj14s: list[str]) -> tuple[str, list[str]]:
    """Recompute the membership digest straight from the shipped identities."""
    roots = sorted({cnpj[:8] for cnpj in cnpj14s})
    encoded = "".join(f"{root}\n" for root in roots).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), roots


def _assert_feed_membership(
    feed_leads: list[dict[str, Any]],
    membership: dict[str, Any],
    *,
    party_roles: dict[str, Any],
) -> dict[str, Any]:
    """Fail closed unless the declared membership is reproducible from the feed.

    This is the producer-side mirror of Warmbly's import check: it re-derives the
    digest from what is actually shipped instead of trusting the value computed
    upstream in this same run.
    """
    cnpjs: list[str] = []
    for lead in feed_leads:
        company = lead.get("company") if isinstance(lead.get("company"), dict) else {}
        cnpj = normalize_cnpj14(str(company.get("cnpj14") or ""))
        if not cnpj:
            raise InputError("published feed lead is missing a canonical CNPJ14")
        if str(lead.get("target_fit_class") or "") != TARGET_CONFIRMED:
            raise InputError(f"published feed lead {cnpj} is not TARGET_CONFIRMED")
        cnpjs.append(cnpj)
    if len(set(cnpjs)) != len(cnpjs):
        duplicates = sorted(cnpj for cnpj, count in Counter(cnpjs).items() if count > 1)
        raise InputError(f"published feed repeats CNPJ14: sample={duplicates[:10]}")
    observed_hash, roots = _reproduce_membership_hash(cnpjs)
    if len(roots) != len(cnpjs):
        repeated = sorted(root for root, count in Counter(cnpj[:8] for cnpj in cnpjs).items() if count > 1)
        raise InputError(f"published feed repeats cnpj_root8: sample={repeated[:10]}")
    declared_hash = str(membership.get("membership_hash") or "")
    if observed_hash != declared_hash:
        raise InputError(
            "declared TARGET_CONFIRMED membership_hash is not reproducible from the published leads: "
            f"declared={declared_hash or 'MISSING'} observed={observed_hash}"
        )
    population = int(membership.get("population_count", -1))
    if population != len(feed_leads) or population != len(roots):
        raise InputError(
            "published lead_count does not close the TARGET_CONFIRMED population: "
            f"population_count={population} leads={len(feed_leads)} unique_roots={len(roots)}"
        )
    if int(membership.get("source_member_count", -1)) != len(feed_leads):
        raise InputError("published TARGET_CONFIRMED source_member_count does not match the shipped leads")
    if int(membership.get("target_confirmed_count", -1)) != len(feed_leads):
        raise InputError("published TARGET_CONFIRMED target_confirmed_count does not match the shipped leads")
    if int(membership.get("duplicate_member_count", -1)) != 0:
        raise InputError("published TARGET_CONFIRMED membership declares duplicate members")
    supplier = sum(
        1
        for lead in feed_leads
        if str((lead.get("contractor_role") or {}).get("target_party_role") or "") == "SUPPLIER"
    )
    if supplier != int(membership.get("supplier_confirmed_count", -1)):
        raise InputError("published SUPPLIER_CONFIRMED count does not match the shipped leads")
    if supplier != int(party_roles.get("supplier_confirmed_count", -1)):
        raise InputError("party role projection SUPPLIER count does not match the shipped leads")
    return {
        "membership_hash": observed_hash,
        "membership_hash_reproduced_from_feed": True,
        "unique_root_count": len(roots),
        "shipped_lead_count": len(feed_leads),
        "supplier_confirmed_count": supplier,
    }


def _assert_consumer_ceilings(*, lead_count: int, chunk_count: int, staged_bytes: int | None = None) -> None:
    """Refuse to publish a feed the consumer contract cannot import.

    Truncating would silently drop authorized companies, so the run aborts and a
    human reconciles the population instead.
    """
    if lead_count > CONSUMER_MAX_LEADS:
        raise InputError(
            "TARGET_CONFIRMED feed exceeds the consumer lead ceiling; refusing to truncate: "
            f"lead_count={lead_count} max={CONSUMER_MAX_LEADS}"
        )
    if chunk_count > CONSUMER_MAX_CHUNKS:
        raise InputError(
            "TARGET_CONFIRMED feed exceeds the consumer chunk ceiling; refusing to truncate: "
            f"chunk_count={chunk_count} max={CONSUMER_MAX_CHUNKS}"
        )
    if staged_bytes is not None and staged_bytes > CONSUMER_MAX_STAGED_BYTES:
        raise InputError(
            "TARGET_CONFIRMED feed exceeds the consumer staged-byte ceiling; refusing to truncate: "
            f"staged_bytes={staged_bytes} max={CONSUMER_MAX_STAGED_BYTES}"
        )


def _members_by_root(
    cnpjs: list[str],
    *,
    source: str,
    allow_legacy_branch_duplicates: bool = False,
) -> dict[str, str]:
    """Index one representative CNPJ14 per canonical membership root."""
    by_root: dict[str, str] = {}
    for raw in cnpjs:
        cnpj = normalize_cnpj14(str(raw or ""))
        if not cnpj:
            raise InputError(f"{source} contains a non-canonical CNPJ14")
        root = cnpj[:8]
        prior = by_root.get(root)
        if prior is not None and prior != cnpj:
            if not allow_legacy_branch_duplicates:
                raise InputError(f"{source} repeats cnpj_root8 {root} with multiple representatives")
            # The pre-roster wire format shipped the whole decision universe,
            # so two establishments from one company can both appear as
            # TARGET_CONFIRMED. This compatibility path is used only while
            # migrating that legacy current. Elect the same stable
            # representative regardless of chunk/input ordering.
            by_root[root] = min(prior, cnpj)
            continue
        by_root[root] = cnpj
    return by_root


def _load_previous_feed_membership(previous_feed_dir: Path | None) -> tuple[dict[str, str], str]:
    """Return the previous release membership keyed by canonical CNPJ root."""
    if previous_feed_dir is None:
        return {}, "UNKNOWN"
    directory = Path(previous_feed_dir)
    if not directory.is_dir():
        raise InputError(f"--previous-feed-dir is not a readable directory: {directory}")
    roster_path = directory / FEED_MEMBERSHIP_FILENAME
    if roster_path.is_file():
        try:
            payload = json.loads(roster_path.read_bytes())
        except (OSError, json.JSONDecodeError) as exc:
            raise InputError(f"invalid previous feed membership roster: {roster_path}") from exc
        if not isinstance(payload, dict) or payload.get("schema_id") != FEED_MEMBERSHIP_SCHEMA:
            raise InputError(f"unsupported previous feed membership roster: {roster_path}")
        members = payload.get("members")
        if not isinstance(members, list):
            raise InputError("previous feed membership roster has no members array")
        cnpjs: list[str] = []
        for member in members:
            if not isinstance(member, dict):
                raise InputError("previous feed membership roster member must bind cnpj14 to cnpj_root")
            cnpj = normalize_cnpj14(str(member.get("cnpj14") or ""))
            if not cnpj or str(member.get("cnpj_root") or "") != cnpj[:8]:
                raise InputError("previous feed membership roster contains an invalid root binding")
            cnpjs.append(cnpj)
        previous = _members_by_root(cnpjs, source="previous feed membership roster")
        expected = canonical_target_membership(list(previous.values()))
        roster_contract = {
            "scope": FEED_SCOPE,
            "schema_version": expected["schema_version"],
            "identity_key": expected["identity_key"],
            "hash_algorithm": expected["hash_algorithm"],
            "population_count": expected["population_count"],
            "membership_hash": expected["membership_hash"],
        }
        for field, value in roster_contract.items():
            if payload.get(field) != value:
                raise InputError(f"previous feed membership roster {field} is not reproducible from its members")
        return previous, "MEMBERSHIP_ROSTER"
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise InputError(f"previous feed directory holds neither {FEED_MEMBERSHIP_FILENAME} nor manifest.json")
    # Transitional path: a release published before the roster existed. Recover
    # the shipped TARGET_CONFIRMED population from its own chunks so a former
    # member can never vanish without a deactivation.
    try:
        manifest = json.loads(manifest_path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"invalid previous feed manifest: {manifest_path}") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("chunks"), list):
        raise InputError(f"previous feed manifest has no chunks: {manifest_path}")
    previous_cnpjs: list[str] = []
    for chunk in manifest["chunks"]:
        if not isinstance(chunk, dict):
            raise InputError("previous feed manifest chunk is not an object")
        name = str(chunk.get("file") or "").strip()
        if not name or Path(name).name != name:
            raise InputError(f"unsafe previous feed chunk name: {name!r}")
        chunk_path = directory / name
        if not chunk_path.is_file():
            raise InputError(f"previous feed manifest references a missing chunk: {name}")
        expected_hash = str(chunk.get("content_hash") or "")
        if not expected_hash or hashlib.sha256(chunk_path.read_bytes()).hexdigest() != expected_hash:
            raise InputError(f"previous feed manifest chunk hash mismatch: {name}")
        try:
            payload = json.loads(chunk_path.read_bytes())
        except (OSError, json.JSONDecodeError) as exc:
            raise InputError(f"invalid previous feed chunk: {chunk_path}") from exc
        for lead in (payload or {}).get("leads") or []:
            if not isinstance(lead, dict) or str(lead.get("target_fit_class") or "") != TARGET_CONFIRMED:
                continue
            cnpj = normalize_cnpj14(str((lead.get("company") or {}).get("cnpj14") or ""))
            if cnpj:
                previous_cnpjs.append(cnpj)
    previous = _members_by_root(
        previous_cnpjs,
        source="previous feed chunks",
        allow_legacy_branch_duplicates=True,
    )
    declared_membership = manifest.get("authoritative_target_membership")
    declared_membership = declared_membership if isinstance(declared_membership, dict) else {}
    expected = canonical_target_membership(list(previous.values()))
    if str(declared_membership.get("membership_hash") or "") != expected["membership_hash"]:
        raise InputError("previous feed manifest membership_hash is not reproducible from its chunks")
    if int(declared_membership.get("population_count", -1)) != len(previous):
        raise InputError("previous feed manifest population_count does not match its unique roots")
    return previous, "PRIOR_RELEASE_CHUNKS"


def _membership_drop_deactivations(
    previous_members: dict[str, str],
    feed_leads: list[dict[str, Any]],
    decision_leads: list[dict[str, Any]],
    *,
    observed_at: str,
) -> list[dict[str, Any]]:
    """Emit one deactivation per account that left the shipped population."""
    shipped_roots = {
        cnpj[:8]
        for lead in feed_leads
        for cnpj in (normalize_cnpj14(str((lead.get("company") or {}).get("cnpj14") or "")),)
        if cnpj
    }
    decision_classes: dict[str, set[str]] = {}
    for lead in decision_leads:
        cnpj = normalize_cnpj14(str((lead.get("company") or {}).get("cnpj14") or ""))
        if cnpj:
            decision_classes.setdefault(cnpj[:8], set()).add(str(lead.get("target_fit_class") or ""))
    deactivations: list[dict[str, Any]] = []
    for root in sorted(set(previous_members) - shipped_roots):
        cnpj = previous_members[root]
        classes = decision_classes.get(root) or set()
        target_fit_class = (
            "TARGET_OUT_OF_SCOPE"
            if "TARGET_OUT_OF_SCOPE" in classes
            else "TARGET_INSUFFICIENT_EVIDENCE"
            if "TARGET_INSUFFICIENT_EVIDENCE" in classes
            else "TARGET_FIT_ABSENT"
        )
        to_state = "SUPPRESSED" if target_fit_class == "TARGET_OUT_OF_SCOPE" else "RESEARCH_REQUIRED"
        deactivations.append(
            {
                "cnpj14": cnpj,
                "from_state": TARGET_CONFIRMED,
                "to_state": to_state,
                "reason_codes": [MEMBERSHIP_DROP_REASON, f"target_fit_class:{target_fit_class}"],
                "delta_source": FEED_SCOPE,
                "target_fit_class": target_fit_class,
                "evaluated_at": observed_at,
            }
        )
    return deactivations


def _merge_deactivations(
    declared: list[dict[str, Any]],
    membership_drops: list[dict[str, Any]],
    *,
    feed_leads: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fold activation deltas and membership drops into one applicable delta.

    A still-shipped account must not also be deactivated: the manifest would then
    both authorize and revoke the same company in one import. Its activation
    state already travels inside the lead payload, so the contradiction is
    dropped here and counted, never applied.
    """
    shipped_roots = {
        cnpj[:8]
        for lead in feed_leads
        for cnpj in (normalize_cnpj14(str((lead.get("company") or {}).get("cnpj14") or "")),)
        if cnpj
    }
    merged: list[dict[str, Any]] = []
    seen_roots: set[str] = set()
    suppressed = 0
    for entry in declared:
        if not isinstance(entry, dict):
            raise InputError("declared deactivation must be an object")
        cnpj = normalize_cnpj14(str(entry.get("cnpj14") or ""))
        if not cnpj:
            raise InputError("declared deactivation has a non-canonical cnpj14")
        root = cnpj[:8]
        if root in shipped_roots:
            suppressed += 1
            continue
        if root in seen_roots:
            continue
        seen_roots.add(root)
        merged.append({**entry, "cnpj14": cnpj})
    for entry in membership_drops:
        cnpj = str(entry["cnpj14"])
        root = cnpj[:8]
        if root in seen_roots:
            continue
        seen_roots.add(root)
        merged.append(entry)
    for entry in merged:
        to_state = str(entry.get("to_state") or "").strip().upper()
        if to_state not in DEACTIVATION_STATES:
            raise InputError(f"deactivation to_state is not accepted by the consumer: {to_state or 'MISSING'}")
        entry["to_state"] = to_state
    return merged, {
        "declared_count": len(declared),
        "membership_drop_count": len(membership_drops),
        "suppressed_because_still_published": suppressed,
        "applied_count": len(merged),
    }


def _feed_membership_roster(
    feed_leads: list[dict[str, Any]],
    *,
    membership: dict[str, Any],
    generated_at: str,
    run_id: str,
    snapshot_hash: str,
) -> dict[str, Any]:
    """Durable roster of what this release shipped, for the next run's delta."""
    members = sorted(
        (
            {
                "cnpj14": normalize_cnpj14(str((lead.get("company") or {}).get("cnpj14") or "")),
                "cnpj_root": normalize_cnpj14(str((lead.get("company") or {}).get("cnpj14") or ""))[:8],
            }
            for lead in feed_leads
        ),
        key=lambda member: member["cnpj14"],
    )
    return {
        "schema_id": FEED_MEMBERSHIP_SCHEMA,
        "scope": FEED_SCOPE,
        "generated_at": generated_at,
        "run_id": run_id,
        "snapshot_hash": snapshot_hash,
        "schema_version": membership["schema_version"],
        "identity_key": membership["identity_key"],
        "hash_algorithm": membership["hash_algorithm"],
        "population_count": len(members),
        "membership_hash": membership["membership_hash"],
        "members": members,
    }


def _chunk_leads(
    leads: list[dict[str, Any]],
    *,
    max_leads: int,
    max_bytes: int,
    source: dict[str, Any],
    generated_at: str,
) -> list[tuple[list[dict[str, Any]], dict[str, Any]]]:
    """Return list of (lead_slice, pagination_stub_without_hash)."""
    if not leads:
        return [([], {"cursor": None, "next_cursor": None, "has_more": False, "chunk_index": 0})]

    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_item_bytes = 0
    for lead in leads:
        item_size = _encoded_lead_item_size(lead)
        trial_count = len(current) + 1
        size = _provisional_chunk_size(
            lead_item_bytes=current_item_bytes + item_size,
            lead_count=trial_count,
            source=source,
            generated_at=generated_at,
            cursor=_decision_cursor(current[0] if current else lead),
            chunk_index=len(chunks),
            # Assume a following chunk so the estimate covers next_cursor + hashes.
            next_cursor=_decision_cursor(lead),
            snapshot_hash=str(source.get("snapshot_hash") or ""),
        )
        over_count = trial_count > max_leads
        over_bytes = size > max_bytes and len(current) >= 1
        if size > max_bytes and not current:
            raise InputError(
                "single TARGET_CONFIRMED lead exceeds the encoded chunk byte ceiling; "
                f"bytes={size} max={max_bytes}"
            )
        if (over_count or over_bytes) and current:
            chunks.append(current)
            current = [lead]
            current_item_bytes = item_size
        else:
            current.append(lead)
            current_item_bytes += item_size
    if current:
        chunks.append(current)

    result: list[tuple[list[dict[str, Any]], dict[str, Any]]] = []
    for idx, slice_leads in enumerate(chunks):
        cursor = _decision_cursor(slice_leads[0]) if slice_leads else None
        has_more = idx < len(chunks) - 1
        next_cursor = _decision_cursor(chunks[idx + 1][0]) if has_more else None
        pagination = {
            "cursor": cursor,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "chunk_index": idx,
        }
        result.append((slice_leads, pagination))
    return result


def export_outreach(cfg: ExportConfig) -> dict[str, Any]:
    """Export chunked confenge.outreach.v1 feed. Idempotent for same inputs."""
    validate_inputs(cfg)
    out = cfg.out_dir
    out.mkdir(parents=True, exist_ok=True)

    universe_rows = read_jsonl(cfg.universe, label="--universe")
    intel_rows = read_jsonl(cfg.account_intelligence, label="--account-intelligence")
    contact_rows = read_jsonl(cfg.contacts, label="--contacts")
    contact_projection_report, contact_projection_report_hash = _read_contact_projection_report(
        cfg.contact_projection_report
    )

    if not universe_rows:
        raise InputError("--universe has no records; refusing empty shallow export")

    if cfg.limit is not None and cfg.limit < 0:
        raise InputError("--limit must be >= 0")

    snapshot_hash = _snapshot_hash(
        cfg.universe,
        cfg.account_intelligence,
        cfg.contacts,
        cfg.target_fit_snapshot,
        cfg.contact_projection_report,
    )
    freshness = dict(cfg.authoritative_source_freshness or {})
    freshness_hash = content_hash_obj(freshness) if freshness else None
    run_id = _run_id(snapshot_hash, cfg.profile_id, cfg.profile_version, freshness_hash)
    # Deterministic resume: reuse generated_at/repo_sha from prior manifest when
    # snapshot_hash matches so re-export yields identical chunk hashes.
    prior_manifest_path = out / "manifest.json"
    prior: dict[str, Any] = {}
    if prior_manifest_path.is_file():
        try:
            prior = json.loads(prior_manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            prior = {}
    prior_source = prior.get("source") if isinstance(prior.get("source"), dict) else {}
    same_snapshot = (
        str(prior_source.get("snapshot_hash") or "") == snapshot_hash
        and prior_source.get("authoritative_freshness_hash") == freshness_hash
    )
    if cfg.generated_at:
        generated_at = cfg.generated_at
    elif same_snapshot and prior.get("generated_at"):
        generated_at = str(prior["generated_at"])
    else:
        generated_at = _utcnow()
    datalake_watermark = str(cfg.datalake_watermark or generated_at)
    _parse_timestamp(
        datalake_watermark,
        field="datalake_watermark",
        cnpj="authoritative-snapshot",
    )
    if cfg.repo_sha is not None:
        repo_sha = cfg.repo_sha
    elif same_snapshot and prior_source.get("repo_sha"):
        repo_sha = str(prior_source["repo_sha"])
    else:
        repo_sha = _git_sha()

    if cfg.target_fit_snapshot is not None:
        target_fit_rows = read_jsonl(cfg.target_fit_snapshot, label="--target-fit-snapshot")
        # Seed every addressable company as an explicit missing tombstone.  The
        # authoritative snapshot then overwrites the companies it contains;
        # omission can never preserve a CONFIRMED decision from an older feed.
        published_index = build_published_index_from_rows(
            [{"cnpj14": row.get("cnpj14") or row.get("cnpj")} for row in universe_rows],
            computed_at=generated_at,
            source_watermark=generated_at,
        )
        try:
            published_index.update(
                build_published_index_from_rows(
                    target_fit_rows,
                    computed_at=generated_at,
                    source_watermark=generated_at,
                    require_authoritative_metadata=cfg.require_authoritative_target_fit_metadata,
                )
            )
        except ValueError as exc:
            raise InputError(str(exc)) from exc
    else:
        target_fit_rows = universe_rows
        try:
            published_index = build_published_index_from_rows(
                target_fit_rows,
                computed_at=generated_at,
                source_watermark=generated_at,
                require_authoritative_metadata=cfg.require_authoritative_target_fit_metadata,
            )
        except ValueError as exc:
            raise InputError(str(exc)) from exc
    leads = build_leads(
        universe_rows,
        intel_rows,
        contact_rows,
        published_index=published_index,
        datalake_watermark=datalake_watermark,
    )
    _attach_contractor_roles(leads, run_id=run_id, observed_at=datalake_watermark)
    _normalize_authoritative_timestamps(leads)
    leads.sort(key=_decision_order_key)
    if cfg.limit is not None:
        leads = leads[: cfg.limit]
    conflict_authorizations_removed = _apply_contractor_role_gate(leads)
    coverage_complete = bool(
        cfg.expected_universe_count is not None
        and cfg.limit is None
        and len(leads) == len(universe_rows) == cfg.expected_universe_count
    )
    # The whole decision universe is validated, then only the TARGET_CONFIRMED
    # membership is shipped. ``leads`` stays the authoritative decision record;
    # ``feed_leads`` is the published outreach population.
    decision_ordering = _assert_authoritative_leads(leads)
    decision_count = len(leads)
    feed_leads, feed_scope = _select_feed_leads(leads)
    feed_ordering = _assert_authoritative_leads(feed_leads)
    party_role_projection = _contractor_role_projection(
        feed_leads,
        conflict_authorizations_removed=conflict_authorizations_removed,
        decision_universe_count=decision_count,
    )
    preferred_route_projection = _reconcile_preferred_route_projection(
        contact_rows,
        feed_leads,
        full_snapshot=cfg.limit is None,
    )
    target_membership = _target_membership_contract(
        feed_leads,
        party_roles=party_role_projection,
        coverage_complete=coverage_complete,
    )
    membership_proof = _assert_feed_membership(
        feed_leads,
        target_membership,
        party_roles=party_role_projection,
    )
    previous_members, previous_membership_source = _load_previous_feed_membership(cfg.previous_feed_dir)
    membership_drops = _membership_drop_deactivations(
        previous_members,
        feed_leads,
        leads,
        observed_at=datalake_watermark,
    )
    contact_projection = _authoritative_contact_projection(
        preferred_route_projection,
        contact_projection_report,
        report_hash=contact_projection_report_hash,
        target_membership=target_membership,
        contact_rows=contact_rows,
        required=cfg.require_authoritative_contact_projection_metadata,
    )

    source = {
        "system": cfg.system,
        "run_id": run_id,
        "snapshot_hash": snapshot_hash,
        "repo_sha": repo_sha,
        "profile_id": cfg.profile_id,
        "profile_version": cfg.profile_version,
        "datalake_watermark": datalake_watermark,
        "authoritative_freshness": freshness or None,
        "authoritative_freshness_hash": freshness_hash,
        "source_operational_health": freshness or None,
    }

    chunk_specs = _chunk_leads(
        feed_leads,
        max_leads=cfg.max_leads_per_chunk,
        max_bytes=cfg.max_bytes_per_chunk,
        source=source,
        generated_at=generated_at,
    )
    _assert_consumer_ceilings(lead_count=len(feed_leads), chunk_count=len(chunk_specs))

    chunk_meta: list[dict[str, Any]] = []
    total_chunk_bytes = 0
    for slice_leads, pagination in chunk_specs:
        # First pass: compute content hash of leads+source (stable) for hashes block.
        leads_hash = content_hash_obj({"leads": slice_leads, "source": source})
        pagination = {
            **pagination,
            "content_hash": leads_hash,
            "hashes": {
                "leads": leads_hash,
                "snapshot": snapshot_hash,
            },
        }
        feed = {
            "schema_version": SCHEMA_OUTREACH,
            "generated_at": generated_at,
            "source": source,
            "pagination": pagination,
            "leads": slice_leads,
        }
        raw = _encode_chunk(feed)
        if len(raw) > cfg.max_bytes_per_chunk:
            raise InputError(
                "encoded outreach chunk exceeds --max-bytes-per-chunk; "
                f"chunk_index={pagination['chunk_index']} bytes={len(raw)} max={cfg.max_bytes_per_chunk}"
            )
        total_chunk_bytes += len(raw)
        file_hash = hashlib.sha256(raw).hexdigest()
        idx = int(pagination["chunk_index"])
        filename = f"chunk_{idx:04d}.json"
        path = out / filename
        # Resume/idempotency: if file exists with same hash, leave it; else overwrite.
        if path.is_file():
            existing = path.read_bytes()
            if hashlib.sha256(existing).hexdigest() == file_hash:
                chunk_meta.append(
                    {
                        "file": filename,
                        "chunk_index": idx,
                        "content_hash": file_hash,
                        "leads_hash": leads_hash,
                        "lead_count": len(slice_leads),
                        "byte_count": len(raw),
                        "cursor": pagination.get("cursor"),
                        "next_cursor": pagination.get("next_cursor"),
                        "has_more": pagination.get("has_more"),
                        "status": "unchanged",
                    }
                )
                continue
        path.write_bytes(raw)
        chunk_meta.append(
            {
                "file": filename,
                "chunk_index": idx,
                "content_hash": file_hash,
                "leads_hash": leads_hash,
                "lead_count": len(slice_leads),
                "byte_count": len(raw),
                "cursor": pagination.get("cursor"),
                "next_cursor": pagination.get("next_cursor"),
                "has_more": pagination.get("has_more"),
                "status": "written",
            }
        )

    _assert_consumer_ceilings(
        lead_count=len(feed_leads),
        chunk_count=len(chunk_meta),
        staged_bytes=total_chunk_bytes,
    )

    # Remove stale chunks from previous larger runs with different snapshot (same out dir).
    # Only delete chunk_*.json not in this run when snapshot changes — safer: delete extras.
    keep = {m["file"] for m in chunk_meta}
    for stale in sorted(out.glob("chunk_*.json")):
        if stale.name not in keep:
            # Only remove if manifest will supersede; keep if same snapshot resume partial
            stale.unlink(missing_ok=True)

    deacts, deactivation_projection = _merge_deactivations(
        list(cfg.deactivations or []),
        membership_drops,
        feed_leads=feed_leads,
    )
    membership_roster = _feed_membership_roster(
        feed_leads,
        membership=target_membership,
        generated_at=generated_at,
        run_id=run_id,
        snapshot_hash=snapshot_hash,
    )
    (out / FEED_MEMBERSHIP_FILENAME).write_bytes(
        (json.dumps(membership_roster, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n").encode(
            "utf-8"
        )
    )
    manifest = {
        "schema_version": "confenge.outreach.manifest.v1",
        "module_version": MODULE_VERSION,
        "generated_at": generated_at,
        "source": source,
        "inputs": {
            "universe": str(cfg.universe.resolve()),
            "account_intelligence": str(cfg.account_intelligence.resolve()),
            "contacts": str(cfg.contacts.resolve()),
            "contact_projection_report": (
                str(cfg.contact_projection_report.resolve()) if cfg.contact_projection_report is not None else None
            ),
            "target_fit_snapshot": (
                str(cfg.target_fit_snapshot.resolve())
                if cfg.target_fit_snapshot is not None
                else str(cfg.universe.resolve())
            ),
        },
        "lead_count": len(feed_leads),
        "chunk_count": len(chunk_meta),
        "max_leads_per_chunk": cfg.max_leads_per_chunk,
        "max_bytes_per_chunk": cfg.max_bytes_per_chunk,
        "total_chunk_bytes": total_chunk_bytes,
        "limit": cfg.limit,
        "authoritative_target_fit": {
            "source": "target_fit_snapshot" if cfg.target_fit_snapshot is not None else "universe_embedded_snapshot",
            # The decision-universe accounting below describes every company
            # extra-cli decided on, not what this feed ships. ``shipped_lead_count``
            # is the published TARGET_CONFIRMED population.
            "full_decision_count": decision_count,
            "universe_count": len(universe_rows),
            "declared_universe_count": cfg.expected_universe_count,
            "coverage_complete": coverage_complete,
            "omission_preserves_authorization": not coverage_complete,
            "shipped_lead_count": len(feed_leads),
            "feed_scope": FEED_SCOPE,
            "decision_class_distribution": feed_scope["decision_class_distribution"],
            "ordering": decision_ordering,
        },
        "authoritative_feed_scope": {
            **feed_scope,
            **membership_proof,
            "ordering": feed_ordering,
            "previous_membership_source": previous_membership_source,
            "previous_membership_count": len(previous_members),
        },
        "authoritative_source_freshness": freshness or None,
        "source_operational_health": freshness or None,
        "authoritative_target_membership": target_membership,
        "authoritative_party_roles": party_role_projection,
        "authoritative_contact_projection": contact_projection,
        "chunks": chunk_meta,
        # Approach B: explicit deactivation delta (idempotent; Warmbly applies without DB coupling)
        "deactivations": deacts,
        "deactivation_count": len(deacts),
        "deactivation_projection": deactivation_projection,
        "feed_membership": {
            "file": FEED_MEMBERSHIP_FILENAME,
            "schema_id": FEED_MEMBERSHIP_SCHEMA,
            "population_count": membership_roster["population_count"],
            "membership_hash": membership_roster["membership_hash"],
        },
        "hashes": {
            "snapshot": snapshot_hash,
            "manifest_inputs": content_hash_obj(
                {
                    "snapshot": snapshot_hash,
                    "run_id": run_id,
                    "chunks": [m["content_hash"] for m in chunk_meta],
                    "deactivations": deacts,
                }
            ),
        },
    }
    manifest_path = out / "manifest.json"
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n").encode(
        "utf-8"
    )
    manifest_path.write_bytes(manifest_bytes)
    manifest["manifest_content_hash"] = hashlib.sha256(manifest_bytes).hexdigest()
    # rewrite with self hash
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n").encode(
        "utf-8"
    )
    manifest_path.write_bytes(manifest_bytes)

    return {
        "ok": True,
        "out_dir": str(out.resolve()),
        "run_id": run_id,
        "snapshot_hash": snapshot_hash,
        "lead_count": len(feed_leads),
        "decision_count": decision_count,
        "chunk_count": len(chunk_meta),
        "total_chunk_bytes": total_chunk_bytes,
        "deactivation_count": len(deacts),
        "authoritative_feed_scope": {**feed_scope, **membership_proof},
        "authoritative_target_membership": target_membership,
        "authoritative_contact_projection": contact_projection,
        "manifest": str(manifest_path.resolve()),
        "chunks": chunk_meta,
    }
