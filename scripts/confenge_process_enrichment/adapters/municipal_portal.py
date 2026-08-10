"""Municipal / small-organ process portal discovery and HTML document harvest.

Targets short administrative process numbers (e.g. 000023/2025, 91/2025) that
are not federal NUP/SEI-shaped.

Strategy (observed, lazy):
1. Build candidate municipal base URLs from municipality + UF.
2. Fetch homepage / transparency / licitações pages.
3. Detect portal family hints (multi24h, portal.php, transparencia.*).
4. Search HTML for process-number variants and supplier CNPJ.
5. Collect nearby PDF/document links.
6. Cache successful patterns on confenge_process_source_registry.

Does NOT invent organ-specific APIs; only uses HTTP GET + HTML link extraction.
"""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from scripts.confenge_process_enrichment.identifiers import (
    digits_only,
    normalize_cnpj,
    process_number_variants,
)

USER_AGENT = "extra-cli-confenge-municipal-portal/1.0"
DEFAULT_TIMEOUT = (8.0, 20.0)

_PDF_RE = re.compile(r"(?i)\.(pdf|zip|docx?|odt)(\?|$)|download|arquivo|anexo|edital")
_PREFIX_STOP = {
    "MUNICIPIO",
    "MUNICIPIO",
    "PREFEITURA",
    "FUNDO",
    "MUNICIPAL",
    "SAUDE",
    "SAUDE",
    "HOSPITAL",
}


def _slug_variants(name: str | None) -> list[str]:
    """Return municipality hostname slug variants (with/without particles)."""
    if not name:
        return []
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^A-Za-z0-9\s-]", " ", text)
    raw_parts = [p for p in text.upper().split() if p]
    # Drop institutional prefixes only
    while raw_parts and raw_parts[0] in _PREFIX_STOP:
        raw_parts = raw_parts[1:]
    if not raw_parts:
        return []
    full = "-".join(p.lower() for p in raw_parts)
    # Without grammatical particles
    no_part = "-".join(
        p.lower() for p in raw_parts if p not in {"DE", "DA", "DO", "DAS", "DOS", "E"}
    )
    # Compact (no hyphens)
    compact = re.sub(r"[^a-z0-9]", "", full)
    # Initials for long multi-word names (Balneário Camboriú -> bc)
    initials = "".join(p[0].lower() for p in raw_parts if p not in {"DE", "DA", "DO", "DAS", "DOS", "E"})
    variants = [full, no_part, compact]
    if len(initials) >= 2:
        variants.append(initials)
    # special: balneario camboriu common host
    if "balneario" in full and "camboriu" in full.replace("ú", "u"):
        variants.extend(["balneariocamboriu", "bc", "balneario-camboriu"])
    if "joinville" in full:
        variants.append("joinville")
    seen: set[str] = set()
    out: list[str] = []
    for v in variants:
        v = v.strip("-")
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def candidate_municipal_bases(
    *,
    municipality: str | None,
    uf: str | None,
    entity_name: str | None = None,
) -> list[str]:
    """Generate plausible municipal website bases (observed Brazilian patterns)."""
    uf = (uf or "").lower().strip()
    bases: list[str] = []
    for slug in _slug_variants(municipality):
        if not slug or not uf:
            continue
        bases.extend(
            [
                f"https://www.{slug}.{uf}.gov.br",
                f"https://{slug}.{uf}.gov.br",
                f"https://transparencia.{slug}.{uf}.gov.br",
                f"https://www.{slug}.{uf}.gov.br/portal.php?pagina=licitacoes_editais",
                f"https://www.{slug}.{uf}.gov.br/licitacoes",
                f"https://www.{slug}.{uf}.gov.br/transparencia",
                f"https://www.{slug}.{uf}.gov.br/servicos/consultar-editais-de-licitacao",
            ]
        )
        compact = re.sub(r"[^a-z0-9]", "", slug)
        if compact:
            bases.append(f"https://pm{compact}.multi24h.com.br/multi24/sistemas/transparencia/")
            bases.append(f"https://{compact}.multi24h.com.br/multi24/sistemas/transparencia/")
            bases.append(
                f"https://pm{compact}.multi24h.com.br/multi24/sistemas/transparencia/index.php?entidade=1&secao=licitacoes&sub=info_licitacao"
            )
            bases.append(
                f"https://pm{compact}.multi24h.com.br/multi24/sistemas/transparencia/index.php?entidade=1&secao=contrato"
            )
    # de-dupe
    seen: set[str] = set()
    out: list[str] = []
    for b in bases:
        if b not in seen:
            seen.add(b)
            out.append(b)
    return out


