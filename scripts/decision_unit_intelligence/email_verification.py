"""Passive, auditable email-domain verification.

DNS/MX plausibility is deliberately separate from mailbox and identity proof.
SMTP and catch-all probes stay disabled unless a future explicit policy provides
an approved verifier adapter, rate limits, and network-reputation safeguards.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol

import dns.exception
import dns.resolver

from scripts.decision_unit_intelligence.models import ReachabilityRoute, normalize_email, now_iso
from scripts.decision_unit_intelligence.reachability import (
    classify_observed_email_channel,
    is_generic_mailbox,
    is_role_mailbox,
)
from scripts.decision_unit_intelligence.web_discovery import JsonDiscoveryCache


class DnsLookupError(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class DnsResolver(Protocol):
    def query(self, domain: str, record_type: str) -> list[str]: ...


class DnspythonResolver:
    def __init__(self, *, timeout_seconds: float = 5.0) -> None:
        self._resolver = dns.resolver.Resolver()
        self._resolver.timeout = timeout_seconds
        self._resolver.lifetime = timeout_seconds

    def query(self, domain: str, record_type: str) -> list[str]:
        try:
            answer = self._resolver.resolve(domain, record_type, raise_on_no_answer=False)
        except dns.resolver.NXDOMAIN as exc:
            raise DnsLookupError("NXDOMAIN") from exc
        except dns.resolver.NoNameservers as exc:
            raise DnsLookupError("NO_NAMESERVERS") from exc
        except dns.exception.Timeout as exc:
            raise DnsLookupError("DNS_TIMEOUT") from exc
        except dns.exception.DNSException as exc:
            raise DnsLookupError(type(exc).__name__.upper()) from exc
        return sorted(str(record).strip() for record in (answer or []))


@dataclass(frozen=True)
class EmailVerificationReport:
    email: str
    syntax: str
    domain: str
    dns: str
    mx: str
    mx_hosts: tuple[str, ...]
    catch_all: str
    smtp: str
    final_classification: str
    checked_at: str
    reason_codes: tuple[str, ...]
    cache_hit: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class PassiveEmailVerifier:
    def __init__(
        self,
        resolver: DnsResolver,
        *,
        cache: JsonDiscoveryCache | None = None,
    ) -> None:
        self.resolver = resolver
        self.cache = cache

    def verify(self, raw_email: str) -> EmailVerificationReport:
        email = normalize_email(raw_email)
        if not email:
            return EmailVerificationReport(
                email=raw_email,
                syntax="INVALID",
                domain="UNKNOWN",
                dns="NOT_CHECKED",
                mx="NOT_CHECKED",
                mx_hosts=(),
                catch_all="UNKNOWN_NOT_PROBED",
                smtp="SKIPPED_POLICY",
                final_classification="UNVERIFIED",
                checked_at=now_iso(),
                reason_codes=("INVALID_SYNTAX", "SMTP_DISABLED_BY_POLICY"),
            )
        domain = email.split("@", 1)[1]
        cached = self.cache.get("email-dns", domain) if self.cache else None
        if cached is not None:
            return EmailVerificationReport(
                email=email,
                syntax="VALID",
                domain=domain,
                dns=str(cached["dns"]),
                mx=str(cached["mx"]),
                mx_hosts=tuple(cached.get("mx_hosts") or []),
                catch_all="UNKNOWN_NOT_PROBED",
                smtp="SKIPPED_POLICY",
                final_classification=_final_classification(email),
                checked_at=str(cached["checked_at"]),
                reason_codes=tuple(cached.get("reason_codes") or []) + ("CACHE_HIT",),
                cache_hit=True,
            )

        dns_status = "UNKNOWN"
        mx_status = "UNKNOWN"
        mx_hosts: tuple[str, ...] = ()
        reasons = ["SYNTAX_VALID", "SMTP_DISABLED_BY_POLICY", "CATCH_ALL_NOT_PROBED"]
        try:
            mx_records = self.resolver.query(domain, "MX")
            mx_hosts = tuple(mx_records)
            if any(record.split() and record.split()[-1] == "." for record in mx_records):
                dns_status = "RESOLVED"
                mx_status = "NULL_MX"
                reasons.append("NULL_MX_DECLINES_EMAIL")
            elif mx_records:
                dns_status = "RESOLVED"
                mx_status = "MX_PRESENT"
                reasons.append("MX_PRESENT_NOT_MAILBOX_PROOF")
            else:
                dns_status, mx_status, fallback_reason = self._implicit_mx(domain)
                reasons.append(fallback_reason)
        except DnsLookupError as exc:
            dns_status = exc.reason
            mx_status = "MISSING"
            reasons.append(exc.reason)

        checked_at = now_iso()
        cache_value = {
            "dns": dns_status,
            "mx": mx_status,
            "mx_hosts": list(mx_hosts),
            "checked_at": checked_at,
            "reason_codes": reasons,
        }
        if self.cache:
            self.cache.set("email-dns", domain, cache_value)
        return EmailVerificationReport(
            email=email,
            syntax="VALID",
            domain=domain,
            dns=dns_status,
            mx=mx_status,
            mx_hosts=mx_hosts,
            catch_all="UNKNOWN_NOT_PROBED",
            smtp="SKIPPED_POLICY",
            final_classification=_final_classification(email),
            checked_at=checked_at,
            reason_codes=tuple(reasons),
        )

    def _implicit_mx(self, domain: str) -> tuple[str, str, str]:
        for record_type in ("A", "AAAA"):
            try:
                if self.resolver.query(domain, record_type):
                    return "RESOLVED", "IMPLICIT_MX_A", "IMPLICIT_MX_NOT_MAILBOX_PROOF"
            except DnsLookupError:
                continue
        return "MISSING", "MISSING", "NO_MX_OR_ADDRESS_RECORD"


def _final_classification(email: str) -> str:
    if is_role_mailbox(email):
        return "GENERIC_ROLE_MAILBOX"
    if is_generic_mailbox(email):
        return "GENERIC_MAILBOX"
    if classify_observed_email_channel(email).value == "DIRECT_EMAIL":
        return "UNVERIFIED_DIRECT_CANDIDATE"
    return "UNVERIFIED"


def verify_email_routes(
    routes: list[ReachabilityRoute],
    verifier: PassiveEmailVerifier,
) -> list[EmailVerificationReport]:
    reports: dict[str, EmailVerificationReport] = {}
    for route in routes:
        email = normalize_email(route.channel_value)
        if not email:
            continue
        report = reports.setdefault(email, verifier.verify(email))
        route.extra["email_verification"] = report.to_dict()
        route.extra["identity_proven_by_verification"] = False
    return list(reports.values())
