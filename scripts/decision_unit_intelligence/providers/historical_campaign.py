"""Tier 0: proprietary campaign artifacts already produced by extra-cli.

This is not Apollo. We start from CNPJ, contracts, QSA cadastre and
corporate channels already observed in the 2026-08-05 reajuste run.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from scripts.decision_unit_intelligence.decision_policy import (
    classify_person_relation,
    infer_service_from_text,
    is_legal_entity_name,
    normalize_observed_role,
)
from scripts.decision_unit_intelligence.evidence import make_evidence
from scripts.decision_unit_intelligence.models import (
    ChannelObservation,
    ChannelType,
    EpistemicClass,
    OwnershipStatus,
    PersonObservation,
    PersonRelation,
    SearchAttempt,
    normalize_cnpj,
    normalize_email,
    stable_id,
)
from scripts.decision_unit_intelligence.providers.base import InvestigationContext, ProviderResult

QSA_ITEM_RE = re.compile(r"^\s*([^()]+?)\s*(?:\(([^)]+)\))?\s*$")

PACKAGE_OBSERVATIONS = Path(__file__).resolve().parents[1] / "data" / "track_a_30.observations.json"

DEFAULT_SEARCH_ROOTS = (
    Path("artifacts/outreach/reajuste-2026-08-05-full-datalake-pr200"),
    Path("/mnt/d/extra consultoria/artifacts/outreach/reajuste-2026-08-05-full-datalake-pr200"),
    Path("/mnt/c/Users/tj_sa/Documents/Codex/2026-08-05/atra/outputs/lead-enrichment-14133"),
)


def parse_qsa_blob(blob: str | None) -> list[tuple[str, str | None]]:
    if not blob:
        return []
    people: list[tuple[str, str | None]] = []
    for chunk in re.split(r"[;|/]|(?:\s+e\s+)", str(blob)):
        chunk = chunk.strip(" \t-")
        if not chunk:
            continue
        m = QSA_ITEM_RE.match(chunk)
        if not m:
            continue
        name = re.sub(r"\s+", " ", m.group(1)).strip(" ,")
        role = (m.group(2) or "").strip() or None
        if len(name) >= 5 and not name.lower().startswith("nao ") and not is_legal_entity_name(name):
            people.append((name, role))
    return people


def _xlsx_rows(path: Path) -> list[dict[str, Any]]:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["CRM_Leads"]
    rows = list(ws.iter_rows(values_only=True))
    headers = list(rows[1])
    out = []
    for row in rows[2:]:
        rec = {str(headers[i]): row[i] if i < len(row) else None for i in range(len(headers))}
        rec["CNPJ"] = normalize_cnpj(str(rec.get("CNPJ") or ""))
        if rec["CNPJ"]:
            out.append(rec)
    return out


_INDEX_CACHE: dict[str, dict[str, Any]] | None = None


def load_campaign_index(extra_paths: list[Path] | None = None) -> dict[str, dict[str, Any]]:
    """Index real campaign rows by CNPJ. Missing files are skipped, not invented."""
    global _INDEX_CACHE
    if extra_paths is None and _INDEX_CACHE is not None:
        return _INDEX_CACHE
    index: dict[str, dict[str, Any]] = {}
    roots = list(DEFAULT_SEARCH_ROOTS)
    if extra_paths:
        roots = list(extra_paths) + roots
    if PACKAGE_OBSERVATIONS.exists():
        bundled = json.loads(PACKAGE_OBSERVATIONS.read_text(encoding="utf-8"))
        for rec in bundled.get("accounts") or []:
            key = normalize_cnpj(rec.get("cnpj"))
            if key:
                index.setdefault(key, {}).update(rec)
    for root in roots:
        top200 = root / "contact_enrichment_top200.json"
        if top200.exists():
            raw = json.loads(top200.read_text(encoding="utf-8"))
            for cnpj, rec in raw.items():
                key = normalize_cnpj(cnpj)
                index.setdefault(key, {}).update({"cnpj": key, **rec, "source": str(top200)})
        top30 = root / "ai_assisted_evidence_review_top30.json"
        if top30.exists():
            payload = json.loads(top30.read_text(encoding="utf-8"))
            for rec in payload.get("reviews") or []:
                key = normalize_cnpj(rec.get("cnpj"))
                if not key:
                    continue
                slot = index.setdefault(key, {"cnpj": key})
                slot["legal_name"] = rec.get("fornecedor") or slot.get("legal_name") or slot.get("razao_social")
                contato = rec.get("contato") or {}
                slot.setdefault("telefone", contato.get("telefone"))
                slot.setdefault("email", contato.get("email"))
                slot.setdefault("site", contato.get("site"))
                slot["contratos_consolidados"] = rec.get("contratos_consolidados")
                slot["top30_review"] = True
                slot["source_top30"] = str(top30)
        xlsx = root / "leads-reajuste-14133-enriquecida-CORRIGIDA.xlsx"
        if xlsx.exists():
            try:
                for rec in _xlsx_rows(xlsx):
                    key = rec["CNPJ"]
                    slot = index.setdefault(key, {"cnpj": key})
                    slot.update(
                        {
                            "legal_name": rec.get("Empresa") or slot.get("legal_name"),
                            "telefone": rec.get("Telefone principal") or slot.get("telefone"),
                            "telefone2": rec.get("Telefone 2 / WhatsApp"),
                            "email": rec.get("E-mail corporativo") or slot.get("email"),
                            "site": rec.get("Site") or slot.get("site"),
                            "fonte": rec.get("Fonte do contato"),
                            "qsa": rec.get("Sócios / administradores"),
                            "qsa2": rec.get("Outros integrantes QSA"),
                            "contratos": rec.get("Qtd. contratos"),
                            "orgao": rec.get("Órgão contratante"),
                            "objeto": rec.get("Objeto resumido"),
                            "valor": rec.get("Valor do contrato"),
                            "melhor_contrato": rec.get("Melhor contrato"),
                            "municipio": rec.get("Município"),
                            "uf": rec.get("UF"),
                            "xlsx": str(xlsx),
                        }
                    )
            except Exception as exc:  # isolated failure
                index.setdefault("_errors", {}).setdefault("xlsx", str(exc))
    cleaned = {k: v for k, v in index.items() if k != "_errors"}
    if extra_paths is None:
        _INDEX_CACHE = cleaned
    return cleaned


class HistoricalCampaignProvider:
    provider_id = "historical_campaign"
    tier = 0

    def __init__(self, index: dict[str, dict[str, Any]] | None = None) -> None:
        self._index = index if index is not None else load_campaign_index()

    def collect(self, context: InvestigationContext) -> ProviderResult:
        cnpj = normalize_cnpj(context.cnpj)
        row = self._index.get(cnpj)
        attempt = SearchAttempt(
            attempt_id=stable_id("att", self.provider_id, cnpj),
            company_entity_id=cnpj,
            tier=0,
            provider_id=self.provider_id,
            source="campaign_artifacts",
            status="miss" if not row else "hit",
            reason=None if row else "cnpj_not_in_campaign_cache",
        )
        if not row:
            return ProviderResult(attempts=[attempt], terminal="miss")
        people: list[PersonObservation] = []
        channels: list[ChannelObservation] = []
        evidence = []
        for blob_key in ("qsa", "qsa2"):
            for name, role in parse_qsa_blob(row.get(blob_key)):
                ev = make_evidence(
                    field="person_name",
                    value=name,
                    epistemic_class=EpistemicClass.OBSERVED,
                    source_type="qsa_rfb",
                    source_url=row.get("fonte") or "rfb/brasilapi",
                    source_id=cnpj,
                    evidence_snippet=f"{name} ({role})" if role else name,
                    extraction_method="qsa_cadastre",
                )
                evidence.append(ev)
                people.append(
                    PersonObservation(
                        observation_id=stable_id("qsa", cnpj, name),
                        company_entity_id=cnpj,
                        person_name=name,
                        observed_role=role,
                        normalized_role_class=normalize_observed_role(role),
                        relation=classify_person_relation(observed_role=role),
                        source_type="qsa_rfb",
                        source_url=row.get("fonte"),
                        observed_at="2026-08-05",
                        epistemic_class=EpistemicClass.OBSERVED,
                        evidence_id=ev.evidence_id,
                        extra={"qsa_only": True},
                    )
                )
        tel = row.get("telefone") or row.get("Telefone principal")
        if tel:
            ev = make_evidence(
                field="company_phone",
                value=str(tel),
                epistemic_class=EpistemicClass.OBSERVED,
                source_type="rfb_cadastre",
                source_url=row.get("fonte") or "rfb/brasilapi",
                source_id=cnpj,
                evidence_snippet=str(tel),
                observed_at="2026-08-05",
                extraction_method="rfb_phone",
            )
            evidence.append(ev)
            channels.append(
                ChannelObservation(
                    observation_id=stable_id("tel", cnpj, str(tel)),
                    company_entity_id=cnpj,
                    channel_type=ChannelType.COMPANY_SWITCHBOARD,
                    channel_value=str(tel),
                    source_type="rfb_cadastre",
                    source_url=row.get("fonte"),
                    observed_at="2026-08-05",
                    epistemic_class=EpistemicClass.OBSERVED,
                    ownership=OwnershipStatus.COMPANY_OWNED,
                    evidence_id=ev.evidence_id,
                    extra={"person_owns_phone": False, "phone_context": "geral"},
                )
            )
        tel2 = row.get("telefone2") or row.get("Telefone 2 / WhatsApp")
        if tel2 and str(tel2) != str(tel or ""):
            ev2 = make_evidence(
                field="company_phone",
                value=str(tel2),
                epistemic_class=EpistemicClass.OBSERVED,
                source_type="rfb_cadastre",
                source_url=row.get("fonte") or "rfb/brasilapi",
                source_id=cnpj,
                evidence_snippet=str(tel2),
                observed_at="2026-08-05",
                extraction_method="rfb_secondary_phone",
            )
            evidence.append(ev2)
            channels.append(
                ChannelObservation(
                    observation_id=stable_id("tel2", cnpj, str(tel2)),
                    company_entity_id=cnpj,
                    channel_type=ChannelType.COMPANY_SWITCHBOARD,
                    channel_value=str(tel2),
                    source_type="rfb_cadastre",
                    source_url=row.get("fonte"),
                    snippet="Telefone 2 (coluna ambígua Telefone 2 / WhatsApp — não prova WhatsApp)",
                    observed_at="2026-08-05",
                    epistemic_class=EpistemicClass.OBSERVED,
                    ownership=OwnershipStatus.COMPANY_OWNED,
                    evidence_id=ev2.evidence_id,
                    extra={
                        "person_owns_phone": False,
                        "explicit_whatsapp": False,
                        "phone_context": "geral",
                        "reason_codes": ["SECONDARY_CORPORATE_PHONE", "WHATSAPP_NOT_EXPLICITLY_MARKED"],
                    },
                )
            )
        email = normalize_email(str(row.get("email") or "") or None)
        if email:
            ev = make_evidence(
                field="company_email",
                value=email,
                epistemic_class=EpistemicClass.OBSERVED,
                source_type="public_page" if row.get("fonte") else "campaign_override",
                source_url=row.get("fonte"),
                source_id=cnpj,
                evidence_snippet=email,
                extraction_method="public_or_manual_override",
            )
            evidence.append(ev)
            channels.append(
                ChannelObservation(
                    observation_id=stable_id("email", cnpj, email),
                    company_entity_id=cnpj,
                    channel_type=ChannelType.GENERIC_CORPORATE_EMAIL,
                    channel_value=email,
                    source_type="public_page",
                    source_url=row.get("fonte"),
                    observed_at="2026-08-05",
                    epistemic_class=EpistemicClass.OBSERVED,
                    ownership=OwnershipStatus.COMPANY_OWNED,
                    evidence_id=ev.evidence_id,
                )
            )
        site = row.get("site")
        if site:
            channels.append(
                ChannelObservation(
                    observation_id=stable_id("site", cnpj, str(site)),
                    company_entity_id=cnpj,
                    channel_type=ChannelType.OTHER_PUBLIC_BUSINESS_ROUTE,
                    channel_value=str(site),
                    source_type="company_site",
                    source_url=str(site),
                    observed_at="2026-08-05",
                    epistemic_class=EpistemicClass.OBSERVED,
                    ownership=OwnershipStatus.COMPANY_OWNED,
                )
            )
            fonte = str(row.get("fonte") or "")
            if "linkedin.com/in/" in fonte.lower():
                channels.append(
                    ChannelObservation(
                        observation_id=stable_id("li", cnpj, fonte),
                        company_entity_id=cnpj,
                        channel_type=ChannelType.PROFESSIONAL_PROFILE,
                        channel_value=fonte,
                        source_type="professional_profile",
                        source_url=fonte,
                        observed_at="2026-08-05",
                        epistemic_class=EpistemicClass.OBSERVED,
                    )
                )
        objeto = str(row.get("objeto") or "")
        orgao = str(row.get("orgao") or "")
        why = None
        if objeto or orgao:
            why = (
                f"Portfólio público com {row.get('contratos') or row.get('contratos_consolidados') or '?'} "
                f"contrato(s). Órgão: {orgao or 'n/d'}. Objeto: {objeto[:180]}"
            )
        service = context.service or infer_service_from_text(objeto)
        # Public official QSA never happens here; still drop if a name is a public body.
        people = [p for p in people if p.relation != PersonRelation.PUBLIC_OFFICIAL]
        attempt.status = "hit"
        attempt.documents_checked = 0
        return ProviderResult(
            people=people,
            channels=channels,
            evidence=evidence,
            attempts=[attempt],
            terminal="ok",
            why_now=why,
            company_site=str(site) if site else None,
            legal_name=row.get("legal_name") or row.get("razao_social") or row.get("Empresa"),
            extra={
                "service_hint": service,
                "row": {k: row.get(k) for k in ("orgao", "valor", "melhor_contrato", "municipio", "uf")},
            },
        )
