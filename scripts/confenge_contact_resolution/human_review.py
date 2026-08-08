"""Human-review package generator (never auto-approves)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _contact_row(
    company: dict[str, Any],
    contact: dict[str, Any] | None,
    *,
    bucket: str,
) -> dict[str, Any]:
    c = contact or {}
    prov = c.get("provenance") or {}
    return {
        "bucket": bucket,
        "empresa": company.get("company_name") or company.get("razao_social"),
        "cnpj14": company.get("cnpj14"),
        "contato": c.get("email") or c.get("phone_e164") or c.get("value") or c.get("phone"),
        "email": c.get("email"),
        "phone": c.get("phone_e164") or c.get("phone"),
        "ownership_status": c.get("ownership_status"),
        "confidence": c.get("confidence"),
        "reason": c.get("ownership_reason") or c.get("verification_reason") or c.get("reason"),
        "source_url": prov.get("source_url") or c.get("source_url"),
        "source_type": prov.get("source_type") or c.get("source_type"),
        "official_domain": company.get("official_domain"),
        "reuse_signal": c.get("associated_company_count"),
        "third_party_signals": c.get("third_party_type"),
        "verification_status": c.get("verification_status"),
        "enrollable": c.get("enrollable"),
        "role_class": c.get("role_class"),
        "commercial_contact_state": company.get("commercial_contact_state"),
        "processing_state": company.get("processing_state"),
    }


def select_review_sample(
    resolutions: list[dict[str, Any]],
    *,
    n_accepted: int = 20,
    n_rejected: int = 20,
    n_unresolved: int = 20,
) -> dict[str, list[dict[str, Any]]]:
    """Diverse sample across accepted / rejected / unresolved."""
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    seen_domains: set[str] = set()
    seen_cnpj: set[str] = set()

    for res in resolutions:
        cnpj = str(res.get("cnpj14") or "")
        if cnpj in seen_cnpj:
            continue
        cands = list(res.get("candidates") or [])
        rej = list(res.get("rejected_contacts") or [])
        enroll = [c for c in cands if c.get("enrollable")]
        review = [
            c
            for c in cands
            if not c.get("enrollable")
            and (c.get("ownership_status") or "")
            in {"LIKELY_COMPANY_OWNED", "UNRESOLVED", "HUMAN_CONFIRMED"}
        ]

        if enroll and len(accepted) < n_accepted:
            # diversity by email domain
            pick = enroll[0]
            dom = (pick.get("email") or "@").split("@")[-1].lower()
            if dom in seen_domains and len(accepted) < n_accepted // 2:
                # still allow if early slots need fill; prefer diversity first half
                if len(accepted) >= 5:
                    continue
            seen_domains.add(dom)
            seen_cnpj.add(cnpj)
            accepted.append(_contact_row(res, pick, bucket="ACCEPTED"))
            continue

        if rej and len(rejected) < n_rejected:
            seen_cnpj.add(cnpj)
            rejected.append(_contact_row(res, rej[0], bucket="REJECTED"))
            continue

        if (review or not cands) and len(unresolved) < n_unresolved:
            seen_cnpj.add(cnpj)
            pick = review[0] if review else None
            row = _contact_row(res, pick, bucket="UNRESOLVED")
            if not pick:
                row["reason"] = res.get("absence_reason") or res.get("investigation_outcome") or "NO_CONTACT_YET"
                row["contato"] = None
            unresolved.append(row)

        if len(accepted) >= n_accepted and len(rejected) >= n_rejected and len(unresolved) >= n_unresolved:
            break

    # Second pass fill if short
    if len(accepted) < n_accepted or len(rejected) < n_rejected or len(unresolved) < n_unresolved:
        for res in resolutions:
            cnpj = str(res.get("cnpj14") or "")
            if cnpj in seen_cnpj:
                continue
            cands = list(res.get("candidates") or [])
            rej = list(res.get("rejected_contacts") or [])
            enroll = [c for c in cands if c.get("enrollable")]
            if enroll and len(accepted) < n_accepted:
                seen_cnpj.add(cnpj)
                accepted.append(_contact_row(res, enroll[0], bucket="ACCEPTED"))
            elif rej and len(rejected) < n_rejected:
                seen_cnpj.add(cnpj)
                rejected.append(_contact_row(res, rej[0], bucket="REJECTED"))
            elif len(unresolved) < n_unresolved:
                seen_cnpj.add(cnpj)
                unresolved.append(
                    _contact_row(
                        res,
                        cands[0] if cands else None,
                        bucket="UNRESOLVED",
                    )
                )

    return {
        "accepted": accepted[:n_accepted],
        "rejected": rejected[:n_rejected],
        "unresolved": unresolved[:n_unresolved],
    }


def write_human_review_package(
    output_dir: Path | str,
    resolutions: list[dict[str, Any]],
    *,
    n_each: int = 20,
    machine_validation: str = "PASS",
) -> dict[str, Any]:
    """Write human-review/ with jsonl + review.md. Never sets HUMAN_REVIEW_PASS."""
    out = Path(output_dir) / "human-review"
    out.mkdir(parents=True, exist_ok=True)
    sample = select_review_sample(
        resolutions,
        n_accepted=n_each,
        n_rejected=n_each,
        n_unresolved=n_each,
    )

    def _write_jsonl(name: str, rows: list[dict[str, Any]]) -> None:
        body = "\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in rows)
        if body:
            body += "\n"
        (out / name).write_text(body, encoding="utf-8")

    _write_jsonl("accepted.jsonl", sample["accepted"])
    _write_jsonl("rejected.jsonl", sample["rejected"])
    _write_jsonl("unresolved.jsonl", sample["unresolved"])

    md = _render_review_md(sample)
    (out / "review.md").write_text(md, encoding="utf-8")

    status = {
        "schema": "confenge-human-review-status-v1",
        "generated_at": _now(),
        "machine_validation": machine_validation,
        "human_validation": "HUMAN_REVIEW_PENDING",
        "counts": {
            "accepted": len(sample["accepted"]),
            "rejected": len(sample["rejected"]),
            "unresolved": len(sample["unresolved"]),
        },
        "note": "Human validation must not be auto-approved by the pipeline.",
    }
    (out / "status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return status


def _render_review_md(sample: dict[str, list[dict[str, Any]]]) -> str:
    lines = [
        "# CONFENGE contact enrichment — human review",
        "",
        f"Generated: {_now()}",
        "",
        "Status: **HUMAN_REVIEW_PENDING** (machine may be PASS; human must review)",
        "",
        "Each case lists company, CNPJ, contact, ownership, confidence, reason, source, domain.",
        "",
    ]
    for title, key in (
        ("Accepted / enrollable", "accepted"),
        ("Rejected", "rejected"),
        ("Unresolved / review required", "unresolved"),
    ):
        rows = sample.get(key) or []
        lines.append(f"## {title} ({len(rows)})")
        lines.append("")
        if not rows:
            lines.append("_No cases in this bucket for this run._")
            lines.append("")
            continue
        for i, r in enumerate(rows, 1):
            lines.append(f"### {i}. {r.get('empresa') or '—'} (`{r.get('cnpj14') or '—'}`)")
            lines.append("")
            lines.append(f"- **contato:** `{r.get('contato') or '—'}`")
            lines.append(f"- **ownership_status:** {r.get('ownership_status') or '—'}")
            lines.append(f"- **confidence:** {r.get('confidence')}")
            lines.append(f"- **reason:** {r.get('reason') or '—'}")
            lines.append(f"- **source_type:** {r.get('source_type') or '—'}")
            lines.append(f"- **source_url:** {r.get('source_url') or '—'}")
            lines.append(f"- **domínio oficial:** {r.get('official_domain') or '—'}")
            lines.append(f"- **reuse signal (associated companies):** {r.get('reuse_signal')}")
            lines.append(f"- **third-party signals:** {r.get('third_party_signals') or '—'}")
            lines.append(f"- **verification_status:** {r.get('verification_status') or '—'}")
            lines.append(f"- **enrollable:** {r.get('enrollable')}")
            lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append("After human review, record pass/fail outside this auto-generated package.")
    lines.append("Do not treat this file as HUMAN_REVIEW_PASS.")
    lines.append("")
    return "\n".join(lines)
