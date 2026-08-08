"""Deterministic contact extraction from HTML/text (no LLM)."""

from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse

_EMAIL_RE = re.compile(
    r"(?i)\b([a-z0-9][a-z0-9._%+\-]{0,63}@[a-z0-9][a-z0-9.\-]{1,63}\.[a-z]{2,24})\b"
)
_PHONE_RE = re.compile(
    r"(?i)(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?(?:9\s*)?\d{4,5}[-\s]?\d{4}"
)
_WA_RE = re.compile(
    r"(?i)(?:https?://)?(?:api\.)?whatsapp\.com/send\?[^\s\"'<>]+|"
    r"(?:https?://)?wa\.me/\d{10,15}|"
    r"whatsapp\s*[:\-]?\s*(\+?\d[\d\s\-()]{8,20})"
)
_MAILTO_RE = re.compile(r"(?i)mailto:([a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,24})")
_TEL_RE = re.compile(r"(?i)tel:([+\d][\d\s\-()]{7,20})")
_HREF_RE = re.compile(r"(?i)href=[\"']([^\"']+)[\"']")
_TITLE_RE = re.compile(r"(?i)<title[^>]*>(.*?)</title>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# Paths that look like contact / about / commercial pages
CONTACTISH_PATH_HINTS = (
    "contato",
    "contact",
    "fale-conosco",
    "fale_conosco",
    "empresa",
    "sobre",
    "about",
    "quem-somos",
    "quem_somos",
    "equipe",
    "team",
    "licitac",
    "comercial",
    "orcament",
    "orçament",
    "engenharia",
    "contrato",
    "trabalhe",
)


def strip_html(html: str) -> str:
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html or "")
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = _TAG_RE.sub(" ", text)
    text = unescape(text)
    return _WS_RE.sub(" ", text).strip()


def extract_emails(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for m in _MAILTO_RE.findall(text or ""):
        e = m.strip().lower()
        if e not in seen and not e.endswith((".png", ".jpg", ".gif", ".svg")):
            seen.add(e)
            found.append(e)
    for m in _EMAIL_RE.findall(text or ""):
        e = m.strip().lower()
        if e in seen:
            continue
        if e.endswith((".png", ".jpg", ".gif", ".svg", ".webp")):
            continue
        if "example.com" in e or "sentry.io" in e or "wixpress.com" in e:
            continue
        seen.add(e)
        found.append(e)
    return found


def extract_phones(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for m in _TEL_RE.findall(text or ""):
        raw = m.strip()
        digits = re.sub(r"\D", "", raw)
        if len(digits) < 10:
            continue
        if digits not in seen:
            seen.add(digits)
            found.append(raw)
    for m in _PHONE_RE.findall(text or ""):
        raw = m.strip()
        digits = re.sub(r"\D", "", raw)
        if len(digits) < 10:
            continue
        if digits not in seen:
            seen.add(digits)
            found.append(raw)
    return found


def extract_whatsapp(text: str) -> list[str]:
    out: list[str] = []
    for m in _WA_RE.finditer(text or ""):
        out.append(m.group(0).strip())
    return out[:10]


def extract_internal_links(html: str, base_url: str, *, same_host: str) -> list[str]:
    """Collect same-domain links, preferring contactish paths."""
    host = same_host.lower().removeprefix("www.")
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    for href in _HREF_RE.findall(html or ""):
        href = href.strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        abs_url = urljoin(base_url, href)
        parsed = urlparse(abs_url)
        if parsed.scheme not in {"http", "https"}:
            continue
        h = (parsed.hostname or "").lower().removeprefix("www.")
        if h != host:
            continue
        clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if clean in seen:
            continue
        seen.add(clean)
        path = (parsed.path or "/").lower()
        score = 0
        for hint in CONTACTISH_PATH_HINTS:
            if hint in path:
                score += 10
        if path in {"/", ""}:
            score += 1
        ranked.append((score, clean))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    return [u for _, u in ranked]


def page_title(html: str) -> str | None:
    m = _TITLE_RE.search(html or "")
    if not m:
        return None
    t = _WS_RE.sub(" ", unescape(m.group(1))).strip()
    return t[:200] or None


def extract_contacts_from_html(
    html: str,
    *,
    source_url: str,
    max_contacts: int = 20,
) -> list[dict[str, Any]]:
    """Return contact dicts suitable for SiteAdapter / contact_pages injection."""
    text = strip_html(html)
    emails = extract_emails(html)  # include mailto from raw
    emails = list(dict.fromkeys(emails + extract_emails(text)))
    phones = extract_phones(html)
    phones = list(dict.fromkeys(phones + extract_phones(text)))
    whatsapp = extract_whatsapp(html)

    contacts: list[dict[str, Any]] = []
    n = max(len(emails), len(phones), 1 if whatsapp else 0)
    n = min(n, max_contacts)
    if not emails and not phones and not whatsapp:
        return []
    for i in range(n):
        email = emails[i] if i < len(emails) else (emails[0] if emails and i == 0 else None)
        phone = phones[i] if i < len(phones) else (phones[0] if phones and i == 0 else None)
        if i > 0 and not (i < len(emails) or i < len(phones)):
            break
        if not email and not phone:
            continue
        # Avoid duplicating the same email+phone pair
        contacts.append(
            {
                "email": email,
                "phone": phone,
                "url": source_url,
                "source_url": source_url,
                "context_text": text[:500],
                "whatsapp_public": whatsapp[0] if whatsapp else None,
                "whatsapp_consent_status": "UNKNOWN",
            }
        )
    # Dedup by email|phone
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for c in contacts:
        key = f"{c.get('email') or ''}|{c.get('phone') or ''}"
        if key in seen or key == "|":
            continue
        seen.add(key)
        out.append(c)
    return out[:max_contacts]


def extract_contacts_from_snippet(
    *,
    title: str | None,
    snippet: str | None,
    url: str | None,
) -> list[dict[str, Any]]:
    blob = " ".join(x for x in (title or "", snippet or "") if x)
    emails = extract_emails(blob)
    phones = extract_phones(blob)
    out: list[dict[str, Any]] = []
    if not emails and not phones:
        return out
    for email in emails or [None]:
        for phone in phones or [None]:
            if not email and not phone:
                continue
            out.append(
                {
                    "email": email,
                    "phone": phone,
                    "url": url,
                    "source_url": url,
                    "name": None,
                    "title_hint": title,
                    "snippet": (snippet or "")[:300],
                }
            )
            break
    return out
