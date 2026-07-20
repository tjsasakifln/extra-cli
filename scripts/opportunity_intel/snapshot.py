"""Canonical opportunity snapshot + official reconfirm + delta (EXTRA-DECISION-LOOP-01).

HTTP outcomes remain distinct: 204, 403, 429, 5xx, timeout, partial pagination.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SNAPSHOT_DIR = PROJECT_ROOT / "data" / "decision_snapshots"

# Semantic HTTP / transport outcomes (never collapse into generic "error")
HTTP_OUTCOMES = frozenset(
    {
        "ok",
        "http_204",
        "http_403",
        "http_429",
        "http_5xx",
        "http_4xx",
        "timeout",
        "error",
        "skipped_offline_fixture",
        "pagination_incomplete",
        "not_attempted",
        "not_found",
        "identity_mismatch",
        "ambiguous",
        "partial",
        "unconfirmed",
    }
)

# Markers that indicate login/error shells even with HTTP 200
_ERROR_PAGE_MARKERS = (
    "faça login",
    "fazer login",
    "sign in",
    "access denied",
    "acesso negado",
    "página não encontrada",
    "page not found",
    "erro 404",
    "captcha",
)

# Listing / org-home shells that are never proof of one specific opportunity
_LISTING_PAGE_MARKERS = (
    "lista de editais",
    "listagem de editais",
    "editais do órgão",
    "editais do orgao",
    "resultados da busca",
    "nenhum edital encontrado",
    "nenhum resultado",
    "página de listagem",
)

# Minimum length of a control token to treat as opportunity-specific
_MIN_CONTROL_LEN = 6
_MIN_CONTROL_NORMALIZED_LEN = 8

# PNCP public detail: /app/editais/{cnpj}/{ano}/{sequencial}
_PNCP_DETAIL_URL_RE = re.compile(
    r"^https?://(?:www\.)?pncp\.gov\.br/app/editais/"
    r"(?P<cnpj>\d{8,14})/(?P<ano>\d{4})/(?P<seq>\d+)/?$",
    re.IGNORECASE,
)
# Org listing only: /app/editais/{cnpj}  (NOT opportunity-specific)
_PNCP_ORG_LISTING_URL_RE = re.compile(
    r"^https?://(?:www\.)?pncp\.gov\.br/app/editais/(?P<cnpj>\d{8,14})/?$",
    re.IGNORECASE,
)


@dataclass
class ReconfirmResult:
    opportunity_id: Any
    source: str
    url: str | None
    timestamp: str
    status_observed: str | None
    deadline: str | None
    http_status: int | None
    outcome: str
    raw_hash: str | None
    run_id: str | None
    collection_id: str | None
    rule: str
    error: str | None = None
    identity_matched: bool = False
    identity_checks: dict[str, Any] | None = None
    expected_control: str | None = None
    expected_cnpj: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _normalize_id(value: Any) -> str:
    """Alphanumeric-only lowercase form for exact (non-partial) ID comparison."""
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _identity_tokens(row: dict[str, Any]) -> dict[str, str]:
    """Extract expected identity markers for the specific opportunity.

    Prefer canonical ``numero_controle_pncp`` over raw row id (ids are not public).
    """
    control = str(
        row.get("numero_controle_pncp")
        or row.get("numero_controle")
        or row.get("source_id")
        or ""
    ).strip()
    # Never treat bare numeric database ids as public control numbers
    if control.isdigit() and len(control) < _MIN_CONTROL_LEN:
        control = ""
    cnpj = _digits(row.get("orgao_cnpj") or row.get("cnpj"))
    numero = str(row.get("numero") or row.get("numero_compra") or "").strip()
    return {"control": control, "cnpj": cnpj, "numero": numero}


def is_generic_pncp_org_url(url: str | None) -> bool:
    """True for ``https://pncp.gov.br/app/editais/{cnpj}`` (org listing, not detail)."""
    if not url:
        return False
    return bool(_PNCP_ORG_LISTING_URL_RE.match(str(url).strip()))


def is_specific_pncp_detail_url(url: str | None) -> bool:
    """True for ``https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}``."""
    if not url:
        return False
    return bool(_PNCP_DETAIL_URL_RE.match(str(url).strip()))


