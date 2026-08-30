"""Shipped coverage evaluate path. Tests and CLI call this function."""

from __future__ import annotations

from typing import Any

from scripts.national_coverage.consumer import consumer_answer, coverage_payload
from scripts.national_coverage.corpus import (
    map_publishers,
    observed_orgs_from_mapping,
    snapshot_from_publishers,
)
from scripts.national_coverage.hashing import digest
from scripts.national_coverage.models import (
    CORE_METHOD_VERSION,
    DEFAULT_FRESHNESS_WINDOW_HOURS,
    DEFAULT_GRAIN,
    ConsultedPartitions,
    CorpusPublisher,
    CoverageRequest,
    NationalCoverageError,
    PublishingOrg,
)
from scripts.national_coverage.partitions import assign_partition_statuses
from scripts.national_coverage.policy import normalize_org_id
from scripts.national_coverage.reconcile import reconcile
from scripts.national_coverage.universe import (
    build_observed_corpus_universe,
    build_official_universe,
)


def _orgs(raw: list[Any]) -> tuple[PublishingOrg, ...]:
    orgs: list[PublishingOrg] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        org_id = normalize_org_id(str(item.get("org_id") or item.get("cnpj") or ""))
        if not org_id or org_id in seen:
            continue
        seen.add(org_id)
        aliases = item.get("aliases") or []
        orgs.append(
            PublishingOrg(
                org_id=org_id,
                name=str(item.get("name") or item.get("razaoSocial") or org_id),
                unit_count=int(item.get("unit_count") or 1),
                uf=str(item["uf"]).strip().upper() if item.get("uf") else None,
                esfera=str(item["esfera"]) if item.get("esfera") else None,
                aliases=tuple(str(alias) for alias in aliases),
            )
        )
    return tuple(orgs)


def _publishers(raw: list[Any]) -> tuple[CorpusPublisher, ...]:
    pubs: list[CorpusPublisher] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        org_id = normalize_org_id(str(item.get("raw_org_id") or item.get("org_id") or item.get("cnpj") or ""))
        if not org_id:
            continue
        aliases = item.get("aliases") or []
        pubs.append(
            CorpusPublisher(
                raw_org_id=org_id,
                contract_count=int(item.get("contract_count") or 0),
                uf=str(item["uf"]).strip().upper() if item.get("uf") else None,
                esfera=str(item["esfera"]) if item.get("esfera") else None,
                first_seen=str(item["first_seen"]) if item.get("first_seen") else None,
                last_seen=str(item["last_seen"]) if item.get("last_seen") else None,
                aliases=tuple(str(alias) for alias in aliases),
            )
        )
    return tuple(pubs)


def _consulted(raw: dict[str, Any] | None, observed: frozenset[str]) -> ConsultedPartitions:
    payload = raw or {}
    found = {normalize_org_id(str(item)) for item in payload.get("found") or []}
    if payload.get("use_observed_as_found", True):
        found |= set(observed)
    zero_raw = payload.get("zero_confirmed") or {}
    failed_raw = payload.get("failed") or {}
    blocked_raw = payload.get("blocked") or {}
    queried = {normalize_org_id(str(item)) for item in payload.get("queried") or []}
    queried |= found
    queried |= {normalize_org_id(str(key)) for key in zero_raw}
    queried |= {normalize_org_id(str(key)) for key in failed_raw}
    return ConsultedPartitions(
        found=frozenset(found),
        zero_confirmed={normalize_org_id(str(key)): str(value) for key, value in zero_raw.items()},
        failed={normalize_org_id(str(key)): str(value) for key, value in failed_raw.items()},
        blocked={normalize_org_id(str(key)): str(value) for key, value in blocked_raw.items()},
        queried=frozenset(queried),
    )


def _request(raw: dict[str, Any] | None) -> CoverageRequest:
    payload = raw or {}
    return CoverageRequest(
        geography=str(payload.get("geography") or "BR"),
        period=str(payload.get("period") or ""),
        source=str(payload.get("source") or "pncp"),
        grain=str(payload.get("grain") or DEFAULT_GRAIN),
    )


