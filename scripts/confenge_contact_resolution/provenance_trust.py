"""Provenance trust + transitive taint for CONFENGE contact send-readiness.

Invariant
---------
EMAIL_SEND_READY requires PROVENANCE_CHAIN_VALID in addition to target/service/
contact/copy/block/freshness gates.

Stored labels alone never grant trust:

  VERIFIED != trusted merely because stored
  COMPANY_OWNED != trusted merely because stored
  HUMAN_CONFIRMED != trusted unless attributable to a real human decision

Any chain that roots (directly or transitively) in TEST_FIXTURE / DEMO /
SYNTHETIC / UNKNOWN cannot become EMAIL_SEND_READY — even when labeled
VERIFIED + COMPANY_OWNED.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

# ── Root source classification ──────────────────────────────────────────────


class RootSourceType(StrEnum):
    REAL_PUBLIC_SOURCE = "REAL_PUBLIC_SOURCE"
    REAL_OFFICIAL_SITE = "REAL_OFFICIAL_SITE"
    REAL_PUBLIC_DOCUMENT = "REAL_PUBLIC_DOCUMENT"
    REAL_REGISTRY = "REAL_REGISTRY"
    REAL_HUMAN_DECISION = "REAL_HUMAN_DECISION"
    TEST_FIXTURE = "TEST_FIXTURE"
    DEMO = "DEMO"
    SYNTHETIC = "SYNTHETIC"
    DERIVED_UNTRUSTED = "DERIVED_UNTRUSTED"
    UNKNOWN = "UNKNOWN"


class ProvenanceTrust(StrEnum):
    REAL_VERIFIED = "REAL_VERIFIED"
    REAL_OBSERVED = "REAL_OBSERVED"
    TAINTED = "TAINTED"
    UNKNOWN = "UNKNOWN"
    HUMAN_ATTRIBUTABLE = "HUMAN_ATTRIBUTABLE"


# Roots that permanently taint a chain (transitive).
TAINTED_ROOTS = frozenset(
    {
        RootSourceType.TEST_FIXTURE.value,
        RootSourceType.DEMO.value,
        RootSourceType.SYNTHETIC.value,
        RootSourceType.DERIVED_UNTRUSTED.value,
        RootSourceType.UNKNOWN.value,
    }
)

# Roots that may support EMAIL_SEND_READY when chain is otherwise clean.
TRUSTED_ROOTS = frozenset(
    {
        RootSourceType.REAL_PUBLIC_SOURCE.value,
        RootSourceType.REAL_OFFICIAL_SITE.value,
        RootSourceType.REAL_PUBLIC_DOCUMENT.value,
        RootSourceType.REAL_REGISTRY.value,
        RootSourceType.REAL_HUMAN_DECISION.value,
    }
)

# Adapter / source_type strings that mean fixture/demo/synthetic origin.
_FIXTURE_SOURCE_TYPES = frozenset(
    {
        "fixture",
        "fixtures",
        "test_fixture",
        "test",
        "demo",
        "synthetic",
        "mock",
        "sample",
        "example",
        "fake",
        "seed",
        "generated",
        "prior_verified_candidate",  # sticky prior label without re-proof
        "cached_synthetic",
        "warmbly.local",
    }
)

_REAL_SOURCE_TYPES = {
    "site": RootSourceType.REAL_OFFICIAL_SITE.value,
    "contact_page": RootSourceType.REAL_OFFICIAL_SITE.value,
    "official_site": RootSourceType.REAL_OFFICIAL_SITE.value,
    "official_domain": RootSourceType.REAL_OFFICIAL_SITE.value,
    "website": RootSourceType.REAL_OFFICIAL_SITE.value,
    "homepage": RootSourceType.REAL_OFFICIAL_SITE.value,
    # Accept canonical enum values (case-normalized to lower above)
    "real_official_site": RootSourceType.REAL_OFFICIAL_SITE.value,
    "real_public_source": RootSourceType.REAL_PUBLIC_SOURCE.value,
    "real_public_document": RootSourceType.REAL_PUBLIC_DOCUMENT.value,
    "real_registry": RootSourceType.REAL_REGISTRY.value,
    "real_human_decision": RootSourceType.REAL_HUMAN_DECISION.value,
    "registry": RootSourceType.REAL_REGISTRY.value,
    "rfb": RootSourceType.REAL_REGISTRY.value,
    "cnpj_registry": RootSourceType.REAL_REGISTRY.value,
    "public_docs": RootSourceType.REAL_PUBLIC_DOCUMENT.value,
    "public_document": RootSourceType.REAL_PUBLIC_DOCUMENT.value,
    "edital": RootSourceType.REAL_PUBLIC_DOCUMENT.value,
    "pncp": RootSourceType.REAL_PUBLIC_SOURCE.value,
    "web_search": RootSourceType.REAL_PUBLIC_SOURCE.value,  # still needs real URL
    "human_outcome": RootSourceType.REAL_HUMAN_DECISION.value,
    "human_decision": RootSourceType.REAL_HUMAN_DECISION.value,
    "human_review": RootSourceType.REAL_HUMAN_DECISION.value,
}

# Demo / fixture domain patterns (defense-in-depth; provenance is primary).
_DEMO_DOMAIN_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"^demo\d*obra\.com\.br$", re.I),
    re.compile(r"^demo\d+\.", re.I),
    re.compile(r"\.demo\.", re.I),
    re.compile(r"^example\.(com|org|net)$", re.I),
    re.compile(r"^test\.", re.I),
    re.compile(r"\.test$", re.I),
    re.compile(r"\.local$", re.I),
    re.compile(r"\.localhost$", re.I),
    re.compile(r"^localhost$", re.I),
    re.compile(r"warmbly\.local$", re.I),
    re.compile(r"^fixture[.-]", re.I),
    re.compile(r"^synthetic[.-]", re.I),
    re.compile(r"^fake[.-]", re.I),
    re.compile(r"^sample[.-]", re.I),
    re.compile(r"^mock[.-]", re.I),
)

_DEMO_EMAIL_LOCAL_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"^test@", re.I),
    re.compile(r"^demo@", re.I),
    re.compile(r"^fixture@", re.I),
    re.compile(r"^fake@", re.I),
    re.compile(r"^synthetic@", re.I),
    re.compile(r"^example@", re.I),
    re.compile(r"^noreply@example", re.I),
)

_FIXTURE_URL_MARKERS = (
    "fixture",
    "/fixtures/",
    "example.com",
    "example.org",
    "demo000obra",
    "demo001obra",
    "demo002obra",
    "demo003obra",
    "demo004obra",
    "demo005obra",
    "demo006obra",
    "demo007obra",
    "demo008obra",
    "demo009obra",
    "warmbly.local",
    "localhost",
    "127.0.0.1",
    "synthetic",
    "fake-contact",
)

_TAINT_NOTE_MARKERS = (
    "fixture",
    "synthetic",
    "demo contact",
    "test only",
    "not commercial",
    "seed data",
    "mock",
    "generated for test",
)

# Public/registry hosts that may host company emails without matching the email domain.
_PUBLIC_PROVENANCE_HOST_SUFFIXES: tuple[str, ...] = (
    "gov.br",
    "jus.br",
    "leg.br",
    "mil.br",
    "pncp.gov.br",
    "brasilapi.com.br",
    "receitaws.com.br",
    "cnpj.biz",
    "casadosdados.com.br",
    "opencnpj.com",
    "consultacnpj.com",
)

# source_type values whose root URL must align with the email/company domain.
_SITE_BOUND_SOURCE_TYPES = frozenset(
    {
        "site",
        "contact_page",
        "official_site",
        "company_site",
        "website",
        "site_scrape",
        "site_scrape_expand",
        "site_scrape_expand_v7",
        "site_scrape_expand_v8",
        "site_scrape_expand_v8b",
        "host_enrich_confirmed",
        "manual_site_expand",
        "public_directories_and_live_domain",
    }
)


def _registrable_labels(host: str) -> set[str]:
    """Token-ish labels from a hostname (drop www/com/br/net/org)."""
    h = (host or "").lower().removeprefix("www.")
    if not h:
        return set()
    parts = [p for p in h.replace("-", "").split(".") if p and p not in {"com", "br", "net", "org", "eng", "www", "co"}]
    # also keep joined brand before public suffix
    sld = h.removeprefix("www.")
    for suf in (".com.br", ".eng.br", ".net.br", ".org.br", ".com", ".net", ".org", ".br"):
        if sld.endswith(suf):
            sld = sld[: -len(suf)]
            break
    sld = sld.split(".")[-1] if sld else ""
    out = set(parts)
    if sld and len(sld) >= 3:
        out.add(sld.replace("-", ""))
    return {t for t in out if len(t) >= 3}


def _is_public_provenance_host(host: str) -> bool:
    h = (host or "").lower().removeprefix("www.")
    if not h:
        return False
    return any(h == s or h.endswith("." + s) for s in _PUBLIC_PROVENANCE_HOST_SUFFIXES)


def provenance_host_aligned_with_email(
    email: str | None,
    *,
    source_url: str | None = None,
    source_type: str | None = None,
    provenance_chain: list[dict[str, Any]] | None = None,
    official_domain: str | None = None,
) -> tuple[bool, str]:
    """Fail-closed when site-bound provenance host is foreign to the email domain.

    Skeptic case: comercial@connector.eng.br with root URL caiafafacilities.com.br
    must never be provenance_chain_valid / EMAIL_SEND_READY.

    Registry/gov public document hosts are allowed without domain match.
    Missing URL for site-bound sources fails closed.
    """
    email_dom = domain_of_email(email)
    st = (source_type or "").strip().lower()
    # Collect root URLs: explicit source_url + chain entries marked root or first hop
    urls: list[str] = []
    types: list[str] = []
    if source_url:
        urls.append(str(source_url))
        types.append(st)
    for link in provenance_chain or []:
        if not isinstance(link, dict):
            continue
        u = link.get("source_url") or link.get("root_source_url") or link.get("url")
        if not u:
            continue
        lst = str(link.get("source_type") or link.get("method") or st).lower()
        if link.get("root") is True or not urls:
            urls.append(str(u))
            types.append(lst)
        elif lst in _SITE_BOUND_SOURCE_TYPES or str(link.get("method") or "").lower() in _SITE_BOUND_SOURCE_TYPES:
            urls.append(str(u))
            types.append(lst)

    if not urls:
        # No URL: site-bound types fail; registry/unknown handled elsewhere
        if st in _SITE_BOUND_SOURCE_TYPES or any(
            str(m).lower() in _SITE_BOUND_SOURCE_TYPES
            for m in ((c or {}).get("method") for c in (provenance_chain or []) if isinstance(c, dict))
        ):
            return False, "provenance_host_missing_for_site_source"
        return True, "no_url_non_site_bound"

    email_labels = _registrable_labels(email_dom or "")
    official_labels = _registrable_labels((official_domain or "").lower().removeprefix("www."))
    allowed_labels = email_labels | official_labels

    for u, ut in zip(urls, types, strict=False):
        raw = str(u).strip()
        # Non-URL placeholders (e.g. "official_company_registry") are not hosts.
        if "://" not in raw and "/" not in raw and "." not in raw:
            if ut in {"registry", "rfb", "cnpj_registry", "public_docs", "public_document", "pncp"} or st in {
                "registry",
                "rfb",
                "cnpj_registry",
                "public_docs",
                "public_document",
                "pncp",
            }:
                continue
            # bare token with site-bound type → fail
            if ut in _SITE_BOUND_SOURCE_TYPES or st in _SITE_BOUND_SOURCE_TYPES:
                return False, f"provenance_host_unparseable:{raw}"
            continue
        host = domain_of_url(raw if "://" in raw else f"https://{raw}")
        if not host:
            if ut in _SITE_BOUND_SOURCE_TYPES or st in _SITE_BOUND_SOURCE_TYPES:
                return False, f"provenance_host_unparseable:{raw}"
            continue
        # host without a TLD (no dot) is not a website — skip alignment
        if "." not in host:
            if ut in {"registry", "rfb", "cnpj_registry"} or st in {"registry", "rfb", "cnpj_registry"}:
                continue
            if ut in _SITE_BOUND_SOURCE_TYPES or st in _SITE_BOUND_SOURCE_TYPES:
                return False, f"provenance_host_unparseable:{host}"
            continue
        if _is_public_provenance_host(host):
            continue
        # site-bound or default: require label overlap with email/official domain
        host_labels = _registrable_labels(host)
        if not allowed_labels:
            return False, f"provenance_host_no_email_domain:{host}"
        if host_labels & allowed_labels:
            continue
        # direct suffix: email domain appears in host or vice-versa
        ed = (email_dom or "").lower().removeprefix("www.")
        hd = host.lower().removeprefix("www.")
        if ed and (ed in hd or hd in ed):
            continue
        od = (official_domain or "").lower().removeprefix("www.")
        if od and (od in hd or hd in od):
            continue
        # registry/public_docs on non-public third-party host still must align or be public
        if ut in {"registry", "rfb", "cnpj_registry", "public_docs", "public_document", "pncp"} or st in {
            "registry",
            "rfb",
            "cnpj_registry",
            "public_docs",
            "public_document",
            "pncp",
        }:
            # allow if not site-bound scrape of wrong company site
            continue
        return False, f"provenance_host_mismatch:{host}!={ed or od or 'unknown'}"

    return True, "provenance_host_aligned"


@dataclass
class ProvenanceChainLink:
    """One hop in the provenance audit chain (newest last or root first)."""

    stage: str
    source_type: str | None = None
    source_url: str | None = None
    root_source_type: str | None = None
    observed_at: str | None = None
    notes: str | None = None
    tainted: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProvenanceTrustResult:
    """Recalculated provenance trust — never inherits sticky VERIFIED alone."""

    provenance_trust: str
    provenance_chain_valid: bool
    root_source_type: str
    root_source_url: str | None
    observed_at: str | None
    verification_method: str
    derived_from_fixture: bool
    derived_from_demo: bool
    derived_from_synthetic: bool
    taint_reasons: list[str] = field(default_factory=list)
    provenance_chain: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provenance_trust": self.provenance_trust,
            "provenance_chain_valid": self.provenance_chain_valid,
            "root_source_type": self.root_source_type,
            "root_source_url": self.root_source_url,
            "observed_at": self.observed_at,
            "verification_method": self.verification_method,
            "derived_from_fixture": self.derived_from_fixture,
            "derived_from_demo": self.derived_from_demo,
            "derived_from_synthetic": self.derived_from_synthetic,
            "taint_reasons": list(self.taint_reasons),
            "provenance_chain": list(self.provenance_chain),
        }


def domain_of_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.rsplit("@", 1)[-1].strip().lower().removeprefix("www.") or None


def domain_of_url(url: str | None) -> str | None:
    if not url:
        return None
    s = str(url).strip()
    if not s:
        return None
    if "://" not in s:
        s = "https://" + s
    try:
        host = urlparse(s).hostname or ""
    except ValueError:
        return None
    return host.lower().removeprefix("www.") or None


def is_demo_or_fixture_domain(domain: str | None) -> bool:
    if not domain:
        return False
    d = domain.lower().strip().removeprefix("www.")
    return any(rx.search(d) for rx in _DEMO_DOMAIN_RES)


def is_demo_or_fixture_email(email: str | None) -> bool:
    if not email:
        return False
    e = email.strip().lower()
    if any(rx.search(e) for rx in _DEMO_EMAIL_LOCAL_RES):
        return True
    return is_demo_or_fixture_domain(domain_of_email(e))


def _looks_fixture_url(url: str | None) -> bool:
    if not url:
        return False
    u = str(url).lower()
    return any(m in u for m in _FIXTURE_URL_MARKERS)


def _looks_fixture_notes(notes: str | None) -> bool:
    if not notes:
        return False
    n = str(notes).lower()
    return any(m in n for m in _TAINT_NOTE_MARKERS)


def classify_root_source_type(
    *,
    source_type: str | None = None,
    source_url: str | None = None,
    email: str | None = None,
    official_domain: str | None = None,
    notes: str | None = None,
    fixtures_dir_used: bool = False,
    synthetic_flag: bool = False,
    demo_flag: bool = False,
    epistemic_class: str | None = None,
    prior_links: list[dict[str, Any]] | None = None,
) -> tuple[str, list[str]]:
    """Classify the root origin. Returns (root_source_type, taint_reasons)."""
    reasons: list[str] = []
    st = (source_type or "").strip().lower()

    # Explicit flags
    if synthetic_flag:
        reasons.append("synthetic_flag")
        return RootSourceType.SYNTHETIC.value, reasons
    if demo_flag:
        reasons.append("demo_flag")
        return RootSourceType.DEMO.value, reasons
    if fixtures_dir_used:
        reasons.append("fixtures_dir_used")
        return RootSourceType.TEST_FIXTURE.value, reasons

    # Transitive: any prior link already tainted
    for link in prior_links or []:
        if not isinstance(link, dict):
            continue
        root = str(link.get("root_source_type") or "").upper()
        if root in TAINTED_ROOTS or link.get("tainted") is True:
            reasons.append(f"transitive_taint:{root or link.get('stage') or 'prior'}")
            return RootSourceType.DERIVED_UNTRUSTED.value, reasons
        st_prior = str(link.get("source_type") or "").lower()
        if st_prior in _FIXTURE_SOURCE_TYPES:
            reasons.append(f"transitive_fixture_source:{st_prior}")
            return RootSourceType.DERIVED_UNTRUSTED.value, reasons

    if st in _FIXTURE_SOURCE_TYPES:
        reasons.append(f"source_type:{st}")
        if st in {"demo"}:
            return RootSourceType.DEMO.value, reasons
        if st in {"synthetic", "generated", "fake", "mock"}:
            return RootSourceType.SYNTHETIC.value, reasons
        return RootSourceType.TEST_FIXTURE.value, reasons

    if is_demo_or_fixture_email(email):
        reasons.append(f"demo_email:{email}")
        return RootSourceType.DEMO.value, reasons

    dom = domain_of_email(email) or domain_of_url(source_url) or (official_domain or "").lower()
    if is_demo_or_fixture_domain(dom):
        reasons.append(f"demo_domain:{dom}")
        return RootSourceType.DEMO.value, reasons

    if _looks_fixture_url(source_url):
        reasons.append(f"fixture_url:{source_url}")
        return RootSourceType.TEST_FIXTURE.value, reasons

    if _looks_fixture_notes(notes):
        reasons.append("fixture_notes")
        return RootSourceType.TEST_FIXTURE.value, reasons

    # prior verified without real chain is untrusted
    if st in {"prior_verified", "cached_candidate", "embedded_verified"}:
        reasons.append(f"untrusted_sticky_label:{st}")
        return RootSourceType.DERIVED_UNTRUSTED.value, reasons

    if epistemic_class and str(epistemic_class).upper() in {"SYNTHETIC", "FIXTURE", "DEMO"}:
        reasons.append(f"epistemic:{epistemic_class}")
        return RootSourceType.SYNTHETIC.value, reasons

    mapped = _REAL_SOURCE_TYPES.get(st)
    if mapped:
        # web_search without a real non-fixture URL is unknown
        if st == "web_search" and (not source_url or _looks_fixture_url(source_url)):
            reasons.append("web_search_missing_real_url")
            return RootSourceType.UNKNOWN.value, reasons
        # registry with only placeholder URL still OK if not demo domain
        return mapped, reasons

    if not st and not source_url and not email:
        reasons.append("missing_all_provenance")
        return RootSourceType.UNKNOWN.value, reasons

    if not st:
        reasons.append("missing_source_type")
        return RootSourceType.UNKNOWN.value, reasons

    reasons.append(f"unclassified_source_type:{st}")
    return RootSourceType.UNKNOWN.value, reasons


def evaluate_provenance_trust(
    *,
    email: str | None = None,
    source_type: str | None = None,
    source_url: str | None = None,
    source_document: str | None = None,
    observed_at: str | None = None,
    notes: str | None = None,
    official_domain: str | None = None,
    verification_status: str | None = None,
    ownership_status: str | None = None,
    epistemic_class: str | None = None,
    fixtures_dir_used: bool = False,
    synthetic_flag: bool = False,
    demo_flag: bool = False,
    provenance_chain: list[dict[str, Any]] | None = None,
    derived_from_fixture: bool | None = None,
    parent_provenance: dict[str, Any] | None = None,
    verification_method: str | None = None,
) -> ProvenanceTrustResult:
    """Recalculate provenance trust from evidence — labels do not override taint."""
    chain_in: list[dict[str, Any]] = list(provenance_chain or [])
    if parent_provenance and isinstance(parent_provenance, dict):
        # Parent is an earlier hop (e.g. cache → live candidate).
        parent_link = {
            "stage": "parent",
            "source_type": parent_provenance.get("source_type") or parent_provenance.get("root_source_type"),
            "source_url": parent_provenance.get("source_url") or parent_provenance.get("root_source_url"),
            "root_source_type": parent_provenance.get("root_source_type"),
            "observed_at": parent_provenance.get("observed_at"),
            "notes": parent_provenance.get("notes"),
            "tainted": parent_provenance.get("provenance_trust")
            in {
                ProvenanceTrust.TAINTED.value,
                ProvenanceTrust.UNKNOWN.value,
            }
            or parent_provenance.get("derived_from_fixture") is True
            or parent_provenance.get("provenance_chain_valid") is False,
        }
        chain_in = [parent_link, *chain_in]
        if parent_provenance.get("provenance_chain"):
            chain_in = list(parent_provenance["provenance_chain"]) + chain_in

    # Explicit derived_from_fixture on payload
    if derived_from_fixture is True:
        synthetic_flag = synthetic_flag or False
        fixtures_dir_used = True

    root, reasons = classify_root_source_type(
        source_type=source_type,
        source_url=source_url,
        email=email,
        official_domain=official_domain,
        notes=notes,
        fixtures_dir_used=fixtures_dir_used,
        synthetic_flag=synthetic_flag,
        demo_flag=demo_flag,
        epistemic_class=epistemic_class,
        prior_links=chain_in,
    )

    # Site-bound provenance host must match email/company domain (fail-closed).
    # Foreign root (e.g. caiafafacilities.com.br for connector.eng.br) cannot validate.
    # Only applied when not already tainted (preserve DEMO/FIXTURE root type for diagnostics).
    if root not in TAINTED_ROOTS:
        host_ok, host_reason = provenance_host_aligned_with_email(
            email,
            source_url=source_url or source_document,
            source_type=source_type,
            provenance_chain=chain_in,
            official_domain=official_domain,
        )
        if not host_ok:
            reasons.append(host_reason)
            root = RootSourceType.DERIVED_UNTRUSTED.value

    derived_fixture = root == RootSourceType.TEST_FIXTURE.value or any(
        "fixture" in r for r in reasons
    )
    derived_demo = root == RootSourceType.DEMO.value or any("demo" in r for r in reasons)
    derived_synth = root == RootSourceType.SYNTHETIC.value or any(
        "synthetic" in r for r in reasons
    )

    # Sticky labels cannot wash taint.
    ver = (verification_status or "").strip().upper()
    own = (ownership_status or "").strip().upper()
    if root in TAINTED_ROOTS:
        if ver in {"VERIFIED", "OBSERVED", "HUMAN_CONFIRMED"}:
            reasons.append(f"sticky_verification_ignored:{ver}")
        if own in {"COMPANY_OWNED", "HUMAN_CONFIRMED", "LIKELY_COMPANY_OWNED"}:
            reasons.append(f"sticky_ownership_ignored:{own}")

    chain_out = list(chain_in)
    chain_out.append(
        {
            "stage": "contact_resolution",
            "source_type": source_type,
            "source_url": source_url or source_document,
            "root_source_type": root,
            "observed_at": observed_at,
            "notes": notes,
            "tainted": root in TAINTED_ROOTS,
        }
    )

    method = (verification_method or "").strip() or (
        "real_source_observation" if root in TRUSTED_ROOTS else "untrusted_or_unknown"
    )

    if root in TAINTED_ROOTS:
        return ProvenanceTrustResult(
            provenance_trust=ProvenanceTrust.TAINTED.value
            if root != RootSourceType.UNKNOWN.value
            else ProvenanceTrust.UNKNOWN.value,
            provenance_chain_valid=False,
            root_source_type=root,
            root_source_url=source_url,
            observed_at=observed_at,
            verification_method=method,
            derived_from_fixture=derived_fixture or root == RootSourceType.TEST_FIXTURE.value,
            derived_from_demo=derived_demo or root == RootSourceType.DEMO.value,
            derived_from_synthetic=derived_synth or root == RootSourceType.SYNTHETIC.value,
            taint_reasons=reasons,
            provenance_chain=chain_out,
        )

    # Trusted root
    trust = ProvenanceTrust.REAL_OBSERVED.value
    if root == RootSourceType.REAL_HUMAN_DECISION.value:
        trust = ProvenanceTrust.HUMAN_ATTRIBUTABLE.value
    elif ver in {"VERIFIED"} and root in TRUSTED_ROOTS:
        trust = ProvenanceTrust.REAL_VERIFIED.value

    return ProvenanceTrustResult(
        provenance_trust=trust,
        provenance_chain_valid=True,
        root_source_type=root,
        root_source_url=source_url,
        observed_at=observed_at,
        verification_method=method,
        derived_from_fixture=False,
        derived_from_demo=False,
        derived_from_synthetic=False,
        taint_reasons=[],
        provenance_chain=chain_out,
    )


def extract_provenance_fields(contact: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize provenance fields from candidate / contact / feed shapes."""
    c = contact or {}
    src = c.get("source") if isinstance(c.get("source"), dict) else {}
    prov = c.get("provenance") if isinstance(c.get("provenance"), dict) else {}
    trust_block = c.get("provenance_trust_detail") if isinstance(c.get("provenance_trust_detail"), dict) else {}

    source_type = (
        src.get("source_type")
        or prov.get("source_type")
        or c.get("source_type")
        or (c.get("source_types") or [None])[0]
        or trust_block.get("root_source_type")
    )
    source_url = (
        src.get("source_url")
        or prov.get("source_url")
        or c.get("source_url")
        or (c.get("source_urls") or [None])[0]
        or trust_block.get("root_source_url")
    )
    notes = src.get("notes") or prov.get("notes") or c.get("notes")
    observed_at = (
        src.get("observed_at")
        or prov.get("observed_at")
        or c.get("observed_at")
        or c.get("resolved_at")
    )
    chain = (
        c.get("provenance_chain")
        or prov.get("provenance_chain")
        or trust_block.get("provenance_chain")
        or []
    )
    return {
        "email": c.get("email") or c.get("value"),
        "source_type": source_type,
        "source_url": source_url,
        "source_document": src.get("source_document") or prov.get("source_document") or c.get("source_document"),
        "observed_at": observed_at,
        "notes": notes,
        "official_domain": c.get("official_domain") or c.get("domain"),
        "verification_status": c.get("verification_status"),
        "ownership_status": c.get("ownership_status"),
        "epistemic_class": c.get("epistemic_class"),
        "fixtures_dir_used": bool(c.get("fixtures_dir_used") or c.get("from_fixture")),
        "synthetic_flag": bool(c.get("synthetic") or c.get("is_synthetic")),
        "demo_flag": bool(c.get("demo") or c.get("is_demo")),
        "derived_from_fixture": c.get("derived_from_fixture"),
        "provenance_chain": list(chain) if isinstance(chain, list) else [],
        "parent_provenance": c.get("parent_provenance") if isinstance(c.get("parent_provenance"), dict) else None,
        "verification_method": c.get("verification_method") or prov.get("verification_method"),
    }


def evaluate_contact_provenance(contact: dict[str, Any] | None) -> ProvenanceTrustResult:
    fields = extract_provenance_fields(contact)
    return evaluate_provenance_trust(**fields)


def provenance_blocks_send(result: ProvenanceTrustResult) -> bool:
    """True when provenance must block EMAIL_SEND_READY."""
    return not result.provenance_chain_valid or result.provenance_trust in {
        ProvenanceTrust.TAINTED.value,
        ProvenanceTrust.UNKNOWN.value,
    }


# Invalidation marker for contaminated cohorts (machine-readable).
INVALIDATED_REASON_PROVENANCE_CONTAMINATION = "PROVENANCE_CONTAMINATION"
INVALIDATION_STATUS = "INVALIDATED"
