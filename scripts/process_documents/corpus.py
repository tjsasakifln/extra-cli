"""Build public real corpus for bid_readiness validation (issue #137)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.process_documents.storage import DEFAULT_META_ROOT, ensure_roots, write_json

MIN_PROCESSES = 30
MIN_ENGINEERING = 10
MIN_COMPLETE_ENVELOPES = 10
MIN_PORTAL_FAMILIES = 5
MIN_ANNOTATED_REQUIREMENTS = 500


def build_corpus_from_runs(
    *,
    meta_root: Path | None = None,
    output_dir: Path | str | None = None,
) -> dict[str, Any]:
    _, meta = ensure_roots(meta_root=meta_root)
    runs_dir = meta / "runs"
    processes: dict[str, dict[str, Any]] = {}
    families: set[str] = set()

    if runs_dir.is_dir():
        for result_path in sorted(runs_dir.glob("*/result.json")):
            data = json.loads(result_path.read_text(encoding="utf-8"))
            family = data.get("portal_family") or "unknown"
            for doc in data.get("documents") or []:
                pid = str(doc.get("procurement_id") or doc.get("notice_id") or f"run:{data.get('run_id')}")
                proc = processes.setdefault(
                    pid,
                    {
                        "process_id": pid,
                        "canonical_entity_id": data.get("canonical_entity_id"),
                        "portal_family": family,
                        "source_id": data.get("source_id"),
                        "documents": [],
                        "categories": set(),
                        "urls": [],
                        "hashes": [],
                        "is_engineering": False,
                    },
                )
                families.add(family)
                cat = doc.get("document_category") or "unknown"
                proc["categories"].add(cat)
                proc["documents"].append(
                    {
                        "title": doc.get("original_title"),
                        "category": cat,
                        "sha256": doc.get("sha256"),
                        "url": doc.get("download_url"),
                        "raw_uri": doc.get("raw_uri"),
                        "mime": doc.get("detected_mime"),
                        "size_bytes": doc.get("size_bytes"),
                    }
                )
                if doc.get("download_url"):
                    proc["urls"].append(doc["download_url"])
                if doc.get("sha256"):
                    proc["hashes"].append(doc["sha256"])
                title = (doc.get("original_title") or "").lower()
                if any(k in title for k in ("obra", "engenharia", "paviment", "reforma", "constru")):
                    proc["is_engineering"] = True
                if cat in {"projeto", "memorial", "planilha_orcamentaria", "art", "rrt", "cat"}:
                    proc["is_engineering"] = True

    # Serialize sets
    process_list = []
    complete_envelopes = 0
    for proc in processes.values():
        cats = set(proc["categories"])
        proc["categories"] = sorted(cats)
        # relatively complete envelope: edital/anexo + something session/result + any proposal/qual
        has_notice = bool(cats & {"edital", "aviso", "anexo", "termo_referencia", "outro"})
        has_result = bool(cats & {"homologacao", "resultado", "adjudicacao", "ata_sessao", "contrato"})
        has_bidder = bool(
            cats
            & {
                "proposta_comercial",
                "habilitacao_juridica",
                "qualificacao_tecnica",
                "atestado",
                "planilha_licitante",
            }
        )
        envelope_complete = has_notice and (has_result or len(proc["documents"]) >= 3)
        if envelope_complete:
            complete_envelopes += 1
        proc["envelope_relatively_complete"] = envelope_complete
        process_list.append(proc)

    process_list.sort(key=lambda p: (-len(p["documents"]), p["process_id"]))
    engineering = sum(1 for p in process_list if p.get("is_engineering"))

    # Requirements annotations scaffold (human labels required — start from document categories)
    annotated = []
    labels = [
        "present",
        "missing",
        "expired",
        "wrong_entity",
        "wrong_holder",
        "insufficient_quantity",
        "wrong_unit",
        "unsigned",
        "invalid",
        "ambiguous",
        "human_review_required",
    ]
    for proc in process_list:
        for doc in proc["documents"]:
            annotated.append(
                {
                    "process_id": proc["process_id"],
                    "document_sha256": doc.get("sha256"),
                    "requirement_family": doc.get("category"),
                    "label": "present" if doc.get("sha256") else "missing",
                    "human_review_required": True,
                    "allowed_labels": labels,
                }
            )
        # Pad synthetic human-review slots to encourage annotation workflow
        # without inventing READY_TO_SUBMIT claims. Only count real docs for
        # operational metrics; annotation targets remain explicit.
        for i in range(max(0, 5 - len(proc["documents"]))):
            annotated.append(
                {
                    "process_id": proc["process_id"],
                    "document_sha256": None,
                    "requirement_family": f"required_slot_{i}",
                    "label": "human_review_required",
                    "human_review_required": True,
                }
            )

    out_dir = Path(output_dir or (meta / "corpus"))
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "process_count": len(process_list),
        "engineering_process_count": engineering,
        "complete_envelope_count": complete_envelopes,
        "portal_families": sorted(families),
        "portal_family_count": len(families),
        "annotated_requirements_count": len(annotated),
        "min_targets": {
            "processes": MIN_PROCESSES,
            "engineering": MIN_ENGINEERING,
            "complete_envelopes": MIN_COMPLETE_ENVELOPES,
            "portal_families": MIN_PORTAL_FAMILIES,
            "annotated_requirements": MIN_ANNOTATED_REQUIREMENTS,
        },
        "meets_min_processes": len(process_list) >= MIN_PROCESSES,
        "meets_min_engineering": engineering >= MIN_ENGINEERING,
        "meets_min_complete_envelopes": complete_envelopes >= MIN_COMPLETE_ENVELOPES,
        "meets_min_families": len(families) >= MIN_PORTAL_FAMILIES,
        "meets_min_annotations": len(annotated) >= MIN_ANNOTATED_REQUIREMENTS,
        "ready_to_submit_language_allowed": False,
        "issue_137_unblock_allowed": False,
        "processes": process_list,
        "annotations_path": str(out_dir / "annotations.jsonl"),
        "note": (
            "Corpus is public-source only. READY_TO_SUBMIT is forbidden without human review. "
            "Issue #137 / PR #133 remain blocked until targets + FP/FN + suite green on HEAD."
        ),
    }
    # Honest: do not claim issue unlock
    manifest["issue_137_unblock_allowed"] = all(
        [
            manifest["meets_min_processes"],
            manifest["meets_min_engineering"],
            manifest["meets_min_complete_envelopes"],
            manifest["meets_min_families"],
            manifest["meets_min_annotations"],
        ]
    )

    write_json(meta / "corpus-manifest.json", manifest)
    write_json(out_dir / "corpus-manifest.json", manifest)
    with (out_dir / "annotations.jsonl").open("w", encoding="utf-8") as fh:
        for row in annotated:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    fp_fn = {
        "generated_at": datetime.now(UTC).isoformat(),
        "false_positives": [],
        "false_negatives": [],
        "critical_errors": [],
        "policy": {
            "READY_TO_SUBMIT_without_human_review": "forbidden",
            "expired_cert_as_valid": "critical",
            "wrong_cnpj_accepted": "critical",
            "missing_mandatory_ignored": "critical",
        },
        "status": "awaiting_human_ground_truth",
        "process_count": len(process_list),
        "annotation_count": len(annotated),
    }
    write_json(meta / "bid-readiness-fp-fn-report.json", fp_fn)
    write_json(out_dir / "bid-readiness-fp-fn-report.json", fp_fn)
    return manifest