def evaluate_from_dict(payload: dict[str, Any]) -> dict[str, Any]:
    official = payload.get("official") or {}
    corpus_raw = payload.get("corpus") or {}
    status = str(official.get("status") or "BLOCKED").upper()
    competence = str(official.get("competence") or payload.get("competence") or "contratos-2026")
    cutoff = str(official.get("cutoff") or payload.get("cutoff") or "")
    as_of = str(official.get("as_of") or corpus_raw.get("as_of") or cutoff)
    retrieved_at = str(official.get("retrieved_at") or as_of or cutoff)
    source = str(official.get("source") or "pncp")
    request = _request(payload.get("request"))
    publishers = _publishers(list(corpus_raw.get("publishers") or []))
    corpus_source = str(corpus_raw.get("source") or "pncp_supplier_contracts")
    corpus_as_of = str(corpus_raw.get("as_of") or as_of)
    measured = bool(official) or bool(publishers) or bool(payload.get("consulted"))
    corpus = None
    if publishers or corpus_raw:
        if not corpus_as_of:
            raise NationalCoverageError("corpus as_of is required")
        corpus = snapshot_from_publishers(publishers, as_of=corpus_as_of, source=corpus_source)

    if status == "AVAILABLE":
        orgs = _orgs(list(official.get("orgs") or []))
        raw_hash = str(official.get("raw_hash") or "")
        if not raw_hash:
            raw_hash = digest({"orgs": official.get("orgs") or [], "source": source, "cutoff": cutoff})
        universe = build_official_universe(
            source=source,
            source_url=official.get("source_url"),
            competence=competence,
            cutoff=cutoff,
            as_of=as_of or cutoff,
            retrieved_at=retrieved_at or as_of or cutoff,
            raw_hash=raw_hash,
            orgs=orgs,
            method_version=str(official.get("method_version") or CORE_METHOD_VERSION),
            units_enumerated=bool(official.get("units_enumerated", True)),
        )
        mapping = (
            map_publishers(corpus, universe)
            if corpus is not None
            else map_publishers(
                snapshot_from_publishers((), as_of=as_of or cutoff, source=corpus_source),
                universe,
            )
        )
        consulted = _consulted(payload.get("consulted"), observed_orgs_from_mapping(mapping))
        partitions = assign_partition_statuses(universe, consulted, request)
    else:
        cause = str(official.get("block_cause") or "official_catalog_not_provided")
        seen_observed: set[str] = set()
        observed_list: list[PublishingOrg] = []
        for pub in publishers:
            if pub.raw_org_id in seen_observed:
                continue
            seen_observed.add(pub.raw_org_id)
            observed_list.append(
                PublishingOrg(
                    org_id=pub.raw_org_id,
                    name=pub.raw_org_id,
                    unit_count=1,
                    uf=pub.uf,
                    esfera=pub.esfera,
                    aliases=pub.aliases,
                )
            )
        observed_orgs = tuple(observed_list)
        observed_hash = str(
            corpus_raw.get("raw_hash") or (corpus.snapshot_hash if corpus else digest({"blocked": cause}))
        )
        universe = build_observed_corpus_universe(
            source=str(corpus_raw.get("source") or source),
            competence=competence,
            cutoff=cutoff or as_of or "unspecified",
            as_of=as_of or cutoff or corpus_as_of or "unspecified",
            retrieved_at=retrieved_at or as_of or cutoff or corpus_as_of or "unspecified",
            raw_hash=observed_hash,
            orgs=observed_orgs,
            official_block_cause=cause,
        )
        mapping = (
            map_publishers(corpus, universe)
            if corpus is not None
            else map_publishers(
                snapshot_from_publishers((), as_of=universe.as_of, source=corpus_source),
                universe,
            )
        )
        consulted = _consulted(payload.get("consulted"), observed_orgs_from_mapping(mapping))
        partitions = assign_partition_statuses(universe, consulted, request)

    freshness = payload.get("freshness") or {}
    blockers_raw = payload.get("authorization_blockers") or []
    if not isinstance(blockers_raw, list):
        raise NationalCoverageError("authorization_blockers_must_be_a_list")
    authorization_blockers = tuple(
        dict.fromkeys(str(item).strip() for item in blockers_raw if str(item).strip())
    )
    record = reconcile(
        universe=universe,
        partitions=partitions,
        corpus=corpus,
        mapping=mapping,
        request=request,
        freshness_window_hours=float(freshness.get("window_hours") or DEFAULT_FRESHNESS_WINDOW_HOURS),
        freshness_as_of=str(freshness.get("as_of") or (corpus.as_of if corpus else universe.as_of)),
        measured=measured,
        authorization_blockers=authorization_blockers,
    )
    consumer = consumer_answer(record)
    return coverage_payload(record, consumer)
