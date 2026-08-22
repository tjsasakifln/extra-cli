#!/usr/bin/env python3
"""Build the bounded controlled-email cohort feed from an exported outreach feed.

Reads the canonical `confenge.outreach.v1` chunks produced by the outreach
pipeline, keeps only accounts whose single `preferred_initial` mailbox survives
the controlled-email hard gates, caps the cohort, and writes:

  <private_root>/<run_stamp>/confenge.outreach.v1.json          (0600, holds PII)
  <private_root>/<run_stamp>/confenge.outreach.v1.json.sha256   (0600)
  <private_root>/<run_stamp>/manifest.redacted.json             (0600, no PII)

Eligibility is re-derived here from the contact's own provenance rather than
trusted from the exported stamp: a feed produced by an older classifier can carry
routes the current policy rejects, and the cohort must reflect the policy that is
shipped now.

The private feed never belongs in Git. The redacted manifest carries the funnel,
the route-class distribution and a stratified evidence sample with hosts only —
never a mailbox, a person or a CNPJ.

This script never sends mail, never opens an SMTP connection and never enables
auto_send. Warmbly owns delivery.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from collections.abc import Iterable, Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.confenge_contact_resolution.discovery.official_domain import (  # noqa: E402
    is_credible_company_domain,
)
from scripts.decision_unit_intelligence.controlled_email import (  # noqa: E402
    DEFAULT_PILOT_ROUTE_CLASSES,
    EmailRouteClass,
    apply_cross_account_preferred_mailbox_gate,
    canonicalize_mailbox,
    email_domain,
    evaluate_controlled_email_eligible,
    route_from_feed_contact,
    shared_preferred_mailbox_owner,
)
from scripts.warmbly_bridge import SCHEMA_OUTREACH  # noqa: E402

MANIFEST_SCHEMA = "confenge.fresh-cohort.manifest.v1"
DEFAULT_PRIVATE_ROOT = Path("/var/lib/extra-consultoria/private/outreach/cohorts")
DEFAULT_COHORT_SIZE = 50
SAMPLE_PER_ROUTE_CLASS = 3

ALLOWED_ROUTE_CLASSES = frozenset(rc.value for rc in DEFAULT_PILOT_ROUTE_CLASSES)
BLOCKING_SUPPRESSION = frozenset({"OPT_OUT", "DNC", "HARD_BOUNCE", "SUPPRESSED"})

# A zero is a finding, not an absence. Every funnel key ships even when unhit.
FUNNEL_KEYS: tuple[str, ...] = (
    "accounts_considered",
    "official_domain",
    "any_public_email",
    *(rc.value for rc in EmailRouteClass if rc != EmailRouteClass.PROBABILISTIC_OR_RISKY),
    "RISKY",
    "controlled_eligible",
    "preferred_initial",
    "no_email",
    "no_domain",
    "blocked",
    "suppressed",
    "double_preferred",
)


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _host(url: str | None) -> str | None:
    from urllib.parse import urlparse

    raw = str(url or "").strip()
    if not raw:
        return None
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or raw.split("/")[0]).lower().removeprefix("www.").strip()
    return host or None


def resolve_official_domain(lead: dict[str, Any], contact: dict[str, Any]) -> str | None:
    """Same official-domain ladder the exporter used, so the recheck is faithful."""
    company = lead.get("company") if isinstance(lead.get("company"), dict) else {}
    extra = contact.get("extra") if isinstance(contact.get("extra"), dict) else {}
    for candidate in (
        contact.get("official_domain"),
        extra.get("official_domain"),
        extra.get("canonical_domain"),
        company.get("official_domain"),
        company.get("website"),
        company.get("site"),
    ):
        host = _host(str(candidate or ""))
        if host:
            return host
    return None


def read_feed_manifest(feed_dir: Path) -> dict[str, Any]:
    manifest_path = feed_dir / "manifest.json"
    if manifest_path.is_file():
        return dict(json.loads(manifest_path.read_text(encoding="utf-8")))
    return {}


def iter_feed_leads(feed_dir: Path) -> Iterator[dict[str, Any]]:
    """Yield leads one chunk at a time.

    The authoritative export covers the whole decision universe — hundreds of
    thousands of leads across hundreds of chunks — so materializing them all is
    how the producer would run the host out of memory. One chunk is held at a
    time; callers that need a whole-feed view take a second pass.
    """
    for chunk in sorted(feed_dir.glob("chunk_*.json")):
        payload = json.loads(chunk.read_text(encoding="utf-8"))
        schema = str(payload.get("schema_version") or "")
        if schema != SCHEMA_OUTREACH:
            raise ValueError(f"{chunk}: expected {SCHEMA_OUTREACH}, found {schema!r}")
        yield from (lead for lead in (payload.get("leads") or []) if isinstance(lead, dict))


def load_feed_leads(feed_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Whole-feed read. Only for small feeds and tests; production streams."""
    return list(iter_feed_leads(feed_dir)), read_feed_manifest(feed_dir)


