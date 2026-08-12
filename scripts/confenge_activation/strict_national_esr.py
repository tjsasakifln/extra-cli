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
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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
from scripts.confenge_outreach_pipeline.integrity_sample import compose_body, compose_subject
from scripts.linkage.keys import is_valid_cnpj14
from scripts.warmbly_bridge.export import ExportConfig, export_outreach

DEFAULT_HARVEST = Path("artifacts/confenge/process-first-national-confirmed")
DEFAULT_OUT = Path("artifacts/confenge/national-commercial-ready")

_EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
_PILOT_ENGINEERING_HOOK_RE = re.compile(
    r"engenhari|obra|paviment|asfalt|drenag|saneamento|esgoto|rede de água|"
    r"construç|reforma|manutenção predial|infraestrutura|terraplen|topografi|"
    r"projeto executivo|fiscalização",
    re.I,
)


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _root8(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) >= 14:
        return digits[:8]
    if len(digits) >= 8:
        return digits[:8]
    return digits


def _cnpj14(value: Any, *, root: str | None = None) -> str | None:
    """Return a defensible full CNPJ; never manufacture branch/check digits."""
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) != 14 or not is_valid_cnpj14(digits):
        return None
    if root and digits[:8] != root:
        return None
    return digits


def _source_host(source_url: str | None) -> str | None:
    if not source_url:
        return None
    raw = str(source_url).strip()
    if not raw:
        return None
    try:
        return (urlparse(raw if "://" in raw else f"https://{raw}").hostname or "").lower() or None
    except ValueError:
        return None


def _company_authored(row: dict[str, Any]) -> bool:
    """Accept company authorship only when the source explicitly proves it."""
    if row.get("company_authored_likely") is True or row.get("found_on_company_document") is True:
        return True
    return str(row.get("source_type") or "").strip().lower() in {
        "site",
        "contact_page",
        "official_site",
        "company_site",
        "website",
    }


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
                    "epistemic_class": row.get("epistemic_class") or "OBSERVED_PUBLIC",
                    "pattern_guessed": bool(row.get("pattern_guessed")),
                    "company_authored_likely": _company_authored(row),
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
                    "epistemic_class": row.get("epistemic_class") or "OBSERVED_PUBLIC",
                    "pattern_guessed": bool(row.get("pattern_guessed")),
                    "company_authored_likely": _company_authored(row),
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
                        "epistemic_class": row.get("epistemic_best") or "OBSERVED_PUBLIC",
                        "pattern_guessed": bool(row.get("pattern_guessed")),
                        "company_authored_likely": _company_authored(row),
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
                    "company_authored_likely": _company_authored(row),
                    "epistemic_class": row.get("epistemic_class") or "OBSERVED_PUBLIC",
                    "provenance_chain": row.get("provenance_chain") or [],
                }
            )
    return by_root


