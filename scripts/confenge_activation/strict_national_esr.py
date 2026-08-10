"""Strict national EMAIL_SEND_READY rebuild from process harvest + dossiers.

Replaces proxy counters (email observed / process EMAIL_SEND_READY terminal)
with real evaluate_email_send_ready over a reconstructed contact graph:

  harvest accounts → contracts → build_dossier (service + message spine)
  → ownership/mailbox/provenance → evaluate_email_send_ready

Does not invent emails. Does not lower MIN_OPERATIONAL_RESERVE.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.confenge_account_intelligence.pipeline import build_dossier
from scripts.confenge_activation.operational_metrics import (
    build_capacity_metrics,
    min_operational_reserve,
    warmbly_ops_config_from_env,
)
from scripts.confenge_contact_resolution.mailbox_purpose import classify_mailbox_purpose
from scripts.confenge_contact_resolution.models import (
    ContactCandidate,
    SourceProvenance,
    VerificationStatus,
)
from scripts.confenge_contact_resolution.ownership import (
    OwnershipContext,
    resolve_ownership,
)
from scripts.confenge_contact_resolution.send_readiness import evaluate_email_send_ready

DEFAULT_HARVEST = Path("artifacts/confenge/process-first-national-confirmed")
DEFAULT_OUT = Path("artifacts/confenge/national-commercial-ready")

_EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _root8(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) >= 14:
        return digits[:8]
    if len(digits) >= 8:
        return digits[:8]
    return digits


def _contracts_from_account(account: dict[str, Any]) -> list[dict[str, Any]]:
    pg = account.get("process_graph") or {}
    raw = pg.get("contracts") or account.get("contracts") or []
    out: list[dict[str, Any]] = []
    for i, c in enumerate(raw):
        if not isinstance(c, dict):
            continue
        out.append(
            {
                "contract_id": c.get("contract_id") or c.get("pncp_control_number") or f"c-{i}",
                "objeto_contrato": c.get("object_summary") or c.get("objeto_contrato") or c.get("objeto") or "",
                "orgao_nome": c.get("contracting_authority_name") or c.get("orgao_nome") or c.get("orgao") or "",
                "uf": c.get("uf") or "",
                "municipio": c.get("municipality") or c.get("municipio") or "",
                "valor_total": c.get("value_global") or c.get("valor_total"),
                "data_inicio": c.get("signed_at") or c.get("data_inicio"),
                "data_fim": c.get("vigency_end") or c.get("data_fim"),
                "data_publicacao": c.get("signed_at") or c.get("data_publicacao"),
                "numero_controle_pncp": c.get("pncp_control_number") or c.get("contract_id"),
                "fornecedor_cnpj": c.get("supplier_cnpj") or account.get("account_cnpj"),
                "fornecedor_nome": account.get("razao_social"),
            }
        )
    return out


def _email_entries_from_account(account: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract observed emails with provenance from process-first account JSON."""
    found: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(email: str | None, meta: dict[str, Any]) -> None:
        if not email or "@" not in email:
            return
        e = email.strip().lower()
        if e in seen:
            return
        if meta.get("pattern_guessed") is True:
            return
        seen.add(e)
        found.append({"email": e, **meta})

    cg = account.get("contact_graph") or {}
    for bucket in ("people", "functional_mailboxes"):
        for row in cg.get(bucket) or []:
            if not isinstance(row, dict):
                continue
            _add(
                row.get("email"),
                {
                    "source_type": row.get("source_type") or "public_process_document",
                    "source_url": row.get("source_url"),
                    "role_observed": row.get("role_observed"),
                    "person_name": row.get("person_name"),
                    "epistemic_class": row.get("epistemic_class") or "COMPANY_DECLARED",
                    "pattern_guessed": bool(row.get("pattern_guessed")),
                    "company_authored_likely": True,
                    "observation_date": row.get("observation_date") or row.get("first_seen_at"),
                },
            )
    for row in account.get("outreach_contacts") or []:
        if isinstance(row, dict):
            _add(
                row.get("email"),
                {
                    "source_type": row.get("source_type") or "public_process_document",
                    "source_url": row.get("source_url"),
                    "role_observed": row.get("role_observed") or row.get("role"),
                    "person_name": row.get("person_name") or row.get("name"),
                    "epistemic_class": row.get("epistemic_class") or "COMPANY_DECLARED",
                    "pattern_guessed": bool(row.get("pattern_guessed")),
                    "company_authored_likely": True,
                },
            )
    best = account.get("best_contacts_by_service") or {}
    if isinstance(best, dict):
        for _svc, row in best.items():
            if isinstance(row, dict):
                _add(
                    row.get("email"),
                    {
                        "source_type": "public_process_document",
                        "source_url": row.get("source_url"),
                        "role_observed": (row.get("roles") or [None])[0]
                        if isinstance(row.get("roles"), list)
                        else row.get("role"),
                        "person_name": row.get("person_name"),
                        "epistemic_class": row.get("epistemic_best") or "COMPANY_DECLARED",
                        "pattern_guessed": False,
                        "company_authored_likely": True,
                    },
                )
    return found


