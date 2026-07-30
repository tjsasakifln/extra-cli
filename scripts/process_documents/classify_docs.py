"""Heuristic classification of public procurement document titles."""

from __future__ import annotations

import re
import unicodedata

from scripts.process_documents.statuses import DocumentCategory


def _norm(text: str) -> str:
    """Normalize titles/filenames for matching (accents, underscores, extensions)."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("_", " ").replace("-", " ")
    # Collapse encoding artifacts: REFER NCIA, T CNICO, OR AMENTO
    text = re.sub(r"\.(pdf|zip|docx?|xlsx?|odt|csv|json)\b", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text.lower()).strip()
    return text


# Ordered rules: first match wins. Keep specific before generic (anexo last-ish).
_RULES: list[tuple[re.Pattern[str], DocumentCategory]] = [
    # Notice / edital family
    (re.compile(r"\bedital\b|\bedital\d|\btexto de edital\b|\bcapa.?licit|\beditais\b"), DocumentCategory.EDITAL),
    (re.compile(r"\bpregao\b|\bpreg[aã]o\b|\bpe\s*\d|\bpe\b\s*\d"), DocumentCategory.EDITAL),
    (
        re.compile(
            r"\bconvite\b|\bcarta convite\b|\bconcorrencia\b|\btomada de precos\b|"
            r"\bcontratacao direta\b|\bcontrata[cç][aã]o direta\b"
        ),
        DocumentCategory.EDITAL,
    ),
    (re.compile(r"\bdispensa\b"), DocumentCategory.AVISO),
    (re.compile(r"\baviso\b|\baviso de licitacao\b|\bcomprovante de public"), DocumentCategory.AVISO),
    (re.compile(r"\bautoriza"), DocumentCategory.AVISO),
    (re.compile(r"\bretific"), DocumentCategory.RETIFICACAO),
    # TR / ETP / DFD (internal phase → notice pack)
    (
        re.compile(
            r"\btermo de refer|\btermo de refer ncia|\btr[_\s]?\d|\btr\b(?:\s|$)|"
            r"\breferencia\b|\brefer ncia\b"
        ),
        DocumentCategory.TERMO_REFERENCIA,
    ),
    (re.compile(r"\bestudo t|\betp\b|\betp\d|\btecnico preliminar|\bt cnico preliminar"), DocumentCategory.ESTUDO_TECNICO),
    (
        re.compile(
            r"\bdfd\b|formalizac|formaliza..o da demanda|documento de formalizacao|"
            r"oficializacao da demanda|documento de formalizacao de demanda"
        ),
        DocumentCategory.ESTUDO_TECNICO,
    ),
    (re.compile(r"\bmapa de risco|\bmapa de riscos\b"), DocumentCategory.ESTUDO_TECNICO),
    (re.compile(r"\bfase interna\b|\bdod\b"), DocumentCategory.ESTUDO_TECNICO),
    (re.compile(r"\bprojeto\b|\bpaviment|\bobra\b"), DocumentCategory.PROJETO),
    (re.compile(r"\bmemorial\b"), DocumentCategory.MEMORIAL),
    (re.compile(r"\bespecificac"), DocumentCategory.ESPECIFICACAO),
    (re.compile(r"\bplanilha\b|\bor amento|\borcament|\bor_amento|\borçamento"), DocumentCategory.PLANILHA_ORCAMENTARIA),
    (re.compile(r"\bcomposi[cç]"), DocumentCategory.COMPOSICAO),
    (re.compile(r"\bcronograma\b"), DocumentCategory.CRONOGRAMA),
    (re.compile(r"\bminuta\b"), DocumentCategory.MINUTA),
    (re.compile(r"\besclarec"), DocumentCategory.ESCLARECIMENTO),
    (re.compile(r"\bimpugnac"), DocumentCategory.IMPUGNACAO),
    # Session / judgment
    (re.compile(r"\bata\b.*\bsess|\bata de|\bata_de|\batas\b|\bata de registro"), DocumentCategory.ATA_SESSAO),
    (re.compile(r"\bdisputa\b|\blances\b|\bregistro de precos"), DocumentCategory.REGISTRO_DISPUTA),
    (re.compile(r"\bhabilitac"), DocumentCategory.HABILITACAO_JURIDICA),
    (re.compile(r"\bcertidao\b.*\bfederal|\bcnd\b|\bcndf\b"), DocumentCategory.DOCUMENTO_FISCAL),
    (re.compile(r"\bfgts\b|\bcndt\b|\btrabalh"), DocumentCategory.DOCUMENTO_TRABALHISTA),
    (re.compile(r"\bbalan[cç]o\b|\bfalenc|\bindice\b"), DocumentCategory.ECONOMICO_FINANCEIRO),
    (re.compile(r"\bqualificac[aã]o tecnica\b|\bqualificacao tecnica\b"), DocumentCategory.QUALIFICACAO_TECNICA),
    (re.compile(r"\bcat\b|certidao de acervo"), DocumentCategory.CAT),
    (re.compile(r"\bart\b|anota[cç][aã]o de responsabilidade"), DocumentCategory.ART),
    (re.compile(r"\brrt\b"), DocumentCategory.RRT),
    (re.compile(r"\batestado\b"), DocumentCategory.ATESTADO),
    (re.compile(r"\bproposta\b"), DocumentCategory.PROPOSTA_COMERCIAL),
    (re.compile(r"\bdiligenc"), DocumentCategory.DILIGENCIA),
    (re.compile(r"\bparecer tecnico\b"), DocumentCategory.PARECER_TECNICO),
    (re.compile(r"\bparecer jurid"), DocumentCategory.PARECER_JURIDICO),
    (re.compile(r"\bjustificativ|\brazao de escolha|\breconhecimento e ratificacao"), DocumentCategory.PARECER_JURIDICO),
    (re.compile(r"\binexigib|\bcredenciamento\b"), DocumentCategory.PARECER_JURIDICO),
    (re.compile(r"\badjudic"), DocumentCategory.ADJUDICACAO),
    (re.compile(r"\bhomolog"), DocumentCategory.HOMOLOGACAO),
    (re.compile(r"\bresultado\b|\bresultados\b"), DocumentCategory.RESULTADO),
    (re.compile(r"\bcontrato\b|\btexto de contrato\b"), DocumentCategory.CONTRATO),
    (re.compile(r"\bgarantia\b"), DocumentCategory.GARANTIA),
    (re.compile(r"\bordem de servi[cç]o\b"), DocumentCategory.ORDEM_SERVICO),
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
    """Classify a document from original_title / filename / free text."""
    norm = _norm(title)
    if not norm:
        return DocumentCategory.UNKNOWN.value
    for pattern, cat in _RULES:
        if pattern.search(norm):
            return cat.value
    return DocumentCategory.OUTRO.value


def classify_document_record(doc: dict) -> str:
    """Prefer existing strong category; reclassify from title fields when weak."""
    stored = (doc.get("document_category") or "").strip()
    title = (
        doc.get("original_title")
        or doc.get("original_filename")
        or doc.get("title")
        or doc.get("file_name")
        or ""
    )
    if stored and stored not in {
        DocumentCategory.OUTRO.value,
        DocumentCategory.UNKNOWN.value,
        "",
    }:
        # Still upgrade if title is richer and stored is generic contract-only? keep stored.
        return stored
    return classify_document_title(str(title))
