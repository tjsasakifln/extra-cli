"""Full case pipeline: create → ingest → match → validate → package → report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.bid_readiness.classify import classify_document
from scripts.bid_readiness.extract import extract_metadata, extract_text_from_bytes, field_value
from scripts.bid_readiness.findings import (
    build_findings,
    derive_package_status,
    derive_system_status,
)
from scripts.bid_readiness.identity import evaluate_identity
from scripts.bid_readiness.ingest import ingest_path
from scripts.bid_readiness.match import match_requirement_to_documents
from scripts.bid_readiness.package import assemble_package
from scripts.bid_readiness.reports import build_report_model, write_reports
from scripts.bid_readiness.requirements_loader import load_requirements
from scripts.bid_readiness.sanitize import sanitize_obj
from scripts.bid_readiness.validity import evaluate_validity
from scripts.bid_readiness.vault import read_object, write_inventory


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def create_case(
    case_dir: Path,
    *,
    case_id: str,
    requirements_path: Path,
    entity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    case_dir.mkdir(parents=True, exist_ok=True)
    requirements = load_requirements(requirements_path)
    _write_json(case_dir / "requirements.json", {"requirements": requirements})
    manifest = {
        "case_id": case_id,
        "created_from_requirements": str(requirements_path),
        "requirements_count": len(requirements),
        "entity": entity
        or {
            "cnpj": "12345678000199",
            "razao_social": "EXTRA CONSTRUTORA FICTICIA LTDA",
            "signatory": "JOAO DA SILVA FICTICIO",
        },
        "simulation_only": True,
    }
    _write_json(case_dir / "case-manifest.json", manifest)
    for sub in ("vault/objects", "documents", "matrices", "findings", "package", "reports"):
        (case_dir / sub).mkdir(parents=True, exist_ok=True)
    return manifest


def run_pipeline(
    *,
    case_id: str,
    requirements_path: Path,
    documents_source: Path,
    reference_date: str,
    output_dir: Path,
    entity: dict[str, Any] | None = None,
    operational: bool = False,
    isolation_ok: bool = True,
) -> dict[str, Any]:
    case_dir = output_dir
    manifest = create_case(case_dir, case_id=case_id, requirements_path=requirements_path, entity=entity)
    entity = manifest["entity"]
    requirements = json.loads((case_dir / "requirements.json").read_text(encoding="utf-8"))["requirements"]

    vault_root = case_dir / "vault"
    objects, warnings = ingest_path(vault_root, documents_source)
    write_inventory(case_dir / "documents" / "inventory.json", objects)

    documents: list[dict[str, Any]] = []
    classification_rows: list[dict[str, Any]] = []
    metadata_rows: list[dict[str, Any]] = []
    extraction_rows: list[dict[str, Any]] = []
    validity_by_doc: dict[str, dict[str, Any]] = {}
    identity_by_doc: dict[str, dict[str, Any]] = {}

    for obj in objects:
        data = read_object(vault_root, obj.sha256)
        text, method = extract_text_from_bytes(data, obj.extension)
        # optional embedded sidecar JSON header
        sidecar = None
        if text.startswith("---META---"):
            try:
                meta_block = text.split("---META---", 2)[1].split("---ENDMETA---", 1)[0]
                sidecar = json.loads(meta_block)
                text = text.split("---ENDMETA---", 1)[-1]
            except Exception:  # noqa: BLE001
                sidecar = None

        clf = classify_document(original_name=obj.original_name, text=text, sidecar=sidecar)
        meta = extract_metadata(text=text, method=method, original_name=obj.original_name, sidecar=sidecar)
        obj.classification = clf["classification"]

        # per-requirement validity rules may refine later; base rule from sidecar
        vrule = (sidecar or {}).get("validity_rule") or {}
        validity = evaluate_validity(
            metadata=meta,
            validity_rule=vrule,
            reference_date=reference_date,
        )
        signatory_types = {
            "PROCURACAO",
            "DECLARACAO",
            "PROPOSTA_COMERCIAL",
            "DOCUMENTO_SIGNATARIO",
            "GARANTIA_PROPOSTA",
        }
        identity = evaluate_identity(
            metadata=meta,
            expected_cnpj=entity.get("cnpj"),
            expected_legal_name=entity.get("razao_social"),
            expected_signatory=(entity.get("signatory") if clf["classification"] in signatory_types else None),
            representation_powers_required=["licitar", "propor"] if clf["classification"] == "PROCURACAO" else None,
            classification=clf["classification"],
        )
        validity_by_doc[obj.document_id] = validity
        identity_by_doc[obj.document_id] = identity

        doc = {
            "document_id": obj.document_id,
            "original_name": obj.original_name,
            "sha256": obj.sha256,
            "size": obj.size,
            "content_type": obj.content_type,
            "extension": obj.extension,
            "source_path": obj.source_path,
            "ingested_at": obj.ingested_at,
            "classification": clf["classification"],
            "classification_detail": clf,
            "sensitivity": obj.sensitivity,
            "metadata": meta,
            "validity": validity,
            "identity": identity,
            "extraction_method": method,
        }
        documents.append(doc)
        classification_rows.append({"document_id": obj.document_id, **clf, "original_name": obj.original_name})
        metadata_rows.append({"document_id": obj.document_id, "fields": sanitize_obj(meta.get("fields") or {})})
        extraction_rows.append(
            {
                "document_id": obj.document_id,
                "method": method,
                "ocr_used": method == "ocr",
                "chars": len(text),
            }
        )

    # rewrite inventory with classification
    write_inventory(case_dir / "documents" / "inventory.json", objects)

    _write_json(case_dir / "documents" / "classification.json", {"items": classification_rows})
    _write_jsonl(case_dir / "documents" / "metadata.jsonl", metadata_rows)
    _write_jsonl(case_dir / "documents" / "extraction.jsonl", extraction_rows)
    _write_json(case_dir / "documents" / "validity.json", validity_by_doc)
    _write_json(case_dir / "documents" / "identity.json", identity_by_doc)
    _write_json(
        case_dir / "documents" / "signatures.json",
        {
            d["document_id"]: {
                "signature_present": field_value(d["metadata"], "signature_present"),
                "signatory": field_value(d["metadata"], "signatario"),
                "status": (
                    "SIGNATURE_PRESENT"
                    if str(field_value(d["metadata"], "signature_present") or "").upper()
                    in {"PRESENT", "SIM", "YES", "ASSINADO", "SIGNATURE_PRESENT"}
                    else "SIGNATURE_NOT_FOUND"
                ),
                "digital_validation": "DIGITAL_VALIDATION_NOT_PERFORMED",
            }
            for d in documents
        },
    )

    match_rows = [
        match_requirement_to_documents(
            req,
            documents,
            validity_by_doc=validity_by_doc,
            identity_by_doc=identity_by_doc,
        )
        for req in requirements
    ]
    _write_json(
        case_dir / "matrices" / "requirement-document.json",
        {"rows": match_rows, "denominator_includes_missing": True},
    )

    # Technical acervo integration (canonical EXTRA base — never a second store)
    from scripts.bid_readiness.integration import integrate_requirements

    tech_reqs = []
    for req in requirements:
        tech = req.get("technical_criteria") or {}
        if tech.get("min_quantity") is not None or tech.get("service") or tech.get("object"):
            tech_reqs.append(
                {
                    "requirement_id": req.get("id") or req.get("requirement_id"),
                    "service": tech.get("service") or tech.get("object") or req.get("text"),
                    "quantity": tech.get("min_quantity"),
                    "unit": tech.get("unit") or "m2",
                    "allow_sum": bool(
                        tech.get("summable") or tech.get("somatório") or tech.get("somatorio")
                    ),
                    "mandatory": req.get("mandatory", True),
                    "document_id": req.get("source_document_id"),
                    "page": req.get("page"),
                    "cell": req.get("cell"),
                    "sheet": req.get("sheet"),
                    "text": req.get("text"),
                }
            )
    if tech_reqs:
        acervo_pack = integrate_requirements(tech_reqs)
        _write_json(case_dir / "matrices" / "technical-acervo-integration.json", acervo_pack)
    else:
        acervo_pack = None

    # Category matrices
    def subset(cats: set[str]) -> list[dict[str, Any]]:
        return [r for r in match_rows if (r.get("category") or "").upper() in cats]

    matrices = {
        "technical-qualification.json": subset({"TECNICA", "TECHNICAL", "QUALIFICACAO_TECNICA"}),
        "economic-financial.json": subset({"ECONOMICA", "ECONOMICO_FINANCEIRA", "FINANCEIRA"}),
        "legal-qualification.json": subset({"JURIDICA", "LEGAL", "HABILITACAO_JURIDICA"}),
        "fiscal-labor.json": subset({"FISCAL", "TRABALHISTA", "FISCAL_TRABALHISTA"}),
        "declarations.json": subset({"DECLARACAO", "DECLARACOES"}),
        "proposal.json": subset({"PROPOSTA", "COMERCIAL"}),
        "submission.json": subset({"PROTOCOLO", "SUBMISSAO", "FORMATO"}),
    }
    for name, rows in matrices.items():
        _write_json(case_dir / "matrices" / name, {"rows": rows})

    findings_bundle = build_findings(
        match_rows=match_rows,
        validity_by_doc=validity_by_doc,
        identity_by_doc=identity_by_doc,
        documents=documents,
        requirements=requirements,
    )
    for key, rows in findings_bundle.items():
        _write_json(case_dir / "findings" / f"{key}.json", {"items": rows})

    package_status = derive_package_status(findings_bundle, match_rows)
    # Forbidden success labels — hard fail, never silent
    if package_status in {"READY_TO_SUBMIT", "HABILITADA", "PROPOSTA APROVADA"}:
        raise RuntimeError(f"forbidden package status produced: {package_status}")

    pkg = assemble_package(
        case_dir=case_dir,
        documents=documents,
        match_rows=match_rows,
        findings_bundle=findings_bundle,
        package_status=package_status,
    )
    _write_json(case_dir / "package" / "package-reconciliation.json", pkg["reconciliation"])

    operational_blocked = not operational
    system_status = derive_system_status(
        isolation_ok=isolation_ok,
        pipeline_ok=True,
        package_status=package_status,
        operational_blocked=operational_blocked,
    )

    summary = {
        "requirements_count": len(requirements),
        "documents_count": len(documents),
        "valid_count": sum(1 for d in documents if d["validity"]["status"] == "VALID"),
        "expired_count": sum(1 for d in documents if d["validity"]["status"] == "EXPIRED"),
        "expiring_count": sum(1 for d in documents if d["validity"]["status"] == "EXPIRING_SOON"),
        "missing_count": sum(1 for r in match_rows if r["status"] == "MISSING"),
        "blockers_count": len(findings_bundle["blockers"]),
        "findings_count": len(findings_bundle["all"]),
        "ingest_warnings": warnings,
    }

    case_model = {
        "case_id": case_id,
        "system_status": system_status,
        "package_status": package_status,
        "reference_date": reference_date,
        "entity": entity,
        "summary": summary,
        "findings": findings_bundle,
        "requirements": requirements,
        "documents": documents,
        "match_rows": match_rows,
        "claims": [
            "Inventário documental content-addressed",
            "Matriz requisito × documento com estados reais",
            "Blockers objetivos derivados de evidências",
            "Pacote simulado local com SIMULATION_ONLY",
        ],
        "non_claims": [
            "READY_TO_SUBMIT",
            "HABILITADA",
            "PROPOSTA APROVADA",
            "GARANTIA ACEITA",
            "Parecer jurídico",
            "Autenticidade biométrica de assinatura",
            "Protocolo em portal",
        ],
        "operational_proof": "OPERATIONAL" if operational else "OPERATIONAL_PROOF_BLOCKED",
        "final_status": "BLOCKED" if operational_blocked or system_status != "SYSTEM_PASS" else "PASS",
    }

    report_model = build_report_model(case_model)
    write_reports(case_dir / "reports", report_model)

    verification = verify_case(case_dir)
    _write_json(case_dir / "verification.json", verification)

    # update manifest
    manifest.update(
        {
            "reference_date": reference_date,
            "system_status": system_status,
            "package_status": package_status,
            "summary": summary,
            "final_status": case_model["final_status"],
            "operational_proof": case_model["operational_proof"],
        }
    )
    _write_json(case_dir / "case-manifest.json", manifest)
    _write_json(
        case_dir / "case-result.json",
        sanitize_obj(
            {
                k: case_model[k]
                for k in (
                    "case_id",
                    "system_status",
                    "package_status",
                    "reference_date",
                    "summary",
                    "claims",
                    "non_claims",
                    "operational_proof",
                    "final_status",
                )
            }
        ),
    )
    return case_model


def revalidate_case(
    case_dir: Path,
    *,
    reference_date: str,
    isolation_ok: bool = True,
    operational: bool = False,
) -> dict[str, Any]:
    """Re-evaluate validity/match/findings for an existing case at a new reference date.

    Does not re-ingest vault objects (hashes remain frozen). Updates:
    documents/validity.json, matrices, findings, package status summary fields,
    reports, verification.json.
    """
    case_dir = Path(case_dir)
    manifest = json.loads((case_dir / "case-manifest.json").read_text(encoding="utf-8"))
    entity = manifest.get("entity") or {}
    requirements = json.loads((case_dir / "requirements.json").read_text(encoding="utf-8"))["requirements"]
    inv = json.loads((case_dir / "documents" / "inventory.json").read_text(encoding="utf-8"))
    # Load per-doc metadata from metadata.jsonl if present
    meta_by_id: dict[str, dict[str, Any]] = {}
    meta_path = case_dir / "documents" / "metadata.jsonl"
    if meta_path.is_file():
        for line in meta_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            meta_by_id[row["document_id"]] = {"fields": row.get("fields") or {}}

    clf_path = case_dir / "documents" / "classification.json"
    clf_by_id: dict[str, dict[str, Any]] = {}
    if clf_path.is_file():
        for item in json.loads(clf_path.read_text(encoding="utf-8")).get("items") or []:
            clf_by_id[item["document_id"]] = item

    identity_prev = {}
    id_path = case_dir / "documents" / "identity.json"
    if id_path.is_file():
        identity_prev = json.loads(id_path.read_text(encoding="utf-8"))

    documents: list[dict[str, Any]] = []
    validity_by_doc: dict[str, dict[str, Any]] = {}
    identity_by_doc: dict[str, dict[str, Any]] = {}

    for inv_doc in inv.get("documents") or []:
        did = inv_doc["document_id"]
        # Rebuild metadata structure expected by evaluate_validity / match
        fields = (meta_by_id.get(did) or {}).get("fields") or {}
        # metadata.jsonl stores sanitized fields; restore nested form for engine
        metadata: dict[str, Any] = {"fields": {}}
        for k, v in fields.items():
            if isinstance(v, dict) and "normalized" in v:
                metadata["fields"][k] = v
            else:
                metadata["fields"][k] = {
                    "original": v,
                    "normalized": v,
                    "source": "revalidate",
                    "confidence": 0.7,
                    "method": "revalidate",
                }

        classification = (clf_by_id.get(did) or {}).get("classification") or inv_doc.get("classification") or "UNKNOWN"
        validity = evaluate_validity(
            metadata=metadata,
            validity_rule={},
            reference_date=reference_date,
        )
        # Prefer previous identity if present (stable); else recompute
        if did in identity_prev:
            identity = identity_prev[did]
        else:
            signatory_types = {
                "PROCURACAO",
                "DECLARACAO",
                "PROPOSTA_COMERCIAL",
                "DOCUMENTO_SIGNATARIO",
                "GARANTIA_PROPOSTA",
            }
            identity = evaluate_identity(
                metadata=metadata,
                expected_cnpj=entity.get("cnpj"),
                expected_legal_name=entity.get("razao_social"),
                expected_signatory=(entity.get("signatory") if classification in signatory_types else None),
                representation_powers_required=["licitar", "propor"] if classification == "PROCURACAO" else None,
                classification=classification,
            )
        validity_by_doc[did] = validity
        identity_by_doc[did] = identity
        documents.append(
            {
                "document_id": did,
                "original_name": inv_doc.get("original_name"),
                "sha256": inv_doc.get("sha256"),
                "classification": classification,
                "metadata": metadata,
                "validity": validity,
                "identity": identity,
            }
        )

    match_rows = [
        match_requirement_to_documents(
            req,
            documents,
            validity_by_doc=validity_by_doc,
            identity_by_doc=identity_by_doc,
        )
        for req in requirements
    ]
    findings_bundle = build_findings(
        match_rows=match_rows,
        validity_by_doc=validity_by_doc,
        identity_by_doc=identity_by_doc,
        documents=documents,
        requirements=requirements,
    )
    package_status = derive_package_status(findings_bundle, match_rows)
    operational_blocked = not operational
    system_status = derive_system_status(
        isolation_ok=isolation_ok,
        pipeline_ok=True,
        package_status=package_status,
        operational_blocked=operational_blocked,
    )

    _write_json(case_dir / "documents" / "validity.json", validity_by_doc)
    _write_json(case_dir / "documents" / "identity.json", identity_by_doc)
    _write_json(
        case_dir / "matrices" / "requirement-document.json",
        {"rows": match_rows, "denominator_includes_missing": True},
    )
    for key, rows in findings_bundle.items():
        _write_json(case_dir / "findings" / f"{key}.json", {"items": rows})

    # Re-assemble package alerts (validity may have changed)
    pkg = assemble_package(
        case_dir=case_dir,
        documents=documents,
        match_rows=match_rows,
        findings_bundle=findings_bundle,
        package_status=package_status,
    )
    _write_json(case_dir / "package" / "package-reconciliation.json", pkg["reconciliation"])

    summary = {
        "requirements_count": len(requirements),
        "documents_count": len(documents),
        "valid_count": sum(1 for d in documents if d["validity"]["status"] == "VALID"),
        "expired_count": sum(1 for d in documents if d["validity"]["status"] == "EXPIRED"),
        "expiring_count": sum(1 for d in documents if d["validity"]["status"] == "EXPIRING_SOON"),
        "missing_count": sum(1 for r in match_rows if r["status"] == "MISSING"),
        "blockers_count": len(findings_bundle["blockers"]),
        "findings_count": len(findings_bundle["all"]),
        "revalidated": True,
        "reference_date": reference_date,
    }
    case_model = {
        "case_id": manifest.get("case_id"),
        "system_status": system_status,
        "package_status": package_status,
        "reference_date": reference_date,
        "entity": entity,
        "summary": summary,
        "findings": findings_bundle,
        "requirements": requirements,
        "documents": documents,
        "match_rows": match_rows,
        "claims": manifest.get("claims") or [],
        "non_claims": [
            "READY_TO_SUBMIT",
            "HABILITADA",
            "PROPOSTA APROVADA",
            "GARANTIA ACEITA",
        ],
        "operational_proof": "OPERATIONAL" if operational else "OPERATIONAL_PROOF_BLOCKED",
        "final_status": "BLOCKED" if operational_blocked or system_status != "SYSTEM_PASS" else "PASS",
    }
    report_model = build_report_model(case_model)
    write_reports(case_dir / "reports", report_model)
    verification = verify_case(case_dir)
    _write_json(case_dir / "verification.json", verification)
    manifest.update(
        {
            "reference_date": reference_date,
            "system_status": system_status,
            "package_status": package_status,
            "summary": summary,
            "final_status": case_model["final_status"],
            "operational_proof": case_model["operational_proof"],
        }
    )
    _write_json(case_dir / "case-manifest.json", manifest)
    return {
        "ok": True,
        "reference_date": reference_date,
        "validity": validity_by_doc,
        "package_status": package_status,
        "system_status": system_status,
        "summary": summary,
        "verification": verification,
    }


def verify_case(case_dir: Path) -> dict[str, Any]:
    """Verify case integrity without regenerating artifacts."""
    case_dir = Path(case_dir)
    errors: list[str] = []
    inv = json.loads((case_dir / "documents" / "inventory.json").read_text(encoding="utf-8"))
    for doc in inv.get("documents") or []:
        sha = doc["sha256"]
        obj = case_dir / "vault" / "objects" / sha
        if not obj.is_file():
            errors.append(f"missing vault object {sha}")
            continue
        import hashlib

        h = hashlib.sha256(obj.read_bytes()).hexdigest()
        if h != sha:
            errors.append(f"vault hash mismatch {sha}")

    reqs = json.loads((case_dir / "requirements.json").read_text(encoding="utf-8"))["requirements"]
    matrix = json.loads((case_dir / "matrices" / "requirement-document.json").read_text(encoding="utf-8"))
    rows = matrix.get("rows") or []
    if len(rows) != len(reqs):
        errors.append("match rows count != requirements count (denominator broken)")
    for r in rows:
        if r.get("mandatory") and r.get("status") == "MISSING":
            # must still exist in rows — already true if present
            pass

    pkg_manifest = json.loads((case_dir / "package" / "package-manifest.json").read_text(encoding="utf-8"))
    if not pkg_manifest.get("simulation_only"):
        errors.append("package missing simulation_only")
    if pkg_manifest.get("package_status") in {
        "READY_TO_SUBMIT",
        "HABILITADA",
        "PROPOSTA APROVADA",
    }:
        errors.append("forbidden package status")

    recon = json.loads((case_dir / "package" / "package-reconciliation.json").read_text(encoding="utf-8"))
    if not recon.get("ok"):
        errors.append("package reconciliation failed")
    if not recon.get("simulation_only_present"):
        errors.append("SIMULATION_ONLY missing from zip")

    blockers = json.loads((case_dir / "findings" / "blockers.json").read_text(encoding="utf-8"))
    for b in blockers.get("items") or []:
        if not b.get("objective_observation"):
            errors.append(f"blocker without evidence: {b.get('finding_id')}")

    return {
        "ok": not errors,
        "errors": errors,
        "requirements_count": len(reqs),
        "documents_count": len(inv.get("documents") or []),
        "blockers_count": len(blockers.get("items") or []),
        "package_status": pkg_manifest.get("package_status"),
    }