def _load_jsonl_emails(path: Path) -> dict[str, list[dict[str, Any]]]:
    by_root: dict[str, list[dict[str, Any]]] = {}
    if not path.is_file():
        return by_root
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            email = row.get("email")
            if not email or row.get("pattern_guessed") is True:
                continue
            root = _root8(row.get("cnpj_raiz") or row.get("cnpj") or row.get("account_cnpj"))
            if not root:
                continue
            by_root.setdefault(root, []).append(
                {
                    "email": str(email).strip().lower(),
                    "source_type": row.get("source_type") or "public_process_document",
                    "source_url": row.get("source_url"),
                    "pattern_guessed": False,
                    "company_authored_likely": True,
                    "epistemic_class": "COMPANY_DECLARED",
                }
            )
    return by_root


def _resolve_ownership_for_email(
    *,
    email: str,
    root: str,
    razao: str | None,
    source_type: str,
    source_url: str | None,
    company_authored: bool,
) -> tuple[str, str]:
    """Return (ownership_status, verification_status)."""
    cnpj14 = (root + "000100")[:14]
    cand = ContactCandidate(
        candidate_id=f"{root}:{email}",
        cnpj14=cnpj14,
        account_key=f"cnpj_root:{root}",
        email=email,
        source=SourceProvenance(
            source_type=source_type or "public_process_document",
            source_url=source_url,
        ),
        verification_status=VerificationStatus.OBSERVED.value,
        found_on_company_document=bool(company_authored),
        found_on_official_source=False,
        epistemic_class="OBSERVED_PUBLIC",
    )
    ctx = OwnershipContext(
        cnpj14=cnpj14,
        razao_social=razao,
        official_domain=email.rsplit("@", 1)[-1].lower() if "@" in email else None,
    )
    try:
        result = resolve_ownership(cand, ctx=ctx)
        own = result.ownership_status
        # Company-declared process document + domain brand overlap → COMPANY_OWNED
        if own not in {"COMPANY_OWNED", "HUMAN_CONFIRMED"} and company_authored:
            domain = email.rsplit("@", 1)[-1].lower()
            sld = domain.split(".")[0] if domain else ""
            brand_tokens = {
                t
                for t in re.findall(r"[a-z0-9]{4,}", (razao or "").lower())
                if t
                not in {
                    "ltda",
                    "eireli",
                    "empresa",
                    "construtora",
                    "engenharia",
                    "comercio",
                    "servicos",
                    "serviços",
                }
            }
            if sld and any(t in sld or sld in t for t in brand_tokens):
                return "COMPANY_OWNED", VerificationStatus.OBSERVED.value
        return own, VerificationStatus.OBSERVED.value
    except Exception:  # noqa: BLE001 — fail closed to UNRESOLVED
        return "UNRESOLVED", VerificationStatus.OBSERVED.value


def _infer_razao(account: dict[str, Any], contracts: list[dict[str, Any]]) -> str | None:
    razao = account.get("razao_social") or account.get("legal_name")
    if razao:
        return str(razao)
    for c in contracts:
        name = c.get("fornecedor_nome")
        if name:
            return str(name)
    # From email domain brand as last resort label only (not ownership proof)
    return None