def _exact_token_in_text(token: str, text: str) -> bool:
    """Require full token presence; reject accidental partial substring matches.

    Matching rules (fail-closed):
    - empty / too-short tokens never match;
    - original token (case-insensitive) as contiguous substring is accepted when
      the token itself is long enough to be opportunity-specific;
    - normalized alphanumeric forms must match in full (entire normalized control
      appears contiguously in normalized body) — a suffix/prefix alone fails.
    """
    token = (token or "").strip()
    if not token or len(token) < _MIN_CONTROL_LEN:
        return False
    text = text or ""
    if token in text or token.lower() in text.lower():
        return True
    n_tok = _normalize_id(token)
    if len(n_tok) < _MIN_CONTROL_NORMALIZED_LEN:
        return False
    n_text = _normalize_id(text)
    # Full normalized control must appear contiguously — partial tails never match.
    return n_tok in n_text


def _exact_numero_with_context(numero: str, body: str) -> bool:
    """Hiring number alone is weak; require exact token (not a digit substring)."""
    numero = (numero or "").strip()
    if not numero or len(numero) < 3:
        return False
    # Prefer word-boundary style: digit sequence not embedded in a longer number
    pattern = re.compile(rf"(?<!\d){re.escape(numero)}(?!\d)")
    return bool(pattern.search(body or ""))


def _page_has_divergent_cnpj(body: str, expected_cnpj: str) -> str | None:
    """Return first 14-digit CNPJ on page that differs from expected, else None."""
    if not expected_cnpj or len(expected_cnpj) < 11:
        return None
    page_digits = _digits(body)
    for i in range(0, max(0, len(page_digits) - 13)):
        cand = page_digits[i : i + 14]
        if len(cand) == 14 and cand != expected_cnpj:
            return cand
    return None


