"""Replay stored ICP observations through the shipped classifier + funnel.

Never invents mailboxes or a class mix. Never sends mail. auto_send stays false.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.decision_unit_intelligence.benchmark import funnel
from scripts.decision_unit_intelligence.controlled_email import (
    classify_account_email_routes,
    route_from_feed_contact,
)
from scripts.decision_unit_intelligence.models import (
    AccountInvestigation,
    SearchLedger,
    normalize_cnpj,
)
from scripts.decision_unit_intelligence.reachability import email_domain, is_freemail

COHORT_SCHEMA = "confenge.controlled_email.cohort_funnel.v1"
AUTO_SEND = False
REPO_ROOT = Path(__file__).resolve().parents[2]

STORED_ICP_INPUT = REPO_ROOT / "artifacts/confenge/contact-enrichment/real-1000-input.jsonl"
STORED_ENROLLABLE = (
    REPO_ROOT
    / "artifacts/confenge/contact-enrichment/real-1000-20260808T164758Z/warmbly_feed/contacts_enrollable.jsonl"
)
STORED_NO_CONTACT = REPO_ROOT / "artifacts/confenge/contact-enrichment/real-1000-20260808T164758Z/no-contact.jsonl"
STORED_TRACK_A = REPO_ROOT / "scripts/decision_unit_intelligence/data/track_a_30.observations.json"
STORED_GOLD = REPO_ROOT / "evals/email_validated/gold/gold-set.v1.jsonl"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _contact_email(row: dict[str, Any]) -> str:
    email = str(row.get("email") or "").strip()
    if not email and "@" in str(row.get("value") or ""):
        email = str(row.get("value")).strip()
    return email.lower()


def load_stored_contact_index() -> dict[str, list[dict[str, Any]]]:
    """Index stored contact rows by CNPJ. Does not invent addresses."""
    by_cnpj: dict[str, list[dict[str, Any]]] = {}

    def _add(cnpj: str, contact: dict[str, Any]) -> None:
        key = normalize_cnpj(cnpj)
        if not key:
            return
        by_cnpj.setdefault(key, []).append(contact)

    for row in _read_jsonl(STORED_ENROLLABLE):
        _add(str(row.get("cnpj14") or ""), row)
    track = json.loads(STORED_TRACK_A.read_text(encoding="utf-8")) if STORED_TRACK_A.is_file() else {}
    for rec in track.get("accounts") or []:
        email = str(rec.get("email") or "").strip()
        if not email:
            continue
        fonte = str(rec.get("fonte") or rec.get("site") or "")
        source = "company_website" if "http" in fonte and "casadosdados" not in fonte else "web_search"
        if "casadosdados" in fonte or "econodata" in fonte:
            source = "web_search"
        _add(
            str(rec.get("cnpj") or ""),
            {
                "email": email,
                "ownership_status": "COMPANY_OWNED" if source == "company_website" else "UNKNOWN",
                "source_type": source,
                "source_url": fonte or rec.get("site"),
                "verification_status": "OBSERVED",
                "name": None,
                "stored_origin": "track_a_30",
            },
        )
    if STORED_GOLD.is_file():
        for rec in _read_jsonl(STORED_GOLD):
            email = str(rec.get("email") or "").strip()
            if not email:
                continue
            _add(
                str(rec.get("account_id") or ""),
                {
                    "email": email,
                    "name": rec.get("person_name"),
                    "ownership_status": "COMPANY_OWNED" if rec.get("source") == "company_website" else "UNKNOWN",
                    "source_type": rec.get("source") or "unknown",
                    "source_url": rec.get("source_url"),
                    "verification_status": "OBSERVED",
                    "channel_epistemic_class": rec.get("epistemic"),
                    "stored_origin": "email_validated_gold",
                },
            )
    return by_cnpj


def load_stored_icp_accounts(*, limit: int = 200) -> list[AccountInvestigation]:
    """First `limit` stored ICP input accounts, with whatever emails were observed."""
    if limit < 100:
        raise ValueError("cohort must load at least 100 stored ICP accounts")
    inputs = _read_jsonl(STORED_ICP_INPUT)
    if len(inputs) < 100:
        raise FileNotFoundError(f"stored ICP input {STORED_ICP_INPUT} has {len(inputs)} rows; need ≥100 observations")
    contacts_by = load_stored_contact_index()
    no_contact = {normalize_cnpj(str(r.get("cnpj14") or "")) for r in _read_jsonl(STORED_NO_CONTACT)}
    accounts: list[AccountInvestigation] = []
    for row in inputs[:limit]:
        cnpj = normalize_cnpj(str(row.get("cnpj14") or row.get("cnpj") or ""))
        if not cnpj:
            continue
        seen_mail: set[str] = set()
        routes = []
        pages = 0
        requests = 0
        official_domain = None
        for contact in contacts_by.get(cnpj, []):
            email = _contact_email(contact)
            if not email or email in seen_mail:
                continue
            seen_mail.add(email)
            payload = {
                "email": email,
                "name": contact.get("name"),
                "ownership_status": contact.get("ownership_status"),
                "source": contact.get("source_type") or contact.get("source"),
                "source_url": contact.get("source_url"),
                "verification_status": contact.get("verification_status"),
                "channel_epistemic_class": contact.get("channel_epistemic_class"),
            }
            routes.append(route_from_feed_contact(payload, account_id=cnpj))
            host = email_domain(email)
            source = str(payload.get("source") or "").lower()
            if (
                host
                and not is_freemail(email)
                and source in {"site", "company_website", "contact_page", "company_site"}
            ):
                official_domain = official_domain or host
        extra: dict[str, Any] = {
            "auto_send": AUTO_SEND,
            "stored_observation": True,
            "no_contact_artifact": cnpj in no_contact,
        }
        if official_domain:
            extra["domain_resolution"] = {"canonical_domain": official_domain}
        accounts.append(
            AccountInvestigation(
                company_entity_id=cnpj,
                cnpj=cnpj,
                legal_name=str(row.get("razao_social") or row.get("company_name") or "") or None,
                service_context="reajuste_14133",
                why_now="stored_icp_observation",
                routes=routes,
                ledger=SearchLedger(provider_attempts=requests, documents_checked=pages),
                extra=extra,
            )
        )
    if len(accounts) < 100:
        raise RuntimeError(f"stored ICP replay produced {len(accounts)} accounts; need ≥100")
    return accounts


def run_cohort_funnel(n: int = 200) -> dict[str, Any]:
    accounts = load_stored_icp_accounts(limit=n)
    payload = funnel(accounts)
    preferred_ok = 0
    double = 0
    for account in accounts:
        ranking = classify_account_email_routes(account)
        flags = sum(1 for item in ranking.classified_routes if item.preferred_initial)
        if flags > 1:
            double += 1
        if flags <= 1:
            preferred_ok += 1
    payload.update(
        {
            "schema_id": COHORT_SCHEMA,
            "auto_send": AUTO_SEND,
            "REAL_EMAIL_SENT": False,
            "accounts_with_at_most_one_preferred": preferred_ok,
            "accounts_with_two_preferred": double,
            "cohort_n": len(accounts),
            "observation_source": str(STORED_ICP_INPUT.relative_to(REPO_ROOT)),
            "contacts_source": str(STORED_ENROLLABLE.relative_to(REPO_ROOT)),
            "hand_built_class_mix": False,
        }
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay stored ICP observations. Never sends mail.")
    parser.add_argument("--n", type=int, default=200)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    payload = run_cohort_funnel(args.n)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
