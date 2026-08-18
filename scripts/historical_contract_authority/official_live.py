"""Bounded official-live acquisition and atomic consumer handoff."""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from scripts.historical_contract_authority.aec import (
    REASON_AEC,
    aec_disposition,
    documentary_score,
    documentary_signals,
)
from scripts.historical_contract_authority.consumer import assemble_consumer_dossier
from scripts.historical_contract_authority.freshness import strip_temporal_for_hash
from scripts.historical_contract_authority.schema import (
    CONSUMER_ID,
    content_hash,
    producer_sha,
    sha256_bytes,
    sha256_text,
)
from scripts.official_contract_semantics.export_publication import observation_to_snapshot_record
from scripts.official_contract_semantics.extract import extract_payload
from scripts.official_contract_semantics.http_client import fetch_official
from scripts.official_contract_semantics.identity import raw_record_hash_for
from scripts.official_contract_semantics.live import (
    default_live_window,
    resolve_dsn,
    run_live_readonly,
)
from scripts.official_contract_semantics.models import OfficialContractObservation, observation_from_mapping

OFFICIAL_LIVE_HANDOFF_SCHEMA = "official-live-authority-handoff/1.1"
MAX_LIVE_CANDIDATES = 20
MAX_LIVE_READY = 1
MAX_PRIMARY_ARTIFACTS = 40
PNCP_CONTRATO_ID = re.compile(r"^(\d{14})-\d+-(\d+)/(\d{4})$")
PNCP_API_CONTRACT = "https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/contratos/{ano}/{seq}"
DEFAULT_RENDEZVOUS = (
    Path.home() / ".local" / "share" / "confenge" / "handoffs" / "contract-analysis" / "official-live-01"
)
PRODUCER_REPO = "tjsasakifln/extra-cli"


def rendezvous_dir() -> Path:
    root = os.environ.get("CONFENGE_HANDOFF_DIR")
    if root:
        return Path(root) / "contract-analysis" / "official-live-01"
    return DEFAULT_RENDEZVOUS


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def git_identity(repo_root: Path | None = None) -> dict[str, str]:
    root = repo_root or Path(__file__).resolve().parents[2]
    identity = {"repo": PRODUCER_REPO, "branch": "unknown", "commit": producer_sha()[:40]}
    git_dir = root / ".git"
    if git_dir.is_file():
        text = git_dir.read_text(encoding="utf-8").strip()
        if text.startswith("gitdir:"):
            git_dir = Path(text.split(":", 1)[1].strip())
            if not git_dir.is_absolute():
                git_dir = (root / git_dir).resolve()
    if not git_dir.is_dir():
        return identity
    common = git_dir
    commondir = git_dir / "commondir"
    if commondir.is_file():
        common_text = commondir.read_text(encoding="utf-8").strip()
        candidate = Path(common_text)
        common = candidate if candidate.is_absolute() else (git_dir / candidate).resolve()
    head = git_dir / "HEAD"
    if not head.is_file():
        return identity
    ref = head.read_text(encoding="utf-8").strip()
    if ref.startswith("ref:"):
        ref_name = ref.split(":", 1)[1].strip()
        identity["branch"] = ref_name.split("refs/heads/", 1)[-1]
        for base in (git_dir, common):
            ref_path = base / ref_name
            if ref_path.is_file():
                identity["commit"] = ref_path.read_text(encoding="utf-8").strip()
                break
    elif len(ref) >= 40:
        identity["commit"] = ref
    return identity


def _object_text(obs: OfficialContractObservation | dict[str, Any]) -> str:
    if isinstance(obs, OfficialContractObservation):
        return str(obs.object_text or "")
    return str(obs.get("object_text") or obs.get("objeto_contrato") or "")


def _contract_id(obs: OfficialContractObservation | dict[str, Any]) -> str:
    if isinstance(obs, OfficialContractObservation):
        return str(obs.contract_identifier or obs.observation_id)
    return str(obs.get("contract_identifier") or obs.get("canonical_contract_id") or obs.get("observation_id") or "")


def group_observations(observations: list[OfficialContractObservation]) -> dict[str, list[OfficialContractObservation]]:
    grouped: dict[str, list[OfficialContractObservation]] = {}
    for item in observations:
        grouped.setdefault(_contract_id(item), []).append(item)
    return grouped


def parse_pncp_contrato_id(contrato_id: str | None) -> tuple[str, int, int] | None:
    match = PNCP_CONTRATO_ID.match((contrato_id or "").strip())
    if not match:
        return None
    return match.group(1), int(match.group(3)), int(match.group(2))


def pncp_contract_urls(contrato_id: str) -> dict[str, str] | None:
    parsed = parse_pncp_contrato_id(contrato_id)
    if not parsed:
        return None
    cnpj, ano, seq = parsed
    detail = PNCP_API_CONTRACT.format(cnpj=cnpj, ano=ano, seq=seq)
    return {"detail": detail, "termos": f"{detail}/termos", "arquivos": f"{detail}/arquivos"}


def select_candidates(
    grouped: dict[str, list[OfficialContractObservation]],
    *,
    limit: int = MAX_LIVE_CANDIDATES,
) -> tuple[list[str], list[dict[str, str]]]:
    scored: list[tuple[int, str, str]] = []
    log: list[dict[str, str]] = []
    for contract_id, items in grouped.items():
        blob = " ".join(_object_text(item) for item in items)
        eligible, reason = aec_disposition(blob)
        has_amendment = any(item.source_kind == "amendment" or item.amendment_type for item in items)
        if not contract_id:
            log.append({"contract_id": "", "disposition": "UNKNOWN", "reason": "missing_contract_identifier"})
            continue
        if not eligible:
            log.append({"contract_id": contract_id, "disposition": "exited", "reason": reason, "score": "0"})
            continue
        score = documentary_score((blob,), has_amendment_artifact=has_amendment)
        scored.append((score, contract_id, REASON_AEC if not has_amendment else "aec_with_amendment_artifact"))
    scored.sort(key=lambda item: (-item[0], item[1]))
    chosen = [item[1] for item in scored[:limit]]
    chosen_set = set(chosen)
    for score, contract_id, reason in scored:
        if contract_id in chosen_set:
            log.append({"contract_id": contract_id, "disposition": "entered", "reason": reason, "score": str(score)})
        else:
            log.append(
                {
                    "contract_id": contract_id,
                    "disposition": "exited",
                    "reason": "beyond_candidate_cap",
                    "score": str(score),
                }
            )
    return chosen, log