def _resolve_ownership_for_email(
    *,
    email: str,
    root: str,
    cnpj14: str | None,
    razao: str | None,
    source_type: str,
    source_url: str | None,
    company_authored: bool,
) -> tuple[str, str]:
    """Return (ownership_status, verification_status)."""
    if not cnpj14 or not is_valid_cnpj14(cnpj14) or cnpj14[:8] != root:
        return "UNRESOLVED", VerificationStatus.OBSERVED.value
    source_kind = (source_type or "").strip().lower()
    if not company_authored and source_kind not in {
        "site",
        "contact_page",
        "official_site",
        "company_site",
        "website",
    }:
        return "UNRESOLVED", VerificationStatus.OBSERVED.value
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
    source_host = _source_host(source_url)
    email_domain = email.rsplit("@", 1)[-1].lower() if "@" in email else None
    official_domain = email_domain if source_host == email_domain else None
    ctx = OwnershipContext(
        cnpj14=cnpj14,
        razao_social=razao,
        official_domain=official_domain,
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
    cnpj14: str | None = None,
) -> dict[str, Any]:
    """Account intelligence → canonical service + message spine package."""
    actual_cnpj14 = _cnpj14(cnpj14, root=root)
    if actual_cnpj14 is None:
        candidates = [
            (account or {}).get("account_cnpj"),
            (account or {}).get("cnpj14"),
            *(c.get("fornecedor_cnpj") for c in contracts),
        ]
        actual_cnpj14 = next((x for raw in candidates if (x := _cnpj14(raw, root=root))), None)
    raw = {
        "cnpj14": actual_cnpj14,
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
    actual_cnpj14 = _cnpj14(company.get("cnpj14"), root=root)
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
            cnpj14=actual_cnpj14,
            razao=razao,
            source_type=str(row.get("source_type") or "public_process_document"),
            source_url=row.get("source_url"),
            company_authored=bool(row.get("company_authored_likely", False)),
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
            provenance_chain=list(row.get("provenance_chain") or []),
            canonical_universe_member=True,
        )
        for r in result.reasons or []:
            reasons_agg[str(r)[:120]] += 1
        # Failure-only counters for loss analysis (pass reasons tracked separately)
        if "service_fit_unsupported" in (result.reasons or []):
            reasons_agg["FAIL:service_fit_unsupported"] += 1
        elif "service_fit_supported" in (result.reasons or []):
            any_service_ok = True
            reasons_agg["PASS:service_fit_supported"] += 1
        if "copy_context_complete" in (result.reasons or []) or result.email_send_ready:
            any_copy_ok = True
        if any("provenance_trust" in str(x) for x in (result.reasons or [])):
            any_prov_ok = True

        payload = {
            "cnpj_raiz": root,
            "cnpj14": actual_cnpj14,
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
        if actual_cnpj14 is None:
            payload["reasons"] = list(payload["reasons"]) + ["invalid_or_missing_cnpj14"]
            payload["email_send_ready"] = False
        if payload["email_send_ready"]:
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


def _load_supplier_identities(roots: list[str], dsn: str | None = None) -> dict[str, dict[str, str]]:
    """Load the most evidenced real CNPJ14/name per root from the canonical lake."""
    import os

    dsn = dsn or os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL")
    if not dsn or not roots:
        return {}
    out: dict[str, dict[str, str]] = {}
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
                    WITH ranked AS (
                      SELECT fornecedor_cnpj_8 AS root,
                             regexp_replace(COALESCE(fornecedor_cnpj, ''), '\\D', '', 'g') AS cnpj14,
                             MAX(NULLIF(TRIM(fornecedor_nome), '')) AS nome,
                             COUNT(*) AS evidence_count,
                             ROW_NUMBER() OVER (
                               PARTITION BY fornecedor_cnpj_8
                               ORDER BY COUNT(*) DESC,
                                        MAX(COALESCE(data_assinatura, data_publicacao)) DESC NULLS LAST
                             ) AS rn
                      FROM pncp_supplier_contracts
                      WHERE fornecedor_cnpj_8 = ANY(%s)
                        AND COALESCE(is_active, TRUE) IS TRUE
                        AND length(
                          regexp_replace(COALESCE(fornecedor_cnpj, ''), '\\D', '', 'g')
                        ) = 14
                      GROUP BY fornecedor_cnpj_8,
                               regexp_replace(COALESCE(fornecedor_cnpj, ''), '\\D', '', 'g')
                    )
                    SELECT root, cnpj14, nome
                    FROM ranked
                    WHERE rn = 1
                    """,
                    (part,),
                )
                for row in cur.fetchall() or []:
                    root = str(row.get("root") or "")
                    cnpj = _cnpj14(row.get("cnpj14"), root=root)
                    if root and cnpj and row.get("nome"):
                        out[root] = {"cnpj14": cnpj, "razao_social": str(row["nome"])}
        conn.close()
    except Exception:  # noqa: BLE001
        return out
    return out


def load_contracts_by_root(
    roots: list[str],
    *,
    dsn: str,
    per_root: int = 30,
) -> dict[str, list[dict[str, Any]]]:
    """Hydrate current public-contract evidence for a small verified cohort."""
    if not dsn:
        raise ValueError("dsn is required to hydrate a pilot cohort")
    if not roots:
        return {}
    import psycopg2
    import psycopg2.extras

    out: dict[str, list[dict[str, Any]]] = {root: [] for root in roots}
    with psycopg2.connect(dsn) as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            WITH ranked AS (
              SELECT fornecedor_cnpj_8,
                     fornecedor_cnpj,
                     fornecedor_nome,
                     contrato_id,
                     objeto_contrato,
                     orgao_nome,
                     uf,
                     municipio,
                     valor_total,
                     data_assinatura,
                     data_publicacao,
                     data_inicio,
                     data_fim,
                     ROW_NUMBER() OVER (
                       PARTITION BY fornecedor_cnpj_8
                       ORDER BY COALESCE(data_assinatura, data_publicacao) DESC NULLS LAST,
                                valor_total DESC NULLS LAST
                     ) AS rn
              FROM pncp_supplier_contracts
              WHERE fornecedor_cnpj_8 = ANY(%s)
                AND COALESCE(is_active, TRUE) IS TRUE
            )
            SELECT * FROM ranked WHERE rn <= %s
            ORDER BY fornecedor_cnpj_8, rn
            """,
            (roots, max(1, int(per_root))),
        )
        for raw in cur.fetchall() or []:
            row = dict(raw)
            root = str(row.get("fornecedor_cnpj_8") or "")
            out.setdefault(root, []).append(
                {
                    "contract_id": row.get("contrato_id"),
                    "numero_controle_pncp": row.get("contrato_id"),
                    "objeto_contrato": row.get("objeto_contrato"),
                    "orgao_nome": row.get("orgao_nome"),
                    "uf": row.get("uf"),
                    "municipio": row.get("municipio"),
                    "valor_total": row.get("valor_total"),
                    "data_inicio": row.get("data_inicio") or row.get("data_assinatura"),
                    "data_fim": row.get("data_fim"),
                    "data_publicacao": row.get("data_publicacao") or row.get("data_assinatura"),
                    "fornecedor_cnpj": row.get("fornecedor_cnpj"),
                    "fornecedor_nome": row.get("fornecedor_nome"),
                }
            )
    return out


