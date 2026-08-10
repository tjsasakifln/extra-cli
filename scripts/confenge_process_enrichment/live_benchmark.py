"""Live PNCP supplier-centric stratified benchmark (≥100 contracts).

Produces funnel metrics + blocked source families without committing raw PDFs/PII.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from scripts.confenge_process_enrichment.contact_extract import extract_contacts_from_text
from scripts.confenge_process_enrichment.doc_priority import rank_documents
from scripts.confenge_process_enrichment.identifiers import normalize_cnpj, normalize_process_number
from scripts.confenge_process_enrichment.models import EpistemicClass
from scripts.confenge_process_enrichment.pncp_supplier_harvest import PncpSupplierHarvester
from scripts.confenge_process_enrichment.process_graph import build_process_graph, contract_node_from_row
from scripts.confenge_process_enrichment.process_resolve import resolve_process_for_contract
from scripts.confenge_process_enrichment.source_registry import ProcessSourceRegistry
from scripts.confenge_process_enrichment.states import TerminalState, derive_terminal, funnel_snapshot
from scripts.confenge_process_enrichment.text_extract import extract_text
from scripts.crawl.pncp_crawler_adapter import transform_contracts

PNCP_CONSULTA = "https://pncp.gov.br/api/consulta/v1"
USER_AGENT = "extra-cli-confenge-process-first-benchmark/1.0"


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


@dataclass
class AccountLiveResult:
    account_cnpj: str
    razao_social: str | None = None
    contracts_resolved: bool = False
    process_number_resolved: bool = False
    process_portal_resolved: bool = False
    documents_fetched: bool = False
    company_authored_docs_found: bool = False
    any_email: bool = False
    verified_email: bool = False
    enrollable_email: bool = False
    named_contact: bool = False
    relevant_role: bool = False
    referral_route: bool = False
    terminal_state: str = TerminalState.PROCESS_NOT_TRACED.value
    investigation_state: str = "NOT_STARTED"
    blockers: list[str] = field(default_factory=list)
    uf: str | None = None
    orgao_cnpj: str | None = None
    docs_listed: int = 0
    docs_downloaded: int = 0
    docs_parsed: int = 0
    commercial_emails: int = 0
    rejected_gov: int = 0
    rejected_other: int = 0
    contract_count: int = 0

    def funnel_row(self) -> dict[str, Any]:
        return {
            "contracts_resolved": self.contracts_resolved,
            "process_number_resolved": self.process_number_resolved,
            "process_portal_resolved": self.process_portal_resolved,
            "documents_fetched": self.documents_fetched,
            "company_authored_docs_found": self.company_authored_docs_found,
            "any_email": self.any_email,
            "verified_email": self.verified_email,
            "enrollable_email": self.enrollable_email,
            "named_contact": self.named_contact,
            "relevant_role": self.relevant_role,
            "referral_route": self.referral_route,
            "terminal_state": self.terminal_state,
        }


def _contract_row_key(raw: dict[str, Any]) -> str:
    ctrl = str(raw.get("numeroControlePNCP") or raw.get("numeroControlePncp") or "").strip()
    if ctrl:
        return ctrl
    org = raw.get("orgaoEntidade")
    org_cnpj = ""
    if isinstance(org, dict):
        org_cnpj = str(org.get("cnpj") or "")
    else:
        org_cnpj = str(raw.get("cnpjOrgao") or "")
    return "|".join(
        [
            org_cnpj,
            str(raw.get("anoContrato") or ""),
            str(raw.get("sequencialContrato") or ""),
            str(raw.get("niFornecedor") or ""),
        ]
    )


def fetch_contract_pages(
    session: requests.Session,
    *,
    since: date,
    until: date,
    max_rows: int = 200,
    page_size: int = 50,
    delay: float = 0.3,
    max_pages: int = 40,
    start_page: int = 1,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = max(1, start_page)
    end_page = page + max_pages - 1
    consecutive_429 = 0
    while len(rows) < max_rows and page <= end_page:
        params = {
            "dataInicial": since.strftime("%Y%m%d"),
            "dataFinal": until.strftime("%Y%m%d"),
            "pagina": str(page),
            "tamanhoPagina": str(page_size),
        }
        try:
            resp = session.get(f"{PNCP_CONSULTA}/contratos", params=params, timeout=(15, 90))
        except requests.RequestException as exc:
            print(f"[harvest] page={page} request error: {exc}", flush=True)
            break
        if resp.status_code == 429:
            consecutive_429 += 1
            wait = min(90.0, 5.0 * consecutive_429 + delay * 10)
            print(
                f"[harvest] HTTP 429 on page={page}; backoff {wait:.1f}s "
                f"(streak={consecutive_429})",
                flush=True,
            )
            if consecutive_429 >= 8:
                break
            time.sleep(wait)
            continue
        consecutive_429 = 0
        if resp.status_code != 200:
            print(f"[harvest] page={page} status={resp.status_code}", flush=True)
            break
        try:
            payload = resp.json()
        except ValueError:
            break
        if not isinstance(payload, dict):
            break
        batch = payload.get("data") or []
        if not batch:
            break
        rows.extend(batch)
        remaining = payload.get("paginasRestantes")
        if page % 5 == 0 or len(rows) >= max_rows:
            print(
                f"[harvest] page={page} rows={len(rows)} paginasRestantes={remaining}",
                flush=True,
            )
        if not remaining or remaining <= 0:
            break
        page += 1
        time.sleep(delay)
    return rows[:max_rows]


def fetch_contracts_deep(
    session: requests.Session,
    *,
    since: date,
    until: date,
    max_rows: int = 2000,
    page_size: int = 50,
    delay: float = 0.35,
    chunk_days: int = 30,
    pages_per_chunk: int = 40,
    page_offsets: tuple[int, ...] = (1,),
) -> list[dict[str, Any]]:
    """Deeper PNCP harvest with 429-aware sequential pagination.

    PNCP public API rate-limits aggressively (~HTTP 429 after a short burst).
    Prefer one sequential walk with backoff over many concurrent-style offsets.
    Optional date chunks run only if the primary walk is still thin.
    """
    seen_keys: set[str] = set()
    rows: list[dict[str, Any]] = []

    def _ingest(batch: list[dict[str, Any]]) -> None:
        for raw in batch:
            if not isinstance(raw, dict):
                continue
            key = _contract_row_key(raw)
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            rows.append(raw)
            if len(rows) >= max_rows:
                return

    # Phase 1: sequential wide-window walk (best unique yield per request)
    need = max_rows - len(rows)
    pages_needed = max(1, (need + page_size - 1) // page_size)
    print(
        f"[harvest] phase1 sequential window={since.isoformat()}..{until.isoformat()} "
        f"pages≤{pages_needed} delay={delay}",
        flush=True,
    )
    batch = fetch_contract_pages(
        session,
        since=since,
        until=until,
        max_rows=need,
        page_size=page_size,
        delay=delay,
        max_pages=pages_needed + 5,
        start_page=1,
    )
    _ingest(batch)

    # Phase 2: monthly chunks only if still below target (after cooldown)
    if len(rows) < max_rows * 0.7:
        print(
            f"[harvest] phase2 monthly chunks (have={len(rows)} target={max_rows}); "
            f"cooldown 20s for rate limit",
            flush=True,
        )
        time.sleep(20.0)
        chunk_days = max(14, int(chunk_days))
        pages_per_chunk = max(10, int(pages_per_chunk))
        cursor = since
        chunk_i = 0
        while cursor <= until and len(rows) < max_rows:
            chunk_end = min(until, cursor + timedelta(days=chunk_days - 1))
            for start_page in page_offsets:
                if len(rows) >= max_rows:
                    break
                batch = fetch_contract_pages(
                    session,
                    since=cursor,
                    until=chunk_end,
                    max_rows=min(page_size * pages_per_chunk, max_rows - len(rows)),
                    page_size=page_size,
                    delay=max(delay, 0.4),
                    max_pages=pages_per_chunk,
                    start_page=start_page,
                )
                before = len(rows)
                _ingest(batch)
                if len(rows) == before and start_page == 1:
                    break
            chunk_i += 1
            print(
                f"[harvest] chunk={chunk_i} rows={len(rows)} unique_keys={len(seen_keys)} "
                f"window={cursor.isoformat()}..{chunk_end.isoformat()}",
                flush=True,
            )
            cursor = chunk_end + timedelta(days=1)
            time.sleep(2.0)

    print(f"[harvest] done rows={len(rows)} unique_keys={len(seen_keys)}", flush=True)
    return rows


def stratify_contracts(raw_rows: list[dict[str, Any]], *, target: int = 100) -> list[dict[str, Any]]:
    """Prefer diversity by UF and organ root; keep first-seen per supplier when possible."""
    transformed = transform_contracts(raw_rows)
    by_uf: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in transformed:
        uf = (t.get("unidade_uf") or t.get("uf") or "NA")[:2]
        by_uf[uf].append(t)

    selected: list[dict[str, Any]] = []
    seen_supplier: set[str] = set()
    # Round-robin UFs for stratification
    uf_keys = sorted(by_uf.keys(), key=lambda u: -len(by_uf[u]))
    idx = {u: 0 for u in uf_keys}
    while len(selected) < target:
        progressed = False
        for u in uf_keys:
            bucket = by_uf[u]
            i = idx[u]
            while i < len(bucket):
                row = bucket[i]
                i += 1
                sup = normalize_cnpj(row.get("fornecedor_cnpj"))
                if len(sup) != 14:
                    continue
                # Prefer unique suppliers but allow refill if needed
                if sup in seen_supplier and len(selected) < target * 0.85:
                    continue
                seen_supplier.add(sup)
                selected.append(row)
                progressed = True
                break
            idx[u] = i
            if len(selected) >= target:
                break
        if not progressed:
            # fill remaining without uniqueness
            for t in transformed:
                if t not in selected and normalize_cnpj(t.get("fornecedor_cnpj")):
                    selected.append(t)
                if len(selected) >= target:
                    break
            break
    return selected[:target]


def _is_functional(email: str | None) -> bool:
    if not email or "@" not in email:
        return False
    local = email.split("@", 1)[0].lower()
    return local in {
        "contato",
        "comercial",
        "licitacao",
        "licitacoes",
        "engenharia",
        "orcamento",
        "financeiro",
        "administrativo",
        "contratos",
        "sac",
        "info",
        "vendas",
    } or local.startswith(("contato", "comercial", "licit"))


def run_live_benchmark(
    *,
    out_dir: Path,
    min_accounts: int = 100,
    max_contract_pages_rows: int = 250,
    max_docs_download_total: int = 80,
    max_docs_per_account: int = 2,
    request_delay: float = 0.3,
    window_days: int = 45,
    allow_ocr: bool = False,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    until = date.today()
    since = until - timedelta(days=window_days)

    started = time.time()
    # ~0.66 unique CNPJ per contract observed; aim rows ≈ min_accounts * 2.2
    target_rows = max(max_contract_pages_rows, int(min_accounts * 2.5), 800)
    harvest_delay = max(request_delay, 0.35 if min_accounts >= 300 else 0.2)
    print(
        f"[bench] deep harvest since={since} until={until} target_rows={target_rows} "
        f"min_accounts={min_accounts} delay={harvest_delay}",
        flush=True,
    )
    raw = fetch_contracts_deep(
        session,
        since=since,
        until=until,
        max_rows=target_rows,
        delay=harvest_delay,
        chunk_days=30 if window_days >= 60 else max(14, window_days // 2),
        pages_per_chunk=max(20, min(60, (min_accounts // 10) + 10)),
        page_offsets=(1,),
    )

    # Attach compra control + supplier name from raw before stratify
    enriched_raw_maps: list[dict[str, Any]] = []
    for rr in raw:
        t = transform_contracts([rr])[0]
        t["numeroControlePncpCompra"] = rr.get("numeroControlePncpCompra")
        t["nomeRazaoSocialFornecedor"] = rr.get("nomeRazaoSocialFornecedor")
        enriched_raw_maps.append(t)
    sample = stratify_contracts(raw, target=max(min_accounts * 2, 120))
    # rebuild sample from enriched maps when possible
    sample_enriched: list[dict[str, Any]] = []
    for srow in sample:
        match = next(
            (
                e
                for e in enriched_raw_maps
                if e.get("fornecedor_cnpj") == srow.get("fornecedor_cnpj")
                and e.get("ano_contrato") == srow.get("ano_contrato")
                and e.get("sequencial_contrato") == srow.get("sequencial_contrato")
            ),
            srow,
        )
        sample_enriched.append(match)
    sample = sample_enriched
    harvester = PncpSupplierHarvester(session=session, request_delay=request_delay, prefer_process_documents_adapter=True)
    registry = ProcessSourceRegistry(out_dir / "process_source_registry.json")

    # group by supplier for account-level metrics — use full enriched map for max unique yield
    by_supplier: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in enriched_raw_maps:
        sup = normalize_cnpj(row.get("fornecedor_cnpj"))
        if len(sup) == 14:
            by_supplier[sup].append(row)
    # prefer stratified order for processing
    stratified_order = [
        normalize_cnpj(r.get("fornecedor_cnpj"))
        for r in sample
        if len(normalize_cnpj(r.get("fornecedor_cnpj"))) == 14
    ]
    suppliers = list(dict.fromkeys(stratified_order))
    for s in by_supplier:
        if s not in suppliers:
            suppliers.append(s)

    # ensure ≥ min_accounts suppliers if possible — widen into *earlier* date windows only
    # (re-fetching the same window wastes rate-limit quota and adds near-zero unique CNPJs)
    widen_days = 30
    while len(suppliers) < min_accounts and widen_days <= 180:
        older_until = since - timedelta(days=1)
        older_since = since - timedelta(days=widen_days)
        if older_until < older_since:
            break
        print(
            f"[bench] unique_suppliers={len(suppliers)} < {min_accounts}; "
            f"widening earlier window {older_since}..{older_until}",
            flush=True,
        )
        time.sleep(15.0)  # cool down rate limit before widen burst
        more = fetch_contracts_deep(
            session,
            since=older_since,
            until=older_until,
            max_rows=max(min_accounts * 2, 600),
            delay=max(harvest_delay, 0.45),
            chunk_days=30,
            pages_per_chunk=30,
            page_offsets=(1,),
        )
        for rr in more:
            t = transform_contracts([rr])[0]
            t["numeroControlePncpCompra"] = rr.get("numeroControlePncpCompra")
            t["nomeRazaoSocialFornecedor"] = rr.get("nomeRazaoSocialFornecedor")
            sup = normalize_cnpj(t.get("fornecedor_cnpj"))
            if len(sup) == 14:
                by_supplier[sup].append(t)
                if sup not in suppliers:
                    suppliers.append(sup)
                raw.append(rr)
        widen_days += 30

    print(
        f"[bench] harvest complete: raw_contracts={len(raw)} unique_suppliers={len(suppliers)} "
        f"(target={min_accounts})",
        flush=True,
    )

    accounts: list[AccountLiveResult] = []
    downloads_left = max_docs_download_total
    source_yield = Counter()
    blocker_families = Counter()
    doc_label_hits = Counter()
    emails_observed = 0
    commercial_emails = 0

    ocr_cache: dict[str, str] = {}
    process_target = max(min_accounts, 100)
    for idx, sup in enumerate(suppliers[:process_target], start=1):
        rows = by_supplier[sup][:5]
        if not rows:
            continue
        razao = rows[0].get("nomeRazaoSocialFornecedor") or rows[0].get("nome_fornecedor")
        graph = build_process_graph(account_cnpj=sup, contracts=rows, razao_social=razao)
        res = AccountLiveResult(
            account_cnpj=sup,
            razao_social=razao,
            contracts_resolved=bool(graph.contracts),
            contract_count=len(graph.contracts),
            uf=graph.contracts[0].uf if graph.contracts else None,
            orgao_cnpj=graph.contracts[0].contracting_authority_cnpj if graph.contracts else None,
        )
        if graph.contracts:
            res.investigation_state = "CONTRACTS_RESOLVED"

        commercial_obs = []
        gov_n = other_n = 0
        process_found = portal = docs_listed = docs_dl = docs_parsed = False
        company_authored = False

        for contract in graph.contracts[:3]:
            if contract.administrative_process_number:
                process_found = True
                res.investigation_state = "PROCESS_NUMBER_RESOLVED"

            resolution = resolve_process_for_contract(
                contract,
                registry=registry,
                company_name=res.razao_social,
                company_cnpj=sup,
                allow_network=True,  # SEI public + identifier discovery
            )
            if resolution.resolved:
                portal = True
                res.investigation_state = "PROCESS_PORTAL_RESOLVED"
            if resolution.process_system_family:
                blocker_families[f"family:{resolution.process_system_family}"] += 0  # ensure key presence via success path
            for b in resolution.blockers:
                res.blockers.append(b)
                fam = b.split(":")[0]
                blocker_families[fam] += 1

            # Non-PNCP portal docs (SEI human-session results or municipal HTML PDFs)
            portal_docs = [
                d
                for d in (resolution.document_index or [])
                if str(d.get("source") or "")
                in {
                    "sei_public_search",
                    "sei_process_page",
                    "sei_human_session",
                    "municipal_portal",
                }
                or "sei" in str(d.get("url") or "").lower()
                or str(d.get("source") or "") == "municipal_portal"
            ]
            if portal_docs:
                source_yield["portal_index"] += len(portal_docs)
            sei_docs = portal_docs
            if sei_docs:
                source_yield["sei_or_muni_index"] += len(sei_docs)
                # Prefer fetching a few portal docs before PNCP noise
                for d in sei_docs[:3]:
                    if downloads_left <= 0 or not d.get("url"):
                        continue
                    try:
                        time.sleep(request_delay)
                        resp = session.get(d["url"], timeout=(15, 90), allow_redirects=True)
                        if resp.status_code != 200 or not resp.content:
                            continue
                        downloads_left -= 1
                        docs_dl = True
                        res.docs_downloaded += 1
                        tre = extract_text(
                            raw_bytes=resp.content if resp.content[:4] == b"%PDF" else resp.content,
                            mime=resp.headers.get("Content-Type"),
                            html=None if resp.content[:4] == b"%PDF" else resp.text,
                            filename=d.get("title"),
                            allow_ocr=allow_ocr,
                            ocr_cache=ocr_cache,
                        )
                        # HTML path for SEI document pages
                        if (not tre.text or len(tre.text) < 40) and resp.headers.get("Content-Type", "").startswith("text"):
                            tre = extract_text(html=resp.text)
                        if tre.text and len(tre.text.strip()) >= 20:
                            docs_parsed = True
                            res.docs_parsed += 1
                            obs = extract_contacts_from_text(
                                tre.text,
                                company_cnpj=sup,
                                company_name=res.razao_social,
                                org_cnpj=contract.contracting_authority_cnpj,
                                source_document_id=str(d.get("url")),
                                source_url=d.get("url"),
                                document_title=d.get("title") or "sei_document",
                                document_type="sei_document",
                                document_produced_by_company=bool(d.get("company_authored_likely")),
                                observation_date=contract.signed_at,
                                contract_id=contract.contract_id,
                            )
                            source_yield["sei_public"] += len(obs)
                            for o in obs:
                                if o.email:
                                    emails_observed += 1
                                if o.epistemic_class == EpistemicClass.PUBLIC_OFFICIAL:
                                    gov_n += 1
                                elif o.epistemic_class in {
                                    EpistemicClass.OTHER_BIDDER,
                                    EpistemicClass.UNKNOWN_ENTITY,
                                    EpistemicClass.THIRD_PARTY_REFERENCE,
                                }:
                                    other_n += 1
                                elif o.is_commercially_usable() and o.email:
                                    commercial_obs.append(o)
                                    commercial_emails += 1
                    except requests.RequestException:
                        blocker_families["SEI_DOWNLOAD_ERROR"] += 1

            harvest = harvester.harvest_contract(contract)
            for b in harvest.blockers:
                res.blockers.append(b)
                blocker_families[b.split(":")[0] if ":" in b else b] += 1
            ranked = rank_documents(harvest.documents)
            # Boost contratos resource and contact-likely titles for download order
            ranked = sorted(
                ranked,
                key=lambda d: (
                    0 if d.get("pncp_resource") == "contratos" else 1,
                    0 if re.search(
                        r"(?i)proposta|habilit|declar|represent|preposto|contrato|procur",
                        d.get("title") or "",
                    )
                    else 1,
                    -float(d.get("efficiency") or d.get("yield_score") or 0),
                ),
            )
            if ranked:
                docs_listed = True
                res.docs_listed += len(ranked)
                res.investigation_state = "PNCP_CONTRACT_DOCS_FETCHED"
            to_fetch = ranked[: max(max_docs_per_account, 4)]
            for d in ranked:
                doc_label_hits[d.get("priority_label") or "other"] += 1
                if d.get("company_authored_likely"):
                    company_authored = True
            for d in to_fetch:
                if downloads_left <= 0 or not d.get("url"):
                    continue
                try:
                    time.sleep(request_delay)
                    resp = session.get(d["url"], timeout=(15, 90), allow_redirects=True)
                    if resp.status_code in (401, 403):
                        res.blockers.append("AUTH_REQUIRED")
                        blocker_families["AUTH_REQUIRED"] += 1
                        continue
                    if resp.status_code == 429:
                        res.blockers.append("SOURCE_BLOCKED")
                        blocker_families["RATE_LIMIT"] += 1
                        continue
                    if resp.status_code != 200 or not resp.content:
                        res.blockers.append(f"HTTP_{resp.status_code}")
                        blocker_families[f"HTTP_{resp.status_code}"] += 1
                        continue
                    downloads_left -= 1
                    docs_dl = True
                    res.docs_downloaded += 1
                    tre = extract_text(
                        raw_bytes=resp.content,
                        mime=resp.headers.get("Content-Type"),
                        filename=d.get("title"),
                        allow_ocr=allow_ocr,
                        ocr_cache=ocr_cache,
                    )
                    if not tre.text or len(tre.text.strip()) < 20:
                        continue
                    docs_parsed = True
                    res.docs_parsed += 1
                    # Expand context: for contract PDFs, CNPJ may be far from email —
                    # pass a CNPJ-anchored window when present.
                    text_for_extract = tre.text
                    cnpj_digits = re.sub(r"\D", "", sup)
                    if cnpj_digits and cnpj_digits in re.sub(r"\D", "", tre.text):
                        # keep full text (attribution uses surrounding windows per match)
                        text_for_extract = tre.text
                    obs = extract_contacts_from_text(
                        text_for_extract,
                        company_cnpj=sup,
                        company_name=res.razao_social,
                        org_cnpj=contract.contracting_authority_cnpj,
                        source_document_id=str(d.get("document_id")),
                        source_url=d.get("url"),
                        document_title=d.get("title"),
                        document_type=d.get("category") or d.get("priority_label"),
                        document_produced_by_company=bool(d.get("company_authored_likely")),
                        observation_date=contract.signed_at,
                        contract_id=contract.contract_id,
                    )
                    source_yield[d.get("priority_label") or "other"] += len(obs)
                    for o in obs:
                        if o.email:
                            emails_observed += 1
                        if o.epistemic_class == EpistemicClass.PUBLIC_OFFICIAL:
                            gov_n += 1
                        elif o.epistemic_class in {
                            EpistemicClass.OTHER_BIDDER,
                            EpistemicClass.UNKNOWN_ENTITY,
                            EpistemicClass.THIRD_PARTY_REFERENCE,
                        }:
                            other_n += 1
                        elif o.is_commercially_usable() and o.email:
                            commercial_obs.append(o)
                            commercial_emails += 1
                except requests.RequestException as exc:
                    res.blockers.append(f"DOWNLOAD:{type(exc).__name__}")
                    blocker_families["DOWNLOAD_ERROR"] += 1

        res.process_number_resolved = process_found
        res.process_portal_resolved = portal
        res.documents_fetched = docs_dl or docs_listed
        # listed without body still counts as "documents_fetched" for index stage; split in metrics
        res.company_authored_docs_found = company_authored
        res.rejected_gov = gov_n
        res.rejected_other = other_n

        named = any(o.person_name for o in commercial_obs)
        roles = any(o.role_observed for o in commercial_obs)
        enrollable = any(
            o.email
            and o.epistemic_class
            in {
                EpistemicClass.COMPANY_DECLARED,
                EpistemicClass.ADMIN_RECORDED_COMPANY_REP,
                EpistemicClass.COMPANY_DOMAIN_OBSERVED,
            }
            and not o.pattern_guessed
            for o in commercial_obs
        )
        referral = any(o.email and _is_functional(o.email) and not o.person_name for o in commercial_obs)
        any_email = any(o.email for o in commercial_obs) or referral

        res.any_email = any_email
        res.verified_email = enrollable
        res.enrollable_email = enrollable
        res.named_contact = named
        res.relevant_role = roles
        res.referral_route = referral and not enrollable
        res.commercial_emails = len({o.email for o in commercial_obs if o.email})

        # documents_fetched flag for funnel: prefer true download; also true if listed
        res.documents_fetched = docs_dl  # strict: body fetched
        listed_only = docs_listed and not docs_dl

        terminal = derive_terminal(
            state=res.investigation_state if hasattr(res, "investigation_state") else "NOT_STARTED",
            has_enrollable_email=enrollable,
            has_verified_email=enrollable,
            has_referral_route=referral and not enrollable,
            has_unverified_contact=any_email and not enrollable,
            process_path_applicable=bool(graph.contracts),
            process_path_attempted=True,
            process_number_found=process_found,
            portal_resolved=portal,
            docs_fetched=docs_dl or docs_listed,
            docs_parsed=docs_parsed,
            blockers=res.blockers,
        )
        # refine listed-only
        if listed_only and not enrollable and not referral and not docs_parsed:
            from scripts.confenge_process_enrichment.states import TerminalState as TS

            if terminal in {TS.DOCUMENTS_PARSED_NO_CONTACT, TS.NO_CONTACT_FOUND}:
                terminal = TS.DOCUMENTS_NOT_FETCHED if not docs_dl else terminal
            # if docs listed but none downloaded due to budget, mark DOCUMENTS_NOT_FETCHED
            if downloads_left <= 0 and docs_listed and not docs_dl:
                terminal = TS.DOCUMENTS_NOT_FETCHED
                res.blockers.append("DOWNLOAD_BUDGET_EXHAUSTED")

        # derive_terminal expects InvestigationState enum - pass string carefully
        try:
            res.terminal_state = terminal.value if hasattr(terminal, "value") else str(terminal)
        except Exception:
            res.terminal_state = str(terminal)

        if enrollable:
            res.investigation_state = "CONTACTS_VERIFIED"
        elif docs_parsed:
            res.investigation_state = "DOCS_PARSED"
        elif docs_listed:
            res.investigation_state = "PNCP_CONTRACT_DOCS_FETCHED"

        accounts.append(res)

        if idx % 10 == 0 or idx == 1 or res.enrollable_email:
            enr = sum(1 for a in accounts if a.enrollable_email)
            print(
                f"[bench] account {idx}/{process_target} "
                f"terminal={res.terminal_state} enrollable={enr}/{len(accounts)} "
                f"downloads_left={downloads_left}",
                flush=True,
            )

        if len(accounts) >= min_accounts:
            break

    # Fix terminal derivation properly with InvestigationState
    from scripts.confenge_process_enrichment.states import InvestigationState

    for a in accounts:
        # recompute terminal cleanly
        st = InvestigationState.NOT_STARTED
        if a.contracts_resolved:
            st = InvestigationState.CONTRACTS_RESOLVED
        if a.process_number_resolved:
            st = InvestigationState.PROCESS_NUMBER_RESOLVED
        if a.process_portal_resolved:
            st = InvestigationState.PROCESS_PORTAL_RESOLVED
        if a.docs_listed:
            st = InvestigationState.PNCP_CONTRACT_DOCS_FETCHED
        if a.docs_downloaded:
            st = InvestigationState.HIGH_VALUE_DOCS_FETCHED
        if a.docs_parsed:
            st = InvestigationState.DOCS_PARSED
        if a.enrollable_email or a.referral_route:
            st = InvestigationState.CONTACTS_VERIFIED
        a.investigation_state = st.value
        term = derive_terminal(
            state=st,
            has_enrollable_email=a.enrollable_email,
            has_verified_email=a.verified_email,
            has_referral_route=a.referral_route,
            has_unverified_contact=a.any_email and not a.enrollable_email,
            process_path_applicable=a.contracts_resolved,
            process_path_attempted=True,
            process_number_found=a.process_number_resolved,
            portal_resolved=a.process_portal_resolved,
            docs_fetched=a.docs_downloaded > 0 or a.docs_listed > 0,
            docs_parsed=a.docs_parsed > 0,
            blockers=a.blockers,
        )
        if a.docs_listed > 0 and a.docs_downloaded == 0 and not a.enrollable_email and not a.referral_route:
            # explicit: index known but bodies not retrieved (budget / HTTP / portal)
            if term in {
                TerminalState.DOCUMENTS_PARSED_NO_CONTACT,
                TerminalState.NO_CONTACT_FOUND,
                TerminalState.PROCESS_FOUND_NOT_FETCHED,
                TerminalState.DOCUMENTS_FETCHED_NOT_PARSED,
            }:
                term = TerminalState.DOCUMENTS_NOT_FETCHED
        a.terminal_state = term.value

    funnel = funnel_snapshot([a.funnel_row() for a in accounts])
    terminals = Counter(a.terminal_state for a in accounts)
    uf_dist = Counter(a.uf or "NA" for a in accounts)

    duration = time.time() - started
    registry.save()

    # sanitized account rows (no emails in aggregate file — only hashes if present)
    account_rows = []
    for a in accounts:
        account_rows.append(
            {
                "account_cnpj_hash": hashlib.sha256(a.account_cnpj.encode()).hexdigest()[:16],
                "uf": a.uf,
                "contract_count": a.contract_count,
                "contracts_resolved": a.contracts_resolved,
                "process_number_resolved": a.process_number_resolved,
                "process_portal_resolved": a.process_portal_resolved,
                "docs_listed": a.docs_listed,
                "docs_downloaded": a.docs_downloaded,
                "docs_parsed": a.docs_parsed,
                "enrollable_email": a.enrollable_email,
                "any_email": a.any_email,
                "referral_route": a.referral_route,
                "named_contact": a.named_contact,
                "terminal_state": a.terminal_state,
                "investigation_state": a.investigation_state,
                "blocker_count": len(a.blockers),
                "blocker_families": sorted({b.split(":")[0] for b in a.blockers})[:8],
            }
        )

    summary = {
        "schema": "confenge.process_first_live_benchmark.v1",
        "generated_at": _now(),
        "window": {"since": since.isoformat(), "until": until.isoformat()},
        "duration_seconds": round(duration, 2),
        "raw_contracts_fetched": len(raw),
        "accounts_target": min_accounts,
        "accounts_evaluated": len(accounts),
        "unique_suppliers": len(accounts),
        "funnel": funnel,
        "terminals": dict(terminals),
        "uf_distribution": dict(uf_dist),
        "source_yield_observations_by_doc_label": dict(source_yield),
        "doc_labels_listed": dict(doc_label_hits),
        "blocker_families": dict(blocker_families.most_common(30)),
        "emails_observed_raw": emails_observed,
        "commercial_emails_attributed": commercial_emails,
        "download_budget": {
            "max_docs_download_total": max_docs_download_total,
            "remaining": downloads_left,
            "docs_downloaded_total": sum(a.docs_downloaded for a in accounts),
            "docs_listed_total": sum(a.docs_listed for a in accounts),
            "docs_parsed_total": sum(a.docs_parsed for a in accounts),
        },
        "coverage": {
            "enrollable_email_rate": round(funnel["accounts_with_enrollable_email"] / max(len(accounts), 1), 4),
            "any_email_rate": round(funnel["accounts_with_any_email"] / max(len(accounts), 1), 4),
            "referral_route_rate": round(funnel["accounts_with_referral_route"] / max(len(accounts), 1), 4),
            "process_number_rate": round(funnel["accounts_process_number_resolved"] / max(len(accounts), 1), 4),
            "docs_listed_rate": round(sum(1 for a in accounts if a.docs_listed > 0) / max(len(accounts), 1), 4),
            "docs_downloaded_rate": round(sum(1 for a in accounts if a.docs_downloaded > 0) / max(len(accounts), 1), 4),
            "verified_or_referral_rate": round(
                sum(1 for a in accounts if a.enrollable_email or a.referral_route) / max(len(accounts), 1),
                4,
            ),
        },
        "honest_limits": [
            "OCR disabled by default in live slice",
            "Web process-portal discovery not fully exercised (PNCP-centric)",
            "Download budget caps deep parse coverage",
            "No datalake DSN — sample from live PNCP contratos window only",
        ],
        "status_hint": "PARTIAL_COVERAGE_TARGET_NOT_MET"
        if funnel["accounts_with_enrollable_email"] / max(len(accounts), 1) < 0.5
        else "READY_CANDIDATE_IF_PRECISION_OK",
        "harvest": {
            "mode": "deep_chunked",
            "window_days": window_days,
            "unique_suppliers_available": len(suppliers),
            "supplier_ceiling_note": (
                "unique_suppliers_available is the public PNCP harvest yield for this run; "
                "if below min_accounts, that is a public-API sampling ceiling (no DSN)."
            ),
        },
    }

    (out_dir / "live-benchmark-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "live-benchmark-accounts-sanitized.json").write_text(
        json.dumps({"accounts": account_rows, "n": len(account_rows)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"[bench] finished accounts={len(accounts)} enrollable_rate="
        f"{summary['coverage']['enrollable_email_rate']} "
        f"duration_s={summary['duration_seconds']}",
        flush=True,
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", default="artifacts/confenge/process-first-enrichment/live-100")
    p.add_argument("--min-accounts", type=int, default=100)
    p.add_argument("--max-downloads", type=int, default=80)
    p.add_argument("--window-days", type=int, default=45)
    p.add_argument("--delay", type=float, default=0.3)
    p.add_argument(
        "--max-contract-rows",
        type=int,
        default=250,
        help="Floor for PNCP contract page rows (deep harvest uses max of this and min_accounts*2.5)",
    )
    args = p.parse_args(argv)
    summary = run_live_benchmark(
        out_dir=Path(args.out_dir),
        min_accounts=args.min_accounts,
        max_contract_pages_rows=args.max_contract_rows,
        max_docs_download_total=args.max_downloads,
        request_delay=args.delay,
        window_days=args.window_days,
    )
    keys = ("accounts_evaluated", "funnel", "coverage", "terminals", "blocker_families", "harvest")
    print(json.dumps({k: summary[k] for k in keys if k in summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
