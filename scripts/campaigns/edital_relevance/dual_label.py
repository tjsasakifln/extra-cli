#!/usr/bin/env python3
"""Independent dual labeling for edital relevance gold corpus.

Two reviewers apply *different* decision trees based on Extra Construtora
commercial inclusion/exclusion criteria. Neither uses sector_classifier
output (avoids circular selection/labeling contamination).

Labels: RELEVANT | IRRELEVANT | UNDECIDABLE
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def _norm(text: str | None) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", str(text))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"\s+", " ", t.lower()).strip()
    return t


# Reviewer A: inclusion-first (desired object types for Extra empreiteira)
_A_INCLUSION = [
    r"\bpavimenta(c|ç)",
    r"\brecapeamento\b",
    r"\bcapeamento\s+asfalt",
    r"\bdrenagem\b",
    r"\bgaleria\s+pluvial\b",
    r"\bterraplenagem\b|\bterraplanagem\b",
    r"\bmuro\s+de\s+arrimo\b|\bcontencao\b",
    r"\bsaneamento\s+(basico|ambiental|urbano)\b",
    r"\brede\s+(de\s+)?esgoto\b|\besgotamento\s+sanitario\b",
    r"\badutora\b|\brede\s+coletora\b",
    r"\binfraestrutura\s+urbana\b|\burbanizacao\b",
    r"\bcal[cç]ad[ao]\b|\bpasseio\s+publico\b",
    r"\bconstru[cç][aã]o\s+de\s+(edif|pred|escola|creche|ubs|ginasio|quadra|"
    r"unidades?\s+habitacionais?|centro\s+administrativo|sede|delegacia)",
    r"\bamplia[cç][aã]o\s+de\s+(escola|creche|pred|edif|ubs|hospital|ginasio|rede)",
    r"\breforma\s+(predial|de\s+edif|de\s+pred|de\s+escola|de\s+creche|estrutural|"
    r"e\s+ampliacao|e\s+adequacao|da\s+delegacia|com\s+fornecimento)",
    r"\bexecu[cç][aã]o\s+de\s+(obra|reforma|cobertura|servicos?\s+de\s+obras?)",
    r"\bmanuten[cç][aã]o\s+(predial|civil\s+das\s+edifica|de\s+edif)",
    r"\bobra[s]?\s+de\s+engenharia\b|\bobras?\s+e\s+servicos?\s+de\s+engenharia\b",
    r"\bexecu[cç][aã]o\s+de\s+obras?\b",
    r"\bempreitada\b",
    r"\bempresa\s+(de\s+)?engenharia\b",
    r"\bponte\b|\bviaduto\b|\bpassarela\b|\bkit\s+ponte\b",
    r"\brefor[cç]o\s+estrutural\b",
    r"\bimpermeabiliza[cç]",
    r"\bprojeto[s]?\s+(executivo|basico|de\s+engenharia|arquitetonic)",
    r"\bfiscaliza[cç][aã]o\s+(de\s+)?(obra|engenharia)\b",
    r"\bobra\s+emergencial\b.+\b(rodovia|via|estrada)\b",
]

_A_EXCLUSION = [
    r"\bmedicamento\b|\bfarmaco\b|\bvacina\b",
    r"\bexames?\s+(laborator|clinico)",
    r"\bcomputador\b|\bnotebook\b|\bsoftware\b|\blicenca\s+de\s+uso\b",
    r"\bcombustivel\b|\bgasolina\b|\bdiesel\b",
    r"\buniforme\b|\bvestuario\b",
    r"\bgeneros?\s+aliment|\bmerenda\b|\brefeicao\b",
    r"\bmanuten[cç][aã]o\s+da\s+frota\b|\bfrota\s+municipal\b",
    r"\bseguro\s+(de\s+)?(frota|veiculo|automovel)\b",
    r"\bvoip\b|\btelefonia\b|\bpabx\b",
    r"\blimpeza\s+(predial|urbana|publica)\b|\bjardinagem\b|\bro[cç]ada\b",
    r"\bcursos?\s+(para|de)\b|\bcapacita[cç][aã]o\b|\btreinamento\b",
    r"\boficina\s+de\s+karate\b|\bevento\s+cultural\b",
    r"\barrecadacao\s+bancaria\b|\bservicos?\s+bancarios?\b",
    r"\bfisioterapia\b|\bcastracao\b|\bzoonoses\b",
    r"\blen[cç]ois?\b|\bmantas?\b|\benxoval\b",
    r"\bconstrucao\s+de\s+conhecimento\b",
    r"\baquisicao\s+de\s+(equipamentos?|computador|veiculo)\b",
    r"\bcredenciamento\b(?!.*\b(obra|engenharia|paviment))",
]

# Reviewer B: exclusion-first, then engineering execution signals
_B_HARD_EXCLUDE = [
    r"\bmedicamento|exame[s]?\s+laborator|fisioterapia|vacina\b",
    r"\bcomputador|notebook|software|informatica|nuvem|cloud\b",
    r"\bcombustivel|gasolina|diesel\b",
    r"\buniforme|vestuario|calcado\s+de\s+seguranca\b",
    r"\bmerenda|generos?\s+aliment|refeicao\b",
    r"\bfrota\b|\boficina\s+mecanica\b|\bseguro\b.+\bveiculo",
    r"\bvoip|telefonia|pabx|central\s+telefonica\b",
    r"\blimpeza\s+predial|jardinagem|rocada|capeina\b",
    r"\bcurso|capacitacao|treinamento|professores\b",
    r"\bkarate|evento\s+cultural|oficina\s+cultural\b",
    r"\barrecadacao|servicos?\s+bancarios?|instituicoes?\s+financeiras?\b",
    r"\bcastracao|zoonoses|len[cç]ois?\b",
    r"\bconstrucao\s+de\s+conhecimento\b",
    r"\bpublicidade|propaganda|midia\s+outdoor\b",
    r"\bassessoria\s+(juridica|contabil|administrativa)\b",
]

_B_ENG_EXEC = [
    r"\bexecu[cç][aã]o\b.+\b(obra|paviment|drenagem|terrapl|saneamento|reforma|cobertura)",
    r"\bpavimentacao\s+asfalt|\basfalto\b.+\bvia",
    r"\bdrenagem\s+(urbana|pluvial)|\bgaleria\s+pluvial\b",
    r"\bterraplenagem|\bterraplanagem|\barrimo\b",
    r"\bsaneamento\s+basico|\brede\s+de\s+esgoto\b",
    r"\bconstru[cç][aã]o\s+de\s+(escola|creche|predio|edificio|ubs|unidades?\s+habitacionais?|"
    r"centro\s+administrativo|sede|delegacia|quadra)",
    r"\bamplia[cç][aã]o\s+de\s+(escola|creche|ubs|predio|rede)",
    r"\breforma\s+(predial|de\s+escola|estrutural|e\s+ampliacao|e\s+adequacao)",
    r"\bmanuten[cç][aã]o\s+predial\b",
    r"\bobras?\s+de\s+engenharia\b|\bobras?\s+e\s+servicos?\s+de\s+engenharia\b|"
    r"\bempreitada\s+(global|integral)?",
    r"\bempresa\s+(especializada\s+)?(em\s+)?engenharia\b",
    r"\bponte\b|\bviaduto\b|\bkit\s+ponte\b",
    r"\brefor[cç]o\s+estrutural\b",
    r"\bimpermeabiliza[cç]",
    r"\bprojeto\s+(executivo|basico)\b.+\bengenharia",
    r"\bfiscaliza[cç][aã]o\s+de\s+obra\b",
    r"\binfraestrutura\s+urbana\b|\bcal[cç]ada\b.+\b(execu|implant)",
    r"\bobra\s+emergencial\b",
]


_INCOMPLETE_NOTICE = re.compile(
    r"\b("
    r"aviso de suspens|suspensa|homologa|"
    r"extrato do aditivo|termo de homologa|termo de ratifica|"
    r"retifica[cç][aã]o|rescisao de ata|"
    r"aviso de licitacao|"
    r"comunicamos na forma da lei|"
    r"chamamento publico para cotacao|"
    r"cotacao de precos|"
    r"extrato\s+(de\s+)?(contrato|ata|t\.?a\.?)|"
    r"lei ordinaria|"
    r"altera a lei|"
    r"institui o plano de saneamento"
    r")\b",
    re.I,
)

_HAS_EXPLICIT_OBJECT = re.compile(
    r"\b("
    r"objeto\s*[:.]|objeto da contrat|constitui objeto|"
    r"execu[cç][aã]o\s+de\s+(obra|reforma|paviment|drenagem|cobertura)|"
    r"constru[cç][aã]o\s+de|empreitada|pavimenta|drenagem urbana|"
    r"obra de engenharia|reforma predial"
    r")\b",
    re.I,
)


def label_reviewer_a(objeto: str, *, titulo: str | None = None) -> tuple[str, str]:
    """Inclusion-first independent reviewer."""
    blob = _norm(f"{titulo or ''} {objeto or ''}")
    if not blob or len(blob) < 8:
        return "UNDECIDABLE", "texto insuficiente para adjudicação A"
    # Procedural notices without explicit object description → UNDECIDABLE
    if _INCOMPLETE_NOTICE.search(blob) and not _HAS_EXPLICIT_OBJECT.search(blob):
        return "UNDECIDABLE", "A-aviso procedural sem objeto de obra explícito"

    for pat in _A_EXCLUSION:
        if re.search(pat, blob, re.I):
            # material-only exception: still IRRELEVANT for pure acquisition
            return "IRRELEVANT", f"A-exclusion matched: {pat}"

    hits = [pat for pat in _A_INCLUSION if re.search(pat, blob, re.I)]
    if hits:
        return "RELEVANT", f"A-inclusion hits={len(hits)}"

    # Weak civil signals without clear exclusion
    if re.search(r"\bobra\b|\bengenharia\s+civil\b|\bedificacao\b", blob, re.I):
        if re.search(r"\b(aquisicao|fornecimento)\b.+\b(material|equipamento)\b", blob, re.I):
            return "IRRELEVANT", "A-material/equipamento sem execução de obra"
        return "UNDECIDABLE", "A-sinais fracos de obra sem inclusão clara"

    return "IRRELEVANT", "A-sem inclusão de engenharia Extra"


def label_reviewer_b(objeto: str, *, titulo: str | None = None) -> tuple[str, str]:
    """Exclusion-first independent reviewer."""
    blob = _norm(f"{titulo or ''} {objeto or ''}")
    if not blob or len(blob) < 8:
        return "UNDECIDABLE", "texto insuficiente para adjudicação B"
    if _INCOMPLETE_NOTICE.search(blob) and not _HAS_EXPLICIT_OBJECT.search(blob):
        return "UNDECIDABLE", "B-aviso procedural sem execução de obra explícita"

    for pat in _B_HARD_EXCLUDE:
        if re.search(pat, blob, re.I):
            # allow override if explicit obra execution also present
            if re.search(
                r"\b(execucao\s+de\s+obra|empreitada|pavimentacao\s+asfalt|"
                r"construcao\s+de\s+escola|reforma\s+predial)\b",
                blob,
                re.I,
            ):
                break
            return "IRRELEVANT", f"B-hard-exclude: {pat}"

    hits = [pat for pat in _B_ENG_EXEC if re.search(pat, blob, re.I)]
    if hits:
        return "RELEVANT", f"B-eng-exec hits={len(hits)}"

    if re.search(r"\b(obra|engenharia|edific|infraestrutura)\b", blob, re.I):
        return "UNDECIDABLE", "B-termo de obra genérico sem execução clara"

    return "IRRELEVANT", "B-sem sinal de execução de engenharia"


def adjudicate(
    label_a: str,
    reason_a: str,
    label_b: str,
    reason_b: str,
    objeto: str,
) -> tuple[str, str, bool]:
    """Adjudicate dual labels. Returns (final, reason, agreed)."""
    if label_a == label_b:
        return label_a, f"agreement:{label_a}", True

    blob = _norm(objeto)

    # Prefer UNDECIDABLE over silent conversion to IRRELEVANT
    if "UNDECIDABLE" in {label_a, label_b}:
        other = label_b if label_a == "UNDECIDABLE" else label_a
        if other == "RELEVANT":
            # strong eng execution → RELEVANT
            if any(re.search(p, blob, re.I) for p in _B_ENG_EXEC[:8]):
                return (
                    "RELEVANT",
                    f"adjudication: undecidable+relevant → RELEVANT ({reason_a}|{reason_b})",
                    False,
                )
            return (
                "UNDECIDABLE",
                f"adjudication: keep UNDECIDABLE ({reason_a}|{reason_b})",
                False,
            )
        # UNDECIDABLE + IRRELEVANT → stay UNDECIDABLE (never silent IRRELEVANT)
        return (
            "UNDECIDABLE",
            f"adjudication: undecidable+irrelevant stays UNDECIDABLE ({reason_a}|{reason_b})",
            False,
        )

    # RELEVANT vs IRRELEVANT
    eng_strong = any(re.search(p, blob, re.I) for p in _B_ENG_EXEC[:10])
    excl_strong = any(re.search(p, blob, re.I) for p in _B_HARD_EXCLUDE[:8])
    if eng_strong and not excl_strong:
        return (
            "RELEVANT",
            f"adjudication: RELEVANT wins on eng_exec ({reason_a}|{reason_b})",
            False,
        )
    if excl_strong and not eng_strong:
        return (
            "IRRELEVANT",
            f"adjudication: IRRELEVANT wins on exclusion ({reason_a}|{reason_b})",
            False,
        )
    return (
        "UNDECIDABLE",
        f"adjudication: unresolved conflict ({reason_a}|{reason_b})",
        False,
    )


def dual_label_record(rec: dict[str, Any]) -> dict[str, Any]:
    obj = rec.get("objeto") or ""
    titulo = rec.get("titulo")
    la, ra = label_reviewer_a(obj, titulo=titulo)
    lb, rb = label_reviewer_b(obj, titulo=titulo)
    final, reason, agreed = adjudicate(la, ra, lb, rb, obj)
    out = dict(rec)
    out["label_reviewer_a"] = la
    out["label_reviewer_a_reason"] = ra
    out["label_reviewer_b"] = lb
    out["label_reviewer_b_reason"] = rb
    out["label_final"] = final
    out["adjudication_reason"] = reason
    out["labels_agreed"] = agreed
    out["reviewers"] = ["criteria_A_inclusion_first", "criteria_B_exclusion_first"]
    return out
