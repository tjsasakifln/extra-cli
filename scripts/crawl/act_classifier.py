#!/usr/bin/env python3
"""Deterministic classifier for public procurement acts (DOM/DOE text).

Classifies free-text titles/bodies into procurement act categories without ML.
Used for CIGA/DOM-SC publications and bulk DOE-SC open data rows.

Designed for *assisted production*: high-precision rules, explicit evidence,
confidence scores, and ``needs_human_review`` for ambiguous cases.

Categories (stable machine ids):
  aviso_licitacao, edital, retificacao, errata, suspensao, reabertura,
  revogacao, anulacao, homologacao, adjudicacao, resultado,
  extrato_contrato, termo_aditivo, apostilamento, rescisao,
  ata_registro_precos, intencao_registro_precos, dispensa, inexigibilidade,
  credenciamento, chamamento_publico, consulta_publica,
  outros_atos_contratacao, nao_relacionado, outros
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

CORE_CATEGORIES: tuple[str, ...] = (
    "aviso_licitacao",
    "edital",
    "retificacao",
    "errata",
    "suspensao",
    "reabertura",
    "revogacao",
    "anulacao",
    "homologacao",
    "adjudicacao",
    "resultado",
    "extrato_contrato",
    "termo_aditivo",
    "apostilamento",
    "rescisao",
    "ata_registro_precos",
    "intencao_registro_precos",
    "dispensa",
    "inexigibilidade",
    "credenciamento",
    "chamamento_publico",
    "consulta_publica",
    "outros_atos_contratacao",
    "nao_relacionado",
    "outros",  # legacy alias for weak/unknown residual
)

ALL_CATEGORIES: tuple[str, ...] = tuple(sorted(CORE_CATEGORIES))

# Field weights: title / official type dominate body text.
# When only free-text is provided (legacy API), ``text`` is treated as primary.
_FIELD_WEIGHTS: dict[str, float] = {
    "title": 1.0,
    "official_type": 0.95,
    "subject": 0.85,
    "category": 0.8,
    "secondary": 0.65,
    "text": 0.75,
}

# Confidence thresholds
_CONF_HIGH = 0.8
_CONF_MEDIUM = 0.55
_REVIEW_THRESHOLD = 0.7
_BASE_MATCH_SCORE = 0.72

# Procurement context (used to gate ambiguous verbs like suspensão/anulação)
_PROCUREMENT_CTX = re.compile(
    r"\b("
    r"licita[cç][aã]o|licitat[oó]ri[oa]|certame|edital|preg[aã]o|"
    r"concorr[eê]ncia|tomada\s+de\s+pre[cç]os?|convite|"
    r"dispensa|inexigib|credenciament|chamamento|consulta\s+p[uú]blica|"
    r"contrato|aditiv|apostilament|registro\s+de\s+pre[cç]os?|"
    r"homologa|adjudica|arp\b|irp\b|sess[aã]o\s+p[uú]blica|"
    r"comiss[aã]o\s+de\s+licita|processo\s+licitat"
    r")\b",
    re.I,
)

# Number / identifier patterns that reinforce procurement signal
_NUMBER_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("num_pregao", re.compile(r"\bpreg[aã]o\s+(eletr[oô]nico\s+|presencial\s+)?n[ºo°\.]*\s*\d+", re.I)),
    ("num_edital", re.compile(r"\bedital\s+n[ºo°\.]*\s*\d+", re.I)),
    ("num_contrato", re.compile(r"\bcontrato\s+n[ºo°\.]*\s*\d+", re.I)),
    ("num_processo", re.compile(r"\b(processo|proc\.?)\s*(administrativo\s+)?n[ºo°\.]*\s*[\d./-]+", re.I)),
    ("num_dispensa", re.compile(r"\bdispensa\s+n[ºo°\.]*\s*\d+", re.I)),
    ("num_inexig", re.compile(r"\binexigibilidade\s+n[ºo°\.]*\s*\d+", re.I)),
    ("num_arp", re.compile(r"\b(arp|ata)\s+n[ºo°\.]*\s*\d+", re.I)),
    ("num_pe", re.compile(r"\bpe\s*n[ºo°\.]*\s*\d+/\d{2,4}\b", re.I)),
    ("num_concorrencia", re.compile(r"\bconcorr[eê]ncia\s+n[ºo°\.]*\s*\d+", re.I)),
    ("num_sei", re.compile(r"\bsei\s*n[ºo°\.]*\s*[\d./-]+", re.I)),
]


@dataclass(frozen=True)
class _Rule:
    """A single classification rule.

    Lower ``priority`` wins when multiple categories fire.
    """

    category: str
    pattern: re.Pattern[str]
    priority: int
    name: str
    weight: float = 1.0
    requires_procurement_ctx: bool = False


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.I | re.UNICODE)


# Priority bands (lower = more specific / preferred):
#   10-19 contract lifecycle, 20-29 award/result, 30-39 cancellation/hold,
#   40-49 correction, 50-59 modality exceptions, 60-69 notices, 70-79 residual
_RULES: tuple[_Rule, ...] = (
    # --- contract lifecycle (most specific first) ---
    _Rule(
        "termo_aditivo",
        _rx(r"\b(termo\s+aditiv|aditivo\s+(ao|do|de)\s+contrato|aditamento\s+(contratual|de\s+contrato|ao\s+contrato)|extrato\s+(do\s+)?(termo\s+)?aditiv)"),
        10,
        "termo_aditivo",
    ),
    _Rule(
        "apostilamento",
        _rx(r"\b(apostilamento|termo\s+de\s+apostila|apostila\s+(ao|do|de)\s+contrato)"),
        11,
        "apostilamento",
    ),
    _Rule(
        "rescisao",
        _rx(r"\b(rescis[aã]o\s+(do\s+|de\s+|contratual)?|distrato\s+(contratual|do\s+contrato)?|rescis[aã]o\s+unilateral)"),
        12,
        "rescisao",
        requires_procurement_ctx=False,  # "rescisão" alone is strong enough in DOE/DOM
    ),
    # Specific post-award admin acts — before generic extrato/contrato nº
    _Rule(
        "outros_atos_contratacao",
        _rx(
            r"\b("
            r"prorroga[cç][aã]o\s+(de\s+)?(prazo|vig[eê]ncia|contrato)|"
            r"prorroga[cç][aã]o\s+de\s+vig[eê]ncia|"
            r"reequil[ií]brio\s+econ[oô]mico|"
            r"reajuste\s+(de\s+)?(pre[cç]o|contratual)|"
            r"ordem\s+de\s+servi[cç]o|"
            r"empenho\s+(de\s+despesa|n[ºo°\.])|"
            r"ratifica[cç][aã]o\s+(da\s+)?(dispensa|inexigib|contrata)|"
            r"autoriza[cç][aã]o\s+de\s+contrata[cç][aã]o|"
            r"comiss[aã]o\s+(permanente\s+de\s+)?licita|"
            r"parecer\s+jur[ií]dico\s+(da\s+)?licita|"
            r"designa[cç][aã]o\s+(d[eo]\s+)?pregoeiro|"
            r"equipe\s+de\s+apoio\s+(do\s+)?preg[aã]o"
            r")\b"
        ),
        13,
        "outros_atos_contratacao",
    ),
    _Rule(
        "extrato_contrato",
        _rx(
            r"\b("
            r"extrato\s+(d[eo]\s+)?contrato|"
            r"celebra[cç][aã]o\s+de\s+contrato|"
            r"assinatura\s+de\s+contrato|"
            r"contrato\s+administrativo\s+n[ºo°\.]*\s*\d+|"
            # Title-like "Contrato nº N" (avoid matching only deep body noise)
            r"^contrato\s+n[ºo°\.]*\s*\d+"
            r")"
        ),
        14,
        "extrato_contrato",
    ),
    _Rule(
        "ata_registro_precos",
        _rx(r"\b(ata\s+(de\s+)?registro\s+de\s+pre[cç]os?|arp\s+n[ºo°\.]*|registro\s+de\s+pre[cç]os?\s+n[ºo°\.]*)"),
        15,
        "ata_registro_precos",
    ),
    _Rule(
        "intencao_registro_precos",
        _rx(r"\b(inten[cç][aã]o\s+(de\s+)?registro\s+de\s+pre[cç]os?|\birp\b|ades[aã]o\s+(à|a)\s+(ata\s+de\s+)?registro\s+de\s+pre[cç]os?)"),
        16,
        "intencao_registro_precos",
    ),
    # --- award / result ---
    _Rule("homologacao", _rx(r"\b(homologa[cç][aã]o|homologa(r|do|da)?)\b"), 20, "homologacao"),
    _Rule("adjudicacao", _rx(r"\b(adjudica[cç][aã]o|adjudica(r|do|da)?)\b"), 21, "adjudicacao"),
    _Rule(
        "resultado",
        _rx(r"\b(resultado\s+(d[aoe]\s+)?(licita[cç][aã]o|preg[aã]o|certame|concorr[eê]ncia|dispensa)|resultado\s+final\s+d[ao]\s+(certame|licita)|julgamento\s+(d[aoe]\s+)?(proposta|licita|habilita))"),
        22,
        "resultado",
    ),
    # --- cancel / hold / reopen ---
    _Rule(
        "revogacao",
        _rx(r"\b(revoga[cç][aã]o|revoga(r|do|da)?)\b"),
        30,
        "revogacao",
        requires_procurement_ctx=True,
    ),
    _Rule(
        "anulacao",
        _rx(r"\b(anula[cç][aã]o|anula(r|do|da)?)\b"),
        31,
        "anulacao",
        requires_procurement_ctx=True,
    ),
    _Rule(
        "suspensao",
        _rx(r"\b(suspens[aã]o|suspende(r|u)?|suspenso)\b"),
        32,
        "suspensao",
        requires_procurement_ctx=True,
    ),
    _Rule(
        "reabertura",
        _rx(r"\b(reabertura|reabre|republica[cç][aã]o\s+para\s+reabertura)\b"),
        33,
        "reabertura",
        requires_procurement_ctx=True,
    ),
    # --- correction ---
    _Rule("errata", _rx(r"\b(errata|retifica[cç][aã]o\s+de\s+errata)\b"), 40, "errata"),
    _Rule(
        "retificacao",
        _rx(r"\b(retifica[cç][aã]o|retifica(r|do|da)?|republica[cç][aã]o)\b"),
        41,
        "retificacao",
        requires_procurement_ctx=True,
    ),
    # --- modality / exception ---
    _Rule(
        "dispensa",
        _rx(r"\b(dispensa\s+(de\s+)?licita[cç][aã]o|licita[cç][aã]o\s+dispensada|dispensa\s+eletr[oô]nica|aviso\s+de\s+dispensa)\b"),
        50,
        "dispensa",
    ),
    _Rule(
        "inexigibilidade",
        _rx(r"\b(inexigibilidade|inexig[ií]vel|contrata[cç][aã]o\s+direta\s+por\s+inexigib)"),
        51,
        "inexigibilidade",
    ),
    _Rule(
        "credenciamento",
        _rx(r"\b(credenciamento|chamamento\s+para\s+credenciamento|aviso\s+de\s+credenciamento)\b"),
        52,
        "credenciamento",
    ),
    _Rule(
        "chamamento_publico",
        _rx(r"\b(chamamento\s+p[uú]blico|chamada\s+p[uú]blica)\b"),
        53,
        "chamamento_publico",
    ),
    _Rule(
        "consulta_publica",
        _rx(r"\b(consulta\s+p[uú]blica|audi[eê]ncia\s+p[uú]blica\s+(de\s+)?(licita|edital|contrata))\b"),
        54,
        "consulta_publica",
    ),
    # --- notices ---
    _Rule(
        "edital",
        _rx(r"\b(edital\s+de\s+licita[cç][aã]o|edital\s+de\s+preg[aã]o|aviso\s+de\s+edital|publica[cç][aã]o\s+(do\s+)?edital|edital\s+n[ºo°\.]*\s*\d+)\b"),
        60,
        "edital",
    ),
    _Rule(
        "aviso_licitacao",
        _rx(
            r"\b("
            r"aviso\s+de\s+licita[cç][aã]o|"
            r"aviso\s+de\s+preg[aã]o|"
            r"preg[aã]o\s+(eletr[oô]nico|presencial)|"
            r"concorr[eê]ncia\s+(p[uú]blica|eletr[oô]nica|n[ºo°\.])|"
            r"tomada\s+de\s+pre[cç]os?|"
            r"convite\s+n[ºo°\.]|"
            r"licita[cç][aã]o\s+n[ºo°\.]*\s*\d+|"
            r"abertura\s+(de\s+)?(licita[cç][aã]o|preg[aã]o|certame|sess[aã]o\s+p[uú]blica)"
            r")\b"
        ),
        62,
        "aviso_licitacao",
    ),
)

# Negative expressions → nao_relacionado when no strong procurement rule fired.
_NEGATIVE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("nomeacao_servidor", _rx(r"\b(nomea[cç][aã]o|nomear|nomeado[as]?)\b.*\b(servidor|cargo|fun[cç][aã]o|comissionad)")),
    ("nomeacao_servidor_inv", _rx(r"\b(servidor|cargo|fun[cç][aã]o)\b.*\b(nomea[cç][aã]o|nomeado)")),
    ("exoneracao", _rx(r"\b(exonera[cç][aã]o|exonerar|exonerado[as]?)\b")),
    ("aposentadoria", _rx(r"\b(aposentadoria|aposentar|aposentado[as]?)\b")),
    ("ferias", _rx(r"\b(f[eé]rias\s+(coletivas|reglamentares|do\s+servidor)|escala\s+de\s+f[eé]rias)\b")),
    ("licenca_servidor", _rx(r"\b(licen[cç]a[-\s](pr[eê]mio|m[eé]dica|gestante|paternidade|capacitação|capacitacao))\b")),
    ("diario_ponto", _rx(r"\b(ponto\s+facultativo|recesso\s+administrativo|feriado\s+(municipal|estadual|nacional))\b")),
    ("diarias", _rx(r"\b(di[aá]rias?\s+(de\s+viagem|a\s+servidor)|indeniza[cç][aã]o\s+de\s+transporte)\b")),
    ("portaria_rh", _rx(r"\b(portaria\s+de\s+(designa[cç][aã]o|nomea[cç][aã]o|exonera[cç][aã]o)|lotação|lotacao\s+de\s+servidor)\b")),
    ("concurso_pessoal", _rx(r"\b(concurso\s+p[uú]blico|processo\s+seletivo\s+(simplificado|de\s+pessoal)|edital\s+de\s+concurso\s+p[uú]blico)\b")),
    ("vacancia", _rx(r"\b(declara[cç][aã]o\s+de\s+vac[aâ]ncia|vac[aâ]ncia\s+de\s+cargo)\b")),
    ("posse", _rx(r"\b(posse\s+(em|no|de)\s+cargo|tomar\s+posse)\b")),
    ("lei_organica", _rx(r"\b(lei\s+org[aâ]nica|emenda\s+[àa]\s+lei\s+org[aâ]nica)\b")),
    ("comunicado_interno", _rx(r"\b(comunicado\s+interno|aviso\s+interno\s+de\s+f[eé]rias)\b")),
    ("saude_educacao_admin", _rx(r"\b(calend[aá]rio\s+escolar|matricula\s+de\s+vacina[cç][aã]o|campanha\s+de\s+vacina[cç][aã]o)\b")),
)


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", str(text))
    return re.sub(r"\s+", " ", text).strip()


def _confidence_label(score: float) -> str:
    if score >= _CONF_HIGH:
        return "high"
    if score >= _CONF_MEDIUM:
        return "medium"
    return "low"


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _find_number_terms(blob: str) -> list[str]:
    found: list[str] = []
    for name, pattern in _NUMBER_PATTERNS:
        m = pattern.search(blob)
        if m:
            found.append(name)
    return found


def _has_procurement_ctx(blob: str) -> bool:
    return bool(_PROCUREMENT_CTX.search(blob))


def _collect_field_blobs(
    text: str,
    *,
    secondary: str | None,
    title: str | None,
    subject: str | None,
    official_type: str | None,
    category: str | None,
) -> dict[str, str]:
    fields: dict[str, str] = {}
    t = _normalize(text)
    if t:
        fields["text"] = t
    for key, value in (
        ("secondary", secondary),
        ("title", title),
        ("subject", subject),
        ("official_type", official_type),
        ("category", category),
    ):
        v = _normalize(value)
        if v:
            fields[key] = v
    return fields


def _combined_blob(fields: dict[str, str]) -> str:
    # Prefer stable order for evidence extraction
    order = ("title", "official_type", "subject", "category", "text", "secondary")
    parts = [fields[k] for k in order if k in fields]
    return " ".join(parts).strip()


@dataclass
class _Hit:
    category: str
    rule_name: str
    pattern: str
    field: str
    priority: int
    score: float
    evidence: str
    term: str


def _match_rules(fields: dict[str, str], blob: str) -> list[_Hit]:
    hits: list[_Hit] = []
    proc_ctx = _has_procurement_ctx(blob)

    for rule in _RULES:
        if rule.requires_procurement_ctx and not proc_ctx:
            # Still allow if the rule pattern itself embeds procurement words
            # and matched on a strong field — re-check per field below.
            pass

        for field_name, field_text in fields.items():
            m = rule.pattern.search(field_text)
            if not m:
                continue
            if rule.requires_procurement_ctx:
                # Accept if field itself has procurement context OR full blob does
                # OR the match span already implies it (pattern includes licita etc.)
                local = field_text
                if not (_has_procurement_ctx(local) or proc_ctx):
                    continue

            fw = _FIELD_WEIGHTS.get(field_name, 0.5)
            # Base match score scaled by field weight (title ≈ full base)
            score = _BASE_MATCH_SCORE * rule.weight * (0.55 + 0.45 * fw)
            start = max(0, m.start() - 24)
            end = min(len(field_text), m.end() + 24)
            hits.append(
                _Hit(
                    category=rule.category,
                    rule_name=rule.name,
                    pattern=rule.pattern.pattern,
                    field=field_name,
                    priority=rule.priority,
                    score=score,
                    evidence=field_text[start:end],
                    term=m.group(0),
                )
            )
    return hits


def _match_negatives(blob: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for name, pattern in _NEGATIVE_RULES:
        m = pattern.search(blob)
        if m:
            found.append((name, m.group(0)))
    return found


def _pick_winner(hits: list[_Hit]) -> tuple[_Hit | None, list[str], list[str]]:
    """Select best hit by priority then score.

    Returns (winner, rules_fired, categories_fired).
    """
    if not hits:
        return None, [], []

    # Deduplicate rule names / categories while preserving order
    rules_fired: list[str] = []
    categories_fired: list[str] = []
    for h in sorted(hits, key=lambda x: (x.priority, -x.score)):
        if h.rule_name not in rules_fired:
            rules_fired.append(h.rule_name)
        if h.category not in categories_fired:
            categories_fired.append(h.category)

    # Best: lowest priority number, then highest score, prefer title field
    field_rank = {f: i for i, f in enumerate(("title", "official_type", "subject", "category", "text", "secondary"))}

    def sort_key(h: _Hit) -> tuple[int, float, int]:
        return (h.priority, -h.score, field_rank.get(h.field, 99))

    winner = sorted(hits, key=sort_key)[0]
    return winner, rules_fired, categories_fired


def _build_result(
    *,
    category: str,
    confidence: float,
    rules_fired: list[str],
    terms_found: list[str],
    reason: str,
    needs_human_review: bool,
    matched_rule: str | None,
    evidence: str,
) -> dict[str, object]:
    conf = _clip01(confidence)
    label = _confidence_label(conf)
    return {
        "category": category,
        "confidence": conf,
        "confidence_label": label,
        "rules_fired": rules_fired,
        "terms_found": terms_found,
        "reason": reason,
        "needs_human_review": needs_human_review,
        # Legacy keys (backward compatible consumers)
        "matched_rule": matched_rule,
        "evidence": evidence,
    }


def classify_act(
    text: str,
    *,
    secondary: str | None = None,
    title: str | None = None,
    subject: str | None = None,
    official_type: str | None = None,
    category: str | None = None,
) -> dict[str, object]:
    """Classify a single act using multi-field deterministic rules.

    Parameters
    ----------
    text:
        Primary free-text body (or combined blob when only one field exists).
    secondary:
        Optional extra text (e.g. body when ``text`` is a title).
    title, subject, official_type, category:
        Structured metadata from DOM/DOE sources when available.

    Returns
    -------
    dict with:
      category, confidence (float 0-1), confidence_label ('high'|'medium'|'low'),
      rules_fired, terms_found, reason, needs_human_review,
      matched_rule (legacy), evidence (legacy)
    """
    fields = _collect_field_blobs(
        text,
        secondary=secondary,
        title=title,
        subject=subject,
        official_type=official_type,
        category=category,
    )
    blob = _combined_blob(fields)

    if not blob:
        return _build_result(
            category="outros",
            confidence=0.1,
            rules_fired=[],
            terms_found=[],
            reason="texto vazio",
            needs_human_review=True,
            matched_rule=None,
            evidence="",
        )

    number_terms = _find_number_terms(blob)
    hits = _match_rules(fields, blob)
    winner, rules_fired, categories_fired = _pick_winner(hits)
    negatives = _match_negatives(blob)
    neg_names = [n for n, _ in negatives]
    terms_found: list[str] = []

    if winner:
        terms_found.append(winner.term.lower())
        for h in hits:
            t = h.term.lower()
            if t not in terms_found:
                terms_found.append(t)
        terms_found.extend(number_terms)

        # Competitive ambiguity: other categories within priority band of winner
        winner_priority = winner.priority
        competitive = [
            c
            for c in categories_fired
            if c != winner.category
            and any(
                h.category == c and abs(h.priority - winner_priority) <= 15 for h in hits
            )
        ]
        multi_cat = len(competitive) > 0
        conf = winner.score
        # Boost when number patterns support procurement
        if number_terms:
            conf += 0.08 * min(len(number_terms), 3)
        # Boost when title/official_type matched
        if winner.field in {"title", "official_type"}:
            conf += 0.12
        # Legacy single-blob call: text is the only signal → treat as primary
        if winner.field == "text" and set(fields.keys()) <= {"text", "secondary"}:
            conf += 0.12
        # Penalty only for close competing categories (e.g. homologacao vs adjudicacao)
        if multi_cat:
            conf -= 0.1

        conf = _clip01(conf)

        # Human review when confidence low, true ambiguity, or residual buckets
        needs_review = (
            conf < _REVIEW_THRESHOLD
            or multi_cat
            or winner.category in {"outros", "outros_atos_contratacao"}
            or len(categories_fired) > 2
        )

        reason_parts = [
            f"regra '{winner.rule_name}' em campo '{winner.field}'",
        ]
        if number_terms:
            reason_parts.append(f"padroes numericos: {', '.join(number_terms)}")
        if multi_cat:
            reason_parts.append(f"categorias candidatas: {', '.join(categories_fired)}")
        if negatives:
            reason_parts.append(f"expressoes negativas tambem presentes: {', '.join(neg_names)}")
            needs_review = True

        return _build_result(
            category=winner.category,
            confidence=conf,
            rules_fired=rules_fired,
            terms_found=terms_found,
            reason="; ".join(reason_parts),
            needs_human_review=needs_review,
            matched_rule=winner.pattern,
            evidence=winner.evidence,
        )

    # No positive rule — check negatives
    if negatives:
        terms_found = [t.lower() for _, t in negatives]
        terms_found.extend(number_terms)
        # If number patterns look like procurement but no rule matched → review
        conf = 0.82 if not number_terms else 0.55
        return _build_result(
            category="nao_relacionado",
            confidence=conf,
            rules_fired=[f"neg:{n}" for n in neg_names],
            terms_found=terms_found,
            reason=f"expressoes nao relacionadas a contratacao: {', '.join(neg_names)}",
            needs_human_review=bool(number_terms),
            matched_rule=negatives[0][0],
            evidence=negatives[0][1],
        )

    # Residual: weak procurement lexicon without a specific act
    if _has_procurement_ctx(blob) or number_terms:
        terms_found = number_terms[:]
        m = _PROCUREMENT_CTX.search(blob)
        if m:
            terms_found.insert(0, m.group(0).lower())
        return _build_result(
            category="outros_atos_contratacao",
            confidence=0.4 if number_terms else 0.35,
            rules_fired=["procurement_context_residual"],
            terms_found=terms_found,
            reason="contexto de contratacao detectado sem ato especifico",
            needs_human_review=True,
            matched_rule="procurement_context_residual",
            evidence=blob[:100],
        )

    return _build_result(
        category="outros",
        confidence=0.15,
        rules_fired=[],
        terms_found=number_terms,
        reason="nenhuma regra de classificacao acionada",
        needs_human_review=True,
        matched_rule=None,
        evidence=blob[:80],
    )


def classify_many(texts: Iterable[str]) -> list[dict[str, object]]:
    """Classify an iterable of plain texts (backward-compatible helper)."""
    return [classify_act(t) for t in texts]


def classify_record(record: dict[str, Any]) -> dict[str, object]:
    """Classify a DOM/DOE-like record dict.

    Recognized keys (any subset): texto/text/body, titulo/title,
    assunto/subject, tipo/tipo_ato/official_type, categoria/category,
    secondary/descricao.
    """
    text = (
        record.get("texto")
        or record.get("text")
        or record.get("body")
        or record.get("conteudo")
        or ""
    )
    return classify_act(
        str(text),
        secondary=_first_str(record, "secondary", "descricao", "ementa"),
        title=_first_str(record, "titulo", "title", "dsTitulo"),
        subject=_first_str(record, "assunto", "subject"),
        official_type=_first_str(record, "tipo", "tipo_ato", "official_type", "tipo_publicacao"),
        category=_first_str(record, "categoria", "category", "cdCategoria"),
    )


def _first_str(record: dict[str, Any], *keys: str) -> str | None:
    for k in keys:
        v = record.get(k)
        if v is not None and str(v).strip():
            return str(v)
    return None
