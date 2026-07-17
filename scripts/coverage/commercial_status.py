#!/usr/bin/env python3
"""Deterministic commercial status classifier for procurement records.

Maps source-specific fields into canonical commercial statuses used by the
Extra Construtora radar and coverage metrics.

Statuses:
  OPEN_OPPORTUNITY, UPCOMING_OPPORTUNITY, RECENT_NOTICE, SUSPENDED,
  CLOSED, RESULT, CONTRACT, AMENDMENT, OTHER_PROCUREMENT_ACT, NOT_RELEVANT
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

STATUSES: tuple[str, ...] = (
    "OPEN_OPPORTUNITY",
    "UPCOMING_OPPORTUNITY",
    "RECENT_NOTICE",
    "SUSPENDED",
    "CLOSED",
    "RESULT",
    "CONTRACT",
    "AMENDMENT",
    "OTHER_PROCUREMENT_ACT",
    "NOT_RELEVANT",
)

# Act categories that can represent commercial opportunities (not results).
OPPORTUNITY_ACT_CATEGORIES = frozenset(
    {
        "aviso_licitacao",
        "edital",
        "dispensa",
        "inexigibilidade",
        "chamamento_publico",
        "credenciamento",
        "intencao_registro_precos",
        "reabertura",
        "consulta_publica",
    }
)

RESULT_ACT_CATEGORIES = frozenset(
    {
        "homologacao",
        "adjudicacao",
        "resultado",
    }
)

CONTRACT_ACT_CATEGORIES = frozenset(
    {
        "extrato_contrato",
        "ata_registro_precos",
        "rescisao",
    }
)

AMENDMENT_ACT_CATEGORIES = frozenset(
    {
        "termo_aditivo",
        "apostilamento",
    }
)

SUSPEND_ACT_CATEGORIES = frozenset(
    {
        "suspensao",
        "revogacao",
        "anulacao",
    }
)

_OPEN_STATUS = re.compile(
    r"\b("
    r"em\s+recebimento\s+de\s+proposta|recebendo\s+proposta|"
    r"aguardando\s+abertura|em\s+sess[aã]o|aberto|publicad[oa]|"
    r"divulga[cç][aã]o|em\s+andamento|fase\s+de\s+lance|"
    r"aguardando\s+abertura\s+da\s+habilita[cç][aã]o|"
    r"aguardando\s+abertura\s+de\s+pre[cç]o"
    r")\b",
    re.I,
)

_CLOSED_STATUS = re.compile(
    r"\b("
    r"homologad[oa]|finalizad[oa]|encerrad[oa]|conclu[ií]d[oa]|"
    r"adjudicad[oa]|fracassad[oa]|deserto|revogad[oa]|anulad[oa]|"
    r"cancelad[oa]|licita[cç][aã]o\s+finalizada|aguardando\s+homologa"
    r")\b",
    re.I,
)

_SUSPEND_STATUS = re.compile(
    r"\b(suspens[oa]|sine[- ]?die|interromp|paralisad)\b",
    re.I,
)

_REVOKED = re.compile(r"\b(revogad|anulad|cancelad)\b", re.I)


def _parse_date(val: Any) -> date | None:
    if val is None or val == "":
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    s = str(val).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


@dataclass
class CommercialClassification:
    status: str
    reason: str
    rules_fired: list[str]
    confidence: float
    needs_human_review: bool
    evaluated_at: str
    as_of: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_commercial(
    *,
    act_category: str | None = None,
    title: str | None = None,
    text: str | None = None,
    official_status: str | None = None,
    data_abertura: Any = None,
    data_encerramento: Any = None,
    data_publicacao: Any = None,
    as_of: date | None = None,
    recent_notice_days: int = 30,
) -> CommercialClassification:
    """Classify a single record into a commercial status (deterministic)."""
    today = as_of or date.today()
    rules: list[str] = []
    title_l = (title or "")[:2000]
    text_l = (text or "")[:4000]
    blob = f"{title_l}\n{text_l}\n{official_status or ''}"
    cat = (act_category or "").strip().lower() or None
    status_s = (official_status or "").strip()

    abertura = _parse_date(data_abertura)
    encerramento = _parse_date(data_encerramento)
    publicacao = _parse_date(data_publicacao)

    # 1) Explicit non-procurement
    if cat in {"nao_relacionado"}:
        rules.append("act_category:nao_relacionado")
        return CommercialClassification(
            status="NOT_RELEVANT",
            reason="Act category is not procurement-related",
            rules_fired=rules,
            confidence=0.95,
            needs_human_review=False,
            evaluated_at=datetime.utcnow().isoformat() + "Z",
            as_of=today.isoformat(),
        )

    # 2) Suspension / revocation
    if cat in SUSPEND_ACT_CATEGORIES or _SUSPEND_STATUS.search(status_s) or _REVOKED.search(status_s):
        rules.append("suspend_or_revoke")
        st = "SUSPENDED" if (cat == "suspensao" or _SUSPEND_STATUS.search(status_s)) else "CLOSED"
        if cat in {"revogacao", "anulacao"} or _REVOKED.search(status_s):
            st = "CLOSED"
            rules.append("revoked_or_annulled")
        return CommercialClassification(
            status=st,
            reason=f"Suspended/closed via category={cat} status={status_s!r}",
            rules_fired=rules,
            confidence=0.9,
            needs_human_review=False,
            evaluated_at=datetime.utcnow().isoformat() + "Z",
            as_of=today.isoformat(),
        )

    # 3) Contract / amendment / result by category
    if cat in CONTRACT_ACT_CATEGORIES:
        rules.append(f"act_category:{cat}")
        return CommercialClassification(
            status="CONTRACT",
            reason=f"Contractual act category {cat}",
            rules_fired=rules,
            confidence=0.92,
            needs_human_review=False,
            evaluated_at=datetime.utcnow().isoformat() + "Z",
            as_of=today.isoformat(),
        )
    if cat in AMENDMENT_ACT_CATEGORIES:
        rules.append(f"act_category:{cat}")
        return CommercialClassification(
            status="AMENDMENT",
            reason=f"Amendment act category {cat}",
            rules_fired=rules,
            confidence=0.92,
            needs_human_review=False,
            evaluated_at=datetime.utcnow().isoformat() + "Z",
            as_of=today.isoformat(),
        )
    if cat in RESULT_ACT_CATEGORIES:
        rules.append(f"act_category:{cat}")
        return CommercialClassification(
            status="RESULT",
            reason=f"Result act category {cat}",
            rules_fired=rules,
            confidence=0.9,
            needs_human_review=False,
            evaluated_at=datetime.utcnow().isoformat() + "Z",
            as_of=today.isoformat(),
        )

    # 4) Official status closed
    if status_s and _CLOSED_STATUS.search(status_s) and not _OPEN_STATUS.search(status_s):
        rules.append(f"official_status_closed:{status_s}")
        # Homologado / finalizado → RESULT; Fracassado/Deserto → CLOSED
        if re.search(r"homolog|adjudic|finaliz|conclu", status_s, re.I):
            st = "RESULT"
        else:
            st = "CLOSED"
        return CommercialClassification(
            status=st,
            reason=f"Official status indicates closed/result: {status_s}",
            rules_fired=rules,
            confidence=0.88,
            needs_human_review=False,
            evaluated_at=datetime.utcnow().isoformat() + "Z",
            as_of=today.isoformat(),
        )

    # 5) Deadline-based open/closed
    if encerramento is not None:
        rules.append(f"data_encerramento:{encerramento.isoformat()}")
        if encerramento < today:
            return CommercialClassification(
                status="CLOSED",
                reason=f"Proposal deadline {encerramento.isoformat()} already passed",
                rules_fired=rules + ["deadline_passed"],
                confidence=0.93,
                needs_human_review=False,
                evaluated_at=datetime.utcnow().isoformat() + "Z",
                as_of=today.isoformat(),
            )
        if abertura is not None and abertura > today:
            rules.append(f"data_abertura:{abertura.isoformat()}")
            return CommercialClassification(
                status="UPCOMING_OPPORTUNITY",
                reason=f"Opens {abertura.isoformat()}, closes {encerramento.isoformat()}",
                rules_fired=rules + ["opens_in_future"],
                confidence=0.9,
                needs_human_review=False,
                evaluated_at=datetime.utcnow().isoformat() + "Z",
                as_of=today.isoformat(),
            )
        return CommercialClassification(
            status="OPEN_OPPORTUNITY",
            reason=f"Proposal deadline {encerramento.isoformat()} still open",
            rules_fired=rules + ["deadline_open"],
            confidence=0.92,
            needs_human_review=False,
            evaluated_at=datetime.utcnow().isoformat() + "Z",
            as_of=today.isoformat(),
        )

    # 6) Open official status without deadline
    if status_s and _OPEN_STATUS.search(status_s):
        rules.append(f"official_status_open:{status_s}")
        return CommercialClassification(
            status="OPEN_OPPORTUNITY",
            reason=f"Official status indicates open: {status_s}",
            rules_fired=rules,
            confidence=0.85,
            needs_human_review=encerramento is None,
            evaluated_at=datetime.utcnow().isoformat() + "Z",
            as_of=today.isoformat(),
        )

    # 7) Opportunity act categories without dates → RECENT_NOTICE if pub recent
    if cat in OPPORTUNITY_ACT_CATEGORIES or re.search(
        r"\b(edital|aviso\s+de\s+licita|preg[aã]o|concorr[eê]ncia|dispensa|inexigib)\b",
        blob,
        re.I,
    ):
        rules.append(f"opportunity_signal:cat={cat}")
        if publicacao is not None:
            age = (today - publicacao).days
            rules.append(f"publication_age_days:{age}")
            if 0 <= age <= recent_notice_days:
                return CommercialClassification(
                    status="RECENT_NOTICE",
                    reason=f"Opportunity-like act published {age}d ago ({publicacao})",
                    rules_fired=rules,
                    confidence=0.75,
                    needs_human_review=True,
                    evaluated_at=datetime.utcnow().isoformat() + "Z",
                    as_of=today.isoformat(),
                )
        return CommercialClassification(
            status="OTHER_PROCUREMENT_ACT",
            reason="Opportunity-like act without open deadline evidence",
            rules_fired=rules,
            confidence=0.65,
            needs_human_review=True,
            evaluated_at=datetime.utcnow().isoformat() + "Z",
            as_of=today.isoformat(),
        )

    if cat in {"retificacao", "errata", "outros_atos_contratacao"}:
        rules.append(f"act_category:{cat}")
        return CommercialClassification(
            status="OTHER_PROCUREMENT_ACT",
            reason=f"Secondary procurement act {cat}",
            rules_fired=rules,
            confidence=0.7,
            needs_human_review=False,
            evaluated_at=datetime.utcnow().isoformat() + "Z",
            as_of=today.isoformat(),
        )

    rules.append("default_not_relevant_or_other")
    conf = 0.4 if cat in {None, "", "outros"} else 0.55
    return CommercialClassification(
        status="NOT_RELEVANT" if cat in {None, "outros"} and not re.search(
            r"\blicita|contrato|edital|preg", blob, re.I
        ) else "OTHER_PROCUREMENT_ACT",
        reason="No strong commercial opportunity signal",
        rules_fired=rules,
        confidence=conf,
        needs_human_review=True,
        evaluated_at=datetime.utcnow().isoformat() + "Z",
        as_of=today.isoformat(),
    )


# Statuses that count toward commercial opportunity coverage (canonical numerator)
COVERAGE_COUNTING_STATUSES = frozenset(
    {
        "OPEN_OPPORTUNITY",
        "UPCOMING_OPPORTUNITY",
        "RECENT_NOTICE",
        "OTHER_PROCUREMENT_ACT",  # only when act is opportunity category — filtered by caller
    }
)

STRICT_OPPORTUNITY_STATUSES = frozenset(
    {
        "OPEN_OPPORTUNITY",
        "UPCOMING_OPPORTUNITY",
        "RECENT_NOTICE",
    }
)
