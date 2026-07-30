"""Heuristic classification of public procurement document titles."""

from __future__ import annotations

import re
import unicodedata

from scripts.process_documents.statuses import DocumentCategory


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text.lower()).strip()


_RULES: list[tuple[re.Pattern[str], DocumentCategory]] = [
    (re.compile(r"\bedital\b"), DocumentCategory.EDITAL),
    (re.compile(r"\baviso\b|\baviso de licitacao\b"), DocumentCategory.AVISO),
    (re.compile(r"\bretific"), DocumentCategory.RETIFICACAO),
    (re.compile(r"\btermo de referencia\b|\btr\b"), DocumentCategory.TERMO_REFERENCIA),
    (re.compile(r"\bestudo tecnico|\betp\b"), DocumentCategory.ESTUDO_TECNICO),
    (re.compile(r"\bprojeto\b"), DocumentCategory.PROJETO),
    (re.compile(r"\bmemorial\b"), DocumentCategory.MEMORIAL),
    (re.compile(r"\bespecificac"), DocumentCategory.ESPECIFICACAO),
    (re.compile(r"\bplanilha\b.*\bor[cç]ament|\bor[cç]ament"), DocumentCategory.PLANILHA_ORCAMENTARIA),
    (re.compile(r"\bcomposi[cç]"), DocumentCategory.COMPOSICAO),
    (re.compile(r"\bcronograma\b"), DocumentCategory.CRONOGRAMA),
    (re.compile(r"\bminuta\b"), DocumentCategory.MINUTA),
    (re.compile(r"\besclarec"), DocumentCategory.ESCLARECIMENTO),
    (re.compile(r"\bimpugnac"), DocumentCategory.IMPUGNACAO),
    (re.compile(r"\bata\b.*\bsess|\bata de"), DocumentCategory.ATA_SESSAO),
    (re.compile(r"\bdisputa\b|\blances\b"), DocumentCategory.REGISTRO_DISPUTA),
    (re.compile(r"\bhabilitac"), DocumentCategory.HABILITACAO_JURIDICA),
    (re.compile(r"\bcertidao\b.*\bfederal|\bcnd\b|\bcndf\b"), DocumentCategory.DOCUMENTO_FISCAL),
    (re.compile(r"\bfgts\b|\bcndt\b|\btrabalh"), DocumentCategory.DOCUMENTO_TRABALHISTA),
    (re.compile(r"\bbalan[cç]o\b|\bfalenc|\bindice\b"), DocumentCategory.ECONOMICO_FINANCEIRO),
    (re.compile(r"\bqualificac[aã]o tecnica\b"), DocumentCategory.QUALIFICACAO_TECNICA),
    (re.compile(r"\b\bcat\b|certidao de acervo"), DocumentCategory.CAT),
    (re.compile(r"\bart\b|anota[cç][aã]o de responsabilidade"), DocumentCategory.ART),
    (re.compile(r"\brrt\b"), DocumentCategory.RRT),
    (re.compile(r"\batestado\b"), DocumentCategory.ATESTADO),
    (re.compile(r"\bproposta\b"), DocumentCategory.PROPOSTA_COMERCIAL),
    (re.compile(r"\bdiligenc"), DocumentCategory.DILIGENCIA),
    (re.compile(r"\bparecer tecnico\b"), DocumentCategory.PARECER_TECNICO),
    (re.compile(r"\bparecer jurid"), DocumentCategory.PARECER_JURIDICO),
    (re.compile(r"\badjudic"), DocumentCategory.ADJUDICACAO),
    (re.compile(r"\bhomolog"), DocumentCategory.HOMOLOGACAO),
    (re.compile(r"\bresultado\b"), DocumentCategory.RESULTADO),
    (re.compile(r"\bcontrato\b"), DocumentCategory.CONTRATO),
    (re.compile(r"\bgarantia\b"), DocumentCategory.GARANTIA),
    (re.compile(r"\bordem de servi[cç]o\b|\bos\b"), DocumentCategory.ORDEM_SERVICO),
    (re.compile(r"\bapostil"), DocumentCategory.APOSTILAMENTO),
    (re.compile(r"\baditiv"), DocumentCategory.TERMO_ADITIVO),
    (re.compile(r"\bsuspens"), DocumentCategory.SUSPENSAO),
    (re.compile(r"\brescis"), DocumentCategory.RESCISAO),
    (re.compile(r"\bsan[cç][aã]o\b|\binidon"), DocumentCategory.SANCAO),
    (re.compile(r"\brecurso\b"), DocumentCategory.RECURSO),
    (re.compile(r"\bcontrarraz"), DocumentCategory.CONTRARRAZAO),
    (re.compile(r"\banexo\b"), DocumentCategory.ANEXO),
]


def classify_document_title(title: str) -> str:
    norm = _norm(title)
    if not norm:
        return DocumentCategory.UNKNOWN.value
    for pattern, cat in _RULES:
        if pattern.search(norm):
            return cat.value
    return DocumentCategory.OUTRO.value
