"""Bounded official-live acquisition and atomic consumer handoff."""

from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.historical_contract_authority.analysis import commercial_adjacency
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
from scripts.official_contract_semantics.live import (
    default_live_window,
    resolve_dsn,
    run_live_readonly,
)
from scripts.official_contract_semantics.models import OfficialContractObservation, observation_from_mapping

OFFICIAL_LIVE_HANDOFF_SCHEMA = "official-live-authority-handoff/1.1"
MAX_LIVE_CANDIDATES = 12
MAX_LIVE_READY = 3
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


def select_candidates(
    grouped: dict[str, list[OfficialContractObservation]],
    *,
    limit: int = MAX_LIVE_CANDIDATES,
) -> tuple[list[str], list[dict[str, str]]]:
    scored: list[tuple[int, str, str]] = []
    log: list[dict[str, str]] = []
    for contract_id, items in grouped.items():
        blob = " ".join(_object_text(item) for item in items)
        adjacency = commercial_adjacency(blob)
        page_bonus = (
            2 if any(item.source_kind == "official_page" and item.source_document_sha256 for item in items) else 0
        )
        fact_bonus = 1 if any(item.value_amount is not None or item.object_text for item in items) else 0
        if not contract_id:
            log.append({"contract_id": "", "disposition": "UNKNOWN", "reason": "missing_contract_identifier"})
            continue
        score = len(adjacency) * 3 + page_bonus + fact_bonus
        if not adjacency and not page_bonus:
            scored.append((score, contract_id, "entered_identity_only"))
        else:
            scored.append((score + 1, contract_id, "entered_adjacency_or_page"))
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
        artifact = artifact_by_doc.get(str(item.source_document_id or item.observation_id)) or {}
        url = item.official_url or artifact.get("url")
        digest = item.source_document_sha256 or artifact.get("sha256")
        locator = _locator_for(item)
        evidence_id = str(item.source_document_id or item.contract_identifier or item.observation_id)
        stable = str(item.contract_identifier or evidence_id).replace("/", "-")
        base = {
            "evidence_id": evidence_id,
            "url": url,
            "sha256": digest,
            "locator": locator,
            "source_refs": [evidence_id],
        }
        if item.object_text and url and digest and locator:
            facts.append(
                {
                    **base,
                    "claim_id": f"fact-object-{stable}",
                    "class": "FACT",
                    "text": f"Objeto oficial: {item.object_text[:240]}",
                    "locator": {"json_path": "$.objetoContrato"},
                }
            )
        if item.value_amount is not None and item.value_semantic:
            facts.append(
                {
                    **base,
                    "claim_id": f"fact-value-{stable}",
                    "class": "FACT",
                    "text": f"Valor {item.value_semantic} publicado: {format(item.value_amount, 'f')} {item.currency or 'BRL'}.",
                    "locator": {"json_path": "$.valorGlobal"},
                }
            )
        if item.period_start or item.period_end:
            facts.append(
                {
                    **base,
                    "claim_id": f"fact-period-{stable}",
                    "class": "FACT",
                    "text": f"Vigência oficial {item.period_start or 'UNKNOWN'} a {item.period_end or 'UNKNOWN'}.",
                    "locator": {"json_path": "$.dataVigenciaInicio"},
                }
            )
        if item.amendment_type:
            facts.append(
                {
                    **base,
                    "claim_id": f"fact-amendment-{stable}",
                    "class": "FACT",
                    "text": f"Fonte oficial registra tipo de aditivo: {item.amendment_type}.",
                }
            )
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


def _insight_for(items: list[OfficialContractObservation], facts: list[dict[str, Any]]) -> str:
    objects = [item.object_text for item in items if item.object_text]
    adjacency = commercial_adjacency(*objects, *(item.get("text") for item in facts))
    if not objects:
        return ""
    primary = objects[0]
    if "aditivo" in adjacency:
        return (
            f"A cadeia documental oficial descreve o contrato «{primary[:180]}» "
            "com menção a aditivo; o insight é a sequência documental, sem comparação."
        )
    if "reajuste" in adjacency or "reequilibrio" in adjacency:
        return (
            f"A fonte oficial descreve «{primary[:180]}» com adjacência de reajuste/reequilíbrio; "
            "não se afirma direito, desequilíbrio ou irregularidade."
        )
    if "prazo" in adjacency:
        return (
            f"A fonte oficial descreve «{primary[:180]}» com componente de prazo; "
            "a leitura é cronológica e não comparativa."
        )
    if "bdi" in adjacency or "defesa_margem" in adjacency:
        return (
            f"A fonte oficial descreve «{primary[:180]}» com adjacência de BDI/margem; "
            "não se infere sobrepreço nem irregularidade."
        )
    if "medicao_glosa" in adjacency:
        return (
            f"A fonte oficial descreve «{primary[:180]}» com adjacência de medição/glosa; "
            "não se afirma inadimplemento nem irregularidade."
        )
    return ""


