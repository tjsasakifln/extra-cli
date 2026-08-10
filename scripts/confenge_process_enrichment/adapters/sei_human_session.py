"""SEI public research with human-provided captcha / session cookies.

Automated SEI search is captcha-gated on ColaboraGov/MJ. This module provides
an explicit operator path:

1. Operator solves captcha (or supplies session cookies from a browser login).
2. Agent/CLI submits protocol search with captcha answer + cookies.
3. Successful document indexes are returned and can be cached.

Never bypasses captcha silently. Never treats default SEI listing pages as
search results without protocol match.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from scripts.confenge_process_enrichment.adapters.sei_public import (
    SeiPublicAdapter,
    SeiSearchResult,
    format_sei_protocol,
    research_url,
)

USER_AGENT = "extra-cli-confenge-sei-human/1.0"


@dataclass
class HumanSessionSpec:
    """Operator-supplied session material for SEI public research."""

    base_url: str
    captcha_answer: str | None = None
    cookies: dict[str, str] = field(default_factory=dict)
    cookie_header: str | None = None
    notes: str | None = None

    @classmethod
    def from_json_file(cls, path: Path) -> HumanSessionSpec:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            base_url=str(data.get("base_url") or data.get("sei_base_url") or "").rstrip("/"),
            captcha_answer=data.get("captcha_answer") or data.get("txtInfraCaptcha"),
            cookies=dict(data.get("cookies") or {}),
            cookie_header=data.get("cookie_header"),
            notes=data.get("notes"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "captcha_answer_present": bool(self.captcha_answer),
            "cookies_count": len(self.cookies),
            "cookie_header_present": bool(self.cookie_header),
            "notes": self.notes,
        }


class SeiHumanSessionAdapter:
    """SEI search that requires explicit human captcha/session material."""

    portal_family = "sei"
    source_id = "sei_human_session"

    def __init__(
        self,
        session_spec: HumanSessionSpec,
        *,
        session: requests.Session | None = None,
        request_delay: float = 0.35,
    ) -> None:
        if not session_spec.base_url:
            raise ValueError("HumanSessionSpec.base_url is required")
        self.spec = session_spec
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.session.headers.setdefault("Accept", "text/html,application/xhtml+xml")
        if session_spec.cookies:
            self.session.cookies.update(session_spec.cookies)
        if session_spec.cookie_header:
            self.session.headers["Cookie"] = session_spec.cookie_header
        self._inner = SeiPublicAdapter(session=self.session, request_delay=request_delay)

    def search_protocol(self, protocol: str) -> SeiSearchResult:
        """Search with human captcha answer injected into the SEI form."""
        base = self.spec.base_url.rstrip("/")
        url = research_url(base)
        code, html, err = self._inner._get(url)
        result = SeiSearchResult(base_url=base, protocol_tried=protocol, raw_status=code)
        if code != 200 or not html:
            result.blocked = True
            result.blocker = f"CONNECTION_FAILED:{err}" if code is None else f"HTTP_{code}"
            return result

        fields = self._inner._parse_form_fields(html)
        if "txtProtocoloPesquisa" not in fields:
            result.blocked = True
            result.blocker = "SEI_FORM_NOT_FOUND"
            return result

        captcha_needed = self._inner._page_requires_captcha(html, fields)
        result.captcha_required = captcha_needed
        if captcha_needed and not (self.spec.captcha_answer or "").strip():
            result.blocked = True
            result.blocker = "SOURCE_REQUIRES_HUMAN_ACCESS"
            result.notes.append(
                "Captcha required; provide captcha_answer in human session JSON "
                f"(GET {url} first to view captcha image)"
            )
            return result

        fields["txtProtocoloPesquisa"] = protocol
        fields["chkSinProcessos"] = fields.get("chkSinProcessos") or "P"
        fields["chkSinDocumentosGerados"] = fields.get("chkSinDocumentosGerados") or "G"
        fields["chkSinDocumentosRecebidos"] = fields.get("chkSinDocumentosRecebidos") or "R"
        fields["hdnFlagPesquisa"] = "1"
        fields["sbmPesquisar"] = fields.get("sbmPesquisar") or "Pesquisar"
        if self.spec.captcha_answer:
            fields["txtInfraCaptcha"] = self.spec.captcha_answer.strip()

        pcode, phtml, perr = self._inner._post(url, fields)
        result.raw_status = pcode
        if pcode != 200 or not phtml:
            result.blocked = True
            result.blocker = f"CONNECTION_FAILED:{perr}" if pcode is None else f"HTTP_{pcode}"
            return result

        matched = self._inner._results_match_protocol(phtml, protocol)
        result.matched_protocol = matched
        if not matched:
            if re_search_captcha_fail(phtml):
                result.blocked = True
                result.blocker = "CAPTCHA_BLOCKED"
                result.notes.append("captcha rejected or expired; re-solve and retry")
                return result
            result.blocker = "PROCESS_NOT_FOUND"
            result.notes.append("protocol not present in result page after human captcha submit")
            return result

        research_base = url if url.endswith("/") else url.rsplit("/", 1)[0] + "/"
        procs, docs = self._inner._extract_links(phtml, research_base)
        result.process_urls = procs
        result.document_urls = docs
        for u in docs:
            result.document_index.append(
                {
                    "url": u,
                    "title": "sei_document",
                    "source": "sei_human_session",
                    "priority_label": "qualification",
                    "company_authored_likely": True,
                }
            )
        for u in procs:
            result.document_index.append(
                {
                    "url": u,
                    "title": "sei_process",
                    "source": "sei_human_session",
                    "priority_label": "other",
                    "company_authored_likely": False,
                }
            )
        # Expand first process pages
        for pu in result.process_urls[:2]:
            for d in self._inner.expand_process_page(pu):
                if d["url"] not in {x.get("url") for x in result.document_index}:
                    d = dict(d)
                    d["source"] = "sei_human_session"
                    result.document_index.append(d)
        return result

    def resolve_and_list_docs(self, process_number: str | None) -> SeiSearchResult:
        protocols = format_sei_protocol(process_number)
        last = SeiSearchResult(base_url=self.spec.base_url, protocol_tried=protocols[0] if protocols else "")
        if not protocols:
            last.blocked = True
            last.blocker = "PROCESS_NUMBER_MISSING"
            return last
        for proto in protocols:
            res = self.search_protocol(proto)
            last = res
            if res.matched_protocol and (res.document_index or res.process_urls):
                return res
        return last


def re_search_captcha_fail(html: str) -> bool:
    import re

    return bool(
        re.search(
            r"(?i)(captcha\s+(inv[aá]lido|incorreto|expirado)|c[oó]digo\s+incorreto|digite\s+o\s+c[oó]digo)",
            html or "",
        )
    )


def operator_session_template(base_url: str = "https://colaboragov.sei.gov.br") -> dict[str, Any]:
    """JSON template for operators providing captcha/session material."""
    return {
        "base_url": base_url.rstrip("/"),
        "captcha_answer": "<paste captcha text after loading research URL>",
        "cookies": {},
        "cookie_header": null_or_str_example(),
        "notes": (
            "1) Open research_url in browser. 2) Solve captcha. "
            "3) Put answer in captcha_answer and/or export cookies. "
            "4) Run: python -m scripts.confenge_process_enrichment sei-human "
            "--session session.json --protocol 13032.283609/2026-26"
        ),
        "research_url": research_url(base_url),
    }


def null_or_str_example() -> str | None:
    return None
