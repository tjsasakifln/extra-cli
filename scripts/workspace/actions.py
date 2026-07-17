"""Side-effect workspace actions: decide, edital analyze, proposal support."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from scripts.workspace.common import (
    EDITAL_WORKSPACE,
    PROPOSAL_WORKSPACE,
    load_ledger,
    load_overrides,
    save_json,
    save_ledger,
    save_overrides,
    slugify,
)

EDITAL_CHECKLIST = [
    ("habilitacao_juridica", "Habilitação jurídica completa e vigente"),
    ("regularidade_fiscal", "Regularidade fiscal federal/estadual/municipal"),
    ("regularidade_trabalhista", "CNDT / regularidade trabalhista"),
    ("qualificacao_tecnica", "Qualificação técnica (atestados CAT compatíveis)"),
    ("qualificacao_economica", "Qualificação econômico-financeira / índices"),
    ("garantia_proposta", "Garantia de proposta exigida e prazo"),
    ("garantia_contrato", "Garantia contratual estimada (se adjudicado)"),
    ("prazo_execucao", "Prazo de execução e cronograma exequível"),
    ("local_obra", "Local da obra/serviço e logística"),
    ("objeto_escopo", "Objeto e escopo alinhados ao perfil Extra"),
    ("visita_tecnica", "Visita técnica obrigatória? data e registro"),
    ("amostra_prototipo", "Amostra/protótipo exigido?"),
    ("orcamento_referencia", "Orçamento de referência / BDI / planilha"),
    ("me_epp", "Tratamento ME/EPP e cota reservada"),
    ("consorcio", "Consórcio permitido e condições"),
    ("subcontratacao", "Subcontratação limites e vedações"),
    ("criterio_julgamento", "Critério de julgamento (menor preço/técnica+preço)"),
    ("prazos_impugnacao", "Prazos de impugnação e esclarecimentos"),
    ("sancoes", "Sanções e multas desproporcionais"),
    ("riscos_contrato", "Riscos contratuais (reajuste, medições, ART)"),
]

PROPOSAL_DISCLAIMER = (
    "AVISO: este workspace é apoio operacional e NÃO substitui a "
    "responsabilidade técnica, jurídica ou comercial da proposta. "
    "Validação humana obrigatória antes de qualquer envio."
)


def decide_opportunity(
    *,
    opportunity_id: str,
    decision: str,
    reason: str,
    tags: list[str] | None = None,
    owner: str = "tiago",
    orgao: str = "",
    objeto: str = "",
    valor: float = 0.0,
) -> dict[str, Any]:
    """Record approve/reject/override in ledger + workspace_overrides."""
    decision_norm = decision.strip().lower()
    mapping = {
        "approve": "participar",
        "participar": "participar",
        "go": "participar",
        "reject": "nao_participar",
        "nao_participar": "nao_participar",
        "no_go": "nao_participar",
        "nogo": "nao_participar",
        "override": "reavaliar",
        "reavaliar": "reavaliar",
        "review": "reavaliar",
    }
    decisao = mapping.get(decision_norm)
    if decisao is None:
        raise ValueError(
            f"Decisão inválida: {decision}. Use approve|reject|override "
            "(ou participar|nao_participar|reavaliar)."
        )

    entry = {
        "id": None,
        "data_avaliacao": date.today().isoformat(),
        "opportunity_id": str(opportunity_id),
        "orgao": orgao or f"opp:{opportunity_id}",
        "edital": str(opportunity_id),
        "objeto": objeto or f"Decisão workspace sobre {opportunity_id}",
        "valor_estimado": valor,
        "decisao": decisao,
        "motivo": reason,
        "confianca": "alta" if decisao != "reavaliar" else "media",
        "pncp_id": str(opportunity_id),
        "notas": f"tags={','.join(tags or [])}; owner={owner}",
        "tags": tags or [],
        "owner": owner,
        "source": "workspace.decide",
    }

    ledger = load_ledger()
    entry["id"] = len(ledger.get("oportunidades") or []) + 1
    ledger.setdefault("oportunidades", []).append(entry)
    save_ledger(ledger)

    overrides = load_overrides()
    overrides.setdefault("overrides", []).append(
        {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "opportunity_id": str(opportunity_id),
            "decision": decisao,
            "reason": reason,
            "tags": tags or [],
            "owner": owner,
            "ledger_id": entry["id"],
        }
    )
    save_overrides(overrides)

    return {
        "status": "OK",
        "ledger_id": entry["id"],
        "decision": decisao,
        "opportunity_id": str(opportunity_id),
        "ledger_path": str(Path("data/extra_ledger.json")),
        "overrides_path": str(Path("data/workspace_overrides.json")),
    }


def scaffold_edital(path_or_url: str) -> dict[str, Any]:
    """Create edital analysis workspace with checklist and optional PDF extract."""
    is_url = path_or_url.lower().startswith(("http://", "https://"))
    source_path = None if is_url else Path(path_or_url).expanduser().resolve()
    base_name = path_or_url if is_url else (source_path.name if source_path else path_or_url)
    slug = slugify(Path(base_name).stem if not is_url else base_name)
    stamp = date.today().isoformat()
    folder = EDITAL_WORKSPACE / f"{stamp}_{slug}"
    folder.mkdir(parents=True, exist_ok=True)

    source_meta = {
        "source": path_or_url,
        "is_url": is_url,
        "local_path": str(source_path) if source_path else None,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "recommendation": "REVIEW",
        "recommendation_reason": (
            "GO nunca é inventado sem evidência. Checklist vazio → REVIEW obrigatório."
        ),
    }
    save_json(folder / "source.json", source_meta)

    checklist_items = []
    for key, label in EDITAL_CHECKLIST:
        checklist_items.append(
            {
                "id": key,
                "label": label,
                "status": "PENDING",
                "evidence": {
                    "page": None,
                    "section": None,
                    "quote": None,
                    "notes": "",
                },
                "risk": None,
            }
        )
    save_json(
        folder / "checklist.yaml.json",
        {
            "version": 1,
            "recommendation_default": "REVIEW",
            "items": checklist_items,
        },
    )

    # Human-readable MD checklist
    md_lines = [
        f"# Análise de Edital — {base_name}",
        "",
        f"- Criado: {source_meta['created_at']}",
        f"- Fonte: `{path_or_url}`",
        "- Recomendação default: **REVIEW** (sem evidência não há GO)",
        "",
        "## Checklist crítico",
        "",
    ]
    for i, (key, label) in enumerate(EDITAL_CHECKLIST, 1):
        md_lines.append(f"### {i}. {label}")
        md_lines.append(f"- id: `{key}`")
        md_lines.append("- status: PENDING")
        md_lines.append("- evidência página: _preencher_")
        md_lines.append("- evidência seção: _preencher_")
        md_lines.append("- citação: _preencher_")
        md_lines.append("")
    md_lines.extend(
        [
            "## Recomendação",
            "",
            "- [ ] REVIEW (default)",
            "- [ ] GO — somente com todas as evidências críticas preenchidas",
            "- [ ] NO_GO — com motivo e trecho do edital",
            "",
            "## Evidências faltantes",
            "",
            "- Todas as linhas do checklist acima (slots vazios).",
            "",
        ]
    )
    (folder / "checklist.md").write_text("\n".join(md_lines), encoding="utf-8")

    extract_status = "pending"
    extract_note = "PDF local não fornecido ou extrator indisponível."
    text_out = folder / "extracted_text.txt"

    if not is_url and source_path and source_path.exists() and source_path.suffix.lower() == ".pdf":
        text, how = _extract_pdf_text(source_path)
        if text:
            text_out.write_text(text, encoding="utf-8")
            extract_status = "ok"
            extract_note = f"Extraído via {how} ({len(text)} chars)."
        else:
            extract_status = "pending"
            extract_note = how

    save_json(
        folder / "extract_status.json",
        {"status": extract_status, "note": extract_note, "path": str(text_out) if extract_status == "ok" else None},
    )

    missing = [c[0] for c in EDITAL_CHECKLIST]
    return {
        "status": "PARTIAL",
        "folder": str(folder),
        "recommendation": "REVIEW",
        "missing_evidence": missing,
        "extract_status": extract_status,
        "extract_note": extract_note,
        "checklist_items": len(EDITAL_CHECKLIST),
    }


def scaffold_proposal(opp_id: str) -> dict[str, Any]:
    """Generate proposal support workspace folder."""
    slug = slugify(str(opp_id))
    folder = PROPOSAL_WORKSPACE / f"{date.today().isoformat()}_{slug}"
    folder.mkdir(parents=True, exist_ok=True)

    docs_checklist = [
        "Carta de apresentação / proposta comercial",
        "Proposta de preços (planilha)",
        "Declarações exigidas no edital",
        "Atestados de capacidade técnica (CATs)",
        "Documentos de habilitação jurídica",
        "Certidões de regularidade",
        "Comprovação de enquadramento ME/EPP (se aplicável)",
        "ART/RRT de elaboração da proposta (se exigido)",
        "Garantia de proposta (se exigida)",
        "Procuração / poderes do signatário",
    ]
    save_json(
        folder / "document_checklist.json",
        {
            "opportunity_id": str(opp_id),
            "items": [{"doc": d, "status": "PENDING", "path": None} for d in docs_checklist],
        },
    )

    matrix = {
        "opportunity_id": str(opp_id),
        "rows": [
            {
                "requirement": "Objeto compatível com perfil",
                "edital_ref": {"page": None, "section": None},
                "compliance": "PENDING",
                "evidence": None,
            },
            {
                "requirement": "Habilitação técnica",
                "edital_ref": {"page": None, "section": None},
                "compliance": "PENDING",
                "evidence": None,
            },
            {
                "requirement": "Habilitação econômico-financeira",
                "edital_ref": {"page": None, "section": None},
                "compliance": "PENDING",
                "evidence": None,
            },
            {
                "requirement": "Prazos e cronograma",
                "edital_ref": {"page": None, "section": None},
                "compliance": "PENDING",
                "evidence": None,
            },
            {
                "requirement": "Garantias",
                "edital_ref": {"page": None, "section": None},
                "compliance": "PENDING",
                "evidence": None,
            },
        ],
    }
    save_json(folder / "compliance_matrix.json", matrix)

    save_json(
        folder / "price_reference.json",
        {
            "status": "PLACEHOLDER",
            "note": "Preencher com workspace prices / contract_intel precos — não inventar.",
            "p25": None,
            "median": None,
            "p75": None,
            "sources": [],
        },
    )

    save_json(
        folder / "margin_scenarios.json",
        {
            "scenarios": [
                {"name": "conservador", "margin_pct": None, "notes": "PENDING elicitation margem_minima"},
                {"name": "base", "margin_pct": None, "notes": "PENDING"},
                {"name": "agressivo", "margin_pct": None, "notes": "PENDING — validar risco"},
            ],
            "disclaimer": PROPOSAL_DISCLAIMER,
        },
    )

    pending = [
        "Preencher checklist de documentos",
        "Completar matriz de conformidade com páginas do edital",
        "Rodar painel de preços e colar referências",
        "Definir cenários de margem com Tiago",
        "Revisão jurídica/técnica humana",
    ]
    save_json(folder / "pending_items.json", {"items": pending})

    (folder / "README.md").write_text(
        "\n".join(
            [
                f"# Apoio à Proposta — oportunidade {opp_id}",
                "",
                PROPOSAL_DISCLAIMER,
                "",
                "## Arquivos",
                "- `document_checklist.json`",
                "- `compliance_matrix.json`",
                "- `price_reference.json`",
                "- `margin_scenarios.json`",
                "- `pending_items.json`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (folder / "DISCLAIMER.txt").write_text(PROPOSAL_DISCLAIMER + "\n", encoding="utf-8")

    return {
        "status": "PARTIAL",
        "folder": str(folder),
        "opportunity_id": str(opp_id),
        "disclaimer": PROPOSAL_DISCLAIMER,
        "pending_items": pending,
    }


def _extract_pdf_text(path: Path) -> tuple[str | None, str]:
    """Try pypdf then pdfminer; never invent content."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        parts: list[str] = []
        for page in reader.pages[:50]:
            parts.append(page.extract_text() or "")
        text = "\n".join(parts).strip()
        if text:
            return text, "pypdf"
        return None, "pypdf instalado mas sem texto extraível (PDF escaneado?)."
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        pypdf_err = str(exc)
    else:
        pypdf_err = "pypdf sem texto"

    try:
        from pdfminer.high_level import extract_text

        text = (extract_text(str(path)) or "").strip()
        if text:
            return text, "pdfminer"
        return None, "pdfminer sem texto extraível."
    except ImportError:
        return None, f"Extrator PDF indisponível (pypdf/pdfminer). Último erro pypdf: {pypdf_err if 'pypdf_err' in dir() else 'not installed'}"
    except Exception as exc:  # noqa: BLE001
        return None, f"Falha pdfminer: {exc}"
