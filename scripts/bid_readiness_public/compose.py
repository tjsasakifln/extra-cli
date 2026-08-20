"""Compose four existing engines into a public-read-bid-readiness/1.0 envelope."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.bid_readiness_public.adapters import (
    AdapterBundle,
    run_acervo_adapter,
    run_bid_adapter,
    run_budget_adapter,
    run_edital_adapter,
)
from scripts.bid_readiness_public.clock import expires_at, iso, parse_clock
from scripts.bid_readiness_public.hashing import attach_hash, digest, sha256_file
from scripts.bid_readiness_public.ingest_guard import RejectedInputError, preflight_path
from scripts.bid_readiness_public.models import (
    DEFAULT_LIMITATIONS,
    DEFAULT_PROHIBITED_CLAIMS,
    HOLD_REASON_CODES,
    MODULES_REUSED,
    POLICY_VERSION,
    PRODUCER_VERSION,
    SCHEMA_VERSION,
    default_policy,
)
from scripts.bid_readiness_public.validators import refuse_envelope

DEFAULT_TTL_SECONDS = 86_400


def engine_versions() -> dict[str, str]:
    import scripts.bid_readiness as bid_readiness
    import scripts.budget_audit as budget_audit
    import scripts.edital_case as edital_case

    return {
        "edital_case": getattr(edital_case, "__version__", "0.1.0"),
        "budget_audit": getattr(budget_audit, "__version__", "0.1.0"),
        "bid_readiness": getattr(bid_readiness, "__version__", "0.1.0"),
        "technical_acervo": "0.1.0",
        "bid_readiness_public": PRODUCER_VERSION,
    }


def _dir_digest(path: Path) -> tuple[str, int]:
    rows: list[dict[str, Any]] = []
    total = 0
    for child in sorted(path.rglob("*")):
        if not child.is_file():
            continue
        size = child.stat().st_size
        total += size
        rows.append(
            {
                "rel": str(child.relative_to(path)),
                "sha256": sha256_file(child),
                "bytes": size,
            }
        )
    return digest(rows), total


def _file_entry(role: str, path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if resolved.is_file():
        return {
            "role": role,
            "filename": resolved.name,
            "sha256": sha256_file(resolved),
            "bytes": resolved.stat().st_size,
            "content_type": resolved.suffix.lower().lstrip(".") or "file",
            "present": True,
        }
    digest_hex, total = _dir_digest(resolved)
    return {
        "role": role,
        "filename": resolved.name,
        "sha256": digest_hex,
        "bytes": total,
        "content_type": "directory",
        "present": True,
    }


def build_input_manifest(
    *,
    edital: Path | None,
    planilha: Path | None,
    documents: Path | None,
    acervo: Path | None,
    requirements: Path | None,
) -> dict[str, Any]:
    inputs: list[dict[str, Any]] = []
    for role, path in (
        ("edital", edital),
        ("planilha", planilha),
        ("documents", documents),
        ("acervo", acervo),
        ("requirements", requirements),
    ):
        if path is not None and Path(path).exists():
            inputs.append(_file_entry(role, Path(path)))
        else:
            inputs.append(
                {
                    "role": role,
                    "filename": None,
                    "sha256": None,
                    "bytes": 0,
                    "content_type": None,
                    "present": False,
                }
            )
    return {"inputs": inputs, "content_included": False}


def _query_id(manifest: dict[str, Any], policy: dict[str, Any], as_of: str) -> str:
    return (
        "prbr1-"
        + digest(
            {
                "schema": SCHEMA_VERSION,
                "manifest": manifest,
                "policy_version": policy.get("policy_version") or POLICY_VERSION,
                "allow_llm": bool(policy.get("allow_llm")),
                "as_of": as_of,
            }
        )[:16]
    )


def _overall_state(
    *,
    rejected: list[str],
    bundles: list[AdapterBundle],
) -> tuple[str, list[str]]:
    if rejected:
        return "REJECT", rejected
    codes: list[str] = []
    for bundle in bundles:
        codes.extend(bundle.reason_codes)
        codes.extend(bundle.blockers)
    hold = [code for code in codes if code in HOLD_REASON_CODES]
    if hold:
        return "HOLD_FOR_DATA", sorted(set(hold))
    return "READY_FOR_HUMAN_REVIEW", sorted(set(codes))


def _summary(bundles: list[AdapterBundle]) -> dict[str, Any]:
    covered: list[str] = []
    missing: list[str] = []
    conflicts: list[str] = []
    unevaluated: list[str] = []
    blockers: list[str] = []
    for bundle in bundles:
        covered.extend(bundle.covered)
        missing.extend(bundle.missing)
        conflicts.extend(bundle.conflicts)
        unevaluated.extend(bundle.unevaluated)
        blockers.extend(bundle.blockers)
    finding_count = sum(len(bundle.findings) for bundle in bundles)
    return {
        "covered_items": covered,
        "missing_items": missing,
        "conflicts": conflicts,
        "unevaluated": unevaluated,
        "blockers": blockers,
        "human_next_steps": [
            "Review UNKNOWN items and supply missing local files when applicable.",
            "Review RISK items against the cited method and locator.",
            "Do not treat this envelope as authorization to submit, publish, or index.",
        ],
        "observable_review": {
            "finding_count": finding_count,
            "module_count": len(MODULES_REUSED),
            "estimated_review_minutes_per_finding": 3,
            "estimated_review_minutes": finding_count * 3,
        },
    }


def load_authorized_manifest(path: Path) -> dict[str, Path | None]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RejectedInputError("unauthorized_manifest", "manifest must be an object")
    payload = raw
    if payload.get("authorized") is not True:
        raise RejectedInputError("unauthorized_manifest", "manifest is not authorized")
    base = Path(path).resolve().parent
    roles: dict[str, Path | None] = {
        "edital": None,
        "planilha": None,
        "documents": None,
        "acervo": None,
        "requirements": None,
    }
    for entry in payload.get("files") or payload.get("inputs") or []:
        role = str(entry.get("role") or "")
        rel = entry.get("path") or entry.get("file")
        if role not in roles or not rel:
            continue
        candidate = (base / str(rel)).resolve()
        if not str(candidate).startswith(str(base)):
            raise RejectedInputError("manifest_path_escape", f"manifest path escapes base: {rel}")
        roles[role] = candidate
    return roles


def produce(
    *,
    edital: Path | None = None,
    planilha: Path | None = None,
    documents: Path | None = None,
    acervo: Path | None = None,
    requirements: Path | None = None,
    work_dir: Path,
    clock: datetime | str | None = None,
    policy: dict[str, Any] | None = None,
    engines_available: dict[str, bool] | None = None,
    source_access: str = "private_local",
    entity: dict[str, Any] | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    acervo_service: str = "pavimentacao asfaltica",
    acervo_quantity: float | None = 100.0,
    acervo_unit: str = "m2",
) -> dict[str, Any]:
    """Run preflight + four adapters and return a hashed private envelope."""
    moment = parse_clock(clock)
    as_of = iso(moment)
    generated = as_of
    expires = iso(expires_at(moment, ttl_seconds))
    active_policy = {**default_policy(), **(policy or {})}
    available = {
        "edital_case": True,
        "budget_audit": True,
        "technical_acervo": True,
        "bid_readiness": True,
        **(engines_available or {}),
    }
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    rejected: list[str] = []
    reject_messages: list[str] = []
    for path in (edital, planilha, documents, acervo, requirements):
        if path is None:
            continue
        try:
            preflight_path(Path(path))
        except RejectedInputError as exc:
            rejected.append(exc.reason_code)
            reject_messages.append(str(exc))

    bundles: list[AdapterBundle] = []
    if not rejected:
        bundles = [
            run_edital_adapter(edital, available=available["edital_case"]),
            run_budget_adapter(planilha, available=available["budget_audit"]),
            run_acervo_adapter(
                acervo,
                available=available["technical_acervo"],
                service=acervo_service,
                quantity=acervo_quantity,
                unit=acervo_unit,
            ),
            run_bid_adapter(
                documents,
                requirements,
                available=available["bid_readiness"],
                work_dir=work_dir,
                entity=entity,
                reference_date=as_of[:10],
            ),
        ]
    else:
        from scripts.bid_readiness_public.adapters import make_finding
        from scripts.bid_readiness_public.hashing import sha256_text

        bundles = [
            AdapterBundle(
                module="ingest_guard",
                available=True,
                findings=[
                    make_finding(
                        finding_id="IN-REJ-001",
                        requirement_id=None,
                        category="ingest",
                        state="UNKNOWN",
                        statement=(
                            "Input refused before parse: " + "; ".join(reject_messages) + ". No engine parser ran."
                        ),
                        source_document_id="ingest_guard",
                        locator={"section": "preflight"},
                        evidence_hash=sha256_text("|".join(rejected)),
                        evidence_ref="ingest_guard.preflight_path",
                        confidence=1.0,
                        coverage={"evaluated": 0, "denominator": 1, "ratio": 0.0},
                        reason_codes=rejected,
                        method="scripts.bid_readiness.ingest + scripts.budget_audit.zip_safety",
                    )
                ],
                reason_codes=rejected,
                blockers=rejected,
                unevaluated=list(MODULES_REUSED),
            )
        ]

    overall, reason_codes = _overall_state(rejected=rejected, bundles=bundles)
    findings = [finding for bundle in bundles for finding in bundle.findings]
    manifest = build_input_manifest(
        edital=edital,
        planilha=planilha,
        documents=documents,
        acervo=acervo,
        requirements=requirements,
    )
    query_id = _query_id(manifest, active_policy, as_of)
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "run_id": query_id,
        "query_id": query_id,
        "generated_at": generated,
        "as_of": as_of,
        "expires_at": expires,
        "input_manifest": manifest,
        "engine_versions": engine_versions(),
        "policy_version": active_policy.get("policy_version") or POLICY_VERSION,
        "source_access": source_access,
        "overall_state": overall,
        "human_review_required": True,
        "not_legal_conclusion": True,
        "publication_authorization": False,
        "index_authorization": False,
        "limitations": list(DEFAULT_LIMITATIONS),
        "prohibited_claims": list(DEFAULT_PROHIBITED_CLAIMS),
        "findings": findings,
        "summary": _summary(bundles),
        "reason_codes": reason_codes,
        "producer_version": PRODUCER_VERSION,
        "modules_reused": list(MODULES_REUSED),
        "policy": {
            "policy_version": active_policy.get("policy_version") or POLICY_VERSION,
            "allow_llm": bool(active_policy.get("allow_llm")),
            "deterministic": True,
        },
    }
    hashed = attach_hash(envelope)
    refuse_envelope(hashed)
    return hashed
