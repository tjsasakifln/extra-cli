"""Document type classification with confidence and human-review flags."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from scripts.edital_case.models import CLASSIFY_RULE_VERSION, DOCUMENT_TYPES

# (type, weight, filename patterns, content patterns)
# More specific types first for filename priority.
_RULES: list[tuple[str, float, list[str], list[str]]] = [
    (
        "TERMO_DE_REFERENCIA",
        1.2,
        [
            r"termo.?de.?refer",
            r"termo_referencia",
            r"(^|[^a-z])tr([^a-z]|$)",
            r"_tr[\._-]",
            r"(^|/)tr\.",
            r"\btr\.pdf\b",
        ],
        [
            r"termo\s+de\s+refer[eê]ncia",
            r"^\s*termo\s+de\s+refer",
        ],
    ),
    (
        "ESTUDO_TECNICO_PRELIMINAR",
        1.2,
        [r"estudo.?t[eé]cnico", r"(^|[^a-z])etp([^a-z]|$)", r"_etp", r"etpmanut"],
        [r"estudo\s+t[eé]cnico\s+preliminar", r"\betp\b"],
    ),
    (
        "PLANILHA_ORCAMENTARIA",
        1.0,
        [r"planilha", r"or[cç]amento", r"orcament"],
        [r"planilha\s+or[cç]ament", r"pre[cç]o\s+unit[aá]rio"],
    ),
    (
        "CRONOGRAMA",
        0.95,
        [r"cronograma"],
        [r"cronograma\s+f[ií]sico", r"cronograma\s+de\s+execu"],
    ),
    (
        "BDI",
        0.9,
        [r"(^|[^a-z])bdi([^a-z]|$)"],
        [r"bonifica[cç][aã]o\s+de\s+despesas\s+indiretas", r"\bBDI\b"],
    ),
    (
        "COMPOSICOES",
        0.85,
        [r"composi[cç]"],
        [r"composi[cç][aã]o\s+de\s+custos", r"insumos"],
    ),
    (
        "MINUTA_CONTRATUAL",
        1.05,
        [r"minuta", r"contrato", r"aditivo"],
        [
            r"minuta\s+(de\s+|do\s+)?contrato",
            r"cl[aá]usula\s+primeira",
            r"contrato\s+administrativo",
        ],
    ),
    (
        "MEMORIAL_DESCRITIVO",
        0.9,
        [r"memorial"],
        [r"memorial\s+descritivo"],
    ),
    (
        "PROJETO",
        0.85,
        [r"projeto"],
        [r"projeto\s+b[aá]sico", r"projeto\s+executivo"],
    ),
    (
        "MODELO_DECLARACAO",
        0.75,
        [r"declara[cç]", r"modelo"],
        [r"modelo\s+de\s+declara[cç]", r"declaro\s+para\s+os\s+devidos"],
    ),
    (
        "AVISO",
        0.7,
        [r"aviso"],
        [r"aviso\s+de\s+licita", r"aviso\s+de\s+contrata"],
    ),
    (
        "ERRATA",
        0.9,
        [r"errata"],
        [r"\berrata\b"],
    ),
    (
        "ESCLARECIMENTO",
        0.8,
        [r"esclarec"],
        [r"resposta\s+a\s+pedido\s+de\s+esclarec"],
    ),
    (
        "EDITAL",
        1.0,
        [r"edital", r"instrumento\s+convocat"],
        [
            r"edital\s+de\s+pre[gğ][aã]o",
            r"edital\s+de\s+licita",
            r"pre[gğ][aã]o\s+eletr[oô]nico\s+n",
            r"processo\s+licitat[oó]rio",
        ],
    ),
    (
        "ANEXO_TECNICO",
        0.6,
        [r"anexo.*tec", r"especifica"],
        [r"especifica[cç][oõ]es\s+t[eé]cnicas"],
    ),
    (
        "ANEXO_ADMINISTRATIVO",
        0.55,
        [r"anexo"],
        [r"anexo\s+[ivxlc0-9]+"],
    ),
]


def _fold(s: str) -> str:
    nk = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nk if not unicodedata.combining(c)).lower()


def classify_document(
    *,
    filename: str,
    text_sample: str,
    extension: str,
) -> dict[str, Any]:
    name = filename.lower()
    name_fold = _fold(filename)
    text = (text_sample or "")[:20000]
    text_head = text[:3000]
    scores: dict[str, float] = {t: 0.0 for t in DOCUMENT_TYPES}
    signals: list[dict[str, Any]] = []

    if extension.lower() not in {
        ".pdf",
        ".docx",
        ".xlsx",
        ".xls",
        ".html",
        ".htm",
        ".txt",
        ".md",
        ".csv",
    }:
        return {
            "result": "UNSUPPORTED",
            "confidence": 1.0,
            "signals": [{"kind": "extension", "value": extension}],
            "rule_version": CLASSIFY_RULE_VERSION,
            "needs_human_review": False,
            "evidence": f"extension {extension} not supported for content classify",
        }

    for dtype, weight, name_pats, content_pats in _RULES:
        for pat in name_pats:
            if re.search(pat, name, re.I) or re.search(pat, name_fold, re.I):
                scores[dtype] += 0.55 * weight
                signals.append({"kind": "filename", "pattern": pat, "type": dtype})
        for pat in content_pats:
            if text and re.search(pat, text, re.I | re.M):
                # Title-like hits in first pages get a boost
                boost = 1.35 if re.search(pat, text_head, re.I | re.M) else 1.0
                scores[dtype] += 0.6 * weight * boost
                signals.append({"kind": "content", "pattern": pat, "type": dtype})

    # Explicit strong title override (common Brazilian docs)
    title_overrides: list[tuple[str, str]] = [
        (r"termo\s+de\s+refer[eê]ncia", "TERMO_DE_REFERENCIA"),
        (r"estudo\s+t[eé]cnico\s+preliminar", "ESTUDO_TECNICO_PRELIMINAR"),
        (r"edital\s+de\s+(pre[gğ][aã]o|licita|concorr)", "EDITAL"),
        (r"minuta\s+(do\s+|de\s+)?contrato", "MINUTA_CONTRATUAL"),
        (r"planilha\s+or[cç]ament", "PLANILHA_ORCAMENTARIA"),
    ]
    for pat, dtype in title_overrides:
        if re.search(pat, text_head, re.I):
            scores[dtype] += 1.5
            signals.append({"kind": "title_override", "pattern": pat, "type": dtype})

    # Filename-first guess (first matching specific rule)
    name_guess = None
    for dtype, _w, name_pats, _c in _RULES:
        if any(re.search(p, name, re.I) or re.search(p, name_fold, re.I) for p in name_pats):
            name_guess = dtype
            break

    # Prefer unambiguous filename for specialized types when content is noisy
    # (editals often *mention* TR/planilha/minuta without being those docs).
    specialized = {
        "TERMO_DE_REFERENCIA",
        "ESTUDO_TECNICO_PRELIMINAR",
        "PLANILHA_ORCAMENTARIA",
        "MINUTA_CONTRATUAL",
        "MEMORIAL_DESCRITIVO",
        "CRONOGRAMA",
        "BDI",
        "COMPOSICOES",
        "PROJETO",
    }
    if name_guess in specialized and scores.get(name_guess, 0) >= 0.4:
        # dampen generic EDITAL score when filename is specialized annex
        scores["EDITAL"] = min(scores.get("EDITAL", 0), scores[name_guess] * 0.5)
        signals.append(
            {
                "kind": "filename_priority",
                "type": name_guess,
                "note": "specialized filename preferred over body mentions",
            }
        )

    # Workbook named planilha/orçamento often *contains* a BDI sheet; that must not
    # reclassify the whole document as BDI-only (loses PLANILHA_ORCAMENTARIA role).
    if (
        name_guess == "PLANILHA_ORCAMENTARIA"
        and extension.lower() in {".xlsx", ".xlsm", ".xls"}
        and scores.get("PLANILHA_ORCAMENTARIA", 0) >= 0.4
    ):
        scores["PLANILHA_ORCAMENTARIA"] = max(
            scores.get("PLANILHA_ORCAMENTARIA", 0),
            scores.get("BDI", 0) + 0.35,
        )
        scores["BDI"] = min(scores.get("BDI", 0), scores["PLANILHA_ORCAMENTARIA"] * 0.55)
        signals.append(
            {
                "kind": "workbook_filename_priority",
                "type": "PLANILHA_ORCAMENTARIA",
                "note": "xlsx filename planilha beats BDI sheet content",
            }
        )

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best_type, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0

    if best_score < 0.35:
        result = "UNKNOWN"
        confidence = round(1.0 - best_score, 3)
        needs_human = True
    else:
        result = best_type
        confidence = round(min(0.99, best_score / (best_score + second_score + 0.15)), 3)
        needs_human = confidence < 0.65 or (best_score - second_score) < 0.2

    if name_guess and result not in {name_guess, "UNKNOWN", "UNSUPPORTED"} and confidence > 0.7:
        needs_human = True
        signals.append(
            {
                "kind": "contradiction",
                "filename_guess": name_guess,
                "content_guess": result,
            }
        )

    evidence = "; ".join(f"{s['kind']}:{s.get('pattern') or s.get('value')}" for s in signals[:8])
    return {
        "result": result if result in DOCUMENT_TYPES else "UNKNOWN",
        "confidence": confidence,
        "signals": signals[:20],
        "rule_version": CLASSIFY_RULE_VERSION,
        "needs_human_review": needs_human,
        "evidence": evidence or "no strong signals",
        "scores_top": ranked[:5],
    }