def _locator_for(obs: OfficialContractObservation) -> dict[str, Any]:
    loc = obs.locator.as_dict()
    if loc:
        return loc
    if obs.source_kind == "official_page":
        return {"section": "official-page"}
    return {"json_path": "$.objetoContrato"} if obs.object_text else {}


def _claims_from_observations(
    items: list[OfficialContractObservation],
    *,
    artifact_by_doc: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    facts: list[dict[str, Any]] = []
    unknowns: list[dict[str, Any]] = []
    inferences: list[dict[str, Any]] = []
    for item in items:
        if item.source_kind == "official_page":
            continue
        artifact = artifact_by_doc.get(str(item.source_document_id or item.observation_id)) or {}
        url = item.official_url or artifact.get("url")
        digest = item.source_document_sha256 or artifact.get("sha256")
        listing_index = (item.extra or {}).get("listing_index")
        prefix = f"$.data[{listing_index}]" if listing_index is not None else "$"
        locator = item.locator.as_dict() or {"json_path": f"{prefix}.objetoContrato"}
        evidence_id = str(item.source_document_id or item.contract_identifier or item.observation_id)
        stable = str(item.contract_identifier or evidence_id).replace("/", "-")
        base = {
            "evidence_id": evidence_id,
            "url": url,
            "sha256": digest,
            "locator": locator,
            "source_refs": [evidence_id],
        }
        if item.source_kind == "process_document" and item.object_text and url and digest and locator:
            page_tag = locator.get("page") if isinstance(locator, dict) else None
            suffix = f"{stable}-p{page_tag}" if page_tag is not None else stable
            for kind, excerpt in extract_clause_excerpts(item.object_text):
                facts.append(
                    {
                        **base,
                        "claim_id": f"fact-{kind}-{suffix}",
                        "class": "FACT",
                        "text": excerpt,
                        "locator": locator,
                    }
                )
            continue
        if item.object_text and url and digest and locator:
            facts.append(
                {
                    **base,
                    "claim_id": f"fact-object-{stable}",
                    "class": "FACT",
                    "text": f"Objeto oficial: {item.object_text[:240]}",
                    "locator": {"json_path": f"{prefix}.objetoContrato"},
                }
            )
        if item.value_amount is not None and item.value_semantic:
            facts.append(
                {
                    **base,
                    "claim_id": f"fact-value-{stable}",
                    "class": "FACT",
                    "text": f"Valor {item.value_semantic} publicado: {format(item.value_amount, 'f')} {item.currency or 'BRL'}.",
                    "locator": {"json_path": f"{prefix}.valorGlobal"},
                }
            )
        if item.period_start or item.period_end:
            facts.append(
                {
                    **base,
                    "claim_id": f"fact-period-{stable}",
                    "class": "FACT",
                    "text": f"Vigência oficial {item.period_start or 'UNKNOWN'} a {item.period_end or 'UNKNOWN'}.",
                    "locator": {"json_path": f"{prefix}.dataVigenciaInicio"},
                }
            )
        if item.amendment_type and url and digest and locator:
            facts.append(
                {
                    **base,
                    "claim_id": f"fact-amendment-{stable}",
                    "class": "FACT",
                    "text": f"Fonte oficial registra tipo de aditivo: {item.amendment_type}.",
                    "locator": locator if locator else {"json_path": "$.tipoTermoContratoNome"},
                }
            )
        if item.amendment_value_delta is not None and url and digest:
            facts.append(
                {
                    **base,
                    "claim_id": f"fact-amendment-delta-{stable}",
                    "class": "FACT",
                    "text": (
                        f"Fonte oficial registra variação documental de valor: "
                        f"{format(item.amendment_value_delta, 'f')} {item.currency or 'BRL'}."
                    ),
                    "locator": {"json_path": "$.valorAcrescimo"},
                }
            )
        if item.source_kind == "process_document":
            continue
        if item.unit is None:
            unknowns.append(
                {
                    **base,
                    "claim_id": f"unk-unit-{stable}",
                    "class": "UNKNOWN",
                    "text": "Unidade física não demonstrada na fonte oficial desta execução.",
                }
            )
        if item.execution_regime is None:
            unknowns.append(
                {
                    **base,
                    "claim_id": f"unk-regime-{stable}",
                    "class": "UNKNOWN",
                    "text": "Regime de execução não demonstrado na fonte oficial desta execução.",
                }
            )
        if item.procurement_modality is None:
            unknowns.append(
                {
                    **base,
                    "claim_id": f"unk-mod-{stable}",
                    "class": "UNKNOWN",
                    "text": "Modalidade não demonstrada na fonte oficial desta execução.",
                }
            )
    return facts, inferences, unknowns


_CLAUSE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("reajuste", re.compile(r".{0,60}reajust\w*.{0,180}", re.I | re.S)),
    (
        "indice",
        re.compile(
            r".{0,40}[íi]ndice(?:\s+nacional|\s+de\s+reajuste|\s+relativo|\s+inicial)?.{0,200}",
            re.I | re.S,
        ),
    ),
    ("data_base", re.compile(r".{0,40}data do or[cç]amento.{0,140}", re.I | re.S)),
)


_NAMED_INDEX_TOKENS = (
    "nacional",
    "coluna",
    "funda",
    "getúlio",
    "getulio",
    "fgv",
    "incc",
    "dnit",
    "sinapi",
)


def extract_clause_excerpts(text: str | None) -> list[tuple[str, str]]:
    """Quote clause fragments present in official page text. Never invent an index family."""
    if not text:
        return []
    found: list[tuple[str, str]] = []
    seen_kinds: set[str] = set()
    for kind, pattern in _CLAUSE_PATTERNS:
        matches = [re.sub(r"\s+", " ", item.group(0)).strip() for item in pattern.finditer(text)]
        if not matches:
            continue
        excerpt = matches[0]
        if kind == "indice":
            named = [item for item in matches if any(token in item.casefold() for token in _NAMED_INDEX_TOKENS)]
            if named:

                def _indice_score(item: str) -> tuple[int, int, int]:
                    starts_clause = 1 if re.match(r"\d+\.\d+", item) else 0
                    starts_clean = 1 if item[:1].isupper() or item[:1].isdigit() else 0
                    return (starts_clause, starts_clean, len(item))

                excerpt = max(named, key=_indice_score)
        if kind in seen_kinds:
            continue
        seen_kinds.add(kind)
        found.append((kind, excerpt[:320]))
    return found