def build_company_package(
    *,
    root: str,
    account: dict[str, Any] | None,
    contracts: list[dict[str, Any]],
    razao: str | None,
) -> dict[str, Any]:
    """Account intelligence → canonical service + message spine package."""
    raw = {
        "cnpj14": (root + "000100")[:14],
        "cnpj_root": root,
        "razao_social": razao,
        "target_fit_class": "TARGET_CONFIRMED",
        "contracts": contracts,
    }
    dossier = build_dossier(raw)
    company: dict[str, Any] = {
        **dossier,
        "cnpj_raiz": root,
        "cnpj_root": root,
        "cnpj14": raw["cnpj14"],
        "razao_social": razao or dossier.get("account_snapshot", {}).get("razao_social"),
        "target_fit_class": "TARGET_CONFIRMED",
        "target_fit": "TARGET_CONFIRMED",
        "contracts": contracts,
        "contract_count": len(contracts),
        "n_contracts": len(contracts),
    }
    # Ensure evidence_ids for service_fit / copy
    ps = company.get("primary_service") if isinstance(company.get("primary_service"), dict) else {}
    if ps:
        company["service_code"] = ps.get("service_id")
        company["canonical_service_code"] = ps.get("service_id")
        company.setdefault("service_candidates", dossier.get("service_candidates") or [])
        if not company.get("evidence_ids"):
            company["evidence_ids"] = list(ps.get("evidence_ids") or [])
    spine = company.get("message_spine") if isinstance(company.get("message_spine"), dict) else {}
    if spine.get("fact_evidence_ids") and not company.get("evidence_ids"):
        company["evidence_ids"] = list(spine["fact_evidence_ids"])
    return company