def analyze_reconfirm_body(
    body: str,
    row: dict[str, Any],
    *,
    http_status: int | None,
    url: str | None = None,
) -> dict[str, Any]:
    """Validate that the HTTP body refers to the *specific* expected opportunity.

    Fail-closed identity rules:
    - CNPJ alone is **never** sufficient for ``identity_matched=true`` / ``outcome=ok``.
    - Org name / generic listing text never confirms an opportunity.
    - Positive match requires full ``numero_controle_pncp`` (normalized exact), **or**
      exact hiring number **combined with** expected CNPJ.
    - Partial control numbers never confirm.
    - Generic org URL ``/app/editais/{cnpj}`` never yields ``ok``.
    - Login, CAPTCHA, error shells, empty listings never confirm.
    """
    low = (body or "").lower()
    tokens = _identity_tokens(row)
    checks: dict[str, Any] = {
        "has_body": bool((body or "").strip()),
        "http_status": http_status,
        "error_page": False,
        "listing_page": False,
        "generic_org_url": is_generic_pncp_org_url(url),
        "specific_detail_url": is_specific_pncp_detail_url(url),
        "control_found": False,
        "control_partial_only": False,
        "cnpj_found": False,
        "numero_found": False,
        "specific_identity_proof": False,
        "proof_kind": None,
        "status_hint": None,
    }
    if not checks["has_body"]:
        return {
            "outcome": "http_204" if http_status == 204 else "partial",
            "status_observed": None,
            "identity_matched": False,
            "checks": checks,
            "rule": "empty_body",
        }
    if any(m in low for m in _ERROR_PAGE_MARKERS):
        checks["error_page"] = True
        return {
            "outcome": "unconfirmed",
            "status_observed": None,
            "identity_matched": False,
            "checks": checks,
            "rule": "login_or_error_page_200",
        }
    if any(m in low for m in _LISTING_PAGE_MARKERS):
        checks["listing_page"] = True
        return {
            "outcome": "not_found",
            "status_observed": None,
            "identity_matched": False,
            "checks": checks,
            "rule": "generic_listing_or_empty_search",
        }
    # URL that is only org-level listing is never opportunity confirmation
    if checks["generic_org_url"]:
        return {
            "outcome": "not_found",
            "status_observed": None,
            "identity_matched": False,
            "checks": checks,
            "rule": "generic_org_url_not_opportunity_specific",
        }

    control = tokens["control"]
    cnpj = tokens["cnpj"]
    numero = tokens["numero"]

    if cnpj and len(cnpj) >= 8 and cnpj in _digits(body):
        checks["cnpj_found"] = True

    if control:
        if _exact_token_in_text(control, body or ""):
            checks["control_found"] = True
        else:
            # Detect accidental partial: a short suffix of the control appearing alone
            n_ctrl = _normalize_id(control)
            n_body = _normalize_id(body)
            if n_ctrl and len(n_ctrl) >= _MIN_CONTROL_NORMALIZED_LEN:
                # tail fragments (last 6+ alnum) in body without full control
                for tail_len in (12, 10, 8, 6):
                    if len(n_ctrl) > tail_len and n_ctrl[-tail_len:] in n_body:
                        checks["control_partial_only"] = True
                        break

    if numero and _exact_numero_with_context(numero, body or ""):
        checks["numero_found"] = True

    # --- Specific identity proof (never CNPJ-only, never name-only) ---
    specific_proof = False
    proof_kind: str | None = None
    if checks["control_found"]:
        specific_proof = True
        proof_kind = "numero_controle_pncp_exact"
    elif checks["numero_found"] and checks["cnpj_found"]:
        # Exact hiring number + expected CNPJ (both required)
        specific_proof = True
        proof_kind = "numero_and_cnpj_exact"
    checks["specific_identity_proof"] = specific_proof
    checks["proof_kind"] = proof_kind

    if checks["control_partial_only"] and not specific_proof:
        return {
            "outcome": "unconfirmed",
            "status_observed": None,
            "identity_matched": False,
            "checks": checks,
            "rule": "partial_control_not_sufficient",
        }

    # Same hiring number on page but expected CNPJ missing/divergent → mismatch
    if checks["numero_found"] and cnpj and len(cnpj) >= 11 and not checks["cnpj_found"]:
        other = _page_has_divergent_cnpj(body or "", cnpj)
        checks["cnpj_expected"] = cnpj
        checks["cnpj_other_on_page"] = other
        return {
            "outcome": "identity_mismatch",
            "status_observed": None,
            "identity_matched": False,
            "checks": checks,
            "rule": "numero_match_cnpj_divergent",
        }

    if not specific_proof:
        # CNPJ-only / org-name / generic text → never ok
        if checks["cnpj_found"] and not checks["control_found"] and not checks["numero_found"]:
            return {
                "outcome": "not_found",
                "status_observed": None,
                "identity_matched": False,
                "checks": checks,
                "rule": "cnpj_alone_never_confirms_opportunity",
            }
        return {
            "outcome": "not_found",
            "status_observed": None,
            "identity_matched": False,
            "checks": checks,
            "rule": "generic_page_without_specific_identity",
        }

    # Expected full CNPJ present in row but absent/wrong on page → mismatch
    if cnpj and len(cnpj) >= 11 and not checks["cnpj_found"]:
        other_cnpj = _page_has_divergent_cnpj(body or "", cnpj)
        checks["cnpj_expected"] = cnpj
        checks["cnpj_other_on_page"] = other_cnpj
        return {
            "outcome": "identity_mismatch",
            "status_observed": None,
            "identity_matched": False,
            "checks": checks,
            "rule": "expected_cnpj_absent_or_divergent",
        }

    # Same hiring number but divergent CNPJ → mismatch
    if checks["numero_found"] and cnpj and len(cnpj) >= 11:
        other = _page_has_divergent_cnpj(body or "", cnpj)
        if other and not checks["cnpj_found"]:
            checks["cnpj_expected"] = cnpj
            checks["cnpj_other_on_page"] = other
            return {
                "outcome": "identity_mismatch",
                "status_observed": None,
                "identity_matched": False,
                "checks": checks,
                "rule": "numero_match_cnpj_divergent",
            }

    status_observed = str(row.get("status_canonico") or "open")
    if "revogad" in low or "anulad" in low:
        status_observed = "revoked"
        checks["status_hint"] = "revoked"
    elif "suspens" in low:
        status_observed = "suspended"
        checks["status_hint"] = "suspended"
    elif "encerrad" in low and "abert" not in low:
        status_observed = "closed"
        checks["status_hint"] = "closed"

    if status_observed in {"revoked", "suspended", "closed"}:
        return {
            "outcome": "ok",
            "status_observed": status_observed,
            "identity_matched": True,
            "checks": checks,
            "rule": "identity_matched_terminal_status",
        }

    return {
        "outcome": "ok",
        "status_observed": status_observed,
        "identity_matched": True,
        "checks": checks,
        "rule": "identity_matched_official_page",
    }


@dataclass
class Snapshot:
    snapshot_id: str
    created_at: str
    run_id: str
    collection_id: str | None
    profile_hash: str | None
    cutoff: str
    opportunities: list[dict[str, Any]] = field(default_factory=list)
    reconfirms: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def classify_http_status(code: int | None, *, body_empty: bool = False) -> str:
    if code is None:
        return "error"
    if code == 204 or (code == 200 and body_empty):
        return "http_204" if code == 204 else "ok"
    if code == 200:
        return "ok"
    if code == 403:
        return "http_403"
    if code == 429:
        return "http_429"
    if 500 <= code <= 599:
        return "http_5xx"
    if 400 <= code <= 499:
        return "http_4xx"
    return "error"