def _primary_contract(dossier: dict[str, Any], contracts: list[dict[str, Any]]) -> dict[str, Any]:
    evidence_ids = list((dossier.get("message_spine") or {}).get("fact_evidence_ids") or [])
    wanted = {str(value).removeprefix("cf-contract-").removeprefix("ev-contract-") for value in evidence_ids}
    chosen = next(
        (row for row in contracts if str(row.get("contract_id") or "") in wanted),
        contracts[0] if contracts else {},
    )
    return {
        "contract_id": chosen.get("contract_id"),
        "agency": chosen.get("orgao_nome"),
        "object": chosen.get("objeto_contrato"),
        "uf": chosen.get("uf"),
        "value_brl": chosen.get("valor_total"),
        "publication_date": chosen.get("data_publicacao"),
        "start_date": chosen.get("data_inicio"),
        "end_date": chosen.get("data_fim"),
    }


def _pilot_message(dossier: dict[str, Any]) -> dict[str, str]:
    """Use the existing composer while leading with evidence, not score prose."""
    copy_dossier = dict(dossier)
    copy_dossier["why_this_account"] = ""
    copy_dossier["why_you"] = ""
    for field in ("observed_fact", "body_seed_fact"):
        copy_dossier[field] = " ".join(str(copy_dossier.get(field) or "").split())
    spine = dict(copy_dossier.get("message_spine") or {})
    for field in ("observed_fact", "why_now", "body_seed_fact"):
        spine[field] = " ".join(str(spine.get(field) or "").split())
    copy_dossier["message_spine"] = spine
    subject = " ".join(compose_subject(copy_dossier).split())
    if len(subject) > 78:
        subject = subject[:78].rsplit(" ", 1)[0].rstrip(" :/-")
    return {"subject": subject, "body": compose_body(copy_dossier)}


def _pilot_access_rank(candidate: dict[str, Any]) -> tuple[int, int, int, str]:
    mailbox = str(candidate.get("mailbox_purpose") or "")
    mailbox_order = {
        "COMERCIAL": 0,
        "LICITACOES": 1,
        "GENERIC_CONTACT": 2,
        "UNKNOWN": 3,
    }
    contracts = int(candidate.get("n_contracts") or 0)
    sweet_spot = 0 if 3 <= contracts <= 20 else 1
    orgs = int(candidate.get("n_agencies") or 0)
    return (mailbox_order.get(mailbox, 9), sweet_spot, orgs, str(candidate.get("cnpj14") or ""))


