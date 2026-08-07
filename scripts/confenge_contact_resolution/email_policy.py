"""Email policy: preserve exact addresses; never treat pattern-guess as enrollable.

Layers (independent, no outbound verification mail):
  1. syntactic
  2. domain shape / freemail heuristics
  3. MX lookup (optional, injectable; skipped offline)
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from scripts.confenge_contact_resolution.models import (
    EmailVerificationLayers,
    VerificationStatus,
)

# Common freemail — lower confidence, still may be OBSERVED if registry-linked.
FREEMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "hotmail.com",
        "yahoo.com",
        "yahoo.com.br",
        "outlook.com",
        "live.com",
        "icloud.com",
        "uol.com.br",
        "bol.com.br",
        "terra.com.br",
        "msn.com",
        "protonmail.com",
        "aol.com",
    }
)

# Functional mailbox local-parts often used by SMBs / public pages.
FUNCTIONAL_LOCAL_PARTS = frozenset(
    {
        "contato",
        "contact",
        "comercial",
        "vendas",
        "sales",
        "orcamento",
        "orçamento",
        "financeiro",
        "adm",
        "admin",
        "administrativo",
        "licitacao",
        "licitacoes",
        "licitações",
        "contratos",
        "engenharia",
        "obras",
        "rh",
        "suporte",
        "sac",
        "atendimento",
        "info",
        "ouvidoria",
        "diretoria",
        "secretaria",
    }
)

_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9](?:[a-zA-Z0-9._%+\-]{0,62}[a-zA-Z0-9])?@"
    r"[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)+$"
)

# nome.sobrenome@ / n.sobrenome@ / nome_sobrenome@ style personal pattern guess
_PERSONAL_PATTERN_RE = re.compile(
    r"^[a-z]{2,}[._][a-z]{2,}(?:[._][a-z]+)?$",
    re.I,
)


@dataclass(frozen=True)
class EmailAssessment:
    email: str | None
    email_display: str | None
    verification_status: str
    layers: EmailVerificationLayers
    is_functional: bool
    is_freemail: bool
    is_pattern_guessed: bool
    enrollable: bool
    confidence_delta: float
    notes: list[str]


def normalize_email_display(raw: str | None) -> str | None:
    """Preserve exact observed string after strip; do not rewrite case beyond strip."""
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def syntactic_ok(email: str | None) -> bool:
    if not email:
        return False
    e = email.strip()
    if len(e) > 254 or "@" not in e:
        return False
    return bool(_EMAIL_RE.match(e))


def domain_of(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.strip().rsplit("@", 1)[-1].lower()


def local_part_of(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.strip().split("@", 1)[0].lower()


def is_freemail(email: str | None) -> bool:
    d = domain_of(email)
    return bool(d and d in FREEMAIL_DOMAINS)


def is_functional_mailbox(email: str | None) -> bool:
    local = local_part_of(email)
    if not local:
        return False
    base = local.split("+", 1)[0]
    if base in FUNCTIONAL_LOCAL_PARTS:
        return True
    # contatos@ / comercial.sc@ etc.
    return any(base.startswith(p) for p in ("contato", "comercial", "licit", "vendas", "orcamento"))


def looks_like_personal_pattern(email: str | None) -> bool:
    """True when local-part matches nome.sobrenome style (pattern-guess risk)."""
    local = local_part_of(email)
    if not local or is_functional_mailbox(email):
        return False
    return bool(_PERSONAL_PATTERN_RE.match(local))


def domain_shape_ok(email: str | None) -> bool:
    d = domain_of(email)
    if not d or "." not in d:
        return False
    labels = d.split(".")
    if any(not lab or len(lab) > 63 for lab in labels):
        return False
    tld = labels[-1]
    return tld.isalpha() and len(tld) >= 2


def check_mx(
    domain: str,
    *,
    resolver: Callable[[str], bool] | None = None,
) -> bool | None:
    """Return True/False if checked, None if not checked.

    Default uses dnspython when available; never sends mail.
    Inject ``resolver`` in tests.
    """
    if resolver is not None:
        return bool(resolver(domain))
    try:
        import dns.resolver  # type: ignore[import-untyped]
    except ImportError:
        return None
    try:
        answers = dns.resolver.resolve(domain, "MX")
        return len(list(answers)) > 0
    except Exception:  # noqa: BLE001 — MX probe is best-effort
        try:
            answers = dns.resolver.resolve(domain, "A")
            return len(list(answers)) > 0
        except Exception:  # noqa: BLE001
            return False


def assess_email(
    raw: str | None,
    *,
    pattern_guessed: bool = False,
    check_mx_flag: bool = False,
    mx_resolver: Callable[[str], bool] | None = None,
) -> EmailAssessment:
    display = normalize_email_display(raw)
    if not display:
        return EmailAssessment(
            email=None,
            email_display=None,
            verification_status=VerificationStatus.NOT_AVAILABLE.value,
            layers=EmailVerificationLayers(),
            is_functional=False,
            is_freemail=False,
            is_pattern_guessed=False,
            enrollable=False,
            confidence_delta=0.0,
            notes=["email_absent"],
        )

    # Canonical lower for comparisons only; keep display exact.
    canonical = display.lower()
    notes: list[str] = []
    syn = syntactic_ok(canonical)
    dom = domain_shape_ok(canonical) if syn else False
    freemail = is_freemail(canonical) if syn else False
    functional = is_functional_mailbox(canonical) if syn else False
    # Explicit pattern_guessed from adapter wins; auto-detect alone does NOT force
    # CANDIDATE_UNVERIFIED (observed nome.sobrenome on a site can be real).
    # Only adapter-declared pattern guesses are non-enrollable by policy.
    is_guess = bool(pattern_guessed)

    mx_ok: bool | None = None
    mx_checked = False
    if check_mx_flag and syn and dom:
        d = domain_of(canonical)
        if d:
            mx_ok = check_mx(d, resolver=mx_resolver)
            mx_checked = mx_ok is not None

    layers = EmailVerificationLayers(
        syntactic_ok=syn,
        domain_ok=dom,
        mx_ok=mx_ok,
        mx_checked=mx_checked,
        pattern_guessed=is_guess,
    )

    if not syn:
        return EmailAssessment(
            email=canonical,
            email_display=display,
            verification_status=VerificationStatus.SYNTAX_INVALID.value,
            layers=layers,
            is_functional=False,
            is_freemail=freemail,
            is_pattern_guessed=is_guess,
            enrollable=False,
            confidence_delta=0.0,
            notes=["email_syntax_invalid"],
        )

    if is_guess:
        notes.append("pattern_guessed_personal_email_not_enrollable")
        return EmailAssessment(
            email=canonical,
            email_display=display,
            verification_status=VerificationStatus.CANDIDATE_UNVERIFIED.value,
            layers=layers,
            is_functional=functional,
            is_freemail=freemail,
            is_pattern_guessed=True,
            enrollable=False,
            confidence_delta=0.05,
            notes=notes,
        )

    # Observed exact address
    delta = 0.35
    if freemail:
        delta = 0.12
        notes.append("freemail_lower_confidence")
    if functional:
        delta = max(delta, 0.28)
        notes.append("functional_mailbox")
    if mx_ok is True:
        delta += 0.05
        notes.append("mx_ok")
    elif mx_ok is False:
        delta -= 0.1
        notes.append("mx_missing")

    return EmailAssessment(
        email=canonical,
        email_display=display,
        verification_status=VerificationStatus.OBSERVED.value,
        layers=layers,
        is_functional=functional,
        is_freemail=freemail,
        is_pattern_guessed=False,
        enrollable=True,  # enrollable as contact candidate; Warmbly still decides channel
        confidence_delta=max(0.0, min(0.5, delta)),
        notes=notes,
    )
