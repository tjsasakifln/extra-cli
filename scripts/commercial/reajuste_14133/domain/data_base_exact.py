"""Structured exact data-base extraction for reajuste em sentido estrito.

Mere mention of the expression "data-base" does NOT satisfy data_base_exata_localizada.
Signature, publication, protocol, upload timestamps and start of execution never count.
Regulatory calendar dates (Instrução Normativa de 24 de janeiro de 2023) never count.
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

# Reajuste in the strict sense only — never "atualização monetária" (late payment)
_REAJUSTE_CTX = re.compile(
    r"reajust(?:e|amento)|repactua[cç]|reequil[ií]brio",
    re.I,
)
_DATA_BASE_LABEL = re.compile(
    r"data[- ]base|data\s+do\s+or[cç]amento\s+estimado|m[eê]s[- ]base|"
    r"compet[eê]ncia\s+(?:do\s+)?(?:or[cç]amento|sinapi|sicro)|"
    r"or[cç]amento\s+estimado\s+(?:de|em|datad[oa])|"
    r"data\s+base\s+sicro|data\s+base\s+sinapi",
    re.I,
)
_FULL_DATE = re.compile(r"\b(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})\b")
_ISO_DATE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_MONTH_YEAR = re.compile(
    r"\b(" + "|".join(_MONTHS.keys()) + r")\s*(?:de\s+)?(20\d{2})\b",
    re.I,
)
_COMP_NUM = re.compile(
    r"\b(?:compet[eê]ncia|ref(?:er[eê]ncia)?\.?|base)\s*"
    r"(?:sinapi|sicro)?\s*"
    r"(\d{1,2})[./\-](20\d{2})\b",
    re.I,
)
# Explicit budget/index competence labels (highest priority)
_EXPLICIT_MES_BASE = re.compile(
    r"m[eê]s[- ]base\s*[:\-]?\s*("
    + "|".join(_MONTHS.keys())
    + r")\s*/?\s*(20\d{2})",
    re.I,
)
_EXPLICIT_DATA_BASE_SICRO_SINAPI = re.compile(
    r"data\s*base\s*(?:sicro|sinapi)\s*[:\-]?\s*("
    + "|".join(_MONTHS.keys())
    + r")\s*/?\s*(20\d{2})",
    re.I,
)
_EXPLICIT_COMP_INDEX = re.compile(
    r"(?:sicro|sinapi)\s*(?:compet[eê]ncia|ref\.?|base)?\s*[:\-]?\s*"
    r"(?:de\s+)?(\d{1,2})[./\-](20\d{2})",
    re.I,
)
_SINAPI_COMP = re.compile(
    r"\bSINAPI\b[^.\n]{0,40}?(?:compet[eê]ncia|ref\.?|base|data\s*base)\s*"
    r"(?:de\s+|:?\s*)?(\d{1,2})[./\-](20\d{2})"
    r"|\b(?:compet[eê]ncia|ref\.?|data\s*base)\s*(?:SINAPI\s*)?(\d{1,2})[./\-](20\d{2})[^.\n]{0,20}SINAPI",
    re.I,
)
_SICRO_COMP = re.compile(
    r"\bSICRO\b[^.\n]{0,40}?(?:compet[eê]ncia|ref\.?|base|data\s*base)\s*"
    r"(?:de\s+|:?\s*)?(\d{1,2})[./\-](20\d{2})"
    r"|\b(?:compet[eê]ncia|ref\.?|data\s*base)\s*(?:SICRO\s*)?(\d{1,2})[./\-](20\d{2})[^.\n]{0,20}SICRO",
    re.I,
)

# Dates that must NEVER be treated as data-base even near a reajuste window
_PROTOCOL_OR_ARTIFACT = re.compile(
    r"assinatur|assinad[oa]|protocol[oa]|protocoliz|"
    r"publica[cç][aã]o|publicado|"
    r"in[ií]cio\s+de\s+vig[eê]ncia|ordem\s+de\s+servi[cç]o|"
    r"anexar\s+documentos|upload|enviado\s+em|em:\s*\d{1,2}[./\-]\d{1,2}[./\-]\d{4}|"
    r"\d{1,2}[./\-]\d{1,2}[./\-]\d{4}\s+\d{1,2}:\d{2}"  # timestamp
    r"|documento\s+assinado|por:\s*\w+.*\bem:\s*",
    re.I,
)
_REGULATORY_CALENDAR = re.compile(
    r"instru[cç][aã]o\s+normativa|portaria|decreto|resolu[cç][aã]o|"
    r"lei\s+n|lei\s+n[ºo°.]|"
    r"de\s+\d{1,2}\s+de\s+(?:"
    + "|".join(_MONTHS.keys())
    + r")\s+de\s+20\d{2}",
    re.I,
)
# Placeholder like XXXXX//202X or //202X without real month
_PLACEHOLDER = re.compile(r"X{2,}|//\s*202X|//\s*20XX|\b20XX\b", re.I)


@dataclass
class ExactDataBaseHit:
    state: str
    value: str | None
    value_date: date | None
    value_month: int | None
    value_year: int | None
    kind: str
    document: str | None
    page_or_cell: str | None
    excerpt: str
    content_hash: str | None
    relation_to_clause: str
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
    window = text[max(0, pos - 500) : pos + 1]
    m = re.findall(r"\[page=(\d+)\]", window)
    return m[-1] if m else None


def _ctx(text: str, pos: int, before: int = 80, after: int = 40) -> str:
    return text[max(0, pos - before) : min(len(text), pos + after)]


def _is_artifact_context(ctx: str) -> bool:
    """True if context is protocol/signature/upload/regulatory — never data-base."""
    if _PROTOCOL_OR_ARTIFACT.search(ctx):
        return True
    if _REGULATORY_CALENDAR.search(ctx):
        return True
    if _PLACEHOLDER.search(ctx):
        return True
    return False


def extract_exact_data_base(
    text: str,
    *,
    document: str | None = None,
    page_hint: str | None = None,
    is_budget_spreadsheet: bool = False,
    clause_windows: list[tuple[int, int]] | None = None,
) -> ExactDataBaseResult:
    """Extract structured exact data-base from document text.

    Rules (fail-closed):
    - Protocol / assinado / upload timestamps never count.
    - Regulatory calendar dates (IN/portaria/decreto de DD de month) never count.
    - Full dates require an explicit data-base / mês-base / orçamento label nearby —
      mere presence inside a wide reajuste window is NOT enough.
    - Month-year without label only counts on budget spreadsheets or explicit index competence.
    """
    if not text or not text.strip():
        return ExactDataBaseResult(
            state=NOT_LOCATED,
            data_base_exata_localizada=False,
            notes=["empty_text"],
        )

    notes: list[str] = []
    hits: list[ExactDataBaseHit] = []

    windows = list(clause_windows or [])
    if not windows:
        for m in _REAJUSTE_CTX.finditer(text):
            windows.append((max(0, m.start() - 250), min(len(text), m.end() + 500)))

    def in_clause(pos: int) -> bool:
        return any(w0 <= pos <= w1 for w0, w1 in windows)

    # Generic mention without date near label
    for m in _DATA_BASE_LABEL.finditer(text):
        snippet = text[m.start() : min(len(text), m.end() + 120)]
        has_date = bool(
            _FULL_DATE.search(snippet)
            or _ISO_DATE.search(snippet)
            or _MONTH_YEAR.search(snippet)
            or _COMP_NUM.search(snippet)
            or _EXPLICIT_MES_BASE.search(snippet)
            or _EXPLICIT_DATA_BASE_SICRO_SINAPI.search(snippet)
        )
        if not has_date:
            notes.append("generic_data_base_mention_without_date")

    # --- Priority A: explicit MÊS-BASE / DATA BASE SICRO|SINAPI labels ---
    for m in _EXPLICIT_MES_BASE.finditer(text):
        mon_name = m.group(1).lower()
        y = int(m.group(2))
        mo = _MONTHS.get(mon_name)
        if not mo:
            continue
        ctx = _ctx(text, m.start(), 40, 40)
        if _is_artifact_context(ctx) and "mês-base" not in ctx.lower() and "mes-base" not in ctx.lower():
            # still allow if the match itself is the mês-base label
            pass
        excerpt = text[max(0, m.start() - 30) : min(len(text), m.end() + 40)].strip()
        state = (
            COMPETENCE_IN_BUDGET_SPREADSHEET
            if is_budget_spreadsheet
            else EXACT_COMPETENCE_IN_REAJUSTE_CLAUSE
            if in_clause(m.start())
            else EXACT_DATE_IN_REFERENCED_BUDGET
        )
        # mês-base in planilha/orçamento section is always a valid exact competence
        if re.search(r"m[eê]s[- ]base", m.group(0), re.I):
            state = (
                COMPETENCE_IN_BUDGET_SPREADSHEET
                if is_budget_spreadsheet
                else EXACT_COMPETENCE_IN_REAJUSTE_CLAUSE
                if in_clause(m.start())
                else EXACT_DATE_IN_REFERENCED_BUDGET
            )
        hits.append(
            ExactDataBaseHit(
                state=state,
                value=f"{y:04d}-{mo:02d}",
                value_date=_safe_date(1, mo, y),
                value_month=mo,
                value_year=y,
                kind="month_year",
                document=document,
                page_or_cell=page_hint or _page_hint_from_pos(text, m.start()),
                excerpt=excerpt[:400],
                content_hash=_hash(excerpt),
                relation_to_clause="in_clause" if in_clause(m.start()) else "referenced_budget",
                confidence="high",
                notes=["explicit_mes_base_label"],
            )
        )

    for m in _EXPLICIT_DATA_BASE_SICRO_SINAPI.finditer(text):
        mon_name = m.group(1).lower()
        y = int(m.group(2))
        mo = _MONTHS.get(mon_name)
        if not mo:
            continue
        excerpt = text[max(0, m.start() - 30) : min(len(text), m.end() + 40)].strip()
        kind_idx = "sicro" if "sicro" in m.group(0).lower() else "sinapi"
        hits.append(
            ExactDataBaseHit(
                state=EXACT_COMPETENCE_IN_REAJUSTE_CLAUSE
                if in_clause(m.start())
                else EXACT_DATE_IN_REFERENCED_BUDGET,
                value=f"{kind_idx.upper()}/{mo:02d}/{y}",
                value_date=_safe_date(1, mo, y),
                value_month=mo,
                value_year=y,
                kind=f"{kind_idx}_competence",
                document=document,
                page_or_cell=page_hint or _page_hint_from_pos(text, m.start()),
                excerpt=excerpt[:400],
                content_hash=_hash(excerpt),
                relation_to_clause="in_clause" if in_clause(m.start()) else "referenced_budget",
                confidence="high",
                notes=["explicit_data_base_sicro_sinapi"],
            )
        )

    for m in _EXPLICIT_COMP_INDEX.finditer(text):
        mo, y = int(m.group(1)), int(m.group(2))
        if not (1 <= mo <= 12):
            continue
        ctx = _ctx(text, m.start())
        if _is_artifact_context(ctx):
            notes.append("skipped_index_comp_artifact_context")
            continue
        excerpt = text[max(0, m.start() - 30) : min(len(text), m.end() + 30)].strip()
        hits.append(
            ExactDataBaseHit(
                state=EXACT_COMPETENCE_IN_REAJUSTE_CLAUSE
                if in_clause(m.start())
                else EXACT_DATE_IN_REFERENCED_BUDGET,
                value=f"{y:04d}-{mo:02d}",
                value_date=_safe_date(1, mo, y),
                value_month=mo,
                value_year=y,
                kind="index_competence",
                document=document,
                page_or_cell=page_hint or _page_hint_from_pos(text, m.start()),
                excerpt=excerpt[:400],
                content_hash=_hash(excerpt),
                relation_to_clause="in_clause" if in_clause(m.start()) else "referenced_budget",
                confidence="high",
            )
        )

    # --- Priority B: full dates ONLY with explicit data-base label nearby ---
    for m in _FULL_DATE.finditer(text):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= mo <= 12 and 1 <= d <= 31 and 2000 <= y <= 2035):
            continue
        ctx = _ctx(text, m.start(), 100, 40)
        if _is_artifact_context(ctx):
            notes.append("skipped_full_date_protocol_or_regulatory")
            continue
        near_label = bool(_DATA_BASE_LABEL.search(ctx))
        # Fail-closed: clause window alone is NOT enough without data-base label
        if not near_label:
            continue
        # Extra: reject if look like HH:MM timestamp companion
        after = text[m.end() : m.end() + 12]
        if re.match(r"\s+\d{1,2}:\d{2}", after):
            notes.append("skipped_full_date_timestamp")
            continue
        dt = _safe_date(d, mo, y)
        if not dt:
            continue
        clause = in_clause(m.start())
        if re.search(r"or[cç]amento|planilha|anexo", ctx, re.I) and not clause:
            state = EXACT_DATE_IN_REFERENCED_BUDGET
            rel = "referenced_budget"
        else:
            state = EXACT_DATE_IN_REAJUSTE_CLAUSE
            rel = "in_clause" if clause else "referenced_budget"
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
                relation_to_clause=rel,
                confidence="high" if clause and near_label else "medium",
            )
        )

    for m in _ISO_DATE.finditer(text):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        ctx = _ctx(text, m.start(), 100, 40)
        if _is_artifact_context(ctx):
            continue
        near_label = bool(_DATA_BASE_LABEL.search(ctx))
        if not near_label:
            continue
        dt = _safe_date(d, mo, y)
        if not dt:
            continue
        excerpt = text[max(0, m.start() - 60) : min(len(text), m.end() + 60)].strip()
        hits.append(
            ExactDataBaseHit(
                state=EXACT_DATE_IN_REAJUSTE_CLAUSE
                if in_clause(m.start())
                else EXACT_DATE_IN_REFERENCED_BUDGET,
                value=dt.isoformat(),
                value_date=dt,
                value_month=mo,
                value_year=y,
                kind="full_date",
                document=document,
                page_or_cell=page_hint or _page_hint_from_pos(text, m.start()),
                excerpt=excerpt[:400],
                content_hash=_hash(excerpt),
                relation_to_clause="in_clause" if in_clause(m.start()) else "referenced_budget",
                confidence="high",
            )
        )

    # --- Priority C: month-year ONLY with data-base label (not bare clause window) ---
    for m in _MONTH_YEAR.finditer(text):
        mon_name = m.group(1).lower()
        y = int(m.group(2))
        mo = _MONTHS.get(mon_name)
        if not mo:
            continue
        ctx = _ctx(text, m.start(), 120, 40)
        if _is_artifact_context(ctx):
            notes.append("skipped_month_year_regulatory_or_protocol")
            continue
        near_label = bool(_DATA_BASE_LABEL.search(ctx))
        if is_budget_spreadsheet and near_label:
            state = COMPETENCE_IN_BUDGET_SPREADSHEET
            rel = "spreadsheet"
        elif near_label:
            state = (
                EXACT_COMPETENCE_IN_REAJUSTE_CLAUSE
                if in_clause(m.start())
                else EXACT_DATE_IN_REFERENCED_BUDGET
            )
            rel = "in_clause" if in_clause(m.start()) else "referenced_budget"
        else:
            # bare "janeiro de 2023" in clause window without label → reject
            continue
        val = f"{y:04d}-{mo:02d}"
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
                confidence="high" if near_label else "medium",
            )
        )

    # --- Priority D: SINAPI/SICRO numeric competence with label language ---
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
        ctx = _ctx(text, m.start())
        if _is_artifact_context(ctx):
            continue
        clause = in_clause(m.start())
        state = (
            EXACT_COMPETENCE_IN_REAJUSTE_CLAUSE
            if clause
            else COMPETENCE_IN_BUDGET_SPREADSHEET
            if is_budget_spreadsheet
            else EXACT_DATE_IN_REFERENCED_BUDGET
        )
        excerpt = text[max(0, m.start() - 40) : min(len(text), m.end() + 40)].strip()
        hits.append(
            ExactDataBaseHit(
                state=state,
                value=f"SINAPI/{mo:02d}/{y}",
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
        ctx = _ctx(text, m.start())
        if _is_artifact_context(ctx):
            continue
        clause = in_clause(m.start())
        state = (
            EXACT_COMPETENCE_IN_REAJUSTE_CLAUSE
            if clause
            else COMPETENCE_IN_BUDGET_SPREADSHEET
            if is_budget_spreadsheet
            else EXACT_DATE_IN_REFERENCED_BUDGET
        )
        excerpt = text[max(0, m.start() - 40) : min(len(text), m.end() + 40)].strip()
        hits.append(
            ExactDataBaseHit(
                state=state,
                value=f"SICRO/{mo:02d}/{y}",
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

    if is_budget_spreadsheet:
        for m in _COMP_NUM.finditer(text):
            mo, y = int(m.group(1)), int(m.group(2))
            if not (1 <= mo <= 12):
                continue
            ctx = _ctx(text, m.start())
            if _is_artifact_context(ctx):
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

    satisfying = [h for h in hits if h.state in EXACT_DATA_BASE_SATISFYING]
    keys: set[tuple] = set()
    for h in satisfying:
        if h.value_year and h.value_month:
            keys.add((h.value_year, h.value_month))
        elif h.value:
            keys.add((h.value,))
    conflicts: list[str] = []
    if len(keys) > 1:
        # Prefer explicit labels over full_date artifacts if both present
        explicit = [
            h
            for h in satisfying
            if h.kind
            in {
                "month_year",
                "sicro_competence",
                "sinapi_competence",
                "index_competence",
                "spreadsheet_month",
            }
            and any(
                n in (h.notes or [])
                or h.kind.endswith("competence")
                or "mes_base" in h.kind
                or "explicit" in " ".join(h.notes or [])
                for n in (h.notes or [""])
            )
            or "explicit" in " ".join(h.notes or [])
            or h.kind
            in {
                "sicro_competence",
                "sinapi_competence",
                "index_competence",
                "spreadsheet_month",
            }
            or (h.kind == "month_year" and h.confidence == "high")
        ]
        # If all explicit hits agree on month/year, drop full_date conflicts
        exp_keys: set[tuple] = set()
        for h in explicit:
            if h.value_year and h.value_month:
                exp_keys.add((h.value_year, h.value_month))
        if len(exp_keys) == 1:
            ym = next(iter(exp_keys))
            satisfying = [
                h
                for h in satisfying
                if h.value_year == ym[0] and h.value_month == ym[1]
            ]
        else:
            conflicts = [f"conflicting_values:{sorted(str(k) for k in keys)}"]
            return ExactDataBaseResult(
                state=CONFLICTING_DATES,
                data_base_exata_localizada=False,
                hits=hits,
                primary=None,
                conflicts=conflicts,
                notes=notes + ["multiple_exact_dates_conflict"],
            )

    priority = {
        EXACT_DATE_IN_REAJUSTE_CLAUSE: 4,
        EXACT_COMPETENCE_IN_REAJUSTE_CLAUSE: 3,
        EXACT_DATE_IN_REFERENCED_BUDGET: 2,
        COMPETENCE_IN_BUDGET_SPREADSHEET: 1,
    }
    # Prefer explicit competence labels over full calendar dates
    kind_boost = {
        "sicro_competence": 5,
        "sinapi_competence": 5,
        "index_competence": 4,
        "month_year": 3,
        "spreadsheet_month": 3,
        "full_date": 1,
    }

    def _sort_key(h: ExactDataBaseHit) -> tuple:
        explicit = 1 if any("explicit" in n for n in (h.notes or [])) else 0
        return (
            explicit,
            kind_boost.get(h.kind, 0),
            priority.get(h.state, 0),
            h.confidence == "high",
        )

    satisfying_sorted = sorted(satisfying, key=_sort_key, reverse=True)
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