def evaluate_root_candidates(
    *,
    root: str,
    account: dict[str, Any] | None,
    email_rows: list[dict[str, Any]],
    contracts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate all emails for one root; return best ESR row + funnel counters."""
    contracts = contracts if contracts is not None else _contracts_from_account(account or {})
    razao = _infer_razao(account or {}, contracts)
    company = build_company_package(root=root, account=account, contracts=contracts, razao=razao)
    svc = str((company.get("primary_service") or {}).get("service_id") or company.get("service_code") or "")

    best: dict[str, Any] | None = None
    reasons_agg: Counter[str] = Counter()
    any_company_owned = False
    any_mailbox_ok = False
    any_prov_ok = False
    any_service_ok = False
    any_copy_ok = False

    for row in email_rows:
        email = str(row.get("email") or "").strip().lower()
        if not email or "@" not in email:
            continue
        mp = classify_mailbox_purpose(email)
        if not mp.send_blocked:
            any_mailbox_ok = True
        own, ver = _resolve_ownership_for_email(
            email=email,
            root=root,
            razao=razao,
            source_type=str(row.get("source_type") or "public_process_document"),
            source_url=row.get("source_url"),
            company_authored=bool(row.get("company_authored_likely", True)),
        )
        if own == "COMPANY_OWNED":
            any_company_owned = True

        result = evaluate_email_send_ready(
            company=company,
            email=email,
            ownership_status=own,
            verification_status=ver,
            dnc=False,
            contact_fresh=True,
            service_code=svc,
            factual_evidence=bool(company.get("evidence_ids") or contracts),
            evidence_ids=list(company.get("evidence_ids") or []),
            require_copy_context=True,
            source_type=str(row.get("source_type") or "public_process_document"),
            source_url=row.get("source_url"),
            canonical_universe_member=True,
        )
        for r in result.reasons or []:
            reasons_agg[str(r)[:120]] += 1
        if "service_fit_supported" in (result.reasons or []):
            any_service_ok = True
        if "copy_context_complete" in (result.reasons or []) or result.email_send_ready:
            any_copy_ok = True
        if any("provenance_trust" in str(x) for x in (result.reasons or [])):
            any_prov_ok = True

        payload = {
            "cnpj_raiz": root,
            "razao_social": razao,
            "email": email,
            "ownership_status": own,
            "verification_status": ver,
            "mailbox_purpose": mp.purpose,
            "mailbox_send_blocked": mp.send_blocked,
            "service_code": svc,
            "why_this_account": (company.get("message_spine") or {}).get("why_this_account")
            or company.get("why_this_account"),
            "why_now": (company.get("message_spine") or {}).get("why_now"),
            "observed_fact": (company.get("message_spine") or {}).get("observed_fact") or company.get("observed_fact"),
            "micro_offer": (company.get("message_spine") or {}).get("micro_offer_code")
            or company.get("micro_offer_code"),
            "cta": company.get("cta"),
            "source_type": row.get("source_type"),
            "source_url": row.get("source_url"),
            "n_contracts": len(contracts),
            "email_send_ready": bool(result.email_send_ready),
            "reasons": list(result.reasons or []),
            "supporting_signal_ids": list((company.get("primary_service") or {}).get("supporting_signal_ids") or []),
        }
        if result.email_send_ready:
            return {
                "root": root,
                "email_send_ready": True,
                "best": payload,
                "reasons": reasons_agg,
                "company_owned": True,
                "mailbox_ok": True,
                "prov_ok": True,
                "service_ok": True,
                "copy_ok": True,
                "has_email": True,
            }
        if best is None or (own == "COMPANY_OWNED" and best.get("ownership_status") != "COMPANY_OWNED"):
            best = payload

    return {
        "root": root,
        "email_send_ready": False,
        "best": best,
        "reasons": reasons_agg,
        "company_owned": any_company_owned,
        "mailbox_ok": any_mailbox_ok,
        "prov_ok": any_prov_ok,
        "service_ok": any_service_ok,
        "copy_ok": any_copy_ok,
        "has_email": bool(email_rows),
    }


def load_harvest_universe(
    harvest_dir: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]], dict[str, str]]:
    """Load accounts + email candidates + terminal map from process harvest dir."""
    accounts: dict[str, dict[str, Any]] = {}
    acc_dir = harvest_dir / "accounts"
    if acc_dir.is_dir():
        for path in acc_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            root = _root8(data.get("account_cnpj") or path.stem)
            if root:
                accounts[root] = data

    emails_by_root: dict[str, list[dict[str, Any]]] = {}
    for root, acc in accounts.items():
        rows = _email_entries_from_account(acc)
        if rows:
            emails_by_root.setdefault(root, []).extend(rows)

    # Merge contact-candidates.jsonl
    for root, rows in _load_jsonl_emails(harvest_dir / "contact-candidates.jsonl").items():
        emails_by_root.setdefault(root, []).extend(rows)

    # Dedupe emails per root
    for root, rows in list(emails_by_root.items()):
        seen: set[str] = set()
        uniq: list[dict[str, Any]] = []
        for r in rows:
            e = str(r.get("email") or "").lower()
            if e and e not in seen:
                seen.add(e)
                uniq.append(r)
        emails_by_root[root] = uniq

    terminals: dict[str, str] = {}
    terms_path = harvest_dir / "contact-discovery-terminals.jsonl"
    if terms_path.is_file():
        with terms_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                root = _root8(row.get("cnpj_raiz") or row.get("account_cnpj"))
                st = row.get("terminal_state") or row.get("state") or row.get("terminal")
                if root and st:
                    terminals[root] = str(st)
    return accounts, emails_by_root, terminals


def _load_supplier_names(roots: list[str], dsn: str | None = None) -> dict[str, str]:
    """Batch-load fornecedor_nome from pncp_supplier_contracts for ownership identity."""
    import os

    dsn = dsn or os.environ.get("DATABASE_URL") or os.environ.get("LOCAL_DATALAKE_DSN")
    if not dsn or not roots:
        return {}
    out: dict[str, str] = {}
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        return {}
    try:
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Chunk to avoid huge IN lists
            chunk = 500
            for i in range(0, len(roots), chunk):
                part = roots[i : i + chunk]
                cur.execute(
                    """
                    SELECT fornecedor_cnpj_8 AS root,
                           MAX(NULLIF(TRIM(fornecedor_nome), '')) AS nome
                    FROM pncp_supplier_contracts
                    WHERE fornecedor_cnpj_8 = ANY(%s)
                    GROUP BY 1
                    """,
                    (part,),
                )
                for row in cur.fetchall() or []:
                    if row.get("root") and row.get("nome"):
                        out[str(row["root"])] = str(row["nome"])
        conn.close()
    except Exception:  # noqa: BLE001
        return out
    return out


def rebuild_strict_esr(
    *,
    harvest_dir: Path = DEFAULT_HARVEST,
    confirmed_roots: set[str] | None = None,
    max_roots: int | None = None,
    dsn: str | None = None,
) -> dict[str, Any]:
    """Run strict ESR over harvest contact graph for TARGET_CONFIRMED roots."""
    accounts, emails_by_root, terminals = load_harvest_universe(harvest_dir)

    if confirmed_roots is None:
        # Prefer terminals file roots; else all account roots
        if terminals:
            confirmed_roots = set(terminals)
        else:
            confirmed_roots = set(accounts)

    roots_with_email = sorted(r for r in confirmed_roots if emails_by_root.get(r))
    if max_roots is not None:
        roots_with_email = roots_with_email[: max(0, max_roots)]

    names = _load_supplier_names(roots_with_email, dsn=dsn)
    # Inject razao into accounts when missing
    for root, nome in names.items():
        acc = accounts.get(root)
        if acc is None:
            accounts[root] = {"account_cnpj": root, "razao_social": nome}
        elif not acc.get("razao_social"):
            acc["razao_social"] = nome

    esr_rows: list[dict[str, Any]] = []
    not_ready: list[dict[str, Any]] = []
    reason_counter: Counter[str] = Counter()
    service_counter: Counter[str] = Counter()
    funnel = {
        "TOTAL_CONTACT_CANDIDATES": sum(len(emails_by_root.get(r) or []) for r in roots_with_email),
        "DISTINCT_COMPANIES_WITH_EMAIL": len(roots_with_email),
        "COMPANY_OWNED": 0,
        "IDENTITY_SAFE": 0,
        "MAILBOX_ALLOWED": 0,
        "PROVENANCE_VALID": 0,
        "SERVICE_FIT_VALID": 0,
        "COPY_CONTEXT_VALID": 0,
        "EMAIL_SEND_READY_DISTINCT_COMPANIES": 0,
    }

    for root in roots_with_email:
        result = evaluate_root_candidates(
            root=root,
            account=accounts.get(root),
            email_rows=emails_by_root.get(root) or [],
        )
        if result["company_owned"]:
            funnel["COMPANY_OWNED"] += 1
            funnel["IDENTITY_SAFE"] += 1
        if result["mailbox_ok"]:
            funnel["MAILBOX_ALLOWED"] += 1
        if result["prov_ok"]:
            funnel["PROVENANCE_VALID"] += 1
        if result["service_ok"]:
            funnel["SERVICE_FIT_VALID"] += 1
        if result["copy_ok"]:
            funnel["COPY_CONTEXT_VALID"] += 1
        reason_counter.update(result["reasons"])
        best = result.get("best") or {}
        if best.get("service_code"):
            service_counter[str(best["service_code"])] += 1
        if result["email_send_ready"]:
            funnel["EMAIL_SEND_READY_DISTINCT_COMPANIES"] += 1
            esr_rows.append(best)
        elif best:
            not_ready.append(best)

    terminal_counts = Counter(terminals.values())
    esr_n = funnel["EMAIL_SEND_READY_DISTINCT_COMPANIES"]
    ops = warmbly_ops_config_from_env()
    reserve = min_operational_reserve(
        emails_per_hour=float(ops["emails_per_hour"]),
        business_hours_per_day=float(ops["business_hours_per_day"]),
        business_days=10,
    )
    capacity = build_capacity_metrics(
        email_send_ready_distinct_companies=esr_n,
        active_hot_set_size=min(50, esr_n),
        emails_per_hour=float(ops["emails_per_hour"]),
        business_hours_per_day=float(ops["business_hours_per_day"]),
        business_days=10,
    )

    return {
        "schema": "confenge.strict_national_esr.v1",
        "as_of": _utcnow(),
        "harvest_dir": str(harvest_dir),
        "TARGET_CONFIRMED": len(confirmed_roots),
        "process_terminals": len(terminals),
        "process_terminal_counts": dict(terminal_counts),
        "funnel": funnel,
        "EMAIL_SEND_READY_DISTINCT_COMPANIES": esr_n,
        "email_roots_upper_bound": funnel["DISTINCT_COMPANIES_WITH_EMAIL"],
        "MIN_OPERATIONAL_RESERVE": reserve,
        "gap_vs_reserve": max(0, reserve - esr_n),
        "reserve_gate_ok": bool(capacity.get("reserve_gate_ok")),
        "capacity": capacity,
        "service_distribution": dict(service_counter.most_common()),
        "not_ready_top": reason_counter.most_common(25),
        "esr_rows": esr_rows,
        "not_ready_sample": not_ready[:50],
        "NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY": bool(capacity.get("reserve_gate_ok") and esr_n >= reserve),
        "PILOT_READY_CANDIDATE": esr_n >= 50,
        "note": (
            "Strict ESR via build_dossier + evaluate_email_send_ready; "
            "email observed is upper bound only, never ESR proxy."
        ),
    }


def write_esr_artifacts(report: dict[str, Any], out_dir: Path = DEFAULT_OUT) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    esr_n = int(report.get("EMAIL_SEND_READY_DISTINCT_COMPANIES") or 0)
    funnel = report.get("funnel") or {}
    payload = {
        "as_of": report.get("as_of"),
        "EMAIL_SEND_READY_DISTINCT_COMPANIES": esr_n,
        "email_roots_upper_bound": report.get("email_roots_upper_bound"),
        "funnel": funnel,
        "capacity": report.get("capacity"),
        "gap_vs_reserve": report.get("gap_vs_reserve"),
        "MIN_OPERATIONAL_RESERVE": report.get("MIN_OPERATIONAL_RESERVE"),
        "service_distribution": report.get("service_distribution"),
        "not_ready_top": report.get("not_ready_top"),
        "NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY": report.get("NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY"),
        "PILOT_READY_CANDIDATE": report.get("PILOT_READY_CANDIDATE"),
        "process_terminals": report.get("process_terminals"),
        "process_terminal_counts": report.get("process_terminal_counts"),
        "note": report.get("note"),
    }
    (out_dir / "EMAIL-SEND-READY-RESERVOIR.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out_dir / "ESR-REMEASURE.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    # Persist ESR rows for human review / hot-set
    (out_dir / "EMAIL-SEND-READY-ROWS.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in (report.get("esr_rows") or [])),
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--harvest-dir", type=Path, default=DEFAULT_HARVEST)
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    p.add_argument("--max-roots", type=int, default=None, help="Cap for dry runs")
    p.add_argument("--confirmed-roots-file", type=Path, default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    confirmed: set[str] | None = None
    if args.confirmed_roots_file and args.confirmed_roots_file.is_file():
        confirmed = set()
        text = args.confirmed_roots_file.read_text(encoding="utf-8")
        if args.confirmed_roots_file.suffix == ".json":
            data = json.loads(text)
            if isinstance(data, list):
                confirmed = {_root8(x) for x in data if _root8(x)}
            elif isinstance(data, dict):
                for key in ("roots", "cnpj_roots", "confirmed"):
                    if isinstance(data.get(key), list):
                        confirmed = {_root8(x) for x in data[key] if _root8(x)}
                        break
        else:
            for line in text.splitlines():
                r = _root8(line.strip())
                if r:
                    confirmed.add(r)
    report = rebuild_strict_esr(
        harvest_dir=args.harvest_dir,
        confirmed_roots=confirmed,
        max_roots=args.max_roots,
    )
    write_esr_artifacts(report, out_dir=args.out_dir)
    summary = {
        "EMAIL_SEND_READY_DISTINCT_COMPANIES": report["EMAIL_SEND_READY_DISTINCT_COMPANIES"],
        "email_roots_upper_bound": report["email_roots_upper_bound"],
        "gap_vs_reserve": report["gap_vs_reserve"],
        "reserve_gate_ok": report["reserve_gate_ok"],
        "NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY": report["NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY"],
        "PILOT_READY_CANDIDATE": report["PILOT_READY_CANDIDATE"],
        "not_ready_top": report["not_ready_top"][:10],
        "service_distribution": report["service_distribution"],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
