"""Canonical claim-language rules for Extra Consultoria (DoD §25).

Executable guards so reports and CLIs cannot silently overclaim.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable

# Patterns that assert physical works tracking (out of product scope).
WORKS_TRACKING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bacompanhamento\s+f[ií]sico\s+de\s+obras?\b", re.I),
    re.compile(r"\bacompanha(?:r|mento)?\s+obras?\s+em\s+campo\b", re.I),
    re.compile(r"\bdi[aá]rio\s+de\s+obra\b", re.I),
    re.compile(r"\bmedição\s+em\s+campo\b", re.I),
    re.compile(r"\bfiscalização\s+f[ií]sica\b", re.I),
)

# Phrases that overclaim market completeness.
COMPLETE_MARKET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bconjunto\s+completo\s+de\s+concorrentes\b", re.I),
    re.compile(r"\btodos\s+os\s+concorrentes\b", re.I),
    re.compile(r"\bmercado\s+completo\b", re.I),
)

# Treating missing data as "no tender exists".
ABSENCE_AS_NO_TENDER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsem\s+licitaç[aã]o\b", re.I),
    re.compile(r"\bn[aã]o\s+h[aá]\s+licitaç[aã]o\b", re.I),
    re.compile(r"\baus[eê]ncia\s+de\s+licitaç[aã]o\b", re.I),
)


@dataclass(frozen=True)
class ClaimCheckResult:
    ok: bool
    rule_id: str
    message: str
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def absence_is_not_no_tender(
    *,
    has_valid_query: bool,
    text: str | None = None,
) -> ClaimCheckResult:
    """Absence of rows is not 'no tender' without a valid consultation."""
    if text and any(p.search(text) for p in ABSENCE_AS_NO_TENDER_PATTERNS):
        if not has_valid_query:
            return ClaimCheckResult(
                ok=False,
                rule_id="absence_requires_valid_query",
                message=(
                    "Ausência de dados não pode ser rotulada como ausência de "
                    "licitação sem consulta válida."
                ),
            )
    if not has_valid_query:
        return ClaimCheckResult(
            ok=True,
            rule_id="absence_requires_valid_query",
            message="Sem consulta válida — use status NOT_CONSULTED / UNKNOWN, não 'sem licitação'.",
            details={"recommended_status": "NOT_CONSULTED"},
        )
    return ClaimCheckResult(
        ok=True,
        rule_id="absence_requires_valid_query",
        message="Consulta válida presente; ausência de linhas pode ser reportada com limitações.",
    )


def winners_are_not_complete_competitors(
    *,
    known_winners: int,
    claim_complete: bool,
) -> ClaimCheckResult:
    """Known winners ≠ full competitor set."""
    if claim_complete:
        return ClaimCheckResult(
            ok=False,
            rule_id="winners_not_complete_competitors",
            message=(
                "Vencedor conhecido não é conjunto completo de concorrentes "
                f"(known_winners={known_winners})."
            ),
            details={"known_winners": known_winners},
        )
    return ClaimCheckResult(
        ok=True,
        rule_id="winners_not_complete_competitors",
        message="Claim de completude de concorrentes ausente — OK.",
        details={"known_winners": known_winners, "label": "observáveis"},
    )


def unidentified_participant_not_nonexistent(
    *,
    participant_id: str | None,
    treated_as_nonexistent: bool,
) -> ClaimCheckResult:
    if treated_as_nonexistent and not participant_id:
        return ClaimCheckResult(
            ok=False,
            rule_id="unidentified_not_nonexistent",
            message="Participante não identificado não pode ser tratado como inexistente.",
        )
    return ClaimCheckResult(
        ok=True,
        rule_id="unidentified_not_nonexistent",
        message="Participante ausente rotulado como UNKNOWN/UNIDENTIFIED — OK.",
        details={"status": "UNKNOWN" if not participant_id else "IDENTIFIED"},
    )


def win_rate(
    *,
    wins: int,
    proposals_submitted: int | None,
) -> ClaimCheckResult:
    """Win rate requires known submitted proposals in denominator."""
    if proposals_submitted is None or proposals_submitted <= 0:
        return ClaimCheckResult(
            ok=False,
            rule_id="win_rate_requires_proposals",
            message="Win rate não é calculado sem propostas enviadas (denominador).",
            details={"wins": wins, "proposals_submitted": proposals_submitted},
        )
    rate = wins / proposals_submitted
    return ClaimCheckResult(
        ok=True,
        rule_id="win_rate_requires_proposals",
        message="Win rate calculável.",
        details={
            "wins": wins,
            "proposals_submitted": proposals_submitted,
            "win_rate": rate,
        },
    )


def score_is_not_probability(
    *,
    label: str,
    calibrated: bool,
) -> ClaimCheckResult:
    lab = label.lower()
    if "probabilidade" in lab or lab.strip() in {"probability", "p(win)", "p_win"}:
        if not calibrated:
            return ClaimCheckResult(
                ok=False,
                rule_id="score_not_probability",
                message="Score não é probabilidade sem calibração.",
                details={"label": label, "calibrated": calibrated},
            )
    return ClaimCheckResult(
        ok=True,
        rule_id="score_not_probability",
        message="Rótulo de score/probabilidade aceitável.",
        details={"label": label, "calibrated": calibrated},
    )


def report_has_limitations(limitations: Iterable[str] | None) -> ClaimCheckResult:
    items = [x.strip() for x in (limitations or []) if str(x).strip()]
    if not items:
        return ClaimCheckResult(
            ok=False,
            rule_id="reports_show_limitations",
            message="Relatórios devem exibir limitações relevantes.",
        )
    return ClaimCheckResult(
        ok=True,
        rule_id="reports_show_limitations",
        message="Limitações presentes.",
        details={"count": len(items)},
    )


_SCOPE_EXCLUSION = re.compile(
    r"(fora\s+de\s+escopo|n[aã]o\s+(?:faz|inclui|acompanha)|exclu[ií]do|"
    r"sem\s+(?:acompanhamento|medi[cç][aã]o)|n[aã]o\s+destinado)",
    re.I,
)


def text_forbids_works_tracking(text: str) -> ClaimCheckResult:
    """Flag affirmative claims of physical works tracking.

    Mentions inside explicit scope-exclusion language are allowed
    (e.g. DOD header stating physical works are out of scope).
    """
    hits: list[str] = []
    for p in WORKS_TRACKING_PATTERNS:
        for m in p.finditer(text):
            start = max(0, m.start() - 120)
            end = min(len(text), m.end() + 120)
            window = text[start:end]
            if _SCOPE_EXCLUSION.search(window):
                continue
            hits.append(p.pattern)
    if hits:
        return ClaimCheckResult(
            ok=False,
            rule_id="no_works_tracking_claim",
            message="Documento afirma acompanhamento físico de obras (fora de escopo).",
            details={"patterns": hits},
        )
    return ClaimCheckResult(
        ok=True,
        rule_id="no_works_tracking_claim",
        message="Sem claim de acompanhamento físico de obras.",
    )


def scan_texts_for_works_claims(texts: dict[str, str]) -> list[ClaimCheckResult]:
    return [
        ClaimCheckResult(
            ok=r.ok,
            rule_id=r.rule_id,
            message=f"{path}: {r.message}",
            details=r.details,
        )
        for path, text in texts.items()
        for r in [text_forbids_works_tracking(text)]
        if not r.ok
    ]


# Canonical forbidden claims for report metadata (extends commercial pack).
LANGUAGE_CLAIMS_FORBIDDEN: tuple[str, ...] = (
    "Ausência de dados como ausência de licitação sem consulta válida",
    "Vencedores observados como conjunto completo de concorrentes",
    "Participante não identificado tratado como inexistente",
    "Win rate sem propostas enviadas no denominador",
    "Score rotulado como probabilidade sem calibração",
    "Relatório sem limitações relevantes",
    "Afirmar que o projeto acompanha obras fisicamente",
    "Percentual sem denominador N",
    "Score/percentual sem limitações explícitas",
    "Dado UNTRUSTED apresentado como pronto para decisão",
)

LANGUAGE_CLAIMS_ALLOWED: tuple[str, ...] = (
    "Reportar NOT_CONSULTED / UNKNOWN quando não houve consulta válida",
    "Listar concorrentes observáveis com N e limitações",
    "Usar score/ranking como ordenação, não probabilidade, sem calibração",
    "Exibir limitações, cobertura, freshness e blockers nos relatórios",
    "Acompanhamento administrativo de contratos (não físico de obra)",
    "Exibir trust_level TRUSTED|DEGRADED|UNTRUSTED|UNKNOWN",
    "Percentuais apenas com N e limitações",
)