def _apply_owner_map(
    leads: Iterable[dict[str, Any]],
    owner: dict[str, str],
) -> Iterator[dict[str, Any]]:
    """Streaming equivalent of the cross-account preferred-mailbox gate."""
    for lead in leads:
        yield apply_cross_account_preferred_mailbox_gate([lead], owner=owner)[0]


def recheck_contact(
    contact: dict[str, Any],
    *,
    account_id: str,
    official_domain: str | None,
) -> Any:
    """Re-derive eligibility under the shipped policy, ignoring the exported stamp."""
    route = route_from_feed_contact(contact, account_id=account_id, official_domain=official_domain)
    return evaluate_controlled_email_eligible(route)


def _contact_blocked(
    contact: dict[str, Any],
    *,
    account_id: str = "",
    official_domain: str | None = None,
    company_label: str = "",
) -> str | None:
    """Reason this mailbox cannot enter the bounded cohort, or None."""
    mailbox = canonicalize_mailbox(str(contact.get("email") or ""))
    if not mailbox or "@" not in mailbox:
        return "mailbox_missing"
    route_class = str(contact.get("route_class") or "")
    if route_class == EmailRouteClass.PROBABILISTIC_OR_RISKY.value:
        return "risky_excluded_from_default_pilot"
    if route_class not in ALLOWED_ROUTE_CLASSES:
        return "route_class_outside_default_pilot"
    if not contact.get("controlled_email_eligible"):
        return "not_controlled_email_eligible"
    if str(contact.get("route_suppression") or "NONE").upper() in BLOCKING_SUPPRESSION:
        return "suppressed"
    if contact.get("dnc") or contact.get("do_not_contact"):
        return "dnc"
    if contact.get("bounce") or contact.get("bounced"):
        return "hard_bounce"
    if contact.get("mailbox_purpose_send_blocked"):
        return "mailbox_purpose_blocked"
    if str(contact.get("mailbox_company_evidence") or "").upper() != "OBSERVED":
        return "mailbox_company_evidence_unknown"
    # Domain resolution is the weak link every class leans on. When it picks the
    # wrong company, mailbox host, page host and official host all agree with
    # each other and the route reads clean end to end — observed in a real run:
    # premium.com.br for a Braga, balboa.com for an ML, capital.com for a
    # Construtora Capital. The registered name is the only independent check.
    evidence_domain = official_domain or email_domain(mailbox)
    if not company_label:
        return "company_name_unavailable_for_domain_check"
    if not evidence_domain or not is_credible_company_domain(evidence_domain, company_label):
        return "domain_not_credible_for_company_name"
    verdict = recheck_contact(contact, account_id=account_id, official_domain=official_domain)
    if not verdict.controlled_email_eligible:
        return "stamp_disagrees_with_shipped_policy"
    if verdict.route_class.value != route_class:
        return "stamp_disagrees_with_shipped_policy"
    return None


