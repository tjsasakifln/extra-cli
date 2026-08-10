"""Process-first enrichment orchestrator."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from scripts.confenge_process_enrichment.contact_extract import (
    extract_contacts_from_text,
)
from scripts.confenge_process_enrichment.contact_graph import (
    build_account_contact_graph,
    select_best_for_service,
)
from scripts.confenge_process_enrichment.models import (
    AccountEnrichmentResult,
    ContactObservation,
    EpistemicClass,
    InvestigationState,
    TerminalState,
)
from scripts.confenge_process_enrichment.outreach_export import graph_to_outreach_contacts
from scripts.confenge_process_enrichment.pncp_supplier_harvest import (
    PncpSupplierHarvester,
    attach_docs_to_contract,
)
from scripts.confenge_process_enrichment.process_graph import (
    build_process_graph,
    graph_has_traceable_process,
    load_contracts_for_supplier,
)
from scripts.confenge_process_enrichment.process_resolve import resolve_process_for_contract
from scripts.confenge_process_enrichment.source_registry import ProcessSourceRegistry
from scripts.confenge_process_enrichment.states import advance, derive_terminal
from scripts.confenge_process_enrichment.text_extract import extract_text


@dataclass
class ProcessFirstConfig:
    allow_network: bool = False
    max_contracts: int = 15
    max_docs_per_contract: int = 8
    max_docs_fetch: int = 12
    allow_ocr: bool = False
    stop_on_high_confidence_email: bool = True
    high_confidence_threshold: float = 0.75
    services: tuple[str, ...] = ("reajuste", "orcamento", "diretoria_b2g", "generic")
    dsn: str | None = None
    registry_path: str | None = None


@dataclass
class ProcessFirstEnricher:
    config: ProcessFirstConfig = field(default_factory=ProcessFirstConfig)
    harvester: PncpSupplierHarvester | None = None
    registry: ProcessSourceRegistry | None = None
    search_fn: Callable[[str, int], list[dict[str, Any]]] | None = None
    fetch_fn: Callable[[str], tuple[int | None, str | None, str | None]] | None = None
    download_fn: Callable[[str], bytes | None] | None = None

    def __post_init__(self) -> None:
        if self.harvester is None:
            self.harvester = PncpSupplierHarvester(
                download=False,
                prefer_process_documents_adapter=True,
            )
        if self.registry is None:
            from pathlib import Path

            path = Path(self.config.registry_path) if self.config.registry_path else None
            self.registry = ProcessSourceRegistry(path)

    def enrich(
        self,
        *,
        account_cnpj: str,
        razao_social: str | None = None,
        contracts: list[dict[str, Any]] | None = None,
        document_texts: list[dict[str, Any]] | None = None,
        known_company_domains: list[str] | None = None,
        dnc_emails: set[str] | None = None,
        bounced_emails: set[str] | None = None,
        existing_enrollable: bool = False,
    ) -> AccountEnrichmentResult:
        cfg = self.config
        state = InvestigationState.NOT_STARTED
        blockers: list[str] = []
        observations: list[ContactObservation] = []
        research_gaps: list[str] = []

        # Progressive cost: if already enrollable and stop flag, skip expensive work
        if existing_enrollable and cfg.stop_on_high_confidence_email:
            return AccountEnrichmentResult(
                account_cnpj=account_cnpj,
                razao_social=razao_social,
                investigation_state=InvestigationState.COMPLETE,
                terminal_state=TerminalState.EMAIL_SEND_READY,
                funnel_flags={"skipped_expensive_existing_enrollable": True},
                limitations=["existing_enrollable_short_circuit"],
            )

        rows = load_contracts_for_supplier(
            account_cnpj,
            dsn=cfg.dsn,
            limit=cfg.max_contracts,
            inline_contracts=contracts,
        )
        graph = build_process_graph(
            account_cnpj=account_cnpj,
            contracts=rows,
            razao_social=razao_social,
        )
        if graph.contracts:
            state = advance(state, InvestigationState.CONTRACTS_RESOLVED)

        process_attempted = False
        process_number_found = False
        portal_resolved = False
        docs_fetched = False
        docs_parsed = False
        company_authored = False

        # Inject pre-parsed document texts (fixture / offline path)
        for doc in document_texts or []:
            text = doc.get("text") or ""
            if not text:
                continue
            docs_parsed = True
            obs = extract_contacts_from_text(
                text,
                company_cnpj=account_cnpj,
                company_name=razao_social,
                known_company_domains=known_company_domains,
                org_cnpj=doc.get("orgao_cnpj"),
                other_bidder_cnpjs=doc.get("other_bidder_cnpjs"),
                source_document_id=doc.get("document_id"),
                source_url=doc.get("url"),
                document_title=doc.get("title"),
                document_type=doc.get("document_type") or doc.get("category"),
                document_produced_by_company=doc.get("company_authored"),
                observation_date=doc.get("observation_date"),
                contract_id=doc.get("contract_id"),
                page=doc.get("page"),
            )
            observations.extend(obs)
            if doc.get("company_authored"):
                company_authored = True

        if document_texts:
            state = advance(state, InvestigationState.DOCS_PARSED)
            if observations:
                state = advance(state, InvestigationState.CONTACTS_EXTRACTED)

        # Contract → PNCP harvest → process resolve
        path_applicable = bool(graph.contracts) or graph_has_traceable_process(graph)
        if not graph.contracts:
            research_gaps.append("no_contracts_in_datalake_or_input")
            path_applicable = False

        docs_budget = cfg.max_docs_fetch
        for contract in graph.contracts[: cfg.max_contracts]:
            process_attempted = True
            if contract.administrative_process_number:
                process_number_found = True
                state = advance(state, InvestigationState.PROCESS_NUMBER_RESOLVED)

            # PNCP harvest (supplier-centric entry via contract keys)
            if cfg.allow_network and self.harvester is not None:
                harvest = self.harvester.harvest_contract(contract)
                blockers.extend(harvest.blockers)
                if harvest.documents:
                    attach_docs_to_contract(contract, harvest)
                    state = advance(state, InvestigationState.PNCP_CONTRACT_DOCS_FETCHED)
                    state = advance(state, InvestigationState.PROCUREMENT_RESOLVED)
                    # Ranked high-value first
                    for dref in sorted(
                        contract.documents,
                        key=lambda d: d.yield_score,
                        reverse=True,
                    )[: cfg.max_docs_per_contract]:
                        if docs_budget <= 0:
                            break
                        if dref.company_authored_likely:
                            company_authored = True
                        if not dref.url or not self.download_fn:
                            # Index-only without body
                            continue
                        docs_budget -= 1
                        try:
                            raw = self.download_fn(dref.url)
                        except Exception as exc:  # noqa: BLE001
                            blockers.append(f"DOWNLOAD:{exc}")
                            continue
                        if not raw:
                            continue
                        docs_fetched = True
                        dref.fetched = True
                        state = advance(state, InvestigationState.HIGH_VALUE_DOCS_FETCHED)
                        tre = extract_text(
                            raw_bytes=raw,
                            mime=dref.mime,
                            filename=dref.title,
                            allow_ocr=cfg.allow_ocr,
                        )
                        if not tre.text:
                            continue
                        docs_parsed = True
                        dref.parsed = True
                        state = advance(state, InvestigationState.DOCS_PARSED)
                        obs = extract_contacts_from_text(
                            tre.text,
                            company_cnpj=account_cnpj,
                            company_name=razao_social,
                            known_company_domains=known_company_domains,
                            org_cnpj=contract.contracting_authority_cnpj,
                            source_document_id=dref.document_id,
                            source_url=dref.url,
                            document_title=dref.title,
                            document_type=dref.category,
                            document_produced_by_company=dref.company_authored_likely,
                            observation_date=contract.signed_at,
                            contract_id=contract.contract_id,
                        )
                        observations.extend(obs)
                        if obs:
                            state = advance(state, InvestigationState.CONTACTS_EXTRACTED)
                        if cfg.stop_on_high_confidence_email and any(
                            o.email
                            and o.epistemic_class
                            in {
                                EpistemicClass.COMPANY_DECLARED,
                                EpistemicClass.ADMIN_RECORDED_COMPANY_REP,
                                EpistemicClass.COMPANY_DOMAIN_OBSERVED,
                            }
                            and not o.pattern_guessed
                            for o in obs
                        ):
                            break

            # Process portal resolution
            resolution = resolve_process_for_contract(
                contract,
                registry=self.registry,
                company_name=razao_social,
                company_cnpj=account_cnpj,
                search_fn=self.search_fn if cfg.allow_network else None,
                fetch_fn=self.fetch_fn if cfg.allow_network else None,
                allow_network=cfg.allow_network,
            )
            if resolution.process_number_normalized:
                process_number_found = True
            if resolution.resolved:
                portal_resolved = True
                state = advance(state, InvestigationState.PROCESS_PORTAL_RESOLVED)
                contract.external_process_sources.append(resolution.to_dict())
            if resolution.document_index:
                state = advance(state, InvestigationState.PROCESS_INDEX_FETCHED)
            blockers.extend(resolution.blockers)

            # Early stop if high-confidence commercial email already in hand
            if cfg.stop_on_high_confidence_email:
                cg_tmp = build_account_contact_graph(
                    observations,
                    account_cnpj=account_cnpj,
                    dnc_emails=dnc_emails,
                    bounced_emails=bounced_emails,
                )
                best = select_best_for_service(cg_tmp, "generic")
                if (
                    best
                    and best.get("email")
                    and best.get("contact_class") == "named_person"
                    and float(best.get("confidence") or 0) >= cfg.high_confidence_threshold
                ):
                    break

        # Never promote pattern guesses
        for obs in list(observations):
            if obs.pattern_guessed:
                continue

        contact_graph = build_account_contact_graph(
            observations,
            account_cnpj=account_cnpj,
            dnc_emails=dnc_emails,
            bounced_emails=bounced_emails,
        )
        if contact_graph.people or contact_graph.functional_mailboxes:
            state = advance(state, InvestigationState.CONTACTS_RESOLVED)

        best_by_service: dict[str, dict[str, Any]] = {}
        for svc in cfg.services:
            sel = select_best_for_service(contact_graph, svc)
            if sel:
                best_by_service[svc] = sel

        referral_routes = []
        for m in contact_graph.functional_mailboxes:
            if m.email and m.is_commercially_usable():
                referral_routes.append(
                    {
                        "email": m.email,
                        "role_observed": m.role_observed,
                        "source_document_id": m.source_document_id,
                        "epistemic_class": m.epistemic_class.value,
                    }
                )

        has_enrollable = any(
            p.emails and p.confidence >= 0.55 and p.epistemic_best
            in {
                EpistemicClass.COMPANY_DECLARED.value,
                EpistemicClass.ADMIN_RECORDED_COMPANY_REP.value,
                EpistemicClass.COMPANY_DOMAIN_OBSERVED.value,
            }
            for p in contact_graph.people
        )
        has_verified = has_enrollable  # process docs count as verified observation
        has_referral = bool(referral_routes)
        has_unverified = bool(contact_graph.people) and not has_enrollable

        if has_enrollable or has_referral:
            state = advance(state, InvestigationState.CONTACTS_VERIFIED)
            state = advance(state, InvestigationState.COMPLETE)
        elif docs_parsed:
            state = advance(state, InvestigationState.COMPLETE)

        docs_were_provided = bool(document_texts)
        terminal = derive_terminal(
            state=state,
            has_enrollable_email=has_enrollable,
            has_verified_email=has_verified,
            has_referral_route=has_referral and not has_enrollable,
            has_unverified_contact=has_unverified,
            process_path_applicable=path_applicable,
            process_path_attempted=process_attempted or docs_were_provided,
            process_number_found=process_number_found or docs_were_provided,
            portal_resolved=portal_resolved or docs_were_provided,
            docs_fetched=docs_fetched or docs_were_provided,
            docs_parsed=docs_parsed or docs_were_provided,
            blockers=blockers,
        )

        # Explicit: site/web-only is NOT used here — if no contracts and no docs, PROCESS_NOT_TRACED
        if not path_applicable and not docs_were_provided:
            terminal = TerminalState.PROCESS_NOT_TRACED
            research_gaps.append("process_path_not_applicable_without_contracts")

        outreach = graph_to_outreach_contacts(contact_graph)
        funnel = {
            "contracts_resolved": bool(graph.contracts),
            "process_number_resolved": process_number_found,
            "process_portal_resolved": portal_resolved,
            "documents_fetched": docs_fetched or bool(document_texts),
            "company_authored_docs_found": company_authored,
            "any_email": any(p.emails for p in contact_graph.people)
            or any(m.email for m in contact_graph.functional_mailboxes),
            "verified_email": has_verified,
            "enrollable_email": has_enrollable,
            "named_contact": any(p.name for p in contact_graph.people),
            "relevant_role": any(p.roles for p in contact_graph.people),
            "referral_route": has_referral,
        }

        dossier = {
            "ACCOUNT": account_cnpj,
            "IDENTITY": {"cnpj": account_cnpj, "razao_social": razao_social},
            "CONTRACT_PORTFOLIO": [c.to_dict() for c in graph.contracts],
            "ADMINISTRATIVE_PROCESSES": [
                {
                    "contract_id": c.contract_id,
                    "process": c.administrative_process_number,
                    "orgao": c.contracting_authority_cnpj,
                    "external": c.external_process_sources,
                }
                for c in graph.contracts
            ],
            "PEOPLE": [p.to_dict() for p in contact_graph.people],
            "EMAILS": sorted({e for p in contact_graph.people for e in p.emails}),
            "REFERRAL_ROUTE": referral_routes,
            "BEST_CONTACT_PER_SERVICE": best_by_service,
            "CONFIDENCE": {
                "enrollable": has_enrollable,
                "terminal": terminal.value,
            },
            "RESEARCH_GAPS": research_gaps,
            "SOURCE_PROVENANCE": "process_first",
        }

        if self.registry and self.config.registry_path:
            try:
                self.registry.save()
            except Exception:  # noqa: S110
                pass

        return AccountEnrichmentResult(
            account_cnpj=account_cnpj,
            razao_social=razao_social,
            investigation_state=state,
            terminal_state=terminal,
            process_graph=graph,
            contact_graph=contact_graph,
            best_contacts_by_service=best_by_service,
            referral_routes=referral_routes,
            blockers=blockers,
            funnel_flags=funnel,
            limitations=list(graph.limitations),
            research_gaps=research_gaps,
            dossier=dossier,
            outreach_contacts=outreach,
        )


def enrich_account(
    account_cnpj: str,
    *,
    razao_social: str | None = None,
    contracts: list[dict[str, Any]] | None = None,
    document_texts: list[dict[str, Any]] | None = None,
    allow_network: bool = False,
    **kwargs: Any,
) -> AccountEnrichmentResult:
    enricher = ProcessFirstEnricher(config=ProcessFirstConfig(allow_network=allow_network, **{
        k: v for k, v in kwargs.items() if k in ProcessFirstConfig.__dataclass_fields__
    }))
    return enricher.enrich(
        account_cnpj=account_cnpj,
        razao_social=razao_social,
        contracts=contracts,
        document_texts=document_texts,
        known_company_domains=kwargs.get("known_company_domains"),
        dnc_emails=kwargs.get("dnc_emails"),
        bounced_emails=kwargs.get("bounced_emails"),
        existing_enrollable=bool(kwargs.get("existing_enrollable")),
    )
