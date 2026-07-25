"""Checklist, timeline, missing annexes, consistency, risks, recommendation."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from scripts.edital_case import DISCLAIMER
from scripts.edital_case.extract import find_excerpt, full_text, load_extraction_blocks
from scripts.edital_case.models import ANNEX_PATTERNS, CHECKLIST_ITEMS, empty_evidence
from scripts.edital_case.store import read_json, utc_now, write_json

# Patterns for checklist analysis
_RULE_PATTERNS: dict[str, list[str]] = {
    "objeto_escopo": [
        r"(?:do\s+)?objeto\s*(?:da\s+(?:presente\s+)?(?:licita[cç][aã]o|contrata[cç][aã]o))?\s*[:\-–]?\s*.{10,220}",
        r"contrata[cç][aã]o\s+de\s+empresa\s+.{10,160}",
        r"registro\s+de\s+pre[cç]os\s+para\s+.{10,160}",
        r"o\s+objeto\s+da\s+presente",
    ],
    "datas_horarios": [
        r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b",
        r"data\s+de\s+(abertura|sess[aã]o|entrega|publica)",
        r"hor[aá]rio",
    ],
    "esclarecimentos_impugnacoes": [
        r"impugna[cç][aã]o",
        r"esclarecimento",
        r"pedido\s+de\s+esclarec",
    ],
    "modalidade": [
        r"pre[gğ][aã]o\s+eletr[oô]nico",
        r"concorr[eê]ncia",
        r"tomada\s+de\s+pre[cç]os",
        r"dispensa\s+de\s+licita",
        r"inexigibilidade",
        r"di[aá]logo\s+competitivo",
    ],
    "criterio_julgamento": [
        r"menor\s+pre[cç]o",
        r"t[eé]cnica\s+e\s+pre[cç]o",
        r"maior\s+desconto",
        r"crit[eé]rio\s+de\s+julgamento",
    ],
    "modo_disputa": [
        r"modo\s+de\s+disputa",
        r"aberto",
        r"fechado",
        r"aberto\s+e\s+fechado",
    ],
    "condicoes_participacao": [
        r"poder[aã]o\s+participar",
        r"n[aã]o\s+poder[aã]o\s+participar",
        r"condi[cç][oõ]es\s+de\s+participa",
    ],
    "consorcio": [r"cons[oó]rcio"],
    "subcontratacao": [r"subcontrata[cç]"],
    "habilitacao_juridica": [
        r"habilita[cç][aã]o\s+jur[ií]dica",
        r"ato\s+constitutivo",
        r"contrato\s+social",
    ],
    "regularidade_fiscal": [
        r"regularidade\s+fiscal",
        r"fazenda\s+nacional",
        r"FGTS",
        r"certid[aã]o\s+negativa",
    ],
    "regularidade_trabalhista": [
        r"regularidade\s+trabalhista",
        r"\bCNDT\b",
        r"justi[cç]a\s+do\s+trabalho",
    ],
    "qualificacao_economica": [
        r"qualifica[cç][aã]o\s+econ[oô]mico",
        r"balan[cç]o\s+patrimonial",
        r" demonstrações contábeis",
        r"demonstra[cç][oõ]es\s+cont[aá]beis",
    ],
    "capital_patrimonio": [
        r"capital\s+social\s+m[ií]nimo",
        r"patrim[oô]nio\s+l[ií]quido",
    ],
    "indices_economicos": [
        r"liquidez\s+geral",
        r"liquidez\s+corrente",
        r"solv[eê]ncia\s+geral",
        r"\bLG\b.*\bLC\b",
        r"índices?\s+cont[aá]beis",
    ],
    "garantia_proposta": [
        r"garantia\s+de\s+proposta",
        r"cau[cç][aã]o",
        r"garantia\s+da\s+proposta",
    ],
    "garantia_contrato": [
        r"garantia\s+contratual",
        r"garantia\s+de\s+execu[cç][aã]o",
        r"seguro.?garantia",
    ],
    "qualificacao_tecnica_operacional": [
        r"capacidade\s+t[eé]cnico.?operacional",
        r"qualifica[cç][aã]o\s+t[eé]cnica",
        r"atestado\s+de\s+capacidade\s+t[eé]cnica",
    ],
    "qualificacao_tecnica_profissional": [
        r"capacidade\s+t[eé]cnico.?profissional",
        r"profissional\s+de\s+n[ií]vel\s+superior",
        r"engenheiro",
        r"registro\s+no\s+CREA",
        r"\bCAU\b",
    ],
    "atestados_cat_art": [
        r"\bCAT\b",
        r"\bART\b",
        r"\bRRT\b",
        r"certid[aã]o\s+de\s+acervo\s+t[eé]cnico",
    ],
    "parcelas_relevancia": [
        r"parcelas?\s+de\s+maior\s+relev[aâ]ncia",
        r"itens?\s+de\s+maior\s+relev[aâ]ncia",
    ],
    "quantitativos_minimos": [
        r"quantitativo\s+m[ií]nimo",
        r"percentual\s+m[ií]nimo",
        r"\d+\s*%\s+do\s+(objeto|valor|quantitativo)",
    ],
    "visita_tecnica": [
        r"visita\s+t[eé]cnica",
        r"vistor\w+",
    ],
    "declaracoes_obrigatorias": [
        r"declara[cç][aã]o\s+de\s+que",
        r"declaro\s+para\s+os\s+devidos",
        r"modelos?\s+de\s+declara[cç]",
    ],
    "formato_proposta": [
        r"proposta\s+de\s+pre[cç]os?",
        r"validade\s+da\s+proposta",
        r"prazo\s+de\s+validade",
    ],
    "orcamento_estimado": [
        r"valor\s+estimado",
        r"or[cç]amento\s+estimativo",
        r"pre[cç]o\s+de\s+refer[eê]ncia",
        r"sigilo\s+do\s+or[cç]amento",
    ],
    "regime_execucao": [
        r"empreitada\s+por\s+pre[cç]o\s+global",
        r"empreitada\s+por\s+pre[cç]o\s+unit[aá]rio",
        r"regime\s+de\s+execu[cç][aã]o",
        r"contrata[cç][aã]o\s+integrada",
        r"contrata[cç][aã]o\s+semi[- ]?integrada",
    ],
    "reajuste": [
        r"reajuste",
        r"repactua[cç][aã]o",
        r"\bIPCA\b",
        r"\bINCC\b",
    ],
    "sancoes": [
        r"san[cç][oõ]es",
        r"multa\s+de",
        r"penalidades",
        r"impedimento\s+de\s+licitar",
    ],
    "riscos_contratuais": [
        r"matriz\s+de\s+riscos",
        r"riscos\s+contratuais",
        r"responsabilidade\s+da\s+contratad",
    ],
    "prazo_execucao": [
        r"prazo\s+de\s+execu[cç][aã]o",
        r"prazo\s+de\s+\d+\s+\(?\s*dias",
        r"cronograma",
    ],
    "local_obra": [
        r"local\s+da\s+(obra|presta[cç][aã]o|execu[cç][aã]o)",
        r"munic[ií]pio\s+de",
        r"endere[cç]o",
    ],
    "me_epp": [
        r"microempresa",
        r"empresa\s+de\s+pequeno\s+porte",
        r"\bME/EPP\b",
        r"LC\s*123",
        r"tratamento\s+diferenciado",
    ],
}

_DATE_PATTERNS = [
    (
        "publicacao",
        r"(publica[cç][aã]o|publicado\s+em|data\s+de\s+publica[cç][aã]o).{0,80}?(\d{1,2}[./]\d{1,2}[./]\d{2,4})",
    ),
    (
        "sessao",
        r"(sess[aã]o\s+p[uú]blica|abertura\s+da\s+sess[aã]o|in[ií]cio\s+da\s+sess[aã]o|disputa).{0,80}?(\d{1,2}[./]\d{1,2}[./]\d{2,4})",
    ),
    (
        "entrega_proposta",
        r"(entrega\s+da\s+proposta|recebimento\s+das\s+propostas|limite\s+para\s+envio|acolhimento\s+das\s+propostas).{0,100}?(\d{1,2}[./]\d{1,2}[./]\d{2,4})",
    ),
    (
        "entrega_proposta",
        r"(propostas?).{0,40}?(\d{1,2}[./]\d{1,2}[./]\d{2,4}).{0,40}?(encerr|at[eé]|limite)",
    ),
    (
        "impugnacao",
        r"(impugna[cç][aã]o|impugnar).{0,100}?(\d{1,2}[./]\d{1,2}[./]\d{2,4})",
    ),
    (
        "esclarecimento",
        r"(esclarecimento|esclarecimentos).{0,100}?(\d{1,2}[./]\d{1,2}[./]\d{2,4})",
    ),
    (
        "visita_tecnica",
        r"(visita\s+t[eé]cnica|vistoria).{0,80}?(\d{1,2}[./]\d{1,2}[./]\d{2,4})",
    ),
    (
        "validade_proposta",
        r"(validade\s+da\s+proposta).{0,40}?(\d{1,3})\s*dias",
    ),
    (
        "execucao",
        r"(prazo\s+de\s+execu[cç][aã]o|prazo\s+para\s+execu[cç][aã]o).{0,40}?(\d{1,4})\s*dias",
    ),
    # generic labeled dates often in summary tables
    (
        "abertura_proposta",
        r"(abertura|in[ií]cio).{0,30}?(proposta|propostas).{0,40}?(\d{1,2}[./]\d{1,2}[./]\d{2,4})",
    ),
    (
        "encerramento_proposta",
        r"(encerramento|fim).{0,30}?(proposta|propostas).{0,40}?(\d{1,2}[./]\d{1,2}[./]\d{2,4})",
    ),
]

def _normalize_date(raw: str) -> str | None:
    raw = raw.strip()
    for fmt in ("%d/%m/%Y", "%d.%m.%Y", "%d/%m/%y", "%d.%m.%y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def load_profile(profile_path: Path | None) -> dict[str, Any]:
    if not profile_path or not profile_path.is_file():
        return {"_status": "MISSING", "path": str(profile_path) if profile_path else None}
    try:
        data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
        data["_status"] = "LOADED"
        data["_path"] = str(profile_path)
        return data
    except Exception as exc:  # noqa: BLE001
        return {"_status": "ERROR", "error": str(exc), "path": str(profile_path)}


def profile_completeness(profile: dict[str, Any]) -> dict[str, Any]:
    """Detect fields that block GO when incomplete."""
    missing: list[str] = []
    if profile.get("_status") != "LOADED":
        return {
            "complete": False,
            "missing": ["profile_file"],
            "blocks_go": True,
            "reason": "perfil ausente ou ilegível",
        }
    region = profile.get("region") or {}
    if not region.get("uf_primary"):
        missing.append("region.uf_primary")
    if profile.get("minimum_value") is None and not (profile.get("value_band_soft") or {}):
        missing.append("value_guidance")
    # operational fields often incomplete by design
    pending_elicitation = []
    if not profile.get("priority_municipalities"):
        pending_elicitation.append("priority_municipalities")
    docs = profile.get("documents") or {}
    if not docs:
        pending_elicitation.append("documents_catalog")
    # GO blocked if key commercial constraints never elicited
    blocks_go = True  # fail-closed: profile alone never enough for GO without full elicitation
    return {
        "complete": len(missing) == 0 and len(pending_elicitation) == 0,
        "missing": missing,
        "pending_elicitation": pending_elicitation,
        "blocks_go": blocks_go,
        "reason": "perfil incompleto ou sem elicitation operacional completa"
        if blocks_go
        else "ok",
    }


def build_corpus(case_dir: Path, inventory: dict[str, Any]) -> dict[str, Any]:
    docs = []
    for d in inventory.get("documents") or []:
        did = d["document_id"]
        blocks = load_extraction_blocks(case_dir, did)
        docs.append(
            {
                **d,
                "blocks": blocks,
                "text": full_text(blocks),
            }
        )
    return {"documents": docs}


def _evidence_from_hit(
    hit: dict[str, Any] | None,
    doc: dict[str, Any] | None,
    *,
    rule_id: str,
    analysis: str,
    confidence: float,
) -> dict[str, Any]:
    ev = empty_evidence()
    ev["rule_id"] = rule_id
    ev["analysis"] = analysis
    ev["confidence"] = confidence
    if not hit or not doc:
        ev["review_status"] = "MISSING"
        return ev
    ev.update(
        {
            "document_id": doc.get("document_id"),
            "document_sha256": doc.get("sha256"),
            "page": hit.get("page"),
            "section": hit.get("section"),
            "paragraph": hit.get("paragraph"),
            "cell": hit.get("cell"),
            "locator": hit.get("locator"),
            "excerpt": hit.get("excerpt"),
            "review_status": "AUTO",
        }
    )
    return ev


def analyze_checklist(corpus: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    items_out: list[dict[str, Any]] = []
    docs = corpus.get("documents") or []

    for item_id, label, category, critical in CHECKLIST_ITEMS:
        if item_id == "aderencia_perfil":
            items_out.append(_analyze_profile_fit(docs, profile, item_id, label, category, critical))
            continue
        if item_id == "anexos_ausentes":
            # filled later / placeholder NEEDS cross
            items_out.append(
                {
                    "id": item_id,
                    "label": label,
                    "category": category,
                    "critical": critical,
                    "status": "MISSING_EVIDENCE",
                    "evidence": empty_evidence()
                    | {
                        "rule_id": "annex.cross",
                        "analysis": "preenchido após missing-documents",
                        "review_status": "PENDING_CROSS",
                    },
                }
            )
            continue
        if item_id == "inconsistencias":
            items_out.append(
                {
                    "id": item_id,
                    "label": label,
                    "category": category,
                    "critical": critical,
                    "status": "MISSING_EVIDENCE",
                    "evidence": empty_evidence()
                    | {
                        "rule_id": "consistency.cross",
                        "analysis": "preenchido após inconsistências",
                        "review_status": "PENDING_CROSS",
                    },
                }
            )
            continue

        patterns = _RULE_PATTERNS.get(item_id) or []
        best_hit = None
        best_doc = None
        for doc in docs:
            if doc.get("quality_status") == "EXTRACTION_FAILED":
                continue
            for pat in patterns:
                hit = find_excerpt(doc.get("blocks") or [], pat)
                if hit:
                    best_hit, best_doc = hit, doc
                    break
            if best_hit:
                break

        extraction_failed_all = bool(docs) and all(
            d.get("quality_status") in {"EXTRACTION_FAILED", "UNSUPPORTED"} for d in docs
        )
        ocr_only = bool(docs) and all(
            d.get("quality_status") == "OCR_REQUIRED" for d in docs
        )

        if extraction_failed_all:
            status = "EXTRACTION_FAILED"
            analysis = "extração falhou em todos os documentos"
            conf = 0.0
        elif ocr_only and not best_hit:
            status = "EXTRACTION_FAILED"
            analysis = "PDF sem camada textual (OCR_REQUIRED); não interpretar como ausência"
            conf = 0.0
        elif best_hit:
            # legal/interpretive items stay NEEDS_HUMAN
            if item_id in {
                "sancoes",
                "riscos_contratuais",
                "condicoes_participacao",
                "me_epp",
            }:
                status = "NEEDS_HUMAN"
                analysis = "trecho localizado; interpretação jurídica/comercial humana necessária"
                conf = 0.7
            elif item_id in {"garantia_proposta", "garantia_contrato", "visita_tecnica"}:
                status = "RISK"
                analysis = "exigência localizada; validar impacto operacional"
                conf = 0.75
            else:
                status = "SATISFIED"
                analysis = "trecho localizado no pacote documental"
                conf = 0.8
        else:
            status = "NOT_FOUND"
            analysis = "padrão não localizado no texto extraído"
            conf = 0.4

        items_out.append(
            {
                "id": item_id,
                "label": label,
                "category": category,
                "critical": critical,
                "status": status,
                "evidence": _evidence_from_hit(
                    best_hit,
                    best_doc,
                    rule_id=f"checklist.{item_id}",
                    analysis=analysis,
                    confidence=conf,
                ),
            }
        )

    return {
        "version": 2,
        "generated_at": utc_now(),
        "item_count": len(items_out),
        "items": items_out,
    }


def _analyze_profile_fit(
    docs: list[dict[str, Any]],
    profile: dict[str, Any],
    item_id: str,
    label: str,
    category: str,
    critical: bool,
) -> dict[str, Any]:
    comp = profile_completeness(profile)
    text = "\n".join(d.get("text") or "" for d in docs).lower()
    positive = [t.lower() for t in (profile.get("positive_terms") or [])]
    hits = [t for t in positive if t and t in text]
    objeto_hit = None
    for doc in docs:
        objeto_hit = find_excerpt(doc.get("blocks") or [], r"objeto[:\s].{10,200}")
        if objeto_hit:
            break

    if comp["blocks_go"]:
        status = "NEEDS_HUMAN"
        analysis = (
            f"perfil com pendências ({', '.join(comp.get('pending_elicitation') or comp.get('missing') or ['incompleto'])}); "
            f"termos positivos no texto: {hits[:5] or 'nenhum'}. Não autoriza GO automático."
        )
        conf = 0.5
    elif hits:
        status = "SATISFIED"
        analysis = f"aderência textual parcial: {hits[:5]}"
        conf = 0.7
    else:
        status = "RISK"
        analysis = "poucos sinais de aderência ao perfil no texto extraído"
        conf = 0.45

    doc0 = docs[0] if docs else None
    return {
        "id": item_id,
        "label": label,
        "category": category,
        "critical": critical,
        "status": status,
        "evidence": _evidence_from_hit(
            objeto_hit,
            doc0,
            rule_id="profile.fit",
            analysis=analysis,
            confidence=conf,
        ),
    }


def _fold_alnum(s: str) -> str:
    import unicodedata

    nk = unicodedata.normalize("NFKD", s or "")
    bare = "".join(c for c in nk if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "", bare)


# Aliases used to match referenced annex names to inventory filenames/types.
_TYPE_ALIASES: dict[str, list[str]] = {
    "TERMO_DE_REFERENCIA": [
        "termodereferencia",
        "termodereferencia",
        "termoreferencia",
        "tr",
    ],
    "ESTUDO_TECNICO_PRELIMINAR": [
        "estudotecnicopreliminar",
        "etp",
        "estudotecnico",
    ],
    "PLANILHA_ORCAMENTARIA": [
        "planilhaorcamentaria",
        "planilhaorcament",
        "orcamento",
    ],
    "CRONOGRAMA": ["cronograma", "cronogramafisicofinanceiro"],
    "MINUTA_CONTRATUAL": ["minutadocontrato", "minuta", "contrato", "aditivo"],
    "MEMORIAL_DESCRITIVO": ["memorialdescritivo", "memorial"],
    "BDI": ["bdi", "composicaodobdi"],
    "PROJETO": ["projetobasico", "projetoexecutivo", "projeto"],
    "EDITAL": ["edital"],
    "MODELO_DECLARACAO": ["modelodeproposta", "modelodedeclaracao", "declaracao"],
}


def _match_inventory_doc(
    *,
    referenced_name: str,
    expected_type: str,
    docs: list[dict[str, Any]],
) -> tuple[str | None, str, float]:
    """Return (matched_document_id, status, confidence)."""
    analyzable = [
        d
        for d in docs
        if (d.get("classification") or {}).get("result")
        not in {None, "UNSUPPORTED", "UNKNOWN"}
        and d.get("supported", True)
    ]
    ref_token = _fold_alnum(referenced_name)
    aliases = list(_TYPE_ALIASES.get(expected_type, []))
    aliases.append(ref_token)

    # 1) Exact classification type match
    if expected_type not in {"ANEXO", "UNKNOWN", "OUTRO"}:
        for d2 in analyzable:
            if (d2.get("classification") or {}).get("result") == expected_type:
                return d2.get("document_id"), "PRESENT", 0.85

    # 2) Filename alias / token match (accent-folded)
    for d2 in analyzable:
        n2 = _fold_alnum(d2.get("original_name") or "")
        if not n2:
            continue
        for alias in aliases:
            if not alias or len(alias) < 2:
                continue
            # short aliases like 'tr' / 'etp' must be boundary-ish
            if len(alias) <= 3:
                if re.search(rf"(?:^|[^a-z0-9]){re.escape(alias)}(?:[^a-z0-9]|$)", n2):
                    return d2.get("document_id"), "PRESENT", 0.8
            elif alias in n2 or n2 in alias:
                return d2.get("document_id"), "PRESENT", 0.78

    # 3) Content title signals only on docs already classified as that type
    # (prevents edital body *mentions* of "Planilha Orçamentária" from
    # counting as a present planilha document).
    title_pats = {
        "TERMO_DE_REFERENCIA": r"termo\s+de\s+refer[eê]ncia",
        "ESTUDO_TECNICO_PRELIMINAR": r"estudo\s+t[eé]cnico\s+preliminar",
        "PLANILHA_ORCAMENTARIA": r"planilha\s+or[cç]ament",
        "MINUTA_CONTRATUAL": r"minuta\s+(do\s+|de\s+)?contrato|contrato\s+administrativo",
        "MEMORIAL_DESCRITIVO": r"memorial\s+descritivo",
        "CRONOGRAMA": r"cronograma\s+f[ií]sico",
        "EDITAL": r"edital\s+de\s+(pre[gğ][aã]o|licita)",
    }
    pat = title_pats.get(expected_type)
    if pat:
        for d2 in analyzable:
            if (d2.get("classification") or {}).get("result") != expected_type:
                continue
            sample = (d2.get("text") or "")[:4000]
            if re.search(pat, sample, re.I):
                return d2.get("document_id"), "PRESENT", 0.82

    # 4) Generic "anexo N" without typed file → AMBIGUOUS never weak PRESENT
    if re.search(r"anexo", referenced_name, re.I):
        vague = [
            d2
            for d2 in analyzable
            if "anexo" in (d2.get("original_name") or "").lower()
        ]
        if vague:
            return vague[0].get("document_id") if len(vague) == 1 else None, "AMBIGUOUS", 0.4

    return None, "MISSING", 0.6


def detect_missing_documents(corpus: dict[str, Any]) -> dict[str, Any]:
    """Cross-reference annex mentions with inventory."""
    docs = corpus.get("documents") or []
    inventory_names = " ".join(
        f"{d.get('original_name','')} {d.get('classification',{}).get('result','')}"
        for d in docs
    ).lower()

    findings: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    for doc in docs:
        # Don't mine annex lists out of unsupported sidecars
        if (doc.get("classification") or {}).get("result") == "UNSUPPORTED":
            continue
        blocks = doc.get("blocks") or []
        for b in blocks:
            text = b.get("text") or ""
            if not text.strip():
                continue
            for pat, dtype in ANNEX_PATTERNS:
                for m in re.finditer(pat, text, re.I):
                    name = m.group(0)
                    key = re.sub(r"\s+", " ", name.lower())
                    # collapse accent variants in key
                    key = _fold_alnum(key) or key
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    matched_id, status, conf = _match_inventory_doc(
                        referenced_name=name,
                        expected_type=dtype if dtype != "ANEXO" else "ANEXO_ADMINISTRATIVO",
                        docs=docs,
                    )
                    # For bare ANEXO keep AMBIGUOUS path from matcher
                    if dtype == "ANEXO" and status == "PRESENT" and conf < 0.75:
                        status = "AMBIGUOUS"
                        conf = min(conf, 0.45)

                    start = max(0, m.start() - 60)
                    end = min(len(text), m.end() + 100)
                    findings.append(
                        {
                            "referenced_name": name,
                            "expected_type": dtype,
                            "referenced_from": {
                                "document_id": doc.get("document_id"),
                                "page": b.get("page"),
                                "section": None,
                                "locator": b.get("locator"),
                                "excerpt": text[start:end].strip(),
                            },
                            "matched_document_id": matched_id,
                            "status": status,
                            "confidence": conf,
                        }
                    )

    return {
        "generated_at": utc_now(),
        "references": findings,
        "missing_count": sum(1 for f in findings if f["status"] == "MISSING"),
        "ambiguous_count": sum(1 for f in findings if f["status"] == "AMBIGUOUS"),
        "present_count": sum(1 for f in findings if f["status"] == "PRESENT"),
        "inventory_fingerprint": sha_simple(inventory_names),
    }


def sha_simple(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def extract_timeline(corpus: dict[str, Any]) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for doc in corpus.get("documents") or []:
        text = doc.get("text") or ""
        blocks = doc.get("blocks") or []
        for kind, pat in _DATE_PATTERNS:
            for m in re.finditer(pat, text, re.I | re.S):
                raw = None
                if m.lastindex:
                    for gi in range(m.lastindex, 0, -1):
                        g = m.group(gi)
                        if g and re.search(r"\d", g):
                            raw = str(g).strip()
                            break
                if not raw:
                    continue
                norm = _normalize_date(raw) if re.search(r"[./]", raw) else None
                hit = find_excerpt(blocks, re.escape(raw))
                events.append(
                    {
                        "kind": kind,
                        "raw_value": raw,
                        "normalized": norm,
                        "timezone": "America/Sao_Paulo",
                        "document_id": doc.get("document_id"),
                        "document_sha256": doc.get("sha256"),
                        "page": (hit or {}).get("page"),
                        "locator": (hit or {}).get("locator"),
                        "excerpt": (hit or {}).get("excerpt")
                        or m.group(0)[:200].replace("\n", " "),
                        "confidence": 0.7
                        if norm or kind in {"validade_proposta", "execucao"}
                        else 0.5,
                        "classification": kind,
                    }
                )
    # conflicts on same kind different normalized
    conflicts = []
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        if e.get("normalized"):
            by_kind.setdefault(e["kind"], []).append(e)
    for kind, evs in by_kind.items():
        norms = {e["normalized"] for e in evs}
        if len(norms) > 1:
            conflicts.append(
                {
                    "kind": kind,
                    "values": sorted(norms),
                    "events": evs,
                    "class": "CONFIRMED_CONFLICT",
                }
            )
    return {
        "generated_at": utc_now(),
        "events": events,
        "conflicts": conflicts,
        "event_count": len(events),
    }


def extract_field(text: str, patterns: list[str]) -> str | None:
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if not m:
            continue
        if m.lastindex:
            for i in range(1, m.lastindex + 1):
                g = m.group(i)
                if g is not None and str(g).strip():
                    return str(g).strip()
        raw = m.group(0)
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    return None


def _normalize_compare_value(field: str, value: str) -> str:
    """Collapse format-only differences before conflict classification."""
    import unicodedata

    v = value or ""
    v = unicodedata.normalize("NFKD", v)
    v = "".join(c for c in v if not unicodedata.combining(c))
    v = v.lower()
    v = re.sub(r"[\r\n\t]+", " ", v)
    v = re.sub(r"\s+", " ", v).strip()
    v = v.strip(" :;,.|-–—")
    if field in {"valor_estimado", "numero_processo", "numero_edital", "bdi"}:
        digits = re.sub(r"\D", "", v)
        return digits or v
    if field in {
        "criterio_julgamento",
        "regime_execucao",
        "orgao",
        "consorcio",
        "subcontratacao",
        "visita_tecnica",
    }:
        v = re.sub(r"[^a-z0-9 %]+", " ", v)
        v = re.sub(r"\s+", " ", v).strip()
        return v
    if field == "garantia":
        # Keep only first 40 folded chars — different legal contexts often NOT_COMPARABLE
        v = re.sub(r"[^a-z0-9 ]+", " ", v)
        return re.sub(r"\s+", " ", v).strip()[:40]
    return v


def check_consistency(corpus: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "numero_processo": [r"processo\s*(?:licitat[oó]rio\s*)?n?[°ºo.]?\s*([0-9]{1,6}\s*/\s*[0-9]{2,4}|[0-9./-]{3,})"],
        "numero_edital": [
            r"(?:pre[gğ][aã]o\s+eletr[oô]nico|edital)\s*n?[°ºo.]?\s*([0-9]{1,4}\s*/\s*[0-9]{2,4})"
        ],
        "orgao": [
            r"(prefeitura\s+municipal\s+de\s+[a-záàâãéêíóôõúç\s]{2,40})",
            r"(universidade\s+[^\n]{5,60})",
        ],
        "valor_estimado": [
            r"valor\s+(total\s+)?estimado[^\dR$]{0,20}R\$\s*([\d.]+,\d{2})",
        ],
        "data_sessao": [
            r"(sess[aã]o|abertura)[^\d]{0,40}(\d{1,2}[./]\d{1,2}[./]\d{2,4})",
        ],
        "prazo_execucao": [r"prazo\s+de\s+execu[cç][aã]o[^\d]{0,20}(\d{1,4}\s*dias?)"],
        "criterio_julgamento": [r"(menor\s+pre[cç]o|t[eé]cnica\s+e\s+pre[cç]o|maior\s+desconto)"],
        "regime_execucao": [
            r"(empreitada\s+por\s+pre[cç]o\s+(global|unit[aá]rio)|contrata[cç][aã]o\s+integrada)"
        ],
        "consorcio": [r"cons[oó]rcio[^\n.]{0,80}"],
        "subcontratacao": [r"subcontrata[cç][aã]o[^\n.]{0,80}"],
        "garantia": [r"garantia\s+(?:de\s+)?(?:proposta|contratual|execu[cç][aã]o|m[ií]nima)[^\n.]{0,80}"],
        "visita_tecnica": [r"visita\s+t[eé]cnica[^\n.]{0,100}"],
        "bdi": [r"BDI[^\n%]{0,40}(\d{1,2}[,.]?\d*\s*%)"],
    }
    per_doc: dict[str, dict[str, str | None]] = {}
    for doc in corpus.get("documents") or []:
        if (doc.get("classification") or {}).get("result") == "UNSUPPORTED":
            continue
        text = doc.get("text") or ""
        extracted: dict[str, str | None] = {}
        for field, pats in fields.items():
            raw = extract_field(text, pats)
            # discard garbage extractions (single punctuation, too short)
            if raw is not None and len(re.sub(r"\W+", "", raw)) < 2:
                raw = None
            extracted[field] = raw
        per_doc[doc["document_id"]] = extracted

    inconsistencies: list[dict[str, Any]] = []
    for field in fields:
        values = {
            did: vals[field]
            for did, vals in per_doc.items()
            if vals.get(field)
        }
        if len(values) <= 1:
            continue
        raw_uniq = set(values.values())
        if len(raw_uniq) <= 1:
            continue
        norms = {_normalize_compare_value(field, v) for v in raw_uniq if v}
        norms.discard("")
        if len(norms) <= 1:
            cls = "FORMAT_VARIATION"
        elif field == "garantia" and len(norms) > 1:
            # Different legal senses of "garantia" across edital/TR/contrato
            # are often not apples-to-apples
            cls = "NOT_COMPARABLE"
        elif field in {"orgao", "criterio_julgamento", "subcontratacao", "consorcio"}:
            # if normalized still differs after fold, still possible conflict
            # but require substantial token difference
            tokens = {frozenset(n.split()) for n in norms}
            if len(tokens) == 1:
                cls = "FORMAT_VARIATION"
            else:
                # intersection of significant tokens
                sets = list(tokens)
                inter = sets[0]
                for s in sets[1:]:
                    inter = inter & s
                if inter and all(len(inter) / max(len(s), 1) >= 0.6 for s in sets):
                    cls = "FORMAT_VARIATION"
                else:
                    cls = "CONFIRMED_CONFLICT"
        else:
            cls = "CONFIRMED_CONFLICT"
        # FORMAT_VARIATION and NOT_COMPARABLE are recorded but not blockers by default
        inconsistencies.append(
            {
                "field": field,
                "values": values,
                "normalized": {k: _normalize_compare_value(field, v or "") for k, v in values.items()},
                "class": cls,
                "analysis": f"divergência em {field} entre documentos ({cls})",
            }
        )
    return {
        "generated_at": utc_now(),
        "per_document_fields": per_doc,
        "inconsistencies": inconsistencies,
        "count": len(inconsistencies),
        "confirmed_conflict_count": sum(
            1 for i in inconsistencies if i.get("class") == "CONFIRMED_CONFLICT"
        ),
    }


def build_requirements_matrix(
    checklist: dict[str, Any],
    timeline: dict[str, Any],
    missing: dict[str, Any],
) -> dict[str, Any]:
    rows = []
    for item in checklist.get("items") or []:
        ev = item.get("evidence") or {}
        rows.append(
            {
                "requisito": item.get("label"),
                "id": item.get("id"),
                "categoria": item.get("category"),
                "obrigatorio": item.get("critical"),
                "condicao": None,
                "documento": ev.get("document_id"),
                "localizador": ev.get("locator"),
                "texto_fonte": ev.get("excerpt"),
                "interpretacao": ev.get("analysis"),
                "risco": item.get("status"),
                "status": item.get("status"),
                "acao_humana": item.get("status")
                in {"NEEDS_HUMAN", "MISSING_EVIDENCE", "NOT_FOUND", "BLOCKER", "RISK"},
            }
        )
    for ev in timeline.get("events") or []:
        rows.append(
            {
                "requisito": f"Prazo/evento: {ev.get('kind')}",
                "id": f"timeline.{ev.get('kind')}",
                "categoria": "prazo",
                "obrigatorio": True,
                "condicao": None,
                "documento": ev.get("document_id"),
                "localizador": ev.get("locator"),
                "texto_fonte": ev.get("excerpt"),
                "interpretacao": f"raw={ev.get('raw_value')} normalized={ev.get('normalized')}",
                "risco": "OK" if ev.get("normalized") else "NEEDS_HUMAN",
                "status": "SATISFIED" if ev.get("normalized") else "NEEDS_HUMAN",
                "acao_humana": not bool(ev.get("normalized")),
            }
        )
    for ref in missing.get("references") or []:
        if ref.get("status") in {"MISSING", "AMBIGUOUS"}:
            rows.append(
                {
                    "requisito": f"Documento referido: {ref.get('referenced_name')}",
                    "id": "missing." + re.sub(r"\W+", "_", (ref.get("referenced_name") or "")[:40]),
                    "categoria": "administrativo",
                    "obrigatorio": True,
                    "condicao": None,
                    "documento": (ref.get("referenced_from") or {}).get("document_id"),
                    "localizador": (ref.get("referenced_from") or {}).get("locator"),
                    "texto_fonte": (ref.get("referenced_from") or {}).get("excerpt"),
                    "interpretacao": f"status={ref.get('status')}",
                    "risco": ref.get("status"),
                    "status": "BLOCKER" if ref.get("status") == "MISSING" else "NEEDS_HUMAN",
                    "acao_humana": True,
                }
            )
    return {"generated_at": utc_now(), "rows": rows, "row_count": len(rows)}


def build_findings(
    checklist: dict[str, Any],
    timeline: dict[str, Any],
    missing: dict[str, Any],
    consistency: dict[str, Any],
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    fid = 0

    def add(
        *,
        severity: str,
        category: str,
        title: str,
        evidence: dict[str, Any],
        status: str,
    ) -> None:
        nonlocal fid
        fid += 1
        findings.append(
            {
                "finding_id": f"F{fid:04d}",
                "severity": severity,
                "category": category,
                "title": title,
                "status": status,
                "evidence": evidence,
            }
        )

    for item in checklist.get("items") or []:
        st = item.get("status")
        if st in {"SATISFIED", "NOT_APPLICABLE"}:
            if st == "SATISFIED":
                add(
                    severity="info",
                    category=item.get("category") or "checklist",
                    title=f"Checklist OK: {item.get('label')}",
                    evidence=item.get("evidence") or {},
                    status=st,
                )
            continue
        sev = {
            "BLOCKER": "critical",
            "RISK": "high",
            "NEEDS_HUMAN": "medium",
            "NOT_FOUND": "medium",
            "MISSING_EVIDENCE": "high",
            "EXTRACTION_FAILED": "critical",
        }.get(st, "low")
        add(
            severity=sev,
            category=item.get("category") or "checklist",
            title=f"Checklist {st}: {item.get('label')}",
            evidence=item.get("evidence") or {},
            status=st,
        )

    for c in timeline.get("conflicts") or []:
        add(
            severity="critical",
            category="prazo",
            title=f"Conflito de datas em {c.get('kind')}: {c.get('values')}",
            evidence={
                "rule_id": "timeline.conflict",
                "excerpt": str(c.get("values")),
                "analysis": "datas divergentes entre documentos",
                "confidence": 0.9,
            },
            status="BLOCKER",
        )

    for ref in missing.get("references") or []:
        if ref.get("status") == "MISSING":
            add(
                severity="high",
                category="anexo",
                title=f"Anexo ausente: {ref.get('referenced_name')}",
                evidence={
                    "document_id": (ref.get("referenced_from") or {}).get("document_id"),
                    "page": (ref.get("referenced_from") or {}).get("page"),
                    "locator": (ref.get("referenced_from") or {}).get("locator"),
                    "excerpt": (ref.get("referenced_from") or {}).get("excerpt"),
                    "rule_id": "missing.annex",
                    "confidence": ref.get("confidence"),
                    "analysis": "referenciado mas não presente no inventário",
                },
                status="BLOCKER",
            )
        elif ref.get("status") == "AMBIGUOUS":
            add(
                severity="medium",
                category="anexo",
                title=f"Referência ambígua: {ref.get('referenced_name')}",
                evidence={
                    "document_id": (ref.get("referenced_from") or {}).get("document_id"),
                    "excerpt": (ref.get("referenced_from") or {}).get("excerpt"),
                    "rule_id": "missing.ambiguous",
                    "confidence": ref.get("confidence"),
                    "analysis": "não marcar PRESENT por aproximação fraca",
                },
                status="NEEDS_HUMAN",
            )

    for inc in consistency.get("inconsistencies") or []:
        cls = inc.get("class")
        if cls == "FORMAT_VARIATION":
            sev, st = "low", "RISK"
        elif cls == "NOT_COMPARABLE":
            sev, st = "info", "NEEDS_HUMAN"
        elif cls == "CONFIRMED_CONFLICT":
            sev, st = "critical", "BLOCKER"
        else:
            sev, st = "medium", "RISK"
        add(
            severity=sev,
            category="consistency",
            title=f"Inconsistência ({cls}): {inc.get('field')}",
            evidence={
                "rule_id": "consistency.field",
                "analysis": inc.get("analysis"),
                "excerpt": str(inc.get("values"))[:500],
                "confidence": 0.85,
            },
            status=st,
        )

    return {
        "generated_at": utc_now(),
        "findings": findings,
        "count": len(findings),
        "by_severity": {
            s: sum(1 for f in findings if f["severity"] == s)
            for s in ("critical", "high", "medium", "low", "info")
        },
    }


def build_risk_register(findings: dict[str, Any]) -> dict[str, Any]:
    risks = []
    for f in findings.get("findings") or []:
        if f.get("severity") in {"critical", "high", "medium"} and f.get("status") != "SATISFIED":
            risks.append(
                {
                    "risk_id": f.get("finding_id"),
                    "title": f.get("title"),
                    "severity": f.get("severity"),
                    "status": f.get("status"),
                    "evidence": f.get("evidence"),
                    "mitigation": "revisão humana obrigatória antes de decisão",
                }
            )
    return {"generated_at": utc_now(), "risks": risks, "count": len(risks)}


def recommend(
    checklist: dict[str, Any],
    findings: dict[str, Any],
    missing: dict[str, Any],
    consistency: dict[str, Any],
    profile: dict[str, Any],
    timeline: dict[str, Any],
) -> dict[str, Any]:
    items = checklist.get("items") or []
    blockers = [
        i
        for i in items
        if i.get("status") in {"BLOCKER", "EXTRACTION_FAILED"} and i.get("critical")
    ]
    missing_essential = [
        r
        for r in (missing.get("references") or [])
        if r.get("status") == "MISSING"
        and (r.get("expected_type") in {
            "TERMO_DE_REFERENCIA",
            "PLANILHA_ORCAMENTARIA",
            "EDITAL",
            "MINUTA_CONTRATUAL",
            "PROJETO",
        } or re.search(r"termo de refer|planilha|edital|minuta|projeto b", (r.get("referenced_name") or ""), re.I))
    ]
    confirmed_conflicts = [
        c
        for c in (consistency.get("inconsistencies") or [])
        if c.get("class") == "CONFIRMED_CONFLICT"
    ]
    date_conflicts = timeline.get("conflicts") or []
    comp = profile_completeness(profile)

    # NO_GO deterministic checks
    no_go_reasons: list[str] = []
    # deadline already passed — if we have entrega/sessao normalized before today
    today = datetime.now(UTC).date().isoformat()
    for ev in timeline.get("events") or []:
        if ev.get("kind") in {"sessao", "entrega_proposta"} and ev.get("normalized"):
            if ev["normalized"] < today:
                no_go_reasons.append(
                    f"prazo {ev['kind']} já vencido ({ev['normalized']})"
                )

    # object clearly out of scope vs negative — only if strong evidence
    # keep conservative: don't NO_GO on weak signals

    favorable = [
        i.get("label")
        for i in items
        if i.get("status") == "SATISFIED"
    ][:15]
    impeditivos = [i.get("label") for i in blockers] + [
        r.get("referenced_name") for r in missing_essential
    ]
    impeditivos += [c.get("field") for c in confirmed_conflicts]
    impeditivos += [f"conflito datas {c.get('kind')}" for c in date_conflicts]

    recommendation = "REVIEW"
    reasons = []

    if no_go_reasons:
        recommendation = "NO_GO"
        reasons = no_go_reasons
    else:
        # GO only under strict conditions — profile incompleteness always blocks
        critical_ok = all(
            i.get("status") in {"SATISFIED", "NOT_APPLICABLE"}
            for i in items
            if i.get("critical")
        )
        if (
            critical_ok
            and not blockers
            and not missing_essential
            and not confirmed_conflicts
            and not date_conflicts
            and not comp["blocks_go"]
        ):
            recommendation = "GO"
            reasons = ["todos os critérios estritos de GO atendidos"]
        else:
            recommendation = "REVIEW"
            if comp["blocks_go"]:
                reasons.append("perfil Extra incompleto / pending elicitation")
            if blockers:
                reasons.append(f"{len(blockers)} itens críticos bloqueantes")
            if missing_essential:
                reasons.append(f"{len(missing_essential)} anexos essenciais ausentes")
            if confirmed_conflicts or date_conflicts:
                reasons.append("conflitos documentais/datas")
            if not critical_ok:
                reasons.append("itens críticos sem evidência plena")
            if not reasons:
                reasons.append("fail-closed default REVIEW")

    return {
        "generated_at": utc_now(),
        "recommendation": recommendation,
        "reasons": reasons,
        "favorable": favorable,
        "impeditive": impeditivos,
        "missing_information": (comp.get("missing") or [])
        + (comp.get("pending_elicitation") or []),
        "next_actions": [
            "Revisar findings críticos com evidências",
            "Obter anexos ausentes junto ao órgão",
            "Completar elicitation do perfil Extra",
            "Decisão humana de go/no-go comercial",
            "Não usar este pack como parecer jurídico",
        ],
        "disclaimer": DISCLAIMER,
        "profile_completeness": comp,
        "counts": {
            "checklist_items": len(items),
            "blockers": len(blockers),
            "missing_essential": len(missing_essential),
            "conflicts": len(confirmed_conflicts) + len(date_conflicts),
            "findings": findings.get("count") or 0,
        },
    }


def patch_cross_checklist(
    checklist: dict[str, Any],
    missing: dict[str, Any],
    consistency: dict[str, Any],
    timeline: dict[str, Any],
) -> dict[str, Any]:
    """Update anexos_ausentes and inconsistencias items after cross analysis."""
    items = checklist.get("items") or []
    for item in items:
        if item.get("id") == "anexos_ausentes":
            miss = missing.get("missing_count") or 0
            amb = missing.get("ambiguous_count") or 0
            if miss:
                item["status"] = "BLOCKER"
                item["evidence"] = empty_evidence() | {
                    "rule_id": "annex.cross",
                    "analysis": f"{miss} anexos referidos ausentes; {amb} ambíguos",
                    "confidence": 0.8,
                    "excerpt": "; ".join(
                        r.get("referenced_name") or ""
                        for r in (missing.get("references") or [])
                        if r.get("status") == "MISSING"
                    )[:500],
                    "review_status": "AUTO",
                }
            elif amb:
                item["status"] = "NEEDS_HUMAN"
                item["evidence"] = empty_evidence() | {
                    "rule_id": "annex.cross",
                    "analysis": f"{amb} referências ambíguas",
                    "confidence": 0.6,
                    "review_status": "AUTO",
                }
            else:
                item["status"] = "SATISFIED"
                item["evidence"] = empty_evidence() | {
                    "rule_id": "annex.cross",
                    "analysis": "nenhum anexo referido como MISSING",
                    "confidence": 0.7,
                    "review_status": "AUTO",
                }
        if item.get("id") == "inconsistencias":
            confs = [
                c
                for c in (consistency.get("inconsistencies") or [])
                if c.get("class") == "CONFIRMED_CONFLICT"
            ]
            fmt = [
                c
                for c in (consistency.get("inconsistencies") or [])
                if c.get("class") == "FORMAT_VARIATION"
            ]
            dconf = timeline.get("conflicts") or []
            if confs or dconf:
                item["status"] = "BLOCKER"
                item["evidence"] = empty_evidence() | {
                    "rule_id": "consistency.cross",
                    "analysis": (
                        f"{len(confs)} conflitos confirmados de campo; "
                        f"{len(fmt)} variações de formato; {len(dconf)} de datas"
                    ),
                    "excerpt": str(
                        [c.get("field") for c in confs]
                        + [c.get("kind") for c in dconf]
                    )[:500],
                    "confidence": 0.85,
                    "review_status": "AUTO",
                }
            elif fmt:
                item["status"] = "RISK"
                item["evidence"] = empty_evidence() | {
                    "rule_id": "consistency.cross",
                    "analysis": f"{len(fmt)} variações de formato (não materiais)",
                    "excerpt": str([c.get("field") for c in fmt])[:500],
                    "confidence": 0.7,
                    "review_status": "AUTO",
                }
            else:
                item["status"] = "SATISFIED"
                item["evidence"] = empty_evidence() | {
                    "rule_id": "consistency.cross",
                    "analysis": "sem conflitos confirmados detectados",
                    "confidence": 0.65,
                    "review_status": "AUTO",
                }
    checklist["items"] = items
    return checklist


def run_analysis(case_dir: Path, profile_path: Path | None) -> dict[str, Any]:
    inventory = read_json(case_dir / "inventory.json")
    profile = load_profile(profile_path)
    corpus = build_corpus(case_dir, inventory)
    checklist = analyze_checklist(corpus, profile)
    missing = detect_missing_documents(corpus)
    timeline = extract_timeline(corpus)
    consistency = check_consistency(corpus)
    checklist = patch_cross_checklist(checklist, missing, consistency, timeline)
    # re-run findings after patch
    requirements = build_requirements_matrix(checklist, timeline, missing)
    findings = build_findings(checklist, timeline, missing, consistency)
    risks = build_risk_register(findings)
    rec = recommend(checklist, findings, missing, consistency, profile, timeline)

    evidence_matrix = {
        "generated_at": utc_now(),
        "entries": [
            {
                "finding_id": f.get("finding_id"),
                "title": f.get("title"),
                "document_id": (f.get("evidence") or {}).get("document_id"),
                "sha256": (f.get("evidence") or {}).get("document_sha256"),
                "locator": (f.get("evidence") or {}).get("locator"),
                "page": (f.get("evidence") or {}).get("page"),
                "excerpt": (f.get("evidence") or {}).get("excerpt"),
            }
            for f in findings.get("findings") or []
        ],
    }

    write_json(case_dir / "checklist.json", checklist)
    write_json(case_dir / "missing-documents.json", missing)
    write_json(case_dir / "timeline.json", timeline)
    write_json(case_dir / "inconsistencies.json", consistency)
    write_json(case_dir / "requirements.json", requirements)
    write_json(case_dir / "findings.json", findings)
    write_json(case_dir / "risk-register.json", risks)
    write_json(case_dir / "evidence-matrix.json", evidence_matrix)
    write_json(case_dir / "recommendation.json", rec)

    return {
        "checklist": checklist,
        "missing": missing,
        "timeline": timeline,
        "consistency": consistency,
        "requirements": requirements,
        "findings": findings,
        "risks": risks,
        "recommendation": rec,
        "evidence_matrix": evidence_matrix,
    }
