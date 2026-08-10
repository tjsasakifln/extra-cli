"""National process-first harvest over live TARGET_CONFIRMED (no Top-N capacity).

Loads CONFIRMED roots from target-fit SHADOW/current, runs ProcessFirstEnricher
with checkpoint/resume, and writes:
  - per-account JSON results
  - public_docs.jsonl consumable by contact-resolution PublicDocsAdapter
  - contact candidates jsonl (observed emails only; no pattern guess as send-ready)
  - terminal discovery states for every processed CONFIRMED

``max_companies`` is smoke-only. Omit for full national population.
Never treat 50 as capacity.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.confenge_activation.operational_metrics import (
    PILOT_ACCEPTANCE_SAMPLE,
    assert_not_pilot_as_capacity,
)
from scripts.confenge_contact_resolution.discovery_state import (
    CONTACT_EXHAUSTED,
    CONTACT_EXTERNAL_BLOCKER,
    CONTACT_FOUND_NOT_SENDABLE,
    CONTACT_READY,
    CONTACT_RETRY_PENDING,
    classify_contact_terminal,
    measure_terminal_coverage,
)
from scripts.confenge_process_enrichment.models import TerminalState
from scripts.confenge_process_enrichment.pipeline import ProcessFirstConfig, ProcessFirstEnricher
from scripts.confenge_target_fit import MODE_SHADOW, TARGET_CONFIRMED
from scripts.confenge_target_fit.db import connect
from scripts.confenge_target_fit.store import get_control

logger = logging.getLogger(__name__)

DEFAULT_OUT = Path("artifacts/confenge/process-first-national-confirmed")


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_cnpj14(root: str, result: Any) -> str:
    """Best-effort 14-digit CNPJ from harvest result contracts; else root stub."""
    root = "".join(c for c in root if c.isdigit())[:8]
    graph = getattr(result, "process_graph", None)
    contracts = list(getattr(graph, "contracts", None) or [])
    for c in contracts:
        raw = getattr(c, "supplier_cnpj", None) or ""
        digits = "".join(ch for ch in str(raw) if ch.isdigit())
        if len(digits) >= 14 and digits[:8] == root:
            return digits[:14]
        if len(digits) == 8 and digits == root:
            continue
    return root + "000100"


@dataclass
class NationalHarvestConfig:
    output_dir: Path = field(default_factory=lambda: DEFAULT_OUT)
    max_companies: int | None = None
    allow_network: bool = True
    max_contracts: int = 8
    max_docs_per_contract: int = 4
    max_docs_fetch: int = 6
    resume: bool = True
    dsn: str | None = None
    politeness_seconds: float = 0.15


def load_confirmed_roots(dsn: str) -> list[dict[str, Any]]:
    """Load TARGET_CONFIRMED company roots from live materialization."""
    conn = connect(dsn, readonly=True)
    try:
        mode_ctrl = get_control(conn, "async_mode")
        mode = str(mode_ctrl.get("mode") or MODE_SHADOW).upper()
        with conn.cursor() as cur:
            if mode == MODE_SHADOW:
                cur.execute(
                    """
                    SELECT company_key, cnpj_raiz, shadow_class AS target_fit_class,
                           shadow_confidence AS conf
                    FROM confenge_target_fit_shadow
                    WHERE shadow_class = %s
                    ORDER BY shadow_confidence DESC NULLS LAST, cnpj_raiz
                    """,
                    (TARGET_CONFIRMED,),
                )
            else:
                cur.execute(
                    """
                    SELECT company_key, cnpj_raiz, target_fit_class,
                           target_fit_confidence AS conf
                    FROM confenge_company_target_fit_current
                    WHERE target_fit_class = %s
                    ORDER BY target_fit_confidence DESC NULLS LAST, cnpj_raiz
                    """,
                    (TARGET_CONFIRMED,),
                )
            return [dict(r) for r in (cur.fetchall() or [])]
    finally:
        conn.close()


def _load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"completed_roots": [], "updated_at": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"completed_roots": [], "updated_at": None}


def _save_checkpoint(path: Path, completed: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "completed_roots": sorted(completed),
                "updated_at": _utcnow(),
                "count": len(completed),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _result_to_public_docs(result: Any) -> list[dict[str, Any]]:
    """Convert enrichment contact graph into public_docs adapter rows."""
    docs: list[dict[str, Any]] = []
    graph = getattr(result, "contact_graph", None)
    if graph is None and hasattr(result, "to_dict"):
        payload = result.to_dict() or {}
        cg = payload.get("contact_graph") or {}
        # dict form from to_dict
        for person in cg.get("people") or []:
            for email in person.get("emails") or []:
                docs.append(
                    {
                        "email": email,
                        "phone": (person.get("phones") or [None])[0],
                        "name": person.get("name"),
                        "cargo": (person.get("roles") or [None])[0],
                        "url": person.get("source_url"),
                        "source_url": person.get("source_url"),
                        "document_id": person.get("source_document_id"),
                        "document": person.get("source_document_id"),
                        "doc_type": "process_administrative",
                        "pattern_guessed_email": False,
                        "epistemic_class": person.get("epistemic_best"),
                        "source_type": "public_process_document",
                    }
                )
        for mbox in cg.get("functional_mailboxes") or []:
            if mbox.get("email"):
                docs.append(
                    {
                        "email": mbox.get("email"),
                        "phone": mbox.get("phone"),
                        "name": None,
                        "cargo": mbox.get("role_observed"),
                        "url": mbox.get("source_url"),
                        "source_url": mbox.get("source_url"),
                        "document_id": mbox.get("source_document_id"),
                        "document": mbox.get("source_document_id"),
                        "doc_type": "process_administrative",
                        "pattern_guessed_email": False,
                        "epistemic_class": mbox.get("epistemic_class"),
                        "source_type": "public_process_document",
                    }
                )
        return docs

    if graph is None:
        return docs

    for person in getattr(graph, "people", None) or []:
        emails = list(getattr(person, "emails", None) or [])
        phones = list(getattr(person, "phones", None) or [])
        roles = list(getattr(person, "roles", None) or [])
        for email in emails:
            docs.append(
                {
                    "email": email,
                    "phone": phones[0] if phones else None,
                    "name": getattr(person, "name", None),
                    "cargo": roles[0] if roles else None,
                    "url": getattr(person, "source_url", None),
                    "source_url": getattr(person, "source_url", None),
                    "document_id": getattr(person, "source_document_id", None),
                    "document": getattr(person, "source_document_id", None),
                    "doc_type": "process_administrative",
                    "pattern_guessed_email": False,
                    "epistemic_class": str(
                        getattr(person, "epistemic_best", None)
                        or getattr(person, "epistemic_class", "")
                        or ""
                    ),
                    "source_type": "public_process_document",
                }
            )
    for mbox in getattr(graph, "functional_mailboxes", None) or []:
        email = getattr(mbox, "email", None)
        if not email:
            continue
        docs.append(
            {
                "email": email,
                "phone": getattr(mbox, "phone", None),
                "name": None,
                "cargo": getattr(mbox, "role_observed", None),
                "url": getattr(mbox, "source_url", None),
                "source_url": getattr(mbox, "source_url", None),
                "document_id": getattr(mbox, "source_document_id", None),
                "document": getattr(mbox, "source_document_id", None),
                "doc_type": "process_administrative",
                "pattern_guessed_email": False,
                "epistemic_class": str(getattr(mbox, "epistemic_class", "") or ""),
                "source_type": "public_process_document",
            }
        )
    # Raw observations as fallback
    for obs in getattr(graph, "observations", None) or []:
        email = getattr(obs, "email", None)
        if not email or bool(getattr(obs, "pattern_guessed", False)):
            continue
        docs.append(
            {
                "email": email,
                "phone": getattr(obs, "phone", None) or getattr(obs, "phone_raw", None),
                "name": getattr(obs, "person_name", None),
                "cargo": getattr(obs, "role_observed", None),
                "url": getattr(obs, "source_url", None),
                "source_url": getattr(obs, "source_url", None),
                "document_id": getattr(obs, "source_document_id", None),
                "document": getattr(obs, "source_document_id", None),
                "doc_type": "process_administrative",
                "pattern_guessed_email": False,
                "epistemic_class": str(getattr(obs, "epistemic_class", "") or ""),
                "source_type": "public_process_document",
            }
        )
    return docs


def _terminal_from_process_result(result: Any) -> str:
    term = result.terminal_state if hasattr(result, "terminal_state") else None
    if term is None and hasattr(result, "to_dict"):
        term = (result.to_dict() or {}).get("terminal_state")
    val = term.value if hasattr(term, "value") else str(term or "")
    if val in {
        TerminalState.EMAIL_SEND_READY.value,
        TerminalState.CONTACT_FOUND_VERIFIED.value,
    }:
        return CONTACT_READY
    if val in {
        TerminalState.CONTACT_FOUND_UNVERIFIED.value,
        TerminalState.REFERRAL_ROUTE_AVAILABLE.value,
    }:
        return CONTACT_FOUND_NOT_SENDABLE
    if val in {
        TerminalState.CAPTCHA_BLOCKED.value,
        TerminalState.AUTH_REQUIRED.value,
        TerminalState.SOURCE_REQUIRES_HUMAN_ACCESS.value,
        TerminalState.SOURCE_NOT_PUBLIC.value,
        TerminalState.SOURCE_BLOCKED.value,
    }:
        return CONTACT_EXTERNAL_BLOCKER
    if val in {
        TerminalState.NO_CONTACT_FOUND.value,
        TerminalState.DOCUMENTS_PARSED_NO_CONTACT.value,
        TerminalState.PARSED_NO_CONTACT.value,
        TerminalState.PROCESS_NOT_FOUND.value,
        TerminalState.DOCUMENTS_NOT_AVAILABLE.value,
    }:
        return CONTACT_EXHAUSTED
    return CONTACT_RETRY_PENDING


def run_national_process_harvest(
    dsn: str,
    *,
    cfg: NationalHarvestConfig | None = None,
) -> dict[str, Any]:
    """Harvest process-first contacts for all TARGET_CONFIRMED (resumable)."""
    cfg = cfg or NationalHarvestConfig()
    if cfg.max_companies == PILOT_ACCEPTANCE_SAMPLE:
        raise ValueError(
            f"Refuse max_companies={PILOT_ACCEPTANCE_SAMPLE}: pilot sample only, "
            "not national harvest capacity."
        )
    assert_not_pilot_as_capacity(cfg.max_companies, context="national-process-harvest")

    out = Path(cfg.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    accounts_dir = out / "accounts"
    accounts_dir.mkdir(exist_ok=True)
    ckpt_path = out / "checkpoint.json"
    public_docs_path = out / "public_docs.jsonl"
    candidates_path = out / "contact-candidates.jsonl"
    terminals_path = out / "contact-discovery-terminals.jsonl"

    roots = load_confirmed_roots(dsn)
    confirmed_keys = [str(r.get("cnpj_raiz") or "") for r in roots if r.get("cnpj_raiz")]
    completed: set[str] = set()
    if cfg.resume:
        completed = set(_load_checkpoint(ckpt_path).get("completed_roots") or [])

    enricher = ProcessFirstEnricher(
        config=ProcessFirstConfig(
            allow_network=cfg.allow_network,
            max_contracts=cfg.max_contracts,
            max_docs_per_contract=cfg.max_docs_per_contract,
            max_docs_fetch=cfg.max_docs_fetch,
            dsn=dsn,
            registry_path=str(out / "process_source_registry.json"),
            stop_on_high_confidence_email=True,
        )
    )
    # Enable downloads when network allowed
    if cfg.allow_network:
        import requests

        session = requests.Session()
        session.headers.setdefault("User-Agent", "extra-cli-confenge-process-national/1.0")

        def _download(url: str) -> bytes | None:
            try:
                resp = session.get(url, timeout=(15, 90))
                if resp.status_code == 200 and resp.content:
                    return resp.content
            except Exception:  # noqa: BLE001
                return None
            return None

        enricher.download_fn = _download
        if enricher.harvester is not None:
            enricher.harvester.download = True

    processed = 0
    emails_found = 0
    send_ready_proxy = 0
    terminals: list[dict[str, Any]] = []
    yield_by_source: dict[str, dict[str, int]] = {
        "pncp_annexes": {"companies_attempted": 0, "contacts_found": 0, "send_ready_found": 0},
        "process_administrative_docs": {
            "companies_attempted": 0,
            "contacts_found": 0,
            "send_ready_found": 0,
        },
    }

    # Append-mode for resume
    docs_mode = "a" if cfg.resume and public_docs_path.is_file() else "w"
    cand_mode = "a" if cfg.resume and candidates_path.is_file() else "w"

    with (
        public_docs_path.open(docs_mode, encoding="utf-8") as docs_fh,
        candidates_path.open(cand_mode, encoding="utf-8") as cand_fh,
    ):
        for row in roots:
            root = str(row.get("cnpj_raiz") or "").strip()
            if len(root) != 8 or not root.isdigit():
                continue
            if root in completed:
                continue
            if cfg.max_companies is not None and processed >= cfg.max_companies:
                break

            # Pass root-padded key; load_contracts_for_supplier matches by root8.
            cnpj14 = root + "000100"
            try:
                t0 = time.time()
                result = enricher.enrich(
                    account_cnpj=root,  # root is enough for root-based contract lookup
                    razao_social=None,
                )
                cnpj14 = normalize_cnpj14(root, result)
            except Exception as exc:  # noqa: BLE001
                logger.warning("harvest failed root=%s err=%s", root, exc)
                st = classify_contact_terminal(
                    cnpj_raiz=root,
                    sources_attempted=["process_administrative_docs", "pncp_annexes"],
                    network_discovery=bool(cfg.allow_network),
                    ladder_complete=False,
                    retryable_error=True,
                    attempt_count=1,
                    meta={"error": f"{type(exc).__name__}: {exc}"},
                )
                terminals.append(st.as_dict())
                completed.add(root)
                processed += 1
                continue

            # Persist account result
            payload = result.to_dict() if hasattr(result, "to_dict") else {}
            (accounts_dir / f"{root}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
                encoding="utf-8",
            )

            pub_docs = _result_to_public_docs(result)
            for d in pub_docs:
                d["cnpj_raiz"] = root
                d["cnpj14"] = cnpj14
                docs_fh.write(json.dumps(d, ensure_ascii=False, default=str) + "\n")
                if d.get("email") and not d.get("pattern_guessed_email"):
                    emails_found += 1
                    cand_fh.write(
                        json.dumps(
                            {
                                "cnpj_raiz": root,
                                "cnpj14": cnpj14,
                                "email": d["email"],
                                "source_type": "public_process_document",
                                "source_url": d.get("source_url"),
                                "source_document": d.get("document_id"),
                                "ownership_status": "COMPANY_OWNED"
                                if "COMPANY" in str(d.get("epistemic_class") or "").upper()
                                else "UNRESOLVED",
                                "pattern_guessed": False,
                                "email_send_ready": False,  # evaluate later via send_readiness
                                "mailbox_purpose": None,
                                "provenance_chain_valid": True,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )

            term = _terminal_from_process_result(result)
            # Count process path as attempted when network harvest ran
            sources = ["process_administrative_docs", "pncp_annexes"]
            yield_by_source["process_administrative_docs"]["companies_attempted"] += 1
            yield_by_source["pncp_annexes"]["companies_attempted"] += 1
            n_email = sum(1 for d in pub_docs if d.get("email") and not d.get("pattern_guessed_email"))
            if n_email:
                yield_by_source["process_administrative_docs"]["contacts_found"] += 1
                yield_by_source["pncp_annexes"]["contacts_found"] += 1
            if term == CONTACT_READY:
                send_ready_proxy += 1
                yield_by_source["process_administrative_docs"]["send_ready_found"] += 1

            st = classify_contact_terminal(
                cnpj_raiz=root,
                sources_attempted=sources,
                network_discovery=bool(cfg.allow_network),
                ladder_complete=term
                in {CONTACT_READY, CONTACT_FOUND_NOT_SENDABLE, CONTACT_EXHAUSTED, CONTACT_EXTERNAL_BLOCKER},
                email_candidates=n_email,
                email_send_ready=1 if term == CONTACT_READY else 0,
                external_blocker="captcha_or_auth"
                if term == CONTACT_EXTERNAL_BLOCKER
                else None,
                attempt_count=1,
                meta={
                    "process_terminal": term,
                    "elapsed_s": round(time.time() - t0, 3),
                },
            )
            # Prefer process-derived terminal label when ladder complete
            if term in {
                CONTACT_READY,
                CONTACT_FOUND_NOT_SENDABLE,
                CONTACT_EXHAUSTED,
                CONTACT_EXTERNAL_BLOCKER,
            }:
                st.terminal_state = term
            terminals.append(st.as_dict())

            completed.add(root)
            processed += 1
            if processed % 25 == 0:
                _save_checkpoint(ckpt_path, completed)
                logger.info(
                    "national process harvest processed=%s completed=%s emails=%s",
                    processed,
                    len(completed),
                    emails_found,
                )
            if cfg.politeness_seconds > 0:
                time.sleep(cfg.politeness_seconds)

    _save_checkpoint(ckpt_path, completed)

    # Terminal coverage for all CONFIRMED (attempted = completed this/prior runs)
    terminal_cov = measure_terminal_coverage(
        terminals if terminals else [],
        target_confirmed_total=len(confirmed_keys),
    )
    # Merge prior terminals if present
    prior_terminals: list[dict[str, Any]] = []
    if terminals_path.is_file() and cfg.resume:
        for line in terminals_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    prior_terminals.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    # Dedup by root preferring latest
    by_root: dict[str, dict[str, Any]] = {str(t.get("cnpj_raiz")): t for t in prior_terminals}
    for t in terminals:
        by_root[str(t.get("cnpj_raiz"))] = t
    merged = list(by_root.values())
    with terminals_path.open("w", encoding="utf-8") as fh:
        for t in merged:
            fh.write(json.dumps(t, ensure_ascii=False) + "\n")
    terminal_cov = measure_terminal_coverage(merged, target_confirmed_total=len(confirmed_keys))

    report = {
        "schema": "confenge.national_process_harvest.v1",
        "as_of": _utcnow(),
        "TARGET_CONFIRMED_total": len(confirmed_keys),
        "processed_this_run": processed,
        "completed_total": len(completed),
        "emails_observed": emails_found,
        "contact_ready_proxy": send_ready_proxy,
        "allow_network": cfg.allow_network,
        "max_companies_bound": cfg.max_companies,
        "output_dir": str(out),
        "public_docs_path": str(public_docs_path),
        "candidates_path": str(candidates_path),
        "terminals_path": str(terminals_path),
        "contact_terminal_coverage": terminal_cov,
        "source_yield": yield_by_source,
        "note": (
            "Process-first harvest over TARGET_CONFIRMED. "
            f"PILOT_ACCEPTANCE_SAMPLE={PILOT_ACCEPTANCE_SAMPLE} is quality-only. "
            "Emails are OBSERVED only; ESR requires evaluate_email_send_ready."
        ),
    }
    (out / "national-harvest-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    return report