def _insight_for(items: list[OfficialContractObservation], facts: list[dict[str, Any]]) -> str:
    """Insight only from retrieved primary documents — never from listing keywords alone."""
    primary = next(
        (item.object_text for item in items if item.source_kind == "contract" and item.object_text),
        "",
    )
    excerpts: list[tuple[str, str]] = []
    for item in items:
        if item.source_kind == "process_document":
            excerpts.extend(extract_clause_excerpts(item.object_text))
    if not excerpts:
        for fact in facts:
            excerpts.extend(extract_clause_excerpts(str(fact.get("text") or "")))
    if excerpts:
        by_kind = {kind: excerpt for kind, excerpt in excerpts}
        quoted = " ".join(
            excerpt for kind in ("indice", "reajuste", "data_base") if (excerpt := by_kind.get(kind))
        )
        if not quoted:
            quoted = excerpts[0][1]
        return (
            f"O contrato oficial de «{(primary or '')[:120]}» documenta no PDF primário: "
            f"{quoted[:480]} A leitura é documental, sem comparação e sem afirmação de direito."
        )
    amendments = [
        item
        for item in items
        if item.source_kind == "amendment"
        and (item.amendment_type in {"valor", "prazo", "prazo_e_valor"} or item.amendment_value_delta is not None)
    ]
    if not amendments:
        return ""
    kinds = sorted({str(item.amendment_type or item.source_kind) for item in amendments})
    return (
        f"A cadeia documental oficial do contrato «{(primary or '')[:180]}» "
        f"inclui {len(amendments)} termo(s) primário(s) recuperado(s) "
        f"({', '.join(kinds)}). O insight é a sequência documental, sem comparação."
    )


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _calculations(items: list[OfficialContractObservation]) -> list[dict[str, Any]]:
    base = next(
        (
            item
            for item in items
            if item.source_kind == "contract" and item.value_amount is not None and item.value_semantic
        ),
        None,
    )
    deltas = [item for item in items if item.amendment_value_delta is not None]
    if base is None:
        return []
    base_amount = _as_decimal(base.value_amount)
    if base_amount is None or base_amount == 0:
        return []
    out: list[dict[str, Any]] = []
    meters = None
    blob = " ".join(item.object_text or "" for item in items)
    match = re.search(r"totalizando\s+([\d.]+)\s+metros", blob, re.I)
    area_m2 = None
    match_m2 = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*m[²2]", blob, re.I)
    if match_m2:
        area_m2 = _as_decimal(match_m2.group(1).replace(".", "").replace(",", "."))
    if match:
        meters = _as_decimal(match.group(1))
    if meters and meters != 0:
        unit = (base_amount / meters).quantize(Decimal("0.0001"))
        out.append(
            {
                "calculation_id": "calc-brl-per-linear-meter",
                "class": "CALCULATION",
                "text": (
                    f"Valor-base {base.value_semantic}={format(base_amount, 'f')} {base.currency or 'BRL'} "
                    f"dividido por {format(meters, 'f')} metros lineares documentados: "
                    f"{format(unit, 'f')} BRL/m."
                ),
                "inputs": {
                    "valor_base": format(base_amount, "f"),
                    "valor_base_semantic": base.value_semantic,
                    "metros_lineares": format(meters, "f"),
                    "currency": base.currency or "BRL",
                    "denominator": "metros_lineares",
                    "rounding": "quantize_0.0001",
                    "unit": "BRL/m",
                },
                "result": format(unit, "f"),
                "method": "contract_value_amount / documented_linear_meters",
            }
        )
    if area_m2 and area_m2 != 0:
        unit = (base_amount / area_m2).quantize(Decimal("0.0001"))
        out.append(
            {
                "calculation_id": "calc-brl-per-square-meter",
                "class": "CALCULATION",
                "text": (
                    f"Valor-base {base.value_semantic}={format(base_amount, 'f')} {base.currency or 'BRL'} "
                    f"dividido por {format(area_m2, 'f')} m² documentados no objeto: "
                    f"{format(unit, 'f')} BRL/m²."
                ),
                "inputs": {
                    "valor_base": format(base_amount, "f"),
                    "valor_base_semantic": base.value_semantic,
                    "area_m2": format(area_m2, "f"),
                    "currency": base.currency or "BRL",
                    "denominator": "area_m2",
                    "rounding": "quantize_0.0001",
                    "unit": "BRL/m2",
                },
                "result": format(unit, "f"),
                "method": "contract_value_amount / documented_area_m2",
            }
        )
    if not deltas:
        return out
    for index, item in enumerate(deltas, start=1):
        delta = _as_decimal(item.amendment_value_delta)
        if delta is None or delta == 0:
            continue
        ratio = (delta / base_amount).quantize(Decimal("0.0001"))
        out.append(
            {
                "calculation_id": f"calc-amendment-ratio-{index}",
                "class": "CALCULATION",
                "text": (
                    f"Razão do valor documental do termo sobre o valor-base "
                    f"{base.value_semantic}={format(base_amount, 'f')} {base.currency or 'BRL'}: "
                    f"{format(ratio, 'f')} (delta={format(delta, 'f')} / base)."
                ),
                "inputs": {
                    "valor_base": format(base_amount, "f"),
                    "valor_base_semantic": base.value_semantic,
                    "valor_termo_delta": format(delta, "f"),
                    "currency": base.currency or "BRL",
                    "denominator": "valor_base",
                    "rounding": "quantize_0.0001",
                },
                "result": format(ratio, "f"),
                "method": "amendment_value_delta / contract_value_amount",
            }
        )
    return out