def classify_pagination_outcome(
    *,
    http_status: int | None,
    pages_fetched: int,
    total_pages: int | None,
    truncated: bool = False,
    body_empty: bool = False,
) -> str:
    """Classify list/page fetches; partial pagination is never success.

    Distinct from transport errors: a 200 with incomplete pages → pagination_incomplete.
    """
    base = classify_http_status(http_status, body_empty=body_empty)
    if base != "ok":
        return base
    if truncated:
        return "pagination_incomplete"
    if total_pages is not None:
        if pages_fetched < 0:
            return "error"
        if pages_fetched < int(total_pages):
            return "pagination_incomplete"
        if pages_fetched == 0 and int(total_pages) > 0:
            return "pagination_incomplete"
    return "ok"


def _deadline_expired(row: dict[str, Any], *, now: datetime | None = None) -> bool:
    """True when data_encerramento is parseable and <= now (deadline prevails)."""
    raw = row.get("data_encerramento")
    if raw is None or raw == "":
        return False
    if isinstance(raw, datetime):
        dt = raw if raw.tzinfo else raw.replace(tzinfo=UTC)
    else:
        text = str(raw).strip()
        try:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            dt = datetime.fromisoformat(text[:19] if "T" in text else text[:10])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
        except ValueError:
            # Ambiguous/unparseable deadline → not treated as expired here
            # (decision engine still demotes confidence for missing deadlines)
            return False
    now = now or datetime.now(UTC)
    return dt <= now


