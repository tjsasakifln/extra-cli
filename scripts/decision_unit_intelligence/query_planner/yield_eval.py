"""Downstream yield from SERP hits. Never ranks by result count."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit

from scripts.decision_unit_intelligence.email_discovery import is_third_party_echo_source
from scripts.decision_unit_intelligence.models import fold_text, normalize_email, normalize_name
from scripts.decision_unit_intelligence.query_planner.spec import QueryExecution, QueryFamily, YieldSignals, host_of
from scripts.decision_unit_intelligence.web_discovery import SearchHit

_EMAIL_RE = re.compile(r"(?<![\w.+-])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})(?![\w-])", re.I)
_PERSON_PAGE_MARKERS = (
    "equipe",
    "diretoria",
    "quem-somos",
    "quem_somos",
    "institucional",
    "nossa-equipe",
    "corpo-tecnico",
    "staff",
    "time",
)
_DOC_SUFFIXES = (".pdf", ".doc", ".docx")


def evaluate_serp_yield(
    hits: Iterable[SearchHit],
    *,
    legal_name: str | None,
    known_domain: str | None,
    known_people: list[str] | None = None,
) -> YieldSignals:
    useful: list[str] = []
    observed: list[str] = []
    identity: list[str] = []
    weak: list[str] = []
    correct_domain = False
    person_page = False
    public_document = False
    people = [normalize_name(name) or "" for name in (known_people or [])]
    people = [name for name in people if name]
    domain = (known_domain or "").lower() or None
    name_tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", (legal_name or "").lower())
        if len(token) >= 4 and token not in {"ltda", "eireli", "engenharia", "construtora", "servicos"}
    ]

    for hit in hits:
        url = hit.url
        if not url:
            continue
        if is_third_party_echo_source(url):
            weak.append(url)
            continue
        host = host_of(url)
        haystack = f"{hit.title} {hit.snippet}"
        folded = fold_text(haystack)
        path = (urlsplit(url).path or "").lower()
        is_useful = False
        if domain and host == domain:
            correct_domain = True
            is_useful = True
        elif host and name_tokens and sum(1 for token in name_tokens if token in host) >= 1:
            is_useful = True
        if any(marker in path for marker in _PERSON_PAGE_MARKERS):
            person_page = True
            is_useful = True
        if (
            people
            and any(fold_text(person) in folded for person in people)
            and (any(marker in path for marker in _PERSON_PAGE_MARKERS) or (domain and host == domain))
        ):
            person_page = True
            is_useful = True
        if path.endswith(_DOC_SUFFIXES) or "filetype:pdf" in folded:
            public_document = True
            is_useful = True
        if is_useful:
            useful.append(url)
        for match in _EMAIL_RE.finditer(haystack):
            email = normalize_email(match.group(1))
            if not email:
                continue
            observed.append(email)
            if _identity_in_snippet(email, people, haystack):
                identity.append(f"{email}")

    return YieldSignals(
        useful_urls=tuple(dict.fromkeys(useful)),
        observed_emails=tuple(dict.fromkeys(observed)),
        identity_associated=tuple(dict.fromkeys(identity)),
        weak_source_urls=tuple(dict.fromkeys(weak)),
        correct_domain=correct_domain,
        person_page=person_page,
        public_document=public_document,
    )


def _identity_in_snippet(email: str, people: list[str], haystack: str) -> bool:
    folded = fold_text(haystack)
    local = email.split("@", 1)[0]
    for person in people:
        person_fold = fold_text(person)
        if not person_fold or person_fold not in folded:
            continue
        if fold_text(email) in folded and person_fold in folded:
            tokens = [tok for tok in person_fold.split() if len(tok) > 2]
            if tokens and all(tok in local.replace(".", " ").replace("_", " ") for tok in (tokens[0], tokens[-1])[:2]):
                return True
            if re.search(rf"(?:e-?mail|contato)\s+(?:de|do|da)\s+{re.escape(person)}", haystack, re.I):
                return True
    return False


def apply_yield(execution: QueryExecution, signals: YieldSignals) -> QueryExecution:
    execution.useful_urls = signals.useful_urls
    execution.useful_url_count = len(signals.useful_urls)
    execution.observed_emails = signals.observed_emails
    execution.observed_email_count = len(signals.observed_emails)
    execution.identity_associated = signals.identity_associated
    execution.identity_associated_count = len(signals.identity_associated)
    execution.weak_source_urls = signals.weak_source_urls
    execution.weak_source_count = len(signals.weak_source_urls)
    execution.correct_domain = signals.correct_domain
    execution.person_page = signals.person_page
    execution.public_document = signals.public_document
    return execution


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * pct
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return float(ordered[low] * (1 - weight) + ordered[high] * weight)


def aggregate_executions(executions: list[QueryExecution]) -> dict[str, Any]:
    executed = [row for row in executions if row.executed]
    searches = len(executed)
    elapsed_ms = sum(row.latency_ms for row in executed)
    elapsed_min = (elapsed_ms / 60000.0) if elapsed_ms else 0.0
    observed = sum(row.observed_email_count for row in executed)
    associated = sum(row.identity_associated_count for row in executed)
    useful = sum(row.useful_url_count for row in executed)
    failures = [row for row in executions if row.failure]
    rate_limited = sum(1 for row in executions if row.http_status == 429)
    latencies = [float(row.latency_ms) for row in executed]
    return {
        "searches": searches,
        "planned": len(executions),
        "useful_pages": useful,
        "useful_pages_per_search": round(useful / searches, 4) if searches else 0.0,
        "observed_emails": observed,
        "observed_email_per_search": round(observed / searches, 4) if searches else 0.0,
        "identity_associated": associated,
        "identity_associated_per_search": round(associated / searches, 4) if searches else 0.0,
        "observed_email_per_minute": round(observed / elapsed_min, 4) if elapsed_min else 0.0,
        "identity_associated_per_minute": round(associated / elapsed_min, 4) if elapsed_min else 0.0,
        "weak_sources": sum(row.weak_source_count for row in executed),
        "result_count_total": sum(row.result_count for row in executed),
        "latency_p50_ms": round(percentile(latencies, 0.50), 2),
        "latency_p95_ms": round(percentile(latencies, 0.95), 2),
        "latency_ms_total": elapsed_ms,
        "failures": len(failures),
        "failure_rate": round(len(failures) / searches, 4) if searches else 0.0,
        "http_429": rate_limited,
        "cache_hits": sum(1 for row in executed if row.cache_hit),
        "skipped_unsupported": sum(1 for row in executions if row.skip_reason == "unsupported_operator"),
        "skipped_early_stop": sum(1 for row in executions if row.skip_reason == "early_stop"),
        "skipped_duplicate": sum(1 for row in executions if row.skip_reason == "duplicate"),
    }


def rank_families(executions: list[QueryExecution]) -> list[dict[str, Any]]:
    grouped: dict[QueryFamily, list[QueryExecution]] = defaultdict(list)
    for row in executions:
        grouped[row.spec.family].append(row)
    ranked = []
    for family, rows in grouped.items():
        metrics = aggregate_executions(rows)
        metrics["family"] = family.value
        ranked.append(metrics)
    ranked.sort(
        key=lambda item: (
            item["identity_associated_per_search"],
            item["observed_email_per_search"],
            item["useful_pages_per_search"],
            -item["searches"],
        ),
        reverse=True,
    )
    return ranked


def rank_queries(executions: list[QueryExecution]) -> list[dict[str, Any]]:
    grouped: dict[str, list[QueryExecution]] = defaultdict(list)
    for row in executions:
        grouped[row.spec.shape_id].append(row)
    ranked = []
    for shape_id, rows in grouped.items():
        metrics = aggregate_executions(rows)
        metrics["shape_id"] = shape_id
        metrics["family"] = rows[0].spec.family.value
        metrics["sample_query"] = rows[0].spec.query
        ranked.append(metrics)
    ranked.sort(
        key=lambda item: (
            item["identity_associated_per_search"],
            item["observed_email_per_search"],
            item["useful_pages_per_search"],
            -item["searches"],
        ),
        reverse=True,
    )
    return ranked
