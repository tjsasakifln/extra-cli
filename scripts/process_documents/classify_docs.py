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
    (re.compile(r"\bprojetos?\b|\bpaviment|\bobra\b"), DocumentCategory.PROJETO),
    (re.compile(r"\bmemorial\b"), DocumentCategory.MEMORIAL),
    (re.compile(r"\bespecificac"), DocumentCategory.ESPECIFICACAO),
    # Licitante planilhas before generic orcamentaria
    (
        re.compile(
            r"\bplanilha do licitante|\bplanilha das licitantes|\bplanilha apresentada|"
            r"\bplanilhas?\b.*\blicitant|\blicitantes?\b.*\bplanilha|\bplanilha_licitante\b"
        ),
        DocumentCategory.PROPOSTA_COMERCIAL,
    ),
    (re.compile(r"\bplanilha\b|\bor amento|\borcament|\bor_amento|\borçamento|\bpesquisa de preco"), DocumentCategory.PLANILHA_ORCAMENTARIA),
    (re.compile(r"\bcomposi[cç]"), DocumentCategory.COMPOSICAO),
    (re.compile(r"\bcronograma\b"), DocumentCategory.CRONOGRAMA),
    (re.compile(r"\bminuta\b|\bminutado"), DocumentCategory.MINUTA),
    (re.compile(r"\besclarec|\bperguntas e respostas|\berrata\b"), DocumentCategory.ESCLARECIMENTO),
    (re.compile(r"\bimpugnac"), DocumentCategory.IMPUGNACAO),
    # Session / judgment
    (re.compile(r"\bata\b|\bata total|\batatotal|\batas\b|\bsessao\b|\bsessão\b"), DocumentCategory.ATA_SESSAO),
    (re.compile(r"\bdisputa\b|\blances\b|\bregistro de precos"), DocumentCategory.REGISTRO_DISPUTA),
    (re.compile(r"\bhabilitac"), DocumentCategory.HABILITACAO_JURIDICA),
    (re.compile(r"\bcertidao\b|\bcnd\b|\bcndf\b|\bregularidade fiscal"), DocumentCategory.DOCUMENTO_FISCAL),
    (re.compile(r"\bfgts\b|\bcndt\b|\btrabalh"), DocumentCategory.DOCUMENTO_TRABALHISTA),
    (re.compile(r"\bbalan[cç]o\b|\bfalenc|\bindice\b|\beconomico"), DocumentCategory.ECONOMICO_FINANCEIRO),
    (re.compile(r"\bqualificac|\batestado de capacidade"), DocumentCategory.QUALIFICACAO_TECNICA),
    (re.compile(r"\bcat\b|certidao de acervo"), DocumentCategory.CAT),
    (re.compile(r"\bart\b|anota[cç][aã]o de responsabilidade"), DocumentCategory.ART),
    (re.compile(r"\brrt\b"), DocumentCategory.RRT),
    (re.compile(r"\batestado\b"), DocumentCategory.ATESTADO),
    (re.compile(r"\bproposta\b"), DocumentCategory.PROPOSTA_COMERCIAL),
    (re.compile(r"\bdeclarac"), DocumentCategory.HABILITACAO_JURIDICA),
    (re.compile(r"\bdiligenc"), DocumentCategory.DILIGENCIA),
    (re.compile(r"\bparecer tecnico\b|\banalise_?\d|\ban[aá]lise\b"), DocumentCategory.PARECER_TECNICO),
    (re.compile(r"\bparecer jurid|\bparecer\b"), DocumentCategory.PARECER_JURIDICO),
    (re.compile(r"\bjustificativ|\brazao de escolha|\breconhecimento e ratificacao"), DocumentCategory.PARECER_JURIDICO),
    (re.compile(r"\binexigib|\bcredenciamento\b"), DocumentCategory.PARECER_JURIDICO),
    (re.compile(r"\badjudic"), DocumentCategory.ADJUDICACAO),
    (re.compile(r"\bhomolog"), DocumentCategory.HOMOLOGACAO),
    (re.compile(r"\bresultado\b|\bresultados\b"), DocumentCategory.RESULTADO),
    (re.compile(r"\bcontrato\b|\btexto de contrato\b|\bcontratos\b"), DocumentCategory.CONTRATO),
    (re.compile(r"\bgarantia\b"), DocumentCategory.GARANTIA),
    (re.compile(r"\bordem de servi[cç]o\b"), DocumentCategory.ORDEM_SERVICO),
    (re.compile(r"\bapostil"), DocumentCategory.APOSTILAMENTO),
    (re.compile(r"\baditiv"), DocumentCategory.TERMO_ADITIVO),
    (re.compile(r"\bsuspens"), DocumentCategory.SUSPENSAO),
    (re.compile(r"\brescis"), DocumentCategory.RESCISAO),
    (re.compile(r"\bsan[cç][aã]o\b|\binidon"), DocumentCategory.SANCAO),
    (re.compile(r"\brecurso\b"), DocumentCategory.RECURSO),
    (re.compile(r"\bcontrarraz"), DocumentCategory.CONTRARRAZAO),
    (re.compile(r"\banexo\b|\brelac..o de itens|\bens?velope\b"), DocumentCategory.ANEXO),
    (re.compile(r"\bdisp\b|\bdispensa\b"), DocumentCategory.AVISO),
    (re.compile(r"\bconc\b|\bconcorr"), DocumentCategory.EDITAL),
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


