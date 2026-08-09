"""Date consolidation and annuality (interregno) for reajuste em sentido estrito.

Data-base must be tied to the estimated budget date (orçamento estimado).
Signature, publication, OS and start of execution must NOT be used silently
as data-base.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from scripts.commercial.reajuste_14133 import (
    DATA_BASE_CONFIRMED,
    DATA_BASE_MISSING,
    DATA_BASE_PROXY,
)

CONFIDENCE_CONFIRMED = "high"
CONFIDENCE_PROXY = "low"
CONFIDENCE_MISSING = "none"


@dataclass
class DateField:
    value: date | None
    source: str
    confidence: str
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": self.value.isoformat() if self.value else None,
            "source": self.source,
            "confidence": self.confidence,
            "notes": self.notes,
        }


@dataclass
class DateBundle:
    orcamento_estimado: DateField
    competencia_orcamento: DateField
    data_limite_proposta: DateField
    data_proposta_vencedora: DateField
    data_assinatura: DateField
    data_publicacao: DateField
    data_ordem_servico: DateField
    inicio_vigencia: DateField
    fim_vigencia: DateField
    ultimo_reajuste: DateField
    data_base_status: str
    data_base_effective: DateField
    proxima_data_aniversario: date | None
    dias_desde_reajuste_aplicavel: int | None
    dias_restantes_vigencia: int | None
    interregno_completo: bool
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "orcamento_estimado": self.orcamento_estimado.as_dict(),
            "competencia_orcamento": self.competencia_orcamento.as_dict(),
            "data_limite_proposta": self.data_limite_proposta.as_dict(),
            "data_proposta_vencedora": self.data_proposta_vencedora.as_dict(),
            "data_assinatura": self.data_assinatura.as_dict(),
            "data_publicacao": self.data_publicacao.as_dict(),
            "data_ordem_servico": self.data_ordem_servico.as_dict(),
            "inicio_vigencia": self.inicio_vigencia.as_dict(),
            "fim_vigencia": self.fim_vigencia.as_dict(),
            "ultimo_reajuste": self.ultimo_reajuste.as_dict(),
            "data_base_status": self.data_base_status,
            "data_base_effective": self.data_base_effective.as_dict(),
            "proxima_data_aniversario": (
                self.proxima_data_aniversario.isoformat() if self.proxima_data_aniversario else None
            ),
            "dias_desde_reajuste_aplicavel": self.dias_desde_reajuste_aplicavel,
            "dias_restantes_vigencia": self.dias_restantes_vigencia,
            "interregno_completo": self.interregno_completo,
            "notes": self.notes,
        }
        return out


def _parse(v: date | str | None) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, date):
        return v
    s = str(v).strip()[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _field(value: date | str | None, source: str, confidence: str, notes: str = "") -> DateField:
    return DateField(value=_parse(value), source=source, confidence=confidence, notes=notes)


def add_years(d: date, years: int) -> date:
    """Add calendar years preserving day when possible (Feb 29 → Feb 28)."""
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def next_anniversary(base: date, as_of: date) -> date:
    """Next annual anniversary of ``base`` strictly after or equal to as_of if same day."""
    cand = base
    while cand < as_of:
        cand = add_years(cand, 1)
    # if cand is far in future from successive adds starting from base — OK
    # if base already > as_of, cand == base
    if cand < as_of:
        cand = add_years(cand, 1)
    # recompute from year offset for stability
    years = as_of.year - base.year
    cand = add_years(base, max(0, years))
    if cand < as_of:
        cand = add_years(base, years + 1)
    return cand


def interregno_days(base: date, as_of: date) -> int:
    return (as_of - base).days


def consolidate_dates(
    *,
    as_of: date,
    orcamento_estimado: date | str | None = None,
    orcamento_source: str = "missing",
    orcamento_confidence: str = CONFIDENCE_MISSING,
    competencia_orcamento: date | str | None = None,
    data_limite_proposta: date | str | None = None,
    data_proposta_vencedora: date | str | None = None,
    data_assinatura: date | str | None = None,
    data_publicacao: date | str | None = None,
    data_ordem_servico: date | str | None = None,
    inicio_vigencia: date | str | None = None,
    fim_vigencia: date | str | None = None,
    ultimo_reajuste: date | str | None = None,
    allow_proxy_for_prospection: bool = True,
) -> DateBundle:
    """Consolidate dates with explicit data-base status.

    Confirmed data-base = orcamento_estimado with high confidence.
    Proxy (assinatura/inicio/publicacao) is only for prospection heuristics.
    """
    notes: list[str] = []
    orc = _field(
        orcamento_estimado,
        orcamento_source if orcamento_estimado else "missing",
        orcamento_confidence if orcamento_estimado else CONFIDENCE_MISSING,
        "Data do orçamento estimado (data-base legal do reajuste)."
        if orcamento_estimado
        else "Data do orçamento estimado ausente — obter no edital/contrato/planilha orçamentária.",
    )
    assin = _field(data_assinatura, "pncp_supplier_contracts.data_assinatura", CONFIDENCE_PROXY)
    pub = _field(
        data_publicacao,
        "pncp_supplier_contracts.data_publicacao_fonte|data_publicacao",
        CONFIDENCE_PROXY,
        "Publicação não é data-base de reajuste.",
    )
    inicio = _field(inicio_vigencia, "pncp_supplier_contracts.data_inicio", CONFIDENCE_PROXY)
    fim = _field(fim_vigencia, "pncp_supplier_contracts.data_fim", CONFIDENCE_PROXY)
    os_date = _field(
        data_ordem_servico,
        "document|missing",
        CONFIDENCE_PROXY if data_ordem_servico else CONFIDENCE_MISSING,
        "OS não é data-base de reajuste.",
    )
    ultimo = _field(
        ultimo_reajuste,
        "document|apostila|missing",
        CONFIDENCE_CONFIRMED if ultimo_reajuste else CONFIDENCE_MISSING,
    )

    if orc.value is not None and orc.confidence == CONFIDENCE_CONFIRMED:
        status = DATA_BASE_CONFIRMED
        effective = orc
    elif orc.value is not None and orc.confidence != CONFIDENCE_MISSING:
        status = DATA_BASE_PROXY
        effective = orc
        notes.append("Orçamento com confiança limitada — não promover a HOT_VERIFIED sem confirmação.")
    else:
        status = DATA_BASE_MISSING
        # proxy chain for prospection only
        proxy_val = None
        proxy_src = "missing"
        if allow_proxy_for_prospection:
            for val, src in (
                (assin.value, "proxy:data_assinatura"),
                (inicio.value, "proxy:data_inicio"),
                (pub.value, "proxy:data_publicacao"),
            ):
                if val is not None:
                    proxy_val = val
                    proxy_src = src
                    break
        if proxy_val is not None:
            status = DATA_BASE_PROXY
            effective = DateField(
                value=proxy_val,
                source=proxy_src,
                confidence=CONFIDENCE_PROXY,
                notes=(
                    "Heurística de prospecção apenas. NÃO é data-base legal. "
                    "Não autoriza HOT_VERIFIED. Obter data do orçamento estimado."
                ),
            )
            notes.append("data_base_status=PROXY — assinatura/início/publicação usadas só como heurística.")
        else:
            effective = DateField(
                value=None,
                source="missing",
                confidence=CONFIDENCE_MISSING,
                notes="Sem data-base nem proxy utilizável.",
            )
            notes.append("data_base_status=MISSING — lead fora de HOT_VERIFIED.")

    # Anniversary reference: last adjustment if known, else effective data-base
    ref_for_anniv = ultimo.value or effective.value
    proxima: date | None = None
    dias_atraso: int | None = None
    interregno_ok = False
    if ref_for_anniv is not None:
        first_due = add_years(ref_for_anniv, 1)
        if as_of >= first_due:
            interregno_ok = True
            dias_atraso = (as_of - first_due).days
            proxima = next_anniversary(ref_for_anniv, as_of)
            # if already past anniversary, next is the following cycle
            if proxima <= as_of:
                proxima = add_years(proxima, 1)
        else:
            interregno_ok = False
            dias_atraso = (as_of - first_due).days  # negative = still waiting
            proxima = first_due

    dias_restantes: int | None = None
    if fim.value is not None:
        dias_restantes = (fim.value - as_of).days

    return DateBundle(
        orcamento_estimado=orc,
        competencia_orcamento=_field(
            competencia_orcamento,
            "document|missing",
            CONFIDENCE_CONFIRMED if competencia_orcamento else CONFIDENCE_MISSING,
        ),
        data_limite_proposta=_field(
            data_limite_proposta,
            "document|missing",
            CONFIDENCE_PROXY if data_limite_proposta else CONFIDENCE_MISSING,
        ),
        data_proposta_vencedora=_field(
            data_proposta_vencedora,
            "document|missing",
            CONFIDENCE_PROXY if data_proposta_vencedora else CONFIDENCE_MISSING,
        ),
        data_assinatura=assin,
        data_publicacao=pub,
        data_ordem_servico=os_date,
        inicio_vigencia=inicio,
        fim_vigencia=fim,
        ultimo_reajuste=ultimo,
        data_base_status=status,
        data_base_effective=effective,
        proxima_data_aniversario=proxima,
        dias_desde_reajuste_aplicavel=dias_atraso,
        dias_restantes_vigencia=dias_restantes,
        interregno_completo=interregno_ok,
        notes=notes,
    )
