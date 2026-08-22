"""Versioned ``confenge-dossier/1.0`` envelope, content hash and public projection."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from scripts.dossier.compose import (
    build_buyer_map,
    build_competitors,
    build_expiring,
    build_findings,
    build_identity,
    build_opportunities,
    build_price_panel,
)
from scripts.dossier.constants import (
    CATALOG_FIXTURE,
    CATALOG_OFFICIAL_LIVE,
    COMPETITOR_LIMIT,
    CONSUMER_WEB_CFG,
    CONTRACT_VERSION,
    DATA_HOLD,
    DATA_READY,
    DATA_REJECT,
    EXPIRING_WINDOW_DAYS,
    FORBIDDEN_CLAIM_TOKENS,
    FORBIDDEN_METRIC_KEYS,
    GRAIN,
    HARD_REJECT_REASONS,
    METHOD_VERSION,
    OFFER_CATALOG,
    OFFER_ID,
    POLICY_VERSION,
    PRODUCER_EXTRA_CLI,
    PUBLIC_REDACTED_FIELDS,
    PUBLIC_SCHEMA,
    REASON_FIXTURE_LABELED_LIVE,
    REASON_FIXTURE_NOT_LIVE,
    REASON_INVALID_CNPJ,
    REASON_TABLE_MISSING,
    REQUIRED_SECTIONS,
    SCHEMA,
    SECTION_BUYER_MAP,
    SECTION_COMPETITORS,
    SECTION_IDENTITY,
    SECTION_OPPORTUNITIES,
    SECTION_PRICE_PANEL,
    UNKNOWN,
)
from scripts.dossier.models import DossierRequest, DossierResult, Section, cnpj14, worst_state
from scripts.dossier.sources import Source

# Excluded from the content hash so two runs over the same data agree byte for byte.
VOLATILE_KEYS = frozenset({"generated_at", "observed_at", "producer_sha", "content_hash", "duration_ms"})

LIMITATION_REFERENCE_SCOPE = (
    "O painel de preços usa o conjunto de referência de órgãos públicos no raio de 200 km "
    "da base de referência; não é uma amostra nacional."
)
LIMITATION_UNKNOWN = "Campo ausente permanece UNKNOWN e não entra no denominador. UNKNOWN não é zero."
LIMITATION_NO_CLAIM = (
    "Os achados são fatos observados mais a pergunta que abrem. O dossiê não afirma direito, "
    "desequilíbrio econômico-financeiro, dano ou que um reajuste seja devido."
)
LIMITATION_FIXTURE = "Execução em modo fixture. Não é evidência oficial e não pode ser publicada como tal."
LIMITATION_ACTIVE_ONLY = (
    "Contratos refletem o estado canônico do DataLake na data de observação; aditivos posteriores "
    "à última coleta podem não estar refletidos."
)


def producer_sha() -> str | None:
    env = os.environ.get("CONFENGE_REPOSITORY_SHA")
    if env:
        return env.strip()
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S607 -- git resolved from PATH by design; fixed argv, no shell
            capture_output=True,
            text=True,
            timeout=10,
            cwd=Path(__file__).resolve().parents[2],
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def _strip_volatile(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_volatile(v) for k, v in sorted(value.items()) if k not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [_strip_volatile(v) for v in value]
    return value


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def content_hash(document: dict[str, Any]) -> str:
    stable = canonical_json(_strip_volatile(document))
    return "sha256:" + hashlib.sha256(stable.encode("utf-8")).hexdigest()


def dossier_id(cnpj: str, as_of: str, catalog_mode: str) -> str:
    digest = hashlib.sha256(f"{cnpj}|{as_of}|{catalog_mode}".encode()).hexdigest()[:16]
    return f"cfg-dossier-{digest}"


def _fold_state(sections: tuple[Section, ...]) -> tuple[str, tuple[str, ...]]:
    by_id = {s.section_id: s for s in sections}
    required_states = tuple(by_id[s].state for s in REQUIRED_SECTIONS if s in by_id)
    state = worst_state(required_states)
    reasons: list[str] = []
    for section in sections:
        for code in section.reason_codes:
            if code not in reasons:
                reasons.append(code)
    if any(code in HARD_REJECT_REASONS for code in reasons):
        state = DATA_REJECT
    # Competitors, expiring contracts and open bids are offer scope too. A source
    # that is simply absent must not fold to READY behind the required trio.
    if any(REASON_TABLE_MISSING in section.reason_codes for section in sections):
        state = worst_state((state, DATA_HOLD))
    return state, tuple(reasons)


EXEMPT_TEXT_SUFFIXES = (
    ".objeto",
    ".objeto_contrato",
    ".razao_social",
    ".nome_fantasia",
    ".buyer_nome",
    ".orgao_nome",
    ".supplier_nome",
)
# The declared-limitations block is frozen policy text under review, not generated
# content. `test_limitations_are_frozen_constants` pins it so the exemption cannot
# become a hole through which generated prose escapes the scan.
EXEMPT_TEXT_PREFIXES = ("$.limitations",)
# Keys whose value is copied verbatim from an official publication.
OFFICIAL_TEXT_KEYS = frozenset(
    {"objeto", "objeto_contrato", "buyer_nome", "orgao_nome", "supplier_nome", "razao_social", "nome_fantasia"}
)


def scan_forbidden(document: dict[str, Any]) -> tuple[str, ...]:
    """Return forbidden claim tokens or metric keys found anywhere in the document.

    Free-text carried straight from official ``objeto`` fields is exempt: the
    engine must not rewrite official text, and an official object that contains
    the word "manutenção" or "irregular" is a fact, not a claim by CONFENGE.
    """
    hits: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in FORBIDDEN_METRIC_KEYS:
                    hits.append(f"metric_key:{key}@{path}")
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")
        elif isinstance(node, str):
            if path.endswith(EXEMPT_TEXT_SUFFIXES) or path.startswith(EXEMPT_TEXT_PREFIXES):
                return
            lowered = node.lower()
            for token in FORBIDDEN_CLAIM_TOKENS:
                if token in lowered:
                    hits.append(f"claim_token:{token}@{path}")

    walk(document, "$")
    return tuple(sorted(set(hits)))


def official_free_text(document: dict[str, Any]) -> tuple[str, ...]:
    """Every string the engine copied verbatim from an official source."""
    texts: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in OFFICIAL_TEXT_KEYS and isinstance(value, str):
                    texts.append(value)
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(document, "$")
    return tuple(texts)


def scan_markdown(markdown: str, document: dict[str, Any]) -> tuple[str, ...]:
    """Scan the delivered markdown, exempting text quoted from official sources.

    The rendered document is what the client reads, so it is scanned like the
    JSON. Path-based exemptions do not survive rendering, so official ``objeto``
    text is recognised by value: a token that also appears inside an official
    string the engine copied is that source's word, not a CONFENGE claim.
    """
    lowered = markdown.lower()
    official = " ".join(official_free_text(document)).lower()
    return tuple(
        sorted(
            {
                f"claim_token:{token}@$.markdown"
                for token in FORBIDDEN_CLAIM_TOKENS
                if token in lowered and token not in official
            }
        )
    )


def build_dossier(source: Source, request: DossierRequest) -> tuple[DossierResult, dict[str, Any]]:
    normalized = cnpj14(request.cnpj)
    competitor_limit = request.competitor_limit or COMPETITOR_LIMIT
    window_days = request.expiring_window_days or EXPIRING_WINDOW_DAYS

    if normalized is None:
        result = DossierResult(
            request=request,
            dossier_id=dossier_id(request.cnpj, request.as_of, request.catalog_mode),
            data_state=DATA_REJECT,
            sections=(),
            findings=(),
            reason_codes=(REASON_INVALID_CNPJ,),
            limitations=(LIMITATION_UNKNOWN,),
        )
        return result, _document(
            result, catalog_mode=request.catalog_mode, competitor_limit=competitor_limit, window_days=window_days
        )

    if request.catalog_mode == CATALOG_OFFICIAL_LIVE and source.catalog_mode != CATALOG_OFFICIAL_LIVE:
        result = DossierResult(
            request=request,
            dossier_id=dossier_id(normalized, request.as_of, request.catalog_mode),
            data_state=DATA_REJECT,
            sections=(),
            findings=(),
            reason_codes=(REASON_FIXTURE_LABELED_LIVE,),
            limitations=(LIMITATION_FIXTURE,),
        )
        return result, _document(
            result, catalog_mode=request.catalog_mode, competitor_limit=competitor_limit, window_days=window_days
        )

    identity_read = source.identity(normalized)
    contracts_read = source.contracts(normalized)
    buyers_read = source.buyers(normalized)
    totals_read = source.portfolio_totals(normalized)
    competitors_read = source.competitors(normalized)
    price_read = source.price_panel(normalized)
    expiring_read = source.expiring(normalized, window_days, request.as_of)
    opportunities_read = source.opportunities(normalized)

    identity = build_identity(identity_read)
    buyer_map = build_buyer_map(buyers_read, contracts_read, totals_read)
    competitors = build_competitors(competitors_read, competitor_limit)
    price_panel = build_price_panel(price_read)
    expiring = build_expiring(expiring_read, window_days)
    opportunities = build_opportunities(opportunities_read)

    sections = (identity, buyer_map, competitors, price_panel, expiring, opportunities)
    findings = build_findings(
        contracts=contracts_read,
        buyer_map=buyer_map,
        price_panel=price_panel,
        expiring=expiring,
        opportunities=opportunities,
        as_of=request.as_of,
        window_days=window_days,
    )
    state, reasons = _fold_state(sections)

    limitations = [LIMITATION_UNKNOWN, LIMITATION_NO_CLAIM, LIMITATION_ACTIVE_ONLY, LIMITATION_REFERENCE_SCOPE]
    if source.catalog_mode == CATALOG_FIXTURE:
        limitations.insert(0, LIMITATION_FIXTURE)
        reasons = tuple([REASON_FIXTURE_NOT_LIVE, *[r for r in reasons if r != REASON_FIXTURE_NOT_LIVE]])

    result = DossierResult(
        request=request,
        dossier_id=dossier_id(normalized, request.as_of, source.catalog_mode),
        data_state=state,
        sections=sections,
        findings=findings,
        reason_codes=reasons,
        limitations=tuple(limitations),
    )
    document = _document(
        result,
        catalog_mode=source.catalog_mode,
        competitor_limit=competitor_limit,
        window_days=window_days,
        contract_count=contracts_read.row_count,
    )
    return result, document


def _document(
    result: DossierResult,
    *,
    catalog_mode: str,
    competitor_limit: int,
    window_days: int,
    contract_count: int = 0,
) -> dict[str, Any]:
    sections = {section.section_id: section.as_dict() for section in result.sections}
    observed = [s.observed_at for s in result.sections if s.observed_at]
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "accepted_schemas": [SCHEMA],
        "contract_version": CONTRACT_VERSION,
        "method_version": METHOD_VERSION,
        "policy_version": POLICY_VERSION,
        "grain": GRAIN,
        "dossier_id": result.dossier_id,
        "cnpj14": cnpj14(result.request.cnpj),
        "as_of": result.request.as_of,
        "catalog_mode": catalog_mode,
        "data_state": result.data_state,
        "producer": PRODUCER_EXTRA_CLI,
        "producer_sha": result.request.producer_sha,
        "consumer": result.request.consumer_id,
        "offer": {"offer_id": OFFER_ID, "catalog": OFFER_CATALOG},
        "parameters": {
            "competitor_limit": competitor_limit,
            "expiring_window_days": window_days,
        },
        "observed_at": min(observed) if observed else None,
        "totals": {
            "contract_count": contract_count,
            "section_count": len(result.sections),
            "finding_count": len(result.findings),
        },
        "reason_codes": list(result.reason_codes),
        "limitations": list(result.limitations),
        "sections": sections,
        "findings": [finding.as_dict() for finding in result.findings],
    }
    document["content_hash"] = content_hash(document)
    return document


def _redact(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: (UNKNOWN if k in PUBLIC_REDACTED_FIELDS else _redact(v)) for k, v in node.items()}
    if isinstance(node, list):
        return [_redact(v) for v in node]
    return node


def _band(value: Any, edges: tuple[int, ...]) -> str:
    """Bucket a count so it stops being a unique quasi-identifier."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return UNKNOWN
    low = 1
    for edge in edges:
        if number <= edge:
            return f"{low}-{edge}"
        low = edge + 1
    return f"{low}+"


