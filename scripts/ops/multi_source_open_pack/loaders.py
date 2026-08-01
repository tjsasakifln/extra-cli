"""Loaders de observações brutas multi-fonte."""

from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from scripts.ops.multi_source_open_pack.events import classify_event
from scripts.ops.multi_source_open_pack.models import SourceObservation
from scripts.ops.multi_source_open_pack.textutil import optional_float, parse_date


def load_csv_dicts(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            out.append(json.loads(line))
    return out


def _obs(
    *,
    fonte: str,
    fonte_papel: str,
    id_externo: str,
    orgao: str,
    orgao_cnpj: str,
    municipio: str,
    uf: str,
    objeto: str,
    modalidade: str,
    valor_estimado: Any,
    data_publicacao: str,
    data_abertura: str,
    data_encerramento: str,
    url: str,
    status_fonte: str,
    categoria_ato: str,
    raw: dict[str, Any] | None = None,
) -> SourceObservation:
    oid = f"{fonte}:{id_externo or hash((orgao, objeto[:80], data_publicacao))}"
    event_type, is_active, excl = classify_event(
        categoria_ato=categoria_ato,
        objeto=objeto,
        status_fonte=status_fonte,
        fonte=fonte,
    )
    return SourceObservation(
        observation_id=oid,
        fonte=fonte,
        fonte_papel=fonte_papel,
        id_externo=str(id_externo or ""),
        orgao=orgao or "",
        orgao_cnpj=orgao_cnpj or "",
        municipio=municipio or "",
        uf=uf or "SC",
        objeto=(objeto or "")[:2000],
        modalidade=modalidade or "",
        valor_estimado=optional_float(valor_estimado),
        data_publicacao=str(data_publicacao or ""),
        data_abertura=str(data_abertura or ""),
        data_encerramento=str(data_encerramento or ""),
        url=str(url or ""),
        status_fonte=status_fonte or "",
        categoria_ato=categoria_ato or "",
        raw=raw or {},
        event_type=event_type,
        is_active_dispute=is_active,
        exclusion_reason=excl,
    )


def load_pncp_observations(path: Path, as_of: date) -> list[SourceObservation]:
    """Load PNCP open export. Does NOT silently drop by date — deadline handled later with timezone."""
    out: list[SourceObservation] = []
    for r in load_csv_dicts(path):
        # Keep rows; deadline filtering is in decision layer with full datetime
        out.append(
            _obs(
                fonte="pncp",
                fonte_papel="required",
                id_externo=r.get("numero_controle_pncp")
                or r.get("source_id")
                or r.get("id")
                or "",
                orgao=r.get("orgao_nome") or "",
                orgao_cnpj=r.get("orgao_cnpj") or "",
                municipio=r.get("municipio") or "",
                uf=r.get("uf") or "SC",
                objeto=r.get("objeto") or "",
                modalidade=r.get("modalidade") or "",
                valor_estimado=r.get("valor_estimado"),
                data_publicacao=r.get("data_publicacao") or "",
                data_abertura=r.get("data_abertura") or "",
                data_encerramento=r.get("data_encerramento") or "",
                url=r.get("link_edital") or r.get("source_url") or "",
                status_fonte=r.get("status_canonico") or "open",
                categoria_ato="edital_aberto",
                raw=dict(r),
            )
        )
    return out


_SC_OPEN_STATUS = (
    "em recebimento de proposta",
    "aguardando abertura da sessao",
    "aguardando abertura da sessão",
    "em sessao",
    "em sessão",
    "aguardando abertura da habilitacao",
    "aguardando abertura da habilitação",
    "open",
    "aberta",
    "aberto",
)
_SC_TERMINAL_STATUS = (
    "homologado",
    "adjudicado",
    "fracassado",
    "deserto",
    "cancelado",
    "revogado",
    "anulado",
    "suspenso",
    "aguardando homologacao",
    "aguardando homologação",
)


def _sc_status_to_event(status: str) -> tuple[str, str]:
    """Map SC Compras portal status → (status_fonte, categoria_ato)."""
    from scripts.ops.multi_source_open_pack.textutil import norm

    s = norm(status)
    if any(t in s for t in _SC_TERMINAL_STATUS):
        if "homolog" in s:
            return status or "homologado", "homologacao"
        if "fracass" in s:
            return status or "fracassado", "fracassado"
        if "desert" in s:
            return status or "deserto", "deserto"
        if "suspens" in s:
            return status or "suspenso", "suspensao"
        return status or "terminal", "resultado"
    if any(t in s for t in _SC_OPEN_STATUS) or not s:
        return status or "open", "portal_estadual_aberto"
    # unknown — do not claim open
    return status or "unknown", "resultado"


def load_sc_compras_observations(path: Path, as_of: date) -> list[SourceObservation]:
    out: list[SourceObservation] = []
    for r in load_jsonl(path):
        status_raw = str(r.get("status") or r.get("situacao") or "")
        status_fonte, categoria = _sc_status_to_event(status_raw)
        out.append(
            _obs(
                fonte="sc_compras",
                fonte_papel="complementary_estadual",
                id_externo=str(r.get("source_id") or r.get("pncp_id") or r.get("api_id") or ""),
                orgao=r.get("orgao_razao_social") or "",
                orgao_cnpj=r.get("orgao_cnpj") or "",
                municipio=r.get("municipio") or "",
                uf=r.get("uf") or "SC",
                objeto=r.get("objeto_compra") or r.get("objeto") or "",
                modalidade=r.get("modalidade_nome") or "",
                valor_estimado=r.get("valor_total_estimado"),
                data_publicacao=str(r.get("data_publicacao") or ""),
                data_abertura=str(r.get("data_abertura") or ""),
                data_encerramento=str(r.get("data_encerramento") or ""),
                url=str(r.get("link_pncp") or r.get("url") or ""),
                status_fonte=status_fonte,
                categoria_ato=categoria,
                raw=r,
            )
        )
    return out


# CIGA categories that may be open dispute candidates (still filtered by events)
CIGA_LICITACAO_CATS = frozenset(
    {
        "edital",
        "aviso_licitacao",
        "chamamento_publico",
        "inexigibilidade",
        "dispensa",
        "credenciamento",
        "reabertura",
        "intencao_registro_precos",
        "retificacao",
        "errata",
        "consulta_publica",
        "contrato",
        "homologacao",
        "adjudicacao",
        "resultado",
        "suspensao",
        "extrato",
    }
)


def load_ciga_observations(
    path: Path, as_of: date, lookback_days: int = 45
) -> list[SourceObservation]:
    """Load CIGA/DOM publications. Keep terminal acts for event classification (not as open opps)."""
    if not path.is_file():
        return []
    min_d = as_of - timedelta(days=lookback_days)
    out: list[SourceObservation] = []
    for r in load_jsonl(path):
        cat = (r.get("act_category") or "").strip()
        if cat and cat not in CIGA_LICITACAO_CATS:
            # still allow if act_category empty but looks like licitacao
            if cat not in {"edital", "aviso_licitacao", "contrato", "homologacao"}:
                # skip clearly non-licitacao if categorized
                if cat not in CIGA_LICITACAO_CATS:
                    continue
        d = parse_date(r.get("data"))
        if d and d < min_d:
            continue
        titulo = r.get("titulo") or ""
        # Map common act categories
        categoria = cat or "publicacao_dom"
        out.append(
            _obs(
                fonte="ciga_ckan",
                fonte_papel="required_municipal",
                id_externo=str(r.get("codigo") or ""),
                orgao=r.get("orgao") or r.get("entidade") or "",
                orgao_cnpj="",
                municipio=r.get("municipio") or "",
                uf="SC",
                objeto=titulo,
                modalidade=cat,
                valor_estimado="",
                data_publicacao=str(r.get("data") or ""),
                data_abertura="",
                data_encerramento="",
                url=str(r.get("url") or ""),
                status_fonte="publicacao_dom",
                categoria_ato=categoria,
                raw=r,
            )
        )
    return out


def load_all_observations(
    *,
    pncp_path: Path | None,
    ciga_path: Path | None,
    sc_path: Path | None,
    as_of: date,
    ciga_lookback_days: int = 45,
) -> list[SourceObservation]:
    rows: list[SourceObservation] = []
    if pncp_path and pncp_path.is_file():
        rows.extend(load_pncp_observations(pncp_path, as_of))
    if ciga_path and ciga_path.is_file():
        rows.extend(load_ciga_observations(ciga_path, as_of, ciga_lookback_days))
    if sc_path and sc_path.is_file():
        rows.extend(load_sc_compras_observations(sc_path, as_of))
    return rows