def _analysis_sections(
    items: list[OfficialContractObservation],
    *,
    insight: str,
    calculations: list[dict[str, Any]],
) -> dict[str, Any]:
    objects = [item.object_text for item in items if item.object_text]
    timeline = []
    for item in items:
        stamp = item.effective_at or item.observed_at or item.source_published_at
        if stamp:
            timeline.append(
                {
                    "at": stamp,
                    "kind": item.source_kind,
                    "amendment_type": item.amendment_type,
                    "url": item.official_url,
                }
            )
    timeline.sort(key=lambda row: str(row.get("at") or ""))
    return {
        "what_documents_show": insight
        or (
            "Os bytes oficiais recuperados demonstram identidade e campos de listagem; "
            "não há termo/aditivo primário nesta execução."
        ),
        "calculation_or_timeline": {
            "calculations": calculations,
            "timeline": timeline,
        },
        "worth_checking": (
            [f"Conferir o teor integral do termo em {item.official_url}" for item in items if item.source_kind == "amendment"]
            or ["Nenhum termo primário para conferência nesta execução."]
        ),
        "limitations": [
            "Sem comparação de pares: unidade, regime, escopo e período compatíveis não foram demonstrados.",
            "atípico nunca significa irregular.",
            "Campos sem evidência oficial permanecem UNKNOWN.",
            "404, lista vazia ou linha ausente não são zero e não são inexistência no mundo.",
        ],
        "cannot_conclude": [
            "irregularidade, culpa, sobrepreço, fraude ou incapacidade",
            "relação comercial, case, cliente ou autorização de publicação/indexação",
            "ausência mundial de aditivo a partir de 404/lista vazia",
        ],
        "sources": sorted({item.official_url for item in items if item.official_url}),
        "object_excerpt": (objects[0][:240] if objects else ""),
        "documentary_signals": list(documentary_signals(*objects)),
    }


def claim_bound_to_retrieved_bytes(claim: dict[str, Any], body: bytes) -> bool:
    """True only when claim.sha256 is the hash of the bytes retrieved from claim.url."""
    digest = str(claim.get("sha256") or "")
    return bool(digest) and digest == raw_record_hash_for(body)


def verify_claim_url_hash(*, claim: dict[str, Any], cache_dir: Path | None = None) -> bool:
    url = claim.get("url")
    if not url:
        return False
    fetched = fetch_official(str(url), cache_dir=cache_dir, retries=0, rate_limit_s=0)
    if not fetched.ok or not fetched.sha256:
        return False
    return fetched.sha256 == str(claim.get("sha256") or "")


def _json_items(body: str) -> list[Any]:
    try:
        payload = json.loads(body)
    except ValueError:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return data
        return [payload]
    return []


def _amendment_type_from_term(item: dict[str, Any]) -> str | None:
    blob = " ".join(
        str(item.get(key) or "")
        for key in ("tipoTermoContratoNome", "tipoTermoContrato", "objetoTermoContrato", "objeto", "descricao")
    ).casefold()
    if item.get("qualificacaoVigencia") or "prazo" in blob or "prorrog" in blob:
        if item.get("qualificacaoAcrescimoSupressao") or "valor" in blob or "quantitativ" in blob:
            return "prazo_e_valor"
        return "prazo"
    if item.get("qualificacaoAcrescimoSupressao") or "valor" in blob or "quantitativ" in blob or "qualitativ" in blob:
        return "valor"
    if item.get("qualificacaoReajuste") or "reajuste" in blob or "repactu" in blob:
        return "outro"
    return None


def term_is_material(item: dict[str, Any]) -> bool:
    """Apostilamento de gestor/fiscal or a zero-delta empty term is not a singularity."""
    if item.get("qualificacaoAcrescimoSupressao") or item.get("qualificacaoVigencia") or item.get("qualificacaoReajuste"):
        return True
    prazo = item.get("prazoAditadoDias")
    if prazo not in {None, "", 0, 0.0, "0", "0.0"}:
        return True
    delta = item.get("valorAcrescido")
    if delta is None:
        delta = item.get("valorAcrescimo")
    if delta not in {None, "", 0, 0.0, "0", "0.0"}:
        return True
    blob = str(item.get("objetoTermoContrato") or item.get("objeto") or "").casefold()
    return any(
        token in blob
        for token in (
            "aditivo de prazo",
            "aditivo de valor",
            "reajuste",
            "reequilibr",
            "prorrog",
            "glosa",
            "mediç",
            "paralis",
            "rescis",
        )
    )