def _sanitize_pilot_contract_dates(contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prevent a future start/publication from being described as a recent event."""
    today = date.today()
    sanitized: list[dict[str, Any]] = []
    for contract in contracts:
        row = dict(contract)
        for field in ("data_inicio", "data_publicacao", "start_date", "publication_date"):
            raw = str(row.get(field) or "")[:10]
            try:
                value = date.fromisoformat(raw)
            except ValueError:
                continue
            if value > today:
                row[field] = None
        sanitized.append(row)
    return sanitized


def build_pilot_review(
    seed_rows: list[dict[str, Any]],
    *,
    contracts_by_root: dict[str, list[dict[str, Any]]],
    target_size: int = 20,
) -> dict[str, Any]:
    """Create a small, diverse and human-reviewable cohort from verified ESR seeds."""
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    def reject(seed: dict[str, Any], reason: str) -> None:
        rejected.append(
            {
                "cnpj14": seed.get("cnpj14"),
                "empresa": seed.get("razao_social") or seed.get("company_name"),
                "email": seed.get("email") or seed.get("contact_email"),
                "reason": reason,
            }
        )

    for seed in seed_rows:
        root = _root8(seed.get("root") or seed.get("cnpj14"))
        cnpj14 = _cnpj14(seed.get("cnpj14"), root=root)
        company_name = str(seed.get("razao_social") or seed.get("company_name") or "").strip()
        email = str(seed.get("email") or seed.get("contact_email") or "").strip().lower()
        source_type = str(seed.get("source_type") or "")
        source_url = seed.get("source_url")
        provenance_chain = list(seed.get("provenance_chain") or [])
        if not cnpj14 or not company_name:
            reject(seed, "invalid_or_missing_company_identity")
            continue
        if not email or "@" not in email:
            reject(seed, "missing_email")
            continue
        if seed.get("dnc") or seed.get("do_not_contact"):
            reject(seed, "do_not_contact")
            continue
        if seed.get("bounced") or seed.get("hard_bounce"):
            reject(seed, "bounce_suppressed")
            continue
        if not seed.get("provenance_chain_valid") or not provenance_chain or not source_url:
            reject(seed, "provenance_not_defensible")
            continue
        if str(seed.get("ownership_status") or "") not in {"COMPANY_OWNED", "HUMAN_CONFIRMED"}:
            reject(seed, "ownership_not_defensible")
            continue
        if str(seed.get("verification_status") or "") not in {"VERIFIED", "HUMAN_CONFIRMED"}:
            reject(seed, "email_not_verified")
            continue
        folded_name = company_name.upper()
        if "CONSORCIO" in folded_name or "CONSÓRCIO" in folded_name:
            reject(seed, "complex_consortium_reserved_for_abm")
            continue
        if "RECUPERACAO JUDICIAL" in folded_name or "RECUPERAÇÃO JUDICIAL" in folded_name:
            reject(seed, "judicial_recovery_risk")
            continue
        mailbox = classify_mailbox_purpose(email)
        if mailbox.send_blocked or mailbox.purpose == "FINANCEIRO":
            reject(seed, f"low_utility_mailbox:{mailbox.purpose}")
            continue

        contracts = contracts_by_root.get(root) or []
        matching_contracts = [row for row in contracts if _root8(row.get("fornecedor_cnpj")) in {"", root}]
        if not matching_contracts:
            reject(seed, "no_current_public_contract_evidence")
            continue
        pilot_contracts = _sanitize_pilot_contract_dates(matching_contracts)
        dossier = build_company_package(
            root=root,
            account={"account_cnpj": cnpj14, "razao_social": company_name},
            contracts=pilot_contracts,
            razao=company_name,
            cnpj14=cnpj14,
        )
        hook_object = str(dossier.get("observed_fact") or "").split("; órgão:", 1)[0]
        if not _PILOT_ENGINEERING_HOOK_RE.search(hook_object):
            reject(seed, "primary_hook_not_engineering_specific")
            continue
        service_code = str((dossier.get("primary_service") or {}).get("service_id") or "")
        readiness = evaluate_email_send_ready(
            company=dossier,
            email=email,
            ownership_status=str(seed.get("ownership_status")),
            verification_status=str(seed.get("verification_status")),
            dnc=False,
            bounce=False,
            contact_fresh=True,
            service_code=service_code,
            factual_evidence=True,
            evidence_ids=list(dossier.get("evidence_ids") or []),
            require_copy_context=True,
            source_type=source_type,
            source_url=source_url,
            provenance_chain=provenance_chain,
            contact={
                "email": email,
                "ownership_status": seed.get("ownership_status"),
                "verification_status": seed.get("verification_status"),
                "source_type": source_type,
                "source_url": source_url,
                "provenance_chain": provenance_chain,
            },
            canonical_universe_member=True,
        )
        if not readiness.email_send_ready:
            reasons = [str(reason) for reason in (readiness.reasons or [])][:4]
            reject(seed, f"email_send_ready_failed:{','.join(reasons)}")
            continue
        agencies = {str(row.get("orgao_nome") or "").strip() for row in matching_contracts}
        primary_contract = _primary_contract(dossier, pilot_contracts)
        message = _pilot_message(dossier)
        candidate = {
            "cnpj14": cnpj14,
            "cnpj_raiz": root,
            "empresa": company_name,
            "razao_social": company_name,
            "contact": email,
            "email": email,
            "mailbox_purpose": mailbox.purpose,
            "ownership_status": seed.get("ownership_status"),
            "verification_status": seed.get("verification_status"),
            "source_type": source_type,
            "source_url": source_url,
            "provenance_chain": provenance_chain,
            "email_send_ready": True,
            "recommended_service": service_code,
            "service_name": (dossier.get("primary_service") or {}).get("label"),
            "service_fit_rationale": dossier.get("service_fit_rationale"),
            "why_this_company": dossier.get("why_this_account"),
            "why_this_account": dossier.get("why_this_account"),
            "why_now": (dossier.get("message_spine") or {}).get("why_now"),
            "observed_fact": dossier.get("observed_fact"),
            "primary_contract": primary_contract,
            "supporting_evidence": [primary_contract],
            "micro_offer": dossier.get("micro_offer_code"),
            "cta": dossier.get("cta"),
            "message": message,
            "draft": message,
            "evidence_ids": list(dossier.get("evidence_ids") or []),
            "supporting_signal_ids": list((dossier.get("primary_service") or {}).get("supporting_signal_ids") or []),
            "n_contracts": len(matching_contracts),
            "n_agencies": len(agencies - {""}),
            "risks": [],
            "review_status": "HUMAN_REVIEW_PENDING",
            "review_decision": None,
            "allowed_decisions": ["APPROVE", "REJECT", "SKIP"],
        }
        if len(matching_contracts) >= 30:
            candidate["risks"].append("portfolio_capped_at_30; access complexity requires human sanity check")
        candidates.append(candidate)

    # One company, one pilot lead. Keep the most operationally useful contact
    # when an upstream seed contains multiple rows for the same valid CNPJ.
    unique_candidates: dict[str, dict[str, Any]] = {}
    for row in candidates:
        key = str(row.get("cnpj14") or "")
        incumbent = unique_candidates.get(key)
        if incumbent is None or _pilot_access_rank(row) < _pilot_access_rank(incumbent):
            if incumbent is not None:
                reject(incumbent, "duplicate_company_candidate")
            unique_candidates[key] = row
        else:
            reject(row, "duplicate_company_candidate")
    candidates = list(unique_candidates.values())

    # Keep very broad/complex accounts in ABM even when a commercial mailbox exists.
    eligible: list[dict[str, Any]] = []
    for row in candidates:
        if int(row.get("n_contracts") or 0) >= 30 and int(row.get("n_agencies") or 0) >= 18:
            rejected.append(
                {
                    "cnpj14": row.get("cnpj14"),
                    "empresa": row.get("empresa"),
                    "email": row.get("email"),
                    "reason": "high_access_complexity_reserved_for_abm",
                }
            )
            continue
        eligible.append(row)

    # Diversity is a pilot sampling concern, not a new global score: rotate services,
    # preferring useful mailboxes and manageable portfolios within each service.
    by_service: dict[str, list[dict[str, Any]]] = {}
    for row in eligible:
        by_service.setdefault(str(row.get("recommended_service") or ""), []).append(row)
    for rows in by_service.values():
        rows.sort(key=_pilot_access_rank)
    selected: list[dict[str, Any]] = []
    service_names = sorted(by_service)
    while len(selected) < max(0, target_size):
        progressed = False
        for service in service_names:
            rows = by_service[service]
            if rows and len(selected) < target_size:
                selected.append(rows.pop(0))
                progressed = True
        if not progressed:
            break

    selected_ids = {id(row) for row in selected}
    for row in eligible:
        if id(row) not in selected_ids:
            rejected.append(
                {
                    "cnpj14": row.get("cnpj14"),
                    "empresa": row.get("empresa"),
                    "email": row.get("email"),
                    "reason": "qualified_reservoir_not_selected_for_first_cohort",
                }
            )
    return {
        "schema": "confenge.pilot_human_review.v1",
        "generated_at": _utcnow(),
        "target_size": target_size,
        "status": "HUMAN_REVIEW_PENDING",
        "n": len(selected),
        "email_send_ready": sum(1 for row in selected if row.get("email_send_ready")),
        "approved": 0,
        "service_distribution": dict(Counter(row["recommended_service"] for row in selected)),
        "leads": selected,
        "rejections": rejected,
    }


def build_pilot_feed_inputs(
    review: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Translate reviewed candidates through the existing Warmbly bridge contract."""
    universe: list[dict[str, Any]] = []
    intelligence: list[dict[str, Any]] = []
    contacts: list[dict[str, Any]] = []
    for rank, lead in enumerate(review.get("leads") or [], 1):
        contract = lead.get("primary_contract") or {}
        evidence_id = f"pncp-contract:{contract.get('contract_id')}"
        source_host = _source_host(lead.get("source_url"))
        universe.append(
            {
                "cnpj14": lead.get("cnpj14"),
                "razao_social": lead.get("razao_social"),
                "rank": rank,
                "tier": "PILOT",
                "target_fit_class": "TARGET_CONFIRMED",
                "target_fit_fresh": True,
                "canonical_universe_member": True,
                "official_domain": source_host,
                "construction_evidence": {
                    "sector_fit": "CONFIRMED_ENGINEERING",
                    "target_fit_class": "TARGET_CONFIRMED",
                    "relevant_contract_count": lead.get("n_contracts"),
                },
                "portfolio": {"pass_contract_count": lead.get("n_contracts")},
                "contracts": [
                    {
                        "id": contract.get("contract_id"),
                        "object": contract.get("object"),
                        "agency": contract.get("agency"),
                        "uf": contract.get("uf"),
                        "value_brl": contract.get("value_brl"),
                        "publication_date": contract.get("publication_date"),
                        "start_date": contract.get("start_date"),
                        "end_date": contract.get("end_date"),
                    }
                ],
            }
        )
        intelligence.append(
            {
                "cnpj14": lead.get("cnpj14"),
                "why_now": {
                    "code": "PUBLIC_CONTRACT_WINDOW",
                    "summary": lead.get("why_now"),
                    "observed_at": contract.get("publication_date") or contract.get("end_date"),
                    "confidence": "HIGH",
                    "evidence_ids": [evidence_id],
                },
                "offer": {
                    "service_code": lead.get("recommended_service"),
                    "canonical_service_code": lead.get("recommended_service"),
                    "extra_cli_service_id": lead.get("recommended_service"),
                    "service_name": lead.get("service_name"),
                    "entry_offer": lead.get("cta"),
                    "micro_offer_code": lead.get("micro_offer"),
                    "rationale": lead.get("service_fit_rationale"),
                },
                "messaging": {
                    "fact_to_mention": lead.get("observed_fact"),
                    "question_to_ask": lead.get("cta"),
                    "cta": lead.get("cta"),
                    "why_now": lead.get("why_now"),
                    "claims_to_avoid": [
                        "dor confirmada",
                        "erro contratual confirmado",
                    ],
                },
                "evidence": [
                    {
                        "id": evidence_id,
                        "type": "PNCP_CONTRACT",
                        "title": "Contrato público observado",
                        "document": contract.get("contract_id"),
                        "date": contract.get("publication_date"),
                        "synthesis": lead.get("observed_fact"),
                        "epistemic_class": "CONFIRMED_FACT",
                        "reliability": "HIGH",
                    }
                ],
                "primary_service": {
                    "service_id": lead.get("recommended_service"),
                    "service_code": lead.get("recommended_service"),
                    "supporting_signal_ids": lead.get("supporting_signal_ids") or [],
                    "evidence_ids": [evidence_id],
                },
                "service_candidates": [
                    {
                        "service_id": lead.get("recommended_service"),
                        "supporting_signal_ids": lead.get("supporting_signal_ids") or [],
                        "evidence_ids": [evidence_id],
                    }
                ],
                "observed_fact": lead.get("observed_fact"),
                "why_this_account": lead.get("why_this_account"),
                "cta": lead.get("cta"),
                "evidence_ids": [evidence_id],
            }
        )
        contacts.append(
            {
                "cnpj14": lead.get("cnpj14"),
                "contacts": [
                    {
                        "email": lead.get("email"),
                        "ownership_status": lead.get("ownership_status"),
                        "verification_status": lead.get("verification_status"),
                        "source_type": lead.get("source_type"),
                        "source_url": lead.get("source_url"),
                        "provenance": {
                            "source_type": lead.get("source_type"),
                            "source_url": lead.get("source_url"),
                            "provenance_chain": lead.get("provenance_chain") or [],
                        },
                        "enrollable": True,
                        "recommended": True,
                        "email_send_ready": True,
                    }
                ],
            }
        )
    return universe, intelligence, contacts


def write_pilot_feed(
    review: dict[str, Any],
    out_dir: Path,
    *,
    authoritative_universe: list[dict[str, Any]] | None = None,
    target_fit_snapshot: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Emit confenge.outreach.v1 only with a declared full decision universe.

    A reviewed pilot is a selection overlay, not an authoritative account
    snapshot.  Exporting only its send-ready rows would let omitted downgrades
    retain stale authorization at the consumer.
    """
    pilot_universe, intelligence, contacts = build_pilot_feed_inputs(review)
    if not pilot_universe:
        raise ValueError("pilot feed requested for a review with no leads")
    if authoritative_universe is None or target_fit_snapshot is None:
        raise ValueError(
            "refusing send-ready-only confenge.outreach.v1: provide the full "
            "authoritative_universe and target_fit_snapshot"
        )
    source_dir = out_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "universe": source_dir / "universe.jsonl",
        "intelligence": source_dir / "account-intelligence.jsonl",
        "contacts": source_dir / "contacts.jsonl",
        "target_fit": source_dir / "target-fit-snapshot.jsonl",
    }
    for key, rows in (
        ("universe", authoritative_universe),
        ("intelligence", intelligence),
        ("contacts", contacts),
        ("target_fit", target_fit_snapshot),
    ):
        paths[key].write_text(
            "".join(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in rows),
            encoding="utf-8",
        )
    return export_outreach(
        ExportConfig(
            universe=paths["universe"],
            account_intelligence=paths["intelligence"],
            contacts=paths["contacts"],
            target_fit_snapshot=paths["target_fit"],
            expected_universe_count=len(authoritative_universe),
            out_dir=out_dir,
            max_leads_per_chunk=max(1, len(authoritative_universe)),
            system="extra-cli-confenge-pilot",
        )
    )


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

    identities = _load_supplier_identities(roots_with_email, dsn=dsn)
    # Inject only identities observed in the canonical datalake.
    for root, identity in identities.items():
        acc = accounts.get(root)
        if acc is None:
            accounts[root] = {
                "account_cnpj": identity["cnpj14"],
                "razao_social": identity["razao_social"],
            }
        else:
            acc["account_cnpj"] = identity["cnpj14"]
            if not acc.get("razao_social"):
                acc["razao_social"] = identity["razao_social"]

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
        # Only failure reasons go into loss/not_ready_top (never PASS: prefixes)
        for reason, n in (result.get("reasons") or Counter()).items():
            r = str(reason)
            if r.startswith("PASS:") or r in {
                "service_fit_supported",
                "all_gates_pass",
                "domain_aligned_with_company",
                "copy_context_complete",
            }:
                continue
            if r.startswith("provenance_trust:") and "REAL_OBSERVED" in r:
                continue
            if r.startswith("service_code:") and result.get("service_ok"):
                continue
            reason_counter[r] += int(n)
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

    # Ontology health: true failures of service fit among evaluated email roots
    service_fit_unsupported = int(reason_counter.get("FAIL:service_fit_unsupported", 0)) + int(
        reason_counter.get("service_fit_unsupported", 0)
    )
    service_fit_ok = service_fit_unsupported == 0

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
        "service_fit_unsupported_count": service_fit_unsupported,
        "service_fit_ontology_ok": service_fit_ok,
        "esr_rows": esr_rows,
        "not_ready_sample": not_ready[:50],
        "NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY": bool(capacity.get("reserve_gate_ok") and esr_n >= reserve),
        "PILOT_READY_CANDIDATE": esr_n >= 50,
        "note": (
            "Strict ESR via build_dossier + evaluate_email_send_ready; "
            "email observed is upper bound only, never ESR proxy. "
            "not_ready_top excludes PASS reasons (service_fit_supported, all_gates_pass)."
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


def write_pilot_review(review: dict[str, Any], out_dir: Path = DEFAULT_OUT) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "HUMAN-REVIEW-SAMPLE.json"
    path.write_text(
        json.dumps(review, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--harvest-dir", type=Path, default=DEFAULT_HARVEST)
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    p.add_argument("--max-roots", type=int, default=None, help="Cap for dry runs")
    p.add_argument("--confirmed-roots-file", type=Path, default=None)
    p.add_argument("--dsn", default=None, help="Canonical datalake DSN (defaults to LOCAL_DATALAKE_DSN)")
    p.add_argument("--pilot-seed-file", type=Path, default=None, help="Verified ESR seed JSON for Top20 review")
    p.add_argument("--pilot-size", type=int, default=20)
    return p


def main(argv: list[str] | None = None) -> int:
    import os

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
        dsn=args.dsn,
    )
    write_esr_artifacts(report, out_dir=args.out_dir)
    pilot_summary: dict[str, Any] | None = None
    if args.pilot_seed_file:
        if not args.pilot_seed_file.is_file():
            raise SystemExit(f"pilot seed file not found: {args.pilot_seed_file}")
        seed_payload = json.loads(args.pilot_seed_file.read_text(encoding="utf-8"))
        if isinstance(seed_payload, list):
            seed_rows = seed_payload
        elif isinstance(seed_payload, dict):
            seed_rows = seed_payload.get("leads") or seed_payload.get("rows") or []
        else:
            seed_rows = []
        if not seed_rows:
            raise SystemExit("pilot seed file contains no leads")
        pilot_dsn = args.dsn or os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL")
        if not pilot_dsn:
            raise SystemExit("--dsn or LOCAL_DATALAKE_DSN is required for pilot hydration")
        seed_roots = sorted({_root8(row.get("root") or row.get("cnpj14")) for row in seed_rows})
        contracts_by_root = load_contracts_by_root(seed_roots, dsn=pilot_dsn)
        review = build_pilot_review(
            seed_rows,
            contracts_by_root=contracts_by_root,
            target_size=max(0, args.pilot_size),
        )
        write_pilot_review(review, out_dir=args.out_dir)
        pilot_summary = {
            "n": review["n"],
            "email_send_ready": review["email_send_ready"],
            "approved": review["approved"],
            "service_distribution": review["service_distribution"],
            "rejections": len(review["rejections"]),
            "warmbly_feed": None,
            "warmbly_feed_note": (
                "Pilot selection is not an authoritative decision snapshot; "
                "use scripts.confenge_outreach_pipeline for feed export."
            ),
        }
    summary = {
        "EMAIL_SEND_READY_DISTINCT_COMPANIES": report["EMAIL_SEND_READY_DISTINCT_COMPANIES"],
        "email_roots_upper_bound": report["email_roots_upper_bound"],
        "gap_vs_reserve": report["gap_vs_reserve"],
        "reserve_gate_ok": report["reserve_gate_ok"],
        "NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY": report["NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY"],
        "PILOT_READY_CANDIDATE": report["PILOT_READY_CANDIDATE"],
        "not_ready_top": report["not_ready_top"][:10],
        "service_distribution": report["service_distribution"],
        "pilot_review": pilot_summary,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