def _artifact(
    obs: OfficialContractObservation, *, retrieved_at: str | None, verified_at: str | None
) -> dict[str, Any] | None:
    if not obs.official_url or not obs.source_document_sha256:
        return None
    return {
        "evidence_id": obs.source_document_id or obs.observation_id,
        "url": obs.official_url,
        "sha256": obs.source_document_sha256,
        "mime": "application/json" if obs.source_kind == "contract" else "text/html",
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
    first = items[0]
    artifacts = [
        item for item in (_artifact(obs, retrieved_at=retrieved_at, verified_at=verified_at) for obs in items) if item
    ]
    by_doc = {str(item["evidence_id"]): item for item in artifacts}
    facts, inferences, unknowns = _claims_from_observations(items, artifact_by_doc=by_doc)
    insight = _insight_for(items, facts)
    limitations = [
        "Sem comparação de pares: unidade, regime, escopo e período compatíveis não foram demonstrados.",
        "atípico nunca significa irregular.",
        "Campos sem evidência oficial permanecem UNKNOWN.",
    ]
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
        "official_urls": sorted({item.official_url for item in items if item.official_url}),
        "event_effective_at": first.effective_at,
        "source_published_at": first.observed_at,
    }
    analysis_id = content_hash(
        {"schema": "official-live-authority-dossier/1.1", "contract_id": contract_id, "window": query_window}
    )[:32]
    return assemble_consumer_dossier(
        analysis_id=analysis_id,
        identity=identity,
        artifacts=artifacts,
        claims=facts,
        calculations=[],
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
            "smallest_next_verifiable_step": (
                "Reverificar a mesma janela PNCP com documentos oficiais que tragam "
                "locator+hash e um insight singular sem linguagem comparativa."
            ),
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
    )
    observations = [observation_from_mapping(row) for row in live.get("observations") or []]
    grouped = group_observations(observations)
    chosen, candidate_log = select_candidates(grouped, limit=bounded)
    retrieved_at = live.get("finished_at") if live.get("documents_obtained") else None
    verified_at = retrieved_at
    bytes_obtained = int(live.get("documents_obtained") or 0) > 0
    query_window = {"start": window_start, "end": window_end, "uf": "SC", "limit": bounded}
    replay = (
        "python3 -m scripts.historical_contract_authority --mode official-live "
        f"--limit {bounded} --start-date {window_start} --end-date {window_end} "
        "--as-of {as_of} --output <handoff-dir>".format(as_of=stamp)
    )
    dossiers: list[dict[str, Any]] = []
    for contract_id in chosen:
        disposition = next(
            (item for item in candidate_log if item.get("contract_id") == contract_id),
            {"disposition": "entered", "reason": "selected"},
        )
        dossiers.append(
            dossier_from_group(
                contract_id,
                grouped[contract_id],
                retrieved_at=retrieved_at if bytes_obtained else None,
                verified_at=verified_at if bytes_obtained else None,
                source_as_of=None,
                as_of=stamp,
                producer=producer,
                replay_command=replay,
                query_window=query_window,
                bytes_obtained=bytes_obtained,
                disposition=str(disposition.get("disposition") or "entered"),
                disposition_reason=str(disposition.get("reason") or ""),
            )
        )
    live_meta = {
        "sources": live.get("sources") or [],
        "documents_considered": live.get("documents_considered"),
        "documents_obtained": live.get("documents_obtained"),
        "documents_failed": live.get("documents_failed"),
        "unavailabilities": live.get("unavailabilities") or [],
        "failures": live.get("failures") or [],
        "reason_codes": [
            item.get("error_kind") for item in (live.get("unavailabilities") or []) if item.get("error_kind")
        ],
        "production_write": False,
        "backfill": False,
        "official_live": bool(bytes_obtained and fetch_pages),
        "dsn_present": bool(resolve_dsn(dsn)),
        "period": live.get("period"),
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