def termos_to_records(
    *,
    contract_id: str,
    termos_url: str,
    body: str,
    sha256: str,
    retrieved_at: str,
    base: OfficialContractObservation | None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, item in enumerate(_json_items(body)):
        if not isinstance(item, dict):
            continue
        if not term_is_material(item):
            continue
        kind = _amendment_type_from_term(item)
        if kind is None:
            continue
        delta = item.get("valorAcrescimo")
        if delta is None:
            delta = item.get("valorAcrescido")
        if delta in {0, 0.0, "0", "0.0"}:
            delta = None
        records.append(
            {
                "source_system": "pncp",
                "source_kind": "amendment",
                "official_url": termos_url,
                "source_document_id": f"{contract_id}:termo:{index}",
                "source_document_sha256": sha256,
                "contract_identifier": contract_id,
                "contracting_entity_identifier": base.contracting_entity_identifier if base else None,
                "supplier_identifier": base.supplier_identifier if base else None,
                "object_text": item.get("objetoTermoContrato") or item.get("objeto") or item.get("descricao"),
                "amendment_type": kind,
                "amendment_value_delta": delta,
                "effective_at": item.get("dataAssinatura") or item.get("dataVigenciaInicio"),
                "observed_at": item.get("dataPublicacaoPncp") or retrieved_at,
                "retrieved_at": retrieved_at,
                "verified_at": retrieved_at,
                "locator": {"json_path": f"$[{index}].tipoTermoContratoNome"},
                "extra": {"term_index": index, "raw_type": item.get("tipoTermoContratoNome")},
                "confidence_class": "explicit_structured_field",
            }
        )
    return records


def deepen_one_contract_terms(
    grouped: dict[str, list[OfficialContractObservation]],
    contract_id: str,
    *,
    cache_dir: Path | None,
    retrieved_at: str,
    artifact_budget: dict[str, int],
) -> dict[str, Any]:
    """Fetch /termos for one AEC candidate. Empty/404 is not_found/unavailable, never zero."""
    if artifact_budget["used"] >= artifact_budget["max"]:
        return {"contract_id": contract_id, "error_kind": "artifact_budget_exhausted", "recorded_as": "unavailable"}
    urls = pncp_contract_urls(contract_id)
    if not urls:
        return {"contract_id": contract_id, "error_kind": "contrato_id_unparseable", "recorded_as": "unavailable"}
    fetched = fetch_official(urls["termos"], cache_dir=cache_dir)
    artifact_budget["used"] += 1
    if fetched.ok and (fetched.status == 204 or not fetched.body):
        return {
            "contract_id": contract_id,
            "official_url": urls["termos"],
            "error_kind": "not_found",
            "message": "termos_http_204_or_empty",
            "recorded_as": "not_found",
        }
    if not fetched.ok or not fetched.body or not fetched.sha256:
        unav = fetched.unavailability
        payload = unav.as_dict() if unav is not None else {"error_kind": "unavailable"}
        payload["contract_id"] = contract_id
        payload["official_url"] = urls["termos"]
        payload.setdefault("recorded_as", "unavailable")
        return payload
    base = next((item for item in grouped.get(contract_id, []) if item.source_kind != "official_page"), None)
    records = termos_to_records(
        contract_id=contract_id,
        termos_url=urls["termos"],
        body=fetched.body,
        sha256=fetched.sha256,
        retrieved_at=retrieved_at,
        base=base,
    )
    if not records:
        return {
            "contract_id": contract_id,
            "official_url": urls["termos"],
            "error_kind": "not_found",
            "message": "termos_list_empty_or_untyped",
            "recorded_as": "not_found",
            "sha256": fetched.sha256,
        }
    extracted = extract_payload(records)
    grouped.setdefault(contract_id, []).extend(extracted.observations)
    return {
        "contract_id": contract_id,
        "official_url": urls["termos"],
        "error_kind": None,
        "term_count": len(extracted.observations),
        "sha256": fetched.sha256,
    }


def _fetch_bytes(url: str, *, cache_dir: Path | None) -> tuple[bytes | None, str | None, dict[str, Any] | None]:
    if cache_dir is not None:
        meta = cache_dir / f"{sha256_text(url)}.bin.json"
        blob = cache_dir / f"{sha256_text(url)}.bin"
        if meta.is_file() and blob.is_file():
            payload = json.loads(meta.read_text(encoding="utf-8"))
            return blob.read_bytes(), payload.get("sha256"), None
    import urllib.error
    import urllib.request

    request = urllib.request.Request(  # noqa: S310 — official https
        url, headers={"User-Agent": "ExtraConsultoria-official-contract-semantics/1.0", "Accept": "*/*"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            status = int(getattr(response, "status", 200) or 200)
            raw = response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, None, {"official_url": url, "error_kind": "unavailable", "message": str(exc)}
    if status >= 400:
        return None, None, {"official_url": url, "error_kind": "http_status", "http_status": status}
    digest = raw_record_hash_for(raw)
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / f"{sha256_text(url)}.bin").write_bytes(raw)
        (cache_dir / f"{sha256_text(url)}.bin.json").write_text(
            json.dumps({"url": url, "sha256": digest, "status": status}, sort_keys=True), encoding="utf-8"
        )
    return raw, digest, None


def pdf_clause_records(
    *,
    contract_id: str,
    pdf_url: str,
    raw: bytes,
    sha256: str,
    retrieved_at: str,
    base: OfficialContractObservation | None,
) -> list[dict[str, Any]]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return []
    import io

    try:
        reader = PdfReader(io.BytesIO(raw))
    except Exception:  # noqa: BLE001 — official PDF parse failure is not a world fact
        return []
    records: list[dict[str, Any]] = []
    material = ("reajuste", "reequilibr", "data do orçamento", "incc", "dnit", "sinapi", r"\bbdi\b")
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if not any(re.search(token, text, re.I) for token in material):
            continue
        records.append(
            {
                "source_system": "pncp",
                "source_kind": "process_document",
                "official_url": pdf_url,
                "source_document_id": f"{contract_id}:pdf:{index}",
                "source_document_sha256": sha256,
                "contract_identifier": contract_id,
                "contracting_entity_identifier": base.contracting_entity_identifier if base else None,
                "supplier_identifier": base.supplier_identifier if base else None,
                "object_text": text[:2400],
                "retrieved_at": retrieved_at,
                "verified_at": retrieved_at,
                "locator": {"page": index, "section": "contrato-oficial"},
                "confidence_class": "explicit_labeled_text",
                "extra": {"pdf_page": index, "pdf_pages": len(reader.pages)},
            }
        )
    return records


def deepen_one_contract_pdf(
    grouped: dict[str, list[OfficialContractObservation]],
    contract_id: str,
    *,
    cache_dir: Path | None,
    retrieved_at: str,
    artifact_budget: dict[str, int],
) -> dict[str, Any]:
    urls = pncp_contract_urls(contract_id)
    if not urls:
        return {"contract_id": contract_id, "error_kind": "contrato_id_unparseable", "recorded_as": "unavailable"}
    if artifact_budget["used"] >= artifact_budget["max"]:
        return {"contract_id": contract_id, "error_kind": "artifact_budget_exhausted", "recorded_as": "unavailable"}
    listing = fetch_official(urls["arquivos"], cache_dir=cache_dir)
    artifact_budget["used"] += 1
    if not listing.ok or not listing.body:
        return {
            "contract_id": contract_id,
            "official_url": urls["arquivos"],
            "error_kind": "not_found" if listing.ok else "unavailable",
            "recorded_as": "not_found" if listing.ok else "unavailable",
        }
    files = _json_items(listing.body)
    pdf_url = None
    for item in files:
        if not isinstance(item, dict):
            continue
        title = f"{item.get('tipoDocumentoNome') or ''} {item.get('titulo') or ''}".casefold()
        href = item.get("url") or item.get("uri")
        if href and ("contrato" in title or "pdf" in title):
            pdf_url = str(href)
            if "contrato" in title:
                break
    if not pdf_url:
        return {
            "contract_id": contract_id,
            "official_url": urls["arquivos"],
            "error_kind": "not_found",
            "message": "no_contrato_pdf_listed",
            "recorded_as": "not_found",
        }
    if artifact_budget["used"] >= artifact_budget["max"]:
        return {"contract_id": contract_id, "error_kind": "artifact_budget_exhausted", "recorded_as": "unavailable"}
    raw, digest, error = _fetch_bytes(pdf_url, cache_dir=cache_dir)
    artifact_budget["used"] += 1
    if error or not raw or not digest:
        return error or {"contract_id": contract_id, "official_url": pdf_url, "error_kind": "unavailable"}
    if raw[:4] != b"%PDF":
        return {"contract_id": contract_id, "official_url": pdf_url, "error_kind": "not_found", "recorded_as": "not_found"}
    base = next((item for item in grouped.get(contract_id, []) if item.source_kind != "official_page"), None)
    records = pdf_clause_records(
        contract_id=contract_id,
        pdf_url=pdf_url,
        raw=raw,
        sha256=digest,
        retrieved_at=retrieved_at,
        base=base,
    )
    if not records:
        return {
            "contract_id": contract_id,
            "official_url": pdf_url,
            "error_kind": "not_found",
            "message": "pdf_without_material_clause",
            "recorded_as": "not_found",
            "sha256": digest,
        }
    extracted = extract_payload(records)
    grouped.setdefault(contract_id, []).extend(extracted.observations)
    return {
        "contract_id": contract_id,
        "official_url": pdf_url,
        "error_kind": None,
        "pdf_pages": len(records),
        "sha256": digest,
    }


def _artifact(
    obs: OfficialContractObservation, *, retrieved_at: str | None, verified_at: str | None
) -> dict[str, Any] | None:
    if not obs.official_url or not obs.source_document_sha256:
        return None
    return {
        "evidence_id": obs.source_document_id or obs.observation_id,
        "url": obs.official_url,
        "sha256": obs.source_document_sha256,
        "mime": (
            "application/pdf"
            if (obs.official_url or "").lower().endswith(".pdf") or "/arquivos/" in (obs.official_url or "")
            else ("application/json" if obs.source_kind != "official_page" else "text/html")
        ),
        "locator": _locator_for(obs),
        "retrieved_at": retrieved_at,
        "verified_at": verified_at,
        "source_kind": obs.source_kind,
        "bytes_obtained": True,
    }


def dossier_from_group(
    contract_id: str,
    items: list[OfficialContractObservation],
    *,
    retrieved_at: str | None,
    verified_at: str | None,
    source_as_of: str | None,
    as_of: str,
    producer: dict[str, str],
    replay_command: str,
    query_window: dict[str, Any],
    bytes_obtained: bool,
    disposition: str,
    disposition_reason: str,
) -> dict[str, Any]:
    first = next((item for item in items if item.source_kind != "official_page"), items[0])
    artifacts = [
        item for item in (_artifact(obs, retrieved_at=retrieved_at, verified_at=verified_at) for obs in items) if item
    ]
    by_doc = {str(item["evidence_id"]): item for item in artifacts}
    facts, inferences, unknowns = _claims_from_observations(items, artifact_by_doc=by_doc)
    insight = _insight_for(items, facts)
    calculations = _calculations(items)
    sections = _analysis_sections(items, insight=insight, calculations=calculations)
    limitations = list(sections["limitations"])
    identity = {
        "analysis_id": contract_id,
        "contract_id": contract_id,
        "process_id": first.process_identifier,
        "orgao_cnpj": first.contracting_entity_identifier,
        "fornecedor_cnpj": first.supplier_identifier,
        "objeto": first.object_text,
        "uf": (first.extra or {}).get("uf"),
        "municipio": (first.extra or {}).get("municipio"),
        "source_system": first.source_system,
        "official_urls": sorted(
            {
                *(item.official_url for item in items if item.official_url),
                *((item.extra or {}).get("portal_url") for item in items if (item.extra or {}).get("portal_url")),
            }
        ),
        "evidence_urls": sorted(
            {item.official_url for item in items if item.official_url and item.source_kind != "official_page"}
        ),
        "event_effective_at": first.effective_at,
        "source_published_at": first.observed_at,
    }
    analysis_id = content_hash(
        {"schema": "official-live-authority-dossier/1.1", "contract_id": contract_id, "window": query_window}
    )[:32]
    payload = assemble_consumer_dossier(
        analysis_id=analysis_id,
        identity=identity,
        artifacts=artifacts,
        claims=facts,
        calculations=calculations,
        inferences=inferences,
        unknowns=unknowns,
        insight=insight,
        limitations=limitations,
        method="official-live-document-chain/1.1",
        producer_repo=producer["repo"],
        producer_commit=producer["commit"],
        replay_command=replay_command,
        query_window=query_window,
        retrieved_at=retrieved_at,
        verified_at=verified_at,
        source_as_of=source_as_of,
        event_effective_at=first.effective_at,
        source_published_at=first.observed_at,
        as_of=as_of,
        bytes_obtained=bytes_obtained and bool(artifacts),
        requested_mode="DOCUMENT_CHAIN",
        candidate_disposition=disposition,
        candidate_reason=disposition_reason,
    )
    payload["analysis"] = {
        **payload["analysis"],
        "what_documents_show": sections["what_documents_show"],
        "calculation_or_timeline": sections["calculation_or_timeline"],
        "worth_checking": sections["worth_checking"],
        "cannot_conclude": sections["cannot_conclude"],
        "sources": sections["sources"],
        "prohibited_conclusions": sections["cannot_conclude"],
    }
    payload["content_hash"] = content_hash(strip_temporal_for_hash({k: v for k, v in payload.items() if k != "content_hash"}))
    return payload


def _write_tree(root: Path, files: dict[str, str]) -> None:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = text if text.endswith("\n") else text + "\n"
        path.write_text(payload, encoding="utf-8")


def write_atomic_rendezvous(dest: Path, files: dict[str, str]) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / f".{dest.name}.tmp.{os.getpid()}"
    backup = dest.parent / f".{dest.name}.bak.{os.getpid()}"
    try:
        _write_tree(tmp, files)
        if dest.exists():
            if backup.exists():
                shutil.rmtree(backup)
            dest.rename(backup)
        tmp.rename(dest)
        if backup.exists():
            shutil.rmtree(backup)
    except Exception:
        if tmp.exists():
            shutil.rmtree(tmp)
        raise
    return dest


def _dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def build_rendezvous_files(
    dossiers: list[dict[str, Any]],
    *,
    producer: dict[str, str],
    generated_at: str,
    replay_command: str,
    query_window: dict[str, Any],
    live_meta: dict[str, Any],
    candidate_log: list[dict[str, str]],
    tests: list[str],
) -> dict[str, str]:
    ready = [item for item in dossiers if item.get("handoff_status") == "HANDOFF_READY"][:MAX_LIVE_READY]
    hold = [item for item in dossiers if item.get("handoff_status") != "HANDOFF_READY"]
    files: dict[str, str] = {}
    for item in (*ready, *hold):
        files[f"dossiers/{item['analysis_id']}.json"] = _dumps(item)
    manifest = {
        "schema": OFFICIAL_LIVE_HANDOFF_SCHEMA,
        "version": "1.1",
        "producer_repo": producer["repo"],
        "producer_branch": producer["branch"],
        "producer_commit": producer["commit"],
        "generated_at": generated_at,
        "query_window": query_window,
        "replay_command": replay_command,
        "consumer": CONSUMER_ID,
        "dossier_count": len(ready),
        "ids": [item["analysis_id"] for item in ready],
        "hold_ids": [item["analysis_id"] for item in hold],
        "candidate_log": candidate_log,
        "publication_authorization": False,
        "index_authorization": False,
        "commercial_relationship_claim": False,
        "production_write": False,
        "backfill": False,
        "live": live_meta,
        "content_hashes": {item["analysis_id"]: item.get("content_hash") for item in (*ready, *hold)},
    }
    manifest["content_hash"] = content_hash(strip_temporal_for_hash(manifest))
    files["manifest.json"] = _dumps(manifest)
    files["replay.txt"] = replay_command + "\n"
    if ready:
        ready_doc = {
            "schema": OFFICIAL_LIVE_HANDOFF_SCHEMA,
            "version": "1.1",
            "producer_repo": producer["repo"],
            "producer_branch": producer["branch"],
            "producer_commit": producer["commit"],
            "generated_at": generated_at,
            "dossier_count": len(ready),
            "ids": [item["analysis_id"] for item in ready],
            "manifest_sha256": sha256_text(files["manifest.json"]),
            "root_content_hash": content_hash(
                strip_temporal_for_hash(
                    {"ids": [item["analysis_id"] for item in ready], "hashes": manifest["content_hashes"]}
                )
            ),
            "status": "READY",
        }
        files["READY.json"] = _dumps(ready_doc)
        files["README.md"] = (
            "# official-live-01\n\n"
            f"status: READY\n"
            f"dossier_count: {len(ready)}\n"
            f"consumer: {CONSUMER_ID} / web-cfg#83\n"
            "publication_authorization: false\n"
            "index_authorization: false\n"
        )
    else:
        rejected = [item for item in candidate_log if item.get("disposition") != "entered"]
        entered = [item for item in candidate_log if item.get("disposition") == "entered"]
        next_step = live_meta.get("smallest_next_verifiable_step") or _default_next_step(
            candidate_log=candidate_log, live_meta=live_meta
        )
        blocked = {
            "schema": OFFICIAL_LIVE_HANDOFF_SCHEMA,
            "version": "1.1",
            "status": "BLOCKED",
            "producer_repo": producer["repo"],
            "producer_commit": producer["commit"],
            "generated_at": generated_at,
            "reason_codes": sorted(
                {code for item in dossiers for code in item.get("reason_codes") or []}
                or list(live_meta.get("reason_codes") or ["no_handoff_ready_dossier"])
            ),
            "sources_tried": live_meta.get("sources") or [],
            "availability": live_meta.get("unavailabilities") or live_meta.get("failures") or [],
            "tests": tests,
            "replay_command": replay_command,
            "ranking": candidate_log,
            "rejected": rejected,
            "entered": entered,
            "budget": live_meta.get("budget")
            or {
                "official_candidates": len(candidate_log),
                "primary_artifacts": live_meta.get("documents_obtained") or 0,
                "caps": {
                    "official_candidates": MAX_LIVE_CANDIDATES,
                    "primary_artifacts": MAX_PRIMARY_ARTIFACTS,
                },
            },
            "smallest_next_verifiable_step": next_step,
            "dossier_count": 0,
        }
        files["BLOCKED.json"] = _dumps(blocked)
        files["README.md"] = (
            "# official-live-01\n\n"
            "status: BLOCKED\n"
            "READY.json was not written.\n"
            f"reason_codes: {', '.join(blocked['reason_codes'])}\n"
        )
    sums = []
    for rel in sorted(name for name in files if name != "SHA256SUMS.txt"):
        sums.append(f"{sha256_bytes(files[rel].encode('utf-8'))}  {rel}")
    files["SHA256SUMS.txt"] = "\n".join(sums) + "\n"
    return files


def run_official_live_handoff(
    *,
    output: Path | None = None,
    dsn: str | None = None,
    limit: int = MAX_LIVE_CANDIDATES,
    start_date: str | None = None,
    end_date: str | None = None,
    cache_dir: Path | None = None,
    fetch_pages: bool = True,
    as_of: str | None = None,
    write_rendezvous: bool = True,
) -> dict[str, Any]:
    started = utc_now()
    stamp = as_of or started
    window_start, window_end = default_live_window(start=start_date, end=end_date, as_of=stamp)
    bounded = max(1, min(int(limit), MAX_LIVE_CANDIDATES))
    dest = output or rendezvous_dir()
    producer = git_identity()
    live = run_live_readonly(
        dsn=dsn,
        limit=bounded,
        out_dir=None,
        cache_dir=cache_dir,
        fetch_pages=fetch_pages,
        as_of=stamp,
        start_date=window_start,
        end_date=window_end,
        scan_limit=80,
        uf_filter="SC",
    )
    observations = [observation_from_mapping(row) for row in live.get("observations") or []]
    grouped = group_observations(observations)
    chosen, candidate_log = select_candidates(grouped, limit=bounded)
    sc_denominator = {
        "sc_scanned": len(grouped),
        "sc_aec_entered": len(chosen),
        "sc_exhausted": not chosen,
    }
    geography = "SC"
    if not chosen:
        national = run_live_readonly(
            dsn=dsn,
            limit=bounded,
            out_dir=None,
            cache_dir=cache_dir,
            fetch_pages=False,
            as_of=stamp,
            start_date=window_start,
            end_date=window_end,
            scan_limit=bounded,
            uf_filter=None,
            aec_only=True,
        )
        live.setdefault("sources", [])
        for source in national.get("sources") or []:
            if source not in live["sources"]:
                live["sources"].append(source)
        live.setdefault("unavailabilities", []).extend(national.get("unavailabilities") or [])
        live["documents_obtained"] = int(live.get("documents_obtained") or 0) + int(
            national.get("documents_obtained") or 0
        )
        national_obs = [observation_from_mapping(row) for row in national.get("observations") or []]
        national_grouped = group_observations(national_obs)
        national_chosen, national_log = select_candidates(national_grouped, limit=bounded)
        for item in national_log:
            item["geography"] = item.get("geography") or "BR"
        candidate_log.extend(
            [{**item, "reason": f"sc_exhausted:{item.get('reason')}"} for item in national_log]
        )
        if national_chosen:
            grouped.update(national_grouped)
            chosen = national_chosen
            geography = "BR"
            sc_denominator["national_fallback"] = True
            sc_denominator["national_aec_entered"] = len(national_chosen)
    listing_urls = {
        item.official_url
        for items in grouped.values()
        for item in items
        if item.official_url and item.source_kind != "official_page"
    }
    artifact_budget = {"used": len(listing_urls), "max": MAX_PRIMARY_ARTIFACTS}
    retrieved_at = live.get("finished_at") or started
    verified_at = retrieved_at
    query_window = {
        "start": window_start,
        "end": window_end,
        "uf": geography,
        "limit": bounded,
        "sc_denominator": sc_denominator,
    }
    replay = (
        "python3 -m scripts.historical_contract_authority --mode official-live "
        f"--limit {bounded} --start-date {window_start} --end-date {window_end} "
        "--as-of {as_of} --output <handoff-dir>".format(as_of=stamp)
    )
    deepen_log: list[dict[str, Any]] = []
    dossiers: list[dict[str, Any]] = []
    for contract_id in chosen:
        deepen_log.append(
            deepen_one_contract_terms(
                grouped,
                contract_id,
                cache_dir=cache_dir,
                retrieved_at=retrieved_at,
                artifact_budget=artifact_budget,
            )
        )
        deepen_log.append(
            deepen_one_contract_pdf(
                grouped,
                contract_id,
                cache_dir=cache_dir,
                retrieved_at=retrieved_at,
                artifact_budget=artifact_budget,
            )
        )
        items = grouped.get(contract_id) or []
        bytes_here = any(item.source_document_sha256 and item.official_url for item in items)
        disposition = next(
            (item for item in candidate_log if item.get("contract_id") == contract_id),
            {"disposition": "entered", "reason": "selected"},
        )
        dossier = dossier_from_group(
            contract_id,
            items,
            retrieved_at=retrieved_at if bytes_here else None,
            verified_at=verified_at if bytes_here else None,
            source_as_of=None,
            as_of=stamp,
            producer=producer,
            replay_command=replay,
            query_window=query_window,
            bytes_obtained=bytes_here,
            disposition=str(disposition.get("disposition") or "entered"),
            disposition_reason=str(disposition.get("reason") or ""),
        )
        dossiers.append(dossier)
        if dossier.get("handoff_status") == "HANDOFF_READY":
            break
    bytes_obtained = artifact_budget["used"] > 0
    live_meta = {
        "sources": live.get("sources") or [],
        "documents_considered": live.get("documents_considered"),
        "documents_obtained": artifact_budget["used"],
        "documents_failed": live.get("documents_failed"),
        "unavailabilities": live.get("unavailabilities") or [],
        "failures": live.get("failures") or [],
        "deepen": deepen_log,
        "reason_codes": [
            item.get("error_kind") for item in (live.get("unavailabilities") or []) if item.get("error_kind")
        ],
        "production_write": False,
        "backfill": False,
        "official_live": bytes_obtained,
        "dsn_present": bool(resolve_dsn(dsn)),
        "period": live.get("period"),
        "budget": {
            "datalake_batches": 1 if resolve_dsn(dsn) else 0,
            "official_candidates": len(chosen),
            "scanned": len(candidate_log),
            "primary_artifacts": artifact_budget["used"],
            "caps": {
                "datalake_batches": 3,
                "official_candidates": MAX_LIVE_CANDIDATES,
                "primary_artifacts": MAX_PRIMARY_ARTIFACTS,
            },
        },
        "smallest_next_verifiable_step": _default_next_step(candidate_log=candidate_log, live_meta={"deepen": deepen_log, "dsn_present": bool(resolve_dsn(dsn))}),
    }
    files = build_rendezvous_files(
        dossiers,
        producer=producer,
        generated_at=started,
        replay_command=replay,
        query_window=query_window,
        live_meta=live_meta,
        candidate_log=candidate_log,
        tests=["tests/historical_contract_authority/test_official_live_handoff.py"],
    )
    written = None
    if write_rendezvous:
        written = str(write_atomic_rendezvous(dest, files))
    ready = [item for item in dossiers if item.get("handoff_status") == "HANDOFF_READY"]
    return {
        "as_of": stamp,
        "output": written or str(dest),
        "files": files,
        "dossiers": dossiers,
        "ready": ready,
        "live": live_meta,
        "producer": producer,
        "replay_command": replay,
        "query_window": query_window,
        "status": "READY" if ready else "BLOCKED",
        "snapshot_records": [observation_to_snapshot_record(item) for item in observations],
        "live_manifest": {key: value for key, value in live.items() if key != "observations"},
    }


def _default_next_step(*, candidate_log: list[dict[str, str]], live_meta: dict[str, Any]) -> str:
    deepen = list(live_meta.get("deepen") or [])
    for item in deepen:
        url = item.get("official_url")
        if url and item.get("error_kind") in {"not_found", "unavailable", "http_status"}:
            return (
                f"Re-fetch and hash {url} "
                f"(recorded_as={item.get('recorded_as') or item.get('error_kind')}, "
                "empty/404 is not zero)."
            )
    aec_entered = [item for item in candidate_log if item.get("disposition") == "entered"]
    if aec_entered:
        urls = pncp_contract_urls(str(aec_entered[0].get("contract_id") or ""))
        if urls:
            return f"Fetch and hash {urls['termos']} for the first AEC shortlist contract."
    if not live_meta.get("dsn_present"):
        return (
            "LOCAL_DATALAKE_DSN read-only SELECT of SC AEC rows with editorial tokens "
            "(aditiv/reajuste/prorrog); public consulta window had no documentary singularity."
        )
    return "Fetch the next official /termos JSON for the first remaining AEC shortlist contract."


def same_consumer_shape(left: dict[str, Any], right: dict[str, Any]) -> bool:
    keys = (
        "schema",
        "analysis_id",
        "identity",
        "provenance",
        "factual_matrix",
        "analysis",
        "gates",
    )
    return all(key in left and key in right for key in keys)