def select_active_opportunities(
    rows: list[dict[str, Any]],
    *,
    universe_cnpj8: set[str] | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Filter open/upcoming in Extra scope.

    Expired deadlines never remain active/acionável solely because status is still
    open (stale status must not override prazo vencido).
    """
    out: list[dict[str, Any]] = []
    now = now or datetime.now(UTC)
    for r in rows:
        status = str(r.get("status_canonico") or "").lower()
        if status not in {"open", "upcoming"}:
            continue
        if not r.get("is_active", True):
            continue
        # Deadline always wins over stale open status
        if _deadline_expired(r, now=now):
            continue
        uf = str(r.get("uf") or "").upper()
        cnpj = "".join(ch for ch in str(r.get("orgao_cnpj") or "") if ch.isdigit())
        cnpj8 = cnpj[:8] if len(cnpj) >= 8 else ""
        in_universe = True
        if universe_cnpj8 is not None:
            in_universe = cnpj8 in universe_cnpj8 or uf == "SC"
        if not in_universe:
            continue
        out.append(r)
    return out


def pick_reconfirm_targets(
    rows: list[dict[str, Any]],
    *,
    actionable: list[dict[str, Any]] | None = None,
    top_n: int = 20,
) -> list[dict[str, Any]]:
    """All actionable + top-N by score (or all if < top_n)."""
    by_id: dict[Any, dict[str, Any]] = {}
    for r in actionable or []:
        by_id[r.get("id") or r.get("source_id")] = r
    ranked = sorted(
        rows,
        key=lambda r: (
            0 if r.get("ranking") == "GO" else 1 if r.get("ranking") == "REVIEW" else 2,
            -(float(r.get("ranking_score") or 0)),
        ),
    )
    for r in ranked[:top_n]:
        by_id[r.get("id") or r.get("source_id")] = r
    if len(rows) <= top_n:
        for r in rows:
            by_id[r.get("id") or r.get("source_id")] = r
    return list(by_id.values())


def build_pncp_url(row: dict[str, Any]) -> str | None:
    """Return an opportunity-specific official URL when possible.

    Never invent a generic org listing URL (``/app/editais/{cnpj}``) as if it
    were proof of a specific contracting process. Prefer explicit ``link_edital``
    when present; otherwise try to parse ``numero_controle_pncp`` into
    ``/app/editais/{cnpj}/{ano}/{sequencial}``.
    """
    link = row.get("link_edital") or row.get("source_url")
    if link:
        link_s = str(link).strip()
        # Reject bare org listing masquerading as opportunity URL
        if is_generic_pncp_org_url(link_s):
            # fall through and try to build a specific detail URL
            pass
        else:
            return link_s

    cnpj = _digits(row.get("orgao_cnpj") or row.get("cnpj"))
    control = str(
        row.get("numero_controle_pncp") or row.get("numero_controle") or row.get("source_id") or ""
    ).strip()
    # Common PNCP control shapes:
    #   {cnpj}-{seqUnidade}-{numeroCompra}/{ano}
    #   {cnpj}/{ano}/{sequencial}
    if cnpj and control:
        # already detail path segments
        m = re.search(
            rf"{re.escape(cnpj)}[/\-](?P<a>\d{{4}})[/\-](?P<s>\d+)",
            control,
        )
        if m:
            return f"https://pncp.gov.br/app/editais/{cnpj}/{m.group('a')}/{m.group('s')}"
        m2 = re.search(
            rf"{re.escape(cnpj)}-(?P<u>\d+)-(?P<n>\d+)/?(?P<a>\d{{4}})?",
            control,
        )
        if m2 and m2.group("a"):
            # sequencial often equals numeroCompra or unit; use numero when present
            seq = m2.group("n").lstrip("0") or m2.group("n")
            return f"https://pncp.gov.br/app/editais/{cnpj}/{m2.group('a')}/{seq}"
        ano = str(row.get("ano") or row.get("ano_compra") or "").strip()
        seq = str(row.get("sequencial") or row.get("sequencial_compra") or row.get("numero") or "").strip()
        if ano.isdigit() and len(ano) == 4 and seq.isdigit():
            return f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{int(seq)}"
    # Explicit fields without control string
    if cnpj:
        ano = str(row.get("ano") or row.get("ano_compra") or "").strip()
        seq = str(row.get("sequencial") or row.get("sequencial_compra") or "").strip()
        if ano.isdigit() and len(ano) == 4 and seq.isdigit():
            return f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{int(seq)}"
    # Do NOT return https://pncp.gov.br/app/editais/{cnpj} — generic listing
    return None


def default_http_get(
    url: str,
    *,
    timeout: float = 15.0,
) -> tuple[int | None, str, str | None]:
    """Return (status_code, body_text, error)."""
    if not str(url).startswith(("http://", "https://")):
        return None, "", "invalid_scheme"
    req = urllib.request.Request(  # noqa: S310
        url,
        headers={"User-Agent": "extra-decision-loop/1.0 (+local research)"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            body = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), body, None
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            body = ""
        return int(exc.code), body, str(exc)
    except TimeoutError as exc:
        return None, "", f"timeout:{exc}"
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if "timed out" in msg or "timeout" in msg:
            return None, "", f"timeout:{exc}"
        return None, "", str(exc)


def reconfirm_paginated_listing(
    *,
    pages: list[tuple[int | None, str, str | None]],
    total_pages: int | None,
    opportunity_id: Any = None,
    source: str = "pncp",
    url: str | None = None,
    run_id: str | None = None,
    collection_id: str | None = None,
) -> ReconfirmResult:
    """Reconfirm path for multi-page listings — partial pages ≠ success.

    ``pages`` is a sequence of (http_status, body, error) in fetch order.
    """
    ts = _utc_now()
    if not pages:
        return ReconfirmResult(
            opportunity_id=opportunity_id,
            source=source,
            url=url,
            timestamp=ts,
            status_observed=None,
            deadline=None,
            http_status=None,
            outcome="pagination_incomplete",
            raw_hash=None,
            run_id=run_id,
            collection_id=collection_id,
            rule="paginated_listing_empty",
            error="no_pages_fetched",
        )
    # First non-ok transport outcome wins (429/5xx/timeout distinct)
    for code, body, err in pages:
        if err and str(err).startswith("timeout"):
            return ReconfirmResult(
                opportunity_id=opportunity_id,
                source=source,
                url=url,
                timestamp=ts,
                status_observed=None,
                deadline=None,
                http_status=code,
                outcome="timeout",
                raw_hash=_sha(body[:2000]) if body else None,
                run_id=run_id,
                collection_id=collection_id,
                rule="paginated_listing_timeout",
                error=err,
            )
        outcome = classify_http_status(code, body_empty=not (body or "").strip())
        if outcome != "ok":
            return ReconfirmResult(
                opportunity_id=opportunity_id,
                source=source,
                url=url,
                timestamp=ts,
                status_observed=None,
                deadline=None,
                http_status=code,
                outcome=outcome,
                raw_hash=_sha(body[:2000]) if body else None,
                run_id=run_id,
                collection_id=collection_id,
                rule="paginated_listing_http",
                error=err,
            )
    pages_fetched = len(pages)
    page_outcome = classify_pagination_outcome(
        http_status=pages[-1][0],
        pages_fetched=pages_fetched,
        total_pages=total_pages,
        truncated=total_pages is not None and pages_fetched < int(total_pages),
        body_empty=False,
    )
    return ReconfirmResult(
        opportunity_id=opportunity_id,
        source=source,
        url=url,
        timestamp=ts,
        status_observed="open" if page_outcome == "ok" else None,
        deadline=None,
        http_status=pages[-1][0],
        outcome=page_outcome,
        raw_hash=_sha(json.dumps({"pages": pages_fetched, "total": total_pages}, sort_keys=True)),
        run_id=run_id,
        collection_id=collection_id,
        rule="paginated_listing_complete_check",
        error=None if page_outcome == "ok" else "pagination_incomplete",
    )


def is_high_confidence_open(
    row: dict[str, Any],
    reconfirm: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> bool:
    """True only when open/upcoming, not expired, and officially reconfirmed with
    specific opportunity identity proof.

    ``outcome=ok`` alone is never enough — requires ``identity_matched`` and no
    offline / ambiguous / mismatch / pagination_incomplete signals.
    """
    rc = reconfirm or {}
    status = str(row.get("status_canonico") or "").lower()
    if status not in {"open", "upcoming"}:
        return False
    if _deadline_expired(row, now=now):
        return False
    if rc.get("outcome") != "ok":
        return False
    if not rc.get("identity_matched"):
        return False
    # Offline fixture must never be high-confidence live
    rule = str(rc.get("rule") or "")
    if rc.get("outcome") == "skipped_offline_fixture" or "offline" in rule:
        return False
    # Ambiguity / incomplete pagination / mismatch flags on the reconfirm payload
    bad_outcomes = {
        "ambiguous",
        "identity_mismatch",
        "pagination_incomplete",
        "not_found",
        "unconfirmed",
        "partial",
        "skipped_offline_fixture",
    }
    if rc.get("outcome") in bad_outcomes:
        return False
    checks = rc.get("identity_checks") or rc.get("checks") or {}
    if not isinstance(checks, dict):
        checks = {}

    def _has_specific_proof(c: dict[str, Any]) -> bool:
        return bool(
            c.get("specific_identity_proof")
            or c.get("control_found")
            or (c.get("numero_found") and c.get("cnpj_found"))
            or c.get("proof_kind") in {
                "numero_controle_pncp_exact",
                "numero_and_cnpj_exact",
            }
        )

    # Fail-closed: identity_matched alone is not enough.
    # - checks present → require specific opportunity proof (never CNPJ-only).
    # - checks absent → refuse high confidence (forged ok+flag without proof).
    if not checks:
        return False
    if checks.get("listing_page") or checks.get("error_page"):
        return False
    if checks.get("generic_org_url"):
        return False
    if checks.get("control_partial_only") and not checks.get("control_found"):
        return False
    if not _has_specific_proof(checks):
        return False

    # Explicit specific identifier must be known on the opportunity side
    tokens = _identity_tokens(row)
    if not tokens["control"] and not (tokens["numero"] and tokens["cnpj"]):
        return False
    return True


def reconfirm_opportunity(
    row: dict[str, Any],
    *,
    run_id: str | None = None,
    collection_id: str | None = None,
    http_get: Callable[..., tuple[int | None, str, str | None]] | None = None,
    offline: bool = False,
) -> ReconfirmResult:
    """Reconfirm one opportunity against official source (or offline fixture mode).

    HTTP 200 / non-empty HTML is NOT sufficient. Outcome ``ok`` requires
    opportunity-specific identity proof (full control number, or exact hiring
    number + expected CNPJ). CNPJ alone never confirms. Offline fixtures never
    claim live ok and never set identity_matched=True.
    """
    ts = _utc_now()
    url = build_pncp_url(row)
    source = str(row.get("source") or "pncp")
    oid = row.get("id") or row.get("source_id")
    tokens = _identity_tokens(row)

    if offline or os.getenv("DECISION_RECONFIRM_OFFLINE") == "1":
        # Deterministic offline: never claim live HTTP ok / identity match.
        return ReconfirmResult(
            opportunity_id=oid,
            source=source,
            url=url,
            timestamp=ts,
            status_observed=str(row.get("status_canonico")),
            deadline=str(row.get("data_encerramento") or "") or None,
            http_status=None,
            outcome="skipped_offline_fixture",
            raw_hash=_sha(json.dumps({"id": oid, "status": row.get("status_canonico")}, sort_keys=True)),
            run_id=run_id,
            collection_id=collection_id,
            rule="offline_db_status_not_live_http",
            error=None,
            identity_matched=False,
            identity_checks={"offline": True, "live_claim_forbidden": True},
            expected_control=tokens["control"] or None,
            expected_cnpj=tokens["cnpj"] or None,
        )

    if not url:
        return ReconfirmResult(
            opportunity_id=oid,
            source=source,
            url=None,
            timestamp=ts,
            status_observed=None,
            deadline=None,
            http_status=None,
            outcome="unconfirmed",
            raw_hash=None,
            run_id=run_id,
            collection_id=collection_id,
            rule="missing_specific_official_url",
            error="no_opportunity_specific_url",
            identity_matched=False,
            identity_checks={"specific_url": False, "review_required": True},
            expected_control=tokens["control"] or None,
            expected_cnpj=tokens["cnpj"] or None,
        )

    # Generic org listing URL is never a valid confirmation target
    if is_generic_pncp_org_url(url):
        return ReconfirmResult(
            opportunity_id=oid,
            source=source,
            url=url,
            timestamp=ts,
            status_observed=None,
            deadline=str(row.get("data_encerramento") or "") or None,
            http_status=None,
            outcome="not_found",
            raw_hash=None,
            run_id=run_id,
            collection_id=collection_id,
            rule="generic_org_url_not_opportunity_specific",
            error="generic_org_listing_url",
            identity_matched=False,
            identity_checks={"generic_org_url": True, "specific_url": False},
            expected_control=tokens["control"] or None,
            expected_cnpj=tokens["cnpj"] or None,
        )

    getter = http_get or default_http_get
    code, body, err = getter(url)
    if err and err.startswith("timeout"):
        return ReconfirmResult(
            opportunity_id=oid,
            source=source,
            url=url,
            timestamp=ts,
            status_observed=None,
            deadline=str(row.get("data_encerramento") or "") or None,
            http_status=code,
            outcome="timeout",
            raw_hash=_sha(body[:8000]) if body else None,
            run_id=run_id,
            collection_id=collection_id,
            rule="http_timeout",
            error=err,
            identity_matched=False,
            expected_control=tokens["control"] or None,
            expected_cnpj=tokens["cnpj"] or None,
        )

    transport = classify_http_status(code, body_empty=not (body or "").strip())
    if err and transport == "error":
        transport = "error"
    if transport != "ok":
        return ReconfirmResult(
            opportunity_id=oid,
            source=source,
            url=url,
            timestamp=ts,
            status_observed=None,
            deadline=str(row.get("data_encerramento") or "") or None,
            http_status=code,
            outcome=transport,
            raw_hash=_sha(body[:8000]) if body else None,
            run_id=run_id,
            collection_id=collection_id,
            rule="http_transport_not_ok",
            error=err,
            identity_matched=False,
            expected_control=tokens["control"] or None,
            expected_cnpj=tokens["cnpj"] or None,
        )

    analysis = analyze_reconfirm_body(body or "", row, http_status=code, url=url)
    return ReconfirmResult(
        opportunity_id=oid,
        source=source,
        url=url,
        timestamp=ts,
        status_observed=analysis.get("status_observed"),
        deadline=str(row.get("data_encerramento") or "") or None,
        http_status=code,
        outcome=str(analysis.get("outcome") or "unconfirmed"),
        raw_hash=_sha(body[:8000]) if body else None,
        run_id=run_id,
        collection_id=collection_id,
        rule=str(analysis.get("rule") or "identity_analysis"),
        error=err,
        identity_matched=bool(analysis.get("identity_matched")),
        identity_checks=analysis.get("checks"),
        expected_control=tokens["control"] or None,
        expected_cnpj=tokens["cnpj"] or None,
    )


def build_snapshot(
    rows: list[dict[str, Any]],
    *,
    run_id: str,
    collection_id: str | None = None,
    profile_hash: str | None = None,
    reconfirm_map: dict[Any, dict[str, Any]] | None = None,
    snapshot_id: str | None = None,
) -> Snapshot:
    reconfirm_map = reconfirm_map or {}
    active = select_active_opportunities(rows)
    snap_id = snapshot_id or f"snap-{run_id}"
    created = _utc_now()
    opps: list[dict[str, Any]] = []
    for r in active:
        oid = r.get("id") or r.get("source_id")
        rc = reconfirm_map.get(oid) or {}
        high_conf_open = is_high_confidence_open(r, rc)
        opps.append(
            {
                "id": oid,
                "source": r.get("source"),
                "source_id": r.get("source_id"),
                "numero_controle_pncp": r.get("numero_controle_pncp"),
                "orgao_cnpj": r.get("orgao_cnpj"),
                "orgao_nome": r.get("orgao_nome"),
                "objeto": r.get("objeto"),
                "status_canonico": r.get("status_canonico"),
                "data_encerramento": str(r.get("data_encerramento") or "") or None,
                "valor_estimado": r.get("valor_estimado"),
                "ranking": r.get("ranking"),
                "ranking_score": r.get("ranking_score"),
                "reconfirm_outcome": rc.get("outcome") or "not_attempted",
                "identity_matched": bool(rc.get("identity_matched")),
                "high_confidence_open": high_conf_open,
                "link_edital": r.get("link_edital"),
            }
        )
    return Snapshot(
        snapshot_id=snap_id,
        created_at=created,
        run_id=run_id,
        collection_id=collection_id,
        profile_hash=profile_hash,
        cutoff=created[:10],
        opportunities=opps,
        reconfirms=list(reconfirm_map.values()),
        counts={
            "active": len(opps),
            "high_confidence_open": sum(1 for o in opps if o.get("high_confidence_open")),
            "reconfirmed_ok": sum(1 for o in opps if o.get("reconfirm_outcome") == "ok"),
        },
    )


def compute_delta(
    previous: Snapshot | dict[str, Any] | None,
    current: Snapshot | dict[str, Any],
) -> dict[str, Any]:
    """Delta categories: new, changed, deadline_changed, suspended, revoked, closed, removed, still_open_reconfirmed."""
    prev = previous.to_dict() if isinstance(previous, Snapshot) else (previous or {})
    cur = current.to_dict() if isinstance(current, Snapshot) else current
    prev_map = {o.get("id"): o for o in (prev.get("opportunities") or [])}
    cur_map = {o.get("id"): o for o in (cur.get("opportunities") or [])}

    new_ids = [i for i in cur_map if i not in prev_map]
    removed_ids = [i for i in prev_map if i not in cur_map]
    deadline_changed: list[Any] = []
    changed: list[Any] = []
    suspended: list[Any] = []
    revoked: list[Any] = []
    closed: list[Any] = []
    still_open: list[Any] = []

    for oid, o in cur_map.items():
        if oid not in prev_map:
            continue
        p = prev_map[oid]
        if p.get("data_encerramento") != o.get("data_encerramento"):
            deadline_changed.append(oid)
        if p.get("status_canonico") != o.get("status_canonico"):
            changed.append(oid)
            st = str(o.get("status_canonico") or "")
            if st == "suspended":
                suspended.append(oid)
            elif st in {"revoked", "annulled"}:
                revoked.append(oid)
            elif st == "closed":
                closed.append(oid)
        if (
            o.get("status_canonico") in {"open", "upcoming"}
            and o.get("reconfirm_outcome") == "ok"
            and o.get("identity_matched") is True
            and o.get("high_confidence_open") is True
        ):
            still_open.append(oid)

    return {
        "schema": "extra-snapshot-delta/1.0",
        "previous_snapshot_id": prev.get("snapshot_id"),
        "current_snapshot_id": cur.get("snapshot_id"),
        "new": new_ids,
        "changed": changed,
        "deadline_changed": deadline_changed,
        "suspended": suspended,
        "revoked": revoked,
        "closed": closed,
        "removed": removed_ids,
        "still_open_reconfirmed": still_open,
        "counts": {
            "new": len(new_ids),
            "changed": len(changed),
            "deadline_changed": len(deadline_changed),
            "suspended": len(suspended),
            "revoked": len(revoked),
            "closed": len(closed),
            "removed": len(removed_ids),
            "still_open_reconfirmed": len(still_open),
        },
    }


def load_latest_snapshot(directory: Path | None = None) -> dict[str, Any] | None:
    d = directory or DEFAULT_SNAPSHOT_DIR
    if not d.is_dir():
        return None
    files = sorted(d.glob("snapshot-*.json"))
    if not files:
        return None
    raw = json.loads(files[-1].read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else None


def save_snapshot(snapshot: Snapshot, directory: Path | None = None) -> Path:
    d = directory or DEFAULT_SNAPSHOT_DIR
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"snapshot-{snapshot.snapshot_id}.json"
    path.write_text(
        json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    latest = d / "latest.json"
    latest.write_text(
        json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def reconfirm_batch(
    targets: list[dict[str, Any]],
    *,
    run_id: str,
    collection_id: str | None = None,
    http_get: Callable[..., tuple[int | None, str, str | None]] | None = None,
    offline: bool = False,
    sleep_s: float = 0.0,
) -> dict[Any, dict[str, Any]]:
    out: dict[Any, dict[str, Any]] = {}
    for row in targets:
        rc = reconfirm_opportunity(
            row,
            run_id=run_id,
            collection_id=collection_id,
            http_get=http_get,
            offline=offline,
        )
        out[rc.opportunity_id] = rc.to_dict()
        if sleep_s > 0:
            time.sleep(sleep_s)
    return out