def _money_band(value: Any) -> str:
    """Order-of-magnitude band. An exact BRL sum resolves a redacted supplier."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return UNKNOWN
    if number <= 0:
        return UNKNOWN
    for edge in (100_000, 1_000_000, 10_000_000, 100_000_000):
        if number < edge:
            return "<" + f"{edge:,}".replace(",", ".")
    return ">=100.000.000"


def _public_competitors(section: dict[str, Any]) -> dict[str, Any]:
    """Publish the shape of the competition, never a row that identifies one.

    An exact valor_sum over a deterministic, publicly reproducible scope is a
    perfect join key: one ``GROUP BY supplier_cnpj HAVING SUM(valor) = <published>``
    resolves a redacted supplier back to a named CNPJ. Exact counts do the same
    job more slowly. Only banded aggregates leave.
    """
    payload = section.get("payload") or {}
    competitors = payload.get("competitors") or []
    counts = [int(c.get("contract_count") or 0) for c in competitors]
    shared = [int(c.get("shared_buyer_count") or 0) for c in competitors]
    return {
        **{k: v for k, v in section.items() if k != "payload"},
        "payload": {
            "competitor_count": len(competitors),
            "primary_category": payload.get("primary_category", UNKNOWN),
            "selection_rule": payload.get("selection_rule", UNKNOWN),
            "contract_count_band": f"{min(counts)}-{max(counts)}" if counts else UNKNOWN,
            "shared_buyer_count_band": f"{min(shared)}-{max(shared)}" if shared else UNKNOWN,
            "value_bands": sorted({_money_band(c.get("valor_sum")) for c in competitors}),
        },
    }


def public_projection(document: dict[str, Any]) -> dict[str, Any]:
    """De-identified projection for web-cfg.

    The prospect is never the subject of a public page. Public bodies, their
    published contracts and the reference panel are public record and stay.
    """
    sections = document.get("sections", {})
    identity = (sections.get(SECTION_IDENTITY) or {}).get("payload", {})
    buyer_map = (sections.get(SECTION_BUYER_MAP) or {}).get("payload", {})

    public: dict[str, Any] = {
        "schema": PUBLIC_SCHEMA,
        "accepted_schemas": [PUBLIC_SCHEMA],
        "contract_version": CONTRACT_VERSION,
        "method_version": METHOD_VERSION,
        "policy_version": POLICY_VERSION,
        "grain": "anonymous_supplier_profile",
        "source_dossier_hash": document.get("content_hash"),
        "as_of": document.get("as_of"),
        "catalog_mode": document.get("catalog_mode"),
        "data_state": document.get("data_state"),
        "producer": PRODUCER_EXTRA_CLI,
        "consumer": CONSUMER_WEB_CFG,
        # Exact counts plus UF plus a 7-digit CNAE identify one supplier
        # nationwide. Bands describe the recorte without naming it.
        "subject_profile": {
            "uf": identity.get("uf", UNKNOWN),
            "cnae_division": str(identity.get("cnae_principal", UNKNOWN))[:2],
            "buyer_count_band": _band(buyer_map.get("buyer_count"), (5, 20, 50, 100)),
            "contract_count_band": _band(buyer_map.get("contract_count"), (10, 50, 200, 1000)),
        },
        "reason_codes": document.get("reason_codes", []),
        "limitations": document.get("limitations", []),
        "sections": {
            SECTION_PRICE_PANEL: _redact(sections.get(SECTION_PRICE_PANEL, {})),
            SECTION_COMPETITORS: _public_competitors(sections.get(SECTION_COMPETITORS, {})),
            SECTION_OPPORTUNITIES: _redact(sections.get(SECTION_OPPORTUNITIES, {})),
        },
        "findings": [
            _redact(f)
            for f in document.get("findings", [])
            if f.get("finding_id", "").startswith(("value_position_in_category", "open_opportunity_from_known_buyer"))
        ],
        "publication_readiness": (
            "DATA_READY"
            if document.get("data_state") == DATA_READY and document.get("catalog_mode") == CATALOG_OFFICIAL_LIVE
            else DATA_HOLD
        ),
    }
    public["content_hash"] = content_hash(public)
    return public