def select_cohort(
    leads: Iterable[dict[str, Any]],
    *,
    limit: int,
    shared_mailbox_owner: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Keep accounts with exactly one surviving preferred_initial mailbox.

    ``shared_mailbox_owner`` lets a streaming caller supply the whole-feed view
    of who keeps each shared mailbox, computed in an earlier pass. Without it the
    leads are materialized, which is only safe for a small feed.
    """
    if shared_mailbox_owner is None:
        gated: Iterable[dict[str, Any]] = apply_cross_account_preferred_mailbox_gate(list(leads))
    else:
        gated = _apply_owner_map(leads, shared_mailbox_owner)

    funnel: Counter[str] = Counter(dict.fromkeys(FUNNEL_KEYS, 0))
    class_counts: Counter[str] = Counter(dict.fromkeys((rc.value for rc in EmailRouteClass), 0))
    selected: list[dict[str, Any]] = []
    claimed: set[str] = set()

    for lead in gated:
        funnel["accounts_considered"] += 1
        company = lead.get("company") if isinstance(lead.get("company"), dict) else {}
        contacts = [c for c in (lead.get("contacts") or []) if isinstance(c, dict)]
        emails = [c for c in contacts if canonicalize_mailbox(str(c.get("email") or ""))]

        if company.get("official_domain") or company.get("website") or any(c.get("official_domain") for c in contacts):
            funnel["official_domain"] += 1
        else:
            funnel["no_domain"] += 1
        if emails:
            funnel["any_public_email"] += 1
        else:
            funnel["no_email"] += 1

        for contact in emails:
            route_class = str(contact.get("route_class") or "")
            if route_class == EmailRouteClass.PROBABILISTIC_OR_RISKY.value:
                funnel["RISKY"] += 1
            elif route_class in ALLOWED_ROUTE_CLASSES:
                funnel[route_class] += 1
            if contact.get("controlled_email_eligible"):
                funnel["controlled_eligible"] += 1

        preferred = [c for c in emails if c.get("preferred_initial")]
        if len(preferred) > 1:
            funnel["double_preferred"] += 1
            funnel["blocked"] += 1
            continue
        if not preferred:
            funnel["blocked"] += 1
            continue

        contact = preferred[0]
        reason = _contact_blocked(
            contact,
            account_id=str(company.get("cnpj14") or lead.get("source_lead_id") or ""),
            official_domain=resolve_official_domain(lead, contact),
            company_label=str(company.get("razao_social") or company.get("nome_fantasia") or ""),
        )
        if reason is not None:
            funnel[f"blocked_{reason}"] += 1
            funnel["blocked"] += 1
            if reason in {"suppressed", "dnc", "hard_bounce"}:
                funnel["suppressed"] += 1
            continue

        mailbox = canonicalize_mailbox(str(contact.get("email") or ""))
        if mailbox in claimed:
            funnel["double_preferred"] += 1
            funnel["blocked"] += 1
            continue

        funnel["preferred_initial"] += 1
        if len(selected) >= limit:
            continue
        claimed.add(mailbox)
        class_counts[str(contact.get("route_class") or "")] += 1
        member = dict(lead)
        member["contacts"] = [contact]
        selected.append(member)

    stats = {
        "funnel": dict(funnel),
        "route_class_distribution": dict(class_counts),
    }
    return selected, stats


def stratified_sample(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Small per-route-class evidence sample. Hosts only — never a mailbox."""
    per_class: Counter[str] = Counter()
    sample: list[dict[str, Any]] = []
    for member in members:
        contact = (member.get("contacts") or [{}])[0]
        route_class = str(contact.get("route_class") or "")
        if per_class[route_class] >= SAMPLE_PER_ROUTE_CLASS:
            continue
        per_class[route_class] += 1
        official = resolve_official_domain(member, contact)
        mailbox_domain = email_domain(str(contact.get("email") or "")) or None
        source_host = _host(contact.get("source_url"))
        # The reviewer's job is to catch a domain the classifier resolved wrongly.
        # Every host-vs-host field below agrees with itself when the resolution is
        # wrong — a domain guessed from the company name matches the page it was
        # crawled from. The independent signal is whether the mailbox domain is
        # credible for the registered company name.
        # The name itself is never emitted: a Brazilian MEI's razao social is a
        # natural person's name and often carries their CPF. Only the verdict.
        company = member.get("company") if isinstance(member.get("company"), dict) else {}
        company_label = str(company.get("razao_social") or company.get("nome_fantasia") or "")
        domain_fits_name = None
        if mailbox_domain and company_label:
            domain_fits_name = bool(is_credible_company_domain(mailbox_domain, company_label))
        sample.append(
            {
                "route_class": route_class,
                "mailbox_domain_fits_company_name": domain_fits_name,
                "source_type": str((contact.get("provenance") or {}).get("source_type") or "")
                or str(contact.get("source_type") or ""),
                "source_host": source_host,
                "official_host": official,
                "mailbox_domain": mailbox_domain,
                "mailbox_domain_matches_official": bool(official and mailbox_domain == official),
                "source_host_matches_official": bool(official and source_host == official),
                "mailbox_company_evidence": contact.get("mailbox_company_evidence"),
                "controlled_email_eligible": bool(contact.get("controlled_email_eligible")),
                "preferred_initial": bool(contact.get("preferred_initial")),
            }
        )
    return sample


def write_private_feed(
    members: list[dict[str, Any]],
    *,
    out_dir: Path,
    source_manifest: dict[str, Any],
    as_of: str,
    run_id: str,
) -> dict[str, Any]:
    """Write the 0600 private feed plus its hash. Returns the feed metadata."""
    out_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(out_dir, 0o700)
    feed = {
        "schema_version": SCHEMA_OUTREACH,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "auto_send": False,
        "smtp": "none",
        "source": {
            **(source_manifest.get("source") or {}),
            "cohort_run_id": run_id,
            "cohort_policy": "controlled-email-policy.v1",
        },
        "pagination": {"has_more": False},
        "leads": members,
    }
    body = json.dumps(feed, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    feed_path = out_dir / "confenge.outreach.v1.json"
    feed_path.write_text(body, encoding="utf-8")
    os.chmod(feed_path, 0o600)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    sha_path = out_dir / "confenge.outreach.v1.json.sha256"
    sha_path.write_text(digest + "\n", encoding="utf-8")
    os.chmod(sha_path, 0o600)
    return {"path": str(feed_path), "sha256": digest, "mode": "0600"}


def build(
    *,
    feed_dir: Path,
    private_root: Path,
    limit: int,
    as_of: str,
    run_stamp: str,
) -> dict[str, Any]:
    source_manifest = read_feed_manifest(feed_dir)
    # Two streaming passes: one to decide who keeps each shared mailbox across
    # the whole feed, one to select. Never the whole feed in memory at once.
    owner = shared_preferred_mailbox_owner(iter_feed_leads(feed_dir))
    members, stats = select_cohort(
        iter_feed_leads(feed_dir),
        limit=limit,
        shared_mailbox_owner=owner,
    )
    out_dir = private_root / run_stamp
    run_id = f"fresh-cohort-{run_stamp}"
    feed_meta = write_private_feed(
        members,
        out_dir=out_dir,
        source_manifest=source_manifest,
        as_of=as_of,
        run_id=run_id,
    )
    funnel = dict(stats["funnel"])
    considered = funnel.get("accounts_considered") or 0
    funnel["yield"] = round(len(members) / considered, 4) if considered else 0.0
    funnel["as_of"] = as_of
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "fresh_run_id": run_id,
        "as_of": as_of,
        "auto_send": False,
        "REAL_EMAIL_SENT": False,
        "smtp": "none",
        "private_feed_path": feed_meta["path"],
        "private_feed_mode": feed_meta["mode"],
        "feed_sha256": feed_meta["sha256"],
        "member_count": len(members),
        "requested_limit": limit,
        "route_class_distribution": stats["route_class_distribution"],
        "funnel": funnel,
        "sample_qa": stratified_sample(members),
        "source_feed": {
            "dir": str(feed_dir),
            "lead_count": source_manifest.get("lead_count"),
            "repo_sha": (source_manifest.get("source") or {}).get("repo_sha"),
            "run_id": (source_manifest.get("source") or {}).get("run_id"),
            "snapshot_hash": (source_manifest.get("source") or {}).get("snapshot_hash"),
        },
        "schema_versions": {
            "outreach_schema": SCHEMA_OUTREACH,
            "controlled_email_policy": "controlled-email-policy.v1",
        },
    }
    manifest_path = out_dir / "manifest.redacted.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(manifest_path, 0o600)
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--feed-dir", required=True, help="Exported 06_warmbly_feed directory")
    ap.add_argument("--private-root", default=str(DEFAULT_PRIVATE_ROOT), help="Private cohort root")
    ap.add_argument("--limit", type=int, default=DEFAULT_COHORT_SIZE, help="Cohort cap")
    ap.add_argument("--as-of", default=date.today().isoformat())
    ap.add_argument("--run-stamp", default=None, help="Defaults to the current UTC stamp")
    args = ap.parse_args(argv)

    manifest = build(
        feed_dir=Path(args.feed_dir),
        private_root=Path(args.private_root),
        limit=int(args.limit),
        as_of=str(args.as_of),
        run_stamp=str(args.run_stamp or _utc_stamp()),
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if manifest["member_count"] > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