def _guess_family(url: str, html: str = "") -> str:
    u = (url or "").lower()
    h = (html or "").lower()
    if "multi24h.com.br" in u or "multi24" in h:
        return "municipal_multi24h"
    if "portal.php" in u or "pagina=licitacoes" in u:
        return "municipal_portal_php"
    if "transparencia" in u:
        return "transparency_portal"
    if "licit" in u:
        return "procurement_portal"
    return "municipal_html"


@dataclass
class MunicipalPortalResult:
    process_number: str | None
    municipality: str | None = None
    uf: str | None = None
    orgao_cnpj: str | None = None
    portal_url: str | None = None
    process_system_family: str = "municipal_html"
    document_index: list[dict[str, Any]] = field(default_factory=list)
    pages_fetched: int = 0
    blockers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    resolved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "process_number": self.process_number,
            "municipality": self.municipality,
            "uf": self.uf,
            "orgao_cnpj": self.orgao_cnpj,
            "portal_url": self.portal_url,
            "process_system_family": self.process_system_family,
            "document_index": self.document_index,
            "pages_fetched": self.pages_fetched,
            "blockers": self.blockers,
            "notes": self.notes,
            "resolved": self.resolved,
        }


class MunicipalPortalAdapter:
    portal_family = "municipal_process"
    source_id = "municipal_portal"

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        timeout: tuple[float, float] = DEFAULT_TIMEOUT,
        request_delay: float = 0.2,
        max_bases: int = 6,
        max_pages: int = 8,
    ) -> None:
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.session.headers.setdefault("Accept", "text/html,application/xhtml+xml")
        self.timeout = timeout
        self.request_delay = request_delay
        self.max_bases = max_bases
        self.max_pages = max_pages

    def _sleep(self) -> None:
        if self.request_delay > 0:
            time.sleep(self.request_delay)

    def _get(self, url: str) -> tuple[int | None, str | None, str | None]:
        try:
            self._sleep()
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            # only treat textual bodies as HTML index
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if resp.status_code == 200 and (
                "html" in ctype or "text" in ctype or (resp.text[:1] == "<")
            ):
                return resp.status_code, resp.text, None
            if resp.status_code == 200:
                return resp.status_code, None, "non_html"
            return resp.status_code, None, f"HTTP {resp.status_code}"
        except requests.Timeout:
            return None, None, "timeout"
        except requests.RequestException as exc:
            return None, None, str(exc)

    def _process_present(self, html: str, process_number: str | None) -> bool:
        if not html or not process_number:
            return False
        variants = process_number_variants(process_number)
        html_l = html.lower()
        dig_html = digits_only(html)
        for v in variants:
            if v and v.lower() in html_l:
                return True
            vd = digits_only(v)
            if len(vd) >= 4 and vd in dig_html:
                return True
        return False

    def _cnpj_present(self, html: str, cnpj: str | None) -> bool:
        if not html or not cnpj:
            return False
        d = normalize_cnpj(cnpj)
        return bool(d) and d in digits_only(html)

    def _extract_docs(self, html: str, base_url: str, *, process_number: str | None) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        seen: set[str] = set()
        for href in re.findall(r'href=["\']([^"\']+)["\']', html or "", flags=re.I):
            if not _PDF_RE.search(href):
                continue
            full = urljoin(base_url, href.replace("&amp;", "&"))
            if full in seen:
                continue
            seen.add(full)
            title = href.rsplit("/", 1)[-1][:180]
            # score lightly by process token in URL/title
            proc_hit = False
            if process_number:
                for v in process_number_variants(process_number)[:4]:
                    if v and v.replace("/", "") in (full + title):
                        proc_hit = True
                        break
            docs.append(
                {
                    "url": full,
                    "title": title,
                    "source": "municipal_portal",
                    "priority_label": "proposal" if re.search(r"(?i)proposta|habilit|declar", title) else "other",
                    "company_authored_likely": bool(
                        re.search(r"(?i)proposta|habilit|declar|procur|represent", title)
                    ),
                    "process_token_in_url": proc_hit,
                }
            )
        # Prefer process-token hits first
        docs.sort(key=lambda d: (0 if d.get("process_token_in_url") else 1, 0 if d.get("company_authored_likely") else 1))
        return docs[:40]

    def _follow_internal_links(self, html: str, base_url: str) -> list[str]:
        out: list[str] = []
        host = urlparse(base_url).netloc
        for href in re.findall(r'href=["\']([^"\']+)["\']', html or "", flags=re.I):
            if href.startswith("#") or href.lower().startswith("javascript:"):
                continue
            full = urljoin(base_url, href.replace("&amp;", "&"))
            p = urlparse(full)
            if p.netloc and host and p.netloc != host and "multi24h.com.br" not in p.netloc:
                # allow multi24h sibling hosts under same municipality domain family
                if not any(x in p.netloc for x in ("multi24h.com.br", host.split(".")[0])):
                    continue
            if re.search(r"(?i)licit|contrato|transpar|edital|processo|protocolo|compra", full):
                if full not in out:
                    out.append(full)
        return out[:12]

    def resolve(
        self,
        *,
        process_number: str | None,
        municipality: str | None,
        uf: str | None,
        orgao_cnpj: str | None = None,
        entity_name: str | None = None,
        supplier_cnpj: str | None = None,
        known_base_url: str | None = None,
    ) -> MunicipalPortalResult:
        result = MunicipalPortalResult(
            process_number=process_number,
            municipality=municipality,
            uf=uf,
            orgao_cnpj=normalize_cnpj(orgao_cnpj) if orgao_cnpj else None,
        )
        if not process_number:
            result.blockers.append("PROCESS_NUMBER_MISSING")
            return result
        # Skip NUP-shaped (handled by SEI)
        if len(digits_only(process_number)) >= 15:
            result.notes.append("nup_shaped_skip_municipal")
            return result

        bases = []
        if known_base_url:
            bases.append(known_base_url)
        bases.extend(
            candidate_municipal_bases(
                municipality=municipality,
                uf=uf,
                entity_name=entity_name,
            )
        )
        bases = bases[: self.max_bases]

        pages_budget = self.max_pages
        best_docs: list[dict[str, Any]] = []
        best_url: str | None = None
        best_family = "municipal_html"

        for base in bases:
            if pages_budget <= 0:
                break
            code, html, err = self._get(base)
            pages_budget -= 1
            result.pages_fetched += 1
            if code is None:
                result.notes.append(f"fail:{base[:40]}:{err}")
                continue
            if code in (401, 403):
                result.blockers.append("AUTH_REQUIRED")
                continue
            if code == 404 or not html:
                continue

            _guess_family(base, html)
            queue = [base]
            queue.extend(self._follow_internal_links(html, base)[:6])
            seen_page: set[str] = set()

            for page_url in queue:
                if pages_budget <= 0:
                    break
                if page_url in seen_page:
                    continue
                seen_page.add(page_url)
                if page_url == base:
                    page_html = html
                    page_code = code
                else:
                    page_code, page_html, page_err = self._get(page_url)
                    pages_budget -= 1
                    result.pages_fetched += 1
                    if page_code != 200 or not page_html:
                        continue
                proc_hit = self._process_present(page_html, process_number)
                cnpj_hit = self._cnpj_present(page_html, supplier_cnpj)
                docs = self._extract_docs(page_html, page_url, process_number=process_number)
                if docs and (proc_hit or cnpj_hit or not best_docs):
                    # Prefer pages with process token match
                    score = (2 if proc_hit else 0) + (1 if cnpj_hit else 0) + min(len(docs), 5)
                    prev = (2 if best_url else -1)
                    if score >= prev or not best_docs:
                        best_docs = docs
                        best_url = page_url
                        best_family = _guess_family(page_url, page_html)
                        result.resolved = True
                elif proc_hit and not best_url:
                    best_url = page_url
                    best_family = _guess_family(page_url, page_html)
                    result.resolved = True
                    result.notes.append("process_token_on_page_without_pdf_links")

            if result.resolved and best_docs:
                break

        result.document_index = best_docs
        result.portal_url = best_url
        result.process_system_family = best_family
        if not result.resolved:
            result.blockers.append("MUNICIPAL_PORTAL_NOT_FOUND")
        return result
