"""Simulated submission package assembly (local only, SIMULATION_ONLY)."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any

from scripts.bid_readiness.vault import read_object

FOLDER_MAP = {
    "CONTRATO_SOCIAL": "01-habilitacao-juridica",
    "ALTERACAO_CONTRATUAL": "01-habilitacao-juridica",
    "CARTAO_CNPJ": "01-habilitacao-juridica",
    "PROCURACAO": "01-habilitacao-juridica",
    "DOCUMENTO_SIGNATARIO": "01-habilitacao-juridica",
    "CERTIDAO_FEDERAL": "02-regularidade-fiscal-trabalhista",
    "CERTIDAO_ESTADUAL": "02-regularidade-fiscal-trabalhista",
    "CERTIDAO_MUNICIPAL": "02-regularidade-fiscal-trabalhista",
    "FGTS": "02-regularidade-fiscal-trabalhista",
    "CNDT": "02-regularidade-fiscal-trabalhista",
    "BALANCO_PATRIMONIAL": "03-economico-financeira",
    "DRE": "03-economico-financeira",
    "INDICES_CONTABEIS": "03-economico-financeira",
    "CERTIDAO_FALENCIA": "03-economico-financeira",
    "ATESTADO_CAPACIDADE_TECNICA": "04-qualificacao-tecnica",
    "CAT": "04-qualificacao-tecnica",
    "ART": "04-qualificacao-tecnica",
    "RRT": "04-qualificacao-tecnica",
    "REGISTRO_CONSELHO_EMPRESA": "04-qualificacao-tecnica",
    "REGISTRO_CONSELHO_PROFISSIONAL": "04-qualificacao-tecnica",
    "VINCULO_PROFISSIONAL": "04-qualificacao-tecnica",
    "PROPOSTA_COMERCIAL": "05-proposta",
    "PLANILHA_PRECOS": "05-proposta",
    "CRONOGRAMA": "05-proposta",
    "BDI": "05-proposta",
    "DECLARACAO": "06-declaracoes",
    "GARANTIA_PROPOSTA": "07-garantia",
}


def deterministic_name(classification: str, original_name: str, sha256: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(original_name).stem)[:40]
    ext = Path(original_name).suffix.lower() or ".bin"
    return f"{classification}_{stem}_{sha256[:10]}{ext}"


def assemble_package(
    *,
    case_dir: Path,
    documents: list[dict[str, Any]],
    match_rows: list[dict[str, Any]],
    findings_bundle: dict[str, list[dict[str, Any]]],
    package_status: str,
) -> dict[str, Any]:
    package_dir = case_dir / "package"
    package_dir.mkdir(parents=True, exist_ok=True)
    vault_root = case_dir / "vault"

    # clean previous package content folders
    for sub in (
        "01-habilitacao-juridica",
        "02-regularidade-fiscal-trabalhista",
        "03-economico-financeira",
        "04-qualificacao-tecnica",
        "05-proposta",
        "06-declaracoes",
        "07-garantia",
    ):
        d = package_dir / sub
        d.mkdir(parents=True, exist_ok=True)

    files_meta: list[dict[str, Any]] = []
    used_names: set[str] = set()
    missing_required = [r for r in match_rows if r.get("mandatory") and r.get("status") == "MISSING"]

    for doc in documents:
        classification = doc.get("classification") or "OUTRO"
        folder = FOLDER_MAP.get(classification, "05-proposta")
        name = deterministic_name(classification, doc["original_name"], doc["sha256"])
        if name in used_names:
            raise RuntimeError(f"package name collision: {name}")
        used_names.add(name)
        rel = f"{folder}/{name}"
        dest = package_dir / rel
        data = read_object(vault_root, doc["sha256"])
        # never alter originals
        dest.write_bytes(data)
        validity = (doc.get("validity") or {}).get("status")
        identity = doc.get("identity") or {}
        identity_findings = list(identity.get("findings") or [])
        # Mirror structured identity statuses into alerts even if findings list is sparse
        if identity.get("cnpj_status") == "CNPJ_MISMATCH" and "CNPJ_MISMATCH" not in identity_findings:
            identity_findings.append("CNPJ_MISMATCH")
        if identity.get("name_status") == "LEGAL_NAME_MISMATCH" and "LEGAL_NAME_MISMATCH" not in identity_findings:
            identity_findings.append("LEGAL_NAME_MISMATCH")
        if (
            identity.get("power_status") == "REPRESENTATION_POWER_UNPROVEN"
            and "REPRESENTATION_POWER_UNPROVEN" not in identity_findings
        ):
            identity_findings.append("REPRESENTATION_POWER_UNPROVEN")
        if identity.get("signatory_status") in {"SIGNATORY_NOT_FOUND", "SIGNATORY_MISMATCH"}:
            if "SIGNATORY_NOT_FOUND" not in identity_findings:
                identity_findings.append("SIGNATORY_NOT_FOUND")

        hard_identity = {
            "CNPJ_MISMATCH",
            "LEGAL_NAME_MISMATCH",
            "REPRESENTATION_POWER_UNPROVEN",
            "SIGNATORY_NOT_FOUND",
        }
        identity_alerts = [f for f in identity_findings if f in hard_identity]

        alerts: list[str] = []
        included_as = "VALID_EVIDENCE"
        if validity in {"EXPIRED", "EXPIRES_BEFORE_SUBMISSION"}:
            included_as = "INCLUDED_WITH_EXPIRED_ALERT"
            alerts.append("EXPIRED_DOCUMENT")
        if identity_alerts:
            # Identity-failed originals must never be labeled VALID_EVIDENCE
            if included_as == "VALID_EVIDENCE":
                included_as = "INCLUDED_WITH_IDENTITY_ALERT"
            else:
                included_as = "INCLUDED_WITH_ALERTS"
            alerts.extend(identity_alerts)
        files_meta.append(
            {
                "package_path": rel,
                "document_id": doc["document_id"],
                "sha256": doc["sha256"],
                "classification": classification,
                "included_as": included_as,
                "alerts": alerts,
                "size": len(data),
            }
        )

    # Banner
    banner = (
        "SIMULATION_ONLY\n"
        "This package is a local simulation for human review.\n"
        "It is NOT a protocol submission and does NOT prove habilitacao.\n"
        f"package_status={package_status}\n"
    )
    (package_dir / "SIMULATION_ONLY.txt").write_text(banner, encoding="utf-8")

    checklist_lines = [
        "# Human review checklist",
        "",
        f"Package status: `{package_status}`",
        "",
        "This checklist does **not** authorize portal submission.",
        "",
        "## Blockers",
    ]
    for b in findings_bundle.get("blockers") or []:
        checklist_lines.append(f"- [{b['severity']}] {b['title']}: {b['objective_observation']}")
    checklist_lines += ["", "## Missing mandatory (still in denominator)", ""]
    for r in missing_required:
        checklist_lines.append(f"- {r['requirement_id']}: {r.get('title')}")
    checklist_lines += [
        "",
        "## Reviewer actions",
        "- [ ] Confirm no private documents will be committed to Git",
        "- [ ] Confirm expired documents are not treated as valid",
        "- [ ] Engineer review of technical candidates",
        "- [ ] Legal review of representation powers",
        "- [ ] Explicit human acceptance before any protocol attempt",
        "",
    ]
    (package_dir / "human-review-checklist.md").write_text("\n".join(checklist_lines), encoding="utf-8")

    # Manifest + checksums
    checksum_lines: list[str] = []
    for fm in files_meta:
        checksum_lines.append(f"{fm['sha256']}  {fm['package_path']}")
    sim_sha = hashlib.sha256(banner.encode("utf-8")).hexdigest()
    checksum_lines.append(f"{sim_sha}  SIMULATION_ONLY.txt")
    (package_dir / "package-checksums.txt").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

    manifest = {
        "simulation_only": True,
        "banner": "SIMULATION_ONLY",
        "package_status": package_status,
        "files": files_meta,
        "missing_required_requirements": [r["requirement_id"] for r in missing_required],
        "file_count": len(files_meta),
        "claims": [
            "Local simulated package for human review",
            "Originals copied without alteration",
        ],
        "non_claims": [
            "READY_TO_SUBMIT",
            "HABILITADA",
            "Portal protocol completed",
            "Legal opinion",
        ],
    }
    (package_dir / "package-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    # ZIP
    zip_path = package_dir / "submission-package.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SIMULATION_ONLY.txt", banner)
        zf.writestr(
            "package-manifest.json",
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        )
        zf.writestr("package-checksums.txt", "\n".join(checksum_lines) + "\n")
        zf.writestr("human-review-checklist.md", "\n".join(checklist_lines))
        for fm in files_meta:
            zf.write(package_dir / fm["package_path"], arcname=fm["package_path"])

    # Reconciliation
    with zipfile.ZipFile(zip_path, "r") as zf:
        zip_names = set(zf.namelist())
    expected = {fm["package_path"] for fm in files_meta} | {
        "SIMULATION_ONLY.txt",
        "package-manifest.json",
        "package-checksums.txt",
        "human-review-checklist.md",
    }
    recon = {
        "zip_path": str(zip_path.relative_to(case_dir)),
        "expected_files": sorted(expected),
        "zip_files": sorted(zip_names),
        "missing_in_zip": sorted(expected - zip_names),
        "extra_in_zip": sorted(zip_names - expected),
        "ok": expected == zip_names,
        "simulation_only_present": "SIMULATION_ONLY.txt" in zip_names,
    }
    return {"manifest": manifest, "reconciliation": recon, "zip_path": str(zip_path)}
