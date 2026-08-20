"""Build and write public-read-bofu-evidence/1.0 packs."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from scripts.bofu_evidence.claims import build_family_claims
from scripts.bofu_evidence.fixtures import load_comparable, load_national_coverage, load_snapshot
from scripts.bofu_evidence.gates import evaluate_gates
from scripts.bofu_evidence.hashutil import canonical_dumps, sha256_text, stamp_hash
from scripts.bofu_evidence.inputs import validate_comparable_input, validate_national_input
from scripts.bofu_evidence.models import (
    CONTRACT_PATH,
    CONTRACT_VERSION,
    FAMILIES,
    FAMILY_QUESTIONS,
    FRESHNESS_MAX_AGE_HOURS,
    PACK_VERSION,
    PROHIBITED_CLAIMS,
    SCHEMA,
    BofuInputError,
    pack_id_for,
    validate_pack,
)


def _resolve_as_of(
    snapshot: dict[str, Any],
    as_of: str | None,
    as_of_source: str | None,
) -> tuple[str, str]:
    if as_of_source == "wall_clock":
        return as_of or str(snapshot.get("as_of") or ""), "wall_clock"
    if as_of:
        return as_of, as_of_source or "cli"
    snapshot_as_of = snapshot.get("as_of")
    if snapshot_as_of:
        return str(snapshot_as_of), "snapshot"
    return "", "missing"


def _expires_for(snapshot: dict[str, Any], as_of: str) -> str:
    if snapshot.get("expires_at"):
        return str(snapshot["expires_at"])
    if snapshot.get("expires"):
        return str(snapshot["expires"])
    from scripts.bofu_evidence.gates import parse_iso

    return (parse_iso(as_of) + timedelta(hours=FRESHNESS_MAX_AGE_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _source_block(family: str, comparable_attached: bool, *, synthetic: bool) -> dict[str, Any]:
    refs = [
        "docs/contracts/national-coverage/national-coverage-v1.json",
    ]
    if comparable_attached:
        refs.append("docs/contracts/contract-comparables/comparable-contracts-v1.json")
    if synthetic:
        refs = [
            "scripts/bofu_evidence/fixtures/snapshot.json",
            "scripts/bofu_evidence/fixtures/pr437_national.json",
        ]
        if comparable_attached:
            refs.append("scripts/bofu_evidence/fixtures/pr435_comparable.json")
    return {
        "id": "bofu-evidence-frozen-snapshot" if synthetic else "bofu-evidence-versioned-inputs",
        "kind": "fixture" if synthetic else "versioned_public_contract",
        "family": family,
        "refs": refs,
        "synthetic": synthetic,
    }


def _method_block() -> dict[str, Any]:
    return {
        "id": "bofu-evidence-pack/1.0",
        "version": PACK_VERSION,
        "reproducible": True,
        "select_only": True,
        "backfill": False,
        "hash": "sha256-canonical-json-excluding-content_hash",
    }


def _coverage_block(national_coverage: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "scoped",
        "state": "partial",
        "national_verdict": national_coverage.get("verdict"),
        "national_claim_authorized": False,
        "denominator_pr": national_coverage.get("pr"),
        "complete_for_national": False,
        "reason_codes": list(national_coverage.get("reason_codes") or []),
    }


def _limitations(family: str, comparable_attached: bool) -> list[str]:
    lines = [
        "Recorte congelado; ausencia de documento nao e fato negativo.",
        "Denominador nacional PARTIAL (#437) bloqueia claim nacional.",
        "publication/index/national permanecem false inclusive em READY.",
    ]
    if comparable_attached:
        lines.append("Comparavel #435 entra so como BRL_TOTAL de paralelepipedo; nao e custo unitario.")
    else:
        lines.append(f"Comparavel #435 nao e pertinente a familia {family}.")
    return lines


def assemble_pack(
    *,
    family: str,
    snapshot: dict[str, Any],
    national_coverage: dict[str, Any],
    claims: list[dict[str, Any]],
    calculations: list[dict[str, Any]],
    comparable_attached: bool,
    as_of: str,
    expires: str,
    as_of_source: str,
    now: str,
    synthetic: bool = False,
) -> dict[str, Any]:
    draft = {
        "schema": SCHEMA,
        "pack_id": pack_id_for(family),
        "version": PACK_VERSION,
        "family": family,
        "question": FAMILY_QUESTIONS[family],
        "as_of": as_of,
        "expires": expires,
        "expires_at": expires,
        "as_of_source": as_of_source,
        "source": _source_block(family, comparable_attached, synthetic=synthetic),
        "method": _method_block(),
        "coverage": _coverage_block(national_coverage),
        "claims": claims,
        "calculations": calculations,
        "limitations": _limitations(family, comparable_attached),
        "prohibited_claims": list(PROHIBITED_CLAIMS),
        "comparable_attached": comparable_attached,
        "publication": False,
        "index": False,
        "national": False,
    }
    gate = evaluate_gates(
        draft,
        national_coverage=national_coverage,
        now=now,
        as_of_source=as_of_source,
    )
    draft["state"] = gate["state"]
    draft["reason_codes"] = gate["reason_codes"]
    draft["publication"] = False
    draft["index"] = False
    draft["national"] = False
    stamped = stamp_hash(draft)
    errors = validate_pack(stamped)
    if errors:
        raise ValueError(f"{stamped['pack_id']} invalid: {errors}")
    return stamped


def _load_inputs(
    *,
    snapshot: dict[str, Any] | None,
    comparable: dict[str, Any] | None,
    national_coverage: dict[str, Any] | None,
    synthetic: bool,
    now: str | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    if snapshot is None or national_coverage is None:
        if not synthetic:
            raise BofuInputError("missing_input")
        snap = snapshot if snapshot is not None else load_snapshot()
        cov = national_coverage if national_coverage is not None else load_national_coverage()
        peers = comparable if comparable is not None else load_comparable()
    else:
        snap = snapshot
        cov = national_coverage
        peers = comparable
    cov = validate_national_input(cov, synthetic=synthetic, now=now)
    if peers is not None:
        peers = validate_comparable_input(peers, synthetic=synthetic, now=now)
    return snap, cov, peers


def build_family_pack(
    family: str,
    *,
    snapshot: dict[str, Any] | None = None,
    comparable: dict[str, Any] | None = None,
    national_coverage: dict[str, Any] | None = None,
    as_of: str | None = None,
    now: str | None = None,
    as_of_source: str | None = None,
    force_comparable: bool = False,
    synthetic: bool = False,
) -> dict[str, Any]:
    snap, cov, peers = _load_inputs(
        snapshot=snapshot,
        comparable=comparable,
        national_coverage=national_coverage,
        synthetic=synthetic,
        now=now,
    )
    resolved_as_of, source = _resolve_as_of(snap, as_of, as_of_source)
    expires = _expires_for(snap, resolved_as_of) if resolved_as_of else ""
    evaluation_now = now or resolved_as_of
    attach_peers = peers if (force_comparable or family == "orcamento_bdi") else None
    claims, calculations, attached = build_family_claims(family, snap, attach_peers, synthetic=synthetic)
    if force_comparable:
        attached = True
    return assemble_pack(
        family=family,
        snapshot=snap,
        national_coverage=cov,
        claims=claims,
        calculations=calculations,
        comparable_attached=attached,
        as_of=resolved_as_of,
        expires=expires,
        as_of_source=source,
        now=evaluation_now,
        synthetic=synthetic,
    )


def build_packs(
    *,
    snapshot: dict[str, Any] | None = None,
    comparable: dict[str, Any] | None = None,
    national_coverage: dict[str, Any] | None = None,
    as_of: str | None = None,
    now: str | None = None,
    as_of_source: str | None = None,
    synthetic: bool = False,
) -> dict[str, Any]:
    snap, cov, peers = _load_inputs(
        snapshot=snapshot,
        comparable=comparable,
        national_coverage=national_coverage,
        synthetic=synthetic,
        now=now,
    )
    resolved_as_of, source = _resolve_as_of(snap, as_of, as_of_source)
    packs = [
        build_family_pack(
            family,
            snapshot=snap,
            comparable=peers,
            national_coverage=cov,
            as_of=resolved_as_of,
            now=now,
            as_of_source=source,
            synthetic=synthetic,
        )
        for family in FAMILIES
    ]
    hashes = {item["pack_id"]: item["content_hash"] for item in packs}
    manifest = stamp_hash(
        {
            "schema": SCHEMA,
            "contract_version": CONTRACT_VERSION,
            "contract_path": CONTRACT_PATH,
            "as_of": resolved_as_of,
            "pack_count": len(packs),
            "families": list(FAMILIES),
            "pack_ids": [item["pack_id"] for item in packs],
            "states": {item["family"]: item["state"] for item in packs},
            "hashes": hashes,
            "publication": False,
            "index": False,
            "national": False,
            "national_coverage": {
                "pr": cov.get("pr"),
                "verdict": cov.get("verdict"),
                "national_claim_authorized": False,
            },
        }
    )
    files: dict[str, str] = {
        "manifest.json": canonical_dumps(manifest) + "\n",
    }
    pack_files: dict[str, str] = {}
    for item in packs:
        pack_files[f"packs/{item['family']}.json"] = canonical_dumps(item) + "\n"
    checksum_rows = [(sha256_text(files["manifest.json"]), "manifest.json")]
    for name, body in sorted(pack_files.items()):
        checksum_rows.append((sha256_text(body), name))
        files[name] = body
    checksum_rows.sort(key=lambda row: row[1])
    sha_body = "".join(f"{digest}  {name}\n" for digest, name in checksum_rows)
    files["SHA256SUMS.txt"] = sha_body
    return {
        "schema": SCHEMA,
        "as_of": resolved_as_of,
        "manifest": manifest,
        "packs": packs,
        "files": files,
        "sha256sums": sha_body,
    }


def write_packs(bundle: dict[str, Any], output_dir: str | Path) -> Path:
    root = Path(output_dir)
    (root / "packs").mkdir(parents=True, exist_ok=True)
    for name, body in bundle["files"].items():
        dest = root / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body, encoding="utf-8")
    return root
