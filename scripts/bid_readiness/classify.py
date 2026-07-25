"""Document classification from content signals (filename alone insufficient)."""

from __future__ import annotations

import re
from typing import Any

from scripts.bid_readiness.models import DocType

# (type, content_patterns, filename_hints)
_RULES: list[tuple[DocType, list[str], list[str]]] = [
    (
        DocType.CERTIDAO_FEDERAL,
        [r"certid[aã]o\s+conjunta", r"receita\s+federal", r"pgfn"],
        ["cnd_federal", "certidao_federal"],
    ),
    (
        DocType.CERTIDAO_ESTADUAL,
        [r"fazenda\s+estadual", r"certid[aã]o\s+estadual"],
        ["certidao_estadual", "cnd_estadual"],
    ),
    (DocType.CERTIDAO_MUNICIPAL, [r"fazenda\s+municipal", r"certid[aã]o\s+municipal"], ["certidao_municipal"]),
    (DocType.FGTS, [r"\bfgts\b", r"crf\b", r"caixa\s+econ[oô]mica"], ["fgts", "crf"]),
    (DocType.CNDT, [r"cndt", r"d[eé]bitos\s+trabalhistas"], ["cndt"]),
    (DocType.CERTIDAO_FALENCIA, [r"fal[eê]ncia", r"recupera[cç][aã]o\s+judicial"], ["falencia"]),
    (DocType.CONTRATO_SOCIAL, [r"contrato\s+social", r"consolidado"], ["contrato_social"]),
    (DocType.ALTERACAO_CONTRATUAL, [r"altera[cç][aã]o\s+contratual"], ["alteracao"]),
    (
        DocType.CARTAO_CNPJ,
        [r"comprovante\s+de\s+inscri[cç][aã]o", r"cart[aã]o\s+cnpj", r"cadastro\s+nacional"],
        ["cartao_cnpj", "cnpj"],
    ),
    (DocType.BALANCO_PATRIMONIAL, [r"balan[cç]o\s+patrimonial", r"ativo\s+circulante"], ["balanco"]),
    (DocType.DRE, [r"demonstra[cç][aã]o\s+do\s+resultado", r"\bdre\b"], ["dre"]),
    (DocType.INDICES_CONTABEIS, [r"liquidez\s+corrente", r"[ií]ndices\s+cont[aá]beis"], ["indices"]),
    (
        DocType.ATESTADO_CAPACIDADE_TECNICA,
        [r"atestado\s+de\s+capacidade", r"atestamos\s+para\s+os\s+devidos"],
        ["atestado"],
    ),
    (DocType.CAT, [r"\bcat\b", r"certid[aã]o\s+de\s+acervo\s+t[eé]cnico"], ["cat_"]),
    (DocType.ART, [r"anota[cç][aã]o\s+de\s+responsabilidade\s+t[eé]cnica", r"\bart\b"], ["art_"]),
    (DocType.RRT, [r"registro\s+de\s+responsabilidade\s+t[eé]cnica", r"\brrt\b"], ["rrt_"]),
    (DocType.PROCURACAO, [r"procura[cç][aã]o", r"outorga\s+poderes"], ["procuracao"]),
    (DocType.DECLARACAO, [r"declar[oa]\s+para\s+os\s+devidos", r"declara[cç][aã]o"], ["declaracao"]),
    (DocType.PROPOSTA_COMERCIAL, [r"proposta\s+comercial", r"valor\s+global"], ["proposta"]),
    (DocType.PLANILHA_PRECOS, [r"planilha\s+de\s+pre[cç]os", r"pre[cç]o\s+unit[aá]rio"], ["planilha"]),
    (DocType.GARANTIA_PROPOSTA, [r"garantia\s+de\s+proposta", r"cau[cç][aã]o"], ["garantia"]),
    (DocType.DOCUMENTO_SIGNATARIO, [r"documento\s+do\s+signat[aá]rio", r"rg\s+e\s+cpf"], ["signatario", "rg_cpf"]),
    (DocType.VINCULO_PROFISSIONAL, [r"v[ií]nculo\s+empregat[ií]cio", r"contrato\s+de\s+trabalho"], ["vinculo"]),
    (
        DocType.REGISTRO_CONSELHO_EMPRESA,
        [r"registro\s+no\s+crea", r"certid[aã]o\s+de\s+registro\s+de\s+pessoa\s+jur"],
        ["crea_empresa"],
    ),
    (DocType.REGISTRO_CONSELHO_PROFISSIONAL, [r"carteira\s+profissional", r"crea\s+n"], ["crea_prof"]),
]


def classify_document(
    *,
    original_name: str,
    text: str,
    sidecar: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify document; filename alone never yields high confidence."""
    if sidecar and sidecar.get("document_type"):
        return {
            "classification": str(sidecar["document_type"]),
            "confidence": float(sidecar.get("classification_confidence", 0.95)),
            "signals": ["sidecar"],
            "rule": "sidecar_override",
            "version": "1.0",
            "evidence": "provided in sidecar metadata",
            "needs_review": False,
        }

    name_l = original_name.lower()
    text_l = (text or "").lower()
    best: DocType | None = None
    best_score = 0.0
    signals: list[str] = []
    rule = "none"

    for dtype, content_pats, name_hints in _RULES:
        score = 0.0
        local_signals: list[str] = []
        content_hit = False
        for pat in content_pats:
            if re.search(pat, text_l, re.I):
                score += 0.45
                content_hit = True
                local_signals.append(f"content:{pat}")
        name_hit = any(h in name_l for h in name_hints)
        if name_hit:
            score += 0.15 if content_hit else 0.05
            local_signals.append("filename_hint")
        if score > best_score:
            best_score = score
            best = dtype
            signals = local_signals
            rule = f"rule:{dtype.value}"

    if best is None or best_score < 0.2:
        return {
            "classification": DocType.UNKNOWN.value,
            "confidence": 0.1,
            "signals": signals or ["insufficient"],
            "rule": "fallback_unknown",
            "version": "1.0",
            "evidence": "no content signal",
            "needs_review": True,
        }

    # Filename alone without content → force low confidence + review
    if "filename_hint" in signals and not any(s.startswith("content:") for s in signals):
        return {
            "classification": best.value,
            "confidence": min(best_score, 0.25),
            "signals": signals,
            "rule": rule + "+filename_only_weak",
            "version": "1.0",
            "evidence": "filename hint without content proof",
            "needs_review": True,
        }

    conf = min(0.98, best_score)
    return {
        "classification": best.value,
        "confidence": round(conf, 3),
        "signals": signals,
        "rule": rule,
        "version": "1.0",
        "evidence": "; ".join(signals),
        "needs_review": conf < 0.5,
    }