# Generic categories that may be upgraded when the title is more specific.
_GENERIC_STORED = frozenset(
    {
        DocumentCategory.OUTRO.value,
        DocumentCategory.UNKNOWN.value,
        DocumentCategory.ANEXO.value,
        "",
    }
)

# Specific families that should win over a stored generic "anexo".
_SPECIFIC_OVER_ANEXO = frozenset(
    {
        DocumentCategory.PROPOSTA_COMERCIAL.value,
        DocumentCategory.PLANILHA_LICITANTE.value,
        DocumentCategory.HABILITACAO_JURIDICA.value,
        DocumentCategory.DOCUMENTO_FISCAL.value,
        DocumentCategory.DOCUMENTO_TRABALHISTA.value,
        DocumentCategory.ECONOMICO_FINANCEIRO.value,
        DocumentCategory.QUALIFICACAO_TECNICA.value,
        DocumentCategory.CAT.value,
        DocumentCategory.ART.value,
        DocumentCategory.RRT.value,
        DocumentCategory.ATESTADO.value,
        DocumentCategory.EDITAL.value,
        DocumentCategory.TERMO_REFERENCIA.value,
        DocumentCategory.ESTUDO_TECNICO.value,
        DocumentCategory.PLANILHA_ORCAMENTARIA.value,
        DocumentCategory.HOMOLOGACAO.value,
        DocumentCategory.ADJUDICACAO.value,
        DocumentCategory.RESULTADO.value,
        DocumentCategory.ATA_SESSAO.value,
        DocumentCategory.CONTRATO.value,
    }
)


def classify_document_record(doc: dict) -> str:
    """Prefer existing strong category; upgrade generic anexo/outro from title."""
    stored = (doc.get("document_category") or "").strip()
    title = (
        doc.get("original_title")
        or doc.get("original_filename")
        or doc.get("title")
        or doc.get("file_name")
        or ""
    )
    title_cat = classify_document_title(str(title))
    if stored and stored not in _GENERIC_STORED:
        return stored
    # Upgrade generic stored categories when title yields a specific family.
    if title_cat in _SPECIFIC_OVER_ANEXO:
        return title_cat
    if title_cat not in {DocumentCategory.OUTRO.value, DocumentCategory.UNKNOWN.value}:
        return title_cat
    if stored == DocumentCategory.ANEXO.value:
        return stored
    # PNCP/CIGA public process pack files without descriptive titles are still
    # process documents (notice envelope). Prefer anexo over discarding as outro.
    source = str(doc.get("source_id") or "").lower()
    mime = str(doc.get("detected_mime") or doc.get("declared_mime") or "").lower()
    ext = str(doc.get("extension") or "").lower()
    url = str(doc.get("download_url") or "")
    is_process_blob = (
        "pdf" in mime
        or "zip" in mime
        or ext in {"pdf", "zip", "docx", "doc", "xlsx", "xls", "odt"}
        or "/arquivos/" in url
    )
    if is_process_blob and (
        source.startswith("pncp")
        or "pncp" in source
        or source.startswith("ciga")
        or "zip_member" in source
        or source.startswith("sc_compras")
    ):
        return DocumentCategory.ANEXO.value
    return title_cat if title_cat else DocumentCategory.OUTRO.value
