"""SEI public consultation adapter (process portal family).

Observed working surface:
  GET/POST .../sei/modulos/pesquisa/md_pesq_processo_pesquisar.php
    ?acao_externa=protocolo_pesquisar&acao_origem_externa=protocolo_pesquisar
    &id_orgao_acesso_externo=0

Many federal organs share ColaboraGov:
  https://colaboragov.sei.gov.br

Search often requires captcha (txtInfraCaptcha). When captcha is required and
unsolved, return CAPTCHA_BLOCKED — do not invent results from default pages.

When search succeeds, parse process/document links and optional emails from
external document consultation pages.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from scripts.confenge_process_enrichment.identifiers import digits_only, normalize_cnpj

USER_AGENT = "extra-cli-confenge-sei-public/1.0 (+process-first-enrichment)"
DEFAULT_TIMEOUT = (8.0, 25.0)

# Observed live bases (not invented). Prefer shared ColaboraGov for federal.
KNOWN_SEI_BASES: list[str] = [
    "https://colaboragov.sei.gov.br",
    "https://sei.mj.gov.br",
    "https://sei.cgu.gov.br",
]

# Organ root CNPJ → preferred SEI base (lazy seeds from observed federal share)
ORG_ROOT_TO_SEI: dict[str, str] = {
    # Ministério da Gestão / Economia cluster often on ColaboraGov / shared
    "00394460": "https://colaboragov.sei.gov.br",
    # CGU
    "00394445": "https://sei.cgu.gov.br",  # may need validation; fallback ColaboraGov
    # MJ
    "00421765": "https://sei.mj.gov.br",
}

_SEI_URL_RE = re.compile(r"(?i)https?://[^\s\"']*sei[^\s\"']*")
_PROTO_RE = re.compile(r"\b\d{5}\.\d{6}/\d{4}-\d{2}\b")
_EMAIL_RE = re.compile(
    r"(?i)\b([a-z0-9][a-z0-9._%+\-]{0,63}@[a-z0-9][a-z0-9.\-]{1,63}\.[a-z]{2,24})\b"
)


def is_sei_url(url: str | None) -> bool:
    if not url:
        return False
    u = url.lower()
    return "sei." in u or "/sei/" in u or "colaboragov.sei" in u


def format_sei_protocol(process_number: str | None) -> list[str]:
    """Return SEI/NUP protocol variants to try in public search."""
    if not process_number:
        return []
    raw = str(process_number).strip()
    out: list[str] = []
    # Already SEI-shaped
    if _PROTO_RE.search(raw):
        out.append(_PROTO_RE.search(raw).group(0))  # type: ignore[union-attr]
    d = digits_only(raw)
    # NUP 17 digits: NNNNN.NNNNNN/YYYY-DD
    if len(d) == 17:
        out.append(f"{d[0:5]}.{d[5:11]}/{d[11:15]}-{d[15:17]}")
    # 15 digits occasional
    if len(d) == 15:
        out.append(f"{d[0:5]}.{d[5:11]}/{d[11:15]}-{d[13:15]}")
    # Keep original and slash variants
    out.append(raw)
    if "/" in raw and "." not in raw:
        out.append(raw)
    # de-dupe
    seen: set[str] = set()
    uniq: list[str] = []
    for v in out:
        if v and v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq


def research_url(base: str) -> str:
    base = base.rstrip("/")
    return (
        f"{base}/sei/modulos/pesquisa/md_pesq_processo_pesquisar.php"
        "?acao_externa=protocolo_pesquisar"
        "&acao_origem_externa=protocolo_pesquisar"
        "&id_orgao_acesso_externo=0"
    )


def resolve_sei_base_for_organ(
    *,
    orgao_cnpj: str | None,
    known_base: str | None = None,
) -> list[str]:
    """Ordered SEI bases to try for an organ."""
    bases: list[str] = []
    if known_base:
        bases.append(known_base.rstrip("/"))
    root = normalize_cnpj(orgao_cnpj)[:8] if orgao_cnpj else ""
    if root and root in ORG_ROOT_TO_SEI:
        bases.append(ORG_ROOT_TO_SEI[root].rstrip("/"))
    for b in KNOWN_SEI_BASES:
        bases.append(b.rstrip("/"))
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for b in bases:
        if b not in seen:
            seen.add(b)
            out.append(b)
    return out


@dataclass
class SeiSearchResult:
    base_url: str
    protocol_tried: str
    process_urls: list[str] = field(default_factory=list)
    document_urls: list[str] = field(default_factory=list)
    document_index: list[dict[str, Any]] = field(default_factory=list)
    emails_observed: list[dict[str, Any]] = field(default_factory=list)
    captcha_required: bool = False
    blocked: bool = False
    blocker: str | None = None
    matched_protocol: bool = False
    raw_status: int | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "protocol_tried": self.protocol_tried,
            "process_urls": self.process_urls,
            "document_urls": self.document_urls,
            "document_index": self.document_index,
            "emails_observed_count": len(self.emails_observed),
            "captcha_required": self.captcha_required,
            "blocked": self.blocked,
            "blocker": self.blocker,
            "matched_protocol": self.matched_protocol,
            "raw_status": self.raw_status,
            "notes": self.notes,
        }


class SeiPublicAdapter:
    portal_family = "sei"
    source_id = "sei_public"

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        timeout: tuple[float, float] = DEFAULT_TIMEOUT,
        request_delay: float = 0.35,
    ) -> None:
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.session.headers.setdefault("Accept", "text/html,application/xhtml+xml")
        self.timeout = timeout
        self.request_delay = request_delay

    def _sleep(self) -> None:
        if self.request_delay > 0:
            time.sleep(self.request_delay)

    def _get(self, url: str) -> tuple[int | None, str | None, str | None]:
        try:
            self._sleep()
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            return resp.status_code, resp.text, None
        except requests.Timeout:
            return None, None, "timeout"
        except requests.RequestException as exc:
            return None, None, str(exc)

    def _post(self, url: str, data: dict[str, str]) -> tuple[int | None, str | None, str | None]:
        try:
            self._sleep()
            resp = self.session.post(url, data=data, timeout=self.timeout, allow_redirects=True)
            return resp.status_code, resp.text, None
        except requests.Timeout:
            return None, None, "timeout"
        except requests.RequestException as exc:
            return None, None, str(exc)

    def _parse_form_fields(self, html: str) -> dict[str, str]:
        fields: dict[str, str] = {}
        for inp in re.findall(r"<input[^>]+>", html or "", flags=re.I):
            name_m = re.search(r'name=["\']([^"\']+)', inp, flags=re.I)
            if not name_m:
                continue
            val_m = re.search(r'value=["\']([^"\']*)', inp, flags=re.I)
            fields[name_m.group(1)] = val_m.group(1) if val_m else ""
        return fields

    def _page_requires_captcha(self, html: str, fields: dict[str, str]) -> bool:
        if "txtInfraCaptcha" in fields:
            return True
        if re.search(r"(?i)captcha", html or "") and "hdnInfraCaptcha" in fields:
            # Some instances set hdnInfraCaptcha=0 when disabled
            if str(fields.get("hdnInfraCaptcha", "0")) not in {"0", "", "false", "False"}:
                return True
            # Presence of captcha input still means human may be required for valid search
            if "txtInfraCaptcha" in (html or ""):
                return True
        return "txtInfraCaptcha" in (html or "")

    def _extract_links(self, html: str, base_url: str) -> tuple[list[str], list[str]]:
        process_urls: list[str] = []
        document_urls: list[str] = []
        for href in re.findall(r'href=["\']([^"\']+)["\']', html or "", flags=re.I):
            href = href.replace("&amp;", "&")
            full = urljoin(base_url, href)
            if "md_pesq_processo_exibir" in full:
                if full not in process_urls:
                    process_urls.append(full)
            elif "md_pesq_documento" in full or "documento_consulta" in full:
                if full not in document_urls:
                    document_urls.append(full)
        return process_urls, document_urls

    def _results_match_protocol(self, html: str, protocol: str) -> bool:
        """True only if search result page contains the queried protocol digits."""
        d_proto = digits_only(protocol)
        if len(d_proto) < 8:
            return False
        d_page = digits_only(html or "")
        # Require substantial protocol presence (avoid false match on short prefixes)
        return d_proto in d_page or d_proto[:12] in d_page

    def search_protocol(
        self,
        protocol: str,
        *,
        base_url: str,
        allow_unverified_results: bool = False,
    ) -> SeiSearchResult:
        """Search SEI public research for a protocol number."""
        base = base_url.rstrip("/")
        url = research_url(base)
        result = SeiSearchResult(base_url=base, protocol_tried=protocol)
        code, html, err = self._get(url)
        result.raw_status = code
        if code is None:
            result.blocked = True
            result.blocker = f"CONNECTION_FAILED:{err}"
            return result
        if code in (401, 403):
            result.blocked = True
            result.blocker = "AUTH_REQUIRED"
            return result
        if code != 200 or not html:
            result.blocked = True
            result.blocker = f"HTTP_{code}"
            return result

        fields = self._parse_form_fields(html)
        if "txtProtocoloPesquisa" not in fields:
            result.blocked = True
            result.blocker = "SEI_FORM_NOT_FOUND"
            result.notes.append("public research form missing txtProtocoloPesquisa")
            return result

        captcha = self._page_requires_captcha(html, fields)
        result.captcha_required = captcha

        fields["txtProtocoloPesquisa"] = protocol
        fields["chkSinProcessos"] = fields.get("chkSinProcessos") or "P"
        fields["chkSinDocumentosGerados"] = fields.get("chkSinDocumentosGerados") or "G"
        fields["chkSinDocumentosRecebidos"] = fields.get("chkSinDocumentosRecebidos") or "R"
        fields["hdnFlagPesquisa"] = "1"
        fields["sbmPesquisar"] = fields.get("sbmPesquisar") or "Pesquisar"

        if captcha and not (fields.get("txtInfraCaptcha") or "").strip():
            # Do not trust default/cached result pages without captcha
            result.blocked = True
            result.blocker = "CAPTCHA_BLOCKED"
            result.notes.append("SEI public search requires captcha; not solved in automation")
            # Still record research URL for human follow-up / registry
            return result

        pcode, phtml, perr = self._post(url, fields)
        result.raw_status = pcode
        if pcode is None:
            result.blocked = True
            result.blocker = f"CONNECTION_FAILED:{perr}"
            return result
        if pcode in (401, 403):
            result.blocked = True
            result.blocker = "AUTH_REQUIRED"
            return result
        if pcode != 200 or not phtml:
            result.blocked = True
            result.blocker = f"HTTP_{pcode}"
            return result

        matched = self._results_match_protocol(phtml, protocol)
        result.matched_protocol = matched
        if not matched and not allow_unverified_results:
            # Default pages often list unrelated processes when captcha fails silently
            if re.search(r"(?i)captcha", phtml):
                result.blocked = True
                result.blocker = "CAPTCHA_BLOCKED"
                result.notes.append("result page did not contain queried protocol; captcha likely required")
                return result
            result.notes.append("queried protocol not found in result page")
            result.blocker = "PROCESS_NOT_FOUND"
            return result

        research_base = urljoin(url, ".")
        procs, docs = self._extract_links(phtml, research_base)
        result.process_urls = procs
        result.document_urls = docs
        for u in docs:
            result.document_index.append(
                {
                    "url": u,
                    "title": "sei_document",
                    "source": "sei_public_search",
                    "priority_label": "qualification",
                    "company_authored_likely": True,
                }
            )
        for u in procs:
            result.document_index.append(
                {
                    "url": u,
                    "title": "sei_process",
                    "source": "sei_public_search",
                    "priority_label": "other",
                    "company_authored_likely": False,
                }
            )
        return result

    def expand_process_page(self, process_url: str, *, max_docs: int = 30) -> list[dict[str, Any]]:
        """Fetch SEI process display page and collect document consultation links."""
        code, html, err = self._get(process_url)
        if code != 200 or not html:
            return []
        docs: list[dict[str, Any]] = []
        base = process_url
        for href in re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I):
            href = href.replace("&amp;", "&")
            full = urljoin(base, href)
            title = None
            if "documento" in full.lower() or "md_pesq_documento" in full:
                # try nearby text - best effort from filename-like query
                title = "sei_doc"
                docs.append(
                    {
                        "url": full,
                        "title": title,
                        "source": "sei_process_page",
                        "priority_label": "qualification",
                        "company_authored_likely": True,
                    }
                )
            if len(docs) >= max_docs:
                break
        return docs

    def extract_emails_from_url(self, url: str) -> list[dict[str, Any]]:
        code, html, err = self._get(url)
        if code != 200 or not html:
            return []
        # If PDF binary was returned as text badly, skip
        if html[:4] == "%PDF" or "application/pdf" in (html[:200] or ""):
            return []
        out: list[dict[str, Any]] = []
        for em in _EMAIL_RE.findall(html):
            out.append(
                {
                    "email": em.lower(),
                    "source_url": url,
                    "source": "sei_public",
                    "document_type": "sei_document",
                }
            )
        return out

    def resolve_and_list_docs(
        self,
        process_number: str | None,
        *,
        orgao_cnpj: str | None = None,
        known_base: str | None = None,
        max_bases: int = 2,
        max_protocols: int = 2,
    ) -> SeiSearchResult:
        """Try protocol variants against organ SEI bases; first useful outcome wins."""
        protocols = format_sei_protocol(process_number)[:max_protocols]
        # Prefer a single federal shared base when process looks like NUP
        bases = resolve_sei_base_for_organ(orgao_cnpj=orgao_cnpj, known_base=known_base)[:max_bases]
        # Cap to one base when captcha is expected (ColaboraGov) unless known_base given
        if not known_base and len(bases) > 1:
            bases = bases[:1]
        last = SeiSearchResult(base_url=bases[0] if bases else "", protocol_tried=protocols[0] if protocols else "")
        if not protocols:
            last.blocker = "PROCESS_NUMBER_MISSING"
            last.blocked = True
            return last
        captcha_hits = 0
        for base in bases:
            for proto in protocols:
                res = self.search_protocol(proto, base_url=base)
                last = res
                if res.blocker == "CAPTCHA_BLOCKED":
                    captcha_hits += 1
                    continue
                if res.matched_protocol and (res.process_urls or res.document_urls):
                    # expand first process page for more docs
                    for pu in res.process_urls[:2]:
                        extra = self.expand_process_page(pu)
                        for d in extra:
                            if d["url"] not in {x.get("url") for x in res.document_index}:
                                res.document_index.append(d)
                                if d["url"] not in res.document_urls:
                                    res.document_urls.append(d["url"])
                    return res
                if res.document_urls or res.process_urls:
                    return res
        if captcha_hits and last.blocker is None:
            last.blocker = "CAPTCHA_BLOCKED"
            last.blocked = True
            last.captcha_required = True
        return last
