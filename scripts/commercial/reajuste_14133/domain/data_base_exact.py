"""Structured exact data-base extraction for reajuste em sentido estrito.

Mere mention of the expression "data-base" does NOT satisfy data_base_exata_localizada.
Signature, publication and start of execution never count as exact data-base.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

# Exact states that satisfy data_base_exata_localizada
EXACT_DATE_IN_REAJUSTE_CLAUSE = "EXACT_DATE_IN_REAJUSTE_CLAUSE"
EXACT_COMPETENCE_IN_REAJUSTE_CLAUSE = "EXACT_COMPETENCE_IN_REAJUSTE_CLAUSE"
EXACT_DATE_IN_REFERENCED_BUDGET = "EXACT_DATE_IN_REFERENCED_BUDGET"
COMPETENCE_IN_BUDGET_SPREADSHEET = "COMPETENCE_IN_BUDGET_SPREADSHEET"

# Non-satisfying states
GENERIC_RULE_WITHOUT_DATE = "GENERIC_RULE_WITHOUT_DATE"
CONFLICTING_DATES = "CONFLICTING_DATES"
NOT_LOCATED = "NOT_LOCATED"
PROXY_SIGNATURE_OR_START = "PROXY_SIGNATURE_OR_START"  # never exact

EXACT_DATA_BASE_SATISFYING = frozenset(
    {
        EXACT_DATE_IN_REAJUSTE_CLAUSE,
        EXACT_COMPETENCE_IN_REAJUSTE_CLAUSE,
        EXACT_DATE_IN_REFERENCED_BUDGET,
        COMPETENCE_IN_BUDGET_SPREADSHEET,
    }
)

_MONTHS = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "março": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
    "jan": 1,
    "fev": 2,
    "mar": 3,
    "abr": 4,
    "mai": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "set": 9,
    "out": 10,
    "nov": 11,
    "dez": 12,
}

_REAJUSTE_CTX = re.compile(
    r"reajust(?:e|amento)|repactua|atualiza[cç][aã]o\s+monet[aá]ria",
    re.I,
)
_DATA_BASE_LABEL = re.compile(
    r"data[- ]base|data\s+do\s+or[cç]amento\s+estimado|m[eê]s[- ]base|"
    r"compet[eê]ncia\s+(?:do\s+)?(?:or[cç]amento|sinapi|sicro)|"
    r"or[cç]amento\s+estimado\s+(?:de|em|datad[oa])",
    re.I,
)
_FULL_DATE = re.compile(
    r"\b(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})\b"
)
_ISO_DATE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_MONTH_YEAR = re.compile(
    r"\b("
    + "|".join(_MONTHS.keys())
    + r")\s*(?:de\s+)?(20\d{2})\b",
    re.I,
)
_COMP_NUM = re.compile(
    r"\b(?:compet[eê]ncia|ref(?:er[eê]ncia)?\.?|base)\s*"
    r"(?:sinapi|sicro)?\s*"
    r"(\d{1,2})[./\-](20\d{2})\b",
    re.I,
)
_SINAPI_COMP = re.compile(
    r"\bSINAPI\b[^.\n]{0,80}?(?:compet[eê]ncia|ref\.?|base)?\s*"
    r"(?:de\s+)?(\d{1,2})[./\-](20\d{2})"
    r"|\b(?:compet[eê]ncia|ref\.?)\s*(?:SINAPI\s*)?(\d{1,2})[./\-](20\d{2})[^.\n]{0,40}SINAPI",
    re.I,
)
_SICRO_COMP = re.compile(
    r"\bSICRO\b[^.\n]{0,80}?(?:compet[eê]ncia|ref\.?|base)?\s*"
    r"(?:de\s+)?(\d{1,2})[./\-](20\d{2})"
    r"|\b(?:compet[eê]ncia|ref\.?)\s*(?:SICRO\s*)?(\d{1,2})[./\-](20\d{2})[^.\n]{0,40}SICRO",
    re.I,
)


@dataclass
class ExactDataBaseHit:
    state: str
    value: str | None
    value_date: date | None
    value_month: int | None
    value_year: int | None
    kind: str  # full_date | month_year | sinapi_competence | sicro_competence | spreadsheet_month
    document: str | None
    page_or_cell: str | None
    excerpt: str
    content_hash: str | None
    relation_to_clause: str  # in_clause | referenced_budget | spreadsheet | generic | conflict
    confidence: str
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["value_date"] = self.value_date.isoformat() if self.value_date else None
        return d


@dataclass
class ExactDataBaseResult:
    state: str
    data_base_exata_localizada: bool
    hits: list[ExactDataBaseHit] = field(default_factory=list)
    primary: ExactDataBaseHit | None = None
    conflicts: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "data_base_exata_localizada": self.data_base_exata_localizada,
            "hits": [h.as_dict() for h in self.hits],
            "primary": self.primary.as_dict() if self.primary else None,
            "conflicts": self.conflicts,
            "notes": self.notes,
        }


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:32]


def _safe_date(d: int, m: int, y: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _page_hint_from_pos(text: str, pos: int) -> str | None:
    # Look backwards for [page=N]
    window = text[max(0, pos - 500) : pos + 1]
    m = re.findall(r"\[page=(\d+)\]", window)
    return m[-1] if m else None


def extract_exact_data_base(
    text: str,
    *,
    document: str | None = None,
    page_hint: str | None = None,
    is_budget_spreadsheet: bool = False,
    clause_windows: list[tuple[int, int]] | None = None,
) -> ExactDataBaseResult:
    """Extract structured exact data-base from document text.

    Does not treat mere "data-base" string as exact. Does not use signature/
    publication/start language as exact data-base.
    """
    if not text or not text.strip():
        return ExactDataBaseResult(
            state=NOT_LOCATED,
            data_base_exata_localizada=False,
            notes=["empty_text"],
        )

    notes: list[str] = []
    hits: list[ExactDataBaseHit] = []

    # Build clause windows if not provided
    windows = list(clause_windows or [])
    if not windows:
        for m in _REAJUSTE_CTX.finditer(text):
            windows.append((max(0, m.start() - 250), min(len(text), m.end() + 500)))

    def in_clause(pos: int) -> bool:
        return any(w0 <= pos <= w1 for w0, w1 in windows)

    # Generic mention without date near label
    for m in _DATA_BASE_LABEL.finditer(text):
        snippet = text[m.start() : min(len(text), m.end() + 120)]
        has_date = bool(_FULL_DATE.search(snippet) or _ISO_DATE.search(snippet) or _MONTH_YEAR.search(snippet) or _COMP_NUM.search(snippet))
        if not has_date:
            notes.append("generic_data_base_mention_without_date")

    # 1) Full dates near data-base / in reajuste clause
    for m in _FULL_DATE.finditer(text):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= mo <= 12 and 1 <= d <= 31 and 2000 <= y <= 2035):
            continue
        # context: must be near data-base label or inside reajuste clause
        ctx = text[max(0, m.start() - 100) : min(len(text), m.end() + 40)]
        near_label = bool(_DATA_BASE_LABEL.search(ctx))
        clause = in_clause(m.start())
        # reject signature/publication/start phrasing
        if re.search(
            r"assinatura|publica[cç][aã]o|in[ií]cio\s+de\s+vig[eê]ncia|"
            r"ordem\s+de\s+servi[cç]o|data\s+da\s+assinatura",
            ctx,
            re.I,
        ) and not near_label:
            continue
        if not (near_label or clause):
            continue
        dt = _safe_date(d, mo, y)
        if not dt:
            continue
        state = EXACT_DATE_IN_REAJUSTE_CLAUSE if clause or near_label else GENERIC_RULE_WITHOUT_DATE
        if near_label and not clause:
            # could be budget reference in clause section
            if re.search(r"or[cç]amento|planilha|anexo", ctx, re.I):
                state = EXACT_DATE_IN_REFERENCED_BUDGET
            else:
                state = EXACT_DATE_IN_REAJUSTE_CLAUSE
        excerpt = text[max(0, m.start() - 60) : min(len(text), m.end() + 60)].strip()
        hits.append(
            ExactDataBaseHit(
                state=state,
                value=dt.isoformat(),
                value_date=dt,
                value_month=mo,
                value_year=y,
                kind="full_date",
                document=document,
                page_or_cell=page_hint or _page_hint_from_pos(text, m.start()),
                excerpt=excerpt[:400],
                content_hash=_hash(excerpt),
                relation_to_clause="in_clause" if clause else "referenced_budget",
                confidence="high" if clause and near_label else "medium",
            )
        )

    for m in _ISO_DATE.finditer(text):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        ctx = text[max(0, m.start() - 100) : min(len(text), m.end() + 40)]
        near_label = bool(_DATA_BASE_LABEL.search(ctx))
        clause = in_clause(m.start())
        if not (near_label or clause):
            continue
        if re.search(r"assinatura|publica[cç][aã]o|ordem\s+de\s+servi[cç]o", ctx, re.I) and not near_label:
            continue
        dt = _safe_date(d, mo, y)
        if not dt:
            continue
        excerpt = text[max(0, m.start() - 60) : min(len(text), m.end() + 60)].strip()
        hits.append(
            ExactDataBaseHit(
                state=EXACT_DATE_IN_REAJUSTE_CLAUSE if (clause or near_label) else GENERIC_RULE_WITHOUT_DATE,
                value=dt.isoformat(),
                value_date=dt,
                value_month=mo,
                value_year=y,
                kind="full_date",
                document=document,
                page_or_cell=page_hint or _page_hint_from_pos(text, m.start()),
                excerpt=excerpt[:400],
                content_hash=_hash(excerpt),
                relation_to_clause="in_clause" if clause else "referenced_budget",
                confidence="high",
            )
        )

    # 2) Month-year competence near data-base / clause
    for m in _MONTH_YEAR.finditer(text):
        mon_name = m.group(1).lower()
        y = int(m.group(2))
        mo = _MONTHS.get(mon_name)
        if not mo:
            continue
        ctx = text[max(0, m.start() - 120) : min(len(text), m.end() + 40)]
        near_label = bool(_DATA_BASE_LABEL.search(ctx))
        clause = in_clause(m.start())
        if not (near_label or clause or is_budget_spreadsheet):
            continue
        if re.search(r"assinatura|publica[cç][aã]o", ctx, re.I) and not near_label:
            continue
        val = f"{y:04d}-{mo:02d}"
        if is_budget_spreadsheet:
            state = COMPETENCE_IN_BUDGET_SPREADSHEET
            rel = "spreadsheet"
        elif clause or near_label:
            state = EXACT_COMPETENCE_IN_REAJUSTE_CLAUSE
            rel = "in_clause"
        else:
            continue
        excerpt = text[max(0, m.start() - 60) : min(len(text), m.end() + 60)].strip()
        hits.append(
            ExactDataBaseHit(
                state=state,
                value=val,
                value_date=_safe_date(1, mo, y),
                value_month=mo,
                value_year=y,
                kind="month_year",
                document=document,
                page_or_cell=page_hint or _page_hint_from_pos(text, m.start()),
                excerpt=excerpt[:400],
                content_hash=_hash(excerpt),
                relation_to_clause=rel,
                confidence="high" if clause else "medium",
            )
        )

    # 3) SINAPI / SICRO competence
    for m in _SINAPI_COMP.finditer(text):
        g = m.groups()
        if g[0] and g[1]:
            mo, y = int(g[0]), int(g[1])
        elif g[2] and g[3]:
            mo, y = int(g[2]), int(g[3])
        else:
            continue
        if not (1 <= mo <= 12):
            continue
        clause = in_clause(m.start())
        state = (
            EXACT_COMPETENCE_IN_REAJUSTE_CLAUSE
            if clause
            else COMPETENCE_IN_BUDGET_SPREADSHEET
            if is_budget_spreadsheet
            else EXACT_DATE_IN_REFERENCED_BUDGET
        )
        val = f"SINAPI/{mo:02d}/{y}"
        excerpt = text[max(0, m.start() - 40) : min(len(text), m.end() + 40)].strip()
        hits.append(
            ExactDataBaseHit(
                state=state,
                value=val,
                value_date=_safe_date(1, mo, y),
                value_month=mo,
                value_year=y,
                kind="sinapi_competence",
                document=document,
                page_or_cell=page_hint or _page_hint_from_pos(text, m.start()),
                excerpt=excerpt[:400],
                content_hash=_hash(excerpt),
                relation_to_clause="in_clause" if clause else "referenced_budget",
                confidence="high" if clause else "medium",
            )
        )

    for m in _SICRO_COMP.finditer(text):
        g = m.groups()
        if g[0] and g[1]:
            mo, y = int(g[0]), int(g[1])
        elif g[2] and g[3]:
            mo, y = int(g[2]), int(g[3])
        else:
            continue
        if not (1 <= mo <= 12):
            continue
        clause = in_clause(m.start())
        state = (
            EXACT_COMPETENCE_IN_REAJUSTE_CLAUSE
            if clause
            else COMPETENCE_IN_BUDGET_SPREADSHEET
            if is_budget_spreadsheet
            else EXACT_DATE_IN_REFERENCED_BUDGET
        )
        val = f"SICRO/{mo:02d}/{y}"
        excerpt = text[max(0, m.start() - 40) : min(len(text), m.end() + 40)].strip()
        hits.append(
            ExactDataBaseHit(
                state=state,
                value=val,
                value_date=_safe_date(1, mo, y),
                value_month=mo,
                value_year=y,
                kind="sicro_competence",
                document=document,
                page_or_cell=page_hint or _page_hint_from_pos(text, m.start()),
                excerpt=excerpt[:400],
                content_hash=_hash(excerpt),
                relation_to_clause="in_clause" if clause else "referenced_budget",
                confidence="high" if clause else "medium",
            )
        )

    # Spreadsheet numeric competence mm/yyyy near "mês base" without clause
    if is_budget_spreadsheet:
        for m in _COMP_NUM.finditer(text):
            mo, y = int(m.group(1)), int(m.group(2))
            if not (1 <= mo <= 12):
                continue
            val = f"{y:04d}-{mo:02d}"
            excerpt = text[max(0, m.start() - 40) : min(len(text), m.end() + 40)].strip()
            hits.append(
                ExactDataBaseHit(
                    state=COMPETENCE_IN_BUDGET_SPREADSHEET,
                    value=val,
                    value_date=_safe_date(1, mo, y),
                    value_month=mo,
                    value_year=y,
                    kind="spreadsheet_month",
                    document=document,
                    page_or_cell=page_hint,
                    excerpt=excerpt[:400],
                    content_hash=_hash(excerpt),
                    relation_to_clause="spreadsheet",
                    confidence="medium",
                )
            )

    if not hits:
        if "generic_data_base_mention_without_date" in notes:
            return ExactDataBaseResult(
                state=GENERIC_RULE_WITHOUT_DATE,
                data_base_exata_localizada=False,
                notes=notes + ["mention_without_exact_date"],
            )
        return ExactDataBaseResult(
            state=NOT_LOCATED,
            data_base_exata_localizada=False,
            notes=notes or ["not_located"],
        )

    # Conflict detection: distinct month/year values among satisfying hits
    satisfying = [h for h in hits if h.state in EXACT_DATA_BASE_SATISFYING]
    keys = set()
    for h in satisfying:
        if h.value_year and h.value_month:
            keys.add((h.value_year, h.value_month))
        elif h.value:
            keys.add((h.value,))
    conflicts: list[str] = []
    if len(keys) > 1:
        conflicts = [f"conflicting_values:{sorted(str(k) for k in keys)}"]
        return ExactDataBaseResult(
            state=CONFLICTING_DATES,
            data_base_exata_localizada=False,
            hits=hits,
            primary=None,
            conflicts=conflicts,
            notes=notes + ["multiple_exact_dates_conflict"],
        )

    # Prefer clause full date > clause competence > referenced budget > spreadsheet
    priority = {
        EXACT_DATE_IN_REAJUSTE_CLAUSE: 4,
        EXACT_COMPETENCE_IN_REAJUSTE_CLAUSE: 3,
        EXACT_DATE_IN_REFERENCED_BUDGET: 2,
        COMPETENCE_IN_BUDGET_SPREADSHEET: 1,
    }
    satisfying_sorted = sorted(
        satisfying,
        key=lambda h: (priority.get(h.state, 0), h.confidence == "high"),
        reverse=True,
    )
    if not satisfying_sorted:
        return ExactDataBaseResult(
            state=GENERIC_RULE_WITHOUT_DATE if notes else NOT_LOCATED,
            data_base_exata_localizada=False,
            hits=hits,
            notes=notes + ["hits_not_in_satisfying_states"],
        )

    primary = satisfying_sorted[0]
    return ExactDataBaseResult(
        state=primary.state,
        data_base_exata_localizada=True,
        hits=hits,
        primary=primary,
        conflicts=[],
        notes=notes,
    )


def is_exact_data_base_state(state: str | None) -> bool:
    return state in EXACT_DATA_BASE_SATISFYING
